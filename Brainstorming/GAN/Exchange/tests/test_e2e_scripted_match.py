"""End to end: six agents, forty-eight ticks, no LLM, invariants at every tick.

This is the T1.8 exit test. It runs the reference match (the PRD section 5.7
defaults and the ``standard_config`` seed) and asserts three things a unit test
cannot:

* it finishes in under five seconds without a single provider call
  (``test_six_by_forty_eight_under_five_seconds``);
* the closed system invariants of CONTRACTS section 6 held at **every** tick,
  checked a second time from the journal rather than from the live ledger, so a
  ``check_invariants`` that silently did nothing would still be caught
  (``test_closed_system_invariants_hold_at_every_tick``);
* with the PRD default every market resolves at ``T`` and therefore settles in
  finalisation, at the virtual tick ``ticks_total + 1``
  (``test_default_scenario_settles_at_finalisation``).
"""

from __future__ import annotations

import time
from collections import defaultdict
from pathlib import Path

import pytest

from pxe.events import (
    Event,
    MarketResolved,
    MarkToMarket,
    MatchEnded,
    MMQuoted,
    ObservationBuilt,
    OrderPlaced,
    PositionSnapshot,
    PredictionRecorded,
    SettlementApplied,
    TickStarted,
    TradeExecuted,
)
from pxe.journal import verify_journal
from pxe.types import FEES_ACCOUNT_ID, MM_ACCOUNT_ID
from tests.test_match_runner import REFERENCE, config_of, of_type, play, world_of

#: The AC/T1.8 budget for a 6 by 48 scripted match, in seconds.
TIME_BUDGET_S = 5.0


@pytest.fixture(scope="module")
def reference_match() -> tuple[float, tuple[Event, ...], int]:
    """Play the reference match once and share it across this module."""
    started = time.perf_counter()
    result, events = play(REFERENCE)
    elapsed = time.perf_counter() - started
    return elapsed, events, result.event_count


@pytest.mark.e2e
@pytest.mark.slow
def test_six_by_forty_eight_under_five_seconds(reference_match: tuple[float, tuple[Event, ...], int]) -> None:
    """T1.8: no LLM, six seats, forty-eight ticks, under five seconds."""
    elapsed, events, event_count = reference_match
    assert events, "the reference match produced an empty journal"
    assert event_count == len(events)
    config = config_of(REFERENCE)
    assert config.n_agents == 6
    assert config.ticks_total == 48
    # The match is substantial and not an empty loop: every tick opened, every
    # seat was observed, the market maker quoted and trades happened.
    assert len(of_type(events, TickStarted)) == 48
    assert len(of_type(events, ObservationBuilt)) == 48 * 6
    assert of_type(events, MMQuoted)
    assert of_type(events, TradeExecuted)
    assert of_type(events, PredictionRecorded)
    assert elapsed < TIME_BUDGET_S, f"the reference match took {elapsed:.3f}s, over the {TIME_BUDGET_S}s budget"


@pytest.mark.e2e
def test_closed_system_invariants_hold_at_every_tick(
    reference_match: tuple[float, tuple[Event, ...], int],
) -> None:
    """I1, I2, I4 and I9 re-derived from the journal, tick by tick.

    ``AccountBook.check_invariants`` already ran on every P4 inside the match.
    This checks the same facts from the outside, from ``PositionSnapshot``
    alone, so a checker that silently did nothing cannot hide behind itself.
    """
    _elapsed, events, _count = reference_match
    snapshots = of_type(events, PositionSnapshot)
    assert snapshots, "no PositionSnapshot was emitted"
    config = config_of(REFERENCE)
    expected_total = config.n_agents * config.initial_cash_cents + config.mm_initial_cash_cents

    per_tick: dict[int, list[PositionSnapshot]] = defaultdict(list)
    for event in snapshots:
        assert isinstance(event, PositionSnapshot)
        per_tick[event.tick].append(event)
    assert len(per_tick) == config.ticks_total

    # A tick on which nobody holds a position satisfies I1 trivially: `net` is
    # empty and `all(...)` over nothing is True. Counting the ticks that really
    # carried a position is what turns "I1 held at every tick" into a claim, and
    # the floor below is asserted after the loop.
    ticks_with_positions = 0
    markets_seen: set[str] = set()
    for tick, rows in sorted(per_tick.items()):
        # I2: cash is conserved, the FEES vault included.
        assert sum(row.cash_cents for row in rows) == expected_total, f"I2 broken at tick {tick}"
        # I1 and I7: every market is net flat across accounts.
        net: dict[str, int] = defaultdict(int)
        for row in rows:
            for position in row.positions:
                net[str(position["market_id"])] += int(position["qty"])
        if net:
            ticks_with_positions += 1
            markets_seen |= set(net)
        assert all(value == 0 for value in net.values()), f"I1 broken at tick {tick}: {dict(net)}"
        for row in rows:
            # I9 and I4.
            assert row.cash_cents >= 0, f"I9 broken at tick {tick} for {row.account_id}"
            assert 0 <= row.reserved_cents <= row.cash_cents, f"I4 broken at tick {tick} for {row.account_id}"
            assert row.free_cash_cents == row.cash_cents - row.reserved_cents

    # I5: every execution is zero sum, fee included.
    trades = of_type(events, TradeExecuted)
    assert trades
    for trade in trades:
        assert isinstance(trade, TradeExecuted)
        assert trade.maker_cash_delta_cents + trade.taker_cash_delta_cents + trade.taker_fee_cents == 0

    # I6: every settlement group is zero sum.
    groups: dict[tuple[int, str], list[int]] = defaultdict(list)
    for line in of_type(events, SettlementApplied):
        assert isinstance(line, SettlementApplied)
        groups[line.tick, line.market_id].append(line.cash_delta_cents)
    assert groups
    for key, deltas in groups.items():
        assert sum(deltas) == 0, f"I6 broken for {key}"

    # The teeth for I1: the per tick check above is only a claim about a closed
    # system if the system actually held positions. The reference match trades
    # from the first ticks onwards, so a large majority of ticks carry one.
    assert ticks_with_positions >= config.ticks_total // 2, (
        f"only {ticks_with_positions} of {config.ticks_total} ticks carried a position, "
        "so the per tick I1 check was largely vacuous"
    )
    assert len(markets_seen) == config.n_markets, (
        f"I1 was only ever exercised on {sorted(markets_seen)}, not on all {config.n_markets} markets"
    )


@pytest.mark.e2e
def test_default_scenario_settles_at_finalisation(
    reference_match: tuple[float, tuple[Event, ...], int],
) -> None:
    """Finalisation step 17 is the normal path, not a defensive one."""
    _elapsed, events, _count = reference_match
    resolutions = of_type(events, MarketResolved)
    assert resolutions, "no market resolved"
    config = config_of(REFERENCE)
    virtual_tick = config.ticks_total + 1
    scenario = world_of(REFERENCE).scenario
    assert all(market.resolution_tick == config.ticks_total for market in scenario.markets), (
        "the reference world no longer resolves every market at T, so this test is about something else"
    )
    assert len(resolutions) == config.n_markets
    for event in resolutions:
        assert isinstance(event, MarketResolved)
        assert event.tick == virtual_tick, "a resolution escaped finalisation"
        assert event.resolution_tick == config.ticks_total
        assert event.payout_cents in (0, 100)
    # Finalisation emits no NewsPublished and makes no mm.note_news call: there
    # is no P2 and no P3 at T + 1 for anybody to act in.
    from pxe.events import NewsPublished

    assert [event for event in of_type(events, NewsPublished) if event.tick == virtual_tick] == []
    assert [event for event in of_type(events, MMQuoted) if event.tick == virtual_tick] == []
    assert [event for event in of_type(events, MarkToMarket) if event.tick == virtual_tick] == []
    # I11: after the final settlement every position is flat.
    ended = of_type(events, MatchEnded)
    assert len(ended) == 1
    last = ended[0]
    assert isinstance(last, MatchEnded)
    assert last.reason == "completed"
    assert last.final_tick == config.ticks_total
    assert last.event_count == len(events)


@pytest.mark.e2e
def test_the_ranking_is_settled_cash_and_sums_to_the_closed_system(
    reference_match: tuple[float, tuple[Event, ...], int],
) -> None:
    """FR-5.5.4: ranked on cash after settlement, never on a mark to market."""
    _elapsed, events, _count = reference_match
    ended = of_type(events, MatchEnded)[0]
    assert isinstance(ended, MatchEnded)
    rankings = ended.rankings
    config = config_of(REFERENCE)
    assert len(rankings) == config.n_agents
    ranks = [int(row["rank"]) for row in rankings]
    assert ranks == sorted(ranks)
    assert ranks[0] == 1
    pnls = [int(row["pnl_cents"]) for row in rankings]
    assert pnls == sorted(pnls, reverse=True)
    for row in rankings:
        assert int(row["pnl_cents"]) == int(row["final_cash_cents"]) - config.initial_cash_cents
    # The whole system is closed: the agents' PnL plus the market maker's plus
    # the fee vault is exactly zero.
    total = sum(pnls) + int(ended.mm_pnl_cents) + int(ended.fees_collected_cents)
    assert total == 0, f"the closed system leaked {total} cents"
    assert any(value != 0 for value in pnls), "nobody made or lost a cent, so the match traded nothing"


@pytest.mark.e2e
def test_a_written_match_is_verifiable_and_hashes_to_its_bytes(tmp_path: Path) -> None:
    """The on disk artefacts of a real match are self consistent."""
    import hashlib

    from tests.test_match_runner import SMALL

    path = tmp_path / "journal.jsonl"
    result, events = play(SMALL, path=path)
    assert events
    verify_journal(list(events))
    raw = path.read_bytes()
    assert raw and b"\r" not in raw
    assert hashlib.blake2b(raw, digest_size=32).hexdigest() == result.journal_hash
    assert of_type(events, OrderPlaced), "no order was ever placed"
    accounts = {event.account_id for event in of_type(events, PositionSnapshot) if isinstance(event, PositionSnapshot)}
    assert MM_ACCOUNT_ID in accounts
    assert FEES_ACCOUNT_ID in accounts
