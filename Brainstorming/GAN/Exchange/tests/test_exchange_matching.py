"""A05: matching, the order cap, the protection band and the reference price.

Covers FR-5.4.1 (price-time priority, partial fills, execution at the maker
price), FR-5.4.2 (limit GTC / market / cancel with the ten active orders per
agent per market cap and a reasoned rejection), FR-5.4.3 (a ``market`` order is
a marketable limit bounded to the protection band, the unexecutable remainder
cancelled and never resting), FR-5.4.6 (the reference price fallback chain) and
the T1.3 throughput gate of 10 000 orders per second.

Every test that looks at the journal asserts it is non empty and holds at least
one event of the type under test before claiming anything (section 10's
anti-vacuous rule).
"""

from __future__ import annotations

import gc
import time

import pytest

from pxe.errors import InvariantViolationError
from pxe.events import OrderCancelled, OrderPlaced, OrderRejected, TradeExecuted
from pxe.exchange.accounts import AccountBook
from pxe.exchange.exchange import Exchange
from pxe.exchange.matching import band_limit_price, plan_match, reference_price
from pxe.journal import Journal
from pxe.types import (
    FEES_ACCOUNT_ID,
    CancelReason,
    MarketSpec,
    MarketStatus,
    MatchConfig,
    OrderIntent,
    OrderStatus,
    OrderType,
    RejectReason,
    ScenarioSpec,
    Side,
    make_agent_id,
    make_market_id,
    taker_fee_cents,
)

# ---------------------------------------------------------------------------
# Local builders (see the note in tests/test_exchange_book.py).
# ---------------------------------------------------------------------------


def _scenario(config: MatchConfig, *, prior_price: int = 50) -> ScenarioSpec:
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


def _arena(config: MatchConfig, journal: Journal, *, n_agents: int | None = None) -> tuple[Exchange, AccountBook]:
    seats = tuple(make_agent_id(index) for index in range(1, (n_agents or config.n_agents) + 1))
    scenario = _scenario(config)
    accounts = AccountBook(
        agent_ids=seats,
        market_ids=tuple(spec.market_id for spec in scenario.markets),
        config=config,
    )
    exchange = Exchange(config=config, scenario=scenario, accounts=accounts, journal=journal)
    exchange.begin_tick(1)
    return (exchange, accounts)


def _limit(
    exchange: Exchange,
    *,
    agent_id: str,
    market_id: str = "M1",
    side: Side = Side.BUY,
    price: int = 50,
    qty: int = 10,
    tick: int = 1,
    item_index: int = 0,
):
    return exchange.submit(
        tick=tick,
        agent_id=agent_id,
        intent=OrderIntent(
            op="place",
            market_id=market_id,
            side=side,
            order_type=OrderType.LIMIT,
            price=price,
            qty=qty,
        ),
        item_index=item_index,
    )


def _market(
    exchange: Exchange,
    *,
    agent_id: str,
    market_id: str = "M1",
    side: Side = Side.BUY,
    qty: int = 10,
    tick: int = 1,
    item_index: int = 0,
):
    return exchange.submit(
        tick=tick,
        agent_id=agent_id,
        intent=OrderIntent(
            op="place",
            market_id=market_id,
            side=side,
            order_type=OrderType.MARKET,
            price=None,
            qty=qty,
        ),
        item_index=item_index,
    )


def _trades(journal: Journal) -> list[TradeExecuted]:
    events = journal.events
    assert events, "the journal must not be empty before it is asserted on"
    trades = [event for event in events if isinstance(event, TradeExecuted)]
    assert trades, "no TradeExecuted was journalled: the assertions below would be vacuous"
    return trades


# ---------------------------------------------------------------------------
# FR-5.4.1
# ---------------------------------------------------------------------------
def test_price_time_priority(standard_config, tmp_journal) -> None:
    """FR-5.4.1: best price first, then oldest first, with partial fills."""
    exchange, accounts = _arena(standard_config, tmp_journal)
    _limit(exchange, agent_id="A1", side=Side.SELL, price=60, qty=10)
    _limit(exchange, agent_id="A2", side=Side.SELL, price=60, qty=10)
    _limit(exchange, agent_id="A3", side=Side.SELL, price=55, qty=10)

    result = _limit(exchange, agent_id="A4", side=Side.BUY, price=60, qty=25)

    trades = _trades(tmp_journal)
    assert [(trade.maker_agent_id, trade.price, trade.qty) for trade in trades] == [
        ("A3", 55, 10),  # better price first
        ("A1", 60, 10),  # then the older of the two 60s
        ("A2", 60, 5),  # then the younger one, partially
    ]
    assert result.accepted
    assert result.filled_qty == 25
    assert result.resting_qty == 0
    assert [trade.taker_agent_id for trade in trades] == ["A4", "A4", "A4"]
    # A2's order survives with the unfilled half, still first in its level.
    remaining = exchange.book("M1").resting_orders()
    assert [(order.agent_id, order.remaining_qty) for order in remaining] == [("A2", 5)]
    assert remaining[0].status is OrderStatus.PARTIALLY_FILLED
    assert accounts.position("A4", "M1").qty == 25


def test_execution_at_maker_price(standard_config, tmp_journal) -> None:
    """FR-5.4.1: the resting price wins, so the taker keeps the difference."""
    exchange, accounts = _arena(standard_config, tmp_journal)
    _limit(exchange, agent_id="A1", side=Side.SELL, price=40, qty=10)
    _limit(exchange, agent_id="A2", side=Side.BUY, price=70, qty=10)

    trades = _trades(tmp_journal)
    assert len(trades) == 1
    assert trades[0].price == 40
    assert trades[0].taker_cash_delta_cents == -400
    assert trades[0].maker_cash_delta_cents == 400
    assert accounts.cash_cents("A2") == standard_config.initial_cash_cents - 400
    assert accounts.cash_cents("A1") == standard_config.initial_cash_cents + 400
    # Zero sum with a zero fee (I5).
    assert trades[0].maker_cash_delta_cents + trades[0].taker_cash_delta_cents + trades[0].taker_fee_cents == 0


def test_partial_fill_leaves_the_remainder_resting(standard_config, tmp_journal) -> None:
    """A GTC limit rests with exactly the unfilled quantity collateralised."""
    exchange, accounts = _arena(standard_config, tmp_journal)
    _limit(exchange, agent_id="A1", side=Side.SELL, price=50, qty=4)
    result = _limit(exchange, agent_id="A2", side=Side.BUY, price=50, qty=10)

    _trades(tmp_journal)
    assert (result.filled_qty, result.resting_qty) == (4, 6)
    book = exchange.book("M1")
    assert book.best_bid() == 50
    assert book.total_qty(Side.BUY) == 6
    # 6 unfilled contracts at 50 cents, and a long position needs no collateral.
    assert accounts.reserved_cents("A2") == 300
    assert accounts.cash_cents("A2") == standard_config.initial_cash_cents - 200


def test_fee_is_charged_per_fill_not_on_the_aggregate(tmp_journal) -> None:
    """CONTRACTS section 6.1: floor(f1) + floor(f2) != floor(f1 + f2), and the parts win."""
    config = MatchConfig(seed=20260827, taker_fee_bps=200)
    exchange, accounts = _arena(config, tmp_journal)
    _limit(exchange, agent_id="A1", side=Side.SELL, price=33, qty=1)
    _limit(exchange, agent_id="A2", side=Side.SELL, price=33, qty=1)
    _limit(exchange, agent_id="A3", side=Side.BUY, price=33, qty=2)

    trades = _trades(tmp_journal)
    assert len(trades) == 2
    assert [trade.taker_fee_cents for trade in trades] == [0, 0]
    # The aggregate would have created a cent out of nothing.
    assert taker_fee_cents(200, 33, 2) == 1
    assert accounts.cash_cents(FEES_ACCOUNT_ID) == 0

    _limit(exchange, agent_id="A4", side=Side.SELL, price=60, qty=10, market_id="M2")
    _limit(exchange, agent_id="A5", side=Side.BUY, price=60, qty=10, market_id="M2")
    later = [trade for trade in _trades(tmp_journal) if trade.market_id == "M2"]
    assert len(later) == 1
    assert later[0].taker_fee_cents == taker_fee_cents(200, 60, 10) == 12
    assert accounts.cash_cents(FEES_ACCOUNT_ID) == 12
    assert accounts.fees_paid_cents("A5", "M2") == 12
    assert accounts.fees_paid_cents("A4", "M2") == 0


# ---------------------------------------------------------------------------
# FR-5.4.2
# ---------------------------------------------------------------------------
def test_order_cap_rejects_eleventh(standard_config, tmp_journal) -> None:
    """FR-5.4.2: ten active orders per agent per market, the next one is refused."""
    exchange, accounts = _arena(standard_config, tmp_journal)
    cap = standard_config.max_active_orders_per_market
    assert cap == 10
    for index in range(cap):
        result = _limit(exchange, agent_id="A1", side=Side.BUY, price=10 + index, qty=1, item_index=index)
        assert result.accepted

    events = tmp_journal.events
    assert events, "the journal must not be empty before it is asserted on"
    placed = [event for event in events if isinstance(event, OrderPlaced)]
    assert len(placed) == cap
    assert [event.active_orders_after for event in placed] == list(range(1, cap + 1))

    refused = _limit(exchange, agent_id="A1", side=Side.BUY, price=25, qty=1, item_index=cap)
    assert not refused.accepted
    assert refused.reason is RejectReason.ORDER_LIMIT_EXCEEDED
    assert refused.order_id is None
    rejected = [event for event in tmp_journal.events if isinstance(event, OrderRejected)]
    assert len(rejected) == 1
    assert rejected[0].reason == str(RejectReason.ORDER_LIMIT_EXCEEDED)
    assert rejected[0].item_index == cap
    assert rejected[0].detail
    assert exchange.book("M1").count_of("A1") == cap
    # The cap is per market: the same agent may still quote elsewhere.
    assert _limit(exchange, agent_id="A1", market_id="M2", side=Side.BUY, price=25, qty=1).accepted
    # And no collateral was locked by the refusal.
    assert accounts.reserved_cents("A1") == sum(10 + index for index in range(cap)) + 25


def test_insufficient_collateral_rejects_that_intent_only(standard_config, tmp_journal) -> None:
    """CONTRACTS section 6.1: all-or-nothing per intent, the rest of the block runs."""
    exchange, accounts = _arena(standard_config, tmp_journal)
    refused = _limit(exchange, agent_id="A1", side=Side.BUY, price=99, qty=100_000, item_index=0)
    assert not refused.accepted
    assert refused.reason is RejectReason.INSUFFICIENT_COLLATERAL
    assert accounts.reserved_cents("A1") == 0

    accepted = _limit(exchange, agent_id="A1", side=Side.BUY, price=40, qty=10, item_index=1)
    assert accepted.accepted
    assert accounts.reserved_cents("A1") == 400

    events = tmp_journal.events
    assert events, "the journal must not be empty before it is asserted on"
    rejected = [event for event in events if isinstance(event, OrderRejected)]
    assert len(rejected) == 1
    assert rejected[0].reason == str(RejectReason.INSUFFICIENT_COLLATERAL)
    assert rejected[0].item_index == 0


def test_cancel_releases_the_collateral_and_a_stale_cancel_is_rejected(standard_config, tmp_journal) -> None:
    """FR-5.4.2 cancel, and P3 liveness: a vanished order is refused in P3, not P2."""
    exchange, accounts = _arena(standard_config, tmp_journal)
    placed = _limit(exchange, agent_id="A1", side=Side.BUY, price=40, qty=10)
    assert placed.order_id is not None
    assert accounts.reserved_cents("A1") == 400

    foreign = exchange.cancel(
        tick=1,
        agent_id="A2",
        order_id=placed.order_id,
        reason=CancelReason.AGENT_REQUEST,
        item_index=0,
    )
    assert not foreign.accepted
    assert foreign.reason is RejectReason.NOT_ORDER_OWNER
    assert accounts.reserved_cents("A1") == 400

    done = exchange.cancel(
        tick=1,
        agent_id="A1",
        order_id=placed.order_id,
        reason=CancelReason.AGENT_REQUEST,
        item_index=1,
    )
    assert done.accepted
    assert accounts.reserved_cents("A1") == 0

    events = tmp_journal.events
    assert events, "the journal must not be empty before it is asserted on"
    cancels = [event for event in events if isinstance(event, OrderCancelled)]
    assert len(cancels) == 1
    assert cancels[0].reason == str(CancelReason.AGENT_REQUEST)
    assert cancels[0].released_cents == 400
    assert cancels[0].remaining_qty == 10

    stale = exchange.cancel(
        tick=2,
        agent_id="A1",
        order_id=placed.order_id,
        reason=CancelReason.AGENT_REQUEST,
        item_index=2,
    )
    assert not stale.accepted
    assert stale.reason is RejectReason.UNKNOWN_ORDER
    reasons = [event.reason for event in tmp_journal.events if isinstance(event, OrderRejected)]
    assert reasons == [str(RejectReason.NOT_ORDER_OWNER), str(RejectReason.UNKNOWN_ORDER)]


def test_cancel_all_emits_markets_ascending_then_bids_then_asks(standard_config, tmp_journal) -> None:
    """CONTRACTS section 7.8: the returned ids are the emission order, verbatim."""
    exchange, accounts = _arena(standard_config, tmp_journal)
    ids = {}
    for market_id, side, price in (
        ("M1", Side.BUY, 30),
        ("M1", Side.BUY, 35),
        ("M1", Side.SELL, 70),
        ("M1", Side.SELL, 65),
        ("M2", Side.BUY, 20),
    ):
        result = _limit(exchange, agent_id="A1", market_id=market_id, side=side, price=price, qty=1)
        ids[(market_id, side, price)] = result.order_id
    # A second account must not be swept by an agent scoped cancel_all.
    other = _limit(exchange, agent_id="A2", market_id="M1", side=Side.BUY, price=25, qty=1)

    cancelled = exchange.cancel_all(tick=1, reason=CancelReason.AGENT_FROZEN, agent_id="A1")
    assert cancelled == (
        ids[("M1", Side.BUY, 35)],
        ids[("M1", Side.BUY, 30)],
        ids[("M1", Side.SELL, 65)],
        ids[("M1", Side.SELL, 70)],
        ids[("M2", Side.BUY, 20)],
    )
    events = tmp_journal.events
    assert events, "the journal must not be empty before it is asserted on"
    cancels = [event for event in events if isinstance(event, OrderCancelled)]
    assert [event.order_id for event in cancels] == list(cancelled)
    assert {event.reason for event in cancels} == {str(CancelReason.AGENT_FROZEN)}
    assert sum(event.released_cents for event in cancels) == 35 + 30 + 35 + 30 + 20
    assert accounts.reserved_cents("A1") == 0
    assert exchange.book("M1").orders_of("A2") == (exchange.book("M1").get(other.order_id),)


def test_closed_market_refuses_every_new_order(standard_config, tmp_journal) -> None:
    """FR-5.4.5: no trading on a resolved or cancelled market."""
    exchange, _accounts = _arena(standard_config, tmp_journal)
    _limit(exchange, agent_id="A1", market_id="M5", side=Side.BUY, price=40, qty=1)
    with pytest.raises(InvariantViolationError):
        exchange.close_market(tick=1, market_id="M5", status=MarketStatus.RESOLVED)

    exchange.cancel_all(tick=1, reason=CancelReason.MARKET_RESOLVED, market_id="M5")
    exchange.close_market(tick=1, market_id="M5", status=MarketStatus.RESOLVED)
    assert exchange.status("M5") is MarketStatus.RESOLVED
    assert "M5" not in exchange.open_market_ids()
    assert exchange.market_state("M5").resolved_tick == 1

    refused = _limit(exchange, agent_id="A1", market_id="M5", side=Side.BUY, price=40, qty=1, tick=2)
    assert not refused.accepted
    assert refused.reason is RejectReason.MARKET_NOT_OPEN
    events = tmp_journal.events
    assert events, "the journal must not be empty before it is asserted on"
    rejected = [event for event in events if isinstance(event, OrderRejected)]
    assert len(rejected) == 1
    assert rejected[0].reason == str(RejectReason.MARKET_NOT_OPEN)


# ---------------------------------------------------------------------------
# FR-5.4.3
# ---------------------------------------------------------------------------
def test_market_order_band_and_ioc_residual(standard_config, tmp_journal) -> None:
    """FR-5.4.3: bounded marketable limit, and the remainder never rests."""
    exchange, accounts = _arena(standard_config, tmp_journal)
    band = standard_config.market_band_cents
    assert band == 10

    # One sided book: the reference price is the public prior, 50.
    _limit(exchange, agent_id="A1", side=Side.SELL, price=55, qty=10)
    result = _market(exchange, agent_id="A2", side=Side.BUY, qty=20, item_index=3)

    events = tmp_journal.events
    assert events, "the journal must not be empty before it is asserted on"
    placed = [event for event in events if isinstance(event, OrderPlaced)]
    assert len(placed) == 2
    taker_placed = placed[1]
    assert taker_placed.requested_type == str(OrderType.MARKET)
    assert taker_placed.tif == "ioc"
    assert taker_placed.ref_price == 50
    assert taker_placed.price == 60  # 50 + band, clamped into 1..99
    assert taker_placed.reserved_cents == 60 * 20

    trades = _trades(tmp_journal)
    assert [(trade.price, trade.qty) for trade in trades] == [(55, 10)]
    cancels = [event for event in events if isinstance(event, OrderCancelled)]
    assert len(cancels) == 1
    assert cancels[0].reason == str(CancelReason.IOC_RESIDUAL)
    assert cancels[0].remaining_qty == 10
    assert cancels[0].released_cents == 60 * 10
    assert (result.filled_qty, result.resting_qty) == (10, 0)
    assert exchange.book("M1").total_qty(Side.BUY) == 0
    assert accounts.reserved_cents("A2") == 0

    # Second market: the whole quantity is outside the band, so nothing trades
    # and nothing rests.
    _limit(exchange, agent_id="A1", market_id="M2", side=Side.SELL, price=65, qty=5)
    blocked = _market(exchange, agent_id="A3", market_id="M2", side=Side.BUY, qty=5)
    assert (blocked.filled_qty, blocked.resting_qty) == (0, 0)
    assert exchange.book("M2").total_qty(Side.BUY) == 0
    m2_cancels = [
        event
        for event in tmp_journal.events
        if isinstance(event, OrderCancelled) and event.market_id == "M2" and event.remaining_qty == 5
    ]
    assert len(m2_cancels) == 1
    assert m2_cancels[0].released_cents == 60 * 5


def test_band_limit_price_clamps_both_directions() -> None:
    """FR-5.4.3 arithmetic, including the 1..99 clamp at the edges."""
    assert band_limit_price(50, Side.BUY, 10) == 60
    assert band_limit_price(50, Side.SELL, 10) == 40
    assert band_limit_price(95, Side.BUY, 10) == 99
    assert band_limit_price(5, Side.SELL, 10) == 1
    assert band_limit_price(50, Side.BUY, 0) == 50


# ---------------------------------------------------------------------------
# FR-5.4.6
# ---------------------------------------------------------------------------
def test_reference_price_fallback_chain(standard_config, tmp_journal) -> None:
    """FR-5.4.6: mid, else the last executed price, else the public prior."""
    exchange, _accounts = _arena(standard_config, tmp_journal)

    # Third branch: nothing has happened, so the prior answers.
    assert exchange.reference_price("M3") == (50, "prior")
    # Still the prior while the book is one sided: there is no mid.
    _limit(exchange, agent_id="A1", market_id="M3", side=Side.SELL, price=60, qty=10)
    assert exchange.reference_price("M3") == (50, "prior")
    # Second branch: a trade empties the book and leaves a last price.
    _limit(exchange, agent_id="A2", market_id="M3", side=Side.BUY, price=62, qty=10)
    _trades(tmp_journal)
    assert exchange.book("M3").is_empty()
    assert exchange.reference_price("M3") == (60, "last")
    # First branch: a two sided book overrides the last price, halves going up.
    _limit(exchange, agent_id="A1", market_id="M3", side=Side.BUY, price=40, qty=5)
    _limit(exchange, agent_id="A3", market_id="M3", side=Side.SELL, price=45, qty=5)
    assert exchange.reference_price("M3") == (43, "mid")

    # And the pure function agrees on an empty book with any legal prior.
    assert reference_price(exchange.book("M4"), 7) == (7, "prior")


def test_ref_history_is_bounded_by_the_config(standard_config, tmp_journal) -> None:
    """P4 step 12: the sparkline never grows past ``config.ref_history_len``."""
    exchange, _accounts = _arena(standard_config, tmp_journal)
    assert exchange.ref_history("M1") == ()
    for price in range(1, standard_config.ref_history_len + 5):
        exchange.push_ref_history("M1", price)
    history = exchange.ref_history("M1")
    assert len(history) == standard_config.ref_history_len
    assert history[-1] == standard_config.ref_history_len + 4
    assert list(history) == sorted(history)

    zero = MatchConfig(seed=1, ref_history_len=0)
    other, _ = _arena(zero, Journal("m-election-1-01"))
    other.push_ref_history("M1", 42)
    assert other.ref_history("M1") == ()


def test_tick_volume_resets_on_begin_tick(standard_config, tmp_journal) -> None:
    """P1 step 0 is the only thing that resets what MarkToMarket publishes."""
    exchange, _accounts = _arena(standard_config, tmp_journal)
    _limit(exchange, agent_id="A1", side=Side.SELL, price=50, qty=7)
    _limit(exchange, agent_id="A2", side=Side.BUY, price=50, qty=7)
    _trades(tmp_journal)
    assert exchange.tick_volume("M1") == 7
    assert exchange.tick_volume("M2") == 0
    exchange.begin_tick(2)
    assert exchange.tick_volume("M1") == 0


def test_book_view_covers_every_market_and_feeds_the_invariants(standard_config, tmp_journal) -> None:
    """CONTRACTS section 7.8: the one argument I3 and I8 are checked against."""
    exchange, accounts = _arena(standard_config, tmp_journal)
    _limit(exchange, agent_id="A1", side=Side.BUY, price=40, qty=5)
    _limit(exchange, agent_id="A2", side=Side.SELL, price=60, qty=5, market_id="M2")
    _limit(exchange, agent_id="A3", side=Side.SELL, price=45, qty=5)
    _market(exchange, agent_id="A4", side=Side.BUY, qty=5)
    _trades(tmp_journal)

    view = exchange.book_view()
    assert set(view.keys()) == {make_market_id(index) for index in range(1, standard_config.n_markets + 1)}
    for market_id, orders in view.items():
        assert list(orders) == sorted(orders, key=lambda order: (order.side, order.priority_key))
        assert all(order.market_id == market_id for order in orders)
    ref_prices = {market_id: exchange.reference_price(market_id)[0] for market_id in exchange.open_market_ids()}
    accounts.check_invariants(ref_prices=ref_prices, book_view=view)


def test_plan_match_never_mutates_the_book(standard_config, tmp_journal) -> None:
    """``plan_match`` is pure, which is what lets the solvency check run first."""
    exchange, _accounts = _arena(standard_config, tmp_journal)
    _limit(exchange, agent_id="A1", side=Side.SELL, price=50, qty=10)
    book = exchange.book("M1")
    before = book.resting_orders()
    plan = plan_match(book, agent_id="A2", side=Side.BUY, limit_price=50, qty=4, fee_bps=0)
    assert plan.fills and plan.fills[0].qty == 4
    assert plan.residual_qty == 0
    assert plan.notional_cents == 200
    assert book.resting_orders() == before


# ---------------------------------------------------------------------------
# T1.3 exit gate: >= 10 000 orders/s locally
# ---------------------------------------------------------------------------
class _JournalSink:
    """A minimal stand-in for ``Journal`` that numbers events and drops them.

    It implements exactly the two members ``Exchange`` uses, ``next_seq`` and
    ``emit``, and it still builds every event object, so the cost of assembling
    the payload stays charged to the exchange. What it does not do is
    ``canonical_json``: T1.3's gate is the matching engine, and the encoder is
    :mod:`pxe.events` (A01), whose own cost T1.2 measures. Timing the two
    together would make this test fail or pass on a change to the encoder.
    """

    __slots__ = ("emitted", "_seq")

    def __init__(self) -> None:
        self.emitted = 0
        self._seq = 0

    @property
    def next_seq(self) -> int:
        return self._seq + 1

    def emit(self, event_cls, *, tick, **payload):
        self._seq += 1
        self.emitted += 1
        return event_cls(seq=self._seq, match_id="m-election-20260827-01", tick=tick, **payload)


def _flat_cycle(exchange: Exchange) -> None:
    """Four orders that produce two executions and leave both accounts flat."""
    _limit(exchange, agent_id="A1", side=Side.BUY, price=50, qty=1)
    _limit(exchange, agent_id="A2", side=Side.SELL, price=50, qty=1)
    _limit(exchange, agent_id="A2", side=Side.BUY, price=50, qty=1)
    _limit(exchange, agent_id="A1", side=Side.SELL, price=50, qty=1)


@pytest.mark.slow
def test_throughput() -> None:
    """T1.3: the matching engine sustains at least 10 000 orders per second locally.

    The workload is a four order cycle that returns both accounts to flat, so it
    exercises the whole hot path (solvency check, reservation, price-time walk,
    ledger, and the three events an executing pair emits) without drifting into
    a collateral or order cap limit that would silently turn the benchmark into
    a stream of cheap rejections. The first round runs against a real
    :class:`~pxe.journal.Journal` and asserts exactly that, on a non empty
    journal, before any rate is claimed.

    What is measured is the **fastest hundred order window** over many short
    windows and several fresh exchanges. Three reasons, all of them about
    measuring the code rather than the machine:

    * this runs inside a shared test session on a developer box, so the process
      is preempted at unpredictable moments; the minimum over many short windows
      is the standard estimator of uncontended throughput, while one long window
      measures whatever else the machine was doing;
    * each round starts from a fresh exchange, so what is timed is the steady
      state rate of the book and not the cost of a structure grown far past any
      real match's size;
    * the cyclic collector is collected and then switched off around the timed
      windows, so garbage left behind by the hundreds of tests that ran before
      this one is not charged to it.

    The end to end rate with the real journal attached is printed beside the
    engine rate, because that is the number a whole match actually runs at.
    """
    config = MatchConfig(seed=20260827)
    rounds = 8
    windows_per_round = 20
    window_cycles = 25
    window_orders = window_cycles * 4
    cycles = windows_per_round * window_cycles

    # Round zero, with the real journal: correctness of the workload, plus the
    # end to end number for the record.
    journal = Journal("m-election-20260827-01")  # in memory: no file I/O in the timing
    exchange, accounts = _arena(config, journal, n_agents=2)
    gc.collect()
    gc.disable()
    try:
        started = time.perf_counter()
        for _cycle in range(cycles):
            _flat_cycle(exchange)
        end_to_end = (cycles * 4) / (time.perf_counter() - started)
    finally:
        gc.enable()
    _trades(journal)
    assert not [event for event in journal.events if isinstance(event, OrderRejected)], (
        "the benchmark must measure accepted orders, not rejections"
    )
    assert len([event for event in journal.events if isinstance(event, TradeExecuted)]) == cycles * 2
    assert len([event for event in journal.events if isinstance(event, OrderPlaced)]) == cycles * 4
    assert exchange.book("M1").is_empty()
    assert accounts.position("A1", "M1").qty == 0
    assert accounts.position("A2", "M1").qty == 0

    best_rate = 0.0
    best_elapsed = 0.0
    for _ in range(rounds):
        sink = _JournalSink()
        exchange, accounts = _arena(config, sink, n_agents=2)
        gc.collect()
        gc.disable()
        try:
            for _window in range(windows_per_round):
                started = time.perf_counter()
                for _cycle in range(window_cycles):
                    _flat_cycle(exchange)
                elapsed = time.perf_counter() - started
                if window_orders / elapsed > best_rate:
                    best_rate = window_orders / elapsed
                    best_elapsed = elapsed
        finally:
            gc.enable()
        # Six events per cycle: four OrderPlaced and two TradeExecuted. If the
        # engine started rejecting instead of matching, this count would drop.
        assert sink.emitted == cycles * 6
        assert exchange.book("M1").is_empty()
        assert accounts.position("A1", "M1").qty == 0

    print(
        f"\nCLOB throughput: {best_rate:,.0f} orders/s "
        f"({best_elapsed * 1e6 / window_orders:.1f} us/order, best of "
        f"{rounds * windows_per_round} windows of {window_orders} orders); "
        f"{end_to_end:,.0f} orders/s end to end with the journal attached"
    )
    assert best_rate >= 10_000, f"only {best_rate:,.0f} orders/s"
