"""Factory baked CMD proofs; generated/runtime code is never executed on host."""
import json
import os
import time
import urllib.request
from uuid import uuid4

import pytest

from autospec.orchestrator.isolated_validation import RuntimeSession,IsolatedValidator,build_delivery_image
from autospec.orchestrator.validation_environment import snapshot_product
from autospec.orchestrator.sandbox import _docker_call
from autospec.validation.final_gate import source_snapshot
from tests.test_runtime_session import docker_fake


def test_plain_baked_launch_never_overrides_image_entrypoint_or_argv(tmp_path,docker_fake):
    command=['python','main.py'];image='sha256:'+'a'*64
    with RuntimeSession(tmp_path,image,command,mount_stage=False,use_image_command=True) as runtime:
        launches=[row[0] for row in docker_fake.calls if row[0][1]=='run' and '-d' in row[0]]
        assert len(launches)==1
        assert launches[0][-1]==image and '--entrypoint' not in launches[0] and '-v' not in launches[0]
        assert '--network' in launches[0] and launches[0][launches[0].index('--network')+1]=='none'
        assert runtime.command==command
    assert not docker_fake.containers


@pytest.mark.parametrize('mismatch',['cmd','entrypoint','source_bind'])
def test_baked_command_mismatch_cannot_start_with_repair_overlay(tmp_path,docker_fake,mismatch):
    command=['python','main.py'];image='sha256:'+'a'*64
    if mismatch=='cmd':docker_fake.baked_command=['python','another.py']
    if mismatch=='entrypoint':docker_fake.baked_entrypoint=['/bin/sh','-c']
    if mismatch=='source_bind':
        with pytest.raises(RuntimeError):RuntimeSession(tmp_path,image,command,use_image_command=True)
        return
    session=RuntimeSession(tmp_path,image,command,mount_stage=False,use_image_command=True,persistent_database=True)
    with pytest.raises(RuntimeError,match='Baked command/entrypoint'):session.__enter__()
    assert session.closed and docker_fake.volume is None
    assert not any(row[0][1] in {'run','exec'} for row in docker_fake.calls)


@pytest.mark.parametrize('command',[[],['-invalid'],['python','bad\x00'],['python']*201])
def test_runtime_command_is_typed_and_bounded_before_any_launch(tmp_path,command):
    with pytest.raises(RuntimeError):RuntimeSession(tmp_path,'image',command)


@pytest.mark.skipif(os.environ.get('AUTOSPEC_REAL_LINUX_VALIDATION')!='1',reason='Opt-in real immutable image default CMD; Linux NETNONE')
@pytest.mark.parametrize('ecosystem',['python','node'])
def test_real_default_cmd_starts_reviewed_python_app_or_node_esm_without_overlay(tmp_path,ecosystem):
    root=tmp_path/'product';root.mkdir()
    if ecosystem=='python':
        (root/'pyproject.toml').write_text('[project]\nname="plain-image-proof"\nversion="1.0.0"\nrequires-python=">=3.12"\ndependencies=["fastapi==0.136.3","uvicorn==0.49.0"]\n')
        (root/'main.py').write_text('from fastapi import FastAPI\napp=FastAPI()\n@app.get("/api/health")\ndef health():return {"baked":True}\n')
        command=['/opt/venv/bin/python','-m','uvicorn','main:app','--host','0.0.0.0','--port','8000']
    else:
        (root/'package.json').write_text(json.dumps({'name':'plain-image-proof','version':'1.0.0','type':'module','dependencies':{'react':'19.0.0'}}))
        (root/'main.js').write_text('import React from "react";import http from "node:http";http.createServer((req,res)=>{res.setHeader("Content-Type","application/json");res.end(JSON.stringify({baked:true,react:React.version}));}).listen(8000,"0.0.0.0");\n')
        command=['node','main.js']
    validator=IsolatedValidator(tmp_path/'cache',timeout=300)
    validator.manager.ensure_lock(root,ecosystem)
    snapshot=source_snapshot(root).digest
    tag='autospec/plain-command-proof:'+uuid4().hex
    try:
        ok,output=build_delivery_image(root,tag,runtime_command=command,evidence_root=tmp_path/'proof',snapshot_hash=snapshot)
        assert ok,output
        receipt=json.loads((tmp_path/'proof/delivery-build.json').read_bytes())
        assert receipt['runtime_command']==command and receipt['runtime_command_mode']=='explicit-factory'
        image=receipt['image_id']
        inspected=_docker_call(['docker','image','inspect',image],capture_output=True,text=True,timeout=10)
        config=json.loads(inspected.stdout)[0]['Config']
        assert config['Cmd']==command and config.get('Entrypoint') in (None,[])
        stage=snapshot_product(root,tmp_path/'stage')
        (stage/('main.py' if ecosystem=='python' else 'main.js')).write_text('STAGE_MUST_NOT_EXECUTE')
        with RuntimeSession(stage,image,command,mount_stage=False,use_image_command=True,ecosystem=ecosystem) as runtime:
            deadline=time.monotonic()+30
            while True:
                try:
                    with urllib.request.urlopen(runtime.origin+'/api/health',timeout=5) as response:body=json.load(response)
                    break
                except OSError:
                    if time.monotonic()>deadline:raise AssertionError(runtime.logs())
                    time.sleep(.1)
            assert body['baked'] is True
            if ecosystem=='node':assert body['react']=='19.0.0'
            inspect=_docker_call(['docker','container','inspect',runtime.identifier],capture_output=True,text=True,timeout=10)
            value=json.loads(inspect.stdout)[0]
            assert value['Config']['Cmd']==command and value['Config'].get('Entrypoint') in (None,[]) and not value['Mounts']
            assert value['HostConfig']['NetworkMode']=='none' and value['HostConfig']['ReadonlyRootfs'] is True
        wrong=RuntimeSession(stage,image,[*command,'--not-the-reviewed-command'],mount_stage=False,use_image_command=True,ecosystem=ecosystem)
        with pytest.raises(RuntimeError,match='Baked command/entrypoint'):wrong.__enter__()
        assert wrong.closed and wrong.identifier is None
        assert source_snapshot(root).digest==snapshot
    finally:
        # Only this test's random tag, not a forced shared image-ID removal.
        _docker_call(['docker','image','rm',tag],capture_output=True,text=True,timeout=10)
