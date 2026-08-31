"""Acceptance tests for :mod:`pxe.journal` (A02, CONTRACTS sections 4.2 to 4.5, 7.4).

Three claims are worth more than all the others here, and each has its own
test:

* the bytes on disk hash to exactly what ``Journal.hash()`` returns
  (``test_file_bytes_hash_equals_journal_hash``, the test AC-P1 and T1.2 cite);
* every one of the 24 event types of section 4.5 survives a write and a read
  byte for byte (``test_every_event_type_round_trips_byte_for_byte``);
* a carriage return is rejected, never normalised, in both directions, which is
  the trap the Windows text mode default sets.

Anti-vacuous rule (section 10): every test that asserts on a journal first
asserts the journal is non empty and holds an event of the type under test.
"""

import dataclasses
import hashlib

import pytest

from pxe.errors import JournalHashMismatchError, NonCanonicalValueError, StoreError
from pxe.events import (
    EVENT_CLASSES,
    JOURNAL_ENCODING,
    JOURNAL_NEWLINE,
    AgentActionReceived,
    AgentActionRejected,
    AgentFrozen,
    AgentTimedOut,
    Event,
    IncidentRaised,
    MarketCancelled,
    MarketResolved,
    MarkToMarket,
    MatchEnded,
    MatchStarted,
    MessagePosted,
    MMQuoted,
    NewsPublished,
    ObservationBuilt,
    OrderCancelled,
    OrderPlaced,
    OrderRejected,
    PositionSnapshot,
    PredictionRecorded,
    SettlementApplied,
    SignalDelivered,
    STPCancelled,
    TickStarted,
    TradeExecuted,
    event_to_line,
    journal_hash,
    journal_hash_from_lines,
)
from pxe.journal import Journal, filter_events, iter_ticks, read_journal, verify_journal, write_journal
from pxe.types import MatchConfig, config_to_journal_dict

MATCH_ID = "m-election-20260827-01"
OTHER_MATCH_ID = "m-election-20260827-02"

#: Digest size of the journal hash, section 4.3.
DIGEST_SIZE = 32


def _match_started(seq: int) -> MatchStarted:
    """The first event of a journal, with a real journalled config."""
    config = MatchConfig(seed=20260827)
    return MatchStarted(
        seq=seq,
        match_id=MATCH_ID,
        tick=0,
        seed=config.seed,
        engine_version=config.engine_version,
        obs_version=config.obs_version,
        action_version=config.action_version,
        scenario_template_id="election",
        scenario_template_version="1.0.0",
        ticks_total=config.ticks_total,
        initial_cash_cents=config.initial_cash_cents,
        config=config_to_journal_dict(config),
        markets=({"market_id": "M1", "question": "Wins?"}, {"market_id": "M2", "question": "Turnout?"}),
        agents=({"agent_id": "A1", "harness_id": "mute", "ranked": True},),
        mm_config=config_to_journal_dict(config)["mm"],
    )


def sample_events() -> tuple[Event, ...]:
    """One event of every type of section 4.5, in a legal envelope order.

    The list is deliberately exhaustive:
    :func:`test_every_event_type_round_trips_byte_for_byte` compares the types
    it covers with :data:`pxe.events.EVENT_CLASSES`, so a 25th event type added
    to the catalogue fails this file until it is round-tripped here too.
    """
    return (
        _match_started(1),
        TickStarted(seq=2, match_id=MATCH_ID, tick=1, open_market_ids=("M1", "M2")),
        NewsPublished(
            seq=3,
            match_id=MATCH_ID,
            tick=1,
            news_id="n-001-00",
            market_ids=("M1",),
            headline="Poll narrows in the north",
            body="Two points, within the margin of error.",
            impact="high",
            is_noise=False,
            origin="info_engine",
        ),
        SignalDelivered(
            seq=4,
            match_id=MATCH_ID,
            tick=1,
            signal_id="s-001-A1-00",
            agent_id="A1",
            market_id="M1",
            kind="point_estimate",
            value_milli=-1250,
            precision_ppm=650_000,
        ),
        MarketResolved(
            seq=5,
            match_id=MATCH_ID,
            tick=1,
            market_id="M2",
            outcome="yes",
            payout_cents=100,
            resolution_tick=0,
            latent_value_milli=1420,
        ),
        MarketCancelled(seq=6, match_id=MATCH_ID, tick=1, market_id="M3", reason="scripted intervention"),
        SettlementApplied(
            seq=7,
            match_id=MATCH_ID,
            tick=1,
            market_id="M2",
            account_id="A1",
            mode="resolution",
            position_qty=12,
            cash_delta_cents=1200,
            cash_before_cents=1_000_000,
            cash_after_cents=1_001_200,
            released_collateral_cents=0,
        ),
        ObservationBuilt(
            seq=8,
            match_id=MATCH_ID,
            tick=1,
            agent_id="A1",
            obs_version="1.0",
            n_markets=2,
            n_news=1,
            n_signals=1,
        ),
        AgentActionReceived(
            seq=9,
            match_id=MATCH_ID,
            tick=1,
            agent_id="A1",
            action_version="1.0",
            source="scripted",
            predictions=({"market_id": "M1", "p_yes_ppm": 540_000},),
            orders=({"op": "place", "market_id": "M1", "side": "buy", "price": 54, "qty": 10},),
            message_public=None,
            rationale="momentum is up",
            n_rejected=1,
        ),
        AgentActionRejected(
            seq=10,
            match_id=MATCH_ID,
            tick=1,
            agent_id="A1",
            scope="order",
            item_index=1,
            reason="INVALID_PRICE",
            detail="price 0 is outside 1..99",
        ),
        AgentTimedOut(seq=11, match_id=MATCH_ID, tick=1, agent_id="A2", reason="AGENT_TIMEOUT"),
        PredictionRecorded(
            seq=12,
            match_id=MATCH_ID,
            tick=1,
            agent_id="A1",
            market_id="M1",
            p_yes_ppm=540_000,
            carried=False,
        ),
        MessagePosted(seq=13, match_id=MATCH_ID, tick=1, agent_id="A1", text="north is mispriced", deliver_tick=2),
        MMQuoted(
            seq=14,
            match_id=MATCH_ID,
            tick=1,
            market_id="M1",
            ref_price=54,
            anchor_price=53,
            bid_price=51,
            ask_price=None,
            quote_qty=20,
            effective_spread=None,
            inventory_qty=-8,
            skew_cents=-1,
            widened=True,
            widen_until_tick=4,
        ),
        OrderPlaced(
            seq=15,
            match_id=MATCH_ID,
            tick=1,
            order_id="o-000001",
            agent_id="A1",
            market_id="M1",
            side="buy",
            requested_type="limit",
            price=54,
            qty=10,
            tif="gtc",
            reserved_cents=540,
            ref_price=None,
            active_orders_after=1,
        ),
        OrderRejected(
            seq=16,
            match_id=MATCH_ID,
            tick=1,
            agent_id="A2",
            market_id="M1",
            side="sell",
            requested_type="market",
            price=None,
            qty=5,
            reason="INSUFFICIENT_COLLATERAL",
            detail="free cash 100 below 460",
            item_index=0,
        ),
        OrderCancelled(
            seq=17,
            match_id=MATCH_ID,
            tick=1,
            order_id="o-000002",
            agent_id="A1",
            market_id="M1",
            side="sell",
            price=60,
            remaining_qty=4,
            reason="stp",
            released_cents=160,
        ),
        TradeExecuted(
            seq=18,
            match_id=MATCH_ID,
            tick=1,
            trade_id="t-000001",
            market_id="M1",
            price=54,
            qty=6,
            maker_order_id="o-000001",
            maker_agent_id="A1",
            maker_side="buy",
            taker_order_id="o-000003",
            taker_agent_id="MM",
            taker_side="sell",
            taker_fee_cents=0,
            maker_cash_delta_cents=-324,
            taker_cash_delta_cents=324,
            maker_position_after=6,
            taker_position_after=-6,
        ),
        STPCancelled(
            seq=19,
            match_id=MATCH_ID,
            tick=1,
            agent_id="A1",
            market_id="M1",
            incoming_order_id="o-000004",
            resting_order_id="o-000002",
            cancelled_qty=4,
            cancel_seq=17,
        ),
        MarkToMarket(
            seq=20,
            match_id=MATCH_ID,
            tick=1,
            market_id="M1",
            ref_price=54,
            ref_source="mid",
            best_bid=51,
            best_ask=57,
            mid_price=54,
            last_price=54,
            bid_depth_qty=40,
            ask_depth_qty=20,
            tick_volume_qty=6,
        ),
        PositionSnapshot(
            seq=21,
            match_id=MATCH_ID,
            tick=1,
            account_id="A1",
            cash_cents=999_676,
            reserved_cents=540,
            free_cash_cents=999_136,
            equity_cents=1_000_000,
            frozen=False,
            positions=({"market_id": "M1", "qty": 6, "cost_basis_cents": 324},),
            resting_order_count=1,
        ),
        AgentFrozen(
            seq=22,
            match_id=MATCH_ID,
            tick=1,
            agent_id="A3",
            equity_cents=0,
            cancelled_order_ids=("o-000005", "o-000006"),
        ),
        IncidentRaised(
            seq=23,
            match_id=MATCH_ID,
            tick=1,
            incident_id="i-0001",
            kind="technical",
            severity="low",
            agent_ids=("A1",),
            market_ids=("M1",),
            score_ppm=120_000,
            detector_version="1.0.0",
            detail={"note": "gateway retry", "attempts": 2},
        ),
        MatchEnded(
            seq=24,
            match_id=MATCH_ID,
            tick=2,
            reason="completed",
            final_tick=1,
            rankings=({"rank": 1, "agent_id": "A1", "pnl_cents": 1200, "pnl_pct_bps": 12},),
            mm_pnl_cents=-340,
            fees_collected_cents=0,
            event_count=24,
        ),
    )


def _fill(journal: Journal) -> tuple[Event, ...]:
    """Append every sample event through ``append`` and return them."""
    events = sample_events()
    for event in events:
        journal.append(event)
    assert journal.events, "anti-vacuous: the journal must hold events before anything is asserted"
    return events


# --------------------------------------------------------------------------
# Round trip (T1.2)
# --------------------------------------------------------------------------
def test_round_trip(tmp_path) -> None:
    """A written journal reads back into exactly the events that were appended."""
    path = tmp_path / "journal.jsonl"
    with Journal(MATCH_ID, path) as journal:
        events = _fill(journal)
        assert journal.next_seq == len(events) + 1
    restored = read_journal(path)
    assert restored, "anti-vacuous: read_journal returned nothing"
    assert isinstance(restored[0], MatchStarted)
    assert isinstance(restored[-1], MatchEnded)
    assert restored == events
    verify_journal(restored)


def test_every_event_type_round_trips_byte_for_byte(tmp_path) -> None:
    """All 24 types of section 4.5 survive write and read with identical bytes."""
    path = tmp_path / "journal.jsonl"
    with Journal(MATCH_ID, path) as journal:
        events = _fill(journal)
    covered = {type(event).TYPE for event in events}
    assert covered == set(EVENT_CLASSES), "every event type of section 4.5 must be round-tripped here"

    restored = read_journal(path)
    assert len(restored) == len(events) == len(EVENT_CLASSES)
    for original, back in zip(events, restored, strict=True):
        assert type(back) is type(original)
        assert event_to_line(back) == event_to_line(original)

    # The reader is byte exact at file level too, not only event by event.
    rewritten = tmp_path / "rewritten.jsonl"
    assert write_journal(rewritten, restored) == journal_hash(events)
    assert rewritten.read_bytes() == path.read_bytes()


def test_a_missing_run_directory_is_created(tmp_path) -> None:
    """``runs/<match_id>/journal.jsonl`` must not need a mkdir at the call site."""
    path = tmp_path / "runs" / MATCH_ID / "journal.jsonl"
    with Journal(MATCH_ID, path) as journal:
        events = _fill(journal)
    assert path.is_file()
    assert read_journal(path) == events


# --------------------------------------------------------------------------
# Section 4.2 and 4.3: the bytes on disk are the hash
# --------------------------------------------------------------------------
@pytest.mark.determinism
def test_file_bytes_hash_equals_journal_hash(tmp_path) -> None:
    """The digest of ``journal.jsonl`` equals ``Journal.hash()`` (AC-P1, T1.2)."""
    path = tmp_path / "journal.jsonl"
    with Journal(MATCH_ID, path) as journal:
        events = _fill(journal)
        expected = journal.hash()
    assert len(events) == 24

    raw = path.read_bytes()
    assert raw, "anti-vacuous: nothing was written to disk"
    assert b"\r" not in raw, "the writer must open the file with newline=JOURNAL_NEWLINE"
    assert raw.count(b"\n") == len(events)
    assert hashlib.blake2b(raw, digest_size=DIGEST_SIZE).hexdigest() == expected
    assert journal_hash(events) == expected
    assert journal_hash_from_lines(raw.decode(JOURNAL_ENCODING).splitlines()) == expected


@pytest.mark.determinism
def test_write_journal_returns_the_hash_of_the_bytes_it_wrote(tmp_path) -> None:
    """``write_journal`` and ``Journal`` produce the same bytes and the same digest."""
    events = sample_events()
    assert events, "anti-vacuous: no events to write"
    streamed = tmp_path / "streamed.jsonl"
    dumped = tmp_path / "dumped.jsonl"
    with Journal(MATCH_ID, streamed) as journal:
        for event in events:
            journal.append(event)
        streamed_hash = journal.hash()
    dumped_hash = write_journal(dumped, events)
    assert dumped_hash == streamed_hash == journal_hash(events)
    assert dumped.read_bytes() == streamed.read_bytes()


@pytest.mark.determinism
def test_in_memory_journal_hashes_like_a_written_one(tmp_path) -> None:
    """A journal with ``path=None`` numbers, validates and hashes identically."""
    memory = Journal(MATCH_ID)
    assert memory.path is None
    events = _fill(memory)
    path = tmp_path / "journal.jsonl"
    assert write_journal(path, events) == memory.hash()
    memory.close()


@pytest.mark.determinism
def test_buffer_size_changes_nothing_on_disk(tmp_path) -> None:
    """The buffer is an I/O detail: the bytes and the hash may not depend on it."""
    digests: list[str] = []
    payloads: list[bytes] = []
    for buffer_size in (1, 3, 4096):
        path = tmp_path / f"journal-{buffer_size}.jsonl"
        with Journal(MATCH_ID, path, buffer_size=buffer_size) as journal:
            _fill(journal)
            digests.append(journal.hash())
        payloads.append(path.read_bytes())
    assert payloads[0], "anti-vacuous: nothing was written"
    assert len(set(digests)) == 1
    assert len(set(payloads)) == 1


def test_a_rejected_buffer_size_is_refused() -> None:
    with pytest.raises(StoreError):
        Journal(MATCH_ID, None, buffer_size=0)


# --------------------------------------------------------------------------
# Section 4.2: carriage returns are rejected, never normalised
# --------------------------------------------------------------------------
@pytest.mark.determinism
def test_read_journal_rejects_a_crlf_file(tmp_path) -> None:
    """A journal written in the Windows default text mode must fail loudly."""
    events = sample_events()
    path = tmp_path / "crlf.jsonl"
    payload = "".join(event_to_line(event).rstrip("\n") + "\r\n" for event in events)
    path.write_bytes(payload.encode(JOURNAL_ENCODING))
    assert path.read_bytes().count(b"\r") == len(events), "anti-vacuous: the fixture file is not CRLF"
    with pytest.raises(NonCanonicalValueError):
        read_journal(path)


@pytest.mark.determinism
def test_read_journal_tolerates_a_trailing_blank_line(tmp_path) -> None:
    events = sample_events()
    path = tmp_path / "journal.jsonl"
    write_journal(path, events)
    with open(path, "a", encoding=JOURNAL_ENCODING, newline=JOURNAL_NEWLINE) as handle:
        handle.write("\n")
    restored = read_journal(path)
    assert restored == events


# --------------------------------------------------------------------------
# Section 4.4: seq, match_id and the envelope
# --------------------------------------------------------------------------
def test_emit_assigns_the_envelope_itself() -> None:
    journal = Journal(MATCH_ID)
    assert journal.next_seq == 1
    first = journal.emit(TickStarted, tick=1, open_market_ids=("M1",))
    second = journal.emit(
        ObservationBuilt, tick=1, agent_id="A1", obs_version="1.0", n_markets=1, n_news=0, n_signals=0
    )
    assert journal.events, "anti-vacuous: emit appended nothing"
    assert isinstance(first, TickStarted)
    assert isinstance(second, ObservationBuilt)
    assert (first.seq, second.seq) == (1, 2)
    assert first.match_id == second.match_id == MATCH_ID
    assert journal.next_seq == 3
    assert journal.events == (first, second)
    journal.close()


def test_append_refuses_a_seq_gap() -> None:
    journal = Journal(MATCH_ID)
    journal.append(_match_started(1))
    assert journal.events, "anti-vacuous: nothing was appended"
    with pytest.raises(JournalHashMismatchError):
        journal.append(TickStarted(seq=3, match_id=MATCH_ID, tick=1, open_market_ids=("M1",)))
    assert journal.next_seq == 2
    journal.close()


def test_append_refuses_a_foreign_match_id() -> None:
    journal = Journal(MATCH_ID)
    journal.append(_match_started(1))
    with pytest.raises(JournalHashMismatchError):
        journal.append(TickStarted(seq=2, match_id=OTHER_MATCH_ID, tick=1, open_market_ids=("M1",)))
    assert len(journal.events) == 1
    journal.close()


def test_a_float_payload_is_refused_and_leaves_the_journal_unchanged() -> None:
    """``canonical_json`` rejects floats, and it does so at the emitting call site."""
    journal = Journal(MATCH_ID)
    journal.append(_match_started(1))
    with pytest.raises(NonCanonicalValueError):
        journal.emit(
            PredictionRecorded,
            tick=1,
            agent_id="A1",
            market_id="M1",
            p_yes_ppm=0.54,  # a probability as a float is the classic mistake
            carried=False,
        )
    assert journal.next_seq == 2
    assert len(journal.events) == 1
    journal.close()


def test_append_after_close_is_refused(tmp_path) -> None:
    journal = Journal(MATCH_ID, tmp_path / "journal.jsonl")
    journal.append(_match_started(1))
    journal.close()
    journal.close()  # idempotent
    with pytest.raises(StoreError):
        journal.append(TickStarted(seq=2, match_id=MATCH_ID, tick=1, open_market_ids=("M1",)))


def test_an_existing_file_is_truncated(tmp_path) -> None:
    path = tmp_path / "journal.jsonl"
    path.write_text("stale content\n", encoding=JOURNAL_ENCODING, newline=JOURNAL_NEWLINE)
    with Journal(MATCH_ID, path) as journal:
        events = _fill(journal)
    assert read_journal(path) == events


def test_flush_makes_the_file_readable_mid_match(tmp_path) -> None:
    """A partial journal (no MatchEnded yet) is readable and verifiable."""
    path = tmp_path / "journal.jsonl"
    journal = Journal(MATCH_ID, path, buffer_size=4096)
    journal.append(_match_started(1))
    journal.append(TickStarted(seq=2, match_id=MATCH_ID, tick=1, open_market_ids=("M1",)))
    assert path.read_bytes() == b"", "the buffer must not reach the disk before flush()"
    journal.flush()
    partial = read_journal(path)
    assert len(partial) == 2, "anti-vacuous: flush wrote nothing"
    verify_journal(partial)
    journal.close()


# --------------------------------------------------------------------------
# verify_journal
# --------------------------------------------------------------------------
def test_verify_journal_accepts_a_real_journal() -> None:
    journal = Journal(MATCH_ID)
    events = _fill(journal)
    # Section 10's anti-vacuous rule, made explicit: verify_journal raises on an
    # empty sequence, so an empty _fill would already fail here, but the claim
    # "a real journal verifies" is only worth making against a real journal.
    assert len(events) > 1, "the fixture journal is empty, so verify_journal would be checking nothing"
    assert isinstance(events[0], MatchStarted)
    verify_journal(events)
    verify_journal(journal.events)
    journal.close()


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda events: (), id="empty"),
        pytest.param(lambda events: events[1:], id="seq_does_not_start_at_1"),
        pytest.param(lambda events: events[:3] + events[4:], id="seq_gap"),
        pytest.param(lambda events: events[:3] + events[2:], id="seq_repeat"),
        pytest.param(lambda events: (events[1], events[0], *events[2:]), id="match_started_not_first"),
    ],
)
def test_verify_journal_rejects_a_broken_envelope(mutate) -> None:
    events = sample_events()
    assert events, "anti-vacuous: no events to break"
    with pytest.raises(JournalHashMismatchError):
        verify_journal(mutate(events))


def test_verify_journal_rejects_a_decreasing_tick() -> None:
    events = sample_events()
    late = TickStarted(seq=2, match_id=MATCH_ID, tick=5, open_market_ids=("M1",))
    early = TickStarted(seq=3, match_id=MATCH_ID, tick=4, open_market_ids=("M1",))
    broken = (events[0], late, early)
    with pytest.raises(JournalHashMismatchError):
        verify_journal(broken)


def test_verify_journal_rejects_two_match_ids() -> None:
    events = sample_events()
    foreign = TickStarted(seq=2, match_id=OTHER_MATCH_ID, tick=1, open_market_ids=("M1",))
    with pytest.raises(JournalHashMismatchError):
        verify_journal((events[0], foreign))


def test_verify_journal_rejects_match_started_at_the_wrong_tick() -> None:
    started = dataclasses.replace(_match_started(1), tick=1)
    with pytest.raises(JournalHashMismatchError):
        verify_journal((started,))


def test_verify_journal_rejects_an_event_after_match_ended() -> None:
    events = sample_events()
    ended = dataclasses.replace(events[-1], seq=1, tick=0)
    trailing = dataclasses.replace(events[1], seq=2)
    with pytest.raises(JournalHashMismatchError):
        verify_journal((ended, trailing))


# --------------------------------------------------------------------------
# iter_ticks and filter_events
# --------------------------------------------------------------------------
def test_iter_ticks_groups_by_ascending_tick() -> None:
    journal = Journal(MATCH_ID)
    events = _fill(journal)
    groups = list(iter_ticks(events))
    assert groups, "anti-vacuous: iter_ticks yielded nothing"
    assert [tick for tick, _ in groups] == [0, 1, 2]
    assert [len(group) for _, group in groups] == [1, 22, 1]
    assert sum(len(group) for _, group in groups) == len(events)
    # Order inside a tick is the journal order, unchanged.
    tick_one = dict(groups)[1]
    assert [event.seq for event in tick_one] == list(range(2, 24))
    journal.close()


def test_filter_events_keeps_journal_order_and_nothing_else() -> None:
    journal = Journal(MATCH_ID)
    events = _fill(journal)
    trades = filter_events(events, TradeExecuted)
    assert len(trades) == 1, "anti-vacuous: no TradeExecuted in the sample journal"
    assert isinstance(trades[0], TradeExecuted)

    pair = filter_events(events, TickStarted, MatchEnded)
    assert [type(event) for event in pair] == [TickStarted, MatchEnded]
    assert [event.seq for event in pair] == sorted(event.seq for event in pair)

    assert filter_events(events) == ()
    assert filter_events((), TradeExecuted) == ()


# --------------------------------------------------------------------------
# The reserved fixture of section 10
# --------------------------------------------------------------------------
@pytest.mark.determinism
def test_tmp_journal_fixture_writes_lf_bytes_that_hash(tmp_journal, tmp_path) -> None:
    """The reserved ``tmp_journal`` fixture is a real, hashable journal."""
    assert tmp_journal.path == tmp_path / "journal.jsonl"
    tmp_journal.emit(TickStarted, tick=1, open_market_ids=("M1", "M2"))
    tmp_journal.emit(
        ObservationBuilt,
        tick=1,
        agent_id="A1",
        obs_version="1.0",
        n_markets=2,
        n_news=0,
        n_signals=0,
    )
    assert len(tmp_journal.events) == 2, "anti-vacuous: the fixture journal is empty"
    expected = tmp_journal.hash()
    tmp_journal.flush()
    raw = tmp_journal.path.read_bytes()
    assert b"\r" not in raw
    assert hashlib.blake2b(raw, digest_size=DIGEST_SIZE).hexdigest() == expected


def test_repr_names_the_match_and_the_count() -> None:
    journal = Journal(MATCH_ID)
    journal.append(_match_started(1))
    text = repr(journal)
    assert MATCH_ID in text
    assert "events=1" in text
    journal.close()
