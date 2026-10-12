"""Offline paid-receipt bookkeeping; scripted costs are not provider proofs."""
import asyncio
from decimal import Decimal

import pytest

from autospec.agents.file_broker import ExecutionContext, active_execution
from autospec.agents.runner import AgentError, AgentResult, active_budget_usd, active_processes, active_skills_enabled
from autospec.orchestrator.pipeline import Pipeline
from tests.test_budget_tracker_reservations import configure, state


@pytest.mark.parametrize('concurrent',[False,True])
@pytest.mark.parametrize('failure',['cancel','error'])
@pytest.mark.parametrize('complete',[False,True])
async def test_paid_result_survives_cancellable_claim_release_in_state_and_journal(tmp_path,monkeypatch,concurrent,failure,complete):
    configure(tmp_path,monkeypatch,enabled=concurrent)
    root=tmp_path/'source';root.mkdir()
    receipt=AgentResult('scripted known receipt',cost_usd=.2,input_tokens=20,output_tokens=5,usage_reported=complete)
    class Port:
        budget_provider_id='bounded-fake'
        async def arun(self,*args,**kwargs):return receipt
    pipeline=Pipeline(state(),Port())
    async def context(*args):return ExecutionContext('offline-scope',root),True
    async def release(owner):
        # Admission must already contain the known receipt at this first await.
        assert pipeline.state.usage.cost_usd==pytest.approx(.2)
        if failure=='cancel':raise asyncio.CancelledError()
        raise RuntimeError('offline release failed')
    monkeypatch.setattr(pipeline,'_aprepare_tool_context',context)
    monkeypatch.setattr(pipeline._claim_arbiter,'release',release)
    before=(active_execution.get(),active_budget_usd.get(),active_processes.get(),active_skills_enabled.get())
    with pytest.raises(asyncio.CancelledError if failure=='cancel' else AgentError) as failed:
        await pipeline._tracked.arun('offline prompt','s',cwd=str(root))
    assert failed.value.usage is receipt
    usage=pipeline.state.usage
    assert usage.cost_usd==pytest.approx(.2) and usage.agent_calls==1
    assert usage.input_tokens==20 and usage.output_tokens==5
    assert usage.unreported_calls==int(not complete)
    assert (active_execution.get(),active_budget_usd.get(),active_processes.get(),active_skills_enabled.get())==before
    if concurrent:
        ledger=pipeline._tracked._reservation_pool.snapshot()
        assert Decimal(ledger['recorded_usd'])==Decimal('.2')
        assert Decimal(ledger['reserved_usd'])==(Decimal('0') if complete else Decimal('.2'))
        assert bool(ledger['blocked_reasons']) is (not complete)
    else:
        assert pipeline._tracked._reservation_pool is None
    assert pipeline._stop_requested is (not complete)


async def test_cleanup_cancellation_cannot_erase_an_already_accounted_error_prefix(tmp_path,monkeypatch):
    configure(tmp_path,monkeypatch)
    root=tmp_path/'source';root.mkdir()
    receipt=AgentResult('scripted paid prefix',cost_usd=.2,usage_reported=False)
    class Port:
        budget_provider_id='bounded-fake'
        async def arun(self,*args,**kwargs):raise AgentError('offline unknown final turn',usage=receipt)
    pipeline=Pipeline(state(),Port())
    async def context(*args):return ExecutionContext('offline-scope',root),True
    async def release(*args):raise asyncio.CancelledError()
    monkeypatch.setattr(pipeline,'_aprepare_tool_context',context)
    monkeypatch.setattr(pipeline._claim_arbiter,'release',release)
    with pytest.raises(asyncio.CancelledError) as failed:await pipeline._tracked.arun('p','s',cwd=str(root))
    assert failed.value.usage is receipt
    assert pipeline.state.usage.cost_usd==pytest.approx(.2)
    assert pipeline.state.usage.agent_calls==pipeline.state.usage.failed_calls==pipeline.state.usage.unreported_calls==1
    ledger=pipeline._tracked._reservation_pool.snapshot()
    assert Decimal(ledger['recorded_usd'])==Decimal('.2') and Decimal(ledger['reserved_usd'])==Decimal('.2')
    assert pipeline._stop_requested and ledger['blocked_reasons']
