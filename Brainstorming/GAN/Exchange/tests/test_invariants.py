"""Property tests for the closed system invariants I1..I12 (A06, FR-5.5.3).

Two halves, and both are required by CONTRACTS section 6.3:

* a hypothesis strategy generating random but **valid** order flows against the
  ledger, asserting I1..I12 after every single operation. Every generated
  example ends with a deterministic closing sequence that guarantees at least
  one trade, one cancellation and one settlement really happened, so no example
  can claim the invariants held over an empty flow (section 10's anti-vacuous
  rule, which has teeth here);
* a control half that **deliberately breaks** the ledger, one invariant at a
  time, and asserts the breach is caught. A checker that never fails is
  indistinguishable from no checker at all, and that is the failure mode this
  file exists to make impossible.

``_Venue`` is the exchange's ledger call sequence and nothing else: check,
reserve, self trade prevention, match, release, apply, settle. A05 owns the real
exchange; this drives exactly the same ``AccountBook`` calls it will.
"""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from pxe.errors import InvariantViolationError
from pxe.exchange.accounts import AccountBook, SettlementLine
from pxe.exchange.fees import reserve_fee_for, taker_fee_for
from pxe.types import (
    FEES_ACCOUNT_ID,
    MM_ACCOUNT_ID,
    MatchConfig,
    Order,
    OrderStatus,
    OrderType,
    Outcome,
    Side,
    TimeInForce,
    Trade,
    make_agent_id,
    make_market_id,
    make_order_id,
    make_trade_id,
    order_collateral_cents,
)

N_AGENTS = 4
N_MARKETS = 3
AGENTS = tuple(make_agent_id(i) for i in range(1, N_AGENTS + 1))
MARKETS = tuple(make_market_id(i) for i in range(1, N_MARKETS + 1))
TRADERS = (*AGENTS, MM_ACCOUNT_ID)
M1 = MARKETS[0]
A1 = AGENTS[0]
A2 = AGENTS[1]


class _Venue:
    """The exchange's ledger call sequence over a minimal price-time book."""

    def __init__(self, config: MatchConfig) -> None:
        self.config = config
        self.accounts = AccountBook(agent_ids=AGENTS, market_ids=MARKETS, config=config)
        self.books: dict[str, list[Order]] = {market_id: [] for market_id in MARKETS}
        self.open_markets: dict[str, bool] = dict.fromkeys(MARKETS, True)
        self.last_price: dict[str, int] = {}
        self.order_seq = 0
        self.trade_seq = 0
        self.n_trades = 0
        self.n_cancels = 0
        self.n_settlements = 0
        self.tick = 1

    # -- reads ---------------------------------------------------------
    def book_view(self) -> dict[str, tuple[Order, ...]]:
        """Every resting order keyed by market id, in priority order."""
        return {
            market_id: tuple(sorted(orders, key=lambda o: o.priority_key))
            for market_id, orders in self.books.items()
            if orders
        }

    def ref_prices(self) -> dict[str, int]:
        """A reference price per still open market."""
        return {market_id: self.last_price.get(market_id, 50) for market_id in MARKETS if self.open_markets[market_id]}

    def check(self) -> None:
        """The P4 step 15 check, plus the equity accessors the runner reads."""
        self.accounts.check_invariants(ref_prices=self.ref_prices(), book_view=self.book_view())
        for account_id in self.accounts.account_ids():
            state = self.accounts.state(account_id)
            assert state.free_cash_cents >= 0
            assert self.accounts.equity_cents(account_id, self.ref_prices()) >= 0

    def resting_of(self, agent_id: str) -> list[Order]:
        """Every resting order of one account, over every market."""
        return [o for market_id in MARKETS for o in self.books[market_id] if o.agent_id == agent_id]

    # -- writes --------------------------------------------------------
    def submit(self, agent_id: str, market_id: str, side: Side, price: int, qty: int) -> bool:
        """Place one order the way the exchange will, or refuse it."""
        if not self.open_markets[market_id]:
            return False
        if (
            len([o for o in self.books[market_id] if o.agent_id == agent_id])
            >= self.config.max_active_orders_per_market
        ):
            return False
        if agent_id == MM_ACCOUNT_ID and not self._within_inventory_cap(market_id, side, qty):
            return False
        collateral = order_collateral_cents(side, price, qty)
        if not self.accounts.can_afford(
            account_id=agent_id,
            collateral_cents=collateral,
            fee_cents=reserve_fee_for(self.config, qty=qty),
        ):
            return False
        # STP is applied after the solvency check, never before (section 6.1).
        for own in list(self.books[market_id]):
            if own.agent_id == agent_id and own.side is not side and _crosses(side, price, own.price):
                self.cancel(own.order_id)
        self.order_seq += 1
        order = Order(
            order_id=make_order_id(self.order_seq),
            agent_id=agent_id,
            market_id=market_id,
            side=side,
            order_type=OrderType.LIMIT,
            price=price,
            qty=qty,
            remaining_qty=qty,
            status=OrderStatus.NEW,
            tif=TimeInForce.GTC,
            created_tick=self.tick,
            seq=self.order_seq,
        )
        self.accounts.reserve_order(account_id=agent_id, order=order)
        order = self._match(order)
        if order.remaining_qty > 0:
            self.books[market_id].append(order.with_status(OrderStatus.OPEN))
        return True

    def cancel(self, order_id: str) -> bool:
        """Cancel one resting order and release its collateral."""
        for market_id in MARKETS:
            for order in self.books[market_id]:
                if order.order_id == order_id:
                    self.accounts.release_order(
                        account_id=order.agent_id, order=order, released_qty=order.remaining_qty
                    )
                    self.books[market_id] = [o for o in self.books[market_id] if o.order_id != order_id]
                    self.n_cancels += 1
                    return True
        return False

    def settle(self, market_id: str, outcome: Outcome | None) -> bool:
        """Cancel the book of a market, then resolve or unwind it."""
        if not self.open_markets[market_id]:
            return False
        for order in list(self.books[market_id]):
            self.cancel(order.order_id)
        lines = self.accounts.apply_settlement(
            market_id=market_id,
            outcome=outcome,
            mode="resolution" if outcome is not None else "unwind",
        )
        self.accounts.check_settlement_invariant(lines)
        assert sum(line.cash_delta_cents for line in lines) == 0
        self.open_markets[market_id] = False
        self.last_price.pop(market_id, None)
        self.n_settlements += 1
        return True

    # -- internals -----------------------------------------------------
    def _within_inventory_cap(self, market_id: str, side: Side, qty: int) -> bool:
        """FR-5.8.3: the market maker never quotes past its inventory cap."""
        current = self.accounts.position(MM_ACCOUNT_ID, market_id).qty
        return abs(current + side.sign * qty) <= self.config.mm.inventory_max

    def _match(self, taker: Order) -> Order:
        """Walk price-time priority and apply every fill to the ledger."""
        makers = sorted(
            (o for o in self.books[taker.market_id] if o.side is not taker.side and o.agent_id != taker.agent_id),
            key=lambda o: o.priority_key,
        )
        for maker in makers:
            if taker.remaining_qty == 0 or not _crosses(taker.side, taker.price, maker.price):
                break
            qty = min(taker.remaining_qty, maker.remaining_qty)
            self.accounts.release_order(account_id=maker.agent_id, order=maker, released_qty=qty)
            self.accounts.release_order(account_id=taker.agent_id, order=taker, released_qty=qty)
            self.trade_seq += 1
            trade = Trade(
                trade_id=make_trade_id(self.trade_seq),
                market_id=maker.market_id,
                price=maker.price,
                qty=qty,
                maker_order_id=maker.order_id,
                maker_agent_id=maker.agent_id,
                maker_side=maker.side,
                taker_order_id=taker.order_id,
                taker_agent_id=taker.agent_id,
                taker_fee_cents=taker_fee_for(self.config, price=maker.price, qty=qty),
                tick=self.tick,
                seq=self.trade_seq,
            )
            maker_delta, taker_delta = self.accounts.apply_trade(trade)
            assert maker_delta + taker_delta + trade.taker_fee_cents == 0
            self.n_trades += 1
            self.last_price[maker.market_id] = maker.price
            filled = maker.with_fill(qty)
            self.books[taker.market_id] = [o for o in self.books[taker.market_id] if o.order_id != maker.order_id]
            if filled.remaining_qty > 0:
                self.books[taker.market_id].append(filled)
            taker = taker.with_fill(qty)
        return taker


def _crosses(taker_side: Side, taker_price: int, maker_price: int) -> bool:
    """Whether an incoming price would execute against a resting price."""
    return taker_price >= maker_price if taker_side is Side.BUY else taker_price <= maker_price


def _config(fee_bps: int) -> MatchConfig:
    """The reference config with one fee setting."""
    return MatchConfig(seed=20260827, n_agents=N_AGENTS, n_markets=N_MARKETS, taker_fee_bps=fee_bps)


def _closing_sequence(venue: _Venue) -> None:
    """A trade, a cancellation and a settlement, whatever the generated flow did.

    This is what makes every hypothesis example non vacuous: an example that
    generated nothing still exercises all three money paths before it claims
    the invariants held. The reserved market is emptied first so the three
    steps cannot be starved by a generated order that happens to sit in the
    way.
    """
    market_id = MARKETS[-1]
    assert venue.open_markets[market_id], "the closing sequence needs its market open"
    for order in list(venue.books[market_id]):
        venue.cancel(order.order_id)
    venue.check()
    assert venue.submit(A2, market_id, Side.SELL, 40, 5)
    assert venue.submit(A1, market_id, Side.BUY, 40, 5)
    venue.check()
    assert venue.submit(A1, market_id, Side.BUY, 2, 5)
    resting = [o for o in venue.books[market_id] if o.agent_id == A1]
    assert resting, "the resting order of the closing sequence disappeared"
    assert venue.cancel(resting[0].order_id)
    venue.check()
    assert venue.settle(market_id, Outcome.YES)
    venue.check()


# ---------------------------------------------------------------------------
# The property half
# ---------------------------------------------------------------------------
_TRADERS = st.sampled_from(TRADERS)
_MARKET = st.sampled_from(MARKETS)
_SIDE = st.sampled_from((Side.BUY, Side.SELL))
_PRICE = st.integers(min_value=1, max_value=99)
_QTY = st.integers(min_value=1, max_value=40)

_PLACE = st.tuples(st.just("place"), _TRADERS, _MARKET, _SIDE, _PRICE, _QTY)
_CANCEL = st.tuples(st.just("cancel"), _TRADERS)
# The last market is deliberately not settleable by a generated op: the
# closing sequence below needs one open market to guarantee a trade, a
# cancellation and a settlement in every single example.
_SETTLE = st.tuples(st.just("settle"), st.sampled_from(MARKETS[:-1]), st.sampled_from((Outcome.YES, Outcome.NO, None)))
_OPS = st.lists(st.one_of(_PLACE, _CANCEL, _SETTLE), min_size=0, max_size=40)


@pytest.mark.property
@pytest.mark.slow
@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(ops=_OPS, fee_bps=st.sampled_from((0, 7, 200)))
def test_invariants_hold_over_random_valid_flows(ops: list[tuple[object, ...]], fee_bps: int) -> None:
    venue = _Venue(_config(fee_bps))
    venue.check()
    for op in ops:
        kind = op[0]
        if kind == "place":
            _, agent_id, market_id, side, price, qty = op
            venue.submit(str(agent_id), str(market_id), side, int(price), int(qty))  # type: ignore[arg-type]
        elif kind == "cancel":
            _, agent_id = op
            resting = venue.resting_of(str(agent_id))
            if resting:
                assert venue.cancel(resting[0].order_id)
        else:
            _, market_id, outcome = op
            venue.settle(str(market_id), outcome)  # type: ignore[arg-type]
        venue.check()

    _closing_sequence(venue)

    # Anti-vacuous, with teeth (section 10): the flow really moved money.
    assert venue.n_trades >= 1, "no trade happened, the invariants were checked over nothing"
    assert venue.n_cancels >= 1, "no cancellation happened"
    assert venue.n_settlements >= 1, "no settlement happened"

    for market_id in MARKETS:
        venue.settle(market_id, Outcome.YES)
    venue.accounts.check_final_invariant()
    assert venue.accounts.total_cash_cents() == venue.accounts.initial_total_cash_cents()


@pytest.mark.property
@pytest.mark.slow
@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    prices=st.lists(st.integers(min_value=1, max_value=99), min_size=2, max_size=12),
    qty=st.integers(min_value=1, max_value=30),
    fee_bps=st.sampled_from((0, 200)),
)
def test_an_unwind_restores_every_cash_balance(prices: list[int], qty: int, fee_bps: int) -> None:
    venue = _Venue(_config(fee_bps))
    before = {a: venue.accounts.cash_cents(a) for a in venue.accounts.account_ids()}
    traded = 0
    for index, price in enumerate(prices):
        seller = AGENTS[index % len(AGENTS)]
        buyer = AGENTS[(index + 1) % len(AGENTS)]
        venue.submit(seller, M1, Side.SELL, price, qty)
        venue.submit(buyer, M1, Side.BUY, price, qty)
        venue.check()
        traded = venue.n_trades
    assert traded >= 1, "no trade happened, the unwind would restore nothing"
    venue.settle(M1, None)
    venue.check()
    for account_id, cash in before.items():
        assert venue.accounts.cash_cents(account_id) == cash, f"{account_id} was not restored"
    assert venue.accounts.cash_cents(FEES_ACCOUNT_ID) == 0


# ---------------------------------------------------------------------------
# The control half: a deliberately broken ledger IS caught
# ---------------------------------------------------------------------------
def _traded_venue(fee_bps: int = 200) -> _Venue:
    """A venue with a real trade, a resting order and a non empty fee vault."""
    venue = _Venue(_config(fee_bps))
    assert venue.submit(A2, M1, Side.SELL, 40, 20)
    assert venue.submit(A1, M1, Side.BUY, 40, 20)
    assert venue.submit(A1, M1, Side.BUY, 30, 10)
    assert venue.n_trades == 1, "the control venue must have traded"
    assert venue.books[M1], "the control venue must have a resting order"
    if fee_bps > 0:
        assert venue.accounts.cash_cents(FEES_ACCOUNT_ID) > 0
    venue.check()
    return venue


def test_the_control_venue_is_green_before_it_is_broken() -> None:
    # Without this, every test below could be passing for the wrong reason.
    venue = _traded_venue()
    venue.check()
    assert venue.accounts.total_cash_cents() == venue.accounts.initial_total_cash_cents()


def test_a_forged_position_is_caught_as_i1() -> None:
    venue = _traded_venue()
    venue.accounts._positions[A1][M1].qty += 1
    with pytest.raises(InvariantViolationError, match="I1"):
        venue.check()


def test_created_cash_is_caught_as_i2() -> None:
    venue = _traded_venue()
    venue.accounts._cash[A1] += 1
    with pytest.raises(InvariantViolationError, match="I2"):
        venue.check()


def test_reserved_cash_drifting_from_the_book_is_caught_as_i3() -> None:
    venue = _traded_venue()
    venue.accounts._order_reserved[A1] += 100
    with pytest.raises(InvariantViolationError, match="I3"):
        venue.check()


def test_reserved_beyond_the_cash_is_caught_as_i4() -> None:
    venue = _traded_venue()
    # Move cash from A1 to FEES so I2 still holds and I4 is the first breach.
    amount = venue.accounts.cash_cents(A1) - 10
    venue.accounts._cash[A1] -= amount
    venue.accounts._cash[FEES_ACCOUNT_ID] += amount
    with pytest.raises(InvariantViolationError, match="I4"):
        venue.check()


def test_a_trade_that_creates_money_is_caught_as_i5() -> None:
    venue = _traded_venue()
    resting = venue.books[M1][0]
    trade = Trade(
        trade_id=make_trade_id(99),
        market_id=M1,
        price=40,
        qty=1,
        maker_order_id=resting.order_id,
        maker_agent_id=A2,
        maker_side=Side.SELL,
        taker_order_id=make_order_id(99),
        taker_agent_id=A1,
        taker_fee_cents=0,
        tick=1,
        seq=99,
    )
    with pytest.raises(InvariantViolationError, match="I5"):
        venue.accounts.check_trade_invariant(
            trade=trade,
            maker_cash_delta_cents=40,
            taker_cash_delta_cents=-39,
            fee_cents=0,
        )
    # The fee must be the one contracted formula on this fill's own price.
    with pytest.raises(InvariantViolationError, match="I5"):
        venue.accounts.check_trade_invariant(
            trade=trade,
            maker_cash_delta_cents=40,
            taker_cash_delta_cents=-41,
            fee_cents=1,
        )


def test_a_settlement_group_that_is_not_zero_sum_is_caught_as_i6() -> None:
    venue = _traded_venue()
    lines = venue.accounts.apply_settlement(market_id=MARKETS[1], outcome=Outcome.YES)
    assert lines == (), "nobody traded that market, so there is nothing to settle"
    forged = (
        SettlementLine(
            account_id=A1,
            market_id=M1,
            mode="resolution",
            position_qty=20,
            cash_delta_cents=2000,
            cash_before_cents=0,
            cash_after_cents=2000,
            released_collateral_cents=0,
        ),
        SettlementLine(
            account_id=A2,
            market_id=M1,
            mode="resolution",
            position_qty=-20,
            cash_delta_cents=-1999,
            cash_before_cents=2000,
            cash_after_cents=1,
            released_collateral_cents=2000,
        ),
    )
    with pytest.raises(InvariantViolationError, match="I6"):
        venue.accounts.check_settlement_invariant(forged)


def test_i6_is_checked_inside_apply_settlement() -> None:
    venue = _traded_venue()
    # Break I1 first: the settlement group can then not sum to zero, and
    # apply_settlement must refuse to return it.
    venue.accounts._positions[A1][M1].qty += 5
    with pytest.raises(InvariantViolationError, match="I6"):
        venue.accounts.apply_settlement(market_id=M1, outcome=Outcome.YES)


def test_long_and_short_asymmetry_is_caught_as_i7() -> None:
    # I7 is an equivalent restatement of I1, so no forgery can break one and
    # not the other: a one sided forge is reported as I1, which is checked
    # first. The independent check still has to have teeth, so it is also
    # invoked directly on the same broken state.
    venue = _traded_venue()
    venue.accounts._positions[A1][M1].qty += 3
    with pytest.raises(InvariantViolationError, match="I1"):
        venue.check()
    with pytest.raises(InvariantViolationError, match="I7"):
        venue.accounts._check_long_short_symmetry()


def test_a_malformed_resting_order_is_caught_as_i8() -> None:
    venue = _traded_venue()
    view = venue.book_view()
    dead = view[M1][0].with_status(OrderStatus.FILLED)
    with pytest.raises(InvariantViolationError, match="I8"):
        venue.accounts.check_invariants(ref_prices=venue.ref_prices(), book_view={M1: (dead,)})


def test_too_many_resting_orders_on_one_market_is_caught_as_i8() -> None:
    config = _config(0)
    venue = _Venue(config)
    for _ in range(config.max_active_orders_per_market):
        assert venue.submit(A1, M1, Side.BUY, 20, 1)
    venue.check()
    # The exchange refuses the eleventh; the checker must catch a book that has it.
    assert not venue.submit(A1, M1, Side.BUY, 20, 1)
    view = venue.book_view()
    extra = Order(
        order_id=make_order_id(999),
        agent_id=A1,
        market_id=M1,
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        price=20,
        qty=1,
        remaining_qty=1,
        status=OrderStatus.OPEN,
        tif=TimeInForce.GTC,
        created_tick=1,
        seq=999,
    )
    venue.accounts.reserve_order(account_id=A1, order=extra)
    with pytest.raises(InvariantViolationError, match="I8"):
        venue.accounts.check_invariants(
            ref_prices=venue.ref_prices(),
            book_view={M1: (*view[M1], extra)},
        )


def test_negative_cash_is_refused_at_the_moment_it_would_happen_i9() -> None:
    venue = _traded_venue(fee_bps=0)
    # Drain A2's cash into FEES, then resolve YES against its short: the debit
    # can no longer be paid and the ledger must refuse rather than go negative.
    amount = venue.accounts.cash_cents(A2) - 100
    venue.accounts._cash[A2] -= amount
    venue.accounts._cash[FEES_ACCOUNT_ID] += amount
    with pytest.raises(InvariantViolationError, match="I9"):
        venue.accounts.apply_settlement(market_id=M1, outcome=Outcome.YES)


def test_market_maker_inventory_over_the_cap_is_caught_as_i10() -> None:
    venue = _traded_venue()
    cap = venue.config.mm.inventory_max
    venue.accounts._positions[MM_ACCOUNT_ID][M1].qty = cap + 1
    venue.accounts._positions[A1][M1].qty -= cap + 1
    with pytest.raises(InvariantViolationError, match="I10"):
        venue.check()


def test_an_open_position_at_finalisation_is_caught_as_i11() -> None:
    venue = _traded_venue()
    with pytest.raises(InvariantViolationError, match="I11"):
        venue.accounts.check_final_invariant()
    for market_id in MARKETS:
        venue.settle(market_id, Outcome.NO)
    venue.accounts.check_final_invariant()


def test_a_forged_cost_basis_is_caught_as_i12() -> None:
    venue = _traded_venue()
    venue.accounts._positions[A1][M1].cost_basis_cents += 7
    with pytest.raises(InvariantViolationError, match="I12"):
        venue.check()
