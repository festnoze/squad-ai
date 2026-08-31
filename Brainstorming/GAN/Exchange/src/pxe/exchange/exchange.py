"""The CLOB facade (CONTRACTS section 7.8): the one emitter of order events.

:class:`Exchange` is the only module that emits ``order_placed``,
``order_rejected``, ``order_cancelled``, ``trade_executed`` and
``stp_cancelled`` (CONTRACTS section 4.5), and the only one that owns the per
match order and trade counters. Everything it decides is derived from three
collaborators it is given and never builds: the :class:`~pxe.types.MatchConfig`
(fees, caps, protection band), the :class:`~pxe.types.ScenarioSpec` (the
markets and their public priors) and the
:class:`~pxe.exchange.accounts.AccountBook` (cash and collateral).

The normative order inside one accepted submission (P3 step 11) is:

1. ``OrderPlaced``;
2. per own resting order the walk crossed, in ``priority_key`` order, one
   ``OrderCancelled(reason=STP)`` immediately followed by one ``STPCancelled``
   carrying that event's ``seq``. The money is on the ``OrderCancelled`` and
   nowhere else (decision 20);
3. one ``TradeExecuted`` per fill, in fill order;
4. for an ``IOC`` residual, one ``OrderCancelled(reason=IOC_RESIDUAL)``.

Two orderings are load bearing and were each written down because the other
reading is equally natural and produces a different journal from the same seed:

* the FR-5.5.1 solvency check runs **before** any STP cancellation, so
  collateral freed by an STP is never available to the order that caused it
  (CONTRACTS section 6.1, decision 21);
* collateral is released **per fill** before the trade is applied to the
  ledger, so free cash never dips below zero between the two halves of an
  execution (invariant I4).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from pxe.errors import InvalidConfigError, InvalidOrderError, InvariantViolationError
from pxe.events import OrderCancelled, OrderPlaced, OrderRejected, STPCancelled, TradeExecuted
from pxe.exchange.accounts import AccountBook
from pxe.exchange.book import OrderBook
from pxe.exchange.fees import reserve_fee_for, taker_fee_for
from pxe.exchange.matching import Fill, band_limit_price, plan_match, reference_price
from pxe.journal import Journal
from pxe.types import (
    MAX_ORDER_QTY,
    PRICE_MAX,
    PRICE_MIN,
    BookSnapshot,
    CancelReason,
    MarketSpec,
    MarketState,
    MarketStatus,
    MatchConfig,
    Order,
    OrderIntent,
    OrderStatus,
    OrderType,
    RejectReason,
    ScenarioSpec,
    Side,
    TimeInForce,
    Trade,
    make_order_id,
    make_trade_id,
    order_collateral_cents,
    sorted_ids,
)

__all__ = [
    "OrderResult",
    "Exchange",
]

#: Hard cap on ``OrderRejected.detail`` and ``OrderCancelled`` free text
#: (CONTRACTS section 4.5: at most 200 characters).
_DETAIL_MAX_CHARS = 200


@dataclass(frozen=True)
class OrderResult:
    """What one call to :meth:`Exchange.submit` or :meth:`Exchange.cancel` did.

    Attributes:
        accepted: True when the intent was acted on. False means one
            ``OrderRejected`` was emitted and nothing else changed.
        order_id: The assigned (or cancelled) order id, ``None`` when the
            intent was refused before an id was minted.
        filled_qty: Contracts executed by this submission, ``0`` for a cancel.
        resting_qty: Contracts left resting in the book afterwards. Always
            ``0`` for an ``IOC`` (FR-5.4.3: the residual never rests) and for a
            cancel.
        reason: The :class:`~pxe.types.RejectReason` when ``accepted`` is
            False, ``None`` otherwise.
        trades: The executions, in fill order.
    """

    accepted: bool
    order_id: str | None
    filled_qty: int
    resting_qty: int
    reason: RejectReason | None
    trades: tuple[Trade, ...]


@dataclass(frozen=True)
class _Accepted:
    """The resolved parameters of an intent that passed every check."""

    market_id: str
    side: Side
    order_type: OrderType
    price: int
    qty: int
    tif: TimeInForce
    ref_price: int | None


class Exchange:
    """CLOB facade. Owns order and trade counters, emits every order/trade event."""

    def __init__(
        self,
        *,
        config: MatchConfig,
        scenario: ScenarioSpec,
        accounts: AccountBook,
        journal: Journal,
    ) -> None:
        """Open one book per market of the scenario, all ``OPEN`` and empty.

        Args:
            config: The match configuration. Read for ``taker_fee_bps``,
                ``max_active_orders_per_market``, ``market_band_cents`` and
                ``ref_history_len``.
            scenario: The generated world. Supplies the market ids and, through
                ``MarketSpec.prior_price``, the last branch of the FR-5.4.6
                reference price chain.
            accounts: The ledger. The exchange reserves, releases and applies
                through it and never mutates cash itself.
            journal: The append only log this exchange emits into.

        Raises:
            InvalidConfigError: If ``config.n_markets`` disagrees with the
                number of markets in the scenario. The runner checks the same
                thing (CONTRACTS section 2.6); checking it here too means an
                exchange built directly by a test cannot silently hold a
                different market count than the config its caps come from.
        """
        if config.n_markets != len(scenario.markets):
            raise InvalidConfigError(
                "config and scenario disagree on the market count",
                n_markets=config.n_markets,
                scenario_markets=len(scenario.markets),
            )
        self._config = config
        self._scenario = scenario
        self._accounts = accounts
        self._journal = journal
        self._specs: dict[str, MarketSpec] = {spec.market_id: spec for spec in scenario.markets}
        self._market_ids: tuple[str, ...] = sorted_ids(tuple(self._specs.keys()))
        self._books: dict[str, OrderBook] = {mid: OrderBook(mid) for mid in self._market_ids}
        self._status: dict[str, MarketStatus] = dict.fromkeys(self._market_ids, MarketStatus.OPEN)
        self._closed_tick: dict[str, int | None] = dict.fromkeys(self._market_ids, None)
        self._tick_volume: dict[str, int] = dict.fromkeys(self._market_ids, 0)
        self._ref_history: dict[str, tuple[int, ...]] = dict.fromkeys(self._market_ids, ())
        self._order_seq = 0
        self._trade_seq = 0

    # ------------------------------------------------------------------
    # Read only views
    # ------------------------------------------------------------------
    def open_market_ids(self) -> tuple[str, ...]:
        """Markets still tradable, ascending.

        Returns:
            The ids whose status is ``OPEN``, in canonical market order.
        """
        return tuple(mid for mid in self._market_ids if self._status[mid] is MarketStatus.OPEN)

    def status(self, market_id: str) -> MarketStatus:
        """Lifecycle state of one market (FR-5.4.5).

        Args:
            market_id: Market to read.

        Returns:
            The :class:`~pxe.types.MarketStatus`.

        Raises:
            InvalidConfigError: If the market is not part of the scenario.
        """
        self._require_market(market_id)
        return self._status[market_id]

    def book(self, market_id: str) -> OrderBook:
        """The live book of one market.

        Args:
            market_id: Market to read.

        Returns:
            The :class:`~pxe.exchange.book.OrderBook`. It is the live object,
            not a copy: read it, never mutate it from outside.

        Raises:
            InvalidConfigError: If the market is not part of the scenario.
        """
        self._require_market(market_id)
        return self._books[market_id]

    def reference_price(self, market_id: str) -> tuple[int, str]:
        """The FR-5.4.6 reference price of one market and its source branch.

        Args:
            market_id: Market to read.

        Returns:
            ``(price, source)`` with ``source`` in ``{"mid", "last", "prior"}``.
            Always defined, which is the AC-P9 half this module owns.

        Raises:
            InvalidConfigError: If the market is not part of the scenario.
        """
        self._require_market(market_id)
        return reference_price(self._books[market_id], self._specs[market_id].prior_price)

    def market_state(self, market_id: str) -> MarketState:
        """Full public state of one market.

        ``outcome`` is always ``None`` here: the exchange closes a market on the
        oracle's instruction (:meth:`close_market`) and is deliberately never
        told which way it resolved, so no second, disagreeing view of an
        outcome can exist. ``MatchState.outcomes`` is where the outcome lives.

        Args:
            market_id: Market to read.

        Returns:
            The :class:`~pxe.types.MarketState`.

        Raises:
            InvalidConfigError: If the market is not part of the scenario.
        """
        self._require_market(market_id)
        return MarketState(
            spec=self._specs[market_id],
            status=self._status[market_id],
            book=self.snapshot(market_id),
            outcome=None,
            resolved_tick=self._closed_tick[market_id],
            ref_history=self._ref_history[market_id],
        )

    def snapshot(self, market_id: str) -> BookSnapshot:
        """Immutable public view of one book, at the current reference price.

        Args:
            market_id: Market to read.

        Returns:
            The :class:`~pxe.types.BookSnapshot`.

        Raises:
            InvalidConfigError: If the market is not part of the scenario.
        """
        ref_price, _source = self.reference_price(market_id)
        return self._books[market_id].snapshot(ref_price)

    def book_view(self) -> Mapping[str, tuple[Order, ...]]:
        """Every resting order, keyed by ``market_id``, in ``priority_key`` order.

        This is the argument P4 step 15 hands to
        ``AccountBook.check_invariants``, which is how I3 and I8 become
        checkable. Every market of the scenario is a key, including the ones
        holding nothing and the ones already closed, so a consumer never has to
        guess whether an absent key means "no orders" or "unknown market".

        Returns:
            A mapping built in canonical market order.
        """
        return {mid: self._books[mid].resting_orders() for mid in self._market_ids}

    def tick_volume(self, market_id: str) -> int:
        """Contracts traded on one market since the last :meth:`begin_tick`.

        Args:
            market_id: Market to read.

        Returns:
            The quantity, ``0`` at the start of every tick.

        Raises:
            InvalidConfigError: If the market is not part of the scenario.
        """
        self._require_market(market_id)
        return self._tick_volume[market_id]

    def ref_history(self, market_id: str) -> tuple[int, ...]:
        """The recent reference prices of one market, oldest first.

        Args:
            market_id: Market to read.

        Returns:
            At most ``config.ref_history_len`` prices.

        Raises:
            InvalidConfigError: If the market is not part of the scenario.
        """
        self._require_market(market_id)
        return self._ref_history[market_id]

    # ------------------------------------------------------------------
    # Tick bookkeeping
    # ------------------------------------------------------------------
    def begin_tick(self, tick: int) -> None:
        """Reset the per tick counters (P1 step 0).

        This is the only thing that resets :meth:`tick_volume`, which P4 step
        12 puts into ``MarkToMarket.tick_volume_qty``. It emits nothing and it
        is the first call of every tick, before ``TickStarted``.

        Args:
            tick: The tick that is starting, ``>= 1``.

        Raises:
            InvalidConfigError: If ``tick`` is below one.
        """
        if tick < 1:
            raise InvalidConfigError("a real tick is >= 1", tick=tick)
        for market_id in self._market_ids:
            self._tick_volume[market_id] = 0

    def push_ref_history(self, market_id: str, ref_price: int) -> None:
        """Append one reference price to a market's bounded history (P4 step 12).

        Args:
            market_id: Market to update.
            ref_price: Reference price in cents, ``1..99``.

        Raises:
            InvalidConfigError: If the market is not part of the scenario.
            InvalidOrderError: If the price is outside the tradable band.
        """
        self._require_market(market_id)
        if not PRICE_MIN <= ref_price <= PRICE_MAX:
            raise InvalidOrderError("reference price out of range", market_id=market_id, ref_price=ref_price)
        limit = self._config.ref_history_len
        if limit == 0:
            # A slice of [-0:] is the whole tuple, which would make a zero
            # length history unbounded. Handle it explicitly.
            self._ref_history[market_id] = ()
            return
        self._ref_history[market_id] = (*self._ref_history[market_id], ref_price)[-limit:]

    # ------------------------------------------------------------------
    # Order lifecycle
    # ------------------------------------------------------------------
    def submit(self, *, tick: int, agent_id: str, intent: OrderIntent, item_index: int) -> OrderResult:
        """Accept or refuse one ``place`` intent, then match it (FR-5.4.1 to FR-5.4.4).

        Args:
            tick: Current tick.
            agent_id: Submitting account, an agent or ``MM``. A market maker
                quote goes through here like anybody else, so the section 6.1
                collateral check applies to it too (P3 step 9).
            intent: The validated intent. ``op`` must be ``"place"``.
            item_index: Position of the intent inside the agent's ``orders``
                array, carried by ``OrderRejected`` so a rejection can be
                joined back to what the agent asked for.

        Returns:
            The :class:`OrderResult`.

        Raises:
            InvalidOrderError: If ``intent.op`` is not ``"place"``. Dispatching
                on ``op`` is P3 step 11's job, so a cancel arriving here is an
                engine bug and never an agent behaviour.
        """
        if intent.op != "place":
            raise InvalidOrderError("submit takes a place intent", op=intent.op, agent_id=agent_id)
        checked = self._check_place(tick=tick, agent_id=agent_id, intent=intent, item_index=item_index)
        if isinstance(checked, OrderResult):
            return checked

        self._order_seq += 1
        order = Order(
            order_id=make_order_id(self._order_seq),
            agent_id=agent_id,
            market_id=checked.market_id,
            side=checked.side,
            order_type=checked.order_type,
            price=checked.price,
            qty=checked.qty,
            remaining_qty=checked.qty,
            status=OrderStatus.NEW,
            tif=checked.tif,
            created_tick=tick,
            seq=self._order_seq,
        )
        book = self._books[checked.market_id]
        reserved_cents = self._accounts.reserve_order(account_id=agent_id, order=order)
        self._journal.emit(
            OrderPlaced,
            tick=tick,
            order_id=order.order_id,
            agent_id=agent_id,
            market_id=order.market_id,
            side=str(order.side),
            requested_type=str(checked.order_type),
            price=order.price,
            qty=order.qty,
            tif=str(order.tif),
            reserved_cents=reserved_cents,
            ref_price=checked.ref_price,
            # Counted at acceptance, this order included, and therefore before
            # the STP cancellations of step 2 can lower it again. That is what
            # makes the field an audit of the FR-5.4.2 cap: it is always
            # <= config.max_active_orders_per_market.
            active_orders_after=book.count_of(agent_id) + 1,
        )

        plan = plan_match(
            book,
            agent_id=agent_id,
            side=order.side,
            limit_price=order.price,
            qty=order.qty,
            fee_bps=self._config.taker_fee_bps,
        )
        self._apply_stp(tick=tick, order=order, stp_order_ids=plan.stp_order_ids, book=book)
        trades = self._apply_fills(tick=tick, order=order, plan_fills=plan.fills, book=book)
        resting_qty = self._settle_residual(tick=tick, order=order, residual_qty=plan.residual_qty, book=book)
        return OrderResult(
            accepted=True,
            order_id=order.order_id,
            filled_qty=order.qty - plan.residual_qty,
            resting_qty=resting_qty,
            reason=None,
            trades=trades,
        )

    def cancel(
        self,
        *,
        tick: int,
        agent_id: str,
        order_id: str,
        reason: CancelReason,
        item_index: int = -1,
    ) -> OrderResult:
        """Take one resting order out of the book and release its collateral.

        A cancel of an order that legitimately went away between P2 and P3
        (filled, STP cancelled, or removed by a resolution) is refused here
        with ``UNKNOWN_ORDER`` and never in P2: P3 liveness is authoritative
        (CONTRACTS section 7.14).

        Args:
            tick: Current tick.
            agent_id: The account asking. It must own the order.
            order_id: Order to cancel.
            reason: Why the order is leaving the book, carried by
                ``OrderCancelled``.
            item_index: Position of the intent inside the agent's ``orders``
                array, ``-1`` when the call does not come from an agent action.

        Returns:
            The :class:`OrderResult`.
        """
        located = self._locate(order_id)
        if located is None:
            return self._reject_cancel(
                tick=tick,
                agent_id=agent_id,
                order_id=order_id,
                order=None,
                market_id=None,
                reason=RejectReason.UNKNOWN_ORDER,
                detail="no such resting order",
                item_index=item_index,
            )
        market_id, order = located
        if order.agent_id != agent_id:
            return self._reject_cancel(
                tick=tick,
                agent_id=agent_id,
                order_id=order_id,
                order=order,
                market_id=market_id,
                reason=RejectReason.NOT_ORDER_OWNER,
                detail="the order belongs to another account",
                item_index=item_index,
            )
        self._cancel_resting(tick=tick, market_id=market_id, order=order, reason=reason)
        return OrderResult(
            accepted=True,
            order_id=order_id,
            filled_qty=0,
            resting_qty=0,
            reason=None,
            trades=(),
        )

    def cancel_all(
        self,
        *,
        tick: int,
        reason: CancelReason,
        agent_id: str | None = None,
        market_id: str | None = None,
    ) -> tuple[str, ...]:
        """Cancel a whole slice of the book, emitting one event per order.

        The three callers of this method are fixed by CONTRACTS section 7.8:
        the oracle (``market_id=`` form, at a resolution or a cancellation), the
        reference market maker (``agent_id="MM", market_id=`` form, P3 step 9)
        and the runner's freeze path (``agent_id=`` form, P4 step 14).

        Args:
            tick: Current tick.
            reason: Why the orders are leaving the book.
            agent_id: Restrict to one account, or ``None`` for every account.
            market_id: Restrict to one market, or ``None`` for every market in
                ascending order.

        Returns:
            The cancelled order ids in **emission order**: markets ascending,
            and inside a market ``priority_key`` order with bids before asks.
            This is exactly what ``AgentFrozen.cancelled_order_ids`` carries.

        Raises:
            InvalidConfigError: If ``market_id`` is not part of the scenario.
        """
        if market_id is not None:
            self._require_market(market_id)
            targets: tuple[str, ...] = (market_id,)
        else:
            targets = self._market_ids
        cancelled: list[str] = []
        for target in targets:
            book = self._books[target]
            orders = book.resting_orders() if agent_id is None else book.orders_of(agent_id)
            for order in orders:
                self._cancel_resting(tick=tick, market_id=target, order=order, reason=reason)
                cancelled.append(order.order_id)
        return tuple(cancelled)

    def close_market(self, *, tick: int, market_id: str, status: MarketStatus) -> None:
        """Stop trading on one market for good (FR-5.4.5).

        Market status transitions have exactly one owner: this method is called
        by ``Oracle.resolve`` and ``Oracle.cancel_market`` and by nothing else
        (CONTRACTS section 7.8).

        Args:
            tick: Current tick, recorded as the market's closing tick.
            market_id: Market to close.
            status: ``RESOLVED`` or ``CANCELLED``.

        Raises:
            InvalidConfigError: If the market is not part of the scenario, if
                ``status`` is not a closed one, or if the market is already
                closed.
            InvariantViolationError: If orders are still resting on it. The
                caller must run ``cancel_all(reason=MARKET_RESOLVED)`` first,
                which is the only ordering that keeps invariant I4 true
                throughout the settlement (P1 step 4a).
        """
        self._require_market(market_id)
        if status not in (MarketStatus.RESOLVED, MarketStatus.CANCELLED):
            raise InvalidConfigError("close_market takes RESOLVED or CANCELLED", status=str(status))
        if self._status[market_id] is not MarketStatus.OPEN:
            raise InvalidConfigError(
                "market is already closed",
                market_id=market_id,
                status=str(self._status[market_id]),
            )
        if not self._books[market_id].is_empty():
            raise InvariantViolationError(
                "closing a market that still holds resting orders; cancel_all comes first",
                market_id=market_id,
                resting=len(self._books[market_id].resting_orders()),
            )
        self._status[market_id] = status
        self._closed_tick[market_id] = tick

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _check_place(
        self,
        *,
        tick: int,
        agent_id: str,
        intent: OrderIntent,
        item_index: int,
    ) -> _Accepted | OrderResult:
        """Run every pre-trade check in order, or emit the one rejection."""
        structural = self._check_structure(tick=tick, agent_id=agent_id, intent=intent, item_index=item_index)
        if isinstance(structural, OrderResult):
            return structural
        market_id, side, order_type, qty, limit_price = structural

        if self._status[market_id] is not MarketStatus.OPEN:
            return self._reject_place(
                tick=tick,
                agent_id=agent_id,
                intent=intent,
                reason=RejectReason.MARKET_NOT_OPEN,
                detail=f"market is {self._status[market_id]}",
                item_index=item_index,
            )
        if self._accounts.is_frozen(agent_id):
            return self._reject_place(
                tick=tick,
                agent_id=agent_id,
                intent=intent,
                reason=RejectReason.AGENT_FROZEN,
                detail="the account is frozen for the rest of the match",
                item_index=item_index,
            )

        ref_price: int | None = None
        if order_type is OrderType.MARKET:
            # FR-5.4.3: a market order is a marketable limit bounded to
            # +/- market_band_cents around the reference price. The unexecutable
            # remainder is cancelled by _settle_residual and never rests.
            reference, _source = self.reference_price(market_id)
            ref_price = reference
            price = band_limit_price(reference, side, self._config.market_band_cents)
            tif = TimeInForce.IOC
        else:
            price = limit_price
            tif = TimeInForce.GTC

        book = self._books[market_id]
        if book.count_of(agent_id) >= self._config.max_active_orders_per_market:
            return self._reject_place(
                tick=tick,
                agent_id=agent_id,
                intent=intent,
                reason=RejectReason.ORDER_LIMIT_EXCEEDED,
                detail=f"already resting {book.count_of(agent_id)} orders on {market_id}",
                item_index=item_index,
                price=price,
            )

        collateral_cents = order_collateral_cents(side, price, qty)
        fee_cents = reserve_fee_for(self._config, qty=qty)
        # Evaluated against the free cash as it stands now, before any STP
        # cancellation this submission would trigger (decision 21).
        if not self._accounts.can_afford(
            account_id=agent_id,
            collateral_cents=collateral_cents,
            fee_cents=fee_cents,
        ):
            return self._reject_place(
                tick=tick,
                agent_id=agent_id,
                intent=intent,
                reason=RejectReason.INSUFFICIENT_COLLATERAL,
                detail=(
                    f"needs {collateral_cents + fee_cents} cents, "
                    f"free cash is {self._accounts.free_cash_cents(agent_id)}"
                ),
                item_index=item_index,
                price=price,
            )
        return _Accepted(
            market_id=market_id,
            side=side,
            order_type=order_type,
            price=price,
            qty=qty,
            tif=tif,
            ref_price=ref_price,
        )

    def _check_structure(
        self,
        *,
        tick: int,
        agent_id: str,
        intent: OrderIntent,
        item_index: int,
    ) -> tuple[str, Side, OrderType, int, int] | OrderResult:
        """Refuse a malformed or unknown-market place intent.

        ``validate_action`` (A11) already drops every one of these, so no branch
        here fires in a correct engine. They are rejections and not exceptions
        on purpose: a bug in the validator must cost an agent one order, never
        abort the match on agent supplied data (CONTRACTS section 2.4, "agent
        misbehaviour is never an exception at the engine boundary").

        Returns:
            ``(market_id, side, order_type, qty, limit_price)`` on success, or
            the :class:`OrderResult` of the emitted rejection. ``limit_price``
            is the validated limit of a ``limit`` order and an unread ``0`` for
            a ``market`` order, whose price comes from the FR-5.4.3 band.
        """
        for name, value in (
            ("market_id", intent.market_id),
            ("side", intent.side),
            ("order_type", intent.order_type),
            ("qty", intent.qty),
        ):
            if value is None:
                return self._reject_place(
                    tick=tick,
                    agent_id=agent_id,
                    intent=intent,
                    reason=RejectReason.MISSING_FIELD,
                    detail=f"a place intent needs {name}",
                    item_index=item_index,
                )
        market_id = intent.market_id
        side = intent.side
        order_type = intent.order_type
        qty = intent.qty
        if market_id is None or side is None or order_type is None or qty is None:
            # Unreachable after the loop above. It is how the type checker
            # learns the four fields are set, without an assert (rule S101).
            raise InvariantViolationError("a place intent lost a field", agent_id=agent_id)
        if market_id not in self._specs:
            return self._reject_place(
                tick=tick,
                agent_id=agent_id,
                intent=intent,
                reason=RejectReason.UNKNOWN_MARKET,
                detail="no such market in this scenario",
                item_index=item_index,
            )
        if not 1 <= qty <= MAX_ORDER_QTY:
            return self._reject_place(
                tick=tick,
                agent_id=agent_id,
                intent=intent,
                reason=RejectReason.INVALID_QTY,
                detail=f"quantity must be in [1, {MAX_ORDER_QTY}]",
                item_index=item_index,
            )
        limit_price = 0
        if order_type is OrderType.LIMIT:
            if intent.price is None:
                return self._reject_place(
                    tick=tick,
                    agent_id=agent_id,
                    intent=intent,
                    reason=RejectReason.MISSING_FIELD,
                    detail="a limit order needs a price",
                    item_index=item_index,
                )
            if not PRICE_MIN <= intent.price <= PRICE_MAX:
                return self._reject_place(
                    tick=tick,
                    agent_id=agent_id,
                    intent=intent,
                    reason=RejectReason.INVALID_PRICE,
                    detail=f"price must be in [{PRICE_MIN}, {PRICE_MAX}]",
                    item_index=item_index,
                )
            limit_price = intent.price
        return (market_id, side, order_type, qty, limit_price)

    def _apply_stp(
        self,
        *,
        tick: int,
        order: Order,
        stp_order_ids: tuple[str, ...],
        book: OrderBook,
    ) -> None:
        """Cancel the incoming order's own crossed orders (FR-5.4.4).

        Per resting order, in ``priority_key`` order: one ``OrderCancelled``
        carrying the released collateral, then one ``STPCancelled`` carrying
        that event's ``seq`` and no money at all (decision 20). The incoming
        order is never stopped: matching already continued past these.
        """
        for resting_order_id in stp_order_ids:
            resting = book.get(resting_order_id)
            if resting is None:
                raise InvariantViolationError(
                    "an STP marked order is no longer in the book",
                    order_id=resting_order_id,
                    market_id=order.market_id,
                )
            cancelled_qty = resting.remaining_qty
            cancel_event = self._cancel_resting(
                tick=tick,
                market_id=order.market_id,
                order=resting,
                reason=CancelReason.STP,
            )
            self._journal.emit(
                STPCancelled,
                tick=tick,
                agent_id=order.agent_id,
                market_id=order.market_id,
                incoming_order_id=order.order_id,
                resting_order_id=resting_order_id,
                cancelled_qty=cancelled_qty,
                cancel_seq=cancel_event.seq,
            )

    def _apply_fills(
        self,
        *,
        tick: int,
        order: Order,
        plan_fills: tuple[Fill, ...],
        book: OrderBook,
    ) -> tuple[Trade, ...]:
        """Execute the planned fills at the maker price, in fill order."""
        trades: list[Trade] = []
        for fill in plan_fills:
            maker_order_id = fill.maker_order_id
            fill_price = fill.price
            fill_qty = fill.qty
            maker = book.get(maker_order_id)
            if maker is None:
                raise InvariantViolationError(
                    "a planned maker is no longer in the book",
                    order_id=maker_order_id,
                    market_id=order.market_id,
                )
            # Collateral is released before the cash moves, on both legs, so
            # free cash never dips below zero mid execution (invariant I4).
            self._accounts.release_order(account_id=maker.agent_id, order=maker, released_qty=fill_qty)
            book.reduce(maker_order_id, fill_qty)
            self._accounts.release_order(account_id=order.agent_id, order=order, released_qty=fill_qty)

            self._trade_seq += 1
            trade = Trade(
                trade_id=make_trade_id(self._trade_seq),
                market_id=order.market_id,
                price=fill_price,
                qty=fill_qty,
                maker_order_id=maker_order_id,
                maker_agent_id=maker.agent_id,
                maker_side=maker.side,
                taker_order_id=order.order_id,
                taker_agent_id=order.agent_id,
                taker_fee_cents=taker_fee_for(self._config, price=fill_price, qty=fill_qty),
                tick=tick,
                seq=self._trade_seq,
            )
            maker_delta, taker_delta = self._accounts.apply_trade(trade)
            book.set_last_price(fill_price)
            self._tick_volume[order.market_id] += fill_qty
            self._journal.emit(
                TradeExecuted,
                tick=tick,
                trade_id=trade.trade_id,
                market_id=trade.market_id,
                price=trade.price,
                qty=trade.qty,
                maker_order_id=trade.maker_order_id,
                maker_agent_id=trade.maker_agent_id,
                maker_side=str(trade.maker_side),
                taker_order_id=trade.taker_order_id,
                taker_agent_id=trade.taker_agent_id,
                taker_side=str(trade.taker_side),
                taker_fee_cents=trade.taker_fee_cents,
                maker_cash_delta_cents=maker_delta,
                taker_cash_delta_cents=taker_delta,
                maker_position_after=self._accounts.position(maker.agent_id, order.market_id).qty,
                taker_position_after=self._accounts.position(order.agent_id, order.market_id).qty,
            )
            trades.append(trade)
        return tuple(trades)

    def _settle_residual(self, *, tick: int, order: Order, residual_qty: int, book: OrderBook) -> int:
        """Rest a GTC residual, or cancel an IOC one (FR-5.4.3).

        Returns:
            The quantity left resting: ``residual_qty`` for a ``GTC`` limit and
            ``0`` for an ``IOC``, whose unexecutable remainder is cancelled and
            never left in the book.
        """
        if residual_qty == 0:
            return 0
        if order.tif is TimeInForce.IOC:
            released_cents = self._accounts.release_order(
                account_id=order.agent_id,
                order=order,
                released_qty=residual_qty,
            )
            self._journal.emit(
                OrderCancelled,
                tick=tick,
                order_id=order.order_id,
                agent_id=order.agent_id,
                market_id=order.market_id,
                side=str(order.side),
                price=order.price,
                remaining_qty=residual_qty,
                reason=str(CancelReason.IOC_RESIDUAL),
                released_cents=released_cents,
            )
            return 0
        filled_qty = order.qty - residual_qty
        resting = order.with_fill(filled_qty) if filled_qty else order.with_status(OrderStatus.OPEN)
        book.add(resting)
        return residual_qty

    def _cancel_resting(
        self,
        *,
        tick: int,
        market_id: str,
        order: Order,
        reason: CancelReason,
    ) -> OrderCancelled:
        """Remove one resting order, release its collateral and emit the event.

        Returns:
            The emitted ``OrderCancelled``. Its ``released_cents`` is the
            single report of that money movement, whatever the cancellation
            path (CONTRACTS section 4.5), and its ``seq`` is what the
            following ``STPCancelled`` points at.
        """
        book = self._books[market_id]
        removed = book.remove(order.order_id)
        released_cents = self._accounts.release_order(
            account_id=removed.agent_id,
            order=removed,
            released_qty=removed.remaining_qty,
        )
        return self._journal.emit(
            OrderCancelled,
            tick=tick,
            order_id=removed.order_id,
            agent_id=removed.agent_id,
            market_id=market_id,
            side=str(removed.side),
            price=removed.price,
            remaining_qty=removed.remaining_qty,
            reason=str(reason),
            released_cents=released_cents,
        )

    def _locate(self, order_id: str) -> tuple[str, Order] | None:
        """Find a resting order across every book of the match."""
        for market_id in self._market_ids:
            order = self._books[market_id].get(order_id)
            if order is not None:
                return (market_id, order)
        return None

    def _reject_place(
        self,
        *,
        tick: int,
        agent_id: str,
        intent: OrderIntent,
        reason: RejectReason,
        detail: str,
        item_index: int,
        price: int | None = None,
    ) -> OrderResult:
        """Emit one ``OrderRejected`` for a refused ``place`` intent."""
        self._journal.emit(
            OrderRejected,
            tick=tick,
            agent_id=agent_id,
            market_id=intent.market_id,
            side=None if intent.side is None else str(intent.side),
            requested_type=None if intent.order_type is None else str(intent.order_type),
            # The band converted price when the refusal happened after the
            # FR-5.4.3 conversion, so a collateral rejection reports the price
            # the check was actually run against.
            price=intent.price if price is None else price,
            qty=intent.qty,
            reason=str(reason),
            detail=detail[:_DETAIL_MAX_CHARS],
            item_index=item_index,
        )
        return OrderResult(
            accepted=False,
            order_id=None,
            filled_qty=0,
            resting_qty=0,
            reason=reason,
            trades=(),
        )

    def _reject_cancel(
        self,
        *,
        tick: int,
        agent_id: str,
        order_id: str,
        order: Order | None,
        market_id: str | None,
        reason: RejectReason,
        detail: str,
        item_index: int,
    ) -> OrderResult:
        """Emit one ``OrderRejected`` for a refused ``cancel`` intent."""
        self._journal.emit(
            OrderRejected,
            tick=tick,
            agent_id=agent_id,
            market_id=market_id,
            side=None if order is None else str(order.side),
            requested_type=None if order is None else str(order.order_type),
            price=None if order is None else order.price,
            qty=None if order is None else order.qty,
            reason=str(reason),
            detail=detail[:_DETAIL_MAX_CHARS],
            item_index=item_index,
        )
        return OrderResult(
            accepted=False,
            order_id=order_id,
            filled_qty=0,
            resting_qty=0,
            reason=reason,
            trades=(),
        )

    def _require_market(self, market_id: str) -> None:
        """Raise when ``market_id`` is not part of the scenario."""
        if market_id not in self._specs:
            raise InvalidConfigError("unknown market", market_id=market_id)
