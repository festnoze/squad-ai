"""A05: the per market order book (CONTRACTS section 7.7, FR-5.4.1, FR-5.4.5).

Two halves, and they are not the same claim:

* the pure structure (``OrderBook``) keeps price-time priority across adds,
  partial reductions and removals, and refuses a price outside the tradable
  band;
* the facade (``Exchange``) turns the band violation into an ``OrderRejected``
  event instead of an exception, because an agent price is agent data and never
  aborts a match (CONTRACTS section 2.4).

Every test that looks at the journal asserts it is non empty and holds at least
one event of the type under test before claiming anything (section 10's
anti-vacuous rule).
"""

from __future__ import annotations

import pytest

from pxe.errors import InvalidOrderError, UnknownOrderError
from pxe.events import OrderPlaced, OrderRejected
from pxe.exchange.book import OrderBook
from pxe.exchange.exchange import Exchange
from pxe.types import (
    DEPTH_LEVELS,
    MarketSpec,
    Order,
    OrderIntent,
    OrderStatus,
    OrderType,
    RejectReason,
    ScenarioSpec,
    Side,
    TimeInForce,
    make_market_id,
)

# ---------------------------------------------------------------------------
# Local builders. Deliberately duplicated in the three A05 test files rather
# than shared: tests/ has no A05 owned helper module (section 13, one row one
# file list), and a fixture name would collide with the ten reserved by
# tests/conftest.py.
# ---------------------------------------------------------------------------


def _scenario(config, *, prior_price: int = 50) -> ScenarioSpec:
    markets = tuple(
        MarketSpec(
            market_id=make_market_id(index),
            question=f"does event {index} happen",
            prior_price=prior_price,
            resolution_tick=config.ticks_total,
            latent_key=f"latent_{index}",
        )
        for index in range(1, config.n_markets + 1)
    )
    return ScenarioSpec(
        template_id="election",
        template_version="1.0.0",
        seed=config.seed,
        ticks_total=config.ticks_total,
        markets=markets,
        talking_mode=config.talking_mode,
        liquidity_profile_name=config.liquidity_profile_name,
    )


def _order(
    *,
    order_id: str,
    agent_id: str,
    side: Side,
    price: int,
    qty: int,
    seq: int,
    market_id: str = "M1",
    remaining_qty: int | None = None,
    status: OrderStatus = OrderStatus.OPEN,
) -> Order:
    return Order(
        order_id=order_id,
        agent_id=agent_id,
        market_id=market_id,
        side=side,
        order_type=OrderType.LIMIT,
        price=price,
        qty=qty,
        remaining_qty=qty if remaining_qty is None else remaining_qty,
        status=status,
        tif=TimeInForce.GTC,
        created_tick=1,
        seq=seq,
    )


# ---------------------------------------------------------------------------
# FR-5.4.5: prices are 1..99, one cent tick
# ---------------------------------------------------------------------------
def test_price_bounds(standard_config, flat_accounts, tmp_journal) -> None:
    """FR-5.4.5: nothing outside 1..99 cents ever reaches the book."""
    # The structure itself refuses an out of band price wherever one can enter.
    book = OrderBook("M1")
    with pytest.raises(InvalidOrderError):
        book.set_last_price(0)
    with pytest.raises(InvalidOrderError):
        book.set_last_price(100)
    with pytest.raises(InvalidOrderError):
        book.snapshot(ref_price=0)
    with pytest.raises(InvalidOrderError):
        book._crossable(Side.BUY, 100)
    # A price is not even expressible on an Order outside the band.
    with pytest.raises(InvalidOrderError):
        _order(order_id="o-000001", agent_id="A1", side=Side.BUY, price=100, qty=1, seq=1)

    # Through the facade the same violation is an event, not an exception.
    exchange = Exchange(
        config=standard_config,
        scenario=_scenario(standard_config),
        accounts=flat_accounts,
        journal=tmp_journal,
    )
    for bad_price in (0, 100, -5):
        exchange.submit(
            tick=1,
            agent_id="A1",
            intent=OrderIntent(
                op="place",
                market_id="M1",
                side=Side.BUY,
                order_type=OrderType.LIMIT,
                price=bad_price,
                qty=5,
            ),
            item_index=0,
        )
    events = tmp_journal.events
    assert events, "the journal must not be empty before it is asserted on"
    rejected = [event for event in events if isinstance(event, OrderRejected)]
    assert len(rejected) == 3
    assert {event.reason for event in rejected} == {str(RejectReason.INVALID_PRICE)}
    assert not [event for event in events if isinstance(event, OrderPlaced)]
    assert exchange.book("M1").is_empty()
    assert flat_accounts.reserved_cents("A1") == 0


# ---------------------------------------------------------------------------
# FR-5.4.1: price-time priority as a property of the structure
# ---------------------------------------------------------------------------
def test_resting_orders_are_best_price_then_oldest() -> None:
    """Bids descend, asks ascend, and inside a level the lowest seq is first."""
    book = OrderBook("M1")
    book.add(_order(order_id="o-000001", agent_id="A1", side=Side.BUY, price=40, qty=5, seq=1))
    book.add(_order(order_id="o-000002", agent_id="A2", side=Side.BUY, price=45, qty=5, seq=2))
    book.add(_order(order_id="o-000003", agent_id="A3", side=Side.BUY, price=45, qty=5, seq=3))
    book.add(_order(order_id="o-000004", agent_id="A1", side=Side.SELL, price=60, qty=5, seq=4))
    book.add(_order(order_id="o-000005", agent_id="A2", side=Side.SELL, price=55, qty=5, seq=5))

    ids = [order.order_id for order in book.resting_orders()]
    assert ids == ["o-000002", "o-000003", "o-000001", "o-000005", "o-000004"]
    # And it is exactly the order Order.priority_key sorts to, per side.
    bids = [order for order in book.resting_orders() if order.side is Side.BUY]
    assert bids == sorted(bids, key=lambda order: order.priority_key)
    asks = [order for order in book.resting_orders() if order.side is Side.SELL]
    assert asks == sorted(asks, key=lambda order: order.priority_key)
    assert book.best_bid() == 45
    assert book.best_ask() == 55
    assert book.total_qty(Side.BUY) == 15
    assert book.total_qty(Side.SELL) == 10


def test_reduce_keeps_time_priority_and_removes_a_filled_order() -> None:
    """A partial fill never sends a resting order to the back of its level."""
    book = OrderBook("M1")
    book.add(_order(order_id="o-000001", agent_id="A1", side=Side.SELL, price=60, qty=10, seq=1))
    book.add(_order(order_id="o-000002", agent_id="A2", side=Side.SELL, price=60, qty=10, seq=2))

    reduced = book.reduce("o-000001", 4)
    assert reduced.remaining_qty == 6
    assert reduced.status is OrderStatus.PARTIALLY_FILLED
    assert [order.order_id for order in book.resting_orders()] == ["o-000001", "o-000002"]
    assert book.total_qty(Side.SELL) == 16

    filled = book.reduce("o-000001", 6)
    assert filled.remaining_qty == 0
    assert filled.status is OrderStatus.FILLED
    assert book.get("o-000001") is None
    assert [order.order_id for order in book.resting_orders()] == ["o-000002"]
    assert book.total_qty(Side.SELL) == 10
    assert book.count_of("A1") == 0

    with pytest.raises(UnknownOrderError):
        book.reduce("o-000001", 1)
    with pytest.raises(InvalidOrderError):
        book.reduce("o-000002", 11)


def test_crossable_walk_stops_at_the_limit_price() -> None:
    """The walk exposes exactly the orders a taker limit reaches, in priority order."""
    book = OrderBook("M1")
    book.add(_order(order_id="o-000001", agent_id="A1", side=Side.SELL, price=55, qty=5, seq=1))
    book.add(_order(order_id="o-000002", agent_id="A2", side=Side.SELL, price=60, qty=5, seq=2))
    book.add(_order(order_id="o-000003", agent_id="A3", side=Side.SELL, price=65, qty=5, seq=3))
    book.add(_order(order_id="o-000004", agent_id="A4", side=Side.BUY, price=30, qty=5, seq=4))

    assert [o.order_id for o in book._crossable(Side.BUY, 60)] == ["o-000001", "o-000002"]
    assert [o.order_id for o in book._crossable(Side.BUY, 54)] == []
    assert [o.order_id for o in book._crossable(Side.SELL, 30)] == ["o-000004"]
    assert [o.order_id for o in book._crossable(Side.SELL, 31)] == []


# ---------------------------------------------------------------------------
# Depth, mid and last price
# ---------------------------------------------------------------------------
def test_depth_aggregates_and_truncates() -> None:
    """Depth is dense, best first, and never longer than the requested level count."""
    book = OrderBook("M1")
    seq = 0
    for price in (30, 35, 40, 45):
        for _ in range(2):
            seq += 1
            book.add(
                _order(
                    order_id=f"o-{seq:06d}",
                    agent_id="A1",
                    side=Side.BUY,
                    price=price,
                    qty=3,
                    seq=seq,
                )
            )
    levels = book.depth(Side.BUY)
    assert len(levels) == DEPTH_LEVELS
    assert [level.price for level in levels] == [45, 40, 35]
    assert [level.qty for level in levels] == [6, 6, 6]
    assert [level.order_count for level in levels] == [2, 2, 2]
    assert book.depth(Side.BUY, 0) == ()
    assert book.depth(Side.SELL) == ()
    with pytest.raises(InvalidOrderError):
        book.depth(Side.BUY, -1)


def test_mid_price_rounds_half_up_and_needs_two_sides() -> None:
    """The mid is defined only on a two sided book, and halves go up (section 2.1)."""
    book = OrderBook("M1")
    assert book.mid_price() is None
    book.add(_order(order_id="o-000001", agent_id="A1", side=Side.BUY, price=40, qty=5, seq=1))
    assert book.mid_price() is None
    book.add(_order(order_id="o-000002", agent_id="A2", side=Side.SELL, price=45, qty=5, seq=2))
    # 42.5 rounds to 43, never to the even 42.
    assert book.mid_price() == 43
    book.remove("o-000002")
    book.add(_order(order_id="o-000003", agent_id="A2", side=Side.SELL, price=44, qty=5, seq=3))
    assert book.mid_price() == 42


def test_last_price_is_undefined_until_an_execution() -> None:
    """``last_price`` is the second branch of FR-5.4.6 and starts empty."""
    book = OrderBook("M1")
    assert book.last_price() is None
    book.set_last_price(37)
    assert book.last_price() == 37


def test_snapshot_mirrors_the_book() -> None:
    """A snapshot is a faithful, immutable view at a given reference price."""
    book = OrderBook("M2")
    book.add(_order(order_id="o-000001", agent_id="A1", side=Side.BUY, price=40, qty=5, seq=1, market_id="M2"))
    book.add(_order(order_id="o-000002", agent_id="A2", side=Side.SELL, price=48, qty=7, seq=2, market_id="M2"))
    book.set_last_price(44)
    snapshot = book.snapshot(ref_price=44)
    assert snapshot.market_id == "M2"
    assert snapshot.best_bid == 40
    assert snapshot.best_ask == 48
    assert snapshot.spread == 8
    assert snapshot.mid_price == 44
    assert snapshot.last_price == 44
    assert snapshot.ref_price == 44


# ---------------------------------------------------------------------------
# Bookkeeping guards
# ---------------------------------------------------------------------------
def test_add_refuses_a_foreign_market_a_duplicate_and_a_non_resting_order() -> None:
    """The three ways a book could start disagreeing with the ledger."""
    book = OrderBook("M1")
    good = _order(order_id="o-000001", agent_id="A1", side=Side.BUY, price=40, qty=5, seq=1)
    book.add(good)
    with pytest.raises(InvalidOrderError):
        book.add(good)
    with pytest.raises(InvalidOrderError):
        book.add(_order(order_id="o-000002", agent_id="A1", side=Side.BUY, price=40, qty=5, seq=2, market_id="M2"))
    with pytest.raises(InvalidOrderError):
        book.add(
            _order(
                order_id="o-000003",
                agent_id="A1",
                side=Side.BUY,
                price=40,
                qty=5,
                seq=3,
                status=OrderStatus.CANCELLED,
            )
        )
    with pytest.raises(InvalidOrderError):
        OrderBook("not-a-market")


def test_counts_and_emptiness_track_the_cap_input() -> None:
    """``count_of`` is what the FR-5.4.2 cap is evaluated against."""
    book = OrderBook("M1")
    assert book.is_empty()
    assert book.count_of("A1") == 0
    for seq in (1, 2, 3):
        book.add(_order(order_id=f"o-{seq:06d}", agent_id="A1", side=Side.BUY, price=30 + seq, qty=1, seq=seq))
    book.add(_order(order_id="o-000004", agent_id="A2", side=Side.BUY, price=20, qty=1, seq=4))
    assert book.count_of("A1") == 3
    assert book.count_of("A2") == 1
    assert [order.order_id for order in book.orders_of("A1")] == ["o-000003", "o-000002", "o-000001"]
    book.remove("o-000002")
    assert book.count_of("A1") == 2
    assert not book.is_empty()
    with pytest.raises(UnknownOrderError):
        book.remove("o-000002")
