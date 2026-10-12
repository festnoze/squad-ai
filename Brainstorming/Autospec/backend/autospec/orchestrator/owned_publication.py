"""Durable qualified-image publication, with NETNONE and owned loopback ingress.

The registry lives outside the producer tree. It is an ownership journal, NOT
an acceptance authority: callers supply independently reviewed image facts.
No PID scans, bridge networks, Docker port publishing, source overlays, fixture
seed or implicit migration are permitted. A different image cannot replace an
existing service without a separately designed migration/rollback policy.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import threading
import time
import uuid
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from ..agents.file_broker import ExecutionContext, FileBroker
from .dependencies import atomic_json, file_lock
from .isolated_validation import RuntimeSession, _runtime_argv
from .sandbox import _cleanup_container, _docker_call


class PublicationError(RuntimeError):
    pass


_SHA = re.compile(r"[a-f0-9]{64}")
_IMAGE = re.compile(r"sha256:[a-f0-9]{64}")
_UUID = re.compile(r"[a-f0-9]{32}")
_LIVE: dict[tuple[str, str], RuntimeSession] = {}
_LIVE_LOCK = threading.RLock()


@dataclass(frozen=True)
class PublicationSpec:
    image_id: str
    snapshot_hash: str
    contract_hash: str
    runtime_command: tuple[str, ...]
    internal_port: int
    local_cookie_mode: bool
    database_path: str
    health_path: str
    migration_command: tuple[str, ...] | None = None

    def __post_init__(self):
        if (not isinstance(self.image_id,str) or not _IMAGE.fullmatch(self.image_id) or
            not all(isinstance(s,str) and _SHA.fullmatch(s) for s in (self.snapshot_hash,self.contract_hash))):
            raise PublicationError('PUBLICATION_FACTS_REQUIRED: immutable image/source/contract identities')
        object.__setattr__(self,'runtime_command',tuple(_runtime_argv(self.runtime_command)))
        if self.runtime_command[0] not in {'/opt/venv/bin/python','node'}:
            raise PublicationError('PUBLICATION_ECOSYSTEM_UNSUPPORTED: reviewed Python/Node argv required')
        if (type(self.internal_port) is not int or not 1<=self.internal_port<=65535 or
            type(self.local_cookie_mode) is not bool or
            self.database_path != '/var/lib/autospec-validation/support.sqlite'):
            raise PublicationError('PUBLICATION_BINDING_UNSUPPORTED: exact factory DB/port/cookie facts required')
        if (not isinstance(self.health_path,str) or not re.fullmatch(r'/[A-Za-z0-9_/-]*',self.health_path) or
            '//' in self.health_path or len(self.health_path)>1024):
            raise PublicationError('PUBLICATION_HEALTH_BINDING_REQUIRED: literal same-origin reviewed path')
        if self.migration_command is not None:
            object.__setattr__(self,'migration_command',tuple(_runtime_argv(self.migration_command)))
            if self.migration_command[0]!=self.runtime_command[0]:
                raise PublicationError('PUBLICATION_MIGRATION_EXECUTOR_UNSUPPORTED: exact reviewed ecosystem interpreter required')

    @property
    def ecosystem(self):
        return 'node' if self.runtime_command[0]=='node' else 'python'

    def payload(self):
        return json.loads(json.dumps(asdict(self)))


def _digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def _inspect(docker, kind, name):
    result=_docker_call([docker,kind,'inspect',name,'--format','{{json .}}'],
                        capture_output=True,text=True,timeout=5,check=False)
    if result.returncode:
        if 'no such' in result.stderr.lower() and any(x in result.stderr.lower() for x in ('object',kind)):
            return None
        raise PublicationError('PUBLICATION_INSPECTION_UNAVAILABLE: '+kind)
    try:
        value=json.loads(result.stdout)
        if not isinstance(value,dict):raise ValueError('object expected')
        return value
    except (TypeError,ValueError) as exc:
        raise PublicationError('PUBLICATION_INSPECTION_INVALID: '+kind) from exc


def _image(docker,spec):
    image=_inspect(docker,'image',spec.image_id)
    if (not image or image.get('Id')!=spec.image_id or image.get('Os')!='linux' or
        image.get('Config',{}).get('WorkingDir')!='/app' or
        image['Config'].get('Cmd')!=list(spec.runtime_command) or image['Config'].get('Entrypoint') not in (None,[]) or
        image['Config'].get('Labels',{}).get('autospec.snapshot')!=spec.snapshot_hash):
        raise PublicationError('PUBLICATION_IMAGE_FACTS_DIFFER: source/CMD/entrypoint/OS')


def _volume(docker,record):
    value=_inspect(docker,'volume',record['volume_name'])
    if value is None:return None
    identity={k:value.get(k) for k in ('Name','Driver','CreatedAt','Labels')}
    if (identity['Name']!=record['volume_name'] or identity['Driver']!='local' or
        not isinstance(identity['CreatedAt'],str) or not identity['CreatedAt'] or
        identity['Labels']!={'autospec.run_id':record['owner'],'autospec.kind':'validation-state'} or
        value.get('Options') not in (None,{}) or
        record['volume_identity'] is not None and identity!=record['volume_identity']):
        raise PublicationError('PUBLICATION_VOLUME_IDENTITY_DIFFER: refusing access/removal')
    return identity


def _container(docker,record,spec,*,migration=False):
    value=_inspect(docker,'container',record['container_id'] or record['container_name'])
    if value is None:return None
    config,host=value.get('Config',{}),value.get('HostConfig',{})
    mounts=value.get('Mounts',[])
    env=dict(item.split('=',1) for item in config.get('Env',[]) if '=' in item)
    expected_env={'APP_ORIGIN':record['origin'],'PORT':str(spec.internal_port),'DATABASE_URL':RuntimeSession.DATABASE_URL}
    if spec.local_cookie_mode:expected_env['SESSION_COOKIE_SECURE']='false'
    if (not _SHA.fullmatch(str(value.get('Id',''))) or value.get('Name')!='/'+record['container_name'] or
        record['container_id'] is not None and value['Id']!=record['container_id'] or
        not isinstance(value.get('Created'),str) or not value['Created'] or
        record['container_created'] is not None and value['Created']!=record['container_created'] or
        value.get('Image')!=spec.image_id or config.get('Cmd')!=list(spec.runtime_command[1:] if migration else spec.runtime_command) or
        (config.get('Entrypoint')!=[spec.runtime_command[0]] if migration else config.get('Entrypoint') not in (None,[])) or
        config.get('User')!='65532:65532' or config.get('WorkingDir')!='/app' or
        config.get('Labels',{}).get('autospec.run_id')!=record['owner'] or config.get('Labels',{}).get('autospec.kind')!='sandbox' or
        any(env.get(k)!=v for k,v in expected_env.items()) or
        host.get('NetworkMode')!='none' or host.get('ReadonlyRootfs') is not True or host.get('Privileged') is not False or
        host.get('CapDrop')!=['ALL'] or host.get('CapAdd') not in (None,[]) or
        host.get('SecurityOpt')!=['no-new-privileges=true'] or host.get('IpcMode')!='private' or
        host.get('PortBindings') not in (None,{}) or host.get('Binds') not in (None,[]) or
        host.get('Devices') not in (None,[]) or host.get('DeviceRequests') not in (None,[]) or
        host.get('ExtraHosts') not in (None,[]) or host.get('Links') not in (None,[]) or host.get('PidMode') not in ('',None) or
        host.get('PidsLimit')!=128 or host.get('Memory')!=1073741824 or host.get('NanoCpus')!=2000000000 or
        host.get('Tmpfs')!={'/tmp':'rw,nosuid,nodev,size=256m,mode=1777'} or
        len(mounts)!=1 or mounts[0].get('Type')!='volume' or mounts[0].get('Name')!=record['volume_name'] or
        mounts[0].get('Destination')!=RuntimeSession.DATABASE_DIRECTORY or mounts[0].get('RW') is not True):
        raise PublicationError('PUBLICATION_CONTAINER_IDENTITY_DIFFER: hardened configuration required')
    fingerprint=_digest({k:value[k] for k in ('Id','Name','Created','Image','Config','HostConfig','Mounts')})
    if record['container_fingerprint'] is not None and fingerprint!=record['container_fingerprint']:
        raise PublicationError('PUBLICATION_CONTAINER_CONFIGURATION_DRIFT')
    return value,fingerprint


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


class PublicationRegistry:
    """External durable resource ownership plus in-process retained ingress.

    recover() is called when the factory starts. A foreign listener occupying
    the recorded port is refused, never killed. Factory death retains Docker
    data/container resources; ingress becomes unavailable until explicit
    recovery (not falsely "running" from a stale record).
    """
    def __init__(self,root:Path,*,docker='docker'):
        self.root=Path(root).absolute()
        if self.root.resolve()!=self.root:
            raise PublicationError('PUBLICATION_REGISTRY_ALIAS_REFUSED')
        self.root.mkdir(parents=True,exist_ok=True)
        self.broker=FileBroker(ExecutionContext('publication-registry',self.root))
        self.docker=docker
        self.stage=self.broker.path('empty-runtime-stage')
        self.stage.mkdir(exist_ok=True)
        if any(self.stage.iterdir()):
            raise PublicationError('PUBLICATION_FACTORY_STAGE_NOT_EMPTY')

    def _paths(self,project_id):
        if not isinstance(project_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',project_id):
            raise PublicationError('PUBLICATION_PROJECT_ID_INVALID')
        return self.broker.path(project_id+'.json'),self.broker.path(project_id+'.lock')

    def _key(self,project_id):return str(self.root),project_id

    def _read(self,project_id):
        path,_=self._paths(project_id)
        if not path.exists():return None
        if not path.is_file() or path.stat().st_size>131072:
            raise PublicationError('PUBLICATION_JOURNAL_INVALID')
        try:
            row=json.loads(path.read_text(encoding='utf-8'))
            if isinstance(row,dict):
                row.setdefault('migration_container_name',None)
                row.setdefault('migration_receipt',None)
            fields={'version','project_id','spec','owner','container_name','container_id','container_created',
                    'container_fingerprint','volume_name','volume_identity','host_port','origin','status','migration','reason',
                    'migration_container_name','migration_receipt'}
            if not isinstance(row,dict) or set(row)!=fields or row['version']!=1 or row['project_id']!=project_id:
                raise ValueError('schema')
            spec=PublicationSpec(**row['spec'])
            if (not isinstance(row['owner'],str) or not _UUID.fullmatch(row['owner']) or
                not re.fullmatch(r'autospec-sandbox-[a-f0-9]{32}',row['container_name']) or
                not re.fullmatch(r'autospec-validation-[a-f0-9]{32}',row['volume_name']) or
                type(row['host_port']) is not int or not 1<=row['host_port']<=65535 or
                row['origin']!=f"http://127.0.0.1:{row['host_port']}" or
                row['status'] not in {'creating','running','stopping','stopped','failed','uncertain','destroyed'} or
                row['migration'] not in {'none','not_started','pending','completed','failed'} or
                not isinstance(row['reason'],str) or len(row['reason'])>4096 or
                row['container_id'] is not None and not _SHA.fullmatch(row['container_id']) or
                row['container_fingerprint'] is not None and not _SHA.fullmatch(row['container_fingerprint']) or
                row['container_created'] is not None and not isinstance(row['container_created'],str) or
                row['volume_identity'] is not None and not isinstance(row['volume_identity'],dict) or
                row['migration_container_name'] is not None and not re.fullmatch(r'autospec-sandbox-[a-f0-9]{32}',row['migration_container_name']) or
                row['migration_receipt'] is not None and not isinstance(row['migration_receipt'],dict)):
                raise ValueError('identities')
            if spec.payload()!=row['spec']:raise ValueError('canonical spec')
            return row
        except (TypeError,ValueError,KeyError) as exc:
            raise PublicationError('PUBLICATION_JOURNAL_INVALID: no recovery or deletion authority') from exc

    def _write(self,record):
        path,_=self._paths(record['project_id'])
        atomic_json(path,record)
        # Re-read through containment before another daemon mutation/admission.
        self._read(record['project_id'])

    def _capture(self,row,spec):
        volume=_volume(self.docker,row)
        if volume is None:raise PublicationError('PUBLICATION_OWNED_VOLUME_MISSING')
        row['volume_identity']=volume
        actual=_container(self.docker,row,spec)
        if actual:
            data,fingerprint=actual
            row.update(container_id=data['Id'],container_created=data['Created'],container_fingerprint=fingerprint)
        return actual

    def _healthy(self,session,spec,timeout,cancel_event=None):
        if not math.isfinite(timeout) or timeout<=0:raise PublicationError('PUBLICATION_DEADLINE_INVALID')
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),_NoRedirect())
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            if cancel_event is not None and cancel_event.is_set():raise PublicationError('PUBLICATION_CANCELLED')
            if not session.is_running():raise PublicationError('PUBLICATION_RUNTIME_EXITED')
            try:
                with opener.open(session.origin+spec.health_path,timeout=min(2,max(.05,deadline-time.monotonic()))) as response:
                    if 200<=response.status<300:
                        response.read(65536)
                        return
            except (OSError,urllib.error.HTTPError):pass
            if cancel_event is not None:cancel_event.wait(.1)
            else:time.sleep(.1)
        raise PublicationError('PUBLICATION_READINESS_UNAVAILABLE: reviewed URL did not return 2xx')

    def _session(self,row,spec):
        try:
            session=RuntimeSession(self.stage,spec.image_id,list(spec.runtime_command),port=spec.internal_port,
                ecosystem=spec.ecosystem,docker=self.docker,env={'PORT':str(spec.internal_port)},
                application_origin=True,local_cookie_mode=spec.local_cookie_mode,persistent_database=True,
                mount_stage=False,use_image_command=True,host_port=row['host_port'],preserve_database=True)
        except OSError as exc:
            raise PublicationError('PUBLICATION_INGRESS_OCCUPIED: no foreign listener may be killed') from exc
        session.owner=row['owner']
        session.name=row['container_name']
        session.volume_name=row['volume_name']
        try:
            if row['volume_identity'] is not None:
                session.restore_owned_database(row['owner'],row['volume_identity'])
        except BaseException:
            session.release_ingress()  # no deletion authority from a failed adoption
            raise
        return session

    def publish(self,project_id,source_root:Path,spec:PublicationSpec,*,host_port=0,timeout=30,cancel_event=None):
        from ..validation.final_gate import source_snapshot
        source=Path(source_root).absolute()
        if source.resolve()!=source or self.root.is_relative_to(source) or source.is_relative_to(self.root):
            raise PublicationError('PUBLICATION_REGISTRY_MUST_BE_EXTERNAL_TO_SOURCE')
        if source_snapshot(source).digest!=spec.snapshot_hash:
            raise PublicationError('PUBLICATION_SOURCE_SNAPSHOT_DIFFER')
        _,lock=self._paths(project_id)
        with file_lock(lock),_LIVE_LOCK:
            _image(self.docker,spec)
            previous=self._read(project_id)
            if previous is not None and previous['status']!='destroyed':
                if previous['spec']!=spec.payload():
                    raise PublicationError('PUBLICATION_UPDATE_REQUIRES_MIGRATION_POLICY: existing service unchanged')
                def source_guard():
                    if source_snapshot(source).digest!=spec.snapshot_hash:
                        raise PublicationError('PUBLICATION_SOURCE_CHANGED_DURING_REUSE: previous service preserved')
                return self._recover(previous,spec,timeout,cancel_event,source_guard=source_guard)
            # Reserve ingress BEFORE launch: APP_ORIGIN is exact even on first
            # start, and a foreign listener fails without touching Docker state.
            session=RuntimeSession(self.stage,spec.image_id,list(spec.runtime_command),port=spec.internal_port,
                ecosystem=spec.ecosystem,docker=self.docker,env={'PORT':str(spec.internal_port)},
                application_origin=True,local_cookie_mode=spec.local_cookie_mode,persistent_database=True,
                mount_stage=False,use_image_command=True,host_port=host_port,preserve_database=True)
            row={'version':1,'project_id':project_id,'spec':spec.payload(),'owner':session.owner,
                 'container_name':session.name,'container_id':None,'container_created':None,'container_fingerprint':None,
                 'volume_name':session.volume_name,'volume_identity':None,'host_port':session.host_port,'origin':session.origin,
                 'status':'creating','migration':'not_started' if spec.migration_command else 'none','reason':'',
                 'migration_container_name':None,'migration_receipt':None}
            try:
                self._write(row)  # ownership intent precedes daemon-side effects
                if cancel_event is not None and cancel_event.is_set():raise PublicationError('PUBLICATION_CANCELLED')
                session.prepare_owned_database()
                row['volume_identity']=_volume(self.docker,row)
                self._write(row)
                if spec.migration_command:
                    if cancel_event is not None and cancel_event.is_set():raise PublicationError('PUBLICATION_CANCELLED')
                    row['migration']='pending';row['migration_container_name']='autospec-sandbox-'+uuid.uuid4().hex;self._write(row)
                    receipt=session.run_database_command(list(spec.migration_command),container_name=row['migration_container_name'],timeout=timeout)
                    row['migration_receipt']=receipt
                    row['migration']='completed' if receipt['return_code']==0 else 'failed'
                    row['migration_container_name']=None;self._write(row)
                    if receipt['return_code']:raise PublicationError('PUBLICATION_MIGRATION_FAILED: no seed/repair fallback')
                session.__enter__()  # exact baked CMD only AFTER migration completed
                self._capture(row,spec);self._write(row)
                self._healthy(session,spec,timeout,cancel_event)
                if source_snapshot(source).digest!=spec.snapshot_hash:
                    raise PublicationError('PUBLICATION_SOURCE_CHANGED_DURING_LAUNCH')
                row['status']='running';self._write(row)
                _LIVE[self._key(project_id)]=session
                return {**json.loads(json.dumps(row)),'created_this_call':True}
            except BaseException as exc:
                self._failed(row,session,exc)
                raise

    def _failed(self,row,session,exc):
        try:
            if session.volume_requested:
                row['volume_identity']=_volume(self.docker,row)
            session.close(preserve_database=True)
            row.update(status='failed',container_id=None,container_created=None,container_fingerprint=None,reason=str(exc)[:4096])
            self._write(row)
        except BaseException:
            row.update(status='uncertain',reason='Daemon cleanup or durable journal could not be attested')
            try:self._write(row)
            except Exception:pass
            raise

    def _recover(self,row,spec,timeout,cancel_event,*,source_guard=None):
        if row['status'] in {'stopping','destroyed','uncertain'} or row['migration'] in {'pending','failed','not_started'}:
            raise PublicationError('PUBLICATION_RECOVERY_BLOCKED: unresolved data/journal operation')
        current=_LIVE.get(self._key(row['project_id']))
        if current is not None and not current.closed:
            actual=self._capture(row,spec)
            if (actual and current.identifier==actual[0]['Id'] and current.owner==row['owner'] and
                current.image==spec.image_id and current.volume_identity==row['volume_identity']):
                self._healthy(current,spec,timeout,cancel_event)
                if source_guard is not None:source_guard()
                return {**json.loads(json.dumps(row)),'created_this_call':False}
            current.release_ingress();_LIVE.pop(self._key(row['project_id']),None)
        _image(self.docker,spec)
        volume=_volume(self.docker,row)
        if volume is None:
            # A prepared intent without any data/container is safe to retry;
            # a known volume disappearing is never silently replaced.
            if row['status']!='creating' or row['volume_identity'] is not None:
                raise PublicationError('PUBLICATION_OWNED_VOLUME_MISSING')
        else:row['volume_identity']=volume
        actual=_container(self.docker,row,spec)
        session=self._session(row,spec)  # reserve recorded port before mutation
        adopted_existing=False
        try:
            if actual and actual[0].get('State',{}).get('Running') is True:
                adopted_existing=True
                data,fingerprint=actual
                row.update(container_id=data['Id'],container_created=data['Created'],container_fingerprint=fingerprint)
                session.restore_owned_container(data['Id'])
            else:
                if actual:_cleanup_container(self.docker,actual[0]['Id'],row['owner'])
                row.update(container_id=None,container_created=None,container_fingerprint=None,status='creating')
                self._write(row)
                session.__enter__()
            self._capture(row,spec)
            self._healthy(session,spec,timeout,cancel_event)
            if source_guard is not None:source_guard()
            row['status']='running';row['reason']='';self._write(row)
            _LIVE[self._key(row['project_id'])]=session
            return {**json.loads(json.dumps(row)),'created_this_call':not adopted_existing}
        except BaseException as exc:
            if adopted_existing:
                # Cancel/refuse this new ingress, not a surviving previously
                # qualified daemon app or DB. Explicit stop is separate authority.
                session.release_ingress()
            else:self._failed(row,session,exc)
            raise

    def recover(self,project_id,*,timeout=30,cancel_event=None):
        _,lock=self._paths(project_id)
        with file_lock(lock),_LIVE_LOCK:
            row=self._read(project_id)
            if row is None:raise PublicationError('PUBLICATION_NOT_REGISTERED')
            return self._recover(row,PublicationSpec(**row['spec']),timeout,cancel_event)

    def status(self,project_id):
        _,lock=self._paths(project_id)
        with file_lock(lock),_LIVE_LOCK:
            row=self._read(project_id)
            if row is None:return {'registered':False,'running':False,'ingress_attached':False}
            if row['status'] in {'stopped','destroyed'}:
                return {**row,'registered':True,'running':False,'ingress_attached':False}
            spec=PublicationSpec(**row['spec']);_image(self.docker,spec)
            if _volume(self.docker,row) is None and row['volume_identity'] is not None:
                raise PublicationError('PUBLICATION_OWNED_VOLUME_MISSING')
            actual=_container(self.docker,row,spec)
            current=_LIVE.get(self._key(project_id))
            attached=(current is not None and not current.closed and current.thread is not None and actual is not None and
                      current.identifier==actual[0]['Id'] and current.owner==row['owner'] and current.volume_identity==row['volume_identity'])
            return {**row,'registered':True,'running':bool(actual and actual[0].get('State',{}).get('Running')),
                    'ingress_attached':attached}

    def stop(self,project_id,*,expected_container_id:str|None=None):
        _,lock=self._paths(project_id)
        with file_lock(lock),_LIVE_LOCK:
            row=self._read(project_id)
            if row is None:raise PublicationError('PUBLICATION_NOT_REGISTERED')
            if row['status']=='destroyed':return row
            if row['status']=='uncertain':raise PublicationError('PUBLICATION_RECOVERY_BLOCKED: uncertain identity')
            spec=PublicationSpec(**row['spec']);_image(self.docker,spec)
            volume=_volume(self.docker,row)
            if row['volume_identity'] is not None and volume is None:raise PublicationError('PUBLICATION_OWNED_VOLUME_MISSING')
            actual=_container(self.docker,row,spec)
            if expected_container_id is not None and (
                (actual is not None and actual[0]['Id']!=expected_container_id) or
                (actual is None and not (row['status']=='stopping' and row['container_id']==expected_container_id))):
                raise PublicationError('PUBLICATION_CLEANUP_RECEIPT_IDENTITY_DIFFER: replacement is not this operation resource')
            migration=None
            if row['migration_container_name'] is not None:
                if spec.migration_command is None:raise PublicationError('PUBLICATION_MIGRATION_IDENTITY_INVALID')
                temporary={**row,'container_name':row['migration_container_name'],'container_id':None,
                    'container_created':None,'container_fingerprint':None}
                migration=_container(self.docker,temporary,replace(spec,runtime_command=spec.migration_command,migration_command=None),migration=True)
            # Persist deliberate stop BEFORE any relay/daemon mutation. If
            # cleanup or its terminal flush fails, startup must never recreate
            # the service. Only another explicit stop may finish this intent.
            row['status']='stopping';row['reason']='';self._write(row)
            if migration is not None:
                _cleanup_container(self.docker,migration[0]['Id'],row['owner'])
            if row['migration_container_name'] is not None:
                row['migration_container_name']=None
            current=_LIVE.pop(self._key(project_id),None)
            if current is not None and not current.closed:
                if actual and current.identifier==actual[0]['Id']:current.close(preserve_database=True)
                else:
                    current.release_ingress()
                    if actual:_cleanup_container(self.docker,actual[0]['Id'],row['owner'])
            elif actual:_cleanup_container(self.docker,actual[0]['Id'],row['owner'])
            row.update(status='stopped',container_id=None,container_created=None,container_fingerprint=None,volume_identity=volume)
            self._write(row)
            return json.loads(json.dumps(row))

    def release_ingress(self,project_id):
        """Graceful factory shutdown/handoff; live Docker app/data survive."""
        _,lock=self._paths(project_id)
        with file_lock(lock),_LIVE_LOCK:
            row=self._read(project_id)
            if row is None:raise PublicationError('PUBLICATION_NOT_REGISTERED')
            self._capture(row,PublicationSpec(**row['spec']));self._write(row)
            current=_LIVE.pop(self._key(project_id),None)
            if current is None:raise PublicationError('PUBLICATION_INGRESS_NOT_OWNED_BY_THIS_PROCESS')
            current.release_ingress()
            return json.loads(json.dumps(row))

    def destroy_data(self,project_id):
        """Explicit irreversible cleanup, ONLY after stop and exact identities."""
        _,lock=self._paths(project_id)
        with file_lock(lock),_LIVE_LOCK:
            row=self._read(project_id)
            if row is None:raise PublicationError('PUBLICATION_NOT_REGISTERED')
            if row['status']=='destroyed':return row
            if row['status']!='stopped' or _container(self.docker,row,PublicationSpec(**row['spec'])) is not None:
                raise PublicationError('PUBLICATION_STOP_REQUIRED_BEFORE_DATA_DESTRUCTION')
            volume=_volume(self.docker,row)
            if volume is not None:
                result=_docker_call([self.docker,'volume','rm',row['volume_name']],capture_output=True,text=True,timeout=5,check=False)
                if result.returncode:raise PublicationError('PUBLICATION_OWNED_VOLUME_CLEANUP_FAILED')
            elif row['volume_identity'] is not None:raise PublicationError('PUBLICATION_OWNED_VOLUME_MISSING')
            row['status']='destroyed';self._write(row)
            return json.loads(json.dumps(row))
