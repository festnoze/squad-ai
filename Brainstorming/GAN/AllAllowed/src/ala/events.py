"""Events and canonical serialization (W0, CONTRACTS section 4).

Every state change in a match is an Event appended to the journal. The event set is closed for v1;
adding a kind is a contract change. The canonical serializer is the single source of the journal bytes:
integers only, keys sorted, compact separators, UTF-8, newline terminated. The journal hash is taken
over exactly these bytes, so the serializer is load bearing for determinism (AC-1).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

JOURNAL_ENCODING = "utf-8"
JOURNAL_NEWLINE = "\n"

# The closed set of event kinds. The runner and detectors both key off these strings.
EVENT_KINDS: frozenset[str] = frozenset(
    {
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
)


@dataclass(frozen=True, slots=True)
class Event:
    """One journalled fact. ``tick`` and ``seq`` order it; ``payload`` holds only JSON scalars that are
    integers, strings, booleans, or nested lists and maps of those. No floats, ever."""

    kind: str
    tick: int
    seq: int
    payload: Mapping[str, Any] = field(default_factory=dict)

    def to_record(self) -> dict[str, Any]:
        """Flatten to the dict that becomes one journal line."""
        return {"kind": self.kind, "tick": self.tick, "seq": self.seq, "payload": dict(self.payload)}

    @staticmethod
    def from_record(record: Mapping[str, Any]) -> Event:
        return Event(
            kind=str(record["kind"]),
            tick=int(record["tick"]),
            seq=int(record["seq"]),
            payload=dict(record.get("payload", {})),
        )


def _assert_no_float(value: Any) -> None:
    """Guard: the journal must contain no floats. Booleans are fine (they are ints in JSON)."""
    if isinstance(value, float):
        raise ValueError(f"float in journal payload: {value!r}")
    if isinstance(value, Mapping):
        for v in value.values():
            _assert_no_float(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            _assert_no_float(v)


def canonical_json(record: Mapping[str, Any]) -> bytes:
    """Serialize one record to the exact bytes that go on a journal line (no trailing newline).

    Keys are sorted, separators are compact, non-ascii is preserved as UTF-8. A float anywhere raises,
    which keeps the golden-rule that money and probabilities are integers from silently breaking.
    """
    _assert_no_float(record)
    text = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return text.encode(JOURNAL_ENCODING)
