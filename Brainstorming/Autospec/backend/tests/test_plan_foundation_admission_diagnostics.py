"""Real factory scaffold and plan gate; maker/native execution are fictional.

No generated app import, paid provider, API, live campaign or Docker call.
"""
import copy
import asyncio
import hashlib
import json
from pathlib import Path

import pytest

from autospec.agents import prompts
from autospec.agents.runner import FakeRunner
from autospec.config import settings
from autospec.contracts import ContractError, ContractFact, import_contract
from autospec.models import ProjectState, Stream, StreamKind, Task, UserStory, StoryStatus, PipelinePhase
from autospec.orchestrator import acceptance, bootstrap, plan_gates, stack, workspace
from autospec.orchestrator.pipeline import Pipeline, DeliveryBlocked
from autospec.orchestrator.build_monitor import BuildMonitor
from autospec.orchestrator.events import bus
from autospec.storage import load_state, workspace_dir

ROOT = Path(__file__).resolve().parents[2]


def receipt_for(state):
    digest = state.plan_admission_public['receipt_sha256']
    path = acceptance.supervisor_root(state.id)/'plans/rejected'/f'{digest}.json'
    assert path.is_file()
    return path, json.loads(path.read_bytes())


@pytest.fixture
def foundation(monkeypatch):
    facts = json.loads((ROOT/'artifacts/remediation/REM-25/source-facts-v02.json').read_bytes())['acceptance_facts']
    brief = (ROOT/'docs/validation/support-client/01_specification.md').read_bytes().decode('utf-8')
    reference = (ROOT/'docs/validation/support-client/02_requirements_verification.md').read_bytes().decode('utf-8')
    contract = import_contract(brief,reference,reviewed_by='parent-source-only-review-2026-10-12',facts=[
        ContractFact.create(f['id'],f['kind'],f['expected'],f['requirement_ids'],f['source_excerpt']) for f in facts])
    state = ProjectState(id='plan-foundation',name='relais-support-rem25-20261012-final',goal='Support',brief=brief,
        product_profile='fullstack',acceptance_contract_hash=contract.contract_hash,iteration=1,
        technical_stack=stack.freeze(dict(backend='python',framework='fastapi',frontend='react',database='sqlite',kind='fullstack',source='explicit')),
        streams=[Stream(id='backend',kind=StreamKind.BACKEND,language='python',primary=True),
                 Stream(id='frontend',kind=StreamKind.FRONTEND,language='react',file_root='frontend')])
    acceptance.contract_store(state.id).save(contract)
    ws = workspace.scaffold(state,streams_enabled=True,ui_tests_enabled=False)
    # Use the real deterministic manifest interface. Native runtime
    # qualification remains a separate parent-owned probe.
    prepared = bootstrap.prepare(state, ws)
    assert prepared.ok
    state.bootstrap_status='ready';state.bootstrap_fingerprint=prepared.fingerprint
    monkeypatch.setattr(settings,'generation_only_agents',True)
    return state,contract,ws


@pytest.mark.parametrize('damage', ['missing_file', 'non_regular_file', 'changed_fingerprint',
                                    'changed_file_set', 'invalid_manifest', 'state_fingerprint'])
def test_plan_policy_revalidates_physical_foundation_before_admission(foundation,damage):
    state,contract,ws=foundation
    manifest_path=ws/bootstrap.MANIFEST
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    if damage == 'missing_file':
        (ws/'main.py').unlink()
    elif damage == 'non_regular_file':
        (ws/'main.py').unlink()
        (ws/'main.py').mkdir()
    elif damage == 'changed_fingerprint':
        manifest['fingerprint']='b'*64
        manifest_path.write_text(json.dumps(manifest),encoding='utf-8')
    elif damage == 'changed_file_set':
        manifest['files'].remove('main.py')
        manifest_path.write_text(json.dumps(manifest),encoding='utf-8')
    elif damage == 'invalid_manifest':
        manifest_path.write_text('{invalid json',encoding='utf-8')
    else:
        state.bootstrap_fingerprint='b'*64

    with pytest.raises(ContractError,match='Socle PLAN'):
        acceptance.plan_policy(state,contract)


def test_plan_policy_allows_legitimate_bootstrap_file_content_edit(foundation):
    state,contract,ws=foundation
    project_config=ws/'pyproject.toml'
    project_config.write_text(project_config.read_text(encoding='utf-8')+'\n# legitimate product edit\n',encoding='utf-8')
    assert acceptance.plan_policy(state,contract).max_lots == 7


async def test_missing_foundation_file_refuses_plan_before_provider(foundation):
    state,contract,ws=foundation
    (ws/'main.py').unlink()
    runner=FakeRunner([])
    pipeline=Pipeline(state,runner)
    with pytest.raises(ContractError,match='Socle PLAN'):
        await pipeline._aplan_phase()
    assert not runner.calls and not state.stories


def candidate(foundation):
    state,contract,ws = foundation
    pkg = workspace.package_name(state)
    checks = acceptance.plan_policy(state,contract).required_vertical_checks
    tasks = [dict(id='F',title='First backend behavior',stream='backend',file_globs=[pkg+'/features/first.py'],requirement_ids=[r.id for r in contract.requirements]),
             dict(id='UI',title='First UI wiring',stream='frontend',file_globs=['frontend/src/App.tsx'],depends_on=['F']),
             dict(id='V',title='Real vertical evidence',stream='frontend',file_globs=['frontend/src/vertical.test.tsx'],depends_on=['F','UI']),
             dict(id='R',title='Later features',stream='backend',file_globs=[pkg+'/features/rest.py'],depends_on=['V'])]
    mapping = {check:'UI' if check == 'frontend_wiring' else 'V' if check.startswith('browser_') or check == 'restart' else 'F' for check in checks}
    return dict(epics=[dict(id='E',title='Support',stories=[dict(id='S',title='First slice',tasks=tasks)])],
        lot_definition='explicit_groups',lots=[dict(id='L',members=['S'])],
        milestones=dict(foundation=['F','UI'],vertical='V',vertical_contract=mapping),
        contract_facts={f.id:f.expected for f in contract.facts},technical_stack=dict(state.technical_stack))


def test_prompts_use_actual_root_package_and_stage_contract(foundation):
    state,contract,ws = foundation
    pkg = workspace.package_name(state)
    assert (ws/pkg/'features').is_dir() and not (ws/'backend').exists()
    assert (ws/'frontend/src/App.tsx').is_file()
    context = prompts.plan_workspace_context(state,pkg)
    assert context['python_package_root'] == pkg
    assert context['stream_roots']['backend'] == '' and context['stream_roots']['frontend'] == 'frontend'
    for prompt in (prompts.po_plan(state,pkg),prompts.po_revise(state,pkg,'{}','constraint errors'),prompts.po_structure(state,pkg)):
        assert 'RACINES CANONIQUES' in prompt and json.dumps(pkg) in prompt
        assert 'AVANT' in prompt or 'avant' in prompt
    policy = acceptance.plan_policy(state,contract)
    assert policy.required_vertical_checks == ('schema','bootstrap','argon2','browser_login','browser_create','api_read','db_committed','restart','frontend_wiring')
    assert 'vertical_contract' in plan_gates.plan_contract_prompt(contract,policy,planning_context=context)


@pytest.mark.parametrize('frontend',['react','vue','angular','svelte'])
def test_vertical_frontend_wiring_applies_to_any_declared_frontend(foundation,frontend):
    state,contract,_=foundation
    selected=dict(state.technical_stack)
    selected['frontend']=frontend
    assert 'frontend_wiring' in plan_gates.vertical_contract_checks(contract,selected)


async def test_wrong_backend_fragment_preserved_before_rejection_no_extra_role(foundation):
    state,contract,ws = foundation
    plan = candidate(foundation)
    for task in plan['epics'][0]['stories'][0]['tasks']:
        if task.get('stream') == 'backend': task['file_globs']=['backend/'+glob for glob in task['file_globs']]
    text = json.dumps(plan,ensure_ascii=False,indent=2)+' '*17000
    runner = FakeRunner([text])
    pipeline = Pipeline(state,runner)
    with pytest.raises(DeliveryBlocked): await pipeline._aplan_phase()
    assert len(runner.calls) == 1 and not state.stories
    assert state.plan_admission_public['status'] == 'fail'
    path, record = receipt_for(state)
    assert any('backend' in error for error in record['admission']['errors'])
    assert not state.plan_findings and state.plan_quality == -1
    assert not path.is_relative_to(ws)
    assert record['response'] == text and record['capture_complete']
    assert record['response_sha256'] == hashlib.sha256(text.encode('utf-8')).hexdigest()
    assert hashlib.sha256(path.read_bytes()).hexdigest() == state.plan_admission_public['receipt_sha256']
    assert record['planning_context']['python_package_root'] == workspace.package_name(state)


@pytest.mark.parametrize('text',['not JSON','{"epics": [',json.dumps({'epics':None})])
async def test_invalid_json_or_shape_has_durable_exact_reason(foundation,text):
    state,contract,ws = foundation
    pipeline = Pipeline(state,FakeRunner([text]))
    with pytest.raises(DeliveryBlocked): await pipeline._aplan_phase()
    _, record = receipt_for(state)
    assert record['response'] == text and record['admission']['errors']
    assert not state.plan_review_issues and not state.stories


@pytest.mark.parametrize('problem',['missing_check','auth_only','late_wiring','wrong_owner','wrong_type'])
async def test_incomplete_first_slice_is_rejected_without_admitting_later_work(foundation,problem):
    state,contract,ws = foundation
    plan = candidate(foundation)
    mapping = plan['milestones']['vertical_contract']
    if problem == 'missing_check': del mapping['restart']
    elif problem == 'auth_only': plan['milestones']['vertical_contract']={'browser_login':'F'}
    elif problem == 'late_wiring': mapping['frontend_wiring']='R'
    elif problem == 'wrong_owner': mapping['db_committed']='unknown'
    else: mapping['api_read']=True
    pipeline = Pipeline(state,FakeRunner([json.dumps(plan)]))
    with pytest.raises(DeliveryBlocked): await pipeline._aplan_phase()
    _, record = receipt_for(state)
    assert any('vertical_contract' in error for error in record['admission']['errors'])
    assert not state.stories


async def test_valid_plan_remaps_all_vertical_owners_and_clears_only_machine_issues(foundation):
    state,contract,ws = foundation
    state.stories=[UserStory(id='S',epic_id='old',title='Old',iteration=0,status=StoryStatus.DONE,
                            tasks=[Task(id='F',story_id='S',status=StoryStatus.DONE)])]
    pipeline = Pipeline(state,FakeRunner([json.dumps(candidate(foundation))]))
    rejected = plan_gates.PlanAdmission('fail',contract.contract_hash,('previous constraint',))
    state.plan_review_issues=['independent critic opinion']
    pipeline._record_contract_plan_admission('old rejected',rejected,{'attempt':'old'})
    await pipeline._aplan_phase()
    assert state.plan_admission_public['status'] == 'pass'
    assert state.plan_review_issues == ['independent critic opinion']
    assert not state.plan_findings
    owners = state.plan_structure['milestones']['vertical_contract']
    assert set(owners) == set(acceptance.plan_policy(state,contract).required_vertical_checks)
    assert owners['schema'] != 'F'
    assert owners['schema'] in state.plan_structure['milestones']['foundation']


def test_same_text_different_admission_context_keeps_both_immutable_receipts(foundation):
    state,contract,ws = foundation
    pipeline = Pipeline(state,FakeRunner([]))
    paths=[]
    for reason,context in [('wrong root',{'root':'one'}),('incomplete vertical',{'root':'two'})]:
        pipeline._record_contract_plan_admission('same complete response',plan_gates.PlanAdmission('fail',contract.contract_hash,(reason,)),context)
        paths.append(receipt_for(state)[0])
    assert paths[0] != paths[1] and all(path.is_file() for path in paths)
    assert json.loads(paths[0].read_bytes())['admission']['errors'] == ['wrong root']
    assert json.loads(paths[1].read_bytes())['admission']['errors'] == ['incomplete vertical']


async def test_capture_overflow_is_explicit_failure_not_truncated_success(foundation):
    state,contract,ws = foundation
    text='x'*(plan_gates.MAX_REJECTED_PLAN_BYTES+1)
    pipeline=Pipeline(state,FakeRunner([text]))
    with pytest.raises(DeliveryBlocked): await pipeline._aplan_phase()
    _,record=receipt_for(state)
    assert record['response'] is None and not record['capture_complete'] and record['capture_limit_exceeded']
    assert record['response_bytes']==len(text) and not state.stories


async def test_structured_wrong_root_rejections_are_captured_before_bounded_repair(foundation,monkeypatch):
    state,contract,ws = foundation
    monkeypatch.setattr(settings,'po_pipeline','on')
    plan=candidate(foundation)
    plan['epics'][0]['stories'][0]['tasks'][0]['file_globs']=['backend/'+workspace.package_name(state)+'/wrong.py']
    text=json.dumps(plan)
    runner=FakeRunner([text,text+' '])
    pipeline=Pipeline(state,runner)
    with pytest.raises(DeliveryBlocked): await pipeline._aplan_phase()
    records=[json.loads(p.read_bytes()) for p in (acceptance.supervisor_root(state.id)/'plans/rejected').glob('*.json')]
    assert len(runner.calls)==2 and not state.stories
    assert {text,text+' '} <= {r['response'] for r in records}
    assert all('RACINES CANONIQUES' in call['prompt'] for call in runner.calls)


async def test_independent_major_finding_not_cleared_or_overridden_by_machine_recalculation(foundation):
    from dataclasses import asdict
    state,contract,ws=foundation
    finding=plan_gates.PlanFinding('independent-major','major',True)
    state.plan_findings=[asdict(finding)]
    pipeline=Pipeline(state,FakeRunner([json.dumps(candidate(foundation))]))
    with pytest.raises(DeliveryBlocked): await pipeline._aplan_phase()
    assert asdict(finding) in state.plan_findings
    _, record = receipt_for(state)
    assert any('independent-major' in error for error in record['admission']['errors'])
    assert not state.stories


@pytest.mark.parametrize('mode',['write_failure','tampered_receipt','directory_alias'])
def test_rejected_receipt_fail_closed_and_idempotent(foundation,monkeypatch,mode,tmp_path):
    import os
    import subprocess
    from autospec.agents.file_broker import FileBroker
    state,contract,ws=foundation
    pipeline=Pipeline(state,FakeRunner([]))
    admission=plan_gates.PlanAdmission('fail',contract.contract_hash,('wrong root',))
    if mode == 'write_failure':
        monkeypatch.setattr(FileBroker,'path',lambda *a,**k:(_ for _ in ()).throw(OSError('unwritable')))
    elif mode == 'directory_alias':
        outside=tmp_path/'outside-receipts';outside.mkdir()
        link=acceptance.supervisor_root(state.id)/'plans'
        if os.name == 'nt':
            subprocess.run(['cmd','/c','mklink','/J',str(link),str(outside)],check=True,capture_output=True)
        else:
            link.symlink_to(outside,target_is_directory=True)
    else:
        pipeline._record_contract_plan_admission('raw',admission,{})
        path=receipt_for(state)[0]
        original=path.read_bytes()
        pipeline._record_contract_plan_admission('raw',admission,{})
        assert path.read_bytes()==original
        path.write_bytes(b'contradiction')
    with pytest.raises(DeliveryBlocked): pipeline._record_contract_plan_admission('raw',admission,{})
    assert state.plan_admission_public['status']=='not_verified' and not state.delivery_ready


def test_capture_limit_counts_utf8_bytes_not_characters(foundation):
    state,contract,ws=foundation
    text='é'*(plan_gates.MAX_REJECTED_PLAN_BYTES//2+1)
    record=plan_gates.rejected_plan_record(text,plan_gates.PlanAdmission('fail',contract.contract_hash,('invalid shape',)))
    assert len(text)<plan_gates.MAX_REJECTED_PLAN_BYTES
    assert record['response_bytes']==len(text.encode('utf-8')) and record['capture_limit_exceeded']
    assert record['response'] is None and not record['capture_complete']


@pytest.mark.parametrize('glob',['**','*/**','**/*.tsx'])
def test_backend_broad_glob_cannot_own_frontend(foundation,glob):
    state,contract,ws=foundation
    plan=candidate(foundation)
    plan['epics'][0]['stories'][0]['tasks'][0]['file_globs']=[glob]
    admission=Pipeline(state,FakeRunner([]))._admit_contract_plan(plan,contract,acceptance.plan_policy(state,contract))
    assert admission.status=='fail' and any('incompatible stream root' in error for error in admission.errors)


def test_backend_glob_cannot_span_mixed_case_nested_frontend_root(foundation):
    state,contract,ws=foundation
    state.streams[1].file_root='Web/Front'
    # The changed root changes the factory-owned scaffold path set. Rebuild the
    # deterministic fixture manifest for that exact state before evaluating the
    # independent glob boundary below.
    (ws/bootstrap.MANIFEST).unlink()
    prepared=bootstrap.prepare(state,ws)
    assert prepared.ok
    state.bootstrap_status='ready';state.bootstrap_fingerprint=prepared.fingerprint
    plan=candidate(foundation)
    tasks=plan['epics'][0]['stories'][0]['tasks']
    tasks[0]['file_globs']=['Web/*/**']
    tasks[1]['file_globs']=['Web/Front/src/App.tsx']
    tasks[2]['file_globs']=['Web/Front/src/vertical.test.tsx']
    admission=Pipeline(state,FakeRunner([]))._admit_contract_plan(plan,contract,acceptance.plan_policy(state,contract))
    assert admission.status=='fail' and any('incompatible stream root' in error for error in admission.errors)


async def test_missing_foundation_without_formal_contract_refuses_plan_before_provider(foundation,monkeypatch):
    state,_,ws=foundation
    (ws/'main.py').unlink()
    runner=FakeRunner([])
    pipeline=Pipeline(state,runner)
    monkeypatch.setattr(pipeline,'_acceptance_contract',lambda:None)
    with pytest.raises(DeliveryBlocked):
        await pipeline._aplan_phase()
    assert not runner.calls and not state.stories


def test_backend_root_level_nonrecursive_glob_is_still_admissible(foundation):
    state,contract,ws=foundation
    plan=candidate(foundation)
    plan['epics'][0]['stories'][0]['tasks'][0]['file_globs']=['test*.py','tests/**',workspace.package_name(state)+'/features/**']
    admission=Pipeline(state,FakeRunner([]))._admit_contract_plan(plan,contract,acceptance.plan_policy(state,contract))
    assert admission.status=='pass'


def test_api_only_prompt_does_not_require_fictional_frontend():
    state=ProjectState(id='api-only',name='Books',goal='API',technical_stack=stack.freeze(
        dict(backend='python',framework='fastapi',frontend='none',database='none',kind='api',source='explicit')))
    block=prompts._workspace_plan_block(state,'books')
    assert 'Aucun frontend' in block and 'Ne reporte PAS App.tsx' not in block
    assert prompts.plan_workspace_context(state,'books')['frontend_entrypoints']==[]


def test_frozen_stack_rejects_changed_fields_even_with_same_decision_digest(foundation):
    state,contract,ws=foundation
    plan=candidate(foundation)
    plan['technical_stack']['framework']='attacker-controlled-framework'
    plan['technical_stack']['decision_sha256']=state.technical_stack['decision_sha256']
    admission=Pipeline(state,FakeRunner([]))._admit_contract_plan(plan,contract,acceptance.plan_policy(state,contract))
    assert admission.status=='fail'
    assert 'plan stack differs from frozen technical_stack decision' in admission.errors


def test_public_admission_never_serializes_private_candidate_diagnostics(foundation):
    state,contract,ws=foundation
    candidate_secret='PRIVATE_CANDIDATE_5fc8d1'
    error_secret='PRIVATE_ERROR_PATH_TITLE_19f8ac'
    pipeline=Pipeline(state,FakeRunner([]))
    admission=plan_gates.PlanAdmission('fail',contract.contract_hash,(f"invalid {error_secret}",))
    pipeline._record_contract_plan_admission(candidate_secret,admission,{'path':error_secret,'title':error_secret})
    _,record=receipt_for(state)
    assert candidate_secret in record['response'] and any(error_secret in error for error in record['admission']['errors'])
    payload=state.model_dump_json()
    assert candidate_secret not in payload and error_secret not in payload
    assert 'plan_admission"' not in payload and 'plan_admission_public' in payload
    monitor=(workspace_dir(state.id)/'build-monitor.jsonl').read_text(encoding='utf-8')
    assert candidate_secret not in monitor and error_secret not in monitor
    events=[event for _,event in bus.replay_since(0) if event.get('project_id')==state.id]
    assert events and candidate_secret not in json.dumps(events) and error_secret not in json.dumps(events)
    assert state.plan_admission_public['diagnostics'][0]['code']=='other_constraint'


def test_rejected_admission_projection_survives_real_state_reload(foundation, monkeypatch, tmp_path):
    state, contract, _ = foundation
    monkeypatch.setattr(settings, 'workspace_root', tmp_path / 'isolated-workspaces')
    acceptance.supervisor_root(state.id).mkdir(parents=True)
    candidate_secret = 'PRIVATE_CANDIDATE_RELOAD_28f1'
    error_secret = 'PRIVATE_ERROR_RELOAD_73ab'
    admission = plan_gates.PlanAdmission('fail', contract.contract_hash,
        (f'contract coverage missing: {error_secret}',))
    pipeline = Pipeline(state, FakeRunner([]))

    pipeline._record_contract_plan_admission(candidate_secret, admission,
        {'file_root': 'private/path', 'candidate': error_secret})

    reloaded = load_state(state.id)
    assert reloaded is not None
    assert reloaded.plan_admission_public == state.plan_admission_public
    assert reloaded.plan_admission_public['status'] == 'fail'
    assert reloaded.plan_admission_public['diagnostic_counts'] == {'coverage': 1}
    serialized = reloaded.model_dump_json()
    for private_text in (candidate_secret, error_secret, 'private/path'):
        assert private_text not in serialized
    receipt_path, receipt = receipt_for(reloaded)
    assert receipt_path.is_file()
    assert receipt['response'] == candidate_secret
    assert error_secret in receipt['admission']['errors'][0]


def test_legacy_state_discards_raw_plan_diagnostics_and_requires_revalidation():
    state=ProjectState(id='legacy-plan-secret',name='Legacy',goal='Test')
    raw=state.model_dump(mode='json')
    raw['plan_admission']={'status':'fail','errors':['LEGACY_PRIVATE_ERROR'],'response':'LEGACY_PRIVATE_PLAN',
                           'milestones':{'foundation':['LEGACY_PRIVATE_ID']},'lots':[]}
    raw['plan_review_issues']=['LEGACY_PRIVATE_REVIEW_ERROR']
    raw['plan_review_suggestions']=['LEGACY_PRIVATE_REVIEW_SUGGESTION']
    raw['plan_findings']=[{'kind':'constraint','source':'deterministic_plan_gate','message':'LEGACY_PRIVATE_FINDING'}]
    migrated=ProjectState.model_validate(raw)
    encoded=migrated.model_dump_json()
    assert 'plan_admission"' not in encoded
    assert 'LEGACY_PRIVATE_ERROR' not in encoded and 'LEGACY_PRIVATE_PLAN' not in encoded
    assert 'LEGACY_PRIVATE_ID' not in encoded
    assert 'LEGACY_PRIVATE_REVIEW_ERROR' not in encoded and 'LEGACY_PRIVATE_FINDING' not in encoded
    assert 'LEGACY_PRIVATE_REVIEW_SUGGESTION' not in encoded
    assert migrated.plan_review_issues==[] and migrated.plan_review_suggestions==[] and migrated.plan_findings==[]
    assert migrated.plan_admission_public['status']=='not_verified'
    assert migrated.plan_structure=={}

    legacy_only=state.model_dump(mode='json')
    legacy_only.pop('plan_admission_public',None)
    legacy_only.pop('plan_structure',None)
    legacy_only['plan_review_issues']=['LEGACY_ONLY_PRIVATE_ISSUE']
    legacy_only['plan_review_suggestions']=['LEGACY_ONLY_PRIVATE_SUGGESTION']
    legacy_only['plan_findings']=[
        {'kind':'constraint','message':'LEGACY_ONLY_PRIVATE_CONSTRAINT'},
        {'kind':'critic','message':'independent accepted opinion'},
    ]
    migrated_only=ProjectState.model_validate(legacy_only)
    encoded_only=migrated_only.model_dump_json()
    assert 'LEGACY_ONLY_PRIVATE_ISSUE' not in encoded_only
    assert 'LEGACY_ONLY_PRIVATE_SUGGESTION' not in encoded_only
    assert 'LEGACY_ONLY_PRIVATE_CONSTRAINT' not in encoded_only
    assert migrated_only.plan_review_issues==[] and migrated_only.plan_review_suggestions==[]
    assert migrated_only.plan_findings==[{'kind':'critic','message':'independent accepted opinion'}]


async def test_plan_tracker_redacts_prompt_candidate_from_interactions_trace_monitor_and_sse(foundation,monkeypatch):
    state,contract,ws=foundation
    from autospec import observability
    prompt_secret='PRIVATE_PROMPT_2b07a1'
    response_secret='PRIVATE_RESPONSE_d74109'
    runner=FakeRunner([response_secret])
    pipeline=Pipeline(state,runner)
    state.phase=PipelinePhase.PLAN
    traces=[]
    monkeypatch.setattr(observability,'trace_agent_call',lambda **kwargs:traces.append(kwargs))
    await pipeline._tracked.arun(prompt_secret, 'PO')
    interactions=pipeline.interactions.for_item('phase:plan')
    assert len(interactions)==1
    assert prompt_secret not in interactions[0].prompt and response_secret not in interactions[0].response
    sidecar_path=workspace_dir(state.id)/'autospec-interactions.jsonl'
    for _ in range(100):
        if sidecar_path.is_file(): break
        await asyncio.sleep(.01)
    sidecar=sidecar_path.read_text(encoding='utf-8')
    assert prompt_secret not in sidecar and response_secret not in sidecar
    assert len(traces)==1 and prompt_secret not in traces[0]['input_text'] and response_secret not in traces[0]['output_text']
    assert prompt_secret not in state.model_dump_json() and response_secret not in state.model_dump_json()
    monitor=(workspace_dir(state.id)/'build-monitor.jsonl').read_text(encoding='utf-8')
    assert prompt_secret not in monitor and response_secret not in monitor
    events=[event for _,event in bus.replay_since(0) if event.get('project_id')==state.id]
    assert events and prompt_secret not in json.dumps(events) and response_secret not in json.dumps(events)


async def test_failed_plan_tracker_redacts_error_from_interaction_and_monitor(foundation,monkeypatch):
    from autospec.agents.runner import AgentError
    state,contract,ws=foundation
    prompt_secret='PRIVATE_FAILED_PROMPT_0c8319'
    error_secret='PRIVATE_PROVIDER_ERROR_PATH_1c6f02'
    class ErrorRunner:
        async def arun(self,*args,**kwargs):
            raise AgentError(error_secret)
    pipeline=Pipeline(state,ErrorRunner())
    state.phase=PipelinePhase.PLAN
    with pytest.raises(AgentError):
        await pipeline._tracked.arun(prompt_secret,'PO')
    interactions=pipeline.interactions.for_item('phase:plan')
    assert len(interactions)==1 and not interactions[0].ok
    assert prompt_secret not in interactions[0].prompt and error_secret not in interactions[0].error
    sidecar_path=workspace_dir(state.id)/'autospec-interactions.jsonl'
    for _ in range(100):
        if sidecar_path.is_file(): break
        await asyncio.sleep(.01)
    sidecar=sidecar_path.read_text(encoding='utf-8')
    monitor=(workspace_dir(state.id)/'build-monitor.jsonl').read_text(encoding='utf-8')
    events=[event for _,event in bus.replay_since(0) if event.get('project_id')==state.id]
    public=' '.join((sidecar,monitor,json.dumps(events),state.model_dump_json()))
    assert prompt_secret not in public and error_secret not in public
