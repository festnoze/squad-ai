"""Factory-only mocks and opt-in Docker probes; NEVER import/run product host.

Offline cases replace all Docker execution and readiness, and bind only owned
loopback sockets. The native case builds/runs the fixture only in NETNONE Linux.
"""
import copy
import json
import os
import queue
import socket
import subprocess
import sys
import threading
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from autospec.orchestrator import isolated_validation as runtime
from autospec.orchestrator import owned_publication as publication
from autospec.orchestrator import sandbox,docker_deploy
from autospec.orchestrator.owned_publication import PublicationError,PublicationRegistry,PublicationSpec
from autospec.validation.final_gate import source_snapshot


_FACTORY_RECOVERY_WORKER = """import json,sys
from autospec.orchestrator.owned_publication import PublicationRegistry
row=PublicationRegistry(sys.argv[1]).recover(sys.argv[2],timeout=30)
print(json.dumps(row),flush=True)
sys.stdin.readline()
"""


class FakeDocker:
    """In-memory daemon; no executable argv is ever launched by these mocks."""
    def __init__(self,spec):
        self.spec=spec;self.volumes={};self.containers={};self.calls=[];self.counter=0
        self.exec_rc=0
    def tracked(self,argv,stdin,cwd,timeout):
        self.calls.append(argv)
        if argv[1:3]==['volume','create']:
            labels=dict(arg.split('=',1) for arg in argv if arg.startswith('autospec.'))
            self.volumes[argv[-1]]={'Name':argv[-1],'Driver':'local','CreatedAt':'2026-10-12T01:00:00Z','Labels':labels,'Options':None}
            return 0,argv[-1]+'\n',''
        if argv[1]=='run' and '--rm' not in argv:
            self.counter+=1;identifier=f'{self.counter:064x}'
            labels=dict(arg.split('=',1) for arg in argv if arg.startswith('autospec.'))
            name=argv[argv.index('--name')+1]
            mount=argv[argv.index('--mount')+1];volume=mount.split('source=',1)[1].split(',',1)[0]
            env=[argv[i+1] for i,arg in enumerate(argv) if arg=='--env']
            migration='-d' not in argv
            self.containers[identifier]={'Id':identifier,'Name':'/'+name,'Created':f'2026-10-12T01:00:0{self.counter}Z',
                'Image':self.spec.image_id,'State':{'Running':not migration},'Config':{'Labels':labels,'User':'65532:65532',
                    'Cmd':argv[argv.index(self.spec.image_id)+1:] if migration else list(self.spec.runtime_command),
                    'Entrypoint':[argv[argv.index('--entrypoint')+1]] if migration else None,'WorkingDir':'/app','Env':env},
                'HostConfig':{'ReadonlyRootfs':True,'CapDrop':['ALL'],'CapAdd':None,'Privileged':False,
                    'SecurityOpt':['no-new-privileges=true'],'NetworkMode':'none','PortBindings':{},'Binds':None,
                    'Devices':[],'DeviceRequests':None,'ExtraHosts':None,'Links':None,'PidMode':'','IpcMode':'private',
                    'PidsLimit':128,'Memory':1073741824,'NanoCpus':2000000000,
                    'Tmpfs':{'/tmp':'rw,nosuid,nodev,size=256m,mode=1777'}},
                'Mounts':[{'Type':'volume','Name':volume,'Destination':runtime.RuntimeSession.DATABASE_DIRECTORY,
                    'RW':True,'Source':'/var/lib/docker/volumes/'+volume+'/_data'}]}
            return (self.exec_rc,'mock migration output','') if migration else (0,identifier+'\n','')
        if argv[1]=='exec':return self.exec_rc,'mock output',''
        return 0,'',''
    def call(self,argv,**kwargs):
        self.calls.append(argv)
        kind,action=argv[1:3];name=argv[3]
        value=None
        if kind=='image' and action=='inspect':
            value={'Id':self.spec.image_id,'Os':'linux','Config':{'WorkingDir':'/app','Cmd':list(self.spec.runtime_command),
                'Entrypoint':None,'Labels':{'autospec.snapshot':self.spec.snapshot_hash}}}
        elif kind=='volume':
            value=self.volumes.get(name)
            if action=='rm':self.volumes.pop(name,None);return SimpleNamespace(returncode=0,stdout='',stderr='')
        elif kind=='container':
            value=next((row for cid,row in self.containers.items() if name in {cid,row['Name'].removeprefix('/')}),None)
            if action=='stop':
                # --time 1 CID differs from normal inspect argv[3].
                value=self.containers.get(argv[-1]);value['State']['Running']=False
                return SimpleNamespace(returncode=0,stdout='',stderr='')
            if action=='rm':self.containers.pop(argv[-1],None);return SimpleNamespace(returncode=0,stdout='',stderr='')
        if value is None:return SimpleNamespace(returncode=1,stdout='',stderr='No such '+kind)
        if argv[-1]=='{{json .State}}':value=value['State']
        out=json.dumps([value]) if '--format' not in argv else json.dumps(value)
        return SimpleNamespace(returncode=0,stdout=out,stderr='')


def setup(tmp_path,monkeypatch,**options):
    source=tmp_path/'product';source.mkdir();(source/'main.py').write_text('# never imported on host\n')
    spec=PublicationSpec('sha256:'+'a'*64,source_snapshot(source).digest,'c'*64,
        ('/opt/venv/bin/python','main.py'),8000,True,runtime.RuntimeSession.DATABASE_DIRECTORY+'/support.sqlite',
        '/api/health',**options)
    fake=FakeDocker(spec)
    monkeypatch.setattr(runtime,'_run_tracked',fake.tracked)
    for module in (runtime,sandbox,publication):monkeypatch.setattr(module,'_docker_call',fake.call)
    monkeypatch.setattr(runtime,'require_sandbox',lambda *a,**k:None)
    monkeypatch.setattr(PublicationRegistry,'_healthy',lambda *a,**k:None)
    registry=PublicationRegistry(tmp_path/'supervisor')
    return source,spec,fake,registry


def cleanup(registry):
    try:registry.stop('project');registry.destroy_data('project')
    except PublicationError:pass


def test_durable_record_handoff_recovers_exact_same_container_port_and_db(tmp_path,monkeypatch):
    source,spec,fake,registry=setup(tmp_path,monkeypatch)
    try:
        first=registry.publish('project',source,spec)
        assert first['status']=='running' and first['migration']=='none'
        assert first['volume_identity']['Name']==first['volume_name']
        registry.release_ingress('project')
        status=PublicationRegistry(registry.root).status('project')
        assert status['running'] and not status['ingress_attached']
        restored=PublicationRegistry(registry.root).recover('project')
        assert first['created_this_call'] and not restored['created_this_call']
        assert {k:v for k,v in restored.items() if k!='created_this_call'}=={k:v for k,v in first.items() if k!='created_this_call'}
        launches=[a for a in fake.calls if a[1]=='run' and '-d' in a]
        assert len(launches)==1 and '-v' not in launches[0] and '--entrypoint' not in launches[0]
        assert launches[0][-1]==spec.image_id and launches[0][launches[0].index('--network')+1]=='none'
        assert registry.status('project')['ingress_attached']
        stopped=registry.stop('project');assert stopped['status']=='stopped' and not fake.containers and fake.volumes
        restored=registry.recover('project')
        assert restored['container_id']!=first['container_id'] and restored['origin']==first['origin']
        assert restored['volume_identity']==first['volume_identity']
    finally:cleanup(registry)
    assert not fake.containers and not fake.volumes


@pytest.mark.parametrize('wrong',['owner','created','network','caps','mount','image','env','volume'])
def test_drift_or_foreign_resource_never_adopted_executed_or_removed(tmp_path,monkeypatch,wrong):
    source,spec,fake,registry=setup(tmp_path,monkeypatch);row=registry.publish('project',source,spec)
    registry.release_ingress('project');original=copy.deepcopy(fake.containers);volumes=copy.deepcopy(fake.volumes)
    container=fake.containers[row['container_id']]
    if wrong=='owner':container['Config']['Labels']['autospec.run_id']='f'*32
    elif wrong=='created':container['Created']='replacement'
    elif wrong=='network':container['HostConfig']['NetworkMode']='host'
    elif wrong=='caps':container['HostConfig']['CapAdd']=['SYS_ADMIN']
    elif wrong=='mount':container['Mounts'].append({'Type':'bind','Source':'host','Destination':'/host','RW':True})
    elif wrong=='image':container['Image']='sha256:'+'b'*64
    elif wrong=='env':container['Config']['Env'].append('APP_ORIGIN=http://foreign')
    elif wrong=='volume':fake.volumes[row['volume_name']]['CreatedAt']='replacement'
    before=len(fake.calls)
    try:
        with pytest.raises(PublicationError,match='DIFFER|DRIFT'):registry.recover('project')
        with pytest.raises(PublicationError):registry.stop('project')
        assert not any(a[1] in {'run','exec'} or a[1:3] in (['container','stop'],['container','rm'],['volume','rm']) for a in fake.calls[before:])
    finally:
        fake.containers=original;fake.volumes=volumes;cleanup(registry)


def test_foreign_port_occupation_refused_without_kill_or_daemon_mutation(tmp_path,monkeypatch):
    source,spec,fake,registry=setup(tmp_path,monkeypatch);row=registry.publish('project',source,spec)
    registry.release_ingress('project')
    try:
        with socket.socket() as foreign:
            foreign.bind(('127.0.0.1',row['host_port']));foreign.listen();before=len(fake.calls)
            with pytest.raises(PublicationError,match='INGRESS_OCCUPIED'):registry.recover('project')
            assert foreign.fileno()>=0
            assert not any(a[1] in {'run','exec','stop','rm'} for a in fake.calls[before:])
    finally:cleanup(registry)


def test_update_refused_preserves_existing_service_and_source_exact(tmp_path,monkeypatch):
    source,spec,fake,registry=setup(tmp_path,monkeypatch)
    try:
        row=registry.publish('project',source,spec)
        changed=PublicationSpec(**{**spec.payload(),'contract_hash':'d'*64})
        with pytest.raises(PublicationError,match='UPDATE_REQUIRES'):registry.publish('project',source,changed)
        assert registry.status('project')['container_id']==row['container_id']
        assert source_snapshot(source).digest==spec.snapshot_hash
    finally:cleanup(registry)


def test_migration_exactly_once_only_on_new_volume_and_unknown_blocks_resume(tmp_path,monkeypatch):
    command=('/opt/venv/bin/python','migration.py')
    source,spec,fake,registry=setup(tmp_path,monkeypatch,migration_command=command)
    try:
        registry.publish('project',source,spec);registry.stop('project');registry.recover('project')
        migrations=[a for a in fake.calls if a[1]=='run' and '--rm' not in a and '-d' not in a]
        assert len(migrations)==1 and migrations[0][migrations[0].index('--entrypoint')+1]==command[0]
        assert migrations[0][-1]==command[1]
        starts=[a for a in fake.calls if a[1]=='run' and '-d' in a]
        assert fake.calls.index(migrations[0])<fake.calls.index(starts[0])
        receipt=registry._read('project')['migration_receipt']
        assert receipt['argv']==list(command) and receipt['return_code']==0
        assert receipt['container_id'] not in fake.containers
        registry.release_ingress('project')
        row=registry._read('project');row['migration']='pending';registry._write(row);before=len(fake.calls)
        with pytest.raises(PublicationError,match='RECOVERY_BLOCKED'):registry.recover('project')
        assert not any(a[1] in {'run','exec'} for a in fake.calls[before:])
        row['migration']='completed';registry._write(row)
    finally:cleanup(registry)


def test_failed_migration_preserves_data_and_requires_explicit_disposition(tmp_path,monkeypatch):
    source,spec,fake,registry=setup(tmp_path,monkeypatch,migration_command=('/opt/venv/bin/python','migration.py'))
    fake.exec_rc=9
    try:
        with pytest.raises(PublicationError,match='MIGRATION_FAILED'):registry.publish('project',source,spec)
        assert registry._read('project')['migration']=='failed' and fake.volumes and not fake.containers
        with pytest.raises(PublicationError,match='RECOVERY_BLOCKED'):registry.recover('project')
    finally:cleanup(registry)


def test_interrupted_prelaunch_migration_cleans_exact_daemon_resource_but_keeps_pending_data(tmp_path,monkeypatch):
    source,spec,fake,registry=setup(tmp_path,monkeypatch,migration_command=('/opt/venv/bin/python','migration.py'))
    original=fake.tracked
    def interrupt(argv,*args):
        result=original(argv,*args)
        if argv[1]=='run' and '--rm' not in argv and '-d' not in argv:
            raise subprocess.TimeoutExpired(argv,1)
        return result
    monkeypatch.setattr(runtime,'_run_tracked',interrupt)
    with pytest.raises(subprocess.TimeoutExpired):registry.publish('project',source,spec)
    row=registry._read('project')
    assert row['migration']=='pending' and row['migration_container_name'] and fake.volumes and not fake.containers
    assert not any(a[1]=='run' and '-d' in a for a in fake.calls)
    with pytest.raises(PublicationError,match='RECOVERY_BLOCKED'):registry.recover('project')
    registry.stop('project');registry.destroy_data('project')
    assert not fake.volumes


def test_cancelled_creation_retains_external_intent_no_product_execution(tmp_path,monkeypatch):
    source,spec,fake,registry=setup(tmp_path,monkeypatch);cancel=threading.Event();cancel.set()
    with pytest.raises(PublicationError,match='CANCELLED'):registry.publish('project',source,spec,cancel_event=cancel)
    assert registry._read('project')['status']=='failed'
    assert not fake.volumes and not fake.containers
    assert not any(a[1] in {'run','exec'} for a in fake.calls)


def test_registry_inside_source_and_invalid_journal_fail_closed(tmp_path,monkeypatch):
    source,spec,fake,registry=setup(tmp_path,monkeypatch)
    with pytest.raises(PublicationError,match='EXTERNAL'):PublicationRegistry(source/'metadata').publish('project',source,spec)
    path,_=registry._paths('project');path.write_text('{"version":1}')
    with pytest.raises(PublicationError,match='JOURNAL_INVALID'):registry.recover('project')


def test_facade_contract_publishes_real_ids_and_undeploy_preserves_db(tmp_path,monkeypatch):
    source,spec,fake,registry=setup(tmp_path,monkeypatch)
    state=SimpleNamespace(id='project',acceptance_contract_hash=spec.contract_hash)
    try:
        result=docker_deploy.deploy_and_verify(state,source,network='UNUSED',host_port=0,
            build_timeout=30,deploy_timeout=30,kind='backend',qualified_image_id=spec.image_id,
            expected_snapshot=spec.snapshot_hash,expected_runtime_command=spec.runtime_command,
            publication_root=registry.root,publication_contract_hash=spec.contract_hash,
            publication_internal_port=spec.internal_port,publication_local_cookie_mode=spec.local_cookie_mode,
            publication_database_path=spec.database_path,publication_health_path=spec.health_path)
        assert result.ok and not result.packaged and result.container in fake.containers and result.host_port>0
        assert result.created_publication_container==result.container
        assert docker_deploy.inspect_deployment('project',publication_root=registry.root).ok
        assert docker_deploy.undeploy('project',publication_root=registry.root).ok
        assert fake.volumes and not fake.containers
        stopped=docker_deploy.inspect_deployment('project',publication_root=registry.root)
        assert not stopped.ok and stopped.skipped
        assert docker_deploy.recover_publication('project',registry.root).ok
    finally:cleanup(registry)


def test_publication_cached_reuse_has_no_creation_receipt_even_when_state_never_flushed(tmp_path,monkeypatch):
    source,spec,fake,registry=setup(tmp_path,monkeypatch);first=registry.publish('project',source,spec)
    state=SimpleNamespace(id='project',acceptance_contract_hash=spec.contract_hash)
    try:
        result=docker_deploy.deploy_and_verify(state,source,network='none',host_port=0,build_timeout=30,deploy_timeout=30,
            kind='backend',qualified_image_id=spec.image_id,expected_snapshot=spec.snapshot_hash,
            expected_runtime_command=spec.runtime_command,publication_root=registry.root,
            publication_contract_hash=spec.contract_hash,publication_internal_port=spec.internal_port,
            publication_local_cookie_mode=spec.local_cookie_mode,publication_database_path=spec.database_path,
            publication_health_path=spec.health_path)
        assert result.ok and result.container==first['container_id'] and not result.created_publication_container
    finally:cleanup(registry)


def test_publication_late_cancel_receipt_never_stops_replacement_cid(tmp_path,monkeypatch):
    source,spec,fake,registry=setup(tmp_path,monkeypatch);first=registry.publish('project',source,spec)
    registry.stop('project');second=registry.publish('project',source,spec)
    assert second['created_this_call'] and second['container_id']!=first['container_id']
    try:
        before=len(fake.calls)
        refused=docker_deploy.undeploy('project',publication_root=registry.root,expected_publication_container=first['container_id'])
        assert not refused.ok and 'RECEIPT_IDENTITY_DIFFER' in refused.detail
        assert second['container_id'] in fake.containers
        assert not any(a[1:3] in (['container','stop'],['container','rm']) for a in fake.calls[before:])
        assert docker_deploy.undeploy('project',publication_root=registry.root,expected_publication_container=second['container_id']).ok
    finally:cleanup(registry)


@pytest.mark.parametrize('cold',[False,True])
def test_publication_source_changes_during_reuse_never_admit_or_stop_old_service(tmp_path,monkeypatch,cold):
    source,spec,fake,registry=setup(tmp_path,monkeypatch);first=registry.publish('project',source,spec)
    if cold:registry.release_ingress('project')
    def edit(*args,**kwargs):(source/'main.py').write_text('# concurrent factory-side source edit\n')
    monkeypatch.setattr(PublicationRegistry,'_healthy',edit)
    before=len(fake.calls)
    try:
        with pytest.raises(PublicationError,match='SOURCE_CHANGED_DURING_REUSE'):registry.publish('project',source,spec)
        assert first['container_id'] in fake.containers and fake.volumes
        assert not any(a[1:3] in (['container','stop'],['container','rm']) for a in fake.calls[before:])
    finally:cleanup(registry)


def test_cold_cancel_only_releases_new_ingress_not_existing_daemon_app_or_db(tmp_path,monkeypatch):
    source,spec,fake,registry=setup(tmp_path,monkeypatch);first=registry.publish('project',source,spec)
    registry.release_ingress('project')
    def cancel(*args,**kwargs):raise PublicationError('PUBLICATION_CANCELLED')
    monkeypatch.setattr(PublicationRegistry,'_healthy',cancel);before=len(fake.calls)
    try:
        with pytest.raises(PublicationError,match='CANCELLED'):registry.publish('project',source,spec)
        assert first['container_id'] in fake.containers and fake.volumes
        assert not any(a[1:3] in (['container','stop'],['container','rm'],['volume','rm']) for a in fake.calls[before:])
        assert not registry.status('project')['ingress_attached']
    finally:cleanup(registry)


def test_recovery_facade_forwards_cancel_event_without_creation_receipt_or_old_resource_cleanup(tmp_path,monkeypatch):
    source,spec,fake,registry=setup(tmp_path,monkeypatch);first=registry.publish('project',source,spec)
    registry.release_ingress('project');event=threading.Event();event.set()
    def cancel(self,session,spec,timeout,cancel_event=None):
        assert cancel_event is event
        raise PublicationError('PUBLICATION_CANCELLED')
    monkeypatch.setattr(PublicationRegistry,'_healthy',cancel);before=len(fake.calls)
    try:
        result=docker_deploy.recover_publication('project',registry.root,cancel_event=event)
        assert not result.ok and 'CANCELLED' in result.detail and not result.created_publication_container
        assert first['container_id'] in fake.containers and fake.volumes
        assert not any(a[1:3] in (['container','stop'],['container','rm'],['volume','rm']) for a in fake.calls[before:])
    finally:cleanup(registry)


def test_publication_intentional_stop_destroy_skip_but_failed_start_is_not_skip(tmp_path,monkeypatch):
    source,spec,fake,registry=setup(tmp_path,monkeypatch)
    registry.publish('project',source,spec);registry.stop('project')
    assert docker_deploy.inspect_deployment('project',publication_root=registry.root).skipped
    registry.destroy_data('project')
    destroyed=docker_deploy.inspect_deployment('project',publication_root=registry.root)
    assert destroyed.skipped and not destroyed.ok
    row=registry._read('project');row['status']='failed';row['volume_identity']=None;registry._write(row)
    failed=docker_deploy.inspect_deployment('project',publication_root=registry.root)
    assert not failed.ok and not failed.skipped


def test_completed_stop_status_needs_no_daemon_query_or_image_recreation(tmp_path,monkeypatch):
    source,spec,fake,registry=setup(tmp_path,monkeypatch)
    registry.publish('project',source,spec);registry.stop('project')
    def unavailable(*args,**kwargs):raise AssertionError('completed stop must not query unavailable Docker')
    with monkeypatch.context() as scoped:
        scoped.setattr(publication,'_docker_call',unavailable)
        status=docker_deploy.inspect_deployment('project',publication_root=registry.root)
        assert status.skipped and not status.ok
    cleanup(registry)


def test_stop_terminal_flush_failure_keeps_durable_intent_and_never_revives(tmp_path,monkeypatch):
    source,spec,fake,registry=setup(tmp_path,monkeypatch);first=registry.publish('project',source,spec)
    write=registry._write
    def fail_final(row):
        if row['status']=='stopped':raise OSError('trusted terminal stop flush failed')
        write(row)
    monkeypatch.setattr(registry,'_write',fail_final)
    try:
        with pytest.raises(OSError,match='terminal stop flush failed'):registry.stop('project')
        assert first['container_id'] not in fake.containers and fake.volumes
        pending=registry._read('project')
        assert pending['status']=='stopping' and pending['container_id']==first['container_id']
        before=len(fake.calls)
        refused=docker_deploy.recover_publication('project',registry.root)
        assert not refused.ok and 'RECOVERY_BLOCKED' in refused.detail
        assert not any(a[1]=='run' for a in fake.calls[before:])
        status=docker_deploy.inspect_deployment('project',publication_root=registry.root)
        assert not status.ok and not status.skipped
        monkeypatch.setattr(registry,'_write',write)
        # An explicit retry can complete its own receipt even though cleanup
        # succeeded before the first terminal journal flush failed.
        done=registry.stop('project',expected_container_id=first['container_id'])
        assert done['status']=='stopped' and fake.volumes
        assert registry.stop('project')['status']=='stopped'
    finally:
        monkeypatch.setattr(registry,'_write',write);cleanup(registry)


def test_stop_intent_flush_failure_does_not_touch_daemon_or_owned_ingress(tmp_path,monkeypatch):
    source,spec,fake,registry=setup(tmp_path,monkeypatch);first=registry.publish('project',source,spec)
    write=registry._write
    def fail_intent(row):
        if row['status']=='stopping':raise OSError('trusted stop intent flush failed')
        write(row)
    monkeypatch.setattr(registry,'_write',fail_intent);before=len(fake.calls)
    try:
        with pytest.raises(OSError,match='intent flush failed'):registry.stop('project')
        assert registry._read('project')['status']=='running'
        assert first['container_id'] in fake.containers and fake.volumes
        assert registry.status('project')['ingress_attached']
        assert not any(a[1:3] in (['container','stop'],['container','rm'],['volume','rm']) for a in fake.calls[before:])
    finally:
        monkeypatch.setattr(registry,'_write',write);cleanup(registry)


def test_stop_cleanup_failure_blocks_recovery_and_preserves_explicit_retry(tmp_path,monkeypatch):
    source,spec,fake,registry=setup(tmp_path,monkeypatch);first=registry.publish('project',source,spec)
    cleanup_container=runtime._cleanup_container
    def fail_cleanup(*args,**kwargs):raise RuntimeError('trusted owned cleanup failed')
    monkeypatch.setattr(runtime,'_cleanup_container',fail_cleanup)
    try:
        with pytest.raises(RuntimeError,match='owned cleanup failed'):registry.stop('project')
        assert registry._read('project')['status']=='stopping'
        assert first['container_id'] in fake.containers and fake.volumes
        before=len(fake.calls)
        with pytest.raises(PublicationError,match='RECOVERY_BLOCKED'):registry.recover('project')
        assert not any(a[1]=='run' for a in fake.calls[before:])
        assert not docker_deploy.inspect_deployment('project',publication_root=registry.root).ok
        monkeypatch.setattr(runtime,'_cleanup_container',cleanup_container)
        assert registry.stop('project',expected_container_id=first['container_id'])['status']=='stopped'
        assert not fake.containers and fake.volumes
    finally:
        monkeypatch.setattr(runtime,'_cleanup_container',cleanup_container);cleanup(registry)


@pytest.mark.skipif(os.environ.get('AUTOSPEC_REAL_LINUX_VALIDATION')!='1',reason='Opt-in NETNONE image/HTTP/SQLite publication, fixture never executed host')
def test_real_baked_netnone_http_persistence_recovery_and_canaries(tmp_path):
    source=tmp_path/'source';source.mkdir()
    (source/'pyproject.toml').write_text('[project]\nname="owned-publication-proof"\nversion="1.0.0"\nrequires-python=">=3.12"\ndependencies=[]\n')
    # Product fixture is copied into the image; host only writes bytes.
    (source/'main.py').write_text('''import os,sqlite3,json
from http.server import HTTPServer,BaseHTTPRequestHandler
path=os.environ['DATABASE_URL'].removeprefix('sqlite:///')
with sqlite3.connect(path) as db:
 db.execute('create table if not exists counter(value integer)')
 if not db.execute('select count(*) from counter').fetchone()[0]:db.execute('insert into counter values(0)')
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  if self.path=='/forbidden':self.send_response(403);self.end_headers();return
  if self.path=='/missing':self.send_response(404);self.end_headers();return
  with sqlite3.connect(path) as db:value=db.execute('select value from counter').fetchone()[0]
  data=json.dumps({'value':value,'origin':os.environ['APP_ORIGIN'],'uid':os.getuid(),'cookie':os.environ['SESSION_COOKIE_SECURE']}).encode()
  self.send_response(200);self.end_headers();self.wfile.write(data)
 def do_POST(self):
  if self.headers.get('Origin')!=os.environ['APP_ORIGIN']:self.send_response(403);self.end_headers();return
  with sqlite3.connect(path) as db:db.execute('update counter set value=value+1')
  self.send_response(204);self.end_headers()
HTTPServer(('0.0.0.0',int(os.environ['PORT'])),Handler).serve_forever()
''')
    from autospec.orchestrator.isolated_validation import IsolatedValidator,build_delivery_image
    validator=IsolatedValidator(tmp_path/'cache',timeout=300);validator.manager.ensure_lock(source,'python')
    snapshot=source_snapshot(source).digest;tag='autospec/publication-proof:'+uuid4().hex
    command=('/opt/venv/bin/python','main.py');registry=PublicationRegistry(tmp_path/'supervisor')
    identifiers=[];volume=None
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def get(origin):
        with opener.open(origin+'/api/health',timeout=10) as response:return json.load(response)
    try:
        ok,output=build_delivery_image(source,tag,runtime_command=command,evidence_root=tmp_path/'build',snapshot_hash=snapshot)
        assert ok,output
        image=json.loads((tmp_path/'build/delivery-build.json').read_bytes())['image_id']
        spec=PublicationSpec(image,snapshot,'c'*64,command,8000,True,
            '/var/lib/autospec-validation/support.sqlite','/api/health')
        with socket.socket() as unrelated:
            unrelated.bind(('127.0.0.1',0));unrelated.listen();sentinel_port=unrelated.getsockname()[1]
            first=registry.publish('project',source,spec,timeout=30);identifiers.append(first['container_id']);volume=first['volume_name']
            assert get(first['origin'])=={'value':0,'origin':first['origin'],'uid':65532,'cookie':'false'}
            request=urllib.request.Request(first['origin'],method='POST',headers={'Origin':first['origin']})
            with opener.open(request,timeout=10) as response:assert response.status==204
            assert get(first['origin'])['value']==1
            session=publication._LIVE[registry._key('project')]
            probe='''import os,socket,json,sys
port=int(sys.argv[1]);blocked=[]
for address,target in [('host.docker.internal',port),('1.1.1.1',443)]:
 try:
  with socket.create_connection((address,target),timeout=.3):pass
 except OSError:blocked.append(address)
 else:raise AssertionError('NETNONE egress escaped')
assert not os.path.exists('/var/run/docker.sock')
assert not any(key in os.environ for key in ('ANTHROPIC_API_KEY','OPENAI_API_KEY','AWS_SECRET_ACCESS_KEY'))
try:open('/app/escape','w')
except OSError:pass
else:raise AssertionError('readonly source escaped')
print(json.dumps(blocked))
'''
            rc,out,err=session.exec(['/usr/local/bin/python','-I','-c',probe,str(sentinel_port)],timeout=10)
            assert rc==0 and json.loads(out)==['host.docker.internal','1.1.1.1'],err
            assert unrelated.fileno()>=0
            registry.release_ingress('project')
            fresh=PublicationRegistry(registry.root);assert not fresh.status('project')['ingress_attached']
            recovered=fresh.recover('project',timeout=30)
            assert recovered['container_id']==first['container_id'] and recovered['volume_identity']==first['volume_identity']
            assert get(recovered['origin'])['value']==1
            # Real factory PROCESS death, not a mocked PID/name sweep. The
            # worker executes trusted supervisor code only; product PID1 stays
            # in the Docker daemon and retains its exact CID/SQLite volume.
            from autospec.agents.runner import spawn_owned_process,close_owned_process
            fresh.release_ingress('project')
            worker=spawn_owned_process([sys.executable,'-c',_FACTORY_RECOVERY_WORKER,str(registry.root),'project'],
                stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            output=queue.Queue()
            reader=threading.Thread(target=lambda:output.put(worker.stdout.readline()),daemon=True);reader.start()
            try:
                recovered_child=json.loads(output.get(timeout=40))
                assert recovered_child['container_id']==first['container_id']
                assert get(recovered_child['origin'])['value']==1
            finally:
                close_owned_process(worker)
                for stream in (worker.stdin,worker.stdout,worker.stderr):
                    if stream is not None and not stream.closed:stream.close()
                reader.join(timeout=1)
            assert worker.poll() is not None and not fresh.status('project')['ingress_attached']
            recovered_after_death=PublicationRegistry(registry.root).recover('project',timeout=30)
            assert recovered_after_death['container_id']==first['container_id']
            assert get(recovered_after_death['origin'])['value']==1
            # Negative HTTP readiness is observed, never treated as success.
            active=publication._LIVE[registry._key('project')]
            for path in ('/forbidden','/missing'):
                bad=PublicationSpec(**{**spec.payload(),'health_path':path})
                with pytest.raises(PublicationError,match='READINESS'):registry._healthy(active,bad,.4)
            fresh.stop('project');assert not fresh.status('project')['running']
            again=fresh.recover('project',timeout=30);identifiers.append(again['container_id'])
            assert again['origin']==first['origin'] and again['container_id']!=first['container_id']
            assert get(again['origin'])['value']==1
            assert source_snapshot(source).digest==snapshot
            assert unrelated.getsockname()[1]==sentinel_port
            proof_root=os.environ.get('AUTOSPEC_PUBLICATION_PROOF_ROOT')
            if proof_root:
                from autospec.orchestrator.dependencies import atomic_json
                atomic_json(publication.FileBroker(publication.ExecutionContext('publication-proof',Path(proof_root))).path('publication-native.json'),
                    {'image_id':image,'source_snapshot':snapshot,'initial':first,'after_handoff':recovered,
                     'after_factory_death':recovered_after_death,'after_stop_restart':again,
                     'canary_egress_stdout':out,'canary_egress_rc':rc,'host_sentinel_port':sentinel_port,
                     'source_unchanged':source_snapshot(source).digest==snapshot,
                     'actual_configuration':publication._LIVE[registry._key('project')].inspect_configuration()})
        registry.stop('project');registry.destroy_data('project')
        for kind,identifier in [('container',cid) for cid in identifiers]+[('volume',volume)]:
            assert publication._inspect('docker',kind,identifier) is None
    finally:
        cleanup(registry)
        sandbox._docker_call(['docker','image','rm',tag],capture_output=True,text=True,timeout=10,check=False)


@pytest.mark.skipif(os.environ.get('AUTOSPEC_REAL_LINUX_VALIDATION')!='1',reason='Opt-in migration-before-plain-image proof, product only inside Docker')
def test_real_schema_migration_precedes_app_that_refuses_empty_database(tmp_path):
    source=tmp_path/'source';source.mkdir()
    (source/'pyproject.toml').write_text('[project]\nname="prelaunch-migration-proof"\nversion="1.0.0"\nrequires-python=">=3.12"\ndependencies=[]\n')
    # Startup reads an existing schema in READ ONLY mode and exits if absent.
    # It cannot create/seed/repair it itself. Never imported/run on the host.
    (source/'main.py').write_text('''import os,sqlite3,json
from http.server import HTTPServer,BaseHTTPRequestHandler
path=os.environ['DATABASE_URL'].removeprefix('sqlite:///')
with sqlite3.connect('file:'+path+'?mode=ro',uri=True) as db:db.execute('select count(*) from items').fetchone()
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  with sqlite3.connect('file:'+path+'?mode=ro',uri=True) as db:count=db.execute('select count(*) from items').fetchone()[0]
  self.send_response(200);self.end_headers();self.wfile.write(json.dumps({'count':count}).encode())
HTTPServer(('0.0.0.0',int(os.environ['PORT'])),Handler).serve_forever()
''')
    (source/'migrate.py').write_text("import os,sqlite3\nwith sqlite3.connect(os.environ['DATABASE_URL'].removeprefix('sqlite:///')) as db:db.execute('create table items(id integer primary key)')\n")
    from autospec.orchestrator.isolated_validation import IsolatedValidator,build_delivery_image
    validator=IsolatedValidator(tmp_path/'cache',timeout=300);validator.manager.ensure_lock(source,'python')
    snapshot=source_snapshot(source).digest;tag='autospec/prelaunch-proof:'+uuid4().hex
    registry=PublicationRegistry(tmp_path/'supervisor');command=('/opt/venv/bin/python','main.py')
    try:
        ok,output=build_delivery_image(source,tag,runtime_command=command,evidence_root=tmp_path/'build',snapshot_hash=snapshot)
        assert ok,output
        image=json.loads((tmp_path/'build/delivery-build.json').read_bytes())['image_id']
        spec=PublicationSpec(image,snapshot,'c'*64,command,8000,False,
            '/var/lib/autospec-validation/support.sqlite','/api/health',('/opt/venv/bin/python','migrate.py'))
        row=registry.publish('project',source,spec,timeout=30)
        assert row['migration']=='completed' and row['migration_receipt']['return_code']==0
        assert row['migration_receipt']['argv']==['/opt/venv/bin/python','migrate.py']
        assert row['migration_receipt']['container_id']!=row['container_id']
        assert publication._inspect('docker','container',row['migration_receipt']['container_id']) is None
        info=publication._LIVE[registry._key('project')].inspect_configuration()
        assert info['runtime_command']==list(command) and info['runtime_entrypoint'] in (None,[])
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(row['origin']+'/api/health',timeout=10) as response:assert json.load(response)=={'count':0}
        registry.stop('project');again=registry.recover('project',timeout=30)
        # Re-running CREATE TABLE would fail; recovery must reuse the recorded
        # migration and DB, launch plain CMD only, and still be healthy.
        assert again['migration_receipt']==row['migration_receipt']
        with opener.open(again['origin']+'/api/health',timeout=10) as response:assert json.load(response)=={'count':0}
        if os.environ.get('AUTOSPEC_PUBLICATION_PROOF_ROOT'):
            from autospec.orchestrator.dependencies import atomic_json
            atomic_json(Path(os.environ['AUTOSPEC_PUBLICATION_PROOF_ROOT'])/'publication-prelaunch-native.json',
                {'initial':row,'after_restart':again,'configuration':info,'schema_row_count':0,
                 'source_unchanged':source_snapshot(source).digest==snapshot})
    finally:
        cleanup(registry)
        sandbox._docker_call(['docker','image','rm',tag],capture_output=True,text=True,timeout=10,check=False)
