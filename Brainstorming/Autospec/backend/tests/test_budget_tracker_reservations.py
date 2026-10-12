"""Optional lane integration: reviewed fake bound, real durable tracker ledger.

No receipt here qualifies Claude or another production provider.
"""
import asyncio
import hashlib
import json
from decimal import Decimal

import pytest

from autospec.agents.runner import AgentError, AgentResult, active_budget_usd
from autospec.config import settings
from autospec.models import ProjectState, PipelinePhase
from autospec.orchestrator.pipeline import Pipeline
from autospec.orchestrator import acceptance


def configure(tmp_path, monkeypatch, *, enabled=True, bounded=True):
    monkeypatch.setattr(settings, "workspace_root", tmp_path / "projects")
    monkeypatch.setattr(settings, "concurrent_budget_reservations", enabled)
    monkeypatch.setattr(settings, "concurrent_budget_call_usd", .4)
    receipt = tmp_path / "factory-provider.json"
    receipt.write_text(json.dumps({"version": 1, "provider": "bounded-fake", "currency": "USD",
        "bound_kind": "hard_usd" if bounded else "estimated_usd", "whole_logical_call": True,
        "all_billable_costs": True, "enforced_before_overshoot": True,
        "exact_usd_transport": "active_budget_usd", "reviewed_by": "offline fixture reviewer"}))
    monkeypatch.setattr(settings, "concurrent_budget_provider_proofs", {"bounded-fake": {
        "path": str(receipt), "sha256": hashlib.sha256(receipt.read_bytes()).hexdigest()}})


def state(pid="lane", **kwargs):
    return ProjectState(id=pid, name="budget", goal="offline fixture", phase=PipelinePhase.BUILD,
                        budget_usd=1, **kwargs)


async def test_concurrent_tracker_transmits_each_envelope_not_project_remainder(tmp_path, monkeypatch):
    configure(tmp_path, monkeypatch)
    both, release = asyncio.Event(), asyncio.Event()
    limits = []
    class Bounded:
        budget_provider_id = "bounded-fake"
        async def arun(self, *args, **kwargs):
            limits.append(active_budget_usd.get())
            if len(limits) == 2: both.set()
            await release.wait()
            return AgentResult("ok", cost_usd=.3)
    pipeline = Pipeline(state(), Bounded())
    calls = [asyncio.create_task(pipeline._tracked.arun("p", "s")) for _ in range(2)]
    await asyncio.wait_for(both.wait(), 30)
    assert limits == [.4, .4] and pipeline._tracked._provider_calls == 2
    ledger = pipeline._tracked._reservation_pool.snapshot()
    assert Decimal(ledger["reserved_usd"]) == Decimal("0.8") and Decimal(ledger["recorded_usd"]) == 0
    release.set()
    await asyncio.gather(*calls)
    assert active_budget_usd.get() is None
    ledger = pipeline._tracked._reservation_pool.snapshot()
    assert Decimal(ledger["recorded_usd"]) == Decimal("0.6") and Decimal(ledger["reserved_usd"]) == 0
    assert pipeline.state.usage.cost_usd == pytest.approx(.6)
    assert (acceptance.supervisor_root("lane") / "budget-reservations.json").is_file()


@pytest.mark.parametrize("kind", ["off", "estimated", "token"])
async def test_ineligible_provider_only_uses_serialized_lane(tmp_path, monkeypatch, kind):
    configure(tmp_path, monkeypatch, enabled=kind != "off", bounded=kind != "estimated")
    entered, release = asyncio.Event(), asyncio.Event()
    calls = []
    class Unqualified:
        budget_provider_id = "bounded-fake"
        async def arun(self, *args, **kwargs):
            calls.append(active_budget_usd.get())
            entered.set()
            await release.wait()
            return AgentResult("ok", cost_usd=.1)
    pipeline = Pipeline(state(budget_tokens=100 if kind == "token" else 0), Unqualified())
    first = asyncio.create_task(pipeline._tracked.arun("p", "s"))
    await asyncio.wait_for(entered.wait(), 5)
    second = asyncio.create_task(pipeline._tracked.arun("p", "s"))
    await asyncio.sleep(.01)
    assert calls == [1] and pipeline._tracked._reservation_pool is None
    release.set()
    await asyncio.gather(first, second)
    assert calls == [1, .9]


@pytest.mark.parametrize("kind", ["cancel", "incomplete", "overshoot"])
async def test_ledger_uncertainty_or_breach_cannot_fallback(tmp_path, monkeypatch, kind):
    configure(tmp_path, monkeypatch)
    entered = asyncio.Event()
    class Bounded:
        budget_provider_id = "bounded-fake"
        async def arun(self, *args, **kwargs):
            entered.set()
            if kind == "cancel": await asyncio.Event().wait()
            return AgentResult("ok", cost_usd=.5 if kind == "overshoot" else .1,
                               usage_reported=kind != "incomplete")
    pipeline = Pipeline(state(), Bounded())
    call = asyncio.create_task(pipeline._tracked.arun("p", "s"))
    await asyncio.wait_for(entered.wait(), 5)
    if kind == "cancel": call.cancel()
    try: await call
    except asyncio.CancelledError: pass
    assert pipeline._stop_requested
    snapshot = pipeline._tracked._reservation_pool.snapshot()
    assert snapshot["blocked_reasons"]
    # Explicitly clearing the display stop cannot erase the durable ledger.
    pipeline._stop_requested = False
    with pytest.raises(AgentError): await pipeline._tracked.arun("p", "s")
    assert pipeline.state.usage.agent_calls == 1


async def test_disabling_active_lane_is_a_decision_not_a_bypass(tmp_path, monkeypatch):
    configure(tmp_path, monkeypatch)
    class Bounded:
        budget_provider_id = "bounded-fake"
        async def arun(self, *args, **kwargs): return AgentResult("ok", cost_usd=.1)
    pipeline = Pipeline(state(), Bounded())
    await pipeline._tracked.arun("p", "s")
    monkeypatch.setattr(settings, "concurrent_budget_reservations", False)
    with pytest.raises(AgentError, match="LANE_CHANGED"):
        await pipeline._tracked.arun("p", "s")
    assert pipeline.state.usage.agent_calls == 1


@pytest.mark.parametrize("problem", ["off", "provider_absent", "tokens"])
async def test_restart_cannot_bypass_existing_durable_lane(tmp_path, monkeypatch, problem):
    configure(tmp_path, monkeypatch)
    class Bounded:
        budget_provider_id = "bounded-fake"
        async def arun(self, *args, **kwargs):
            return AgentResult("incomplete", cost_usd=.1, usage_reported=False)
    first = Pipeline(state(), Bounded())
    await first._tracked.arun("p", "s")
    # Even removing the in-memory/state stop does not change the journal.
    recovered = state(budget_tokens=100 if problem == "tokens" else 0)
    if problem == "off": monkeypatch.setattr(settings, "concurrent_budget_reservations", False)
    if problem == "provider_absent": monkeypatch.setattr(settings, "concurrent_budget_provider_proofs", {})
    second = Pipeline(recovered, Bounded())
    with pytest.raises(AgentError, match="LANE_CHANGED"):
        await second._tracked.arun("cannot redispatch", "s")
    assert second._stop_requested and recovered.usage.agent_calls == 0


async def test_preprovider_checkpoint_failure_releases_zero_known_reservation(tmp_path, monkeypatch):
    configure(tmp_path, monkeypatch)
    from autospec.orchestrator import pipeline as module
    from autospec.storage import PersistenceError
    class Forbidden:
        budget_provider_id = "bounded-fake"
        async def arun(self, *args, **kwargs): pytest.fail("checkpoint failure must prevent spend")
    pipeline = Pipeline(state(), Forbidden())
    def failed(*args, **kwargs): raise PersistenceError("offline disk failure")
    monkeypatch.setattr(module, "save_state_checkpoint", failed)
    with pytest.raises(PersistenceError): await pipeline._tracked.arun("p", "s")
    snapshot = pipeline._tracked._reservation_pool.snapshot()
    assert snapshot["reserved_usd"] == "0" and snapshot["unreported_calls"] == 0
    assert pipeline.state.usage.agent_calls == 0
