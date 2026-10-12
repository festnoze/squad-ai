"""REM-25 supervisor. Import is inert; --preflight never creates; --launch creates once."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import stat
import subprocess
import sys
import time
import uuid
from urllib.request import Request, build_opener, ProxyHandler

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = Path('C:/Dev/squad-ai/Brainstorming/Autospec/workspace')
HASHES = {
 'docs/validation/support-client/01_specification.md': '0a99950df5ee132253fa5aefb1a8f6e4f7a4b64c1436072564be6d28195fb0f3',
 'docs/validation/support-client/02_requirements_verification.md': 'efdab8ea54208557f01abcb5324172e42b9c5cf88536611d64ba65b92564cbf4',
 'artifacts/remediation/REM-25/source-facts-v02.json': 'f2b3105f207cdf4d2feb7219535146e6890d838c7b4a93a4975c6ded040644b9',
}
OFF = ('FAKE_AGENTS', 'REFINE', 'REFINE_PO', 'REFINE_DEV', 'REVIEW_PLAN',
 'SECURITY_REVIEW', 'EVALUATOR', 'INDEPENDENCE', 'LANGFUSE', 'ROLE_ROUTING',
 'ESCALATE_ON_RETRY', 'DISPUTE_ESCALATION', 'CONCURRENT_BUDGET_RESERVATIONS',
 'PARTIAL_DELIVERY', 'GOVERNANCE', 'OBSERVATIONS', 'ORPHAN_SWEEP_ON_BOOT', 'NPM_SHARED_CACHE',
 'RETRO', 'KNOWLEDGE', 'SHARED_LESSONS')
CLI_FLAGS = ('--restricted','--safe-mode','--tools','--strict-mcp-config',
 '--disable-slash-commands','--no-chrome','--no-session-persistence','--permission-prompts')
MODELS = tuple('MODEL_'+p for p in ('SPEC','ANALYZE','PLAN','ARCHITECT','BUILD','DONE','BOSS','WORKER','CHECKER'))
AUTH_KEYS = ('loggedIn','authMethod','apiProvider','subscriptionType')
STACK = dict(backend='python',framework='fastapi',frontend='react',database='sqlite',kind='fullstack',source='explicit')
LEGACY_STACK = dict(backend='Python/FastAPI',database='SQLite',frontend='React/TypeScript/Vite')
# Deliberately NOT a general restart/retry facility. Only the known zero-call
# failure of this exact campaign may cross this one-shot recovery boundary.
RECOVERY_CAMPAIGN = 'relais-support-rem25-20261012-final'
RECOVERY_PROJECT = 'relais-support-rem25-20261012-fi-0e6ebc49'
RECOVERY_COMMIT = '312cc2d38dc1a8ce7125243e4b3f36ac5ca03395'
RECOVERY_PAYLOAD_SHA256 = 'b0d4fea581030338244aaa62e8df0b794047d702cc39b3cbdd1a6ddd8696ebaf'
RECOVERY_STATE_SHA256 = 'b3e78ec1f96e1d3fa2f097965099a210182d3e713735c049d6325c2cda673256'
RECOVERY_JOURNAL_SHA256 = 'ebee209c9703c16ff2e1e060da4a9b410d57c5febbfc00ff0530701425a66a68'
RECOVERY_CONTRACT = 'b6850a3f3486afaa97816567e26ae79705464d2703ac204c0ca3440acf9e3bc6'
RECOVERY_ORACLE_SHA256 = '06fef2a5c08632e6dd6f398c6d54d4e8a30963055d601b5c002be83a4d0bdb80'
RECOVERY_ERROR = "'Python/FastAPI' is not a valid BackendLanguage"

class AdmissionError(RuntimeError):
    pass

def digest(data):
    return hashlib.sha256(data).hexdigest()

def canonical(data):
    return json.dumps(data,sort_keys=True,ensure_ascii=False).encode('utf-8')

def environment(base,campaign,port):
    env = {k:v for k,v in base.items() if not (k.endswith('API_KEY') or
        k.startswith(('ANTHROPIC_','OPENAI_','LANGFUSE_','MODEL_')) or
        k in ('CLAUDE_CODE_OAUTH_TOKEN','PYTHONPATH','PYTHONHOME','_FORCE_MODEL',
              'AUTOSPEC_CAMPAIGN_COMMIT','AUTOSPEC_CAMPAIGN_RUNTIME_DIR'))}
    env.update({k:'false' for k in OFF})
    env.update({k:'sonnet' for k in MODELS})
    env.update(GENERATION_ONLY_AGENTS='true',AGENT_PROVIDER='claude code',
        CLAUDE_MODEL='sonnet',CONSTITUTION_MODEL='sonnet',MODEL_LADDER='',
        PRESET='',MAX_PARALLEL_DEVS='1',SANDBOX='true',PO_PIPELINE='off',
        WORKSPACE_ROOT=str(campaign/'projects'),EXTERNAL_REVIEW_WAIT_SECONDS='7200',
        AUTOSPEC_CONTROL_HOSTS=json.dumps([f'127.0.0.1:{port}']),AUTOSPEC_CONTROL_ORIGINS='[]')
    return env

def validate_environment(env,campaign,port):
    for k,v in environment({},campaign,port).items():
        if env.get(k) != v:
            raise AdmissionError('configuration mismatch: '+k)
    if any(k.endswith('API_KEY') or k.startswith('ANTHROPIC_') for k in env):
        raise AdmissionError('direct API credentials forbidden')

def command(args,*,cwd,env):
    if args[0] == 'claude':
        args = [next((shutil.which(n) for n in ('claude.cmd','claude.exe','claude') if shutil.which(n)), 'claude'), *args[1:]]
    r = subprocess.run(args,cwd=cwd,env=env,capture_output=True,text=True,timeout=30,check=False)
    if r.returncode:
        raise AdmissionError('prerequisite command failed: '+args[0])
    return r.stdout

def check_port(port):
    if port in (18004,8126) or not 1024 <= port <= 65535:
        raise AdmissionError('forbidden factory port')
    with socket.socket() as sock:
        if os.name == 'nt':
            sock.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
        sock.bind(('127.0.0.1',port))

def preflight(root,campaign,port,expected_commit,env,*,run=command,port_check=check_port,workspace=WORKSPACE,recovery_project=None):
    validate_environment(env,campaign,port)
    if not re.fullmatch('[0-9a-f]{40}',expected_commit):
        raise AdmissionError('qualified full commit SHA required')
    if campaign.parent.resolve() != workspace.resolve() or not re.fullmatch(
        'relais-support-rem25-[a-z0-9][a-z0-9-]{0,63}',campaign.name):
        raise AdmissionError('precisely named new campaign under workspace required')
    recovery = None
    if recovery_project is not None:
        recovery = recovery_snapshot(root,campaign,recovery_project)
    elif campaign.exists():
        raise AdmissionError('campaign exists; no retry or budget reset')
    head = run(['git','rev-parse','HEAD'],cwd=root,env=env).strip()
    dirty = run(['git','status','--porcelain','--untracked-files=all'],cwd=root,env=env)
    if head != expected_commit or dirty.strip():
        raise AdmissionError('factory identity not clean qualified commit')
    sources = {}
    for name,sha in HASHES.items():
        data = (root/name).read_bytes()
        if digest(data) != sha:
            raise AdmissionError('immutable source hash mismatch: '+name)
        sources[name] = data.decode('utf-8')
    if port in (18004,8126) or not 1024 <= port <= 65535:
        raise AdmissionError('forbidden factory port')
    port_check(port)
    docker = run([env.get('DOCKER_CMD','docker'),'info','--format','{{.OSType}}'],cwd=root,env=env).strip()
    if docker != 'linux':
        raise AdmissionError('Docker Linux required')
    cli = env.get('CLAUDE_CMD','claude')
    help_text = run([cli,'--help'],cwd=root,env=env)
    if any(flag not in help_text for flag in (*CLI_FLAGS,'--model','auth')):
        raise AdmissionError('Claude CLI interface unavailable')
    raw = json.loads(run([cli,'auth','status','--json'],cwd=root,env=env))
    auth = {k:raw.get(k) for k in AUTH_KEYS}
    if auth != dict(loggedIn=True,authMethod='claude.ai',apiProvider='firstParty',subscriptionType='team'):
        raise AdmissionError('Claude Team subscription not explicitly attested')
    receipt = dict(factory_commit=head,source_hashes=dict(HASHES),auth=auth,
        checked_at=datetime.now(timezone.utc).isoformat(),docker_os=docker,
        port=port,campaign=str(campaign),sources=sources)
    if recovery is not None:
        receipt['recovery'] = recovery
    return receipt

def payload(receipt,campaign):
    sources = receipt['sources']
    facts = json.loads(sources['artifacts/remediation/REM-25/source-facts-v02.json'])
    ids = [f'{p}-{n:02d}' for p,c in (('SEC',15),('FUN',13),('ARC',9),('UX',8),('TST',6),('OPS',6)) for n in range(1,c+1)]
    if facts['acceptance_facts'][0]['requirement_ids'] != ids:
        raise AdmissionError('requirement identity mismatch')
    return dict(name=campaign.name,goal='Construire Relais Support : sources v0.2 completes, 57 IDs, 56 obligatoires, OPS-06 diagnostic, 7 lots maximum.',
        auto_spec=True,product_profile='fullstack',budget_usd=40.0,
        brief=sources['docs/validation/support-client/01_specification.md'],
        acceptance_reference=sources['docs/validation/support-client/02_requirements_verification.md'],
        acceptance_facts=facts['acceptance_facts'],acceptance_reviewed_by='parent-source-only-review-2026-10-12',
        acceptance_max_lots=7,technical_stack=dict(STACK))

def _regular(path):
    info = path.lstat()
    if (path.is_symlink() or getattr(info,'st_file_attributes',0) & 0x400 or
        (stat.S_ISREG(info.st_mode) and info.st_nlink != 1) or
        not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode))):
        raise AdmissionError('recovery path alias/special file forbidden')
    return info

def _inventory(campaign,allowed_files=None):
    files,total = {},0
    def visit(path):
        nonlocal total
        info = _regular(path)
        if stat.S_ISDIR(info.st_mode):
            relative = path.relative_to(campaign).as_posix()
            if (allowed_files is not None and relative != '.' and
                relative not in ('projects/.autospec-tmp','.autospec-tmp') and
                not any(name.startswith(relative+'/') for name in allowed_files)):
                raise AdmissionError('unexpected campaign/product directory')
            for child in path.iterdir(): visit(child)
        else:
            total += info.st_size
            if total > 16*1024*1024:
                raise AdmissionError('recovery evidence bound exceeded')
            files[path.relative_to(campaign).as_posix()] = path.read_bytes()
    visit(campaign)
    return files

def _json(data):
    def pairs(items):
        out = {}
        for key,value in items:
            if key in out: raise AdmissionError('duplicate recovery JSON field')
            out[key] = value
        return out
    return json.loads(data,object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(AdmissionError('nonfinite recovery JSON')))

def recovery_snapshot(root,campaign,project):
    if campaign.name != RECOVERY_CAMPAIGN or project != RECOVERY_PROJECT:
        raise AdmissionError('only the exact known campaign/project may recover')
    if (campaign/'recovery-attempt.json').exists():
        raise AdmissionError('recovery already attempted; UNKNOWN must never retry')
    state_path = f'projects/{project}/autospec-state.json'
    oracle_path = f'projects/.autospec-supervisor/{project}/contracts/{RECOVERY_CONTRACT}.json'
    allowed = {'preflight.json','input.json','creation-attempt.json','supervisor.jsonl',
               'factory-identity.json','factory.log',state_path,f'projects/{project}/build-monitor.jsonl',oracle_path,
               *(f'inputs/{Path(name).name}' for name in HASHES)}
    files = _inventory(campaign,allowed)
    if set(files) != allowed:
        raise AdmissionError('unexpected or missing campaign/product files')
    old,body,marker = (_json(files[name]) for name in ('preflight.json','input.json','creation-attempt.json'))
    events = [_json(line) for line in files['supervisor.jsonl'].splitlines() if line]
    admitted = [e for e in events if e.get('event') == 'ADMITTED']
    created = [e for e in events if e.get('event') == 'CREATED']
    attempted = [e for e in events if e.get('event') == 'CREATE_ATTEMPT']
    if (len(admitted) != 1 or {k:v for k,v in admitted[0].items() if k not in ('time','event')} != old or
        len(created) != 1 or created[0].get('project_id') != project or len(attempted) != 1 or
        attempted[0].get('payload_sha256') != RECOVERY_PAYLOAD_SHA256 or
        any(e.get('event') in ('CREATE_OUTCOME_UNKNOWN','RECOVERY_ATTEMPT','RECOVERY_OUTCOME_UNKNOWN') for e in events) or
        digest(files['supervisor.jsonl']) != RECOVERY_JOURNAL_SHA256):
        raise AdmissionError('known CREATED journal identity required')
    if (old.get('factory_commit') != RECOVERY_COMMIT or old.get('source_hashes') != HASHES or
        old.get('campaign') != str(campaign) or old.get('docker_os') != 'linux' or
        old.get('auth') != dict(loggedIn=True,authMethod='claude.ai',apiProvider='firstParty',subscriptionType='team') or
        old.get('estimated_budget_usd') != 40 or old.get('billing_cap') is not False or
        old.get('payload_sha256') != RECOVERY_PAYLOAD_SHA256 or
        marker != dict(payload_sha256=RECOVERY_PAYLOAD_SHA256,outcome='UNKNOWN') or
        digest(files['input.json']) != RECOVERY_PAYLOAD_SHA256):
        raise AdmissionError('original admission/input identity changed')
    validate_environment(old['configuration'],campaign,old['port'])
    for name,sha in HASHES.items():
        if digest(files['inputs/'+Path(name).name]) != sha or digest((root/name).read_bytes()) != sha:
            raise AdmissionError('immutable recovery source changed')
    sources = {name:files['inputs/'+Path(name).name].decode('utf-8') for name in HASHES}
    expected = payload({'sources':sources},campaign) | {'technical_stack':LEGACY_STACK}
    if body != expected or digest(files[oracle_path]) != RECOVERY_ORACLE_SHA256:
        raise AdmissionError('original brief/budget/oracle changed')
    state = _json(files[state_path])
    usage = state.get('usage',{})
    if (state.get('id') != project or state.get('name') != campaign.name or state.get('phase') != 'needs_attention' or
        state.get('bootstrap_status') != 'failed' or state.get('bootstrap_detail') != RECOVERY_ERROR or
        state.get('bootstrap_fingerprint') != '' or state.get('bootstrap_verified_once') is not False or
        state.get('running') is not False or state.get('paused') is not False or state.get('stories') != [] or
        state.get('brief') != body['brief'] or state.get('acceptance_contract_hash') != RECOVERY_CONTRACT or
        state.get('budget_usd') != 40 or state.get('technical_stack') != LEGACY_STACK or
        any(type(usage.get(k)) not in (int,float) or usage[k] != 0 for k in
            ('cost_usd','input_tokens','output_tokens','agent_calls','failed_calls','unreported_calls')) or
        digest(files[state_path]) != RECOVERY_STATE_SHA256):
        raise AdmissionError('not the exact pre-bootstrap zero-usage failure')
    identity = _json(files['factory-identity.json'])
    if identity.get('factory_commit') != RECOVERY_COMMIT:
        raise AdmissionError('original factory identity changed')
    return dict(project_id=project,state=state,state_path=state_path,
                files_sha256={k:digest(v) for k,v in files.items()},journal_bytes=len(files['supervisor.jsonl']))

def reserve_recovery(campaign,recovery,receipt):
    runtime = campaign/'recovery-runtime'/uuid.uuid4().hex
    attempt = dict(outcome='UNKNOWN',retry_permitted=False,project_id=recovery['project_id'],
                   factory_commit=receipt['factory_commit'],runtime_dir=str(runtime),
                   original_files_sha256=recovery['files_sha256'])
    # Exclusive, durable intent precedes even starting the replacement factory.
    with (campaign/'recovery-attempt.json').open('xb') as out:
        out.write(canonical(attempt)); out.flush(); os.fsync(out.fileno())
    journal(campaign,'RECOVERY_ATTEMPT',**attempt)
    runtime.mkdir(parents=True,exist_ok=False)
    return runtime

def verify_recovery_invariants(campaign,recovery,state,*,language_changed=False):
    expected = dict(recovery['state'])
    if language_changed:
        expected['technical_stack'] = dict(backend='python',source='explicit')
    if canonical(state) != canonical(expected):
        raise AdmissionError('recovery metadata changed immutable state/usage/budget')
    expected_project = {k.removeprefix('projects/'):v for k,v in recovery['files_sha256'].items() if k.startswith('projects/')}
    files = _inventory(campaign/'projects',expected_project)
    if set(files) != set(expected_project):
        raise AdmissionError('product files appeared before resume')
    for name,sha in recovery['files_sha256'].items():
        if name == recovery['state_path'] or name == 'supervisor.jsonl': continue
        if digest((campaign/name).read_bytes()) != sha:
            raise AdmissionError('recovery immutable evidence changed')
    disk_state = _json(files[recovery['state_path'].removeprefix('projects/')])
    if canonical(disk_state) != canonical(expected):
        raise AdmissionError('persisted recovery state differs from API state')
    with (campaign/'supervisor.jsonl').open('rb') as original:
        if digest(original.read(recovery['journal_bytes'])) != recovery['files_sha256']['supervisor.jsonl']:
            raise AdmissionError('original journal bytes changed')

def recover_once(campaign,url,recovery,*,request=None):
    request = request or http
    project = recovery['project_id']
    intent = _json((campaign/'recovery-attempt.json').read_bytes())
    if (intent.get('project_id') != project or intent.get('outcome') != 'UNKNOWN' or
        intent.get('retry_permitted') is not False or intent.get('original_files_sha256') != recovery['files_sha256']):
        raise AdmissionError('exclusive recovery intent does not bind this state')
    endpoint = url+'/api/projects/'+project
    with (campaign/'recovery-dispatch.json').open('xb') as out:
        out.write(canonical(dict(project_id=project,outcome='UNKNOWN',retry_permitted=False)))
        out.flush(); os.fsync(out.fileno())
    try:
        verify_recovery_invariants(campaign,recovery,request('GET',endpoint))
        result = request('PUT',endpoint+'/language',{'language':'python'})
        if result.get('ok') is not True:
            raise AdmissionError('language metadata was not acknowledged')
        verify_recovery_invariants(campaign,recovery,request('GET',endpoint),language_changed=True)
        journal(campaign,'RESUME_ATTEMPT',project_id=project,outcome='UNKNOWN',retry_permitted=False)
        # Never repeat this request, including ambiguous timeout/connection loss.
        if request('POST',endpoint+'/resume-build').get('ok') is not True:
            raise AdmissionError('resume not acknowledged; outcome remains UNKNOWN')
        journal(campaign,'RESUMED',project_id=project)
        return project
    except BaseException:
        journal(campaign,'RECOVERY_OUTCOME_UNKNOWN',project_id=project,retry_permitted=False)
        raise

def journal(destination,event,**fields):
    with (destination/'supervisor.jsonl').open('a',encoding='utf-8') as f:
        f.write(json.dumps(dict(time=datetime.now(timezone.utc).isoformat(),event=event,**fields),ensure_ascii=False)+'\n')
        f.flush()
        os.fsync(f.fileno())

def http(method,url,body=None):
    req = Request(url,data=canonical(body) if body is not None else None,
                  method=method,headers={'Content-Type':'application/json'})
    with build_opener(ProxyHandler({})).open(req,timeout=30) as response:
        return json.load(response)

def create_once(campaign,url,body,*,request=http):
    with (campaign/'creation-attempt.json').open('x',encoding='utf-8') as f:
        json.dump(dict(payload_sha256=digest(canonical(body)),outcome='UNKNOWN'),f)
        f.flush()
        os.fsync(f.fileno())
    journal(campaign,'CREATE_ATTEMPT',payload_sha256=digest(canonical(body)))
    try:
        project = request('POST',url+'/api/projects',body)['id']
        if not re.fullmatch('[a-zA-Z0-9_-]+',project):
            raise AdmissionError('invalid creation identity')
    except Exception:
        journal(campaign,'CREATE_OUTCOME_UNKNOWN',retry_permitted=False)
        raise
    journal(campaign,'CREATED',project_id=project)
    return project

def trusted_imports(root,env):
    # This installed python-dotenv lacks PYTHON_DOTENV_DISABLED. Disable local
    # .env loading in the fresh trusted process BEFORE any Autospec import.
    os.environ.clear()
    os.environ.update(env)
    import dotenv
    dotenv.load_dotenv = lambda *args,**kwargs: False
    sys.path.insert(0,str(root/'backend'))

def factory(root,port):
    env = dict(os.environ)
    validate_environment(env,Path(env['WORKSPACE_ROOT']).parent,port)
    expected = env['AUTOSPEC_CAMPAIGN_COMMIT']
    if command(['git','rev-parse','HEAD'],cwd=root,env=env).strip() != expected or command(
        ['git','status','--porcelain','--untracked-files=all'],cwd=root,env=env).strip():
        raise AdmissionError('factory identity changed before import')
    if any(digest((root/name).read_bytes()) != sha for name,sha in HASHES.items()):
        raise AdmissionError('source changed before factory import')
    trusted_imports(root,env)
    from autospec.config import settings
    from autospec.orchestrator.profiles import PROFILES
    validate_settings(settings,PROFILES['fullstack'].overrides,Path(env['WORKSPACE_ROOT']))
    from autospec.agents.generation_policy import GenerationOnlyRunner
    from autospec.api.server import app, _runner, _SERVER_STARTED_AT, _LOADED_SOURCE_STAMP
    if not isinstance(_runner,GenerationOnlyRunner):
        raise AdmissionError('generation-only runner missing')
    identity = dict(pid=os.getpid(),started_at=_SERVER_STARTED_AT,source_stamp=_LOADED_SOURCE_STAMP,
                    factory_commit=expected)
    runtime = runtime_directory(env,Path(env['WORKSPACE_ROOT']).parent)
    with (runtime/'factory-identity.json').open('xb') as f:
        f.write(canonical(identity))
        f.flush()
        os.fsync(f.fileno())
    import uvicorn
    uvicorn.run(app,host='127.0.0.1',port=port,reload=False,access_log=False)

def validate_settings(settings,overrides,workspace):
    off = ('fake_agents','refine_enabled','refine_po','refine_dev','review_plan_enabled',
        'security_review_enabled','evaluator_enabled','independence_enabled','langfuse_enabled',
        'role_routing_enabled','escalate_on_retry_enabled','dispute_escalation_enabled',
        'concurrent_budget_reservations','partial_delivery_enabled','governance_enabled',
        'observations_enabled','orphan_sweep_on_boot','npm_shared_cache','retro_enabled',
        'knowledge_enabled','shared_lessons_enabled')
    for name in off:
        if getattr(settings,name,None) is not False or overrides.get(name,False) is not False:
            raise AdmissionError('effective setting/profile mismatch: '+name)
    if (settings.agent_provider != 'claude code' or settings.claude_model != 'sonnet' or
        not settings.generation_only_agents or not settings.sandbox_enabled or
        settings.workspace_root != workspace or settings.external_review_wait_seconds != 7200 or
        settings.max_parallel_devs != 1 or settings.model_ladder or
        any(v != 'sonnet' for v in [*settings.phase_models.values(),*settings.model_tiers.values()])):
        raise AdmissionError('effective provider/model/workspace/budget composition mismatch')

class RetainedInterpreter(str):
    """Creation identity plus the exact live OS handle; owner closes in finally."""
    def __new__(cls,identity,api,handle):
        obj = str.__new__(cls,identity)
        obj.api,obj.handle = api,handle
        return obj

    def assert_alive(self):
        import ctypes
        from ctypes import wintypes
        self.api.GetExitCodeProcess.argtypes = [wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)]
        self.api.GetExitCodeProcess.restype = wintypes.BOOL
        code = wintypes.DWORD()
        if not self.handle or not self.api.GetExitCodeProcess(self.handle,ctypes.byref(code)) or code.value != 259:
            raise AdmissionError('owned actual interpreter no longer alive')

    def close(self):
        if self.handle:
            handle,self.handle = self.handle,None
            self.api.CloseHandle(handle)

def job_member_identity(job,pid):
    # A Windows venv redirector may own a different actual interpreter PID.
    # Accept that PID ONLY after acquiring its handle and proving membership
    # in this exact retained Job. Never trust PID/command line alone.
    import ctypes
    from ctypes import wintypes
    api = ctypes.WinDLL('kernel32',use_last_error=True)
    api.OpenProcess.argtypes = [wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
    api.OpenProcess.restype = wintypes.HANDLE
    api.IsProcessInJob.argtypes = [wintypes.HANDLE,wintypes.HANDLE,ctypes.POINTER(wintypes.BOOL)]
    api.IsProcessInJob.restype = wintypes.BOOL
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = api.OpenProcess(0x1000,False,pid)
    if not handle:
        raise AdmissionError('actual interpreter handle unavailable')
    try:
        member = wintypes.BOOL()
        if not api.IsProcessInJob(handle,job.handle,ctypes.byref(member)) or not member.value:
            raise AdmissionError('actual interpreter not in owned factory Job')
        from autospec.agents.runner import _process_identity
        from types import SimpleNamespace
        return RetainedInterpreter(_process_identity(SimpleNamespace(_handle=handle)),api,handle)
    except BaseException:
        api.CloseHandle(handle)
        raise

def monitor_state(state):
    summary = {k:state.get(k) for k in ('phase','running','paused','error','budget_usd',
        'acceptance_result','delivery_ready','generation_checkpoint')}
    usage = state.get('usage') or {}
    summary.update({k:usage.get(k) for k in ('cost_usd','unreported_calls','agent_calls')})
    return summary

def runtime_directory(env,campaign):
    runtime = Path(env.get('AUTOSPEC_CAMPAIGN_RUNTIME_DIR',str(campaign)))
    if runtime != campaign:
        if (runtime.parent != campaign/'recovery-runtime' or not re.fullmatch('[0-9a-f]{32}',runtime.name)):
            raise AdmissionError('exact owned recovery runtime directory required')
        _regular(campaign/'recovery-runtime')
        _regular(runtime)
        attempt = _json((campaign/'recovery-attempt.json').read_bytes())
        if attempt.get('runtime_dir') != str(runtime) or attempt.get('project_id') != RECOVERY_PROJECT:
            raise AdmissionError('runtime not bound to exclusive recovery intent')
    return runtime

def supervise(root,campaign,port,env,receipt,*,runtime_dir=None,recovery=None):
    if os.name != 'nt':
        raise AdmissionError('owned Windows Jobs required')
    env = dict(env,AUTOSPEC_CAMPAIGN_COMMIT=receipt['factory_commit'])
    if runtime_dir is not None:
        env['AUTOSPEC_CAMPAIGN_RUNTIME_DIR'] = str(runtime_dir)
    runtime = runtime_directory(env,campaign)
    trusted_imports(root,env)
    from autospec.agents.runner import _WindowsJob, _process_identity
    job = _WindowsJob()
    proc,actual = None,None
    try:
        with (runtime/'factory.log').open('xb') as log:
            proc = subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--factory','--port',str(port)],
                cwd=root,env=env,stdout=log,stderr=log,
                creationflags=0x00000004|subprocess.CREATE_NO_WINDOW)  # CREATE_SUSPENDED
            job.assign_and_resume(proc)
            journal(campaign,'FACTORY_OWNED',pid=proc.pid,creation_identity=_process_identity(proc))
            url = f'http://127.0.0.1:{port}'
            deadline = time.monotonic()+60
            while True:
                if proc.poll() is not None:
                    raise AdmissionError('factory exited before creation')
                try:
                    health = http('GET',url+'/api/health')
                    identity_path = runtime/'factory-identity.json'
                    if identity_path.exists():
                        identity = json.loads(identity_path.read_text())
                        if (health.get('ok') and
                            health.get('started_at') == identity['started_at'] and
                            health.get('source_stamp') == identity['source_stamp'] == health.get('source_stamp_now')):
                            actual = job_member_identity(job,identity['pid'])
                            journal(campaign,'INTERPRETER_OWNED',pid=identity['pid'],creation_identity=actual)
                            break
                except OSError:
                    if actual is not None:
                        raise  # Do not swallow ownership/journal failures and leak retained handles.
                    pass
                if time.monotonic() >= deadline:
                    raise AdmissionError('readiness timeout; no POST')
                time.sleep(0.5)
            if isinstance(actual,RetainedInterpreter):
                actual.assert_alive()
            project = (recover_once(campaign,url,recovery) if recovery is not None else
                       create_once(campaign,url,payload(receipt,campaign)))
            seen,last = set(),None
            while proc.poll() is None:
                if isinstance(actual,RetainedInterpreter):
                    actual.assert_alive()
                stop = runtime/'stop-intent.json'
                if stop.exists():
                    _regular(stop)
                    if _json(stop.read_bytes()) != dict(action='stop',project_id=project):
                        raise AdmissionError('invalid owned stop intent')
                    journal(campaign,'STOP_INTENT_OBSERVED',project_id=project,runtime_dir=str(runtime))
                    return 0  # Exact retained Job/handles are drained by finally.
                state = http('GET',url+'/api/projects/'+project)
                summary = monitor_state(state)
                if summary != last:
                    journal(campaign,'STATE',state=summary)
                    print(json.dumps(summary),flush=True)
                    last = summary
                for path in (campaign/'projects').rglob('review-request.json'):
                    key = (str(path),digest(path.read_bytes()))
                    if key not in seen:
                        journal(campaign,'EXTERNAL_REVIEW_REQUIRED',path=key[0],sha256=key[1])
                        print('External review required: '+key[0],flush=True)
                        seen.add(key)
                # Retain ownership through blocking/completion until operator
                # interruption. No approval, retry, or product mutation.
                time.sleep(5)
            raise AdmissionError('owned factory exited')
    finally:
        # A suspended child may not have been assigned when assignment fails.
        # Its Popen process handle is still ours: terminate exactly that child,
        # never resolve/kill a PID, name or workspace path. Cleanup errors are
        # journaled without masking the original assignment/admission exception.
        errors = []
        try:
            job.close()
        except Exception as exc:
            errors.append(type(exc).__name__)
        try:
            if proc is not None:
                if proc.poll() is None:
                    try:
                        proc.terminate()
                    except OSError as exc:
                        errors.append(type(exc).__name__)
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=10)
        except Exception as exc:
            errors.append(type(exc).__name__)
        finally:
            if isinstance(actual,RetainedInterpreter):
                actual.close()
        if errors:
            journal(campaign,'OWNED_CLEANUP_ERROR',errors=errors)
        journal(campaign,'SUPERVISOR_STOPPED',product_mutated=False,
                metadata_recovery_attempted=recovery is not None,runtime_dir=str(runtime))

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    modes = p.add_mutually_exclusive_group(required=True)
    modes.add_argument('--preflight',action='store_true')
    modes.add_argument('--launch',action='store_true')
    modes.add_argument('--recover-bootstrap',action='store_true',help='one-shot recovery of the exact zero-call campaign')
    modes.add_argument('--factory',action='store_true',help=argparse.SUPPRESS)
    p.add_argument('--campaign')
    p.add_argument('--expected-commit')
    p.add_argument('--project-id')
    p.add_argument('--port',type=int,default=8130)
    a = p.parse_args(argv)
    if a.factory:
        return factory(ROOT,a.port)
    if not a.campaign or not a.expected_commit:
        p.error('--campaign and --expected-commit required')
    if a.recover_bootstrap and not a.project_id:
        p.error('--project-id required for bootstrap recovery')
    if a.project_id and not a.recover_bootstrap:
        p.error('--project-id is only valid for bootstrap recovery')
    campaign = WORKSPACE/a.campaign
    env = environment(os.environ,campaign,a.port)
    receipt = preflight(ROOT,campaign,a.port,a.expected_commit,env,**(
        {'recovery_project':a.project_id} if a.recover_bootstrap else {}))
    body = payload(receipt,campaign)
    safe = {k:v for k,v in receipt.items() if k != 'sources'}
    safe.update(configuration={k:env[k] for k in environment({},campaign,a.port)},
                payload_sha256=digest(canonical(body)),estimated_budget_usd=40,billing_cap=False)
    if a.preflight:
        print(json.dumps(safe,indent=2))
        return 0
    if a.recover_bootstrap:
        recovery = receipt['recovery']
        if recovery_snapshot(ROOT,campaign,a.project_id) != recovery:
            raise AdmissionError('recovery evidence changed since preflight')
        runtime = reserve_recovery(campaign,recovery,receipt)
        (runtime/'preflight.json').write_bytes(canonical(safe))
        return supervise(ROOT,campaign,a.port,env,receipt,runtime_dir=runtime,recovery=recovery)
    campaign.mkdir(exist_ok=False)
    (campaign/'projects').mkdir()
    (campaign/'inputs').mkdir()
    for name in receipt['sources']:
        (campaign/'inputs'/Path(name).name).write_bytes(receipt['sources'][name].encode('utf-8'))
    (campaign/'preflight.json').write_bytes(canonical(safe))
    (campaign/'input.json').write_bytes(canonical(body))
    journal(campaign,'ADMITTED',**safe)
    return supervise(ROOT,campaign,a.port,env,receipt)

if __name__ == '__main__':
    main()
