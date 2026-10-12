"""External image-tag ownership; product code never runs on the host."""
import json
import os
import threading
from types import SimpleNamespace
from uuid import uuid4

import pytest

from autospec.orchestrator import owned_packages as packages,docker_deploy
from autospec.orchestrator.owned_packages import PackageRegistry,PackageSpec,PackageError
from autospec.validation.final_gate import source_snapshot


class FakeDocker:
    def __init__(self,spec):
        self.spec=spec;self.calls=[];self.aliases={};self.on_tag=None;self.image_present=True
        self.image={'Id':spec.image_id,'Os':'linux','Config':{'WorkingDir':'/app','Cmd':list(spec.runtime_command),
            'Entrypoint':None,'Labels':{'autospec.snapshot':spec.snapshot_hash}}}
    def call(self,argv,**kw):
        self.calls.append(argv)
        if argv[1:3]==['image','inspect']:
            name=argv[3]
            image=self.image if name==self.spec.image_id and self.image_present else self.aliases.get(name)
            return SimpleNamespace(returncode=0 if image else 1,stdout=json.dumps(image) if image else '',stderr='' if image else 'No such image')
        if argv[1]=='tag':
            self.aliases[argv[3]]=dict(self.image)
            if self.on_tag:self.on_tag(argv)
            return SimpleNamespace(returncode=0,stdout='',stderr='')
        if argv[1:3]==['image','rm']:
            assert argv[3]!=self.spec.image_id and ':latest' not in argv[3]
            self.aliases.pop(argv[3],None)
            return SimpleNamespace(returncode=0,stdout='',stderr='')
        pytest.fail('package cannot start/build/probe/delete non-alias resources: '+str(argv))


def setup(tmp_path,monkeypatch):
    source=tmp_path/'source';source.mkdir();(source/'main.py').write_text('raise RuntimeError("MUST_NOT_EXECUTE_WHILE_PACKAGING")\n')
    spec=PackageSpec('sha256:'+'a'*64,source_snapshot(source).digest,'c'*64,('/opt/venv/bin/python','main.py'))
    fake=FakeDocker(spec);monkeypatch.setattr(packages,'_docker_call',fake.call)
    registry=PackageRegistry(tmp_path/'supervisor')
    return source,spec,fake,registry


def test_package_external_journal_reconcile_and_detach_only_exact_uuid_alias(tmp_path,monkeypatch):
    source,spec,fake,registry=setup(tmp_path,monkeypatch)
    foreign='autospec/unrelated:owned-by-someone-else';fake.aliases[foreign]=dict(fake.image)
    row=registry.package('project',source,spec)
    assert row['status']=='packaged' and row['absence_checked'] is True and row['alias'].endswith(':'+row['owner'])
    reused=registry.package('project',source,spec)
    assert row['created_this_call'] is True and reused['created_this_call'] is False
    assert {k:v for k,v in reused.items() if k!='created_this_call'}=={k:v for k,v in row.items() if k!='created_this_call'}
    assert PackageRegistry(registry.root).inspect('project',expected=spec)['packaged']
    assert len([a for a in fake.calls if a[1]=='tag'])==1
    detached=registry.detach('project');assert detached['status']=='detached' and not registry.inspect('project')['packaged']
    assert foreign in fake.aliases and spec.image_id not in [a[-1] for a in fake.calls if a[1:3]==['image','rm']]
    assert source_snapshot(source).digest==spec.snapshot_hash


@pytest.mark.parametrize('defect',['id','os','cmd','entrypoint','label','workdir'])
def test_image_facts_rejected_before_tag(defect,tmp_path,monkeypatch):
    source,spec,fake,registry=setup(tmp_path,monkeypatch)
    if defect=='id':fake.image['Id']='sha256:'+'b'*64
    elif defect=='os':fake.image['Os']='windows'
    elif defect=='cmd':fake.image['Config']['Cmd']=['wrong']
    elif defect=='entrypoint':fake.image['Config']['Entrypoint']=['/bin/sh']
    elif defect=='label':fake.image['Config']['Labels']['autospec.snapshot']='b'*64
    elif defect=='workdir':fake.image['Config']['WorkingDir']='/other'
    with pytest.raises(PackageError,match='FACTS_DIFFER'):registry.package('project',source,spec)
    assert not any(a[1]=='tag' for a in fake.calls)


def test_foreign_replaced_alias_and_unknown_journal_never_grant_cleanup(tmp_path,monkeypatch):
    source,spec,fake,registry=setup(tmp_path,monkeypatch);row=registry.package('project',source,spec)
    fake.aliases[row['alias']]={'Id':'sha256:'+'b'*64};before=len(fake.calls)
    with pytest.raises(PackageError,match='IDENTITY_DIFFER'):registry.detach('project')
    assert not any(a[1:3]==['image','rm'] for a in fake.calls[before:])
    path,_=registry._paths('project');path.write_text('{}')
    with pytest.raises(PackageError,match='JOURNAL_INVALID'):registry.detach('project')


def test_cancel_during_tag_detaches_only_alias_recorded_before_mutation(tmp_path,monkeypatch):
    source,spec,fake,registry=setup(tmp_path,monkeypatch);cancel=threading.Event()
    def after_tag(argv):
        record=registry._read('project')
        assert record['status']=='prepared' and record['alias']==argv[-1] and record['absence_checked']
        cancel.set()
    fake.on_tag=after_tag
    with pytest.raises(PackageError,match='CANCELLED'):registry.package('project',source,spec,cancel_event=cancel)
    row=registry._read('project');assert row['status']=='detached' and not fake.aliases
    assert [a for a in fake.calls if a[1:3]==['image','rm']]==[['docker','image','rm',row['alias']]]


def test_update_refused_without_explicit_detach_keeps_previous_alias(tmp_path,monkeypatch):
    source,spec,fake,registry=setup(tmp_path,monkeypatch);row=registry.package('project',source,spec)
    new=PackageSpec(**{**spec.payload(),'contract_hash':'d'*64})
    with pytest.raises(PackageError,match='EXPLICIT_DETACH'):registry.package('project',source,new)
    assert fake.aliases[row['alias']]['Id']==spec.image_id


def test_missing_alias_does_not_silently_repackage_or_adopt_latest(tmp_path,monkeypatch):
    source,spec,fake,registry=setup(tmp_path,monkeypatch);row=registry.package('project',source,spec)
    del fake.aliases[row['alias']]
    with pytest.raises(PackageError,match='OWNED_ALIAS_MISSING'):registry.package('project',source,spec)
    assert not registry.inspect('project')['packaged']
    registry.detach('project')  # already absent: logical cleanup, no Docker rm
    assert not any(a[1:3]==['image','rm'] for a in fake.calls)


def test_facade_qualified_package_is_inspected_by_sha_and_detached_without_legacy(tmp_path,monkeypatch):
    source,spec,fake,registry=setup(tmp_path,monkeypatch);state=SimpleNamespace(id='project',acceptance_contract_hash=spec.contract_hash)
    monkeypatch.setattr(docker_deploy,'_docker',lambda *a,**k:pytest.fail('qualified packages never inspect latest or legacy container'))
    result=docker_deploy.deploy_and_verify(state,source,network='UNUSED',host_port=0,build_timeout=30,deploy_timeout=30,
        kind='cli',qualified_image_id=spec.image_id,expected_snapshot=spec.snapshot_hash,
        expected_runtime_command=spec.runtime_command,packaging_root=registry.root)
    assert result.ok and result.packaged and result.image==spec.image_id and not result.container
    assert result.created_package_alias
    inspect=docker_deploy.inspect_packaged_image('project',packaging_root=registry.root,qualified_image_id=spec.image_id,
        expected_snapshot=spec.snapshot_hash,expected_runtime_command=spec.runtime_command,expected_contract_hash=spec.contract_hash)
    assert inspect.ok and inspect.image==spec.image_id
    assert docker_deploy.undeploy('project',packaging_root=registry.root).ok
    assert not fake.aliases
    stopped=docker_deploy.inspect_packaged_image('project',packaging_root=registry.root)
    assert stopped.skipped and not stopped.ok  # startup does not turn deliberate detach into failure


def test_late_cancel_receipt_cannot_detach_newer_package_journal(tmp_path,monkeypatch):
    source,spec,fake,registry=setup(tmp_path,monkeypatch)
    first=registry.package('project',source,spec);registry.detach('project')
    second=registry.package('project',source,spec)
    assert first['alias']!=second['alias'] and second['created_this_call']
    before=len(fake.calls)
    refused=docker_deploy.undeploy('project',packaging_root=registry.root,
        expected_package_alias=first['alias'],expected_package_image_id=spec.image_id)
    assert not refused.ok and 'RECEIPT_IDENTITY_DIFFER' in refused.detail
    assert second['alias'] in fake.aliases and not any(a[1:3]==['image','rm'] for a in fake.calls[before:])
    assert docker_deploy.undeploy('project',packaging_root=registry.root,
        expected_package_alias=second['alias'],expected_package_image_id=spec.image_id).ok


def test_facade_reuse_has_no_new_creation_receipt_even_without_state_flush(tmp_path,monkeypatch):
    source,spec,fake,registry=setup(tmp_path,monkeypatch)
    first=registry.package('project',source,spec)
    state=SimpleNamespace(id='project',acceptance_contract_hash=spec.contract_hash)  # no prior CID/image state
    result=docker_deploy.deploy_and_verify(state,source,network='UNUSED',host_port=0,build_timeout=30,deploy_timeout=30,
        kind='library',qualified_image_id=spec.image_id,expected_snapshot=spec.snapshot_hash,
        expected_runtime_command=spec.runtime_command,packaging_root=registry.root)
    assert result.ok and not result.created_package_alias and first['alias'] in fake.aliases
    registry.detach('project')


def test_uncertain_or_missing_live_package_does_not_become_intentional_skip(tmp_path,monkeypatch):
    source,spec,fake,registry=setup(tmp_path,monkeypatch);first=registry.package('project',source,spec)
    fake.aliases.pop(first['alias'])
    missing=docker_deploy.inspect_packaged_image('project',packaging_root=registry.root)
    assert not missing.ok and not missing.skipped
    row=registry._read('project');row['status']='uncertain';registry._write(row)
    uncertain=docker_deploy.inspect_packaged_image('project',packaging_root=registry.root)
    assert not uncertain.ok and uncertain.infra and not uncertain.skipped
    registry.detach('project')


def test_source_edit_during_cached_alias_inspection_refused_preserving_old_package(tmp_path,monkeypatch):
    source,spec,fake,registry=setup(tmp_path,monkeypatch);row=registry.package('project',source,spec)
    original=fake.call
    def edit(argv,**kwargs):
        result=original(argv,**kwargs)
        if argv[1:3]==['image','inspect'] and argv[3]==row['alias']:
            (source/'main.py').write_text('# concurrent factory-side source edit\n')
        return result
    monkeypatch.setattr(packages,'_docker_call',edit);before=len(fake.calls)
    with pytest.raises(PackageError,match='SOURCE_CHANGED_DURING_REUSE'):registry.package('project',source,spec)
    assert row['alias'] in fake.aliases
    assert not any(a[1]=='tag' or a[1:3]==['image','rm'] for a in fake.calls[before:])
    monkeypatch.setattr(packages,'_docker_call',original);registry.detach('project')


@pytest.mark.skipif(os.environ.get('AUTOSPEC_REAL_LINUX_VALIDATION')!='1',reason='Opt-in actual image alias/shared identity proof; product not executed')
def test_real_qualified_alias_detach_preserves_shared_image_and_other_alias(tmp_path):
    from autospec.orchestrator.isolated_validation import IsolatedValidator,build_delivery_image
    from autospec.orchestrator.sandbox import _docker_call
    source=tmp_path/'source';source.mkdir()
    (source/'pyproject.toml').write_text('[project]\nname="owned-packaging-proof"\nversion="1.0.0"\nrequires-python=">=3.12"\ndependencies=[]\n')
    (source/'main.py').write_text('raise RuntimeError("MUST_NOT_START_PRODUCT_WHILE_PACKAGING")\n')
    validator=IsolatedValidator(tmp_path/'cache',timeout=300);validator.manager.ensure_lock(source,'python')
    snapshot=source_snapshot(source).digest;command=('/opt/venv/bin/python','main.py')
    tag='autospec/package-builder-proof:'+uuid4().hex;other='autospec/package-shared-proof:'+uuid4().hex
    registry=PackageRegistry(tmp_path/'supervisor')
    try:
        ok,output=build_delivery_image(source,tag,runtime_command=command,evidence_root=tmp_path/'build',snapshot_hash=snapshot)
        assert ok,output
        image=json.loads((tmp_path/'build/delivery-build.json').read_bytes())['image_id']
        assert _docker_call(['docker','tag',image,other],capture_output=True,text=True,timeout=10).returncode==0
        spec=PackageSpec(image,snapshot,'c'*64,command)
        row=registry.package('project',source,spec)
        assert registry.inspect('project',expected=spec)['packaged']
        removed=registry.detach('project');assert removed['status']=='detached'
        assert packages._image('docker',row['alias']) is None
        assert packages._image('docker',other)['Id']==image and packages._image('docker',image)['Id']==image
        assert source_snapshot(source).digest==snapshot
        if os.environ.get('AUTOSPEC_PACKAGE_PROOF_ROOT'):
            from pathlib import Path
            from autospec.orchestrator.dependencies import atomic_json
            atomic_json(Path(os.environ['AUTOSPEC_PACKAGE_PROOF_ROOT'])/'package-native.json',
                {'initial':row,'detached':removed,'shared_alias':other,'shared_image_id':packages._image('docker',other)['Id'],
                 'owned_alias_absent':packages._image('docker',row['alias']) is None,'source_unchanged':source_snapshot(source).digest==snapshot})
    finally:
        if registry._read('project') is not None:registry.detach('project')
        for alias in (other,tag):_docker_call(['docker','image','rm',alias],capture_output=True,text=True,timeout=10,check=False)
