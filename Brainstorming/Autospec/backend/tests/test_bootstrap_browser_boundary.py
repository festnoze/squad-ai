"""Bootstrap browser admission/lifecycle; no hostile JS executes on host."""
from pathlib import Path
from types import SimpleNamespace
import pytest
from autospec.orchestrator import bootstrap
from autospec.orchestrator.isolated_validation import RuntimeSession
from autospec.validation import browser_contracts


def runtime(tmp_path,monkeypatch):
    session=RuntimeSession(tmp_path,"image",["python"],port=8000)
    state=dict(container_id="a"*64,network_mode="none",running=True,published_ports={})
    monkeypatch.setattr(session,"_assert_owned",lambda:state["container_id"])
    monkeypatch.setattr(session,"inspect_configuration",lambda:dict(state))
    return session,state


async def test_model_shaped_browser_runtime_fails_before_driver_construction(monkeypatch):
    monkeypatch.setattr(browser_contracts,"PlaywrightHarness",lambda *a,**k:pytest.fail("driver must not be constructed"))
    with pytest.raises(bootstrap.BootstrapFailure,match="actual owned"):
        await bootstrap._browser_preflight(SimpleNamespace(origin="http://127.0.0.1:8123"),timeout_s=1,require_api=False)


@pytest.mark.parametrize("field,value",[("network_mode","host"),("running",False),("published_ports",{"8000/tcp":[]})])
async def test_bootstrap_requires_live_unpublished_netnone(tmp_path,monkeypatch,field,value):
    session,state=runtime(tmp_path,monkeypatch);state[field]=value
    monkeypatch.setattr(browser_contracts,"PlaywrightHarness",lambda *a,**k:pytest.fail("driver must not be constructed"))
    try:
        with pytest.raises(bootstrap.BootstrapFailure,match="NETNONE"):
            await bootstrap._browser_preflight(session,timeout_s=1,require_api=False)
    finally:session.server.server_close()


@pytest.mark.parametrize("problem",["none","host_browser","client_network","parent_restart","parent_stopped","bad_http","page_error","guard_failure","driver_failure"])
async def test_bootstrap_remote_receipt_and_cleanup_required(tmp_path,monkeypatch,problem):
    session,state=runtime(tmp_path,monkeypatch);constructed=[];closed=[];functions=[]
    class Page:
        def set_default_timeout(self,ms):assert 1<=ms<=15000
        def on(self,*args):pass
        async def goto(self,*a,**k):return SimpleNamespace(status=404 if problem=="bad_http" else 200)
        async def wait_for_function(self,script):
            functions.append(script)
            if problem=="parent_restart":state["container_id"]="b"*64
            if problem=="parent_stopped":state["running"]=False
    class Harness:
        def __init__(self,adapter,**options):
            constructed.append((adapter,options))
            self.browser_environment=dict(host_chromium=problem=="host_browser",parent_id="a"*64,
                network_mode="container:"+"a"*64,client_network_exposed=problem=="client_network")
        async def page(self,case,width):
            assert width==1280
            if problem=="driver_failure":raise RuntimeError("private-token must not be published")
            if problem=="page_error":case.console_errors.append("untrusted secret")
            if problem=="guard_failure":case.check("external",False,True)
            return Page()
        async def close(self):closed.append(True)
    monkeypatch.setattr(browser_contracts,"PlaywrightHarness",Harness)
    try:
        if problem=="none":
            detail=await bootstrap._browser_preflight(session,timeout_s=1,require_api=True)
            assert "Chromium Docker" in detail and "frontend → API probe OK" in detail
            assert len(functions)==2
        else:
            with pytest.raises(bootstrap.BootstrapFailure) as error:
                await bootstrap._browser_preflight(session,timeout_s=1,require_api=True)
            assert "private-token" not in str(error.value) and "untrusted secret" not in str(error.value)
        assert closed==[True]
        adapter,options=constructed[0]
        assert adapter.supervised_runtime is session and options==dict(bindings={},routes={"home":"/"})
        assert not hasattr(adapter,"trusted_fixture_local_browser")
    finally:session.server.server_close()


def test_legacy_host_browser_entrypoint_is_disabled_and_not_called_by_preflight():
    script=Path(bootstrap.__file__).with_name("isolated_browser.cjs").read_text(encoding="utf-8")
    assert "process.exitCode = 2" in script and "ISOLATION_UNAVAILABLE" in script
    assert "chromium.launch" not in script and "require('playwright')" not in script
    source=Path(bootstrap.__file__).read_text(encoding="utf-8").split("def _isolated_preflight",1)[1]
    assert "isolated_browser.cjs" not in source and "NODE_PATH" not in source and "_run_tracked" not in source
