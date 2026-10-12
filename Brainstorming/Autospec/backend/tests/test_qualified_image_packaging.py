"""Qualified artifacts never rebuild or publish through an unproven bridge."""
import json
import os
import threading
from types import SimpleNamespace
from uuid import uuid4

import pytest

from autospec.orchestrator import docker_deploy as deployment
from autospec.orchestrator.isolated_validation import IsolatedValidator,build_delivery_image
from autospec.orchestrator.sandbox import _docker_call
from autospec.validation.final_gate import source_snapshot


def fixture(tmp_path):
    root=tmp_path/'source';root.mkdir();(root/'main.py').write_text('# offline source identity fixture\n')
    state=SimpleNamespace(id='qualified-test',acceptance_contract_hash='c'*64)
    snapshot=source_snapshot(root).digest
    command=['/opt/venv/bin/python','main.py'];identifier='sha256:'+'a'*64
    image={'Id':identifier,'Os':'linux','Config':{'Labels':{'autospec.snapshot':snapshot},
        'WorkingDir':'/app','Cmd':command,'Entrypoint':None}}
    args=dict(network='autospec-net',host_port=8000,build_timeout=30,deploy_timeout=30,
        kind='backend',qualified_image_id=identifier,expected_snapshot=snapshot,expected_runtime_command=command)
    return root,state,args,image


def fake(monkeypatch,image):
    calls=[]
    aliases=set()
    def docker(argv,**kwargs):
        calls.append(argv)
        if argv[:2]==['image','inspect']:
            if argv[2]!=image['Id'] and argv[2] not in aliases:return 1,'No such image: '+argv[2]
            return 0,json.dumps([image])
        if argv[0]=='tag':aliases.add(argv[2]);return 0,''
        pytest.fail('unqualified mutating/probing command: '+str(argv))
    monkeypatch.setattr(deployment,'_docker',docker)
    for name in ('build_image','ensure_network','check_cross_reachability','replace_container','list_deployed'):
        monkeypatch.setattr(deployment,name,lambda *a,**kw:pytest.fail('contract cannot enter legacy deployment'))
    return calls


def test_web_image_is_packaged_but_not_deployed_and_never_rebuilt(tmp_path,monkeypatch):
    root,state,args,image=fixture(tmp_path);calls=fake(monkeypatch,image)
    before=source_snapshot(root).digest
    result=deployment.deploy_and_verify(state,root,**args)
    assert not result.ok and result.packaged and result.infra and result.image==image['Id']
    assert result.container=='' and result.host_port==0 and 'PUBLICATION_ISOLATION_UNAVAILABLE' in result.detail
    assert [a for a in calls if a[0]=='tag'][0][:2]==['tag',image['Id']]
    assert all(a[0] in {'image','tag'} for a in calls)
    assert source_snapshot(root).digest==before


@pytest.mark.parametrize('kind',['cli','library'])
def test_qualified_cli_library_without_registry_never_uses_legacy_or_unowned_alias(tmp_path,monkeypatch,kind):
    root,state,args,image=fixture(tmp_path);calls=fake(monkeypatch,image);args['kind']=kind
    result=deployment.deploy_and_verify(state,root,**args)
    assert not result.ok and result.packaged and result.container=='' and result.image==image['Id']
    assert 'PACKAGING_REGISTRY_REQUIRED' in result.detail and calls==[]


@pytest.mark.parametrize('wrong',['source','id','cmd','entrypoint','label','os'])
def test_bad_qualified_facts_are_refused_before_tag_or_publication(tmp_path,monkeypatch,wrong):
    root,state,args,image=fixture(tmp_path)
    if wrong=='source':(root/'main.py').write_text('# source drift\n')
    elif wrong=='id':image['Id']='sha256:'+'b'*64
    elif wrong=='cmd':image['Config']['Cmd']=['/opt/venv/bin/python','different.py']
    elif wrong=='entrypoint':image['Config']['Entrypoint']=['/bin/sh']
    elif wrong=='label':image['Config']['Labels']['autospec.snapshot']='b'*64
    elif wrong=='os':image['Os']='windows'
    calls=fake(monkeypatch,image)
    result=deployment.deploy_and_verify(state,root,**args)
    assert not result.ok and not result.packaged
    assert not any(a[0]=='tag' for a in calls)


def test_contract_missing_qualified_facts_never_falls_back_to_legacy(tmp_path,monkeypatch):
    root,state,args,image=fixture(tmp_path);calls=fake(monkeypatch,image)
    for field in ('qualified_image_id','expected_snapshot','expected_runtime_command'):args.pop(field)
    result=deployment.deploy_and_verify(state,root,**args)
    assert not result.ok and calls==[]


def test_existing_alias_name_is_not_adopted_or_retagged(tmp_path,monkeypatch):
    root,state,args,image=fixture(tmp_path);calls=[]
    def docker(argv,**kwargs):calls.append(argv);return 0,json.dumps([image])
    monkeypatch.setattr(deployment,'_docker',docker)
    result=deployment.deploy_and_verify(state,root,**args)
    assert not result.ok and 'ALIAS_OCCUPIED' in result.detail
    assert not any(a[0]=='tag' for a in calls)


def test_cancelled_tag_request_cleans_only_exact_owned_alias_without_cancellation_block(tmp_path,monkeypatch):
    root,state,args,image=fixture(tmp_path);event=threading.Event();calls=[];created=[]
    def docker(argv,**kwargs):
        calls.append(argv)
        if argv[0]=='tag':created.append(argv[2]);event.set();return 0,''
        if argv[:2]==['image','rm']:
            assert not deployment._cancelled() and argv[2] in created
            return 0,''
        if argv[:2]==['image','inspect']:
            if argv[2]==image['Id'] or argv[2] in created:return 0,json.dumps([image])
            return 1,'No such image'
        pytest.fail('no runtime/network operation allowed')
    monkeypatch.setattr(deployment,'_docker',docker);args['cancel_event']=event
    result=deployment.deploy_and_verify(state,root,**args)
    assert not result.ok and result.cancelled and not result.packaged
    assert ['image','rm',created[0]] in calls
    assert deployment._operation.cancel_event is None


@pytest.mark.skipif(os.environ.get('AUTOSPEC_REAL_LINUX_VALIDATION')!='1',reason='Opt-in actual immutable image inspect/tag without deployment')
def test_real_qualified_image_packaging_keeps_source_exact_and_never_starts_product(tmp_path):
    root,state,args,_=fixture(tmp_path)
    (root/'main.py').write_text('raise RuntimeError("PACKAGING_MUST_NOT_EXECUTE_PRODUCT")\n')
    (root/'pyproject.toml').write_text('[project]\nname="qualified-packaging-proof"\nversion="1.0.0"\nrequires-python=">=3.12"\ndependencies=[]\n')
    validator=IsolatedValidator(tmp_path/'cache',timeout=300);validator.manager.ensure_lock(root,'python')
    snapshot=source_snapshot(root).digest
    tag='autospec/qualified-packaging-proof:'+uuid4().hex
    alias=None
    try:
        ok,output=build_delivery_image(root,tag,runtime_command=args['expected_runtime_command'],evidence_root=tmp_path/'proof',snapshot_hash=snapshot)
        assert ok,output
        image=json.loads((tmp_path/'proof/delivery-build.json').read_bytes())['image_id']
        args.update(qualified_image_id=image,expected_snapshot=snapshot)
        result=deployment.deploy_and_verify(state,root,**args)
        assert not result.ok and result.packaged and result.image==image and result.container==''
        alias=result.detail.split('; alias ',1)[1]
        inspected=_docker_call(['docker','image','inspect',alias],capture_output=True,text=True,timeout=10)
        assert json.loads(inspected.stdout)[0]['Id']==image
        assert source_snapshot(root).digest==snapshot
    finally:
        for owned_tag in [alias,tag]:
            if owned_tag:_docker_call(['docker','image','rm',owned_tag],capture_output=True,text=True,timeout=10)
