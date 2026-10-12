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


@pytest.mark.skipif(os.environ.get("AUTOSPEC_DOCKER_BOOTSTRAP_BROWSER")!="1",reason="explicit real bootstrap false-green counterexample opt-in")
@pytest.mark.parametrize("mode",["static_ok","wrong_nonce","actual_frontend_fetch"])
async def test_real_bootstrap_requires_frontend_originated_nonce_bound_api_response(tmp_path,mode):
    from autospec.orchestrator.isolated_validation import RuntimeSession
    from autospec.orchestrator.sandbox import _docker_call
    inspected=_docker_call(["docker","image","inspect","ghcr.io/astral-sh/uv:python3.12-bookworm-slim","--format","{{.Id}}"],
        capture_output=True,text=True,timeout=5,check=False)
    assert inspected.returncode==0,"pre-existing official factory image required"
    expected=dict(status="ok",service="autospec-bootstrap",database="ok",probe="supervisor-nonce-not-product-output")
    body=dict(expected,probe="wrong") if mode=="wrong_nonce" else expected
    html='<html><meta charset="utf-8"><body><div id="root"><p>Frontend → API → base de données : OK</p></div>'
    if mode!="static_ok":html+='<script>fetch("/api/health").then(r=>r.json()).then(x=>window.health=x)</script>'
    html+='</body></html>'
    server=f'''from http.server import BaseHTTPRequestHandler,HTTPServer
import json
body={body!r}
html={html!r}
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  self.send_response(200);self.send_header('Content-Type','application/json' if self.path=='/api/health' else 'text/html; charset=utf-8');self.end_headers()
  self.wfile.write(json.dumps(body).encode() if self.path=='/api/health' else html.encode())
 def log_message(self,*a):pass
HTTPServer(('127.0.0.1',8000),Handler).serve_forever()
'''
    source=tmp_path/"empty-stage";source.mkdir()
    with RuntimeSession(source,inspected.stdout.strip(),["/usr/local/bin/python","-I","-u","-c",server],application_origin=True) as runtime:
        if mode=="actual_frontend_fetch":
            detail=await bootstrap._browser_preflight(runtime,timeout_s=30,require_api=True,expected_health=expected)
            assert "frontend → API probe OK" in detail
        else:
            with pytest.raises(bootstrap.BootstrapFailure):
                await bootstrap._browser_preflight(runtime,timeout_s=15,require_api=True,expected_health=expected)
