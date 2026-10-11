"""Budget admission and truthful usage telemetry without any paid agent calls."""
import asyncio
import json

import pytest

from autospec.agents.personas import persona
from autospec.agents.runner import (
    AgentError, AgentResult, ClaudeCliRunner, ProcessRegistry,
    active_budget_usd, active_processes, active_skills_enabled,
)
from autospec.config import settings
from autospec.models import ProjectState
from autospec.orchestrator.pipeline import Pipeline


def cli_reply(monkeypatch, payload, code=0):
    commands = []
    def run(args, *rest):
        commands.append(args)
        return code, json.dumps(payload), ""
    monkeypatch.setattr("autospec.agents.runner._run_tracked", run)
    return commands


async def test_claude_input_totals_include_cache_read_and_creation(monkeypatch):
    cli_reply(monkeypatch, {"result": "ok", "total_cost_usd": .5, "usage": {
        "input_tokens": 10, "cache_creation_input_tokens": 200,
        "cache_read_input_tokens": 3000, "output_tokens": 20,
    }})
    result = await ClaudeCliRunner().arun("p", "s")
    assert result.input_tokens == 3210
    assert result.output_tokens == 20
    assert result.cost_usd == .5
    assert result.usage_reported


@pytest.mark.parametrize("code", [0, 1])
async def test_error_response_retains_reported_usage(monkeypatch, code):
    cli_reply(monkeypatch, {"result": "budget exhausted", "is_error": True,
        "total_cost_usd": .25, "usage": {"input_tokens": 10}}, code)
    with pytest.raises(AgentError) as caught:
        await ClaudeCliRunner().arun("p", "s")
    assert caught.value.usage.cost_usd == .25
    assert caught.value.usage.input_tokens == 10


async def test_invalid_cli_usage_cannot_poison_totals(monkeypatch):
    cli_reply(monkeypatch, {"result": "ok", "total_cost_usd": "NaN",
        "duration_ms": "Infinity", "usage": {"input_tokens": -9,
            "output_tokens": {}, "cache_read_input_tokens": "Infinity"}})
    result = await ClaudeCliRunner().arun("p", "s")
    assert (result.cost_usd, result.input_tokens, result.output_tokens, result.duration_ms) == (0, 0, 0, 0)
    assert not result.usage_reported


@pytest.mark.parametrize("payload,budget", [
    ({"usage": {"output_tokens": 1}}, {"budget_usd": 1}),
    ({"usage": {"input_tokens": 1, "output_tokens": 1}}, {"budget_usd": 1}),
    ({"total_cost_usd": .1}, {"budget_tokens": 100}),
    ({"total_cost_usd": .1, "usage": {"input_tokens": 1}}, {"budget_tokens": 100}),
])
async def test_partial_telemetry_stops_budgeted_calls_instead_of_claiming_zero(monkeypatch, payload, budget):
    commands = cli_reply(monkeypatch, {"result": "ok", **payload})
    p = Pipeline(ProjectState(id="partial-telemetry", name="n", goal="g", **budget), ClaudeCliRunner())
    result = await p._tracked.arun("p", "s")
    assert not result.usage_reported
    assert p.state.usage.unreported_calls == 1
    assert p._stop_requested
    with pytest.raises(AgentError, match="non lancé"):
        await p._tracked.arun("retry", "s")
    assert len(commands) == 1


async def test_complete_zero_telemetry_is_not_mistaken_for_missing_usage(monkeypatch):
    cli_reply(monkeypatch, {"result": "ok", "total_cost_usd": 0,
                           "usage": {"input_tokens": 0, "output_tokens": 0}})
    result = await ClaudeCliRunner().arun("p", "s")
    assert result.usage_reported


async def test_claude_receives_remaining_estimated_budget(monkeypatch):
    commands = cli_reply(monkeypatch, {"result": "ok"})
    token = active_budget_usd.set(.123456)
    try:
        await ClaudeCliRunner().arun("p", "s")
    finally:
        active_budget_usd.reset(token)
    assert commands[0][commands[0].index("--max-budget-usd") + 1] == "0.123456"
    await ClaudeCliRunner().arun("p", "s")
    assert "--max-budget-usd" not in commands[1]


async def test_zero_remaining_budget_never_launches_cli(monkeypatch):
    commands = cli_reply(monkeypatch, {"result": "never"})
    token = active_budget_usd.set(0)
    try:
        with pytest.raises(AgentError) as error:
            await ClaudeCliRunner().arun("p", "s")
        assert error.value.budget_exhausted
    finally:
        active_budget_usd.reset(token)
    assert not commands


class Results:
    def __init__(self, *results):
        self.results = list(results)
        self.calls = 0
        self.budgets = []

    async def arun(self, *args, **kwargs):
        self.calls += 1
        self.budgets.append(active_budget_usd.get())
        result = self.results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result


async def test_effective_estimates_match_all_usage_ledgers(monkeypatch):
    monkeypatch.setattr(settings, "role_routing_enabled", True)
    monkeypatch.setattr(settings, "tier_price_in", {"worker": 1.0})
    monkeypatch.setattr(settings, "tier_price_out", {"worker": 3.0})
    runner = Results(AgentResult("ok", input_tokens=1_000_000, output_tokens=2_000_000))
    p = Pipeline(ProjectState(id="estimate", name="n", goal="g"), runner)
    await p._tracked.arun("p", persona("dev"))
    total, iteration = p.state.usage, p.state.iteration_usage[p.state.iteration]
    assert total.model_dump() == iteration.model_dump()
    assert total.cost_usd == 7.0
    assert p.interactions.for_item(f"phase:{p.state.phase.value}")[-1].cost_usd == 7.0


async def test_failed_call_effective_estimate_matches_ledger_and_interaction(monkeypatch):
    monkeypatch.setattr(settings, "tier_price_in", {"worker": 1.0})
    monkeypatch.setattr(settings, "tier_price_out", {"worker": 3.0})
    runner = Results(AgentError("failed response", usage=AgentResult(
        "", cost_usd=0, input_tokens=1_000_000, output_tokens=2_000_000,
    )))
    p = Pipeline(ProjectState(id="failed-estimate", name="n", goal="g"), runner)
    with pytest.raises(AgentError, match="failed response"):
        await p._tracked.arun("p", persona("dev"))
    total, iteration = p.state.usage, p.state.iteration_usage[p.state.iteration]
    interaction = p.interactions.for_item(f"phase:{p.state.phase.value}")[-1]
    assert total.model_dump() == iteration.model_dump()
    assert total.cost_usd == interaction.cost_usd == 7.0
    assert total.failed_calls == 1 and not interaction.ok


async def test_failures_keep_known_usage_and_mark_unknown_calls():
    runner = Results(AgentError("response error", usage=AgentResult("", cost_usd=.4, input_tokens=42)),
                     AgentError("timeout"))
    p = Pipeline(ProjectState(id="errors", name="n", goal="g"), runner)
    for _ in range(2):
        with pytest.raises(AgentError):
            await p._tracked.arun("p", "s")
    assert p.state.usage.cost_usd == .4
    assert p.state.usage.input_tokens == 42
    assert p.state.usage.agent_calls == 2
    assert p.state.usage.failed_calls == 2
    assert p.state.usage.unreported_calls == 1
    assert p.state.usage.model_dump() == p.state.iteration_usage[p.state.iteration].model_dump()


async def test_missing_usage_with_budget_stops_automatic_retries():
    runner = Results(AgentError("timeout"), AgentResult("must not run"))
    p = Pipeline(ProjectState(id="unknown-budget", name="n", goal="g", budget_usd=1), runner)
    with pytest.raises(AgentError):
        await p._tracked.arun("p", "s")
    with pytest.raises(AgentError, match="non lancé"):
        await p._tracked.arun("retry", "s")
    assert p._stop_requested and runner.calls == 1
    assert p.state.usage.unreported_calls == 1
    assert any("reprise explicite" in message.content for message in p.state.chat)


async def test_cancelled_call_is_not_reported_as_free_and_restores_context():
    p = Pipeline(ProjectState(id="cancel-usage", name="n", goal="g"), Results(asyncio.CancelledError()))
    registry = ProcessRegistry()
    token = active_processes.set(registry)
    skills = active_skills_enabled.set(True)
    try:
        with pytest.raises(asyncio.CancelledError):
            await p._tracked.arun("p", "s")
        assert active_processes.get() is registry
        assert active_skills_enabled.get() is True
        assert active_budget_usd.get() is None
    finally:
        active_processes.reset(token)
        active_skills_enabled.reset(skills)
    assert p.state.usage.unreported_calls == p.state.usage.failed_calls == 1


async def test_parallel_budgeted_calls_cannot_all_spend_remaining_budget():
    class Slow(Results):
        async def arun(self, *args, **kwargs):
            await asyncio.sleep(.01)
            return await super().arun(*args, **kwargs)
    runner = Slow(AgentResult("ok", cost_usd=1), AgentResult("never"), AgentResult("never"))
    p = Pipeline(ProjectState(id="budget-queue", name="n", goal="g", budget_usd=1), runner)
    results = await asyncio.gather(*(p._tracked.arun("p", "s") for _ in range(3)), return_exceptions=True)
    assert runner.calls == 1
    assert runner.budgets == [1]
    assert sum(isinstance(result, AgentError) for result in results) == 2
    assert p.state.usage.agent_calls == 1  # rejected calls were never attempted
    assert p._stop_requested


async def test_budget_added_in_flight_waits_for_all_previously_unbudgeted_calls():
    class Pending:
        def __init__(self):
            self.allowances = []
            self.started = [asyncio.Event(), asyncio.Event()]
            self.release = [asyncio.Event(), asyncio.Event()]
        async def arun(self, *args, **kwargs):
            index = len(self.allowances)
            allowance = active_budget_usd.get()
            self.allowances.append(allowance)
            if index < 2:
                self.started[index].set()
                await self.release[index].wait()
                return AgentResult("existing", cost_usd=.3)
            return AgentResult("new", cost_usd=allowance)
    runner = Pending()
    p = Pipeline(ProjectState(id="new-budget", name="n", goal="g"), runner)
    first = asyncio.create_task(p._tracked.arun("one", "s"))
    second = asyncio.create_task(p._tracked.arun("two", "s"))
    await asyncio.wait_for(asyncio.gather(*(event.wait() for event in runner.started)), 2)
    p.state.budget_usd = 1
    p._enforce_budget()  # same update as the budget API
    queued = asyncio.create_task(p._tracked.arun("three", "s"))
    await asyncio.sleep(0)
    assert runner.allowances == [None, None]
    runner.release[0].set()
    await first
    await asyncio.sleep(0)
    assert runner.allowances == [None, None]
    runner.release[1].set()
    await asyncio.wait_for(asyncio.gather(second, queued), 2)
    assert runner.allowances == [None, None, pytest.approx(.4)]
    assert p.state.usage.cost_usd == pytest.approx(1)
    assert p._tracked._active_calls == 0 and p._tracked._idle.is_set()


async def test_cancelling_budget_waiter_does_not_consume_usage_or_leak_admission():
    started, release = asyncio.Event(), asyncio.Event()
    class Pending:
        def __init__(self): self.calls = 0
        async def arun(self, *args, **kwargs):
            self.calls += 1
            started.set()
            await release.wait()
            return AgentResult("ok", cost_usd=.1)
    runner = Pending()
    p = Pipeline(ProjectState(id="cancel-budget-wait", name="n", goal="g"), runner)
    running = asyncio.create_task(p._tracked.arun("one", "s"))
    await asyncio.wait_for(started.wait(), 2)
    p.state.budget_usd = 1
    queued = asyncio.create_task(p._tracked.arun("two", "s"))
    await asyncio.sleep(0)
    queued.cancel()
    with pytest.raises(asyncio.CancelledError):
        await queued
    release.set()
    await running
    assert p.state.usage.agent_calls == runner.calls == 1
    assert p._tracked._active_calls == 0 and p._tracked._idle.is_set()
    await asyncio.wait_for(p._tracked.arun("three", "s"), 2)
    assert p.state.usage.agent_calls == runner.calls == 2


async def test_running_cancellation_releases_new_budget_waiter_without_launching_it():
    started = asyncio.Event()
    class Pending:
        def __init__(self): self.calls = 0
        async def arun(self, *args, **kwargs):
            self.calls += 1
            started.set()
            await asyncio.Event().wait()
    runner = Pending()
    p = Pipeline(ProjectState(id="cancel-budget-active", name="n", goal="g"), runner)
    running = asyncio.create_task(p._tracked.arun("one", "s"))
    await asyncio.wait_for(started.wait(), 2)
    p.state.budget_usd = 1
    queued = asyncio.create_task(p._tracked.arun("two", "s"))
    await asyncio.sleep(0)
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running
    with pytest.raises(AgentError, match="non lancé"):
        await asyncio.wait_for(queued, 2)
    assert runner.calls == p.state.usage.agent_calls == 1
    assert p.state.usage.unreported_calls == 1
    assert p._tracked._active_calls == 0 and p._tracked._idle.is_set()


async def test_remaining_budget_recomputed_between_calls():
    runner = Results(AgentResult("one", cost_usd=.25), AgentResult("two", cost_usd=.25))
    p = Pipeline(ProjectState(id="remaining", name="n", goal="g", budget_usd=1), runner)
    await p._tracked.arun("p", "s")
    await p._tracked.arun("p", "s")
    assert runner.budgets == [1, .75]


async def test_native_cli_budget_stop_prevents_retry_even_below_meter_limit(monkeypatch):
    commands = cli_reply(monkeypatch, {"result": "native guard", "subtype": "error_max_budget_usd",
        "total_cost_usd": .8, "usage": {"input_tokens": 50}})
    p = Pipeline(ProjectState(id="native-limit", name="n", goal="g", budget_usd=1), ClaudeCliRunner())
    with pytest.raises(AgentError):
        await p._tracked.arun("p", "s")
    assert p._stop_requested
    assert p.state.usage.cost_usd == .8
    with pytest.raises(AgentError, match="non lancé"):
        await p._tracked.arun("retry", "s")
    assert len(commands) == 1


async def test_cached_tokens_exhaust_token_budget_before_next_call(monkeypatch):
    commands = cli_reply(monkeypatch, {"result": "ok", "usage": {"cache_read_input_tokens": 500}})
    p = Pipeline(ProjectState(id="cache-budget", name="n", goal="g", budget_tokens=100), ClaudeCliRunner())
    await p._tracked.arun("p", "s")
    with pytest.raises(AgentError, match="non lancé"):
        await p._tracked.arun("p", "s")
    assert len(commands) == 1


async def test_without_budget_parallel_calls_remain_parallel():
    class Parallel:
        def __init__(self):
            self.started = 0
            self.both = asyncio.Event()
        async def arun(self, *args, **kwargs):
            self.started += 1
            if self.started == 2:
                self.both.set()
            await asyncio.wait_for(self.both.wait(), timeout=2)
            return AgentResult("ok")
    runner = Parallel()
    p = Pipeline(ProjectState(id="parallel", name="n", goal="g"), runner)
    await asyncio.gather(p._tracked.arun("p", "s"), p._tracked.arun("p", "s"))
    assert p.state.usage.agent_calls == 2


@pytest.mark.parametrize("amount", ["NaN", "Infinity", "-Infinity"])
def test_api_refuses_nonfinite_budgets(amount):
    from pydantic import ValidationError
    from autospec.api.server import CreateProjectRequest, BudgetRequest
    for schema, data in ((CreateProjectRequest, {"goal": "g", "budget_usd": amount}),
                         (BudgetRequest, {"budget_usd": amount})):
        with pytest.raises(ValidationError):
            schema.model_validate(data)


@pytest.mark.parametrize("amount", ["NaN", "Infinity", "-Infinity"])
def test_nonfinite_environment_timeouts_and_prices_use_safe_default(monkeypatch, amount):
    from autospec.config import _env_float
    monkeypatch.setenv("AUTOSPEC_TEST_FLOAT", amount)
    assert _env_float("AUTOSPEC_TEST_FLOAT", 30.0, minimum=1.0) == 30.0
