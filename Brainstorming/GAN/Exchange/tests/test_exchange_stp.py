"""A05: self-trade prevention (FR-5.4.4, CONTRACTS section 6.1, decisions 20 and 21).

Three claims, and they are independent:

1. an incoming order that would cross its own resting order **cancels the
   resting one** and keeps walking, so the self trade never happens and the
   incoming order is not stopped;
2. the collateral of the cancelled resting order is released **exactly once**,
   by the ``OrderCancelled``, and ``STPCancelled`` carries no money at all;
3. that release happens **after** the FR-5.5.1 solvency check, so it is never
   available to the order that caused it.

Every test that looks at the journal asserts it is non empty and holds at least
one event of the type under test before claiming anything (section 10's
anti-vacuous rule).
"""

from __future__ import annotations

from pxe.events import OrderCancelled, OrderPlaced, OrderRejected, STPCancelled, TradeExecuted
from pxe.exchange.accounts import AccountBook
from pxe.exchange.exchange import Exchange
from pxe.journal import Journal
from pxe.types import (
    CancelReason,
    MarketSpec,
    MatchConfig,
    OrderIntent,
    OrderType,
    RejectReason,
    ScenarioSpec,
    Side,
    make_agent_id,
    make_market_id,
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


def _arena(config: MatchConfig, journal: Journal) -> tuple[Exchange, AccountBook]:
    scenario = _scenario(config)
    accounts = AccountBook(
        agent_ids=tuple(make_agent_id(index) for index in range(1, config.n_agents + 1)),
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
    side: Side,
    price: int,
    qty: int,
    market_id: str = "M1",
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


def _stp_events(journal: Journal) -> list[STPCancelled]:
    events = journal.events
    assert events, "the journal must not be empty before it is asserted on"
    stp = [event for event in events if isinstance(event, STPCancelled)]
    assert stp, "no STPCancelled was journalled: the assertions below would be vacuous"
    return stp


# ---------------------------------------------------------------------------
# FR-5.4.4
# ---------------------------------------------------------------------------
def test_self_cross_cancels_resting(standard_config, tmp_journal) -> None:
    """FR-5.4.4: the resting order goes, the self trade never happens."""
    exchange, accounts = _arena(standard_config, tmp_journal)
    resting = _limit(exchange, agent_id="A1", side=Side.SELL, price=55, qty=10)
    assert resting.order_id is not None
    assert accounts.reserved_cents("A1") == (100 - 55) * 10

    incoming = _limit(exchange, agent_id="A1", side=Side.BUY, price=60, qty=10, item_index=1)

    stp = _stp_events(tmp_journal)
    assert len(stp) == 1
    assert stp[0].agent_id == "A1"
    assert stp[0].market_id == "M1"
    assert stp[0].resting_order_id == resting.order_id
    assert stp[0].incoming_order_id == incoming.order_id
    assert stp[0].cancelled_qty == 10

    assert not [event for event in tmp_journal.events if isinstance(event, TradeExecuted)]
    assert exchange.book("M1").get(resting.order_id) is None
    assert exchange.book("M1").best_bid() == 60
    assert exchange.book("M1").best_ask() is None
    # The incoming order was never stopped: its whole size rests.
    assert (incoming.filled_qty, incoming.resting_qty) == (0, 10)
    assert accounts.reserved_cents("A1") == 60 * 10


def test_stp_does_not_stop_the_incoming_order(standard_config, tmp_journal) -> None:
    """The walk skips the own order and reaches the next maker by priority."""
    exchange, accounts = _arena(standard_config, tmp_journal)
    own = _limit(exchange, agent_id="A1", side=Side.SELL, price=50, qty=6)
    _limit(exchange, agent_id="A2", side=Side.SELL, price=52, qty=6)

    result = _limit(exchange, agent_id="A1", side=Side.BUY, price=55, qty=6, item_index=1)

    stp = _stp_events(tmp_journal)
    assert len(stp) == 1
    assert stp[0].resting_order_id == own.order_id
    trades = [event for event in tmp_journal.events if isinstance(event, TradeExecuted)]
    assert len(trades) == 1
    # The own order sat at the better price and was skipped, not matched.
    assert (trades[0].maker_agent_id, trades[0].price, trades[0].qty) == ("A2", 52, 6)
    assert (result.filled_qty, result.resting_qty) == (6, 0)
    assert accounts.position("A1", "M1").qty == 6
    assert accounts.position("A2", "M1").qty == -6


def test_stp_never_touches_another_agents_order(standard_config, tmp_journal) -> None:
    """Two different agents crossing is a trade, not an STP cancellation."""
    exchange, _accounts = _arena(standard_config, tmp_journal)
    _limit(exchange, agent_id="A1", side=Side.SELL, price=50, qty=5)
    _limit(exchange, agent_id="A2", side=Side.BUY, price=50, qty=5)

    events = tmp_journal.events
    assert events, "the journal must not be empty before it is asserted on"
    trades = [event for event in events if isinstance(event, TradeExecuted)]
    assert len(trades) == 1
    assert not [event for event in events if isinstance(event, STPCancelled)]
    assert not [event for event in events if isinstance(event, OrderCancelled)]


# ---------------------------------------------------------------------------
# Decision 20: the money is on the OrderCancelled and nowhere else
# ---------------------------------------------------------------------------
def test_stp_releases_collateral_exactly_once(standard_config, tmp_journal) -> None:
    """One release per cancelled order, reported by one event, joinable by seq."""
    exchange, accounts = _arena(standard_config, tmp_journal)
    near = _limit(exchange, agent_id="A1", side=Side.SELL, price=55, qty=5)
    far = _limit(exchange, agent_id="A1", side=Side.SELL, price=58, qty=5)
    _limit(exchange, agent_id="A2", side=Side.SELL, price=57, qty=5)
    assert accounts.reserved_cents("A1") == (100 - 55) * 5 + (100 - 58) * 5 == 225 + 210

    incoming = _limit(exchange, agent_id="A1", side=Side.BUY, price=60, qty=15, item_index=3)

    events = tmp_journal.events
    assert events, "the journal must not be empty before it is asserted on"
    stp = _stp_events(tmp_journal)
    stp_cancels = [event for event in events if isinstance(event, OrderCancelled) and event.reason == "stp"]

    # Two own orders were crossed, in priority order: 55 before 58.
    assert [event.order_id for event in stp_cancels] == [near.order_id, far.order_id]
    assert [event.released_cents for event in stp_cancels] == [225, 210]
    assert [event.remaining_qty for event in stp_cancels] == [5, 5]
    assert [event.resting_order_id for event in stp] == [near.order_id, far.order_id]

    # Decision 20: the pair is OrderCancelled then STPCancelled, and only the
    # first carries money, so a projection summing releases cannot double count.
    for cancel_event, stp_event in zip(stp_cancels, stp, strict=True):
        assert stp_event.seq == cancel_event.seq + 1
        assert stp_event.cancel_seq == cancel_event.seq
        assert not hasattr(stp_event, "released_cents")
        assert stp_event.cancelled_qty == cancel_event.remaining_qty

    # The walk continued past both of them and hit the only foreign maker.
    trades = [event for event in events if isinstance(event, TradeExecuted)]
    assert len(trades) == 1
    assert (trades[0].maker_agent_id, trades[0].price, trades[0].qty) == ("A2", 57, 5)
    assert (incoming.filled_qty, incoming.resting_qty) == (5, 10)

    # Exactly once: the ledger holds only the residual's collateral, the long
    # position needs none, and the book agrees with the ledger (I3, I8).
    assert accounts.reserved_cents("A1") == 60 * 10
    assert accounts.total_cash_cents() == accounts.initial_total_cash_cents()
    ref_prices = {market_id: exchange.reference_price(market_id)[0] for market_id in exchange.open_market_ids()}
    accounts.check_invariants(ref_prices=ref_prices, book_view=exchange.book_view())

    # And a second cancellation of an already STP cancelled order is refused
    # rather than releasing the same collateral twice.
    again = exchange.cancel(
        tick=1,
        agent_id="A1",
        order_id=near.order_id,
        reason=CancelReason.AGENT_REQUEST,
        item_index=4,
    )
    assert not again.accepted
    assert again.reason is RejectReason.UNKNOWN_ORDER
    assert accounts.reserved_cents("A1") == 60 * 10


def test_stp_and_ioc_residual_are_two_separate_cancellations(standard_config, tmp_journal) -> None:
    """A market order can both STP and leave an unexecutable remainder (FR-5.4.3)."""
    exchange, accounts = _arena(standard_config, tmp_journal)
    own = _limit(exchange, agent_id="A1", side=Side.SELL, price=52, qty=4)

    result = exchange.submit(
        tick=1,
        agent_id="A1",
        intent=OrderIntent(
            op="place",
            market_id="M1",
            side=Side.BUY,
            order_type=OrderType.MARKET,
            price=None,
            qty=4,
        ),
        item_index=1,
    )

    stp = _stp_events(tmp_journal)
    assert len(stp) == 1
    assert stp[0].resting_order_id == own.order_id
    cancels = [event for event in tmp_journal.events if isinstance(event, OrderCancelled)]
    assert [event.reason for event in cancels] == [str(CancelReason.STP), str(CancelReason.IOC_RESIDUAL)]
    assert cancels[0].released_cents == (100 - 52) * 4
    # The band converted price is 50 + 10 = 60, so the residual released 60 * 4.
    assert cancels[1].released_cents == 60 * 4
    assert cancels[1].order_id == result.order_id
    assert (result.filled_qty, result.resting_qty) == (0, 0)
    assert exchange.book("M1").is_empty()
    assert accounts.reserved_cents("A1") == 0


# ---------------------------------------------------------------------------
# Decision 21 and CONTRACTS section 6.1: the ordering against the solvency check
# ---------------------------------------------------------------------------
def test_stp_release_is_not_available_to_the_incoming_order(tmp_journal) -> None:
    """CONTRACTS section 6.1, verbatim: the check runs first, so the STP cash is not there.

    The contract's own example. An agent with 10 000 cents rests a sell of 100
    at 60, reserving ``40 * 100 = 4000`` and leaving 6 000 free. It then sends a
    buy of 100 at 61, needing ``61 * 100 = 6100``. That is refused, even though
    the STP cancellation the same submission would trigger frees 4 000 first.
    The other reading (scan, cancel, then check) accepts the order and produces
    a different journal from the same seed, which is why this test exists.
    """
    config = MatchConfig(seed=20260827, initial_cash_cents=10_000, mm_initial_cash_cents=10_000)
    exchange, accounts = _arena(config, tmp_journal)
    resting = _limit(exchange, agent_id="A1", side=Side.SELL, price=60, qty=100)
    assert resting.accepted
    assert accounts.reserved_cents("A1") == 4_000
    assert accounts.free_cash_cents("A1") == 6_000
    # The cash is there; only the *free* cash is not. That is the whole point.
    assert accounts.cash_cents("A1") == 10_000
    assert accounts.cash_cents("A1") > 61 * 100

    refused = _limit(exchange, agent_id="A1", side=Side.BUY, price=61, qty=100, item_index=1)

    events = tmp_journal.events
    assert events, "the journal must not be empty before it is asserted on"
    rejected = [event for event in events if isinstance(event, OrderRejected)]
    assert len(rejected) == 1
    assert rejected[0].reason == str(RejectReason.INSUFFICIENT_COLLATERAL)
    assert rejected[0].price == 61
    assert rejected[0].qty == 100
    assert not refused.accepted
    assert refused.reason is RejectReason.INSUFFICIENT_COLLATERAL

    # Nothing was cancelled, nothing was released, nothing rests on the buy side.
    assert not [event for event in events if isinstance(event, STPCancelled)]
    assert not [event for event in events if isinstance(event, OrderCancelled)]
    assert len([event for event in events if isinstance(event, OrderPlaced)]) == 1
    assert exchange.book("M1").get(resting.order_id) is not None
    assert accounts.reserved_cents("A1") == 4_000

    # It really was a collateral question: freeing the same 4 000 by hand makes
    # the identical order acceptable.
    exchange.cancel(
        tick=1,
        agent_id="A1",
        order_id=resting.order_id,
        reason=CancelReason.AGENT_REQUEST,
        item_index=2,
    )
    assert accounts.free_cash_cents("A1") == 10_000
    accepted = _limit(exchange, agent_id="A1", side=Side.BUY, price=61, qty=100, item_index=3)
    assert accepted.accepted
    assert accounts.reserved_cents("A1") == 6_100
