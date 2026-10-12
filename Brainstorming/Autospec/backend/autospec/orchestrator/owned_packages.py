"""Qualified CLI/library artifact ownership, never a latest-name or CID guess.

An external prepared journal precedes a UUID tag request. Fresh immutable
image/source/default-command facts are required on every admission. Detach
removes only the exact owned alias, never rmi(imageSHA), shared tags, containers,
networks, source files or dependency caches. This is NOT a review authority.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import asdict,dataclass
from pathlib import Path

from ..agents.file_broker import ExecutionContext,FileBroker
from .dependencies import atomic_json,file_lock
from .isolated_validation import _runtime_argv
from .sandbox import _docker_call


class PackageError(RuntimeError):pass


@dataclass(frozen=True)
class PackageSpec:
    image_id: str
    snapshot_hash: str
    contract_hash: str
    runtime_command: tuple[str,...]

    def __post_init__(self):
        if (not isinstance(self.image_id,str) or not re.fullmatch(r'sha256:[a-f0-9]{64}',self.image_id) or
            not all(isinstance(x,str) and re.fullmatch(r'[a-f0-9]{64}',x) for x in (self.snapshot_hash,self.contract_hash))):
            raise PackageError('PACKAGE_FACTS_REQUIRED: immutable image/source/contract identities')
        object.__setattr__(self,'runtime_command',tuple(_runtime_argv(self.runtime_command)))

    def payload(self):return json.loads(json.dumps(asdict(self)))


def _image(docker,name):
    result=_docker_call([docker,'image','inspect',name,'--format','{{json .}}'],capture_output=True,text=True,timeout=5,check=False)
    if result.returncode:
        if 'no such' in result.stderr.lower() and any(x in result.stderr.lower() for x in ('image','object')):return None
        raise PackageError('PACKAGE_INSPECTION_UNAVAILABLE')
    try:
        value=json.loads(result.stdout)
        if not isinstance(value,dict):raise ValueError('image object')
        return value
    except (ValueError,TypeError) as exc:raise PackageError('PACKAGE_INSPECTION_INVALID') from exc


def attest_package_image(spec:PackageSpec,*,docker='docker'):
    value=_image(docker,spec.image_id)
    if (not value or value.get('Id')!=spec.image_id or value.get('Os')!='linux' or
        value.get('Config',{}).get('WorkingDir')!='/app' or value['Config'].get('Cmd')!=list(spec.runtime_command) or
        value['Config'].get('Entrypoint') not in (None,[]) or
        value['Config'].get('Labels',{}).get('autospec.snapshot')!=spec.snapshot_hash):
        raise PackageError('PACKAGE_IMAGE_FACTS_DIFFER: actual source/image/CMD/entrypoint/OS')
    return value


class PackageRegistry:
    def __init__(self,root:Path,*,docker='docker'):
        self.root=Path(root).absolute()
        if self.root.resolve()!=self.root:raise PackageError('PACKAGE_REGISTRY_ALIAS_REFUSED')
        self.root.mkdir(parents=True,exist_ok=True)
        self.broker=FileBroker(ExecutionContext('package-registry',self.root));self.docker=docker

    def _paths(self,project_id):
        if not isinstance(project_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',project_id):
            raise PackageError('PACKAGE_PROJECT_ID_INVALID')
        return self.broker.path(project_id+'.json'),self.broker.path(project_id+'.lock')

    def _alias(self,project_id,owner):
        return 'autospec/qualified-package-'+hashlib.sha256(project_id.encode()).hexdigest()[:16]+':'+owner

    def _read(self,project_id):
        path,_=self._paths(project_id)
        if not path.exists():return None
        if not path.is_file() or path.stat().st_size>131072:raise PackageError('PACKAGE_JOURNAL_INVALID')
        try:
            row=json.loads(path.read_text(encoding='utf-8'))
            if (not isinstance(row,dict) or set(row)!={'version','project_id','spec','owner','alias','absence_checked','status'} or
                type(row['version']) is not int or row['version']!=1 or row['project_id']!=project_id or
                not isinstance(row['owner'],str) or not re.fullmatch(r'[a-f0-9]{32}',row['owner']) or
                row['alias']!=self._alias(project_id,row['owner']) or row['absence_checked'] is not True or
                row['status'] not in {'prepared','packaged','detached','uncertain'} or PackageSpec(**row['spec']).payload()!=row['spec']):
                raise ValueError('journal schema/ownership')
            return row
        except (KeyError,TypeError,ValueError) as exc:
            raise PackageError('PACKAGE_JOURNAL_INVALID: no tag/removal authority') from exc

    def _write(self,row):
        path,_=self._paths(row['project_id']);atomic_json(path,row);self._read(row['project_id'])

    def _assert_alias(self,row):
        value=_image(self.docker,row['alias'])
        if value is not None and value.get('Id')!=row['spec']['image_id']:
            raise PackageError('PACKAGE_ALIAS_IDENTITY_DIFFER: foreign replacement never removed')
        return value

    def package(self,project_id,source_root:Path,spec:PackageSpec,*,cancel_event=None):
        from ..validation.final_gate import source_snapshot
        source=Path(source_root).absolute()
        if source.resolve()!=source or self.root.is_relative_to(source) or source.is_relative_to(self.root):
            raise PackageError('PACKAGE_REGISTRY_MUST_BE_EXTERNAL_TO_SOURCE')
        if source_snapshot(source).digest!=spec.snapshot_hash:raise PackageError('PACKAGE_SOURCE_SNAPSHOT_DIFFER')
        _,lock=self._paths(project_id)
        with file_lock(lock):
            if cancel_event is not None and cancel_event.is_set():raise PackageError('PACKAGE_CANCELLED')
            attest_package_image(spec,docker=self.docker)
            row=self._read(project_id)
            if row is not None and row['status']!='detached':
                if row['spec']!=spec.payload():raise PackageError('PACKAGE_UPDATE_REQUIRES_EXPLICIT_DETACH: previous package unchanged')
                if row['status']=='uncertain':raise PackageError('PACKAGE_JOURNAL_UNCERTAIN: explicit disposition required')
                alias=self._assert_alias(row)
                if alias is not None:
                    if source_snapshot(source).digest!=spec.snapshot_hash:
                        raise PackageError('PACKAGE_SOURCE_CHANGED_DURING_REUSE: previous alias preserved')
                    row['status']='packaged';self._write(row);return {**row,'created_this_call':False}
                if row['status']=='packaged':raise PackageError('PACKAGE_OWNED_ALIAS_MISSING')
            else:
                owner=uuid.uuid4().hex
                row={'version':1,'project_id':project_id,'spec':spec.payload(),'owner':owner,
                     'alias':self._alias(project_id,owner),'absence_checked':True,'status':'prepared'}
                if _image(self.docker,row['alias']) is not None:raise PackageError('PACKAGE_ALIAS_OCCUPIED')
                self._write(row)  # proven absent UUID intent precedes tag request
            try:
                if cancel_event is not None and cancel_event.is_set():raise PackageError('PACKAGE_CANCELLED')
                result=_docker_call([self.docker,'tag',spec.image_id,row['alias']],capture_output=True,text=True,timeout=10,check=False)
                if result.returncode:raise PackageError('PACKAGE_TAG_UNAVAILABLE')
                if self._assert_alias(row) is None:raise PackageError('PACKAGE_TAG_IDENTITY_MISSING')
                attest_package_image(spec,docker=self.docker)
                if source_snapshot(source).digest!=spec.snapshot_hash:raise PackageError('PACKAGE_SOURCE_CHANGED_DURING_TAG')
                if cancel_event is not None and cancel_event.is_set():raise PackageError('PACKAGE_CANCELLED')
                row['status']='packaged';self._write(row);return {**json.loads(json.dumps(row)),'created_this_call':True}
            except BaseException:
                # Even cancellation/daemon timeout cannot authorize rmi SHA or
                # removal of an alias whose identity changed concurrently.
                try:self._detach(row)
                except Exception:
                    row['status']='uncertain'
                    try:self._write(row)
                    except Exception:pass
                raise

    def inspect(self,project_id,*,expected:PackageSpec|None=None):
        _,lock=self._paths(project_id)
        with file_lock(lock):
            row=self._read(project_id)
            if row is None:return {'registered':False,'packaged':False}
            if expected is not None and row['spec']!=expected.payload():raise PackageError('PACKAGE_EXPECTED_FACTS_DIFFER')
            if row['status']=='detached':return {**row,'registered':True,'packaged':False}
            if row['status']=='uncertain':raise PackageError('PACKAGE_JOURNAL_UNCERTAIN')
            attest_package_image(PackageSpec(**row['spec']),docker=self.docker)
            exists=self._assert_alias(row) is not None
            return {**row,'registered':True,'packaged':exists}

    def _detach(self,row):
        alias=self._assert_alias(row)
        if alias is not None:
            attest_package_image(PackageSpec(**row['spec']),docker=self.docker)
            result=_docker_call([self.docker,'image','rm',row['alias']],capture_output=True,text=True,timeout=10,check=False)
            if result.returncode or self._assert_alias(row) is not None:raise PackageError('PACKAGE_OWNED_ALIAS_CLEANUP_UNAVAILABLE')
        row['status']='detached';self._write(row)
        return json.loads(json.dumps(row))

    def detach(self,project_id,*,expected_alias:str|None=None,expected_image_id:str|None=None):
        _,lock=self._paths(project_id)
        with file_lock(lock):
            row=self._read(project_id)
            if row is None:raise PackageError('PACKAGE_NOT_REGISTERED')
            if (expected_alias is not None and row['alias']!=expected_alias or
                expected_image_id is not None and row['spec']['image_id']!=expected_image_id):
                raise PackageError('PACKAGE_CLEANUP_RECEIPT_IDENTITY_DIFFER: replacement is not this operation resource')
            # Fresh alias ID determines authority even for an uncertain tag
            # request. Immutable journal/schema still cannot remove foreign ID.
            return self._detach(row)
