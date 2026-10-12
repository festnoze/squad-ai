"""Independent offline counterexamples, not generated-product qualification.

All provider ports are scripted. RED means the blocking invariant is currently
violated, never that a real provider was contacted or a product was accepted.
"""
import hashlib

import pytest

from autospec.agents.personas import persona
from autospec.agents.runner import AgentError, AgentResult, active_budget_usd
from autospec.config import settings
from autospec.contracts import import_contract
from autospec.models import PipelinePhase, ProjectState, UserStory
from autospec.orchestrator import acceptance
from autospec.orchestrator.dependencies import atomic_json
from autospec.orchestrator.pipeline import Pipeline
from autospec.storage import workspace_dir
from autospec.validation.final_gate import source_snapshot
from autospec.validation.support_adapter import AdapterUnavailable


class OfflineReceiptRunner:
    def __init__(self):
        self.calls = 0
        self.allowances = []

    async def arun(self, *args, **kwargs):
        self.calls += 1
        self.allowances.append(active_budget_usd.get())
        return AgentResult('{}', cost_usd=0.01, input_tokens=1, output_tokens=1)


def uncertain_pipeline(monkeypatch, **budget):
    monkeypatch.setattr(settings, 'concurrent_budget_reservations', False)
    runner = OfflineReceiptRunner()
    state = ProjectState(id='review-unreported', name='Review', goal='Offline guard only',
        phase=PipelinePhase.STOPPED, stories=[UserStory(id='S-1', epic_id='E', title='Pending')], **budget)
    state.usage.cost_usd = 0.1
    state.usage.unreported_calls = 1
    state.generation_checkpoint = {'status': 'interrupted', 'cost_incomplete': True}
    return Pipeline(state, runner), runner


@pytest.mark.parametrize('budget', [{'budget_usd': 1}, {'budget_tokens': 100}])
async def test_historical_unknown_usage_blocks_direct_serialized_admission(monkeypatch, budget):
    pipeline, runner = uncertain_pipeline(monkeypatch, **budget)
    try:
        await pipeline._tracked.arun('offline counterprobe', persona('dev'))
    except AgentError:
        pass
    assert runner.calls == 0, f'unreconciled history dispatched {runner.calls} offline calls; allowances={runner.allowances}'
    assert pipeline.state.usage.unreported_calls == 1
    assert pipeline.state.usage.cost_usd == 0.1


async def test_explicit_resume_does_not_silently_reconcile_unknown_cost(monkeypatch):
    pipeline, runner = uncertain_pipeline(monkeypatch, budget_usd=1)
    async def resumed(**kwargs):
        await pipeline._tracked.arun('offline resumed worker', persona('dev'))
    monkeypatch.setattr(pipeline, '_aresume_build_run', resumed)
    try:
        await pipeline.aresume_build()
        if pipeline._task is not None:
            await pipeline._task
    except (AgentError, ValueError):
        pass
    assert runner.calls == 0, 'resume dispatched with an unreconciled interrupted call'
    assert pipeline.state.usage.unreported_calls == 1


async def test_new_feedback_does_not_bypass_unreconciled_budget(monkeypatch):
    pipeline, runner = uncertain_pipeline(monkeypatch, budget_usd=1)
    await pipeline.asend_user_message('Offline feedback: pending item should remain blocked by unknown cost.')
    if pipeline._impact_task is not None:
        await pipeline._impact_task
    assert runner.calls == 0, 'feedback reactivated inference against the unknown remaining allowance'
    assert pipeline.state.usage.unreported_calls == 1


async def test_clean_reported_history_still_allows_nominal_offline_call(monkeypatch):
    pipeline, runner = uncertain_pipeline(monkeypatch, budget_usd=1)
    pipeline.state.usage.unreported_calls = 0  # explicit trusted test setup, not production reconciliation
    await pipeline._tracked.arun('offline nominal', persona('dev'))
    assert runner.calls == 1 and runner.allowances == [0.9]
    assert pipeline.state.usage.unreported_calls == 0


async def test_final_report_cache_must_revalidate_current_review_engine(monkeypatch):
    contract = import_contract('A reviewed book.', '| BOOK-01 | B / X+R | Reviewed book |',
                               reviewed_by='offline mechanical fixture')
    state = ProjectState(id='review-cache', name='Review cache', goal='Offline only',
        brief=contract.brief, acceptance_contract_hash=contract.contract_hash)
    acceptance.contract_store(state.id).save(contract)
    source = workspace_dir(state.id)
    source.mkdir(parents=True)
    (source/'main.py').write_text('# inert fixture; never imported or executed\n')
    snapshot = source_snapshot(source).digest
    supervisor = acceptance.supervisor_root(state.id)
    proofs = []
    for kind in ('X', 'R'):
        path = supervisor/('synthetic-'+kind+'.json')
        atomic_json(path, {'scope': 'offline admission mechanism metatest, NOT product proof'})
        proofs.append(dict(type=kind, path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            snapshot_hash=snapshot, contract_hash=contract.contract_hash, checks=['BOOK-01:mechanism'], passed=True))
    requirement = contract.requirements[0]
    row = dict(id=requirement.id, gate=requirement.gate, expected=requirement.expected, status='PASS',
        observed='synthetic old-engine mechanism receipt', reproduction=['offline fixture'], impact='', limits=[], proofs=proofs)
    atomic_json(supervisor/'reports'/snapshot/'verification-reports.json',
        [dict(contract_hash=contract.contract_hash, snapshot_hash=snapshot, requirements=[row])])
    runner = OfflineReceiptRunner()
    pipeline = Pipeline(state, runner)
    revalidation = []
    async def refuse_stale_engine(*args, **kwargs):
        revalidation.append((args, kwargs))
        raise AdapterUnavailable('cached source review engine/protocol changed; fresh external review required')
    monkeypatch.setattr(pipeline, '_await_reviewed_configuration', refuse_stale_engine)
    admitted = await pipeline._aindependent_acceptance_phase()
    assert not admitted and not state.delivery_ready, 'final cache bypassed current review-engine revalidation'
    assert len(revalidation) == 1
    assert runner.calls == 0
