"""Real pinned-browser invalidation across product NETNONE recreation."""
import asyncio
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from autospec.orchestrator.isolated_validation import RuntimeSession
from autospec.orchestrator.sandbox import _docker_call
from autospec.validation.browser_contracts import PlaywrightHarness
from autospec.validation.support_adapter import AdapterUnavailable
from tests.test_docker_browser_real import SERVER


@pytest.mark.skipif(os.environ.get("AUTOSPEC_DOCKER_BROWSER_TESTS")!="1",reason="opt-in owned Docker browser restart proof")
async def test_actual_old_browser_after_restart_is_env_unavailable_not_product_fail_or_host_fallback(tmp_path,monkeypatch):
    from playwright.async_api import BrowserType
    async def forbidden_host_launch(*args,**kwargs): raise AssertionError("host Chromium forbidden")
    monkeypatch.setattr(BrowserType,"launch",forbidden_host_launch)
    image=_docker_call(["docker","image","inspect","ghcr.io/astral-sh/uv:python3.12-bookworm-slim","--format","{{.Id}}"],
        capture_output=True,text=True,timeout=5,check=False)
    assert image.returncode==0
    stage=tmp_path/"stage";stage.mkdir()
    runtime=RuntimeSession(stage,image.stdout.strip(),["/usr/local/bin/python","-I","-u","-c",SERVER],application_origin=True)
    old=fresh=None
    try:
        await asyncio.to_thread(runtime.__enter__)
        adapter=SimpleNamespace(base_url=runtime.origin,supervised_runtime=runtime,live_sqlite=True,manifest=SimpleNamespace(accounts={}))
        def owner():return PlaywrightHarness(adapter,bindings={},routes={"home":"/"})
        def case():return SimpleNamespace(requests=[],console_errors=[],check=lambda *args:None)
        old=owner();page=await old.page(case(),1280)
        assert await page.locator("h1").inner_text()=="Remote isolated browser"
        before=dict(old.browser_environment);old_parent=runtime.identifier;old_browser=old.docker_browser.identifier
        await asyncio.to_thread(runtime.restart)
        assert runtime.identifier!=old_parent and runtime.is_running()
        with pytest.raises(AdapterUnavailable,match="no namespace adoption"):
            await old.page(case(),1280)
        with pytest.raises(AdapterUnavailable):await old.page(case(),1280)
        absent=_docker_call(["docker","container","inspect",old_browser],capture_output=True,text=True,timeout=5,check=False)
        assert absent.returncode!=0 and runtime.is_running()
        fresh=owner();new_page=await fresh.page(case(),1280)
        assert await new_page.locator("h1").inner_text()=="Remote isolated browser"
        assert fresh.browser_environment["network_mode"]=="container:"+runtime.identifier
        assert fresh.browser_environment["host_chromium"] is False
        selected=os.environ.get("AUTOSPEC_DOCKER_BROWSER_RESTART_EVIDENCE_ROOT")
        if selected:
            target=Path(selected).resolve();target.mkdir(parents=True,exist_ok=True)
            (target/"receipt.json").write_bytes(json.dumps(dict(scope="owned trusted-fixture browser lifecycle meta-test",
                old_environment=before,new_environment=fresh.browser_environment,
                parent_changed=runtime.identifier!=old_parent,old_browser_removed=True,
                old_harness_refused_without_host_launch=True,new_explicit_harness_actual_http=True,
                runtime=runtime.inspect_configuration()),sort_keys=True,ensure_ascii=True).encode("utf-8"))
    finally:
        if old:await old.close()
        if fresh:await fresh.close()
        runtime.close()
