"""The projection of a journal into results (CONTRACTS_V2 sections 12.3, 12.5 and 12.11).

``project(events)`` reads the journal and **nothing else**: no dataset, no agent, no gateway, no engine
state. That is what makes ``pmx replay`` a real check rather than a re-run (section 9.5): a
``results.json`` that cannot be rebuilt from ``journal.jsonl`` is a bug in this module, never a reason to
widen the journal with a derived number. The two observed inputs the journal carries for exactly this
reason are ``market_listed`` (category, tags, event key, close, fold, hardness tags) and
``market_priced`` (the bar's own close and the as-of close), and every number below is a function of
those plus the forecasts, the orders, the fills, the settlements and the marks.

The scores themselves are not computed here. ``pmx.scoring`` (E3) owns every forecast number of section
12.1 and ``pmx.metrics.calibration`` (E3) every reliability number of 12.2, so the projection's job is to
turn journal rows into ``ForecastBar`` records, hand them over, and assemble the result. Two spellings of
the time-weighted Brier is exactly how ``settlement_applied.agent_brier_tw_micro`` and ``PerMarket``
would drift apart.

Two consequences of "the journal alone" are worth stating because they look like omissions:

* The block bootstrap needs an ``RngTree`` and ``project`` takes no seed, so the tree is rebuilt from
  ``run_started.seed`` as ``RngTree(seed).child("stats")``, exactly the tree section 6.2 hands to
  ``pmx.metrics.stats``. The seed is in the journal, so the intervals replay byte for byte.
* A market with no ``settled`` event inside the run has no outcome, so it carries no scored row. It is
  still counted in ``n_markets_open`` (what the agent saw) and absent from ``n_markets`` (what it was
  scored on). A run over a whole dataset settles every market and the two agree.

Ratios are ``0`` when their denominator is ``0`` and a slice with ``n == 0`` reports zeros throughout, so
the projection of a one-agent ``follower(1000, 0)`` run is a complete result and not a
``ZeroDivisionError`` (section 12's preamble).

A continuous instrument is projected per ``(agent, instrument, ISO week, horizon)`` cell (amendment
C1b, section 17.6): the unit of a continuous claim is a cell and not an instrument, so that is the row
that feeds every ``Interval``. Its score half is ``pmx.scoring``'s aggregation of the week's resolved
horizons, its money half is the cash the fills, the fees and the cash events of that week moved, and
its baseline is the random walk, whose skill is ``0`` by construction exactly as ``market_follower``'s
is on a binary.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from pmx.errors import JournalError
from pmx.journal import (
    ActionReceived,
    AgentRuined,
    CashEventApplied,
    EquityMarked,
    FeeCharged,
    Filled,
    ForecastRecorded,
    ForecastResolved,
    InstrumentClosed,
    JournalEvent,
    MarketListed,
    MarketPriced,
    OrderPlaced,
    ResearchSpent,
    RunEnded,
    RunStarted,
    Settled,
    SettlementApplied,
)
from pmx.metrics.behavioral import Descriptors, descriptors
from pmx.metrics.calibration import (
    CalibrationEntry,
    binary_entry,
    calibration_bin_views,
    calibration_table,
    ece_ppm,
    reliability_bins,
    sharpness_ppm,
)
from pmx.metrics.performance import Performance, performance
from pmx.metrics.stats import Interval, block_key, bootstrap_lower_bound, iso_week_key
from pmx.rng import RngTree
from pmx.scoring import (
    ContinuousHorizonScore,
    ForecastBar,
    HorizonBucket,
    HorizonResolution,
    bar_weights_ms,
    brier_series_micro,
    horizon_bucket_of,
    market_brier_series_micro,
    score_binary_market,
    score_continuous_horizon,
    weighted_mean_micro,
)
from pmx.types import (
    BINARY_POINT_VALUE_MICRO,
    BINARY_TICK_SIZE_MICRO,
    CENTS_PER_UNIT,
    HORIZON_BUCKETS,
    NOTIONAL_DENOMINATOR,
    RANDOM_WALK_BRIER_MICRO,
    CalibrationBinView,
    MarketMeta,
    bar_of,
    interval_ms,
    round_half_up,
)

#: Amendment C1b's three events (section 9.2, ruling R164) are matched by ``TYPE``; their dataclasses are
#: ``pmx.journal``'s since gate G2 and the names below are the ``TYPE`` strings those classes carry.
CASH_EVENT_APPLIED = CashEventApplied.TYPE
FORECAST_RESOLVED = ForecastResolved.TYPE
INSTRUMENT_CLOSED = InstrumentClosed.TYPE

#: The one divisor of a cash movement (17.1): ``NOTIONAL_DENOMINATOR`` under this module's older name.
NOTIONAL_CENTS_DENOMINATOR = NOTIONAL_DENOMINATOR

__all__ = (
    "AgentResult",
    "MarketResult",
    "PerMarket",
    "RunHandle",
    "RunProjection",
    "project",
)


# --------------------------------------------------------------------------------------------------
# The structures section 12.11 declares
# --------------------------------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class PerMarket:
    """One row per ``(agent, market)``: the input of every :class:`Interval` (section 12.11).

    The eight defaulted fields are amendment C1b's; on a binary run they carry their defaults and
    ``unit_key`` is the market id, so the sort key of ``RunProjection.per_market`` is stable for every
    kind (ruling R199).
    """

    agent_id: str
    market_id: str
    provider: str
    category: str
    tags: tuple[str, ...]
    block_key: str
    fold: str
    hardness_tags: tuple[str, ...]
    n_forecast_bars: int
    agent_brier_tw_micro: int
    market_brier_tw_micro: int
    skill_micro: int
    log_micronats: int
    pmv_1d_bp: int
    pmv_7d_bp: int
    realised_pnl_cents: int
    fees_cents: int
    n_fills: int
    abstained_bars: int
    traded: bool
    kind: str = "binary"
    horizon_bars: int = 0
    unit_key: str = ""
    dir_brier_micro: int = 0
    pinball_micro: int = 0
    baseline_pinball_micro: int = 0
    n_resolved: int = 0
    n_cash_events: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "agent_id": self.agent_id,
            "market_id": self.market_id,
            "provider": self.provider,
            "category": self.category,
            "tags": list(self.tags),
            "block_key": self.block_key,
            "fold": self.fold,
            "hardness_tags": list(self.hardness_tags),
            "n_forecast_bars": self.n_forecast_bars,
            "agent_brier_tw_micro": self.agent_brier_tw_micro,
            "market_brier_tw_micro": self.market_brier_tw_micro,
            "skill_micro": self.skill_micro,
            "log_micronats": self.log_micronats,
            "pmv_1d_bp": self.pmv_1d_bp,
            "pmv_7d_bp": self.pmv_7d_bp,
            "realised_pnl_cents": self.realised_pnl_cents,
            "fees_cents": self.fees_cents,
            "n_fills": self.n_fills,
            "abstained_bars": self.abstained_bars,
            "traded": self.traded,
            "kind": self.kind,
            "horizon_bars": self.horizon_bars,
            "unit_key": self.unit_key,
            "dir_brier_micro": self.dir_brier_micro,
            "pinball_micro": self.pinball_micro,
            "baseline_pinball_micro": self.baseline_pinball_micro,
            "n_resolved": self.n_resolved,
            "n_cash_events": self.n_cash_events,
        }


@dataclass(frozen=True, slots=True)
class AgentResult:
    """One agent's whole run (section 12.11).

    ``ece_ppm`` and ``sharpness_ppm`` are defaulted extensions of the declared field list (preamble
    rule 2, reported): section 12.10 requires ``ece_ppm`` on every leaderboard row, a leaderboard is
    built from a :class:`RunProjection` alone, and ``CalibrationBinView`` (section 8.3) carries no
    ``mean_prob_ppm``, so the exact number either crosses here or is approximated from a bin midpoint.
    It crosses here.
    """

    agent_id: str
    family: str
    kind: str
    genome_hash: str
    ruined: bool
    n_markets: int
    n_markets_traded: int
    n_markets_open: int
    brier_tw_micro: int
    skill: Interval
    pnl: Interval
    pnl_cents: int
    return_bp: int
    max_drawdown_bp: int
    sharpe_milli: int
    turnover_cents: int
    fill_ratio_ppm: int
    fees_paid_cents: int
    abstention_ppm: int
    explicit_abstain_ppm: int
    descriptors: Descriptors
    calibration: tuple[CalibrationBinView, ...]
    horizons: tuple[HorizonBucket, ...]
    research_units_spent: int
    pinball_skill: Interval | None = None
    exposure_by_kind: tuple[tuple[str, int], ...] = ()
    n_cash_events: int = 0
    ece_ppm: int = 0
    sharpness_ppm: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "agent_id": self.agent_id,
            "family": self.family,
            "kind": self.kind,
            "genome_hash": self.genome_hash,
            "ruined": self.ruined,
            "n_markets": self.n_markets,
            "n_markets_traded": self.n_markets_traded,
            "n_markets_open": self.n_markets_open,
            "brier_tw_micro": self.brier_tw_micro,
            "skill": self.skill.to_dict(),
            "pnl": self.pnl.to_dict(),
            "pnl_cents": self.pnl_cents,
            "return_bp": self.return_bp,
            "max_drawdown_bp": self.max_drawdown_bp,
            "sharpe_milli": self.sharpe_milli,
            "turnover_cents": self.turnover_cents,
            "fill_ratio_ppm": self.fill_ratio_ppm,
            "fees_paid_cents": self.fees_paid_cents,
            "abstention_ppm": self.abstention_ppm,
            "explicit_abstain_ppm": self.explicit_abstain_ppm,
            "descriptors": self.descriptors.to_dict(),
            "calibration": [row.to_dict() for row in self.calibration],
            "horizons": [row.to_dict() for row in self.horizons],
            "research_units_spent": self.research_units_spent,
            "pinball_skill": None if self.pinball_skill is None else self.pinball_skill.to_dict(),
            "exposure_by_kind": [[kind, cents] for kind, cents in self.exposure_by_kind],
            "n_cash_events": self.n_cash_events,
            "ece_ppm": self.ece_ppm,
            "sharpness_ppm": self.sharpness_ppm,
        }


@dataclass(frozen=True, slots=True)
class MarketResult:
    """One market of the run, with its own baseline score (section 12.11)."""

    market_id: str
    provider: str
    category: str
    fold: str
    block_key: str
    outcome: int
    n_bars: int
    market_brier_tw_micro: int
    life_mean_price_bp: int
    hardness_tags: tuple[str, ...]
    kind: str = "binary"
    vendor: str = ""
    last_price_ticks: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "market_id": self.market_id,
            "provider": self.provider,
            "category": self.category,
            "fold": self.fold,
            "block_key": self.block_key,
            "outcome": self.outcome,
            "n_bars": self.n_bars,
            "market_brier_tw_micro": self.market_brier_tw_micro,
            "life_mean_price_bp": self.life_mean_price_bp,
            "hardness_tags": list(self.hardness_tags),
            "kind": self.kind,
            "vendor": self.vendor,
            "last_price_ticks": self.last_price_ticks,
        }


@dataclass(frozen=True, slots=True)
class RunProjection:
    """What ``results.json`` holds: ``canonical_json(projection.to_dict()) + "\\n"`` and nothing else."""

    run_id: str
    dataset_hash: str
    config_hash: str
    interval_min: int
    t0_ms: int
    t1_ms: int
    liquidity: str
    liquidity_params_hash: str
    agents: tuple[AgentResult, ...]
    markets: tuple[MarketResult, ...]
    per_market: tuple[PerMarket, ...]
    ruined_agent_ids: tuple[str, ...]

    def agent(self, agent_id: str) -> AgentResult:
        """The one row of ``agent_id``, or a :class:`JournalError` naming what the run carried."""
        for result in self.agents:
            if result.agent_id == agent_id:
                return result
        raise JournalError(
            "this projection carries no such agent",
            agent_id=agent_id,
            agents=",".join(result.agent_id for result in self.agents),
        )

    def rows_of(self, agent_id: str) -> tuple[PerMarket, ...]:
        """Every scored ``(agent, market)`` row of one agent, in the projection's own order."""
        return tuple(row for row in self.per_market if row.agent_id == agent_id)

    def to_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "dataset_hash": self.dataset_hash,
            "config_hash": self.config_hash,
            "interval_min": self.interval_min,
            "t0_ms": self.t0_ms,
            "t1_ms": self.t1_ms,
            "liquidity": self.liquidity,
            "liquidity_params_hash": self.liquidity_params_hash,
            "agents": [row.to_dict() for row in self.agents],
            "markets": [row.to_dict() for row in self.markets],
            "per_market": [row.to_dict() for row in self.per_market],
            "ruined_agent_ids": list(self.ruined_agent_ids),
        }


@dataclass(frozen=True, slots=True)
class RunHandle:
    """What ``run_backtest`` returns and every caller of the engine holds (section 12.11)."""

    run_id: str
    run_dir: Path
    journal_path: Path
    journal_hash: str
    dataset_hash: str
    config_hash: str
    projection: RunProjection
    n_events: int
    n_bars: int
    ruined_agent_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """The handle as canonical JSON: the two paths render as POSIX strings, never as ``Path``."""
        return {
            "run_id": self.run_id,
            "run_dir": self.run_dir.as_posix(),
            "journal_path": self.journal_path.as_posix(),
            "journal_hash": self.journal_hash,
            "dataset_hash": self.dataset_hash,
            "config_hash": self.config_hash,
            "projection": self.projection.to_dict(),
            "n_events": self.n_events,
            "n_bars": self.n_bars,
            "ruined_agent_ids": list(self.ruined_agent_ids),
        }


# --------------------------------------------------------------------------------------------------
# The walk
# --------------------------------------------------------------------------------------------------
@dataclass(slots=True)
class _MarketState:
    """Everything one market's events said, in bar order.

    ``kind``, ``vendor`` and the four scales are amendment C1b's ``market_listed`` fields (ruling
    R164), defaulted to what a v2 journal means: a binary of its own provider, one cent a tick, one
    unit a point. ``closed`` is the ``instrument_closed`` event of a continuous instrument, which is
    what a settled binary's ``settled`` is: the row that says the instrument was scored in this run.
    """

    listed: MarketListed
    bars_ms: list[int]
    close_bp: dict[int, int]
    last_close_bp: dict[int, int]
    settled: Settled | None = None
    kind: str = "binary"
    vendor: str = ""
    tick_size_micro: int = BINARY_TICK_SIZE_MICRO
    point_value_micro: int = BINARY_POINT_VALUE_MICRO
    closed: JournalEvent | None = None

    @property
    def is_binary(self) -> bool:
        """True for the binary kind, whose outcome, payout and Brier are sections 8.7's and 12.1's."""
        return self.kind == "binary"

    @property
    def scored(self) -> bool:
        """True when the run scored the instrument: it settled, or it closed (ruling R150)."""
        return self.settled is not None if self.is_binary else self.closed is not None


@dataclass(slots=True)
class _PairState:
    """Everything one ``(agent, market)`` pair's events said."""

    forecasts: list[tuple[int, int, bool]]
    fills: list[tuple[int, int, int, int, int]]
    order_bars: set[int]
    action_kinds: dict[int, str]
    fee_bars: list[tuple[int, int]] = field(default_factory=list)
    cash_event_bars: list[tuple[int, int]] = field(default_factory=list)
    fees_cents: int = 0
    n_fills: int = 0
    n_cash_events: int = 0
    filled_size: int = 0
    requested_size: int = 0
    settlement: SettlementApplied | None = None


@dataclass(slots=True)
class _AgentState:
    """Everything one agent's own events said."""

    agent_id: str
    family: str
    kind: str
    genome_hash: str
    equities_cents: list[int]
    drawdowns_bp: list[int]
    final_cash_cents: int = 0
    fees_paid_cents: int = 0
    research_units_spent: int = 0
    ruined: bool = False


def _event_int(event: JournalEvent, name: str, default: int = 0) -> int:
    """An integer payload field of an event this module matches by ``TYPE`` (amendment C1b)."""
    value = getattr(event, name, default)
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def _event_str(event: JournalEvent, name: str, default: str = "") -> str:
    """A string payload field of an event this module matches by ``TYPE``."""
    value = getattr(event, name, default)
    return value if isinstance(value, str) else default


def _event_bool(event: JournalEvent, name: str) -> bool:
    """A boolean payload field of an event this module matches by ``TYPE``."""
    value = getattr(event, name, False)
    return value if isinstance(value, bool) else False


def _event_ticks(event: JournalEvent, name: str) -> tuple[int, ...] | None:
    """A quantile tuple payload field, ``None`` when the agent stated none (section 17.5)."""
    value = getattr(event, name, None)
    if not isinstance(value, tuple | list):
        return None
    return tuple(item for item in value if isinstance(item, int) and not isinstance(item, bool))


def _resolution_of(event: JournalEvent) -> HorizonResolution:
    """One ``forecast_resolved`` payload as the scored record ``pmx.scoring`` aggregates (17.5)."""
    pinball = getattr(event, "pinball_micro", None)
    return HorizonResolution(
        forecast_bar_ms=_event_int(event, "forecast_bar_ms"),
        horizon_bars=_event_int(event, "horizon_bars"),
        up_probability_ppm=_event_int(event, "up_probability_ppm"),
        quantiles_ticks=_event_ticks(event, "quantiles_ticks"),
        price_ref_ticks=_event_int(event, "price_ref_ticks"),
        price_realised_ticks=_event_int(event, "price_realised_ticks"),
        realised_sign=_event_int(event, "realised_sign"),
        directional_brier_micro=_event_int(event, "directional_brier_micro"),
        pinball_micro=pinball if isinstance(pinball, int) and not isinstance(pinball, bool) else None,
        baseline_pinball_micro=_event_int(event, "baseline_pinball_micro"),
        carried=_event_bool(event, "carried"),
    )


def _int_of(mapping: Mapping[str, object], key: str, default: int) -> int:
    value = mapping.get(key, default)
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def _str_of(mapping: Mapping[str, object], key: str, default: str) -> str:
    value = mapping.get(key, default)
    return value if isinstance(value, str) else default


def project(events: Sequence[JournalEvent]) -> RunProjection:
    """Rebuild the whole result of a run from its journal (sections 12.3, 12.5 and 12.11).

    Args:
        events: The journal, in ``seq`` order, starting at ``run_started``.

    Returns:
        The :class:`RunProjection` whose canonical JSON is ``results.json``.

    Raises:
        JournalError: If the journal does not start with ``run_started``, or if a forecast bar carries
            no ``market_priced`` (a journal that cannot be scored is a journal bug, never a bar to drop
            quietly).
    """
    if not events or not isinstance(events[0], RunStarted):
        raise JournalError("a projection starts at run_started", n_events=len(events))
    started = events[0]
    config = started.config
    interval = interval_ms(started.interval_min)
    bankroll_cents = _int_of(config, "bankroll_cents", 100_000)

    markets: dict[str, _MarketState] = {}
    pairs: dict[tuple[str, str], _PairState] = {}
    agents: dict[str, _AgentState] = {}
    for row in started.roster:
        agent_id = _str_of(row, "agent_id", "")
        agents[agent_id] = _AgentState(
            agent_id=agent_id,
            family=_str_of(row, "family", ""),
            kind=_str_of(row, "kind", "scripted"),
            genome_hash=_str_of(row, "genome_hash", ""),
            equities_cents=[],
            drawdowns_bp=[],
        )
    ruined_ids: list[str] = []
    resolved: dict[tuple[str, str, str, int], list[HorizonResolution]] = {}

    def pair(agent_id: str, market_id: str) -> _PairState:
        key = (agent_id, market_id)
        state = pairs.get(key)
        if state is None:
            state = _PairState(forecasts=[], fills=[], order_bars=set(), action_kinds={})
            pairs[key] = state
        return state

    for event in events:
        if isinstance(event, MarketListed):
            markets[event.market_id] = _MarketState(
                listed=event,
                bars_ms=[],
                close_bp={},
                last_close_bp={},
                kind=_event_str(event, "kind", "binary"),
                vendor=_event_str(event, "vendor", event.provider),
                tick_size_micro=_event_int(event, "tick_size_micro", BINARY_TICK_SIZE_MICRO),
                point_value_micro=_event_int(event, "point_value_micro", BINARY_POINT_VALUE_MICRO),
            )
        elif isinstance(event, MarketPriced):
            priced = markets.get(event.market_id)
            if priced is not None and event.bar_ms not in priced.close_bp:
                priced.bars_ms.append(event.bar_ms)
                priced.close_bp[event.bar_ms] = event.close_bp
                priced.last_close_bp[event.bar_ms] = event.last_close_bp
        elif isinstance(event, ForecastRecorded):
            pair(event.agent_id, event.market_id).forecasts.append(
                (event.bar_ms, event.prob_ppm, event.carried)
            )
        elif isinstance(event, ActionReceived):
            for intent in event.intents:
                pair(event.agent_id, _str_of(intent, "market_id", "")).action_kinds[event.bar_ms] = (
                    _str_of(intent, "kind", "hold")
                )
        elif isinstance(event, OrderPlaced):
            pair(event.agent_id, event.market_id).order_bars.add(event.bar_ms)
        elif isinstance(event, Filled):
            filled = pair(event.agent_id, event.market_id)
            filled.fills.append(
                (
                    event.bar_ms,
                    event.filled_size,
                    event.requested_size,
                    event.cash_delta_cents,
                    event.position_after,
                )
            )
            filled.n_fills += 1
            filled.filled_size += event.filled_size
            filled.requested_size += event.requested_size
        elif isinstance(event, FeeCharged):
            charged = pair(event.agent_id, event.market_id)
            charged.fees_cents += event.fee_cents
            charged.fee_bars.append((event.bar_ms, event.fee_cents))
        elif isinstance(event, Settled):
            settled = markets.get(event.market_id)
            if settled is not None:
                settled.settled = event
        elif isinstance(event, SettlementApplied):
            pair(event.agent_id, event.market_id).settlement = event
        elif isinstance(event, EquityMarked):
            marked = agents.get(event.agent_id)
            if marked is not None:
                marked.equities_cents.append(event.equity_cents)
                marked.drawdowns_bp.append(event.drawdown_bp)
                marked.final_cash_cents = event.cash_cents
                marked.fees_paid_cents = event.fees_paid_cents
        elif isinstance(event, ResearchSpent):
            spent = agents.get(event.agent_id)
            if spent is not None and event.granted:
                spent.research_units_spent += event.units
        elif isinstance(event, AgentRuined):
            ruined = agents.get(event.agent_id)
            if ruined is not None:
                ruined.ruined = True
            if event.agent_id not in ruined_ids:
                ruined_ids.append(event.agent_id)
        elif event.TYPE == FORECAST_RESOLVED:
            horizon_row = _resolution_of(event)
            resolved.setdefault(
                (
                    _event_str(event, "agent_id"),
                    _event_str(event, "market_id"),
                    iso_week_key(horizon_row.forecast_bar_ms),
                    horizon_row.horizon_bars,
                ),
                [],
            ).append(horizon_row)
        elif event.TYPE == INSTRUMENT_CLOSED:
            instrument = markets.get(_event_str(event, "market_id"))
            if instrument is not None:
                instrument.closed = event
        elif event.TYPE == CASH_EVENT_APPLIED:
            booked = pair(_event_str(event, "agent_id"), _event_str(event, "market_id"))
            booked.n_cash_events += 1
            booked.cash_event_bars.append((event.bar_ms, _event_int(event, "cash_delta_cents")))
        elif isinstance(event, RunEnded):
            for agent_id in event.ruined_agent_ids:
                if agent_id not in ruined_ids:
                    ruined_ids.append(agent_id)
                ended = agents.get(agent_id)
                if ended is not None:
                    ended.ruined = True

    metas = {
        market_id: _meta_of(state)
        for market_id, state in markets.items()
        if state.is_binary and state.settled is not None
    }
    blocks = {market_id: block_key(meta) for market_id, meta in metas.items()}

    scored_pairs = sorted(
        key for key in pairs if key[1] in metas and pairs[key].forecasts
    )
    bars_by_pair = {
        key: _forecast_bars(pairs[key], markets[key[1]]) for key in scored_pairs
    }
    binary_rows = [
        _per_market_row(
            agent_id=agent_id,
            market_id=market_id,
            state=pairs[(agent_id, market_id)],
            market=markets[market_id],
            bars=bars_by_pair[(agent_id, market_id)],
            block=blocks[market_id],
            interval=interval,
        )
        for agent_id, market_id in scored_pairs
    ]
    continuous_rows = [
        _continuous_row(
            agent_id=agent_id,
            market_id=market_id,
            week=week,
            horizon_bars=horizon_bars,
            resolutions=resolved[(agent_id, market_id, week, horizon_bars)],
            market=markets[market_id],
            state=pairs.get((agent_id, market_id)),
        )
        for agent_id, market_id, week, horizon_bars in sorted(resolved)
        if market_id in markets
    ]
    per_market = tuple(
        sorted(
            [*binary_rows, *continuous_rows],
            key=lambda row: (row.agent_id, row.market_id, row.horizon_bars, row.unit_key),
        )
    )

    stats_tree = RngTree(started.seed).child("stats")
    agent_results = tuple(
        _agent_result(
            state=agents[agent_id],
            rows=tuple(row for row in per_market if row.agent_id == agent_id),
            pairs=pairs,
            markets=markets,
            bars_by_pair=bars_by_pair,
            bankroll_cents=bankroll_cents,
            interval=interval,
            stats_tree=stats_tree,
        )
        for agent_id in sorted(agents)
    )

    market_results = tuple(
        _market_result(
            markets[market_id],
            block=blocks.get(market_id, iso_week_key(_sort_ms(markets[market_id]))),
        )
        for market_id in sorted(
            (market_id for market_id, state in markets.items() if state.scored),
            key=lambda market_id: (_sort_ms(markets[market_id]), market_id),
        )
    )

    return RunProjection(
        run_id=started.run_id,
        dataset_hash=started.dataset_hash,
        config_hash=started.config_hash,
        interval_min=started.interval_min,
        t0_ms=started.t0_ms,
        t1_ms=started.t1_ms,
        liquidity=_str_of(config, "liquidity", "historical"),
        liquidity_params_hash=_str_of(config, "liquidity_params_hash", ""),
        agents=agent_results,
        markets=market_results,
        per_market=per_market,
        ruined_agent_ids=tuple(sorted(ruined_ids)),
    )


def _forecast_bars(state: _PairState, market: _MarketState) -> tuple[ForecastBar, ...]:
    """One :class:`ForecastBar` per ``forecast_recorded``, carrying the as-of price of the same bar.

    A forecast bar with no ``market_priced`` is a journal that cannot be scored: both events are
    emitted in the same bar for every open market (section 8.2), so the absence is a bug in whoever
    wrote the journal and it is raised rather than skipped.
    """
    bars: list[ForecastBar] = []
    for bar_ms, prob_ppm, _ in state.forecasts:
        price_bp = market.last_close_bp.get(bar_ms)
        if price_bp is None:
            raise JournalError(
                "a forecast bar carries no market_priced",
                market_id=market.listed.market_id,
                bar_ms=bar_ms,
            )
        bars.append(ForecastBar(t_ms=bar_ms, prob_ppm=prob_ppm, market_price_bp=price_bp))
    return tuple(bars)


def _meta_of(state: _MarketState) -> MarketMeta:
    """The leak-free metadata of a settled market, rebuilt from its two journal events.

    ``block_key`` (section 12.4) takes a ``MarketMeta`` and the projection holds only the journal, which
    is exactly why ``market_listed`` and ``settled`` carry what they carry (section 9.2).
    """
    listed = state.listed
    settled = state.settled
    if settled is None:  # pragma: no cover - the caller filters on it
        raise JournalError("a market meta needs its settled event", market_id=listed.market_id)
    return MarketMeta(
        id=listed.market_id,
        provider=listed.provider,
        category=listed.category,
        tags=listed.tags,
        event_key=listed.event_key,
        created_at_ms=listed.created_at_ms,
        close_at_ms=listed.close_at_ms,
        resolved_at_ms=settled.resolved_at_ms,
        resolution=settled.outcome,
        interval_min=listed.interval_min,
        n_bars=settled.n_bars,
        hardness_tags=listed.hardness_tags,
        fee_schedule_id=listed.fee_schedule_id,
        fold=listed.fold,
    )


def _sort_ms(state: _MarketState) -> int:
    """The instant section 3 orders an instrument by: ``resolved_at_ms``, generalised (ruling R186).

    A binary orders by its ``settled.resolved_at_ms``. A continuous instrument has none, and R186 reads
    it as ``delisted_at_ms`` when set, else the dataset's window end: from the journal alone that is
    ``market_listed.close_at_ms`` (which carries ``delisted_at_ms``, ``0`` when unset) and, when unset,
    the bar of its ``instrument_closed``, which is the run's own window end for it.
    """
    if state.is_binary:
        return state.settled.resolved_at_ms if state.settled is not None else 0
    if state.listed.close_at_ms > 0:
        return state.listed.close_at_ms
    return state.closed.bar_ms if state.closed is not None else 0


def _market_result(state: _MarketState, *, block: str) -> MarketResult:
    listed = state.listed
    if not state.is_binary:
        return _continuous_market_result(state, block=block)
    settled = state.settled
    if settled is None:  # pragma: no cover - the caller filters on it
        raise JournalError("a market result needs its settled event", market_id=listed.market_id)
    last_bar = state.bars_ms[-1] if state.bars_ms else 0
    return MarketResult(
        market_id=listed.market_id,
        provider=listed.provider,
        category=listed.category,
        fold=listed.fold,
        block_key=block,
        outcome=settled.outcome,
        n_bars=settled.n_bars,
        market_brier_tw_micro=settled.market_brier_tw_micro,
        life_mean_price_bp=settled.life_mean_price_bp,
        hardness_tags=listed.hardness_tags,
        vendor=listed.provider,
        last_price_ticks=state.close_bp.get(last_bar, 0),
    )


def _continuous_market_result(state: _MarketState, *, block: str) -> MarketResult:
    """One continuous instrument's row (12.11, ruling R163): no outcome, the mean close in ticks.

    ``outcome`` is ``-1`` because there is nothing to be right about, ``market_brier_tw_micro`` is the
    random walk's constant (which is what the row's baseline scores, 17.5), ``life_mean_price_bp`` is
    the mean of the instrument's own closes in ticks, and ``hardness_tags`` is empty (R186).
    """
    listed = state.listed
    closed = state.closed
    if closed is None:  # pragma: no cover - the caller filters on it
        raise JournalError("an instrument result needs its instrument_closed", market_id=listed.market_id)
    closes = [state.close_bp[bar_ms] for bar_ms in state.bars_ms]
    return MarketResult(
        market_id=listed.market_id,
        provider=listed.provider,
        category=listed.category,
        fold=listed.fold,
        block_key=block,
        outcome=-1,
        n_bars=_event_int(closed, "n_bars", len(closes)),
        market_brier_tw_micro=RANDOM_WALK_BRIER_MICRO,
        life_mean_price_bp=round_half_up(sum(closes), len(closes)) if closes else 0,
        hardness_tags=(),
        kind=state.kind,
        vendor=state.vendor,
        last_price_ticks=_event_int(closed, "last_price_ticks"),
    )


def _continuous_row(
    *,
    agent_id: str,
    market_id: str,
    week: str,
    horizon_bars: int,
    resolutions: Sequence[HorizonResolution],
    market: _MarketState,
    state: _PairState | None,
) -> PerMarket:
    """One ``(agent, instrument, ISO week, horizon)`` cell (17.6, rulings R163 and R186).

    The unit of a continuous claim is a cell and not an instrument, so the row that feeds every
    ``Interval`` is per cell: ``block_key`` is the cell's own week, ``unit_key`` is
    ``"<market_id>/<week>"``, and the PnL half is the cash the fills, the fees and the cash events of
    **that week** moved. The score half is ``pmx.scoring``'s aggregation of the week's resolved
    horizons; ``pmv_1d_bp`` carries the row's own horizon PMV, because a continuous row has one horizon
    and section 12.11 gives ``PerMarket`` one PMV column per binary horizon (reported).
    """
    listed = market.listed
    score: ContinuousHorizonScore = score_continuous_horizon(resolutions, horizon_bars=horizon_bars)
    # The cell's bars are **every** bar of the instrument the agent decided on in that week, not only
    # the bars whose horizon resolved: the money half of the row is the week's cash, and a fill made on
    # a bar whose horizon fell outside the run would otherwise be booked in no cell at all.
    bars = (
        frozenset(item.forecast_bar_ms for item in resolutions)
        if state is None
        else frozenset(
            bar_ms for bar_ms, _, _ in state.forecasts if iso_week_key(bar_ms) == week
        )
    )
    realised, fees, cash_events, n_fills, traded, abstained = _week_ledger(state, bars)
    return PerMarket(
        agent_id=agent_id,
        market_id=market_id,
        provider=listed.provider,
        category=listed.category,
        tags=listed.tags,
        block_key=week,
        fold=listed.fold,
        hardness_tags=(),
        n_forecast_bars=score.n_resolved,
        agent_brier_tw_micro=score.dir_brier_micro,
        market_brier_tw_micro=RANDOM_WALK_BRIER_MICRO,
        skill_micro=score.skill_micro,
        log_micronats=0,
        pmv_1d_bp=score.pmv_bp,
        pmv_7d_bp=0,
        realised_pnl_cents=realised,
        fees_cents=fees,
        n_fills=n_fills,
        abstained_bars=abstained,
        traded=traded,
        kind=market.kind,
        horizon_bars=horizon_bars,
        unit_key=f"{market_id}/{week}",
        dir_brier_micro=score.dir_brier_micro,
        pinball_micro=score.pinball_micro,
        baseline_pinball_micro=score.baseline_pinball_micro,
        n_resolved=score.n_resolved,
        n_cash_events=cash_events,
    )


def _week_ledger(
    state: _PairState | None, bars: frozenset[int]
) -> tuple[int, int, int, int, bool, int]:
    """The cash, the fees, the cash events, the fills and the abstentions of one cell's bars (17.6).

    Only the bars of that week are counted, so an instrument's weeks partition its own fills exactly
    once. Two cells of the same week at different horizons carry the same money, which is what section
    17.6 declares: the unit is the ``(instrument, week)`` cell and the row key adds the horizon, so a
    claim at one horizon books each week's cash once.
    """
    if state is None:
        return 0, 0, 0, 0, False, len(bars)
    cash = sum(delta for bar_ms, _, _, delta, _ in state.fills if bar_ms in bars)
    fees = sum(fee for bar_ms, fee in state.fee_bars if bar_ms in bars)
    events = sum(delta for bar_ms, delta in state.cash_event_bars if bar_ms in bars)
    n_events = sum(1 for bar_ms, _ in state.cash_event_bars if bar_ms in bars)
    n_fills = sum(1 for bar_ms, _, _, _, _ in state.fills if bar_ms in bars)
    traded = any(filled >= 1 for bar_ms, filled, _, _, _ in state.fills if bar_ms in bars)
    abstained = sum(
        1
        for bar_ms in sorted(bars)
        if bar_ms not in state.order_bars and _position_at_bar_end(state, bar_ms) == 0
    )
    return cash - fees + events, fees, n_events, n_fills, traded, abstained


def _position_at_bar_end(state: _PairState, bar_ms: int) -> int:
    """The position the **agent** chose to end that bar with: the last fill at or before ``bar_ms``.

    Settlement is deliberately not applied here even though it flattens the leg in the settle phase of
    the settling bar (section 8.7). ``abstention_ppm`` (12.3) measures the bars an agent ended flat
    **and** placed no order on, and it exists to expose silence; counting the settling bar of every
    position an agent carried to the end would report abstention for the most committed trader in the
    run, which is the failure mode section 12.3 wrote the column to avoid.
    """
    position = 0
    for fill_bar_ms, _, _, _, position_after in state.fills:
        if fill_bar_ms > bar_ms:
            break
        position = position_after
    return position


def _per_market_row(
    *,
    agent_id: str,
    market_id: str,
    state: _PairState,
    market: _MarketState,
    bars: Sequence[ForecastBar],
    block: str,
    interval: int,
) -> PerMarket:
    settled = market.settled
    if settled is None:  # pragma: no cover - the caller filters on it
        raise JournalError("a scored row needs its settled event", market_id=market_id)
    listed = market.listed
    settle_bar_ms = bar_of(settled.resolved_at_ms, listed.interval_min)
    score = score_binary_market(
        bars,
        outcome=settled.outcome,
        close_at_ms=listed.close_at_ms,
        settle_bar_ms=settle_bar_ms,
        interval_ms=interval,
    )
    abstained = sum(
        1
        for bar_ms, _, _ in state.forecasts
        if bar_ms not in state.order_bars and _position_at_bar_end(state, bar_ms) == 0
    )
    settlement = state.settlement
    return PerMarket(
        agent_id=agent_id,
        market_id=market_id,
        provider=listed.provider,
        category=listed.category,
        tags=listed.tags,
        block_key=block,
        fold=listed.fold,
        hardness_tags=listed.hardness_tags,
        n_forecast_bars=score.n_forecast_bars,
        agent_brier_tw_micro=score.agent_brier_tw_micro,
        market_brier_tw_micro=score.market_brier_tw_micro,
        skill_micro=score.skill_micro,
        log_micronats=score.log_micronats,
        pmv_1d_bp=score.pmv_1d_bp,
        pmv_7d_bp=score.pmv_7d_bp,
        realised_pnl_cents=0 if settlement is None else settlement.realised_pnl_cents,
        fees_cents=state.fees_cents,
        n_fills=state.n_fills,
        abstained_bars=abstained,
        traded=any(filled >= 1 for _, filled, _, _, _ in state.fills),
        unit_key=market_id,
        n_resolved=score.n_forecast_bars,
    )


def _legs_and_deviations(
    *,
    agent_id: str,
    pairs: Mapping[tuple[str, str], _PairState],
    markets: Mapping[str, _MarketState],
    interval: int,
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """The agent's closed-leg lengths in bars and its per-forecast deviations from the as-of price."""
    legs: list[int] = []
    deviations: list[int] = []
    for (owner, market_id), state in sorted(pairs.items()):
        if owner != agent_id:
            continue
        market = markets.get(market_id)
        if market is None:
            continue
        for bar_ms, prob_ppm, _ in state.forecasts:
            price_bp = market.last_close_bp.get(bar_ms)
            if price_bp is not None:
                deviations.append(prob_ppm // 100 - price_bp)
        opened_at: int | None = None
        position = 0
        for fill_bar_ms, _, _, _, position_after in state.fills:
            if position == 0 and position_after != 0:
                opened_at = fill_bar_ms
            elif position != 0 and position_after == 0 and opened_at is not None:
                legs.append((fill_bar_ms - opened_at) // interval)
                opened_at = None
            position = position_after
        if position != 0 and opened_at is not None and state.settlement is not None:
            legs.append((state.settlement.bar_ms - opened_at) // interval)
    return tuple(legs), tuple(deviations)


def _calibration_entries(
    *,
    agent_id: str,
    pairs: Mapping[tuple[str, str], _PairState],
    markets: Mapping[str, _MarketState],
) -> tuple[CalibrationEntry, ...]:
    """One calibration entry per scored ``(market, bar)`` forecast of the agent (section 12.2).

    Bins count forecasts and are never time-weighted, which section 12.2 states so that nobody "fixes"
    it, and the slice key is ``(category, horizon_bucket)`` so nothing is pooled across categories.
    """
    entries: list[CalibrationEntry] = []
    for (owner, market_id), state in sorted(pairs.items()):
        if owner != agent_id:
            continue
        market = markets.get(market_id)
        if market is None or market.settled is None:
            continue
        for bar_ms, prob_ppm, _ in state.forecasts:
            entries.append(
                binary_entry(
                    category=market.listed.category,
                    horizon_bucket=horizon_bucket_of(bar_ms, close_at_ms=market.listed.close_at_ms),
                    prob_ppm=prob_ppm,
                    outcome=market.settled.outcome,
                )
            )
    return tuple(entries)


def _horizon_buckets(
    *,
    agent_id: str,
    pairs: Mapping[tuple[str, str], _PairState],
    markets: Mapping[str, _MarketState],
    bars_by_pair: Mapping[tuple[str, str], tuple[ForecastBar, ...]],
    interval: int,
) -> tuple[HorizonBucket, ...]:
    """The four buckets of section 12.1 pooled over the agent's markets, always all four.

    E3's ``horizon_buckets`` slices one ``(agent, market)`` record; an agent's row pools its markets, so
    the weighted sums are accumulated here and divided once. The weights are the record's own
    (``bar_weights_ms``), so a bar's weight does not change because it is looked at through a bucket or
    through a roster.
    """
    totals: dict[str, tuple[int, int, int, int]] = {name: (0, 0, 0, 0) for name in HORIZON_BUCKETS}
    for (owner, market_id), bars in sorted(bars_by_pair.items()):
        if owner != agent_id:
            continue
        market = markets[market_id]
        settled = market.settled
        if settled is None:  # pragma: no cover - bars_by_pair is built over settled markets
            continue
        weights = bar_weights_ms(bars, interval_ms=interval)
        agent_series = brier_series_micro(bars, outcome=settled.outcome)
        market_series = market_brier_series_micro(bars, outcome=settled.outcome)
        for index, bar in enumerate(bars):
            name = horizon_bucket_of(bar.t_ms, close_at_ms=market.listed.close_at_ms)
            weight_total, agent_total, market_total, n_bars = totals[name]
            totals[name] = (
                weight_total + weights[index],
                agent_total + agent_series[index] * weights[index],
                market_total + market_series[index] * weights[index],
                n_bars + 1,
            )
    buckets: list[HorizonBucket] = []
    for name in HORIZON_BUCKETS:
        weight_total, agent_total, market_total, n_bars = totals[name]
        agent_brier = 0 if weight_total == 0 else round_half_up(agent_total, weight_total)
        market_brier = 0 if weight_total == 0 else round_half_up(market_total, weight_total)
        buckets.append(
            HorizonBucket(
                bucket=name,
                n_bars=n_bars,
                brier_tw_micro=agent_brier,
                market_brier_tw_micro=market_brier,
                skill_micro=market_brier - agent_brier,
            )
        )
    return tuple(buckets)


def _agent_result(
    *,
    state: _AgentState,
    rows: Sequence[PerMarket],
    pairs: Mapping[tuple[str, str], _PairState],
    markets: Mapping[str, _MarketState],
    bars_by_pair: Mapping[tuple[str, str], tuple[ForecastBar, ...]],
    bankroll_cents: int,
    interval: int,
    stats_tree: RngTree,
) -> AgentResult:
    agent_id = state.agent_id
    own = {key: value for key, value in pairs.items() if key[0] == agent_id}
    open_market_ids = sorted(market_id for (_, market_id), value in own.items() if value.forecasts)
    traded_market_ids = sorted(
        market_id
        for (_, market_id), value in own.items()
        if any(filled >= 1 for _, filled, _, _, _ in value.fills)
    )
    categories_open = {
        markets[market_id].listed.category for market_id in open_market_ids if market_id in markets
    }
    categories_traded = {
        markets[market_id].listed.category for market_id in traded_market_ids if market_id in markets
    }
    stats: Performance = performance(
        agent_id=agent_id,
        bankroll_cents=bankroll_cents,
        final_cash_cents=state.final_cash_cents,
        equities_cents=state.equities_cents,
        drawdowns_bp=state.drawdowns_bp,
        cash_deltas_cents=[delta for value in own.values() for _, _, _, delta, _ in value.fills],
        filled_size=sum(value.filled_size for value in own.values()),
        requested_size=sum(value.requested_size for value in own.values()),
        fees_paid_cents=state.fees_paid_cents,
        ruined=state.ruined,
        n_markets_traded=len(traded_market_ids),
        n_markets_open=len(open_market_ids),
        abstained_bars=sum(row.abstained_bars for row in rows),
        explicit_abstain_bars=sum(
            1 for value in own.values() for kind in value.action_kinds.values() if kind == "abstain"
        ),
        decision_bars=sum(len(value.forecasts) for value in own.values()),
    )
    legs, deviations = _legs_and_deviations(
        agent_id=agent_id, pairs=pairs, markets=markets, interval=interval
    )
    entries = _calibration_entries(agent_id=agent_id, pairs=pairs, markets=markets)
    bins = reliability_bins(entries)
    blocks = [row.block_key for row in rows]
    total_bars = sum(row.n_forecast_bars for row in rows)
    return AgentResult(
        agent_id=agent_id,
        family=state.family,
        kind=state.kind,
        genome_hash=state.genome_hash,
        ruined=state.ruined,
        n_markets=len(rows),
        n_markets_traded=stats.n_markets_traded,
        n_markets_open=stats.n_markets_open,
        brier_tw_micro=weighted_mean_micro(
            [row.agent_brier_tw_micro for row in rows], [row.n_forecast_bars for row in rows]
        )
        if total_bars
        else 0,
        skill=bootstrap_lower_bound([row.skill_micro for row in rows], blocks, rng=stats_tree),
        pnl=bootstrap_lower_bound([row.realised_pnl_cents for row in rows], blocks, rng=stats_tree),
        pnl_cents=stats.pnl_cents,
        return_bp=stats.return_bp,
        max_drawdown_bp=stats.max_drawdown_bp,
        sharpe_milli=stats.sharpe_milli,
        turnover_cents=stats.turnover_cents,
        fill_ratio_ppm=stats.fill_ratio_ppm,
        fees_paid_cents=stats.fees_paid_cents,
        abstention_ppm=stats.abstention_ppm,
        explicit_abstain_ppm=stats.explicit_abstain_ppm,
        descriptors=descriptors(
            turnover_cents=stats.turnover_cents,
            bankroll_cents=bankroll_cents,
            n_markets_open=stats.n_markets_open,
            deviations_bp=deviations,
            abstention_ppm=stats.abstention_ppm,
            leg_lengths_bars=legs,
            categories_traded=len(categories_traded),
            categories_open=len(categories_open),
        ),
        calibration=calibration_bin_views(calibration_table(entries)),
        horizons=_horizon_buckets(
            agent_id=agent_id,
            pairs=pairs,
            markets=markets,
            bars_by_pair=bars_by_pair,
            interval=interval,
        ),
        research_units_spent=state.research_units_spent,
        pinball_skill=_pinball_skill(rows, stats_tree=stats_tree),
        exposure_by_kind=_exposure_by_kind(
            own=own, markets=markets, n_marked_bars=len(state.equities_cents)
        ),
        n_cash_events=sum(value.n_cash_events for value in own.values()),
        ece_ppm=ece_ppm(bins),
        sharpness_ppm=sharpness_ppm(bins),
    )


def _pinball_skill(rows: Sequence[PerMarket], *, stats_tree: RngTree) -> Interval | None:
    """The quantile half of an agent's score, over its continuous cells (17.6, ruling R163).

    ``None`` on a binary-only run, because a binary row has no quantile to be wrong about and section
    12.10 reports the column as ``n: 0`` there rather than as a zero interval.
    """
    cells = [row for row in rows if row.kind != "binary"]
    if not cells:
        return None
    values = [row.baseline_pinball_micro - row.pinball_micro for row in cells]
    return bootstrap_lower_bound(values, [row.block_key for row in cells], rng=stats_tree)


def _exposure_by_kind(
    *,
    own: Mapping[tuple[str, str], _PairState],
    markets: Mapping[str, _MarketState],
    n_marked_bars: int,
) -> tuple[tuple[str, int], ...]:
    """The mean absolute marked notional per kind, in cents, sorted by kind (12.3, ruling R163).

    The mean is over the bars the agent was marked at, so an agent that held nothing reports nothing and
    an agent that held one instrument for a tenth of the run reports a tenth of its notional. The
    position at a bar is the last ``filled.position_after`` at or before it, and the price is that bar's
    own ``market_priced`` close, which is exactly what the close phase marked it against (section 8.7).
    """
    if n_marked_bars <= 0:
        return ()
    totals: dict[str, int] = {}
    for (_, market_id), state in own.items():
        market = markets.get(market_id)
        if market is None or not state.fills:
            continue
        total = 0
        for bar_ms in market.bars_ms:
            position = _position_at_bar_end(state, bar_ms)
            if position == 0:
                continue
            total += abs(_notional_cents(market, position, market.close_bp[bar_ms]))
        if total:
            totals[market.kind] = totals.get(market.kind, 0) + total
    return tuple(
        (kind, round_half_up(total, n_marked_bars)) for kind, total in sorted(totals.items())
    )


def _notional_cents(market: _MarketState, position: int, price: int) -> int:
    """The marked notional of a position in cents (section 17.1), floored, unsigned by the caller.

    A binary is ``position * price_bp`` hundredths of a cent per contract, which is section 8.7's own
    ``position * mark_price_bp // 100``; a continuous instrument reads ``size_milli`` and
    ``price_ticks`` through the four-factor product, divided once (ruling R146).
    """
    if market.is_binary:
        return position * price // CENTS_PER_UNIT
    numerator = position * price * market.tick_size_micro * market.point_value_micro
    return numerator // NOTIONAL_CENTS_DENOMINATOR
