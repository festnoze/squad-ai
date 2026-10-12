"""Opt-in actual OS boundary. All JavaScript executes only inside Docker.

AUTOSPEC_DOCKER_BROWSER_TESTS=1, pre-existing official Python factory base.
These proofs are observer meta-tests, not 57-ID generated-product acceptance.
"""
import asyncio
import hashlib
import json
import os
import threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

from autospec.orchestrator.isolated_validation import RuntimeSession
from autospec.orchestrator.sandbox import _docker_call
from autospec.validation.browser_contracts import PlaywrightHarness

REAL=pytest.mark.skipif(os.environ.get("AUTOSPEC_DOCKER_BROWSER_TESTS")!="1",reason="explicit Docker browser proof opt-in")
SERVER=r'''from http.server import BaseHTTPRequestHandler,HTTPServer
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  self.send_response(200);self.send_header('Content-Type','text/html');self.send_header('Set-Cookie','probe=owned; HttpOnly; SameSite=Strict; Path=/');self.end_headers()
  self.wfile.write((self.headers.get('Cookie','') if self.path=='/echo' else '<html><body><h1>Remote isolated browser</h1><script>document.body.dataset.origin=location.origin</script></body></html>').encode())
 def log_message(self,*a):pass
HTTPServer(('127.0.0.1',8000),Handler).serve_forever()
'''
PROBE=r'''const fs=require('fs'),dgram=require('dgram');
const result={uid:process.getuid(),docker_socket:fs.existsSync('/var/run/docker.sock'),
 database_mount:fs.existsSync('/var/lib/autospec-validation'),product_source:fs.existsSync('/app')};
try{fs.writeFileSync('/opt/autospec-browser/readonly-probe','x');result.root_write='allowed'}catch(e){result.root_write=e.code}
const socket=dgram.createSocket('udp4');socket.send(Buffer.from('owned-negative-network-probe'),3478,'198.51.100.1',e=>{
 result.external_udp=e?e.code:'sent';socket.close();process.stdout.write(JSON.stringify(result));});
'''


@REAL
async def test_real_remote_browser_has_origin_cookies_no_host_loopback_db_socket_or_udp(tmp_path):
    inspected=_docker_call(["docker","image","inspect","ghcr.io/astral-sh/uv:python3.12-bookworm-slim","--format","{{.Id}}"],capture_output=True,text=True,timeout=5,check=False)
    assert inspected.returncode==0,"pre-existing official Python factory image required"
    stage=tmp_path/"stage";stage.mkdir()
    runtime=RuntimeSession(stage,inspected.stdout.strip(),["/usr/local/bin/python","-I","-u","-c",SERVER],application_origin=True)
    seen=[]
    class Canary(BaseHTTPRequestHandler):
        def do_GET(self):seen.append(self.path);self.send_response(200);self.end_headers();self.wfile.write(b"HOST")
        def log_message(self,*a):pass
    canary=ThreadingHTTPServer(("127.0.0.1",0),Canary);thread=threading.Thread(target=canary.serve_forever,daemon=True);thread.start()
    harness=None;browser_id=None;receipt=None
    try:
        await asyncio.to_thread(runtime.__enter__)
        adapter=SimpleNamespace(base_url=runtime.origin,supervised_runtime=runtime,live_sqlite=True,manifest=SimpleNamespace(accounts={}))
        harness=PlaywrightHarness(adapter,bindings={},routes={"home":"/"})
        await harness.start();browser_id=harness.docker_browser.identifier
        receipt=dict(harness.browser_environment)
        # Deliberately omit API route guards for this trusted OS negative probe:
        # failure to reach host must come from NETNONE, not route interception.
        context=await harness.browser.new_context(service_workers="block");harness.contexts.append(context)
        page=await context.new_page();await page.goto(runtime.origin)
        assert await page.locator("h1").inner_text()=="Remote isolated browser"
        assert await page.locator("body").get_attribute("data-origin")==runtime.origin
        assert "probe=owned" in await page.evaluate("fetch('/echo').then(r=>r.text())")
        host_url=f"http://127.0.0.1:{canary.server_address[1]}/owned-canary"
        assert await page.evaluate("async url=>{try{await fetch(url,{signal:AbortSignal.timeout(1500)});return false}catch(_){return true}}",host_url)
        assert seen==[]
        result=_docker_call(["docker","exec",browser_id,"node","--eval",PROBE],capture_output=True,text=True,timeout=10,check=False)
        assert result.returncode==0
        observed=json.loads(result.stdout)
        assert observed==dict(uid=65532,docker_socket=False,database_mount=False,product_source=False,root_write="EROFS",external_udp="ENETUNREACH")
        assert receipt["network_mode"]=="container:"+runtime.identifier
        assert receipt["host_chromium"] is False and receipt["client_network_exposed"] is False
        evidence=os.environ.get("AUTOSPEC_DOCKER_BROWSER_EVIDENCE_ROOT")
        if evidence:
            root=Path(evidence);root.mkdir(parents=True,exist_ok=True)
            screenshot=root/"remote-netnone.png";await page.screenshot(path=str(screenshot))
            receipt.update(observed=observed,host_canary_requests=seen,origin_preserved=True,cookie_roundtrip=True,
                scope="actual isolated browser meta-test, not generated product acceptance",screenshot_sha256=hashlib.sha256(screenshot.read_bytes()).hexdigest())
            (root/"receipt.json").write_text(json.dumps(receipt,sort_keys=True,indent=2),encoding="utf-8")
    finally:
        if harness:await harness.close()
        if browser_id:
            absent=_docker_call(["docker","container","inspect",browser_id],capture_output=True,text=True,timeout=5,check=False)
            assert absent.returncode!=0 and runtime.is_running(),"only browser removed; owned parent remains active"
        runtime.close();canary.shutdown();canary.server_close();thread.join(timeout=2)
