"""A15 acceptance tests: the journal projection and the PRD 7.1 metrics.

Every test here starts from a **non empty** projection of a real journal and
asserts that the rows it is about to measure exist (CONTRACTS section 10's anti
vacuous rule). The three golden journals of ``tests/golden/`` are the primary
input: they are frozen bytes, so a projection regression shows up as a metric
change and not as a flaky engine run.

The four claims this file exists for:

* ``project`` populates every row family, so A16, A17, A18, A21 and A22 are not
  coding against five empty tuples that satisfy every type annotation.
* PnL is ``final_cash_cents - initial_cash_cents`` after settlement and it is
  derived from the executions and the outcomes only. AC-P4: rewriting every
  ``PredictionRecorded`` in the journal moves no performance number by one cent.
* ``PerformanceMetrics.pnl_bps`` equals the journalled
  ``MatchEnded.rankings[].pnl_pct_bps`` agent by agent, which is the only thing
  that catches A09 and A15 drifting to two formulas (section 9).
* ``final_ranking`` reproduces the settled ranking of ``MatchEnded`` and **not**
  the mark to market standings of the last tick (FR-5.5.4).
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from pxe.errors import InvalidConfigError
from pxe.events import (
    AgentFrozen,
    Event,
    MarketResolved,
    MarkToMarket,
    MatchEnded,
    MatchStarted,
    MessagePosted,
    OrderCancelled,
    OrderPlaced,
    PositionSnapshot,
    PredictionRecorded,
    SignalDelivered,
    TradeExecuted,
)
from pxe.journal import read_journal
from pxe.metrics.performance import (
    PerformanceMetrics,
    compute_performance,
    final_ranking,
    max_drawdown_cents_of,
    pnl_of,
    sharpe_milli_of,
)
from pxe.metrics.projection import MatchProjection, project
from pxe.rng import RngTree
from pxe.types import (
    MM_ACCOUNT_ID,
    Incident,
    IncidentKind,
    Outcome,
    Side,
    bps_ratio,
    make_incident_id,
)
from tests.test_match_runner import (
    GOLDEN_DIR,
    REFERENCE,
    SMALL,
    WIDE,
    Chatterbox,
    Recipe,
    Spendthrift,
    agents_of,
    config_of,
    custom_recipe,
    of_type,
    play_with_agents,
    world_of,
)

GOLDEN: tuple[Recipe, ...] = (REFERENCE, SMALL, WIDE)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def golden_events(recipe: Recipe) -> tuple[Event, ...]:
    """Read one frozen journal from ``tests/golden/``."""
    path = GOLDEN_DIR / f"{recipe.name}.journal.jsonl"
    assert path.exists(), f"missing golden journal for {recipe.name}"
    events = read_journal(path)
    assert events, "the golden journal read back empty, so every assertion below would be vacuous"
    return events


def match_ended_of(events: tuple[Event, ...]) -> MatchEnded:
    """Return the single ``MatchEnded`` of a finished journal."""
    ended = of_type(events, MatchEnded)
    assert len(ended) == 1, "a finished journal holds exactly one MatchEnded"
    last = ended[0]
    assert isinstance(last, MatchEnded)
    return last


@pytest.fixture(scope="module")
def reference() -> MatchProjection:
    """The projection of the reference golden match, built once."""
    return project(golden_events(REFERENCE))


# ---------------------------------------------------------------------------
# project: the row families
# ---------------------------------------------------------------------------
def test_projection_reads_the_whole_reference_journal(reference: MatchProjection) -> None:
    """The scalars come from MatchStarted and MatchEnded, never from a default."""
    events = golden_events(REFERENCE)
    started = of_type(events, MatchStarted)[0]
    assert isinstance(started, MatchStarted)
    ended = match_ended_of(events)

    assert reference.match_id == started.match_id
    assert reference.seed == started.seed
    assert reference.ticks_total == started.ticks_total == REFERENCE.ticks_total
    assert reference.initial_cash_cents == started.initial_cash_cents
    assert reference.mm_pnl_cents == ended.mm_pnl_cents
    assert reference.fees_collected_cents == ended.fees_collected_cents
    assert reference.agent_ids == tuple(f"A{index}" for index in range(1, len(REFERENCE.baselines) + 1))
    assert reference.market_ids == tuple(f"M{index}" for index in range(1, REFERENCE.n_markets + 1))
    assert MM_ACCOUNT_ID not in reference.agent_ids, "MM is not a ranked seat (section 2.3)"


@pytest.mark.parametrize("recipe", GOLDEN, ids=lambda recipe: recipe.name)
def test_every_row_family_is_populated(recipe: Recipe) -> None:
    """Anti vacuous: five empty tuples satisfy every annotation A16 codes against."""
    events = golden_events(recipe)
    projection = project(events)
    assert projection.trades, "no trade row"
    assert projection.orders, "no order row"
    assert projection.predictions, "no prediction row"
    assert projection.signals, "no signal row"
    assert projection.highlights, "no highlight"
    assert len(projection.trades) == len(of_type(events, TradeExecuted))
    assert len(projection.orders) == len(of_type(events, OrderPlaced))
    assert len(projection.predictions) == len(of_type(events, PredictionRecorded))
    assert len(projection.signals) == len(of_type(events, SignalDelivered))


def test_messages_are_projected_when_talking_mode_is_on() -> None:
    """The fifth row family needs FR-5.6.1, which no baseline exercises."""
    config = replace(config_of(SMALL), talking_mode=True)
    plain = world_of(SMALL)
    world = replace(plain, scenario=replace(plain.scenario, talking_mode=True))
    rng = RngTree(config.seed)
    seats = agents_of(SMALL, config, rng)
    for agent_id in seats:
        seats[agent_id] = Chatterbox(
            agent_id=agent_id, config=config, rng=rng.child(f"agent/{agent_id}").substream(f"agent.{agent_id}")
        )
    _result, events = play_with_agents(SMALL, factories=seats, config=config, world=world, rng=rng)
    posted = of_type(events, MessagePosted)
    assert posted, "talking mode produced no MessagePosted, so this test would be vacuous"

    projection = project(events)
    assert len(projection.messages) == len(posted)
    assert all(row.deliver_tick == row.tick + 1 for row in projection.messages)
    assert [(row.tick, row.agent_id) for row in projection.messages] == sorted(
        (row.tick, row.agent_id) for row in projection.messages
    )


@pytest.mark.parametrize("recipe", GOLDEN, ids=lambda recipe: recipe.name)
def test_rows_come_out_in_the_contracted_order(recipe: Recipe) -> None:
    """Section 7.17: the row order is part of the contract, not an accident."""
    projection = project(golden_events(recipe))
    assert projection.trades and projection.orders and projection.predictions and projection.signals
    rank = {agent_id: index for index, agent_id in enumerate(projection.agent_ids)}
    market_rank = {market_id: index for index, market_id in enumerate(projection.market_ids)}

    trades = [(row.tick, row.trade_id) for row in projection.trades]
    assert trades == sorted(trades)
    orders = [(row.placed_tick, row.order_id) for row in projection.orders]
    assert orders == sorted(orders)
    predictions = [(row.tick, rank[row.agent_id], market_rank[row.market_id]) for row in projection.predictions]
    assert predictions == sorted(predictions)
    signals = [(row.tick, rank[row.agent_id], row.signal_id) for row in projection.signals]
    assert signals == sorted(signals)
    highlights = [(row.tick, row.kind, row.market_id or "") for row in projection.highlights]
    assert highlights == sorted(highlights)


@pytest.mark.parametrize("recipe", GOLDEN, ids=lambda recipe: recipe.name)
def test_every_per_tick_series_has_length_ticks_total(recipe: Recipe) -> None:
    """Section 9: a resolution never shortens an array."""
    events = golden_events(recipe)
    projection = project(events)
    assert of_type(events, PositionSnapshot), "no PositionSnapshot, so the series would be padding only"
    assert of_type(events, MarkToMarket), "no MarkToMarket, so ref_price would be padding only"
    for _agent_id, series in projection.equity_cents:
        assert len(series) == projection.ticks_total
    for _agent_id, series in projection.cash_cents:
        assert len(series) == projection.ticks_total
    for _market_id, series in projection.ref_price:
        assert len(series) == projection.ticks_total
    assert len(projection.equity_cents) == len(projection.agent_ids)
    assert len(projection.ref_price) == len(projection.market_ids)


def test_equity_and_cash_series_are_the_position_snapshots(reference: MatchProjection) -> None:
    """The series are read, not recomputed: they must equal the journal values."""
    events = golden_events(REFERENCE)
    snapshots = [event for event in of_type(events, PositionSnapshot) if isinstance(event, PositionSnapshot)]
    assert snapshots
    for agent_id in reference.agent_ids:
        expected = [
            event.equity_cents
            for event in snapshots
            if event.account_id == agent_id and 1 <= event.tick <= reference.ticks_total
        ]
        assert len(expected) == reference.ticks_total
        assert list(reference.equity_series(agent_id)) == expected
        assert list(reference.cash_series(agent_id)) == [
            event.cash_cents
            for event in snapshots
            if event.account_id == agent_id and 1 <= event.tick <= reference.ticks_total
        ]


def test_a_resolved_market_keeps_its_last_reference_price() -> None:
    """Section 9: MarkToMarket stops at the resolution, the series does not.

    ``league_wide`` resolves ``M4`` at tick 22 of 24, so the last two entries of
    its ``ref_price`` series exist only because A15 pads them forward.
    """
    events = golden_events(WIDE)
    projection = project(events)
    resolved = [event for event in of_type(events, MarketResolved) if isinstance(event, MarketResolved)]
    early = [event for event in resolved if event.resolution_tick < projection.ticks_total]
    assert early, "no market resolved mid match, so the padding rule is untested here"
    target = early[0].market_id
    marks = [
        event
        for event in of_type(events, MarkToMarket)
        if isinstance(event, MarkToMarket) and event.market_id == target
    ]
    assert len(marks) < projection.ticks_total, "the market was marked on every tick, so nothing is padded"
    series = dict(projection.ref_price)[target]
    last_observed = marks[-1].ref_price
    assert series[marks[-1].tick - 1] == last_observed
    assert set(series[marks[-1].tick :]) == {last_observed}


@pytest.mark.parametrize("recipe", GOLDEN, ids=lambda recipe: recipe.name)
def test_outcomes_and_resolution_ticks(recipe: Recipe) -> None:
    """Outcomes cover the resolved markets, resolution ticks cover every market."""
    events = golden_events(recipe)
    projection = project(events)
    resolved = [event for event in of_type(events, MarketResolved) if isinstance(event, MarketResolved)]
    assert resolved
    assert dict(projection.outcomes) == {event.market_id: Outcome(event.outcome) for event in resolved}
    assert [market_id for market_id, _tick in projection.resolution_ticks] == list(projection.market_ids)
    scheduled = {event.market_id: event.resolution_tick for event in resolved}
    for market_id, tick in projection.resolution_ticks:
        assert tick == scheduled[market_id], "the scheduled tick disagrees with MarketResolved"
    assert projection.outcome_of(projection.market_ids[0]) is not None
    assert projection.outcome_of("M99") is None


def test_order_rows_fold_placement_fills_and_cancellation(reference: MatchProjection) -> None:
    """One OrderRecord folds OrderPlaced, TradeExecuted and OrderCancelled."""
    events = golden_events(REFERENCE)
    placed = {event.order_id: event for event in of_type(events, OrderPlaced) if isinstance(event, OrderPlaced)}
    cancelled = {
        event.order_id: event for event in of_type(events, OrderCancelled) if isinstance(event, OrderCancelled)
    }
    filled: dict[str, int] = {}
    for event in of_type(events, TradeExecuted):
        assert isinstance(event, TradeExecuted)
        for order_id in (event.maker_order_id, event.taker_order_id):
            filled[order_id] = filled.get(order_id, 0) + event.qty
    assert placed and cancelled and filled

    rows = {row.order_id: row for row in reference.orders}
    assert set(rows) == set(placed)
    for order_id, row in rows.items():
        source = placed[order_id]
        assert (row.agent_id, row.market_id, row.side, row.price, row.qty) == (
            source.agent_id,
            source.market_id,
            source.side,
            source.price,
            source.qty,
        )
        assert row.placed_tick == source.tick
        assert row.reserved_cents == source.reserved_cents
        assert row.filled_qty == filled.get(order_id, 0)
        assert row.filled_qty <= row.qty
        if order_id in cancelled:
            assert row.cancelled_tick == cancelled[order_id].tick
            assert row.cancel_reason == cancelled[order_id].reason
            assert row.released_cents == cancelled[order_id].released_cents
        else:
            assert row.cancelled_tick is None
            assert row.cancel_reason is None

    resting = [row for row in reference.orders if row.cancelled_tick is None]
    assert resting, "every order was cancelled, so the still resting branch is untested"


# ---------------------------------------------------------------------------
# Highlights
# ---------------------------------------------------------------------------
def test_big_trade_highlights_are_above_three_medians(reference: MatchProjection) -> None:
    """The threshold is exactly three times the integral median notional."""
    notionals = sorted(row.price * row.qty for row in reference.trades)
    assert notionals
    median = notionals[(len(notionals) - 1) // 2]
    expected = {row.trade_id for row in reference.trades if row.price * row.qty > 3 * median}
    assert expected, "no trade is outsized in the reference match"
    big = [row for row in reference.highlights if row.kind == "big_trade"]
    assert len(big) == len(expected)
    for row in big:
        assert row.magnitude_cents > 3 * median
        assert row.market_id in reference.market_ids
        assert len(row.agent_ids) == 2
        assert row.label.endswith("of notional.")


def test_an_early_resolution_is_a_highlight() -> None:
    """WIDE resolves M4 at tick 22 of 24, which PRD section 9 calls marking."""
    projection = project(golden_events(WIDE))
    early = [row for row in projection.highlights if row.kind == "early_resolution"]
    assert early, "league_wide no longer resolves a market mid match"
    row = early[0]
    assert row.market_id == "M4"
    assert row.tick == 23, "the highlight sits on the tick the resolution was emitted"
    assert row.agent_ids == ()
    assert "before the end of the match" in row.label


def test_no_early_resolution_highlight_when_every_market_matures_at_the_end(
    reference: MatchProjection,
) -> None:
    """Every market of REFERENCE resolves at T, so nothing resolved early."""
    assert all(tick == reference.ticks_total for _market_id, tick in reference.resolution_ticks)
    assert [row for row in reference.highlights if row.kind == "early_resolution"] == []


def test_a_bankruptcy_is_a_highlight() -> None:
    """AgentFrozen becomes one highlight carrying the equity at the freeze."""
    recipe = custom_recipe(
        baselines=("spendthrift", "fundamentalist", "momentum", "bayesian"),
        seed=11,
        ticks=24,
        markets=2,
        template="election",
    )
    config = config_of(recipe, initial_cash_cents=20_000, bankruptcy_free_cash_floor_cents=3_000)
    rng = RngTree(config.seed)
    seats = agents_of(
        replace(recipe, baselines=("fundamentalist", "fundamentalist", "momentum", "bayesian")),
        config,
        rng,
    )
    seats["A1"] = Spendthrift(agent_id="A1", config=config, rng=rng.child("agent/A1").substream("agent.A1"))
    _result, events = play_with_agents(recipe, factories=seats, config=config)
    frozen = of_type(events, AgentFrozen)
    assert frozen, "no agent was frozen, so the bankruptcy highlight is untested"

    projection = project(events)
    rows = [row for row in projection.highlights if row.kind == "bankruptcy"]
    assert len(rows) == len(frozen)
    first = frozen[0]
    assert isinstance(first, AgentFrozen)
    assert rows[0].tick == first.tick
    assert rows[0].agent_ids == (first.agent_id,)
    assert rows[0].market_id is None
    assert rows[0].magnitude_cents == first.equity_cents
    assert "went bankrupt" in rows[0].label


def test_incidents_are_the_only_non_journal_input(reference: MatchProjection) -> None:
    """Section 4.5: incidents are not journalled, so project() must be handed them."""
    assert [row for row in reference.highlights if row.kind == "integrity_alert"] == []
    incident = Incident(
        incident_id=make_incident_id(1),
        kind=IncidentKind.COLLUSION,
        severity="high",
        tick=7,
        agent_ids=("A2", "A1"),
        market_ids=("M3",),
        score_ppm=812_345,
        detail=(("pairs", 1),),
        detector_version="1.0.0",
    )
    with_alert = project(golden_events(REFERENCE), incidents=(incident,))
    alerts = [row for row in with_alert.highlights if row.kind == "integrity_alert"]
    assert len(alerts) == 1
    assert alerts[0].tick == 7
    assert alerts[0].agent_ids == ("A1", "A2"), "agent ids are canonically sorted"
    assert alerts[0].market_id == "M3"
    assert alerts[0].magnitude_cents == 0
    assert "812345 ppm" in alerts[0].label
    # A detector version bump can never move a metric: everything else is equal.
    assert compute_performance(with_alert) == compute_performance(reference)
    assert with_alert.trades == reference.trades


# ---------------------------------------------------------------------------
# project: refusals and accessors
# ---------------------------------------------------------------------------
def test_a_journal_without_match_started_is_refused() -> None:
    """There is no seed, no horizon and no seat list to guess (section 4.4)."""
    events = golden_events(SMALL)
    without = tuple(event for event in events if not isinstance(event, MatchStarted))
    assert len(without) == len(events) - 1
    with pytest.raises(InvalidConfigError):
        project(without)


def test_project_does_not_depend_on_the_order_it_is_handed(reference: MatchProjection) -> None:
    """Section 2.3: events are canonically ordered by seq, by project itself."""
    shuffled = tuple(reversed(golden_events(REFERENCE)))
    assert project(shuffled) == reference


def test_agent_index_and_series_refuse_an_unknown_seat(reference: MatchProjection) -> None:
    """A silent -1 would index the last agent's series."""
    assert reference.agent_index("A1") == 0
    assert reference.agent_index(reference.agent_ids[-1]) == len(reference.agent_ids) - 1
    with pytest.raises(InvalidConfigError):
        reference.agent_index(MM_ACCOUNT_ID)
    with pytest.raises(InvalidConfigError):
        reference.equity_series("A99")


# ---------------------------------------------------------------------------
# PRD 7.1: performance
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("recipe", GOLDEN, ids=lambda recipe: recipe.name)
def test_pnl_is_the_settled_cash_difference(recipe: Recipe) -> None:
    """Section 9: PnL is final_cash - initial_cash, after settlement.

    The projection derives it from the executions and the outcomes; the runner
    read it off the ledger at finalisation step 18. They are two independent
    routes to the same integer and this is where they meet.
    """
    events = golden_events(recipe)
    projection = project(events)
    ended = match_ended_of(events)
    assert ended.rankings
    journalled = {str(row["agent_id"]): row for row in ended.rankings}
    metrics = compute_performance(projection)
    assert len(metrics) == len(journalled)
    for row in metrics:
        assert row.pnl_cents == journalled[row.agent_id]["pnl_cents"]
        assert projection.initial_cash_cents + row.pnl_cents == journalled[row.agent_id]["final_cash_cents"]


@pytest.mark.parametrize("recipe", GOLDEN, ids=lambda recipe: recipe.name)
def test_pnl_bps_equals_the_journalled_pnl_pct_bps(recipe: Recipe) -> None:
    """Section 9: the same number under two names, and they must agree."""
    events = golden_events(recipe)
    projection = project(events)
    journalled = {str(row["agent_id"]): int(row["pnl_pct_bps"]) for row in match_ended_of(events).rankings}
    assert journalled
    metrics = compute_performance(projection)
    assert any(row.pnl_bps != 0 for row in metrics), "every PnL is flat, so the ratio is untested"
    for row in metrics:
        assert row.pnl_bps == journalled[row.agent_id]
        assert row.pnl_bps == bps_ratio(row.pnl_cents, projection.initial_cash_cents)


@pytest.mark.parametrize("recipe", GOLDEN, ids=lambda recipe: recipe.name)
def test_mm_pnl_is_reported_and_excluded(recipe: Recipe) -> None:
    """FR-5.8.5: the market maker PnL is published and never ranked or rated.

    "Computed like any agent PnL but excluded from ranking": both halves are
    asserted here, and the first is what makes the second meaningful. The one
    formula is :func:`pnl_of`, applied to ``MM``, and it must reproduce the
    ``mm_pnl_cents`` the runner journalled from the ledger at step 19.
    """
    events = golden_events(recipe)
    projection = project(events)
    ended = match_ended_of(events)
    assert any(MM_ACCOUNT_ID in (row.maker_agent_id, row.taker_agent_id) for row in projection.trades)
    assert pnl_of(projection, MM_ACCOUNT_ID) == ended.mm_pnl_cents != 0
    assert projection.mm_pnl_cents == ended.mm_pnl_cents
    # Published separately, and out of every ranked collection.
    assert MM_ACCOUNT_ID not in projection.agent_ids
    assert MM_ACCOUNT_ID not in [row.agent_id for row in compute_performance(projection)]
    assert MM_ACCOUNT_ID not in [row.agent_id for row in final_ranking(projection)]


@pytest.mark.parametrize("recipe", GOLDEN, ids=lambda recipe: recipe.name)
def test_the_match_is_zero_sum_across_every_account(recipe: Recipe) -> None:
    """FR-5.5.3: a closed system, so every PnL plus the fees sums to zero."""
    projection = project(golden_events(recipe))
    assert projection.trades
    total = sum(row.pnl_cents for row in compute_performance(projection))
    total += projection.mm_pnl_cents + projection.fees_collected_cents
    assert total == 0


def test_the_fee_arm_of_every_metric_is_exercised() -> None:
    """FR-5.4.7 through the projection: a taker fee is collected, paid and closed.

    ``MatchConfig.taker_fee_bps`` defaults to ``0`` and all three golden
    journals use the default, so every fee assertion in this file is otherwise
    an assertion that zero equals zero: a projection that dropped
    ``taker_fee_cents`` entirely would pass them all. This test plays the same
    small match with a real 1.5 % fee and pins the three places the money
    appears, including the FR-5.5.3 closed system identity, which only has a
    third term when the vault is non empty.
    """
    config = config_of(SMALL, taker_fee_bps=150)
    _result, events = play_with_agents(SMALL, factories=agents_of(SMALL, config, RngTree(config.seed)), config=config)
    projection = project(events)
    assert projection.trades, "nobody traded, so no fee could be charged"
    charged = sum(row.taker_fee_cents for row in projection.trades)
    assert charged > 0, "a 150 bps fee collected nothing, so this test would be vacuous"
    assert projection.fees_collected_cents == charged
    metrics = compute_performance(projection)
    paid = sum(row.fees_paid_cents for row in metrics)
    mm_paid = sum(row.taker_fee_cents for row in projection.trades if row.taker_agent_id == MM_ACCOUNT_ID)
    assert paid + mm_paid == charged, "the per seat fees do not add up to the vault"
    assert any(row.fees_paid_cents > 0 for row in metrics), "no ranked seat ever took liquidity"
    # The closed system still closes with a third, non zero term (FR-5.5.3).
    total = sum(row.pnl_cents for row in metrics) + projection.mm_pnl_cents + projection.fees_collected_cents
    assert total == 0


@pytest.mark.parametrize("recipe", GOLDEN, ids=lambda recipe: recipe.name)
def test_volume_trades_and_fees_come_from_trade_executed(recipe: Recipe) -> None:
    """Section 9: from TradeExecuted where the agent is maker or taker."""
    events = golden_events(recipe)
    projection = project(events)
    raw = [event for event in of_type(events, TradeExecuted) if isinstance(event, TradeExecuted)]
    assert raw
    metrics = {row.agent_id: row for row in compute_performance(projection)}
    for agent_id, row in metrics.items():
        mine = [event for event in raw if agent_id in (event.maker_agent_id, event.taker_agent_id)]
        assert row.trade_count == len(mine)
        assert row.volume_qty == sum(event.qty for event in mine)
        assert row.maker_trade_count == sum(1 for event in mine if event.maker_agent_id == agent_id)
        assert row.fees_paid_cents == sum(event.taker_fee_cents for event in mine if event.taker_agent_id == agent_id)
        assert row.maker_trade_count <= row.trade_count
    assert sum(row.trade_count for row in metrics.values()) > 0, "nobody traded, so this test would be vacuous"


def test_a_mute_agent_has_no_trade_and_no_drawdown(reference: MatchProjection) -> None:
    """AC-P9: the mute baseline predicts and never orders, so its PnL is flat."""
    metrics = {row.agent_id: row for row in compute_performance(reference)}
    flat = [row for row in metrics.values() if row.trade_count == 0]
    assert flat, "no seat abstained, so the empty branch of every metric is untested"
    for row in flat:
        assert row.volume_qty == 0
        assert row.maker_trade_count == 0
        assert row.fees_paid_cents == 0
        assert row.pnl_cents == 0
        assert row.pnl_bps == 0
        assert row.sharpe_milli == 0
        assert row.max_drawdown_cents == 0
        assert row.max_drawdown_bps == 0


@pytest.mark.parametrize("recipe", GOLDEN, ids=lambda recipe: recipe.name)
def test_max_drawdown_is_the_worst_peak_to_trough(recipe: Recipe) -> None:
    """Section 9: max over t of (running max of equity) - equity_t, in cents."""
    projection = project(golden_events(recipe))
    metrics = compute_performance(projection)
    assert any(row.max_drawdown_cents > 0 for row in metrics), "no seat drew down, so this test is vacuous"
    for row in metrics:
        series = projection.equity_series(row.agent_id)
        expected = 0
        peak = series[0]
        for value in series:
            peak = max(peak, value)
            expected = max(expected, peak - value)
        assert row.max_drawdown_cents == expected >= 0
        assert row.max_drawdown_bps == bps_ratio(expected, projection.initial_cash_cents)


def test_drawdown_and_sharpe_of_hand_built_series() -> None:
    """The two float touching helpers, pinned on series a reader can check."""
    assert max_drawdown_cents_of(()) == 0
    assert max_drawdown_cents_of((100,)) == 0
    assert max_drawdown_cents_of((100, 140, 90, 120)) == 50
    assert max_drawdown_cents_of((10, 20, 30)) == 0
    # A perfectly linear trajectory has a zero standard deviation of increments.
    assert sharpe_milli_of((100, 200, 300, 400)) == 0
    assert sharpe_milli_of((100,)) == 0
    assert sharpe_milli_of((100, 200)) == 0
    # d = (10, -5, 15): mean 20/3, sample stdev sqrt(325/3) = 10.4083, so
    # 1000 * mean / stdev = 640.51, which round_half_up sends to 641.
    assert sharpe_milli_of((0, 10, 5, 20)) == 641
    # The mirror trajectory reports the mirror ratio: -640.51 goes to -641, so
    # a gain and its mirror loss report the same magnitude here.
    assert sharpe_milli_of((0, -10, -5, -20)) == -641


@pytest.mark.parametrize("recipe", GOLDEN, ids=lambda recipe: recipe.name)
def test_sharpe_is_zero_exactly_when_the_increments_are_flat(recipe: Recipe) -> None:
    """Section 9: 0 when stdev(d) == 0, and signed otherwise."""
    projection = project(golden_events(recipe))
    metrics = compute_performance(projection)
    assert any(row.sharpe_milli != 0 for row in metrics), "every trajectory is flat, so this test is vacuous"
    for row in metrics:
        series = projection.equity_series(row.agent_id)
        diffs = [series[index + 1] - series[index] for index in range(len(series) - 1)]
        if len(set(diffs)) <= 1:
            assert row.sharpe_milli == 0
        else:
            assert row.sharpe_milli == sharpe_milli_of(series)


def test_performance_is_in_canonical_agent_order(reference: MatchProjection) -> None:
    """Section 2.3: ascending numeric suffix, which is agent_ids itself."""
    metrics = compute_performance(reference)
    assert [row.agent_id for row in metrics] == list(reference.agent_ids)
    assert all(isinstance(row, PerformanceMetrics) for row in metrics)


# ---------------------------------------------------------------------------
# AC-P4: PnL depends on trades only
# ---------------------------------------------------------------------------
def _with_rewritten_predictions(events: tuple[Event, ...]) -> tuple[Event, ...]:
    """Return the journal with every declared probability replaced by garbage."""
    out: list[Event] = []
    for event in events:
        if isinstance(event, PredictionRecorded):
            out.append(replace(event, p_yes_ppm=1_000_000 - event.p_yes_ppm, carried=not event.carried))
        else:
            out.append(event)
    return tuple(out)


@pytest.mark.parametrize("recipe", GOLDEN, ids=lambda recipe: recipe.name)
def test_performance_ignores_every_declared_prediction(recipe: Recipe) -> None:
    """AC-P4: no score enters the computation of the other one."""
    events = golden_events(recipe)
    assert of_type(events, PredictionRecorded), "no prediction to mutate, so this test would be vacuous"
    mutated = _with_rewritten_predictions(events)
    original = project(events)
    altered = project(mutated)
    assert altered.predictions != original.predictions, "the mutation did not change the prediction rows"
    assert compute_performance(altered) == compute_performance(original)
    assert final_ranking(altered) == final_ranking(original)


def test_pnl_moves_when_a_trade_moves(reference: MatchProjection) -> None:
    """The mirror of the test above: PnL is not inert, it depends on the trades."""
    events = golden_events(REFERENCE)
    trades = [event for event in of_type(events, TradeExecuted) if isinstance(event, TradeExecuted)]
    assert trades
    target = trades[0]
    doubled = tuple(
        replace(event, taker_cash_delta_cents=event.taker_cash_delta_cents - 1_000)
        if isinstance(event, TradeExecuted) and event.trade_id == target.trade_id
        else event
        for event in events
    )
    altered = compute_performance(project(doubled))
    before = {row.agent_id: row.pnl_cents for row in compute_performance(reference)}
    after = {row.agent_id: row.pnl_cents for row in altered}
    assert after[target.taker_agent_id] == before[target.taker_agent_id] - 1_000


# ---------------------------------------------------------------------------
# FR-5.5.4: the ranking is settled, never marked
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("recipe", GOLDEN, ids=lambda recipe: recipe.name)
def test_final_ranking_reproduces_the_journalled_settlement(recipe: Recipe) -> None:
    """FR-5.5.4, step 18: rank on cash after settlement, ties share the lowest rank."""
    events = golden_events(recipe)
    projection = project(events)
    journalled = match_ended_of(events).rankings
    assert journalled
    computed = final_ranking(projection)
    assert [(row.rank, row.agent_id, row.pnl_cents, row.final_cash_cents, row.pnl_pct_bps) for row in computed] == [
        (
            int(row["rank"]),
            str(row["agent_id"]),
            int(row["pnl_cents"]),
            int(row["final_cash_cents"]),
            int(row["pnl_pct_bps"]),
        )
        for row in journalled
    ]
    assert [row.rank for row in computed] == sorted(row.rank for row in computed)


@pytest.mark.parametrize("recipe", GOLDEN, ids=lambda recipe: recipe.name)
def test_ranking_is_settled_not_marked(recipe: Recipe) -> None:
    """FR-5.5.4: the settled order and the last tick equity order are not the same.

    This is the claim that makes the rule testable rather than decorative: on all
    three golden matches the seat leading on mark to market equity at the last
    played tick is not in the same place as after settlement, so a projection
    that ranked on ``equity_cents[-1]`` would pass every other test in this file
    and fail this one.
    """
    projection = project(golden_events(recipe))
    settled = [row.agent_id for row in final_ranking(projection)]
    marked = [
        agent_id
        for agent_id, _equity in sorted(
            ((agent_id, projection.equity_series(agent_id)[-1]) for agent_id in projection.agent_ids),
            key=lambda pair: -pair[1],
        )
    ]
    assert len(settled) == len(marked) == len(projection.agent_ids)
    assert settled != marked, "the two orders coincide in this match, so the rule is untested here"


def test_a_tie_shares_the_lowest_rank() -> None:
    """Step 18: ties share the lowest rank, broken for display by agent_id.

    Dropping every trade row leaves every seat on a PnL of exactly zero, which is
    the only way to reach a full tie from a real journal without forging one.
    """
    projection = project(golden_events(REFERENCE))
    assert projection.trades, "the reference match has no trade, so removing them proves nothing"
    tied = replace(projection, trades=())
    ranking = final_ranking(tied)
    assert {row.rank for row in ranking} == {1}
    assert [row.agent_id for row in ranking] == list(projection.agent_ids)
    assert all(row.pnl_cents == 0 and row.pnl_pct_bps == 0 for row in ranking)
    assert all(row.final_cash_cents == projection.initial_cash_cents for row in ranking)


# ---------------------------------------------------------------------------
# aggregate.py: it needs A16 and A17
# ---------------------------------------------------------------------------
def test_compute_all_joins_the_three_families_and_round_trips(tmp_path: Path) -> None:
    """CONTRACTS section 4.6: metrics.json has exactly one writer and one reader.

    ``aggregate`` is the only A15 module that imports ``calibration`` (A16) and
    ``behavioral`` (A17). Until both have landed this skips with a named reason
    rather than passing on nothing (section 10).
    """
    from pxe.metrics.aggregate import compute_all, read_metrics, write_metrics

    projection = project(golden_events(REFERENCE))
    assert projection.trades and projection.predictions
    metrics = compute_all(projection)
    assert metrics.match_id == projection.match_id
    assert len(metrics.performance) == len(projection.agent_ids)
    assert len(metrics.calibration) == len(projection.agent_ids)
    assert len(metrics.descriptors) == len(projection.agent_ids)
    assert metrics.performance == compute_performance(projection)
    assert metrics.mm_pnl_cents == projection.mm_pnl_cents
    assert metrics.fees_collected_cents == projection.fees_collected_cents

    path = tmp_path / "runs" / projection.match_id / "metrics.json"
    write_metrics(path, metrics)
    assert path.exists()
    raw = path.read_bytes()
    assert b"\r" not in raw, "metrics.json must be written with newline='\\n' (section 4.2)"
    assert read_metrics(path) == metrics
    # Rewriting is byte stable, which is what makes the store comparison honest.
    write_metrics(path, metrics)
    assert path.read_bytes() == raw


def test_read_metrics_refuses_a_foreign_file(tmp_path: Path) -> None:
    """A silently defaulted metric would be published as a measurement."""
    from pxe.metrics.aggregate import read_metrics

    path = tmp_path / "metrics.json"
    path.write_text('{"match_id": "m-election-1-01"}\n', encoding="utf-8", newline="\n")
    with pytest.raises(InvalidConfigError):
        read_metrics(path)


# ---------------------------------------------------------------------------
# A cross check that keeps the trade side of the projection honest
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("recipe", GOLDEN, ids=lambda recipe: recipe.name)
def test_the_trade_rows_net_to_zero_per_market(recipe: Recipe) -> None:
    """I1 seen from the projection: every contract bought was sold by somebody.

    It is what makes the PnL derivation of :func:`pnl_of` legitimate: the payout
    leg it adds per market is a redistribution and not a creation of contracts.
    """
    projection = project(golden_events(recipe))
    assert projection.trades
    per_market: dict[str, dict[str, int]] = {market_id: {} for market_id in projection.market_ids}
    for row in projection.trades:
        sign = Side(row.maker_side).sign
        book = per_market[row.market_id]
        book[row.maker_agent_id] = book.get(row.maker_agent_id, 0) + sign * row.qty
        book[row.taker_agent_id] = book.get(row.taker_agent_id, 0) - sign * row.qty
    traded = [market_id for market_id, book in per_market.items() if book]
    assert traded, "no market traded, so this test would be vacuous"
    for market_id in traded:
        assert sum(per_market[market_id].values()) == 0, market_id
        assert MM_ACCOUNT_ID in per_market[market_id], f"the market maker never traded {market_id}"
