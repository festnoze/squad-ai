"""A08: per market resolution and FR-5.4.5 cancellation (CONTRACTS sections 5.0 and 7.11).

Four claims, and they are independent:

1. a market whose ``resolution_tick`` is ``r`` is tradable for the whole of
   tick ``r`` and resolves in P1 of tick ``r + 1``, with the envelope tick and
   the payload ``resolution_tick`` differing by exactly one (section 5.0);
2. an early resolution (``r < ticks_total``, FR-5.2.3) cancels the resting
   orders, releases their collateral through ``OrderCancelled`` and closes
   trading for good;
3. a scripted cancellation fires at the tick it was scheduled for, ``c`` and
   not ``c + 1``, because it is an intervention and not a maturity (FR-5.4.5);
4. a cancellation unwinds every execution: the cash is exactly back where it
   was and the positions are flat.

Every test that looks at the journal asserts it is non empty and holds at least
one event of the type under test before claiming anything (section 10's
anti-vacuous rule).

The builders below are local on purpose: the oracle has to be driven over a
world whose resolution ticks and cancellations are chosen by the test, which is
not what the shared ``tiny_world`` fixture is for. The last test of the file
does use that fixture, against a really generated world, so the hand built
scenarios cannot drift away from what ``generate_world`` produces.
"""

from __future__ import annotations

import pytest

from pxe.errors import InvalidConfigError
from pxe.events import (
    MarketCancelled,
    MarketResolved,
    NewsPublished,
    OrderCancelled,
    SettlementApplied,
)
from pxe.exchange.accounts import AccountBook
from pxe.exchange.exchange import Exchange
from pxe.journal import Journal
from pxe.oracle.resolver import Oracle, ResolutionReport
from pxe.types import (
    CancelReason,
    MarketSpec,
    MarketStatus,
    MatchConfig,
    OrderIntent,
    OrderType,
    Outcome,
    RejectReason,
    ScenarioSpec,
    Side,
    make_agent_id,
    make_market_id,
)
from pxe.world.generator import World
from pxe.world.latent import LatentProcess

TICKS = 24
MARKETS = 2
AGENTS = 4

#: Latent level, in thousandths, used for a market whose outcome is YES and for
#: one whose outcome is NO. The sign is what makes the revealed
#: ``latent_value_milli`` agree with the frozen outcome; the magnitude is
#: arbitrary and no assertion depends on it.
_YES_LEVEL_MILLI = 400
_NO_LEVEL_MILLI = -400


# ---------------------------------------------------------------------------
# Local builders
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


def _world(
    config: MatchConfig,
    *,
    resolution_ticks: tuple[int, ...],
    outcomes: tuple[Outcome, ...],
    cancellations: tuple[tuple[int, str, str], ...] = (),
) -> World:
    assert len(resolution_ticks) == len(outcomes) == config.n_markets
    markets = tuple(
        MarketSpec(
            market_id=make_market_id(index + 1),
            question=f"does event {index + 1} happen",
            prior_price=50,
            resolution_tick=resolution_ticks[index],
            latent_key=f"latent_{index + 1}",
        )
        for index in range(config.n_markets)
    )
    scenario = ScenarioSpec(
        template_id="election",
        template_version="1.0.0",
        seed=config.seed,
        ticks_total=config.ticks_total,
        markets=markets,
        cancellations=cancellations,
        talking_mode=config.talking_mode,
        liquidity_profile_name=config.liquidity_profile_name,
    )
    latent = LatentProcess(
        keys=tuple(spec.latent_key for spec in markets),
        values_milli=tuple(
            tuple(
                (_YES_LEVEL_MILLI if outcomes[index] is Outcome.YES else _NO_LEVEL_MILLI)
                for _tick in range(config.ticks_total + 1)
            )
            for index in range(config.n_markets)
        ),
    )
    return World(
        scenario=scenario,
        latent=latent,
        outcomes=tuple((spec.market_id, outcomes[index]) for index, spec in enumerate(markets)),
        news_plan=(),
    )


def _arena(config: MatchConfig, world: World, journal: Journal) -> tuple[Exchange, AccountBook, Oracle]:
    accounts = AccountBook(
        agent_ids=tuple(make_agent_id(index) for index in range(1, config.n_agents + 1)),
        market_ids=world.market_ids(),
        config=config,
    )
    exchange = Exchange(config=config, scenario=world.scenario, accounts=accounts, journal=journal)
    return (exchange, accounts, Oracle(world=world))


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


def _cross(exchange: Exchange, *, price: int, qty: int, market_id: str = "M1", tick: int = 1) -> None:
    """A2 rests a sell, A1 lifts it, so A1 is long and A2 is short."""
    _place(exchange, agent_id="A2", side=Side.SELL, price=price, qty=qty, market_id=market_id, tick=tick)
    _place(
        exchange,
        agent_id="A1",
        side=Side.BUY,
        price=price,
        qty=qty,
        market_id=market_id,
        tick=tick,
        item_index=1,
    )


def _events(journal: Journal, event_cls: type) -> list:
    """Return every event of one type, after the two anti-vacuous assertions."""
    assert journal.events, "the journal must not be empty before it is asserted on"
    found = [event for event in journal.events if isinstance(event, event_cls)]
    assert found, f"no {event_cls.__name__} was journalled: the assertions below would be vacuous"
    return found


# ---------------------------------------------------------------------------
# Section 5.0: which tick a market is tradable at, which tick it resolves at
# ---------------------------------------------------------------------------
def test_due_market_ids_is_empty_at_tick_one(tmp_journal) -> None:
    """Nothing is due at tick 1: the earliest legal resolution tick is 1, so r + 1 is 2."""
    config = _config()
    world = _world(config, resolution_ticks=(1, TICKS), outcomes=(Outcome.YES, Outcome.NO))
    _exchange, _accounts, oracle = _arena(config, world, tmp_journal)
    assert oracle.due_market_ids(1) == ()
    assert oracle.due_market_ids(2) == ("M1",)


def test_market_is_tradable_on_its_resolution_tick(tmp_journal) -> None:
    """FR-5.2.3 and section 5.0: open for the whole of tick r, resolved in P1 of r + 1."""
    config = _config()
    world = _world(config, resolution_ticks=(5, TICKS), outcomes=(Outcome.YES, Outcome.NO))
    exchange, accounts, oracle = _arena(config, world, tmp_journal)

    # Tick 5 is the market's own resolution tick: it is not due and it trades.
    exchange.begin_tick(5)
    assert oracle.due_market_ids(5) == ()
    assert exchange.status("M1") is MarketStatus.OPEN
    _cross(exchange, price=40, qty=10, tick=5)
    assert accounts.position("A1", "M1").qty == 10
    assert oracle.resolve.__doc__  # the method exists before the failure below is claimed
    with pytest.raises(InvalidConfigError):
        oracle.resolve(tick=5, market_id="M1", exchange=exchange, accounts=accounts, journal=tmp_journal)

    # Tick 6 resolves it, before that tick's observations would be built.
    exchange.begin_tick(6)
    assert oracle.due_market_ids(6) == ("M1",)
    report = oracle.resolve(tick=6, market_id="M1", exchange=exchange, accounts=accounts, journal=tmp_journal)
    assert isinstance(report, ResolutionReport)
    assert exchange.status("M1") is MarketStatus.RESOLVED
    assert oracle.due_market_ids(7) == ()


def test_resolution_envelope_tick_is_one_after_the_payload_tick(tmp_journal) -> None:
    """The envelope tick is r + 1 and the payload resolution_tick is r, on purpose."""
    config = _config()
    world = _world(config, resolution_ticks=(5, TICKS), outcomes=(Outcome.YES, Outcome.NO))
    exchange, accounts, oracle = _arena(config, world, tmp_journal)
    exchange.begin_tick(6)
    oracle.resolve(tick=6, market_id="M1", exchange=exchange, accounts=accounts, journal=tmp_journal)

    resolved = _events(tmp_journal, MarketResolved)
    assert len(resolved) == 1
    assert (resolved[0].tick, resolved[0].resolution_tick) == (6, 5)
    assert resolved[0].market_id == "M1"
    assert resolved[0].outcome == "yes"
    assert resolved[0].payout_cents == 100
    assert resolved[0].latent_value_milli == _YES_LEVEL_MILLI


def test_finalisation_resolves_everything_left(tmp_journal) -> None:
    """With the PRD default every market matures at T, so every match settles at T + 1."""
    config = _config()
    world = _world(config, resolution_ticks=(TICKS, TICKS), outcomes=(Outcome.YES, Outcome.NO))
    exchange, accounts, oracle = _arena(config, world, tmp_journal)
    assert oracle.due_market_ids(TICKS) == ()
    assert oracle.due_market_ids(TICKS + 1) == ("M1", "M2")

    for market_id in oracle.due_market_ids(TICKS + 1):
        oracle.resolve(
            tick=TICKS + 1,
            market_id=market_id,
            exchange=exchange,
            accounts=accounts,
            journal=tmp_journal,
        )
    resolved = _events(tmp_journal, MarketResolved)
    assert [event.market_id for event in resolved] == ["M1", "M2"]
    assert {event.tick for event in resolved} == {TICKS + 1}
    assert [event.resolution_tick for event in resolved] == [TICKS, TICKS]
    accounts.check_final_invariant()


# ---------------------------------------------------------------------------
# FR-5.2.3: an early resolution frees the collateral and closes trading
# ---------------------------------------------------------------------------
def test_early_resolution_releases_collateral(tmp_journal) -> None:
    """FR-5.2.3: the resting orders leave first, and their collateral comes back."""
    config = _config()
    world = _world(config, resolution_ticks=(5, TICKS), outcomes=(Outcome.YES, Outcome.NO))
    exchange, accounts, oracle = _arena(config, world, tmp_journal)

    exchange.begin_tick(5)
    _place(exchange, agent_id="A1", side=Side.BUY, price=40, qty=10, tick=5)
    _place(exchange, agent_id="A3", side=Side.SELL, price=60, qty=10, tick=5, item_index=1)
    # A market the resolution must not touch, so "released everything" cannot pass vacuously.
    _place(exchange, agent_id="A1", side=Side.BUY, price=30, qty=10, market_id="M2", tick=5, item_index=2)
    assert accounts.reserved_cents("A1") == 40 * 10 + 30 * 10
    assert accounts.reserved_cents("A3") == (100 - 60) * 10

    exchange.begin_tick(6)
    report = oracle.resolve(tick=6, market_id="M1", exchange=exchange, accounts=accounts, journal=tmp_journal)

    cancelled = [event for event in _events(tmp_journal, OrderCancelled) if event.tick == 6]
    assert [event.reason for event in cancelled] == [CancelReason.MARKET_RESOLVED] * 2
    assert sorted(event.released_cents for event in cancelled) == [400, 400]
    assert set(report.cancelled_order_ids) == {event.order_id for event in cancelled}
    assert accounts.reserved_cents("A3") == 0
    assert accounts.reserved_cents("A1") == 30 * 10  # only the M2 order still holds collateral
    assert accounts.free_cash_cents("A1") == config.initial_cash_cents - 30 * 10


def test_resolution_closes_trading(tmp_journal) -> None:
    """FR-5.4.5: a resolved market accepts nothing, and the refusal is an event."""
    config = _config()
    world = _world(config, resolution_ticks=(5, TICKS), outcomes=(Outcome.YES, Outcome.NO))
    exchange, accounts, oracle = _arena(config, world, tmp_journal)
    exchange.begin_tick(6)
    oracle.resolve(tick=6, market_id="M1", exchange=exchange, accounts=accounts, journal=tmp_journal)

    result = _place(exchange, agent_id="A1", side=Side.BUY, price=40, qty=10, tick=6, item_index=3)
    assert result.accepted is False
    assert result.reason is RejectReason.MARKET_NOT_OPEN
    # The untouched market still trades, so the assertion above is about M1 and not about the book.
    assert _place(exchange, agent_id="A1", side=Side.BUY, price=40, qty=10, market_id="M2", tick=6).accepted


def test_resolve_emits_market_resolved_once_and_no_news(tmp_journal) -> None:
    """Single emitter rule: the oracle emits MarketResolved and never NewsPublished."""
    config = _config()
    world = _world(config, resolution_ticks=(5, TICKS), outcomes=(Outcome.YES, Outcome.NO))
    exchange, accounts, oracle = _arena(config, world, tmp_journal)
    exchange.begin_tick(6)
    _cross(exchange, price=40, qty=10, tick=6)
    oracle.resolve(tick=6, market_id="M1", exchange=exchange, accounts=accounts, journal=tmp_journal)

    assert len(_events(tmp_journal, MarketResolved)) == 1
    assert _events(tmp_journal, SettlementApplied)
    assert not [event for event in tmp_journal.events if isinstance(event, NewsPublished)]
    # Sub-step order a, b, c, e: every OrderCancelled precedes MarketResolved,
    # which precedes every SettlementApplied of that market.
    seq_of = {type(event).__name__: event.seq for event in tmp_journal.events}
    assert seq_of["MarketResolved"] < seq_of["SettlementApplied"]


def test_resolving_twice_is_refused(tmp_journal) -> None:
    """A second resolution would emit a second MarketResolved: refused, not idempotent."""
    config = _config()
    world = _world(config, resolution_ticks=(5, TICKS), outcomes=(Outcome.YES, Outcome.NO))
    exchange, accounts, oracle = _arena(config, world, tmp_journal)
    exchange.begin_tick(6)
    oracle.resolve(tick=6, market_id="M1", exchange=exchange, accounts=accounts, journal=tmp_journal)
    with pytest.raises(InvalidConfigError):
        oracle.resolve(tick=7, market_id="M1", exchange=exchange, accounts=accounts, journal=tmp_journal)
    assert len(_events(tmp_journal, MarketResolved)) == 1


def test_unknown_market_is_refused(tmp_journal) -> None:
    """The oracle never invents a market: an unknown id raises."""
    config = _config()
    world = _world(config, resolution_ticks=(TICKS, TICKS), outcomes=(Outcome.YES, Outcome.NO))
    exchange, accounts, oracle = _arena(config, world, tmp_journal)
    with pytest.raises(InvalidConfigError):
        oracle.outcome("M7")
    with pytest.raises(InvalidConfigError):
        oracle.resolve(tick=2, market_id="M7", exchange=exchange, accounts=accounts, journal=tmp_journal)


def test_outcome_is_the_frozen_one(tmp_journal) -> None:
    """The oracle draws nothing: it reads what world generation already froze."""
    config = _config()
    world = _world(config, resolution_ticks=(TICKS, TICKS), outcomes=(Outcome.YES, Outcome.NO))
    _exchange, _accounts, oracle = _arena(config, world, tmp_journal)
    assert (oracle.outcome("M1"), oracle.outcome("M2")) == (Outcome.YES, Outcome.NO)
    assert oracle.outcome("M1") is world.outcome("M1")


# ---------------------------------------------------------------------------
# FR-5.4.5: the scripted cancellation
# ---------------------------------------------------------------------------
def test_scripted_cancellation_at_scheduled_tick(tmp_journal) -> None:
    """FR-5.4.5: a cancellation fires at tick c, not c + 1, and closes the market there."""
    config = _config()
    world = _world(
        config,
        resolution_ticks=(TICKS, TICKS),
        outcomes=(Outcome.YES, Outcome.NO),
        cancellations=((7, "M1", "event voided by the organiser"),),
    )
    exchange, accounts, oracle = _arena(config, world, tmp_journal)

    assert oracle.due_cancellations(6) == ()
    assert oracle.due_cancellations(7) == (("M1", "event voided by the organiser"),)
    assert oracle.due_cancellations(8) == ()

    exchange.begin_tick(7)
    _cross(exchange, price=40, qty=10, tick=7)
    report = oracle.cancel_market(
        tick=7,
        market_id="M1",
        reason="event voided by the organiser",
        exchange=exchange,
        accounts=accounts,
        journal=tmp_journal,
    )
    cancelled = _events(tmp_journal, MarketCancelled)
    assert len(cancelled) == 1
    assert (cancelled[0].tick, cancelled[0].market_id) == (7, "M1")
    assert cancelled[0].reason == "event voided by the organiser"
    assert exchange.status("M1") is MarketStatus.CANCELLED
    assert (report.outcome, report.payout_cents) == (None, 0)
    # A cancelled market is never also resolved.
    assert not [event for event in tmp_journal.events if isinstance(event, MarketResolved)]
    assert oracle.due_market_ids(TICKS + 1) == ("M2",)


def test_cancel_unwinds_everything(tmp_journal) -> None:
    """FR-5.4.5: the unwind restores the cash exactly and leaves every position flat."""
    config = _config(taker_fee_bps=0)
    world = _world(
        config,
        resolution_ticks=(TICKS, TICKS),
        outcomes=(Outcome.YES, Outcome.NO),
        cancellations=((7, "M1", "void"),),
    )
    exchange, accounts, oracle = _arena(config, world, tmp_journal)

    exchange.begin_tick(7)
    _cross(exchange, price=37, qty=13, tick=7)
    _place(exchange, agent_id="A3", side=Side.BUY, price=20, qty=5, tick=7, item_index=2)
    assert accounts.cash_cents("A1") != config.initial_cash_cents
    assert accounts.position("A2", "M1").qty == -13

    oracle.cancel_market(
        tick=7,
        market_id="M1",
        reason="void",
        exchange=exchange,
        accounts=accounts,
        journal=tmp_journal,
    )

    settlements = [event for event in _events(tmp_journal, SettlementApplied) if event.mode == "unwind"]
    # The two counterparties plus the FEES line section 6.4 always closes an unwind with.
    assert [event.account_id for event in settlements] == ["A1", "A2", "FEES"]
    assert sum(event.cash_delta_cents for event in settlements) == 0
    for account_id in accounts.account_ids():
        assert accounts.position(account_id, "M1").qty == 0
        assert accounts.reserved_cents(account_id) == 0
    for index in range(1, config.n_agents + 1):
        agent_id = make_agent_id(index)
        assert accounts.cash_cents(agent_id) == config.initial_cash_cents
    assert accounts.cash_cents("FEES") == 0
    assert accounts.total_cash_cents() == accounts.initial_total_cash_cents()


def test_cancelling_twice_is_refused(tmp_journal) -> None:
    """A cancelled market is closed for good, like a resolved one."""
    config = _config()
    world = _world(config, resolution_ticks=(TICKS, TICKS), outcomes=(Outcome.YES, Outcome.NO))
    exchange, accounts, oracle = _arena(config, world, tmp_journal)
    oracle.cancel_market(
        tick=7, market_id="M1", reason="void", exchange=exchange, accounts=accounts, journal=tmp_journal
    )
    with pytest.raises(InvalidConfigError):
        oracle.cancel_market(
            tick=8, market_id="M1", reason="void", exchange=exchange, accounts=accounts, journal=tmp_journal
        )
    with pytest.raises(InvalidConfigError):
        oracle.resolve(tick=TICKS + 1, market_id="M1", exchange=exchange, accounts=accounts, journal=tmp_journal)
    assert len(_events(tmp_journal, MarketCancelled)) == 1


def test_cancellation_releases_the_resting_collateral(tmp_journal) -> None:
    """The orders leave through OrderCancelled(MARKET_CANCELLED), which carries the money."""
    config = _config()
    world = _world(
        config,
        resolution_ticks=(TICKS, TICKS),
        outcomes=(Outcome.YES, Outcome.NO),
        cancellations=((7, "M1", "void"),),
    )
    exchange, accounts, oracle = _arena(config, world, tmp_journal)
    exchange.begin_tick(7)
    _place(exchange, agent_id="A1", side=Side.BUY, price=45, qty=8, tick=7)
    assert accounts.reserved_cents("A1") == 45 * 8

    oracle.cancel_market(
        tick=7, market_id="M1", reason="void", exchange=exchange, accounts=accounts, journal=tmp_journal
    )
    cancelled = _events(tmp_journal, OrderCancelled)
    assert [event.reason for event in cancelled] == [CancelReason.MARKET_CANCELLED]
    assert cancelled[0].released_cents == 45 * 8
    assert accounts.reserved_cents("A1") == 0


# ---------------------------------------------------------------------------
# The same rules against a really generated world (A03), not a hand built one
# ---------------------------------------------------------------------------
def test_generated_world_resolves_at_its_own_tick(tiny_world, tmp_journal) -> None:
    """Every market of a generated world matures at its own tick, and only there."""
    config = MatchConfig(seed=20260827, ticks_total=tiny_world.scenario.ticks_total, n_agents=AGENTS, n_markets=2)
    exchange, accounts, oracle = _arena(config, tiny_world, tmp_journal)
    resolved_at: dict[str, int] = {}
    for tick in range(1, config.ticks_total + 2):
        exchange.begin_tick(min(tick, config.ticks_total))
        for market_id in oracle.due_market_ids(tick):
            report = oracle.resolve(
                tick=tick,
                market_id=market_id,
                exchange=exchange,
                accounts=accounts,
                journal=tmp_journal,
            )
            assert report.outcome is tiny_world.outcome(market_id)
            resolved_at[market_id] = tick

    resolved = _events(tmp_journal, MarketResolved)
    assert len(resolved) == len(tiny_world.market_ids())
    for event in resolved:
        spec = tiny_world.scenario.market(event.market_id)
        assert event.resolution_tick == spec.resolution_tick
        assert event.tick == spec.resolution_tick + 1
        assert resolved_at[event.market_id] == event.tick
    accounts.check_final_invariant()
