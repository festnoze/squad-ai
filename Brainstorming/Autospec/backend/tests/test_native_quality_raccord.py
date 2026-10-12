"""Offline raccord mechanics plus opt-in real Linux pytest/coverage collection.

Fake ports and synthetic R below test orchestration, not product acceptance.
Only the opt-in test executes its trusted fixture source, inside Docker.
"""
import hashlib
import json
import os
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import pytest

from autospec.contracts import import_contract
from autospec.orchestrator.dependencies import atomic_json
from autospec.orchestrator.isolated_validation import IsolatedValidator
from autospec.orchestrator.test_integrity import SuiteEvidence
from autospec.validation import native_quality_raccord as raccord
from autospec.validation.coordinator import SupervisorEvidenceStore
from autospec.validation.final_gate import source_snapshot
from autospec.validation.quality_contracts import NativeSuiteSpec, native_quality_plan_hash
from autospec.validation.support_adapter import AdapterUnavailable, Proof


def fixture_plan(tmp_path, *, failed=False):
    source=tmp_path/'product';source.mkdir()
    (source/'logic.py').write_text('def answer():\n return 42\n',encoding='utf-8')
    (source/'test_logic.py').write_text('from logic import answer\ndef test_answer():\n assert answer()==42\n',encoding='utf-8')
    control=tmp_path/'supervisor';control.mkdir()
    contract=import_contract('Offline collection fixture.', '| TST-01 | B / X+R | Native suite |',reviewed_by='offline unit metatest')
    snapshot=source_snapshot(source).digest
    mapping=control/'mapping.json'
    atomic_json(mapping,dict(snapshot_hash=snapshot,contract_hash=contract.contract_hash,nominal_security_db_mocks=False,
        requirements={'TST-01':[dict(suite='backend',test='test_logic.py::test_answer',assertion='offline inspected fixture assertion')]}))
    spec=NativeSuiteSpec('backend','.','python',('logic.py',),('auth',),coverage_source='logic')
    digest=native_quality_plan_hash((spec,),mapping)
    reviewpath=control/'synthetic-review.json';atomic_json(reviewpath,{'scope':'synthetic offline plan mechanics only'})
    review=Proof('R',str(reviewpath),hashlib.sha256(reviewpath.read_bytes()).hexdigest(),snapshot,contract.contract_hash,
        ('QUALITY:plan:'+digest,'TST-01:native_review','TST-02:mapping','TST-03:inventory'))
    atomic_json(control/'quality-plan.json',dict(snapshot_hash=snapshot,contract_hash=contract.contract_hash,
        candidate=dict(suites=[asdict(spec)],requirements_mapping={'TST-01':[]},mutation=None,nominal_security_db_mocks=False,e2e_mode='native'),
        mapping_path=str(mapping),plan_hash=digest,review=asdict(review),mutant_snapshot_hash=None))
    return source,snapshot,contract,control,FixturePort(failed=failed)


class FixturePort:
    """Observed command records are a scripted port, not a subprocess proof."""
    def __init__(self, *, failed=False, receipt=True):
        self.calls=[];self.failed=failed;self.receipt=receipt
    def run_suite(self,root,ecosystem,mode,reportpath,**options):
        self.calls.append((root,ecosystem,mode,reportpath,options))
        rc=int(self.failed)
        raw=dict(scope='offline fixture port, not executed product suite',return_code=rc)
        atomic_json(reportpath,raw)
        coverage={'files':{'logic.py':{'summary':{'num_statements':2,'covered_lines':0 if self.failed else 2,
            'num_branches':0,'covered_branches':0}}},'totals':{}}
        atomic_json(options['coveragepath'],coverage)
        executed=dict(argv=['fixture-port','--suite'],return_code=rc,image_id='sha256:'+'a'*64,
            source_fingerprint='b'*64,environment_fingerprint='c'*64,
            timing=dict(phase='tests',seconds=1.25,started_at='2026-10-12T00:00:00+00:00',ended_at='2026-10-12T00:00:01.25+00:00'),
            environment_preparation=dict(phase='install',seconds=.5,started_at='2026-10-12T00:00:00+00:00',ended_at='2026-10-12T00:00:00.5+00:00'))
        if self.receipt:atomic_json(reportpath.with_suffix('.execution.json'),executed)
        evidence=SuiteEvidence({'test_logic.py::test_answer':'failed' if self.failed else 'passed'},1,rc,report_valid=True)
        return SimpleNamespace(evidence=evidence,coverage=coverage,output='offline fixture output',
            image=executed['image_id'],source_fingerprint=executed['source_fingerprint'],fingerprint=executed['environment_fingerprint'],
            execution_receipt=executed if self.receipt else None)


async def test_missing_plan_is_nv_without_even_one_execution(tmp_path):
    source,snapshot,contract,control,port=fixture_plan(tmp_path)
    (control/'quality-plan.json').unlink()
    result=await raccord.collect_native_quality(None,contract,source,snapshot,control,validator=port)
    assert result['status']=='NOT_VERIFIED' and result['observations']==[] and port.calls==[]
    assert not (control/'observations.json').exists()


@pytest.mark.parametrize('drift',['source','mapping','review'])
async def test_stale_or_unreviewed_source_cannot_publish_or_execute(tmp_path,drift):
    source,snapshot,contract,control,port=fixture_plan(tmp_path)
    if drift=='source':(source/'logic.py').write_text('changed')
    elif drift=='mapping':(control/'mapping.json').write_text('{}')
    else:(control/'synthetic-review.json').write_text('changed')
    if drift=='source':
        with pytest.raises(AdapterUnavailable):await raccord.collect_native_quality(None,contract,source,snapshot,control,validator=port)
    else:
        result=await raccord.collect_native_quality(None,contract,source,snapshot,control,validator=port)
        assert result['status']=='NOT_VERIFIED'
    assert port.calls==[] and not (control/'observations.json').exists()


@pytest.mark.parametrize('failed',[False,True])
async def test_real_collector_records_scripted_port_and_retains_red_metrics(tmp_path,failed):
    source,snapshot,contract,control,port=fixture_plan(tmp_path,failed=failed)
    result=await raccord.collect_native_quality(None,contract,source,snapshot,control,validator=port)
    assert result['status']=='PARTIAL' and len(port.calls)==1
    assert set(result['observations'])=={'native_suites','requirement_test_mapping','coverage'}
    store=SupervisorEvidenceStore(control,snapshot,contract.contract_hash)
    suite=(await store.observe('native_suites'))[0]
    assert suite['failed']==int(failed) and suite['return_code']==int(failed)
    assert (await store.observe('coverage'))['backend']['lines']['covered']==(0 if failed else 2)
    assert result['native_receipts']['backend']['argv']==['fixture-port','--suite']
    assert result['native_receipts']['backend']['return_code']==int(failed)
    assert {row['phase'] for row in result['timings']}=={'tests','install'}
    assert all(row['seconds']>0 for row in result['timings'])
    assert all(p.type=='X' for p in await store.proofs('TST-01'))
    assert any('browser_e2e:' in limit for limit in result['limits'])
    assert any('authorization_mutation:' in limit for limit in result['limits'])
    assert source_snapshot(source).digest==snapshot


async def test_missing_observed_argv_is_never_reconstructed(tmp_path):
    source,snapshot,contract,control,port=fixture_plan(tmp_path);port.receipt=False
    result=await raccord.collect_native_quality(None,contract,source,snapshot,control,validator=port)
    assert result['native_receipts']=={} and result['timings']==[]
    assert any('native artifact unavailable' in limit for limit in result['limits'])


def experiment(tmp_path, *, failed=False):
    observed=[dict(check='ownership',passed=not failed,observed=not failed,expected=True)]
    path=tmp_path/'experiment.json';atomic_json(path,dict(snapshot_hash='a'*64,contract_hash='b'*64,checks=observed))
    proof=Proof('X',str(path),hashlib.sha256(path.read_bytes()).hexdigest(),'a'*64,'b'*64,('SEC-09:ownership',),not failed)
    return observed,proof


@pytest.mark.parametrize('failed',[False,True])
def test_experiment_only_derives_native_observed_verdict_never_acceptance(tmp_path,failed):
    observed,proof=experiment(tmp_path,failed=failed)
    row=raccord._experimental_row('SEC-09',observed,[proof],snapshot='a'*64,contract='b'*64,evidence_root=tmp_path,required={'ownership'})
    assert row['status']=='EXPERIMENTAL' and row['runtime_status']==('FAIL' if failed else 'PASS')


@pytest.mark.parametrize('bad',['r_only','incomplete','wrong_identity','wrong_outcome','wrong_observations','wrong_tags','outside','hardlink'])
def test_experiment_refuses_source_review_or_incomplete_native_proof(tmp_path,bad):
    observed,proof=experiment(tmp_path)
    raw=asdict(proof);required={'ownership'}
    if bad=='r_only':raw.update(type='R',passed=False)
    elif bad=='incomplete':required.add('pagination')
    elif bad=='wrong_identity':raw['snapshot_hash']='c'*64
    elif bad=='wrong_outcome':raw['passed']=False
    elif bad=='wrong_observations':observed=[dict(check='ownership',passed=True,observed='different')]
    elif bad=='wrong_tags':raw['checks']=('SEC-09:other',)
    elif bad=='outside':
        outside=tmp_path.parent/(tmp_path.name+'-outside.json');outside.write_bytes(Path(raw['path']).read_bytes());raw['path']=str(outside)
    elif bad=='hardlink':os.link(raw['path'],tmp_path/'alias.json')
    with pytest.raises(AdapterUnavailable):raccord._experimental_row('SEC-09',observed,[raw],snapshot='a'*64,contract='b'*64,evidence_root=tmp_path,required=required)


async def test_mutant_runtime_callback_requires_the_exact_external_profile(tmp_path,monkeypatch):
    source,snapshot,contract,control,_=fixture_plan(tmp_path)
    mutant=tmp_path/'mutant';mutant.mkdir();(mutant/'logic.py').write_text('changed')
    mutant_id=source_snapshot(mutant).digest
    calls=[]
    async def runtime(*args):calls.append(args);return {'scope':'offline callback only'}
    monkeypatch.setattr(raccord,'_mutation_runtime',runtime)
    plan={'mutant_snapshot_hash':mutant_id,'mutant_supervisor_root':control/'mutation-profiles'/mutant_id}
    probe=raccord._mutation_callback(contract,source,snapshot,control,plan)
    await probe(source,snapshot,contract.contract_hash);await probe(mutant,mutant_id,contract.contract_hash)
    assert [call[3] for call in calls]==[control,plan['mutant_supervisor_root']]
    plan['mutant_supervisor_root']=control/'unreviewed'
    with pytest.raises(AdapterUnavailable):await probe(mutant,mutant_id,contract.contract_hash)
    with pytest.raises(AdapterUnavailable):await probe(mutant,mutant_id,'c'*64)
    assert len(calls)==2


async def test_browser_api_timing_is_separate_and_cleanup_is_owned(tmp_path,monkeypatch):
    events=[]
    class Context:
        async def __aenter__(self):events.append('enter');return self
        async def __aexit__(self,*args):events.append('close')
    monkeypatch.setattr(raccord.coordinator,'_context',lambda *args,**kwargs:(Context(),None))
    async def execute(*args,**kwargs):
        events.append(kwargs);return [dict(id='E2E-01',mode='alone',proofs=[])]
    monkeypatch.setattr(raccord.coordinator,'_execute_e2e',execute)
    timings=[];contract=SimpleNamespace(contract_hash='b'*64)
    browser=raccord._BrowserRun(contract,tmp_path,'a'*64,tmp_path,timings)
    result=await browser.verify_e2e('a'*64,mode='alone',scenario_ids=['E2E-01'])
    assert result['scenarios'][0]['id']=='E2E-01' and events[-1]=='close'
    assert events[1]==dict(modes=('alone',),scenario_ids=['E2E-01'])
    assert timings[0]['phase']=='browser' and timings[0]['seconds']>=0 and 'argv' not in timings[0]
    with pytest.raises(AdapterUnavailable):await browser.verify_e2e('c'*64,mode='alone',scenario_ids=[])


@pytest.mark.skipif(os.environ.get('AUTOSPEC_REAL_LINUX_VALIDATION')!='1',reason='Opt-in real isolated pytest/coverage publication')
async def test_real_linux_collection_exports_exact_command_coverage_and_intact_x(tmp_path):
    source,_,contract,control,_=fixture_plan(tmp_path)
    (source/'pyproject.toml').write_text('[project]\nname="raccord-proof"\nversion="0.1.0"\nrequires-python=">=3.12"\ndependencies=["pytest==9.0.3"]\n')
    validator=IsolatedValidator(control/'linux-cache',timeout=300)
    validator.manager.ensure_lock(source,'python')
    # Refresh the reviewed synthetic metatest identity after Linux lock generation.
    snapshot=source_snapshot(source).digest
    mapping=control/'mapping.json';value=json.loads(mapping.read_bytes());value['snapshot_hash']=snapshot;atomic_json(mapping,value)
    plan=json.loads((control/'quality-plan.json').read_bytes());plan['snapshot_hash']=snapshot;plan['review']['snapshot_hash']=snapshot
    digest=native_quality_plan_hash((NativeSuiteSpec('backend','.','python',('logic.py',),('auth',),coverage_source='logic'),),mapping)
    plan['plan_hash']=digest;plan['review']['checks']=['QUALITY:plan:'+digest,'TST-01:native_review','TST-02:mapping','TST-03:inventory']
    atomic_json(control/'quality-plan.json',plan)
    result=await raccord.collect_native_quality(None,contract,source,snapshot,control,validator=validator)
    store=SupervisorEvidenceStore(control,snapshot,contract.contract_hash)
    suite=(await store.observe('native_suites'))[0]
    assert suite['passed']==1 and suite['failed']==0 and suite['report_valid'] is True
    receipt=result['native_receipts']['backend']
    assert receipt['argv'][:3]==['/opt/venv/bin/python','-m','pytest'] and receipt['return_code']==0
    assert all(Proof(**p).intact(snapshot_hash=snapshot,contract_hash=contract.contract_hash) for p in receipt['proofs'])
    coverage=await store.observe('coverage');assert coverage['backend']['lines']=={'total':2,'covered':2}
    assert result['status']=='PARTIAL' and all(row['seconds']>0 for row in result['timings'])
    assert source_snapshot(source).digest==snapshot
