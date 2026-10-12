"""Independent recovery counterexamples; author incident fixture is synthetic only."""
import copy
import importlib.util
import json
from pathlib import Path
import pytest

ROOT=Path('C:/Users/e.millerioux/.codex/worktrees/rem25-bootstrap-recovery/squad-ai/Brainstorming/Autospec')
spec=importlib.util.spec_from_file_location('author_recovery_fixture',ROOT/'backend/tests/test_support_campaign_bootstrap_recovery.py')
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
c=a.c

@pytest.fixture
def incident(tmp_path,monkeypatch):
    # Existing fixture constructs only a new owned temporary incident; no real
    # campaign read/write or provider/process call is performed by this setup.
    return a.incident.__wrapped__(tmp_path,monkeypatch)

def test_healthy_metadata_async_persist_gap_gets_bounded_readonly_wait(incident):
    recovery,runtime=a.reserved(incident)
    campaign,state,path=incident
    requests=[];put=[False];reads=[0]
    def request(method,url,body=None):
        requests.append(method)
        assert (campaign/'recovery-dispatch.json').exists()
        assert json.loads((campaign/'recovery-attempt.json').read_text())['outcome']=='UNKNOWN'
        if method=='PUT':
            put[0]=True;state['technical_stack']={'backend':'python','source':'explicit'}
            return {'ok':True,'state':copy.deepcopy(state)}
        if method=='GET':
            if put[0]:
                reads[0]+=1
                if reads[0]>=2:path.write_bytes(c.canonical(state))
            return copy.deepcopy(state)
        assert method=='POST' and url.endswith('/'+c.RECOVERY_PROJECT+'/resume-build')
        assert c.canonical(json.loads(path.read_bytes()))==c.canonical(state)
        return {'ok':True}
    assert c.recover_once(campaign,'http://127.0.0.1:8130',recovery,request=request)==c.RECOVERY_PROJECT
    assert requests.count('PUT')==requests.count('POST')==1
    assert reads[0]>=2

def test_provider_event_added_to_initial_monitor_is_not_zero_call_evidence(incident):
    campaign,state,path=incident
    monitor=path.parent/'build-monitor.jsonl'
    with monitor.open('ab') as out:
        out.write(b'{"kind":"agent","project":"'+c.RECOVERY_PROJECT.encode()+b'","role":"dev","ok":false,"error":"unknown usage"}\n')
    with pytest.raises(c.AdmissionError):a.snapshot(incident)

@pytest.mark.parametrize('field,value',[('id','different'),('budget_usd',80),('acceptance_contract_hash','f'*64)])
def test_put_response_contradiction_is_not_ignored_even_if_later_get_looks_original(incident,field,value):
    recovery,runtime=a.reserved(incident)
    campaign,state,path=incident
    requests=[]
    def request(method,url,body=None):
        requests.append(method)
        if method=='GET':return copy.deepcopy(state)
        if method=='PUT':
            state['technical_stack']={'backend':'python','source':'explicit'}
            path.write_bytes(c.canonical(state))
            conflicting=copy.deepcopy(state);conflicting[field]=value
            return {'ok':True,'state':conflicting}
        return {'ok':True}
    with pytest.raises(c.AdmissionError):c.recover_once(campaign,'http://127.0.0.1:8130',recovery,request=request)
    assert 'POST' not in requests

def test_exact_nominal_and_unknown_resume_remain_single_dispatch(incident):
    recovery,runtime=a.reserved(incident)
    requests=[]
    request=a.api(incident,requests,ambiguous=True)
    with pytest.raises(TimeoutError):c.recover_once(incident[0],'http://127.0.0.1:8130',recovery,request=request)
    with pytest.raises(FileExistsError):c.recover_once(incident[0],'http://127.0.0.1:8130',recovery,request=request)
    assert [method for method,_,_ in requests]==['GET','PUT','GET','POST']

def test_canonical_payload_composes_actual_resolver_without_provider(incident):
    from autospec.models import ProjectState,BackendLanguage
    from autospec.orchestrator.stack import resolve,freeze
    sources={name:(ROOT/name).read_bytes().decode('utf-8') for name in c.HASHES}
    body=c.payload({'sources':sources},incident[0])
    state=ProjectState(id='independent',name='Independent',goal=body['goal'],brief=body['brief'],
        product_profile=body['product_profile'],technical_stack=body['technical_stack'])
    assert BackendLanguage(state.technical_stack['backend']) is BackendLanguage.PYTHON
    decision=freeze(resolve(state))
    assert {k:decision[k] for k in ('backend','framework','frontend','database','kind')}=={
        'backend':'python','framework':'fastapi','frontend':'react','database':'sqlite','kind':'fullstack'}

def startup(incident):
    root=incident[0]/'projects'/'.autospec-supervisor'/c.RECOVERY_PROJECT/'publication'
    (root/'empty-runtime-stage').mkdir(parents=True)
    (root/(c.RECOVERY_PROJECT+'.lock')).write_bytes(b'0')
    return root

def test_startup_bookkeeping_is_not_admitted_as_initial_incident(incident):
    startup(incident)
    with pytest.raises(c.AdmissionError):a.snapshot(incident)
    assert not (incident[0]/'recovery-attempt.json').exists()

def test_exact_startup_pair_permits_only_same_project_single_resume(incident):
    recovery,runtime=a.reserved(incident)
    root=startup(incident)
    calls=[]
    assert c.verify_recovery_invariants(incident[0],recovery,incident[1],after_startup=True)
    with pytest.raises(c.AdmissionError):c.verify_recovery_invariants(incident[0],recovery,incident[1])
    assert c.recover_once(incident[0],'http://127.0.0.1:8130',recovery,request=a.api(incident,calls))==c.RECOVERY_PROJECT
    assert [m for m,_,_ in calls]==['GET','PUT','GET','POST']
    assert (root/(c.RECOVERY_PROJECT+'.lock')).read_bytes()==b'0'
    assert not list((root/'empty-runtime-stage').iterdir())

@pytest.mark.parametrize('bad',['lock_bytes','foreign_lock','publication_journal','empty_stage_child','stage_product','extra_directory','hardlink'])
def test_startup_exception_cannot_hide_unknown_evidence_or_product(incident,bad):
    recovery,runtime=a.reserved(incident)
    root=startup(incident);lock=root/(c.RECOVERY_PROJECT+'.lock')
    if bad=='lock_bytes':lock.write_bytes(b'0\n')
    elif bad=='foreign_lock':(root/'foreign.lock').write_bytes(b'0')
    elif bad=='publication_journal':(root/(c.RECOVERY_PROJECT+'.json')).write_bytes(b'{"registered":true}')
    elif bad=='empty_stage_child':(root/'empty-runtime-stage'/'empty').mkdir()
    elif bad=='stage_product':(root/'empty-runtime-stage'/'product.py').write_bytes(b'not allowed')
    elif bad=='extra_directory':(root/'unknown').mkdir()
    else:
        import os
        os.link(lock,incident[0]/'hardlink-bookkeeping')
    calls=[]
    with pytest.raises(c.AdmissionError):c.recover_once(incident[0],'http://127.0.0.1:8130',recovery,request=a.api(incident,calls))
    assert [m for m,_,_ in calls]==['GET']
    assert json.loads((incident[0]/'recovery-attempt.json').read_bytes())['outcome']=='UNKNOWN'
