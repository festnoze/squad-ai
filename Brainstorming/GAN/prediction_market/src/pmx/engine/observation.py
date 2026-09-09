"""The observation builder: the one place the as-of rules are applied, by filtering (the leak boundary).

Everything an agent may know at bar ``t`` passes through this module, and it passes through it by being
**filtered**, never by being trusted (CONTRACTS_V2 section 5.4). That sentence is the whole design: a
memory that returns an unfiltered view, an importer that stamped a bar in the future, a hive that hands
back an entry it should have held, a research grant carrying tomorrow's headline and a cash event the
venue has announced but not yet applied are all things this builder drops on the floor. If the filter
lived in the caller, one caller would forget it and the run would produce a number nobody could trust.

What that means field by field (section 5.4, generalised by amendment C1b's rulings R181 and R183):

* a bar is visible when it is **completed**: ``b.t_ms + interval_ms <= now_ms``. The "current price" is
  the close of the last completed bar, and on a market's very first bar there is none, so
  ``last_price_bp`` is ``first_price_bp``, ``bars`` is empty and both quotes are ``None`` (ruling R11);
* a trade is visible when ``trade.t_ms < now_ms``, and only inside a granted ``history`` research result;
* a news item is visible when ``visible_from_ms <= now_ms``, which is ``published_at_ms +
  safety_lag_ms`` stamped at build time, so the lag cannot be skipped here or applied twice;
* a hive entry is visible when ``visible_from_ms <= now_ms``, and a forecast of a market that is still
  open in this very observation is dropped whatever the hive said: an unsettled market's forecast is the
  one leak the hive's own stamp cannot be checked against inside a view (section 7.9);
* a memory record is visible when ``written_at_ms <= now_ms`` (ruling R13);
* a cash event is visible when its **application bar has completed** (ruling R183): an announced
  dividend stays hidden until the cum-date close, and a funding rate until it is paid;
* ``close_at_ms`` is public on a binary and is ``0`` on a continuous instrument, whose ``delisted_at_ms``
  and ``last_bar`` are future information; on a continuous instrument ``tradable`` therefore carries
  ``open(i, t)``, because ``t < last_bar(i)`` would announce the last bar one bar ahead (ruling R181).

Two structural rules complete it. **Never a clock**: no bar count, no index relative to the end, no
``resolved_at_ms``, no ``t1_ms``, no ``last_bar``; every observation this module builds is checked against
the forbidden key set before it is returned (:func:`mentions_forbidden_key`, then
:func:`assert_no_leak` on anything the cheap test cannot clear), so a field added to a view by a later
package cannot smuggle one in silently. And **never a silent truncation**: an observation over
``OBSERVATION_MAX_BYTES`` raises :class:`~pmx.errors.ObservationTooLargeError`, because two agents seeing
different worlds on the same bar is a leak of a different kind (section 8.1).

The research budget is accounted here too (sections 8.1 and 8.4): a request costs
``RESEARCH_UNIT_COST[kind]`` units, is granted at the **next** bar, and a request that would exceed the
agent's remaining budget is refused and costs nothing. Exploration has a price, so its value can be
measured rather than assumed.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, fields
from types import MappingProxyType
from typing import Final, NoReturn, Protocol, cast

from pmx import OBS_VERSION
from pmx.engine.calendar import KIND_BINARY, Calendar, applies_at
from pmx.errors import InvalidConfigError, LeakError, ObservationTooLargeError, SchemaError
from pmx.journal import canonical_json
from pmx.types import (
    BINARY_POINT_VALUE_MICRO,
    BINARY_TICK_SIZE_MICRO,
    CASH_EVENT_KINDS,
    CASH_EVENTS_VIEW_MAX,
    CONTINUOUS_CALENDAR_ID,
    DATA_CASH_EVENT_KINDS,
    INSTRUMENT_KINDS,
    MS_PER_DAY,
    MS_PER_HOUR,
    NEWS_PER_MARKET_MAX,
    OBSERVATION_MAX_BYTES,
    RESEARCH_KINDS,
    RESEARCH_UNIT_COST,
    Bar,
    CashEventView,
    HiveView,
    Limits,
    MarketView,
    MemoryView,
    NewsItem,
    NewsView,
    Observation,
    PortfolioView,
    PositionView,
    RejectReason,
    ResearchGrant,
    ResearchRequest,
    ResearchView,
    RunConfig,
    Trade,
    bar_of,
    interval_ms,
    limits_from_config,
    rank_news_items,
    sorted_market_ids,
)

# --------------------------------------------------------------------------------------------------
# Caps the contract states in prose or in a field comment and that ``pmx.types`` does not carry.
#
# ``CASH_EVENT_KINDS``, ``DATA_CASH_EVENT_KINDS`` and ``CASH_EVENTS_VIEW_MAX`` are no longer here: they
# are ``pmx.types``' (section 13, 17.9's R177 and R183 rows) and are imported above, so the kind order
# ruling R193 makes normative has one spelling and the view cannot sort by an order the engine did not
# apply in. The five below are still stated in prose only and each remains a reported contract issue,
# so that D1 can hold the one spelling.
# --------------------------------------------------------------------------------------------------
#: ``NewsView.text`` is 600 characters of body, never the 4 000 the dataset keeps (section 8.3).
NEWS_VIEW_TEXT_CHARS: Final = 600
#: ``MarketView.description`` is at most 1 000 characters (section 8.3).
DESCRIPTION_VIEW_CHARS: Final = 1_000
#: ``HiveView.resolutions`` carries the last 200 settled markets (section 8.3).
HIVE_RESOLUTIONS_VIEW_MAX: Final = 200
#: ``MemoryView.notes`` carries the last 20 notes (section 8.3).
MEMORY_NOTES_VIEW_MAX: Final = 20
#: A granted ``news`` research request is a deeper digest: three times the caps (section 8.4).
RESEARCH_NEWS_MULTIPLIER: Final = 3

#: Every key section 8.3's clock test forbids anywhere in an observation, plus section 7.9's fields, the
#: cluster-derived and detector-derived names amendment C1 adds (ruling R116, sections 16.3 and 16.4) and
#: amendment C1b's (rulings R151, R181 and R183). The check is a **key set** test and not an integer
#: scan, because a scan cannot pass on legal data: ``close_at_ms == resolved_at_ms`` is the normal case on
#: both venues, and ``bars_window = 90`` collides with the bar count of any ninety-bar market.
#:
#: Four names 7.9 bans on a cluster record cannot be banned as keys, and saying so is part of the rule:
#: ``kind`` (a ``NewsView``'s, a ``MarketView``'s and a ``CashEventView``'s), ``source`` (a
#: ``NewsView``'s), ``currency`` (a ``MarketView``'s) and ``market_ids`` (a lesson's and a note's) are
#: all legal keys of a legal observation. What carries them into a view is an ``EventCluster`` or an
#: ``OpportunityEvent`` **structure**, and every structural name of both (``cluster_id``,
#: ``constraint_id``, ``reasons``, ``evidence``, ``opportunity_id``, ``detector_id``) is on the list, so
#: no such record can reach an observation whole. ``detail`` is on the list too: the one legal ``detail``
#: in an observation is an applied cash event's, and that subtree is set aside before the scan
#: (:func:`leak_scan_payload`), so the name is free to mean "a ``MatchReason`` got in here".
FORBIDDEN_OBSERVATION_KEYS: Final = (
    # Section 7.9's dataset fields and section 8.3's clock names.
    "resolved_at_ms",
    "resolution",
    "resolution_source",
    "final_price_bp",
    "hardness_tags",
    "quality",
    "fold",
    "n_bars",
    "bars_remaining",
    "bar_index",
    "t1_ms",
    # Amendment C1b: the delisting, the last bar and anything derived from it (ruling R181).
    "delisted_at_ms",
    "last_bar",
    "last_bar_ms",
    "last_price_ticks",
    "n_forecasts_unresolved",
    "price_realised_ticks",
    "realised_sign",
    # Amendment C1b: a cash event and every field of one, outside the applied subtree (ruling R183).
    "cash_event_id",
    "detail",
    "rate_ppm",
    "rate_ppm_per_day",
    "dividend_micro",
    "numerator",
    "denominator",
    "gap_ticks",
    "from_price_ticks",
    "to_price_ticks",
    "from_symbol",
    "to_symbol",
    "mark_ticks",
    # Amendment C1: every cluster-derived and constraint-derived name (sections 16.3, ruling R116).
    "cluster_id",
    "constraint_id",
    "score_permille",
    "resolution_span_ms",
    "asof",
    "reasons",
    # Amendment C1: every field of an ``OpportunityEvent`` (section 16.4, ruling R116).
    "opportunity_id",
    "detector_id",
    "window",
    "duration_bars",
    "size_ppm",
    "size_net_bp",
    "payoff_cents",
    "tradable_for_money",
    "evidence",
)

_FLAT_POSITION: Final = PositionView(position=0, avg_cost_bp=0, unrealised_cents=0, open_orders=())
#: A bounded memo of the per-instrument prefix sums of :func:`_tape_stats`. It is a memo of a pure
#: function of the tape (keyed by the tape's identity), so it can move no number and no journal byte; it
#: exists because ``volume_milli_to_date`` is a cumulative sum and a run asks for it once per agent per
#: bar, which without the memo is quadratic in the length of every tape.
_TAPE_STATS_CACHE: dict[tuple[str, int, int, int], tuple[tuple[int, ...], tuple[int, ...]]] = {}
_TAPE_STATS_CACHE_MAX: Final = 4_096


# --------------------------------------------------------------------------------------------------
# The surfaces E1 reads. Each one is the read side of a record another package owns, and gate G2 has
# landed all of them (``pmx.types.Instrument``, ``CashEvent``, and A2's memory and hive): they stay
# structural here because the builder reads only what it filters, and the declared classes satisfy them.
# What is NOT resolved, and is reported as a contract issue rather than settled inside one package: the
# same four names are declared a second time in the engine wave (``InstrumentLike`` and
# ``CashEventLike`` in ``pmx.engine.execution``, ``MemoryLike`` and ``HiveLike`` in
# ``pmx.engine.runner``), with different member sets, so a caller cannot tell which surface a record
# must satisfy. Consolidating them means choosing where the engine's structural protocols live, which
# section 11.1 already argues for and which the gate must rule on (see the file list of section 13).
# --------------------------------------------------------------------------------------------------
class InstrumentLike(Protocol):
    """What the builder reads of an instrument: ``pmx.types.Instrument`` (D1, gate G2, ruling R144).

    A ``Market`` satisfies it today. The two per-kind spellings the base resolves (``listed_at_ms`` for
    ``created_at_ms``, ``first_price_ticks`` for ``first_price_bp``) are read through the accessors below
    rather than declared here, so that this protocol is exactly the surface both kinds share.
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
    """One dated cash event: ``pmx.types.CashEvent`` (D1, gate G2, section 17.3)."""

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


class MemoryLike(Protocol):
    """The read side of ``pmx.agents.memory.Memory`` (section 10.3, A2, wave 3).

    The builder calls ``view`` and nothing else, then filters what comes back: memory was the one channel
    into an observation with no as-of filter at all (ruling R13).
    """

    def view(self, *, now_ms: int) -> MemoryView: ...


class HiveLike(Protocol):
    """The read side of ``pmx.agents.hive.Hive`` (section 10.4, A3, wave 3)."""

    def view(
        self,
        *,
        now_ms: int,
        agent_id: str,
        market_ids: Sequence[str],
        limits: Limits,
        live_coop: bool,
    ) -> HiveView: ...


# --------------------------------------------------------------------------------------------------
# Per-kind accessors: one spelling per name the two record shapes disagree about (amendment C1b)
# --------------------------------------------------------------------------------------------------
def instrument_kind(instrument: InstrumentLike) -> str:
    """``Instrument.kind`` (ruling R144). A record without the field is a binary, as its default says."""
    kind = str(getattr(instrument, "kind", KIND_BINARY))
    if kind not in INSTRUMENT_KINDS:
        raise SchemaError("unknown instrument kind", market_id=instrument.id, kind=kind)
    return kind


def listed_at_ms_of(instrument: InstrumentLike) -> int:
    """``Instrument.listed_at_ms``, which on a ``Market`` is ``created_at_ms`` (section 17.1)."""
    value = getattr(instrument, "listed_at_ms", None)
    if value is None:
        value = getattr(instrument, "created_at_ms", None)
    return int(cast(int, value))


def first_price_of(instrument: InstrumentLike) -> int:
    """The instrument's opening quote in ticks: ``first_price_bp`` on a binary, ``first_price_ticks``
    on a continuous instrument, one field name in the view (ruling R148)."""
    value = getattr(instrument, "first_price_bp", None)
    if value is None:
        value = getattr(instrument, "first_price_ticks", None)
    if value is None:
        raise SchemaError("instrument carries no first price", market_id=instrument.id)
    return int(cast(int, value))


def question_of(instrument: InstrumentLike) -> str:
    """``MarketView.question``. A continuous instrument carries none (17.1), so its view shows the
    venue's own symbol, which is the closest thing to a question a price series has."""
    question = getattr(instrument, "question", None)
    if question is not None:
        return str(question)
    return str(getattr(instrument, "symbol", instrument.id))


def tick_size_micro_of(instrument: InstrumentLike) -> int:
    """``Instrument.tick_size_micro``; a binary is ``BINARY_TICK_SIZE_MICRO = 100`` (ruling R145)."""
    return int(cast(int, getattr(instrument, "tick_size_micro", BINARY_TICK_SIZE_MICRO)))


def point_value_micro_of(instrument: InstrumentLike) -> int:
    """``Instrument.point_value_micro``; a binary is ``BINARY_POINT_VALUE_MICRO = 1_000_000``."""
    return int(cast(int, getattr(instrument, "point_value_micro", BINARY_POINT_VALUE_MICRO)))


def session_calendar_id_of(instrument: InstrumentLike) -> str:
    """``Instrument.session_calendar_id``; every binary names the synthesised ``continuous`` calendar."""
    return str(getattr(instrument, "session_calendar_id", CONTINUOUS_CALENDAR_ID))


def underlying_id_of(instrument: InstrumentLike) -> str | None:
    """``ContinuousInstrument.underlying_id``: a perp's spot twin (17.7's basis family)."""
    value = getattr(instrument, "underlying_id", None)
    return None if value is None else str(value)


def twins_of(instrument: InstrumentLike) -> tuple[str, ...]:
    """``ContinuousInstrument.twins``: the same underlying on other venues, sorted (17.7's pairs)."""
    return tuple(str(twin) for twin in cast(Iterable[object], getattr(instrument, "twins", ())))


def cash_events_of(instrument: InstrumentLike) -> tuple[CashEventLike, ...]:
    """``ContinuousInstrument.cash_events``: the dated records of 17.3 that come from data."""
    return tuple(cast(Iterable[CashEventLike], getattr(instrument, "cash_events", ())))


# --------------------------------------------------------------------------------------------------
# Cash events: what has been applied, and when it was
# --------------------------------------------------------------------------------------------------
def visible_cash_events(
    instrument: InstrumentLike, *, now_ms: int, calendar: Calendar | None = None
) -> tuple[CashEventView, ...]:
    """The instrument's applied **data** cash events, oldest first, at most ``CASH_EVENTS_VIEW_MAX``.

    An event is visible exactly as a bar is (ruling R183): once its application bar has completed
    (``applies_at(e) + interval_ms <= now_ms``) it is the venue's published past. One whose application
    bar has not completed never appears, however long ago the venue announced it, which is why an
    announced dividend is hidden until the cum-date close and a funding time until it is paid.

    The three engine kinds (``borrow_fee``, ``carry``, ``forced_flat``) are never in a market view: they
    are the agent's own charges and reach it through its portfolio (ruling R183).

    The application bar comes from :func:`pmx.engine.calendar.applies_at`, ruling R175's **one**
    implementation, which is also what ``Execution.apply_cash_events`` calls: the leak boundary and the
    money path answer "when did this apply" with the same body, so an agent can never be shown a
    dividend at a bar the engine paid it at another. Without a ``calendar`` the three old-regime kinds
    have no ``prev_bar`` to read, so that function answers ``None`` and they stay hidden; the runner
    always passes the run's calendar (ruling R187), so no run takes that branch.
    """
    span = interval_ms(instrument.interval_min)
    applied: list[tuple[tuple[int, int, int, str], CashEventView]] = []
    for event in cash_events_of(instrument):
        if event.kind not in DATA_CASH_EVENT_KINDS or event.origin != "data":
            continue
        at_ms = applies_at(event, instrument, calendar)
        if at_ms is None or at_ms + span > now_ms:
            continue
        order = (at_ms, CASH_EVENT_KINDS.index(event.kind), event.t_ms, event.cash_event_id)
        applied.append(
            (
                order,
                CashEventView(
                    kind=event.kind,
                    t_ms=event.t_ms,
                    applied_at_ms=at_ms,
                    detail=dict(event.detail),
                ),
            )
        )
    applied.sort(key=lambda item: item[0])
    return tuple(view for _, view in applied[-CASH_EVENTS_VIEW_MAX:])


def hours_to_next_bar(instrument: InstrumentLike, *, now_ms: int, calendar: Calendar | None) -> int:
    """``(next_bar(i, now_ms) - now_ms) // MS_PER_HOUR`` from the sealed calendar, ``0`` on a binary.

    It is the venue's own rule and therefore public (section 7.9's "a fixed schedule is not a datum
    about the future"): on a session instrument it says how long the weekend is, which is exactly what an
    agent deciding on Friday afternoon needs in order to price the gap it cannot trade through.

    **From the sealed calendar, and never from the run's own timeline** (section 8.3). The two differ at
    exactly one place and the difference is a leak: ``Calendar.next_bar`` is clamped by ``t1_ms`` and by
    ``last_bar(i)``, so on the instrument's last bar it answers nothing and this field would publish
    ``0`` where the venue's schedule says twenty-four or seventy-two hours, announcing ``last_bar(i)``
    and the run's ``t1_ms`` (both forbidden by 7.9 and ruling R181). :meth:`Calendar.session_next_bar`
    is therefore what is read, and a delisting the venue has not yet published stays hidden behind the
    schedule's own answer.
    """
    if instrument_kind(instrument) == KIND_BINARY or calendar is None:
        return 0
    nxt = calendar.session_next_bar(instrument.id, now_ms)
    if nxt is None:
        return 0
    return (nxt - now_ms) // MS_PER_HOUR


# --------------------------------------------------------------------------------------------------
# The research budget (sections 8.1 and 8.4)
# --------------------------------------------------------------------------------------------------
def research_cost(kind: str) -> int:
    """``RESEARCH_UNIT_COST[kind]`` (section 8.1), the one price table E1 grants and E5 journals."""
    cost = RESEARCH_UNIT_COST.get(kind)
    if cost is None:
        raise InvalidConfigError("unknown research kind", kind=kind, known=sorted(RESEARCH_UNIT_COST))
    return cost


@dataclass(frozen=True, slots=True)
class ResearchOutcome:
    """What one research request cost and whether it was granted: the ``research_spent`` payload (9.2).

    ``units`` is the **price of the kind** whether or not the request was granted, which is what section
    8.1 says the event carries; a refused request leaves ``remaining`` untouched and costs nothing.
    """

    agent_id: str
    kind: str
    market_id: str | None
    units: int
    remaining: int
    granted: bool
    reason: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "agent_id": self.agent_id,
            "kind": self.kind,
            "market_id": self.market_id,
            "units": self.units,
            "remaining": self.remaining,
            "granted": self.granted,
            "reason": self.reason,
        }


class ResearchLedger:
    """One run's research budgets, per agent (sections 8.1 and 8.4).

    Exploration has a price so that its value can be measured: the budget is spent in units, the spend is
    journaled, and section 12.6 charges ``RESEARCH_PENALTY_UNITS`` against the selection objective for
    what was spent. A request that would exceed the remaining budget is refused **and costs nothing**,
    rather than being partially served, so an agent cannot buy half a request by asking twice.
    """

    __slots__ = ("_remaining", "_total")

    def __init__(self, config: RunConfig, agent_ids: Sequence[str]) -> None:
        self._total = {agent_id: config.research_budget_for(agent_id) for agent_id in agent_ids}
        self._remaining = dict(self._total)

    def total(self, agent_id: str) -> int:
        return self._total.get(agent_id, 0)

    def remaining(self, agent_id: str) -> int:
        return self._remaining.get(agent_id, 0)

    def request(self, *, agent_id: str, request: ResearchRequest) -> ResearchOutcome:
        """Price one request, spend the units when it is granted, and say why when it is not."""
        if agent_id not in self._total:
            raise InvalidConfigError("unknown agent in the research ledger", agent_id=agent_id)
        remaining = self._remaining[agent_id]
        if request.kind not in RESEARCH_KINDS:
            return ResearchOutcome(
                agent_id=agent_id,
                kind=request.kind,
                market_id=request.market_id,
                units=0,
                remaining=remaining,
                granted=False,
                reason=RejectReason.BAD_RESEARCH.value,
            )
        cost = research_cost(request.kind)
        if request.kind in ("history", "wiki_asof") and request.market_id is None:
            return ResearchOutcome(
                agent_id=agent_id,
                kind=request.kind,
                market_id=None,
                units=cost,
                remaining=remaining,
                granted=False,
                reason=RejectReason.BAD_RESEARCH.value,
            )
        if cost > remaining:
            return ResearchOutcome(
                agent_id=agent_id,
                kind=request.kind,
                market_id=request.market_id,
                units=cost,
                remaining=remaining,
                granted=False,
                reason=RejectReason.BUDGET_EXCEEDED.value,
            )
        self._remaining[agent_id] = remaining - cost
        return ResearchOutcome(
            agent_id=agent_id,
            kind=request.kind,
            market_id=request.market_id,
            units=cost,
            remaining=remaining - cost,
            granted=True,
        )


def build_grant(
    *,
    request: ResearchRequest,
    granted_at_ms: int,
    config: RunConfig,
    news: Sequence[NewsItem] = (),
    trades: Sequence[Trade] = (),
    background: Sequence[NewsItem] = (),
) -> ResearchGrant:
    """The payload of one granted request, as of ``granted_at_ms`` (the bar it was granted at, 5.4).

    A grant is filtered when it is built and filtered **again** when it enters an observation
    (:func:`build_observation`), because it is content that crossed a bar boundary: its as-of instant is
    the previous bar's, and nothing in it may be newer than the bar it is read at.

    * ``news``: a deeper digest of the market's items, three times the per-market cap (section 8.4),
      never beyond ``NEWS_PER_MARKET_MAX``; when the request names a market the digest is that market's
      linked items, exactly as the per-market digest of a view is;
    * ``history``: the last ``config.trades_window`` prints strictly before ``granted_at_ms``;
    * ``wiki_asof``: the point-in-time background snapshots visible at ``granted_at_ms``, the most recent
      ``config.news_per_market`` of them. Section 8.4 calls the payload "a background article" and states
      no cap; an uncapped one would carry a year of revisions of one subject and could push the whole
      observation over ``OBSERVATION_MAX_BYTES``, which raises rather than truncates (8.1), so the
      per-market digest cap is applied and reported as a contract issue.
    """
    kind = request.kind
    if kind not in RESEARCH_KINDS:
        raise InvalidConfigError("unknown research kind", kind=kind)
    if kind == "history":
        kept = tuple(trade for trade in trades if trade.t_ms < granted_at_ms)
        return ResearchGrant(
            kind=kind,
            market_id=request.market_id,
            granted_at_ms=granted_at_ms,
            trades=kept[-config.trades_window :] if config.trades_window > 0 else (),
        )
    source = background if kind == "wiki_asof" else news
    visible = tuple(item for item in source if item.visible_from_ms <= granted_at_ms)
    if kind == "news":
        if request.market_id is not None:
            # A deeper digest of **the market's** items (8.4): a caller that handed the global digest to
            # a per-market request gets the market's items out of it, not the world's.
            visible = tuple(item for item in visible if request.market_id in item.match_ids)
        cap = min(config.news_per_market * RESEARCH_NEWS_MULTIPLIER, NEWS_PER_MARKET_MAX)
        ranked = rank_news_items(visible, market_id=request.market_id)[:cap]
    else:
        ordered = tuple(sorted(visible, key=lambda item: (item.published_at_ms, item.news_id)))
        ranked = ordered[-config.news_per_market :] if config.news_per_market > 0 else ()
    return ResearchGrant(
        kind=kind,
        market_id=request.market_id,
        granted_at_ms=granted_at_ms,
        news=tuple(news_view_of(item, market_id=request.market_id) for item in ranked),
    )


# --------------------------------------------------------------------------------------------------
# The projections
# --------------------------------------------------------------------------------------------------
def news_view_of(item: NewsItem, *, market_id: str | None = None) -> NewsView:
    """One dataset item as an agent sees it: 600 characters of body and the score of **this** market.

    A ``NewsItem`` carries one score per linked market and a rank only exists relative to a market, so a
    global digest carries the item's best link and a per-market digest carries the market's own.
    """
    score = (
        item.score_for(market_id)
        if market_id is not None
        else (max(item.match_scores_permille) if item.match_scores_permille else 0)
    )
    return NewsView(
        news_id=item.news_id,
        source=item.source,
        kind=item.kind,
        published_at_ms=item.published_at_ms,
        headline=item.headline,
        text=item.text[:NEWS_VIEW_TEXT_CHARS],
        section=item.section,
        url=item.url,
        match_score_permille=score,
    )


def completed_bars(instrument: InstrumentLike, *, now_ms: int, limit: int) -> tuple[Bar, ...]:
    """The last ``limit`` completed bars at ``now_ms``, oldest first, ``()`` when none is completed.

    The instrument's own ``bars_before`` is the declared accessor (section 7.2) and is what is called;
    what it returns is then filtered again here on ``b.t_ms + interval_ms <= now_ms``. The second filter
    is not paranoia about D1: it is the leak boundary refusing to trust a record it did not build, which
    is the same reason the news filter is applied here although the loader already applied it.
    """
    if limit <= 0:
        return ()
    span = interval_ms(instrument.interval_min)
    kept = tuple(bar for bar in instrument.bars_before(now_ms, limit) if bar.t_ms + span <= now_ms)
    return kept[-limit:]


def _tape_stats(instrument: InstrumentLike) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """Prefix sums of ``volume_milli`` and ``n_trades`` over the instrument's bars, memoised.

    ``prefix[i]`` is the sum over the first ``i`` bars, so the sum over the completed bars is one lookup
    once the number of completed bars is known.
    """
    bars = instrument.bars
    key = (
        instrument.id,
        len(bars),
        bars[0].t_ms if bars else -1,
        bars[-1].t_ms if bars else -1,
    )
    cached = _TAPE_STATS_CACHE.get(key)
    if cached is not None:
        return cached
    volume = [0]
    trades = [0]
    for bar in bars:
        volume.append(volume[-1] + bar.volume_milli)
        trades.append(trades[-1] + bar.n_trades)
    computed = (tuple(volume), tuple(trades))
    if len(_TAPE_STATS_CACHE) >= _TAPE_STATS_CACHE_MAX:
        _TAPE_STATS_CACHE.clear()
    _TAPE_STATS_CACHE[key] = computed
    return computed


def tape_stats_at(instrument: InstrumentLike, *, now_ms: int) -> tuple[int, int, int]:
    """``(volume_milli_7d, volume_milli_to_date, n_trades_to_date)`` over **completed** bars only.

    "To date" is to the last completed bar and never to the bar being decided: the bar an agent is
    deciding at has not printed yet, and a volume that included it would say how the day went.
    """
    bars = instrument.bars
    if not bars:
        return 0, 0, 0
    span = interval_ms(instrument.interval_min)
    volume, trades = _tape_stats(instrument)
    completed = 0
    for index in range(len(bars) - 1, -1, -1):
        if bars[index].t_ms + span <= now_ms:
            completed = index + 1
            break
    if completed == 0:
        return 0, 0, 0
    week_from = now_ms - 7 * MS_PER_DAY
    first = completed
    for index in range(completed - 1, -1, -1):
        if bars[index].t_ms < week_from:
            break
        first = index
    return volume[completed] - volume[first], volume[completed], trades[completed]


def market_view_fields(
    instrument: InstrumentLike,
    *,
    now_ms: int,
    config: RunConfig,
    tradable: bool,
    position: PositionView,
    news: Sequence[NewsView] = (),
    trades: Sequence[Trade] = (),
    calendar: Calendar | None = None,
) -> dict[str, object]:
    """Every field of ``MarketView`` (section 8.3), including amendment C1b's eight, as a mapping.

    It is a mapping and not a ``MarketView`` because D1 has not landed the eight defaulted fields of
    ruling R188 yet (``kind``, ``tick_size_micro``, ``point_value_micro``, ``session_calendar_id``,
    ``hours_to_next_bar``, ``underlying_id``, ``twins``, ``cash_events``): the values are computed here,
    where they belong, and :func:`_market_view` drops the ones the dataclass cannot yet accept. That is
    the one place gate G2's change lands, and it is reported as a contract issue.

    ``close_at_ms`` is the venue's published close on a binary and ``0`` on a continuous instrument, whose
    ``delisted_at_ms`` is future information; ``tradable`` is the caller's, because on a continuous
    instrument the view carries ``open(i, t)`` and not ``tradable(i, t)`` (ruling R181).
    """
    kind = instrument_kind(instrument)
    bars = completed_bars(instrument, now_ms=now_ms, limit=config.bars_window)
    quote = bars[-1] if bars else None
    volume_7d, volume_to_date, n_trades_to_date = tape_stats_at(instrument, now_ms=now_ms)
    close_at_ms = 0 if kind != KIND_BINARY else int(cast(int, getattr(instrument, "close_at_ms", 0)))
    return {
        "market_id": instrument.id,
        "provider": instrument.provider,
        "url": instrument.url,
        "question": question_of(instrument),
        "description": instrument.description[:DESCRIPTION_VIEW_CHARS],
        "category": instrument.category,
        "tags": tuple(instrument.tags),
        "currency": instrument.currency,
        "created_at_ms": listed_at_ms_of(instrument),
        "close_at_ms": close_at_ms,
        "tradable": tradable,
        "bars": bars,
        "first_price_bp": first_price_of(instrument),
        "last_price_bp": quote.close_bp if quote is not None else first_price_of(instrument),
        "best_bid_bp": quote.yes_bid_bp if quote is not None else None,
        "best_ask_bp": quote.yes_ask_bp if quote is not None else None,
        "volume_milli_7d": volume_7d,
        "volume_milli_to_date": volume_to_date,
        "n_trades_to_date": n_trades_to_date,
        "trades": tuple(trades),
        "news": tuple(news),
        "position": position,
        "fee_schedule_id": instrument.fee_schedule_id,
        "kind": kind,
        "tick_size_micro": tick_size_micro_of(instrument),
        "point_value_micro": point_value_micro_of(instrument),
        "session_calendar_id": session_calendar_id_of(instrument),
        "hours_to_next_bar": hours_to_next_bar(instrument, now_ms=now_ms, calendar=calendar),
        "underlying_id": underlying_id_of(instrument),
        "twins": twins_of(instrument),
        "cash_events": visible_cash_events(instrument, now_ms=now_ms, calendar=calendar),
    }


def _market_view(view_fields: Mapping[str, object]) -> MarketView:
    """``MarketView(**view_fields)``.

    Nothing is filtered out: ``MarketView`` carries the eight defaulted fields of ruling R188 since gate
    G2, so every name :func:`market_view_fields` produces is a field of the dataclass. A name that
    diverges is a ``TypeError`` here rather than a value silently dropped from an observation, which is
    the whole reason the filter is gone.
    """
    factory = cast(Callable[..., MarketView], MarketView)
    return factory(**view_fields)


# --------------------------------------------------------------------------------------------------
# The as-of filters over what another package handed us
# --------------------------------------------------------------------------------------------------
def filter_memory_view(view: MemoryView, *, now_ms: int) -> MemoryView:
    """Drop every memory record written after ``now_ms`` (ruling R13) and cap the notes at 20.

    ``Memory.view(now_ms=...)`` filters already; this is the leak boundary applying the rule itself, and
    the poisoned-future test injects a record stamped after ``now_ms`` through a memory that does not.
    Calibration bins and priors carry counts and no stamp of their own, so what can be filtered is
    filtered and what cannot is what section 10.3 makes monotone (a bin is only ever incremented).
    """
    lessons = tuple(lesson for lesson in view.lessons if lesson.written_at_ms <= now_ms)
    notes = tuple(note for note in view.notes if note.written_at_ms <= now_ms)
    return MemoryView(
        calibration=view.calibration,
        priors=view.priors,
        features=view.features,
        lessons=lessons,
        notes=notes[-MEMORY_NOTES_VIEW_MAX:],
    )


def filter_hive_view(
    view: HiveView, *, now_ms: int, interval_min: int, open_market_ids: Sequence[str], limits: Limits, live_coop: bool
) -> HiveView:
    """Apply the hive's own visibility rules again, and the one rule a view cannot state (section 7.9).

    Three filters, in the order they matter:

    1. an entry with ``visible_from_ms > now_ms`` is dropped, which is what a lesson carries its stamp
       for; the lessons are then re-ranked by section 10.4's key and capped, so a hive that returned more
       than the cap or ranked them differently cannot change what the agent reads;
    2. a **resolution** is visible from ``bar_of(resolved_at_ms) + interval_ms``, the first bar strictly
       after the settling bar (ruling R12), which is recomputable from the view itself;
    3. a **forecast** of a market that is open in this very observation is dropped whatever the hive
       said. A forecast entry's stamp is derived from its market's resolution, which a view does not
       carry, so the check that can be made here is the one that matters: no agent ever reads another
       agent's forecast on a market that has not settled. ``open_market_ids`` is therefore every
       instrument the caller declared **open** at this bar and not only the ones the observation had
       room for: an open market beyond ``markets_per_obs_max`` is still unsettled, and filtering against
       the truncated list would surface exactly the forecast 7.9 forbids. ``prev_bar_forecasts`` is the
       one exception the contract allows, is empty unless ``live_coop``, and every entry of it must sit
       at ``now_ms - interval_ms``, which is section 8.3's normative sentence and is read literally here:
       on a session instrument the previous **bar** is Friday's and this filter drops a Friday entry read
       on a Monday. Dropping is the conservative side of a leak boundary and the sentence is the
       contract's, so the gap is reported rather than reinterpreted (ruling R192 rewrote
       ``decided_at_ms`` and left this one alone).

    ``reputations`` passes through: a ``ReputationView`` carries no stamp of its own, and 10.4 makes the
    hive compute it "as of now", which is the one thing this function cannot recompute from a view.

    Each cap selects its own **most recent** entries rather than trusting the order the hive returned
    them in (10.4's ranking columns), so a hive that sorted differently or returned more than the cap
    cannot change what the agent reads. Recency reads ``visible_from_ms`` where the view carries it
    (a lesson), the recomputed release bar for a resolution, and ``bar_ms`` for a forecast, whose own
    ``visible_from_ms`` is not in the view; the ties break on the ids, so the result is a pure function
    of the set of entries.
    """
    span = interval_ms(interval_min)
    open_ids = set(open_market_ids)
    lessons = tuple(
        sorted(
            (lesson for lesson in view.lessons if lesson.visible_from_ms <= now_ms),
            key=lambda lesson: (-lesson.author_skill_micro, -lesson.visible_from_ms, lesson.entry_id),
        )
    )[: limits.hive_lessons]
    released = [
        item
        for item in view.resolutions
        if bar_of(item.resolved_at_ms, interval_min) + span <= now_ms
    ]
    released.sort(key=lambda item: (item.resolved_at_ms, item.market_id))
    resolutions = tuple(released[-HIVE_RESOLUTIONS_VIEW_MAX:])
    settled = [
        item
        for item in view.forecasts
        if item.bar_ms < now_ms and item.market_id not in open_ids
    ]
    settled.sort(key=lambda item: (item.bar_ms, item.market_id, item.agent_id))
    forecasts = tuple(settled[-limits.hive_forecasts :]) if limits.hive_forecasts > 0 else ()
    prev_bar = (
        tuple(item for item in view.prev_bar_forecasts if item.bar_ms == now_ms - span)
        if live_coop
        else ()
    )
    return HiveView(
        lessons=lessons,
        reputations=view.reputations,
        resolutions=resolutions,
        forecasts=forecasts,
        prev_bar_forecasts=prev_bar,
    )


def filter_grant(grant: ResearchGrant, *, now_ms: int) -> ResearchGrant:
    """A grant crossed a bar boundary, so its content is filtered again at the bar it is read at.

    A ``NewsView`` carries no ``visible_from_ms`` (the strong filter ran when the grant was built, over
    the dataset's ``NewsItem``), so what is checkable here is that nothing in it was **published** after
    ``now_ms``, which no visible item can have been. A print is checked on ``t_ms < now_ms``, exactly as
    a trade inside a market view is.
    """
    return ResearchGrant(
        kind=grant.kind,
        market_id=grant.market_id,
        granted_at_ms=grant.granted_at_ms,
        news=tuple(item for item in grant.news if item.published_at_ms <= now_ms),
        trades=tuple(trade for trade in grant.trades if trade.t_ms < now_ms),
    )


# --------------------------------------------------------------------------------------------------
# The sensor gene's hook (PRD v5 section 1; amendment C1c will write the catalogue as section 18)
#
# PRD v5 makes **which information an agent consumes part of its genome**: a sensor set, priced per bar,
# so that evolution can discover that reading the news beats reading the tape, or that a cheap diet beats
# an expensive one. The structural half of that is here and nothing else is: this module gates the view
# fields whose data a built dataset already carries, and it gates them by **subtraction**.
#
# Subtraction is the whole safety argument. An observation is assembled exactly as it was before, by the
# same filters, and the sensor set is then applied by dropping names from what those filters produced. A
# sensor set can therefore only ever narrow an observation: there is no second assembly path a new
# sensor could widen, so no sensor set can expose a byte the as-of rules of section 5.4 forbid, and the
# default set (nothing dropped) is byte-identical to the builder that predates the hook. It costs a
# computed and discarded field per gated sensor, which is the price of one code path instead of two.
#
# What is **not** here, and what amendment C1c and package S1 must add, is written at
# :data:`SENSOR_VIEW_FIELDS`.
# --------------------------------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class SensorFields:
    """The view fields one sensor gates: ``MarketView`` field names, then ``Observation`` field names.

    A field may be gated by more than one sensor, and then it is present as soon as **any** of its
    sensors is bought (:func:`unsensed_view_fields` is a set difference over the union of what was
    bought). A field named by no sensor at all is ungated and is always present.
    """

    market: frozenset[str] = frozenset()
    observation: frozenset[str] = frozenset()


#: The one place a sensor's reach is declared, so that C1c extends it in one place (PRD v5 section 1).
#:
#: Every name here is a sensor of the PRD's catalogue **whose data a built dataset already carries and
#: whose fields the view builders above already produce**, spelled as the fields are spelled in this file
#: today. Nothing else is wired, because a sensor whose data does not exist would gate nothing and would
#: read as a promise: ``comments``, ``hn``, ``gdelt_recent``, ``filings``, ``macro_releases``,
#: ``wiki_asof`` and the two hive sensors (``hive_insights``, ``hive_reputation``) are therefore absent
#: from this mapping and unknown to :func:`resolve_sensor_set`.
#:
#: What C1c and S1 must add, each as a row of this mapping plus the fields the row gates:
#:
#: * the sensors whose data F1 to F5 import (``filings``, ``macro_releases``, ``hn``, ``gdelt_recent``,
#:   ``comments``) and the deeper ``wiki_asof``, which today is a **research kind** and not a sensor: the
#:   research budget of section 8.1 and the sensor budget of PRD v5 section 1.2 are the same allowance
#:   read twice, and C1c has to say which one prices a grant;
#: * the two hive sensors. ``Observation.hive`` is deliberately ungated here: ``hive_insights`` is the
#:   promoted rules of PRD v5 section 2, which do not exist, and splitting ``HiveView`` between
#:   ``hive_reputation`` (its ``reputations``) and ``hive_insights`` (the rest) is a sub-structure gate,
#:   which is the next item;
#: * **sub-structure gating**. A sensor here gates a whole view field. ``volume_profile`` should also
#:   gate ``Bar.volume_milli``, ``Bar.n_trades`` and ``Bar.open_interest`` inside ``bars``, and
#:   ``microstructure`` should gate ``Bar.yes_bid_bp`` and ``Bar.yes_ask_bp``, which cannot be done from
#:   this module: ``Bar.to_dict`` is D1's, so a partial bar is a ``pmx.types`` change and a contract row;
#: * ``cash_events`` (a market view's applied dividends, splits, rolls and funding times, ruling R183) is
#:   ungated because the PRD's catalogue names no sensor for it: ``volume_profile`` says "funding" while
#:   a dividend is not microstructure at all, so C1c has to place it rather than this hook guessing;
#: * a sensor's **cost, version hash and as-of lag**, the ``SensorBlock`` integer feature format and the
#:   budget rule. None of that is here: this hook only decides what an observation carries.
#:
#: The identity and contract fields of a market view (``market_id``, ``provider``, ``url``, ``question``,
#: ``description``, ``category``, ``tags``, ``currency``, ``created_at_ms``, ``tradable``,
#: ``fee_schedule_id``, ``kind``, ``tick_size_micro``, ``point_value_micro``), the agent's own book
#: (``position``, ``portfolio``) and what it is judged under (``limits``, ``research``, ``obs_version``,
#: ``agent_id``, ``now_ms``, ``interval_min``, ``markets``) are ungated on purpose: an agent that cannot
#: name the instrument it trades or read its own cash cannot act at all, and a diet is about information
#: about the world.
SENSOR_VIEW_FIELDS: Final[Mapping[str, SensorFields]] = MappingProxyType(
    {
        # The instrument's own bars and the as-of price they carry (cost 0 in the PRD: always on).
        "tape": SensorFields(market=frozenset({"bars", "first_price_bp", "last_price_bp"})),
        # Last prints, bid and ask where the venue published them.
        "microstructure": SensorFields(market=frozenset({"best_bid_bp", "best_ask_bp", "trades"})),
        "volume_profile": SensorFields(
            market=frozenset({"volume_milli_7d", "volume_milli_to_date", "n_trades_to_date"})
        ),
        # The cluster's other instruments, as far as an observation names them today (17.7's families).
        "cross_asset": SensorFields(market=frozenset({"underlying_id", "twins"})),
        # The venue's published schedule: hours to close, hours to the next bar, which calendar.
        "calendar": SensorFields(
            market=frozenset({"close_at_ms", "session_calendar_id", "hours_to_next_bar"})
        ),
        # Wikipedia Current events, linked and global: the per-market digest and the global one.
        "wiki_daily": SensorFields(market=frozenset({"news"}), observation=frozenset({"news"})),
        "memory": SensorFields(observation=frozenset({"memory"})),
    }
)

#: Every sensor name this hook knows, sorted, so a caller can name the full diet explicitly.
SENSOR_NAMES: Final = tuple(sorted(SENSOR_VIEW_FIELDS))

#: The ``MarketView`` and ``Observation`` fields some sensor gates. A field outside these is always
#: present, whatever the sensor set, which is what makes the ungated list above a checkable claim.
GATED_MARKET_VIEW_FIELDS: Final = frozenset(
    name for gated in SENSOR_VIEW_FIELDS.values() for name in gated.market
)
GATED_OBSERVATION_FIELDS: Final = frozenset(
    name for gated in SENSOR_VIEW_FIELDS.values() for name in gated.observation
)


def resolve_sensor_set(sensors: Iterable[str] | None) -> frozenset[str] | None:
    """The sensor set as the builder uses it: ``None`` means "every sensor", so nothing is gated.

    ``None`` is the default and the value every caller that predates the hook passes implicitly, and the
    full set resolves back to it, so ``sensors=SENSOR_NAMES`` and ``sensors=None`` are the same bytes and
    not merely the same fields.

    An unknown name is **refused** rather than ignored: a genome that names a sensor this build does not
    have would otherwise silently get a diet it did not ask for, and a mutation that misspells a sensor
    would read as a free one. The error is ``InvalidConfigError``, exactly as an unknown research kind is
    (:func:`research_cost`), because a sensor name comes from a genome and a genome is configuration.
    """
    if sensors is None:
        return None
    named = frozenset(sensors)
    unknown = sorted(named - frozenset(SENSOR_VIEW_FIELDS))
    if unknown:
        raise InvalidConfigError("unknown sensor", sensors=unknown, known=list(SENSOR_NAMES))
    return None if named == frozenset(SENSOR_VIEW_FIELDS) else named


def unsensed_view_fields(sensors: frozenset[str] | None) -> tuple[frozenset[str], frozenset[str]]:
    """``(market fields, observation fields)`` a resolved sensor set did not buy, and therefore drops.

    A gated field is kept when **any** of the sensors that gate it was bought, so adding a sensor can
    only add fields: the result is a set difference and never a rebuild.
    """
    if sensors is None:
        return frozenset(), frozenset()
    bought_market = frozenset(name for sensor in sensors for name in SENSOR_VIEW_FIELDS[sensor].market)
    bought_observation = frozenset(
        name for sensor in sensors for name in SENSOR_VIEW_FIELDS[sensor].observation
    )
    return GATED_MARKET_VIEW_FIELDS - bought_market, GATED_OBSERVATION_FIELDS - bought_observation


def _unsensed_attribute(view: object, name: str) -> NoReturn:
    """Refuse the read of a field the agent's sensors did not buy, and say which field it was.

    ``SchemaError`` is the taxonomy's nearest fit ("a structural rule of the contract that the schema
    cannot express") and is reported as a contract issue: section 13.1 should carry a
    ``SensorAbsentError`` of its own, because this is a distinct failure and ``errors.py`` is D1's file.
    """
    unsensed = cast(frozenset[str], object.__getattribute__(view, "unsensed_fields"))
    if name in unsensed:
        raise SchemaError(
            "field was not sensed",
            field=name,
            unsensed=sorted(unsensed),
            view=type(view).__name__,
        )
    raise AttributeError(name)


class SensedMarketView(MarketView):
    """A market view a narrowed sensor set assembled: an unsensed field is **absent**, never zeroed.

    Absence is represented twice over, and both spellings say the same thing:

    * the slot is **not set**. ``MarketView`` is a ``slots=True`` dataclass, so an unset field has no
      value at all in the object: there is no zero to mistake for a price, no ``None`` to mistake for an
      unknown quote and no empty tuple to mistake for a market with no prints. Reading it raises
      (:func:`_unsensed_attribute`), and so does ``hasattr``, so an agent cannot probe the absence into
      a default either;
    * the key is **omitted** from :meth:`to_dict`, which is what an LLM agent reads and what is hashed.

    That is the representation ruling of this hook, and the alternative was a sentinel value in the slot.
    A sentinel would have to be typed into every field of ``MarketView`` (``int | Unsensed``), which is
    D1's file, and it would widen the type of every field for every consumer of a full observation, so a
    scripted agent would carry a narrowing branch on a field it always has. An unset slot needs no type
    change anywhere and fails closed.

    ``to_dict`` is the **full** renderer's output minus the unsensed keys, and not a second renderer:
    :func:`sensed_market_view` builds a plain ``MarketView`` from the same fields, renders it with D1's
    own ``to_dict`` and drops the dropped names, so a field D1 adds to the dataclass cannot go missing
    from a narrowed observation while nothing fails.

    Equality and hashing read the rendered payload and the unsensed set, because the dataclass' own read
    every field and would raise on an unsensed one.
    """

    __slots__ = ("_payload", "unsensed_fields")

    _payload: dict[str, object]
    #: The ``MarketView`` field names this agent's sensors did not buy.
    unsensed_fields: frozenset[str]

    def to_dict(self) -> dict[str, object]:
        return dict(self._payload)

    def __getattr__(self, name: str) -> NoReturn:
        _unsensed_attribute(self, name)

    def __repr__(self) -> str:
        return (
            f"SensedMarketView(market_id={self._payload.get('market_id')!r}, "
            f"unsensed={sorted(self.unsensed_fields)})"
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SensedMarketView):
            return False
        return self.unsensed_fields == other.unsensed_fields and self._payload == other._payload

    def __hash__(self) -> int:
        return hash((self.unsensed_fields, canonical_json(self._payload)))


class SensedObservation(Observation):
    """An observation a narrowed sensor set assembled. Absence is exactly :class:`SensedMarketView`'s."""

    __slots__ = ("_payload", "unsensed_fields")

    _payload: dict[str, object]
    #: The ``Observation`` field names this agent's sensors did not buy.
    unsensed_fields: frozenset[str]

    def to_dict(self) -> dict[str, object]:
        return dict(self._payload)

    def __getattr__(self, name: str) -> NoReturn:
        _unsensed_attribute(self, name)

    def __repr__(self) -> str:
        return (
            f"SensedObservation(agent_id={self._payload.get('agent_id')!r}, "
            f"now_ms={self._payload.get('now_ms')!r}, unsensed={sorted(self.unsensed_fields)})"
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SensedObservation):
            return False
        return self.unsensed_fields == other.unsensed_fields and self._payload == other._payload

    def __hash__(self) -> int:
        return hash((self.unsensed_fields, canonical_json(self._payload)))


def sensed_market_view(view_fields: Mapping[str, object], *, unsensed: frozenset[str]) -> MarketView:
    """A market view over ``view_fields`` with ``unsensed`` dropped, or the plain view when none is.

    The empty case returns exactly what :func:`_market_view` returns, so the default sensor set is not a
    special case of this function: it is the same object it always was.
    """
    full = _market_view(view_fields)
    if not unsensed:
        return full
    payload = {name: value for name, value in full.to_dict().items() if name not in unsensed}
    view = object.__new__(SensedMarketView)
    object.__setattr__(view, "unsensed_fields", unsensed)
    object.__setattr__(view, "_payload", payload)
    for name, value in view_fields.items():
        if name not in unsensed:
            object.__setattr__(view, name, value)
    return view


def sensed_observation(observation: Observation, *, unsensed: frozenset[str]) -> Observation:
    """``observation`` with its ``unsensed`` top-level fields dropped, or ``observation`` itself."""
    if not unsensed:
        return observation
    payload = {name: value for name, value in observation.to_dict().items() if name not in unsensed}
    narrowed = object.__new__(SensedObservation)
    object.__setattr__(narrowed, "unsensed_fields", unsensed)
    object.__setattr__(narrowed, "_payload", payload)
    for field in fields(Observation):
        if field.name not in unsensed:
            object.__setattr__(narrowed, field.name, getattr(observation, field.name))
    return narrowed


# --------------------------------------------------------------------------------------------------
# The builder
# --------------------------------------------------------------------------------------------------
def build_observation(
    *,
    agent_id: str,
    now_ms: int,
    config: RunConfig,
    markets: Sequence[InstrumentLike],
    positions: Mapping[str, PositionView],
    portfolio: PortfolioView,
    memory: MemoryLike | None,
    hive: HiveLike | None,
    news: Sequence[NewsItem],
    grants: Sequence[ResearchGrant],
    calendar: Calendar | None = None,
    sensors: Iterable[str] | None = None,
) -> Observation:
    """One agent's whole world at one bar, filtered (sections 5.4, 7.9 and 8.3).

    ``markets`` are the instruments that are **open** at ``now_ms`` (the runner's ``BarSlice.open_ids``);
    this function decides what of them the agent may see and how much of it. ``calendar`` is a
    keyword-only addition with a default (reported): the tradability of a continuous instrument, the
    application bar of a dividend and the hours to the next bar are all lookups only the calendar can
    answer (ruling R187), and the contract's signature predates them. On a binary run everything is
    computed from the market records and the calendar changes no byte.

    When more than ``markets_per_obs_max`` instruments are open, the observation carries the first
    ``markets_per_obs_max`` by ``market_id`` **among the tradable ones**, then by ``market_id`` among the
    rest (section 8.3). The rule is deterministic, so E1, E5 and A5 agree about which markets are
    addressable; the ones that did not fit are still forecast-carried by the runner and still scored.

    ``sensors`` is the agent's **sensor set** (PRD v5 section 1, the hook above): keyword-only, and
    ``None`` means every sensor, which is what every caller that predates the hook passes and which is
    byte-identical to the builder without it. A narrowed set is applied by **subtraction** over what the
    as-of filters produced, so it can only ever narrow this observation: a field the set did not buy is
    absent from the view and its key is absent from the payload, and nothing about the filtering above
    depends on the set. The size cap and the leak guard then run on the narrowed payload, which is what
    the agent actually reads.
    """
    sensor_set = resolve_sensor_set(sensors)
    unsensed_market, unsensed_observation = unsensed_view_fields(sensor_set)
    span = interval_ms(config.interval_min)
    if now_ms % span != 0:
        raise InvalidConfigError("now_ms must be a bar open", now_ms=now_ms, interval_min=config.interval_min)
    ordered = sorted(markets, key=lambda instrument: instrument.id)
    ids = [instrument.id for instrument in ordered]
    if len(set(ids)) != len(ids):
        duplicates = sorted({market_id for market_id in ids if ids.count(market_id) > 1})
        raise InvalidConfigError("two instruments share an id", market_ids=duplicates)
    tradable = {
        instrument.id: _tradable_flag(instrument, now_ms=now_ms, config=config, calendar=calendar)
        for instrument in ordered
    }
    selected = [instrument for instrument in ordered if tradable[instrument.id]]
    selected += [instrument for instrument in ordered if not tradable[instrument.id]]
    selected = selected[: config.markets_per_obs_max]
    selected.sort(key=lambda instrument: instrument.id)

    visible_news = tuple(item for item in news if item.visible_from_ms <= now_ms)
    kept_grants = tuple(filter_grant(grant, now_ms=now_ms) for grant in grants)
    history_by_market = {
        grant.market_id: grant.trades for grant in kept_grants if grant.kind == "history" and grant.market_id
    }
    views: list[MarketView] = []
    for instrument in selected:
        linked = rank_news_items(
            [item for item in visible_news if instrument.id in item.match_ids], market_id=instrument.id
        )[: config.news_per_market]
        prints = tuple(
            trade for trade in history_by_market.get(instrument.id, ()) if trade.t_ms < now_ms
        )
        views.append(
            sensed_market_view(
                market_view_fields(
                    instrument,
                    now_ms=now_ms,
                    config=config,
                    tradable=tradable[instrument.id],
                    position=positions.get(instrument.id, _FLAT_POSITION),
                    news=[news_view_of(item, market_id=instrument.id) for item in linked],
                    trades=prints[-config.trades_window :] if config.trades_window > 0 else (),
                    calendar=calendar,
                ),
                unsensed=unsensed_market,
            )
        )

    market_ids = sorted_market_ids(view.market_id for view in views)
    limits = limits_from_config(config, research_units_total=config.research_budget_for(agent_id))
    digest = tuple(
        news_view_of(item) for item in rank_news_items(visible_news)[: config.news_global]
    )
    memory_view = (
        filter_memory_view(memory.view(now_ms=now_ms), now_ms=now_ms) if memory is not None else MemoryView()
    )
    if hive is None or config.no_hive:
        hive_view = HiveView()
    else:
        hive_view = filter_hive_view(
            hive.view(
                now_ms=now_ms,
                agent_id=agent_id,
                market_ids=market_ids,
                limits=limits,
                live_coop=config.live_coop,
            ),
            now_ms=now_ms,
            interval_min=config.interval_min,
            # Every open instrument, not the ones that fit: a market beyond ``markets_per_obs_max`` is
            # still open, and a forecast on it is still another agent's forecast on an unsettled market.
            open_market_ids=sorted_market_ids(instrument.id for instrument in ordered),
            limits=limits,
            live_coop=config.live_coop,
        )
    observation = Observation(
        obs_version=OBS_VERSION,
        agent_id=agent_id,
        now_ms=now_ms,
        interval_min=config.interval_min,
        markets=tuple(views),
        news=digest,
        portfolio=portfolio,
        memory=memory_view,
        hive=hive_view,
        research=ResearchView(
            units_remaining=portfolio.research_units_remaining, granted=kept_grants
        ),
        limits=limits,
    )
    observation = sensed_observation(observation, unsensed=unsensed_observation)
    payload = observation.to_dict()
    rendered = canonical_json(payload)
    check_observation_size(rendered, agent_id=agent_id, now_ms=now_ms)
    if mentions_forbidden_key(rendered):
        assert_no_leak(payload, agent_id=agent_id, now_ms=now_ms)
    return observation


def _tradable_flag(
    instrument: InstrumentLike, *, now_ms: int, config: RunConfig, calendar: Calendar | None
) -> bool:
    """What ``MarketView.tradable`` says: ``tradable(m, t)`` on a binary, ``open(i, t)`` on a continuous
    instrument (ruling R181), because ``t < last_bar(i)`` would announce the last bar one bar ahead.

    With a calendar the answer is the calendar's, which is the one implementation (ruling R187). Without
    one it is recomputed from the record for a binary, whose ``close_at_ms`` and settling bar are all the
    predicate of 5.3 needs; a continuous instrument the caller declared open is open.
    """
    kind = instrument_kind(instrument)
    if calendar is not None:
        return calendar.is_open(instrument.id, now_ms) if kind != KIND_BINARY else calendar.is_tradable(
            instrument.id, now_ms
        )
    if kind != KIND_BINARY:
        return True
    span = interval_ms(instrument.interval_min)
    close_at_ms = int(cast(int, getattr(instrument, "close_at_ms", 0)))
    settles_at_ms = bar_of(int(cast(int, getattr(instrument, "resolved_at_ms", 0))), instrument.interval_min)
    return now_ms + span <= close_at_ms and settles_at_ms != now_ms


def render_observation_json(obs: Observation) -> str:
    """``canonical_json(obs.to_dict())``: what an ``observations/`` dump holds and what is hashed.

    The hash of an observation may legally be journaled (section 9.3) precisely because an observation
    carries no float, so this one encoder suffices and there is no float-tolerant sibling.
    """
    return canonical_json(obs.to_dict())


def observation_bytes(obs: Observation) -> int:
    """The canonical size of an observation, in bytes: ``observation_built.bytes`` (section 9.2)."""
    return len(render_observation_json(obs).encode("utf-8"))


def check_observation_size(payload: str, *, agent_id: str, now_ms: int) -> int:
    """Refuse an observation over ``OBSERVATION_MAX_BYTES`` rather than truncating it (section 8.1)."""
    size = len(payload.encode("utf-8"))
    if size > OBSERVATION_MAX_BYTES:
        raise ObservationTooLargeError(
            "observation exceeds OBSERVATION_MAX_BYTES",
            agent_id=agent_id,
            now_ms=now_ms,
            bytes=size,
            limit=OBSERVATION_MAX_BYTES,
        )
    return size


def mentions_forbidden_key(rendered: str) -> bool:
    """Could this rendered observation carry a forbidden key? A cheap test that is wrong in one direction.

    ``False`` is a proof: canonical JSON has no whitespace (section 4.1), so every object key appears
    literally as ``"<name>":``, and a name that is absent from the text is in no object of the payload.
    ``True`` is only a suspicion, because a news headline may quote the words, and the exact structural
    check of :func:`assert_no_leak` decides it.

    The split exists because the guard runs on **every** observation of every agent of every bar and not
    only in a test: on a 56-market bar of the 2026 dataset the recursive walk is a third of the cost of
    building the observation, and a guard that is expensive is a guard somebody eventually switches off.
    """
    return any(f'"{key}":' in rendered for key in FORBIDDEN_OBSERVATION_KEYS)


def observation_key_set(payload: object) -> frozenset[str]:
    """Every key that appears anywhere in a rendered observation, at any depth.

    The clock test is structural rather than an integer scan, because a scan cannot pass on legal data
    (section 8.3): ``close_at_ms == resolved_at_ms`` is the normal case on both venues and ``bars_window``
    collides with the bar count of any market that long.
    """
    found: set[str] = set()
    stack: list[object] = [payload]
    while stack:
        node = stack.pop()
        if isinstance(node, Mapping):
            for key, value in cast(Mapping[str, object], node).items():
                found.add(key)
                stack.append(value)
        elif isinstance(node, (list, tuple)):
            stack.extend(cast(Sequence[object], node))
    return frozenset(found)


def leak_scan_payload(payload: object) -> object:
    """The payload the key check runs over: the observation minus its two published-past subtrees.

    Section 8.3's key set and section 7.9's field list are stated globally, and two of the structures
    section 8.3 itself declares inside an ``Observation`` carry a name from that list **legally**, because
    what they hold is the venue's or the hive's published past rather than a fact about the future:

    * ``hive.resolutions`` is ``(market_id, outcome, life_mean_price_bp, resolved_at_ms)``, and a
      resolution entry is released one bar **after** the settling bar (ruling R12). Its ``resolved_at_ms``
      is the announcement of a settlement that has happened; the ban exists so that an agent cannot read
      the resolution instant of a market that is still **open**, which the filter of
      :func:`filter_hive_view` is what enforces;
    * a market view's ``cash_events`` carries each applied event's ``detail`` verbatim (ruling R183),
      whose keys are ``dividend_micro``, ``rate_ppm``, ``gap_ticks`` and friends. 7.9 bans those names for
      an event whose application bar has **not** completed, which :func:`visible_cash_events` is what
      enforces.

    Both exemptions are exactly this narrow: the key is legal inside that one subtree and nowhere else in
    an observation, so a ``resolved_at_ms`` on a market view or a ``dividend_micro`` on a portfolio still
    raises. The contradiction between the global sentence and the two declared structures is reported as a
    contract issue.
    """
    if not isinstance(payload, Mapping):
        return payload
    scanned = dict(cast(Mapping[str, object], payload))
    hive = scanned.get("hive")
    if isinstance(hive, Mapping):
        hive_copy = dict(cast(Mapping[str, object], hive))
        hive_copy["resolutions"] = []
        scanned["hive"] = hive_copy
    markets = scanned.get("markets")
    if isinstance(markets, list):
        stripped: list[object] = []
        for view in cast(list[object], markets):
            if isinstance(view, Mapping):
                view_copy = dict(cast(Mapping[str, object], view))
                if "cash_events" in view_copy:
                    view_copy["cash_events"] = []
                stripped.append(view_copy)
            else:
                stripped.append(view)
        scanned["markets"] = stripped
    return scanned


def assert_no_leak(payload: object, *, agent_id: str, now_ms: int) -> None:
    """Raise ``LeakError`` when a rendered observation carries a key section 7.9 or 8.3 forbids.

    It decides every observation the builder produces, not only a test: a field added to a view by a
    later package would otherwise carry an outcome into a prompt with nothing failing. The builder reaches
    it through :func:`mentions_forbidden_key`, which can only skip a payload in which no forbidden name
    appears at all. The two subtrees :func:`leak_scan_payload` sets aside are the venue's and the hive's
    published past, and nothing else is set aside.
    """
    forbidden = sorted(
        observation_key_set(leak_scan_payload(payload)) & frozenset(FORBIDDEN_OBSERVATION_KEYS)
    )
    if forbidden:
        raise LeakError(
            "observation carries a forbidden key",
            agent_id=agent_id,
            now_ms=now_ms,
            keys=forbidden,
        )
