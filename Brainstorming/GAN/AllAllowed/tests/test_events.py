"""Tests for events and the canonical serializer (W0, CONTRACTS section 4).

Why these: ``canonical_json`` is the single producer of journal bytes, and the journal hash is taken
over exactly those bytes. Sorted keys, compact separators, and a hard float rejection are what make two
runs byte-identical and keep the "money is integer" golden rule from silently failing.
"""

from __future__ import annotations

import pytest

from ala.events import EVENT_KINDS, Event, canonical_json


def test_canonical_json_sorts_keys() -> None:
    assert canonical_json({"b": 1, "a": 2}) == b'{"a":2,"b":1}'


def test_canonical_json_uses_compact_separators() -> None:
    out = canonical_json({"x": 1, "y": [1, 2, 3]})
    assert b" " not in out
    assert out == b'{"x":1,"y":[1,2,3]}'


def test_canonical_json_rejects_a_top_level_float() -> None:
    with pytest.raises(ValueError):
        canonical_json({"amount": 1.5})


def test_canonical_json_rejects_a_nested_float() -> None:
    with pytest.raises(ValueError):
        canonical_json({"outer": {"inner": [1, 2, 3.0]}})


def test_canonical_json_allows_bools_and_ints() -> None:
    # Booleans are ints in JSON and must survive; only true floats are rejected.
    assert canonical_json({"ok": True, "n": 0, "neg": -5}) == b'{"n":0,"neg":-5,"ok":true}'


def test_canonical_json_preserves_non_ascii_as_utf8() -> None:
    out = canonical_json({"k": "café"})
    assert out.decode("utf-8") == '{"k":"café"}'


def test_event_record_roundtrips() -> None:
    ev = Event(kind="submit", tick=3, seq=7, payload={"agent_id": "seat-01", "answer_ppm": 42})
    record = ev.to_record()
    back = Event.from_record(record)
    assert back == ev
    assert back.kind == "submit"
    assert back.tick == 3
    assert back.seq == 7
    assert back.payload == {"agent_id": "seat-01", "answer_ppm": 42}


def test_event_from_record_coerces_scalars() -> None:
    # Records read from disk arrive as plain JSON; the ints must come back as ints.
    ev = Event.from_record({"kind": "scored", "tick": "5", "seq": "9", "payload": {"score": 10}})
    assert ev.tick == 5
    assert ev.seq == 9
    assert ev.payload == {"score": 10}


def test_event_from_record_tolerates_missing_payload() -> None:
    ev = Event.from_record({"kind": "match_ended", "tick": 12, "seq": 100})
    assert ev.payload == {}


def test_event_kinds_is_the_closed_v1_set() -> None:
    expected = {
        "match_started",
        "agent_born",
        "tool_called",
        "fs_write",
        "fs_remove",
        "proc_kill",
        "privilege_escalation",
        "board_post",
        "dm_sent",
        "submit",
        "rubric_hash",
        "scored",
        "scorer_skipped",
        "floor_raised",
        "agent_died",
        "agent_cloned",
        "match_ended",
    }
    assert set(EVENT_KINDS) == expected
    assert isinstance(EVENT_KINDS, frozenset)
