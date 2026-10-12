"""Supervisor handoff tests, never generated-source calls to a provider."""
import asyncio
from types import SimpleNamespace

import pytest

from autospec.agents.runner import FakeRunner
from autospec.config import settings
from autospec.models import ProjectState
from autospec.orchestrator.pipeline import Pipeline
from autospec.validation.source_reviewer import ReviewPending
from autospec.validation.support_adapter import AdapterUnavailable


def pipeline():
    return Pipeline(ProjectState(id="external-review",name="Review",goal="offline"),FakeRunner())


def contract():
    return SimpleNamespace(contract_hash="b"*64)


async def test_missing_review_publishes_request_and_cannot_call_generation_provider(monkeypatch,tmp_path):
    from autospec.validation import source_reviewer
    p=pipeline()
    monkeypatch.setattr(settings,"external_review_wait_seconds",0)
    async def pending(*args,**kwargs): raise ReviewPending(tmp_path/"request.json","operational_proposal")
    monkeypatch.setattr(source_reviewer,"ensure_reviewed_configuration",pending)
    with pytest.raises(ReviewPending):
        await p._await_reviewed_configuration(contract(),tmp_path,"a"*64,phase="vertical")
    assert not p.runner.calls and "external-source-review" not in p.state.agent_activity


async def test_async_wait_changes_stage_and_accepts_external_receipt_only(monkeypatch,tmp_path):
    from autospec.validation import source_reviewer
    p=pipeline();calls=[]
    monkeypatch.setattr(settings,"external_review_wait_seconds",5)
    async def supplied(*args,**kwargs):
        calls.append(kwargs["phase"])
        if len(calls)==1: raise ReviewPending(tmp_path/"request.json","independent_review")
        return {"status":"REVIEWED"}
    monkeypatch.setattr(source_reviewer,"ensure_reviewed_configuration",supplied)
    assert (await p._await_reviewed_configuration(contract(),tmp_path,"a"*64,phase="final"))["status"]=="REVIEWED"
    assert calls==["final","final"] and not p.runner.calls


async def test_stop_interrupts_review_without_provider_dispatch(monkeypatch,tmp_path):
    from autospec.validation import source_reviewer
    p=pipeline();entered=asyncio.Event()
    monkeypatch.setattr(settings,"external_review_wait_seconds",5)
    async def pending(*args,**kwargs):
        entered.set()
        raise ReviewPending(tmp_path/"request.json","operational_proposal")
    monkeypatch.setattr(source_reviewer,"ensure_reviewed_configuration",pending)
    waiter=asyncio.create_task(p._await_reviewed_configuration(contract(),tmp_path,"a"*64,phase="vertical"))
    await asyncio.wait_for(entered.wait(),2)
    assert p.state.agent_activity["external-source-review"]["model"]=="gpt-6.1-sol"
    p._stop_requested=True
    with pytest.raises(AdapterUnavailable,match="interrupted"):await waiter
    assert not p.runner.calls and not p.state.agent_activity


async def test_cancel_cleans_visible_wait(monkeypatch,tmp_path):
    from autospec.validation import source_reviewer
    p=pipeline();entered=asyncio.Event()
    monkeypatch.setattr(settings,"external_review_wait_seconds",30)
    async def pending(*args,**kwargs):
        entered.set();raise ReviewPending(tmp_path/"request.json","operational_proposal")
    monkeypatch.setattr(source_reviewer,"ensure_reviewed_configuration",pending)
    waiter=asyncio.create_task(p._await_reviewed_configuration(contract(),tmp_path,"a"*64,phase="vertical"))
    await asyncio.wait_for(entered.wait(),2);waiter.cancel()
    with pytest.raises(asyncio.CancelledError):await waiter
    assert not p.runner.calls and not p.state.agent_activity
