"""Actual frontend bootstrap, generated scaffold JS only in Docker Chromium."""
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from autospec.orchestrator import bootstrap,workspace
from autospec.validation.browser_contracts import PlaywrightHarness


@pytest.mark.skipif(os.environ.get("AUTOSPEC_DOCKER_BOOTSTRAP_BROWSER")!="1",reason="explicit real frontend bootstrap opt-in")
@pytest.mark.parametrize("kind",["frontend","fullstack"])
async def test_real_frontend_bootstrap_renders_only_in_owned_netnone_browser(tmp_path,monkeypatch,kind):
    state=SimpleNamespace(id="isolated-browser-bootstrap",name="Isolated frontend bootstrap",streams=[],
        brownfield_path="",product_profile="auto",backend_language=SimpleNamespace(value="python"),
        technical_stack=dict(backend="none" if kind=="frontend" else "python",framework="none" if kind=="frontend" else "fastapi",
            frontend="react",database="none" if kind=="frontend" else "sqlite",kind=kind))
    monkeypatch.setattr(workspace,"workspace_dir",lambda _:tmp_path)
    workspace.scaffold(state,streams_enabled=False,ui_tests_enabled=False)
    result=bootstrap.prepare(state,tmp_path);assert result.ok,result.detail
    receipts=[]
    original=PlaywrightHarness.close
    async def retained_close(self):
        receipt=dict(self.browser_environment)
        await original(self)
        receipts.append(receipt)
    monkeypatch.setattr(PlaywrightHarness,"close",retained_close)
    verified=await bootstrap.verify(state,tmp_path,timeout_s=300)
    assert verified.ok,verified.detail
    assert "Chromium Docker" in verified.detail
    assert len(receipts)==1 and receipts[0]["host_chromium"] is False
    assert receipts[0]["network_mode"]=="container:"+receipts[0]["parent_id"]
    assert receipts[0]["client_network_exposed"] is False and receipts[0]["database_mount"] is False
    assert receipts[0]["user"]=="65532:65532" and receipts[0]["read_only"] is True
    destination=os.environ.get("AUTOSPEC_BOOTSTRAP_BROWSER_EVIDENCE_ROOT")
    if destination:
        root=Path(destination)/kind;root.mkdir(parents=True,exist_ok=True)
        (root/"receipt.json").write_text(json.dumps(dict(scope="real deterministic bootstrap fixture, not generated-product conformity",
            result=verified.detail,bootstrap_fingerprint=verified.fingerprint,browser=receipts[0],
            bootstrap_observer_sha256=hashlib.sha256(Path(bootstrap.__file__).read_bytes()).hexdigest()),indent=2),encoding="utf-8")
