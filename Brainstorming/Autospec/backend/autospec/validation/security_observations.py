"""Supervisor-only bounded scans and source-reviewed cookie deployment facts.

No product import or command is executed on the host. Detectors are deliberately
limited: known probe secrets and recognizable credential material, complemented
by independent R. An unavailable/oversized surface never becomes an empty scan.
"""
from __future__ import annotations

import hashlib
import base64
import json
import io
import re
import tarfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from uuid import uuid4

from .support_adapter import AdapterUnavailable, Proof
from .public_crypto_fixtures import classify_public_vendor_material


def validate_security_environment(environment):
    if not isinstance(environment, dict) or not environment:
        raise ValueError("explicit source-reviewed security environment required")
    for key, value in environment.items():
        if (not isinstance(key, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", key)
                or key in {"PATH", "HOME", "USER", "HOST", "PORT", "DATABASE_URL", "APP_ORIGIN"}
                or key.startswith(("PYTHON", "NODE", "LD_", "UV_", "NPM_", "DOCKER", "AUTOSPEC"))
                or any(s in key for s in ("PASSWORD", "TOKEN", "SECRET", "CREDENTIAL", "API_KEY"))
                or value not in {"true", "false", "1", "0", "production", "development", "prod", "dev"}):
            raise ValueError("bounded non-secret source-reviewed mode configuration required")


@dataclass(frozen=True)
class CookieDeploymentMode:
    environment: dict[str, str]
    tls: bool

    def validate(self):
        validate_security_environment(self.environment)
        if type(self.tls) is not bool:
            raise ValueError("explicit real TLS mode required")


@dataclass(frozen=True)
class SecurityObservationBindings:
    cookie_name: str
    fixture_case: str
    actor: str
    app_module: str
    app_attribute: str
    modes: dict[str, CookieDeploymentMode]
    artifact_roots: tuple[str, ...]

    @classmethod
    def from_dict(cls, value):
        if (not isinstance(value, dict) or not isinstance(value.get("modes"), dict)
                or not isinstance(value.get("artifact_roots"), (list,tuple))):
            raise ValueError("typed reviewed security observation structure required")
        data = dict(value)
        data["modes"] = {k: CookieDeploymentMode(**v) for k, v in data["modes"].items()}
        data["artifact_roots"] = tuple(data["artifact_roots"])
        return cls(**data)

    def validate(self):
        if (not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9-]{0,63}", self.cookie_name)
                or not re.fullmatch(r"[A-Z][A-Z0-9_-]{0,63}", self.fixture_case)
                or not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", self.actor)
                or not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*", self.app_module)
                or not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", self.app_attribute)):
            raise ValueError("exact reviewed cookie/fixture/ASGI facts required")
        if set(self.modes) != {"https", "http_local_explicit", "http_without_exception"}:
            raise ValueError("all three frozen source cookie conditions must be bound")
        for name, mode in self.modes.items():
            mode.validate()
            if mode.tls != (name == "https"):
                raise ValueError("cookie mode transport does not match its source condition")
        if not self.artifact_roots or len(set(self.artifact_roots)) != len(self.artifact_roots):
            raise ValueError("explicit owned artifact scan scope required")
        for relative in self.artifact_roots:
            p = PurePosixPath(relative)
            if not isinstance(relative, str) or p.is_absolute() or ".." in p.parts or "\\" in relative:
                raise ValueError("artifact scan roots must be relative supervisor scope")


class BoundedSecretScanner:
    MAX_BYTES = 768 * 1024 * 1024
    MAX_FILES = 60000
    _patterns = (
        ("argon2_hash", re.compile(rb"\$argon2(?:id|i|d)\$v=\d+\$m=\d+,t=\d+,p=\d+\$[A-Za-z0-9+/]+\$[A-Za-z0-9+/]+")),
        ("private_key", re.compile(rb"-----BEGIN ((?:RSA |DSA |EC |OPENSSH |ENCRYPTED )?PRIVATE KEY)-----[\t \r\n]{0,128}([A-Za-z0-9+/=\t \r\n]{64,32768})[\t \r\n]{0,128}-----END \1-----")),
        ("credential_assignment", re.compile(rb"(?i)(?:password|api[_-]?key|client[_-]?secret)\s*[=:]\s*['\"]([^'\"\r\n]{8,256})['\"]")),
    )

    def __init__(self, secrets):
        self.secrets = sorted({s.encode() for s in secrets if isinstance(s, str) and len(s) >= 8})
        if len(self.secrets)>2048 or sum(map(len,self.secrets))>1024*1024:
            raise AdapterUnavailable("known probe-secret inventory exceeds bounded complete scan")
        self._carry=max([33536,*map(len,self.secrets)])
        self.bytes = 0
        self.files = 0
        self.findings = []
        self.inventory = []

    def scan(self, stream, *, scope, name):
        self.files += 1
        if self.files > self.MAX_FILES:
            raise AdapterUnavailable("secret scan file count exceeds bounded complete scope")
        digest = hashlib.sha256()
        tail = b""
        file_bytes = 0
        seen = set()
        while chunk := stream.read(65536):
            self.bytes += len(chunk)
            if self.bytes > self.MAX_BYTES:
                raise AdapterUnavailable("secret scan bytes exceed bounded complete scope")
            digest.update(chunk)
            file_bytes += len(chunk)
            text = tail + chunk
            base_offset=file_bytes-len(chunk)-len(tail)
            matches = [("known_probe_secret", s, text.find(s), {}) for s in self.secrets if s in text]
            application = scope != "image" or ":app/" in name
            for kind, pattern in self._patterns:
                if not application and kind != "private_key": continue
                for match in pattern.finditer(text):
                    if kind == "private_key":
                        try: decoded = base64.b64decode(re.sub(rb"\s", b"", match.group(2)), validate=True)
                        except ValueError: continue
                        if len(decoded) < 32 or not (decoded.startswith(b"\x30") or decoded.startswith(b"openssh-key-v1\x00")):
                            continue
                    detail=dict(material_sha256=hashlib.sha256(decoded).hexdigest(),pem_type=match.group(1).decode()) if kind=="private_key" else {}
                    matches.append((kind, match.group(0), match.start(), detail))
            for kind, value, offset, detail in matches:
                identity = (kind, hashlib.sha256(value).hexdigest())
                if identity not in seen:
                    seen.add(identity)
                    self.findings.append(dict(scope=scope, file=name, kind=kind, value_sha256=identity[1],
                        offset=base_offset+offset,match_bytes=len(value),**detail))
            tail = text[-self._carry:]
        self.inventory.append(dict(scope=scope, file=name, sha256=digest.hexdigest()))

    def scan_tree(self, root, *, scope):
        from ..agents.file_broker import ExecutionContext, FileBroker
        root = Path(root).resolve()
        if not root.is_dir():
            raise AdapterUnavailable("explicit scan scope directory absent")
        broker = FileBroker(ExecutionContext("native-security-scan", root))
        for path in sorted(root.rglob("*")):
            relative = path.relative_to(root).as_posix()
            checked = broker.path(relative)
            if checked.is_file():
                with checked.open("rb") as stream:
                    self.scan(stream, scope=scope, name=relative)

    def scan_image(self, archive, image_id):
        # A docker image save tar contains every layer, including removed
        # material. Never extract paths or follow archive links on the host.
        with tarfile.open(archive, mode="r") as image:
            manifest = image.getmember("manifest.json")
            if not manifest.isfile() or manifest.size > 1024*1024:
                raise AdapterUnavailable("bounded native Docker save manifest absent")
            entries = json.load(image.extractfile(manifest))
            selected = []
            for entry in entries:
                config = image.getmember(entry["Config"])
                if not config.isfile() or config.size > 1024*1024:
                    raise AdapterUnavailable("bounded image configuration absent")
                raw=image.extractfile(config).read()
                digest = hashlib.sha256(raw).hexdigest()
                if image_id == "sha256:" + digest: selected.append(entry)
            if len(selected) != 1 or not selected[0].get("Layers") or len(selected[0]["Layers"]) > 200:
                raise AdapterUnavailable("export configuration does not identify one exact immutable image")
            self.scan(io.BytesIO(image.extractfile(selected[0]["Config"]).read()),scope="image",name="native-docker-image-configuration")
            for name in selected[0]["Layers"]:
                member = image.getmember(name)
                if not member.isfile(): raise AdapterUnavailable("image layer is not a regular archive member")
                with tarfile.open(fileobj=image.extractfile(member), mode="r|") as layer:
                    for entry in layer:
                        if entry.isfile():
                            with layer.extractfile(entry) as stream:
                                self.scan(stream, scope="image", name=name + ":" + entry.name)

    def receipt(self, root, *, scopes, snapshot, contract, provenance):
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        # Do not silently discard detector results. Only independently reviewed
        # PUBLIC bytes in one byte-identical vendor file are non-credentials;
        # known probe secrets and application copies can never take this path.
        inventory = {}
        for item in self.inventory:
            inventory.setdefault((item["scope"], item["file"]), []).append(item["sha256"])
        findings, public_material = [], []
        for finding in self.findings:
            hashes = inventory.get((finding["scope"], finding["file"]), ())
            classified = (classify_public_vendor_material(finding, file_sha256=hashes[0])
                          if len(hashes) == 1 else None)
            if classified is None:
                findings.append(finding)
            else:
                public_material.append(classified)
        value = dict(findings=findings, detector_candidates=self.findings,
            public_non_credentials=public_material, scopes=scopes, complete=True,
            scanned_files=self.files, scanned_bytes=self.bytes,
            limits=["known probe secrets and structurally complete PEM material across every byte/layer; assignment and Argon2 heuristics limited to application/source/logs/artifacts",
                "not universal discovery of unknown vendor secrets; independent source/image R remains mandatory",
                "public self-test material classification is exact file/key identity, not supply-chain approval or permission to use public keys as application credentials"])
        payload = dict(snapshot_hash=snapshot, contract_hash=contract, observed=value,
            inventory=self.inventory, provenance=provenance)
        path = root / ("security-scan-" + uuid4().hex + ".json")
        path.write_bytes(json.dumps(payload, sort_keys=True, ensure_ascii=True).encode())
        value["artifacts"] = [{"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}]
        tags = ("SEC-01:secret_scan",) if scopes == ["source", "image", "logs"] else ("SEC-15:secret_scan",)
        proof = Proof("X", str(path), value["artifacts"][0]["sha256"], snapshot, contract, tags,
            passed=not findings, detail="native complete bounded scope; all candidates and exact public classifications retained, contents withheld")
        return value, proof


# Only inside a disposable NETNONE container. Ephemeral TLS material under
# /tmp is never copied into image/evidence. Product import is confined here.
COOKIE_MODE_LAUNCHER = r'''
import importlib,json,os,subprocess,sys,tempfile,uvicorn
q=json.loads(sys.argv[1]);sys.path.insert(0,'/app');options={}
if q['tls']:
 root=tempfile.mkdtemp(prefix='autospec-cookie-tls-');key=root+'/key.pem';cert=root+'/cert.pem'
 p=subprocess.run(['/usr/bin/openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',key,'-out',cert,'-subj','/CN=127.0.0.1','-addext','subjectAltName=IP:127.0.0.1','-days','1'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10)
 if p.returncode: raise RuntimeError('factory ephemeral TLS certificate unavailable')
 os.chmod(key,0o600);options=dict(ssl_keyfile=key,ssl_certfile=cert)
 open('/tmp/autospec-cookie-cert-path','w').write(cert)
app=getattr(importlib.import_module(q['module']),q['attribute'])
uvicorn.run(app,host='127.0.0.1',port=q['port'],access_log=False,log_level='warning',proxy_headers=False,**options)
'''

COOKIE_MODE_REQUEST = r'''
import hashlib,http.client,json,ssl,sys,time
q=json.load(sys.stdin);end=time.monotonic()+12
while True:
 try:
  if q['tls']:
   cert=open('/tmp/autospec-cookie-cert-path').read();context=ssl.create_default_context(cafile=cert)
   c=http.client.HTTPSConnection('127.0.0.1',q['port'],context=context,timeout=3)
  else:c=http.client.HTTPConnection('127.0.0.1',q['port'],timeout=3)
  c.connect();break
 except (OSError,ssl.SSLError):
  if time.monotonic()>=end:raise RuntimeError('isolated cookie transport unavailable')
  time.sleep(.1)
tls_version=c.sock.version() if q['tls'] else None
c.request('POST',q['path'],json.dumps(q['credentials']),{'Content-Type':'application/json','Origin':q['origin']})
r=c.getresponse();from http.cookies import SimpleCookie
matches=[];header_hashes=[]
for name,value in r.getheaders():
 if name.lower()=='set-cookie':
  cookie=SimpleCookie();cookie.load(value);header_hashes.append(hashlib.sha256(value.encode()).hexdigest())
  if q['cookie_name'] in cookie:matches.append(cookie[q['cookie_name']])
if len(matches)>1:raise RuntimeError('ambiguous actual session cookie headers')
m=matches[0] if matches else None
result={'status':r.status,'tls_version':tls_version,'cookie_present':m is not None,'set_cookie_header_sha256':header_hashes}
if m:result.update(secure=bool(m['secure']),httponly=bool(m['httponly']),samesite=m['samesite'],path=m['path'],token_sha256=hashlib.sha256(m.value.encode()).hexdigest())
raw=r.read(1048577)
if len(raw)>1048576:raise RuntimeError('cookie probe response exceeds complete bound')
# Private observer transport only; caller removes these fictitious auth
# values before ANY evidence serialization, retaining them in memory for scans.
result['_probe_secrets']=[m.value] if m else []
try:
 body=json.loads(raw);csrf=body.get(q['csrf_field'])
 if isinstance(csrf,str) and csrf:result['_probe_secrets'].append(csrf)
except (ValueError,AttributeError):pass
c.close();print(json.dumps(result))
'''
