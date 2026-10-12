"""Control-plane guards, not generated-product security acceptance."""
from types import SimpleNamespace
import hashlib
import os
from pathlib import Path
import socket
import threading
import time

import httpx
import pytest
from fastapi import FastAPI

from autospec.api import server
from autospec.api.control_boundary import ControlPolicy, FactoryControlBoundary


def guarded(policy=None):
    inner = FastAPI()
    effects = []
    @inner.get("/observe")
    @inner.post("/mutate")
    async def endpoint():
        effects.append("route reached")
        return {"ok": True}
    return FactoryControlBoundary(inner, policy=policy or ControlPolicy()), effects


async def request(app, *, url="http://127.0.0.1:8100", method="POST", headers=None,
                  client=("127.0.0.1", 44000)):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=client), base_url=url) as http:
        return await http.request(method, "/observe" if method == "GET" else "/mutate", headers=headers)


@pytest.mark.parametrize("origin", ["http://127.0.0.1:19533", "https://untrusted.example", "null",
    "http://127.0.0.1:8123", "http://localhost:8100", "http://localhost:5183/",
    "http://localhost:5183.evil", "http://user@localhost:5183", "HTTP://localhost:5183"])
@pytest.mark.parametrize("method", ["POST", "GET"])
async def test_foreign_or_malformed_origin_never_reaches_any_control_route(origin, method):
    app, effects = guarded()
    response = await request(app, method=method, headers={"Origin":origin})
    assert response.status_code == 403 and not effects
    assert response.json() == {"detail":"CONTROL_ORIGIN_OR_HOST_REFUSED"}
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize("url,origin,headers,client", [
    ("http://127.0.0.1:8100", None, {}, ("127.0.0.1", 1)),
    ("http://127.0.0.1:8100", "http://127.0.0.1:8100", {}, ("127.0.0.1", 1)),
    ("http://127.0.0.1:8123", "http://127.0.0.1:8123", {}, ("127.0.0.1", 1)),
    ("https://127.0.0.1:9843", "https://127.0.0.1:9843", {}, ("127.0.0.1", 1)),
    ("http://[::1]:8100", "http://[::1]:8100", {}, ("::1", 1)),
    ("http://127.0.0.1:8100", "http://localhost:5183", {}, ("127.0.0.1", 1)),
    ("http://127.0.0.1:8100", "http://127.0.0.1:5183", {}, ("127.0.0.1", 1)),
    ("http://127.0.0.1:8100", "http://localhost:5183", {"Host":"localhost:5183"}, ("127.0.0.1", 1)),
    ("http://127.0.0.1:8100", None, {"Host":"localhost:5183"}, ("127.0.0.1", 1)),
    ("http://127.0.0.1:8100", None, {}, ("::ffff:127.0.0.1", 1)),
])
async def test_local_cli_served_gui_and_exact_vite_proxy_are_nominal(url, origin, headers, client):
    app, effects = guarded()
    if origin is not None: headers = {**headers, "Origin":origin}
    response = await request(app, url=url, headers=headers, client=client)
    assert response.status_code == 200 and effects == ["route reached"]
    if origin is not None: assert response.headers["access-control-allow-origin"] == origin


@pytest.mark.parametrize("host", ["rebinding.example:8100", "127.0.0.1.evil:8100", "localhost.evil:8100",
    "localhost.:8100", "192.0.2.1:8100", "127.0.0.1:19533", "127.0.0.1:",
    "[::1]extra", "localhost@untrusted.example", "test", "testserver", "0x7f000001:8100"])
@pytest.mark.parametrize("method", ["GET", "POST"])
async def test_dns_rebinding_and_unknown_host_fail_even_without_origin(host, method):
    app, effects = guarded()
    response = await request(app, method=method, headers={"Host":host,
        "X-Forwarded-Host":"127.0.0.1:8100", "Forwarded":"host=127.0.0.1:8100"})
    assert response.status_code == 403 and not effects


@pytest.mark.parametrize("client", [("192.0.2.1", 1), ("10.0.0.1", 1), ("testclient", 1), ("localhost", 1)])
async def test_nonlocal_peer_cannot_spoof_loopback_host(client):
    app, effects = guarded()
    response = await request(app, client=client)
    assert response.status_code == 403 and not effects


@pytest.mark.parametrize("headers", [
    [("Host","127.0.0.1:8100"),("Host","rebinding.example:8100")],
    [("Host","127.0.0.1:8100"),("Host","127.0.0.1:8100")],
    [("Origin","http://127.0.0.1:8100"),("Origin","null")],
])
async def test_duplicate_authority_or_origin_headers_are_not_collapsed(headers):
    app, effects = guarded()
    response = await request(app, headers=headers)
    assert response.status_code == 403 and not effects


@pytest.mark.parametrize("origin", ["http://localhost:5183", "http://127.0.0.1:8100"])
async def test_exact_allowed_preflight_has_explicit_cors_and_no_effect(origin):
    app, effects = guarded()
    response = await request(app, method="OPTIONS", headers={"Origin":origin,
        "Access-Control-Request-Method":"POST", "Access-Control-Request-Headers":"Content-Type"})
    assert response.status_code == 200 and not effects
    assert response.headers["access-control-allow-origin"] == origin
    assert "*" not in response.headers["access-control-allow-methods"]
    assert "*" not in response.headers["access-control-allow-headers"]


@pytest.mark.parametrize("headers", [
    {"Origin":"null","Access-Control-Request-Method":"POST"},
    {"Origin":"http://127.0.0.1:19533","Access-Control-Request-Method":"POST"},
    {"Origin":"http://localhost:5183","Access-Control-Request-Method":"TRACE"},
    {"Origin":"http://localhost:5183","Access-Control-Request-Method":"POST","Access-Control-Request-Headers":"X-Tool"},
])
async def test_preflight_never_authorizes_unknown_origin_method_or_header(headers):
    app, effects = guarded()
    response = await request(app, method="OPTIONS", headers=headers)
    assert response.status_code in {400, 403} and not effects


async def test_explicit_custom_authority_is_not_an_implicit_custom_origin():
    app, effects = guarded(ControlPolicy((), ("factory.example:8100",)))
    rejected = await request(app, url="http://factory.example:8100", client=("192.0.2.1", 1),
        headers={"Origin":"http://factory.example:8100"})
    assert rejected.status_code == 403 and not effects
    cli = await request(app, url="http://factory.example:8100", client=("192.0.2.1", 1))
    assert cli.status_code == 200 and effects == ["route reached"]
    approved, observed = guarded(ControlPolicy(("http://factory.example:8100",), ("factory.example:8100",)))
    gui = await request(approved, url="http://factory.example:8100", client=("192.0.2.1", 1),
        headers={"Origin":"http://factory.example:8100"})
    assert gui.status_code == 200 and observed == ["route reached"]


async def test_configured_hostname_without_port_still_requires_actual_server_port():
    app, effects = guarded(ControlPolicy((), ("factory.example",)))
    rejected = await request(app, headers={"Host":"factory.example:19533"}, client=("192.0.2.1",1))
    assert rejected.status_code == 403 and not effects
    approved = await request(app, headers={"Host":"factory.example:8100"}, client=("192.0.2.1",1))
    assert approved.status_code == 200 and effects == ["route reached"]


async def test_configured_loopback_name_does_not_authorize_a_remote_peer():
    app, effects = guarded(ControlPolicy((), ("127.0.0.1:8100", "localhost")))
    response = await request(app, client=("192.0.2.1",1))
    assert response.status_code == 403 and not effects
    response = await request(app, headers={"Host":"localhost:8100"}, client=("192.0.2.1",1))
    assert response.status_code == 403 and not effects


@pytest.mark.parametrize("name,value", [
    ("AUTOSPEC_CONTROL_ORIGINS", "*"), ("AUTOSPEC_CONTROL_ORIGINS", '["*"]'),
    ("AUTOSPEC_CONTROL_ORIGINS", '["null"]'), ("AUTOSPEC_CONTROL_ORIGINS", '["http://localhost:5183/"]'),
    ("AUTOSPEC_CONTROL_ORIGINS", '["http://localhost:5183","http://localhost:5183"]'),
    ("AUTOSPEC_CONTROL_ORIGINS", '[true]'), ("AUTOSPEC_CONTROL_ORIGINS", "{}"),
    ("AUTOSPEC_CONTROL_HOSTS", '["*.example"]'), ("AUTOSPEC_CONTROL_HOSTS", '["localhost:"]'),
    ("AUTOSPEC_CONTROL_HOSTS", '["localhost:65536"]'), ("AUTOSPEC_CONTROL_HOSTS", '["http://localhost"]'),
    ("AUTOSPEC_CONTROL_HOSTS", '["LOCALHOST"]'), ("AUTOSPEC_CONTROL_HOSTS", '["localhost","localhost"]'),
])
def test_configuration_is_bounded_exact_and_fail_closed(monkeypatch, name, value):
    for setting in ("AUTOSPEC_CONTROL_ORIGINS", "AUTOSPEC_CONTROL_HOSTS"):
        monkeypatch.delenv(setting, raising=False)
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError): ControlPolicy.from_environment()


def test_explicit_empty_config_disables_default_dev_origins(monkeypatch):
    monkeypatch.setenv("AUTOSPEC_CONTROL_ORIGINS", "[]")
    monkeypatch.setenv("AUTOSPEC_CONTROL_HOSTS", "[]")
    assert ControlPolicy.from_environment() == ControlPolicy((), ())


@pytest.mark.parametrize("origin,expected", [(None, 200), ("http://127.0.0.1:8100", 200),
    ("http://localhost:5183", 200), ("http://127.0.0.1:19533", 403), ("null", 403)])
async def test_real_factory_undeploy_route_is_guarded_before_pipeline_effects(monkeypatch, origin, expected):
    effects = []
    async def withdraw(): effects.append("inert withdrawal")
    monkeypatch.setattr(server, "pipelines", {"control-meta":SimpleNamespace(aundeploy=withdraw)})
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://127.0.0.1:8100") as client:
        response = await client.post("/api/projects/control-meta/undeploy", headers={"Origin":origin} if origin else {})
    assert response.status_code == expected
    assert bool(effects) is (expected == 200)


@pytest.mark.parametrize("origin,host,allowed", [("null", "127.0.0.1:8100", False),
    ("http://localhost:5183", "127.0.0.1:8100", True),
    ("http://127.0.0.1:8100", "rebinding.example:8100", False)])
async def test_websocket_boundary_uses_same_authority_and_origin_policy(origin, host, allowed):
    effects, messages = [], []
    async def inner(scope, receive, send):
        effects.append("trusted websocket handler")
        await send({"type":"websocket.close", "code":1000})
    async def receive(): return {"type":"websocket.connect"}
    async def send(message): messages.append(message)
    scope = {"type":"websocket", "scheme":"ws", "server":("127.0.0.1",8100),
        "client":("127.0.0.1", 1), "headers":[(b"host",host.encode()),(b"origin",origin.encode())]}
    await FactoryControlBoundary(inner, policy=ControlPolicy())(scope, receive, send)
    assert bool(effects) is allowed and messages[-1]["code"] == (1000 if allowed else 1008)


def test_real_loopback_factory_control_cli_served_gui_and_dev_proxy(monkeypatch):
    """Actual TCP/controller route, inert pipeline, exact owned listener only."""
    import uvicorn
    from autospec.orchestrator.dependencies import atomic_json
    effects = []
    async def withdraw(): effects.append("inert native withdrawal")
    monkeypatch.setattr(server, "pipelines", {"native-control":SimpleNamespace(aundeploy=withdraw)})
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    port = listener.getsockname()[1]
    native = uvicorn.Server(uvicorn.Config(server.app, log_level="warning", access_log=False,
                                         lifespan="off", proxy_headers=False))
    thread = threading.Thread(target=native.run, kwargs={"sockets":[listener]}, daemon=True)
    observations = []
    thread.start()
    try:
        deadline = time.monotonic() + 5
        while not native.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(.01)
        assert native.started and thread.is_alive()
        origin = "http://127.0.0.1:" + str(port)
        with httpx.Client(base_url=origin, timeout=3, trust_env=False) as client:
            cases = [
                ("CLI", {}, 200),
                ("served GUI same origin", {"Origin":origin}, 200),
                ("exact Vite dev proxy", {"Host":"localhost:5183","Origin":"http://localhost:5183"}, 200),
                ("product origin", {"Origin":"http://127.0.0.1:19533"}, 403),
                ("opaque origin", {"Origin":"null"}, 403),
                ("DNS rebinding", {"Host":"rebinding.example:"+str(port)}, 403),
            ]
            for name, headers, expected in cases:
                before = len(effects)
                response = client.post("/api/projects/native-control/undeploy", headers=headers)
                assert response.status_code == expected
                assert len(effects) - before == int(expected == 200)
                observations.append(dict(case=name, status_code=response.status_code,
                    callback_delta=len(effects)-before, origin=headers.get("Origin"),
                    host=headers.get("Host", "127.0.0.1:"+str(port))))
            response = client.get("/api/projects/never-present", headers={"Host":"rebinding.example:"+str(port)})
            assert response.status_code == 403
            observations.append(dict(case="rebinding GET without Origin", status_code=response.status_code))
            response = client.options("/api/projects/native-control/undeploy", headers={"Origin":"http://localhost:5183",
                "Access-Control-Request-Method":"POST","Access-Control-Request-Headers":"Content-Type"})
            assert response.status_code == 200
            assert response.headers["access-control-allow-origin"] == "http://localhost:5183"
            observations.append(dict(case="exact dev preflight", status_code=response.status_code))
    finally:
        native.should_exit = True
        thread.join(timeout=5)
        listener.close()
        assert not thread.is_alive()
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", port))
    if os.environ.get("AUTOSPEC_CONTROL_PROOF_ROOT"):
        source = Path(server.__file__)
        boundary = source.with_name("control_boundary.py")
        atomic_json(Path(os.environ["AUTOSPEC_CONTROL_PROOF_ROOT"])/"factory-control-native.json",
            dict(scope="trusted factory TCP controller only; pipeline callback inert; NOT product acceptance",
                 server_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                 boundary_sha256=hashlib.sha256(boundary.read_bytes()).hexdigest(),
                 observations=observations, callback_count=len(effects), listener_port=port,
                 listener_released=True, server_thread_stopped=True,
                 limits=["GUI request headers exercised through real TCP; no new React visual E2E claimed",
                         "No product code, browser JS, real Docker withdrawal or paid provider ran"]))
