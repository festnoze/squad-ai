"""FR-5.1.3: the journal alone replays a match (A09, CONTRACTS section 4.1).

The point of these tests is what they do **not** touch. ``replay_journal``
receives a sequence of events read back from a file and nothing else: no
``World``, no ``InfoEngine``, no ``ScriptedAgent``, no ``AgentGateway`` and no
seed. If a fact an engine decision depends on were missing from the journal,
either the rebuild would raise or one of the ``PositionSnapshot`` and
``MarkToMarket`` comparisons in ``verify_replay`` would fail.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from pxe.errors import ReplayMismatchError
from pxe.events import (
    Event,
    MarketResolved,
    MatchEnded,
    MessagePosted,
    PositionSnapshot,
    PredictionRecorded,
    TradeExecuted,
)
from pxe.journal import read_journal
from pxe.rng import RngTree
from pxe.runner.replay import replay_journal, replay_to_tick, verify_replay
from pxe.types import FEES_ACCOUNT_ID, MM_ACCOUNT_ID, Outcome
from tests.test_match_runner import (
    REFERENCE,
    SMALL,
    WIDE,
    Chatterbox,
    agents_of,
    config_of,
    of_type,
    play,
    play_with_agents,
    world_of,
)


@pytest.fixture
def written_match(tmp_path: Path) -> tuple[Path, tuple[Event, ...]]:
    """Play the WIDE recipe to disk. It resolves a market mid match."""
    path = tmp_path / "journal.jsonl"
    _result, events = play(WIDE, path=path)
    return path, events


def test_replay_from_journal_only(written_match: tuple[Path, tuple[Event, ...]]) -> None:
    """FR-5.1.3: the file on disk is the only input to the rebuild."""
    path, events = written_match
    from_disk = read_journal(path)
    assert from_disk, "the journal file replayed to nothing"
    assert len(from_disk) == len(events)
    assert of_type(from_disk, TradeExecuted), "the match traded nothing, so the replay proves little"

    state = replay_journal(from_disk)
    config = config_of(WIDE)

    # The rebuilt configuration and scenario came out of MatchStarted.
    assert state.config == config
    assert state.match_id == f"m-{WIDE.template_id}-{WIDE.seed}-01"
    assert state.tick == config.ticks_total + 1
    assert len(state.scenario.markets) == config.n_markets
    assert [market.market_id for market in state.scenario.markets] == [
        f"M{index}" for index in range(1, config.n_markets + 1)
    ]
    # The four unjournalled scenario fields are deliberately not recovered.
    assert state.scenario.correlations == ()
    assert state.scenario.cancellations == ()
    assert state.scenario.held_out is False
    assert state.scenario.notes == ""

    # Every outcome the oracle published is back.
    resolutions = of_type(from_disk, MarketResolved)
    assert resolutions
    assert state.outcomes == {
        event.market_id: Outcome(event.outcome) for event in resolutions if isinstance(event, MarketResolved)
    }

    # I11: after the final settlement every position is flat, so equity is cash.
    for account_id in state.accounts.account_ids():
        for market in state.scenario.markets:
            assert state.accounts.position(account_id, market.market_id).qty == 0
    assert state.open_market_ids() == ()

    # The rebuilt cash agrees with the ranking the runner journalled.
    ended = of_type(from_disk, MatchEnded)[0]
    assert isinstance(ended, MatchEnded)
    for row in ended.rankings:
        assert state.accounts.cash_cents(str(row["agent_id"])) == int(row["final_cash_cents"])
    assert state.accounts.cash_cents(MM_ACCOUNT_ID) - config.mm_initial_cash_cents == ended.mm_pnl_cents
    assert state.accounts.cash_cents(FEES_ACCOUNT_ID) == ended.fees_collected_cents

    # And the last prediction of every seat is back, for every market.
    predictions = of_type(from_disk, PredictionRecorded)
    assert predictions
    expected: dict[tuple[str, str], int] = {}
    for event in predictions:
        assert isinstance(event, PredictionRecorded)
        expected[event.agent_id, event.market_id] = event.p_yes_ppm
    assert state.last_prediction_ppm == expected


def test_verify_replay_accepts_a_real_journal(written_match: tuple[Path, tuple[Event, ...]]) -> None:
    """Every snapshot and every mark of a real match agrees with the rebuild."""
    path, _events = written_match
    from_disk = read_journal(path)
    assert of_type(from_disk, PositionSnapshot), "no snapshot to compare against"
    verify_replay(from_disk)


def test_verify_replay_rejects_a_tampered_snapshot(written_match: tuple[Path, tuple[Event, ...]]) -> None:
    """The comparison has teeth: one wrong cent is caught."""
    path, _events = written_match
    from_disk = list(read_journal(path))
    index = next(
        position
        for position, event in enumerate(from_disk)
        if isinstance(event, PositionSnapshot) and event.account_id == "A1" and event.tick == 3
    )
    original = from_disk[index]
    assert isinstance(original, PositionSnapshot)
    from_disk[index] = replace(original, cash_cents=original.cash_cents + 1)
    with pytest.raises(ReplayMismatchError):
        verify_replay(from_disk)


def test_verify_replay_rejects_a_tampered_mark(written_match: tuple[Path, tuple[Event, ...]]) -> None:
    """A wrong reference price is caught too, not only a wrong balance."""
    from pxe.events import MarkToMarket

    path, _events = written_match
    from_disk = list(read_journal(path))
    index = next(position for position, event in enumerate(from_disk) if isinstance(event, MarkToMarket))
    original = from_disk[index]
    assert isinstance(original, MarkToMarket)
    moved = original.ref_price + 1 if original.ref_price < 99 else original.ref_price - 1
    from_disk[index] = replace(original, ref_price=moved)
    with pytest.raises(ReplayMismatchError):
        verify_replay(from_disk)


def test_replay_to_tick_matches_that_tick_snapshots(written_match: tuple[Path, tuple[Event, ...]]) -> None:
    """A mid match rebuild equals the PositionSnapshot block of that tick."""
    path, _events = written_match
    from_disk = read_journal(path)
    snapshots = of_type(from_disk, PositionSnapshot)
    assert snapshots
    for tick in (1, 5, WIDE.ticks_total // 2, WIDE.ticks_total):
        state = replay_to_tick(from_disk, tick)
        assert state.tick == tick
        rows = [event for event in snapshots if isinstance(event, PositionSnapshot) and event.tick == tick]
        assert rows, f"no snapshot at tick {tick}"
        for row in rows:
            assert state.accounts.cash_cents(row.account_id) == row.cash_cents
            assert state.accounts.reserved_cents(row.account_id) == row.reserved_cents
            assert state.accounts.resting_order_count(row.account_id) == row.resting_order_count
            for position in row.positions:
                rebuilt = state.accounts.position(row.account_id, str(position["market_id"]))
                assert rebuilt.qty == int(position["qty"])
                assert rebuilt.cost_basis_cents == int(position["cost_basis_cents"])


def test_replay_to_tick_zero_is_the_state_after_match_started(
    written_match: tuple[Path, tuple[Event, ...]],
) -> None:
    """Tick 0 is MatchStarted alone: a funded, flat, fully open match."""
    path, _events = written_match
    from_disk = read_journal(path)
    state = replay_to_tick(from_disk, 0)
    config = config_of(WIDE)
    assert state.tick == 0
    assert state.open_market_ids() == tuple(f"M{i}" for i in range(1, config.n_markets + 1))
    assert state.frozen_agent_ids == frozenset()
    assert state.last_prediction_ppm == {}
    assert state.outcomes == {}
    for agent_id in state.ranked_agent_ids():
        assert state.accounts.cash_cents(agent_id) == config.initial_cash_cents
        assert state.accounts.reserved_cents(agent_id) == 0
    assert state.accounts.cash_cents(MM_ACCOUNT_ID) == config.mm_initial_cash_cents
    assert state.accounts.cash_cents(FEES_ACCOUNT_ID) == 0


def test_replay_of_the_reference_match_verifies() -> None:
    """The 6 by 48 reference match replays and verifies from memory too."""
    _result, events = play(REFERENCE)
    assert events
    verify_replay(events)
    state = replay_journal(events)
    assert len(state.outcomes) == config_of(REFERENCE).n_markets


def test_a_talking_match_replays_its_pending_messages() -> None:
    """CONTRACTS section 7.12: pending_messages is MessagePosted past final_tick."""
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
    for event in posted:
        assert isinstance(event, MessagePosted)
        assert event.deliver_tick == event.tick + 1

    last = of_type(events, MatchEnded)[0]
    assert isinstance(last, MatchEnded)
    expected = [
        event.agent_id for event in posted if isinstance(event, MessagePosted) and event.deliver_tick > last.final_tick
    ]
    assert expected, "no message was posted on the last tick, so nothing should be pending"
    state = replay_journal(events)
    assert [message.agent_id for message in state.pending_messages] == expected
    # Mid match exactly the messages of that tick are pending: a message posted
    # at t is delivered at t + 1 and leaves the queue there.
    cut = SMALL.ticks_total // 2
    midway = replay_to_tick(events, cut)
    still_pending = [event.agent_id for event in posted if isinstance(event, MessagePosted) and event.tick == cut]
    assert still_pending
    assert [message.agent_id for message in midway.pending_messages] == still_pending


def test_replay_refuses_a_journal_without_match_started() -> None:
    _result, events = play(SMALL)
    assert events
    with pytest.raises(ReplayMismatchError):
        replay_journal(events[1:])
    with pytest.raises(ReplayMismatchError):
        replay_journal(())
