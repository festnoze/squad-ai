"""Guard lifecycle only: no hostile JS, server or external connection executes."""
from types import SimpleNamespace
import pytest
from autospec.validation.browser_contracts import PlaywrightHarness,BROWSER_NETWORK_LIMITS
from autospec.validation.support_adapter import AdapterUnavailable


class FakePage:
    def __init__(self,events):self.events=events
    def set_default_timeout(self,value):self.events.append("timeout")
    def on(self,event,callback):self.events.append("on:"+event)
    async def goto(self,url):self.events.append("goto")


class FakeContext:
    def __init__(self,events,unsupported=False):self.events=events;self.unsupported=unsupported;self.handlers={};self.closed=False
    async def route(self,pattern,handler):self.events.append("http_guard");self.handlers["http"]=handler
    async def route_web_socket(self,pattern,handler):
        self.events.append("ws_guard")
        if self.unsupported:raise NotImplementedError
        self.handlers["ws"]=handler
    async def new_page(self):self.events.append("new_page");return FakePage(self.events)
    async def close(self):self.closed=True;self.events.append("close")


class FakeBrowser:
    def __init__(self,events,unsupported=False):self.events=events;self.context=FakeContext(events,unsupported);self.options=None
    async def new_context(self,**options):self.options=options;self.events.append("context");return self.context


def harness(unsupported=False):
    events=[];browser=FakeBrowser(events,unsupported)
    adapter=SimpleNamespace(base_url="http://127.0.0.1:8123",manifest=SimpleNamespace(accounts={}))
    owner=PlaywrightHarness(adapter,bindings={},routes={"home":"/"});owner.browser=browser
    checks=[]
    case=SimpleNamespace(requests=[],console_errors=[],check=lambda tag,observed,expected:checks.append((tag,observed,expected)))
    return owner,browser,case,checks,events


async def test_SW_block_and_WS_deny_install_before_any_page_or_script():
    owner,browser,case,checks,events=harness()
    await owner.page(case,1280)
    assert browser.options["service_workers"]=="block"
    assert events.index("http_guard")<events.index("new_page")
    assert events.index("ws_guard")<events.index("new_page")<events.index("goto")
    assert "OS sandbox" in BROWSER_NETWORK_LIMITS[0]
    assert "WebRTC/UDP" in BROWSER_NETWORK_LIMITS[1]


@pytest.mark.parametrize("url",["ws://127.0.0.1:8123/socket","wss://example.invalid/socket"])
async def test_every_websocket_is_closed_without_connecting_to_server(url):
    owner,browser,case,checks,events=harness();await owner.page(case,1280)
    closed=[]
    async def close(**options):closed.append(options)
    socket=SimpleNamespace(url=url,close=close)
    await browser.context.handlers["ws"](socket)
    assert closed==[dict(code=1008,reason="trusted harness WebSocket deny policy")]
    assert checks[-1][0]=="websocket_attempt_blocked"


async def test_missing_WS_guard_fails_closed_before_new_page_and_closes_context():
    owner,browser,case,checks,events=harness(True)
    with pytest.raises(AdapterUnavailable):await owner.page(case,1280)
    assert "new_page" not in events and browser.context.closed
    assert owner.contexts==[]


@pytest.mark.parametrize("url",["https://example.invalid/api/tickets","http://127.0.0.1:9999/api/tickets","file:///private"])
async def test_negative_page_route_cannot_override_origin_guard_and_fetch_elsewhere(url):
    owner,browser,case,checks,events=harness();aborted=[]
    async def abort():aborted.append(True)
    route=SimpleNamespace(request=SimpleNamespace(url=url),abort=abort)
    assert not await owner.guard_probe_route(route,case)
    assert aborted==[True] and checks[-1][0]=="negative_probe_external_request_blocked"
