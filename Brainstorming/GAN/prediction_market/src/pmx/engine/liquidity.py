"""The ``LiquidityModel`` protocol, the envelope rule and the ``historical`` model (CONTRACTS_V2 16.1).

This is the one module in the repository that computes a fill price (ruling R113, architecture rule 9).
``Execution`` validates, nets, truncates against cash and journals; it asks the run's model what a fill
costs and never invents a price of its own. That split is what lets wave 7's ``calibrated_impact`` and
wave 10's ``adversarial_mm`` plug in without touching the engine.

Two things are worth reading before changing anything here.

**The batch shape is not a convenience.** ``quote_bar`` is called once per (market, bar) with every order
drained there, because under the decision latency rule of 16.2 all of them were queued a bar earlier and
arrive at the same open: pricing them one at a time would invent an arrival sequence the tape never had,
and rationing a scarce volume cap fairly is impossible without seeing the whole batch (ruling R126).

**The envelope is a constraint, not a parameter.** :func:`check_envelope` is executable: it drives a model
over a batch twice and once per permutation and reports which of the five rules it broke. A model may
widen a spread; it may not print a price the tape never showed, fill more than the cap, let arrival order
matter, or discount a fee.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, localcontext
from itertools import permutations
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from pmx.engine.fees import (
    BINARY_POINT_VALUE_MICRO,
    BINARY_TICK_SIZE_MICRO,
    MILLI,
    PRICE_TICKS_MAX,
    FeeSchedule,
    fee_cents,
)
from pmx.errors import InvalidConfigError
from pmx.types import BP_ONE, Bar, RunConfig, clamp_price_bp, round_half_up

if TYPE_CHECKING:  # pragma: no cover - import-time typing only
    from collections.abc import Mapping, Sequence

__all__ = [
    "CAP_UNLIMITED",
    "ENVELOPE_BREACHES",
    "LIQUIDITY_MODELS",
    "MILLI",
    "UNFILLED_REASONS",
    "Fill",
    "HistoricalLiquidity",
    "LiquidityMarketView",
    "LiquidityModel",
    "LiquidityOrder",
    "ObservedFlow",
    "allocate_cap",
    "cap_milli",
    "check_envelope",
    "clamp_price",
    "envelope_bounds",
    "event_fill",
    "finalise_fill",
    "half_spread_ticks",
    "make_liquidity",
    "slippage_ticks",
    "truncate_for_cash",
]

#: The three implementations the contract declares (16.1). Only ``historical`` exists in wave 2.
LIQUIDITY_MODELS: tuple[str, ...] = ("historical", "calibrated_impact", "adversarial_mm")

#: ``filled.unfilled_reason`` (9.2). The precedence when more than one truncation applies is this order:
#: the reason names the **first that fired**, so a market order rationed by the cap and then cut by cash
#: reports ``volume_cap`` and the projection's diagnosis matches the engine's (8.6).
UNFILLED_REASONS: tuple[str, ...] = ("none", "zero_volume", "no_cross", "no_liquidity", "volume_cap", "cash")

#: ``filled.price_source`` (9.2, rulings R111, R138 and R152). ``vwap`` is not here: R113 abolished the
#: vwap base and no model may return the old spelling.
PRICE_SOURCES: tuple[str, ...] = ("open", "quote", "limit", "impact", "mm", "event")

#: What :func:`cap_milli` returns for a market whose tape carries no volume because its source has none
#: (``source == "reconstructed"``, ruling R41 restated inside the envelope): there is no cap to ration.
#: Returning the arithmetic ``0`` instead would make the demo pack, the only committed dataset, fill
#: nothing.
CAP_UNLIMITED: int = -1

#: The breaches :func:`check_envelope` can report, in the order it reports them (16.1).
ENVELOPE_BREACHES: tuple[str, ...] = (
    "quote_inside_spread",
    "outside_range",
    "over_cap",
    "order_dependent",
    "not_deterministic",
    "negative_fill",
    "size_not_conserved",
    "bad_reason",
    "bad_fee",
)

#: Above this batch size :func:`check_envelope` drives rotations and the reverse instead of every
#: permutation: ``7!`` calls per generated case turns a property test into a hang, and a model that is
#: order dependent shows it on a rotation.
_MAX_PERMUTATION_ORDERS: int = 5


@dataclass(frozen=True, slots=True)
class LiquidityMarketView:
    """Everything a model may see of a market, and nothing else (ruling R114).

    No ``resolution``, no ``resolved_at_ms``, no ``final_price_bp`` and no agent id: section 7.9 would
    otherwise be reachable through the execution path, and a price that could depend on who is buying is
    not one tape for everyone.

    ``source`` is the market's own (``imported``, or ``reconstructed`` for the migrated v1 pack, 7.2);
    the envelope reads only whether it is ``reconstructed``.
    """

    market_id: str
    provider: str
    category: str
    currency: str
    fee_schedule_id: str
    source: str
    interval_min: int
    liquidity_decile: int = -1
    kind: str = "binary"
    tick_size_micro: int = BINARY_TICK_SIZE_MICRO
    point_value_micro: int = BINARY_POINT_VALUE_MICRO
    short_allowed: bool = True


#: The view a call that names no market reads as (ruling R173): a binary, at the binary scales.
_BINARY_VIEW = LiquidityMarketView(
    market_id="",
    provider="",
    category="",
    currency="",
    fee_schedule_id="",
    source="imported",
    interval_min=1_440,
)


@dataclass(frozen=True, slots=True)
class LiquidityOrder:
    """One drained intent, carrying no identity at all (ruling R114).

    ``size_milli`` is ``size * MILLI`` on a binary and the order's own milli size on a continuous
    instrument, whose quantities are already milli-units (rulings R148 and R173). ``limit_price_bp`` and
    ``resting_since_ms`` are what let a model compute ``min(L, bar.open_bp)``, ``no_cross`` and the maker
    fee role, none of which is knowable from a bare ``(side, size)`` pair (ruling R126).
    """

    side: str
    kind: str
    size_milli: int
    limit_price_bp: int | None = None
    resting_since_ms: int | None = None


@dataclass(frozen=True, slots=True)
class Fill:
    """What a model answers for one order: a price inside the envelope and the fee that price implies."""

    price_bp: int
    base_price_bp: int
    slippage_bp: int
    filled_milli: int
    unfilled_milli: int
    unfilled_reason: str
    price_source: str
    role: str
    fee_cents: int


@dataclass(frozen=True, slots=True)
class ObservedFlow:
    """The one channel a model carries state through: what actually filled on a (market, bar).

    Aggregate and identity-free, which is what makes it the population's revealed behaviour without
    breaching ruling R114.
    """

    market_id: str
    t_ms: int
    bought_milli: int
    sold_milli: int
    n_fills: int
    last_fill_price_bp: int


@runtime_checkable
class LiquidityModel(Protocol):
    """The pricing surface every implementation satisfies (16.1)."""

    model_id: str
    params_hash: str

    def quote_bar(
        self,
        market_view: LiquidityMarketView,
        bar: Bar,
        orders: Sequence[LiquidityOrder],
        *,
        schedule: FeeSchedule,
        now_ms: int,
    ) -> tuple[Fill, ...]:
        """One :class:`Fill` per order, in the same positions."""
        ...

    def on_bar_end(self, observed_flow: ObservedFlow) -> None:
        """Called once per (market, bar) after :meth:`quote_bar`, in canonical market order."""
        ...


# --------------------------------------------------------------------------------------------------
# The envelope arithmetic, shared by every implementation
# --------------------------------------------------------------------------------------------------
def clamp_price(x: int, *, view: LiquidityMarketView | None = None) -> int:
    """A legal price of this instrument: ``clamp_price_bp`` on a binary, ``1..PRICE_TICKS_MAX`` otherwise.

    A ``clamp_price_bp`` left on a continuous path would print 6 341 257 ticks as 9 999, which is exactly
    what E2's continuous envelope test fails a model for (ruling R173).
    """
    if view is None or view.kind == "binary":
        return clamp_price_bp(x)
    return max(1, min(PRICE_TICKS_MAX, x))


def envelope_bounds(bar: Bar, *, kind: str = "binary") -> tuple[int, int]:
    """The ``(low, high)`` a fill must sit inside, after the legal-price clamp (rule 3, ruling R173)."""
    view = _BINARY_VIEW if kind == "binary" else LiquidityMarketView(
        market_id="",
        provider="",
        category="",
        currency="",
        fee_schedule_id="",
        source="imported",
        interval_min=1_440,
        kind=kind,
    )
    low = clamp_price(bar.low_bp, view=view)
    high = clamp_price(bar.high_bp, view=view)
    return (min(low, high), max(low, high))


def slippage_ticks(base: int, *, config: RunConfig, taken_pct: int, view: LiquidityMarketView | None = None) -> int:
    """Section 8.6 step 4's slippage, in the instrument's ticks (ruling R173).

    On a binary it is ``slippage_bp_per_pct * taken_pct``, an absolute number of basis points of the
    payout, which is the v2 rule unchanged. On a continuous kind it is the same number of basis points
    **relative to the price**, because ten basis points of a 63 412 tick price is not ten ticks.
    """
    if taken_pct <= 0 or config.slippage_bp_per_pct <= 0:
        return 0
    if view is None or view.kind == "binary":
        return config.slippage_bp_per_pct * taken_pct
    return round_half_up(base * config.slippage_bp_per_pct * taken_pct, BP_ONE)


def cap_milli(bar: Bar, *, config: RunConfig, source: str) -> int:
    """The milli-units every order of this (market, bar) shares (rule 2), or :data:`CAP_UNLIMITED`.

    A market with ``source == "reconstructed"`` carries no volume because its source has none (PRD 3.3),
    not because nothing traded, so rule 2 does not apply to it and there is no cap to ration.
    """
    if source == "reconstructed":
        return CAP_UNLIMITED
    return (max(0, bar.volume_milli) * config.volume_cap_permille) // 1_000


def _tie_key(order: LiquidityOrder, index: int) -> tuple[int, str, str, int, int]:
    """Section 8.6 step 2's remainder tie-break: ``(-size_milli, side, kind, limit_price_bp)`` then order.

    Two orders that tie on all four keys are the same order in every respect the tape can see, so which
    of them takes the extra milli-unit changes no aggregate (rulings R127 and R141).
    """
    return (-order.size_milli, order.side, order.kind, order.limit_price_bp or 0, index)


def allocate_cap(orders: Sequence[LiquidityOrder], *, cap_milli: int) -> tuple[int, ...]:
    """Ration a shared cap **pro rata**, not first come first served (rulings R127 and R141).

    Order ``i`` receives ``(size_i * cap) // requested``, and the remainder, at most one milli-unit per
    order, goes to the largest fractional parts. Under arrival rationing two buys of 80 and 40 against a
    cap of 100 fill 80 and 20 in one sequence and 60 and 40 in the other, so both the multiset of fills
    and the aggregate notional move with the order the batch happened to arrive in, which envelope rule 4
    forbids and which under evolution turns a naming accident into a fitness edge.

    Args:
        orders: The orders sharing the cap, in the canonical order of section 3.
        cap_milli: The cap, or :data:`CAP_UNLIMITED` when the tape carries no volume to ration.

    Returns:
        One allocation per order, in the same positions, summing to at most ``cap_milli``.
    """
    requested = sum(max(0, order.size_milli) for order in orders)
    if not orders:
        return ()
    if cap_milli == CAP_UNLIMITED or requested <= cap_milli:
        return tuple(max(0, order.size_milli) for order in orders)
    if cap_milli <= 0 or requested <= 0:
        return tuple(0 for _ in orders)
    allocations = [(max(0, order.size_milli) * cap_milli) // requested for order in orders]
    remainder = cap_milli - sum(allocations)
    if remainder > 0:
        fractions = [(max(0, order.size_milli) * cap_milli) % requested for order in orders]
        ranked = sorted(range(len(orders)), key=lambda i: (-fractions[i], _tie_key(orders[i], i)))
        for index in ranked[:remainder]:
            allocations[index] += 1
    return tuple(allocations)


def half_spread_ticks(bar_prev: Bar, bar: Bar, *, schedule: FeeSchedule) -> int:
    """Corwin and Schultz (2012) on two consecutive bars' highs and lows, then the schedule's floor (17.4).

    A crypto or Yahoo bar carries no bid and no ask, and rule 1 of the envelope is then not
    "unconstrained": a tape without quotes still charges the spread its own ranges imply. ``Decimal`` is
    the one legal non-integer arithmetic here (section 1.3): ``ln``, ``sqrt`` and ``exp`` are correctly
    rounded by the decimal specification, so the estimate is identical on every platform, and the result
    is an integer number of ticks before anything is priced.

    A negative alpha (two trending bars) and a pair of flat bars both estimate zero, so a
    ``reconstructed`` bar of the demo pack, where every bar is flat, prices at the open exactly as it did
    before this floor existed. The estimate is the **floor** of the envelope, not its ceiling: rule 3
    still bounds a fill by the bar's range.
    """
    estimate = 0
    if bar_prev.low_bp > 0 and bar.low_bp > 0:
        with localcontext() as ctx:
            ctx.prec = 40
            h1, l1, h2, l2 = (Decimal(x) for x in (bar_prev.high_bp, bar_prev.low_bp, bar.high_bp, bar.low_bp))
            beta = (h1 / l1).ln() ** 2 + (h2 / l2).ln() ** 2
            gamma = (max(h1, h2) / min(l1, l2)).ln() ** 2
            k = Decimal(3) - Decimal(2) * Decimal(2).sqrt()
            alpha = ((Decimal(2) * beta).sqrt() - beta.sqrt()) / k - (gamma / k).sqrt()
            if alpha > 0:
                spread = Decimal(2) * (alpha.exp() - 1) / (1 + alpha.exp())
                estimate = int((spread * Decimal(bar.open_bp) / 2).to_integral_value(rounding=ROUND_HALF_UP))
    return max(estimate, schedule.min_half_spread_ticks)


def _role_of(order: LiquidityOrder) -> str:
    """``taker`` for a market order, ``maker`` for a resting limit fill (rule 5)."""
    return "taker" if order.kind == "market" else "maker"


def _fee_size(filled_milli: int, view: LiquidityMarketView) -> int:
    """The size ``fee_cents`` is called with: whole contracts on a binary, milli-units otherwise.

    A ``// MILLI`` on a continuous instrument would turn a one milli-coin fill into a fee on nothing
    (ruling R173).
    """
    return filled_milli // MILLI if view.kind == "binary" else filled_milli


def _fee_of(*, price: int, filled_milli: int, order: LiquidityOrder, schedule: FeeSchedule,
            view: LiquidityMarketView) -> int:
    """Envelope rule 5, in one place: the fee of the fill the journal writes and no other number."""
    return fee_cents(
        schedule,
        size=_fee_size(filled_milli, view),
        price_bp=price,
        role=_role_of(order),
        side=order.side,
        tick_size_micro=view.tick_size_micro,
        point_value_micro=view.point_value_micro,
    )


def finalise_fill(
    *,
    quoted_bp: int,
    base_bp: int,
    order: LiquidityOrder,
    bar: Bar,
    filled_milli: int,
    unfilled_reason: str,
    price_source: str,
    schedule: FeeSchedule,
    market_view: LiquidityMarketView | None = None,
) -> Fill:
    """Build a :class:`Fill` that is inside the envelope and whose fee is rule 5's, by construction.

    The price is clamped into the bar's range and into the instrument's legal price space, the slippage
    is the signed distance from the base in the order's own direction (never negative), the role follows
    the order kind, and the fee is computed from the price and the size the fill actually carries. This
    is the only constructor of a :class:`Fill` a model should use, which is what makes rules 3 and 5 hold
    for every implementation rather than for the careful ones.

    Args:
        quoted_bp: The price the model wants, before the envelope clamp.
        base_bp: The price before impact; equal to ``quoted_bp`` for a limit fill.
        order: The order being answered.
        bar: The execution bar, which bounds the price.
        filled_milli: How much fills, in milli-units; ``0`` for a fill that did not happen.
        unfilled_reason: One of :data:`UNFILLED_REASONS`; ignored when the order fills whole.
        price_source: One of :data:`PRICE_SOURCES`.
        schedule: The market's fee schedule.
        market_view: The market; ``None`` reads as a binary view (ruling R173).

    Returns:
        The fill, with ``filled_milli + unfilled_milli == order.size_milli``.

    Raises:
        InvalidConfigError: On a reason or a source outside its enum, or a size outside the order.
    """
    view = market_view if market_view is not None else _BINARY_VIEW
    if unfilled_reason not in UNFILLED_REASONS:
        raise InvalidConfigError("unfilled_reason is not one of UNFILLED_REASONS", reason=unfilled_reason)
    if price_source not in PRICE_SOURCES:
        raise InvalidConfigError("price_source is not one of PRICE_SOURCES", price_source=price_source)
    if not 0 <= filled_milli <= order.size_milli:
        raise InvalidConfigError("a fill is between zero and the order", filled=filled_milli, size=order.size_milli)
    low, high = envelope_bounds(bar, kind=view.kind)
    price = min(max(clamp_price(quoted_bp, view=view), low), high)
    base = min(max(clamp_price(base_bp, view=view), low), high)
    slippage = price - base if order.side == "buy" else base - price
    unfilled = order.size_milli - filled_milli
    reason = "none" if unfilled == 0 else unfilled_reason
    if unfilled > 0 and reason == "none":
        raise InvalidConfigError("an unfilled remainder needs a reason", size=order.size_milli, filled=filled_milli)
    return Fill(
        price_bp=price,
        base_price_bp=base,
        slippage_bp=max(0, slippage),
        filled_milli=filled_milli,
        unfilled_milli=unfilled,
        unfilled_reason=reason,
        price_source=price_source,
        role=_role_of(order),
        fee_cents=_fee_of(price=price, filled_milli=filled_milli, order=order, schedule=schedule, view=view),
    )


def truncate_for_cash(
    fill: Fill,
    *,
    max_filled_milli: int,
    schedule: FeeSchedule,
    market_view: LiquidityMarketView | None = None,
    order: LiquidityOrder | None = None,
) -> Fill:
    """Section 8.6 step 5: lower a fill to what cash allows, and re-establish rule 5 on the result.

    The fee is recomputed for the smaller size, because envelope rule 5 is stated over **the fill the
    journal writes** and not over an intermediate the journal never sees (ruling R130). The reason obeys
    8.6's precedence: a fill already truncated by the volume cap keeps ``volume_cap``, since that is the
    first truncation that fired, and only a fill the tape would have honoured whole reports ``cash``.

    Args:
        fill: The fill the model returned.
        max_filled_milli: The largest size the agent's cash can pay for.
        schedule: The market's fee schedule.
        market_view: The market; ``None`` reads as a binary view.
        order: The order the fill answers, when the caller has it; only its ``side`` and ``kind`` are
            read, and the fill's own ``role`` stands in when it is absent.

    Returns:
        The fill itself when nothing is cut, else a fill with a smaller size, a smaller fee and a reason.
    """
    view = market_view if market_view is not None else _BINARY_VIEW
    ceiling = max(0, max_filled_milli)
    if fill.filled_milli <= ceiling:
        return fill
    size_milli = fill.filled_milli + fill.unfilled_milli
    filled = ceiling
    reason = fill.unfilled_reason if fill.unfilled_reason != "none" else "cash"
    side = order.side if order is not None else ("buy" if fill.role == "taker" else "buy")
    kind = order.kind if order is not None else ("market" if fill.role == "taker" else "limit")
    shrunk = LiquidityOrder(side=side, kind=kind, size_milli=size_milli, limit_price_bp=None, resting_since_ms=None)
    return Fill(
        price_bp=fill.price_bp,
        base_price_bp=fill.base_price_bp,
        slippage_bp=fill.slippage_bp,
        filled_milli=filled,
        unfilled_milli=size_milli - filled,
        unfilled_reason="none" if filled == size_milli else reason,
        price_source=fill.price_source,
        role=fill.role,
        fee_cents=_fee_of(price=fill.price_bp, filled_milli=filled, order=shrunk, schedule=schedule, view=view),
    )


def event_fill(
    order: LiquidityOrder,
    *,
    price_ticks: int,
    schedule: FeeSchedule,
    market_view: LiquidityMarketView | None = None,
) -> Fill:
    """Price the fills execution creates without an agent's order (17.3, ruling R152).

    The two legs of a future's ``roll`` at the roll record's two prices, and the ``forced_flat`` at the
    close of ``last_bar(i)``. The envelope is satisfied by construction, because ``price_ticks`` is a
    price the tape printed, so ``check_envelope`` never drives this function: it is not a
    ``LiquidityModel`` and it is the only path that may emit ``price_source = "event"``.

    ``market_view`` is keyword-only with a binary default (preamble rule 2): without the instrument's
    scales a ``notional_bp`` fee, which is what every crypto and equity schedule charges, cannot be
    computed at all.
    """
    view = market_view if market_view is not None else _BINARY_VIEW
    price = clamp_price(price_ticks, view=view)
    return Fill(
        price_bp=price,
        base_price_bp=price,
        slippage_bp=0,
        filled_milli=order.size_milli,
        unfilled_milli=0,
        unfilled_reason="none",
        price_source="event",
        role="taker",
        fee_cents=fee_cents(
            schedule,
            size=_fee_size(order.size_milli, view),
            price_bp=price,
            role="taker",
            side=order.side,
            tick_size_micro=view.tick_size_micro,
            point_value_micro=view.point_value_micro,
        ),
    )


# --------------------------------------------------------------------------------------------------
# The historical model: section 8.6 steps 1 to 4, and nothing else
# --------------------------------------------------------------------------------------------------
class HistoricalLiquidity:
    """Section 8.6 steps 1 to 4: the bar's quote when it has one, else the bar's open, the volume cap and
    the linear slippage of ``RunConfig`` (16.1).

    ``params_hash`` is ``""``: the model has no parameter the config does not already carry, so two runs
    that differ in the tape they faced differ in ``config_hash`` alone.

    One implementation note the protocol forces. The half-spread floor of 17.4 needs the instrument's
    **previous** bar, and ``quote_bar`` is handed only the execution bar while ``ObservedFlow`` carries no
    bar at all: the model therefore remembers the last bar it was asked to price per market and uses it
    only when its ``t_ms`` is strictly earlier. When there is no earlier bar (the first bar of an
    instrument's life inside this run, or a bar nobody traded into) the schedule's
    ``min_half_spread_ticks`` stands alone rather than an estimate being fabricated from one bar. This is
    reported as a contract issue against 16.1.
    """

    __slots__ = ("_config", "_last_bar", "model_id", "params_hash")

    def __init__(self, config: RunConfig) -> None:
        self.model_id: str = "historical"
        self.params_hash: str = ""
        self._config = config
        self._last_bar: dict[str, Bar] = {}

    def quote_bar(
        self,
        market_view: LiquidityMarketView,
        bar: Bar,
        orders: Sequence[LiquidityOrder],
        *,
        schedule: FeeSchedule,
        now_ms: int,
    ) -> tuple[Fill, ...]:
        """One :class:`Fill` per order, in the same positions (16.1).

        The whole batch is priced from what the bar and the model's own earlier bars say, so the answer
        is a function of the batch as a set: the cap is rationed pro rata and each fill's slippage is a
        function of its **own** allocated size, which is what makes the multiset of fills invariant under
        permutation (envelope rule 4).
        """
        del now_ms  # the execution bar is `bar`; the model reads no clock of its own
        view = market_view
        reconstructed = view.source == "reconstructed"
        previous = self._last_bar.get(view.market_id)
        if previous is not None and previous.t_ms >= bar.t_ms:
            previous = None
        self._last_bar[view.market_id] = bar
        zero_volume = bar.volume_milli <= 0 and not reconstructed
        bases: list[int] = []
        sources: list[str] = []
        blocked: list[str | None] = []
        for order in orders:
            base, source, reason = self._base_of(order, bar, view, previous, schedule)
            bases.append(base)
            sources.append(source)
            blocked.append("zero_volume" if zero_volume else reason)
        eligible = [index for index, reason in enumerate(blocked) if reason is None]
        cap = cap_milli(bar, config=self._config, source=view.source)
        allocations = allocate_cap([orders[index] for index in eligible], cap_milli=cap)
        allocated = dict(zip(eligible, allocations, strict=True))
        fills: list[Fill] = []
        for index, order in enumerate(orders):
            reason = blocked[index]
            if reason is not None:
                fills.append(
                    finalise_fill(
                        quoted_bp=bases[index],
                        base_bp=bases[index],
                        order=order,
                        bar=bar,
                        filled_milli=0,
                        unfilled_reason=reason,
                        price_source=sources[index],
                        schedule=schedule,
                        market_view=view,
                    )
                )
                continue
            filled = allocated[index]
            if view.kind == "binary":
                filled -= filled % MILLI
            if order.kind == "limit":
                quoted = bases[index]
            else:
                taken_pct = 0 if reconstructed else (filled * 100) // max(1, bar.volume_milli)
                slip = slippage_ticks(bases[index], config=self._config, taken_pct=taken_pct, view=view)
                quoted = bases[index] + slip if order.side == "buy" else bases[index] - slip
            fills.append(
                finalise_fill(
                    quoted_bp=quoted,
                    base_bp=bases[index],
                    order=order,
                    bar=bar,
                    filled_milli=filled,
                    unfilled_reason="volume_cap",
                    price_source=sources[index],
                    schedule=schedule,
                    market_view=view,
                )
            )
        return tuple(fills)

    def on_bar_end(self, observed_flow: ObservedFlow) -> None:
        """``historical`` keeps no flow state: the tape it prices is the tape, whoever traded it."""
        del observed_flow

    def _base_of(
        self,
        order: LiquidityOrder,
        bar: Bar,
        view: LiquidityMarketView,
        previous: Bar | None,
        schedule: FeeSchedule,
    ) -> tuple[int, str, str | None]:
        """The base price of one order, its ``price_source``, and the reason it cannot fill at all.

        A limit order is priced by 8.6's crossing rule (``min(L, open)`` for a buy, ``max(L, open)`` for
        a sell) and reports ``no_cross`` when the bar's range never reaches ``L``. A market order takes
        the bar's quote on its side when the bar carries one, else the open plus or minus the half-spread
        floor of 17.4.
        """
        low, high = envelope_bounds(bar, kind=view.kind)
        if order.kind == "limit":
            limit = order.limit_price_bp
            if limit is None:
                return (min(max(bar.open_bp, low), high), "limit", "no_liquidity")
            crosses = bar.low_bp <= limit if order.side == "buy" else bar.high_bp >= limit
            raw = min(limit, bar.open_bp) if order.side == "buy" else max(limit, bar.open_bp)
            base = min(max(clamp_price(raw, view=view), low), high)
            return (base, "limit", None if crosses else "no_cross")
        quote = bar.yes_ask_bp if order.side == "buy" else bar.yes_bid_bp
        if quote is not None:
            return (min(max(clamp_price(quote, view=view), low), high), "quote", None)
        spread = schedule.min_half_spread_ticks
        if previous is not None:
            spread = half_spread_ticks(previous, bar, schedule=schedule)
        raw = bar.open_bp + spread if order.side == "buy" else bar.open_bp - spread
        return (min(max(clamp_price(raw, view=view), low), high), "open", None)


def make_liquidity(config: RunConfig, *, params: Mapping[str, object] | None = None) -> LiquidityModel:
    """Build the model ``config.liquidity`` names (16.1, ruling R139).

    Every caller builds its own and hands it to ``run_backtest``: the runner never builds one, so a
    journal can never claim a liquidity it did not run under.

    Raises:
        InvalidConfigError: On a name outside :data:`LIQUIDITY_MODELS`, on a model this wave does not
            ship (``calibrated_impact`` is R1c's in wave 7, ``adversarial_mm`` R4a's in wave 10), or on
            parameters handed to ``historical``, which has none.
    """
    name = _config_liquidity(config)
    if name not in LIQUIDITY_MODELS:
        raise InvalidConfigError("liquidity is not one of LIQUIDITY_MODELS", liquidity=name)
    if name != "historical":
        raise InvalidConfigError("this liquidity model is not built yet in this wave", liquidity=name)
    if params:
        raise InvalidConfigError("the historical model has no parameters", liquidity=name)
    if _config_params_hash(config) != "":
        raise InvalidConfigError("historical carries no params_hash", liquidity=name)
    return HistoricalLiquidity(config)


def _config_liquidity(config: RunConfig) -> str:
    """``config.liquidity`` (8.1, ruling R112), the one name the model must answer to."""
    return config.liquidity


def _config_params_hash(config: RunConfig) -> str:
    """``config.liquidity_params_hash`` (8.1, ruling R112)."""
    return config.liquidity_params_hash


# --------------------------------------------------------------------------------------------------
# check_envelope: the function every implementation must pass
# --------------------------------------------------------------------------------------------------
def _fill_key(fill: Fill) -> tuple[int, int, int, int, int, str, str, str, int]:
    """A total order over fills, so a multiset comparison needs no hashing of a dataclass."""
    return (
        fill.price_bp,
        fill.base_price_bp,
        fill.slippage_bp,
        fill.filled_milli,
        fill.unfilled_milli,
        fill.unfilled_reason,
        fill.price_source,
        fill.role,
        fill.fee_cents,
    )


def _order_key(order: LiquidityOrder) -> tuple[str, str, int, int, int]:
    """A total order over orders, used to find the orders a batch carries more than once."""
    return (order.side, order.kind, order.size_milli, order.limit_price_bp or 0, order.resting_since_ms or 0)


def _drivings(orders: Sequence[LiquidityOrder]) -> tuple[tuple[int, ...], ...]:
    """The index permutations :func:`check_envelope` drives, the identity first.

    Every permutation up to :data:`_MAX_PERMUTATION_ORDERS` orders; beyond it the rotations and the
    reverse, which is where an implementation that consumes a shared cap by arrival shows itself.
    """
    count = len(orders)
    identity = tuple(range(count))
    if count <= 1:
        return (identity,)
    if count <= _MAX_PERMUTATION_ORDERS:
        return tuple(permutations(identity))
    rotations = [tuple(identity[shift:] + identity[:shift]) for shift in range(count)]
    return (identity, *rotations[1:], tuple(reversed(identity)))


def check_envelope(
    model: LiquidityModel,
    *,
    market_view: LiquidityMarketView,
    bar: Bar,
    orders: Sequence[LiquidityOrder],
    config: RunConfig,
    schedule: FeeSchedule,
) -> tuple[str, ...]:
    """Drive a model over one batch and report which envelope rules it broke (16.1).

    The batch is priced twice in the given order (``not_deterministic``) and once per permutation
    (``order_dependent``, on the multiset of fills and on the fill each individually distinguishable
    order receives). Rules 1, 3 and 5 are checked per fill, rule 2 on the batch total, and the
    arithmetic of :class:`Fill` on every answer.

    Rule 1 is checked on **taker** fills only, and that reading is deliberate: 8.6's limit rule prices a
    resting buy at ``min(L, bar.open_bp)``, which on a quoted bar is below the ask by construction, so
    applying "a buy quotes at or above the ask" to a maker fill would fail every implementation for
    obeying the other half of the contract. It is reported as a contract issue against 16.1 rule 1.

    Returns:
        The breaches observed, in :data:`ENVELOPE_BREACHES` order, empty when the model is inside the
        envelope.
    """
    batch = tuple(orders)
    observed: list[str] = []

    def note(breach: str) -> None:
        if breach not in observed:
            observed.append(breach)

    first = tuple(model.quote_bar(market_view, bar, batch, schedule=schedule, now_ms=bar.t_ms))
    second = tuple(model.quote_bar(market_view, bar, batch, schedule=schedule, now_ms=bar.t_ms))
    if first != second:
        note("not_deterministic")
    if len(first) != len(batch):
        note("size_not_conserved")
        return tuple(name for name in ENVELOPE_BREACHES if name in observed)

    low, high = envelope_bounds(bar, kind=market_view.kind)
    cap = cap_milli(bar, config=config, source=market_view.source)
    for order, fill in zip(batch, first, strict=True):
        if fill.filled_milli < 0 or fill.unfilled_milli < 0:
            note("negative_fill")
        if fill.filled_milli + fill.unfilled_milli != order.size_milli:
            note("size_not_conserved")
        unknown_reason = fill.unfilled_reason not in UNFILLED_REASONS
        empty_reason = fill.unfilled_reason == "none" and fill.unfilled_milli != 0
        if unknown_reason or empty_reason:
            note("bad_reason")
        wrong_role = fill.role != _role_of(order)
        expected_fee = _fee_of(
            price=fill.price_bp,
            filled_milli=max(0, fill.filled_milli),
            order=order,
            schedule=schedule,
            view=market_view,
        )
        if wrong_role or fill.fee_cents != expected_fee:
            note("bad_fee")
        if fill.filled_milli <= 0:
            continue
        if not low <= fill.price_bp <= high or fill.price_bp != clamp_price(fill.price_bp, view=market_view):
            note("outside_range")
        if order.kind == "market":
            ask = bar.yes_ask_bp
            bid = bar.yes_bid_bp
            if order.side == "buy":
                floor_price = min(max(ask, low), high) if ask is not None else min(bar.open_bp + _floor_of(
                    bar, market_view, schedule), high)
                if fill.price_bp < floor_price:
                    note("quote_inside_spread")
            else:
                cap_price = min(max(bid, low), high) if bid is not None else max(bar.open_bp - _floor_of(
                    bar, market_view, schedule), low)
                if fill.price_bp > cap_price:
                    note("quote_inside_spread")
    if cap != CAP_UNLIMITED and sum(max(0, fill.filled_milli) for fill in first) > cap:
        note("over_cap")

    counts: dict[tuple[str, str, int, int, int], int] = {}
    for order in batch:
        key = _order_key(order)
        counts[key] = counts.get(key, 0) + 1
    baseline = sorted(_fill_key(fill) for fill in first)
    for indices in _drivings(batch)[1:]:
        permuted = tuple(batch[index] for index in indices)
        answer = tuple(model.quote_bar(market_view, bar, permuted, schedule=schedule, now_ms=bar.t_ms))
        if len(answer) != len(permuted) or sorted(_fill_key(fill) for fill in answer) != baseline:
            note("order_dependent")
            continue
        for position, index in enumerate(indices):
            if counts[_order_key(batch[index])] == 1 and answer[position] != first[index]:
                note("order_dependent")
    return tuple(name for name in ENVELOPE_BREACHES if name in observed)


def _floor_of(bar: Bar, view: LiquidityMarketView, schedule: FeeSchedule) -> int:
    """The half-spread floor rule 1 imposes on a bar with no quote, as the checker can see it.

    The checker holds one bar, so it cannot recompute a two-bar Corwin and Schultz estimate; the
    schedule's ``min_half_spread_ticks`` is the part of the floor every implementation owes on any bar,
    and an implementation that quotes **wider** than the estimate is inside the envelope anyway (17.4:
    the estimate is the floor, not the ceiling).
    """
    del bar, view
    return schedule.min_half_spread_ticks
