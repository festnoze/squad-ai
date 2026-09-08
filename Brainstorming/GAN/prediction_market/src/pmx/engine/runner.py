"""The bar loop: one run of a roster over a dataset (CONTRACTS_V2 sections 8.2, 9.2, 9.3 and 9.5).

``run_backtest`` is the only place the eight phases of section 8.2 happen, in that order, with that
purity. It owns the events section 9.3 assigns to it and no others: execution journals every cent it
moves, memory journals every write, the hive journals every entry, and the runner journals the bar, the
market, the observation, the decision, the forecast, the settlement, the mark and the run.

Three rules shape the loop and are worth stating where they are implemented:

* **Decision latency** (section 16.2). ``decide`` hands every order-producing action to
  ``Execution.place``, which queues it and reserves nothing; ``execute`` drains the queue of the
  instrument's **previous** bar. ``execute`` stays after ``observe``, which is less physical and is the
  only safe order: a fill at bar ``t``'s open lands in cash and in ``avg_cost_bp``, so an observation
  built after it would carry the price of a bar that has not completed. The drain is driven over
  ``Execution.pending_market_ids(t_ms=t)`` and not over the bar slice (ruling R131), because a market
  that settled at ``t - interval`` is in none of the slice's tuples and is still owed its
  ``order_rejected(not_tradable)``.
* **A ruined agent keeps being scored** (section 8.2). It receives no observation and no ``decide``
  call, and the runner still records ``forecast_recorded(carried=true)`` for every open market at every
  later bar, so ``settlement_applied.n_forecast_bars`` is equal across the roster and every agent's
  Brier is computed on the same bars as the market's own.
* **The two scored settle events are the runner's** (section 9.3). ``Execution`` never sees a forecast,
  so ``settled.market_brier_tw_micro`` and ``settlement_applied.agent_brier_tw_micro`` are computed here
  through ``pmx.scoring`` (E3), the same functions the projection uses. One implementation, one number.

* **A continuous instrument is the same loop** (amendment C1b, sections 17.2, 17.3 and 17.5). The
  settle phase drives ``Execution.apply_cash_events`` per instrument in canonical order and
  ``Execution.force_flat`` at ``last_bar(i)``, then the runner emits its own two events: one
  ``forecast_resolved`` per horizon whose realisation became public at this bar, and one
  ``instrument_closed`` per instrument that closed. The forecast record carries one statement per
  declared horizon: the pair the agent stated, the pair ruling R184 synthesises from
  ``MarketAction.prob_ppm``, the agent's previous statement, or the random walk. None of it runs on a
  binary run, where ``closing_ids`` is empty and every open market is a ``Market``.

What the runner does **not** do: build an ``RngTree`` (section 6.2 hands it one), build a
``LiquidityModel`` (section 16.1, ruling R139: it is handed one and checks it against the config), call
an LLM (only the gateway does), or read a clock.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import ClassVar, Protocol

from pmx import CONTRACT_VERSION, ENGINE_VERSION
from pmx import journal as _journal
from pmx.data.loader import read_json_file
from pmx.engine.calendar import KIND_BINARY, BarSlice, Calendar
from pmx.engine.execution import Execution
from pmx.engine.fees import (
    BINARY_POINT_VALUE_MICRO,
    BINARY_TICK_SIZE_MICRO,
    FEE_SCHEDULES,
    FeeSchedule,
)
from pmx.engine.liquidity import LiquidityModel
from pmx.engine.observation import (
    ResearchLedger,
    build_grant,
    build_observation,
    check_observation_size,
    render_observation_json,
)
from pmx.errors import DatasetHashMismatchError, InvalidConfigError, JournalError, LeakError
from pmx.journal import (
    ActionReceived,
    ActionRejected,
    AgentRuined,
    BarClosed,
    BarOpened,
    EquityMarked,
    FeeCharged,
    Filled,
    ForecastRecorded,
    Journal,
    JournalEvent,
    MarketListed,
    MarketPriced,
    ObservationBuilt,
    ReplyReceived,
    ResearchSpent,
    RunEnded,
    RunStarted,
    Settled,
    SettlementApplied,
    canonical_json,
    canonical_sha256,
    journal_hash_of_file,
    payload_field_names,
    read_journal,
    verify_journal,
)
from pmx.metrics.projection import RunHandle, RunProjection, project
from pmx.rng import RNG_ALGORITHM_VERSION, RngTree
from pmx.scoring import (
    QUANTILE_LEVELS_PPM,
    RANDOM_WALK_UP_PPM,
    ForecastBar,
    HorizonResolution,
    baseline_quantiles_ticks,
    brier_tw_micro,
    market_brier_tw_micro,
    resolve_horizon,
    signed_mean,
)
from pmx.types import (
    ACTION_KINDS,
    JOURNAL_ENCODING,
    JOURNAL_NEWLINE,
    LESSON_MAX_CHARS,
    LESSONS_PER_BAR_MAX,
    MS_PER_DAY,
    NOTES_MAX_CHARS,
    PPM_ONE,
    PRICE_MAX_BP,
    PRICE_MIN_BP,
    RESEARCH_KINDS,
    SETTLE_NO_BP,
    SETTLE_YES_BP,
    TTL_BARS_MAX,
    Actions,
    Dataset,
    HiveView,
    Lesson,
    Limits,
    Market,
    MarketAction,
    MemoryView,
    Observation,
    PortfolioView,
    PositionView,
    RejectReason,
    ResearchGrant,
    ResearchRequest,
    RunConfig,
    bar_of,
    interval_ms,
    market_set_hash,
    ppm_from_bp,
    round_half_up,
    sorted_agent_ids,
    sorted_market_ids,
)

__all__ = ("Agent", "ResolutionEvent", "RunHandle", "replay", "run_backtest")

#: Section 10.4's reputation window. ``REPUTATION_WINDOW_MARKETS`` is declared there as a constant of
#: ``pmx.agents.hive`` (A3, wave 3), which does not exist while the engine wave is being built, so the
#: number is restated here beside its one use. Reported as a contract issue: it belongs in ``pmx.types``
#: like every other number a test can pin.
REPUTATION_WINDOW_MARKETS = 50

#: The default probability of a market an agent has never stated one for (section 8.4).
CARRIED_DEFAULT_PPM = PPM_ONE // 2

#: Amendment C1b's two ``RejectReason`` values (section 8.4, ruling R157). ``pmx.types.RejectReason`` is
#: D1's and gains them at gate G2 (17.9); until then the two strings live here, beside their one use, and
#: they are legal in the journal because ``action_rejected.reason`` is a free string and not an enum.
REASON_BAD_HORIZON = "bad_horizon"
REASON_BAD_QUANTILES = "bad_quantiles"


def default_horizons_bars(interval_min: int) -> tuple[int, ...]:
    """Section 17.5's default horizons in bars: one bar, one day, one week, duplicates removed.

    ``pmx.types.default_horizons_bars`` is the declared home (ruling R188, gate G2) because
    ``RunConfig`` resolves the empty tuple before hashing. D1 has not landed it, so the arithmetic is
    restated here beside its one caller and reported as a contract issue; the day the name exists this
    function becomes a re-export.
    """
    span = interval_ms(interval_min)
    return tuple(sorted({1, max(1, MS_PER_DAY // span), max(1, 7 * MS_PER_DAY // span)}))


def run_horizons_bars(config: RunConfig) -> tuple[int, ...]:
    """``config.horizons_bars``, resolved to the defaults when empty (section 8.1, ruling R157).

    ``RunConfig.horizons_bars`` is amendment C1b's field and D1 lands it at gate G2, so it is read
    defensively: a config written before the field exists means "the defaults", which is exactly what an
    empty tuple means in the declared dataclass.
    """
    declared = getattr(config, "horizons_bars", ())
    if isinstance(declared, tuple) and declared:
        return tuple(sorted({int(value) for value in declared}))
    return default_horizons_bars(config.interval_min)


# --------------------------------------------------------------------------------------------------
# The journal classes ruling R164 gives ``pmx.journal`` at gate G2, bridged until it carries them
#
# ``forecast_resolved`` and ``instrument_closed`` are the runner's two amendment C1b events (section
# 9.3) and D7's dataclasses land with the schema's ``oneOf`` in the same gate G2 commit. Resolving the
# class by name and by capability means the runner writes D7's event the moment it exists and never
# silently drops a contracted field; the two bridges below are what it writes until then, exactly as
# ``pmx.engine.execution`` bridges ``cash_event_applied``. Reported as a contract issue: while the
# bridge is in use a journal that carries one of the three events is refused by ``read_journal`` and by
# ``journal.v2.json``, so a continuous run cannot be replayed until gate G2 lands them.
# --------------------------------------------------------------------------------------------------
@dataclass(frozen=True, slots=True, kw_only=True)
class _MarketListedC1b(MarketListed):
    """``market_listed`` with the eight instrument fields of amendment C1b (ruling R164).

    Written for a continuous instrument only: on a binary every one of the eight carries the default
    the projection reads when the field is absent, so a binary journal keeps the bytes it has today.
    """

    kind: str
    vendor: str
    symbol: str
    tick_size_micro: int
    point_value_micro: int
    session_calendar_id: str
    borrow_schedule_id: str | None
    carry_schedule_id: str | None


@dataclass(frozen=True, slots=True, kw_only=True)
class _ForecastRecordedC1b(ForecastRecorded):
    """``forecast_recorded`` with the continuous payload of section 17.5 (ruling R157).

    ``horizons`` items are ``{horizon_bars, up_probability_ppm, quantiles_ticks}`` mappings, which is
    the shape ``forecast.v1.json`` validates and the shape the projection reads back.
    """

    price_ref_ticks: int
    horizons: tuple[Mapping[str, object], ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class _ForecastResolvedC1b(JournalEvent):
    """``forecast_resolved`` (9.2 and 17.5): one resolved horizon of one ``(agent, instrument)``.

    Emitted at the settle phase of ``t_h``, the bar at which the realisation became public.
    """

    agent_id: str
    market_id: str
    forecast_bar_ms: int
    horizon_bars: int
    up_probability_ppm: int
    quantiles_ticks: tuple[int, ...] | None
    price_ref_ticks: int
    price_realised_ticks: int
    realised_sign: int
    directional_brier_micro: int
    pinball_micro: int | None
    baseline_pinball_micro: int
    carried: bool

    TYPE: ClassVar[str] = "forecast_resolved"
    PHASES: ClassVar[tuple[str, ...]] = ("settle",)


@dataclass(frozen=True, slots=True, kw_only=True)
class _InstrumentClosedC1b(JournalEvent):
    """``instrument_closed`` (9.2 and 17.3): one continuous instrument, once, at ``last_bar(i)``."""

    market_id: str
    kind: str
    reason: str
    last_price_ticks: int
    n_bars: int
    n_forecasts_unresolved: int

    TYPE: ClassVar[str] = "instrument_closed"
    PHASES: ClassVar[tuple[str, ...]] = ("settle",)


def _bridged(
    name: str, *, needs: tuple[str, ...], phases: tuple[str, ...], fallback: type[JournalEvent]
) -> type[JournalEvent]:
    """``pmx.journal``'s class of that name when it carries what the contract asks, else the bridge."""
    candidate = getattr(_journal, name, None)
    if isinstance(candidate, type) and issubclass(candidate, JournalEvent):
        carried = set(payload_field_names(candidate))
        if set(needs) <= carried and set(phases) <= set(candidate.PHASES):
            return candidate
    return fallback


_MARKET_LISTED_C1B = _bridged(
    "MarketListed",
    needs=("kind", "vendor", "symbol", "tick_size_micro", "point_value_micro"),
    phases=("open",),
    fallback=_MarketListedC1b,
)
_FORECAST_RECORDED_C1B = _bridged(
    "ForecastRecorded",
    needs=("price_ref_ticks", "horizons"),
    phases=("decide",),
    fallback=_ForecastRecordedC1b,
)
_FORECAST_RESOLVED = _bridged(
    "ForecastResolved",
    needs=("forecast_bar_ms", "horizon_bars", "directional_brier_micro"),
    phases=("settle",),
    fallback=_ForecastResolvedC1b,
)
_INSTRUMENT_CLOSED = _bridged(
    "InstrumentClosed",
    needs=("last_price_ticks", "n_forecasts_unresolved"),
    phases=("settle",),
    fallback=_InstrumentClosedC1b,
)


# --------------------------------------------------------------------------------------------------
# The collaborators the runner calls.
#
# Section 10.2 declares ``Agent``, ``Memory``, ``Hive`` and ``ResolutionEvent`` in files A1, A2 and A3
# own and section 11.1 declares ``Gateway`` and ``AgentReply`` in ``pmx.types`` (D1). None of those names
# exists while wave 2 is being built, and the runner cannot be annotated against a module that is not
# there. The protocols below are therefore the **structural view** of what the runner actually calls:
# every concrete agent, memory and hive of wave 3 satisfies them without importing anything from here,
# because a ``Protocol`` matches by shape. Reported as a contract issue: the four protocols and
# ``ResolutionEvent`` belong in a wave-1 file (section 11.1 already argues exactly that for ``Gateway``).
# --------------------------------------------------------------------------------------------------
class GenomeLike(Protocol):
    """What the runner needs of a genome: its family and its canonical dictionary (section 10.1).

    ``family`` is a **read-only** member, and that is not a detail: section 10.1's ``Genome`` is
    ``frozen=True``, and a protocol that declared a mutable attribute would be satisfied by no frozen
    dataclass at all. The runner reads it and never writes it, so read-only is also what it means.
    """

    @property
    def family(self) -> str: ...

    def to_dict(self) -> dict[str, object]: ...


class MemoryLike(Protocol):
    """What the runner needs of a memory (section 10.3): the read side and the two write paths.

    ``view`` is here because the runner hands the same object to E1's ``build_observation``, whose own
    protocol is the read side (section 8.3). One object, one shape, no cast.
    """

    @property
    def agent_id(self) -> str: ...

    def view(self, *, now_ms: int) -> MemoryView: ...
    def add_lesson(self, text: str, market_ids: tuple[str, ...], *, written_at_ms: int) -> None: ...
    def add_note(self, text: str, market_id: str | None, *, written_at_ms: int) -> None: ...
    def snapshot(self) -> dict[str, object]: ...
    def freeze(self) -> None: ...


class HiveLike(Protocol):
    """What the runner needs of a hive (section 10.4): the read side, the four writes, a snapshot.

    ``write_forecast`` carries amendment C1b's four keyword-only arguments (ruling R160), which the
    runner fills for a continuous instrument and leaves at their defaults for a binary.
    """

    def view(
        self,
        *,
        now_ms: int,
        agent_id: str,
        market_ids: Sequence[str],
        limits: Limits,
        live_coop: bool,
    ) -> HiveView: ...
    def write_forecast(
        self,
        *,
        agent_id: str,
        market_id: str,
        bar_ms: int,
        prob_ppm: int,
        resolved_at_ms: int,
        interval_min: int,
        horizon_bars: int = 0,
        quantiles_ticks: tuple[int, ...] | None = None,
        price_ref_ticks: int = 0,
        resolves_at_ms: int | None = None,
    ) -> object: ...
    def write_resolution(
        self,
        *,
        market_id: str,
        outcome: int,
        life_mean_price_bp: int,
        resolved_at_ms: int,
        interval_min: int,
    ) -> object: ...
    def write_lesson(
        self, *, agent_id: str, text: str, market_ids: tuple[str, ...], bar_ms: int, interval_min: int
    ) -> object: ...
    def write_reputation(
        self,
        *,
        agent_id: str,
        category: str,
        bar_ms: int,
        interval_min: int,
        n: int,
        skill_micro: int,
        pnl_cents: int,
    ) -> object: ...
    def snapshot(self) -> dict[str, object]: ...


class ReplyLike(Protocol):
    """What the runner needs of an ``AgentReply`` (section 11.1): its source, its error and its shape."""

    agent_id: str
    source: str
    error: str | None

    @property
    def raw(self) -> Mapping[str, object] | None: ...


class GatewayLike(Protocol):
    """What the runner needs of a ``Gateway`` (section 11.1): one call per bar for every observation."""

    def collect_replies(
        self, *, bar_ms: int, observations: Sequence[Observation], config: RunConfig
    ) -> tuple[ReplyLike, ...]: ...


@dataclass(frozen=True, slots=True)
class ResolutionEvent:
    """What an agent learns when a market it forecast or held settles (section 10.2).

    ``market_prices`` is the **as-of** price series (``market_priced.last_close_bp``), the one the agent
    could see when it stated each forecast and the one section 12.1 scores the market on, so an agent's
    own ledger and the engine's ``skill_micro`` cannot disagree about what the market said.
    """

    market_id: str
    category: str
    tags: tuple[str, ...]
    provider: str
    outcome: int
    resolved_at_ms: int
    close_at_ms: int
    created_at_ms: int
    forecasts: tuple[tuple[int, int], ...]
    market_prices: tuple[tuple[int, int], ...]
    realised_pnl_cents: int
    fees_cents: int
    agent_brier_tw_micro: int
    market_brier_tw_micro: int

    def to_dict(self) -> dict[str, object]:
        return {
            "market_id": self.market_id,
            "category": self.category,
            "tags": list(self.tags),
            "provider": self.provider,
            "outcome": self.outcome,
            "resolved_at_ms": self.resolved_at_ms,
            "close_at_ms": self.close_at_ms,
            "created_at_ms": self.created_at_ms,
            "forecasts": [[bar_ms, prob_ppm] for bar_ms, prob_ppm in self.forecasts],
            "market_prices": [[bar_ms, price_bp] for bar_ms, price_bp in self.market_prices],
            "realised_pnl_cents": self.realised_pnl_cents,
            "fees_cents": self.fees_cents,
            "agent_brier_tw_micro": self.agent_brier_tw_micro,
            "market_brier_tw_micro": self.market_brier_tw_micro,
        }


class Agent(Protocol):
    """What the runner calls on an agent (section 10.2), structurally.

    ``kind``, ``model`` and ``knowledge_cutoff_ms`` are members rather than arguments because
    ``run_started.roster`` journals them per agent and the runner has no other path to a model id. All
    seven are read-only for the reason :class:`GenomeLike`'s ``family`` is: the runner reads them, and a
    mutable declaration would refuse every agent that keeps them frozen.
    """

    @property
    def agent_id(self) -> str: ...
    @property
    def family(self) -> str: ...
    @property
    def genome(self) -> GenomeLike: ...
    @property
    def needs_gateway(self) -> bool: ...
    @property
    def kind(self) -> str: ...
    @property
    def model(self) -> str | None: ...
    @property
    def knowledge_cutoff_ms(self) -> int | None: ...

    def reset(self, *, rng: object, memory: MemoryLike | None, config: RunConfig) -> None: ...
    def observe(self, obs: Observation) -> None: ...
    def decide(self) -> Actions: ...
    def learn(self, event: ResolutionEvent) -> None: ...
    def snapshot(self) -> dict[str, object]: ...


def _reply_lesson_count(reply: ReplyLike) -> int:
    """How many lessons a gateway reply carried, from its raw payload alone (section 9.2).

    The runner counts the payload rather than the validated actions because ``reply_received`` is
    written before ``decide`` runs: it reports what arrived, and ``action_received.n_lessons`` reports
    what survived validation.
    """
    raw = reply.raw
    if raw is None:
        return 0
    lessons = raw.get("lessons")
    return len(lessons) if isinstance(lessons, list) else 0


# --------------------------------------------------------------------------------------------------
# Validation of one reply (section 8.4)
# --------------------------------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class _Rejection:
    """One refused item of one reply: the ``action_rejected`` payload minus its envelope."""

    market_id: str | None
    scope: str
    item_index: int
    reason: str
    detail: str


@dataclass(frozen=True, slots=True)
class _HorizonPair:
    """One validated ``HorizonForecast`` of section 17.5: a statement on one instrument's horizon."""

    market_id: str
    horizon_bars: int
    up_probability_ppm: int
    quantiles_ticks: tuple[int, ...] | None


@dataclass(frozen=True, slots=True)
class _Validated:
    """What survived validation of one agent's reply at one bar."""

    intents: tuple[tuple[int, MarketAction], ...]
    rejections: tuple[_Rejection, ...]
    research: ResearchRequest | None
    notes: str
    lessons: tuple[Lesson, ...]
    horizon_pairs: tuple[_HorizonPair, ...] = ()


def _validate_limit(action: MarketAction) -> tuple[str, str] | None:
    """The limit-order checks of section 8.4, in the order the reasons are declared."""
    if action.side is None:
        return (RejectReason.MISSING_FIELD.value, "limit needs a side")
    if action.side not in ("buy", "sell"):
        return (RejectReason.BAD_KIND.value, f"side {action.side!r}")
    if action.price_bp is None:
        return (RejectReason.MISSING_FIELD.value, "limit needs a price")
    if not PRICE_MIN_BP <= action.price_bp <= PRICE_MAX_BP:
        return (RejectReason.BAD_PRICE.value, f"price_bp {action.price_bp}")
    if action.size is None:
        return (RejectReason.MISSING_FIELD.value, "limit needs a size")
    if action.size < 1:
        return (RejectReason.BAD_SIZE.value, f"size {action.size}")
    if action.ttl_bars is None:
        return (RejectReason.MISSING_FIELD.value, "limit needs a ttl")
    if not 1 <= action.ttl_bars <= TTL_BARS_MAX:
        return (RejectReason.BAD_TTL.value, f"ttl_bars {action.ttl_bars}")
    return None


def _validate(
    actions: Actions,
    *,
    open_ids: Sequence[str],
    horizons: tuple[int, ...] = (),
    continuous_ids: frozenset[str] = frozenset(),
) -> _Validated:
    """Validate one ``Actions`` against sections 8.4 and 17.5: keep every valid item, refuse the rest.

    A partially invalid payload keeps its valid items (truncation, never a crash), one action per market
    per bar with the **first occurrence winning**, and every refusal carries the ``item_index`` of the
    item it refused so a rejection can be traced back to the intent that caused it.

    ``horizons`` and ``continuous_ids`` are the run's declared horizons and the open continuous
    instruments; both are empty on a binary run, where ``Actions.horizon_forecasts`` is ``()`` and the
    second loop does nothing.
    """
    open_set = frozenset(open_ids)
    seen: set[str] = set()
    intents: list[tuple[int, MarketAction]] = []
    rejections: list[_Rejection] = []
    for index, action in enumerate(actions.markets):
        failure: tuple[str, str] | None = None
        if action.market_id not in open_set:
            failure = (RejectReason.UNKNOWN_MARKET.value, action.market_id)
        elif action.market_id in seen:
            failure = (RejectReason.DUPLICATE.value, action.market_id)
        elif not 0 <= action.prob_ppm <= PPM_ONE:
            failure = (RejectReason.BAD_PROB.value, f"prob_ppm {action.prob_ppm}")
        elif action.kind not in ACTION_KINDS:
            failure = (RejectReason.BAD_KIND.value, f"kind {action.kind!r}")
        elif action.kind == "target" and action.target_position is None:
            failure = (RejectReason.MISSING_FIELD.value, "target needs a target_position")
        elif action.kind == "limit":
            failure = _validate_limit(action)
        if failure is None:
            seen.add(action.market_id)
            intents.append((index, action))
            continue
        reason, detail = failure
        rejections.append(
            _Rejection(
                market_id=action.market_id, scope="market", item_index=index, reason=reason, detail=detail
            )
        )
    notes = actions.notes
    if len(notes) > NOTES_MAX_CHARS:
        rejections.append(
            _Rejection(
                market_id=None,
                scope="notes",
                item_index=0,
                reason=RejectReason.NOTES_TOO_LONG.value,
                detail=f"{len(notes)} chars",
            )
        )
        notes = ""
    lessons: list[Lesson] = []
    for index, lesson in enumerate(actions.lessons):
        if len(lessons) >= LESSONS_PER_BAR_MAX:
            rejections.append(
                _Rejection(
                    market_id=None,
                    scope="lessons",
                    item_index=index,
                    reason=RejectReason.TOO_MANY_LESSONS.value,
                    detail=f"{len(actions.lessons)} lessons",
                )
            )
            continue
        if not 1 <= len(lesson.text) <= LESSON_MAX_CHARS:
            rejections.append(
                _Rejection(
                    market_id=None,
                    scope="lessons",
                    item_index=index,
                    reason=RejectReason.LESSON_TOO_LONG.value,
                    detail=f"{len(lesson.text)} chars",
                )
            )
            continue
        lessons.append(lesson)
    research = actions.research
    if research is not None and research.kind not in RESEARCH_KINDS:
        rejections.append(
            _Rejection(
                market_id=research.market_id,
                scope="research",
                item_index=0,
                reason=RejectReason.BAD_RESEARCH.value,
                detail=f"kind {research.kind!r}",
            )
        )
        research = None
    pairs = _validate_horizons(
        actions,
        stated_probs={action.market_id: action.prob_ppm for _, action in intents},
        horizons=horizons,
        continuous_ids=continuous_ids,
        rejections=rejections,
    )
    return _Validated(
        intents=tuple(intents),
        rejections=tuple(rejections),
        research=research,
        notes=notes,
        lessons=tuple(lessons),
        horizon_pairs=pairs,
    )


def _validate_horizons(
    actions: Actions,
    *,
    stated_probs: Mapping[str, int],
    horizons: tuple[int, ...],
    continuous_ids: frozenset[str],
    rejections: list[_Rejection],
) -> tuple[_HorizonPair, ...]:
    """The ``horizon_forecasts`` half of section 17.5's validation (ruling R157).

    ``Actions.horizon_forecasts`` is amendment C1b's field and D1 lands it at gate G2, so it is read
    defensively: an ``Actions`` written before the field exists states no pair and every horizon is
    carried. ``item_index`` indexes the ``horizon_forecasts`` array, and ``detail`` names the horizon,
    so a refusal is traceable to the pair that caused it even though the scope is ``market``.
    """
    declared = getattr(actions, "horizon_forecasts", ())
    if not isinstance(declared, tuple) or not declared:
        return ()
    allowed = frozenset(horizons)
    shortest = horizons[0] if horizons else 0
    seen: set[tuple[str, int]] = set()
    pairs: list[_HorizonPair] = []
    for index, item in enumerate(declared):
        market_id = str(getattr(item, "market_id", ""))
        horizon_bars = int(getattr(item, "horizon_bars", 0))
        up_ppm = int(getattr(item, "up_probability_ppm", 0))
        quantiles = getattr(item, "quantiles_ticks", None)
        key = (market_id, horizon_bars)
        failure: tuple[str, str] | None = None
        if market_id not in continuous_ids:
            failure = (RejectReason.UNKNOWN_MARKET.value, market_id)
        elif key in seen:
            failure = (RejectReason.DUPLICATE.value, f"{market_id} h{horizon_bars}")
        elif horizon_bars not in allowed:
            failure = (REASON_BAD_HORIZON, f"h{horizon_bars}")
        elif not 0 <= up_ppm <= PPM_ONE:
            failure = (RejectReason.BAD_PROB.value, f"up_probability_ppm {up_ppm}")
        elif quantiles is not None and not _monotone_quantiles(quantiles):
            failure = (REASON_BAD_QUANTILES, f"h{horizon_bars}")
        elif (
            horizon_bars == shortest
            and market_id in stated_probs
            and stated_probs[market_id] != up_ppm
        ):
            failure = (
                RejectReason.BAD_PROB.value,
                f"prob_ppm {stated_probs[market_id]} disagrees with h{horizon_bars} {up_ppm}",
            )
        if failure is None:
            seen.add(key)
            pairs.append(
                _HorizonPair(
                    market_id=market_id,
                    horizon_bars=horizon_bars,
                    up_probability_ppm=up_ppm,
                    quantiles_ticks=None if quantiles is None else tuple(int(q) for q in quantiles),
                )
            )
            continue
        reason, detail = failure
        rejections.append(
            _Rejection(
                market_id=market_id or None,
                scope="market",
                item_index=index,
                reason=reason,
                detail=detail,
            )
        )
    return tuple(pairs)


def _monotone_quantiles(quantiles: object) -> bool:
    """The five levels of ``QUANTILE_LEVELS_PPM``, non-decreasing and positive (ruling R159)."""
    if not isinstance(quantiles, tuple | list) or len(quantiles) != len(QUANTILE_LEVELS_PPM):
        return False
    values = [value for value in quantiles if isinstance(value, int) and not isinstance(value, bool)]
    if len(values) != len(QUANTILE_LEVELS_PPM):
        return False
    return all(values[i] <= values[i + 1] for i in range(len(values) - 1)) and values[0] >= 1


# --------------------------------------------------------------------------------------------------
# The run's own bookkeeping
# --------------------------------------------------------------------------------------------------
@dataclass(slots=True)
class _MarketRecord:
    """The market's own series inside the run: its as-of forecast and its per-bar close.

    ``closes_by_bar`` is the same series keyed by bar, which is what the horizon realisation of section
    17.5 reads: the close of the ``h``-th completed bar after the reference bar.
    """

    bars: list[ForecastBar]
    closes: list[int]
    closes_by_bar: dict[int, int] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class _Statement:
    """One agent's statement on one horizon of one continuous instrument at one bar (section 17.5)."""

    horizon_bars: int
    up_probability_ppm: int
    quantiles_ticks: tuple[int, ...] | None
    carried: bool
    price_ref_ticks: int
    resolves_at_ms: int | None

    def to_payload(self) -> dict[str, object]:
        """The ``forecast_recorded.horizons`` item of section 9.2 (``forecast.v1.json``'s shape)."""
        return {
            "horizon_bars": self.horizon_bars,
            "up_probability_ppm": self.up_probability_ppm,
            "quantiles_ticks": None
            if self.quantiles_ticks is None
            else list(self.quantiles_ticks),
        }


@dataclass(frozen=True, slots=True)
class _PendingHorizon:
    """One statement waiting for the bar at which its realisation becomes public (ruling R160)."""

    agent_id: str
    market_id: str
    forecast_bar_ms: int
    realise_bar_ms: int
    statement: _Statement


@dataclass(slots=True)
class _PairRecord:
    """One ``(agent, market)`` pair's forecasts and realised cash inside the run."""

    bars: list[ForecastBar]
    realised_cents: int = 0
    fees_cents: int = 0


@dataclass(slots=True)
class _Reputation:
    """One ``(agent, category)`` reputation window (section 10.4)."""

    skills_micro: list[int]
    pnl_cents: int = 0


def _roster_rows(roster: Sequence[Agent]) -> tuple[Mapping[str, object], ...]:
    """The ``run_started.roster`` payload: one row per agent, in agent order (sections 4.3 and 9.2)."""
    rows: list[Mapping[str, object]] = []
    for agent in sorted(roster, key=lambda item: item.agent_id):
        genome = agent.genome.to_dict()
        genome_hash = canonical_sha256(genome)
        rows.append(
            {
                "agent_id": agent.agent_id,
                "family": agent.family,
                "kind": agent.kind,
                "genome_hash": genome_hash,
                "genome": genome,
                "model": agent.model,
                "knowledge_cutoff_ms": agent.knowledge_cutoff_ms,
            }
        )
    return tuple(rows)


def _check_roster(roster: Sequence[Agent]) -> tuple[Agent, ...]:
    """The roster in canonical agent order, refusing an empty one and a duplicated id."""
    if not roster:
        raise InvalidConfigError("a run needs at least one agent")
    ids = [agent.agent_id for agent in roster]
    duplicates = sorted({agent_id for agent_id in ids if ids.count(agent_id) > 1})
    if duplicates:
        raise InvalidConfigError("two agents share an id", agent_ids=duplicates)
    return tuple(sorted(roster, key=lambda agent: agent.agent_id))


def _check_liquidity(config: RunConfig, liquidity: LiquidityModel) -> None:
    """A journal may not claim a liquidity it did not run under (section 16.1, ruling R112)."""
    declared = str(getattr(config, "liquidity", "historical"))
    declared_hash = str(getattr(config, "liquidity_params_hash", ""))
    if liquidity.model_id != declared:
        raise InvalidConfigError(
            "the liquidity model disagrees with the config",
            config_liquidity=declared,
            model_id=liquidity.model_id,
        )
    if liquidity.params_hash != declared_hash:
        raise InvalidConfigError(
            "the liquidity params hash disagrees with the config",
            config_liquidity_params_hash=declared_hash,
            params_hash=liquidity.params_hash,
        )


def _schedules_for(dataset: Dataset, market_ids: Sequence[str]) -> dict[str, FeeSchedule]:
    """The fee schedules the run's markets name, from the shipped rows of ``pmx.engine.fees``.

    ``FEE_SCHEDULES`` is E2's registry; section 8.8 ships the schedules as data but names no registry, so
    the name is E2's and this is its one reader in the engine. Reported as a contract issue.
    """
    wanted = {dataset.meta(market_id).fee_schedule_id for market_id in market_ids}
    return {
        schedule_id: FEE_SCHEDULES[schedule_id] for schedule_id in sorted(wanted) if schedule_id in FEE_SCHEDULES
    }


def _memory_provenance(
    config: RunConfig, *, journal_dir: Path, t0_ms: int
) -> tuple[str | None, int | None]:
    """The memory snapshot hash and source ``t1_ms`` of ``config.memory_from_run_id`` (section 8.1).

    Raises ``LeakError`` when the source run ended after this run starts: a snapshot taken from a run
    that covered the validation or the sealed months would inject resolved outcomes into a calibration
    table, and no as-of filter would see it.
    """
    source = config.memory_from_run_id
    if source is None:
        return None, None
    path = journal_dir / source / "manifest.json"
    if not path.exists():
        raise InvalidConfigError("memory_from_run_id names no run directory", run_id=source, path=str(path))
    document = read_json_file(path)
    if not isinstance(document, dict):
        raise InvalidConfigError("a run manifest is a JSON object", run_id=source)
    snapshots = document.get("memory_snapshots", {})
    source_t1 = document.get("t1_ms")
    if not isinstance(source_t1, int):
        raise InvalidConfigError("the source manifest carries no t1_ms", run_id=source)
    if source_t1 > t0_ms:
        raise LeakError(
            "a memory snapshot may only travel forward in time",
            memory_from_run_id=source,
            source_t1_ms=source_t1,
            t0_ms=t0_ms,
        )
    return canonical_sha256(snapshots), source_t1


class _TailJournal(Journal):
    """D7's :class:`~pmx.journal.Journal`, plus the events appended since the last read.

    The runner writes ``settlement_applied.realised_pnl_cents`` and reads the fills and fees
    ``Execution`` journaled to build it (section 8.7), rather than keeping a second ledger that could
    disagree with the journal. The obvious way to read them is ``journal.events[first_seq - 1:]``, and
    it is quadratic: ``Journal.events`` copies the **whole** journal into a tuple on every access, so a
    run of a few thousand bars over a few hundred markets spends minutes copying pointers. This
    subclass keeps the tail as it is appended and hands it over once, which is the same events in
    constant amortised time. Reported as a contract issue: ``Journal`` could expose the tail itself.
    """

    def __init__(self, run_id: str, path: Path | None = None) -> None:
        super().__init__(run_id, path)
        self._tail: list[JournalEvent] = []

    def append(self, event: JournalEvent) -> JournalEvent:
        appended = super().append(event)
        self._tail.append(appended)
        return appended

    def take_tail(self) -> tuple[JournalEvent, ...]:
        """The events appended since the last call, and forget them."""
        tail = tuple(self._tail)
        self._tail.clear()
        return tail


def _optional_id(base: object, name: str) -> str | None:
    """A schedule id read off an instrument record, ``None`` when absent or empty (section 17.1)."""
    value = getattr(base, name, None)
    return value if isinstance(value, str) and value != "" else None


def _write_text(path: Path, payload: str) -> None:
    """Write one artefact, LF and UTF-8 without a BOM (section 4.2)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding=JOURNAL_ENCODING, newline=JOURNAL_NEWLINE) as handle:
        handle.write(payload)


def run_backtest(
    dataset: Dataset,
    roster: Sequence[Agent],
    config: RunConfig,
    *,
    tree: RngTree,
    journal_dir: Path,
    liquidity: LiquidityModel,
    gateway: GatewayLike | None = None,
    memory: Mapping[str, MemoryLike] | None = None,
    hive: HiveLike | None = None,
    dump_observations: bool = False,
) -> RunHandle:
    """Run one backtest and return its handle (sections 8.2, 9.5 and 12.11).

    Args:
        dataset: The sealed (or demo) dataset the run reads. The runner opens no other file.
        roster: The agents, in any order; the run sorts them by ``agent_id`` (section 3).
        config: The run's config. ``market_ids_hash`` must equal the hash of the market set the run
            carries, and ``interval_min`` must equal the dataset's and every market's.
        tree: The run's ``RngTree``, built by the caller as ``RngTree(config.seed)`` (section 6.2). The
            runner consumes no randomness of its own; it hands each agent its ``agent.<agent_id>``
            substream at ``reset``.
        journal_dir: The directory the run directory is created inside (``runs/`` in practice).
        liquidity: The run's liquidity model, required and keyword-only (ruling R139).
        gateway: The gateway for LLM agents, or ``None`` for a scripted-only run.
        memory: One ``Memory`` per ``agent_id``, or ``None`` to run with no memory at all, which is what
            wave 2's scripted-stub gate run produces.
        hive: The run's hive, or ``None`` for no hive.
        dump_observations: Write ``observations/<bar_ms>-<agent_id>.json`` for the leak audit.

    Returns:
        The :class:`~pmx.metrics.projection.RunHandle`: the run id, its directory, the journal and its
        hash, the projection, and the counts a caller reports.

    Raises:
        InvalidConfigError: On a config that disagrees with the dataset, the market set or the model.
        DatasetHashMismatchError: On a ``market_ids_hash`` that is not the run's market set.
        LeakError: On a memory snapshot from a run that ended after this one starts.
    """
    agents = _check_roster(roster)
    _check_liquidity(config, liquidity)
    calendar = Calendar(dataset, config)
    market_ids = calendar.market_ids()
    if config.market_ids_hash == "":
        raise InvalidConfigError("config.market_ids_hash must be set by the caller (section 8.1)")
    recomputed = market_set_hash(market_ids)
    if recomputed != config.market_ids_hash:
        raise DatasetHashMismatchError(
            "config.market_ids_hash is not the hash of the run's market set",
            expected=recomputed,
            declared=config.market_ids_hash,
        )
    span = interval_ms(config.interval_min)
    t0_ms, t1_ms = calendar.t0_ms, calendar.t1_ms
    memory_hash, memory_from_run_t1_ms = _memory_provenance(
        config, journal_dir=journal_dir, t0_ms=t0_ms
    )

    config_hash = canonical_sha256(config.to_dict())
    run_id = f"r-{dataset.manifest.dataset_hash[:8]}-{config.seed}-{config_hash[:8]}"
    run_dir = journal_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    journal_path = run_dir / "journal.jsonl"

    rows = _roster_rows(agents)
    agent_ids = sorted_agent_ids(agent.agent_id for agent in agents)
    by_id = {agent.agent_id: agent for agent in agents}

    journal = _TailJournal(run_id, journal_path)
    schedules = _schedules_for(dataset, market_ids)
    execution = Execution(
        journal=journal, config=config, schedules=schedules, liquidity=liquidity
    )
    research = ResearchLedger(config, agent_ids)

    journal.emit(
        RunStarted,
        bar_ms=0,
        seed=config.seed,
        engine_version=ENGINE_VERSION,
        contract_version=CONTRACT_VERSION,
        rng_algorithm_version=RNG_ALGORITHM_VERSION,
        dataset_name=dataset.manifest.name,
        dataset_hash=dataset.manifest.dataset_hash,
        interval_min=config.interval_min,
        t0_ms=t0_ms,
        t1_ms=t1_ms,
        market_ids=market_ids,
        config=config.to_dict(),
        config_hash=config_hash,
        folds={
            "train_end_ms": dataset.manifest.split.train_end_ms,
            "validation_end_ms": dataset.manifest.split.validation_end_ms,
        },
        memory_from_run_id=config.memory_from_run_id,
        memory_hash=memory_hash,
        memory_from_run_t1_ms=memory_from_run_t1_ms,
        contamination_hash=config.contamination_hash,
        roster=rows,
    )

    for agent_id in agent_ids:
        agent = by_id[agent_id]
        own_memory = None if memory is None else memory.get(agent_id)
        if own_memory is not None and config.memory_frozen:
            own_memory.freeze()
        execution.register_agent(agent_id)
        agent.reset(
            rng=tree.child(f"agent/{agent_id}").substream(f"agent.{agent_id}"),
            memory=own_memory,
            config=config,
        )

    state = _RunState(
        agent_ids=agent_ids,
        by_id=by_id,
        calendar=calendar,
        config=config,
        dataset=dataset,
        execution=execution,
        hive=hive,
        horizons=run_horizons_bars(config),
        journal=journal,
        memory=memory,
        research=research,
        span=span,
        gateway=gateway,
        run_dir=run_dir,
        dump_observations=dump_observations,
    )

    n_bars = 0
    last_bar_ms = t0_ms
    for bar in calendar.bars():
        state.run_bar(bar)
        last_bar_ms = bar.t_ms
        n_bars += 1

    journal.emit(
        RunEnded,
        bar_ms=t1_ms,
        reason="completed",
        final_bar_ms=last_bar_ms,
        n_bars=n_bars,
        event_count=journal.next_seq,
        ruined_agent_ids=execution.ruined_agent_ids(),
    )
    events = journal.events
    journal.close()

    journal_hash = journal_hash_of_file(journal_path)
    _write_text(run_dir / "journal.sha256", f"{journal_hash}  journal.jsonl{JOURNAL_NEWLINE}")
    projection = project(events)
    _write_text(run_dir / "results.json", canonical_json(projection.to_dict()) + JOURNAL_NEWLINE)
    _write_text(
        run_dir / "manifest.json",
        canonical_json(
            {
                "run_id": run_id,
                "kind": "backtest",
                "seed": config.seed,
                "dataset_name": dataset.manifest.name,
                "dataset_hash": dataset.manifest.dataset_hash,
                "market_ids_hash": config.market_ids_hash,
                "fold": config.fold,
                "t0_ms": t0_ms,
                "t1_ms": t1_ms,
                "config": config.to_dict(),
                "config_hash": config_hash,
                "roster": list(rows),
                "journal_hash": journal_hash,
                "engine_version": ENGINE_VERSION,
                "contract_version": CONTRACT_VERSION,
                "rng_algorithm_version": RNG_ALGORITHM_VERSION,
                "memory_snapshots": {
                    agent_id: snapshot.snapshot()
                    for agent_id, snapshot in sorted((memory or {}).items())
                },
                "agent_snapshots": {agent_id: by_id[agent_id].snapshot() for agent_id in agent_ids},
                "hive_snapshot": None if hive is None else hive.snapshot(),
                "memory_hash": memory_hash,
            }
        )
        + JOURNAL_NEWLINE,
    )
    return RunHandle(
        run_id=run_id,
        run_dir=run_dir,
        journal_path=journal_path,
        journal_hash=journal_hash,
        dataset_hash=dataset.manifest.dataset_hash,
        config_hash=config_hash,
        projection=projection,
        n_events=len(events),
        n_bars=n_bars,
        ruined_agent_ids=execution.ruined_agent_ids(),
    )


@dataclass(slots=True)
class _RunState:
    """Everything one run carries between its bars, so the phase methods read like section 8.2."""

    agent_ids: tuple[str, ...]
    by_id: Mapping[str, Agent]
    calendar: Calendar
    config: RunConfig
    dataset: Dataset
    execution: Execution
    hive: HiveLike | None
    horizons: tuple[int, ...]
    journal: _TailJournal
    memory: Mapping[str, MemoryLike] | None
    research: ResearchLedger
    span: int
    gateway: GatewayLike | None
    run_dir: Path
    dump_observations: bool
    listed: set[str] = field(default_factory=set)
    markets: dict[str, _MarketRecord] = field(default_factory=dict)
    pairs: dict[tuple[str, str], _PairRecord] = field(default_factory=dict)
    last_prob: dict[tuple[str, str], int] = field(default_factory=dict)
    pending_research: dict[str, ResearchRequest] = field(default_factory=dict)
    reputations: dict[tuple[str, str], _Reputation] = field(default_factory=dict)
    as_of: dict[str, int] = field(default_factory=dict)
    stated_horizons: dict[tuple[str, str, int], tuple[int, tuple[int, ...] | None]] = field(
        default_factory=dict
    )
    pending_horizons: dict[int, list[_PendingHorizon]] = field(default_factory=dict)
    unresolved: dict[str, int] = field(default_factory=dict)
    bar_horizons: dict[tuple[str, str], tuple[_Statement, ...]] = field(default_factory=dict)
    bar_lessons: list[tuple[str, str, tuple[str, ...]]] = field(default_factory=list)

    # ---- helpers --------------------------------------------------------------------------------
    def market(self, market_id: str) -> Market:
        return self.dataset.market(market_id)

    def record(self, market_id: str) -> _MarketRecord:
        found = self.markets.get(market_id)
        if found is None:
            found = _MarketRecord(bars=[], closes=[])
            self.markets[market_id] = found
        return found

    def pair(self, agent_id: str, market_id: str) -> _PairRecord:
        key = (agent_id, market_id)
        found = self.pairs.get(key)
        if found is None:
            found = _PairRecord(bars=[])
            self.pairs[key] = found
        return found

    def kind_of(self, market_id: str) -> str:
        """The instrument's kind, from E1's one implementation (ruling R144)."""
        return self.calendar.kind_of(market_id)

    def continuous_ids(self, market_ids: Sequence[str]) -> tuple[str, ...]:
        """The continuous instruments of a set, in canonical market order (sections 3 and 17.2)."""
        return tuple(
            market_id for market_id in market_ids if self.kind_of(market_id) != KIND_BINARY
        )

    def portfolio_of(self, agent_id: str) -> PortfolioView:
        """The agent's portfolio with the research budget the runner owns filled in (section 8.3)."""
        view = self.execution.portfolio(agent_id)
        return replace(view, research_units_remaining=self.research.remaining(agent_id))

    # ---- the eight phases -----------------------------------------------------------------------
    def run_bar(self, bar: BarSlice) -> None:
        """One bar, phases 1 to 8 of section 8.2, in that order and no other."""
        first_seq = self.journal.next_seq
        self.bar_horizons.clear()
        self.bar_lessons.clear()
        open_markets = [self.market(market_id) for market_id in bar.open_ids]
        self.phase_open(bar, open_markets)
        observations = self.phase_observe(bar)
        self.phase_decide(bar, observations)
        self.phase_execute(bar)
        settled = self.phase_settle(bar)
        self.phase_learn(settled)
        self.phase_hive(bar, settled)
        self.phase_close(bar, open_markets, first_seq)

    def phase_open(self, bar: BarSlice, open_markets: Sequence[Market]) -> None:
        """List, price and expire (phase 1). Every event here is an observed input, never a derived one."""
        t_ms = bar.t_ms
        self.journal.emit(
            BarOpened,
            bar_ms=t_ms,
            open_market_ids=bar.open_ids,
            tradable_market_ids=bar.tradable_ids,
            settling_market_ids=bar.settling_ids,
            listed_market_ids=bar.listed_ids,
        )
        for market_id in bar.listed_ids:
            if market_id in self.listed:
                continue
            self.listed.add(market_id)
            self._emit_listed(market_id, t_ms)
        for market in open_markets:
            current = market.bar_at(t_ms)
            if current is None:
                raise JournalError("an open market has no bar at its own bar", market_id=market.id, bar_ms=t_ms)
            completed = market.bars_before(t_ms, 1)
            last_close_bp = completed[-1].close_bp if completed else market.first_price_bp
            self.as_of[market.id] = last_close_bp
            record = self.record(market.id)
            record.bars.append(
                ForecastBar(
                    t_ms=t_ms, prob_ppm=ppm_from_bp(last_close_bp), market_price_bp=last_close_bp
                )
            )
            record.closes.append(current.close_bp)
            record.closes_by_bar[t_ms] = current.close_bp
            self.journal.emit(
                MarketPriced,
                bar_ms=t_ms,
                market_id=market.id,
                close_bp=current.close_bp,
                last_close_bp=last_close_bp,
                vwap_bp=current.vwap_bp,
                volume_milli=current.volume_milli,
            )
        self.execution.expire_orders(t_ms=t_ms, markets=open_markets)

    def _emit_listed(self, market_id: str, t_ms: int) -> None:
        """``market_listed`` once per instrument, with amendment C1b's eight fields when it has them.

        A binary emits exactly the eleven fields of the v2 catalogue, so no byte of a binary journal
        moves; a continuous instrument emits the eight of ruling R164 as well, read off its own record,
        and its ``close_at_ms`` is ``delisted_at_ms`` (``0`` when unset), which is what section 9.2 says
        and what 8.3 forbids an observation from carrying (ruling R181).
        """
        meta = self.dataset.meta(market_id)
        kind = self.kind_of(market_id)
        if kind == KIND_BINARY:
            self.journal.emit(
                MarketListed,
                bar_ms=t_ms,
                market_id=market_id,
                provider=meta.provider,
                category=meta.category,
                tags=meta.tags,
                event_key=meta.event_key,
                created_at_ms=meta.created_at_ms,
                close_at_ms=meta.close_at_ms,
                interval_min=meta.interval_min,
                fee_schedule_id=meta.fee_schedule_id,
                hardness_tags=meta.hardness_tags,
                fold=meta.fold,
            )
            return
        instrument = self.market(market_id)
        base: object = getattr(instrument, "instrument", instrument)
        delisted = getattr(instrument, "delisted_at_ms", None)
        self.journal.emit(
            _MARKET_LISTED_C1B,
            bar_ms=t_ms,
            market_id=market_id,
            provider=meta.provider,
            category=meta.category,
            tags=meta.tags,
            event_key=meta.event_key,
            created_at_ms=meta.created_at_ms,
            close_at_ms=int(delisted) if isinstance(delisted, int) else 0,
            interval_min=meta.interval_min,
            fee_schedule_id=meta.fee_schedule_id,
            hardness_tags=meta.hardness_tags,
            fold=meta.fold,
            kind=kind,
            vendor=str(getattr(base, "vendor", meta.provider)),
            symbol=str(getattr(base, "symbol", market_id)),
            tick_size_micro=int(getattr(base, "tick_size_micro", BINARY_TICK_SIZE_MICRO)),
            point_value_micro=int(getattr(base, "point_value_micro", BINARY_POINT_VALUE_MICRO)),
            session_calendar_id=str(getattr(base, "session_calendar_id", "continuous")),
            borrow_schedule_id=_optional_id(base, "borrow_schedule_id"),
            carry_schedule_id=_optional_id(base, "carry_schedule_id"),
        )

    def phase_observe(self, bar: BarSlice) -> dict[str, Observation]:
        """One observation per non-ruined agent, with the as-of filter of section 5.4 (phase 2)."""
        t_ms = bar.t_ms
        open_markets = [self.market(market_id) for market_id in bar.open_ids]
        news = self.dataset.news_global(t_ms)
        observations: dict[str, Observation] = {}
        for agent_id in self.agent_ids:
            if self.execution.is_ruined(agent_id):
                continue
            grants = self._grants_for(agent_id, t_ms)
            positions: dict[str, PositionView] = {
                market.id: self.execution.position(agent_id, market.id) for market in open_markets
            }
            observation = build_observation(
                agent_id=agent_id,
                now_ms=t_ms,
                config=self.config,
                markets=open_markets,
                positions=positions,
                portfolio=self.portfolio_of(agent_id),
                memory=None if self.memory is None else self.memory.get(agent_id),
                hive=self.hive,
                news=news,
                grants=grants,
            )
            observations[agent_id] = observation
            payload = render_observation_json(observation)
            size = check_observation_size(payload, agent_id=agent_id, now_ms=t_ms)
            hive_view = observation.hive
            self.journal.emit(
                ObservationBuilt,
                bar_ms=t_ms,
                agent_id=agent_id,
                n_markets=len(observation.markets),
                n_news=len(observation.news),
                n_hive=len(hive_view.lessons)
                + len(hive_view.reputations)
                + len(hive_view.resolutions)
                + len(hive_view.forecasts)
                + len(hive_view.prev_bar_forecasts),
                n_bars_max=max((len(view.bars) for view in observation.markets), default=0),
                research_remaining=self.research.remaining(agent_id),
                bytes=size,
                obs_sha256=canonical_sha256(observation.to_dict()),
            )
            if self.dump_observations:
                _write_text(self.run_dir / "observations" / f"{t_ms}-{agent_id}.json", payload + JOURNAL_NEWLINE)
        return observations

    def _grants_for(self, agent_id: str, t_ms: int) -> tuple[ResearchGrant, ...]:
        """The research granted to this agent at this bar: what it asked for at the previous one (8.2)."""
        request = self.pending_research.pop(agent_id, None)
        if request is None:
            return ()
        market_id = request.market_id
        if request.kind == "history" and market_id is not None:
            grant = build_grant(
                request=request,
                granted_at_ms=t_ms,
                config=self.config,
                trades=self.market(market_id).trades,
            )
        elif request.kind == "wiki_asof" and market_id is not None:
            grant = build_grant(
                request=request,
                granted_at_ms=t_ms,
                config=self.config,
                background=self.dataset.background_for(market_id, t_ms),
            )
        else:
            items = (
                self.dataset.news_for(market_id, t_ms)
                if market_id is not None
                else self.dataset.news_global(t_ms)
            )
            grant = build_grant(request=request, granted_at_ms=t_ms, config=self.config, news=items)
        return (grant,)

    def phase_decide(self, bar: BarSlice, observations: Mapping[str, Observation]) -> None:
        """Observe, decide, validate, forecast, spend research and queue every order (phase 3)."""
        t_ms = bar.t_ms
        replies = self._collect_replies(t_ms, observations)
        for agent_id in self.agent_ids:
            observation = observations.get(agent_id)
            if observation is None:
                self._record_forecasts(agent_id, bar, stated={})
                continue
            agent = self.by_id[agent_id]
            agent.observe(observation)
            reply = replies.get(agent_id)
            if reply is not None:
                self.journal.emit(
                    ReplyReceived,
                    bar_ms=t_ms,
                    agent_id=agent_id,
                    source=reply.source,
                    error=reply.error,
                    schema_valid=reply.raw is not None,
                    n_lessons=_reply_lesson_count(reply),
                )
            actions = agent.decide()
            validated = _validate(
                actions,
                open_ids=bar.open_ids,
                horizons=self.horizons,
                continuous_ids=frozenset(self.continuous_ids(bar.open_ids)),
            )
            source = "scripted" if reply is None else reply.source
            self.journal.emit(
                ActionReceived,
                bar_ms=t_ms,
                agent_id=agent_id,
                source=source,
                intents=tuple(action.to_dict() for _, action in validated.intents),
                research=None if validated.research is None else validated.research.to_dict(),
                notes=validated.notes,
                n_lessons=len(validated.lessons),
                n_rejected=len(validated.rejections),
            )
            for rejection in validated.rejections:
                self.journal.emit(
                    ActionRejected,
                    bar_ms=t_ms,
                    agent_id=agent_id,
                    market_id=rejection.market_id,
                    scope=rejection.scope,
                    item_index=rejection.item_index,
                    reason=rejection.reason,
                    detail=rejection.detail,
                )
            self._record_forecasts(
                agent_id,
                bar,
                stated={action.market_id: action.prob_ppm for _, action in validated.intents},
                pairs=validated.horizon_pairs,
            )
            self._spend_research(agent_id, t_ms, validated.research)
            self._write_lessons(agent_id, t_ms, validated)
            for item_index, action in validated.intents:
                if action.kind == "hold":
                    continue
                self.execution.place(
                    agent_id=agent_id,
                    market=self.market(action.market_id),
                    action=action,
                    item_index=item_index,
                    t_ms=t_ms,
                )

    def _collect_replies(
        self, t_ms: int, observations: Mapping[str, Observation]
    ) -> dict[str, ReplyLike]:
        """One gateway call per bar, covering every LLM agent's observation (section 11.3)."""
        if self.gateway is None:
            return {}
        wanted = [
            observations[agent_id]
            for agent_id in self.agent_ids
            if agent_id in observations and self.by_id[agent_id].needs_gateway
        ]
        if not wanted:
            return {}
        replies = self.gateway.collect_replies(bar_ms=t_ms, observations=wanted, config=self.config)
        return {reply.agent_id: reply for reply in replies}

    def _record_forecasts(
        self,
        agent_id: str,
        bar: BarSlice,
        *,
        stated: Mapping[str, int],
        pairs: Sequence[_HorizonPair] = (),
    ) -> None:
        """One ``forecast_recorded`` per open market, carried when the agent did not state one (8.2).

        On a continuous instrument the event also carries ``price_ref_ticks`` and one ``horizons`` item
        per declared horizon (section 17.5): a stated pair, the pair ruling R184 synthesises from
        ``MarketAction.prob_ppm``, the agent's previous statement, or the random walk.
        """
        by_market: dict[str, dict[int, _HorizonPair]] = {}
        for pair in pairs:
            by_market.setdefault(pair.market_id, {})[pair.horizon_bars] = pair
        for market_id in bar.open_ids:
            key = (agent_id, market_id)
            if market_id in stated:
                prob_ppm = stated[market_id]
                carried = False
            else:
                prob_ppm = self.last_prob.get(key, CARRIED_DEFAULT_PPM)
                carried = True
            self.last_prob[key] = prob_ppm
            price_bp = self.as_of[market_id]
            self.pair(agent_id, market_id).bars.append(
                ForecastBar(t_ms=bar.t_ms, prob_ppm=prob_ppm, market_price_bp=price_bp)
            )
            if self.kind_of(market_id) == KIND_BINARY:
                self.journal.emit(
                    ForecastRecorded,
                    bar_ms=bar.t_ms,
                    agent_id=agent_id,
                    market_id=market_id,
                    prob_ppm=prob_ppm,
                    carried=carried,
                )
                continue
            statements = self._horizon_statements(
                agent_id=agent_id,
                market_id=market_id,
                t_ms=bar.t_ms,
                pairs=by_market.get(market_id, {}),
                stated_prob=stated.get(market_id),
                price_ref_ticks=price_bp,
            )
            self.bar_horizons[key] = statements
            self.journal.emit(
                _FORECAST_RECORDED_C1B,
                bar_ms=bar.t_ms,
                agent_id=agent_id,
                market_id=market_id,
                prob_ppm=prob_ppm,
                carried=carried,
                price_ref_ticks=price_bp,
                horizons=tuple(statement.to_payload() for statement in statements),
            )

    def _horizon_statements(
        self,
        *,
        agent_id: str,
        market_id: str,
        t_ms: int,
        pairs: Mapping[int, _HorizonPair],
        stated_prob: int | None,
        price_ref_ticks: int,
    ) -> tuple[_Statement, ...]:
        """One statement per declared horizon, and the queue entry that resolves it (section 17.5).

        The four sources are, in this order: the pair the agent stated; the pair ruling R184 synthesises
        from ``MarketAction.prob_ppm`` for the **shortest** horizon of a market the agent addressed, so a
        family that states only a probability states a direction; the agent's previous statement on that
        pair; and the random walk, whose ``up_probability_ppm`` is ``500_000`` and whose five quantiles
        are the reference price, which is what a silent agent means and what scores ``0`` skill.
        """
        shortest = self.horizons[0] if self.horizons else 0
        statements: list[_Statement] = []
        for horizon_bars in self.horizons:
            pair = pairs.get(horizon_bars)
            key = (agent_id, market_id, horizon_bars)
            quantiles: tuple[int, ...] | None
            if pair is not None:
                up_ppm, quantiles, carried = pair.up_probability_ppm, pair.quantiles_ticks, False
                self.stated_horizons[key] = (up_ppm, quantiles)
            elif horizon_bars == shortest and stated_prob is not None:
                up_ppm, quantiles, carried = stated_prob, None, False
                self.stated_horizons[key] = (up_ppm, quantiles)
            else:
                previous = self.stated_horizons.get(key)
                if previous is None:
                    # The random walk is defined **against the current reference price** (ruling R158),
                    # so it is rebuilt every bar and never remembered: a memoised one would carry the
                    # first bar's quantiles forward, and a silent agent's pinball skill would drift away
                    # from the zero the baseline's own identity asserts.
                    up_ppm = RANDOM_WALK_UP_PPM
                    quantiles = baseline_quantiles_ticks(price_ref_ticks)
                else:
                    up_ppm, quantiles = previous
                carried = True
            resolves = self._resolution_bars(market_id, t_ms, horizon_bars)
            statement = _Statement(
                horizon_bars=horizon_bars,
                up_probability_ppm=up_ppm,
                quantiles_ticks=quantiles,
                carried=carried,
                price_ref_ticks=price_ref_ticks,
                resolves_at_ms=None if resolves is None else resolves[1],
            )
            statements.append(statement)
            if resolves is None:
                # A horizon beyond the run's last bar of the instrument never resolves and is not
                # scored; ``instrument_closed.n_forecasts_unresolved`` reports it (ruling R160).
                self.unresolved[market_id] = self.unresolved.get(market_id, 0) + 1
                continue
            realise_bar_ms, public_bar_ms = resolves
            self.pending_horizons.setdefault(public_bar_ms, []).append(
                _PendingHorizon(
                    agent_id=agent_id,
                    market_id=market_id,
                    forecast_bar_ms=t_ms,
                    realise_bar_ms=realise_bar_ms,
                    statement=statement,
                )
            )
        return tuple(statements)

    def _resolution_bars(self, market_id: str, t_ms: int, horizon_bars: int) -> tuple[int, int] | None:
        """``(the bar whose close is the realisation, the bar it becomes public at)`` (section 17.5).

        The realisation of a horizon ``h`` stated at bar ``t`` is the close of the bar ``h - 1`` bars
        after ``t`` on the **instrument's own** sequence, and it becomes public at the open of the bar
        ``h`` bars after ``t``. ``Calendar.next_bar`` is the one implementation of that step (ruling
        R187) and it is clamped by the run, so a horizon with no bar left returns ``None``.
        """
        realise = t_ms
        public = t_ms
        for _ in range(horizon_bars):
            nxt = self.calendar.next_bar(market_id, public)
            if nxt is None:
                return None
            realise, public = public, nxt
        return realise, public

    def _spend_research(self, agent_id: str, t_ms: int, request: ResearchRequest | None) -> None:
        """Price one request through the ledger and journal what it cost (sections 8.1 and 8.4)."""
        if request is None:
            return
        outcome = self.research.request(agent_id=agent_id, request=request)
        self.journal.emit(
            ResearchSpent,
            bar_ms=t_ms,
            agent_id=agent_id,
            kind=outcome.kind,
            market_id=outcome.market_id,
            units=outcome.units,
            remaining=outcome.remaining,
            granted=outcome.granted,
        )
        if outcome.granted:
            self.pending_research[agent_id] = request

    def _write_lessons(self, agent_id: str, t_ms: int, validated: _Validated) -> None:
        """Lessons and notes go to the agent's memory, and to the hive phase of the same bar.

        Memory journals every write (section 10.3); the hive entry is written in phase 7, one per
        lesson and note written this bar (section 8.2), which is why the texts are remembered here
        rather than re-derived from ``action_received``.
        """
        for lesson in validated.lessons:
            self.bar_lessons.append((agent_id, lesson.text, lesson.market_ids))
        if validated.notes:
            self.bar_lessons.append((agent_id, validated.notes, ()))
        own = None if self.memory is None else self.memory.get(agent_id)
        if own is None:
            return
        for lesson in validated.lessons:
            own.add_lesson(lesson.text, lesson.market_ids, written_at_ms=t_ms)
        if validated.notes:
            own.add_note(validated.notes, None, written_at_ms=t_ms)

    def phase_execute(self, bar: BarSlice) -> None:
        """Drain the queue of the instrument's previous bar (phase 4, section 16.2, ruling R131)."""
        t_ms = bar.t_ms
        self.journal.take_tail()
        for market_id in self.execution.pending_market_ids(t_ms=t_ms):
            self.execution.execute_bar(t_ms=t_ms, market=self.market(market_id))
        self._absorb_cash(self.journal.take_tail())

    def _absorb_cash(self, events: Sequence[JournalEvent]) -> None:
        """Accumulate the fills and fees execution just journaled into the per-pair realised cash.

        ``settlement_applied.realised_pnl_cents`` is "fills plus settlement minus fees on this market"
        (section 8.7), and the runner is the one that writes it, so it reads the events execution wrote
        rather than keeping a second ledger of its own.
        """
        for event in events:
            if isinstance(event, Filled):
                record = self.pair(event.agent_id, event.market_id)
                record.realised_cents += event.cash_delta_cents
            elif isinstance(event, FeeCharged):
                record = self.pair(event.agent_id, event.market_id)
                record.realised_cents -= event.fee_cents
                record.fees_cents += event.fee_cents

    def phase_settle(self, bar: BarSlice) -> tuple[tuple[str, int], ...]:
        """Settle every settling market and emit the two scored events (phase 5, section 9.3)."""
        t_ms = bar.t_ms
        settled: list[tuple[str, int]] = []
        for market_id in sorted_market_ids(bar.settling_ids):
            market = self.market(market_id)
            positions_before = {
                agent_id: self.execution.position(agent_id, market_id).position
                for agent_id in self.agent_ids
            }
            self.journal.take_tail()
            deltas = self.execution.settle(market=market)
            self._absorb_cash(self.journal.take_tail())
            record = self.record(market_id)
            outcome = market.resolution
            n_bars = len(record.bars)
            market_brier = market_brier_tw_micro(
                record.bars, outcome=outcome, interval_ms=self.span
            )
            self.journal.emit(
                Settled,
                bar_ms=t_ms,
                market_id=market_id,
                outcome=outcome,
                payout_bp=SETTLE_YES_BP if outcome == 1 else SETTLE_NO_BP,
                resolved_at_ms=market.resolved_at_ms,
                n_bars=n_bars,
                market_brier_tw_micro=market_brier,
                life_mean_price_bp=round_half_up(sum(record.closes), n_bars) if n_bars else 0,
            )
            for agent_id in self.agent_ids:
                pair = self.pairs.get((agent_id, market_id))
                delta = deltas.get(agent_id, 0)
                if pair is None and delta == 0 and positions_before[agent_id] == 0:
                    continue
                bars = () if pair is None else tuple(pair.bars)
                agent_brier = brier_tw_micro(bars, outcome=outcome, interval_ms=self.span)
                realised = (0 if pair is None else pair.realised_cents) + delta
                if pair is not None:
                    pair.realised_cents = realised
                self.journal.emit(
                    SettlementApplied,
                    bar_ms=t_ms,
                    agent_id=agent_id,
                    market_id=market_id,
                    position=positions_before[agent_id],
                    cash_delta_cents=delta,
                    cash_after_cents=self.execution.portfolio(agent_id).cash_cents,
                    realised_pnl_cents=realised,
                    agent_brier_tw_micro=agent_brier,
                    n_forecast_bars=len(bars),
                )
                self._note_reputation(
                    agent_id=agent_id,
                    market=market,
                    agent_brier=agent_brier,
                    market_brier=market_brier,
                    realised=realised,
                )
            settled.append((market_id, outcome))
        self._settle_continuous(bar)
        return tuple(settled)

    def _settle_continuous(self, bar: BarSlice) -> None:
        """The continuous half of phase 5, in the order section 8.2 lists it (amendment C1b).

        Per instrument in canonical order: the cash events whose application bar is this one
        (``Execution.apply_cash_events``, section 17.3), then the forced flat at ``last_bar(i)``
        (``Execution.force_flat``, ruling R150). Then the runner's own two events: one
        ``forecast_resolved`` per horizon whose realisation became public at this bar (17.5) and one
        ``instrument_closed`` per instrument that closed (17.3). Nothing here runs on a binary run:
        ``closing_ids`` is empty and no open market is continuous.
        """
        t_ms = bar.t_ms
        self.journal.take_tail()
        for market_id in self.continuous_ids(bar.open_ids):
            instrument = self.market(market_id)
            self.execution.apply_cash_events(t_ms=t_ms, market=instrument)
            if market_id in bar.closing_ids:
                self.execution.force_flat(t_ms=t_ms, market=instrument)
        self._absorb_cash(self.journal.take_tail())
        self._resolve_horizons(t_ms)
        for market_id in sorted_market_ids(bar.closing_ids):
            self._close_instrument(market_id, t_ms)

    def _resolve_horizons(self, t_ms: int) -> None:
        """``forecast_resolved`` for every horizon whose realisation became public at this bar (R160).

        In agent then instrument then forecast bar then horizon order (section 17.5). The two price
        lookups are the runner's (the reference is the close of the last completed bar at the forecast
        bar, the realisation the close of the ``h``-th completed bar after it) and every scored field is
        ``pmx.scoring``'s, so the journal and the projection cannot disagree about what a loss was.
        """
        pending = self.pending_horizons.pop(t_ms, None)
        if not pending:
            return
        for item in sorted(
            pending,
            key=lambda row: (
                row.agent_id,
                row.market_id,
                row.forecast_bar_ms,
                row.statement.horizon_bars,
            ),
        ):
            realised = self.record(item.market_id).closes_by_bar.get(item.realise_bar_ms)
            if realised is None:
                raise JournalError(
                    "a resolved horizon has no close at its realisation bar",
                    market_id=item.market_id,
                    realise_bar_ms=item.realise_bar_ms,
                )
            statement = item.statement
            resolution: HorizonResolution = resolve_horizon(
                forecast_bar_ms=item.forecast_bar_ms,
                horizon_bars=statement.horizon_bars,
                up_probability_ppm=statement.up_probability_ppm,
                quantiles_ticks=statement.quantiles_ticks,
                price_ref_ticks=statement.price_ref_ticks,
                price_realised_ticks=realised,
                carried=statement.carried,
            )
            self.journal.emit(
                _FORECAST_RESOLVED,
                bar_ms=t_ms,
                agent_id=item.agent_id,
                market_id=item.market_id,
                forecast_bar_ms=resolution.forecast_bar_ms,
                horizon_bars=resolution.horizon_bars,
                up_probability_ppm=resolution.up_probability_ppm,
                quantiles_ticks=resolution.quantiles_ticks,
                price_ref_ticks=resolution.price_ref_ticks,
                price_realised_ticks=resolution.price_realised_ticks,
                realised_sign=resolution.realised_sign,
                directional_brier_micro=resolution.directional_brier_micro,
                pinball_micro=resolution.pinball_micro,
                baseline_pinball_micro=resolution.baseline_pinball_micro,
                carried=resolution.carried,
            )

    def _close_instrument(self, market_id: str, t_ms: int) -> None:
        """``instrument_closed`` once, at ``last_bar(i)``, after the forced flat (section 17.3)."""
        record = self.record(market_id)
        instrument = self.market(market_id)
        delisted = getattr(instrument, "delisted_at_ms", None)
        reason = "window_end"
        if isinstance(delisted, int) and bar_of(delisted, self.config.interval_min) - self.span == t_ms:
            reason = "delisted"
        self.journal.emit(
            _INSTRUMENT_CLOSED,
            bar_ms=t_ms,
            market_id=market_id,
            kind=self.kind_of(market_id),
            reason=reason,
            last_price_ticks=record.closes_by_bar.get(t_ms, 0),
            n_bars=len(record.bars),
            n_forecasts_unresolved=self.unresolved.get(market_id, 0),
        )

    def _note_reputation(
        self, *, agent_id: str, market: Market, agent_brier: int, market_brier: int, realised: int
    ) -> None:
        """Keep the ``(agent, category)`` window section 10.4 computes a reputation over."""
        key = (agent_id, market.category)
        found = self.reputations.get(key)
        if found is None:
            found = _Reputation(skills_micro=[])
            self.reputations[key] = found
        found.skills_micro.append(market_brier - agent_brier)
        del found.skills_micro[:-REPUTATION_WINDOW_MARKETS]
        found.pnl_cents += realised

    def phase_learn(self, settled: Sequence[tuple[str, int]]) -> None:
        """``agent.learn`` for every agent that forecast or held a settled market (phase 6)."""
        for market_id, outcome in settled:
            market = self.market(market_id)
            record = self.record(market_id)
            market_brier = market_brier_tw_micro(record.bars, outcome=outcome, interval_ms=self.span)
            for agent_id in self.agent_ids:
                pair = self.pairs.get((agent_id, market_id))
                if pair is None or not pair.bars:
                    continue
                event = ResolutionEvent(
                    market_id=market_id,
                    category=market.category,
                    tags=market.tags,
                    provider=market.provider,
                    outcome=outcome,
                    resolved_at_ms=market.resolved_at_ms,
                    close_at_ms=market.close_at_ms,
                    created_at_ms=market.created_at_ms,
                    forecasts=tuple((item.t_ms, item.prob_ppm) for item in pair.bars),
                    market_prices=tuple((item.t_ms, item.market_price_bp) for item in pair.bars),
                    realised_pnl_cents=pair.realised_cents,
                    fees_cents=pair.fees_cents,
                    agent_brier_tw_micro=brier_tw_micro(
                        pair.bars, outcome=outcome, interval_ms=self.span
                    ),
                    market_brier_tw_micro=market_brier,
                )
                self.by_id[agent_id].learn(event)

    def phase_hive(self, bar: BarSlice, settled: Sequence[tuple[str, int]]) -> None:
        """The four hive writes of phase 7, in the order section 8.2 lists them."""
        hive = self.hive
        if hive is None:
            return
        t_ms = bar.t_ms
        interval_min = self.config.interval_min
        for agent_id in self.agent_ids:
            for market_id in bar.open_ids:
                prob_ppm = self.last_prob.get((agent_id, market_id))
                if prob_ppm is None:
                    continue
                statements = self.bar_horizons.get((agent_id, market_id))
                if statements is None:
                    hive.write_forecast(
                        agent_id=agent_id,
                        market_id=market_id,
                        bar_ms=t_ms,
                        prob_ppm=prob_ppm,
                        resolved_at_ms=self.dataset.meta(market_id).resolved_at_ms,
                        interval_min=interval_min,
                    )
                    continue
                # Amendment C1b (17.5, ruling R160): one entry per (forecast, horizon), released one
                # bar after the bar at which the realisation became public, and none at all for a
                # horizon that never resolves.
                for statement in statements:
                    if statement.resolves_at_ms is None:
                        continue
                    hive.write_forecast(
                        agent_id=agent_id,
                        market_id=market_id,
                        bar_ms=t_ms,
                        prob_ppm=statement.up_probability_ppm,
                        resolved_at_ms=0,
                        interval_min=interval_min,
                        horizon_bars=statement.horizon_bars,
                        quantiles_ticks=statement.quantiles_ticks,
                        price_ref_ticks=statement.price_ref_ticks,
                        resolves_at_ms=statement.resolves_at_ms,
                    )
        for market_id, outcome in settled:
            record = self.record(market_id)
            n_bars = len(record.bars)
            hive.write_resolution(
                market_id=market_id,
                outcome=outcome,
                life_mean_price_bp=round_half_up(sum(record.closes), n_bars) if n_bars else 0,
                resolved_at_ms=self.dataset.meta(market_id).resolved_at_ms,
                interval_min=interval_min,
            )
        affected = sorted(
            {
                (agent_id, self.dataset.meta(market_id).category)
                for market_id, _ in settled
                for agent_id in self.agent_ids
                if (agent_id, market_id) in self.pairs
            }
        )
        for agent_id, category in affected:
            found = self.reputations.get((agent_id, category))
            if found is None:
                continue
            hive.write_reputation(
                agent_id=agent_id,
                category=category,
                bar_ms=t_ms,
                interval_min=interval_min,
                n=len(found.skills_micro),
                skill_micro=signed_mean(found.skills_micro),
                pnl_cents=found.pnl_cents,
            )
        for author_id, text, market_ids in self.bar_lessons:
            hive.write_lesson(
                agent_id=author_id,
                text=text,
                market_ids=market_ids,
                bar_ms=t_ms,
                interval_min=interval_min,
            )

    def phase_close(self, bar: BarSlice, open_markets: Sequence[Market], first_seq: int) -> None:
        """Mark, freeze the ruined, and close the bar (phase 8, section 8.7)."""
        t_ms = bar.t_ms
        views = self.execution.mark(t_ms=t_ms, markets=open_markets, agent_ids=self.agent_ids)
        for agent_id in self.agent_ids:
            view = views[agent_id]
            self.journal.emit(
                EquityMarked,
                bar_ms=t_ms,
                agent_id=agent_id,
                cash_cents=view.cash_cents,
                reserved_cents=view.reserved_cents,
                positions_value_cents=view.equity_cents - view.cash_cents,
                equity_cents=view.equity_cents,
                fees_paid_cents=view.fees_paid_cents,
                peak_equity_cents=view.peak_equity_cents,
                drawdown_bp=view.drawdown_bp,
                n_open_positions=view.n_open_positions,
                n_open_orders=view.n_open_orders,
            )
        for agent_id, equity_cents, cancelled in self.execution.drain_ruined():
            self.journal.emit(
                AgentRuined,
                bar_ms=t_ms,
                agent_id=agent_id,
                equity_cents=equity_cents,
                cancelled_order_ids=cancelled,
            )
        self.journal.emit(
            BarClosed, bar_ms=t_ms, n_events=self.journal.next_seq - first_seq + 1
        )


def replay(run_dir: Path) -> RunProjection:
    """Rebuild ``results.json`` from ``journal.jsonl`` alone and assert byte equality (section 9.5).

    Args:
        run_dir: The run directory, holding ``journal.jsonl``, ``journal.sha256`` and ``results.json``.

    Returns:
        The rebuilt projection, which is byte-identical to the stored one.

    Raises:
        JournalError: On a journal whose hash, ordering, engine version or projection does not match
            what the directory holds. A ``results.json`` that cannot be rebuilt from the journal is a
            bug in the projection, never a reason to widen the journal with a derived number.
    """
    journal_path = run_dir / "journal.jsonl"
    events = read_journal(journal_path, validate=True)
    verify_journal(events)
    digest = journal_hash_of_file(journal_path)
    digest_path = run_dir / "journal.sha256"
    if digest_path.exists():
        with open(digest_path, encoding=JOURNAL_ENCODING, newline=JOURNAL_NEWLINE) as handle:
            stored = handle.read().split(" ")[0]
        if stored != digest:
            raise JournalError("journal.sha256 does not match journal.jsonl", stored=stored, computed=digest)
    started = events[0]
    if not isinstance(started, RunStarted):
        raise JournalError("a run journal starts at run_started", first=events[0].TYPE)
    if started.engine_version != ENGINE_VERSION:
        raise JournalError(
            "this journal was written by another engine",
            journal_engine_version=started.engine_version,
            engine_version=ENGINE_VERSION,
        )
    projection = project(events)
    rebuilt = canonical_json(projection.to_dict()) + JOURNAL_NEWLINE
    results_path = run_dir / "results.json"
    if results_path.exists():
        with open(results_path, encoding=JOURNAL_ENCODING, newline=JOURNAL_NEWLINE) as handle:
            stored_results = handle.read()
        if stored_results != rebuilt:
            raise JournalError(
                "results.json is not the projection of journal.jsonl",
                run_dir=str(run_dir),
                stored_bytes=len(stored_results),
                rebuilt_bytes=len(rebuilt),
            )
    return projection
