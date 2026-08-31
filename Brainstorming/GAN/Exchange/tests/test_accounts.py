"""Acceptance tests for pxe.exchange.accounts and pxe.exchange.fees (A06).

Every money movement here is driven through the same call sequence the exchange
(A05) will use: ``can_afford`` then ``reserve_order``, then ``release_order``
plus ``apply_trade`` per fill, then ``apply_settlement``. Nothing forges an
``AccountState``: CONTRACTS section 5 P4 step 14 requires the freeze state to be
reached through real order flow, and a test that assembles the end state by hand
proves nothing about the path that gets there.

``_Venue`` below is that call sequence and nothing more. It is deliberately not
an exchange: it has no events, no protection band and no reference price. A05
owns those, and when ``pxe.exchange.exchange`` lands the same ledger calls run
under it unchanged.
"""

from __future__ import annotations

import pytest

from pxe.errors import InvalidConfigError, InvariantViolationError
from pxe.exchange.accounts import AccountBook, SettlementLine
from pxe.exchange.fees import reserve_fee_for, taker_fee_for
from pxe.types import (
    FEES_ACCOUNT_ID,
    MM_ACCOUNT_ID,
    AccountKind,
    MatchConfig,
    Order,
    OrderStatus,
    OrderType,
    Outcome,
    Side,
    TimeInForce,
    make_agent_id,
    make_market_id,
    make_order_id,
    make_trade_id,
    order_collateral_cents,
    taker_fee_cents,
)

AGENTS = tuple(make_agent_id(i) for i in range(1, 7))
MARKETS = tuple(make_market_id(i) for i in range(1, 6))
M1 = MARKETS[0]
M2 = MARKETS[1]
A1 = AGENTS[0]
A2 = AGENTS[1]
A3 = AGENTS[2]


def make_config(**overrides: object) -> MatchConfig:
    """A standard config with the A06 relevant knobs overridable."""
    base: dict[str, object] = {"seed": 20260827}
    base.update(overrides)
    return MatchConfig(**base)  # type: ignore[arg-type]


def make_book(config: MatchConfig | None = None) -> AccountBook:
    """A six seat, five market flat ledger (the ``flat_accounts`` shape)."""
    return AccountBook(agent_ids=AGENTS, market_ids=MARKETS, config=config or make_config())


class _Venue:
    """The exchange's ledger call sequence, with a minimal price-time book."""

    def __init__(self, accounts: AccountBook, config: MatchConfig) -> None:
        self.accounts = accounts
        self.config = config
        self.books: dict[str, list[Order]] = {market_id: [] for market_id in MARKETS}
        self.last_price: dict[str, int] = {}
        self.order_seq = 0
        self.trade_seq = 0
        self.n_trades = 0
        self.n_cancels = 0
        self.n_settlements = 0
        self.n_rejects = 0
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
        """A reference price per market: the last trade, else the 50 cent prior."""
        return {market_id: self.last_price.get(market_id, 50) for market_id in MARKETS}

    def check(self) -> None:
        """Run the per tick invariant check exactly as P4 step 15 does."""
        self.accounts.check_invariants(ref_prices=self.ref_prices(), book_view=self.book_view())

    def resting(self, agent_id: str, market_id: str) -> list[Order]:
        """The agent's resting orders on one market."""
        return [o for o in self.books[market_id] if o.agent_id == agent_id]

    # -- writes --------------------------------------------------------
    def submit(self, agent_id: str, market_id: str, side: Side, price: int, qty: int, *, ioc: bool = False) -> bool:
        """Place one order: check, reserve, self trade prevention, match, rest."""
        collateral = order_collateral_cents(side, price, qty)
        fee_reserve = reserve_fee_for(self.config, qty=qty)
        if len(self.resting(agent_id, market_id)) >= self.config.max_active_orders_per_market:
            self.n_rejects += 1
            return False
        if not self.accounts.can_afford(account_id=agent_id, collateral_cents=collateral, fee_cents=fee_reserve):
            self.n_rejects += 1
            return False
        # The solvency check above is evaluated BEFORE any STP release
        # (CONTRACTS section 6.1): the released cash is never available to the
        # order that caused the cancellation.
        for own in list(self.books[market_id]):
            if own.agent_id == agent_id and own.side is not side and self._crosses(side, price, own.price):
                self.cancel(agent_id, own.order_id)
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
            tif=TimeInForce.IOC if ioc else TimeInForce.GTC,
            created_tick=self.tick,
            seq=self.order_seq,
        )
        self.accounts.reserve_order(account_id=agent_id, order=order)
        order = self._match(order)
        if order.remaining_qty == 0:
            return True
        if ioc:
            self.accounts.release_order(account_id=agent_id, order=order, released_qty=order.remaining_qty)
            return True
        self.books[market_id].append(order.with_status(OrderStatus.OPEN))
        return True

    def cancel(self, agent_id: str, order_id: str) -> None:
        """Cancel one resting order and release its collateral."""
        for market_id, orders in self.books.items():
            for order in orders:
                if order.order_id == order_id:
                    if order.agent_id != agent_id:
                        raise AssertionError("cancelling someone else's order")
                    self.accounts.release_order(account_id=agent_id, order=order, released_qty=order.remaining_qty)
                    self.books[market_id] = [o for o in orders if o.order_id != order_id]
                    self.n_cancels += 1
                    return
        raise AssertionError(f"unknown resting order {order_id}")

    def cancel_all(self, market_id: str) -> None:
        """Cancel every resting order of one market, as the oracle does first."""
        for order in list(self.books[market_id]):
            self.cancel(order.agent_id, order.order_id)

    def settle(self, market_id: str, outcome: Outcome | None) -> tuple[SettlementLine, ...]:
        """Cancel the book, then settle, exactly as P1 step 4 orders it."""
        self.cancel_all(market_id)
        mode = "resolution" if outcome is not None else "unwind"
        lines = self.accounts.apply_settlement(market_id=market_id, outcome=outcome, mode=mode)
        self.n_settlements += 1
        self.last_price.pop(market_id, None)
        return lines

    # -- internals -----------------------------------------------------
    @staticmethod
    def _crosses(taker_side: Side, taker_price: int, maker_price: int) -> bool:
        """Whether an incoming price would execute against a resting price."""
        return taker_price >= maker_price if taker_side is Side.BUY else taker_price <= maker_price

    def _match(self, taker: Order) -> Order:
        """Walk price-time priority and apply every fill to the ledger."""
        book = self.books[taker.market_id]
        makers = sorted(
            (o for o in book if o.side is not taker.side and o.agent_id != taker.agent_id),
            key=lambda o: o.priority_key,
        )
        for maker in makers:
            if taker.remaining_qty == 0 or not self._crosses(taker.side, taker.price, maker.price):
                break
            qty = min(taker.remaining_qty, maker.remaining_qty)
            self.accounts.release_order(account_id=maker.agent_id, order=maker, released_qty=qty)
            self.accounts.release_order(account_id=taker.agent_id, order=taker, released_qty=qty)
            self.trade_seq += 1
            trade = self.accounts_trade(maker, taker, qty)
            self.accounts.apply_trade(trade)
            self.n_trades += 1
            self.last_price[taker.market_id] = maker.price
            filled_maker = maker.with_fill(qty)
            self.books[taker.market_id] = [o for o in book if o.order_id != maker.order_id]
            book = self.books[taker.market_id]
            if filled_maker.remaining_qty > 0:
                book.append(filled_maker)
            taker = taker.with_fill(qty)
        return taker

    def accounts_trade(self, maker: Order, taker: Order, qty: int) -> object:
        """Build the Trade of one fill, with the one contracted fee formula."""
        from pxe.types import Trade

        return Trade(
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


# ---------------------------------------------------------------------------
# The flat ledger
# ---------------------------------------------------------------------------
def test_a_fresh_book_is_funded_and_flat() -> None:
    config = make_config()
    book = make_book(config)
    assert book.account_ids(), "the ledger must not be empty"
    assert len(book.account_ids()) == len(AGENTS) + 2
    assert book.total_cash_cents() == len(AGENTS) * config.initial_cash_cents + config.mm_initial_cash_cents
    assert book.total_cash_cents() == book.initial_total_cash_cents()
    for account_id in book.account_ids():
        assert book.reserved_cents(account_id) == 0
        assert book.resting_order_count(account_id) == 0
        assert not book.is_frozen(account_id)
        for market_id in MARKETS:
            assert book.position(account_id, market_id).qty == 0


def test_the_reserved_flat_accounts_fixture_works(flat_accounts: AccountBook) -> None:
    # The section 10 fixture name is reserved by tests/conftest.py and starts
    # working for every workstream the moment this module exists.
    assert flat_accounts.account_ids() == (*AGENTS, MM_ACCOUNT_ID, FEES_ACCOUNT_ID)
    assert flat_accounts.ranked_agent_ids() == AGENTS
    assert flat_accounts.total_cash_cents() == flat_accounts.initial_total_cash_cents()
    for account_id in flat_accounts.account_ids():
        assert flat_accounts.reserved_cents(account_id) == 0
    flat_accounts.check_invariants(ref_prices={}, book_view={})
    flat_accounts.check_final_invariant()


def test_account_ids_are_in_the_canonical_account_order() -> None:
    book = make_book()
    assert book.account_ids() == (*AGENTS, MM_ACCOUNT_ID, FEES_ACCOUNT_ID)
    assert book.ranked_agent_ids() == AGENTS
    assert book.state(MM_ACCOUNT_ID).kind is AccountKind.MARKET_MAKER
    assert book.state(FEES_ACCOUNT_ID).kind is AccountKind.FEES
    assert book.state(A1).kind is AccountKind.AGENT


def test_the_fee_vault_starts_empty_and_the_mm_is_funded_ten_times_over() -> None:
    config = make_config()
    book = make_book(config)
    assert book.cash_cents(FEES_ACCOUNT_ID) == 0
    assert book.cash_cents(MM_ACCOUNT_ID) == config.mm_initial_cash_cents
    assert config.mm_initial_cash_cents >= config.initial_cash_cents


def test_unknown_ids_are_rejected_everywhere() -> None:
    book = make_book()
    with pytest.raises(InvalidConfigError):
        book.cash_cents("A9")
    with pytest.raises(InvalidConfigError):
        book.position(A1, "M9")
    with pytest.raises(InvalidConfigError):
        AccountBook(agent_ids=[A1, A1], market_ids=MARKETS, config=make_config())
    with pytest.raises(InvalidConfigError):
        AccountBook(agent_ids=[MM_ACCOUNT_ID], market_ids=MARKETS, config=make_config())


# ---------------------------------------------------------------------------
# FR-5.5.1 collateral formulas
# ---------------------------------------------------------------------------
def test_buy_collateral_is_price_times_quantity() -> None:
    config = make_config()
    book = make_book(config)
    venue = _Venue(book, config)
    assert venue.submit(A1, M1, Side.BUY, 40, 100)
    assert book.reserved_cents(A1) == 40 * 100
    assert book.free_cash_cents(A1) == config.initial_cash_cents - 4000
    assert book.resting_order_count(A1) == 1
    venue.check()


def test_sell_collateral_is_hundred_minus_price_times_quantity() -> None:
    config = make_config()
    book = make_book(config)
    venue = _Venue(book, config)
    assert venue.submit(A1, M1, Side.SELL, 40, 100)
    assert book.reserved_cents(A1) == (100 - 40) * 100
    venue.check()


def test_there_is_no_cross_market_netting() -> None:
    # FR-5.5.2: the requirement is the sum of the per market worst cases.
    config = make_config()
    book = make_book(config)
    venue = _Venue(book, config)
    assert venue.submit(A1, M1, Side.BUY, 40, 100)
    assert venue.submit(A1, M2, Side.SELL, 40, 100)
    assert book.reserved_cents(A1) == 40 * 100 + 60 * 100
    venue.check()


def test_collateral_is_released_on_cancellation() -> None:
    config = make_config()
    book = make_book(config)
    venue = _Venue(book, config)
    venue.submit(A1, M1, Side.BUY, 40, 100)
    order_id = venue.resting(A1, M1)[0].order_id
    venue.cancel(A1, order_id)
    assert venue.n_cancels == 1
    assert book.reserved_cents(A1) == 0
    assert book.free_cash_cents(A1) == config.initial_cash_cents
    assert book.resting_order_count(A1) == 0
    venue.check()


def test_a_short_position_locks_the_full_payout() -> None:
    config = make_config()
    book = make_book(config)
    venue = _Venue(book, config)
    venue.submit(A2, M1, Side.SELL, 40, 100)  # resting
    venue.submit(A1, M1, Side.BUY, 40, 100)  # crosses it
    assert venue.n_trades == 1
    short = book.position(A2, M1)
    assert short.qty == -100
    assert short.cost_basis_cents == -4000
    # The 100 cent payout per contract, less nothing: the 40 cents received per
    # contract are already sitting in cash.
    assert book.reserved_cents(A2) == 100 * 100
    assert book.cash_cents(A2) == config.initial_cash_cents + 4000
    assert book.free_cash_cents(A2) == config.initial_cash_cents - 6000
    venue.check()


def test_a_long_position_locks_nothing() -> None:
    config = make_config()
    book = make_book(config)
    venue = _Venue(book, config)
    venue.submit(A2, M1, Side.SELL, 40, 100)
    venue.submit(A1, M1, Side.BUY, 40, 100)
    assert book.position(A1, M1).qty == 100
    assert book.reserved_cents(A1) == 0
    assert book.cash_cents(A1) == make_config().initial_cash_cents - 4000
    venue.check()


def test_a_better_fill_releases_the_unused_collateral() -> None:
    config = make_config()
    book = make_book(config)
    venue = _Venue(book, config)
    venue.submit(A2, M1, Side.SELL, 40, 100)
    venue.submit(A1, M1, Side.BUY, 60, 100)  # willing to pay 60, fills at 40
    assert venue.n_trades == 1
    assert book.reserved_cents(A1) == 0
    assert book.cash_cents(A1) == config.initial_cash_cents - 4000
    venue.check()


def test_a_partial_fill_keeps_the_residual_collateralised() -> None:
    config = make_config()
    book = make_book(config)
    venue = _Venue(book, config)
    venue.submit(A2, M1, Side.SELL, 40, 40)
    venue.submit(A1, M1, Side.BUY, 40, 100)
    assert venue.n_trades == 1
    assert book.position(A1, M1).qty == 40
    assert book.reserved_cents(A1) == 40 * 60  # 60 contracts still resting at 40
    assert book.resting_order_count(A1) == 1
    venue.check()


def test_an_ioc_residual_is_released_and_never_rests() -> None:
    config = make_config()
    book = make_book(config)
    venue = _Venue(book, config)
    venue.submit(A2, M1, Side.SELL, 40, 40)
    venue.submit(A1, M1, Side.BUY, 40, 100, ioc=True)
    assert book.resting_order_count(A1) == 0
    assert book.reserved_cents(A1) == 0
    venue.check()


def test_reserving_twice_for_one_order_is_an_invariant_violation() -> None:
    config = make_config()
    book = make_book(config)
    order = Order(
        order_id=make_order_id(1),
        agent_id=A1,
        market_id=M1,
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        price=40,
        qty=10,
        remaining_qty=10,
        status=OrderStatus.NEW,
        tif=TimeInForce.GTC,
        created_tick=1,
        seq=1,
    )
    book.reserve_order(account_id=A1, order=order)
    with pytest.raises(InvariantViolationError):
        book.reserve_order(account_id=A1, order=order)
    with pytest.raises(InvalidConfigError):
        book.reserve_order(account_id=A2, order=order)
    with pytest.raises(InvariantViolationError):
        book.release_order(account_id=A1, order=order, released_qty=11)


def test_releasing_an_unreserved_order_is_an_invariant_violation() -> None:
    book = make_book()
    order = Order(
        order_id=make_order_id(7),
        agent_id=A1,
        market_id=M1,
        side=Side.SELL,
        order_type=OrderType.LIMIT,
        price=40,
        qty=10,
        remaining_qty=10,
        status=OrderStatus.OPEN,
        tif=TimeInForce.GTC,
        created_tick=1,
        seq=7,
    )
    with pytest.raises(InvariantViolationError):
        book.release_order(account_id=A1, order=order, released_qty=10)


# ---------------------------------------------------------------------------
# FR-5.5.5 no negative balance is reachable
# ---------------------------------------------------------------------------
def test_an_order_beyond_the_free_collateral_is_refused() -> None:
    config = make_config()
    book = make_book(config)
    venue = _Venue(book, config)
    qty = config.initial_cash_cents // 50
    assert venue.submit(A1, M1, Side.BUY, 50, qty)
    assert book.free_cash_cents(A1) == 0
    assert not venue.submit(A1, M1, Side.BUY, 50, 1)
    assert venue.n_rejects == 1
    assert book.free_cash_cents(A1) == 0
    venue.check()


def test_can_afford_holds_back_the_worst_case_fee() -> None:
    config = make_config(taker_fee_bps=200)
    book = make_book(config)
    collateral = order_collateral_cents(Side.BUY, 50, 100)
    fee = reserve_fee_for(config, qty=100)
    assert fee == 200 * 100 * 100 // 10_000
    assert book.can_afford(account_id=A1, collateral_cents=collateral, fee_cents=fee)
    assert not book.can_afford(
        account_id=A1,
        collateral_cents=config.initial_cash_cents - fee + 1,
        fee_cents=fee,
    )
    with pytest.raises(InvalidConfigError):
        book.can_afford(account_id=A1, collateral_cents=-1, fee_cents=0)


def test_no_flow_can_drive_the_cash_negative() -> None:
    config = make_config(taker_fee_bps=200)
    book = make_book(config)
    venue = _Venue(book, config)
    # Both sides spend everything they have, then the market resolves against
    # the short. Nothing in that sequence may produce a negative balance.
    venue.submit(A2, M1, Side.SELL, 50, 10_000)
    venue.submit(A1, M1, Side.BUY, 50, 9_000)
    assert venue.n_trades == 1
    venue.check()
    venue.settle(M1, Outcome.YES)
    for account_id in book.account_ids():
        assert book.cash_cents(account_id) >= 0
        assert book.free_cash_cents(account_id) >= 0
    venue.check()


# ---------------------------------------------------------------------------
# I5: executions are zero sum, fees land in FEES (FR-5.4.7)
# ---------------------------------------------------------------------------
def test_a_trade_is_zero_sum_and_only_the_taker_pays() -> None:
    config = make_config(taker_fee_bps=200)
    book = make_book(config)
    venue = _Venue(book, config)
    maker_cash = book.cash_cents(A2)
    taker_cash = book.cash_cents(A1)
    venue.submit(A2, M1, Side.SELL, 50, 100)
    venue.submit(A1, M1, Side.BUY, 50, 100)
    assert venue.n_trades == 1
    fee = taker_fee_cents(200, 50, 100)
    assert fee > 0, "the fee must be non zero or this test proves nothing"
    assert book.cash_cents(A2) == maker_cash + 5000
    assert book.cash_cents(A1) == taker_cash - 5000 - fee
    assert book.cash_cents(FEES_ACCOUNT_ID) == fee
    assert book.fees_paid_cents(A1, M1) == fee
    assert book.fees_paid_cents(A2, M1) == 0
    assert book.total_cash_cents() == book.initial_total_cash_cents()
    venue.check()


def test_the_fee_is_charged_per_fill_and_never_on_the_aggregate() -> None:
    # Two price levels, so floor(f1) + floor(f2) can differ from floor(f1 + f2).
    config = make_config(taker_fee_bps=7)
    book = make_book(config)
    venue = _Venue(book, config)
    venue.submit(A2, M1, Side.SELL, 41, 33)
    venue.submit(A3, M1, Side.SELL, 43, 33)
    venue.submit(A1, M1, Side.BUY, 50, 66)
    assert venue.n_trades == 2
    per_fill = taker_fee_cents(7, 41, 33) + taker_fee_cents(7, 43, 33)
    assert book.fees_paid_cents(A1, M1) == per_fill
    assert book.cash_cents(FEES_ACCOUNT_ID) == per_fill
    venue.check()


def test_apply_trade_refuses_a_self_trade() -> None:
    from pxe.types import Trade

    config = make_config()
    book = make_book(config)
    trade = Trade(
        trade_id=make_trade_id(1),
        market_id=M1,
        price=50,
        qty=10,
        maker_order_id=make_order_id(1),
        maker_agent_id=A1,
        maker_side=Side.SELL,
        taker_order_id=make_order_id(2),
        taker_agent_id=A1,
        taker_fee_cents=0,
        tick=1,
        seq=1,
    )
    with pytest.raises(InvariantViolationError):
        book.apply_trade(trade)


def test_check_trade_invariant_catches_a_trade_that_creates_money() -> None:
    from pxe.types import Trade

    book = make_book()
    trade = Trade(
        trade_id=make_trade_id(1),
        market_id=M1,
        price=50,
        qty=10,
        maker_order_id=make_order_id(1),
        maker_agent_id=A2,
        maker_side=Side.SELL,
        taker_order_id=make_order_id(2),
        taker_agent_id=A1,
        taker_fee_cents=0,
        tick=1,
        seq=1,
    )
    with pytest.raises(InvariantViolationError, match="I5"):
        book.check_trade_invariant(
            trade=trade,
            maker_cash_delta_cents=500,
            taker_cash_delta_cents=-499,
            fee_cents=0,
        )


# ---------------------------------------------------------------------------
# I6 and settlement (FR-5.5.3, FR-5.5.4)
# ---------------------------------------------------------------------------
def test_a_yes_resolution_pays_a_hundred_cents_a_contract() -> None:
    config = make_config()
    book = make_book(config)
    venue = _Venue(book, config)
    venue.submit(A2, M1, Side.SELL, 40, 100)
    venue.submit(A1, M1, Side.BUY, 40, 100)
    lines = venue.settle(M1, Outcome.YES)
    assert lines, "a settlement must produce lines or the test proves nothing"
    assert [line.account_id for line in lines] == [A1, A2]
    assert all(line.mode == "resolution" for line in lines)
    long_line = lines[0]
    short_line = lines[1]
    assert long_line.cash_delta_cents == 100 * 100
    assert short_line.cash_delta_cents == -100 * 100
    assert short_line.released_collateral_cents == 100 * 100
    assert long_line.cash_after_cents == long_line.cash_before_cents + long_line.cash_delta_cents
    assert book.cash_cents(A1) == config.initial_cash_cents + 6000
    assert book.cash_cents(A2) == config.initial_cash_cents - 6000
    assert book.position(A1, M1).qty == 0
    assert book.reserved_cents(A2) == 0
    venue.check()
    book.check_final_invariant()


def test_a_no_resolution_pays_nothing_and_still_reports_every_holder() -> None:
    config = make_config()
    book = make_book(config)
    venue = _Venue(book, config)
    venue.submit(A2, M1, Side.SELL, 40, 100)
    venue.submit(A1, M1, Side.BUY, 40, 100)
    lines = venue.settle(M1, Outcome.NO)
    assert [line.account_id for line in lines] == [A1, A2]
    assert all(line.cash_delta_cents == 0 for line in lines)
    assert book.cash_cents(A1) == config.initial_cash_cents - 4000
    assert book.cash_cents(A2) == config.initial_cash_cents + 4000
    venue.check()


def test_a_settlement_skips_accounts_flat_with_no_cost_basis() -> None:
    config = make_config()
    book = make_book(config)
    venue = _Venue(book, config)
    venue.submit(A2, M1, Side.SELL, 40, 100)
    venue.submit(A1, M1, Side.BUY, 40, 100)
    lines = venue.settle(M1, Outcome.YES)
    touched = {line.account_id for line in lines}
    assert A3 not in touched
    assert MM_ACCOUNT_ID not in touched
    assert FEES_ACCOUNT_ID not in touched


def test_settlement_lines_come_in_canonical_account_order() -> None:
    config = make_config()
    book = make_book(config)
    venue = _Venue(book, config)
    # A3 sells to A1, then MM sells to A2: four accounts hold a position.
    venue.submit(A3, M1, Side.SELL, 40, 10)
    venue.submit(A1, M1, Side.BUY, 40, 10)
    venue.submit(MM_ACCOUNT_ID, M1, Side.SELL, 40, 10)
    venue.submit(A2, M1, Side.BUY, 40, 10)
    lines = venue.settle(M1, Outcome.YES)
    assert [line.account_id for line in lines] == [A1, A2, A3, MM_ACCOUNT_ID]


def test_check_settlement_invariant_catches_a_group_that_is_not_zero_sum() -> None:
    book = make_book()
    lines = (
        SettlementLine(
            account_id=A1,
            market_id=M1,
            mode="resolution",
            position_qty=10,
            cash_delta_cents=1000,
            cash_before_cents=0,
            cash_after_cents=1000,
            released_collateral_cents=0,
        ),
    )
    with pytest.raises(InvariantViolationError, match="I6"):
        book.check_settlement_invariant(lines)


# ---------------------------------------------------------------------------
# FR-5.4.5: a cancellation unwinds everything and restores the cash
# ---------------------------------------------------------------------------
def test_an_unwind_restores_every_account_exactly() -> None:
    config = make_config(taker_fee_bps=200)
    book = make_book(config)
    venue = _Venue(book, config)
    before = {account_id: book.cash_cents(account_id) for account_id in book.account_ids()}
    venue.submit(A2, M1, Side.SELL, 40, 100)
    venue.submit(A1, M1, Side.BUY, 40, 100)
    assert book.cash_cents(FEES_ACCOUNT_ID) > 0, "the fee must be non zero or the refund proves nothing"
    lines = venue.settle(M1, None)
    assert lines, "an unwind must produce lines"
    assert all(line.mode == "unwind" for line in lines)
    assert lines[-1].account_id == FEES_ACCOUNT_ID
    for account_id, cash in before.items():
        assert book.cash_cents(account_id) == cash, f"{account_id} was not restored"
    assert book.fees_paid_cents(A1, M1) == 0
    assert book.position(A1, M1).qty == 0
    venue.check()
    book.check_final_invariant()


def test_an_unwind_refunds_the_taker_fee_to_the_taker() -> None:
    config = make_config(taker_fee_bps=200)
    book = make_book(config)
    venue = _Venue(book, config)
    venue.submit(A2, M1, Side.SELL, 40, 100)
    venue.submit(A1, M1, Side.BUY, 40, 100)
    fee = taker_fee_cents(200, 40, 100)
    lines = venue.settle(M1, None)
    taker_line = next(line for line in lines if line.account_id == A1)
    assert taker_line.cash_delta_cents == 4000 + fee
    fees_line = next(line for line in lines if line.account_id == FEES_ACCOUNT_ID)
    assert fees_line.cash_delta_cents == -fee
    assert book.cash_cents(FEES_ACCOUNT_ID) == 0


def test_an_unwind_refunds_a_closed_round_trip_too() -> None:
    # A1 buys then sells the same size: flat, zero basis, but it paid two fees.
    config = make_config(taker_fee_bps=200)
    book = make_book(config)
    venue = _Venue(book, config)
    venue.submit(A2, M1, Side.SELL, 40, 100)
    venue.submit(A1, M1, Side.BUY, 40, 100)
    venue.submit(A3, M1, Side.BUY, 40, 100)
    venue.submit(A1, M1, Side.SELL, 40, 100)
    assert venue.n_trades == 2
    assert book.position(A1, M1).qty == 0
    assert book.position(A1, M1).cost_basis_cents == 0
    paid = book.fees_paid_cents(A1, M1)
    assert paid == 2 * taker_fee_cents(200, 40, 100)
    lines = venue.settle(M1, None)
    a1_line = next(line for line in lines if line.account_id == A1)
    assert a1_line.cash_delta_cents == paid
    assert book.cash_cents(A1) == config.initial_cash_cents


def test_settlement_mode_and_outcome_must_agree() -> None:
    book = make_book()
    with pytest.raises(InvalidConfigError):
        book.apply_settlement(market_id=M1, outcome=None, mode="resolution")
    with pytest.raises(InvalidConfigError):
        book.apply_settlement(market_id=M1, outcome=Outcome.YES, mode="unwind")
    with pytest.raises(InvalidConfigError):
        book.apply_settlement(market_id=M1, outcome=Outcome.YES, mode="netting")


# ---------------------------------------------------------------------------
# FR-5.5.5 bankruptcy, reached through real order flow
# ---------------------------------------------------------------------------
def test_freeze_triggers_when_free_cash_exhausted() -> None:
    config = make_config()
    book = make_book(config)
    venue = _Venue(book, config)
    qty = config.initial_cash_cents // 50
    # A1 spends every cent it has on a long, A2 sells into it.
    assert venue.submit(A2, M1, Side.SELL, 50, qty)
    assert venue.submit(A1, M1, Side.BUY, 50, qty)
    assert venue.n_trades == 1
    assert book.position(A1, M1).qty == qty
    assert book.cash_cents(A1) == 0
    assert book.free_cash_cents(A1) == 0
    assert book.resting_order_count(A1) == 0
    # This is the P4 step 14 predicate, evaluated on real state.
    is_bankrupt = (
        book.free_cash_cents(A1) <= config.bankruptcy_free_cash_floor_cents and book.resting_order_count(A1) == 0
    ) or book.equity_cents(A1, venue.ref_prices()) <= config.bankruptcy_equity_floor_cents
    assert is_bankrupt
    assert not book.is_frozen(A1)
    book.freeze(A1)
    assert book.is_frozen(A1)
    assert book.state(A1).frozen
    venue.check()


def test_a_freeze_is_permanent_and_only_for_ranked_agents() -> None:
    book = make_book()
    book.freeze(A1)
    book.freeze(A1)
    assert book.is_frozen(A1)
    with pytest.raises(InvalidConfigError):
        book.freeze(MM_ACCOUNT_ID)
    with pytest.raises(InvalidConfigError):
        book.freeze(FEES_ACCOUNT_ID)


def test_an_agent_with_resting_orders_is_not_bankrupt() -> None:
    config = make_config()
    book = make_book(config)
    venue = _Venue(book, config)
    qty = config.initial_cash_cents // 50
    assert venue.submit(A1, M1, Side.BUY, 50, qty)
    assert book.free_cash_cents(A1) == 0
    assert book.resting_order_count(A1) == 1, "it can free the cash by cancelling next tick"
    venue.check()


# ---------------------------------------------------------------------------
# Equity, views and snapshots (FR-5.5.4, FR-5.8.3)
# ---------------------------------------------------------------------------
def test_equity_marks_positions_at_the_reference_price() -> None:
    config = make_config()
    book = make_book(config)
    venue = _Venue(book, config)
    venue.submit(A2, M1, Side.SELL, 40, 100)
    venue.submit(A1, M1, Side.BUY, 40, 100)
    assert book.equity_cents(A1, {M1: 40}) == config.initial_cash_cents
    assert book.equity_cents(A1, {M1: 60}) == config.initial_cash_cents + 2000
    assert book.equity_cents(A2, {M1: 60}) == config.initial_cash_cents - 2000
    # A market absent from ref_prices is already settled and contributes nothing.
    assert book.equity_cents(A1, {}) == config.initial_cash_cents - 4000
    # An account id is not a market id: the canonical sort helper says so.
    with pytest.raises(InvalidConfigError):
        book.equity_cents(A1, {MM_ACCOUNT_ID: 40})
    # A market this book does not hold contributes nothing.
    assert book.equity_cents(A1, {"M9": 40}) == config.initial_cash_cents - 4000


def test_inventory_view_is_a_sorted_snapshot_of_every_market() -> None:
    config = make_config()
    book = make_book(config)
    venue = _Venue(book, config)
    venue.submit(A1, M2, Side.BUY, 40, 10)
    venue.submit(MM_ACCOUNT_ID, M2, Side.SELL, 40, 10)
    view = book.inventory_view(MM_ACCOUNT_ID)
    assert view.account_id == MM_ACCOUNT_ID
    assert [mid for mid, _ in view.inventory_qty_by_market] == list(MARKETS)
    assert view.inventory_qty(M2) == -10
    assert view.inventory_qty(M1) == 0
    assert view.free_cash_cents == book.free_cash_cents(MM_ACCOUNT_ID)
    assert view.cash_cents - view.reserved_cents == view.free_cash_cents


def test_state_omits_markets_with_nothing_on_them() -> None:
    config = make_config()
    book = make_book(config)
    venue = _Venue(book, config)
    venue.submit(A2, M2, Side.SELL, 40, 10)
    venue.submit(A1, M2, Side.BUY, 40, 10)
    state = book.state(A1)
    assert [pos.market_id for pos in state.positions] == [M2]
    assert state.free_cash_cents == book.free_cash_cents(A1)
    assert len(book.states()) == len(book.account_ids())
    assert [s.account_id for s in book.states()] == list(book.account_ids())


# ---------------------------------------------------------------------------
# check_invariants and check_final_invariant
# ---------------------------------------------------------------------------
def test_check_invariants_needs_both_arguments() -> None:
    book = make_book()
    with pytest.raises(TypeError):
        book.check_invariants(ref_prices={})  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        book.check_invariants(book_view={})  # type: ignore[call-arg]


def test_check_invariants_catches_a_book_the_ledger_never_reserved() -> None:
    # I3: an order resting in the book with no collateral behind it.
    config = make_config()
    book = make_book(config)
    ghost = Order(
        order_id=make_order_id(99),
        agent_id=A1,
        market_id=M1,
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        price=40,
        qty=10,
        remaining_qty=10,
        status=OrderStatus.OPEN,
        tif=TimeInForce.GTC,
        created_tick=1,
        seq=99,
    )
    with pytest.raises(InvariantViolationError, match="I3"):
        book.check_invariants(ref_prices={M1: 40}, book_view={M1: (ghost,)})


def test_check_invariants_catches_the_order_cap_and_a_dead_order() -> None:
    config = make_config()
    book = make_book(config)
    venue = _Venue(book, config)
    cap = config.max_active_orders_per_market
    for _ in range(cap):
        assert venue.submit(A1, M1, Side.BUY, 40, 1)
    venue.check()
    view = venue.book_view()
    doubled = {M1: view[M1] + view[M1]}
    with pytest.raises(InvariantViolationError, match="I3"):
        book.check_invariants(ref_prices={M1: 40}, book_view=doubled)
    dead = view[M1][0].with_status(OrderStatus.CANCELLED)
    with pytest.raises(InvariantViolationError, match="I8"):
        book.check_invariants(ref_prices={M1: 40}, book_view={M1: (dead, *view[M1][1:])})


def test_check_final_invariant_refuses_an_open_position() -> None:
    config = make_config()
    book = make_book(config)
    venue = _Venue(book, config)
    venue.submit(A2, M1, Side.SELL, 40, 10)
    venue.submit(A1, M1, Side.BUY, 40, 10)
    with pytest.raises(InvariantViolationError, match="I11"):
        book.check_final_invariant()
    venue.settle(M1, Outcome.YES)
    book.check_final_invariant()
    for account_id in book.account_ids():
        assert book.equity_cents(account_id, {}) == book.cash_cents(account_id)


# ---------------------------------------------------------------------------
# pxe.exchange.fees: delegation only
# ---------------------------------------------------------------------------
def test_fees_helpers_delegate_to_the_one_owner() -> None:
    config = make_config(taker_fee_bps=200)
    assert taker_fee_for(config, price=37, qty=13) == taker_fee_cents(200, 37, 13)
    assert reserve_fee_for(config, qty=13) == taker_fee_cents(200, 100, 13)
    zero = make_config()
    assert zero.taker_fee_bps == 0
    assert taker_fee_for(zero, price=37, qty=13) == 0
    assert reserve_fee_for(zero, qty=13) == 0


def test_the_reserved_fee_is_never_smaller_than_the_charged_fee() -> None:
    config = make_config(taker_fee_bps=200)
    for price in range(1, 100):
        assert reserve_fee_for(config, qty=7) >= taker_fee_for(config, price=price, qty=7)
