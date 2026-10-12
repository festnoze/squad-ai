"""Factory-owned remote Chromium in the exact product's NETNONE namespace.

Only constant supervisor code and integrity-locked packages enter the image.
There is no source mount, host port publication, Docker socket, host networking,
client-network exposure or host Chromium fallback. Docker/its Linux kernel are
the trusted outer boundary; this does not attest Chromium's internal sandbox.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import tarfile
import time
import threading
from importlib.metadata import version
from uuid import uuid4
from urllib.parse import urlsplit

from ..agents.runner import _run_tracked
from ..orchestrator.isolated_validation import RuntimeSession
from ..orchestrator.sandbox import _docker_call, _cleanup_container, _container_identity
from .support_adapter import AdapterUnavailable

PLAYWRIGHT_VERSION = "1.63.0"
BASE_IMAGE = "mcr.microsoft.com/playwright:v1.63.0-noble"
# Official manifest digest observed via Docker pull + MCR on 2026-10-12.
BASE_IMAGE_PIN = "mcr.microsoft.com/playwright@sha256:eff16c30e6f3f4af0a03fa4b706120d5e9b0891c344a27d64559aff5900a4a27"
PACKAGE_INTEGRITY = "sha512-+7ziBLidS4NaNCdt57SUDT+wYmmd5fmiQejUic/kb+YsYSCPyOOE9sebzMjNmQrsnNpDJqd4WHvV/8lfKfUDUg=="
CORE_INTEGRITY = "sha512-rYCsBF/M5HjUch52bbtVONEFjv6Xu8sm8h72dNlR5bzIE1fvC/bxgspzkjSfU+MweEMmPM8KJebG6nnyxo5mCg=="

# No product parameters become code, imports, paths, environment or shell text.
# The two argv are bounded ports. The random control token exists only in this
# process and private startup metadata, not container argv or durable receipts.
SERVER_SCRIPT = r"""'use strict';
const net = require('node:net');
const crypto = require('node:crypto');
const {chromium} = require('/opt/autospec-browser/node_modules/playwright');
const relayPort = Number(process.argv[1]), productPort = Number(process.argv[2]);
if (![relayPort, productPort].every(p => Number.isInteger(p) && p >= 1 && p <= 65535)) process.exit(2);
let relay, browserServer;
async function stop() {
  try { if (browserServer) await browserServer.close(); } catch (_) {}
  if (relay) relay.close();
  process.exit(0);
}
process.on('SIGTERM', stop); process.on('SIGINT', stop);
(async () => {
  if (relayPort !== productPort) {
    relay = net.createServer(client => {
      const upstream = net.connect({host:'127.0.0.1',port:productPort});
      client.on('error', () => upstream.destroy()); upstream.on('error', () => client.destroy());
      client.on('close', () => upstream.destroy()); upstream.on('close', () => client.destroy());
      client.pipe(upstream); upstream.pipe(client);
    });
    await new Promise((resolve,reject) => {relay.once('error',reject);relay.listen(relayPort,'127.0.0.1',resolve);});
  }
  browserServer = await chromium.launchServer({host:'127.0.0.1',port:0,
    wsPath:crypto.randomBytes(32).toString('hex'),headless:true,timeout:30000});
  const endpoint = new URL(browserServer.wsEndpoint());
  process.stdout.write(JSON.stringify({version:'1.63.0',control_port:Number(endpoint.port),
    control_path:endpoint.pathname,relay_port:relayPort})+'\n');
})().catch(() => {process.stderr.write('trusted browser startup failed\n');process.exit(1);});
"""


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def factory_context(base_image_id: str) -> tuple[str, str]:
    """An ASCII tar stream containing exactly three constant factory files."""
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", base_image_id):
        raise AdapterUnavailable("immutable factory base image required")
    package = {"name":"autospec-browser-factory","version":"1.0.0","private":True,
               "dependencies":{"playwright":PLAYWRIGHT_VERSION}}
    lock = {"name":package["name"],"version":package["version"],"lockfileVersion":3,"requires":True,
        "packages":{"":{"name":package["name"],"version":package["version"],"dependencies":package["dependencies"]},
            "node_modules/playwright":{"version":PLAYWRIGHT_VERSION,
                "resolved":f"https://registry.npmjs.org/playwright/-/playwright-{PLAYWRIGHT_VERSION}.tgz",
                "integrity":PACKAGE_INTEGRITY,"dependencies":{"playwright-core":PLAYWRIGHT_VERSION},
                "bin":{"playwright":"cli.js"},"engines":{"node":">=20"}},
            "node_modules/playwright-core":{"version":PLAYWRIGHT_VERSION,
                "resolved":f"https://registry.npmjs.org/playwright-core/-/playwright-core-{PLAYWRIGHT_VERSION}.tgz",
                "integrity":CORE_INTEGRITY,"bin":{"playwright-core":"cli.js"},"engines":{"node":">=20"}}}}
    dockerfile = (f"FROM {BASE_IMAGE_PIN}\nLABEL autospec.base_image_id={base_image_id}\nWORKDIR /opt/autospec-browser\n"
        "ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1\nCOPY package.json package-lock.json ./\n"
        "RUN npm ci --ignore-scripts --no-audit --no-fund --omit=optional --cache=/tmp/npm-cache "
        "&& rm -rf /tmp/npm-cache\nUSER 65532:65532\n")
    files = {"Dockerfile":dockerfile,"package.json":_json(package),"package-lock.json":_json(lock)}
    recipe = hashlib.sha256(_json({**files,"server":SERVER_SCRIPT}).encode("ascii")).hexdigest()
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for name, value in files.items():
            data = value.encode("ascii"); info = tarfile.TarInfo(name)
            info.size, info.mode, info.mtime = len(data), 0o644, 0
            archive.addfile(info, io.BytesIO(data))
    return stream.getvalue().decode("ascii"), recipe


def _inspect_image(docker, reference):
    result = _docker_call([docker,"image","inspect",reference],capture_output=True,text=True,timeout=10,check=False)
    if result.returncode: return None
    try:
        data = json.loads(result.stdout)[0]
        if not re.fullmatch(r"sha256:[a-f0-9]{64}",data["Id"]) or data["Os"] != "linux": raise ValueError
        return data
    except (ValueError,KeyError,IndexError,TypeError) as exc:
        raise AdapterUnavailable("browser image identity cannot be attested") from exc


def prepare_browser_image(*, docker="docker", timeout=300):
    """Networked source-free factory preparation; runtime itself has NETNONE.

    No product cwd/config, build context, build args, secrets, SSH or hooks are
    accepted. npm ci uses exact public tarball integrity and ignores scripts.
    """
    if type(timeout) not in {int,float} or not 1 <= timeout <= 900:
        raise AdapterUnavailable("bounded browser factory preparation required")
    base = _inspect_image(docker,BASE_IMAGE_PIN)
    if base is None:
        rc,_,_ = _run_tracked([docker,"pull",BASE_IMAGE_PIN],"",None,timeout)
        if rc: raise AdapterUnavailable("official browser base preparation failed (output withheld)")
        base = _inspect_image(docker,BASE_IMAGE_PIN)
    if base is None: raise AdapterUnavailable("official browser base absent after pull")
    context,recipe = factory_context(base["Id"])
    tag = "autospec-browser:pw-1.63.0-"+recipe[:16]
    image = _inspect_image(docker,tag)
    if image is None:
        rc,_,_ = _run_tracked([docker,"build","--network=default","--progress=plain","--label",
            "autospec.browser_recipe="+recipe,"--label","autospec.playwright="+PLAYWRIGHT_VERSION,"-t",tag,"-"],context,None,timeout)
        if rc: raise AdapterUnavailable("source-free browser factory build failed (output withheld)")
        image = _inspect_image(docker,tag)
    labels = (image or {}).get("Config",{}).get("Labels") or {}
    if image is None or labels.get("autospec.browser_recipe") != recipe or labels.get("autospec.playwright") != PLAYWRIGHT_VERSION:
        raise AdapterUnavailable("factory browser recipe/version cannot be attested")
    return image["Id"], {"base_image_id":base["Id"],"image_id":image["Id"],"recipe_sha256":recipe,
        "playwright":PLAYWRIGHT_VERSION,"package_integrity":PACKAGE_INTEGRITY,"core_integrity":CORE_INTEGRITY,
        "source_free":True,"install_hooks":False}


def browser_run_command(docker, image, parent_id, owner, name, relay_port, product_port):
    if not re.fullmatch(r"sha256:[a-f0-9]{64}",image) or not re.fullmatch(r"[a-f0-9]{64}",parent_id):
        raise AdapterUnavailable("immutable image and parent identities required")
    if not re.fullmatch(r"[a-f0-9]{32}",owner) or not re.fullmatch(r"autospec-sandbox-[a-f0-9]{32}",name):
        raise AdapterUnavailable("factory-generated browser ownership required")
    if any(type(p) is not int or not 1 <= p <= 65535 for p in (relay_port,product_port)):
        raise AdapterUnavailable("bounded browser relay ports required")
    return [docker,"run","-d","--name",name,"--label","autospec.run_id="+owner,"--label","autospec.kind=sandbox",
        "--pull","never","--network","container:"+parent_id,"--ipc","private","--init",
        "--user","65532:65532","--read-only","--cap-drop","ALL","--security-opt","no-new-privileges=true",
        "--memory","2g","--cpus","2","--pids-limit","256","--ulimit","nofile=1024:1024",
        "--tmpfs","/tmp:rw,nosuid,nodev,size=512m,mode=1777",
        "--tmpfs","/dev/shm:rw,nosuid,nodev,size=512m,mode=1777",
        "--env","HOME=/tmp","--workdir","/opt/autospec-browser","--entrypoint","node",image,
        "--eval",SERVER_SCRIPT,str(relay_port),str(product_port)]


class DockerBrowserSession:
    """Only an actual, active RuntimeSession grants the namespace capability."""
    def __init__(self, runtime: RuntimeSession, *, origin: str, image_id=None):
        if not isinstance(runtime,RuntimeSession):
            raise AdapterUnavailable("actual supervised product RuntimeSession required")
        parsed=urlsplit(origin)
        if parsed.scheme!="http" or parsed.hostname!="127.0.0.1" or parsed.path or parsed.query or parsed.fragment or parsed.username or origin!=runtime.origin:
            raise AdapterUnavailable("browser origin must equal the exact owned HTTP runtime origin")
        if parsed.port is None or image_id is not None and not re.fullmatch(r"sha256:[a-f0-9]{64}",image_id):
            raise AdapterUnavailable("invalid owned browser origin/image")
        self.runtime,self.docker,self.origin=runtime,runtime.docker,origin
        self.parent_id=runtime._assert_owned()
        self.relay_port,self.product_port=parsed.port,runtime.port
        self.owner,self.name=uuid4().hex,"autospec-sandbox-"+uuid4().hex
        self.image_id,self.identifier,self.tunnel=image_id,None,None
        self._endpoint=None;self.closed=False;self.receipt={}
        self.operation_lock=threading.RLock()
        self._assert_parent()

    def _assert_parent(self):
        value=self.runtime.inspect_configuration()
        if (self.runtime._assert_owned()!=self.parent_id or not re.fullmatch(r"[a-f0-9]{64}",self.parent_id)
                or value["container_id"]!=self.parent_id or value["network_mode"]!="none"
                or value["running"] is not True or value["published_ports"]
                or value["user"]!="65532:65532" or value["read_only"] is not True
                or value["privileged"] is not False or set(value["cap_drop"] or [])!={"ALL"}
                or set(value["security_opt"] or []) not in ({"no-new-privileges"},{"no-new-privileges=true"})):
            raise AdapterUnavailable("browser parent must remain the exact active unpublished NETNONE runtime")
        return value

    def _inspect(self):
        result=_docker_call([self.docker,"container","inspect",self.identifier],capture_output=True,text=True,timeout=5,check=False)
        try:
            data=json.loads(result.stdout)[0];host=data["HostConfig"];config=data["Config"];labels=config.get("Labels") or {}
            expected_env={"PATH":"/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin","LANG":"C.UTF-8","LC_ALL":"C.UTF-8",
                "PLAYWRIGHT_BROWSERS_PATH":"/ms-playwright","PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD":"1","HOME":"/tmp"}
            environment=dict(value.split("=",1) for value in config["Env"])
            if (result.returncode or data["Id"]!=self.identifier or data["Image"]!=self.image_id
                or labels.get("autospec.run_id")!=self.owner or labels.get("autospec.kind")!="sandbox"
                or data["State"]["Running"] is not True or config["User"]!="65532:65532"
                or config["Entrypoint"]!=["node"] or config["WorkingDir"]!="/opt/autospec-browser"
                or config["Cmd"]!=["--eval",SERVER_SCRIPT,str(self.relay_port),str(self.product_port)]
                or environment!=expected_env or len(config["Env"])!=len(expected_env)
                or host["NetworkMode"]!="container:"+self.parent_id or host["ReadonlyRootfs"] is not True
                or host["Privileged"] is not False or host.get("CapAdd") or set(host.get("CapDrop") or [])!={"ALL"}
                or set(host.get("SecurityOpt") or []) not in ({"no-new-privileges"},{"no-new-privileges=true"})
                or host.get("Binds") or host.get("PortBindings") or host.get("Devices") or host.get("ExtraHosts")
                or host.get("PidMode")!="" or host.get("IpcMode")!="private"
                or host.get("PidsLimit")!=256 or host.get("Memory")!=2*1024**3 or host.get("NanoCpus")!=2*10**9
                or any(m["Type"]!="tmpfs" or m["Destination"] not in {"/tmp","/dev/shm"} for m in data["Mounts"])
                or host.get("Tmpfs")!={"/tmp":"rw,nosuid,nodev,size=512m,mode=1777","/dev/shm":"rw,nosuid,nodev,size=512m,mode=1777"}): raise ValueError
            return {"container_id":data["Id"],"image_id":data["Image"],"parent_id":self.parent_id,
                "network_mode":host["NetworkMode"],"parent_network_mode":"none","published_ports":{},
                "user":config["User"],"read_only":True,"cap_drop":host["CapDrop"],"security_opt":host["SecurityOpt"],
                "binds":[],"database_mount":False,"client_network_exposed":False,"host_chromium":False}
        except (ValueError,TypeError,KeyError,IndexError) as exc:
            raise AdapterUnavailable("owned browser isolation configuration cannot be attested") from exc

    def start(self):
        with self.operation_lock:
            return self._start_owned()

    def _start_owned(self):
        if self.closed or self.identifier: raise AdapterUnavailable("browser session already started/closed")
        if version("playwright")!=PLAYWRIGHT_VERSION: raise AdapterUnavailable("locked Playwright client/server version mismatch")
        try:
            self._assert_parent()
            if self.image_id is None: self.image_id,self.receipt=prepare_browser_image(docker=self.docker)
            else:
                image=_inspect_image(self.docker,self.image_id)
                base=_inspect_image(self.docker,BASE_IMAGE_PIN)
                recipe=factory_context(base["Id"])[1] if base else None
                labels=(image or {}).get("Config",{}).get("Labels") or {}
                if not image or recipe is None or labels.get("autospec.playwright")!=PLAYWRIGHT_VERSION or labels.get("autospec.browser_recipe")!=recipe:
                    raise AdapterUnavailable("requested browser image is not a version-attested factory image")
            self._assert_parent()
            rc,out,_=_run_tracked(browser_run_command(self.docker,self.image_id,self.parent_id,self.owner,self.name,self.relay_port,self.product_port),"",None,30)
            self.identifier=_container_identity(self.docker,self.name,self.owner)
            if rc or self.identifier is None or out.strip()!=self.identifier:
                raise AdapterUnavailable("browser launch immutable identity mismatch")
            self.receipt.update(self._inspect())
            deadline=time.monotonic()+35
            while time.monotonic()<deadline:
                self._assert_parent();self._inspect()
                result=_docker_call([self.docker,"logs",self.identifier],capture_output=True,text=True,timeout=3,check=False)
                if result.returncode: raise AdapterUnavailable("private browser startup metadata unavailable")
                if len(result.stdout)>4096: raise AdapterUnavailable("browser startup metadata exceeds bound")
                if result.stdout.strip():
                    metadata=json.loads(result.stdout.strip())
                    if (set(metadata)!={"version","control_port","control_path","relay_port"} or metadata["version"]!=PLAYWRIGHT_VERSION
                        or type(metadata["control_port"]) is not int or not 1<=metadata["control_port"]<=65535
                        or metadata["control_port"] in {self.product_port,self.relay_port}
                        or not re.fullmatch(r"/[a-f0-9]{64}",metadata["control_path"])
                        or metadata["relay_port"]!=self.relay_port): raise AdapterUnavailable("invalid private browser control metadata")
                    self.tunnel=self.runtime.open_control_port(metadata["control_port"])
                    self._endpoint=f"ws://127.0.0.1:{self.tunnel.host_port}"+metadata["control_path"]
                    self.receipt["relay_port"]=self.relay_port
                    self.receipt["control_token_published"]=False
                    return self
                time.sleep(.1)
            raise AdapterUnavailable("isolated browser startup deadline exceeded")
        except BaseException:
            self.close();raise

    @property
    def endpoint(self):
        if not self._endpoint or self.closed: raise AdapterUnavailable("owned browser control not active")
        self._assert_parent();self._inspect()
        return self._endpoint

    def close(self):
        with self.operation_lock:
            self._close_owned()

    def _close_owned(self):
        if self.closed:return
        try:
            # Exact immutable browser only, never remove/restart its parent.
            if self.identifier:
                if _container_identity(self.docker,self.identifier,self.owner)==self.identifier:
                    _cleanup_container(self.docker,self.identifier,self.owner)
            else:
                _cleanup_container(self.docker,self.name,self.owner)
        finally:
            if self.tunnel:self.tunnel.close()
            self._endpoint=None;self.closed=True

    def __repr__(self):
        return f"DockerBrowserSession(parent_id={self.parent_id!r}, closed={self.closed!r})"
