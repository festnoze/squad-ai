"""Structural boundary tests. Fake Docker only tests admission, never PASS UX."""
import copy
import io
import json
import tarfile
from types import SimpleNamespace

import pytest

from autospec.validation import docker_browser as module
from autospec.validation.browser_contracts import PlaywrightHarness
from autospec.validation.support_adapter import AdapterUnavailable
from autospec.orchestrator.isolated_validation import RuntimeSession


def capability(tmp_path,monkeypatch):
    runtime=RuntimeSession(tmp_path,"image",["python"],port=8000)
    state=dict(container_id="a"*64,network_mode="none",running=True,published_ports={},user="65532:65532",
        read_only=True,privileged=False,cap_drop=["ALL"],security_opt=["no-new-privileges=true"])
    monkeypatch.setattr(runtime,"_assert_owned",lambda:state["container_id"])
    monkeypatch.setattr(runtime,"inspect_configuration",lambda:copy.deepcopy(state))
    return runtime,state


def test_factory_tar_contains_no_product_paths_hooks_or_credentials():
    payload,digest=module.factory_context("sha256:"+"b"*64)
    with tarfile.open(fileobj=io.BytesIO(payload.encode("ascii")),mode="r") as archive:
        assert archive.getnames()==["Dockerfile","package.json","package-lock.json"]
        files={n:archive.extractfile(n).read().decode("ascii") for n in archive.getnames()}
    dockerfile=files["Dockerfile"]
    assert module.BASE_IMAGE_PIN in dockerfile and "--ignore-scripts" in dockerfile
    assert "USER 65532:65532" in dockerfile and "COPY ." not in dockerfile
    lock=json.loads(files["package-lock.json"])
    assert set(lock["packages"])=={"","node_modules/playwright","node_modules/playwright-core"}
    assert lock["packages"]["node_modules/playwright"]["integrity"]==module.PACKAGE_INTEGRITY
    assert lock["packages"]["node_modules/playwright-core"]["integrity"]==module.CORE_INTEGRITY
    assert digest==module.factory_context("sha256:"+"b"*64)[1]
    assert "host:'127.0.0.1'" in module.SERVER_SCRIPT and "randomBytes(32)" in module.SERVER_SCRIPT


def test_run_builder_has_exact_namespace_no_mounts_or_published_ports():
    args=module.browser_run_command("docker","sha256:"+"b"*64,"a"*64,"c"*32,"autospec-sandbox-"+"d"*32,8123,8000)
    assert args[args.index("--network")+1]=="container:"+"a"*64
    assert args[args.index("--user")+1]=="65532:65532"
    assert "--read-only" in args and args[args.index("--cap-drop")+1]=="ALL"
    assert not set(args)&{"-v","--volume","--mount","-p","--publish","--privileged","--add-host"}
    assert args[args.index("--ipc")+1]=="private" and "--ipc=host" not in args
    assert args[-3:]==[module.SERVER_SCRIPT,"8123","8000"]


@pytest.mark.parametrize("port",[True,0,65536,"8000",-1])
def test_run_builder_rejects_unbounded_or_model_shaped_ports(port):
    with pytest.raises(AdapterUnavailable):
        module.browser_run_command("docker","sha256:"+"b"*64,"a"*64,"c"*32,"autospec-sandbox-"+"d"*32,port,8000)


@pytest.mark.parametrize("field,value",[("network_mode","bridge"),("published_ports",{"9222/tcp":[]}),
    ("running",False),("container_id","invalid"),("user","0"),("read_only",False),
    ("privileged",True),("cap_drop",[]),("security_opt",["no-new-privileges=true","seccomp=unconfined"])])
def test_parent_must_be_actual_owned_hardened_unpublished_netnone(tmp_path,monkeypatch,field,value):
    runtime,state=capability(tmp_path,monkeypatch);state[field]=value
    try:
        with pytest.raises(AdapterUnavailable):module.DockerBrowserSession(runtime,origin=runtime.origin)
    finally:runtime.server.server_close()


def test_model_shaped_runtime_cannot_grant_namespace():
    with pytest.raises(AdapterUnavailable):module.DockerBrowserSession(SimpleNamespace(origin="http://127.0.0.1:8123"),origin="http://127.0.0.1:8123")


def configuration(session):
    return dict(Id="d"*64,Image="sha256:"+"b"*64,State=dict(Running=True),Mounts=[],
        Config=dict(User="65532:65532",Labels={"autospec.run_id":session.owner,"autospec.kind":"sandbox"},
            Entrypoint=["node"],WorkingDir="/opt/autospec-browser",Cmd=["--eval",module.SERVER_SCRIPT,str(session.relay_port),str(session.product_port)],
            Env=["PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin","LANG=C.UTF-8","LC_ALL=C.UTF-8",
                 "PLAYWRIGHT_BROWSERS_PATH=/ms-playwright","PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1","HOME=/tmp"]),
        HostConfig=dict(NetworkMode="container:"+session.parent_id,ReadonlyRootfs=True,Privileged=False,
            CapAdd=None,CapDrop=["ALL"],SecurityOpt=["no-new-privileges=true"],Binds=None,PortBindings={},
            Devices=[],ExtraHosts=None,PidMode="",IpcMode="private",PidsLimit=256,Memory=2*1024**3,NanoCpus=2*10**9,
            Tmpfs={"/tmp":"rw,nosuid,nodev,size=512m,mode=1777","/dev/shm":"rw,nosuid,nodev,size=512m,mode=1777"}))


@pytest.mark.parametrize("field,value",[("NetworkMode","host"),("ReadonlyRootfs",False),("Privileged",True),
    ("CapAdd",["SYS_ADMIN"]),("CapDrop",[]),("SecurityOpt",["no-new-privileges=true","seccomp=unconfined"]),
    ("Binds",["/var/run/docker.sock:/var/run/docker.sock"]),("PortBindings",{"9222/tcp":[]}),
    ("Devices",[{}]),("ExtraHosts",["host:host-gateway"]),("PidMode","host"),("IpcMode","host"),
    ("PidsLimit",0),("Memory",0),("NanoCpus",0),("Tmpfs",{})])
def test_fresh_browser_inspection_rejects_weakened_daemon_configuration(tmp_path,monkeypatch,field,value):
    runtime,_=capability(tmp_path,monkeypatch)
    try:
        session=module.DockerBrowserSession(runtime,origin=runtime.origin,image_id="sha256:"+"b"*64);session.identifier="d"*64
        config=configuration(session);config["HostConfig"][field]=value
        monkeypatch.setattr(module,"_docker_call",lambda *a,**k:SimpleNamespace(returncode=0,stdout=json.dumps([config])))
        with pytest.raises(AdapterUnavailable):session._inspect()
    finally:runtime.server.server_close()


def test_never_adopts_restarted_parent_or_removes_it_and_never_repr_token(tmp_path,monkeypatch):
    runtime,state=capability(tmp_path,monkeypatch);removed=[];closed=[]
    try:
        session=module.DockerBrowserSession(runtime,origin=runtime.origin);session.identifier="d"*64
        session._endpoint="ws://127.0.0.1:9999/"+"secret"*8
        session.tunnel=SimpleNamespace(close=lambda:closed.append(True))
        state["container_id"]="e"*64
        with pytest.raises(AdapterUnavailable):_ = session.endpoint
        monkeypatch.setattr(module,"_container_identity",lambda *a:"d"*64)
        monkeypatch.setattr(module,"_cleanup_container",lambda *a:removed.append(a))
        assert "secret" not in repr(session)
        session.close();session.close()
        assert len(removed)==1 and removed[0][1]=="d"*64 and closed==[True] and not runtime.closed
    finally:runtime.server.server_close()


def owner(**fields):
    adapter=SimpleNamespace(base_url="http://127.0.0.1:8123",manifest=SimpleNamespace(accounts={}),**fields)
    return PlaywrightHarness(adapter,bindings={},routes={"home":"/"})


@pytest.mark.parametrize("fields,local",[({},False),({"live_sqlite":True},False),({"live_sqlite":True},True),
    ({"supervised_runtime":object()},False)])
async def test_host_chromium_default_and_live_sqlite_local_optin_fail_closed(monkeypatch,fields,local):
    import playwright.async_api
    calls=[]
    monkeypatch.setattr(playwright.async_api,"async_playwright",lambda:calls.append("HOST_DRIVER"))
    harness=owner(**fields);harness.trusted_fixture_local_browser=local
    with pytest.raises(AdapterUnavailable):await harness.start()
    assert calls==[] and harness.browser is None


async def test_remote_driver_connect_never_launches_or_exposes_host_network(monkeypatch):
    import playwright.async_api
    calls=[]
    class Session:
        def __init__(self,runtime,*,origin):self.endpoint="ws://127.0.0.1:9999/secret";self.receipt={"host_chromium":False}
        def start(self):calls.append("container-start")
        def close(self):calls.append("container-and-tunnel-close")
    class Driver:
        def __init__(self):self.chromium=self
        async def start(self):calls.append("driver-start");return self
        async def launch(self,**kw):raise AssertionError("host Chromium must never launch")
        async def connect(self,endpoint,**kw):calls.append(("connect",kw));return SimpleNamespace(close=self.browser_close)
        async def browser_close(self):calls.append("browser-close")
        async def stop(self):calls.append("driver-stop")
    monkeypatch.setattr(module,"DockerBrowserSession",Session)
    monkeypatch.setattr(playwright.async_api,"async_playwright",Driver)
    harness=owner(supervised_runtime=object(),live_sqlite=True)
    await harness.start();await harness.close()
    assert ("connect",dict(timeout=10000,expose_network="")) in calls
    assert calls.index("browser-close")<calls.index("container-and-tunnel-close")<calls.index("driver-stop")
    assert harness.browser_environment["host_chromium"] is False


async def test_remote_factory_failure_cannot_fall_back_to_local_fixture_flag(monkeypatch):
    import playwright.async_api
    calls=[]
    class Session:
        def __init__(self,*a,**kw):pass
        def start(self):raise AdapterUnavailable("factory failure")
        def close(self):calls.append("close")
    monkeypatch.setattr(module,"DockerBrowserSession",Session)
    monkeypatch.setattr(playwright.async_api,"async_playwright",lambda:calls.append("HOST_DRIVER"))
    harness=owner(supervised_runtime=object(),live_sqlite=True);harness.trusted_fixture_local_browser=True
    with pytest.raises(AdapterUnavailable):await harness.start()
    assert calls==["close"]


@pytest.mark.parametrize("field,value",[("Env",["HOME=/tmp","AWS_SECRET_ACCESS_KEY=forbidden"]),("Cmd",["/product/script.js"]),
    ("Entrypoint",["sh"]),("WorkingDir","/app")])
def test_browser_has_only_constant_factory_code_and_credential_free_env(tmp_path,monkeypatch,field,value):
    runtime,_=capability(tmp_path,monkeypatch)
    try:
        session=module.DockerBrowserSession(runtime,origin=runtime.origin,image_id="sha256:"+"b"*64);session.identifier="d"*64
        config=configuration(session);config["Config"][field]=value
        monkeypatch.setattr(module,"_docker_call",lambda *a,**k:SimpleNamespace(returncode=0,stdout=json.dumps([config])))
        with pytest.raises(AdapterUnavailable):session._inspect()
    finally:runtime.server.server_close()


async def test_connection_failure_never_publishes_private_ws_capability(monkeypatch):
    import playwright.async_api
    class Session:
        def __init__(self,*a,**kw):self.endpoint="ws://127.0.0.1:9999/private-secret"
        def start(self):pass
        def close(self):pass
    class Driver:
        def __init__(self):self.chromium=self
        async def start(self):return self
        async def connect(self,endpoint,**kw):raise ValueError("failed connection "+endpoint)
        async def stop(self):pass
    monkeypatch.setattr(module,"DockerBrowserSession",Session);monkeypatch.setattr(playwright.async_api,"async_playwright",Driver)
    harness=owner(supervised_runtime=object(),live_sqlite=True)
    with pytest.raises(AdapterUnavailable) as caught:await harness.start()
    assert "private-secret" not in str(caught.value) and caught.value.__suppress_context__ and caught.value.__cause__ is None


async def test_cancellation_still_closes_factory_browser_without_host_launch(monkeypatch):
    import asyncio
    class Session:
        def __init__(self,*a,**kw):self.closed=False
        def start(self):raise asyncio.CancelledError()
        def close(self):self.closed=True
    monkeypatch.setattr(module,"DockerBrowserSession",Session)
    harness=owner(supervised_runtime=object(),live_sqlite=True)
    with pytest.raises(asyncio.CancelledError):await harness.start()
    assert harness.docker_browser.closed and harness.playwright is None
