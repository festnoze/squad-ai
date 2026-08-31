"""Acceptance tests for the budgets and the parallelism (A13, T2.5, FR-6.2.3).

CONTRACTS sections 7.16 and 13. Five test names are cited by the traceability
rows of section 11 and are therefore normative, not decorative:
``test_budget_cap_enforced``, ``test_token_cap_enforced``,
``test_per_tick_tokens_equal_per_call_tokens``, ``test_calls_run_in_parallel``
and ``test_slow_agent_does_not_extend_tick_beyond_timeout``.

How the provider is faked, and why that is honest
-------------------------------------------------
:class:`FakeProviderGateway` does exactly what A14's ``ClaudeCliGateway`` does
around a call, in the same order: ``check(scope="call")``, ``check(scope="match")``,
``check_tokens(...)``, then the call, then ``record(reply)``. Everything it
does not do (spawn a process, parse stdout) is A14's, and is tested in
``test_gateway_claude_cli.py``. The budget arithmetic, the fallback and the
parallelism are A13's and are tested here against the real
:class:`~pxe.gateway.budget.BudgetTracker` and the real
:class:`~pxe.gateway.protocol.BaseGateway`.

The anti vacuous rule (section 10) is applied through
:func:`assert_replies_cover` and, for the tracker only tests, by asserting the
tracker actually recorded a call before claiming anything about its totals.
"""

import asyncio
import time
from collections.abc import Mapping, Sequence

import pytest

from pxe.errors import BudgetExceededError, InvalidConfigError
from pxe.gateway.budget import BudgetTracker
from pxe.gateway.protocol import AgentReply, BaseGateway
from pxe.types import (
    DEFAULT_PREDICTION_PPM,
    AgentSource,
    GatewayConfig,
    MarketObservation,
    MarketStatus,
    MatchConfig,
    Observation,
    ObservationLimits,
    RejectReason,
    make_agent_id,
    make_market_id,
)

#: An empty but schema shaped action payload. The gateway never validates it.
EMPTY_ACTION: Mapping[str, object] = {
    "action_version": "1.0",
    "predictions": [],
    "orders": [],
    "message_public": None,
    "rationale": None,
}


# ---------------------------------------------------------------------------
# Scaffolding
# ---------------------------------------------------------------------------
def make_observation(*, agent_id: str, tick: int = 1) -> Observation:
    """Build a minimal one market observation for one seat.

    Args:
        agent_id: The seat.
        tick: The tick it describes.

    Returns:
        A complete ``Observation``. The fake provider never reads it; it exists
        because ``acollect_actions`` is driven by observations.
    """
    config = MatchConfig(seed=20260827)
    market = MarketObservation(
        market_id=make_market_id(1),
        question="toy question",
        status=MarketStatus.OPEN,
        prior_price=50,
        resolution_tick=config.ticks_total,
        ref_price=50,
        mid_price=50,
        best_bid=49,
        best_ask=51,
        bid_depth=((49, 100),),
        ask_depth=((51, 100),),
        last_price=50,
        ref_history=(50,),
        position_qty=0,
        cost_basis_cents=0,
        my_orders=(),
        my_last_prediction_ppm=DEFAULT_PREDICTION_PPM,
    )
    return Observation(
        obs_version=config.obs_version,
        match_id="m-election-20260827-01",
        tick=tick,
        ticks_total=config.ticks_total,
        agent_id=agent_id,
        cash_cents=config.initial_cash_cents,
        reserved_cents=0,
        free_cash_cents=config.initial_cash_cents,
        equity_cents=config.initial_cash_cents,
        news=(),
        signals=(),
        markets=(market,),
        messages=(),
        limits=ObservationLimits(
            max_active_orders_per_market=config.max_active_orders_per_market,
            price_min=1,
            price_max=99,
            market_band_cents=config.market_band_cents,
            taker_fee_bps=config.taker_fee_bps,
            message_max_chars=config.message_max_chars,
            max_orders_per_action=config.max_orders_per_action,
        ),
    )


def seat_ids(n: int) -> tuple[str, ...]:
    """Return the first ``n`` ranked seat ids.

    Args:
        n: How many seats.

    Returns:
        ``("A1", ..., "An")``.
    """
    return tuple(make_agent_id(index) for index in range(1, n + 1))


def observations_for(seats: Sequence[str], *, tick: int = 1) -> tuple[Observation, ...]:
    """Build one observation per seat.

    Args:
        seats: The seats to build for.
        tick: The tick to describe.

    Returns:
        One observation per seat, in seat order.
    """
    return tuple(make_observation(agent_id=agent_id, tick=tick) for agent_id in seats)


def assert_replies_cover(replies: Sequence[AgentReply], seats: Sequence[str]) -> None:
    """Assert the reply tuple is non empty and covers exactly ``seats``.

    Args:
        replies: What the gateway returned.
        seats: The seats that were asked.
    """
    assert replies, "the gateway returned no reply at all"
    assert len(replies) == len(seats), f"expected {len(seats)} replies, got {len(replies)}"
    assert [reply.agent_id for reply in replies] == sorted(seats)


class FakeProviderGateway(BaseGateway):
    """A gateway that spends a fixed cost and a fixed number of tokens per call.

    It performs the same budget dance as A14's CLI adapter: both caps checked
    before the call is sent, so a breach costs nothing, and the reply recorded
    after it returns.
    """

    def __init__(
        self,
        *,
        gateway_config: GatewayConfig,
        budget: BudgetTracker,
        cost_usd: float = 0.01,
        input_tokens: int = 120,
        output_tokens: int = 60,
        cached_input_tokens: int = 35_000,
        delay_s: float = 0.0,
        slow_seats: Mapping[str, float] | None = None,
    ) -> None:
        """Bind the per call cost, the token counts and the fake latency.

        Args:
            gateway_config: Timeouts, caps and parallelism.
            budget: The tracker to check against and record into.
            cost_usd: Cost reported for every call.
            input_tokens: Non cached input tokens reported for every call.
            output_tokens: Output tokens reported for every call.
            cached_input_tokens: Cached input tokens reported for every call.
                Large on purpose: the CLI overhead is about 35k and must not be
                budgeted.
            delay_s: Sleep applied to every call.
            slow_seats: Per seat sleep, overriding ``delay_s``.
        """
        super().__init__(gateway_config=gateway_config, budget=budget)
        self._cost_usd = cost_usd
        self._input_tokens = input_tokens
        self._output_tokens = output_tokens
        self._cached_input_tokens = cached_input_tokens
        self._delay_s = delay_s
        self._slow_seats = dict(slow_seats or {})
        #: Every ``(agent_id, tick)`` whose call reached the provider.
        self.sent: list[tuple[str, int]] = []
        self.live = 0
        self.peak = 0

    async def acall_agent(self, *, agent_id: str, observation: Observation, tick: int) -> AgentReply:
        """Check the budgets, sleep, answer and record.

        Args:
            agent_id: The seat being called.
            observation: The observation to answer. Unused by the fake.
            tick: The tick being decided.

        Returns:
            A successful reply carrying the configured cost and token counts.

        Raises:
            BudgetExceededError: If a cap refuses the call. The bridge turns it
                into the FR-5.1.1 fallback.
        """
        del observation
        budget = self.budget
        assert budget is not None
        budget.check(scope="call", amount_usd=self._cost_usd)
        budget.check(scope="match", amount_usd=self._cost_usd)
        budget.check_tokens(
            input_tokens=self._input_tokens,
            output_tokens=self._output_tokens,
            agent_id=agent_id,
            tick=tick,
        )
        self.sent.append((agent_id, tick))
        self.live += 1
        self.peak = max(self.peak, self.live)
        try:
            delay = self._slow_seats.get(agent_id, self._delay_s)
            if delay > 0.0:
                await asyncio.sleep(delay)
            reply = AgentReply(
                agent_id=agent_id,
                raw=dict(EMPTY_ACTION),
                raw_text="{}",
                source=AgentSource.LLM,
                error=None,
                cost_usd=self._cost_usd,
                latency_ms=int(delay * 1000),
                input_tokens=self._input_tokens,
                output_tokens=self._output_tokens,
                cached_input_tokens=self._cached_input_tokens,
                attempts=1,
            )
        finally:
            self.live -= 1
        budget.record(reply, tick=tick)
        return reply


def make_reply(agent_id: str, *, cost_usd: float, input_tokens: int, output_tokens: int) -> AgentReply:
    """Build a successful reply carrying the given telemetry.

    Args:
        agent_id: The seat.
        cost_usd: Cost to report.
        input_tokens: Non cached input tokens to report.
        output_tokens: Output tokens to report.

    Returns:
        The reply.
    """
    return AgentReply(
        agent_id=agent_id,
        raw=dict(EMPTY_ACTION),
        raw_text="{}",
        source=AgentSource.LLM,
        error=None,
        cost_usd=cost_usd,
        latency_ms=1,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_input_tokens=35_000,
    )


# ---------------------------------------------------------------------------
# The five tests section 11 names
# ---------------------------------------------------------------------------
async def test_budget_cap_enforced() -> None:
    """T2.5: the per match USD cap holds, and a breach costs nothing.

    Six seats, a cap of 0.05 USD and a cost of 0.02 USD per call: two calls fit,
    the other four are refused **before** being sent, become the FR-5.1.1
    fallback and the match continues.
    """
    seats = seat_ids(6)
    config = GatewayConfig(
        timeout_s=5.0,
        max_budget_usd_per_call=0.02,
        max_budget_usd_per_match=0.05,
        max_parallel_calls=1,  # sequential, so "which two fit" is deterministic
    )
    budget = BudgetTracker(config)
    gateway = FakeProviderGateway(gateway_config=config, budget=budget, cost_usd=0.02)
    replies = await gateway.acollect_actions(tick=1, observations=observations_for(seats), config=MatchConfig(seed=1))
    assert_replies_cover(replies, seats)
    accepted = [reply for reply in replies if reply.ok]
    refused = [reply for reply in replies if not reply.ok]
    assert len(accepted) == 2, "the cap let through the wrong number of calls"
    assert len(refused) == 4
    for reply in refused:
        assert reply.error is RejectReason.BUDGET_EXCEEDED
        assert reply.source is AgentSource.FALLBACK
        assert reply.raw is None
        assert reply.cost_usd == 0.0, "a refused call must cost nothing"
    assert gateway.sent == [("A1", 1), ("A2", 1)], "a refused call still reached the provider"
    assert budget.calls("match") == 2
    assert budget.spent_usd("match") <= config.max_budget_usd_per_match
    assert budget.remaining_usd("match") == pytest.approx(0.01)


async def test_token_cap_enforced() -> None:
    """FR-6.2.3: an oversized call is refused before it is sent, and costs nothing."""
    seats = seat_ids(3)
    config = GatewayConfig(
        timeout_s=5.0,
        max_input_tokens_per_call=100,
        max_output_tokens_per_call=50,
        max_parallel_calls=3,
    )
    budget = BudgetTracker(config)
    gateway = FakeProviderGateway(gateway_config=config, budget=budget, input_tokens=5_000, output_tokens=10)
    replies = await gateway.acollect_actions(tick=2, observations=observations_for(seats), config=MatchConfig(seed=1))
    assert_replies_cover(replies, seats)
    for reply in replies:
        assert reply.error is RejectReason.BUDGET_EXCEEDED
        assert reply.source is AgentSource.FALLBACK
    assert gateway.sent == [], "an oversized call was sent to the provider"
    assert budget.spent_tokens("match") == (0, 0)
    assert budget.spent_usd("match") == 0.0
    # The output side is capped too, independently.
    with pytest.raises(BudgetExceededError):
        budget.check_tokens(input_tokens=10, output_tokens=51)
    budget.check_tokens(input_tokens=100, output_tokens=50)  # exactly at the caps: legal


async def test_per_tick_tokens_equal_per_call_tokens() -> None:
    """Decision 14: one call per agent per tick, so per tick equals per call.

    This is the test that fails loudly the day a second provider call per tick
    appears, which is exactly what CONTRACTS section 7.16 asks it to do.
    """
    seats = seat_ids(5)
    ticks = (1, 2, 3, 4)
    config = GatewayConfig(timeout_s=5.0, max_budget_usd_per_match=100.0, max_parallel_calls=5)
    budget = BudgetTracker(config)
    gateway = FakeProviderGateway(
        gateway_config=config, budget=budget, cost_usd=0.001, input_tokens=120, output_tokens=60
    )
    for tick in ticks:
        replies = await gateway.acollect_actions(
            tick=tick, observations=observations_for(seats, tick=tick), config=MatchConfig(seed=1)
        )
        assert_replies_cover(replies, seats)
        assert all(reply.ok for reply in replies)
    assert budget.calls("match") == len(seats) * len(ticks)
    for tick in ticks:
        for agent_id in seats:
            assert budget.tick_tokens(agent_id, tick) == (120, 60), f"{agent_id} at tick {tick}"
    assert budget.spent_tokens("call") == (120, 60), "the last call and the tick must agree"
    assert budget.spent_tokens("match") == (120 * 20, 60 * 20)
    # A tick nobody played has no tokens, which is what makes the equality above
    # a claim and not a tautology.
    assert budget.tick_tokens("A1", 99) == (0, 0)


async def test_calls_run_in_parallel() -> None:
    """T2.5: the calls of a tick overlap, bounded by ``max_parallel_calls``."""
    seats = seat_ids(6)
    delay_s = 0.15
    config = GatewayConfig(timeout_s=5.0, max_budget_usd_per_match=100.0, max_parallel_calls=6)
    budget = BudgetTracker(config)
    gateway = FakeProviderGateway(gateway_config=config, budget=budget, cost_usd=0.0, delay_s=delay_s)
    started = time.perf_counter()
    replies = await gateway.acollect_actions(tick=1, observations=observations_for(seats), config=MatchConfig(seed=1))
    elapsed_s = time.perf_counter() - started
    assert_replies_cover(replies, seats)
    assert all(reply.ok for reply in replies)
    assert gateway.peak == 6, f"only {gateway.peak} calls were ever in flight at once"
    sequential_s = delay_s * len(seats)
    assert elapsed_s < sequential_s / 2, f"{elapsed_s:.2f}s for six {delay_s}s calls, that is sequential"

    # And the bound is honoured: with a parallelism of two, two are in flight.
    narrow = GatewayConfig(timeout_s=5.0, max_budget_usd_per_match=100.0, max_parallel_calls=2)
    throttled = FakeProviderGateway(gateway_config=narrow, budget=BudgetTracker(narrow), cost_usd=0.0, delay_s=0.02)
    replies = await throttled.acollect_actions(tick=1, observations=observations_for(seats), config=MatchConfig(seed=1))
    assert_replies_cover(replies, seats)
    assert throttled.peak == 2, f"the parallelism bound was ignored, peak was {throttled.peak}"


async def test_slow_agent_does_not_extend_tick_beyond_timeout() -> None:
    """T2.5: one agent's timeout does not stretch the tick beyond the bound."""
    seats = seat_ids(6)
    timeout_s = 0.1
    config = GatewayConfig(timeout_s=timeout_s, max_budget_usd_per_match=100.0, max_parallel_calls=len(seats))
    budget = BudgetTracker(config)
    gateway = FakeProviderGateway(
        gateway_config=config,
        budget=budget,
        cost_usd=0.0,
        delay_s=0.0,
        slow_seats={"A3": 30.0},  # a provider that never answers
    )
    started = time.perf_counter()
    replies = await gateway.acollect_actions(tick=1, observations=observations_for(seats), config=MatchConfig(seed=1))
    elapsed_s = time.perf_counter() - started
    assert_replies_cover(replies, seats)
    by_id = {reply.agent_id: reply for reply in replies}
    assert by_id["A3"].error is RejectReason.AGENT_TIMEOUT
    assert by_id["A3"].source is AgentSource.FALLBACK
    assert all(by_id[agent_id].ok for agent_id in seats if agent_id != "A3")
    # One wave of six parallel calls: the tick is bounded by one timeout, not by
    # the thirty second sleep and not by six timeouts.
    assert elapsed_s < 1.0, f"the tick took {elapsed_s:.2f}s for a {timeout_s}s timeout"


async def test_the_tick_bound_is_one_timeout_per_wave() -> None:
    """The documented bound: ``ceil(n / max_parallel_calls) * timeout_s``."""
    seats = seat_ids(4)
    config = GatewayConfig(timeout_s=0.1, max_budget_usd_per_match=100.0, max_parallel_calls=2)
    budget = BudgetTracker(config)
    gateway = FakeProviderGateway(gateway_config=config, budget=budget, cost_usd=0.0, delay_s=30.0)
    started = time.perf_counter()
    replies = await gateway.acollect_actions(tick=1, observations=observations_for(seats), config=MatchConfig(seed=1))
    elapsed_s = time.perf_counter() - started
    assert_replies_cover(replies, seats)
    assert all(reply.error is RejectReason.AGENT_TIMEOUT for reply in replies)
    assert elapsed_s < 1.5, f"four calls in two waves of a 0.1s timeout took {elapsed_s:.2f}s"


# ---------------------------------------------------------------------------
# The tracker itself
# ---------------------------------------------------------------------------
def test_record_accumulates_cost_and_tokens() -> None:
    """The three scopes accumulate what the replies reported."""
    config = GatewayConfig(max_budget_usd_per_match=1.0, max_budget_usd_per_tournament=10.0)
    budget = BudgetTracker(config)
    budget.note_tick(7)
    for index in range(1, 4):
        budget.record(make_reply(make_agent_id(index), cost_usd=0.03, input_tokens=100, output_tokens=40))
    assert budget.calls("match") == 3, "nothing was recorded, the assertions below would be vacuous"
    assert budget.spent_usd("match") == pytest.approx(0.09)
    assert budget.spent_usd("tournament") == pytest.approx(0.09)
    assert budget.spent_usd("call") == pytest.approx(0.03)
    assert budget.spent_tokens("match") == (300, 120)
    assert budget.spent_tokens("call") == (100, 40)
    assert budget.remaining_usd("match") == pytest.approx(0.91)
    assert budget.remaining_usd("tournament") == pytest.approx(9.91)
    # note_tick is how a reply that carries no tick still lands on one.
    assert budget.tick_tokens("A1", 7) == (100, 40)
    assert budget.tick_tokens("A1", 8) == (0, 0)


def test_cached_input_tokens_are_not_budgeted() -> None:
    """The 35k tokens of CLI overhead would breach every cap if they counted."""
    config = GatewayConfig(max_input_tokens_per_call=8_192, max_budget_usd_per_match=1.0)
    budget = BudgetTracker(config)
    budget.record(make_reply("A1", cost_usd=0.02, input_tokens=1_000, output_tokens=100))
    assert budget.calls("match") == 1
    assert budget.spent_tokens("match") == (1_000, 100), "cached input tokens leaked into the budget"
    budget.check_tokens(input_tokens=1_000, output_tokens=100, agent_id="A1")


def test_the_cumulative_match_token_cap_is_the_runaway_guard() -> None:
    """``max_tokens_per_match`` bounds a runaway match, and ``0`` disables it."""
    config = GatewayConfig(max_tokens_per_match=500, max_budget_usd_per_match=10.0)
    budget = BudgetTracker(config)
    budget.record(make_reply("A1", cost_usd=0.0, input_tokens=300, output_tokens=100))
    assert budget.spent_tokens("match") == (300, 100)
    with pytest.raises(BudgetExceededError):
        budget.check_tokens(input_tokens=200, output_tokens=1, agent_id="A1")
    # The cap is read per agent when the seat is known, which is how
    # GatewayConfig documents it: A2 has spent nothing.
    budget.check_tokens(input_tokens=200, output_tokens=1, agent_id="A2")
    # Without a seat it is the whole match that is guarded.
    with pytest.raises(BudgetExceededError):
        budget.check_tokens(input_tokens=200, output_tokens=1)
    unlimited = BudgetTracker(
        GatewayConfig(max_tokens_per_match=0, max_input_tokens_per_call=0, max_output_tokens_per_call=0)
    )
    unlimited.check_tokens(input_tokens=10**7, output_tokens=10**6)


def test_the_call_scope_does_not_accumulate() -> None:
    """A call is checked against its own cap, not against the calls before it."""
    budget = BudgetTracker(GatewayConfig(max_budget_usd_per_call=0.05, max_budget_usd_per_match=10.0))
    for _ in range(10):
        budget.check(scope="call", amount_usd=0.05)
        budget.record(make_reply("A1", cost_usd=0.05, input_tokens=1, output_tokens=1))
    assert budget.calls("match") == 10
    assert budget.spent_usd("match") == pytest.approx(0.5)
    assert budget.remaining_usd("call") == pytest.approx(0.05)
    with pytest.raises(BudgetExceededError):
        budget.check(scope="call", amount_usd=0.06)


def test_spending_exactly_to_the_cap_is_legal() -> None:
    """A float epsilon must not turn a legal call into a fallback."""
    budget = BudgetTracker(GatewayConfig(max_budget_usd_per_match=0.30))
    for _ in range(3):
        budget.check(scope="match", amount_usd=0.10)
        budget.record(make_reply("A1", cost_usd=0.10, input_tokens=1, output_tokens=1))
    assert budget.calls("match") == 3
    assert budget.spent_usd("match") == pytest.approx(0.30)
    assert budget.remaining_usd("match") == pytest.approx(0.0, abs=1e-9)
    with pytest.raises(BudgetExceededError):
        budget.check(scope="match", amount_usd=0.01)


def test_reset_match_keeps_the_tournament_total() -> None:
    """A tournament reuses one tracker, so the match scope has to be releasable."""
    budget = BudgetTracker(GatewayConfig(max_budget_usd_per_match=1.0, max_budget_usd_per_tournament=10.0))
    budget.note_tick(3)
    budget.record(make_reply("A1", cost_usd=0.40, input_tokens=100, output_tokens=50))
    assert budget.spent_usd("match") == pytest.approx(0.40)
    budget.reset_match()
    assert budget.spent_usd("match") == 0.0
    assert budget.spent_tokens("match") == (0, 0)
    assert budget.tick_tokens("A1", 3) == (0, 0)
    assert budget.spent_usd("tournament") == pytest.approx(0.40)
    assert budget.calls("tournament") == 1


def test_unknown_scopes_and_negative_amounts_are_config_errors() -> None:
    """A typo in a scope name is a contract bug, not a budget breach."""
    budget = BudgetTracker(GatewayConfig())
    for scope in ("tick", "agent", "", "MATCH"):
        with pytest.raises(InvalidConfigError):
            budget.check(scope=scope, amount_usd=0.0)
        with pytest.raises(InvalidConfigError):
            budget.spent_usd(scope)
        with pytest.raises(InvalidConfigError):
            budget.spent_tokens(scope)
        with pytest.raises(InvalidConfigError):
            budget.remaining_usd(scope)
        with pytest.raises(InvalidConfigError):
            budget.calls(scope)
    with pytest.raises(InvalidConfigError):
        budget.check(scope="match", amount_usd=-1.0)
    with pytest.raises(InvalidConfigError):
        budget.check_tokens(input_tokens=-1, output_tokens=0)


async def test_a_gateway_without_a_budget_spends_nothing() -> None:
    """A scripted gateway has no budget attached and must not need one."""

    class Free(BaseGateway):
        async def acall_agent(self, *, agent_id: str, observation: Observation, tick: int) -> AgentReply:
            return AgentReply(
                agent_id=agent_id,
                raw=dict(EMPTY_ACTION),
                raw_text=None,
                source=AgentSource.SCRIPTED,
                error=None,
            )

    gateway = Free(gateway_config=GatewayConfig(timeout_s=1.0))
    assert gateway.budget is None
    seats = seat_ids(2)
    replies = await gateway.acollect_actions(tick=1, observations=observations_for(seats), config=MatchConfig(seed=1))
    assert_replies_cover(replies, seats)
    assert all(reply.ok and reply.cost_usd == 0.0 for reply in replies)
