"""REST payloads and REST routes of the replay API (CONTRACTS section 7.21).

Three rules shape every line of this module, and they are the reason it is long:

1. **Nothing here recomputes engine logic.** Every number served comes from a
   journal event, from a :class:`~pxe.metrics.projection.MatchProjection`, from
   ``runs/<match_id>/metrics.json`` or from the
   :class:`~pxe.store.db.Store`. Where a payload field has no supplier in any
   of those, the derivation is a pure regrouping of journalled numbers, it is
   named in the docstring of the builder that does it, and it is listed in
   ``docs/REPLAY_API.md``.
2. **The payload models are the contract.** Field names, ``snake_case``
   spelling, units (cents for money, ``1..99`` for a price, ppm for a
   probability, ticks for a duration) and nullability mirror section 7.21
   character for character, because ``web/src/api/types.ts`` is a hand written
   mirror of them and a rename no test catches is a silent build break for
   A24.
3. **One builder, one payload.** ``TickState`` is built exactly once per
   ``(match_id, tick)`` and cached as bytes, so ``GET .../ticks/{tick}`` and
   the WebSocket ``tick`` frame are byte identical by construction rather than
   by review (section 7.21, "the same ``TickState`` type is served by both").

The cache is an LRU of :data:`MATCH_CACHE_SIZE` entries keyed by ``match_id``.
A cache entry holds the journal, the projection and every per tick payload, so
a warm random access by tick is a dictionary lookup and a byte copy.
"""

from __future__ import annotations

import json
import unicodedata
from collections import OrderedDict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel

from pxe import ACTION_VERSION, ENGINE_VERSION, OBS_VERSION
from pxe.errors import PxeError, StoreError
from pxe.events import (
    AgentActionReceived,
    AgentActionRejected,
    AgentTimedOut,
    Event,
    MarketCancelled,
    MarketResolved,
    MarkToMarket,
    MatchEnded,
    MatchStarted,
    MMQuoted,
    NewsPublished,
    OrderCancelled,
    OrderPlaced,
    OrderRejected,
    PositionSnapshot,
    TickStarted,
    TradeExecuted,
    journal_hash,
)
from pxe.journal import read_journal
from pxe.metrics import projection as projection_module
from pxe.metrics.aggregate import MatchMetrics, compute_all
from pxe.metrics.behavioral import DESCRIPTOR_NAMES
from pxe.metrics.calibration import reliability_curve
from pxe.metrics.projection import MatchProjection, OrderRecord
from pxe.store.db import Store
from pxe.store.files import artefact_paths
from pxe.tournament.elites import DEFAULT_ELITE_AXES, DEFAULT_ELITE_BINS
from pxe.tournament.latin_square import verify_balance
from pxe.types import (
    DEPTH_LEVELS,
    IncidentKind,
    bps_ratio,
    round_half_up,
    sorted_ids,
)
from pxe.types import (
    Incident as IncidentRecord,
)

__all__ = [
    "API_VERSION",
    "MATCH_CACHE_SIZE",
    "MAX_QUERY_CHARS",
    "WS_SPEEDS",
    "Health",
    "Page",
    "MatchSummary",
    "MarketInfo",
    "AgentInfo",
    "Ranking",
    "MatchDetail",
    "BookLevelDto",
    "MarketTick",
    "PositionDto",
    "AccountTick",
    "NewsDto",
    "SignalDto",
    "TradeDto",
    "PredictionDto",
    "MessageDto",
    "ResolutionDto",
    "Highlight",
    "HighlightsEnvelope",
    "TickState",
    "AgentSeries",
    "MarketSeries",
    "MatchSeries",
    "DecisionPrediction",
    "DecisionOrder",
    "Decision",
    "PerformanceRow",
    "ReliabilityBin",
    "CalibrationRow",
    "DescriptorRow",
    "MatchMetricsPayload",
    "Incident",
    "IncidentsEnvelope",
    "TournamentSummary",
    "LeaderboardRow",
    "ProgressionPoint",
    "ProgressionRow",
    "EliteCellDto",
    "Elites",
    "CostRow",
    "LiquidityCostRow",
    "ProfileBalance",
    "Kpi",
    "TournamentDetail",
    "ReplayService",
    "api_error",
    "build_router",
    "sample_payloads",
    "iter_payload_models",
]

#: Payload version of section 7.21. The ``/api`` prefix itself is unversioned;
#: this is what ``Health.api_version`` reports and what a client pins against.
#: It lives here and not in :mod:`pxe.api.app` because ``app`` imports this
#: module and a lazy import back would be a ruff ``PLC0415`` violation.
API_VERSION: str = "1"

#: How many match projections stay resident. CONTRACTS section 7.21 fixes it at
#: eight: a replay session touches one match, a tournament view a handful.
MATCH_CACHE_SIZE: int = 8

#: Longest accepted ``q`` on ``GET .../decisions``. Anything longer is a ``400``
#: (section 7.21, "a ``q`` longer than 200 characters is a ``400``").
MAX_QUERY_CHARS: int = 200

#: The seven legal WebSocket speeds, in ticks per second (section 7.21).
WS_SPEEDS: tuple[int, ...] = (1, 2, 4, 8, 16, 32, 64)

#: Colour slots the UI has (section 7.25, ``AGENT_COLOURS`` has eight entries).
COLOUR_SLOTS: int = 8

#: ``colour_index`` of an account that is out of the ranking. ``MM`` is neutral
#: grey in the UI and is never given a colour (section 7.25); the field is a
#: non nullable ``int`` in section 7.21, so the out of band value is ``-1``.
NO_COLOUR_INDEX: int = -1

#: Conventional TrueSkill display interval: ``mu`` plus or minus three sigma.
#: Section 7.21 asks for ``ci_low``/``ci_high`` on a leaderboard row and names
#: no supplier; the store keeps ``mu`` and ``sigma`` and nothing else per
#: harness, so the interval is the conservative one a rating is read with.
CI_SIGMA_MULTIPLIER: float = 3.0

#: The TrueSkill prior sigma of :class:`~pxe.tournament.ratings.RatingService`,
#: used as the denominator of the ``sigma_shrink_ppm`` KPI.
INITIAL_SIGMA: float = 8.333

#: Matches a harness must have played before its sigma counts toward
#: ``sigma_shrink_ppm`` (PRD section 15: "after 20 matches").
SIGMA_SHRINK_MIN_MATCHES: int = 20

_PPM: int = 1_000_000

MarketStatusLiteral = Literal["open", "resolved", "cancelled"]
OutcomeLiteral = Literal["yes", "no"]
RefSourceLiteral = Literal["mid", "last", "prior"]
SideLiteral = Literal["buy", "sell"]


# ---------------------------------------------------------------------------
# Errors (section 7.21 rule 3: one shape for every 4xx and 5xx)
# ---------------------------------------------------------------------------
def api_error(status: int, code: str, message: str, **detail: Any) -> HTTPException:
    """Build the one error a route ever raises.

    Section 7.21 rule 3 fixes the body shape as
    ``{"error": {"code": ..., "message": ..., "detail": {...}}}`` and the status
    carries the class: ``404`` unknown match, tournament or tick, ``400`` a
    malformed query parameter, ``409`` an artefact that exists but is
    incomplete, ``500`` anything else. ``web/src/api/client.ts`` throws one
    ``ApiError`` built from that shape and nothing else, so a route that
    invents a second shape breaks the only error path the UI has.

    Args:
        status: HTTP status code.
        code: A ``RejectReason`` or :class:`~pxe.errors.PxeError` code.
        message: One human readable sentence.
        **detail: Structured context, JSON scalars only.

    Returns:
        The exception to raise. The application level handler of
        :mod:`pxe.api.app` renders it.
    """
    return HTTPException(status_code=status, detail={"code": code, "message": message, "detail": dict(detail)})


# ---------------------------------------------------------------------------
# Payload models. Section 7.21, verbatim.
# ---------------------------------------------------------------------------
class Health(BaseModel):
    """Liveness plus the four versions a client pins itself against."""

    status: Literal["ok"]
    engine_version: str
    obs_version: str
    action_version: str
    api_version: str


class Page[T](BaseModel):
    """One page of a listing. ``total`` counts the whole collection."""

    items: list[T]
    total: int
    limit: int
    offset: int


class MatchSummary(BaseModel):
    """One row of ``GET /api/matches``, and the head of :class:`MatchDetail`."""

    match_id: str
    tournament_id: str | None
    template_id: str
    template_version: str
    seed: int
    ticks_total: int
    n_markets: int
    n_agents: int
    journal_hash: str
    held_out: bool
    finished: bool
    winner_agent_id: str | None
    winner_harness_key: str | None


class MarketInfo(BaseModel):
    """Static definition of one market plus its terminal state."""

    market_id: str
    question: str
    prior_price: int
    resolution_tick: int
    status: MarketStatusLiteral
    outcome: OutcomeLiteral | None
    correlated_with: list[str]


class AgentInfo(BaseModel):
    """One seat, as the UI labels it."""

    agent_id: str
    harness_key: str
    kind: Literal["llm", "scripted"]
    display_name: str
    colour_index: int
    info_profile: Literal["generalist", "specialist", "delayed"]
    ranked: bool


class Ranking(BaseModel):
    """One line of the settled final ranking (FR-5.5.4)."""

    rank: int
    agent_id: str
    harness_key: str
    pnl_cents: int
    final_cash_cents: int
    pnl_pct_bps: int


class MatchDetail(MatchSummary):
    """Everything static about one match, plus its settled outcome."""

    config: dict[str, Any]
    mm_config: dict[str, Any]
    markets: list[MarketInfo]
    agents: list[AgentInfo]
    rankings: list[Ranking]
    mm_pnl_cents: int
    fees_collected_cents: int
    event_count: int
    liquidity_profile_name: Literal["liquid", "standard", "illiquid"]
    talking_mode: bool


class BookLevelDto(BaseModel):
    """One aggregated price level of a book side."""

    price: int
    qty: int


class MarketTick(BaseModel):
    """One market at the close of one tick."""

    market_id: str
    status: MarketStatusLiteral
    ref_price: int
    ref_source: RefSourceLiteral
    mid_price: int | None
    best_bid: int | None
    best_ask: int | None
    last_price: int | None
    bids: list[BookLevelDto]
    asks: list[BookLevelDto]
    bid_depth_qty: int
    ask_depth_qty: int
    tick_volume_qty: int
    mm_bid: int | None
    mm_ask: int | None
    mm_widened: bool


class PositionDto(BaseModel):
    """One non flat market position of one account."""

    market_id: str
    qty: int
    cost_basis_cents: int


class AccountTick(BaseModel):
    """One account at the close of one tick, straight from ``PositionSnapshot``."""

    account_id: str
    cash_cents: int
    reserved_cents: int
    free_cash_cents: int
    equity_cents: int
    frozen: bool
    resting_order_count: int
    positions: list[PositionDto]


class NewsDto(BaseModel):
    """One published news item. ``is_noise`` is served but never revealed by the UI."""

    news_id: str
    market_ids: list[str]
    headline: str
    body: str
    impact: Literal["low", "medium", "high"]
    is_noise: bool
    origin: Literal["info_engine", "resolution", "cancellation"]


class SignalDto(BaseModel):
    """One private signal, shown to the omniscient replay spectator."""

    signal_id: str
    agent_id: str
    market_id: str
    kind: str
    value_milli: int
    precision_ppm: int


class TradeDto(BaseModel):
    """One execution of the tick."""

    trade_id: str
    market_id: str
    price: int
    qty: int
    maker_agent_id: str
    taker_agent_id: str
    taker_side: SideLiteral


class PredictionDto(BaseModel):
    """One ``PredictionRecorded`` term of the tick."""

    agent_id: str
    market_id: str
    p_yes_ppm: int
    carried: bool


class MessageDto(BaseModel):
    """One public message posted this tick (FR-5.6.1)."""

    agent_id: str
    text: str
    deliver_tick: int


class ResolutionDto(BaseModel):
    """One market resolved during this tick."""

    market_id: str
    outcome: OutcomeLiteral
    payout_cents: int


class Highlight(BaseModel):
    """One annotated marking event (PRD section 9). ``label`` is the reason a spectator reads."""

    tick: int
    kind: Literal["big_trade", "early_resolution", "integrity_alert", "bankruptcy"]
    agent_ids: list[str]
    market_id: str | None
    magnitude_cents: int
    label: str


class TickState(BaseModel):
    """The whole world at one tick. Self contained: a client can resume from it with no state."""

    match_id: str
    tick: int
    open_market_ids: list[str]
    markets: list[MarketTick]
    accounts: list[AccountTick]
    news: list[NewsDto]
    signals: list[SignalDto]
    trades: list[TradeDto]
    predictions: list[PredictionDto]
    messages: list[MessageDto]
    resolutions: list[ResolutionDto]
    highlights: list[Highlight]


class HighlightsEnvelope(BaseModel):
    """Body of ``GET .../highlights``: section 7.21 spells it ``{"highlights": Highlight[]}``."""

    highlights: list[Highlight]


class AgentSeries(BaseModel):
    """One per tick series of one agent. ``values`` has length ``ticks_total``, index 0 is tick 1."""

    agent_id: str
    values: list[int]


class MarketSeries(BaseModel):
    """One per tick series of one market. Same length rule as :class:`AgentSeries`."""

    market_id: str
    values: list[int]


class MatchSeries(BaseModel):
    """The four per tick series the PnL race draws."""

    match_id: str
    ticks_total: int
    equity_cents: list[AgentSeries]
    cash_cents: list[AgentSeries]
    ref_price: list[MarketSeries]
    rank: list[AgentSeries]


class DecisionPrediction(BaseModel):
    """One prediction of one decision row, ``carried`` included (FR-6.2.4)."""

    market_id: str
    p_yes_ppm: int
    carried: bool


class DecisionOrder(BaseModel):
    """One order intent of one decision row, with what became of it."""

    op: Literal["place", "cancel"]
    market_id: str | None
    side: SideLiteral | None
    type: Literal["limit", "market"] | None
    price: int | None
    qty: int | None
    order_id: str | None
    outcome: Literal["filled", "partial", "resting", "rejected", "cancelled"]
    reject_reason: str | None


class Decision(BaseModel):
    """One ``(tick, agent)`` row of the decision journal (T4.4)."""

    tick: int
    agent_id: str
    source: Literal["llm", "scripted", "fallback"]
    predictions: list[DecisionPrediction]
    orders: list[DecisionOrder]
    message_public: str | None
    rationale: str | None
    headline: str
    timed_out: bool
    n_rejected: int
    trade_ids: list[str]


class PerformanceRow(BaseModel):
    """One agent's performance metrics (CONTRACTS section 9)."""

    agent_id: str
    pnl_cents: int
    pnl_bps: int
    sharpe_milli: int
    max_drawdown_cents: int
    max_drawdown_bps: int
    volume_qty: int
    trade_count: int
    maker_trade_count: int
    fees_paid_cents: int


class ReliabilityBin(BaseModel):
    """One bin of a reliability curve."""

    bin_upper_ppm: int
    n: int
    observed_yes_ppm: int


class CalibrationRow(BaseModel):
    """One agent's Brier score and its reliability curve."""

    agent_id: str
    brier_ppm: int
    n_terms: int
    n_carried: int
    reliability: list[ReliabilityBin]


class DescriptorRow(BaseModel):
    """One agent's six MAP-Elites behavioural descriptors."""

    agent_id: str
    maker_ratio_ppm: int
    reaction_latency_milli: int
    holding_horizon_milli: int
    herfindahl_ppm: int
    leverage_ppm: int
    message_intensity_ppm: int


class MatchMetricsPayload(BaseModel):
    """What ``GET /api/matches/{id}/metrics`` serves: ``metrics.json`` plus the curves."""

    match_id: str
    performance: list[PerformanceRow]
    calibration: list[CalibrationRow]
    descriptors: list[DescriptorRow]
    mm_pnl_cents: int
    fees_collected_cents: int


class Incident(BaseModel):
    """One integrity alert. Detectors run offline, so this is never a journal event."""

    incident_id: str
    kind: str
    severity: str
    match_id: str
    tick: int
    agent_ids: list[str]
    market_ids: list[str]
    score_ppm: int
    detector_version: str
    detail: dict[str, Any]


class IncidentsEnvelope(BaseModel):
    """Body of ``GET .../incidents``: section 7.21 spells it ``{"incidents": Incident[]}``."""

    incidents: list[Incident]


class TournamentSummary(BaseModel):
    """One row of ``GET /api/tournaments``."""

    tournament_id: str
    format: str
    n_matches: int
    n_harnesses: int
    seeds: list[int]
    total_cost_usd: float
    finished: bool


class LeaderboardRow(BaseModel):
    """One TrueSkill leaderboard row with its display interval."""

    rank: int
    harness_key: str
    mu: float
    sigma: float
    matches: int
    ci_low: float
    ci_high: float


class ProgressionPoint(BaseModel):
    """One version of one harness on its progression curve."""

    harness_key: str
    version: str
    mu: float
    sigma: float
    matches: int


class ProgressionRow(BaseModel):
    """The per version progression curve of one ``harness_id`` (PRD section 9)."""

    harness_id: str
    points: list[ProgressionPoint]


class EliteCellDto(BaseModel):
    """One occupied cell of the MAP-Elites archive."""

    coords: list[int]
    harness_key: str
    mu: float
    descriptors: list[int]


class Elites(BaseModel):
    """The MAP-Elites grid: its axes, its bin counts and its occupied cells."""

    axes: list[str]
    bins: list[int]
    cells: list[EliteCellDto]


class CostRow(BaseModel):
    """Provider bill of one harness over one tournament."""

    harness_key: str
    cost_usd: float


class LiquidityCostRow(BaseModel):
    """Cost of liquidity of one liquidity profile (FR-5.8.5)."""

    profile: str
    mm_pnl_cents: int


class ProfileBalance(BaseModel):
    """The FR-5.3.2 Latin square residual. ``exact`` false is a measurement, not an error."""

    exact: bool
    max_deviation: int
    seeds: int
    seats: int


class Kpi(BaseModel):
    """One PRD section 15 KPI. ``unit`` says how to read ``value_ppm``."""

    name: str
    value_ppm: int
    unit: str


class TournamentDetail(TournamentSummary):
    """Everything the tournament view draws (PRD section 9, T4.3)."""

    leaderboard: list[LeaderboardRow]
    progression: list[ProgressionRow]
    elites: Elites
    costs_usd: list[CostRow]
    incidents: list[Incident]
    liquidity_cost_cents: list[LiquidityCostRow]
    profile_balance: ProfileBalance
    kpis: list[Kpi]


# ---------------------------------------------------------------------------
# Internal per tick fold
# ---------------------------------------------------------------------------
@dataclass
class _RestingOrder:
    """One order still on the book, as the journal describes it."""

    market_id: str
    side: str
    price: int
    remaining_qty: int


@dataclass
class _TickFold:
    """Everything one tick's events say, before it becomes a :class:`TickState`."""

    open_market_ids: tuple[str, ...] = ()
    marks: dict[str, MarkToMarket] = field(default_factory=dict)
    levels: dict[str, tuple[tuple[BookLevelDto, ...], tuple[BookLevelDto, ...]]] = field(default_factory=dict)
    quotes: dict[str, MMQuoted] = field(default_factory=dict)
    snapshots: list[PositionSnapshot] = field(default_factory=list)
    news: list[NewsPublished] = field(default_factory=list)
    resolutions: list[MarketResolved] = field(default_factory=list)


@dataclass
class _AgentTickFold:
    """One ``(tick, agent)`` block of P2 and P3 events."""

    received: AgentActionReceived | None = None
    timed_out: bool = False
    rejections: list[AgentActionRejected] = field(default_factory=list)
    order_rejects: dict[int, OrderRejected] = field(default_factory=dict)
    placed: list[OrderPlaced] = field(default_factory=list)
    cancelled: dict[str, OrderCancelled] = field(default_factory=dict)


def _book_levels(
    resting: Mapping[str, _RestingOrder], market_id: str
) -> tuple[tuple[BookLevelDto, ...], tuple[BookLevelDto, ...]]:
    """Aggregate the resting orders of one market into its top price levels.

    This is the one derivation in this module that no single journal field
    carries: ``MarkToMarket`` publishes ``best_bid``, ``best_ask`` and the two
    total depths, but not the per level breakdown ``MarketTick.bids`` and
    ``.asks`` need. It is a regrouping of ``OrderPlaced.qty`` minus the
    ``TradeExecuted.qty`` that consumed it, with no matching, no collateral and
    no fee arithmetic, and
    ``test_api.py::test_book_levels_agree_with_mark_to_market`` pins the result
    against the journalled ``best_bid``, ``best_ask``, ``bid_depth_qty`` and
    ``ask_depth_qty`` of every mark of the reference match.

    Args:
        resting: Live resting orders, keyed by order id.
        market_id: The market to aggregate.

    Returns:
        ``(bids, asks)``, best first, at most :data:`~pxe.types.DEPTH_LEVELS`
        levels per side.
    """
    bids: dict[int, int] = {}
    asks: dict[int, int] = {}
    for order in resting.values():
        if order.market_id != market_id:
            continue
        book = bids if order.side == "buy" else asks
        book[order.price] = book.get(order.price, 0) + order.remaining_qty
    bid_levels = tuple(
        BookLevelDto(price=price, qty=bids[price]) for price in sorted(bids, reverse=True)[:DEPTH_LEVELS]
    )
    ask_levels = tuple(BookLevelDto(price=price, qty=asks[price]) for price in sorted(asks)[:DEPTH_LEVELS])
    return bid_levels, ask_levels


def _live_ranks(equity: Sequence[tuple[str, Sequence[int]]], ticks_total: int) -> dict[str, list[int]]:
    """Turn the per tick equity series into the per tick live leaderboard.

    ``MatchSeries.rank`` is the only series section 7.21 asks for that
    :class:`~pxe.metrics.projection.MatchProjection` does not carry. It is
    built here from ``equity_cents``, ranked descending with ties sharing the
    lowest rank and broken for display only by ascending ``agent_id``, which is
    the display rule finalisation step 18 states for the settled ranking.

    Args:
        equity: ``(agent_id, series)`` pairs, every series of length
            ``ticks_total``.
        ticks_total: The horizon.

    Returns:
        ``agent_id`` to a ``ticks_total`` long 1 based rank series.
    """
    out: dict[str, list[int]] = {agent_id: [] for agent_id, _series in equity}
    for index in range(ticks_total):
        ordered = sorted(equity, key=lambda pair: (-pair[1][index], pair[0]))
        rank = 0
        previous: int | None = None
        for position, (agent_id, series) in enumerate(ordered, start=1):
            value = series[index]
            if previous is None or value != previous:
                rank = position
                previous = value
            out[agent_id].append(rank)
    return out


def _decision_headline(
    *,
    tick: int,
    agent_id: str,
    source: str,
    orders: Sequence[Mapping[str, Any]],
    n_predictions: int,
    n_rejected: int,
    timed_out: bool,
) -> str:
    """Build the one line summary ``q`` searches (section 7.21, ``Decision.headline``).

    The field exists so that a text search has something stable to match when
    an agent supplied no rationale and no message, which is the normal case for
    a scripted seat. It names the tick, the seat, the source, the shape of the
    block and the markets touched, so a spectator typing ``M3`` finds every
    decision that touched ``M3``.

    Args:
        tick: The tick.
        agent_id: The seat.
        source: ``llm``, ``scripted`` or ``fallback``.
        orders: The journalled order intents.
        n_predictions: How many predictions the row carries.
        n_rejected: ``AgentActionReceived.n_rejected``.
        timed_out: Whether an ``AgentTimedOut`` fired for this seat this tick.

    Returns:
        The headline.
    """
    places = sum(1 for intent in orders if intent.get("op") == "place")
    cancels = sum(1 for intent in orders if intent.get("op") == "cancel")
    markets = sorted_ids([str(intent["market_id"]) for intent in orders if intent.get("market_id")])
    parts = [f"tick {tick}", agent_id, source]
    if timed_out:
        parts.append("timed out")
    parts.append(f"{places} place")
    parts.append(f"{cancels} cancel")
    parts.append(f"{n_predictions} predictions")
    if n_rejected:
        parts.append(f"{n_rejected} rejected")
    if markets:
        parts.append("markets " + ",".join(markets))
    return " | ".join(parts)


def _order_outcome(record: OrderRecord | None) -> Literal["filled", "partial", "resting", "rejected", "cancelled"]:
    """Read what became of an accepted order off its folded record.

    Args:
        record: The projection's fold of that order's whole life, or ``None``
            when the projection never saw it (which cannot happen for an
            ``OrderPlaced`` that is in the same journal).

    Returns:
        One of the five ``DecisionOrder.outcome`` values.
    """
    if record is None:
        return "resting"
    if record.filled_qty >= record.qty:
        return "filled"
    if record.filled_qty > 0:
        return "partial"
    if record.cancelled_tick is not None:
        return "cancelled"
    return "resting"


def _normalise(text: str) -> str:
    """Normalise a string for the ``q`` substring search.

    Section 7.21: case insensitive substring match after Unicode NFKC
    normalisation, no regex, no tokenisation, no ranking.

    Args:
        text: Raw text.

    Returns:
        The NFKC normalised, case folded form.
    """
    return unicodedata.normalize("NFKC", text).casefold()


# ---------------------------------------------------------------------------
# The per match cache entry
# ---------------------------------------------------------------------------
class _MatchView:
    """Every payload of one match, built once from its journal and projection.

    A view is what the LRU holds. Building it reads the journal, folds it into
    a :class:`~pxe.metrics.projection.MatchProjection` through the store, and
    pre-renders every ``TickState`` as bytes, so a warm ``GET .../ticks/{tick}``
    is a dictionary lookup and a byte copy and the WebSocket ``tick`` frame is
    the same bytes decoded (section 7.21, "one builder in the API").
    """

    def __init__(
        self,
        *,
        events: Sequence[Event],
        projection: MatchProjection,
        summary_row: Mapping[str, Any] | None,
        journal_digest: str,
    ) -> None:
        """Build the whole view.

        Args:
            events: The journal, ascending by ``seq``.
            projection: The folded projection, incidents included.
            summary_row: The ``match`` row of the store when the match was
                saved, which is the only source of ``tournament_id`` and
                ``held_out`` (the journal carries neither), or ``None``.
            journal_digest: The AC-P1 journal hash.
        """
        self.events: tuple[Event, ...] = tuple(events)
        self.projection = projection
        self.started = _first_match_started(self.events)
        self.ended = _last_match_ended(self.events)
        self.ticks_total = self.started.ticks_total
        self.match_id = self.started.match_id
        self.journal_hash = journal_digest
        self._row = summary_row
        self._resolved_at, self._cancelled_at = _closure_ticks(self.events)
        self.detail = self._build_detail()
        self.summary = MatchSummary(**{key: getattr(self.detail, key) for key in MatchSummary.model_fields})
        self._tick_json = self._build_ticks()
        self.series = self._build_series()
        self.decisions = self._build_decisions()

    # -- static -----------------------------------------------------------
    @property
    def first_tick(self) -> int:
        """The lowest reachable tick, always ``0`` (``MatchStarted``)."""
        return 0

    @property
    def last_tick(self) -> int:
        """The highest reachable tick, ``ticks_total + 1`` (finalisation)."""
        return self.ticks_total + 1

    def tick_bytes(self, tick: int) -> bytes:
        """Return the pre-rendered ``TickState`` of one tick.

        Args:
            tick: A tick in ``0..ticks_total + 1``.

        Returns:
            The JSON body, exactly the bytes the REST route and the WebSocket
            frame both use.

        Raises:
            HTTPException: ``404`` when the tick is outside the reachable range.
        """
        payload = self._tick_json.get(tick)
        if payload is None:
            raise api_error(
                404,
                "UNKNOWN_TICK",
                "tick outside the replayable range",
                match_id=self.match_id,
                tick=tick,
                first_tick=self.first_tick,
                last_tick=self.last_tick,
            )
        return payload

    def clamp_tick(self, tick: int) -> int:
        """Clamp a tick into ``0..ticks_total + 1``.

        Args:
            tick: Any integer.

        Returns:
            The clamped tick.
        """
        return max(self.first_tick, min(self.last_tick, tick))

    def highlights(self, kinds: Sequence[str]) -> list[Highlight]:
        """Return the annotated highlights, optionally filtered by kind.

        Args:
            kinds: Requested kinds, empty for all of them.

        Returns:
            The highlights, in projection order ``(tick, kind, market_id)``.
        """
        wanted = frozenset(kinds)
        return [
            Highlight(
                tick=row.tick,
                kind=row.kind,  # type: ignore[arg-type]
                agent_ids=list(row.agent_ids),
                market_id=row.market_id,
                magnitude_cents=row.magnitude_cents,
                label=row.label,
            )
            for row in self.projection.highlights
            if not wanted or row.kind in wanted
        ]

    def rankings(self) -> list[Ranking]:
        """Return the settled final ranking, ascending by rank, empty while unfinished."""
        return list(self.detail.rankings)

    # -- builders ---------------------------------------------------------
    def _harness_keys(self) -> dict[str, str]:
        """Map every seat to its harness key.

        ``MatchStarted.agents`` carries ``harness_id``, ``harness_version`` and
        ``config_hash`` and not the key itself, and section 2.2 fixes the key as
        ``<harness_id>@<version>+<config_hash[:8]>``.

        Returns:
            ``agent_id`` to harness key.
        """
        out: dict[str, str] = {}
        for row in self.started.agents:
            harness_id = str(row["harness_id"])
            version = str(row["harness_version"])
            digest = str(row["config_hash"])
            out[str(row["agent_id"])] = f"{harness_id}@{version}+{digest[:8]}"
        return out

    def _agent_kinds(self) -> dict[str, str]:
        """Decide whether each seat was an LLM or a scripted brain.

        ``MatchStarted.agents`` does not carry ``HarnessConfig.kind`` and the
        journal has no other field for it, so the decision is read off the
        actions the seat actually produced: a seat that ever returned an action
        with ``source == "llm"`` was behind a provider, everything else is
        scripted. ``AgentActionReceived.source`` is journalled verbatim, so this
        is a read and not an inference about the engine.

        Returns:
            ``agent_id`` to ``"llm"`` or ``"scripted"``.
        """
        kinds = {str(row["agent_id"]): "scripted" for row in self.started.agents}
        for event in self.events:
            if isinstance(event, AgentActionReceived) and event.source == "llm":
                kinds[event.agent_id] = "llm"
        return kinds

    def _build_detail(self) -> MatchDetail:
        """Assemble :class:`MatchDetail` from the journal and the store row."""
        row = self._row or {}
        config = dict(self.started.config)
        keys = self._harness_keys()
        kinds = self._agent_kinds()
        groups: dict[str, list[str]] = {}
        for spec in self.started.markets:
            group = str(spec.get("correlation_group", ""))
            if group:
                groups.setdefault(group, []).append(str(spec["market_id"]))
        outcomes = dict(self.projection.outcomes)
        markets = [
            MarketInfo(
                market_id=str(spec["market_id"]),
                question=str(spec["question"]),
                prior_price=int(spec["prior_price"]),
                resolution_tick=int(spec["resolution_tick"]),
                status=self._status_at(str(spec["market_id"]), self.last_tick),
                outcome=_outcome_literal(outcomes.get(str(spec["market_id"]))),
                correlated_with=list(
                    sorted_ids(
                        [
                            other
                            for other in groups.get(str(spec.get("correlation_group", "")), [])
                            if other != str(spec["market_id"])
                        ]
                        if str(spec.get("correlation_group", ""))
                        else []
                    )
                ),
            )
            for spec in self.started.markets
        ]
        agents = [
            AgentInfo(
                agent_id=str(spec["agent_id"]),
                harness_key=keys[str(spec["agent_id"])],
                kind=kinds[str(spec["agent_id"])],  # type: ignore[arg-type]
                display_name=f"{spec['agent_id']} {spec['harness_id']}",
                colour_index=_colour_index(str(spec["agent_id"]), bool(spec["ranked"])),
                info_profile=str(spec["info_profile_kind"]),  # type: ignore[arg-type]
                ranked=bool(spec["ranked"]),
            )
            for spec in self.started.agents
        ]
        rankings = [
            Ranking(
                rank=int(line["rank"]),
                agent_id=str(line["agent_id"]),
                harness_key=keys.get(str(line["agent_id"]), ""),
                pnl_cents=int(line["pnl_cents"]),
                final_cash_cents=int(line["final_cash_cents"]),
                pnl_pct_bps=int(line["pnl_pct_bps"]),
            )
            for line in (self.ended.rankings if self.ended is not None else ())
        ]
        winner = rankings[0].agent_id if rankings else None
        return MatchDetail(
            match_id=self.match_id,
            tournament_id=_optional_str(row.get("tournament_id")),
            template_id=self.started.scenario_template_id,
            template_version=self.started.scenario_template_version,
            seed=self.started.seed,
            ticks_total=self.ticks_total,
            n_markets=len(self.started.markets),
            n_agents=sum(1 for spec in self.started.agents if bool(spec["ranked"])),
            journal_hash=self.journal_hash,
            held_out=bool(row.get("held_out", False)),
            finished=self.ended is not None,
            winner_agent_id=winner,
            winner_harness_key=keys.get(winner or "", None) if winner else None,
            config=config,
            mm_config=dict(self.started.mm_config),
            markets=markets,
            agents=agents,
            rankings=rankings,
            mm_pnl_cents=self.projection.mm_pnl_cents,
            fees_collected_cents=self.projection.fees_collected_cents,
            event_count=len(self.events),
            liquidity_profile_name=str(config.get("liquidity_profile_name", "standard")),  # type: ignore[arg-type]
            talking_mode=bool(config.get("talking_mode", False)),
        )

    def _status_at(self, market_id: str, tick: int) -> MarketStatusLiteral:
        """Return the status of one market at the close of one tick."""
        resolved = self._resolved_at.get(market_id)
        cancelled = self._cancelled_at.get(market_id)
        if resolved is not None and resolved <= tick:
            return "resolved"
        if cancelled is not None and cancelled <= tick:
            return "cancelled"
        return "open"

    def _build_ticks(self) -> dict[int, bytes]:
        """Pre-render every reachable ``TickState`` as JSON bytes."""
        folds: dict[int, _TickFold] = {tick: _TickFold() for tick in range(0, self.last_tick + 1)}
        resting: dict[str, _RestingOrder] = {}
        for event in self.events:
            fold = folds.get(event.tick)
            if fold is None:
                continue
            if isinstance(event, TickStarted):
                fold.open_market_ids = tuple(event.open_market_ids)
            elif isinstance(event, OrderPlaced):
                resting[event.order_id] = _RestingOrder(event.market_id, event.side, event.price, event.qty)
            elif isinstance(event, TradeExecuted):
                _consume(resting, event.maker_order_id, event.qty)
                _consume(resting, event.taker_order_id, event.qty)
            elif isinstance(event, OrderCancelled):
                resting.pop(event.order_id, None)
            elif isinstance(event, MarkToMarket):
                fold.marks[event.market_id] = event
                fold.levels[event.market_id] = _book_levels(resting, event.market_id)
            elif isinstance(event, MMQuoted):
                fold.quotes[event.market_id] = event
            elif isinstance(event, PositionSnapshot):
                fold.snapshots.append(event)
            elif isinstance(event, NewsPublished):
                fold.news.append(event)
            elif isinstance(event, MarketResolved):
                fold.resolutions.append(event)
        return self._render_ticks(folds)

    def _render_ticks(self, folds: Mapping[int, _TickFold]) -> dict[int, bytes]:
        """Turn the per tick folds into rendered JSON bodies."""
        by_tick_signals = _group(self.projection.signals)
        by_tick_trades = _group(self.projection.trades)
        by_tick_predictions = _group(self.projection.predictions)
        by_tick_messages = _group(self.projection.messages)
        by_tick_highlights = _group(self.projection.highlights)
        refs = dict(self.projection.ref_price)
        sources: dict[str, str] = {}
        out: dict[int, bytes] = {}
        for tick in range(0, self.last_tick + 1):
            fold = folds[tick]
            for market_id, mark in fold.marks.items():
                sources[market_id] = mark.ref_source
            state = TickState(
                match_id=self.match_id,
                tick=tick,
                open_market_ids=list(self._open_ids(tick, fold)),
                markets=[self._market_tick(tick, spec, fold, refs, sources) for spec in self.started.markets],
                accounts=[_account_tick(row) for row in fold.snapshots],
                news=[_news_dto(row) for row in fold.news],
                signals=[
                    SignalDto(
                        signal_id=row.signal_id,
                        agent_id=row.agent_id,
                        market_id=row.market_id,
                        kind=row.kind,
                        value_milli=row.value_milli,
                        precision_ppm=row.precision_ppm,
                    )
                    for row in by_tick_signals.get(tick, ())
                ],
                trades=[
                    TradeDto(
                        trade_id=row.trade_id,
                        market_id=row.market_id,
                        price=row.price,
                        qty=row.qty,
                        maker_agent_id=row.maker_agent_id,
                        taker_agent_id=row.taker_agent_id,
                        taker_side=row.taker_side,
                    )
                    for row in by_tick_trades.get(tick, ())
                ],
                predictions=[
                    PredictionDto(
                        agent_id=row.agent_id,
                        market_id=row.market_id,
                        p_yes_ppm=row.p_yes_ppm,
                        carried=row.carried,
                    )
                    for row in by_tick_predictions.get(tick, ())
                ],
                messages=[
                    MessageDto(agent_id=row.agent_id, text=row.text, deliver_tick=row.deliver_tick)
                    for row in by_tick_messages.get(tick, ())
                ],
                resolutions=[
                    ResolutionDto(
                        market_id=row.market_id,
                        outcome=row.outcome,  # type: ignore[arg-type]
                        payout_cents=row.payout_cents,
                    )
                    for row in fold.resolutions
                ],
                highlights=[
                    Highlight(
                        tick=row.tick,
                        kind=row.kind,
                        agent_ids=list(row.agent_ids),
                        market_id=row.market_id,
                        magnitude_cents=row.magnitude_cents,
                        label=row.label,
                    )
                    for row in by_tick_highlights.get(tick, ())
                ],
            )
            out[tick] = state.model_dump_json().encode("utf-8")
        return out

    def _open_ids(self, tick: int, fold: _TickFold) -> tuple[str, ...]:
        """Return the markets tradable in P3 of one tick.

        ``TickStarted.open_market_ids`` is the journalled answer for a real
        tick. The two virtual ticks have no ``TickStarted``: at tick ``0``
        nothing has resolved yet, so every market is listed, and at
        ``ticks_total + 1`` there is no P3, so nothing is.
        """
        if fold.open_market_ids:
            return fold.open_market_ids
        if tick == 0:
            return tuple(str(spec["market_id"]) for spec in self.started.markets)
        return ()

    def _market_tick(
        self,
        tick: int,
        spec: Mapping[str, Any],
        fold: _TickFold,
        refs: Mapping[str, tuple[int, ...]],
        sources: Mapping[str, str],
    ) -> MarketTick:
        """Build one :class:`MarketTick`.

        A tradable market takes every number from its ``MarkToMarket``, which is
        the journalled close of that tick. A market already resolved or
        cancelled emits no mark, so its ``ref_price`` is read from
        ``MatchProjection.ref_price``, the series A15 pads forward (CONTRACTS
        section 9: "A15 owns the padding; nobody else re-derives it"), and its
        ``ref_source`` is the last one the journal published for it.
        """
        market_id = str(spec["market_id"])
        quote = fold.quotes.get(market_id)
        mark = fold.marks.get(market_id)
        bids, asks = fold.levels.get(market_id, ((), ()))
        if mark is not None:
            return MarketTick(
                market_id=market_id,
                status=self._status_at(market_id, tick),
                ref_price=mark.ref_price,
                ref_source=mark.ref_source,  # type: ignore[arg-type]
                mid_price=mark.mid_price,
                best_bid=mark.best_bid,
                best_ask=mark.best_ask,
                last_price=mark.last_price,
                bids=list(bids),
                asks=list(asks),
                bid_depth_qty=mark.bid_depth_qty,
                ask_depth_qty=mark.ask_depth_qty,
                tick_volume_qty=mark.tick_volume_qty,
                mm_bid=quote.bid_price if quote is not None else None,
                mm_ask=quote.ask_price if quote is not None else None,
                mm_widened=bool(quote.widened) if quote is not None else False,
            )
        series = refs.get(market_id, ())
        index = min(max(tick, 1), self.ticks_total) - 1
        ref_price = series[index] if series else int(spec["prior_price"])
        return MarketTick(
            market_id=market_id,
            status=self._status_at(market_id, tick),
            ref_price=ref_price if tick >= 1 else int(spec["prior_price"]),
            ref_source=sources.get(market_id, "prior") if tick >= 1 else "prior",  # type: ignore[arg-type]
            mid_price=None,
            best_bid=None,
            best_ask=None,
            last_price=None,
            bids=[],
            asks=[],
            bid_depth_qty=0,
            ask_depth_qty=0,
            tick_volume_qty=0,
            mm_bid=quote.bid_price if quote is not None else None,
            mm_ask=quote.ask_price if quote is not None else None,
            mm_widened=bool(quote.widened) if quote is not None else False,
        )

    def _build_series(self) -> MatchSeries:
        """Assemble the four per tick series, each of length ``ticks_total``."""
        ranks = _live_ranks(self.projection.equity_cents, self.ticks_total)
        return MatchSeries(
            match_id=self.match_id,
            ticks_total=self.ticks_total,
            equity_cents=[
                AgentSeries(agent_id=agent_id, values=list(values)) for agent_id, values in self.projection.equity_cents
            ],
            cash_cents=[
                AgentSeries(agent_id=agent_id, values=list(values)) for agent_id, values in self.projection.cash_cents
            ],
            ref_price=[
                MarketSeries(market_id=market_id, values=list(values))
                for market_id, values in self.projection.ref_price
            ],
            rank=[AgentSeries(agent_id=agent_id, values=ranks[agent_id]) for agent_id in self.projection.agent_ids],
        )

    def _build_decisions(self) -> tuple[Decision, ...]:
        """Assemble one decision row per ``(tick, agent)`` that produced an action."""
        blocks: dict[tuple[int, str], _AgentTickFold] = {}
        for event in self.events:
            key = _decision_key(event)
            if key is None:
                continue
            block = blocks.setdefault(key, _AgentTickFold())
            _absorb(block, event)
        by_order = {record.order_id: record for record in self.projection.orders}
        predictions: dict[tuple[int, str], list[DecisionPrediction]] = {}
        for row in self.projection.predictions:
            predictions.setdefault((row.tick, row.agent_id), []).append(
                DecisionPrediction(market_id=row.market_id, p_yes_ppm=row.p_yes_ppm, carried=row.carried)
            )
        trades: dict[tuple[int, str], list[str]] = {}
        for trade in self.projection.trades:
            for agent_id in (trade.maker_agent_id, trade.taker_agent_id):
                bucket = trades.setdefault((trade.tick, agent_id), [])
                if trade.trade_id not in bucket:
                    bucket.append(trade.trade_id)
        rows: list[Decision] = []
        for (tick, agent_id), block in sorted(blocks.items(), key=lambda item: (item[0][0], _seat_rank(item[0][1]))):
            received = block.received
            if received is None:
                continue
            rows.append(
                _decision_row(
                    tick=tick,
                    agent_id=agent_id,
                    received=received,
                    block=block,
                    by_order=by_order,
                    predictions=predictions.get((tick, agent_id), []),
                    trade_ids=trades.get((tick, agent_id), []),
                )
            )
        return tuple(rows)


# ---------------------------------------------------------------------------
# Journal readers used by the view
# ---------------------------------------------------------------------------
def _consume(resting: dict[str, _RestingOrder], order_id: str, qty: int) -> None:
    """Reduce one resting order by a filled quantity, dropping it when exhausted.

    Args:
        resting: Live resting orders, keyed by order id.
        order_id: The order that was filled.
        qty: Filled quantity.
    """
    order = resting.get(order_id)
    if order is None:
        return
    order.remaining_qty -= qty
    if order.remaining_qty <= 0:
        resting.pop(order_id, None)


def _first_match_started(events: Sequence[Event]) -> MatchStarted:
    """Return the ``MatchStarted`` of a journal.

    Args:
        events: The journal.

    Returns:
        The first event, which section 4.4 fixes as ``MatchStarted``.

    Raises:
        HTTPException: ``409`` when the journal carries none, that is when the
            artefact exists but is not a match yet.
    """
    for event in events:
        if isinstance(event, MatchStarted):
            return event
    raise api_error(409, "INCOMPLETE_ARTEFACT", "the journal carries no match_started event")


def _last_match_ended(events: Sequence[Event]) -> MatchEnded | None:
    """Return the ``MatchEnded`` of a journal, or ``None`` while it is unfinished."""
    for event in reversed(events):
        if isinstance(event, MatchEnded):
            return event
    return None


def _closure_ticks(events: Sequence[Event]) -> tuple[dict[str, int], dict[str, int]]:
    """Return the envelope tick at which each market resolved and each was cancelled."""
    resolved: dict[str, int] = {}
    cancelled: dict[str, int] = {}
    for event in events:
        if isinstance(event, MarketResolved):
            resolved.setdefault(event.market_id, event.tick)
        elif isinstance(event, MarketCancelled):
            cancelled.setdefault(event.market_id, event.tick)
    return resolved, cancelled


def _outcome_literal(value: object) -> OutcomeLiteral | None:
    """Coerce a resolved outcome to the wire literal, ``None`` while open or cancelled."""
    if value is None:
        return None
    text = str(value)
    return "yes" if text == "yes" else "no"


def _optional_str(value: object) -> str | None:
    """Return ``str(value)`` or ``None``."""
    return None if value is None else str(value)


def _colour_index(agent_id: str, ranked: bool) -> int:
    """Assign the UI colour slot of one seat.

    Section 7.25: the API assigns it from the seat number, ``A1`` gets ``0``.
    ``MM`` is neutral grey and is never given a colour, so an unranked seat gets
    :data:`NO_COLOUR_INDEX`.

    Args:
        agent_id: Seat id.
        ranked: Whether the seat competes.

    Returns:
        ``0..7`` for a ranked seat, ``-1`` otherwise.
    """
    if not ranked or not agent_id.startswith("A"):
        return NO_COLOUR_INDEX
    return (int(agent_id[1:]) - 1) % COLOUR_SLOTS


def _seat_rank(agent_id: str) -> tuple[int, str]:
    """Sort key putting ranked seats in canonical order and anything else last."""
    if agent_id.startswith("A") and agent_id[1:].isdigit():
        return (int(agent_id[1:]), agent_id)
    return (10**6, agent_id)


def _group(rows: Sequence[Any]) -> dict[int, list[Any]]:
    """Group projection rows by their ``tick`` field, preserving row order."""
    out: dict[int, list[Any]] = {}
    for row in rows:
        out.setdefault(int(row.tick), []).append(row)
    return out


def _account_tick(row: PositionSnapshot) -> AccountTick:
    """Turn one ``PositionSnapshot`` into an :class:`AccountTick`."""
    return AccountTick(
        account_id=row.account_id,
        cash_cents=row.cash_cents,
        reserved_cents=row.reserved_cents,
        free_cash_cents=row.free_cash_cents,
        equity_cents=row.equity_cents,
        frozen=row.frozen,
        resting_order_count=row.resting_order_count,
        positions=[
            PositionDto(
                market_id=str(position["market_id"]),
                qty=int(position["qty"]),
                cost_basis_cents=int(position["cost_basis_cents"]),
            )
            for position in row.positions
        ],
    )


def _news_dto(row: NewsPublished) -> NewsDto:
    """Turn one ``NewsPublished`` into a :class:`NewsDto`."""
    return NewsDto(
        news_id=row.news_id,
        market_ids=list(row.market_ids),
        headline=row.headline,
        body=row.body,
        impact=row.impact,  # type: ignore[arg-type]
        is_noise=row.is_noise,
        origin=row.origin,  # type: ignore[arg-type]
    )


def _decision_key(event: Event) -> tuple[int, str] | None:
    """Return the ``(tick, agent_id)`` a P2 or P3 event belongs to, or ``None``."""
    if isinstance(event, AgentActionReceived | AgentActionRejected | AgentTimedOut):
        return (event.tick, event.agent_id)
    if isinstance(event, OrderPlaced | OrderRejected | OrderCancelled):
        return (event.tick, event.agent_id)
    return None


def _absorb(block: _AgentTickFold, event: Event) -> None:
    """Fold one event into its ``(tick, agent)`` decision block."""
    if isinstance(event, AgentActionReceived):
        block.received = event
    elif isinstance(event, AgentTimedOut):
        block.timed_out = True
    elif isinstance(event, AgentActionRejected):
        block.rejections.append(event)
    elif isinstance(event, OrderRejected):
        block.order_rejects[event.item_index] = event
    elif isinstance(event, OrderPlaced):
        block.placed.append(event)
    elif isinstance(event, OrderCancelled):
        block.cancelled[event.order_id] = event


def _decision_row(
    *,
    tick: int,
    agent_id: str,
    received: AgentActionReceived,
    block: _AgentTickFold,
    by_order: Mapping[str, OrderRecord],
    predictions: Sequence[DecisionPrediction],
    trade_ids: Sequence[str],
) -> Decision:
    """Assemble one decision row.

    The intent to event join uses ``OrderRejected.item_index``, which P3 step 11
    fills with the index of the intent inside ``AgentActionReceived.orders``
    (``enumerate(action.orders)`` in ``MatchRunner._apply_orders``). Accepted
    ``place`` intents therefore consume the ``OrderPlaced`` events of the block
    in submission order, and a ``cancel`` intent is matched on its own
    ``order_id``.
    """
    placed = list(block.placed)
    orders: list[DecisionOrder] = []
    for index, intent in enumerate(received.orders):
        rejected = block.order_rejects.get(index)
        order_id = _optional_str(intent.get("order_id"))
        outcome: Literal["filled", "partial", "resting", "rejected", "cancelled"] = "rejected"
        reason: str | None = None
        if rejected is not None:
            reason = rejected.reason
        elif intent.get("op") == "place":
            event = placed.pop(0) if placed else None
            if event is not None:
                order_id = event.order_id
                outcome = _order_outcome(by_order.get(event.order_id))
            else:
                outcome = "resting"
        elif order_id is not None and order_id in block.cancelled:
            outcome = "cancelled"
        orders.append(
            DecisionOrder(
                op=str(intent["op"]),  # type: ignore[arg-type]
                market_id=_optional_str(intent.get("market_id")),
                side=_optional_str(intent.get("side")),  # type: ignore[arg-type]
                type=_optional_str(intent.get("type")),  # type: ignore[arg-type]
                price=None if intent.get("price") is None else int(intent["price"]),
                qty=None if intent.get("qty") is None else int(intent["qty"]),
                order_id=order_id,
                outcome=outcome,
                reject_reason=reason,
            )
        )
    return Decision(
        tick=tick,
        agent_id=agent_id,
        source=received.source,  # type: ignore[arg-type]
        predictions=list(predictions),
        orders=orders,
        message_public=received.message_public,
        rationale=received.rationale,
        headline=_decision_headline(
            tick=tick,
            agent_id=agent_id,
            source=received.source,
            orders=received.orders,
            n_predictions=len(predictions),
            n_rejected=received.n_rejected,
            timed_out=block.timed_out,
        ),
        timed_out=block.timed_out,
        n_rejected=received.n_rejected,
        trade_ids=list(trade_ids),
    )


# ---------------------------------------------------------------------------
# The service
# ---------------------------------------------------------------------------
class ReplayService:
    """The read only data layer of the API: one store, one runs directory, one LRU.

    Every route and the WebSocket go through this object, so the caching of a
    match projection has exactly one home (section 7.21, "``create_app`` loads a
    match projection once and caches it per ``match_id`` in an LRU of 8
    entries"). It is not thread safe, for the same reason
    :class:`~pxe.store.db.Store` is not: a replay server is one process serving
    reads.
    """

    def __init__(self, *, runs_dir: Path, store: Store, cache_size: int = MATCH_CACHE_SIZE) -> None:
        """Bind the service to its artefacts.

        Args:
            runs_dir: The runs root, ``runs/`` normally.
            store: The projection database plus artefact directory.
            cache_size: How many match views stay resident.
        """
        self._runs_dir = Path(runs_dir)
        self._store = store
        self._cache_size = max(1, cache_size)
        self._cache: OrderedDict[str, _MatchView] = OrderedDict()

    @property
    def runs_dir(self) -> Path:
        """The runs root this service reads."""
        return self._runs_dir

    @property
    def store(self) -> Store:
        """The store this service reads."""
        return self._store

    def health(self) -> Health:
        """Return the liveness payload with the four pinned versions."""
        return Health(
            status="ok",
            engine_version=ENGINE_VERSION,
            obs_version=OBS_VERSION,
            action_version=ACTION_VERSION,
            api_version=API_VERSION,
        )

    # -- match discovery --------------------------------------------------
    def match_ids(self, *, tournament_id: str | None = None) -> tuple[str, ...]:
        """List every match this service can serve, ascending by ``match_id``.

        The store is the contracted source. A standalone ``pxe match run``
        writes artefacts without saving a row, so the on disk directories are
        unioned in when no tournament filter is given; a filtered listing stays
        store only, because an on disk match belongs to no tournament.

        Args:
            tournament_id: Restrict to the matches of one tournament.

        Returns:
            The match ids.
        """
        rows = self._store.list_matches(tournament_id=tournament_id, limit=10_000, offset=0)
        ids = {str(row["match_id"]) for row in rows}
        if tournament_id is None:
            ids |= {
                entry.name
                for entry in sorted(self._runs_dir.glob("*"))
                if entry.is_dir() and (entry / "journal.jsonl").exists()
            }
        return tuple(sorted(ids))

    def list_matches(self, *, tournament_id: str | None, limit: int, offset: int) -> Page[MatchSummary]:
        """Return one page of match summaries.

        Args:
            tournament_id: Restrict to one tournament, or ``None``.
            limit: Page size.
            offset: Page offset.

        Returns:
            The page, ``total`` counting the whole collection.
        """
        ids = self.match_ids(tournament_id=tournament_id)
        window = ids[offset : offset + limit]
        return Page[MatchSummary](
            items=[self.view(match_id).summary for match_id in window],
            total=len(ids),
            limit=limit,
            offset=offset,
        )

    def view(self, match_id: str) -> _MatchView:
        """Return the cached view of one match, building it on a miss.

        Args:
            match_id: The match.

        Returns:
            The view.

        Raises:
            HTTPException: ``404`` when no journal exists for that id, ``409``
                when the journal exists but carries no ``MatchStarted``.
        """
        cached = self._cache.get(match_id)
        if cached is not None:
            self._cache.move_to_end(match_id)
            return cached
        built = self._build_view(match_id)
        self._cache[match_id] = built
        self._cache.move_to_end(match_id)
        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)
        return built

    def _build_view(self, match_id: str) -> _MatchView:
        """Read, project and pre-render one match."""
        path = artefact_paths(self._runs_dir, match_id)["journal"]
        if not path.exists():
            raise api_error(404, "UNKNOWN_MATCH", "no journal for that match id", match_id=match_id)
        try:
            events = read_journal(path)
            incidents = self._store.load_incidents(match_id=match_id)
            projected = projection_module.project(events, incidents=incidents)
        except PxeError as exc:
            raise api_error(409, exc.code, str(exc), match_id=match_id) from exc
        row: Mapping[str, Any] | None = None
        for candidate in self._store.list_matches(limit=10_000, offset=0):
            if str(candidate["match_id"]) == match_id:
                row = candidate
                break
        return _MatchView(
            events=events,
            projection=projected,
            summary_row=row,
            journal_digest=journal_hash(events),
        )

    # -- match payloads ---------------------------------------------------
    def events_page(
        self,
        match_id: str,
        *,
        from_tick: int | None,
        to_tick: int | None,
        types: str | None,
        limit: int,
        offset: int,
    ) -> Page[dict[str, Any]]:
        """Return one page of journal lines, verbatim.

        Args:
            match_id: The match.
            from_tick: Inclusive lower bound, clamped, ``0`` by default.
            to_tick: Inclusive upper bound, clamped, ``ticks_total + 1`` by
                default.
            types: Comma separated event type names, or ``None`` for all.
            limit: Page size.
            offset: Page offset.

        Returns:
            The page of ``JournalEvent`` mappings.
        """
        view = self.view(match_id)
        low = view.clamp_tick(0 if from_tick is None else from_tick)
        high = view.clamp_tick(view.last_tick if to_tick is None else to_tick)
        wanted = frozenset(name.strip() for name in types.split(",") if name.strip()) if types else frozenset()
        selected = [
            event
            for event in view.events
            if low <= event.tick <= high and (not wanted or str(event.TYPE.value) in wanted)
        ]
        window = selected[offset : offset + limit]
        return Page[dict[str, Any]](
            items=[dict(event.to_dict()) for event in window],
            total=len(selected),
            limit=limit,
            offset=offset,
        )

    def series(self, match_id: str, *, agent_ids: Sequence[str], market_ids: Sequence[str]) -> MatchSeries:
        """Return the four per tick series, optionally filtered.

        Args:
            match_id: The match.
            agent_ids: Keep only these seats, empty for all of them.
            market_ids: Keep only these markets, empty for all of them.

        Returns:
            The series payload.
        """
        full = self.view(match_id).series
        if not agent_ids and not market_ids:
            return full
        agents = frozenset(agent_ids)
        markets = frozenset(market_ids)
        return MatchSeries(
            match_id=full.match_id,
            ticks_total=full.ticks_total,
            equity_cents=[row for row in full.equity_cents if not agents or row.agent_id in agents],
            cash_cents=[row for row in full.cash_cents if not agents or row.agent_id in agents],
            ref_price=[row for row in full.ref_price if not markets or row.market_id in markets],
            rank=[row for row in full.rank if not agents or row.agent_id in agents],
        )

    def metrics(self, match_id: str) -> MatchMetricsPayload:
        """Return ``metrics.json`` plus the reliability curves.

        ``runs/<match_id>/metrics.json`` is the contracted source
        (:func:`pxe.metrics.aggregate.read_metrics` through
        :meth:`~pxe.store.db.Store.load_metrics`). A finished match whose file
        was never written falls back to
        :func:`pxe.metrics.aggregate.compute_all` over the cached projection,
        which is the same A15 code path; an unfinished match is a ``409``.

        Args:
            match_id: The match.

        Returns:
            The metrics payload.

        Raises:
            HTTPException: ``409`` when neither source can answer.
        """
        view = self.view(match_id)
        metrics = self._load_metrics(view)
        curves = {row.agent_id: reliability_curve(view.projection, row.agent_id) for row in metrics.calibration}
        return MatchMetricsPayload(
            match_id=metrics.match_id,
            performance=[
                PerformanceRow(
                    agent_id=row.agent_id,
                    pnl_cents=row.pnl_cents,
                    pnl_bps=row.pnl_bps,
                    sharpe_milli=row.sharpe_milli,
                    max_drawdown_cents=row.max_drawdown_cents,
                    max_drawdown_bps=row.max_drawdown_bps,
                    volume_qty=row.volume_qty,
                    trade_count=row.trade_count,
                    maker_trade_count=row.maker_trade_count,
                    fees_paid_cents=row.fees_paid_cents,
                )
                for row in metrics.performance
            ],
            calibration=[
                CalibrationRow(
                    agent_id=row.agent_id,
                    brier_ppm=row.brier_ppm,
                    n_terms=row.n_terms,
                    n_carried=row.n_carried,
                    reliability=[
                        ReliabilityBin(bin_upper_ppm=upper, n=count, observed_yes_ppm=observed)
                        for upper, count, observed in curves.get(row.agent_id, ())
                    ],
                )
                for row in metrics.calibration
            ],
            descriptors=[
                DescriptorRow(
                    agent_id=row.agent_id,
                    maker_ratio_ppm=row.maker_ratio_ppm,
                    reaction_latency_milli=row.reaction_latency_milli,
                    holding_horizon_milli=row.holding_horizon_milli,
                    herfindahl_ppm=row.herfindahl_ppm,
                    leverage_ppm=row.leverage_ppm,
                    message_intensity_ppm=row.message_intensity_ppm,
                )
                for row in metrics.descriptors
            ],
            mm_pnl_cents=metrics.mm_pnl_cents,
            fees_collected_cents=metrics.fees_collected_cents,
        )

    def _load_metrics(self, view: _MatchView) -> MatchMetrics:
        """Read ``metrics.json`` or, for a finished match, recompute it through A15."""
        try:
            return self._store.load_metrics(view.match_id)
        except StoreError as exc:
            if view.ended is None:
                raise api_error(
                    409,
                    "INCOMPLETE_ARTEFACT",
                    "the match has no metrics.json and is not finished",
                    match_id=view.match_id,
                ) from exc
            return compute_all(view.projection)

    def incidents(self, match_id: str) -> list[Incident]:
        """Return the integrity incidents of one match."""
        view = self.view(match_id)
        return [_incident_dto(row, view.match_id) for row in self._store.load_incidents(match_id=view.match_id)]

    def decisions(
        self,
        match_id: str,
        *,
        agent_id: str | None,
        from_tick: int | None,
        to_tick: int | None,
        q: str | None,
        limit: int,
        offset: int,
    ) -> Page[Decision]:
        """Return one page of decision rows, filtered and searched.

        Args:
            match_id: The match.
            agent_id: Keep only this seat, or ``None``.
            from_tick: Inclusive lower bound, ``1`` by default.
            to_tick: Inclusive upper bound, ``ticks_total`` by default.
            q: Case insensitive substring, matched over the concatenation of
                ``headline``, ``rationale`` and ``message_public`` after NFKC
                normalisation. Not a regex and never ranked.
            limit: Page size.
            offset: Page offset.

        Returns:
            The page, rows in ``(tick, agent_id)`` order.

        Raises:
            HTTPException: ``400`` when ``q`` is longer than
                :data:`MAX_QUERY_CHARS`.
        """
        if q is not None and len(q) > MAX_QUERY_CHARS:
            raise api_error(
                400,
                "INVALID_QUERY",
                f"q is longer than {MAX_QUERY_CHARS} characters",
                length=len(q),
                max_chars=MAX_QUERY_CHARS,
            )
        view = self.view(match_id)
        low = view.clamp_tick(1 if from_tick is None else from_tick)
        high = view.clamp_tick(view.ticks_total if to_tick is None else to_tick)
        needle = _normalise(q) if q else ""
        rows = [
            row
            for row in view.decisions
            if low <= row.tick <= high
            and (agent_id is None or row.agent_id == agent_id)
            and (not needle or needle in _normalise(_haystack(row)))
        ]
        window = rows[offset : offset + limit]
        return Page[Decision](items=list(window), total=len(rows), limit=limit, offset=offset)

    # -- tournament payloads ----------------------------------------------
    def list_tournaments(self, *, limit: int, offset: int) -> Page[TournamentSummary]:
        """Return one page of tournament summaries."""
        rows = self._store.list_tournaments(limit=10_000, offset=0)
        window = rows[offset : offset + limit]
        return Page[TournamentSummary](
            items=[_tournament_summary(row) for row in window],
            total=len(rows),
            limit=limit,
            offset=offset,
        )

    def tournament(self, tournament_id: str) -> TournamentDetail:
        """Assemble the whole tournament view payload.

        Every field comes from a :class:`~pxe.store.db.Store` reader:
        ``leaderboard`` from ``load_ratings``, ``progression`` from
        ``load_rating_series``, ``elites`` from ``load_elites``, ``costs_usd``
        from ``load_costs_usd``, ``incidents`` from ``load_incidents`` and the
        cost of liquidity from the ``match`` rows of the tournament. The two
        derived fields are documented in ``docs/REPLAY_API.md``:
        ``ci_low``/``ci_high`` is the conventional ``mu`` plus or minus three
        sigma display interval, and ``profile_balance`` is
        :func:`pxe.tournament.latin_square.verify_balance` over the task
        assignments the store still holds.

        Args:
            tournament_id: The tournament.

        Returns:
            The payload.

        Raises:
            HTTPException: ``404`` when the tournament is unknown.
        """
        summary = self._tournament_row(tournament_id)
        matches = self._store.list_matches(tournament_id=tournament_id, limit=10_000, offset=0)
        ratings = self._store.load_ratings(tournament_id)
        leaderboard = [
            LeaderboardRow(
                rank=index,
                harness_key=record.harness_key,
                mu=record.mu,
                sigma=record.sigma,
                matches=record.matches,
                ci_low=record.mu - CI_SIGMA_MULTIPLIER * record.sigma,
                ci_high=record.mu + CI_SIGMA_MULTIPLIER * record.sigma,
            )
            for index, record in enumerate(ratings, start=1)
        ]
        incidents = [
            _incident_dto(row, _incident_match_id(row, matches))
            for row in self._store.load_incidents(tournament_id=tournament_id)
        ]
        return TournamentDetail(
            **summary.model_dump(),
            leaderboard=leaderboard,
            progression=self._progression(ratings),
            elites=self._elites(tournament_id),
            costs_usd=[
                CostRow(harness_key=key, cost_usd=cost) for key, cost in self._store.load_costs_usd(tournament_id)
            ],
            incidents=incidents,
            liquidity_cost_cents=_liquidity_cost(matches),
            profile_balance=self._profile_balance(tournament_id),
            kpis=self._kpis(tournament_id, matches=matches, ratings=ratings, incidents=incidents),
        )

    def _tournament_row(self, tournament_id: str) -> TournamentSummary:
        """Find one tournament summary by id."""
        for row in self._store.list_tournaments(limit=10_000, offset=0):
            if str(row["tournament_id"]) == tournament_id:
                return _tournament_summary(row)
        raise api_error(404, "UNKNOWN_TOURNAMENT", "no such tournament", tournament_id=tournament_id)

    def _progression(self, ratings: Sequence[Any]) -> list[ProgressionRow]:
        """Build the per version progression curves of every harness id in the leaderboard."""
        harness_ids: list[str] = []
        for record in ratings:
            harness_id = str(record.harness_key).split("@", 1)[0]
            if harness_id not in harness_ids:
                harness_ids.append(harness_id)
        rows: list[ProgressionRow] = []
        for harness_id in sorted(harness_ids):
            points = self._store.load_rating_series(harness_id)
            rows.append(
                ProgressionRow(
                    harness_id=harness_id,
                    points=[
                        ProgressionPoint(
                            harness_key=key,
                            version=key.split("@", 1)[1].split("+", 1)[0] if "@" in key else "",
                            mu=mu,
                            sigma=sigma,
                            matches=matches,
                        )
                        for key, mu, sigma, matches in points
                    ],
                )
            )
        return rows

    def _elites(self, tournament_id: str) -> Elites:
        """Rebuild the MAP-Elites grid shape from its stored cells.

        ``save_elites`` persists one row per occupied cell and no grid header,
        so the header comes from the normative default grid of section 7.19,
        :data:`~pxe.tournament.elites.DEFAULT_ELITE_AXES` and
        :data:`~pxe.tournament.elites.DEFAULT_ELITE_BINS`, which is the grid
        ``TournamentOrchestrator`` builds. Reading ``bins`` off the occupied
        cells instead would report the observed extent and not the grid, so an
        archive whose top bin happens to be empty would be drawn one column
        short. A grid of another arity (an archive built by hand, PRD section 8
        allows two axes) falls back to the leading descriptor names and to the
        observed extent, which is the best a header-less row set supports.
        """
        cells = self._store.load_elites(tournament_id)
        if not cells:
            return Elites(axes=[], bins=[], cells=[])
        arity = len(cells[0].coords)
        if arity == len(DEFAULT_ELITE_AXES):
            axes, bins = list(DEFAULT_ELITE_AXES), list(DEFAULT_ELITE_BINS)
        else:
            axes = list(DESCRIPTOR_NAMES[:arity])
            bins = [max(int(cell.coords[axis]) for cell in cells) + 1 for axis in range(arity)]
        return Elites(
            axes=axes,
            bins=bins,
            cells=[
                EliteCellDto(
                    coords=list(cell.coords),
                    harness_key=cell.harness_key,
                    mu=cell.mu,
                    descriptors=list(cell.descriptors),
                )
                for cell in cells
            ],
        )

    def _profile_balance(self, tournament_id: str) -> ProfileBalance:
        """Measure the FR-5.3.2 residual over the task assignments the store holds."""
        tasks = self._store.pending_tasks(tournament_id)
        assignments = [list(task.profile_assignment) for task in tasks if task.profile_assignment]
        report = verify_balance(assignments)
        return ProfileBalance(
            exact=report.exact,
            max_deviation=report.max_deviation,
            seeds=report.seeds,
            seats=report.seats,
        )

    def _kpis(
        self,
        tournament_id: str,
        *,
        matches: Sequence[Mapping[str, Any]],
        ratings: Sequence[Any],
        incidents: Sequence[Incident],
    ) -> list[Kpi]:
        """Build the seven PRD section 15 KPIs from store readers.

        ``heldout_gain_mu_milli`` is reported as ``0``: its supplier is
        :mod:`pxe.evolve` through the store (section 7.24) and no store reader
        exposes it, which is recorded as a contract gap in
        ``docs/REPLAY_API.md``. "Engagement replay" is deliberately absent
        (CONTRACTS decision 34).
        """
        costs = self._store.load_costs_usd(tournament_id)
        total_usd = sum(cost for _key, cost in costs)
        n_matches = max(1, len(matches))
        technical = {row.match_id for row in incidents if row.kind == str(IncidentKind.TECHNICAL)}
        clean = sum(1 for row in matches if str(row["match_id"]) not in technical)
        sigmas = sorted(record.sigma for record in ratings if int(record.matches) >= SIGMA_SHRINK_MIN_MATCHES)
        median_sigma = sigmas[len(sigmas) // 2] if sigmas else 0.0
        mm_pnl = [int(row["mm_pnl_cents"]) for row in matches]
        return [
            Kpi(
                name="cost_per_match_usd_milli",
                value_ppm=round_half_up(total_usd * 1000.0 / n_matches),
                unit="milli_usd",
            ),
            Kpi(name="cost_per_tournament_usd_milli", value_ppm=round_half_up(total_usd * 1000.0), unit="milli_usd"),
            Kpi(name="matches_per_night", value_ppm=len(matches), unit="count"),
            Kpi(name="clean_completion_ppm", value_ppm=clean * _PPM // n_matches, unit="ppm"),
            Kpi(
                name="sigma_shrink_ppm",
                value_ppm=round_half_up(median_sigma / INITIAL_SIGMA * _PPM) if median_sigma else 0,
                unit="ppm",
            ),
            Kpi(name="heldout_gain_mu_milli", value_ppm=0, unit="milli"),
            Kpi(
                name="liquidity_cost_cents_per_match",
                value_ppm=bps_ratio(sum(mm_pnl), n_matches * 10_000) if mm_pnl else 0,
                unit="cents",
            ),
        ]


def _haystack(row: Decision) -> str:
    """Concatenate the three searched fields of a decision row."""
    return " ".join(part for part in (row.headline, row.rationale or "", row.message_public or "") if part)


def _incident_dto(row: IncidentRecord, match_id: str) -> Incident:
    """Turn one :class:`~pxe.types.Incident` into its wire form."""
    return Incident(
        incident_id=row.incident_id,
        kind=str(row.kind),
        severity=row.severity,
        match_id=match_id,
        tick=row.tick,
        agent_ids=list(row.agent_ids),
        market_ids=list(row.market_ids),
        score_ppm=row.score_ppm,
        detector_version=row.detector_version,
        detail={str(key): value for key, value in row.detail},
    )


def _incident_match_id(row: IncidentRecord, matches: Sequence[Mapping[str, Any]]) -> str:
    """Return the match a tournament wide incident belongs to.

    ``Store.load_incidents(tournament_id=...)`` stamps ``Incident.match_id``
    from the row it read, so the answer is exact. The single match fallback is
    kept for an alert built by hand (a test, or a detector run that never went
    through the store), where the tournament has exactly one candidate.
    """
    if row.match_id:
        return row.match_id
    return str(matches[0]["match_id"]) if len(matches) == 1 else ""


def _tournament_summary(row: Mapping[str, Any]) -> TournamentSummary:
    """Turn one ``list_tournaments`` row into a :class:`TournamentSummary`."""
    return TournamentSummary(
        tournament_id=str(row["tournament_id"]),
        format=str(row["format"]),
        n_matches=int(row.get("n_matches", 0)),
        n_harnesses=int(row["n_harnesses"]),
        seeds=[int(value) for value in row.get("seeds", ())],
        total_cost_usd=float(row.get("total_cost_usd", 0.0)),
        finished=bool(row.get("finished", False)),
    )


def _liquidity_cost(matches: Sequence[Mapping[str, Any]]) -> list[LiquidityCostRow]:
    """Sum the market maker PnL of a tournament's matches, per liquidity profile."""
    totals: dict[str, int] = {}
    for row in matches:
        profile = str(row["liquidity_profile_name"])
        totals[profile] = totals.get(profile, 0) + int(row["mm_pnl_cents"])
    return [LiquidityCostRow(profile=profile, mm_pnl_cents=totals[profile]) for profile in sorted(totals)]


# ---------------------------------------------------------------------------
# The router
# ---------------------------------------------------------------------------
def build_router(service: ReplayService) -> APIRouter:
    """Build the ``/api`` router of section 7.21.

    Every route is a ``GET``. Hot payloads are returned as a pre-rendered
    :class:`~fastapi.Response` so that the bytes a REST client sees and the
    bytes a WebSocket client sees are the same object; ``response_model`` still
    documents the shape, which is what ``pxe api openapi`` renders into
    ``docs/REPLAY_API.md``.

    Args:
        service: The data layer.

    Returns:
        The router, to be mounted under ``/api``.
    """
    router = APIRouter(prefix="/api", tags=["replay"])

    @router.get("/health", response_model=Health, summary="Liveness and pinned versions")
    def get_health() -> Health:
        """Return the API version plus the three engine versions a client pins."""
        return service.health()

    @router.get("/matches", response_model=Page[MatchSummary], summary="List matches")
    def get_matches(
        tournament_id: Annotated[str | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=500)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> Page[MatchSummary]:
        """List the matches this server can replay, ascending by ``match_id``."""
        return service.list_matches(tournament_id=tournament_id, limit=limit, offset=offset)

    @router.get("/matches/{match_id}", response_model=MatchDetail, summary="One match")
    def get_match(match_id: str) -> MatchDetail:
        """Return everything static about one match plus its settled ranking."""
        return service.view(match_id).detail

    @router.get("/matches/{match_id}/events", response_model=Page[dict[str, Any]], summary="Journal lines")
    def get_events(
        match_id: str,
        *,
        from_tick: Annotated[int | None, Query()] = None,
        to_tick: Annotated[int | None, Query()] = None,
        types: Annotated[str | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=20_000)] = 5000,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> Page[dict[str, Any]]:
        """Return one page of journal lines, verbatim, filtered by tick and type."""
        return service.events_page(
            match_id, from_tick=from_tick, to_tick=to_tick, types=types, limit=limit, offset=offset
        )

    @router.get("/matches/{match_id}/ticks/{tick}", response_model=TickState, summary="The world at one tick")
    def get_tick(match_id: str, tick: int) -> Response:
        """Return the whole ``TickState`` of one tick, the same bytes the socket sends."""
        return Response(content=service.view(match_id).tick_bytes(tick), media_type="application/json")

    @router.get("/matches/{match_id}/series", response_model=MatchSeries, summary="Per tick series")
    def get_series(
        match_id: str,
        *,
        agent_id: Annotated[list[str] | None, Query()] = None,
        market_id: Annotated[list[str] | None, Query()] = None,
    ) -> MatchSeries:
        """Return the four per tick series, each of length ``ticks_total``."""
        return service.series(match_id, agent_ids=agent_id or [], market_ids=market_id or [])

    @router.get("/matches/{match_id}/metrics", response_model=MatchMetricsPayload, summary="Match metrics")
    def get_metrics(match_id: str) -> MatchMetricsPayload:
        """Return ``metrics.json`` plus one reliability curve per agent."""
        return service.metrics(match_id)

    @router.get("/matches/{match_id}/incidents", response_model=IncidentsEnvelope, summary="Integrity incidents")
    def get_incidents(match_id: str) -> IncidentsEnvelope:
        """Return the offline detector output of one match."""
        return IncidentsEnvelope(incidents=service.incidents(match_id))

    @router.get("/matches/{match_id}/highlights", response_model=HighlightsEnvelope, summary="Annotated highlights")
    def get_highlights(match_id: str, kind: Annotated[list[str] | None, Query()] = None) -> HighlightsEnvelope:
        """Return the annotated marking events, optionally filtered by kind."""
        return HighlightsEnvelope(highlights=service.view(match_id).highlights(kind or []))

    @router.get("/matches/{match_id}/decisions", response_model=Page[Decision], summary="Decision journal")
    def get_decisions(
        match_id: str,
        *,
        agent_id: Annotated[str | None, Query()] = None,
        from_tick: Annotated[int | None, Query()] = None,
        to_tick: Annotated[int | None, Query()] = None,
        q: Annotated[str | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=5000)] = 500,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> Page[Decision]:
        """Return one page of ``(tick, agent)`` decision rows, searched by ``q``."""
        return service.decisions(
            match_id, agent_id=agent_id, from_tick=from_tick, to_tick=to_tick, q=q, limit=limit, offset=offset
        )

    @router.get("/tournaments", response_model=Page[TournamentSummary], summary="List tournaments")
    def get_tournaments(
        limit: Annotated[int, Query(ge=1, le=500)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> Page[TournamentSummary]:
        """List the saved tournaments, ascending by ``tournament_id``."""
        return service.list_tournaments(limit=limit, offset=offset)

    @router.get("/tournaments/{tournament_id}", response_model=TournamentDetail, summary="One tournament")
    def get_tournament(tournament_id: str) -> TournamentDetail:
        """Return the leaderboard, the grid, the curves, the alerts and the KPIs."""
        return service.tournament(tournament_id)

    return router


def sample_payloads(service: ReplayService, *, match_id: str, tournament_id: str | None = None) -> dict[str, Any]:
    """Build one sample of every payload of section 7.21, from real data.

    This is what ``pxe api openapi --samples`` writes into
    ``web/tests/fixtures/`` (section 7.25). The samples are produced by the
    real builders against a real recorded match, never written by hand: a hand
    written fixture lets A24 build its whole application against a fiction.

    Args:
        service: The data layer, pointed at a runs directory that holds the
            match.
        match_id: The recorded match to sample.
        tournament_id: A recorded tournament to sample, or ``None`` to skip the
            two tournament payloads.

    Returns:
        Fixture name to payload, JSON ready. Keys are the file stems
        ``web/tests/fixtures/<name>.json``.
    """
    view = service.view(match_id)
    out: dict[str, Any] = {
        "health": service.health().model_dump(),
        "matches_page": service.list_matches(tournament_id=None, limit=50, offset=0).model_dump(),
        "match_detail": view.detail.model_dump(),
        "events_page": service.events_page(
            match_id, from_tick=0, to_tick=2, types=None, limit=50, offset=0
        ).model_dump(),
        "tick_state": json.loads(view.tick_bytes(min(view.ticks_total, 12)).decode("utf-8")),
        "tick_state_zero": json.loads(view.tick_bytes(0).decode("utf-8")),
        "tick_state_final": json.loads(view.tick_bytes(view.last_tick).decode("utf-8")),
        "match_series": service.series(match_id, agent_ids=(), market_ids=()).model_dump(),
        "match_metrics": service.metrics(match_id).model_dump(),
        "incidents": {"incidents": [row.model_dump() for row in service.incidents(match_id)]},
        "highlights": {"highlights": [row.model_dump() for row in view.highlights([])]},
        "decisions_page": service.decisions(
            match_id, agent_id=None, from_tick=None, to_tick=None, q=None, limit=50, offset=0
        ).model_dump(),
        "ws_frames": _ws_frame_samples(view),
    }
    out["tournaments_page"] = service.list_tournaments(limit=50, offset=0).model_dump()
    if tournament_id is not None:
        out["tournament_detail"] = service.tournament(tournament_id).model_dump()
    return out


def _ws_frame_samples(view: _MatchView) -> dict[str, Any]:
    """Build one sample of every WebSocket frame type, for ``web/src/api/socket.ts``."""
    tick = min(view.ticks_total, 12)
    state = json.loads(view.tick_bytes(tick).decode("utf-8"))
    highlights = view.highlights([])
    return {
        "hello": {
            "type": "hello",
            "match_id": view.match_id,
            "ticks_total": view.ticks_total,
            "speed": 1,
            "from_tick": 1,
            "api_version": API_VERSION,
            "engine_version": ENGINE_VERSION,
        },
        "snapshot": {"type": "snapshot", "tick": tick, "state": state},
        "tick": {"type": "tick", "tick": tick, "state": state},
        "highlight": {"type": "highlight", "highlight": highlights[0].model_dump() if highlights else None},
        "ended": {
            "type": "ended",
            "final_tick": view.ended.final_tick if view.ended is not None else view.ticks_total,
            "rankings": [row.model_dump() for row in view.rankings()],
            "mm_pnl_cents": view.projection.mm_pnl_cents,
            "fees_collected_cents": view.projection.fees_collected_cents,
        },
        "error": {"type": "error", "code": "INVALID_FRAME", "message": "unknown frame type"},
        "pong": {"type": "pong", "t": 1},
    }


def iter_payload_models() -> Iterable[type[BaseModel]]:
    """Yield every payload model of section 7.21, for the generated documentation."""
    return (
        Health,
        MatchSummary,
        MarketInfo,
        AgentInfo,
        Ranking,
        MatchDetail,
        BookLevelDto,
        MarketTick,
        PositionDto,
        AccountTick,
        NewsDto,
        SignalDto,
        TradeDto,
        PredictionDto,
        MessageDto,
        ResolutionDto,
        Highlight,
        HighlightsEnvelope,
        TickState,
        AgentSeries,
        MarketSeries,
        MatchSeries,
        DecisionPrediction,
        DecisionOrder,
        Decision,
        PerformanceRow,
        ReliabilityBin,
        CalibrationRow,
        DescriptorRow,
        MatchMetricsPayload,
        Incident,
        IncidentsEnvelope,
        TournamentSummary,
        LeaderboardRow,
        ProgressionPoint,
        ProgressionRow,
        EliteCellDto,
        Elites,
        CostRow,
        LiquidityCostRow,
        ProfileBalance,
        Kpi,
        TournamentDetail,
    )
