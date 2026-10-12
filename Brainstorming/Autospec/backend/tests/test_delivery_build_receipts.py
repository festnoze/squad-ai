"""Factory build receipts distinguish executed commands and attested cache layers."""
import hashlib
import json
import os
import uuid
from pathlib import Path

import pytest

from autospec.orchestrator import validation_environment as environments
from autospec.orchestrator import isolated_validation as module
from autospec.orchestrator.validation_environment import LinuxEnvironment, LinuxEnvironmentManager
from autospec.orchestrator.isolated_validation import build_delivery_image
from autospec.validation.final_gate import source_snapshot


def _source(root, frontend=False):
    root.mkdir()
    (root/'pyproject.toml').write_text('[project]\nname="delivery-receipt-proof"\nversion="1.0.0"\nrequires-python=">=3.12"\ndependencies=[]\n')
    (root/'uv.lock').write_text('version=1\nrevision=3\n')
    (root/'main.py').write_text('print("baked source")\n')
    if frontend:
        front = root/'frontend'; front.mkdir(); (front/'src').mkdir()
        (front/'package.json').write_text(json.dumps({'name':'delivery-receipt-front-proof','version':'1.0.0','type':'module',
            'devDependencies':{'vite':'5.4.21','typescript':'5.9.3'}}))
        (front/'package-lock.json').write_text(json.dumps({'lockfileVersion':3,'packages':{}}))
        (front/'tsconfig.json').write_text(json.dumps({'compilerOptions':{'target':'ES2022','module':'ESNext','moduleResolution':'Bundler','strict':True},'include':['src']}))
        (front/'index.html').write_text('<html><body><div id="app"></div><script type="module" src="/src/main.ts"></script></body></html>')
        (front/'src/main.ts').write_text('document.getElementById("app")!.textContent="Receipt proof";\n')


def test_dependency_prepare_records_builder_and_verified_cache_separately(tmp_path, monkeypatch):
    root=tmp_path/'product'; _source(root)
    manager=LinuxEnvironmentManager(tmp_path/'cache')
    base={'Id':'sha256:'+'a'*64,'Architecture':'amd64','RepoDigests':['factory/base@sha256:'+'b'*64]}
    monkeypatch.setattr(manager,'_base',lambda _:base)
    images={}
    monkeypatch.setattr(manager,'_image',lambda name:images[name])
    calls=[]
    def build(argv,stdin,cwd,timeout):
        calls.append(argv)
        context=Path(cwd)
        assert {p.name for p in context.iterdir()}=={'pyproject.toml','uv.lock','Dockerfile'}
        fingerprint=argv[argv.index('--label')+1].split('=',1)[1]
        image={'Id':'sha256:'+'c'*64,'Config':{'Labels':{'autospec.environment':fingerprint}}}
        images[argv[argv.index('-t')+1]]=image;images[image['Id']]=image
        return 0,'factory builder executed',''
    monkeypatch.setattr(environments,'_run_tracked',build)
    first={};environment=manager.prepare(root,'python','runtime',receipt=first)
    assert first['status']=='build_attested' and first['rc']==0 and first['argv']==calls[0]
    second={};cached=manager.prepare(root,'python','runtime',receipt=second)
    assert cached==environment and len(calls)==1
    assert second['status']=='cache_attested' and second['rc'] is None and second['argv'] is None
    install=module._dependency_command_receipt(manager,root,cached,second,'backend_install')
    assert install['execution']=='attested-cache' and install['rc'] is None
    assert install['argv']==['uv','sync','--locked','--no-build','--no-install-project','--no-config','--no-dev']


@pytest.fixture
def fake_delivery(tmp_path,monkeypatch):
    root=tmp_path/'product';_source(root,True)
    conditions={'frontend_rc':0,'wrong_image':False,'tag_drift':False}
    commands=[]
    snapshot=source_snapshot(root).digest
    class Manager:
        _recipe=staticmethod(LinuxEnvironmentManager._recipe)
        def __init__(self,cache_root,**kwargs):self.cache_root=cache_root
        def prepare(self,source,eco,mode,*,receipt=None):
            fingerprint=('a' if eco=='python' else 'b')*64
            image='sha256:'+('c' if eco=='python' else 'd')*64
            inputs={'toolchain_digest':'factory/base@sha256:'+'e'*64}
            manifest=source/('pyproject.toml' if eco=='python' else 'package.json')
            recipe=self._recipe(inputs['toolchain_digest'],eco,mode,fingerprint,manifest)
            attestation={'inputs':inputs,'image':image,'recipe_sha256':hashlib.sha256(recipe.encode()).hexdigest()}
            if receipt is not None:receipt.update(status='cache_attested',image_id=image,attestation=attestation,argv=None,rc=None)
            return LinuxEnvironment(eco,mode,fingerprint,image,attestation)
        def _image(self,name):
            if name.startswith('autospec/clean-env:'):
                return {'Id':'sha256:'+('f' if conditions['tag_drift'] else 'c')*64}
            return {'Id':'sha256:'+'f'*64,'Config':{'Labels':{'autospec.snapshot':'0'*64 if conditions['wrong_image'] else snapshot}}}
    def isolated(argv,stage,image,**kwargs):
        commands.append(('frontend',argv))
        if conditions['frontend_rc']==0:
            (stage/'dist').mkdir();(stage/'dist/index.html').write_text('fresh isolated dist')
        return conditions['frontend_rc'],'typecheck/build result',''
    def docker(argv,stdin,cwd,timeout):
        commands.append(('image',argv))
        recipe=(Path(cwd)/'Dockerfile').read_text()
        assert f'LABEL autospec.snapshot={snapshot}' in recipe
        assert 'RUN npm' not in recipe and '--network=none' in argv
        return 0,'image built',''
    monkeypatch.setattr(environments,'LinuxEnvironmentManager',Manager)
    monkeypatch.setattr(module,'run_isolated',isolated)
    monkeypatch.setattr(module,'_run_tracked',docker)
    return root,conditions,commands,snapshot


def test_delivery_receipt_has_exact_snapshot_locks_dist_and_real_composite_rc(tmp_path,fake_delivery):
    root,_,commands,snapshot=fake_delivery
    ok,_=build_delivery_image(root,'test/image',evidence_root=tmp_path/'evidence',snapshot_hash=snapshot)
    assert ok
    receipt=json.loads((tmp_path/'evidence/delivery-build.json').read_text())
    assert receipt['status']=='PASS' and receipt['snapshot_hash']==snapshot
    assert receipt['image_id']=='sha256:'+'f'*64
    assert receipt['isolated'] and receipt['no_host_dependencies'] and receipt['manifest_only_install']
    assert set(receipt['locks_sha256'])=={'uv.lock','frontend/package-lock.json'}
    assert receipt['frontend_files']=={'frontend/dist/index.html':hashlib.sha256(b'fresh isolated dist').hexdigest()}
    install=[c for c in receipt['commands'] if c['kind'].endswith('_install')]
    assert len(install)==2 and all(c['rc'] is None and c['execution']=='attested-cache' for c in install)
    composite=next(c for c in receipt['commands'] if c['kind']=='typecheck_frontend_build')
    assert composite['components']==['typecheck','frontend_build'] and composite['rc']==0
    assert 'tsc -b --pretty false && exec node' in ' '.join(composite['argv'])
    assert [(c['kind'],c['argv']) for c in receipt['commands'] if c['rc'] is not None]==[
        ('typecheck_frontend_build',commands[0][1]),('image_build',commands[1][1])]
    assert not (root/'frontend/dist').exists()


def test_frontend_failure_is_preserved_without_claiming_image_build(tmp_path,fake_delivery):
    root,conditions,commands,snapshot=fake_delivery;conditions['frontend_rc']=2
    ok,_=build_delivery_image(root,'test/image',evidence_root=tmp_path/'evidence',snapshot_hash=snapshot)
    assert not ok and len(commands)==1
    receipt=json.loads((tmp_path/'evidence/delivery-build.json').read_text())
    assert receipt['status']=='FAIL' and receipt['image_id'] is None and not receipt['frontend_files']
    assert not any(c['kind']=='image_build' for c in receipt['commands'])
    assert next(c['rc'] for c in receipt['commands'] if c['kind']=='typecheck_frontend_build')==2


@pytest.mark.parametrize('drift',['tag_drift','wrong_image'])
def test_changed_image_identity_never_produces_green_receipt(tmp_path,fake_delivery,drift):
    root,conditions,_,snapshot=fake_delivery;conditions[drift]=True
    with pytest.raises(RuntimeError,match='identity|snapshot'):
        build_delivery_image(root,'test/image',evidence_root=tmp_path/'evidence',snapshot_hash=snapshot)
    receipt=json.loads((tmp_path/'evidence/delivery-build.json').read_text())
    assert receipt['status']=='FAIL' and receipt['image_id'] is None


def test_receipt_root_and_snapshot_are_validated_before_builder(tmp_path,monkeypatch):
    root=tmp_path/'product';_source(root)
    monkeypatch.setattr(module,'_build_delivery_image',lambda *a,**k:pytest.fail('invalid identity must not build'))
    with pytest.raises(RuntimeError,match='external'):
        build_delivery_image(root,'test/image',evidence_root=root/'evidence',snapshot_hash=source_snapshot(root).digest)
    with pytest.raises(RuntimeError,match='differs'):
        build_delivery_image(root,'test/image',evidence_root=tmp_path/'evidence',snapshot_hash='0'*64)


@pytest.mark.skipif(os.environ.get('AUTOSPEC_REAL_LINUX_VALIDATION')!='1',reason='Opt-in real locked Linux dependency/frontend/final image receipts')
def test_real_delivery_receipt_then_attested_cache(tmp_path):
    from autospec.orchestrator.sandbox import _docker_call
    root=tmp_path/'product';_source(root,True)
    (root/'uv.lock').unlink();(root/'frontend/package-lock.json').unlink()
    manager=LinuxEnvironmentManager(tmp_path/'lock-cache',timeout=600)
    manager.ensure_lock(root,'python');manager.ensure_lock(root/'frontend','node')
    snapshot=source_snapshot(root).digest
    tags=['autospec/receipt-probe:'+uuid.uuid4().hex for _ in range(2)]
    try:
        for index,tag in enumerate(tags):
            evidence=tmp_path/f'evidence-{index}'
            ok,output=build_delivery_image(root,tag,timeout=600,evidence_root=evidence,snapshot_hash=snapshot)
            assert ok,output
            receipt=json.loads((evidence/'delivery-build.json').read_text())
            assert receipt['status']=='PASS' and receipt['snapshot_hash']==snapshot
            assert receipt['image_id'].startswith('sha256:') and receipt['frontend_files']
            installs=[c for c in receipt['commands'] if c['kind'].endswith('_install')]
            assert all(c['rc'] is None for c in installs)
            if index:assert all(c['execution']=='attested-cache' for c in installs)
            assert next(c['rc'] for c in receipt['commands'] if c['kind']=='typecheck_frontend_build')==0
            assert next(c['rc'] for c in receipt['commands'] if c['kind']=='image_build')==0
            inspected=_docker_call(['docker','image','inspect',receipt['image_id']],capture_output=True,text=True,timeout=10)
            image=json.loads(inspected.stdout)[0]
            assert image['Id']==receipt['image_id'] and image['Config']['Labels']['autospec.snapshot']==snapshot
        assert not (root/'.venv').exists() and not (root/'frontend/node_modules').exists()
        assert source_snapshot(root).digest==snapshot
    finally:
        for tag in tags:_docker_call(['docker','image','rm',tag],capture_output=True,text=True,timeout=10)
