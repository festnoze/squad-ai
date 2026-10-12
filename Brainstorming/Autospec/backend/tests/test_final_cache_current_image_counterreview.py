"""Independent inert counterproof: historical report != current Docker image.

Every provider/image/builder port is strict mock. No Docker or product/model
execution occurs. The fixture proves admission mechanics, never product PASS.
"""
import hashlib
import json

import pytest

from autospec.agents.runner import FakeRunner
from autospec.config import settings
from autospec.contracts import import_contract
from autospec.models import ProjectState
from autospec.orchestrator import acceptance
from autospec.orchestrator.dependencies import atomic_json
from autospec.orchestrator.pipeline import Pipeline
from autospec.storage import workspace_dir
from autospec.validation import coordinator,delivery_raccord
from autospec.validation.final_gate import source_snapshot,verification_cache_context
from autospec.validation.support_adapter import AdapterUnavailable


@pytest.mark.parametrize('with_readme',[False,True])
@pytest.mark.parametrize('image_problem',['missing','cmd_drift'])
async def test_historical_final_cache_never_admits_unavailable_or_changed_image(tmp_path,monkeypatch,with_readme,image_problem):
    monkeypatch.setattr(settings,'workspace_root',tmp_path/'workspace')
    monkeypatch.setattr(settings,'docker_delivery',False)
    brief='An exact built delivery image is required; this is an offline mechanical fixture.'
    table='| OPS-01 | B / X | Exact built image |'
    if with_readme:table+='\n| OPS-05 | B / X+R | Reviewed runtime instructions |'
    contract=import_contract(brief,table,reviewed_by='offline independent counterreview fixture')
    state=ProjectState(id='image-cache-counter',name='Offline image cache',goal=brief,
        brief=brief,acceptance_contract_hash=contract.contract_hash)
    acceptance.contract_store(state.id).save(contract)
    source=workspace_dir(state.id);source.mkdir(parents=True)
    (source/'main.py').write_text('# inert bytes, never imported or executed\n')
    snapshot=source_snapshot(source).digest;supervisor=acceptance.supervisor_root(state.id)
    rows=[]
    for requirement in contract.requirements:
        proofs=[]
        for kind in ('X','R'):
            path=supervisor/(requirement.id+'-'+kind+'.json')
            atomic_json(path,{'scope':'synthetic historical receipt for admission mechanism ONLY'})
            proofs.append(dict(type=kind,path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                snapshot_hash=snapshot,contract_hash=contract.contract_hash,
                checks=[requirement.id+':mechanism'],passed=True))
        rows.append(dict(id=requirement.id,gate=requirement.gate,expected=requirement.expected,status='PASS',
            observed='synthetic historical build, not current availability',reproduction=['inert fixture'],
            impact='',limits=[],proofs=proofs))
    reportpath=supervisor/'reports'/snapshot/'verification-reports.json'
    atomic_json(reportpath,[dict(contract_hash=contract.contract_hash,snapshot_hash=snapshot,requirements=rows)])
    historical_bytes=reportpath.read_bytes()
    atomic_json(reportpath.with_name('verification-context.json'),
        {'context':verification_cache_context(contract.contract_hash,snapshot,supervisor),
         'reports_sha256':hashlib.sha256(historical_bytes).hexdigest()})
    runner=FakeRunner();pipeline=Pipeline(state,runner);monkeypatch.setattr(pipeline,'_sync',lambda:None)
    called={'review':0,'image':0,'rebuild':0,'verify':0,'facts':0}
    async def reviewed(*args,**kwargs):called['review']+=1;return {'status':'REVIEWED'}
    async def unavailable_image(observed_contract,observed_source,observed_supervisor):
        called['image']+=1
        assert observed_contract.contract_hash==contract.contract_hash
        assert source_snapshot(observed_source).digest==snapshot and observed_supervisor==supervisor
        raise AdapterUnavailable('CURRENT_IMAGE_UNAVAILABLE' if image_problem=='missing' else 'CURRENT_IMAGE_CMD_IDENTITY_DIFFER')
    async def forbidden_rebuild(*args,**kwargs):called['rebuild']+=1;raise AssertionError('cache must not repair/rebuild')
    async def forbidden_verify(*args,**kwargs):called['verify']+=1;raise AssertionError('cache must not invoke fresh model/probes')
    async def forbidden_facts(*args,**kwargs):called['facts']+=1;raise AssertionError('cache must not invent fresh facts')
    monkeypatch.setattr(pipeline,'_await_reviewed_configuration',reviewed)
    monkeypatch.setattr(delivery_raccord,'load_qualified_delivery_image',unavailable_image)
    monkeypatch.setattr(delivery_raccord,'collect_native_delivery_build',forbidden_rebuild)
    monkeypatch.setattr(delivery_raccord,'collect_native_final_facts',forbidden_facts)
    monkeypatch.setattr(coordinator,'verify_project',forbidden_verify)
    admitted=await pipeline._aindependent_acceptance_phase()
    observed={'case':image_problem,'with_readme':with_readme,'admitted':admitted,
        'delivery_ready':state.delivery_ready,'port_calls':called,'provider_calls':len(runner.calls),
        'historical_receipts_unchanged':reportpath.read_bytes()==historical_bytes,
        'acceptance_result':state.acceptance_result,'scope':'offline factory mechanism; no actual product proof'}
    print(json.dumps(observed,sort_keys=True))
    assert called['review']==1 and called['rebuild']==called['verify']==called['facts']==0
    assert not runner.calls and reportpath.read_bytes()==historical_bytes
    assert not admitted and not state.delivery_ready,'historical cache was admitted without current exact image facts'
    assert called['image']==1 and state.acceptance_result['status']=='NOT_VERIFIED'
