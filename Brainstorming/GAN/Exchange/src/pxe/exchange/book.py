"""One price-time ordered book per market (CONTRACTS section 7.7, FR-5.4.1).

The book is the only place that knows where a resting order sits. It is a pure
data structure: it never emits an event, never touches the ledger and never
decides whether an order is affordable. :mod:`pxe.exchange.exchange` owns those
three questions.

Shape and why
-------------
Prices are integers in ``1..99`` with a one cent tick (FR-5.4.5), so a side is
stored as a fixed array of ninety-nine FIFO levels indexed by price. That makes
every operation an index plus a list append or a bounded scan, and it makes
price-time priority a property of the storage rather than of a comparison
function that could drift from :attr:`pxe.types.Order.priority_key`:

* best price first is "walk the array from the best end";
* oldest first inside a level is "the list is appended to in ``seq`` order".

``seq`` is assigned by the exchange and increases by one per accepted order, so
appending is enough and no sort is ever performed on a hot path. The two
guarantees together are exactly FR-5.4.1's "priorite prix-temps".
"""

from __future__ import annotations

from pxe.errors import InvalidOrderError, UnknownOrderError
from pxe.types import (
    DEPTH_LEVELS,
    PRICE_MAX,
    PRICE_MIN,
    RE_MARKET_ID,
    BookLevel,
    BookSnapshot,
    Order,
    Side,
    round_half_up,
)

__all__ = [
    "OrderBook",
]


class OrderBook:
    """The resting orders of one market, in price-time priority (FR-5.4.1).

    Attributes are private; every read goes through a method so the internal
    level array can change without moving a public signature.
    """

    def __init__(self, market_id: str) -> None:
        """Build an empty book for one market.

        Args:
            market_id: ``M1``..``M8``.

        Raises:
            InvalidOrderError: If ``market_id`` is not a market id.
        """
        if not RE_MARKET_ID.match(market_id):
            raise InvalidOrderError("not a market id", market_id=market_id)
        self._market_id = market_id
        # Index 0 is unused: a price is 1..99, so index == price.
        self._bid_levels: list[list[Order]] = [[] for _ in range(PRICE_MAX + 1)]
        self._ask_levels: list[list[Order]] = [[] for _ in range(PRICE_MAX + 1)]
        self._by_id: dict[str, Order] = {}
        self._counts: dict[str, int] = {}
        self._qty: dict[Side, int] = {Side.BUY: 0, Side.SELL: 0}
        self._last_price: int | None = None
        # Cached best of each side. Kept in step by add/remove rather than
        # rescanned on every read, because reference_price() is called for
        # every market at every P4 and for every market order conversion, and a
        # ninety-nine level scan there is the difference between a book that
        # sustains ten thousand orders a second and one that does not.
        self._best_bid_price: int | None = None
        self._best_ask_price: int | None = None

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------
    @property
    def market_id(self) -> str:
        """The market this book belongs to."""
        return self._market_id

    # ------------------------------------------------------------------
    # Prices
    # ------------------------------------------------------------------
    def best_bid(self) -> int | None:
        """Highest resting bid price.

        Returns:
            The price in cents, or ``None`` when the bid side is empty.
        """
        return self._best_bid_price

    def best_ask(self) -> int | None:
        """Lowest resting ask price.

        Returns:
            The price in cents, or ``None`` when the ask side is empty.
        """
        return self._best_ask_price

    def mid_price(self) -> int | None:
        """Rounded mid of the two best limits (PRD glossary, FR-5.4.6).

        Returns:
            ``round_half_up((best_bid + best_ask) / 2)``, or ``None`` when the
            book is not two sided. Half cents go up, never to even:
            :func:`pxe.types.round_half_up` is the one rounding helper and the
            builtin ``round`` is banned (CONTRACTS section 2.1).
        """
        bid = self.best_bid()
        ask = self.best_ask()
        if bid is None or ask is None:
            return None
        return round_half_up((bid + ask) / 2)

    def last_price(self) -> int | None:
        """Last executed price on this market.

        Returns:
            The price in cents, or ``None`` before the first trade.
        """
        return self._last_price

    def set_last_price(self, price: int) -> None:
        """Record the price of an execution (FR-5.4.6 second fallback).

        Args:
            price: Execution price in cents, ``1..99``.

        Raises:
            InvalidOrderError: If the price is outside the tradable band.
        """
        if not PRICE_MIN <= price <= PRICE_MAX:
            raise InvalidOrderError("last price out of range", market_id=self._market_id, price=price)
        self._last_price = price

    # ------------------------------------------------------------------
    # Depth
    # ------------------------------------------------------------------
    def depth(self, side: Side, levels: int = DEPTH_LEVELS) -> tuple[BookLevel, ...]:
        """Aggregated price levels of one side, best first.

        Args:
            side: Side to read.
            levels: Maximum number of levels returned, ``>= 0``.

        Returns:
            Up to ``levels`` :class:`~pxe.types.BookLevel` entries, best price
            first. Empty prices are skipped, so the result is dense.

        Raises:
            InvalidOrderError: If ``levels`` is negative.
        """
        if levels < 0:
            raise InvalidOrderError("level count must be >= 0", market_id=self._market_id, levels=levels)
        out: list[BookLevel] = []
        for price in self._price_scan(side):
            if len(out) == levels:
                break
            orders = self._levels_of(side)[price]
            if not orders:
                continue
            out.append(
                BookLevel(
                    price=price,
                    qty=sum(order.remaining_qty for order in orders),
                    order_count=len(orders),
                )
            )
        return tuple(out)

    def total_qty(self, side: Side) -> int:
        """Total resting quantity of one side.

        Args:
            side: Side to read.

        Returns:
            The sum of ``remaining_qty`` over that side, ``0`` when empty.
        """
        return self._qty[side]

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------
    def resting_orders(self) -> tuple[Order, ...]:
        """Every resting order: bids in priority order, then asks.

        Returns:
            The tuple the exchange hands to ``book_view()`` and the order in
            which ``cancel_all`` emits (CONTRACTS section 7.8).
        """
        return self._side_orders(Side.BUY) + self._side_orders(Side.SELL)

    def orders_of(self, agent_id: str) -> tuple[Order, ...]:
        """The resting orders of one account, in the order of :meth:`resting_orders`.

        Args:
            agent_id: Account id, an agent or ``MM``.

        Returns:
            That account's resting orders, bids in priority order then asks.
        """
        return tuple(order for order in self.resting_orders() if order.agent_id == agent_id)

    def count_of(self, agent_id: str) -> int:
        """How many orders one account rests on this market (the FR-5.4.2 cap).

        Args:
            agent_id: Account id.

        Returns:
            The count, ``0`` when the account rests nothing here.
        """
        return self._counts.get(agent_id, 0)

    def get(self, order_id: str) -> Order | None:
        """Look one resting order up by id.

        Args:
            order_id: ``o-000001`` style id.

        Returns:
            The order, or ``None`` when it is not resting in this book.
        """
        return self._by_id.get(order_id)

    def add(self, order: Order) -> None:
        """Rest an order at the back of its price level.

        Args:
            order: The order to rest. Its ``status`` must be resting and its
                ``market_id`` must be this book's.

        Raises:
            InvalidOrderError: If the market does not match, the status is not
                a resting one, nothing is left to rest, or the id is already in
                the book.
        """
        if order.market_id != self._market_id:
            raise InvalidOrderError(
                "order belongs to another market",
                market_id=self._market_id,
                order_market_id=order.market_id,
                order_id=order.order_id,
            )
        if not order.status.is_resting:
            raise InvalidOrderError(
                "only a resting order may sit in the book",
                order_id=order.order_id,
                status=str(order.status),
            )
        if order.remaining_qty < 1:
            raise InvalidOrderError("nothing left to rest", order_id=order.order_id, remaining=order.remaining_qty)
        if order.order_id in self._by_id:
            raise InvalidOrderError("order id already in the book", order_id=order.order_id)
        self._levels_of(order.side)[order.price].append(order)
        self._by_id[order.order_id] = order
        self._counts[order.agent_id] = self._counts.get(order.agent_id, 0) + 1
        self._qty[order.side] += order.remaining_qty
        if order.side is Side.BUY:
            if self._best_bid_price is None or order.price > self._best_bid_price:
                self._best_bid_price = order.price
        elif self._best_ask_price is None or order.price < self._best_ask_price:
            self._best_ask_price = order.price

    def remove(self, order_id: str) -> Order:
        """Take an order out of the book, whatever remains of it.

        Args:
            order_id: Order to remove.

        Returns:
            The order as it was resting, unchanged. The caller decides the
            terminal status and releases the collateral.

        Raises:
            UnknownOrderError: If the order is not resting in this book.
        """
        order = self._by_id.get(order_id)
        if order is None:
            raise UnknownOrderError("order is not resting", market_id=self._market_id, order_id=order_id)
        level = self._levels_of(order.side)[order.price]
        for index, resting in enumerate(level):
            if resting.order_id == order_id:
                del level[index]
                break
        del self._by_id[order_id]
        self._qty[order.side] -= order.remaining_qty
        remaining_count = self._counts[order.agent_id] - 1
        if remaining_count == 0:
            del self._counts[order.agent_id]
        else:
            self._counts[order.agent_id] = remaining_count
        if not level:
            self._rescan_best(order.side)
        return order

    def reduce(self, order_id: str, qty: int) -> Order:
        """Execute ``qty`` contracts of a resting order, keeping its priority.

        A partial fill never changes the order's place in its level: the same
        list slot is overwritten with the reduced copy, which is what makes
        FR-5.4.1's time priority survive partial executions.

        Args:
            order_id: Order to reduce.
            qty: Executed quantity, ``1 <= qty <= remaining_qty``.

        Returns:
            The reduced order. When it is fully filled it is removed from the
            book first and returned with status ``FILLED``.

        Raises:
            UnknownOrderError: If the order is not resting in this book.
            InvalidOrderError: If ``qty`` exceeds what is left.
        """
        order = self._by_id.get(order_id)
        if order is None:
            raise UnknownOrderError("order is not resting", market_id=self._market_id, order_id=order_id)
        if not 1 <= qty <= order.remaining_qty:
            raise InvalidOrderError(
                "fill exceeds the resting quantity",
                order_id=order_id,
                qty=qty,
                remaining=order.remaining_qty,
            )
        reduced = order.with_fill(qty)
        if reduced.remaining_qty == 0:
            self.remove(order_id)
            return reduced
        level = self._levels_of(order.side)[order.price]
        for index, resting in enumerate(level):
            if resting.order_id == order_id:
                level[index] = reduced
                break
        self._by_id[order_id] = reduced
        self._qty[order.side] -= qty
        return reduced

    # ------------------------------------------------------------------
    # Views
    # ------------------------------------------------------------------
    def snapshot(self, ref_price: int, levels: int = DEPTH_LEVELS) -> BookSnapshot:
        """Immutable public view of this book.

        Args:
            ref_price: Reference price in cents (FR-5.4.6), computed by
                :func:`pxe.exchange.matching.reference_price`. It is passed in
                rather than derived here because the fallback chain needs the
                market's public prior, which the book does not hold.
            levels: Number of aggregated levels exposed per side.

        Returns:
            The :class:`~pxe.types.BookSnapshot`.

        Raises:
            InvalidOrderError: If ``ref_price`` is outside ``1..99`` or
                ``levels`` is negative.
        """
        if not PRICE_MIN <= ref_price <= PRICE_MAX:
            raise InvalidOrderError("reference price out of range", market_id=self._market_id, ref_price=ref_price)
        return BookSnapshot(
            market_id=self._market_id,
            bids=self.depth(Side.BUY, levels),
            asks=self.depth(Side.SELL, levels),
            last_price=self._last_price,
            ref_price=ref_price,
            mid_price=self.mid_price(),
        )

    def is_empty(self) -> bool:
        """Whether no order rests here.

        Returns:
            True when both sides are empty.
        """
        return not self._by_id

    # ------------------------------------------------------------------
    # Internals, shared with pxe.exchange.matching only
    # ------------------------------------------------------------------
    def _crossable(self, taker_side: Side, limit_price: int) -> tuple[Order, ...]:
        """Resting orders a taker would cross, in strict price-time order.

        This is the walk FR-5.4.1 describes, materialised once so the planner
        can iterate it without holding a live view of the level arrays.

        Args:
            taker_side: Side of the incoming order.
            limit_price: Its limit price in cents. A buy crosses asks at or
                below it, a sell crosses bids at or above it.

        Returns:
            The candidate makers, best price first then oldest first. Empty
            when nothing is crossable.

        Raises:
            InvalidOrderError: If ``limit_price`` is outside ``1..99``.
        """
        if not PRICE_MIN <= limit_price <= PRICE_MAX:
            raise InvalidOrderError("limit price out of range", market_id=self._market_id, price=limit_price)
        maker_side = taker_side.opposite
        if maker_side is Side.SELL:
            best = self._best_ask_price
            if best is None or best > limit_price:
                return ()
            prices = range(best, limit_price + 1)
        else:
            best = self._best_bid_price
            if best is None or best < limit_price:
                return ()
            prices = range(best, limit_price - 1, -1)
        levels = self._levels_of(maker_side)
        out: list[Order] = []
        for price in prices:
            out.extend(levels[price])
        return tuple(out)

    def _rescan_best(self, side: Side) -> None:
        """Recompute one side's cached best price after its best level emptied."""
        levels = self._levels_of(side)
        for price in self._price_scan(side):
            if levels[price]:
                if side is Side.BUY:
                    self._best_bid_price = price
                else:
                    self._best_ask_price = price
                return
        if side is Side.BUY:
            self._best_bid_price = None
        else:
            self._best_ask_price = None

    def _levels_of(self, side: Side) -> list[list[Order]]:
        """Return the level array of one side."""
        return self._bid_levels if side is Side.BUY else self._ask_levels

    def _price_scan(self, side: Side) -> range:
        """Return the price range of one side, best price first."""
        if side is Side.BUY:
            return range(PRICE_MAX, PRICE_MIN - 1, -1)
        return range(PRICE_MIN, PRICE_MAX + 1)

    def _side_orders(self, side: Side) -> tuple[Order, ...]:
        """Return one side's resting orders in ``priority_key`` order."""
        levels = self._levels_of(side)
        out: list[Order] = []
        for price in self._price_scan(side):
            out.extend(levels[price])
        return tuple(out)
