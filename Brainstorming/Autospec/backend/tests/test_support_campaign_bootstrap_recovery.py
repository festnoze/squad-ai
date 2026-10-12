"""Supervisor-only incident metatests: no real API, factory, CLI or provider."""
import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('support_recovery',ROOT/'tools/support_benchmark_campaign.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
SHA = 'a'*40


@pytest.fixture
def incident(tmp_path,monkeypatch):
    from autospec.contracts import ContractFact,ContractStore,import_contract
    from autospec.models import ProjectState
    campaign = tmp_path/c.RECOVERY_CAMPAIGN
    campaign.mkdir()
    project = campaign/'projects'/c.RECOVERY_PROJECT
    project.mkdir(parents=True)
    (campaign/'projects'/'.autospec-tmp').mkdir()
    (campaign/'inputs').mkdir()
    sources = {name:(ROOT/name).read_bytes().decode('utf-8') for name in c.HASHES}
    for name,text in sources.items():
        (campaign/'inputs'/Path(name).name).write_bytes(text.encode('utf-8'))
    body = c.payload({'sources':sources},campaign) | {'technical_stack':dict(c.LEGACY_STACK)}
    assert c.digest(c.canonical(body)) == c.RECOVERY_PAYLOAD_SHA256
    old = dict(factory_commit=c.RECOVERY_COMMIT,source_hashes=dict(c.HASHES),
               campaign=str(campaign),docker_os='linux',port=8130,estimated_budget_usd=40,billing_cap=False,
               auth=dict(loggedIn=True,authMethod='claude.ai',apiProvider='firstParty',subscriptionType='team'),
               configuration=c.environment({},campaign,8130),payload_sha256=c.RECOVERY_PAYLOAD_SHA256)
    (campaign/'input.json').write_bytes(c.canonical(body))
    (campaign/'preflight.json').write_bytes(c.canonical(old))
    (campaign/'creation-attempt.json').write_bytes(c.canonical(dict(payload_sha256=c.RECOVERY_PAYLOAD_SHA256,outcome='UNKNOWN')))
    c.journal(campaign,'ADMITTED',**old)
    c.journal(campaign,'CREATE_ATTEMPT',payload_sha256=c.RECOVERY_PAYLOAD_SHA256)
    c.journal(campaign,'CREATED',project_id=c.RECOVERY_PROJECT)
    monkeypatch.setattr(c,'RECOVERY_JOURNAL_SHA256',c.digest((campaign/'supervisor.jsonl').read_bytes()))
    facts = [ContractFact.create(f['id'],f['kind'],f['expected'],f['requirement_ids'],f['source_excerpt']) for f in body['acceptance_facts']]
    contract = import_contract(body['brief'],body['acceptance_reference'],reviewed_by=body['acceptance_reviewed_by'],facts=facts)
    assert contract.contract_hash == c.RECOVERY_CONTRACT
    oracle = ContractStore(campaign/'projects'/'.autospec-supervisor'/c.RECOVERY_PROJECT/'contracts',product_write_roots=[project]).save(contract)
    assert c.digest(oracle.read_bytes()) == c.RECOVERY_ORACLE_SHA256
    state = ProjectState(id=c.RECOVERY_PROJECT,name=campaign.name,goal=body['goal'],brief=body['brief'],
        product_profile='fullstack',auto_spec=True,budget_usd=40,acceptance_contract_hash=contract.contract_hash,
        acceptance_max_lots=7,technical_stack=dict(c.LEGACY_STACK),phase='needs_attention',bootstrap_status='failed',
        bootstrap_detail=c.RECOVERY_ERROR,delivery_issues=[c.RECOVERY_ERROR]).model_dump(mode='json')
    state_path = project/'autospec-state.json'
    state_path.write_bytes(c.canonical(state))
    # Explicit synthetic incident. Production constant remains the real pinned
    # state hash; these metatests never alter/read the actual campaign state.
    monkeypatch.setattr(c,'RECOVERY_STATE_SHA256',c.digest(state_path.read_bytes()))
    (project/'build-monitor.jsonl').write_bytes(b'bootstrap failed before provider\n')
    monkeypatch.setattr(c,'RECOVERY_MONITOR_SHA256',c.digest((project/'build-monitor.jsonl').read_bytes()))
    (campaign/'factory.log').write_bytes(b'first factory log bytes\n')
    (campaign/'factory-identity.json').write_bytes(c.canonical(dict(factory_commit=c.RECOVERY_COMMIT,pid=123,started_at=4,source_stamp='old')))
    return campaign,state,state_path


def snapshot(incident):
    return c.recovery_snapshot(ROOT,incident[0],c.RECOVERY_PROJECT)


def reserved(incident):
    recovery = snapshot(incident)
    runtime = c.reserve_recovery(incident[0],recovery,{'factory_commit':SHA})
    return recovery,runtime


def test_exact_incident_readonly_then_exclusive_intent_preserves_first_runtime(incident):
    campaign,state,path = incident
    original = {p:p.read_bytes() for p in campaign.iterdir() if p.is_file()}
    recovery,runtime = reserved(incident)
    assert runtime.parent == campaign/'recovery-runtime'
    assert c.runtime_directory({'AUTOSPEC_CAMPAIGN_RUNTIME_DIR':str(runtime)},campaign) == runtime
    assert all(p.read_bytes() == data for p,data in original.items() if p.name != 'supervisor.jsonl')
    assert (campaign/'supervisor.jsonl').read_bytes().startswith(original[campaign/'supervisor.jsonl'])
    assert json.loads((campaign/'recovery-attempt.json').read_bytes())['outcome'] == 'UNKNOWN'
    with pytest.raises(FileExistsError): c.reserve_recovery(campaign,recovery,{'factory_commit':SHA})
    with pytest.raises(c.AdmissionError,match='already attempted'): snapshot(incident)


@pytest.mark.parametrize('field,value',[('phase','stopped'),('bootstrap_status','ready'),('bootstrap_detail','other failure'),
    ('bootstrap_fingerprint','hash'),('bootstrap_verified_once',True),('stories',[{'id':'started'}]),
    ('budget_usd',0),('brief','changed'),('acceptance_contract_hash','b'*64),('running',True),('paused',True),
    ('agent_activity',{'dev':{'logical_call_active':True}}),('unknown_future_work','present')])
def test_changed_or_old_state_cannot_recover(incident,field,value):
    campaign,state,path = incident
    state[field] = value
    path.write_bytes(c.canonical(state))
    with pytest.raises(c.AdmissionError): snapshot(incident)
    assert not (campaign/'recovery-attempt.json').exists()


@pytest.mark.parametrize('field',['cost_usd','input_tokens','output_tokens','agent_calls','failed_calls','unreported_calls'])
@pytest.mark.parametrize('value',[1,True,'0'])
def test_nonzero_or_untyped_usage_refused(incident,field,value):
    campaign,state,path = incident
    state['usage'][field] = value
    path.write_bytes(c.canonical(state))
    with pytest.raises(c.AdmissionError): snapshot(incident)


@pytest.mark.parametrize('name',['main.py','.git/config','new-empty-dir','../other-product.txt'])
def test_additional_files_or_directories_refused(incident,name):
    campaign,state,path = incident
    extra = path.parent/name
    extra.parent.mkdir(parents=True,exist_ok=True)
    if name == 'new-empty-dir': extra.mkdir()
    else: extra.write_bytes(b'not an admissible pre-bootstrap incident')
    with pytest.raises(c.AdmissionError): snapshot(incident)


@pytest.mark.parametrize('relative',['input.json','preflight.json','creation-attempt.json','factory-identity.json',
    'inputs/01_specification.md',f'projects/.autospec-supervisor/{c.RECOVERY_PROJECT}/contracts/{c.RECOVERY_CONTRACT}.json'])
def test_historical_evidence_tamper_refused(incident,relative):
    campaign,*_ = incident
    path = campaign/relative
    path.write_bytes(path.read_bytes()+b'changed')
    with pytest.raises((c.AdmissionError,json.JSONDecodeError)): snapshot(incident)


@pytest.mark.parametrize('event',['CREATE_OUTCOME_UNKNOWN','CREATED','RECOVERY_OUTCOME_UNKNOWN'])
def test_unknown_or_duplicate_creation_refused(incident,event):
    c.journal(incident[0],event,project_id=c.RECOVERY_PROJECT)
    with pytest.raises(c.AdmissionError,match='journal'): snapshot(incident)


def test_wrong_project_and_campaign_refused(incident):
    with pytest.raises(c.AdmissionError): c.recovery_snapshot(ROOT,incident[0],'other-id')
    with pytest.raises(c.AdmissionError): c.recovery_snapshot(ROOT,incident[0].parent/'other-campaign',c.RECOVERY_PROJECT)


def test_recovery_requires_all_fresh_git_linux_team_model_guards(incident):
    campaign,*_ = incident
    env = c.environment({},campaign,8130)
    def run(args,**kw):
        if args[:2] == ['git','rev-parse']: return SHA
        if args[:2] == ['git','status']: return ''
        if args[0] == 'docker': return 'linux'
        if args[1:] == ['--help']: return '--model auth '+' '.join(c.CLI_FLAGS)
        return json.dumps(dict(loggedIn=True,authMethod='claude.ai',apiProvider='firstParty',subscriptionType='team'))
    kwargs = dict(root=ROOT,campaign=campaign,port=8130,expected_commit=SHA,env=env,
                  run=run,port_check=lambda p:None,workspace=campaign.parent,recovery_project=c.RECOVERY_PROJECT)
    assert c.preflight(**kwargs)['factory_commit'] == SHA
    for kind in ('dirty','docker','auth','model'):
        def bad(args,**kw):
            if kind == 'dirty' and args[:2] == ['git','status']: return ' M anything'
            if kind == 'docker' and args[0] == 'docker': return 'windows'
            if kind == 'auth' and args[1:] == ['auth','status','--json']: return '{}'
            return run(args,**kw)
        values = kwargs | {'run':bad}
        if kind == 'model': values['env'] = env | {'MODEL_BUILD':'opus'}
        with pytest.raises(c.AdmissionError): c.preflight(**values)
    assert not (campaign/'recovery-attempt.json').exists()


def api(incident,calls,*,tamper=None,ambiguous=False):
    campaign,state,path = incident
    def request(method,url,body=None):
        calls.append((method,url,body))
        assert not (method == 'POST' and url.endswith('/api/projects'))
        if method == 'GET': return copy.deepcopy(state)
        if method == 'PUT':
            assert url.endswith('/'+c.RECOVERY_PROJECT+'/language') and body == {'language':'python'}
            state['technical_stack'] = dict(backend='python',source='explicit')
            if tamper: tamper(state)
            path.write_bytes(c.canonical(state))
            return dict(ok=True,state=copy.deepcopy(state))
        assert method == 'POST' and url.endswith('/'+c.RECOVERY_PROJECT+'/resume-build')
        if ambiguous: raise TimeoutError('resume outcome unknown')
        return {'ok':True}
    return request


def test_metadata_then_once_resume_same_identity_and_budget(incident):
    recovery,runtime = reserved(incident)
    calls = []
    assert c.recover_once(incident[0],'http://127.0.0.1:8130',recovery,request=api(incident,calls)) == c.RECOVERY_PROJECT
    assert [row[0] for row in calls] == ['GET','PUT','GET','POST']
    assert incident[1]['budget_usd'] == 40 and incident[1]['usage'] == recovery['state']['usage']
    assert (incident[0]/'factory.log').read_bytes() == b'first factory log bytes\n'
    with pytest.raises(FileExistsError): c.recover_once(incident[0],'http://127.0.0.1:8130',recovery,request=api(incident,calls))
    assert len(calls) == 4


@pytest.mark.parametrize('field,value',[('id','other'),('brief','changed'),('budget_usd',80),
    ('acceptance_contract_hash','c'*64),('usage',{'cost_usd':1}),('stories',[{'id':'started'}])])
def test_metadata_invariant_tamper_blocks_resume(incident,field,value):
    recovery,_ = reserved(incident)
    calls = []
    request = api(incident,calls,tamper=lambda state:state.update({field:value}))
    with pytest.raises(c.AdmissionError): c.recover_once(incident[0],'http://127.0.0.1:8130',recovery,request=request)
    assert [row[0] for row in calls] == ['GET','PUT']
    assert 'RECOVERY_OUTCOME_UNKNOWN' in (incident[0]/'supervisor.jsonl').read_text()


def test_ambiguous_resume_never_retries(incident):
    recovery,_ = reserved(incident)
    calls = []
    request = api(incident,calls,ambiguous=True)
    with pytest.raises(TimeoutError): c.recover_once(incident[0],'http://127.0.0.1:8130',recovery,request=request)
    with pytest.raises(FileExistsError): c.recover_once(incident[0],'http://127.0.0.1:8130',recovery,request=request)
    assert [row[0] for row in calls] == ['GET','PUT','GET','POST']
    assert json.loads((incident[0]/'recovery-attempt.json').read_bytes())['outcome'] == 'UNKNOWN'


def test_recovery_requires_reserved_intent_before_any_http(incident):
    recovery = snapshot(incident)
    calls = []
    with pytest.raises(FileNotFoundError): c.recover_once(incident[0],'http://127.0.0.1:8130',recovery,request=api(incident,calls))
    assert not calls


def test_runtime_alias_and_forged_location_refused(incident):
    recovery,runtime = reserved(incident)
    with pytest.raises(c.AdmissionError): c.runtime_directory({'AUTOSPEC_CAMPAIGN_RUNTIME_DIR':str(runtime/'child')},incident[0])
    with pytest.raises((c.AdmissionError,FileNotFoundError)): c.runtime_directory({'AUTOSPEC_CAMPAIGN_RUNTIME_DIR':str(runtime.parent/('b'*32))},incident[0])


def test_main_recovery_does_not_create_or_reset_campaign(incident,monkeypatch):
    campaign,*_ = incident
    recovery = snapshot(incident)
    sources = {name:(ROOT/name).read_bytes().decode('utf-8') for name in c.HASHES}
    receipt = dict(factory_commit=SHA,sources=sources,recovery=recovery)
    monkeypatch.setattr(c,'WORKSPACE',campaign.parent)
    monkeypatch.setattr(c,'preflight',lambda *a,**k:receipt)
    calls = []
    monkeypatch.setattr(c,'supervise',lambda *a,**k:calls.append((a,k)))
    original = (campaign/'input.json').read_bytes()
    c.main(['--recover-bootstrap','--campaign',campaign.name,'--project-id',c.RECOVERY_PROJECT,'--expected-commit',SHA])
    assert len(calls) == 1 and calls[0][1]['recovery'] == recovery
    assert calls[0][1]['runtime_dir'] != campaign
    assert (campaign/'input.json').read_bytes() == original


@pytest.mark.parametrize('ambiguous',[False,True])
def test_owned_recovery_finally_and_stop_intent_no_real_process(incident,monkeypatch,ambiguous):
    from types import SimpleNamespace
    from autospec.agents import runner
    campaign,state,path = incident
    recovery,runtime = reserved(incident)
    env = c.environment({},campaign,8130)
    events,calls = [],[]
    class Function:
        def __init__(self,fn): self.fn = fn
        def __call__(self,*args): return self.fn(*args)
    def alive(handle,out):
        assert handle == 99
        out._obj.value = 259
        return True
    actual = c.RetainedInterpreter('retained-created-at',SimpleNamespace(
        GetExitCodeProcess=Function(alive),CloseHandle=Function(lambda h:events.append(('actual-closed',h)))),99)
    class Process:
        pid = 42
        def poll(self): return None
        def terminate(self): events.append('terminated')
        def wait(self,timeout): assert timeout == 10; events.append('wait')
    class Job:
        def assign_and_resume(self,p): events.append('assigned')
        def close(self): events.append('job-closed')
    def spawn(*args,**kwargs):
        assert kwargs['env']['AUTOSPEC_CAMPAIGN_RUNTIME_DIR'] == str(runtime)
        assert kwargs['env']['WORKSPACE_ROOT'] == str(campaign/'projects')
        assert kwargs['env']['GENERATION_ONLY_AGENTS'] == 'true'
        (runtime/'factory-identity.json').write_bytes(c.canonical(dict(pid=42,started_at=5,source_stamp='fresh',factory_commit=SHA)))
        return Process()
    request_api = api(incident,calls,ambiguous=ambiguous)
    def request(method,url,body=None):
        if url.endswith('/api/health'):
            return dict(ok=True,started_at=5,source_stamp='fresh',source_stamp_now='fresh')
        result = request_api(method,url,body)
        if method == 'POST':
            (runtime/'stop-intent.json').write_bytes(c.canonical(dict(action='stop',project_id=c.RECOVERY_PROJECT)))
        return result
    monkeypatch.setattr(c,'trusted_imports',lambda *a:None)
    monkeypatch.setattr(c.subprocess,'Popen',spawn)
    monkeypatch.setattr(runner,'_WindowsJob',Job)
    monkeypatch.setattr(runner,'_process_identity',lambda p:'redirector-created-at')
    monkeypatch.setattr(c,'job_member_identity',lambda job,pid:actual)
    monkeypatch.setattr(c,'http',request)
    if ambiguous:
        with pytest.raises(TimeoutError): c.supervise(ROOT,campaign,8130,env,{'factory_commit':SHA},runtime_dir=runtime,recovery=recovery)
    else:
        assert c.supervise(ROOT,campaign,8130,env,{'factory_commit':SHA},runtime_dir=runtime,recovery=recovery) == 0
    assert events == ['assigned','job-closed','terminated','wait',('actual-closed',99)]
    assert [row[0] for row in calls] == ['GET','PUT','GET','POST']
    assert (campaign/'factory.log').read_bytes() == b'first factory log bytes\n'
    assert (runtime/'factory.log').exists()
    log = (campaign/'supervisor.jsonl').read_text()
    assert 'SUPERVISOR_STOPPED' in log
    assert ('STOP_INTENT_OBSERVED' in log) is not ambiguous


@pytest.mark.parametrize('mode',['delayed','timeout','corrupt','api_drift','oracle_drift','new_file'])
def test_async_metadata_persistence_only_known_original_disk_may_lag(incident,monkeypatch,mode):
    campaign,state,path = incident
    recovery,_ = reserved(incident)
    calls = []
    old_bytes = path.read_bytes()
    clock = [0.0]
    monkeypatch.setattr(c.time,'monotonic',lambda:clock[0])
    def sleep(seconds):
        assert seconds == 0.05
        clock[0] += 1  # No real wait. A read-only atomic writer settles later.
        if clock[0] == 2 and mode == 'delayed': path.write_bytes(c.canonical(state))
        if clock[0] == 1 and mode == 'corrupt': path.write_bytes(b'{"unknown_partial_state":true}')
        if clock[0] == 1 and mode == 'api_drift': state['usage']['unreported_calls'] = 1
        if clock[0] == 1 and mode == 'oracle_drift':
            oracle = campaign/'projects'/'.autospec-supervisor'/c.RECOVERY_PROJECT/'contracts'/(c.RECOVERY_CONTRACT+'.json')
            oracle.write_bytes(oracle.read_bytes()+b'changed')
        if clock[0] == 1 and mode == 'new_file': (path.parent/'main.py').write_bytes(b'not allowed before resume')
    monkeypatch.setattr(c.time,'sleep',sleep)
    normal = api(incident,calls)
    def asynchronous(method,url,body=None):
        result = normal(method,url,body)
        if method == 'PUT': path.write_bytes(old_bytes)
        return result
    if mode == 'delayed':
        assert c.recover_once(campaign,'http://127.0.0.1:8130',recovery,request=asynchronous) == c.RECOVERY_PROJECT
        assert clock[0] == 2
        assert [row[0] for row in calls] == ['GET','PUT','GET','GET','GET','POST']
    else:
        with pytest.raises(c.AdmissionError): c.recover_once(campaign,'http://127.0.0.1:8130',recovery,request=asynchronous)
        assert not any(row[0] == 'POST' for row in calls)
        assert clock[0] <= 5
        with pytest.raises(FileExistsError): c.recover_once(campaign,'http://127.0.0.1:8130',recovery,request=asynchronous)
    assert sum(row[0] == 'PUT' for row in calls) == 1


def test_prior_agent_or_unknown_usage_build_monitor_refused(incident):
    campaign,state,path = incident
    monitor = path.parent/'build-monitor.jsonl'
    monitor.write_bytes(monitor.read_bytes()+b'{"kind":"agent","usage":null}\n')
    with pytest.raises(c.AdmissionError,match='build-monitor'): snapshot(incident)
    assert not (campaign/'recovery-attempt.json').exists()


@pytest.mark.parametrize('field,value',[('id','other'),('budget_usd',80),('acceptance_contract_hash','c'*64)])
def test_contradictory_put_receipt_blocks_even_when_get_and_disk_good(incident,field,value):
    campaign,*_ = incident
    recovery,_ = reserved(incident)
    calls = []
    normal = api(incident,calls)
    def contradictory(method,url,body=None):
        result = normal(method,url,body)
        if method == 'PUT': result['state'][field] = value
        return result
    with pytest.raises(c.AdmissionError): c.recover_once(campaign,'http://127.0.0.1:8130',recovery,request=contradictory)
    assert [row[0] for row in calls] == ['GET','PUT']
