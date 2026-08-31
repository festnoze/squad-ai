"""A08: ``settle``, the one and only emitter of ``SettlementApplied`` (CONTRACTS section 7.11).

Three claims:

1. **payments are exact to the cent.** A YES contract pays exactly ``100`` cents
   and a NO contract exactly ``0``, the group is zero sum across accounts
   (invariant I6), the total cash of the system is unchanged (I2) and every
   line's ``cash_before + cash_delta == cash_after``;
2. **an unwind refunds the taker fees** (FR-5.4.5, CONTRACTS section 6.4). An
   agent that traded on a market that was then cancelled is exactly as rich as
   before the market existed, which is only true because the ``FEES`` vault
   pays the fees back. With the default ``taker_fee_bps = 0`` the bug is
   invisible, so every test here that touches the refund sets a non zero fee;
3. **the emission order is the canonical account order** of section 2.3 (ranked
   agents ascending, then ``MM``, then ``FEES``). That order is the journal
   byte order and therefore part of the AC-P1 hash.

Every test that looks at the journal asserts it is non empty and holds at least
one ``SettlementApplied`` before claiming anything (section 10's anti-vacuous
rule).
"""

from __future__ import annotations

import pytest

from pxe.errors import InvalidConfigError
from pxe.events import SettlementApplied
from pxe.exchange.accounts import AccountBook
from pxe.exchange.exchange import Exchange
from pxe.journal import Journal
from pxe.oracle.settlement import settle
from pxe.types import (
    FEES_ACCOUNT_ID,
    MM_ACCOUNT_ID,
    MarketSpec,
    MatchConfig,
    OrderIntent,
    OrderType,
    Outcome,
    ScenarioSpec,
    Side,
    make_agent_id,
    make_market_id,
    sorted_account_ids,
)

TICKS = 24
MARKETS = 2
AGENTS = 4


# ---------------------------------------------------------------------------
# Local builders. ``settle`` needs no world, so these are lighter than
# tests/test_oracle.py's: a scenario, a ledger, a book and a journal.
# ---------------------------------------------------------------------------
def _config(**overrides: object) -> MatchConfig:
    base: dict[str, object] = {
        "seed": 20260827,
        "ticks_total": TICKS,
        "n_agents": AGENTS,
        "n_markets": MARKETS,
    }
    base.update(overrides)
    return MatchConfig(**base)  # type: ignore[arg-type]


def _scenario(config: MatchConfig) -> ScenarioSpec:
    markets = tuple(
        MarketSpec(
            market_id=make_market_id(index),
            question=f"does event {index} happen",
            prior_price=50,
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


def _place(
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


def _cross(
    exchange: Exchange,
    *,
    maker: str,
    taker: str,
    price: int,
    qty: int,
    market_id: str = "M1",
    tick: int = 1,
) -> None:
    """``maker`` rests a sell, ``taker`` lifts it: the taker ends long and pays the fee."""
    _place(exchange, agent_id=maker, side=Side.SELL, price=price, qty=qty, market_id=market_id, tick=tick)
    _place(
        exchange,
        agent_id=taker,
        side=Side.BUY,
        price=price,
        qty=qty,
        market_id=market_id,
        tick=tick,
        item_index=1,
    )


def _settlements(journal: Journal, *, market_id: str | None = None) -> list[SettlementApplied]:
    """Return the SettlementApplied events, after the two anti-vacuous assertions."""
    assert journal.events, "the journal must not be empty before it is asserted on"
    found = [event for event in journal.events if isinstance(event, SettlementApplied)]
    assert found, "no SettlementApplied was journalled: the assertions below would be vacuous"
    if market_id is None:
        return found
    return [event for event in found if event.market_id == market_id]


# ---------------------------------------------------------------------------
# Claim 1: exact to the cent
# ---------------------------------------------------------------------------
def test_payouts_are_exact_to_the_cent(tmp_journal) -> None:
    """A YES pays exactly 100 per contract, a NO exactly 0, and no cent appears or vanishes."""
    config = _config(taker_fee_bps=0)
    exchange, accounts = _arena(config, tmp_journal)

    # M1: A1 is long 13 at 37, A2 is short 13. M1 resolves YES.
    _cross(exchange, maker="A2", taker="A1", price=37, qty=13)
    # M2: A4 is long 7 at 63, A3 is short 7. M2 resolves NO.
    _cross(exchange, maker="A3", taker="A4", price=63, qty=7, market_id="M2")

    lines_yes = settle(tick=TICKS + 1, market_id="M1", outcome=Outcome.YES, accounts=accounts, journal=tmp_journal)
    lines_no = settle(tick=TICKS + 1, market_id="M2", outcome=Outcome.NO, accounts=accounts, journal=tmp_journal)

    events = _settlements(tmp_journal)
    assert len(events) == len(lines_yes) + len(lines_no) == 4
    assert {event.tick for event in events} == {TICKS + 1}
    assert {event.mode for event in events} == {"resolution"}

    # Exactly 100 cents per YES contract, exactly 0 per NO contract.
    by_key = {(event.market_id, event.account_id): event for event in events}
    assert by_key[("M1", "A1")].cash_delta_cents == 13 * 100
    assert by_key[("M1", "A2")].cash_delta_cents == -13 * 100
    assert by_key[("M2", "A4")].cash_delta_cents == 0
    assert by_key[("M2", "A3")].cash_delta_cents == 0
    # A NO still produces a line: the position was real and its collateral is released.
    assert by_key[("M2", "A3")].position_qty == -7
    assert by_key[("M2", "A3")].released_collateral_cents == 7 * 100
    assert by_key[("M2", "A4")].released_collateral_cents == 0

    # Every line is internally consistent, and every group is zero sum (I6).
    for event in events:
        assert event.cash_before_cents + event.cash_delta_cents == event.cash_after_cents
    for market_id in ("M1", "M2"):
        assert sum(event.cash_delta_cents for event in events if event.market_id == market_id) == 0

    # Hand computed final cash, cent by cent.
    assert accounts.cash_cents("A1") == config.initial_cash_cents - 37 * 13 + 13 * 100
    assert accounts.cash_cents("A2") == config.initial_cash_cents + 37 * 13 - 13 * 100
    assert accounts.cash_cents("A3") == config.initial_cash_cents + 63 * 7
    assert accounts.cash_cents("A4") == config.initial_cash_cents - 63 * 7
    assert accounts.total_cash_cents() == accounts.initial_total_cash_cents()
    accounts.check_final_invariant()


def test_settlement_flattens_every_position_and_cost_basis(tmp_journal) -> None:
    """After the group nothing is held: I11 becomes reachable and I12 stays true."""
    config = _config(taker_fee_bps=0)
    exchange, accounts = _arena(config, tmp_journal)
    _cross(exchange, maker="A2", taker="A1", price=41, qty=6)
    assert accounts.position("A1", "M1").qty == 6
    assert accounts.position("A1", "M1").cost_basis_cents != 0

    settle(tick=TICKS + 1, market_id="M1", outcome=Outcome.YES, accounts=accounts, journal=tmp_journal)
    assert _settlements(tmp_journal, market_id="M1")
    for account_id in accounts.account_ids():
        position = accounts.position(account_id, "M1")
        assert (position.qty, position.cost_basis_cents) == (0, 0)
        assert accounts.reserved_cents(account_id) == 0


def test_an_untouched_market_settles_silently(tmp_journal) -> None:
    """Nobody traded it, so there is no line and therefore no event: no empty payload."""
    config = _config(taker_fee_bps=0)
    exchange, accounts = _arena(config, tmp_journal)
    _cross(exchange, maker="A2", taker="A1", price=41, qty=6)

    before = len(tmp_journal.events)
    lines = settle(tick=TICKS + 1, market_id="M2", outcome=Outcome.YES, accounts=accounts, journal=tmp_journal)
    assert lines == ()
    assert len(tmp_journal.events) == before

    # The same call on the traded market does emit, so the assertion above is
    # about "flat" and not about a broken emitter.
    settle(tick=TICKS + 1, market_id="M1", outcome=Outcome.YES, accounts=accounts, journal=tmp_journal)
    assert len(_settlements(tmp_journal, market_id="M1")) == 2


# ---------------------------------------------------------------------------
# Claim 2: the FR-5.4.5 unwind refunds the taker fees
# ---------------------------------------------------------------------------
def test_unwind_refunds_taker_fees(tmp_journal) -> None:
    """FR-5.4.5 and section 6.4: after an unwind every account is exactly as rich as before."""
    config = _config(taker_fee_bps=100)  # 1 %, so the refund is visible at all
    exchange, accounts = _arena(config, tmp_journal)

    _cross(exchange, maker="A2", taker="A1", price=37, qty=13)
    _cross(exchange, maker="A4", taker="A3", price=51, qty=9)
    fee_a1 = (100 * 37 * 13) // 10_000
    fee_a3 = (100 * 51 * 9) // 10_000
    assert (fee_a1, fee_a3) == (4, 4)
    assert accounts.fees_paid_cents("A1", "M1") == fee_a1
    assert accounts.fees_paid_cents("A3", "M1") == fee_a3
    assert accounts.cash_cents(FEES_ACCOUNT_ID) == fee_a1 + fee_a3
    assert accounts.cash_cents("A1") == config.initial_cash_cents - 37 * 13 - fee_a1

    lines = settle(tick=7, market_id="M1", outcome=None, accounts=accounts, journal=tmp_journal, mode="unwind")
    events = _settlements(tmp_journal, market_id="M1")
    assert len(events) == len(lines) == 5
    assert {event.mode for event in events} == {"unwind"}
    assert {event.tick for event in events} == {7}

    # The FEES line pays back every fee collected on that market, and it is last.
    assert events[-1].account_id == FEES_ACCOUNT_ID
    assert events[-1].cash_delta_cents == -(fee_a1 + fee_a3)
    by_account = {event.account_id: event for event in events}
    assert by_account["A1"].cash_delta_cents == 37 * 13 + fee_a1
    assert by_account["A3"].cash_delta_cents == 51 * 9 + fee_a3
    assert by_account["A2"].cash_delta_cents == -37 * 13
    assert by_account["A4"].cash_delta_cents == -51 * 9
    assert sum(event.cash_delta_cents for event in events) == 0

    # Nobody is poorer than before the market existed: that is what "restitue le cash" means.
    for index in range(1, config.n_agents + 1):
        assert accounts.cash_cents(make_agent_id(index)) == config.initial_cash_cents
    assert accounts.cash_cents(FEES_ACCOUNT_ID) == 0
    assert accounts.fees_paid_cents("A1", "M1") == 0
    assert accounts.total_cash_cents() == accounts.initial_total_cash_cents()


def test_unwind_refunds_only_the_cancelled_market(tmp_journal) -> None:
    """A fee paid on another market stays collected: the refund is per market."""
    config = _config(taker_fee_bps=200)
    exchange, accounts = _arena(config, tmp_journal)
    _cross(exchange, maker="A2", taker="A1", price=37, qty=13)
    _cross(exchange, maker="A4", taker="A3", price=51, qty=9, market_id="M2")
    fee_m1 = (200 * 37 * 13) // 10_000
    fee_m2 = (200 * 51 * 9) // 10_000
    assert fee_m1 > 0 and fee_m2 > 0

    settle(tick=7, market_id="M1", outcome=None, accounts=accounts, journal=tmp_journal, mode="unwind")
    assert _settlements(tmp_journal, market_id="M1")
    assert accounts.cash_cents(FEES_ACCOUNT_ID) == fee_m2
    assert accounts.fees_paid_cents("A3", "M2") == fee_m2
    assert accounts.cash_cents("A1") == config.initial_cash_cents
    assert accounts.cash_cents("A3") == config.initial_cash_cents - 51 * 9 - fee_m2


def test_mode_and_outcome_must_agree(tmp_journal) -> None:
    """A mode that disagrees with the outcome is a bug and not a default."""
    config = _config()
    exchange, accounts = _arena(config, tmp_journal)
    _cross(exchange, maker="A2", taker="A1", price=41, qty=6)
    with pytest.raises(InvalidConfigError):
        settle(tick=7, market_id="M1", outcome=Outcome.YES, accounts=accounts, journal=tmp_journal, mode="unwind")
    with pytest.raises(InvalidConfigError):
        settle(tick=7, market_id="M1", outcome=None, accounts=accounts, journal=tmp_journal)
    with pytest.raises(InvalidConfigError):
        settle(tick=7, market_id="M1", outcome=Outcome.YES, accounts=accounts, journal=tmp_journal, mode="netting")
    # Nothing was emitted and nothing moved: a refused settlement is not a partial one.
    assert not [event for event in tmp_journal.events if isinstance(event, SettlementApplied)]
    assert accounts.position("A1", "M1").qty == 6


def test_unknown_market_is_refused(tmp_journal) -> None:
    """settle never invents a market."""
    config = _config()
    _exchange, accounts = _arena(config, tmp_journal)
    with pytest.raises(InvalidConfigError):
        settle(tick=7, market_id="M7", outcome=Outcome.YES, accounts=accounts, journal=tmp_journal)


# ---------------------------------------------------------------------------
# Claim 3: the emission order is the canonical account order
# ---------------------------------------------------------------------------
def test_settlement_events_follow_the_canonical_account_order(tmp_journal) -> None:
    """Ranked agents ascending, then MM, then FEES: the journal byte order of section 2.3."""
    config = _config(taker_fee_bps=100)
    exchange, accounts = _arena(config, tmp_journal)

    # MM is the maker on both crosses, so it ends short and its line is not the
    # lexicographic neighbour of the agent lines: "FEES" < "MM" < "A1" is wrong
    # in two different ways and this ordering catches both.
    _place(exchange, agent_id=MM_ACCOUNT_ID, side=Side.SELL, price=45, qty=20)
    _place(exchange, agent_id="A3", side=Side.BUY, price=45, qty=8, item_index=1)
    _place(exchange, agent_id="A1", side=Side.BUY, price=45, qty=12, item_index=2)
    assert accounts.position(MM_ACCOUNT_ID, "M1").qty == -20

    lines = settle(tick=7, market_id="M1", outcome=None, accounts=accounts, journal=tmp_journal, mode="unwind")
    events = _settlements(tmp_journal, market_id="M1")
    order = [event.account_id for event in events]
    assert order == ["A1", "A3", MM_ACCOUNT_ID, FEES_ACCOUNT_ID]
    assert order == list(sorted_account_ids(order))
    assert [line.account_id for line in lines] == order
    # One event per line, and the events are contiguous and in sequence.
    seqs = [event.seq for event in events]
    assert seqs == list(range(seqs[0], seqs[0] + len(seqs)))
    assert sum(event.cash_delta_cents for event in events) == 0


def test_resolution_group_holds_no_fees_line(tmp_journal) -> None:
    """Only an unwind refunds fees, so only an unwind carries a FEES line."""
    config = _config(taker_fee_bps=100)
    exchange, accounts = _arena(config, tmp_journal)
    _cross(exchange, maker="A2", taker="A1", price=37, qty=13)
    assert accounts.cash_cents(FEES_ACCOUNT_ID) > 0

    settle(tick=TICKS + 1, market_id="M1", outcome=Outcome.YES, accounts=accounts, journal=tmp_journal)
    events = _settlements(tmp_journal, market_id="M1")
    assert [event.account_id for event in events] == ["A1", "A2"]
    assert sum(event.cash_delta_cents for event in events) == 0
    # The fee stays collected: a resolution is not an unwind.
    assert accounts.cash_cents(FEES_ACCOUNT_ID) == (100 * 37 * 13) // 10_000
