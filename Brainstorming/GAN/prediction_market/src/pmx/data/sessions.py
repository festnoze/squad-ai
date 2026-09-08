"""Session membership, decided in one place (CONTRACTS_V2 17.2, rulings R149, R174, R185; rule 11).

A bar of a continuous instrument exists only inside a trading session, and three consumers need to agree
about that to the character: the loader (which refuses a bar outside its calendar and a missing bar inside
one), E1's ``Calendar`` (``open(i, t) = listed and in_session``) and E2's ``Execution`` (which charges a
borrow fee or a carry once per session, at the session's last bar). Architecture rule 11 therefore gives
this module the exclusive right to bind ``in_session``: a bar outside its calendar does not exist, and
that sentence has one implementation and one test.

A calendar is a **dated** record and not a weekly template, because daylight saving makes a UTC template
wrong for half the year: XNYS opens at 13:30Z in summer and 14:30Z in winter. The generator at the bottom
of this module is how F4 builds the static calendars for a window from an exchange's rules and holidays;
the result is sealed with the dataset and read back by :func:`load_calendar`. The ``continuous`` calendar
(one session covering everything) is synthesised and never a file, so every rule below reduces to 7.2's
dense grid on a binary or a crypto instrument.

The formula is the contract's: a bar opening at ``t`` intersects a session ``s`` iff
``t < s.close_ms and t + interval_ms > s.open_ms``. A bar that starts before a session opens and ends
inside it exists, because the tape prints in it; a venue's pre-market bar is a load error and not a feature.
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from pmx.errors import SchemaError
from pmx.types import (
    CONTINUOUS_CALENDAR_ID,
    MS_PER_DAY,
    MS_PER_MINUTE,
    DatasetWindow,
    Session,
    SessionCalendar,
    bar_of,
    continuous_calendar,
    day_start_ms,
    interval_ms,
    ms_from_iso_date,
)

__all__ = (
    "SessionRule",
    "calendar_from_payload",
    "check_calendar",
    "continuous_calendar",
    "days_since_previous_close",
    "generate_calendar",
    "in_session",
    "is_session_close",
    "load_calendar",
    "next_bar_ms",
    "prev_bar_ms",
    "session_bars",
    "session_index",
)

#: 1970-01-01 was a Thursday: ``(days_since_epoch + 3) % 7`` is Python's ``weekday()`` with Monday ``0``.
_EPOCH_WEEKDAY = 3


def _sessions(calendar: SessionCalendar | Sequence[Session]) -> Sequence[Session]:
    return calendar.sessions if isinstance(calendar, SessionCalendar) else calendar


def _closes(sessions: Sequence[Session]) -> list[int]:
    return [session.close_ms for session in sessions]


def session_index(calendar: SessionCalendar | Sequence[Session], t_ms: int, *, interval_min: int) -> int | None:
    """The index of the first session the bar opening at ``t_ms`` intersects, or ``None``.

    The sessions are sorted by ``open_ms`` and non-overlapping (17.2), so they are sorted by ``close_ms``
    too and the first candidate is one bisection away: the first session whose close is after ``t_ms``.
    """
    sessions = _sessions(calendar)
    if not sessions:
        return None
    index = bisect_right(_closes(sessions), t_ms)
    if index >= len(sessions):
        return None
    session = sessions[index]
    if t_ms < session.close_ms and t_ms + interval_ms(interval_min) > session.open_ms:
        return index
    return None


def in_session(calendar: SessionCalendar | Sequence[Session], t_ms: int, *, interval_min: int) -> bool:
    """``in_session(i, t)`` of section 17.2: does the bar opening at ``t_ms`` intersect a session?

    This is the one binding of the name in the codebase (architecture rule 11). ``t_ms`` is a grid point
    of the instrument; the caller aligns it, because a bar is identified by its open.
    """
    return session_index(calendar, t_ms, interval_min=interval_min) is not None


def next_bar_ms(calendar: SessionCalendar | Sequence[Session], t_ms: int, *, interval_min: int) -> int | None:
    """The first grid point strictly after ``bar_of(t_ms)`` that intersects a session, or ``None``.

    On the ``continuous`` calendar this is the next grid point; on a session calendar it is Monday's
    first bar after Friday's last one, which is what the latency rule of 16.2 waits for. ``None`` means
    the calendar has no session left, which on a sealed dataset means its window has ended.
    """
    sessions = _sessions(calendar)
    span = interval_ms(interval_min)
    candidate = bar_of(t_ms, interval_min) + span
    if not sessions:
        return None
    for index in range(bisect_right(_closes(sessions), candidate), len(sessions)):
        session = sessions[index]
        # The first grid point at or after ``candidate`` whose bar still reaches into the session.
        first = max(candidate, bar_of(session.open_ms - span, interval_min) + span)
        if first < session.close_ms:
            return first
    return None


def prev_bar_ms(calendar: SessionCalendar | Sequence[Session], t_ms: int, *, interval_min: int) -> int | None:
    """The last grid point strictly before ``bar_of(t_ms)`` that intersects a session, or ``None``."""
    sessions = _sessions(calendar)
    span = interval_ms(interval_min)
    candidate = bar_of(t_ms, interval_min) - span
    if not sessions:
        return None
    opens = [session.open_ms for session in sessions]
    # Every session whose open is at or before the end of the candidate bar can hold a bar before it.
    for index in range(bisect_right(opens, candidate + span - 1) - 1, -1, -1):
        session = sessions[index]
        last = min(candidate, bar_of(session.close_ms - 1, interval_min))
        if last + span > session.open_ms:
            return last
    return None


def session_bars(
    calendar: SessionCalendar | Sequence[Session], *, start_ms: int, end_ms: int, interval_min: int
) -> tuple[int, ...]:
    """Every grid point in ``[start_ms, end_ms)`` whose bar intersects a session, ascending.

    Built session by session rather than grid point by grid point, so a year of hourly bars over a
    calendar of two hundred and fifty sessions costs the sessions and not the year.
    """
    sessions = _sessions(calendar)
    span = interval_ms(interval_min)
    if start_ms % span != 0:
        raise SchemaError("start_ms is not on the grid", start_ms=start_ms, interval_min=interval_min)
    bars: list[int] = []
    last_added: int | None = None
    for session in sessions:
        if session.close_ms <= start_ms or session.open_ms >= end_ms:
            continue
        first = max(start_ms, bar_of(session.open_ms - span, interval_min) + span)
        if last_added is not None and first <= last_added:
            first = last_added + span
        t_ms = first
        while t_ms < session.close_ms and t_ms < end_ms:
            bars.append(t_ms)
            last_added = t_ms
            t_ms += span
    return tuple(bars)


def is_session_close(calendar: SessionCalendar | Sequence[Session], t_ms: int, *, interval_min: int) -> bool:
    """Is the bar opening at ``t_ms`` the **last** bar of its session?

    ``borrow_fee`` and ``carry`` (17.3) are charged once per session at this bar, with ``t_ms + interval_ms
    - 1`` as the event's instant (ruling R176). On the ``continuous`` calendar no bar is a session close,
    so a market that never closes owes no per-session charge.
    """
    index = session_index(calendar, t_ms, interval_min=interval_min)
    if index is None:
        return False
    session = _sessions(calendar)[index]
    return t_ms + interval_ms(interval_min) >= session.close_ms


def days_since_previous_close(
    calendar: SessionCalendar | Sequence[Session], t_ms: int, *, interval_min: int
) -> int | None:
    """Calendar days since the previous session's close, for a bar that is a session close; else ``None``.

    A weekend is therefore charged on Monday as three days (17.3). The first session of a calendar has no
    previous close and counts one day, which is what a borrow charged from the day of the short means.
    """
    if not is_session_close(calendar, t_ms, interval_min=interval_min):
        return None
    sessions = _sessions(calendar)
    index = session_index(calendar, t_ms, interval_min=interval_min)
    if index is None or index == 0:
        return 1
    current_close = sessions[index].close_ms
    previous_close = sessions[index - 1].close_ms
    return max(1, (day_start_ms(current_close) - day_start_ms(previous_close)) // MS_PER_DAY)


# --------------------------------------------------------------------------------------------------
# Reading a sealed calendar
# --------------------------------------------------------------------------------------------------
def check_calendar(calendar: SessionCalendar) -> None:
    """What the schema cannot say: every session inside the window, sorted, non-overlapping."""
    if calendar.window.start_ms >= calendar.window.end_ms:
        raise SchemaError("the calendar window is empty", calendar_id=calendar.calendar_id)
    previous_close: int | None = None
    for session in calendar.sessions:
        if session.open_ms >= session.close_ms:
            raise SchemaError("a session opens before it closes", calendar_id=calendar.calendar_id)
        if session.open_ms < calendar.window.start_ms or session.close_ms > calendar.window.end_ms:
            raise SchemaError(
                "a session lies outside the calendar window",
                calendar_id=calendar.calendar_id,
                open_ms=session.open_ms,
                close_ms=session.close_ms,
            )
        if previous_close is not None and session.open_ms < previous_close:
            raise SchemaError("sessions must be sorted and non-overlapping", calendar_id=calendar.calendar_id)
        previous_close = session.close_ms
    if not calendar.sessions:
        raise SchemaError("a calendar carries at least one session", calendar_id=calendar.calendar_id)
    if tuple(sorted(set(calendar.holidays))) != calendar.holidays:
        raise SchemaError("holidays must be sorted and unique", calendar_id=calendar.calendar_id)


def calendar_from_payload(payload: object, *, where: str = "") -> SessionCalendar:
    """Schema, then the strict model, then the frozen dataclass: the one door into a calendar from JSON.

    ``continuous`` is refused here as it is by the schema (ruling R185): the one calendar that is never a
    file cannot arrive through the file door.
    """
    from pmx.data.schema import session_calendar_from_payload

    calendar = session_calendar_from_payload(payload, where=where)
    if calendar.calendar_id == CONTINUOUS_CALENDAR_ID:
        raise SchemaError("the continuous calendar is synthesised, never a file", where=where)
    check_calendar(calendar)
    return calendar


def load_calendar(path: Path) -> SessionCalendar:
    """Load ``calendars/<calendar_id>.json`` and refuse a file whose name is not its id."""
    from pmx.data.loader import read_json_file

    calendar = calendar_from_payload(read_json_file(path), where=path.name)
    if path.stem != calendar.calendar_id:
        raise SchemaError(
            "calendar file name does not match its id", path=path.name, calendar_id=calendar.calendar_id
        )
    return calendar


# --------------------------------------------------------------------------------------------------
# The generator the static calendars are built with (F4 calls it; the result is data, sealed)
# --------------------------------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class SessionRule:
    """One dated regime of an exchange: on these weekdays, between these dates, open and close at these
    minutes of the UTC day.

    Daylight saving is two rules with two date ranges, which is exactly why the calendar is dated. A
    session may cross midnight (``close_minute`` above 1 440), and a rule with one weekday and a close
    several days later expresses the FX week (Sunday 22:00Z to Friday 22:00Z) as one session.
    """

    from_date: str
    to_date: str
    weekdays: tuple[int, ...]
    open_minute: int
    close_minute: int

    def __post_init__(self) -> None:
        if not 0 <= self.open_minute < self.close_minute <= 7 * 24 * 60:
            raise SchemaError("a session rule opens before it closes, within one week", rule=str(self))
        if any(day not in range(7) for day in self.weekdays):
            raise SchemaError("weekdays are 0 (Monday) to 6 (Sunday)", weekdays=list(self.weekdays))


def _weekday(day_ms: int) -> int:
    return (day_ms // MS_PER_DAY + _EPOCH_WEEKDAY) % 7


def generate_calendar(
    *,
    calendar_id: str,
    description: str,
    source_url: str,
    as_of_date: str,
    window_start_ms: int,
    window_end_ms: int,
    rules: Sequence[SessionRule],
    holidays: Sequence[str] = (),
) -> SessionCalendar:
    """The sessions of an exchange over a window, from its dated rules and its holidays.

    A holiday removes every session opening on that UTC day. Sessions are emitted sorted and are refused
    when two rules overlap, because an overlapping schedule is a data error and not something to merge
    silently. The result is what F4 writes to ``data/calendars/<id>.json`` and the builder copies into a
    dataset; it is deterministic from its inputs and reads no clock.
    """
    holiday_days = {ms_from_iso_date(day) for day in holidays}
    sessions: list[Session] = []
    day_ms = day_start_ms(window_start_ms)
    while day_ms < window_end_ms:
        weekday = _weekday(day_ms)
        for rule in rules:
            if not ms_from_iso_date(rule.from_date) <= day_ms < ms_from_iso_date(rule.to_date):
                continue
            if weekday not in rule.weekdays or day_ms in holiday_days:
                continue
            open_ms = day_ms + rule.open_minute * MS_PER_MINUTE
            close_ms = day_ms + rule.close_minute * MS_PER_MINUTE
            if open_ms < window_start_ms or close_ms > window_end_ms:
                continue
            sessions.append(Session(open_ms=open_ms, close_ms=close_ms))
        day_ms += MS_PER_DAY
    sessions.sort(key=lambda session: (session.open_ms, session.close_ms))
    for previous, current in zip(sessions, sessions[1:], strict=False):
        if current.open_ms < previous.close_ms:
            raise SchemaError(
                "two session rules overlap", calendar_id=calendar_id, at_ms=current.open_ms
            )
    calendar = SessionCalendar(
        calendar_id=calendar_id,
        description=description,
        source_url=source_url,
        as_of_date=as_of_date,
        window=DatasetWindow(start_ms=window_start_ms, end_ms=window_end_ms),
        sessions=tuple(sessions),
        holidays=tuple(sorted(set(holidays))),
    )
    check_calendar(calendar)
    return calendar

