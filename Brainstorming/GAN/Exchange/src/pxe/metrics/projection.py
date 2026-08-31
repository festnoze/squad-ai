"""The one and only journal reader for metrics (CONTRACTS section 7.17, A15).

:func:`project` folds a journal into a :class:`MatchProjection`, and every other
metric module (calibration, behavioral, aggregate, integrity, the store and the
API) consumes that projection and never the raw events. The row types below are
therefore load bearing: A16, A17, A18, A21, A22 and A25 all code against these
exact field names.

Three rules shape this module, and each of them is a contract clause rather than
a preference:

* **Journal only.** The single exception is the ``incidents`` argument, because
  integrity incidents are deliberately not journalled (section 4.5), so
  ``Highlight.kind == "integrity_alert"`` has no other source. It defaults to
  ``()``, which keeps ``project(events)`` a pure function of the journal and
  makes it impossible for a detector version bump to move a metric.
* **Every per tick series has length ``ticks_total``** (section 9), so a
  resolution never shortens an array and no consumer aligns indices. Equity and
  cash come from ``PositionSnapshot``, which P4 emits for every account on every
  tick; ``ref_price`` comes from ``MarkToMarket``, which P4 emits for **open**
  markets only, so a resolved market's series is padded forward with its last
  observed reference price. A15 owns that padding and nobody re-derives it.
* **Canonical order.** Rows are sorted exactly as their docstring states, and
  that order is part of the contract because bootstrap resampling in
  :mod:`pxe.metrics` and in :mod:`pxe.integrity` consumes them in order.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from pxe.errors import InvalidConfigError
from pxe.events import (
    AgentFrozen,
    Event,
    MarketResolved,
    MarkToMarket,
    MatchEnded,
    MatchStarted,
    MessagePosted,
    OrderCancelled,
    OrderPlaced,
    PositionSnapshot,
    PredictionRecorded,
    SettlementApplied,
    SignalDelivered,
    TradeExecuted,
)
from pxe.types import Incident, Outcome, sorted_ids

__all__ = [
    "TradeRecord",
    "OrderRecord",
    "PredictionRow",
    "SignalRecord",
    "MessageRecord",
    "Highlight",
    "MatchProjection",
    "project",
]

#: A trade is a highlight when its notional is strictly above this multiple of
#: the match median trade notional (section 7.17, ``Highlight.kind`` docstring).
_BIG_TRADE_MEDIAN_MULTIPLIER = 3

#: The four ``Highlight.kind`` values. Private: the contract publishes the
#: strings, not a constant, and A22 mirrors them in its TypeScript union.
_KIND_BIG_TRADE = "big_trade"
_KIND_EARLY_RESOLUTION = "early_resolution"
_KIND_INTEGRITY_ALERT = "integrity_alert"
_KIND_BANKRUPTCY = "bankruptcy"

#: ``SettlementApplied.mode`` of a normal maturity, as opposed to an unwind.
_MODE_RESOLUTION = "resolution"


# --------------------------------------------------------------------------
# The five row types plus the highlight
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class TradeRecord:
    """One TradeExecuted. Sorted by (tick, trade_id)."""

    trade_id: str
    tick: int
    market_id: str
    price: int
    qty: int
    maker_order_id: str
    maker_agent_id: str
    maker_side: str  # "buy" | "sell"
    taker_order_id: str
    taker_agent_id: str
    taker_side: str
    taker_fee_cents: int
    maker_cash_delta_cents: int
    taker_cash_delta_cents: int


@dataclass(frozen=True)
class OrderRecord:
    """One order's whole life, folded from OrderPlaced + OrderCancelled + TradeExecuted.

    Sorted by (placed_tick, order_id). An order still resting at the end of the
    match has ``cancelled_tick`` None and ``cancel_reason`` None.
    """

    order_id: str
    agent_id: str
    market_id: str
    side: str  # "buy" | "sell"
    requested_type: str  # "limit" | "market"
    price: int  # the banded limit price for a market order
    qty: int  # originally submitted quantity
    placed_tick: int
    filled_qty: int
    cancelled_tick: int | None
    cancel_reason: str | None  # a CancelReason value
    reserved_cents: int
    released_cents: int


@dataclass(frozen=True)
class PredictionRow:
    """One PredictionRecorded. Sorted by (tick, agent_id, market_id).

    Named PredictionRow and not PredictionRecord on purpose: the event is
    PredictionRecorded and there is no ``types.Prediction``, so one concept keeps
    exactly two names, the event and the row.
    """

    agent_id: str
    market_id: str
    tick: int
    p_yes_ppm: int
    carried: bool


@dataclass(frozen=True)
class SignalRecord:
    """One SignalDelivered. Sorted by (tick, agent_id, signal_id)."""

    signal_id: str
    tick: int
    agent_id: str
    market_id: str
    kind: str  # a SignalKind value
    value_milli: int
    precision_ppm: int


@dataclass(frozen=True)
class MessageRecord:
    """One MessagePosted. Sorted by (tick, agent_id)."""

    agent_id: str
    tick: int
    text: str
    deliver_tick: int


@dataclass(frozen=True)
class Highlight:
    """One annotated marking event of the match (PRD section 9).

    Sorted by (tick, kind, market_id). This is the whole data contract behind the
    UI's "evenements marquants annotes" and behind AC-P7 ("a newcomer identifies
    the winner and a reason in under 30 s"): without it A24 has to re-derive
    interestingness from raw events in the browser.

    ``kind`` is one of ``"big_trade"`` (notional above 3x the match median),
    ``"early_resolution"`` (a market resolving before ``ticks_total``),
    ``"integrity_alert"`` (one incident from ``incidents.jsonl``) or
    ``"bankruptcy"``.

    ``label`` is the one sentence a spectator reads. It is built here and not in
    the browser, because AC-P7 is exactly the claim that a reason is available
    without a chart, and section 7.21 serves this field verbatim as
    ``Highlight.label``.
    """

    tick: int
    kind: str
    agent_ids: tuple[str, ...]  # sorted, may be empty
    market_id: str | None
    magnitude_cents: int
    label: str


# --------------------------------------------------------------------------
# The projection
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class MatchProjection:
    """Everything every metric module needs, folded from one journal.

    Attributes:
        match_id: Match the journal belongs to.
        seed: Root seed, from ``MatchStarted``.
        ticks_total: Played horizon. Every per tick series has this length.
        agent_ids: The **ranked** seats, ascending (section 2.3). ``MM`` and
            ``FEES`` are not seats and are not here; the market maker appears in
            ``mm_pnl_cents`` and in the trade rows instead.
        market_ids: Every market of the scenario, ascending.
        outcomes: One pair per **resolved** market, ascending. A cancelled
            market has no outcome and is therefore absent, which is what tells a
            consumer to treat its trades as unwound (FR-5.4.5).
        resolution_ticks: The scheduled resolution tick of **every** market,
            ascending, from ``MatchStarted.markets``. A cancelled market keeps
            its scheduled tick here, so ``sum over markets of resolution_tick``
            is well defined for A16.
        equity_cents: Per ranked agent, per tick, from ``PositionSnapshot``.
        cash_cents: Per ranked agent, per tick, from ``PositionSnapshot``.
        ref_price: Per market, per tick, from ``MarkToMarket``, padded forward
            past a resolution with the last observed reference price and padded
            backwards, before the first observation, with the market prior.
        trades: Every execution, ascending by (tick, trade_id).
        orders: Every order's whole life, ascending by (placed_tick, order_id).
        predictions: Every ``PredictionRecorded``, ascending.
        signals: Every ``SignalDelivered``, ascending.
        messages: Every ``MessagePosted``, ascending.
        highlights: The annotated marking events, ascending.
        mm_pnl_cents: Market maker PnL, the FR-5.8.5 cost of liquidity.
        fees_collected_cents: Final balance of the ``FEES`` vault.
        initial_cash_cents: Starting cash of one ranked seat.
    """

    match_id: str
    seed: int
    ticks_total: int
    agent_ids: tuple[str, ...]
    market_ids: tuple[str, ...]
    outcomes: tuple[tuple[str, Outcome], ...]
    resolution_ticks: tuple[tuple[str, int], ...]
    equity_cents: tuple[tuple[str, tuple[int, ...]], ...]  # per agent, per tick
    cash_cents: tuple[tuple[str, tuple[int, ...]], ...]
    ref_price: tuple[tuple[str, tuple[int, ...]], ...]  # per market, per tick
    trades: tuple[TradeRecord, ...]
    orders: tuple[OrderRecord, ...]
    predictions: tuple[PredictionRow, ...]
    signals: tuple[SignalRecord, ...]
    messages: tuple[MessageRecord, ...]
    highlights: tuple[Highlight, ...]
    mm_pnl_cents: int
    fees_collected_cents: int
    initial_cash_cents: int

    def agent_index(self, agent_id: str) -> int:
        """Return the position of one ranked seat inside :attr:`agent_ids`.

        Args:
            agent_id: A ranked seat id.

        Returns:
            The 0 based index, which is the row index of every per agent series.

        Raises:
            InvalidConfigError: If ``agent_id`` is not a ranked seat of this
                match. A silent ``-1`` would index the last agent's series.
        """
        try:
            return self.agent_ids.index(agent_id)
        except ValueError as exc:
            raise InvalidConfigError(
                "not a ranked seat of this match",
                match_id=self.match_id,
                agent_id=agent_id,
            ) from exc

    def equity_series(self, agent_id: str) -> tuple[int, ...]:
        """Return the per tick equity of one ranked seat, in cents.

        Args:
            agent_id: A ranked seat id.

        Returns:
            A tuple of length :attr:`ticks_total`, index 0 being tick 1.

        Raises:
            InvalidConfigError: If ``agent_id`` is not a ranked seat.
        """
        return self.equity_cents[self.agent_index(agent_id)][1]

    def cash_series(self, agent_id: str) -> tuple[int, ...]:
        """Return the per tick cash of one ranked seat, in cents.

        The sibling of :meth:`equity_series`, kept because every consumer that
        reads one reads the other and neither should re-index by hand.

        Args:
            agent_id: A ranked seat id.

        Returns:
            A tuple of length :attr:`ticks_total`, index 0 being tick 1.

        Raises:
            InvalidConfigError: If ``agent_id`` is not a ranked seat.
        """
        return self.cash_cents[self.agent_index(agent_id)][1]

    def outcome_of(self, market_id: str) -> Outcome | None:
        """Return the realised outcome of one market, or ``None``.

        ``None`` means the market was cancelled (FR-5.4.5) or the journal stops
        before its resolution. Both cases carry the same consequence for a PnL
        projection, which is why they share one answer.

        Args:
            market_id: Market of this scenario.

        Returns:
            The outcome, or ``None`` when the market never resolved.
        """
        for candidate, outcome in self.outcomes:
            if candidate == market_id:
                return outcome
        return None


# --------------------------------------------------------------------------
# Mutable accumulators used while folding. Private.
# --------------------------------------------------------------------------
@dataclass
class _OrderFold:
    """One order under construction, folded from three event families."""

    order_id: str
    agent_id: str
    market_id: str
    side: str
    requested_type: str
    price: int
    qty: int
    placed_tick: int
    reserved_cents: int
    filled_qty: int = 0
    cancelled_tick: int | None = None
    cancel_reason: str | None = None
    released_cents: int = 0

    def freeze(self) -> OrderRecord:
        """Return the immutable row this fold describes."""
        return OrderRecord(
            order_id=self.order_id,
            agent_id=self.agent_id,
            market_id=self.market_id,
            side=self.side,
            requested_type=self.requested_type,
            price=self.price,
            qty=self.qty,
            placed_tick=self.placed_tick,
            filled_qty=self.filled_qty,
            cancelled_tick=self.cancelled_tick,
            cancel_reason=self.cancel_reason,
            reserved_cents=self.reserved_cents,
            released_cents=self.released_cents,
        )


@dataclass
class _Fold:
    """Everything one pass over the journal accumulates."""

    equity: dict[str, dict[int, int]] = field(default_factory=dict)
    cash: dict[str, dict[int, int]] = field(default_factory=dict)
    ref: dict[str, dict[int, int]] = field(default_factory=dict)
    trades: list[TradeRecord] = field(default_factory=list)
    orders: dict[str, _OrderFold] = field(default_factory=dict)
    predictions: list[PredictionRow] = field(default_factory=list)
    signals: list[SignalRecord] = field(default_factory=list)
    messages: list[MessageRecord] = field(default_factory=list)
    outcomes: dict[str, Outcome] = field(default_factory=dict)
    resolved_at: dict[str, int] = field(default_factory=dict)
    settled_in_cents: dict[str, int] = field(default_factory=dict)
    freezes: list[AgentFrozen] = field(default_factory=list)
    ended: MatchEnded | None = None


# --------------------------------------------------------------------------
# project
# --------------------------------------------------------------------------
def project(events: Sequence[Event], *, incidents: Sequence[Incident] = ()) -> MatchProjection:
    """Fold a journal into the one projection every metric module consumes.

    Every metric module consumes a :class:`MatchProjection`, never raw events,
    never engine state.

    ``incidents`` is the one thing the journal cannot supply: integrity
    incidents are deliberately not journalled (section 4.5, decision 10), and
    ``Highlight.kind == "integrity_alert"`` needs them. It defaults to ``()`` so
    ``project(events)`` stays a pure function of the journal and a detector
    version bump can never move a metric; callers that have the file pass it
    (``Store.load_projection`` passes ``self.load_incidents(match_id=...)``, and
    the API therefore gets alert highlights while ``test_metrics_decoupling.py``
    does not).

    Args:
        events: The journal, in any order: it is sorted by ``seq`` here, which is
            the only ordering section 2.3 recognises for events.
        incidents: Integrity incidents of the same match, from
            ``runs/<match_id>/incidents.jsonl``.

    Returns:
        The folded projection.

    Raises:
        InvalidConfigError: If the sequence holds no ``MatchStarted``. Without it
            there is no seed, no horizon and no seat list, so there is no
            projection to build and guessing one would silently produce empty
            series that satisfy every type annotation.
    """
    ordered = tuple(sorted(events, key=lambda event: event.seq))
    started = _match_started(ordered)
    ticks_total = started.ticks_total
    agent_ids = sorted_ids([str(row["agent_id"]) for row in started.agents if bool(row["ranked"])])
    market_ids = sorted_ids([str(row["market_id"]) for row in started.markets])
    priors = {str(row["market_id"]): int(row["prior_price"]) for row in started.markets}
    scheduled = {str(row["market_id"]): int(row["resolution_tick"]) for row in started.markets}

    fold = _collect(ordered, agent_ids=frozenset(agent_ids), ticks_total=ticks_total)
    agent_rank = {agent_id: index for index, agent_id in enumerate(agent_ids)}
    market_rank = {market_id: index for index, market_id in enumerate(market_ids)}

    mm_pnl_cents, fees_collected_cents = _closing_totals(fold)

    return MatchProjection(
        match_id=started.match_id,
        seed=started.seed,
        ticks_total=ticks_total,
        agent_ids=agent_ids,
        market_ids=market_ids,
        outcomes=tuple((market_id, fold.outcomes[market_id]) for market_id in market_ids if market_id in fold.outcomes),
        resolution_ticks=tuple((market_id, scheduled[market_id]) for market_id in market_ids),
        equity_cents=tuple(
            (agent_id, _series(fold.equity.get(agent_id, {}), ticks_total, started.initial_cash_cents))
            for agent_id in agent_ids
        ),
        cash_cents=tuple(
            (agent_id, _series(fold.cash.get(agent_id, {}), ticks_total, started.initial_cash_cents))
            for agent_id in agent_ids
        ),
        ref_price=tuple(
            (market_id, _series(fold.ref.get(market_id, {}), ticks_total, priors[market_id]))
            for market_id in market_ids
        ),
        trades=tuple(sorted(fold.trades, key=lambda row: (row.tick, row.trade_id))),
        orders=tuple(
            sorted((held.freeze() for held in fold.orders.values()), key=lambda row: (row.placed_tick, row.order_id))
        ),
        predictions=tuple(
            sorted(
                fold.predictions,
                key=lambda row: (row.tick, agent_rank.get(row.agent_id, len(agent_rank)), market_rank[row.market_id]),
            )
        ),
        signals=tuple(
            sorted(
                fold.signals,
                key=lambda row: (row.tick, agent_rank.get(row.agent_id, len(agent_rank)), row.signal_id),
            )
        ),
        messages=tuple(
            sorted(fold.messages, key=lambda row: (row.tick, agent_rank.get(row.agent_id, len(agent_rank))))
        ),
        highlights=_highlights(fold, incidents=incidents, ticks_total=ticks_total),
        mm_pnl_cents=mm_pnl_cents,
        fees_collected_cents=fees_collected_cents,
        initial_cash_cents=started.initial_cash_cents,
    )


def _match_started(ordered: Sequence[Event]) -> MatchStarted:
    """Return the ``MatchStarted`` of a journal.

    Args:
        ordered: The journal, ascending by ``seq``.

    Returns:
        The first ``MatchStarted``.

    Raises:
        InvalidConfigError: If there is none.
    """
    for event in ordered:
        if isinstance(event, MatchStarted):
            return event
    raise InvalidConfigError("a journal without MatchStarted cannot be projected (section 4.4)")


def _collect(ordered: Sequence[Event], *, agent_ids: frozenset[str], ticks_total: int) -> _Fold:
    """Walk the journal exactly once and accumulate every row family.

    A trade or a cancellation naming an order id that was never placed is
    ignored rather than fatal: ``replay_to_tick`` and a partially written journal
    legitimately start after an ``OrderPlaced``, and there is no field to invent
    for the missing order.

    Args:
        ordered: The journal, ascending by ``seq``.
        agent_ids: The ranked seats, so ``MM`` and ``FEES`` snapshots are skipped.
        ticks_total: Horizon, so finalisation events (tick ``ticks_total + 1``)
            never land in a per tick series.

    Returns:
        The accumulator.
    """
    fold = _Fold()
    for event in ordered:
        tick = event.tick
        in_horizon = 1 <= tick <= ticks_total
        if isinstance(event, PositionSnapshot):
            if in_horizon and event.account_id in agent_ids:
                fold.equity.setdefault(event.account_id, {})[tick] = event.equity_cents
                fold.cash.setdefault(event.account_id, {})[tick] = event.cash_cents
        elif isinstance(event, MarkToMarket):
            if in_horizon:
                fold.ref.setdefault(event.market_id, {})[tick] = event.ref_price
        elif isinstance(event, TradeExecuted):
            _fold_trade(fold, event)
        elif isinstance(event, OrderPlaced):
            fold.orders[event.order_id] = _OrderFold(
                order_id=event.order_id,
                agent_id=event.agent_id,
                market_id=event.market_id,
                side=event.side,
                requested_type=event.requested_type,
                price=event.price,
                qty=event.qty,
                placed_tick=tick,
                reserved_cents=event.reserved_cents,
            )
        elif isinstance(event, OrderCancelled):
            held = fold.orders.get(event.order_id)
            if held is not None:
                held.cancelled_tick = tick
                held.cancel_reason = event.reason
                held.released_cents += event.released_cents
        elif isinstance(event, PredictionRecorded):
            fold.predictions.append(
                PredictionRow(
                    agent_id=event.agent_id,
                    market_id=event.market_id,
                    tick=tick,
                    p_yes_ppm=event.p_yes_ppm,
                    carried=event.carried,
                )
            )
        elif isinstance(event, SignalDelivered):
            fold.signals.append(
                SignalRecord(
                    signal_id=event.signal_id,
                    tick=tick,
                    agent_id=event.agent_id,
                    market_id=event.market_id,
                    kind=event.kind,
                    value_milli=event.value_milli,
                    precision_ppm=event.precision_ppm,
                )
            )
        elif isinstance(event, MessagePosted):
            fold.messages.append(
                MessageRecord(agent_id=event.agent_id, tick=tick, text=event.text, deliver_tick=event.deliver_tick)
            )
        elif isinstance(event, MarketResolved):
            fold.outcomes[event.market_id] = Outcome(event.outcome)
            fold.resolved_at[event.market_id] = event.resolution_tick
        elif isinstance(event, SettlementApplied):
            if event.mode == _MODE_RESOLUTION and event.cash_delta_cents > 0:
                fold.settled_in_cents[event.market_id] = (
                    fold.settled_in_cents.get(event.market_id, 0) + event.cash_delta_cents
                )
        elif isinstance(event, AgentFrozen):
            fold.freezes.append(event)
        elif isinstance(event, MatchEnded):
            fold.ended = event
    return fold


def _fold_trade(fold: _Fold, event: TradeExecuted) -> None:
    """Record one execution and credit the filled quantity to both orders."""
    fold.trades.append(
        TradeRecord(
            trade_id=event.trade_id,
            tick=event.tick,
            market_id=event.market_id,
            price=event.price,
            qty=event.qty,
            maker_order_id=event.maker_order_id,
            maker_agent_id=event.maker_agent_id,
            maker_side=event.maker_side,
            taker_order_id=event.taker_order_id,
            taker_agent_id=event.taker_agent_id,
            taker_side=event.taker_side,
            taker_fee_cents=event.taker_fee_cents,
            maker_cash_delta_cents=event.maker_cash_delta_cents,
            taker_cash_delta_cents=event.taker_cash_delta_cents,
        )
    )
    for order_id in (event.maker_order_id, event.taker_order_id):
        held = fold.orders.get(order_id)
        if held is not None:
            held.filled_qty += event.qty


def _series(observed: Mapping[int, int], ticks_total: int, before: int) -> tuple[int, ...]:
    """Expand a sparse per tick mapping into a dense series of length ``ticks_total``.

    A tick with no observation carries the last observed value, which is exactly
    the section 9 rule for a resolved market's ``ref_price``; ticks before the
    first observation carry ``before``.

    Args:
        observed: Tick (1 based) to value.
        ticks_total: Length of the returned series.
        before: Value used until the first observation.

    Returns:
        A tuple of length ``ticks_total``, index 0 being tick 1.
    """
    out: list[int] = []
    last = before
    for tick in range(1, ticks_total + 1):
        last = observed.get(tick, last)
        out.append(last)
    return tuple(out)


def _closing_totals(fold: _Fold) -> tuple[int, int]:
    """Return ``(mm_pnl_cents, fees_collected_cents)`` as ``MatchEnded`` reported them.

    Both numbers are journalled, once, by the runner at finalisation step 19, and
    the journal is the law (section 4.1): re-deriving them here would put a
    second formula next to the one in :mod:`pxe.metrics.performance` and section
    9 is explicit that two spellings of one number are one too many. A journal
    that stops before ``MatchEnded`` (a live replay, ``replay_to_tick``) has not
    reported them yet and therefore carries ``0`` for both; the cost of
    liquidity of a finished match is cross checked against
    ``pnl_of(projection, "MM")`` by
    ``test_metrics_performance.py::test_mm_pnl_is_reported_and_excluded``.

    Args:
        fold: The accumulator.

    Returns:
        The market maker PnL and the fee vault balance, both in cents.
    """
    if fold.ended is None:
        return (0, 0)
    return (fold.ended.mm_pnl_cents, fold.ended.fees_collected_cents)


# --------------------------------------------------------------------------
# Highlights
# --------------------------------------------------------------------------
def _highlights(fold: _Fold, *, incidents: Sequence[Incident], ticks_total: int) -> tuple[Highlight, ...]:
    """Build the annotated marking events of the match (PRD section 9).

    Args:
        fold: The accumulator.
        incidents: Integrity incidents, the only non journal input.
        ticks_total: Horizon, which is what makes a resolution "early".

    Returns:
        The highlights, sorted by (tick, kind, market_id). A ``market_id`` of
        ``None`` sorts before any market id, and equal keys keep journal order
        because :func:`sorted` is stable.
    """
    rows: list[Highlight] = []
    rows.extend(_big_trade_highlights(fold))
    rows.extend(_early_resolution_highlights(fold, ticks_total=ticks_total))
    rows.extend(_incident_highlights(incidents))
    rows.extend(_bankruptcy_highlights(fold))
    return tuple(sorted(rows, key=lambda row: (row.tick, row.kind, row.market_id or "")))


def _big_trade_highlights(fold: _Fold) -> list[Highlight]:
    """Flag every trade whose notional is above three times the match median.

    The median is integral (the lower of the two middle values on an even count)
    so the threshold is exactly reproducible and no float reaches a comparison
    that decides what a spectator sees.

    Args:
        fold: The accumulator.

    Returns:
        One highlight per outsized trade, in journal order.
    """
    if not fold.trades:
        return []
    notionals = sorted(row.price * row.qty for row in fold.trades)
    median = notionals[(len(notionals) - 1) // 2]
    threshold = _BIG_TRADE_MEDIAN_MULTIPLIER * median
    rows: list[Highlight] = []
    for row in sorted(fold.trades, key=lambda trade: (trade.tick, trade.trade_id)):
        notional = row.price * row.qty
        if notional <= threshold:
            continue
        parties = tuple(sorted({row.maker_agent_id, row.taker_agent_id}))
        rows.append(
            Highlight(
                tick=row.tick,
                kind=_KIND_BIG_TRADE,
                agent_ids=parties,
                market_id=row.market_id,
                magnitude_cents=notional,
                label=(
                    f"Big trade on {row.market_id}: {row.taker_agent_id} took {row.qty} contracts "
                    f"at {row.price} cents from {row.maker_agent_id}, {notional} cents of notional."
                ),
            )
        )
    return rows


def _early_resolution_highlights(fold: _Fold, *, ticks_total: int) -> list[Highlight]:
    """Flag every market that resolved before the end of the match.

    Args:
        fold: The accumulator.
        ticks_total: Horizon.

    Returns:
        One highlight per early resolution, ascending by market id.
    """
    rows: list[Highlight] = []
    for market_id in sorted_ids(sorted(fold.resolved_at)):
        scheduled = fold.resolved_at[market_id]
        if scheduled >= ticks_total:
            continue
        outcome = fold.outcomes[market_id]
        remaining = ticks_total - scheduled
        rows.append(
            Highlight(
                tick=scheduled + 1,
                kind=_KIND_EARLY_RESOLUTION,
                agent_ids=(),
                market_id=market_id,
                magnitude_cents=fold.settled_in_cents.get(market_id, 0),
                label=(
                    f"{market_id} resolved {str(outcome).upper()} at tick {scheduled}, "
                    f"{remaining} ticks before the end of the match."
                ),
            )
        )
    return rows


def _incident_highlights(incidents: Sequence[Incident]) -> list[Highlight]:
    """Turn each integrity incident into one highlight.

    Args:
        incidents: Detector output for this match.

    Returns:
        One highlight per incident, ascending by (tick, incident_id).
    """
    rows: list[Highlight] = []
    for incident in sorted(incidents, key=lambda item: (item.tick, item.incident_id)):
        agents = tuple(sorted_ids(incident.agent_ids)) if incident.agent_ids else ()
        market_id = incident.market_ids[0] if len(incident.market_ids) == 1 else None
        who = ", ".join(agents) if agents else "no named agent"
        rows.append(
            Highlight(
                tick=incident.tick,
                kind=_KIND_INTEGRITY_ALERT,
                agent_ids=agents,
                market_id=market_id,
                magnitude_cents=0,
                label=(
                    f"Integrity alert {incident.incident_id}: {incident.kind} "
                    f"({incident.severity}) involving {who}, score {incident.score_ppm} ppm."
                ),
            )
        )
    return rows


def _bankruptcy_highlights(fold: _Fold) -> list[Highlight]:
    """Turn each ``AgentFrozen`` into one highlight.

    Args:
        fold: The accumulator.

    Returns:
        One highlight per freeze, in journal order.
    """
    return [
        Highlight(
            tick=event.tick,
            kind=_KIND_BANKRUPTCY,
            agent_ids=(event.agent_id,),
            market_id=None,
            magnitude_cents=event.equity_cents,
            label=(
                f"{event.agent_id} went bankrupt at tick {event.tick} with {event.equity_cents} cents of equity "
                f"and {len(event.cancelled_order_ids)} resting orders cancelled."
            ),
        )
        for event in fold.freezes
    ]
