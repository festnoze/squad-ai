"""Offline supervisor counter-tests: no Docker/Claude subprocess or inference."""
import importlib.util
import json
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('support_campaign', ROOT/'tools/support_benchmark_campaign.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
SHA = 'a'*40

@pytest.fixture
def setup(tmp_path):
    campaign = tmp_path/'relais-support-rem25-offline'
    env = c.environment({'ANTHROPIC_API_KEY':'secret','MODEL_BUILD':'opus','LANGFUSE_SECRET_KEY':'secret'},campaign,8130)
    calls = []
    def run(args,**kwargs):
        calls.append(args)
        if args[:2] == ['git','rev-parse']: return SHA
        if args[:2] == ['git','status']: return ''
        if args[0] == 'docker': return 'linux'
        if args[1:] == ['--help']: return '--model auth '+' '.join(c.CLI_FLAGS)
        if args[1:] == ['auth','status','--json']:
            return json.dumps(dict(loggedIn=True,authMethod='claude.ai',apiProvider='firstParty',subscriptionType='team',email='never-store'))
        raise AssertionError(args)
    def check(**overrides):
        values = dict(root=ROOT,campaign=campaign,port=8130,expected_commit=SHA,
                      env=env,run=run,port_check=lambda p: None,workspace=tmp_path)
        values.update(overrides)
        return c.preflight(**values)
    return campaign,env,calls,run,check

def test_preflight_nominal_is_read_only(setup):
    campaign,env,calls,run,check = setup
    receipt = check()
    assert not campaign.exists()
    assert list(receipt['auth']) == list(c.AUTH_KEYS)
    assert 'never-store' not in json.dumps(receipt)
    assert calls[-1] == ['claude','auth','status','--json']
    assert len(calls) == 5
    assert 'ANTHROPIC_API_KEY' not in env
    assert all(env[k] == 'false' for k in c.OFF)
    assert all(env[k] == 'sonnet' for k in c.MODELS)

@pytest.mark.parametrize('key,value',[('AGENT_PROVIDER','anthropic'),('CLAUDE_MODEL','opus'),
 ('MODEL_CHECKER','haiku'),('GENERATION_ONLY_AGENTS','false'),('FAKE_AGENTS','true'),
 ('REFINE','true'),('ROLE_ROUTING','true'),('LANGFUSE','true'),('CONCURRENT_BUDGET_RESERVATIONS','true'),
 ('SANDBOX','false'),('ANTHROPIC_API_KEY','secret')])
def test_config_tamper_refused_before_probe(setup,key,value):
    campaign,env,calls,run,check = setup
    env[key] = value
    with pytest.raises(c.AdmissionError): check()
    assert not calls

@pytest.mark.parametrize('port',[18004,8126,0,65536])
def test_forbidden_port(setup,port):
    campaign,env,calls,run,check = setup
    with pytest.raises(c.AdmissionError): check(port=port,env=c.environment({},campaign,port))
    assert all(args[0] == 'git' for args in calls)

def test_old_campaign_refused(setup):
    campaign,env,calls,run,check = setup
    campaign.mkdir()
    (campaign/'old-cost-ledger').write_text('preserve')
    with pytest.raises(c.AdmissionError): check()
    assert not calls
    assert (campaign/'old-cost-ledger').read_text() == 'preserve'

@pytest.mark.parametrize('kind',['commit','dirty','docker','auth','help'])
def test_admission_failure(setup,kind):
    campaign,env,calls,run,check = setup
    def altered(args,**kwargs):
        if kind == 'commit' and args[:2] == ['git','rev-parse']: return 'b'*40
        if kind == 'dirty' and args[:2] == ['git','status']: return ' M backend/autospec/config.py'
        if kind == 'docker' and args[0] == 'docker': return 'windows'
        if kind == 'auth' and args[1:] == ['auth','status','--json']:
            return json.dumps(dict(loggedIn=True,authMethod='api-key',apiProvider='firstParty',subscriptionType='team'))
        if kind == 'help' and args[1:] == ['--help']: return 'unsupported'
        return run(args,**kwargs)
    with pytest.raises(c.AdmissionError): check(run=altered)
    assert not campaign.exists()

@pytest.mark.parametrize('source',list(c.HASHES))
def test_hash_tamper(setup,tmp_path,source):
    campaign,env,calls,run,check = setup
    root = tmp_path/'copy'
    for name in c.HASHES:
        target = root/name
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes((ROOT/name).read_bytes()+ (b'changed' if name == source else b''))
    with pytest.raises(c.AdmissionError,match='hash mismatch'): check(root=root)

def test_complete_payload(setup):
    campaign,env,calls,run,check = setup
    body = c.payload(check(),campaign)
    assert body['budget_usd'] == 40
    assert body['acceptance_max_lots'] == 7
    assert len(body['acceptance_facts'][0]['requirement_ids']) == 57
    assert body['brief'] == (ROOT/list(c.HASHES)[0]).read_bytes().decode('utf-8')
    assert body['acceptance_reference'] == (ROOT/list(c.HASHES)[1]).read_bytes().decode('utf-8')
    assert body['technical_stack'] == dict(backend='Python/FastAPI',database='SQLite',frontend='React/TypeScript/Vite')

def test_creation_exactly_once_and_unknown_never_retries(tmp_path):
    calls = []
    def timeout(method,url,body):
        calls.append(method)
        raise TimeoutError('unknown result')
    with pytest.raises(TimeoutError): c.create_once(tmp_path,'http://127.0.0.1:8130',{},request=timeout)
    with pytest.raises(FileExistsError): c.create_once(tmp_path,'http://127.0.0.1:8130',{},request=timeout)
    assert calls == ['POST']
    assert json.loads((tmp_path/'creation-attempt.json').read_text())['outcome'] == 'UNKNOWN'
    assert 'CREATE_OUTCOME_UNKNOWN' in (tmp_path/'supervisor.jsonl').read_text()

def test_nominal_creation_inert(tmp_path):
    calls = []
    def request(*args):
        calls.append(args)
        return {'id':'relais-support-offline-123'}
    assert c.create_once(tmp_path,'http://127.0.0.1:8130',{'budget_usd':40},request=request).endswith('123')
    assert len(calls) == 1
    assert calls[0][0] == 'POST'

@pytest.mark.parametrize('mode',['--preflight','--launch'])
def test_main_modes_offline(setup,monkeypatch,mode):
    campaign,env,calls,run,check = setup
    receipt = check()
    monkeypatch.setattr(c,'WORKSPACE',campaign.parent)
    monkeypatch.setattr(c,'preflight',lambda *a,**k: receipt)
    launched = []
    monkeypatch.setattr(c,'supervise',lambda *a: launched.append(a))
    c.main([mode,'--campaign',campaign.name,'--expected-commit',SHA])
    if mode == '--preflight':
        assert not launched and not campaign.exists()
    else:
        assert len(launched) == 1
        assert (campaign/'input.json').exists()
        assert (campaign/'preflight.json').exists()
        assert not (campaign/'creation-attempt.json').exists()  # mocked supervisor

@pytest.mark.parametrize('wrong_identity',[False,True])
def test_supervisor_owned_job_and_readiness_offline(setup,monkeypatch,wrong_identity):
    from autospec.agents import runner
    campaign,env,calls,run,check = setup
    receipt = check()
    campaign.mkdir()
    reviews = campaign/'projects'/'p'/'source-reviews'/'snapshot'
    reviews.mkdir(parents=True)
    (reviews/'review-request.json').write_text('{"phase":"vertical"}')
    identity = dict(pid=42,started_at=123,source_stamp='sha')
    (campaign/'factory-identity.json').write_text(json.dumps(identity))
    events = []
    class Process:
        pid = 42
        def poll(self): return None
        def wait(self,timeout): events.append('wait')
    class Job:
        def assign_and_resume(self,p): events.append('assigned')
        def close(self): events.append('closed')
    monkeypatch.setattr(runner,'_WindowsJob',Job)
    monkeypatch.setattr(runner,'_process_identity',lambda p: 'owned-handle')
    monkeypatch.setattr(c,'trusted_imports',lambda *a: None)
    monkeypatch.setattr(c,'job_member_identity',lambda job,pid: 'owned-interpreter')
    spawned = []
    def spawn(*a,**kw):
        spawned.append(kw)
        assert kw['env']['GENERATION_ONLY_AGENTS'] == 'true'
        assert kw['env']['AUTOSPEC_CAMPAIGN_COMMIT'] == SHA
        return Process()
    monkeypatch.setattr(c.subprocess,'Popen',spawn)
    ticks = iter([0,100])
    monkeypatch.setattr(c.time,'monotonic',lambda: next(ticks))
    requests = []
    def request(method,url,body=None):
        requests.append((method,url))
        if url.endswith('/api/health'):
            return dict(ok=True,started_at=999 if wrong_identity else 123,
                        source_stamp='sha',source_stamp_now='sha')
        if method == 'POST': return {'id':'p'}
        return {'phase':'build','cost_usd':0,'budget_usd':40}
    monkeypatch.setattr(c,'http',request)
    # create_once binds its default at import; inject inert request explicitly.
    original_create = c.create_once
    monkeypatch.setattr(c,'create_once',lambda *a: original_create(*a,request=request))
    monkeypatch.setattr(c.time,'sleep',lambda s: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(c.AdmissionError if wrong_identity else KeyboardInterrupt):
        c.supervise(ROOT,campaign,8130,env,receipt)
    assert events == ['assigned','closed','wait']
    assert len(spawned) == 1
    assert sum(m == 'POST' for m,u in requests) == (0 if wrong_identity else 1)
    log = (campaign/'supervisor.jsonl').read_text()
    assert 'SUPERVISOR_STOPPED' in log
    if not wrong_identity: assert 'EXTERNAL_REVIEW_REQUIRED' in log

def test_effective_settings_and_profile_offline(setup,monkeypatch):
    from autospec.config import Settings
    from autospec.orchestrator.profiles import PROFILES
    campaign,env,*_ = setup
    for key,value in env.items(): monkeypatch.setenv(key,value)
    settings = Settings()
    c.validate_settings(settings,PROFILES['fullstack'].overrides,campaign/'projects')
    settings.retro_enabled = True
    with pytest.raises(c.AdmissionError,match='retro'): c.validate_settings(settings,{},campaign/'projects')
    settings.retro_enabled = False
    with pytest.raises(c.AdmissionError,match='refine'): c.validate_settings(settings,{'refine_enabled':True},campaign/'projects')

@pytest.mark.parametrize('flag',c.CLI_FLAGS)
def test_mandatory_cli_flag_missing_refused(setup,flag):
    campaign,env,calls,run,check = setup
    def missing(args,**kwargs):
        if args[1:] == ['--help']: return '--model auth '+' '.join(f for f in c.CLI_FLAGS if f != flag)
        return run(args,**kwargs)
    with pytest.raises(c.AdmissionError,match='interface'): check(run=missing)

@pytest.mark.parametrize('member',[True,False])
def test_interpreter_exact_job_membership_no_real_os_call(monkeypatch,member):
    import ctypes
    from types import SimpleNamespace
    from autospec.agents import runner
    calls = []
    class Function:
        def __init__(self,fn): self.fn = fn
        def __call__(self,*args): return self.fn(*args)
    def is_member(handle,job,out):
        assert (handle,job) == (99,77)
        out._obj.value = member
        return True
    api = SimpleNamespace(OpenProcess=Function(lambda *a:99),
        IsProcessInJob=Function(is_member),CloseHandle=Function(lambda h:calls.append(h)))
    monkeypatch.setattr(ctypes,'WinDLL',lambda *a,**k:api)
    monkeypatch.setattr(runner,'_process_identity',lambda p:'actual-process-created-at')
    if member: assert c.job_member_identity(SimpleNamespace(handle=77),123) == 'actual-process-created-at'
    else:
        with pytest.raises(c.AdmissionError,match='not in owned'): c.job_member_identity(SimpleNamespace(handle=77),123)
    assert calls == [99]
