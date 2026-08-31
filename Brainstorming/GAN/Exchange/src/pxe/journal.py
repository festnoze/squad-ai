r"""Append only event journal for Prediction Exchange (pxe), CONTRACTS section 7.4.

This module is the **only writer of** ``runs/<match_id>/journal.jsonl`` and the
only reader that turns those bytes back into events. Everything else in the
engine emits through :class:`Journal` and never touches a file handle.

Why this module is safety critical
----------------------------------
The journal is the AC-P1 artefact: two machines run the same seed and compare
``journal_hash``. That comparison is only meaningful if the bytes on disk are
exactly the concatenation of ``canonical_json(event.to_dict()) + "\n"``, so:

1. every file is opened with ``encoding=JOURNAL_ENCODING`` and
   ``newline=JOURNAL_NEWLINE`` (that is ``"utf-8"`` and ``"\n"``). The default
   text mode of :func:`open` rewrites ``"\n"`` into ``"\r\n"`` on Windows, the
   primary development platform here, which would leave the in-memory hash
   right and the file wrong;
2. a line holding a carriage return is **rejected**, never normalised away, on
   the way in as well as on the way out (:func:`read_journal` mirrors
   :func:`pxe.events.journal_hash_from_lines` here);
3. the line is built at append time, even when no path was given, so a float in
   a payload raises :class:`~pxe.errors.NonCanonicalValueError` at the emitting
   call site instead of at the next flush.

Ownership (CONTRACTS section 4.5): this module appends whatever an emitter hands
it and never invents an event. ``seq`` is assigned here, and here only, which is
what makes "``seq`` starts at 1 and increases by exactly 1" a property of the
type rather than a convention.
"""

import hashlib
import logging
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any, Literal, TextIO, TypeVar

from pxe.errors import JournalHashMismatchError, NonCanonicalValueError, StoreError
from pxe.events import (
    JOURNAL_ENCODING,
    JOURNAL_NEWLINE,
    Event,
    MatchEnded,
    MatchStarted,
    event_from_line,
    event_to_line,
    journal_hash,
)

__all__ = [
    "Journal",
    "read_journal",
    "write_journal",
    "verify_journal",
    "iter_ticks",
    "filter_events",
]

_LOG = logging.getLogger("pxe.journal")

#: Digest size of the journal hash, in bytes. blake2b-256, as section 4.3.
_HASH_DIGEST_SIZE = 32

E = TypeVar("E", bound=Event)


def _reject_carriage_return(line: str, index: int) -> None:
    r"""Raise when a journal line holds a carriage return (section 4.2).

    Args:
        line: The raw line, read with ``newline=JOURNAL_NEWLINE``.
        index: 0 based position of the line in the file, for the error context.

    Raises:
        NonCanonicalValueError: If the line contains ``"\\r"``.
    """
    if "\r" in line:
        raise NonCanonicalValueError(
            "journal lines must use LF endings; open the file with newline=JOURNAL_NEWLINE",
            path=f"$[{index}]",
            value="carriage return",
        )


def _open_for_write(path: Path, mode: Literal["w", "a"]) -> TextIO:
    """Open a journal file with the one and only legal set of arguments.

    Args:
        path: Target file. Missing parent directories are created.
        mode: ``"w"`` for a fresh file, ``"a"`` for an append.

    Returns:
        The open text handle, LF only, UTF-8 without a BOM.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    return open(path, mode, encoding=JOURNAL_ENCODING, newline=JOURNAL_NEWLINE)


class Journal:
    r"""Append only event log. The only writer of journal.jsonl.

    The file is opened exactly as
    ``open(path, "w", encoding=JOURNAL_ENCODING, newline=JOURNAL_NEWLINE)``
    (that is ``encoding="utf-8"``, ``newline="\n"``). Never the text mode
    default: on Windows it turns ``"\n"`` into ``"\r\n"`` and the bytes on disk
    stop matching ``journal_hash()``. Reads use ``newline="\n"`` too, so a stray
    ``"\r"`` is not swallowed by universal newline translation.

    A journal with ``path=None`` is a pure in memory log: it validates and
    numbers events exactly the same way, and :meth:`hash` returns the same
    digest a written file would have. That is the mode unit tests use.

    Attributes are exposed as read only properties on purpose: an ``seq``
    assigned twice, or a ``match_id`` changed halfway through, is an AC-P1
    failure that no later check can repair.
    """

    __slots__ = ("_match_id", "_path", "_events", "_pending", "_buffer_size", "_handle", "_closed")

    def __init__(self, match_id: str, path: Path | None = None, *, buffer_size: int = 256) -> None:
        """Open a fresh journal for one match.

        Args:
            match_id: Match this journal belongs to. Every appended event must
                carry exactly this id.
            path: Destination file, or ``None`` for an in memory journal.
                Parent directories are created. An existing file is truncated:
                a journal is written once, from ``seq`` 1.
            buffer_size: Number of pending lines held before they are handed to
                the operating system. Must be at least 1. It changes nothing
                about the bytes, only how often they are written.

        Raises:
            StoreError: If ``buffer_size`` is below 1.
        """
        if buffer_size < 1:
            raise StoreError("buffer_size must be at least 1", buffer_size=buffer_size)
        self._match_id = match_id
        self._path = path
        self._events: list[Event] = []
        self._pending: list[str] = []
        self._buffer_size = buffer_size
        self._closed = False
        self._handle: TextIO | None = _open_for_write(path, "w") if path is not None else None

    # ------------------------------------------------------------------
    # Read only state
    # ------------------------------------------------------------------
    @property
    def match_id(self) -> str:
        """Match id every event of this journal carries."""
        return self._match_id

    @property
    def path(self) -> Path | None:
        """Destination file, or ``None`` for an in memory journal."""
        return self._path

    @property
    def next_seq(self) -> int:
        """``seq`` the next appended event must carry. Starts at 1."""
        return len(self._events) + 1

    @property
    def events(self) -> tuple[Event, ...]:
        """Every event appended so far, in ``seq`` order."""
        return tuple(self._events)

    # ------------------------------------------------------------------
    # Writing
    # ------------------------------------------------------------------
    def emit(self, event_cls: type[E], *, tick: int, **payload: Any) -> E:
        """Build the event with the next seq and this match_id, append, return it.

        This is the call every emitter of section 4.5 uses. The envelope
        (``seq``, ``match_id``) is never passed by the caller, which is what
        stops two emitters from choosing the same ``seq``.

        Args:
            event_cls: Concrete event class, one of the 24 of section 4.5.
            tick: Tick the event belongs to. ``0`` for
                :class:`~pxe.events.MatchStarted` and ``ticks_total + 1`` for
                every finalisation event (section 5.0).
            **payload: The event's own fields, by keyword.

        Returns:
            The freshly built and appended event, typed as the class passed in.

        Raises:
            NonCanonicalValueError: If a payload value cannot be canonically
                serialised (a float, a set, an unsupported type).
            StoreError: If the journal is closed.
        """
        event = event_cls(seq=self.next_seq, match_id=self._match_id, tick=tick, **payload)
        self.append(event)
        return event

    def append(self, event: Event) -> Event:
        """Append a pre-built event. Raises JournalHashMismatchError on a seq gap.

        The same error covers the other half of the envelope: an event carrying
        another match's id would silently corrupt the hash of both journals.

        Args:
            event: Event whose ``seq`` is exactly :attr:`next_seq` and whose
                ``match_id`` is exactly :attr:`match_id`.

        Returns:
            The event that was appended, unchanged.

        Raises:
            JournalHashMismatchError: On a ``seq`` gap or a foreign ``match_id``.
            NonCanonicalValueError: If the event cannot be canonically encoded.
            StoreError: If the journal is closed.
        """
        if self._closed:
            raise StoreError("journal is closed", match_id=self._match_id, seq=event.seq)
        if event.seq != self.next_seq:
            raise JournalHashMismatchError(
                "journal seq must increase by exactly 1",
                match_id=self._match_id,
                expected_seq=self.next_seq,
                actual_seq=event.seq,
                event_type=str(event.TYPE),
            )
        if event.match_id != self._match_id:
            raise JournalHashMismatchError(
                "event belongs to another match",
                expected_match_id=self._match_id,
                actual_match_id=event.match_id,
                seq=event.seq,
            )
        # Encoded now, not at flush time: a float must fail at the emitting call
        # site, and it must fail even for an in memory journal (section 4.2).
        line = event_to_line(event)
        self._events.append(event)
        if self._handle is not None:
            self._pending.append(line)
            if len(self._pending) >= self._buffer_size:
                self.flush()
        return event

    def flush(self) -> None:
        """Write every pending line and flush the handle. No-op in memory."""
        handle = self._handle
        if handle is None:
            self._pending.clear()
            return
        if self._pending:
            handle.write("".join(self._pending))
            self._pending.clear()
        handle.flush()

    def close(self) -> None:
        """Flush and close the file. Idempotent; further appends are refused."""
        if self._closed:
            return
        self.flush()
        if self._handle is not None:
            self._handle.close()
            self._handle = None
        self._closed = True
        _LOG.debug(
            "journal closed",
            extra={"match_id": self._match_id, "event_count": len(self._events)},
        )

    # ------------------------------------------------------------------
    # Hashing
    # ------------------------------------------------------------------
    def hash(self) -> str:
        """Return the blake2b-256 journal digest compared by AC-P1.

        Because a line is exactly what is written to disk, this digest equals
        the digest of the ``journal.jsonl`` bytes once the journal is flushed.
        ``tests/test_journal.py::test_file_bytes_hash_equals_journal_hash``
        pins that equality against a real file.

        Returns:
            A 64 character lowercase hex digest.
        """
        return journal_hash(self._events)

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------
    def __enter__(self) -> "Journal":
        """Return the journal itself, so ``with Journal(...) as j`` reads well."""
        return self

    def __exit__(self, *exc: Any) -> None:
        """Close the journal, whether the block succeeded or raised."""
        self.close()

    def __repr__(self) -> str:
        """Render the match id, the event count and the destination."""
        return f"Journal(match_id={self._match_id!r}, events={len(self._events)}, path={self._path!r})"


# --------------------------------------------------------------------------
# Module level helpers
# --------------------------------------------------------------------------
def read_journal(path: Path) -> tuple[Event, ...]:
    r"""Opens with encoding=JOURNAL_ENCODING, newline=JOURNAL_NEWLINE.

    Reading with an explicit ``newline`` is what makes a CRLF journal
    detectable: universal newline mode would hand back clean ``"\\n"`` lines and
    the corruption would only surface once two machines compared files.

    Args:
        path: The ``journal.jsonl`` file.

    Returns:
        Every event of the file, in file order.

    Raises:
        NonCanonicalValueError: If a line contains a carriage return.
        ValueError: If a line is not a valid event object.
    """
    events: list[Event] = []
    with open(path, encoding=JOURNAL_ENCODING, newline=JOURNAL_NEWLINE) as handle:
        for index, raw in enumerate(handle):
            _reject_carriage_return(raw, index)
            line = raw.rstrip("\n")
            if not line:
                continue
            events.append(event_from_line(line))
    return tuple(events)


def write_journal(path: Path, events: Sequence[Event]) -> str:
    """Write and return the journal hash. Same open() arguments as Journal.

    Used for a journal held in memory (a golden fixture, a re-serialisation
    after a read). The envelope is not re-checked here: call
    :func:`verify_journal` first when the events did not come from a
    :class:`Journal`.

    Args:
        path: Destination file. Parent directories are created, an existing
            file is truncated.
        events: Events in ``seq`` order.

    Returns:
        The blake2b-256 hex digest of the bytes just written.

    Raises:
        NonCanonicalValueError: If an event cannot be canonically encoded.
    """
    digest = hashlib.blake2b(digest_size=_HASH_DIGEST_SIZE)
    with _open_for_write(path, "w") as handle:
        for event in events:
            line = event_to_line(event)
            handle.write(line)
            digest.update(line.encode(JOURNAL_ENCODING))
    return digest.hexdigest()


def verify_journal(events: Sequence[Event]) -> None:
    """Raise JournalHashMismatchError if seq, tick ordering or envelope is broken.

    The checks are exactly the guarantees of section 4.4, and no more: a journal
    read halfway through a match has no :class:`~pxe.events.MatchEnded` yet and
    is still valid.

    1. the journal is not empty;
    2. every event carries the same ``match_id``;
    3. ``seq`` is ``1, 2, 3, ...`` with no gap and no repeat;
    4. ``tick`` never decreases;
    5. :class:`~pxe.events.MatchStarted`, when present, is the first event, with
       ``seq == 1`` and ``tick == 0``;
    6. :class:`~pxe.events.MatchEnded`, when present, is the last event.

    Args:
        events: Events in file order.

    Raises:
        JournalHashMismatchError: On any breach of the six rules above.
    """
    if not events:
        raise JournalHashMismatchError("journal is empty")
    match_id = events[0].match_id
    previous_tick = events[0].tick
    last_index = len(events) - 1
    for index, event in enumerate(events):
        expected_seq = index + 1
        if event.seq != expected_seq:
            raise JournalHashMismatchError(
                "journal seq must increase by exactly 1",
                match_id=match_id,
                expected_seq=expected_seq,
                actual_seq=event.seq,
                event_type=str(event.TYPE),
            )
        if event.match_id != match_id:
            raise JournalHashMismatchError(
                "journal mixes two match ids",
                expected_match_id=match_id,
                actual_match_id=event.match_id,
                seq=event.seq,
            )
        if event.tick < previous_tick:
            raise JournalHashMismatchError(
                "journal ticks must never decrease",
                match_id=match_id,
                seq=event.seq,
                previous_tick=previous_tick,
                actual_tick=event.tick,
            )
        previous_tick = event.tick
        if isinstance(event, MatchStarted) and (index != 0 or event.seq != 1 or event.tick != 0):
            raise JournalHashMismatchError(
                "match_started must be seq 1 at tick 0",
                match_id=match_id,
                seq=event.seq,
                tick=event.tick,
            )
        if isinstance(event, MatchEnded) and index != last_index:
            raise JournalHashMismatchError(
                "match_ended must be the last event",
                match_id=match_id,
                seq=event.seq,
                event_count=len(events),
            )


def iter_ticks(events: Sequence[Event]) -> Iterator[tuple[int, tuple[Event, ...]]]:
    """Group events by tick, ascending, preserving the order inside a tick.

    Exactly one entry per distinct tick, so a consumer cannot see the same tick
    twice; for a journal that respects section 4.4 that is also the file order.
    Ticks ``0`` (:class:`~pxe.events.MatchStarted`) and ``ticks_total + 1``
    (finalisation) are ordinary entries here, which is what makes finalisation
    trivially separable in a projection.

    Args:
        events: Events in ``seq`` order.

    Yields:
        ``(tick, events_of_that_tick)`` pairs, ticks ascending.
    """
    grouped: dict[int, list[Event]] = {}
    for event in events:
        grouped.setdefault(event.tick, []).append(event)
    for tick in sorted(grouped):
        yield tick, tuple(grouped[tick])


def filter_events(events: Sequence[Event], *types: type[Event]) -> tuple[Event, ...]:
    """Keep the events of the given classes, in journal order.

    Args:
        events: Events in ``seq`` order.
        *types: Concrete event classes to keep. With no class given nothing
            matches and the result is empty, never "everything".

    Returns:
        The matching events, order preserved.
    """
    if not types:
        return ()
    kept = tuple(types)
    return tuple(event for event in events if isinstance(event, kept))
