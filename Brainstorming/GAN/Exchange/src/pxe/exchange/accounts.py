"""The ledger: cash, collateral, fees, settlement lines and invariants I1..I12.

This module is the money (CONTRACTS section 7.9, FR-5.5.1 to FR-5.5.5). Three
properties make it what it is, and every design choice below follows from one
of them:

1. **No float ever touches an accounting field.** Every amount is an integer
   number of cents, every price an integer in ``1..99`` and every quantity an
   integer number of contracts.
2. **The system is closed** (FR-5.5.3). The aggregate net position of a market
   is zero, the sum of the cash of every account is constant, and every
   execution and every settlement is zero sum between accounts. Those facts are
   checked, not assumed: :meth:`AccountBook.check_invariants` runs on every P4
   tick of every match, not only in tests.
3. **No negative balance is reachable** (FR-5.5.5). Collateral is reserved at
   placement, released on cancellation and transformed on execution, and a
   reservation that would exceed the free cash is refused before it happens.

:class:`AccountBook` holds **no** :class:`~pxe.journal.Journal` and emits
nothing (CONTRACTS section 4.5). It mutates the ledger and returns the facts;
the oracle (A08) owns the ``SettlementApplied`` emission loop and the exchange
(A05) owns every order and trade event. Giving this class a journal handle
would put one emission loop in two workstreams at once.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from pxe.errors import InvalidConfigError, InvariantViolationError
from pxe.types import (
    FEES_ACCOUNT_ID,
    MM_ACCOUNT_ID,
    RE_AGENT_ID,
    RE_MARKET_ID,
    AccountKind,
    AccountState,
    InventoryView,
    MatchConfig,
    Order,
    Outcome,
    Position,
    Trade,
    order_collateral_cents,
    position_collateral_cents,
    sorted_account_ids,
    sorted_ids,
    taker_fee_cents,
)

__all__ = [
    "SettlementLine",
    "AccountBook",
]

#: The two settlement modes. ``"resolution"`` pays the binary outcome,
#: ``"unwind"`` restores the cash of a cancelled market (FR-5.4.5).
_MODE_RESOLUTION = "resolution"
_MODE_UNWIND = "unwind"


@dataclass(frozen=True, slots=True)
class SettlementLine:
    """One account's cash movement inside one settlement group.

    A group is everything that happens to one market at one settlement, and it
    is zero sum across accounts (invariant I6). The oracle turns each line into
    exactly one ``SettlementApplied`` event, in the canonical account order the
    lines already come in (CONTRACTS section 2.3), which is why the field names
    below are exactly the event's payload field names.

    Attributes:
        account_id: Settled account: a ranked agent, ``MM`` or ``FEES``.
        market_id: Settled market.
        mode: ``"resolution"`` or ``"unwind"``.
        position_qty: Signed position that was settled, before it was flattened.
        cash_delta_cents: Signed cash movement applied to the account.
        cash_before_cents: Cash held before the movement.
        cash_after_cents: Cash held after the movement.
        released_collateral_cents: Collateral released by flattening the
            position, that is ``100 * max(0, -position_qty)``.
    """

    account_id: str
    market_id: str
    mode: str
    position_qty: int
    cash_delta_cents: int
    cash_before_cents: int
    cash_after_cents: int
    released_collateral_cents: int


@dataclass(slots=True)
class _Pos:
    """Mutable per (account, market) ledger row.

    :class:`~pxe.types.Position` is the frozen snapshot handed out; this is the
    internal cell that is actually mutated.

    Attributes:
        qty: Signed net quantity.
        cost_basis_cents: Signed net cash paid to build the position, fees
            excluded. Summed over the accounts of one market it is zero (I12).
        fees_paid_cents: Taker fees this account paid on this market.
    """

    qty: int = 0
    cost_basis_cents: int = 0
    fees_paid_cents: int = 0

    @property
    def is_empty(self) -> bool:
        """True when the row carries no position and no cost basis."""
        return self.qty == 0 and self.cost_basis_cents == 0


def _settlement_delta_cents(row: _Pos, outcome: Outcome | None, fee_refund_cents: int) -> int:
    """Cash movement of one settlement line.

    A resolution pays the binary outcome on the position; an unwind restores
    the cost basis and refunds the taker fees (FR-5.4.5, CONTRACTS section 6.4).

    Args:
        row: The ledger row being settled.
        outcome: The realised outcome, or ``None`` for an unwind.
        fee_refund_cents: Taker fees refunded by an unwind, ``0`` otherwise.

    Returns:
        The signed cash movement in cents.
    """
    if outcome is None:
        return row.cost_basis_cents + fee_refund_cents
    return row.qty * outcome.payout_cents


class AccountBook:
    """The ledger of every account of one match.

    Accounts are the ranked seats plus the two reserved accounts ``MM`` and
    ``FEES``, and they are always walked in the canonical account order of
    CONTRACTS section 2.3 (ranked agents ascending, then ``MM``, then
    ``FEES``), because that order is the journal byte order and therefore part
    of the AC-P1 hash.
    """

    def __init__(self, *, agent_ids: Sequence[str], market_ids: Sequence[str], config: MatchConfig) -> None:
        """Build a flat ledger: every account funded, nothing reserved.

        Takes the whole config, not a handful of scalars: the invariants this
        class owns need ``initial_cash_cents``, ``mm_initial_cash_cents``,
        ``taker_fee_bps``, ``max_active_orders_per_market`` and
        ``mm.inventory_max``, and passing them one by one is how I8 and I10
        silently stopped being checkable.

        Args:
            agent_ids: Ranked seat ids, ``A1``..``A8``. Order is irrelevant:
                they are stored in canonical order.
            market_ids: Market ids of the match, ``M1``..``M8``.
            config: The match configuration.

        Raises:
            InvalidConfigError: If an id is malformed or duplicated.
        """
        self._config = config
        self._agent_ids = sorted_ids(tuple(agent_ids))
        self._market_ids = sorted_ids(tuple(market_ids))
        for agent_id in self._agent_ids:
            if not RE_AGENT_ID.match(agent_id):
                raise InvalidConfigError("not a ranked agent id", agent_id=agent_id)
        for market_id in self._market_ids:
            if not RE_MARKET_ID.match(market_id):
                raise InvalidConfigError("not a market id", market_id=market_id)
        if len(set(self._agent_ids)) != len(self._agent_ids):
            raise InvalidConfigError("duplicate agent id", agent_ids=list(self._agent_ids))
        if len(set(self._market_ids)) != len(self._market_ids):
            raise InvalidConfigError("duplicate market id", market_ids=list(self._market_ids))

        self._account_ids = sorted_account_ids((*self._agent_ids, MM_ACCOUNT_ID, FEES_ACCOUNT_ID))
        self._cash: dict[str, int] = {}
        self._order_reserved: dict[str, int] = {}
        self._open_orders: dict[str, dict[str, int]] = {}
        self._positions: dict[str, dict[str, _Pos]] = {}
        self._frozen: dict[str, bool] = {}
        for account_id in self._account_ids:
            self._cash[account_id] = self._initial_cash_of(account_id)
            self._order_reserved[account_id] = 0
            self._open_orders[account_id] = {}
            self._positions[account_id] = {market_id: _Pos() for market_id in self._market_ids}
            self._frozen[account_id] = False
        self._initial_total_cents = sum(self._cash[account_id] for account_id in self._account_ids)

    # ------------------------------------------------------------------
    # Identity and read only accessors
    # ------------------------------------------------------------------
    def account_ids(self) -> tuple[str, ...]:
        """Every account, in the canonical account order (CONTRACTS section 2.3).

        Returns:
            Ranked agents ascending, then ``MM``, then ``FEES``.
        """
        return self._account_ids

    def ranked_agent_ids(self) -> tuple[str, ...]:
        """The ranked seats only, ascending.

        ``MM`` and ``FEES`` are out of the ranking (FR-5.8.5, FR-5.4.7).

        Returns:
            The ranked agent ids.
        """
        return self._agent_ids

    def state(self, account_id: str) -> AccountState:
        """Snapshot one account.

        Args:
            account_id: Account to snapshot.

        Returns:
            An immutable :class:`~pxe.types.AccountState`. Markets with a null
            position and a null cost basis are omitted from ``positions``.

        Raises:
            InvalidConfigError: If the account is unknown.
            InvariantViolationError: If the snapshot would be inconsistent
                (negative cash, or reserved outside ``[0, cash]``). That is
                raised by :class:`~pxe.types.AccountState` itself and means the
                caller snapshotted mid mutation.
        """
        self._require_account(account_id)
        positions = tuple(
            self.position(account_id, market_id)
            for market_id in self._market_ids
            if not self._positions[account_id][market_id].is_empty
        )
        return AccountState(
            account_id=account_id,
            kind=self._kind_of(account_id),
            cash_cents=self._cash[account_id],
            reserved_cents=self.reserved_cents(account_id),
            positions=positions,
            frozen=self._frozen[account_id],
        )

    def states(self) -> tuple[AccountState, ...]:
        """Snapshot every account, in canonical account order.

        Returns:
            One :class:`~pxe.types.AccountState` per account.
        """
        return tuple(self.state(account_id) for account_id in self._account_ids)

    def cash_cents(self, account_id: str) -> int:
        """Total cash of one account, collateral included.

        Args:
            account_id: Account to read.

        Returns:
            The cash in cents, never negative (FR-5.5.5).

        Raises:
            InvalidConfigError: If the account is unknown.
        """
        self._require_account(account_id)
        return self._cash[account_id]

    def reserved_cents(self, account_id: str) -> int:
        """Cash locked by resting orders and open short positions (FR-5.5.1).

        There is no cross market netting (FR-5.5.2): the total is the plain sum
        of the per order and per market worst cases.

        Args:
            account_id: Account to read.

        Returns:
            The reserved cash in cents.

        Raises:
            InvalidConfigError: If the account is unknown.
        """
        self._require_account(account_id)
        total = self._order_reserved[account_id]
        rows = self._positions[account_id]
        for market_id in self._market_ids:
            total += position_collateral_cents(rows[market_id].qty)
        return total

    def free_cash_cents(self, account_id: str) -> int:
        """Cash available for new collateral: ``cash_cents - reserved_cents``.

        Args:
            account_id: Account to read.

        Returns:
            The free cash in cents, never negative while the invariants hold.

        Raises:
            InvalidConfigError: If the account is unknown.
        """
        return self.cash_cents(account_id) - self.reserved_cents(account_id)

    def position(self, account_id: str, market_id: str) -> Position:
        """Net position of one account on one market.

        Args:
            account_id: Account to read.
            market_id: Market to read.

        Returns:
            A frozen :class:`~pxe.types.Position`, flat when nothing was traded.

        Raises:
            InvalidConfigError: If the account or the market is unknown.
        """
        self._require_account(account_id)
        self._require_market(market_id)
        row = self._positions[account_id][market_id]
        return Position(
            market_id=market_id,
            qty=row.qty,
            cost_basis_cents=row.cost_basis_cents,
            fees_paid_cents=row.fees_paid_cents,
        )

    def inventory_view(self, account_id: str) -> InventoryView:
        """A frozen read only snapshot of one account, for the market maker.

        The reference market maker needs its own inventory to skew and to cap
        (FR-5.8.3) and its free cash to know whether a quote can be
        collateralised, but it must not hold a mutation handle on the ledger
        and :mod:`pxe.mm` must not import this module. This snapshot is the
        boundary: A06 produces it, A07 consumes it, and
        :class:`~pxe.types.InventoryView` lives in :mod:`pxe.types` so neither
        package imports the other.

        Args:
            account_id: Account to snapshot, normally ``MM``.

        Returns:
            The snapshot, with one entry per market of the match sorted by
            ``market_id``.

        Raises:
            InvalidConfigError: If the account is unknown.
        """
        self._require_account(account_id)
        rows = self._positions[account_id]
        return InventoryView(
            account_id=account_id,
            cash_cents=self._cash[account_id],
            reserved_cents=self.reserved_cents(account_id),
            free_cash_cents=self.free_cash_cents(account_id),
            inventory_qty_by_market=tuple((market_id, rows[market_id].qty) for market_id in self._market_ids),
        )

    def is_frozen(self, account_id: str) -> bool:
        """Whether the account went bankrupt (FR-5.5.5).

        Args:
            account_id: Account to read.

        Returns:
            True once the account has been frozen. A freeze is permanent.

        Raises:
            InvalidConfigError: If the account is unknown.
        """
        self._require_account(account_id)
        return self._frozen[account_id]

    def freeze(self, account_id: str) -> None:
        """Freeze a bankrupt agent for the rest of the match (FR-5.5.5).

        Freezing is idempotent and permanent. The runner cancels the agent's
        resting orders through the exchange **before** calling this, so the
        collateral is released by ``OrderCancelled`` events (CONTRACTS
        section 4.5, P4 step 14).

        Args:
            account_id: Ranked agent to freeze.

        Raises:
            InvalidConfigError: If the account is unknown, or is ``MM`` or
                ``FEES``: only ranked agents are ranked, and only a ranked
                agent can go bankrupt.
        """
        self._require_account(account_id)
        if account_id not in self._positions or not RE_AGENT_ID.match(account_id):
            raise InvalidConfigError("only a ranked agent can be frozen", account_id=account_id)
        self._frozen[account_id] = True

    def resting_order_count(self, account_id: str) -> int:
        """How many of the account's orders still hold collateral.

        This is a **count** and deliberately not a list of ids: the ids live in
        the book and not in the ledger, and ``MatchState.resting_order_ids`` is
        the one accessor for them (CONTRACTS section 7.12). The count is what
        the FR-5.5.5 bankruptcy predicate needs.

        Args:
            account_id: Account to read.

        Returns:
            The number of orders whose collateral is still reserved.

        Raises:
            InvalidConfigError: If the account is unknown.
        """
        self._require_account(account_id)
        return len(self._open_orders[account_id])

    def fees_paid_cents(self, account_id: str, market_id: str) -> int:
        """Taker fees this account paid on this market.

        Needed by the FR-5.4.5 unwind refund (CONTRACTS section 6.4) and by
        ``PerformanceMetrics.fees_paid_cents``. An unwind refunds them and
        resets this to zero, because after a cancellation the market must leave
        the account exactly as it found it.

        Args:
            account_id: Account to read.
            market_id: Market to read.

        Returns:
            The fees paid in cents, always ``>= 0``.

        Raises:
            InvalidConfigError: If the account or the market is unknown.
        """
        self._require_account(account_id)
        self._require_market(market_id)
        return self._positions[account_id][market_id].fees_paid_cents

    def total_cash_cents(self) -> int:
        """Sum of the cash of every account, the quantity invariant I2 pins.

        Returns:
            The total cash in cents.
        """
        return sum(self._cash[account_id] for account_id in self._account_ids)

    def initial_total_cash_cents(self) -> int:
        """The constant I2 compares :meth:`total_cash_cents` against.

        That is ``n_agents * config.initial_cash_cents +
        config.mm_initial_cash_cents``, with ``n_agents`` the number of seats
        this book was actually built with and the ``FEES`` vault starting at
        zero.

        Returns:
            The total cash in cents at tick 0.
        """
        return self._initial_total_cents

    def equity_cents(self, account_id: str, ref_prices: Mapping[str, int]) -> int:
        """Mark to market equity (FR-5.5.4).

        Args:
            account_id: Account to value.
            ref_prices: Reference price per market id (FR-5.4.6). Iterated
                through :func:`~pxe.types.sorted_ids`, never in mapping order
                (CONTRACTS section 2.3). Markets absent from it are already
                settled and contribute nothing.

        Returns:
            ``cash_cents + sum(qty * ref_price)``.

        Raises:
            InvalidConfigError: If the account is unknown, or a key of
                ``ref_prices`` is an account id rather than a market id (the
                canonical sort helper refuses ``MM`` and ``FEES``). A market id
                this book does not hold contributes nothing rather than
                raising, which is what makes a settled market disappear from
                the valuation on its own.
        """
        self._require_account(account_id)
        rows = self._positions[account_id]
        total = self._cash[account_id]
        for market_id in sorted_ids(tuple(ref_prices.keys())):
            row = rows.get(market_id)
            if row is not None:
                total += row.qty * ref_prices[market_id]
        return total

    # ------------------------------------------------------------------
    # Collateral: reserved at placement, released on cancel (FR-5.5.1)
    # ------------------------------------------------------------------
    def can_afford(self, *, account_id: str, collateral_cents: int, fee_cents: int) -> bool:
        """The FR-5.5.1 pre-trade solvency check, evaluated before matching.

        ``accept iff free_cash_cents(a) >= collateral(order) +
        max_taker_fee_cents(fee_bps, qty)``. The fee term is the worst case, so
        a better fill can never defeat the check. Collateral released by an STP
        cancellation that the same submission triggers is deliberately **not**
        available here (CONTRACTS section 6.1): this is evaluated first.

        Args:
            account_id: Submitting account.
            collateral_cents: Collateral the order would lock.
            fee_cents: Worst case taker fee of the order.

        Returns:
            True when the order may be accepted.

        Raises:
            InvalidConfigError: If the account is unknown or an amount is
                negative.
        """
        self._require_account(account_id)
        if collateral_cents < 0 or fee_cents < 0:
            raise InvalidConfigError(
                "collateral and fee must be >= 0",
                collateral=collateral_cents,
                fee=fee_cents,
            )
        return self.free_cash_cents(account_id) >= collateral_cents + fee_cents

    def reserve_order(self, *, account_id: str, order: Order) -> int:
        """Lock the collateral of an accepted order (FR-5.5.1).

        The amount is ``price * remaining_qty`` for a buy and
        ``(100 - price) * remaining_qty`` for a sell, computed from
        :func:`~pxe.types.order_collateral_cents` on the **unfilled** quantity.
        It is read from the order's fields and not from
        ``Order.collateral_cents``, because that property returns ``0`` while
        the order is still ``NEW``, which is exactly the state it is in when
        the exchange reserves for it.

        Args:
            account_id: Owning account.
            order: The order being accepted. ``remaining_qty`` is the quantity
                to collateralise.

        Returns:
            The amount locked in cents.

        Raises:
            InvalidConfigError: If the account is unknown or the order belongs
                to another account.
            InvariantViolationError: If collateral is already held for that
                order id, or if the reservation would push the free cash below
                zero (I4). Either is an engine bug: the caller must run
                :meth:`can_afford` first.
        """
        self._require_account(account_id)
        if order.agent_id != account_id:
            raise InvalidConfigError(
                "order belongs to another account",
                account_id=account_id,
                order_owner=order.agent_id,
                order_id=order.order_id,
            )
        self._require_market(order.market_id)
        held = self._open_orders[account_id]
        if order.order_id in held:
            raise InvariantViolationError(
                "collateral already reserved for this order",
                account_id=account_id,
                order_id=order.order_id,
            )
        amount = order_collateral_cents(order.side, order.price, order.remaining_qty)
        if amount > self.free_cash_cents(account_id):
            raise InvariantViolationError(
                "I4: reserving more collateral than the free cash",
                account_id=account_id,
                order_id=order.order_id,
                collateral=amount,
                free_cash=self.free_cash_cents(account_id),
            )
        held[order.order_id] = amount
        self._order_reserved[account_id] += amount
        return amount

    def release_order(self, *, account_id: str, order: Order, released_qty: int) -> int:
        """Release the collateral of a quantity that left the book.

        Called on every path where an order stops holding collateral: an agent
        cancellation, an IOC residual, a market maker requote, a resolution, an
        STP cancellation, a freeze, and each fill of a partially executed
        order. When the released quantity exhausts what the order still held,
        the order stops counting in :meth:`resting_order_count`.

        Args:
            account_id: Owning account.
            order: The order releasing collateral, carrying the side and the
                price the collateral was computed at.
            released_qty: Quantity whose collateral is released, ``>= 0``.

        Returns:
            The amount released in cents.

        Raises:
            InvalidConfigError: If the account is unknown, the order belongs to
                another account, or ``released_qty`` is negative.
            InvariantViolationError: If no collateral is held for that order
                id, or the release exceeds what is held. Either would create
                money.
        """
        self._require_account(account_id)
        if order.agent_id != account_id:
            raise InvalidConfigError(
                "order belongs to another account",
                account_id=account_id,
                order_owner=order.agent_id,
                order_id=order.order_id,
            )
        if released_qty < 0:
            raise InvalidConfigError("released quantity must be >= 0", qty=released_qty)
        held = self._open_orders[account_id]
        current = held.get(order.order_id)
        if current is None:
            raise InvariantViolationError(
                "no collateral is held for this order",
                account_id=account_id,
                order_id=order.order_id,
            )
        amount = order_collateral_cents(order.side, order.price, released_qty)
        if amount > current:
            raise InvariantViolationError(
                "release exceeds the collateral held for this order",
                account_id=account_id,
                order_id=order.order_id,
                release=amount,
                held=current,
            )
        remaining = current - amount
        if remaining == 0:
            del held[order.order_id]
        else:
            held[order.order_id] = remaining
        self._order_reserved[account_id] -= amount
        return amount

    # ------------------------------------------------------------------
    # Executions and settlements
    # ------------------------------------------------------------------
    def apply_trade(self, trade: Trade) -> tuple[int, int]:
        """Move the cash, the position and the fee of one execution.

        The execution happens at the maker price (FR-5.4.1) and only the taker
        pays a fee (FR-5.4.7), which is routed to the ``FEES`` vault and
        accumulated in ``fees_paid_cents``. Invariant I5 is checked before this
        returns.

        Args:
            trade: The execution to apply.

        Returns:
            ``(maker_cash_delta_cents, taker_cash_delta_cents)``, exactly what
            ``TradeExecuted`` carries.

        Raises:
            InvalidConfigError: If an account or the market is unknown.
            InvariantViolationError: If the maker and the taker are the same
                account (a self trade must have been prevented by STP,
                FR-5.4.4), if the cash of an account would go negative (I9), or
                if the trade is not zero sum (I5).
        """
        self._require_market(trade.market_id)
        self._require_account(trade.maker_agent_id)
        self._require_account(trade.taker_agent_id)
        if trade.maker_agent_id == trade.taker_agent_id:
            raise InvariantViolationError(
                "a self trade reached the ledger; STP must prevent it (FR-5.4.4)",
                account_id=trade.maker_agent_id,
                trade_id=trade.trade_id,
            )
        fee_cents = trade.taker_fee_cents
        if fee_cents < 0:
            raise InvalidConfigError("taker fee must be >= 0", fee=fee_cents, trade_id=trade.trade_id)

        notional_cents = trade.price * trade.qty
        maker_buys = trade.maker_side.sign > 0
        maker_cash_delta = -notional_cents if maker_buys else notional_cents
        taker_cash_delta = (notional_cents if maker_buys else -notional_cents) - fee_cents

        self._apply_leg(
            account_id=trade.maker_agent_id,
            market_id=trade.market_id,
            qty_delta=trade.qty if maker_buys else -trade.qty,
            basis_delta=notional_cents if maker_buys else -notional_cents,
            cash_delta=maker_cash_delta,
            fee_cents=0,
        )
        self._apply_leg(
            account_id=trade.taker_agent_id,
            market_id=trade.market_id,
            qty_delta=-trade.qty if maker_buys else trade.qty,
            basis_delta=-notional_cents if maker_buys else notional_cents,
            cash_delta=taker_cash_delta,
            fee_cents=fee_cents,
        )
        self._credit(FEES_ACCOUNT_ID, fee_cents)
        self.check_trade_invariant(
            trade=trade,
            maker_cash_delta_cents=maker_cash_delta,
            taker_cash_delta_cents=taker_cash_delta,
            fee_cents=fee_cents,
        )
        return (maker_cash_delta, taker_cash_delta)

    def apply_settlement(
        self,
        *,
        market_id: str,
        outcome: Outcome | None,
        mode: str = _MODE_RESOLUTION,
    ) -> tuple[SettlementLine, ...]:
        """Settle one market for every account, and flatten every position.

        ``outcome`` ``None`` means an unwind (FR-5.4.5, CONTRACTS section 6.4):
        each account gets its cost basis back plus a refund of every taker fee
        it paid on that market, and the ``FEES`` vault pays those refunds. A
        resolution instead pays ``qty * outcome.payout_cents``, which sums to
        zero across accounts precisely because of invariant I1.

        Lines come in canonical account order, ``FEES`` last, and invariant I6
        is checked before this returns. The ledger is the only thing mutated:
        no event is emitted here (CONTRACTS section 7.11 owns that loop).

        Args:
            market_id: Market being settled.
            outcome: The realised outcome, or ``None`` for an unwind.
            mode: ``"resolution"`` or ``"unwind"``. It must agree with
                ``outcome``: they are two spellings of the same decision and a
                disagreement is a bug, not a default.

        Returns:
            One line per account that held a position, a cost basis or (on an
            unwind) a fee to refund, plus the ``FEES`` line of an unwind.

        Raises:
            InvalidConfigError: If the market is unknown, ``mode`` is not one of
                the two modes, or ``mode`` and ``outcome`` disagree.
            InvariantViolationError: If the group is not zero sum (I6) or an
                account's cash would go negative (I9).
        """
        self._require_market(market_id)
        if mode not in (_MODE_RESOLUTION, _MODE_UNWIND):
            raise InvalidConfigError("unknown settlement mode", mode=mode)
        is_unwind = mode == _MODE_UNWIND
        if is_unwind != (outcome is None):
            raise InvalidConfigError(
                "settlement mode and outcome disagree",
                mode=mode,
                outcome=None if outcome is None else str(outcome),
            )

        lines: list[SettlementLine] = []
        refunded_fees_cents = 0
        for account_id in self._account_ids:
            if account_id == FEES_ACCOUNT_ID:
                continue
            row = self._positions[account_id][market_id]
            fee_refund = row.fees_paid_cents if is_unwind else 0
            if row.is_empty and fee_refund == 0:
                continue
            cash_delta = _settlement_delta_cents(row, outcome, fee_refund)
            released = position_collateral_cents(row.qty)
            cash_before = self._cash[account_id]
            self._credit(account_id, cash_delta)
            lines.append(
                SettlementLine(
                    account_id=account_id,
                    market_id=market_id,
                    mode=mode,
                    position_qty=row.qty,
                    cash_delta_cents=cash_delta,
                    cash_before_cents=cash_before,
                    cash_after_cents=self._cash[account_id],
                    released_collateral_cents=released,
                )
            )
            refunded_fees_cents += fee_refund
            row.qty = 0
            row.cost_basis_cents = 0
            if is_unwind:
                row.fees_paid_cents = 0

        if is_unwind and lines:
            cash_before = self._cash[FEES_ACCOUNT_ID]
            self._credit(FEES_ACCOUNT_ID, -refunded_fees_cents)
            lines.append(
                SettlementLine(
                    account_id=FEES_ACCOUNT_ID,
                    market_id=market_id,
                    mode=mode,
                    position_qty=0,
                    cash_delta_cents=-refunded_fees_cents,
                    cash_before_cents=cash_before,
                    cash_after_cents=self._cash[FEES_ACCOUNT_ID],
                    released_collateral_cents=0,
                )
            )

        self.check_settlement_invariant(lines)
        return tuple(lines)

    # ------------------------------------------------------------------
    # Invariants I1..I12 (FR-5.5.3)
    # ------------------------------------------------------------------
    def check_invariants(self, *, ref_prices: Mapping[str, int], book_view: Mapping[str, Sequence[Order]]) -> None:
        """The per tick state check: I1, I2, I3, I4, I7, I8, I9, I10 and I12.

        Both arguments are required and never ``None``: an optional book view
        means I3 and I8 silently do not run, which is how a ledger that has
        drifted from the book passes a whole match.

        Args:
            ref_prices: Reference price per open market (FR-5.4.6). Present so
                the check has everything a mark to market needs; iterated
                through :func:`~pxe.types.sorted_ids`.
            book_view: Every resting order keyed by ``market_id``, as returned
                by ``Exchange.book_view()``. Iterated through
                :func:`~pxe.types.sorted_ids`.

        Raises:
            InvariantViolationError: Naming the first breach found, in the
                order I1, I2, I3, I4, I7, I8, I9, I10, I12.
            InvalidConfigError: If a key of either mapping is not a market id.
        """
        for market_id in sorted_ids(tuple(ref_prices.keys())):
            self._require_market(market_id)
        order_reserved = self._recompute_order_collateral(book_view)
        self._check_net_positions()
        self._check_cash_conservation()
        self._check_reserved_matches_book(order_reserved)
        self._check_free_cash()
        self._check_long_short_symmetry()
        self._check_book_orders(book_view)
        self._check_non_negative_cash()
        self._check_mm_inventory_cap()
        self._check_cost_basis_closure()

    def check_trade_invariant(
        self,
        *,
        trade: Trade,
        maker_cash_delta_cents: int,
        taker_cash_delta_cents: int,
        fee_cents: int,
    ) -> None:
        """I5, at the moment the trade is applied.

        An execution is zero sum: what the maker loses, the taker gains, minus
        the fee, which lands in the ``FEES`` vault. The fee itself has exactly
        one formula, :func:`~pxe.types.taker_fee_cents` on this fill's own
        price and quantity: charging an aggregate over several fills breaks
        this check by up to a cent per price level, because the formula floors.

        Args:
            trade: The execution.
            maker_cash_delta_cents: Signed cash movement of the maker.
            taker_cash_delta_cents: Signed cash movement of the taker.
            fee_cents: Fee debited from the taker.

        Raises:
            InvariantViolationError: If the three amounts do not sum to zero,
                if the fee is not the contracted per fill fee, or if the fee
                did not land in ``FEES``.
        """
        total = maker_cash_delta_cents + taker_cash_delta_cents + fee_cents
        if total != 0:
            raise InvariantViolationError(
                "I5: trade is not zero sum",
                trade_id=trade.trade_id,
                maker_delta=maker_cash_delta_cents,
                taker_delta=taker_cash_delta_cents,
                fee=fee_cents,
                total=total,
            )
        expected_fee = taker_fee_cents(self._config.taker_fee_bps, trade.price, trade.qty)
        if fee_cents != expected_fee or fee_cents != trade.taker_fee_cents:
            raise InvariantViolationError(
                "I5: the taker fee is not the contracted per fill fee",
                trade_id=trade.trade_id,
                fee=fee_cents,
                trade_fee=trade.taker_fee_cents,
                expected=expected_fee,
            )
        if self._cash[FEES_ACCOUNT_ID] < fee_cents:
            raise InvariantViolationError(
                "I5: the taker fee did not land in the FEES vault",
                trade_id=trade.trade_id,
                fee=fee_cents,
                vault=self._cash[FEES_ACCOUNT_ID],
            )

    def check_settlement_invariant(self, lines: Sequence[SettlementLine]) -> None:
        """I6, over one settlement group.

        Args:
            lines: Every line of the group, the ``FEES`` line included.

        Raises:
            InvariantViolationError: If the cash deltas do not sum to zero.
        """
        total = sum(line.cash_delta_cents for line in lines)
        if total != 0:
            raise InvariantViolationError(
                "I6: settlement group is not zero sum",
                market_id=lines[0].market_id if lines else "",
                n_lines=len(lines),
                total=total,
            )

    def check_final_invariant(self) -> None:
        """I11, at finalisation step 18.

        After the final settlement every position is flat, so equity equals
        cash for everyone and the ranking of FR-5.5.4 is a settled ranking and
        not a marked one.

        Raises:
            InvariantViolationError: If any account still holds a position, or
                if any cash went negative.
        """
        for account_id in self._account_ids:
            rows = self._positions[account_id]
            for market_id in self._market_ids:
                if rows[market_id].qty != 0:
                    raise InvariantViolationError(
                        "I11: a position is still open after the final settlement",
                        account_id=account_id,
                        market_id=market_id,
                        qty=rows[market_id].qty,
                    )
            if self._cash[account_id] < 0:
                raise InvariantViolationError(
                    "I11: negative cash after the final settlement",
                    account_id=account_id,
                    cash=self._cash[account_id],
                )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------
    def _initial_cash_of(self, account_id: str) -> int:
        """Starting cash of one account (FR-5.5.3, decision 16)."""
        if account_id == MM_ACCOUNT_ID:
            return self._config.mm_initial_cash_cents
        if account_id == FEES_ACCOUNT_ID:
            return 0
        return self._config.initial_cash_cents

    def _kind_of(self, account_id: str) -> AccountKind:
        """Account kind of one account id."""
        if account_id == MM_ACCOUNT_ID:
            return AccountKind.MARKET_MAKER
        if account_id == FEES_ACCOUNT_ID:
            return AccountKind.FEES
        return AccountKind.AGENT

    def _require_account(self, account_id: str) -> None:
        """Raise when the account is not held by this book."""
        if account_id not in self._cash:
            raise InvalidConfigError("unknown account", account_id=account_id)

    def _require_market(self, market_id: str) -> None:
        """Raise when the market is not part of this match."""
        if market_id not in self._market_ids:
            raise InvalidConfigError("unknown market", market_id=market_id)

    def _credit(self, account_id: str, cash_delta_cents: int) -> None:
        """Move cash and refuse to go negative (I9, FR-5.5.5)."""
        after = self._cash[account_id] + cash_delta_cents
        if after < 0:
            raise InvariantViolationError(
                "I9: cash would go negative",
                account_id=account_id,
                cash=self._cash[account_id],
                delta=cash_delta_cents,
            )
        self._cash[account_id] = after

    def _apply_leg(
        self,
        *,
        account_id: str,
        market_id: str,
        qty_delta: int,
        basis_delta: int,
        cash_delta: int,
        fee_cents: int,
    ) -> None:
        """Apply one side of an execution to the ledger."""
        row = self._positions[account_id][market_id]
        row.qty += qty_delta
        row.cost_basis_cents += basis_delta
        row.fees_paid_cents += fee_cents
        self._credit(account_id, cash_delta)

    def _recompute_order_collateral(self, book_view: Mapping[str, Sequence[Order]]) -> dict[str, int]:
        """Sum the FR-5.5.1 order collateral of ``book_view``, per account (I3)."""
        totals: dict[str, int] = dict.fromkeys(self._account_ids, 0)
        for market_id in sorted_ids(tuple(book_view.keys())):
            self._require_market(market_id)
            for order in book_view[market_id]:
                if order.agent_id not in totals:
                    raise InvariantViolationError(
                        "I3: the book holds an order of an unknown account",
                        account_id=order.agent_id,
                        order_id=order.order_id,
                    )
                totals[order.agent_id] += order_collateral_cents(order.side, order.price, order.remaining_qty)
        return totals

    def _check_net_positions(self) -> None:
        """I1: the aggregate net position of every market is zero."""
        for market_id in self._market_ids:
            total = sum(self._positions[account_id][market_id].qty for account_id in self._account_ids)
            if total != 0:
                raise InvariantViolationError(
                    "I1: aggregate net position is not zero",
                    market_id=market_id,
                    net_qty=total,
                )

    def _check_cash_conservation(self) -> None:
        """I2: the sum of the cash of every account is constant."""
        total = self.total_cash_cents()
        if total != self._initial_total_cents:
            raise InvariantViolationError(
                "I2: total cash is not conserved",
                total=total,
                expected=self._initial_total_cents,
            )

    def _check_reserved_matches_book(self, order_reserved: Mapping[str, int]) -> None:
        """I3: the ledger's reserved cash equals the formula recomputed from the book."""
        for account_id in self._account_ids:
            rows = self._positions[account_id]
            position_part = sum(position_collateral_cents(rows[market_id].qty) for market_id in self._market_ids)
            expected = order_reserved[account_id] + position_part
            actual = self.reserved_cents(account_id)
            if actual != expected:
                raise InvariantViolationError(
                    "I3: reserved cash drifted from the book",
                    account_id=account_id,
                    reserved=actual,
                    recomputed=expected,
                    order_part=order_reserved[account_id],
                    position_part=position_part,
                )

    def _check_free_cash(self) -> None:
        """I4: ``0 <= reserved <= cash`` and ``free_cash >= 0`` for every account."""
        for account_id in self._account_ids:
            reserved = self.reserved_cents(account_id)
            cash = self._cash[account_id]
            if reserved < 0 or reserved > cash:
                raise InvariantViolationError(
                    "I4: reserved cash outside [0, cash]",
                    account_id=account_id,
                    reserved=reserved,
                    cash=cash,
                )

    def _check_long_short_symmetry(self) -> None:
        """I7: per market, the longs exactly mirror the shorts."""
        for market_id in self._market_ids:
            longs = 0
            shorts = 0
            for account_id in self._account_ids:
                qty = self._positions[account_id][market_id].qty
                if qty > 0:
                    longs += qty
                else:
                    shorts += qty
            if longs != -shorts:
                raise InvariantViolationError(
                    "I7: long and short quantities do not mirror",
                    market_id=market_id,
                    longs=longs,
                    shorts=shorts,
                )

    def _check_book_orders(self, book_view: Mapping[str, Sequence[Order]]) -> None:
        """I8: every resting order is well formed and within the FR-5.4.2 cap."""
        cap = self._config.max_active_orders_per_market
        for market_id in sorted_ids(tuple(book_view.keys())):
            counts: dict[str, int] = {}
            for order in book_view[market_id]:
                if not 1 <= order.remaining_qty <= order.qty:
                    raise InvariantViolationError(
                        "I8: resting order quantity out of range",
                        market_id=market_id,
                        order_id=order.order_id,
                        remaining=order.remaining_qty,
                        qty=order.qty,
                    )
                if not order.status.is_resting:
                    raise InvariantViolationError(
                        "I8: a non resting order sits in the book",
                        market_id=market_id,
                        order_id=order.order_id,
                        status=str(order.status),
                    )
                counts[order.agent_id] = counts.get(order.agent_id, 0) + 1
            for account_id in sorted_account_ids(tuple(counts.keys())):
                if counts[account_id] > cap:
                    raise InvariantViolationError(
                        "I8: too many resting orders on one market",
                        account_id=account_id,
                        market_id=market_id,
                        count=counts[account_id],
                        cap=cap,
                    )

    def _check_non_negative_cash(self) -> None:
        """I9: no account holds negative cash."""
        for account_id in self._account_ids:
            if self._cash[account_id] < 0:
                raise InvariantViolationError(
                    "I9: negative cash",
                    account_id=account_id,
                    cash=self._cash[account_id],
                )

    def _check_mm_inventory_cap(self) -> None:
        """I10: the market maker respects its per market inventory cap (FR-5.8.3)."""
        limit = self._config.mm.inventory_max
        rows = self._positions[MM_ACCOUNT_ID]
        for market_id in self._market_ids:
            qty = rows[market_id].qty
            if abs(qty) > limit:
                raise InvariantViolationError(
                    "I10: market maker inventory exceeds the cap",
                    market_id=market_id,
                    inventory_qty=qty,
                    cap=limit,
                )

    def _check_cost_basis_closure(self) -> None:
        """I12: per market, the cost bases of every account sum to zero."""
        for market_id in self._market_ids:
            total = sum(self._positions[account_id][market_id].cost_basis_cents for account_id in self._account_ids)
            if total != 0:
                raise InvariantViolationError(
                    "I12: aggregate cost basis is not zero",
                    market_id=market_id,
                    cost_basis=total,
                )
