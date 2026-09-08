"""Bankroll, orders, fills, cash events, settlement, ruin and marking (CONTRACTS_V2 8.5 to 8.9, 17.3).

``Execution`` owns every cent an agent has and every position it holds, and it owns nothing else. It does
not price a fill (``pmx.engine.liquidity`` does, ruling R113), it does not score a forecast (it never sees
one, which is why ``settled`` and ``settlement_applied`` belong to the runner), and it does not decide
which bar comes next (the runner drives it). What it guarantees is the accounting invariant of 8.9: for
every agent, over the journal alone, cash is the bankroll plus every fill, minus every fee, plus every
settlement, plus every cash event, and a fill never takes cash below zero.

Three rules shape the code more than any other.

**A decision at bar ``t`` executes at the open of the instrument's next bar** (16.2). :meth:`Execution.place`
is called in the decide phase and only queues: it emits no event, moves no cent and reserves nothing.
:meth:`Execution.execute_bar` drains what was accepted at the instrument's previous bar, prices the whole
market's batch through one ``quote_bar`` call, and writes every execute-phase event with ``decided_at_ms``
naming the bar the intent came from. An intent whose market is no longer tradable when its bar arrives is
``order_rejected(not_tradable)`` and nothing else, which is the rule and not a defect: the agent decided on
information ending at the last completed bar, and the tape it would have to trade against carries the close
and the outcome.

**Every cash flow that is not a fill is a dated cash event** (17.3). Funding, dividends, splits, rolls,
borrow fees, the fx carry and the forced flat are one record family applied in the settle phase, in kind
order, and journaled once, so the invariant stays an identity for every instrument kind. A corporate event
applies at the last bar priced in the **old** regime (ruling R175), which is why a buy at an ex-date open
receives no dividend and a buy at a split's effective open is not multiplied.

**One rounding, against the agent** (ruling R146). Every cash movement is an exact integer product divided
once, up when the agent pays and down when it receives, so no cent is ever created by rounding.

Two dependencies of this module do not exist yet and are reported as contract issues rather than papered
over: the C1b names of ``pmx.types`` (section 17.9, gate G2), which ``pmx.engine.fees`` bridges, and the
journal event classes of ruling R164, which the private bridges below supply until ``pmx.journal`` carries
them. Both bridges prefer the real name the moment it exists.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar, Protocol, runtime_checkable

from pmx import journal as _journal
from pmx.engine import fees
from pmx.engine.fees import (
    BINARY_POINT_VALUE_MICRO,
    BINARY_TICK_SIZE_MICRO,
    CASH_EVENT_KINDS,
    MICRO,
    MILLI,
    NOTIONAL_CENTS_MAX,
    NOTIONAL_DENOMINATOR,
    CarrySchedule,
    FeeSchedule,
    cash_in_cents,
    cash_out_cents,
    mark_value_cents,
    notional_micro,
    split_position_milli,
)
from pmx.engine.liquidity import (
    Fill,
    LiquidityMarketView,
    LiquidityModel,
    LiquidityOrder,
    ObservedFlow,
    event_fill,
    truncate_for_cash,
)
from pmx.errors import InvalidConfigError
from pmx.journal import (
    FeeCharged,
    Filled,
    Journal,
    JournalEvent,
    OrderExpired,
    OrderPlaced,
    OrderRejected,
    canonical_sha256,
    payload_field_names,
)
from pmx.types import (
    BP_ONE,
    CENTS_PER_UNIT,
    MS_PER_DAY,
    PPM_ONE,
    Bar,
    MarketAction,
    OpenOrderView,
    PortfolioView,
    PositionView,
    RunConfig,
    bar_of,
    bp_ratio,
    cost_cents,
    day_start_ms,
    interval_ms,
    proceeds_cents,
    round_half_up,
    sorted_agent_ids,
    sorted_market_ids,
)

if TYPE_CHECKING:  # pragma: no cover - import-time typing only
    pass

__all__ = [
    "CashEventLike",
    "EngineCashEvent",
    "Execution",
    "InstrumentLike",
    "InstrumentSpec",
    "applies_at",
    "instrument_spec",
]


# --------------------------------------------------------------------------------------------------
# What execution reads of an instrument, a cash event and a bar calendar
# --------------------------------------------------------------------------------------------------
@runtime_checkable
class InstrumentLike(Protocol):
    """The instrument surface execution reads (7.2 and 17.1).

    Declared structurally so that a ``Market`` (the binary instrument, which exists) and a
    ``ContinuousInstrument`` (which gate G2 lands in ``pmx.types``) satisfy it without this module
    naming a class that is not written yet. Every member is read-only, which both a frozen dataclass
    field and a property satisfy.
    """

    @property
    def id(self) -> str: ...

    @property
    def provider(self) -> str: ...

    @property
    def interval_min(self) -> int: ...

    @property
    def source(self) -> str: ...

    @property
    def category(self) -> str: ...

    @property
    def currency(self) -> str: ...

    @property
    def fee_schedule_id(self) -> str: ...

    def bar_at(self, t_ms: int) -> Bar | None: ...

    def bars_before(self, now_ms: int, limit: int) -> tuple[Bar, ...]: ...


@runtime_checkable
class CashEventLike(Protocol):
    """One dated cash event (17.3), read structurally for the reason :class:`InstrumentLike` is."""

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


class BarCalendar(Protocol):
    """The three bar lookups of 8.3 (ruling R187), which ``applies_at`` and the queue read.

    E1's ``Calendar`` is the one implementation for a run; :class:`Execution` builds an equivalent over
    the session calendars it was handed, because 8.6 gives it those and not a ``Calendar``.
    """

    def last_bar(self, market_id: str) -> int: ...

    def next_bar(self, market_id: str, t_ms: int) -> int | None: ...

    def prev_bar(self, market_id: str, t_ms: int) -> int | None: ...


@dataclass(frozen=True, slots=True)
class EngineCashEvent:
    """A cash event the engine generates: ``borrow_fee``, ``carry`` or ``forced_flat`` (ruling R177).

    ``pmx.types.CashEvent`` is the record gate G2 lands (17.9) and is field for field this shape; the
    engine needs a constructor in wave 2 because these three kinds are its own and no importer may write
    them (rule 10 forbids the data layer from reading ``pmx.engine.fees``). ``cash_event_id`` is the
    contract's: ``"ce-" + sha256(canonical_json([market_id, kind, t_ms, detail]))[:16]``.
    """

    cash_event_id: str
    market_id: str
    kind: str
    t_ms: int
    origin: str
    detail: Mapping[str, int | str]
    source_url: str = ""

    @classmethod
    def build(cls, *, market_id: str, kind: str, t_ms: int,
              detail: Mapping[str, int | str]) -> EngineCashEvent:
        """Build an engine event with the contract's id, which hashes the instant it applies at (R176)."""
        payload = [market_id, kind, t_ms, dict(detail)]
        return cls(
            cash_event_id="ce-" + canonical_sha256(payload)[:16],
            market_id=market_id,
            kind=kind,
            t_ms=t_ms,
            origin="engine",
            detail=dict(detail),
        )


@dataclass(frozen=True, slots=True)
class InstrumentSpec:
    """The ``Instrument`` base of 17.1 as execution needs it, for a binary and a continuous kind alike.

    A ``Market`` satisfies the base "through the view ``Market.instrument``" (17.1), a property gate G2
    adds; until then :func:`instrument_spec` derives exactly the mapping that section's table declares
    (``kind = "binary"``, ``tick_size_micro = 100``, ``point_value_micro = 1_000_000``,
    ``session_calendar_id = "continuous"``, no borrow or carry schedule, ``listed_at_ms =
    created_at_ms``, ``delisted_at_ms = resolved_at_ms``, ``short_allowed = True``), so no code path here
    has two shapes to read.
    """

    id: str
    provider: str
    vendor: str
    symbol: str
    kind: str
    currency: str
    category: str
    source: str
    tick_size_micro: int
    point_value_micro: int
    session_calendar_id: str
    fee_schedule_id: str
    borrow_schedule_id: str | None
    carry_schedule_id: str | None
    listed_at_ms: int
    delisted_at_ms: int | None
    short_allowed: bool
    interval_min: int
    close_at_ms: int
    resolved_at_ms: int
    resolution: int

    @property
    def is_binary(self) -> bool:
        """True for the binary kind, whose netting, settlement and payout are 8.5's and 8.7's."""
        return self.kind == "binary"

    @property
    def interval_ms(self) -> int:
        return interval_ms(self.interval_min)


def _int_attr(obj: object, name: str, fallback: int) -> int:
    value = getattr(obj, name, fallback)
    return value if isinstance(value, int) and not isinstance(value, bool) else fallback


def _opt_int_attr(obj: object, name: str, fallback: int | None) -> int | None:
    value = getattr(obj, name, fallback)
    if value is None:
        return None
    return value if isinstance(value, int) and not isinstance(value, bool) else fallback


def _str_attr(obj: object, name: str, fallback: str) -> str:
    value = getattr(obj, name, fallback)
    return value if isinstance(value, str) else fallback


def _opt_str_attr(obj: object, name: str) -> str | None:
    value = getattr(obj, name, None)
    return value if isinstance(value, str) and value != "" else None


def _bool_attr(obj: object, name: str, fallback: bool) -> bool:
    value = getattr(obj, name, fallback)
    return value if isinstance(value, bool) else fallback


def instrument_spec(instrument: InstrumentLike) -> InstrumentSpec:
    """Read the ``Instrument`` base of 17.1 off a market or a continuous instrument.

    Prefers the instrument's own ``instrument`` view when it carries one (the property of ruling R144),
    then the object's own fields, then the binary mapping of 17.1's table. A binary therefore keeps every
    number it has today and a continuous instrument is read from its own record.
    """
    base: object = getattr(instrument, "instrument", None)
    if base is None:
        base = instrument
    kind = _str_attr(base, "kind", "binary")
    if kind not in fees.INSTRUMENT_KINDS:
        raise InvalidConfigError("instrument kind is not one of INSTRUMENT_KINDS", market_id=instrument.id,
                                 kind=kind)
    created = _int_attr(instrument, "created_at_ms", 0)
    resolved = _int_attr(instrument, "resolved_at_ms", 0)
    return InstrumentSpec(
        id=instrument.id,
        provider=instrument.provider,
        vendor=_str_attr(base, "vendor", instrument.provider),
        symbol=_str_attr(base, "symbol", _str_attr(instrument, "provider_id", instrument.id)),
        kind=kind,
        currency=instrument.currency,
        category=instrument.category,
        source=instrument.source,
        tick_size_micro=_int_attr(base, "tick_size_micro", BINARY_TICK_SIZE_MICRO),
        point_value_micro=_int_attr(base, "point_value_micro", BINARY_POINT_VALUE_MICRO),
        session_calendar_id=_str_attr(base, "session_calendar_id", "continuous"),
        fee_schedule_id=instrument.fee_schedule_id,
        borrow_schedule_id=_opt_str_attr(base, "borrow_schedule_id"),
        carry_schedule_id=_opt_str_attr(base, "carry_schedule_id"),
        listed_at_ms=_int_attr(base, "listed_at_ms", created),
        delisted_at_ms=_opt_int_attr(base, "delisted_at_ms", resolved if kind == "binary" else None),
        short_allowed=_bool_attr(base, "short_allowed", kind != "spot_crypto"),
        interval_min=instrument.interval_min,
        close_at_ms=_int_attr(instrument, "close_at_ms", 0),
        resolved_at_ms=resolved,
        resolution=_int_attr(instrument, "resolution", -1),
    )


#: The three corporate kinds, whose entitlement follows the regime of the prices (ruling R175).
_OLD_REGIME_KINDS: tuple[str, ...] = ("dividend", "split", "roll")


def applies_at(event: CashEventLike, instrument: InstrumentLike, calendar: BarCalendar) -> int | None:
    """The bar at whose settle phase execution applies ``event`` (17.3, ruling R175).

    A ``dividend``, a ``split`` and a ``roll`` are stamped with the first instant of the **new** regime
    (the ex-date open, the split's effective open, the first new-contract bar) and the raw tape already
    reflects them from that bar's open, so they apply one bar earlier, at the last close priced in the
    old regime. Without that shift a buy at the ex-date open collects a dividend the tape had already
    taken out of the price, which anyone holding a corporate calendar could farm. ``funding``,
    ``borrow_fee``, ``carry`` and ``forced_flat`` are charges on, or the close of, a position held
    through an instant, and apply at ``bar_of(t_ms)``.

    Returns:
        The application bar, or ``None`` when it lies outside the run and no position can exist there.
    """
    bar = bar_of(event.t_ms, instrument.interval_min)
    if event.kind in _OLD_REGIME_KINDS:
        return calendar.prev_bar(instrument.id, bar)
    return bar


# --------------------------------------------------------------------------------------------------
# The journal classes ruling R164 gives ``pmx.journal`` at gate G2, bridged until it carries them
# --------------------------------------------------------------------------------------------------
@dataclass(frozen=True, slots=True, kw_only=True)
class _OrderPlacedC1(OrderPlaced):
    """``order_placed`` with ``decided_at_ms`` (R111) and the settle phase of an event fill (R152)."""

    decided_at_ms: int

    PHASES: ClassVar[tuple[str, ...]] = ("execute", "settle")


@dataclass(frozen=True, slots=True, kw_only=True)
class _OrderRejectedC1(OrderRejected):
    """``order_rejected`` with ``decided_at_ms``: without it a rejection cannot be traced to its intent."""

    decided_at_ms: int


@dataclass(frozen=True, slots=True, kw_only=True)
class _FilledC1b(Filled):
    """``filled``, which an event fill of 17.3 writes in the settle phase (ruling R152)."""

    PHASES: ClassVar[tuple[str, ...]] = ("execute", "settle")


@dataclass(frozen=True, slots=True, kw_only=True)
class _FeeChargedC1b(FeeCharged):
    """``fee_charged``, which an event fill of 17.3 writes in the settle phase (ruling R152)."""

    PHASES: ClassVar[tuple[str, ...]] = ("execute", "settle")


@dataclass(frozen=True, slots=True, kw_only=True)
class _CashEventAppliedC1b(JournalEvent):
    """``cash_event_applied`` (9.2 and 17.3): one event per (agent, instrument, cash event).

    ``cash_delta_cents`` is ``0`` for ``split``, ``roll`` and ``forced_flat``, whose money moves in their
    fills, and signed for the other four, where it may take cash below zero (ruling R179).
    """

    agent_id: str
    market_id: str
    cash_event_id: str
    kind: str
    origin: str
    position_before: int
    position_after: int
    avg_cost_ticks_before: int
    avg_cost_ticks_after: int
    cash_delta_cents: int
    order_ids: tuple[str, ...]
    detail: Mapping[str, int | str]

    TYPE: ClassVar[str] = "cash_event_applied"
    PHASES: ClassVar[tuple[str, ...]] = ("settle",)


def _resolve_event(name: str, *, needs: tuple[str, ...], phases: tuple[str, ...],
                   fallback: type[JournalEvent]) -> type[JournalEvent]:
    """``pmx.journal``'s class of that name when it carries what the contract asks, else the bridge.

    Ruling R164 gives D7 ``CashEventApplied``, the ``settle`` phase of the three execute-phase events and
    ``decided_at_ms``, applied by gate G2. Resolving by name and by capability means the engine uses D7's
    class the moment it lands, and never silently writes an event missing a contracted field.
    """
    candidate = getattr(_journal, name, None)
    if isinstance(candidate, type) and issubclass(candidate, JournalEvent):
        carried = set(payload_field_names(candidate))
        if set(needs) <= carried and set(phases) <= set(candidate.PHASES):
            return candidate
    return fallback


_ORDER_PLACED = _resolve_event(
    "OrderPlaced", needs=("decided_at_ms",), phases=("execute", "settle"), fallback=_OrderPlacedC1
)
_ORDER_REJECTED = _resolve_event(
    "OrderRejected", needs=("decided_at_ms",), phases=("execute",), fallback=_OrderRejectedC1
)
_FILLED = _resolve_event("Filled", needs=(), phases=("execute", "settle"), fallback=_FilledC1b)
_FEE_CHARGED = _resolve_event("FeeCharged", needs=(), phases=("execute", "settle"), fallback=_FeeChargedC1b)
_ORDER_EXPIRED = _resolve_event(
    "OrderExpired", needs=(), phases=("open", "settle", "close"), fallback=OrderExpired
)
_CASH_EVENT_APPLIED = _resolve_event(
    "CashEventApplied",
    needs=("cash_event_id", "position_before", "position_after", "cash_delta_cents", "order_ids"),
    phases=("settle",),
    fallback=_CashEventAppliedC1b,
)


# --------------------------------------------------------------------------------------------------
# Internal state
# --------------------------------------------------------------------------------------------------
@dataclass(slots=True)
class _Leg:
    """One agent's leg on one instrument: signed size and the entry price of the open leg.

    ``avg_cost_bp`` is stored in the instrument's own price space for both legs, so a NO leg opened at a
    YES price of 6 327 carries 6 327 and its unrealised value is the mirror of a YES leg's.
    """

    position: int = 0
    avg_cost_bp: int = 0


@dataclass(slots=True)
class _Resting:
    """A resting limit order and the cash it has earmarked."""

    order_id: str
    agent_id: str
    market_id: str
    side: str
    limit_price_bp: int
    size: int
    remaining: int
    reserved_cents: int
    expires_at_ms: int
    placed_at_ms: int
    ttl_bars: int


@dataclass(slots=True)
class _AgentState:
    """Everything execution knows about one agent. Cash and equity are signed (rulings R179 and R180)."""

    cash_cents: int
    reserved_cents: int = 0
    fees_paid_cents: int = 0
    peak_equity_cents: int = 0
    drawdown_bp: int = 0
    equity_cents: int = 0
    ruined: bool = False
    legs: dict[str, _Leg] = field(default_factory=dict)
    resting: dict[str, _Resting] = field(default_factory=dict)


@dataclass(slots=True)
class _Pending:
    """One queued intent: what ``place`` accepted, and the bar its instrument will drain it at."""

    agent_id: str
    market_id: str
    action: MarketAction
    item_index: int
    decided_at_ms: int
    drain_at_ms: int
    sequence: int


@dataclass(slots=True)
class _Ready:
    """One order about to be priced: its id, the liquidity order, and the resting row behind it."""

    agent_id: str
    order_id: str
    market_id: str
    decided_at_ms: int
    order: LiquidityOrder
    size: int
    resting: _Resting | None


class Execution:
    """The one owner of cash, positions, orders and cash events (8.5 to 8.9, 17.3).

    Args:
        journal: The run's journal. Execution emits ``order_placed``, ``order_rejected``, ``filled``,
            ``fee_charged``, ``order_expired`` and ``cash_event_applied``, and nothing else (9.3).
        config: The run's config: the bankroll, the volume cap, the slippage, the ruin floor.
        schedules: The fee schedules of the run by id; the shipped rows of ``pmx.engine.fees`` answer
            for an id this mapping does not carry.
        liquidity: The run's model (16.1). Required and keyword-only: execution never builds one.
        calendars: The sealed session calendars by id (ruling R174). ``None`` means the synthesised
            ``continuous`` calendar for every instrument, which is what a binary run passes.
        carry_schedules: The borrow and carry schedules by id, when a run declares one 17.4 does not
            ship. Additive and keyword-only (preamble rule 2), and needed: 17.4 ships no ``carry``
            schedule at all, so an fx instrument that names a ``carry_schedule_id`` would name a row
            nothing carries and the ``carry`` kind of 17.3 would be unreachable. Reported as a contract
            issue.
    """

    __slots__ = (
        "_carry_schedules",
        "_config",
        "_grid",
        "_journal",
        "_last_price",
        "_liquidity",
        "_next_order_seq",
        "_pending",
        "_pending_seq",
        "_ruin_pending",
        "_schedules",
        "_specs",
        "_states",
    )

    def __init__(
        self,
        *,
        journal: Journal,
        config: RunConfig,
        schedules: Mapping[str, FeeSchedule],
        liquidity: LiquidityModel,
        calendars: Mapping[str, object] | None = None,
        carry_schedules: Mapping[str, CarrySchedule] | None = None,
    ) -> None:
        self._journal = journal
        self._config = config
        self._schedules = dict(schedules)
        self._carry_schedules = dict(carry_schedules) if carry_schedules is not None else {}
        self._liquidity = liquidity
        self._specs: dict[str, InstrumentSpec] = {}
        self._states: dict[str, _AgentState] = {}
        self._pending: list[_Pending] = []
        self._pending_seq = 0
        self._next_order_seq = 0
        self._last_price: dict[str, int] = {}
        self._ruin_pending: list[tuple[str, int, tuple[str, ...]]] = []
        self._grid = _SessionGrid(config=config, calendars=calendars or {})

    # ----------------------------------------------------------------------
    # Read-only state and roster
    # ----------------------------------------------------------------------
    def register_agent(self, agent_id: str) -> None:
        """Give an agent its bankroll before its first order, so ``mark`` reports it from bar one.

        Additive to 8.6's surface: the contract never says how execution learns the roster, and an agent
        that first appeared at its first fill would be missing from the equity series before it.
        """
        self._agent(agent_id)

    def agent_ids(self) -> tuple[str, ...]:
        """Every agent execution holds state for, in canonical order (section 3)."""
        return sorted_agent_ids(self._states)

    def ruined_agent_ids(self) -> tuple[str, ...]:
        """The agents frozen by the ruin rule of 8.7, in canonical order."""
        return sorted_agent_ids(agent_id for agent_id, state in self._states.items() if state.ruined)

    def is_ruined(self, agent_id: str) -> bool:
        """Whether the ruin rule of 8.7 has frozen this agent."""
        return self._agent(agent_id).ruined

    def drain_ruined(self) -> tuple[tuple[str, int, tuple[str, ...]], ...]:
        """The agents ruined by the last :meth:`mark`, with their equity and the orders it cancelled.

        Additive to 8.6's surface, and required by 9.3: ``agent_ruined`` is the runner's event and
        carries ``cancelled_order_ids``, which only execution knows.
        """
        drained = tuple(self._ruin_pending)
        self._ruin_pending.clear()
        return drained

    def portfolio(self, agent_id: str) -> PortfolioView:
        """The agent's portfolio as of the last :meth:`mark` (8.3).

        ``research_units_remaining`` is ``0`` here: the research budget is the runner's, and the
        observation builder fills it in.
        """
        state = self._agent(agent_id)
        open_positions = sum(1 for leg in state.legs.values() if leg.position != 0)
        return PortfolioView(
            cash_cents=state.cash_cents,
            reserved_cents=state.reserved_cents,
            equity_cents=state.equity_cents,
            fees_paid_cents=state.fees_paid_cents,
            peak_equity_cents=state.peak_equity_cents,
            drawdown_bp=state.drawdown_bp,
            n_open_positions=open_positions,
            n_open_orders=len(state.resting),
            research_units_remaining=0,
        )

    def position(self, agent_id: str, market_id: str) -> PositionView:
        """The agent's leg on one instrument, marked at the last price execution saw for it (8.3)."""
        state = self._agent(agent_id)
        leg = state.legs.get(market_id)
        position = 0 if leg is None else leg.position
        avg_cost = 0 if leg is None else leg.avg_cost_bp
        spec = self._specs.get(market_id)
        mark = self._last_price.get(market_id, 0)
        unrealised = 0
        if spec is not None and position != 0 and mark > 0:
            unrealised = self._value_cents(spec, position, mark) - self._value_cents(spec, position, avg_cost)
        orders = tuple(
            OpenOrderView(
                order_id=row.order_id,
                side=row.side,
                price_bp=row.limit_price_bp,
                remaining_size=row.remaining,
                expires_at_ms=row.expires_at_ms,
            )
            for row in sorted(state.resting.values(), key=_by_order_id)
            if row.market_id == market_id
        )
        return PositionView(
            position=position, avg_cost_bp=avg_cost, unrealised_cents=unrealised, open_orders=orders
        )

    def pending_market_ids(self, *, t_ms: int) -> tuple[str, ...]:
        """The instruments whose batch bar is ``t_ms``, in canonical market order (8.6, ruling R131).

        Two sets sit in it. First, every item ``place`` accepted at the instrument's previous bar, which
        is what the runner must drive ``execute_bar`` over: a market that closed or settled at that
        previous bar is in no tuple of E1's ``BarSlice`` at ``t_ms`` and is still owed its
        ``order_rejected(not_tradable)``. Second, every instrument carrying a **resting** limit order,
        because 8.6 has a resting order try against each later bar's range until its ttl runs out and the
        drain is the only entry point the runner has. The second half is reported as a contract issue
        against R131, which names only the first.
        """
        ready = {item.market_id for item in self._pending if item.drain_at_ms == t_ms}
        for state in self._states.values():
            for row in state.resting.values():
                ready.add(row.market_id)
        return sorted_market_ids(ready)

    # ----------------------------------------------------------------------
    # The decide phase: queue, reserve nothing, emit nothing
    # ----------------------------------------------------------------------
    def place(self, *, agent_id: str, market: InstrumentLike, action: MarketAction, item_index: int,
              t_ms: int) -> None:
        """Queue one order-producing action for the instrument's next bar (16.2, ruling R110).

        It emits no event, moves no cent and reserves nothing. A ``hold`` produces no order at all, and a
        ``target`` or an ``abstain`` is queued whatever the current position: the comparison that turns
        it into a no-op happens at the execution bar, which is what makes ``target`` the safe idiom under
        latency (a target repeated while a fill is in flight becomes a no-op once the fill lands).
        """
        spec = self._spec(market)
        self._agent(agent_id)
        if action.kind not in ("target", "limit", "abstain"):
            return
        drain_at = self._grid.next_bar(spec.id, t_ms)
        if drain_at is None:
            return
        self._pending_seq += 1
        self._pending.append(
            _Pending(
                agent_id=agent_id,
                market_id=spec.id,
                action=action,
                item_index=item_index,
                decided_at_ms=t_ms,
                drain_at_ms=drain_at,
                sequence=self._pending_seq,
            )
        )

    # ----------------------------------------------------------------------
    # The open phase: expiries
    # ----------------------------------------------------------------------
    def expire_orders(self, *, t_ms: int, markets: Sequence[InstrumentLike]) -> None:
        """Expire the resting orders phase 1 of 8.2 expires: the ttl ran out, or the market closed.

        Additive to 8.6's surface, and required by 8.2: the open phase emits ``order_expired`` and 9.3
        makes execution its one emitter, while the surface of 8.6 has no open-phase entry point. The
        omission is reported as a contract issue.
        """
        known: dict[str, tuple[InstrumentSpec, InstrumentLike]] = {}
        for market in markets:
            known[self._spec(market).id] = (self._spec(market), market)
        for agent_id in self.agent_ids():
            state = self._states[agent_id]
            for row in sorted(state.resting.values(), key=_by_order_id):
                entry = known.get(row.market_id)
                reason = ""
                if row.expires_at_ms <= t_ms:
                    reason = "ttl"
                elif entry is None or not self._tradable(entry[0], t_ms, entry[1].bar_at(t_ms)):
                    reason = "not_tradable"
                if reason:
                    self._expire(state, row, reason=reason, t_ms=t_ms, phase="open")

    # ----------------------------------------------------------------------
    # The execute phase
    # ----------------------------------------------------------------------
    def execute_bar(self, *, t_ms: int, market: InstrumentLike) -> None:
        """Drain the instrument's queue at bar ``t_ms``, price it in one batch and journal every event.

        The batch is built in the canonical order of section 3: agents by ``agent_id``, and inside one
        agent its resting orders by ``order_id`` (time priority, since ids are dense in submission order)
        before the intents it decided at the previous bar, in submission order. It is priced by one
        ``quote_bar`` call, because under latency every order in it arrives at the same open (R126).
        """
        spec = self._spec(market)
        drained = [item for item in self._pending
                   if item.market_id == spec.id and item.drain_at_ms == t_ms]
        if drained:
            self._pending = [item for item in self._pending
                             if not (item.market_id == spec.id and item.drain_at_ms == t_ms)]
        drained.sort(key=lambda item: (item.agent_id, item.sequence))
        bar = market.bar_at(t_ms)
        tradable = self._tradable(spec, t_ms, bar)
        schedule = fees.fee_schedule(spec.fee_schedule_id, schedules=self._schedules)
        view = self._view(spec)
        ready: list[_Ready] = []
        for agent_id in self.agent_ids():
            state = self._states[agent_id]
            if tradable and bar is not None and not state.ruined:
                ready.extend(self._resting_orders(state, spec, agent_id))
            for item in (row for row in drained if row.agent_id == agent_id):
                entry = self._prepare(item, spec, bar, tradable=tradable)
                if entry is not None:
                    ready.append(entry)
        if bar is None or not ready:
            return
        fills = self._liquidity.quote_bar(
            view, bar, tuple(entry.order for entry in ready), schedule=schedule, now_ms=t_ms
        )
        if len(fills) != len(ready):
            raise InvalidConfigError(
                "a liquidity model answers one Fill per order",
                market_id=spec.id, orders=len(ready), fills=len(fills),
            )
        bought = 0
        sold = 0
        n_fills = 0
        last = 0
        for entry, quoted in zip(ready, fills, strict=True):
            filled, price = self._apply_fill(
                entry=entry, spec=spec, fill=quoted, schedule=schedule, view=view, t_ms=t_ms, phase="execute"
            )
            if filled > 0:
                n_fills += 1
                last = price
                if entry.order.side == "buy":
                    bought += self._to_milli(spec, filled)
                else:
                    sold += self._to_milli(spec, filled)
        self._liquidity.on_bar_end(
            ObservedFlow(market_id=spec.id, t_ms=t_ms, bought_milli=bought, sold_milli=sold,
                         n_fills=n_fills, last_fill_price_bp=last)
        )

    def _resting_orders(self, state: _AgentState, spec: InstrumentSpec, agent_id: str) -> list[_Ready]:
        """One agent's resting orders on this instrument, by ``order_id`` (time priority, section 3)."""
        entries: list[_Ready] = []
        for row in sorted(state.resting.values(), key=_by_order_id):
            if row.market_id != spec.id:
                continue
            entries.append(
                _Ready(
                    agent_id=agent_id,
                    order_id=row.order_id,
                    market_id=spec.id,
                    decided_at_ms=row.placed_at_ms,
                    order=LiquidityOrder(
                        side=row.side,
                        kind="limit",
                        size_milli=self._to_milli(spec, row.remaining),
                        limit_price_bp=row.limit_price_bp,
                        resting_since_ms=row.placed_at_ms,
                    ),
                    size=row.remaining,
                    resting=row,
                )
            )
        return entries

    def _prepare(self, item: _Pending, spec: InstrumentSpec, bar: Bar | None, *,
                 tradable: bool) -> _Ready | None:
        """Turn one drained intent into a placed order, or reject it and return ``None`` (8.6 step 0 on).

        Every rejection this method writes is an ``order_rejected`` at the execution bar carrying
        ``decided_at_ms``: the market stopped being tradable, the agent was ruined between deciding and
        executing, the intent is missing a field a limit order needs, the notional exceeds
        ``NOTIONAL_CENTS_MAX`` (the one place that cap is checked, ruling R196), the instrument allows no
        short, or a resting order cannot fund its reservation.
        """
        state = self._agent(item.agent_id)
        if not tradable or bar is None:
            self._reject(item, "not_tradable", "the instrument is not tradable at its execution bar")
            return None
        if state.ruined:
            self._reject(item, "ruined", "the agent was ruined between deciding and executing")
            return None
        action = item.action
        position = self._leg(state, spec.id).position
        limit_price: int | None = None
        if action.kind in ("target", "abstain"):
            target = 0 if action.kind == "abstain" else action.target_position
            if target is None:
                self._reject(item, "missing_field", "a target action carries no target_position")
                return None
            delta = target - position
            if delta == 0:
                return None
            side = "buy" if delta > 0 else "sell"
            size = abs(delta)
            price_for_cap = bar.high_bp
            origin = "abstain" if action.kind == "abstain" else "target"
        elif action.kind == "limit":
            if action.side not in ("buy", "sell"):
                self._reject(item, "missing_field", "a limit action carries no side")
                return None
            if action.price_bp is None or action.price_bp < 1:
                self._reject(item, "bad_price", "a limit action carries no price")
                return None
            if action.size is None or action.size < 1:
                self._reject(item, "bad_size", "a limit action carries no size")
                return None
            if action.ttl_bars is None or action.ttl_bars < 1:
                self._reject(item, "bad_ttl", "a limit action carries no ttl")
                return None
            side = action.side
            size = action.size
            limit_price = action.price_bp
            price_for_cap = limit_price
            origin = "limit"
        else:  # pragma: no cover - place queues no other kind
            return None
        capped = self._short_capped(spec, position, side, size)
        if capped <= 0:
            self._reject(item, "short_not_allowed", "this instrument allows no short position")
            return None
        size = capped
        if notional_micro(self._to_milli(spec, size), price_for_cap, spec.tick_size_micro,
                          spec.point_value_micro) > NOTIONAL_CENTS_MAX * NOTIONAL_DENOMINATOR:
            self._reject(item, "bad_size", "the order notional exceeds NOTIONAL_CENTS_MAX")
            return None
        resting: _Resting | None = None
        if limit_price is not None and action.ttl_bars is not None:
            reserved = self._reservation(spec, side, size, limit_price)
            if reserved > self._free_cash(state):
                self._reject(item, "insufficient_cash",
                             "the reservation of the limit order exceeds free cash")
                return None
            resting = self._open_resting(
                state=state, spec=spec, item=item, side=side, size=size, limit_price=limit_price,
                ttl_bars=action.ttl_bars, reserved=reserved,
            )
            order_id = resting.order_id
        else:
            order_id = self._new_order_id()
            self._emit_placed(
                order_id=order_id, agent_id=item.agent_id, market_id=spec.id, kind="market", side=side,
                price_bp=None, size=size, ttl_bars=None, expires_at_ms=None, reserved_cents=0,
                origin=origin, decided_at_ms=item.decided_at_ms, t_ms=item.drain_at_ms, phase="execute",
            )
        return _Ready(
            agent_id=item.agent_id,
            order_id=order_id,
            market_id=spec.id,
            decided_at_ms=item.decided_at_ms,
            order=LiquidityOrder(
                side=side,
                kind="limit" if limit_price is not None else "market",
                size_milli=self._to_milli(spec, size),
                limit_price_bp=limit_price,
                resting_since_ms=item.drain_at_ms if limit_price is not None else None,
            ),
            size=size,
            resting=resting,
        )

    def _open_resting(self, *, state: _AgentState, spec: InstrumentSpec, item: _Pending, side: str,
                      size: int, limit_price: int, ttl_bars: int, reserved: int) -> _Resting:
        """Put a limit order on the book: reserve its worst-case opening cost and journal it (8.5).

        ``placed_at_ms`` is the bar the order was **drained** at, one bar after it was decided, so
        ``ttl_bars`` counts from the bar the order actually rests (8.6).
        """
        order_id = self._new_order_id()
        expires = item.drain_at_ms + ttl_bars * spec.interval_ms
        row = _Resting(
            order_id=order_id,
            agent_id=item.agent_id,
            market_id=spec.id,
            side=side,
            limit_price_bp=limit_price,
            size=size,
            remaining=size,
            reserved_cents=reserved,
            expires_at_ms=expires,
            placed_at_ms=item.drain_at_ms,
            ttl_bars=ttl_bars,
        )
        state.resting[order_id] = row
        state.reserved_cents += reserved
        self._emit_placed(
            order_id=order_id, agent_id=item.agent_id, market_id=spec.id, kind="limit", side=side,
            price_bp=limit_price, size=size, ttl_bars=ttl_bars, expires_at_ms=expires,
            reserved_cents=reserved, origin="limit", decided_at_ms=item.decided_at_ms,
            t_ms=item.drain_at_ms, phase="execute",
        )
        return row

    def _apply_fill(self, *, entry: _Ready, spec: InstrumentSpec, fill: Fill, schedule: FeeSchedule,
                    view: LiquidityMarketView, t_ms: int, phase: str) -> tuple[int, int]:
        """Apply one priced order: truncate for cash, net the position, move the cash, journal it.

        Returns:
            ``(filled, price)``: the size that filled in the instrument's own units (whole contracts on a
            binary, milli-units on a continuous instrument), and the price it filled at.
        """
        state = self._agent(entry.agent_id)
        own_reserved = entry.resting.reserved_cents if entry.resting is not None else 0
        available = self._free_cash(state, own_reserved=own_reserved)
        offered = self._from_milli(spec, fill.filled_milli)
        ceiling = self._affordable(
            spec=spec, position=self._leg(state, spec.id).position, side=entry.order.side,
            price=fill.price_bp, requested=offered, available=available, schedule=schedule, role=fill.role,
            resting=entry.resting,
        )
        truncated = truncate_for_cash(
            fill, max_filled_milli=self._to_milli(spec, ceiling), schedule=schedule, market_view=view,
            order=entry.order,
        )
        filled = self._from_milli(spec, truncated.filled_milli)
        unfilled = entry.size - filled
        reason = truncated.unfilled_reason
        if unfilled > 0 and reason == "none":
            reason = "volume_cap"
        leg = self._leg(state, spec.id)
        before = leg.position
        avg_before = leg.avg_cost_bp
        close_size, open_size, cash_delta, after, avg_after = self._net(
            spec=spec, position=before, avg_cost=avg_before, side=entry.order.side, size=filled,
            price=truncated.price_bp,
        )
        released = 0
        if entry.resting is not None:
            row = entry.resting
            row.remaining -= filled
            new_reserved = (
                self._reservation(spec, row.side, row.remaining, row.limit_price_bp)
                if row.remaining > 0 else 0
            )
            released = row.reserved_cents - new_reserved
            state.reserved_cents -= released
            row.reserved_cents = new_reserved
            if row.remaining <= 0:
                del state.resting[row.order_id]
        leg.position = after
        leg.avg_cost_bp = avg_after
        state.cash_cents += cash_delta - truncated.fee_cents
        state.fees_paid_cents += truncated.fee_cents
        self._journal.emit(
            _FILLED,
            bar_ms=t_ms,
            phase=phase,
            order_id=entry.order_id,
            agent_id=entry.agent_id,
            market_id=spec.id,
            side=entry.order.side,
            kind=entry.order.kind,
            requested_size=entry.size,
            filled_size=filled,
            unfilled_size=unfilled,
            unfilled_reason="none" if unfilled == 0 else reason,
            base_price_bp=truncated.base_price_bp,
            slippage_bp=truncated.slippage_bp,
            fill_price_bp=truncated.price_bp,
            price_source=truncated.price_source,
            close_size=close_size,
            open_size=open_size,
            cash_delta_cents=cash_delta,
            released_cents=released,
            position_before=before,
            position_after=after,
            avg_cost_bp_after=avg_after,
        )
        self._journal.emit(
            _FEE_CHARGED,
            bar_ms=t_ms,
            phase=phase,
            order_id=entry.order_id,
            agent_id=entry.agent_id,
            market_id=spec.id,
            fee_cents=truncated.fee_cents,
            schedule_id=schedule.schedule_id,
            role=truncated.role,
        )
        return (filled, truncated.price_bp)

    # ----------------------------------------------------------------------
    # The settle phase: settlement, cash events, the forced flat
    # ----------------------------------------------------------------------
    def settle(self, *, market: InstrumentLike) -> Mapping[str, int]:
        """Pay every position of a settling binary and expire every resting order on it (8.7).

        Returns:
            ``{agent_id: cash_delta_cents}`` for every agent that held a position, in canonical order.
            The two scored events of the settle phase are the runner's: execution never sees a forecast.
        """
        spec = self._spec(market)
        if not spec.is_binary:
            raise InvalidConfigError("settle is for binary markets only (17.3)", market_id=spec.id,
                                     kind=spec.kind)
        outcome = spec.resolution
        if outcome not in (0, 1):
            raise InvalidConfigError("a settling market resolves to 0 or 1", market_id=spec.id,
                                     outcome=outcome)
        t_ms = bar_of(spec.resolved_at_ms, spec.interval_min)
        deltas: dict[str, int] = {}
        for agent_id in self.agent_ids():
            state = self._states[agent_id]
            for row in sorted(state.resting.values(), key=_by_order_id):
                if row.market_id == spec.id:
                    self._expire(state, row, reason="settled", t_ms=t_ms, phase="settle")
            leg = state.legs.get(spec.id)
            if leg is None or leg.position == 0:
                continue
            if leg.position > 0:
                delta = leg.position * CENTS_PER_UNIT if outcome == 1 else 0
            else:
                delta = -leg.position * CENTS_PER_UNIT if outcome == 0 else 0
            state.cash_cents += delta
            deltas[agent_id] = delta
            leg.position = 0
            leg.avg_cost_bp = 0
        self._last_price[spec.id] = BP_ONE if outcome == 1 else 0
        return deltas

    def apply_cash_events(self, *, t_ms: int, market: InstrumentLike) -> None:
        """Apply every cash event of this instrument whose application bar is ``t_ms`` (17.3, R151).

        The order inside the bar is ``(kind order in CASH_EVENT_KINDS, t_ms, cash_event_id)`` and then
        the agents in ``agent_id`` order (ruling R193): kind first, so a funding never applies after a
        roll of the same bar and a dividend is paid per pre-split share, whatever instant the venue
        stamped each record with.
        """
        spec = self._spec(market)
        if spec.is_binary:
            return
        bar = market.bar_at(t_ms)
        events = [event for event in self._events_of(market, spec, t_ms, bar)
                  if applies_at(event, market, self._grid) == t_ms]
        events.sort(key=lambda event: (_kind_rank(event.kind), event.t_ms, event.cash_event_id))
        for event in events:
            self._apply_one_event(event=event, spec=spec, bar=bar, t_ms=t_ms)

    def force_flat(self, *, t_ms: int, market: InstrumentLike) -> None:
        """Close every position on a continuous instrument at the close of its last bar (17.3, R150).

        The flat is a **fill** and never a mark: a mark would let a run end with a paper number nobody
        could have realised, and a fill pays the fee the venue would have charged. A cover that cash
        cannot pay is truncated like any buy, and the residual liability stays in ``equity_marked`` to the
        end of the run, marked at the instrument's last price (ruling R198).
        """
        spec = self._spec(market)
        if spec.is_binary:
            raise InvalidConfigError("a binary settles, it is never forced flat", market_id=spec.id)
        bar = market.bar_at(t_ms)
        if bar is None:
            raise InvalidConfigError("the forced flat needs the bar it prices at", market_id=spec.id,
                                     t_ms=t_ms)
        delisted = spec.delisted_at_ms
        delisting = delisted is not None and bar_of(delisted, spec.interval_min) <= t_ms + spec.interval_ms
        detail: dict[str, int | str] = {
            "reason": "delisted" if delisting else "window_end",
            "price_ticks": bar.close_bp,
        }
        event = EngineCashEvent.build(
            market_id=spec.id, kind="forced_flat", t_ms=t_ms + spec.interval_ms - 1, detail=detail
        )
        self._apply_one_event(event=event, spec=spec, bar=bar, t_ms=t_ms)

    # ----------------------------------------------------------------------
    # The close phase: marking and ruin
    # ----------------------------------------------------------------------
    def mark(self, *, t_ms: int, markets: Sequence[InstrumentLike],
             agent_ids: Sequence[str] | None = None) -> Mapping[str, PortfolioView]:
        """Mark every agent at the close of bar ``t_ms`` itself, then apply the ruin rule (8.7).

        The mark price is the close of bar ``t_ms``, which has elapsed by the time the close phase runs,
        and is deliberately **not** the observation's ``last_price_bp`` (the close of the last
        *completed* bar at the bar's open, 5.4). Marking against the previous bar would give a different
        equity, drawdown and ruin series for every agent on every bar, so the two names are distinct and
        only this one marks.

        ``agent_ids`` is additive: it lets the runner mark an agent that has not traded yet.
        """
        for market in markets:
            spec = self._spec(market)
            bar = market.bar_at(t_ms)
            if bar is not None:
                self._last_price[spec.id] = bar.close_bp
        for agent_id in agent_ids or ():
            self._agent(agent_id)
        views: dict[str, PortfolioView] = {}
        for agent_id in self.agent_ids():
            state = self._states[agent_id]
            value = 0
            for market_id, leg in sorted(state.legs.items()):
                if leg.position == 0:
                    continue
                spec = self._specs[market_id]
                price = self._last_price.get(market_id, leg.avg_cost_bp)
                value += self._value_cents(spec, leg.position, price)
            state.equity_cents = state.cash_cents + value
            state.peak_equity_cents = max(state.peak_equity_cents, state.equity_cents)
            state.drawdown_bp = (
                0 if state.peak_equity_cents == 0
                else bp_ratio(state.equity_cents - state.peak_equity_cents, state.peak_equity_cents)
            )
            if not state.ruined and state.equity_cents <= self._config.ruin_floor_cents:
                cancelled = [row.order_id for row in sorted(state.resting.values(), key=_by_order_id)]
                self._expire_all(state, reason="ruined", t_ms=t_ms, phase="close")
                state.ruined = True
                self._ruin_pending.append((agent_id, state.equity_cents, tuple(cancelled)))
            views[agent_id] = self.portfolio(agent_id)
        return views

    # ----------------------------------------------------------------------
    # Cash events
    # ----------------------------------------------------------------------
    def _events_of(self, market: InstrumentLike, spec: InstrumentSpec, t_ms: int,
                   bar: Bar | None) -> tuple[CashEventLike, ...]:
        """The data events an instrument file carries, plus the engine events this bar generates."""
        stored = getattr(market, "cash_events", ())
        events: list[CashEventLike] = []
        if isinstance(stored, tuple | list):
            events.extend(event for event in stored if _is_cash_event(event))
        if bar is not None:
            events.extend(self._engine_events(spec=spec, t_ms=t_ms, bar=bar))
        return tuple(events)

    def _engine_events(self, *, spec: InstrumentSpec, t_ms: int, bar: Bar) -> tuple[CashEventLike, ...]:
        """The ``borrow_fee`` and ``carry`` events of one session close (17.3, rulings R176 and R177).

        One event per (instrument, session), stamped with the session's last bar plus one interval minus
        one millisecond, so ``bar_of(t_ms)`` is the applying bar. A weekend is charged on Monday, which is
        what ``days`` counts. An instrument on the synthesised ``continuous`` calendar never closes a
        session and therefore owes no per-session charge, which is right for crypto and is why every
        binary run generates none.
        """
        if spec.borrow_schedule_id is None and spec.carry_schedule_id is None:
            return ()
        days = self._grid.session_days(spec.id, t_ms)
        if days is None:
            return ()
        stamp = t_ms + spec.interval_ms - 1
        built: list[CashEventLike] = []
        for schedule_id, kind in ((spec.borrow_schedule_id, "borrow_fee"), (spec.carry_schedule_id, "carry")):
            if schedule_id is None:
                continue
            rate = fees.carry_schedule(schedule_id, schedules=self._carry_schedules).rate_ppm_per_day
            built.append(
                EngineCashEvent.build(
                    market_id=spec.id,
                    kind=kind,
                    t_ms=stamp,
                    detail={"rate_ppm_per_day": rate, "days": days, "mark_ticks": bar.close_bp},
                )
            )
        return tuple(built)

    def _apply_one_event(self, *, event: CashEventLike, spec: InstrumentSpec, bar: Bar | None,
                         t_ms: int) -> None:
        """Apply one cash event to every agent, in ``agent_id`` order, and journal one event each.

        Nothing is written for an agent whose position is zero before and after (17.3). A ``split`` and a
        ``roll`` first expire every resting order on the instrument, because a price in the old scale is
        not a price any more (ruling R153).

        A debit expires the agent's whole book with ``reason = "debit"`` whenever it leaves
        ``reserved_cents`` above ``max(0, cash_cents)``, which is wider than ruling R179's literal
        trigger ("the event that took cash below zero"): a charge that leaves cash positive but under
        the reservations would break 8.9's ``reserved_cents(a) <= max(0, cash_cents(a))`` line, and that
        line is the one the invariant asserts. The widening is reported as a contract issue.
        """
        if event.kind in ("split", "roll"):
            expiry = "corporate_action" if event.kind == "split" else "roll"
            for agent_id in self.agent_ids():
                state = self._states[agent_id]
                for row in sorted(state.resting.values(), key=_by_order_id):
                    if row.market_id == spec.id:
                        self._expire(state, row, reason=expiry, t_ms=t_ms, phase="settle")
        for agent_id in self.agent_ids():
            state = self._states[agent_id]
            leg = state.legs.get(spec.id)
            if leg is None or leg.position == 0:
                continue
            before = leg.position
            avg_before = leg.avg_cost_bp
            order_ids: tuple[str, ...] = ()
            delta = 0
            if event.kind == "funding":
                delta = self._rate_cash(spec=spec, event=event, position=before, bar=bar, long_pays=True)
            elif event.kind == "carry":
                delta = self._rate_cash(spec=spec, event=event, position=before, bar=bar, long_pays=False)
            elif event.kind == "borrow_fee":
                if before >= 0:
                    continue
                delta = -abs(self._rate_cash(spec=spec, event=event, position=before, bar=bar,
                                             long_pays=False))
            elif event.kind == "dividend":
                delta = self._dividend_cash(event=event, position=before)
            elif event.kind == "split":
                numerator = _detail_int(event, "numerator", 1)
                denominator = _detail_int(event, "denominator", 1)
                leg.position = split_position_milli(before, numerator, denominator)
                leg.avg_cost_bp = round_half_up(avg_before * denominator, numerator)
            elif event.kind in ("roll", "forced_flat"):
                order_ids = self._event_fills(event=event, spec=spec, agent_id=agent_id, leg=leg, bar=bar,
                                              t_ms=t_ms)
            else:  # pragma: no cover - CASH_EVENT_KINDS is closed
                raise InvalidConfigError("unknown cash event kind", kind=event.kind, market_id=spec.id)
            if delta != 0:
                state.cash_cents += delta
                if state.reserved_cents > max(0, state.cash_cents):
                    self._expire_all(state, reason="debit", t_ms=t_ms, phase="settle")
            self._journal.emit(
                _CASH_EVENT_APPLIED,
                bar_ms=t_ms,
                phase="settle",
                agent_id=agent_id,
                market_id=spec.id,
                cash_event_id=event.cash_event_id,
                kind=event.kind,
                origin=event.origin,
                position_before=before,
                position_after=leg.position,
                avg_cost_ticks_before=avg_before,
                avg_cost_ticks_after=leg.avg_cost_bp,
                cash_delta_cents=delta,
                order_ids=order_ids,
                detail=dict(event.detail),
            )

    def _event_fills(self, *, event: CashEventLike, spec: InstrumentSpec, agent_id: str, leg: _Leg,
                     bar: Bar | None, t_ms: int) -> tuple[str, ...]:
        """The fills a ``roll`` or a ``forced_flat`` creates (17.3, rulings R150 and R152).

        A roll closes the position at the old contract's price and reopens it at the new one, so a
        position never earns or loses the gap: it pays two fills. The reopening leg goes through
        ``truncate_for_cash`` and the short-notional rule like any order, so a position can shrink across
        a roll and the residual is in that leg's ``unfilled_size`` and in ``position_after`` (R198).
        """
        schedule = fees.fee_schedule(spec.fee_schedule_id, schedules=self._schedules)
        view = self._view(spec)
        legs: list[tuple[int, str, int]] = []
        if event.kind == "roll":
            position = leg.position
            legs.append((_detail_int(event, "from_price_ticks", 0), "sell" if position > 0 else "buy",
                         abs(position)))
            legs.append((_detail_int(event, "to_price_ticks", 0), "buy" if position > 0 else "sell",
                         abs(position)))
        else:
            price = _detail_int(event, "price_ticks", bar.close_bp if bar is not None else 0)
            legs.append((price, "sell" if leg.position > 0 else "buy", abs(leg.position)))
        order_ids: list[str] = []
        for price, side, size in legs:
            if size <= 0 or price <= 0:
                continue
            capped = self._short_capped(spec, leg.position, side, size)
            if capped <= 0:
                continue
            order = LiquidityOrder(side=side, kind="market", size_milli=self._to_milli(spec, capped))
            quoted = event_fill(order, price_ticks=price, schedule=schedule, market_view=view)
            order_id = self._new_order_id()
            self._emit_placed(
                order_id=order_id, agent_id=agent_id, market_id=spec.id, kind="market", side=side,
                price_bp=None, size=capped, ttl_bars=None, expires_at_ms=None, reserved_cents=0,
                origin=event.kind, decided_at_ms=t_ms, t_ms=t_ms, phase="settle",
            )
            entry = _Ready(
                agent_id=agent_id,
                order_id=order_id,
                market_id=spec.id,
                decided_at_ms=t_ms,
                order=order,
                size=capped,
                resting=None,
            )
            self._apply_fill(entry=entry, spec=spec, fill=quoted, schedule=schedule, view=view, t_ms=t_ms,
                             phase="settle")
            order_ids.append(order_id)
        return tuple(order_ids)

    def _rate_cash(self, *, spec: InstrumentSpec, event: CashEventLike, position: int, bar: Bar | None,
                   long_pays: bool) -> int:
        """``funding``, ``borrow_fee`` and ``carry``: a rate on the marked notional, signed (17.3).

        Rounded against the agent on both sides: what it pays is a ceiling and what it receives a floor.
        ``long_pays`` separates ``funding`` (a long pays a positive rate and a short receives) from
        ``carry`` (a long receives a positive rate and pays a negative one).
        """
        rate = _detail_int(event, "rate_ppm", _detail_int(event, "rate_ppm_per_day", 0))
        days = max(1, _detail_int(event, "days", 1))
        mark = _detail_int(event, "mark_ticks", bar.close_bp if bar is not None else 0)
        if rate == 0 or mark <= 0 or position == 0:
            return 0
        product = notional_micro(abs(position), mark, spec.tick_size_micro, spec.point_value_micro)
        product *= abs(rate) * days
        denominator = NOTIONAL_DENOMINATOR * PPM_ONE
        long_side = position > 0
        rate_positive = rate > 0
        pays = (long_side == rate_positive) if long_pays else (long_side != rate_positive)
        if pays:
            return -_ceil_div(product, denominator)
        return product // denominator

    @staticmethod
    def _dividend_cash(*, event: CashEventLike, position: int) -> int:
        """A dividend per unit held: a long receives the floor, a short pays the ceiling (17.3)."""
        per_unit = _detail_int(event, "dividend_micro", 0)
        if per_unit == 0 or position == 0:
            return 0
        denominator = MILLI * MICRO // CENTS_PER_UNIT
        magnitude = abs(position) * abs(per_unit)
        receives = (position > 0) == (per_unit > 0)
        if receives:
            return magnitude // denominator
        return -_ceil_div(magnitude, denominator)

    # ----------------------------------------------------------------------
    # Netting, cash and reservations
    # ----------------------------------------------------------------------
    def _net(self, *, spec: InstrumentSpec, position: int, avg_cost: int, side: str, size: int,
             price: int) -> tuple[int, int, int, int, int]:
        """Section 8.5's netting at one price: close the opposite leg first, then open the rest.

        On a binary the opposite leg is the complement (a NO contract is a long in the complement and
        pays up front, so closing it *receives* and opening it *pays*). On a continuous instrument the
        opposite leg is a liability: a sell beyond the long **receives** at the fill price and a buy
        beyond the short **pays** to cover (ruling R154).

        Returns:
            ``(close_size, open_size, cash_delta_cents, position_after, avg_cost_after)``.
        """
        if size <= 0:
            return (0, 0, 0, position, avg_cost)
        closable = max(0, -position) if side == "buy" else max(0, position)
        close_size = min(size, closable)
        open_size = size - close_size
        after = position + size if side == "buy" else position - size
        if spec.is_binary:
            if side == "buy":
                delta = proceeds_cents(close_size, BP_ONE - price) - cost_cents(open_size, price)
            else:
                delta = proceeds_cents(close_size, price) - cost_cents(open_size, BP_ONE - price)
        else:
            tick, point = spec.tick_size_micro, spec.point_value_micro
            if side == "buy":
                delta = -cash_out_cents(close_size, price, tick, point)
                delta -= cash_out_cents(open_size, price, tick, point)
            else:
                delta = cash_in_cents(close_size, price, tick, point)
                delta += cash_in_cents(open_size, price, tick, point)
        return (close_size, open_size, delta, after,
                _avg_cost_after(after=after, open_size=open_size, price=price, previous=avg_cost))

    def _affordable(self, *, spec: InstrumentSpec, position: int, side: str, price: int, requested: int,
                    available: int, schedule: FeeSchedule, role: str,
                    resting: _Resting | None = None) -> int:
        """The largest size the agent's free cash can pay for, fee included (8.5 and 8.6 step 5).

        Section 8.5 spells the truncation as ``floor(free_cash / unit_cost)`` over the opening part. That
        formula ignores the fee, which is also paid out of cash, so it can leave cash below zero, and it
        is conservative in the other direction because ``cost_cents(k, p) <= k * cost_cents(1, p)``. What
        is implemented is the property the invariant asserts: the largest size whose **total** outlay
        (the opening cost, minus the closing proceeds, plus the fee) the free cash can pay, plus the
        short-notional rule of 17.3 on a continuous opening short. On a pure opening fill with no fee the
        two agree exactly. The deviation is reported as a contract issue.

        ``resting`` is the row behind a limit fill, and the third term of the predicate is its reason:
        8.5 sizes a reservation at the worst-case opening **cost** and says nothing about the maker fee,
        which is paid out of the same cash, so a fill that spent every reserved cent would leave a
        remainder resting against a reservation the agent no longer holds and 8.9's
        ``reserved_cents(a) <= max(0, cash_cents(a))`` would be false by the fee. The predicate therefore
        asks what the invariant asks: after this fill, does the cash still cover every reservation,
        including the one the remainder keeps. It is reported as a contract issue against 8.5.

        The predicate is true at ``0`` (the invariant held before the fill) and false after its largest
        true size (the outlay falls while the opposite leg closes and rises once the new leg opens), so a
        bisection finds that size; the bisection only ever accepts a size the predicate holds at, so the
        invariant is preserved even where the remainder term makes the predicate non-monotone.
        """
        if requested <= 0:
            return 0

        def affordable(size: int) -> bool:
            if size < 0:
                return False
            _close, open_size, delta, _after, _avg = self._net(
                spec=spec, position=position, avg_cost=0, side=side, size=size, price=price
            )
            fee = fees.fee_cents(
                schedule,
                size=size if spec.is_binary else self._to_milli(spec, size),
                price_bp=price,
                role=role,
                side=side,
                tick_size_micro=spec.tick_size_micro,
                point_value_micro=spec.point_value_micro,
            )
            remainder = 0
            if resting is not None:
                remainder = self._reservation(
                    spec, resting.side, resting.remaining - size, resting.limit_price_bp
                )
            if available + delta - fee - remainder < 0:
                return False
            if not spec.is_binary and side == "sell" and open_size > 0:
                notional = cash_out_cents(open_size, price, spec.tick_size_micro, spec.point_value_micro)
                if notional > available:
                    return False
            return True

        if affordable(requested):
            return requested
        low, high = 0, requested
        while high - low > 1:
            middle = (low + high) // 2
            if affordable(middle):
                low = middle
            else:
                high = middle
        return low

    def _reservation(self, spec: InstrumentSpec, side: str, size: int, limit_price: int) -> int:
        """The worst-case opening cost a resting order earmarks (8.5).

        On a binary that is ``cost_cents(size, L)`` for a buy and ``cost_cents(size, 10_000 - L)`` for a
        sell, because a sell beyond the long opens a NO leg that pays up front. On a continuous
        instrument both sides reserve the notional at the limit price: a long pays it, and a short may
        not open beyond its free cash (17.3), so the same number is what the order must be able to fund.
        """
        if size <= 0:
            return 0
        if spec.is_binary:
            return cost_cents(size, limit_price) if side == "buy" else cost_cents(size, BP_ONE - limit_price)
        return cash_out_cents(size, limit_price, spec.tick_size_micro, spec.point_value_micro)

    @staticmethod
    def _short_capped(spec: InstrumentSpec, position: int, side: str, size: int) -> int:
        """Cap a sell at what a short-forbidden instrument allows: closing only (17.1, 17.3).

        ``spot_crypto`` is the kind that carries ``short_allowed = false``: its short is the ``perp``
        twin, not a negative spot position.
        """
        if spec.is_binary or spec.short_allowed or side != "sell":
            return size
        return min(size, max(0, position))

    @staticmethod
    def _free_cash(state: _AgentState, *, own_reserved: int = 0) -> int:
        """``max(0, cash - reserved)`` (8.5), with the order's own reservation given back to it.

        While a debit balance stands (``cash < 0``, ruling R179) this is ``0``, so no opening fill lands
        until a credit or a closing fill repays it.
        """
        return max(0, state.cash_cents - (state.reserved_cents - own_reserved))

    # ----------------------------------------------------------------------
    # Journal helpers
    # ----------------------------------------------------------------------
    def _emit_placed(self, *, order_id: str, agent_id: str, market_id: str, kind: str, side: str,
                     price_bp: int | None, size: int, ttl_bars: int | None, expires_at_ms: int | None,
                     reserved_cents: int, origin: str, decided_at_ms: int, t_ms: int, phase: str) -> None:
        """Write one ``order_placed``, carrying the bar its intent was decided at (16.2, ruling R111)."""
        self._journal.emit(
            _ORDER_PLACED,
            bar_ms=t_ms,
            phase=phase,
            order_id=order_id,
            agent_id=agent_id,
            market_id=market_id,
            kind=kind,
            side=side,
            price_bp=price_bp,
            size=size,
            ttl_bars=ttl_bars,
            expires_at_ms=expires_at_ms,
            reserved_cents=reserved_cents,
            origin=origin,
            decided_at_ms=decided_at_ms,
        )

    def _reject(self, item: _Pending, reason: str, detail: str) -> None:
        """Write one ``order_rejected`` for a drained intent that never becomes an order (8.6 step 0)."""
        self._journal.emit(
            _ORDER_REJECTED,
            bar_ms=item.drain_at_ms,
            phase="execute",
            agent_id=item.agent_id,
            market_id=item.market_id,
            item_index=item.item_index,
            reason=reason,
            detail=detail,
            decided_at_ms=item.decided_at_ms,
        )

    def _expire(self, state: _AgentState, row: _Resting, *, reason: str, t_ms: int, phase: str) -> None:
        """Take a resting order off the book, release its reservation and journal it."""
        if state.resting.get(row.order_id) is not row:
            return
        released = row.reserved_cents
        state.reserved_cents -= released
        row.reserved_cents = 0
        del state.resting[row.order_id]
        self._journal.emit(
            _ORDER_EXPIRED,
            bar_ms=t_ms,
            phase=phase,
            order_id=row.order_id,
            agent_id=row.agent_id,
            market_id=row.market_id,
            remaining_size=row.remaining,
            released_cents=released,
            reason=reason,
        )

    def _expire_all(self, state: _AgentState, *, reason: str, t_ms: int, phase: str) -> None:
        """Expire every resting order of one agent, whatever the instrument (ruling R179's debit rule)."""
        for row in sorted(state.resting.values(), key=_by_order_id):
            self._expire(state, row, reason=reason, t_ms=t_ms, phase=phase)

    def _new_order_id(self) -> str:
        """The next order id: ``o-<seq:08d>``, dense from ``o-00000001`` per run (section 2)."""
        self._next_order_seq += 1
        return f"o-{self._next_order_seq:08d}"

    # ----------------------------------------------------------------------
    # Small helpers
    # ----------------------------------------------------------------------
    def _agent(self, agent_id: str) -> _AgentState:
        """The agent's state, created with the run's bankroll the first time it is touched."""
        state = self._states.get(agent_id)
        if state is None:
            state = _AgentState(
                cash_cents=self._config.bankroll_cents,
                peak_equity_cents=self._config.bankroll_cents,
                equity_cents=self._config.bankroll_cents,
            )
            self._states[agent_id] = state
        return state

    @staticmethod
    def _leg(state: _AgentState, market_id: str) -> _Leg:
        """The agent's leg on one instrument, created flat the first time it is touched."""
        leg = state.legs.get(market_id)
        if leg is None:
            leg = _Leg()
            state.legs[market_id] = leg
        return leg

    def _spec(self, market: InstrumentLike) -> InstrumentSpec:
        """The instrument's base view, read once per instrument and cached."""
        spec = self._specs.get(market.id)
        if spec is None:
            spec = instrument_spec(market)
            self._specs[market.id] = spec
            self._grid.register(spec)
        return spec

    def _view(self, spec: InstrumentSpec) -> LiquidityMarketView:
        """The market as a model may see it: no outcome, no resolution instant, no identity (R114).

        ``liquidity_decile`` is ``-1``: it is a training-fold projection of the manifest's ``impact``
        block (ruling R135), which only ``calibrated_impact`` reads and which no manifest carries yet.
        """
        return LiquidityMarketView(
            market_id=spec.id,
            provider=spec.provider,
            category=spec.category,
            currency=spec.currency,
            fee_schedule_id=spec.fee_schedule_id,
            source=spec.source,
            interval_min=spec.interval_min,
            liquidity_decile=-1,
            kind=spec.kind,
            tick_size_micro=spec.tick_size_micro,
            point_value_micro=spec.point_value_micro,
            short_allowed=spec.short_allowed,
        )

    @staticmethod
    def _to_milli(spec: InstrumentSpec, size: int) -> int:
        """A size in the instrument's units, as milli-units for the liquidity boundary (17.1)."""
        return size * MILLI if spec.is_binary else size

    @staticmethod
    def _from_milli(spec: InstrumentSpec, size_milli: int) -> int:
        """A milli size back in the instrument's units: whole contracts on a binary, milli-units else.

        Money is integral, so a partial contract is not a fill; a milli-coin is (rulings R148, R173).
        """
        return size_milli // MILLI if spec.is_binary else size_milli

    def _value_cents(self, spec: InstrumentSpec, position: int, price: int) -> int:
        """The signed marked value of a position at one price (8.7 and 17.1)."""
        if position == 0:
            return 0
        if spec.is_binary:
            if position > 0:
                return position * price // CENTS_PER_UNIT
            return -position * (BP_ONE - price) // CENTS_PER_UNIT
        return mark_value_cents(position, price, spec.tick_size_micro, spec.point_value_micro)

    def _tradable(self, spec: InstrumentSpec, t_ms: int, bar: Bar | None) -> bool:
        """``tradable(i, t)`` of 5.3 and 17.2: the predicate a **fill** may land under.

        A binary is ``listed and t + interval <= close_at_ms and not settles``, so no fill exists at
        ``bar_of(close_at_ms)`` or at ``bar_of(resolved_at_ms)`` (ruling R9). A continuous instrument is
        ``open(i, t) and t < last_bar(i)``, and ``last_bar`` needs the run's end: when the config carries
        no ``t1_ms`` the instrument's own delisting bounds it, and when neither is known execution
        refuses no fill of its own and the runner's ``force_flat`` bar is the only close.
        """
        if bar is None:
            return False
        if spec.is_binary:
            first = bar_of(spec.listed_at_ms, spec.interval_min)
            settling = bar_of(spec.resolved_at_ms, spec.interval_min)
            listed = first <= t_ms <= settling
            return listed and t_ms + spec.interval_ms <= spec.close_at_ms and t_ms != settling
        if t_ms < bar_of(spec.listed_at_ms, spec.interval_min):
            return False
        if not self._grid.covers(spec.id, t_ms):
            return False
        last = self._grid.last_bar_or_none(spec.id)
        return last is None or t_ms < last


def _ceil_div(numerator: int, denominator: int) -> int:
    """``ceil(numerator / denominator)`` in integers, for a positive denominator."""
    return -((-numerator) // denominator)


def _by_order_id(row: _Resting) -> str:
    """Resting orders of one market are tried in ``order_id`` order: time priority (section 3)."""
    return row.order_id


def _avg_cost_after(*, after: int, open_size: int, price: int, previous: int) -> int:
    """The volume-weighted entry price of the open leg: unchanged on a close, ``0`` when flat (8.5)."""
    if after == 0:
        return 0
    if open_size <= 0:
        return previous
    existing = abs(after) - open_size
    if existing <= 0:
        return price
    return round_half_up(existing * previous + open_size * price, existing + open_size)


def _kind_rank(kind: str) -> int:
    """The position of a cash event kind in :data:`CASH_EVENT_KINDS` (ruling R193's order)."""
    return CASH_EVENT_KINDS.index(kind) if kind in CASH_EVENT_KINDS else len(CASH_EVENT_KINDS)


def _detail_int(event: CashEventLike, key: str, fallback: int) -> int:
    """One integer field of a cash event's ``detail``, or the fallback when the record omits it."""
    value = event.detail.get(key, fallback)
    return value if isinstance(value, int) and not isinstance(value, bool) else fallback


def _is_cash_event(candidate: object) -> bool:
    """Whether an object carries the six fields of a ``CashEvent`` (17.3), whatever class it is."""
    names = ("cash_event_id", "market_id", "kind", "t_ms", "origin", "detail")
    return all(hasattr(candidate, name) for name in names)


class _SessionGrid:
    """The bar arithmetic execution needs, over the sealed session calendars it was handed (17.2).

    E1's ``Calendar`` is the run's implementation of ``last_bar``, ``next_bar`` and ``prev_bar`` (ruling
    R187), and ``Execution`` is given ``calendars`` rather than a ``Calendar`` (8.6, ruling R174), so this
    class answers the same three questions from the calendars plus the config's window. The session
    predicate is the contract's (``t < close_ms and t + interval > open_ms``); gate G2 lands
    ``pmx.data.sessions`` and architecture rule 11 then makes that module the one implementation, which
    is reported as a contract issue.
    """

    __slots__ = ("_config", "_sessions", "_specs")

    def __init__(self, *, config: RunConfig, calendars: Mapping[str, object]) -> None:
        self._config = config
        self._specs: dict[str, InstrumentSpec] = {}
        self._sessions = {calendar_id: _sessions_of(calendar) for calendar_id, calendar in calendars.items()}

    def register(self, spec: InstrumentSpec) -> None:
        """Remember an instrument's calendar, interval and window, the first time execution sees it."""
        self._specs[spec.id] = spec

    def covers(self, market_id: str, t_ms: int) -> bool:
        """Whether a bar of this instrument exists at ``t_ms``: its interval intersects a session.

        An instrument whose calendar is absent or synthesised (``continuous``, one session covering
        everything) is covered at every grid point, which is 7.2's dense grid for a binary (R185).
        """
        spec = self._specs.get(market_id)
        if spec is None:
            return True
        windows = self._sessions.get(spec.session_calendar_id, ())
        if not windows:
            return True
        end = t_ms + spec.interval_ms
        return any(t_ms < close_ms and end > open_ms for open_ms, close_ms in windows)

    def next_bar(self, market_id: str, t_ms: int) -> int | None:
        """The instrument's next bar after ``t_ms``, which after a Friday session is Monday's first bar.

        Bounded by the run's ``t1_ms`` and not by the instrument's delisting, because the bar an intent
        drains at may be a bar the instrument is no longer tradable at: that item is owed its
        ``order_rejected(not_tradable)`` (16.2), and a queue that dropped it would write nothing.
        """
        spec = self._specs.get(market_id)
        if spec is None:
            return t_ms + interval_ms(self._config.interval_min)
        limit = self._run_limit()
        candidate = t_ms + spec.interval_ms
        while candidate < limit:
            if self.covers(market_id, candidate):
                return candidate
            candidate += spec.interval_ms
        return None

    def prev_bar(self, market_id: str, t_ms: int) -> int | None:
        """The instrument's last bar before ``t_ms``, or ``None`` when that lies outside the run.

        ``applies_at`` reads it, and the ``None`` is load bearing: a corporate event dated on the run's
        first bar of the instrument has no old-regime bar inside the run and is not applied, because no
        position can exist before it (17.3).
        """
        spec = self._specs.get(market_id)
        if spec is None:
            return None
        floor_ms = max(bar_of(spec.listed_at_ms, spec.interval_min), self._t0(spec))
        candidate = t_ms - spec.interval_ms
        while candidate >= floor_ms:
            if self.covers(market_id, candidate):
                return candidate
            candidate -= spec.interval_ms
        return None

    def last_bar(self, market_id: str) -> int:
        """``last_bar(i)``: the last bar of the run at which the instrument is open (17.2)."""
        found = self.last_bar_or_none(market_id)
        if found is None:
            raise InvalidConfigError("the instrument has no last bar inside the run", market_id=market_id)
        return found

    def last_bar_or_none(self, market_id: str) -> int | None:
        """``last_bar(i)``, or ``None`` when neither the run nor the instrument bounds it yet."""
        spec = self._specs.get(market_id)
        if spec is None:
            return None
        bounds = [self._run_limit()]
        if spec.delisted_at_ms is not None:
            bounds.append(bar_of(spec.delisted_at_ms, spec.interval_min))
        limit = min(bounds)
        if limit >= _NO_LIMIT:
            return None
        return self.prev_bar(market_id, limit)

    def session_days(self, market_id: str, t_ms: int) -> int | None:
        """Calendar days since the previous session close, when ``t_ms`` is a session's **last** bar.

        ``None`` when the bar is not a session close, which is every bar of the synthesised
        ``continuous`` calendar: a market that never closes owes no per-session charge.
        """
        spec = self._specs.get(market_id)
        if spec is None:
            return None
        windows = self._sessions.get(spec.session_calendar_id, ())
        if not windows:
            return None
        step = spec.interval_ms
        for index, (open_ms, close_ms) in enumerate(windows):
            if not (t_ms < close_ms and t_ms + step > open_ms):
                continue
            if t_ms + step < close_ms and self.covers(market_id, t_ms + step):
                return None
            if index == 0:
                return 1
            previous_close = windows[index - 1][1]
            return max(1, (day_start_ms(close_ms) - day_start_ms(previous_close)) // MS_PER_DAY)
        return None

    def _t0(self, spec: InstrumentSpec) -> int:
        t0 = self._config.t0_ms
        return bar_of(t0, spec.interval_min) if t0 is not None else 0

    def _run_limit(self) -> int:
        """The first grid point outside the run: its ``t1_ms``, or "no bound is known"."""
        t1 = self._config.t1_ms
        return t1 if t1 is not None else _NO_LIMIT


#: Stands for "no bound is known": with neither a ``t1_ms`` nor a delisting, an instrument's last bar is
#: not a fact execution holds, and it says so rather than inventing one.
_NO_LIMIT: int = 1 << 62


def _sessions_of(calendar: object) -> tuple[tuple[int, int], ...]:
    """The ``(open_ms, close_ms)`` pairs of a session calendar, whatever shape it arrives in.

    ``SessionCalendar`` is a ``pmx.types`` dataclass gate G2 lands (17.9); a mapping read straight from
    ``session_calendar.v1.json`` is the other shape a caller can hold in wave 2, and both are read here.
    """
    sessions: object = getattr(calendar, "sessions", None)
    if sessions is None and isinstance(calendar, Mapping):
        sessions = calendar.get("sessions")
    if not isinstance(sessions, tuple | list):
        return ()
    pairs: list[tuple[int, int]] = []
    for session in sessions:
        open_ms = _session_field(session, "open_ms")
        close_ms = _session_field(session, "close_ms")
        if open_ms is None or close_ms is None or close_ms <= open_ms:
            continue
        pairs.append((open_ms, close_ms))
    return tuple(sorted(pairs))


def _session_field(session: object, name: str) -> int | None:
    """One instant of a session, read off an attribute or a mapping key."""
    value: object = getattr(session, name, None)
    if value is None and isinstance(session, Mapping):
        value = session.get(name)
    return value if isinstance(value, int) and not isinstance(value, bool) else None
