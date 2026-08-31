"""The journal: writer, reader, and hash (W1, CONTRACTS section 3.2).

The journal is the only source of truth. It is a JSONL file, one canonical record per line, appended
in phase order. Its hash is a sha256 over the exact bytes, and two runs of the same seed with scripted
agents must produce the same hash (AC-1). Replay reads the journal back into events and nothing else.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator, Sequence
from pathlib import Path

from ala.errors import JournalError
from ala.events import EVENT_KINDS, JOURNAL_ENCODING, JOURNAL_NEWLINE, Event, canonical_json


class Journal:
    """An append-only event log backed by a file, plus an in-memory mirror for hashing and replay."""

    __slots__ = ("_fh", "_lines", "_path", "_seq")

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._seq = 0
        self._lines: list[bytes] = []
        self._fh = self._path.open("wb")

    @property
    def path(self) -> Path:
        return self._path

    def append(self, kind: str, tick: int, payload: dict[str, object] | None = None) -> Event:
        """Append one event, assigning the monotonic sequence number. Returns the event."""
        if kind not in EVENT_KINDS:
            raise JournalError(f"unknown event kind: {kind!r}")
        event = Event(kind=kind, tick=tick, seq=self._seq, payload=payload or {})
        self._seq += 1
        line = canonical_json(event.to_record())
        self._fh.write(line)
        self._fh.write(JOURNAL_NEWLINE.encode(JOURNAL_ENCODING))
        self._lines.append(line)
        return event

    def flush(self) -> None:
        self._fh.flush()

    def close(self) -> None:
        if not self._fh.closed:
            self._fh.flush()
            self._fh.close()

    def hash(self) -> str:
        """sha256 of the joined bytes of every line, newline separated. This is the match fingerprint."""
        h = hashlib.sha256()
        for line in self._lines:
            h.update(line)
            h.update(JOURNAL_NEWLINE.encode(JOURNAL_ENCODING))
        return h.hexdigest()

    def __enter__(self) -> Journal:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def read_events(path: Path | str) -> list[Event]:
    """Read a journal file back into a list of events, in file order."""
    import json

    events: list[Event] = []
    p = Path(path)
    if not p.exists():
        raise JournalError(f"no journal at {p}")
    with p.open("r", encoding=JOURNAL_ENCODING) as fh:
        for lineno, raw in enumerate(fh, start=1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                record = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise JournalError(f"bad journal line {lineno}: {exc}") from exc
            events.append(Event.from_record(record))
    return events


def hash_file(path: Path | str) -> str:
    """Recompute a journal's hash from its file bytes, for `match verify` and replay checks."""
    p = Path(path)
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for line in fh:
            h.update(line if line.endswith(b"\n") else line + b"\n")
    return h.hexdigest()


def iter_ticks(events: Sequence[Event]) -> Iterator[tuple[int, list[Event]]]:
    """Group events by tick in order, yielding (tick, events_at_tick)."""
    if not events:
        return
    current = events[0].tick
    bucket: list[Event] = []
    for ev in events:
        if ev.tick != current:
            yield current, bucket
            current = ev.tick
            bucket = []
        bucket.append(ev)
    yield current, bucket
