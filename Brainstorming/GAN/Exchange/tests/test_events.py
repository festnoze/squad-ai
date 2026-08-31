"""Anchor tests for :mod:`pxe.events` (A01).

Focus: the journal is the AC-P1 artefact, so these tests guard the encoder, the
line format and the LF rule that a Windows development box breaks by default.
"""

import hashlib

import pytest

from pxe.errors import NonCanonicalValueError
from pxe.events import (
    JOURNAL_ENCODING,
    JOURNAL_NEWLINE,
    ObservationBuilt,
    STPCancelled,
    TickStarted,
    canonical_json,
    event_from_line,
    event_to_line,
    journal_hash,
    journal_hash_from_lines,
    stable_json,
)

_MATCH_ID = "m-election-1-01"


def _sample_events() -> list:
    return [
        TickStarted(seq=1, match_id=_MATCH_ID, tick=1, open_market_ids=("M1", "M2")),
        ObservationBuilt(
            seq=2,
            match_id=_MATCH_ID,
            tick=1,
            agent_id="A1",
            obs_version="1.0",
            n_markets=2,
            n_news=1,
            n_signals=0,
        ),
    ]


# --------------------------------------------------------------------------
# Section 4.2: no float ever reaches the journal
# --------------------------------------------------------------------------
@pytest.mark.determinism
def test_canonical_json_rejects_floats_and_sets() -> None:
    with pytest.raises(NonCanonicalValueError):
        canonical_json({"x": 1.5})
    with pytest.raises(NonCanonicalValueError):
        canonical_json({"x": {1, 2}})


@pytest.mark.determinism
def test_canonical_json_sorts_keys_and_strips_whitespace() -> None:
    assert canonical_json({"b": 1, "a": 2}) == '{"a":2,"b":1}'


def test_stable_json_rounds_floats_without_the_banned_builtin() -> None:
    """Half way values must round up, not to even (section 2.1)."""
    assert stable_json({"x": 0.0000005}) == '{"x":1e-06}'
    assert stable_json({"x": 0.0000015}) == '{"x":2e-06}'


# --------------------------------------------------------------------------
# Section 3.5: the observation renderer is outside the journal
# --------------------------------------------------------------------------
@pytest.mark.determinism
def test_observation_built_carries_no_digest() -> None:
    fields = set(ObservationBuilt.__dataclass_fields__)
    assert "obs_hash" not in fields
    assert "obs_bytes" not in fields
    assert {"agent_id", "obs_version", "n_markets", "n_news", "n_signals"} <= fields


@pytest.mark.determinism
def test_stp_cancelled_carries_no_money() -> None:
    """The released collateral lives on the OrderCancelled that precedes it."""
    fields = set(STPCancelled.__dataclass_fields__)
    assert "released_cents" not in fields
    assert "cancel_seq" in fields


# --------------------------------------------------------------------------
# Section 4.2: LF line endings, and the hash of the bytes
# --------------------------------------------------------------------------
@pytest.mark.determinism
def test_journal_constants_are_lf_utf8() -> None:
    assert JOURNAL_ENCODING == "utf-8"
    assert JOURNAL_NEWLINE == "\n"


@pytest.mark.determinism
def test_written_lines_hash_equals_journal_hash(tmp_path) -> None:
    events = _sample_events()
    path = tmp_path / "journal.jsonl"
    with open(path, "w", encoding=JOURNAL_ENCODING, newline=JOURNAL_NEWLINE) as handle:
        for event in events:
            handle.write(event_to_line(event))
    raw = path.read_bytes()
    assert b"\r" not in raw
    assert hashlib.blake2b(raw, digest_size=32).hexdigest() == journal_hash(events)


@pytest.mark.determinism
def test_crlf_lines_are_rejected_not_normalised() -> None:
    events = _sample_events()
    good = [event_to_line(e) for e in events]
    assert journal_hash_from_lines(good) == journal_hash(events)
    bad = [line.rstrip("\n") + "\r\n" for line in good]
    with pytest.raises(NonCanonicalValueError):
        journal_hash_from_lines(bad)


def test_line_round_trip_preserves_optional_enum_fields() -> None:
    for event in _sample_events():
        assert event_from_line(event_to_line(event)) == event
