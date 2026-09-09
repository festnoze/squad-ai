"""The run calendar: which bars a run has, and what each instrument is at every one of them.

A run is a **calendar of bars**, never a per-market tick list (PRD 4.1): one bar timestamp at a time, in
ascending order, with every instrument of the run judged against the same instant. This module owns that
timeline and the five predicates the whole engine reads off it (CONTRACTS_V2 sections 5.2, 5.3, 8.2, 16.2
and 17.2), so that E2's queue drain, E5's phase loop and E1's own observation builder cannot each invent
their own answer to "is this market tradable now" and disagree by one bar.

Three rules carry the design, and each of them exists because a leak with money attached was found behind
its absence:

* **Only a bar entirely inside the trading window is tradable** (ruling R9). On a daily grid the bar that
  contains ``close_at_ms``, and the settling bar, carry prints made after the venue closed and after the
  outcome was known (the election-night tape at 9 900 bp). ``tradable`` therefore requires
  ``t + interval_ms <= close_at_ms`` and refuses the settling bar, and no fill may land anywhere else.
* **A decision is worth taking one bar earlier than a fill may land** (amendment C1, section 16.2). An
  action decided at ``t`` executes at the open of the instrument's **next** bar, so ``actionable(i, t)``
  is ``tradable(i, next_bar(i, t))``. A market's last actionable bar is one bar before its last tradable
  bar, and the action decided on the last tradable bar has nowhere to fill: that is the rule, not a
  defect to be patched.
* **The run calendar is the union of the instruments' bar timestamps** (amendment C1b, section 17.2,
  ruling R149). A grid point at which no instrument of the run has a bar is not a bar of the run and
  produces no event: on a run of session instruments alone a weekend simply does not exist, and on a run
  that carries one binary every grid point is a bar, exactly as it was before the amendment.

The three lookups ``last_bar``, ``next_bar`` and ``prev_bar`` are declared here once (ruling R187)
because four other places need them and none of them may compute its own: the queue drain of 17.2,
``decided_at_ms`` (R192), ``applies_at`` (R175) and the forced flat of 17.3. ``last_bar(i)`` is future
information about a continuous instrument (7.9), which is why the observation builder never renders it
and ``MarketView.tradable`` carries ``open(i, t)`` on a continuous instrument instead (ruling R181).

Nothing here reads a tape unless it has to: the predicates are computed from ``MarketMeta``, the
leak-free projection, because a binary's bars are dense on the grid from ``bar_of(created_at_ms)`` to
``bar_of(resolved_at_ms)`` (section 5.2, enforced by the loader) and that is exactly the set of bars at
which the market is open. A continuous instrument's bars are dense **on its session calendar**, so its
open bars are the grid points inside a session, which is the one case that reads the instrument (for its
``session_calendar_id``) and the dataset's sealed calendars.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final, Protocol

from pmx.data.sessions import next_bar_ms, session_bars
from pmx.errors import InvalidConfigError, SchemaError
from pmx.types import (
    CONTINUOUS_CALENDAR_ID,
    DECISION_LATENCY_BARS,
    INSTRUMENT_KINDS,
    Bar,
    Dataset,
    Instrument,
    MarketMeta,
    RunConfig,
    Session,
    SessionCalendar,
    Trade,
    bar_of,
    interval_ms,
    sorted_market_ids,
)

#: ``INSTRUMENT_KINDS[0]``: the one kind with a resolution (section 17.1).
KIND_BINARY = INSTRUMENT_KINDS[0]


def meta_kind(meta: MarketMeta) -> str:
    """The kind of one instrument as the run's calendar reads it (ruling R144, section 17.1).

    ``MarketMeta.kind`` is ``pmx.types``' field and defaults to ``binary``, so a meta written before
    amendment C1b names the one kind that has a resolution. The value is checked here as well as in
    ``MarketMeta`` itself, because this is the reader every phase of the bar loop goes through and a kind
    outside ``INSTRUMENT_KINDS`` would otherwise pick a code path by falling off the binary branch.

    Ruling R207 (section 13.1): the engine's reader raises ``SchemaError``, because the kind came from a
    file, while ``pmx.types.MarketMeta.__post_init__`` keeps ``InvalidConfigError`` for a meta *built* with
    a kind outside the table, which is a construction error and not a file's. Two conditions, two errors.
    """
    kind = str(getattr(meta, "kind", KIND_BINARY))
    if kind not in INSTRUMENT_KINDS:
        raise SchemaError("unknown instrument kind", market_id=meta.id, kind=kind)
    return kind

# --------------------------------------------------------------------------------------------------
# The slice of one bar
# --------------------------------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class BarSlice:
    """What one bar of the run is, told once so every phase of section 8.2 agrees (section 8.3).

    Every tuple is in ``market_id`` order (section 3: markets inside an observation, an action set or a
    settlement loop are ordered by id), so a journal written from these tuples is byte-stable.

    ``closing_ids`` is amendment C1b's (ruling R187): the continuous instruments whose ``last_bar`` is
    this bar, which is where the forced flat of 17.3 happens and where the runner emits
    ``instrument_closed``. It is empty on a binary run, and it is deliberately **not** derivable inside an
    observation: ``last_bar(i)`` is future information (7.9).
    """

    t_ms: int
    open_ids: tuple[str, ...]
    tradable_ids: tuple[str, ...]
    settling_ids: tuple[str, ...]
    listed_ids: tuple[str, ...]
    closing_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "t_ms": self.t_ms,
            "open_ids": list(self.open_ids),
            "tradable_ids": list(self.tradable_ids),
            "settling_ids": list(self.settling_ids),
            "listed_ids": list(self.listed_ids),
            "closing_ids": list(self.closing_ids),
        }


@dataclass(frozen=True, slots=True)
class _Entry:
    """One instrument's timeline inside the run, precomputed from its metadata.

    ``session_bars`` is filled only for a continuous instrument whose calendar has gaps: a binary and a
    24/7 instrument are contiguous on the grid, and a range needs no list. ``first_ms`` and ``last_ms``
    are the first and the last bar of the run at which the instrument is **open**, already clamped into
    ``[t0_ms, t1_ms)``; ``last_ms`` is ``last_bar(i)`` for every kind.

    ``sessions`` and ``session_closes`` are the instrument's **whole** sealed calendar, which is not the
    same object as ``session_bars``: the run window clamps what the engine may process, and it may not
    clamp what the venue's published schedule says. ``venue_next_bar`` is the difference, and it is a
    leak boundary rather than a convenience (see :meth:`Calendar.session_next_bar`).
    """

    market_id: str
    kind: str
    interval_min: int
    close_at_ms: int
    settles_at_ms: int
    first_ms: int
    last_ms: int
    session_bars: tuple[int, ...] = ()
    session_bar_set: frozenset[int] = field(default_factory=frozenset)
    sessions: tuple[Session, ...] = ()
    session_closes: tuple[int, ...] = ()

    @property
    def in_run(self) -> bool:
        """Does the instrument have at least one bar inside the run?"""
        return self.first_ms <= self.last_ms

    @property
    def is_continuous(self) -> bool:
        return self.kind != KIND_BINARY

    def is_open(self, t_ms: int) -> bool:
        if not self.in_run or not self.first_ms <= t_ms <= self.last_ms:
            return False
        if self.session_bars:
            return t_ms in self.session_bar_set
        return True

    def venue_next_bar(self, t_ms: int) -> int | None:
        """The next grid point after ``t_ms`` at which the **venue** has a bar, run window ignored.

        It is the sealed calendar's answer and nothing else: no run window, no delisting, no clamp. A
        24/7 instrument (and a binary, whose calendar is the synthesised ``continuous`` one) answers the
        next grid point; a session instrument answers the first grid point that intersects its next
        session, which after a Friday close is Monday. ``None`` means the sealed calendar has no session
        left, which on a real dataset means the calendar's window has ended. The arithmetic is
        ``pmx.data.sessions.next_bar_ms`` (D1's, ruling R174), the one implementation.
        """
        if not self.sessions:
            return bar_of(t_ms, self.interval_min) + interval_ms(self.interval_min)
        return next_bar_ms(self.sessions, t_ms, interval_min=self.interval_min)


# --------------------------------------------------------------------------------------------------
# The calendar
# --------------------------------------------------------------------------------------------------
class Calendar:
    """The bars of one run and every predicate of sections 5.3 and 17.2 over them.

    ``Calendar(dataset, config)`` is the contract's constructor (section 8.3). ``calendars`` is a
    keyword-only addition with a default, for the reason E2's ``Execution`` also takes one (8.6, ruling
    R174): a caller that already holds the run's sealed calendars can hand them over. When it is omitted
    the calendars come from ``Dataset.calendar`` (7.2), which synthesises ``continuous`` and reads every
    other one from the sealed ``calendars/`` directory, so a continuous instrument naming a calendar the
    dataset does not carry is refused (``SchemaError``) rather than silently treated as trading around
    the clock: a wrong session set moves every fill of the instrument.
    """

    __slots__ = ("_config", "_dataset", "_entries", "_interval_ms", "_order", "_t0_ms", "_t1_ms")

    def __init__(
        self,
        dataset: Dataset,
        config: RunConfig,
        *,
        calendars: Mapping[str, SessionCalendar] | None = None,
    ) -> None:
        self._dataset = dataset
        self._config = config
        self._interval_ms = interval_ms(config.interval_min)
        metas = _run_metas(dataset, config)
        _check_one_grid(dataset, config, metas)
        self._t0_ms, self._t1_ms = _run_window(config, metas)
        entries: dict[str, _Entry] = {}
        for meta in metas:
            entry = self._entry_of(meta, calendars)
            if entry.in_run:
                entries[meta.id] = entry
        self._entries = entries
        # The iteration order of a dict is never an output order (section 3): the ids are sorted once,
        # here, and every tuple this class returns is built from this sequence.
        self._order = sorted_market_ids(entries)

    # ---- the contract's four members ------------------------------------------------------------
    @property
    def t0_ms(self) -> int:
        """The first bar the run processes, inclusive."""
        return self._t0_ms

    @property
    def t1_ms(self) -> int:
        """The end of the run, exclusive. It is never shown to an agent (section 8.3)."""
        return self._t1_ms

    def bars(self) -> Iterator[BarSlice]:
        """Every bar of the run, ascending: the union of the instruments' bars (17.2, ruling R149).

        A grid point at which no instrument is open is not yielded at all, so a weekend of an
        equity-only run produces no ``bar_opened`` and no event of any kind. On a run that carries a
        binary every grid point in ``[t0_ms, t1_ms)`` is a bar, because a binary's bars are dense.
        """
        t_ms = self._t0_ms
        while t_ms < self._t1_ms:
            slice_ = self.bar_slice(t_ms)
            if slice_.open_ids:
                yield slice_
            t_ms += self._interval_ms

    def last_bar(self, market_id: str) -> int:
        """``last_bar(i)`` of section 17.2: the last bar of the run at which the instrument is open.

        For a continuous instrument this is the bar of the forced flat (17.3) and the bar
        ``instrument_closed`` names; for a binary it is its settling bar, or the run's last bar when the
        run ends first. It is future information about a continuous instrument and never reaches an
        observation (7.9, ruling R181).
        """
        return self._entry(market_id).last_ms

    def next_bar(self, market_id: str, t_ms: int) -> int | None:
        """The instrument's next bar strictly after ``t_ms``, inside the run, or ``None``.

        On a session calendar this is Monday's first bar after Friday's last one, which is what the
        latency rule of 16.2 reads and what the queue of 8.6 waits for.
        """
        entry = self._entry(market_id)
        if entry.session_bars:
            index = bisect_right(entry.session_bars, t_ms)
            return entry.session_bars[index] if index < len(entry.session_bars) else None
        candidate = bar_of(t_ms, entry.interval_min) + self._interval_ms
        if candidate < entry.first_ms:
            candidate = entry.first_ms
        return candidate if candidate <= entry.last_ms else None

    def session_next_bar(self, market_id: str, t_ms: int) -> int | None:
        """The **venue's** next bar for the instrument, from the sealed calendar, ignoring the run window.

        This is not :meth:`next_bar` and the difference is a leak, not a nicety. ``next_bar`` answers
        "what does this run process next", which is clamped by ``t1_ms`` and by ``last_bar(i)``, and is
        what the queue drain of 17.2 and ``decided_at_ms`` (R192) must read. ``MarketView`` carries
        ``hours_to_next_bar`` computed "from the sealed calendar (public, the venue's rule)" (8.3), and
        the two answers differ at exactly the bars where the difference matters: on ``last_bar(i)`` the
        clamped lookup returns nothing, so an observation built from it would publish ``0`` hours and
        announce the instrument's last bar and the run's ``t1_ms``, both of which 7.9 forbids. The venue's
        schedule is not a datum about the future (7.9), so it is answered in full.
        """
        return self._entry(market_id).venue_next_bar(t_ms)

    def prev_bar(self, market_id: str, t_ms: int) -> int | None:
        """The instrument's last bar strictly before ``t_ms``, inside the run, or ``None``.

        ``applies_at`` of section 17.3 reads it for a dividend, a split and a roll: the last bar priced
        in the old regime (ruling R175). ``None`` means the event has no bar to apply at in this run and
        is therefore not applied, because no position can exist before the run's first bar.
        """
        entry = self._entry(market_id)
        if entry.session_bars:
            index = bisect_left(entry.session_bars, t_ms)
            return entry.session_bars[index - 1] if index > 0 else None
        candidate = bar_of(t_ms, entry.interval_min)
        if candidate >= t_ms:
            candidate -= self._interval_ms
        if candidate > entry.last_ms:
            candidate = entry.last_ms
        return candidate if candidate >= entry.first_ms else None

    # ---- the predicates of sections 5.3 and 17.2 ------------------------------------------------
    def market_ids(self) -> tuple[str, ...]:
        """Every instrument of the run that has at least one bar in it, in ``market_id`` order."""
        return self._order

    def kind_of(self, market_id: str) -> str:
        """The instrument's kind, one of ``INSTRUMENT_KINDS`` (``binary`` for a ``Market``)."""
        return self._entry(market_id).kind

    def is_listed(self, market_id: str, t_ms: int) -> bool:
        """``listed(i, t)``: the instrument exists at this bar, in session or not."""
        entry = self._entry(market_id)
        return entry.in_run and entry.first_ms <= t_ms <= entry.last_ms

    def is_open(self, market_id: str, t_ms: int) -> bool:
        """``open(i, t)``: what an observation carries. Listed, not settled before ``t``, in session."""
        return self._entry(market_id).is_open(t_ms)

    def settles(self, market_id: str, t_ms: int) -> bool:
        """``settles(i, t)``: the bar that contains ``resolved_at_ms``. Never true for a continuous kind."""
        entry = self._entry(market_id)
        if entry.is_continuous:
            return False
        return entry.settles_at_ms == t_ms

    def closes(self, market_id: str, t_ms: int) -> bool:
        """``closes(i, t) = (t == last_bar(i))`` of 17.2: the forced-flat bar. Continuous kinds only."""
        entry = self._entry(market_id)
        return entry.is_continuous and entry.in_run and entry.last_ms == t_ms

    def is_tradable(self, market_id: str, t_ms: int) -> bool:
        """``tradable(i, t)``: a fill may land on this bar, and on no other (ruling R9).

        Binary: open, the whole bar inside the trading window (``t + interval_ms <= close_at_ms``), and
        not the settling bar. Continuous: open and before ``last_bar(i)``, whose only fill is the
        engine's forced flat.
        """
        entry = self._entry(market_id)
        if not entry.is_open(t_ms):
            return False
        if entry.is_continuous:
            return t_ms < entry.last_ms
        return t_ms + self._interval_ms <= entry.close_at_ms and entry.settles_at_ms != t_ms

    def is_actionable(self, market_id: str, t_ms: int) -> bool:
        """``actionable(i, t) = tradable(i, next_bar(i, t))`` (section 16.2).

        The predicate a **decision** is worth taking under, one bar of latency ahead of the fill. An
        instrument with no next bar in the run is not actionable at ``t``: an action decided on the run's
        last bar has no execute phase to drain it.
        """
        if DECISION_LATENCY_BARS != 1:  # pragma: no cover - the constant is 1 and 16.2 forbids a config field
            raise InvalidConfigError("DECISION_LATENCY_BARS is one bar", value=DECISION_LATENCY_BARS)
        nxt = self.next_bar(market_id, t_ms)
        return nxt is not None and self.is_tradable(market_id, nxt)

    def bar_slice(self, t_ms: int) -> BarSlice:
        """The four sets and the closing set of one bar, in ``market_id`` order (section 8.2, phase 1)."""
        open_ids: list[str] = []
        tradable_ids: list[str] = []
        settling_ids: list[str] = []
        listed_ids: list[str] = []
        closing_ids: list[str] = []
        for market_id in self._order:
            entry = self._entries[market_id]
            if not entry.is_open(t_ms):
                continue
            open_ids.append(market_id)
            if self.is_tradable(market_id, t_ms):
                tradable_ids.append(market_id)
            if not entry.is_continuous and entry.settles_at_ms == t_ms:
                settling_ids.append(market_id)
            if entry.first_ms == t_ms:
                listed_ids.append(market_id)
            if entry.is_continuous and entry.last_ms == t_ms:
                closing_ids.append(market_id)
        return BarSlice(
            t_ms=t_ms,
            open_ids=tuple(open_ids),
            tradable_ids=tuple(tradable_ids),
            settling_ids=tuple(settling_ids),
            listed_ids=tuple(listed_ids),
            closing_ids=tuple(closing_ids),
        )

    # ---- internals ------------------------------------------------------------------------------
    @property
    def interval_ms(self) -> int:
        return self._interval_ms

    def _entry(self, market_id: str) -> _Entry:
        entry = self._entries.get(market_id)
        if entry is None:
            raise SchemaError(
                "market is not in the run's calendar",
                market_id=market_id,
                dataset=self._dataset.manifest.name,
                fold=self._config.fold,
            )
        return entry

    def _entry_of(self, meta: MarketMeta, calendars: Mapping[str, SessionCalendar] | None) -> _Entry:
        kind = meta_kind(meta)
        span = self._interval_ms
        first_ms = max(bar_of(meta.created_at_ms, meta.interval_min), self._t0_ms)
        if kind == KIND_BINARY:
            settles_at_ms = bar_of(meta.resolved_at_ms, meta.interval_min)
            return _Entry(
                market_id=meta.id,
                kind=kind,
                interval_min=meta.interval_min,
                close_at_ms=meta.close_at_ms,
                settles_at_ms=settles_at_ms,
                first_ms=first_ms,
                last_ms=min(settles_at_ms, self._last_grid_bar()),
            )
        # A continuous instrument is listed while ``t < bar_of(delisted_at_ms)`` (17.2), so the bar that
        # **contains** the delisting instant is not a bar of the instrument and the last one is the bar
        # before it, whatever the instant's alignment (ruling R150: "the bar before
        # ``bar_of(delisted_at_ms)``"). With no delisting the instrument is listed to the end of the run,
        # which is where the window clamps it. ``MarketMeta`` cannot tell the two apart, because R186
        # collapses ``delisted_at_ms`` and the dataset's window end into one ``resolved_at_ms``, so the
        # field is read from the instrument record (gate G2 ruling: the record is the one place it lives).
        instrument = self._dataset.market(meta.id).instrument
        delisted_at_ms = instrument.delisted_at_ms
        last_open = (
            self._last_grid_bar()
            if delisted_at_ms is None
            else bar_of(int(delisted_at_ms), meta.interval_min) - span
        )
        last_ms = min(last_open, self._last_grid_bar())
        sessions = self._sessions_for(meta, instrument, calendars)
        if sessions is None:
            return _Entry(
                market_id=meta.id,
                kind=kind,
                interval_min=meta.interval_min,
                close_at_ms=0,
                settles_at_ms=-1,
                first_ms=first_ms,
                last_ms=last_ms,
            )
        bars = (
            session_bars(sessions, start_ms=first_ms, end_ms=last_ms + span, interval_min=meta.interval_min)
            if first_ms <= last_ms
            else ()
        )
        if not bars:
            # ``first_ms > last_ms`` is ``in_run == False``: the instrument has no bar in this run and is
            # not one of its instruments at all, rather than an instrument that is never open.
            return _Entry(
                market_id=meta.id,
                kind=kind,
                interval_min=meta.interval_min,
                close_at_ms=0,
                settles_at_ms=-1,
                first_ms=1,
                last_ms=0,
            )
        return _Entry(
            market_id=meta.id,
            kind=kind,
            interval_min=meta.interval_min,
            close_at_ms=0,
            settles_at_ms=-1,
            first_ms=bars[0],
            last_ms=bars[-1],
            session_bars=bars,
            session_bar_set=frozenset(bars),
            sessions=tuple(sessions),
            session_closes=tuple(session.close_ms for session in sessions),
        )

    def _last_grid_bar(self) -> int:
        return self._t1_ms - self._interval_ms

    def _sessions_for(
        self,
        meta: MarketMeta,
        instrument: Instrument,
        calendars: Mapping[str, SessionCalendar] | None,
    ) -> Sequence[Session] | None:
        """The sessions of a continuous instrument's calendar, or ``None`` for a 24/7 instrument.

        ``None`` is the synthesised ``continuous`` calendar of ruling R185 (one session covering
        everything), which is why it is never read from a file and never produces a gap.
        """
        calendar_id = instrument.session_calendar_id
        if calendar_id == CONTINUOUS_CALENDAR_ID:
            return None
        if calendars is not None and calendar_id in calendars:
            return calendars[calendar_id].sessions
        try:
            return self._dataset.calendar(calendar_id).sessions
        except SchemaError as error:
            raise SchemaError(
                "no session calendar available for a continuous instrument",
                market_id=meta.id,
                calendar_id=calendar_id,
                dataset=self._dataset.manifest.name,
            ) from error


# --------------------------------------------------------------------------------------------------
# When a cash event applies: ruling R175, in one place
# --------------------------------------------------------------------------------------------------
#: The three kinds whose application bar is the last bar priced in the **old** regime (ruling R175).
#: Every name is one of ``pmx.types.CASH_EVENT_KINDS``; the other four apply at ``bar_of(t_ms)``.
OLD_REGIME_KINDS: Final = ("dividend", "split", "roll")


class BarLookups(Protocol):
    """The three bar lookups of section 8.3 (ruling R187), which ``applies_at`` and E2's queue read.

    :class:`Calendar` is the one implementation for a run; ``Execution`` builds an equivalent over the
    session calendars it was handed, because 8.6 gives it those and not a ``Calendar``. Declared here
    rather than twice, so a caller cannot satisfy one lookup surface and fail the other.
    """

    def last_bar(self, market_id: str) -> int: ...

    def next_bar(self, market_id: str, t_ms: int) -> int | None: ...

    def prev_bar(self, market_id: str, t_ms: int) -> int | None: ...


class CashEventStamp(Protocol):
    """What :func:`applies_at` reads of a cash event: the kind and the instant (section 17.3).

    Structural, and only these two members, so the one rule is callable from the leak boundary and from
    the module that moves money without either of them naming the other's protocols.
    """

    @property
    def kind(self) -> str: ...

    @property
    def t_ms(self) -> int: ...


class InstrumentClock(Protocol):
    """What :func:`applies_at` reads of an instrument: its id and its bar interval (section 17.1)."""

    @property
    def id(self) -> str: ...

    @property
    def interval_min(self) -> int: ...


class InstrumentLike(Protocol):
    """The instrument surface the engine reads (sections 7.2 and 17.1), declared once (ruling R205).

    The union of what execution and the observation builder read: a ``Market`` and a
    ``ContinuousInstrument`` both satisfy it, and neither half of the engine declares its own copy, so a
    caller cannot satisfy one surface and fail the other. Every member is read-only, which a frozen
    dataclass field and a property both satisfy; the two per-kind spellings the base resolves
    (``listed_at_ms`` for ``created_at_ms``, ``first_price_ticks`` for ``first_price_bp``) are read through
    the builder's accessors and are deliberately not members.
    """

    @property
    def id(self) -> str: ...

    @property
    def provider(self) -> str: ...

    @property
    def url(self) -> str: ...

    @property
    def description(self) -> str: ...

    @property
    def category(self) -> str: ...

    @property
    def tags(self) -> tuple[str, ...]: ...

    @property
    def currency(self) -> str: ...

    @property
    def source(self) -> str: ...

    @property
    def interval_min(self) -> int: ...

    @property
    def bars(self) -> tuple[Bar, ...]: ...

    @property
    def trades(self) -> tuple[Trade, ...]: ...

    @property
    def fee_schedule_id(self) -> str: ...

    def bar_at(self, t_ms: int) -> Bar | None: ...

    def bars_before(self, now_ms: int, limit: int) -> tuple[Bar, ...]: ...


class CashEventLike(Protocol):
    """One dated cash event, ``pmx.types.CashEvent`` (section 17.3), declared once (ruling R205)."""

    @property
    def cash_event_id(self) -> str: ...

    @property
    def market_id(self) -> str: ...

    @property
    def kind(self) -> str: ...

    @property
    def t_ms(self) -> int: ...

    @property
    def origin(self) -> str: ...

    @property
    def detail(self) -> Mapping[str, int | str]: ...


def applies_at(
    event: CashEventStamp, instrument: InstrumentClock, calendar: BarLookups | None
) -> int | None:
    """The bar at whose settle phase execution applies ``event`` (section 17.3, ruling R175).

    A ``dividend``, a ``split`` and a ``roll`` are stamped with the first instant of the **new** regime
    (the ex-date open, the split's effective open, the first new-contract bar) and the raw tape already
    reflects them from that bar's open, so they apply one bar earlier, at the last close priced in the
    old regime: ``prev_bar(i, bar_of(t_ms))``. Without that shift a buy at the ex-date open collects a
    dividend the tape had already taken out of the price, which anyone holding a corporate calendar
    could farm. ``funding``, ``borrow_fee``, ``carry`` and ``forced_flat`` are charges on, or the close
    of, a position held through an instant, and apply at ``bar_of(t_ms)``.

    Ruling R175 declares the rule as ``pmx.engine.execution.applies_at`` and that name is this function,
    re-exported: the body lives here because the money path (``Execution.apply_cash_events``) and the
    leak boundary (``pmx.engine.observation.visible_cash_events``, ruling R183) both decide visibility
    and entitlement with it, and an engine whose two halves each held a copy would show an agent a
    dividend at a bar it was paid at another. ``pmx.engine.calendar`` is the module both may import,
    because it moves no money and reads no fill.

    Returns:
        The application bar, or ``None`` when it lies outside the run and no position can exist there.
        ``None`` is also the answer for the three old-regime kinds when there is no ``calendar`` to read
        ``prev_bar`` from: an event whose application bar cannot be computed is not applied, and is
        therefore never visible, which is the conservative side of both boundaries. ``Execution`` always
        holds a calendar and the runner always passes one, so no run takes that branch.
    """
    bar = bar_of(event.t_ms, instrument.interval_min)
    if event.kind in OLD_REGIME_KINDS:
        if calendar is None:
            return None
        return calendar.prev_bar(instrument.id, bar)
    return bar


# --------------------------------------------------------------------------------------------------
# The run's market set and its window
# --------------------------------------------------------------------------------------------------
def _run_metas(dataset: Dataset, config: RunConfig) -> tuple[MarketMeta, ...]:
    """The instruments of the run: the fold the config names, and the kinds it carries.

    A continuous instrument belongs to every fold (17.6, ruling R186: its ``fold`` is ``"all"``), so a
    training run carries it beside the binaries whose ``fold`` is ``"train"``. ``config.kinds`` is
    amendment C1b's filter (8.1), validated by ``RunConfig`` itself; an empty tuple means every kind the
    dataset has.
    """
    kinds = config.kinds
    selected = [
        meta
        for meta in dataset.metas
        if (config.fold == "all" or meta.fold == config.fold or meta.fold == "all")
        and (not kinds or meta.kind in kinds)
    ]
    if not selected:
        raise InvalidConfigError(
            "the run carries no instrument",
            dataset=dataset.manifest.name,
            fold=config.fold,
            kinds=list(kinds),
        )
    return tuple(selected)


def _check_one_grid(dataset: Dataset, config: RunConfig, metas: Sequence[MarketMeta]) -> None:
    """One grid per run (section 5.3, ruling R10). There is no run-time resampling.

    ``run_backtest`` raises the same error (E5); the calendar raises it too because it cannot build a
    timeline on two intervals and would otherwise produce a plausible, wrong one.
    """
    if config.interval_min != dataset.manifest.interval_min:
        raise InvalidConfigError(
            "config.interval_min must equal the manifest's",
            config_interval_min=config.interval_min,
            manifest_interval_min=dataset.manifest.interval_min,
        )
    mismatched = sorted(meta.id for meta in metas if meta.interval_min != config.interval_min)
    if mismatched:
        raise InvalidConfigError(
            "every market of the run must be on the run's grid",
            interval_min=config.interval_min,
            market_ids=mismatched[:8],
        )


def _run_window(config: RunConfig, metas: Sequence[MarketMeta]) -> tuple[int, int]:
    """``(t0_ms, t1_ms)``: the config's when it states them, else section 8.1's defaults.

    The default ``t0_ms`` is ``bar_of(min created_at_ms)`` and the default ``t1_ms`` is
    ``bar_of(max resolved_at_ms) + interval_ms``, so the last bar of the run is the last settling bar and
    every market of the dataset gets its whole life. Both are aligned to the grid: a ``t0_ms`` between
    two grid points would shift every bar of the run off the tape.
    """
    span = interval_ms(config.interval_min)
    first = min(bar_of(meta.created_at_ms, config.interval_min) for meta in metas)
    last = max(bar_of(meta.resolved_at_ms, config.interval_min) for meta in metas)
    t0_ms = bar_of(config.t0_ms, config.interval_min) if config.t0_ms is not None else first
    t1_ms = bar_of(config.t1_ms, config.interval_min) if config.t1_ms is not None else last + span
    if config.t1_ms is not None and config.t1_ms % span != 0:
        t1_ms += span
    if t1_ms <= t0_ms:
        raise InvalidConfigError("the run has no bar", t0_ms=t0_ms, t1_ms=t1_ms)
    return t0_ms, t1_ms
