"""Native regression: static OK text is not a frontend/API observation.

All fixture HTML/JS executes only in owned Docker, never on the host. Historical
native-v2.xml retains the observed pre-fix false acceptance; this regression now
requires rejection after the supervisor nonce-bound response correction.
"""
import hashlib
import json
import os
from pathlib import Path

import pytest

from autospec.orchestrator import bootstrap
from autospec.orchestrator.isolated_validation import RuntimeSession
from autospec.orchestrator.sandbox import _docker_call


SERVER=r'''from http.server import BaseHTTPRequestHandler,HTTPServer
import json
requests=[]
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  requests.append(self.path);open('/tmp/bootstrap-counter-requests.json','w').write(json.dumps(requests))
  self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.end_headers()
  self.wfile.write('<html><body><div id="root"><p>Frontend → API → base de données : OK</p></div></body></html>'.encode())
 def log_message(self,*a):pass
HTTPServer(('127.0.0.1',8000),Handler).serve_forever()
'''


@pytest.mark.skipif(os.environ.get("AUTOSPEC_BOOTSTRAP_COUNTERPROOF")!="1",reason="Explicit real NETNONE static-OK counterexample opt-in")
@pytest.mark.asyncio
async def test_native_bootstrap_rejects_literal_ok_without_actual_api_response(tmp_path):
    inspected=_docker_call(["docker","image","inspect","ghcr.io/astral-sh/uv:python3.12-bookworm-slim","--format","{{.Id}}"],
        capture_output=True,text=True,timeout=5,check=False)
    assert inspected.returncode==0,"pre-existing official factory image required"
    source=tmp_path/"empty-stage";source.mkdir()
    runtime=RuntimeSession(source,inspected.stdout.strip(),["/usr/local/bin/python","-I","-u","-c",SERVER],application_origin=True)
    try:
        runtime.__enter__()
        expected = {"status": "ok", "service": "autospec-bootstrap", "database": "ok", "probe": "supervisor-counterexample-nonce"}
        with pytest.raises(bootstrap.BootstrapFailure) as rejected:
            await bootstrap._browser_preflight(runtime,timeout_s=25,require_api=True,expected_health=expected)
        rc,out,err=runtime.exec(["/usr/local/bin/python","-I","-c","print(open('/tmp/bootstrap-counter-requests.json').read())"])
        assert rc==0,err
        paths=json.loads(out)
        assert paths and not any(path.startswith("/api/") for path in paths)
        root=os.environ.get("AUTOSPEC_BOOTSTRAP_COUNTERPROOF_ROOT")
        if root:
            target=Path(root);target.mkdir(parents=True,exist_ok=True)
            (target/"literal-ok-rejected.json").write_text(json.dumps(dict(
                scope="Actual NETNONE browser rejected static literal OK without observed frontend API response; NOT a complete product PASS",
                bootstrap_source_sha256=hashlib.sha256(Path(bootstrap.__file__).read_bytes()).hexdigest(),
                server_script_sha256=hashlib.sha256(SERVER.encode()).hexdigest(),detail=str(rejected.value),
                observed_http_paths=paths,api_calls=0,runtime=runtime.inspect_configuration()),indent=2))
    finally:runtime.close()
