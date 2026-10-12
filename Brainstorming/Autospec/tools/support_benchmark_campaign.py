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
import subprocess
import sys
import time
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

class AdmissionError(RuntimeError):
    pass

def digest(data):
    return hashlib.sha256(data).hexdigest()

def canonical(data):
    return json.dumps(data,sort_keys=True,ensure_ascii=False).encode('utf-8')

def environment(base,campaign,port):
    env = {k:v for k,v in base.items() if not (k.endswith('API_KEY') or
        k.startswith(('ANTHROPIC_','OPENAI_','LANGFUSE_','MODEL_')) or
        k in ('CLAUDE_CODE_OAUTH_TOKEN','PYTHONPATH','PYTHONHOME','_FORCE_MODEL'))}
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

def preflight(root,campaign,port,expected_commit,env,*,run=command,port_check=check_port,workspace=WORKSPACE):
    validate_environment(env,campaign,port)
    if not re.fullmatch('[0-9a-f]{40}',expected_commit):
        raise AdmissionError('qualified full commit SHA required')
    if campaign.parent.resolve() != workspace.resolve() or not re.fullmatch(
        'relais-support-rem25-[a-z0-9][a-z0-9-]{0,63}',campaign.name):
        raise AdmissionError('precisely named new campaign under workspace required')
    if campaign.exists():
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
    return dict(factory_commit=head,source_hashes=dict(HASHES),auth=auth,
        checked_at=datetime.now(timezone.utc).isoformat(),docker_os=docker,
        port=port,campaign=str(campaign),sources=sources)

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
        acceptance_max_lots=7,technical_stack={'backend':'Python/FastAPI','database':'SQLite','frontend':'React/TypeScript/Vite'})

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
    with (Path(env['WORKSPACE_ROOT']).parent/'factory-identity.json').open('xb') as f:
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
        return _process_identity(SimpleNamespace(_handle=handle))
    finally:
        api.CloseHandle(handle)

def supervise(root,campaign,port,env,receipt):
    if os.name != 'nt':
        raise AdmissionError('owned Windows Jobs required')
    env = dict(env,AUTOSPEC_CAMPAIGN_COMMIT=receipt['factory_commit'])
    trusted_imports(root,env)
    from autospec.agents.runner import _WindowsJob, _process_identity
    job = _WindowsJob()
    proc = None
    try:
        with (campaign/'factory.log').open('xb') as log:
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
                    identity_path = campaign/'factory-identity.json'
                    if identity_path.exists():
                        identity = json.loads(identity_path.read_text())
                        if (health.get('ok') and
                            health.get('started_at') == identity['started_at'] and
                            health.get('source_stamp') == identity['source_stamp'] == health.get('source_stamp_now')):
                            actual = job_member_identity(job,identity['pid'])
                            journal(campaign,'INTERPRETER_OWNED',pid=identity['pid'],creation_identity=actual)
                            break
                except OSError:
                    pass
                if time.monotonic() >= deadline:
                    raise AdmissionError('readiness timeout; no POST')
                time.sleep(0.5)
            project = create_once(campaign,url,payload(receipt,campaign))
            seen,last = set(),None
            while proc.poll() is None:
                state = http('GET',url+'/api/projects/'+project)
                summary = {k:state.get(k) for k in ('phase','status','budget_usd','cost_usd','acceptance_verdict')}
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
        job.close()  # Only owned tree, never global/path-based stop.
        if proc is not None:
            proc.wait(timeout=30)
        journal(campaign,'SUPERVISOR_STOPPED',product_mutated=False)

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    modes = p.add_mutually_exclusive_group(required=True)
    modes.add_argument('--preflight',action='store_true')
    modes.add_argument('--launch',action='store_true')
    modes.add_argument('--factory',action='store_true',help=argparse.SUPPRESS)
    p.add_argument('--campaign')
    p.add_argument('--expected-commit')
    p.add_argument('--port',type=int,default=8130)
    a = p.parse_args(argv)
    if a.factory:
        return factory(ROOT,a.port)
    if not a.campaign or not a.expected_commit:
        p.error('--campaign and --expected-commit required')
    campaign = WORKSPACE/a.campaign
    env = environment(os.environ,campaign,a.port)
    receipt = preflight(ROOT,campaign,a.port,a.expected_commit,env)
    body = payload(receipt,campaign)
    safe = {k:v for k,v in receipt.items() if k != 'sources'}
    safe.update(configuration={k:env[k] for k in environment({},campaign,a.port)},
                payload_sha256=digest(canonical(body)),estimated_budget_usd=40,billing_cap=False)
    if a.preflight:
        print(json.dumps(safe,indent=2))
        return 0
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
