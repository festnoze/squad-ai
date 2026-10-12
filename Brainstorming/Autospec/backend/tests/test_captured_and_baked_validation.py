"""No source bind when testing baked images; stdout is not stderr help text."""
import json
import os
import socket
import subprocess
import time
import urllib.request
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from autospec.orchestrator import isolated_validation as module
from autospec.orchestrator.isolated_validation import IsolatedValidator, RuntimeSession, build_delivery_image
from autospec.orchestrator.sandbox import _docker_call
from autospec.orchestrator.validation_environment import snapshot_product


def test_captured_never_merges_streams_or_exports_product_changes(tmp_path, monkeypatch):
    root=tmp_path/'source';root.mkdir();(root/'main.py').write_text('source')
    environment=SimpleNamespace(image='attested',fingerprint='proof')
    manager=SimpleNamespace(prepare=lambda *args:environment)
    def isolated(argv,stage,*args,**kwargs):
        assert stage!=root
        (stage/'main.py').write_text('mutated only inside disposable stage')
        return 0,'','diagnostic usage on stderr only'
    monkeypatch.setattr(module,'run_isolated',isolated)
    result=IsolatedValidator(tmp_path/'cache',manager=manager).run_captured(root,'python',['python','main.py','--help'])
    assert result==(0,'','diagnostic usage on stderr only',environment)
    assert (root/'main.py').read_text()=='source'


@pytest.mark.skipif(os.environ.get('AUTOSPEC_REAL_LINUX_VALIDATION')!='1',reason='Opt-in real net-none captured streams/timeout and baked-image proof')
def test_real_captured_streams_timeout_and_baked_source_not_stage(tmp_path):
    product=tmp_path/'product';product.mkdir()
    (product/'pyproject.toml').write_text('[project]\nname="baked-proof"\nversion="1.0.0"\nrequires-python=">=3.12"\ndependencies=[]\n')
    (product/'main.py').write_text('''from http.server import BaseHTTPRequestHandler,HTTPServer
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  self.send_response(200);self.end_headers();self.wfile.write(b'BAKED_SOURCE_ONLY')
HTTPServer(('0.0.0.0',8000),Handler).serve_forever()
''')
    validator=IsolatedValidator(tmp_path/'cache')
    validator.manager.ensure_lock(product,'python')
    rc,out,err,environment=validator.run_captured(product,'python',['/opt/venv/bin/python','-c',"import sys;print('stdout-help');print('stderr-diagnostic',file=sys.stderr)"])
    assert rc==0 and out.strip()=='stdout-help' and err.strip()=='stderr-diagnostic'
    validator.timeout=3
    with pytest.raises(subprocess.TimeoutExpired):
        validator.run_captured(product,'python',['/opt/venv/bin/python','-c','import time;time.sleep(60)'])
    validator.timeout=300
    tag='autospec/baked-probe:'+uuid.uuid4().hex
    ok,output=build_delivery_image(product,tag)
    assert ok,output
    try:
        inspected=_docker_call(['docker','image','inspect',tag],capture_output=True,text=True,timeout=10)
        image=json.loads(inspected.stdout)[0]['Id']
        # Divergent stage must NEVER mask /app baked into this exact image.
        (product/'main.py').write_text("raise RuntimeError('STAGE_SOURCE_MUST_NOT_RUN')\n")
        stage=snapshot_product(product,tmp_path/'stage')
        with RuntimeSession(stage,image,['/opt/venv/bin/python','main.py'],mount_stage=False) as session:
            deadline=time.monotonic()+30
            while True:
                try:
                    with urllib.request.urlopen(session.origin,timeout=10) as response: body=response.read()
                    break
                except OSError:
                    if time.monotonic()>deadline:raise AssertionError(session.logs())
                    time.sleep(.1)
            assert body==b'BAKED_SOURCE_ONLY'
            result=_docker_call(['docker','container','inspect',session.identifier],capture_output=True,text=True,timeout=10)
            container=json.loads(result.stdout)[0]
            assert container['Image']==image and not container['Mounts']
            assert container['HostConfig']['NetworkMode']=='none'
            session.restart()
            assert session.is_running()
        assert (stage/'main.py').read_text()=="raise RuntimeError('STAGE_SOURCE_MUST_NOT_RUN')\n"
    finally:
        # Remove only this test's random tag, never force-remove a shared ID.
        _docker_call(['docker','image','rm',tag],capture_output=True,text=True,timeout=10)
