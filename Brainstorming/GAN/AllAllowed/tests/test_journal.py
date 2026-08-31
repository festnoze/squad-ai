"""Tests for the journal writer, reader, and hash (W1, CONTRACTS section 3.2).

Why these: the journal is the only source of truth. Monotonic seq gives events a total order, the hash
is the match fingerprint used by ``match verify``, and read_events must round-trip perfectly or replay
would diverge from the live run.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ala.errors import JournalError
from ala.journal import Journal, hash_file, iter_ticks, read_events


def _write_sample(path: Path) -> Journal:
    journal = Journal(path)
    journal.append("match_started", 0, {"seed": 42})
    journal.append("agent_born", 0, {"agent_id": "seat-01", "budget": 100})
    journal.append("submit", 1, {"agent_id": "seat-01", "answer_ppm": 5})
    journal.append("scored", 1, {"agent_id": "seat-01", "answer_ppm": 5, "score": 10, "paid": 100})
    journal.append("match_ended", 2, {"ticks": 2, "final_ranking": ["seat-01"]})
    return journal


def test_append_assigns_monotonic_seq(tmp_path: Path) -> None:
    journal = Journal(tmp_path / "j.jsonl")
    seqs = [
        journal.append("match_started", 0, {}).seq,
        journal.append("agent_born", 0, {"agent_id": "a"}).seq,
        journal.append("submit", 1, {"agent_id": "a", "answer_ppm": 1}).seq,
    ]
    journal.close()
    assert seqs == [0, 1, 2]


def test_append_rejects_unknown_kind(tmp_path: Path) -> None:
    journal = Journal(tmp_path / "j.jsonl")
    with pytest.raises(JournalError):
        journal.append("not_an_event", 0, {})
    journal.close()


def test_hash_is_stable_across_identical_writes(tmp_path: Path) -> None:
    a = _write_sample(tmp_path / "a.jsonl")
    b = _write_sample(tmp_path / "b.jsonl")
    ha, hb = a.hash(), b.hash()
    a.close()
    b.close()
    assert ha == hb


def test_in_memory_hash_matches_file_hash(tmp_path: Path) -> None:
    path = tmp_path / "j.jsonl"
    journal = _write_sample(path)
    live_hash = journal.hash()
    journal.close()
    assert hash_file(path) == live_hash


def test_read_events_roundtrips(tmp_path: Path) -> None:
    path = tmp_path / "j.jsonl"
    journal = _write_sample(path)
    journal.close()
    events = read_events(path)
    assert [e.kind for e in events] == [
        "match_started",
        "agent_born",
        "submit",
        "scored",
        "match_ended",
    ]
    assert [e.seq for e in events] == [0, 1, 2, 3, 4]
    assert events[3].payload == {"agent_id": "seat-01", "answer_ppm": 5, "score": 10, "paid": 100}


def test_canonical_write_rejects_a_float_payload(tmp_path: Path) -> None:
    """A float never reaches the journal file: the canonical serializer refuses it on append."""
    journal = Journal(tmp_path / "j.jsonl")
    with pytest.raises(ValueError):
        journal.append("scored", 1, {"agent_id": "a", "answer_ppm": 5, "score": 10, "paid": 1.5})
    journal.close()


def test_read_events_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(JournalError):
        read_events(tmp_path / "nope.jsonl")


def test_iter_ticks_groups_in_order(tmp_path: Path) -> None:
    path = tmp_path / "j.jsonl"
    journal = _write_sample(path)
    journal.close()
    events = read_events(path)
    grouped = list(iter_ticks(events))
    ticks = [t for t, _ in grouped]
    assert ticks == [0, 1, 2]
    # Tick 0 holds match_started and agent_born; tick 1 holds submit and scored.
    assert [e.kind for e in grouped[0][1]] == ["match_started", "agent_born"]
    assert [e.kind for e in grouped[1][1]] == ["submit", "scored"]
    assert [e.kind for e in grouped[2][1]] == ["match_ended"]


def test_iter_ticks_on_empty_yields_nothing() -> None:
    assert list(iter_ticks([])) == []
