"""A10: the observation builder is faithful, compact and outside the journal.

Five claims, and they are independent (CONTRACTS sections 7.13, 8.1 and 5.0,
PRD section 6.1, WBS T2.4):

1. **Fidelity is absolute.** Every resting order of the agent and every non flat
   position it holds on an open market round trips exactly into the payload,
   order id, side, price and remaining quantity included. This is the half of
   T2.4 that compaction may never touch.
2. **The payload is compact.** At the median tick of a real world, over a real
   book, the documented counting rule of ``estimate_tokens`` stays under 2000.
3. **Section 5.0 decides which markets appear.** A market whose
   ``resolution_tick`` is ``r`` is in the tick ``r`` observation and gone at
   ``r + 1``; when every market has resolved the ``markets`` array is empty and
   the payload is still schema valid.
4. **The public prior is visible at tick 1** (FR-5.2.4), which is the only
   reference price a market has before anybody trades.
5. **``obs_hash`` and ``obs_bytes`` live in ``observations.jsonl`` and nowhere
   else** (section 3.5, decision 11), so recompacting cannot move a journal
   hash.

The arena below is built from the real world generator, the real
``AccountBook``, the real ``Exchange`` and a real ``Journal``: the book is
filled by actual order flow, never by forging an ``Order`` or an
``AccountState``. Every test that looks at that journal first asserts it is non
empty and holds at least one event of the type under test (section 10's
anti-vacuous rule).

``pxe.runner.state`` (A09) is landing in parallel with A10. The local
``StubMatchState`` mirrors the ``MatchState`` surface of section 7.12 that the
builder reads, so these tests exercise the real exchange and ledger without
waiting for it; ``test_build_observation_accepts_the_contracted_match_state``
then drives the same call through the real class behind ``importorskip``, so the
stub cannot quietly diverge from the contract.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any

import pytest

from pxe.errors import ObservationValidationError
from pxe.events import ObservationBuilt, OrderPlaced, TradeExecuted, stable_json
from pxe.exchange.accounts import AccountBook
from pxe.exchange.exchange import Exchange
from pxe.info.engine import InfoEngine
from pxe.info.profiles import build_profile, default_profile_kinds
from pxe.journal import Journal
from pxe.rng import RngTree
from pxe.runner.observation_builder import (
    MESSAGES_MAX_ITEMS,
    TOKEN_BUDGET,
    TOKEN_CHARS_PER_TOKEN,
    build_observation,
    estimate_tokens,
    observation_bytes,
    observation_hash,
    observation_to_json,
    validate_observation,
    write_observation,
)
from pxe.types import (
    DEFAULT_PREDICTION_PPM,
    DEPTH_LEVELS,
    PRICE_MAX,
    PRICE_MIN,
    CancelReason,
    InfoProfileKind,
    MarketStatus,
    MatchConfig,
    Order,
    OrderIntent,
    OrderType,
    Outcome,
    PublicMessage,
    ScenarioSpec,
    Side,
    make_agent_id,
    ppm_from_prob,
    prob_from_ppm,
    sorted_ids,
)
from pxe.world.generator import World, generate_world

SEED = 20260827
TICKS = 48
MARKETS = 5
AGENTS = 6
#: The tick T2.4 states the budget at. With the PRD default horizon of 48 it is
#: tick 24, and the arena below has traded, quoted and rested by then.
MEDIAN_TICK = TICKS // 2
QTY = 10


# ---------------------------------------------------------------------------
# The MatchState surface A10 reads (CONTRACTS section 7.12)
# ---------------------------------------------------------------------------
@dataclass
class StubMatchState:
    """Exactly the fields and methods of ``MatchState`` the builder touches."""

    config: MatchConfig
    scenario: ScenarioSpec
    match_id: str
    tick: int
    accounts: AccountBook
    exchange: Exchange
    outcomes: dict[str, Outcome] = field(default_factory=dict)
    last_prediction_ppm: dict[tuple[str, str], int] = field(default_factory=dict)
    pending_messages: tuple[PublicMessage, ...] = ()
    frozen_agent_ids: frozenset[str] = frozenset()

    def open_market_ids(self) -> tuple[str, ...]:
        return sorted_ids(self.exchange.open_market_ids())

    def ref_prices(self) -> dict[str, int]:
        return {mid: self.exchange.reference_price(mid)[0] for mid in self.open_market_ids()}

    def ranked_agent_ids(self) -> tuple[str, ...]:
        return self.accounts.ranked_agent_ids()

    def active_agent_ids(self) -> tuple[str, ...]:
        return tuple(a for a in self.ranked_agent_ids() if a not in self.frozen_agent_ids)

    def resting_order_ids(self, agent_id: str) -> tuple[str, ...]:
        view = self.exchange.book_view()
        out: list[str] = []
        for market_id in sorted_ids(tuple(view.keys())):
            out.extend(o.order_id for o in view[market_id] if o.agent_id == agent_id)
        return tuple(out)


@dataclass
class Arena:
    """A real world, a real ledger, a real book and the state built over them."""

    config: MatchConfig
    world: World
    journal: Journal
    accounts: AccountBook
    exchange: Exchange
    state: StubMatchState
    info: InfoEngine

    def agent_ids(self) -> tuple[str, ...]:
        return tuple(make_agent_id(index) for index in range(1, AGENTS + 1))

    def priors(self) -> dict[str, int]:
        return {spec.market_id: spec.prior_price for spec in self.world.scenario.markets}

    def resting(self, agent_id: str) -> dict[str, tuple[Order, ...]]:
        view = self.exchange.book_view()
        out: dict[str, tuple[Order, ...]] = {}
        for market_id in sorted_ids(tuple(view.keys())):
            mine = tuple(o for o in view[market_id] if o.agent_id == agent_id)
            if mine:
                out[market_id] = mine
        return out

    def observation(self, agent_id: str = "A1", *, tick: int | None = None, messages: tuple[PublicMessage, ...] = ()):
        at = self.state.tick if tick is None else tick
        return build_observation(
            config=self.config,
            state=self.state,
            agent_id=agent_id,
            tick=at,
            news=self.info.news_for_tick(at),
            signals=self.info.signals_for_tick(at),
            messages=messages,
        )


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------
def _config(**overrides: Any) -> MatchConfig:
    base: dict[str, Any] = {"seed": SEED, "ticks_total": TICKS, "n_agents": AGENTS, "n_markets": MARKETS}
    base.update(overrides)
    return MatchConfig(**base)


def _info_engine(world: World, config: MatchConfig) -> InfoEngine:
    market_ids = world.market_ids()
    kinds = default_profile_kinds(AGENTS)
    profiles = {}
    for index, kind in enumerate(kinds, start=1):
        agent_id = make_agent_id(index)
        focus = market_ids[(index - 1) % len(market_ids)] if kind is InfoProfileKind.SPECIALIST else None
        profiles[agent_id] = build_profile(kind, market_ids=market_ids, focus_market_id=focus)
    return InfoEngine(world=world, profiles=profiles, rng=RngTree(config.seed).child("info"), ticks_total=TICKS)


def _place(
    exchange: Exchange,
    *,
    tick: int,
    agent_id: str,
    market_id: str,
    side: Side,
    price: int,
    qty: int = QTY,
    item_index: int = 0,
) -> None:
    exchange.submit(
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


def _arena(**config_overrides: Any) -> Arena:
    """A five market, forty-eight tick election world driven to the median tick.

    The book is filled by real submissions: two crossing pairs create positions
    and a cost basis, then every seat rests one bid and one ask per market at a
    price of its own, which gives more than ``DEPTH_LEVELS`` levels per side and
    a full ``ref_history``.
    """
    config = _config(**config_overrides)
    world = generate_world(template_id="election", seed=SEED, ticks_total=TICKS, n_markets=MARKETS)
    journal = Journal("m-election-20260827-01")
    agent_ids = tuple(make_agent_id(index) for index in range(1, AGENTS + 1))
    accounts = AccountBook(agent_ids=agent_ids, market_ids=world.market_ids(), config=config)
    exchange = Exchange(config=config, scenario=world.scenario, accounts=accounts, journal=journal)
    priors = {spec.market_id: spec.prior_price for spec in world.scenario.markets}

    # Two executions per market: A1 lifts A2, A4 lifts A3. Everyone ends the
    # tick with a position, a cost basis and something to mark to market.
    exchange.begin_tick(1)
    for market_id, prior in priors.items():
        cross = min(PRICE_MAX, prior + AGENTS + 1)
        _place(exchange, tick=1, agent_id="A2", market_id=market_id, side=Side.SELL, price=cross)
        _place(exchange, tick=1, agent_id="A1", market_id=market_id, side=Side.BUY, price=cross, item_index=1)
        _place(exchange, tick=1, agent_id="A3", market_id=market_id, side=Side.SELL, price=cross, item_index=2)
        _place(exchange, tick=1, agent_id="A4", market_id=market_id, side=Side.BUY, price=cross, item_index=3)

    # One bid and one ask per seat per market, never crossing: every bid sits
    # below the prior and every ask above it.
    for index, agent_id in enumerate(agent_ids, start=1):
        for market_id, prior in priors.items():
            _place(
                exchange,
                tick=1,
                agent_id=agent_id,
                market_id=market_id,
                side=Side.BUY,
                price=max(PRICE_MIN, prior - index),
            )
            _place(
                exchange,
                tick=1,
                agent_id=agent_id,
                market_id=market_id,
                side=Side.SELL,
                price=min(PRICE_MAX, prior + index),
                item_index=1,
            )

    # Walk the ticks so the sparkline is full at the median tick.
    for tick in range(1, MEDIAN_TICK + 1):
        exchange.begin_tick(tick)
        for market_id in world.market_ids():
            exchange.push_ref_history(market_id, exchange.reference_price(market_id)[0])

    state = StubMatchState(
        config=config,
        scenario=world.scenario,
        match_id=journal.match_id,
        tick=MEDIAN_TICK,
        accounts=accounts,
        exchange=exchange,
        outcomes={},
        last_prediction_ppm={
            (agent_id, market_id): ppm_from_prob(0.375)
            for agent_id in agent_ids[:3]
            for market_id in world.market_ids()
        },
    )
    return Arena(
        config=config,
        world=world,
        journal=journal,
        accounts=accounts,
        exchange=exchange,
        state=state,
        info=_info_engine(world, config),
    )


def _events(journal: Journal, event_cls: type) -> list[Any]:
    """Return every event of one type, after the two anti-vacuous assertions."""
    assert journal.events, "the journal must not be empty before it is asserted on"
    found = [event for event in journal.events if isinstance(event, event_cls)]
    assert found, f"no {event_cls.__name__} was journalled: the assertions below would be vacuous"
    return found


# ---------------------------------------------------------------------------
# T2.4, first half: fidelity
# ---------------------------------------------------------------------------
def test_all_resting_orders_and_positions_present() -> None:
    """100 % of the agent's resting orders and positions round trip (T2.4)."""
    arena = _arena()
    assert len(_events(arena.journal, OrderPlaced)) > AGENTS * MARKETS
    assert _events(arena.journal, TradeExecuted), "the arena must have traded, or positions would be vacuous"

    for agent_id in arena.agent_ids():
        payload = observation_to_json(arena.observation(agent_id))
        validate_observation(payload)
        blocks = {block["market_id"]: block for block in payload["markets"]}
        expected = arena.resting(agent_id)

        # Every market the agent rests an order on is a market it can see, and
        # the two sets of orders are equal, not merely overlapping.
        assert set(expected) <= set(blocks), f"{agent_id} rests orders on a market it cannot see"
        seen_orders = 0
        seen_positions = 0
        for market_id, block in blocks.items():
            wire = {(o["order_id"], o["side"], o["price"], o["qty_remaining"]) for o in block["my_orders"]}
            truth = {
                (o.order_id, o.side.value, o.price, o.remaining_qty)
                for o in expected.get(market_id, ())
                if o.status.is_resting
            }
            assert wire == truth, f"{agent_id} on {market_id}: orders lost or invented"
            seen_orders += len(truth)

            position = arena.accounts.position(agent_id, market_id)
            assert block["position_qty"] == position.qty
            assert block["cost_basis_cents"] == position.cost_basis_cents
            seen_positions += 1 if position.qty != 0 else 0

        assert seen_orders >= 2 * MARKETS, f"{agent_id} should rest at least one bid and one ask per market"
        if agent_id in ("A1", "A2", "A3", "A4"):
            assert seen_positions == MARKETS, f"{agent_id} traded every market and must show every position"


def test_a_short_position_is_reported_with_its_negative_quantity() -> None:
    """A2 sold to A1 on every market, so its blocks carry a negative quantity."""
    arena = _arena()
    assert _events(arena.journal, TradeExecuted)
    payload = observation_to_json(arena.observation("A2"))
    quantities = [block["position_qty"] for block in payload["markets"]]
    assert quantities, "no market block, the assertion below would be vacuous"
    assert all(qty < 0 for qty in quantities), quantities
    assert all(block["cost_basis_cents"] < 0 for block in payload["markets"])


# ---------------------------------------------------------------------------
# T2.4, second half: the token budget
# ---------------------------------------------------------------------------
def test_median_tick_under_two_thousand_tokens() -> None:
    """Under 2000 estimated tokens at the median tick, for every seat (T2.4).

    The counting rule is the documented one of ``estimate_tokens``:
    ``ceil(len(stable_json(payload)) / 3.6)`` characters of the exact payload
    that crosses the boundary. It is provider independent on purpose, so this
    budget cannot move when a tokeniser is updated.
    """
    arena = _arena()
    assert _events(arena.journal, OrderPlaced)
    for agent_id in arena.agent_ids():
        payload = observation_to_json(arena.observation(agent_id))
        validate_observation(payload)
        assert payload["markets"], "an empty observation would make this budget meaningless"
        assert payload["markets"][0]["my_orders"], "fidelity first: the budget is measured with the orders in"
        tokens = estimate_tokens(payload)
        assert tokens < TOKEN_BUDGET, f"{agent_id}: {tokens} estimated tokens at tick {MEDIAN_TICK}"


def test_median_tick_stays_in_budget_with_talking_mode_on() -> None:
    """The talking mode variant also fits: eight maximal messages cost little."""
    arena = _arena(talking_mode=True)
    assert _events(arena.journal, OrderPlaced)
    messages = tuple(
        PublicMessage(
            agent_id=make_agent_id(index),
            tick=MEDIAN_TICK - 1,
            text="x" * arena.config.message_max_chars,
            deliver_tick=MEDIAN_TICK,
        )
        for index in range(2, AGENTS + 1)
    )
    payload = observation_to_json(arena.observation("A1", messages=messages))
    validate_observation(payload)
    assert len(payload["messages"]) == AGENTS - 1
    assert estimate_tokens(payload) < TOKEN_BUDGET


def test_fidelity_wins_over_the_budget_when_the_book_is_saturated() -> None:
    """The 2000 token target is a median tick budget, fidelity is a hard rule.

    At the I8 ceiling (``max_active_orders_per_market`` orders on every market)
    the payload legitimately exceeds the budget, and every single order is still
    there: T2.4 says "100 % of the agent's active orders", with no exception for
    a large book. This test exists so a future compaction pass cannot buy tokens
    by dropping orders.
    """
    arena = _arena(max_active_orders_per_market=20, ref_history_len=32)
    cap = arena.config.max_active_orders_per_market
    for market_id, prior in arena.priors().items():
        for index in range(cap - 2):
            _place(
                arena.exchange,
                tick=MEDIAN_TICK,
                agent_id="A1",
                market_id=market_id,
                side=Side.BUY,
                price=max(PRICE_MIN, min(PRICE_MAX, prior - 20 + index)),
                qty=1,
                item_index=index,
            )
    payload = observation_to_json(arena.observation("A1"))
    validate_observation(payload)
    total = sum(len(block["my_orders"]) for block in payload["markets"])
    assert total == cap * MARKETS, total
    assert estimate_tokens(payload) > TOKEN_BUDGET, "the point of this test is a payload over the budget"
    expected = {order.order_id for orders in arena.resting("A1").values() for order in orders}
    seen = {order["order_id"] for block in payload["markets"] for order in block["my_orders"]}
    assert seen == expected


def test_estimate_tokens_follows_the_documented_rule() -> None:
    """The rule is the specification, so it is asserted directly."""
    payload = {"a": "b", "list": [1, 2, 3]}
    expected = math.ceil(len(stable_json(payload)) / TOKEN_CHARS_PER_TOKEN)
    assert estimate_tokens(payload) == expected
    assert estimate_tokens({}) == 1
    # Monotone in payload size, which is what makes it usable as a budget.
    assert estimate_tokens({"a": "b" * 400}) > estimate_tokens({"a": "b"})


# ---------------------------------------------------------------------------
# Section 5.0: which markets appear
# ---------------------------------------------------------------------------
def test_market_present_on_its_resolution_tick() -> None:
    """A market with ``resolution_tick == r`` is in the tick ``r`` observation.

    It leaves the payload only once the oracle has closed it, which P1 step 4
    of tick ``r + 1`` does before the observations of that tick are built.
    """
    arena = _arena()
    assert _events(arena.journal, OrderPlaced)
    target = arena.world.scenario.markets[0].market_id
    resolution_tick = arena.world.scenario.markets[0].resolution_tick

    arena.state.tick = resolution_tick
    present = observation_to_json(arena.observation("A1", tick=resolution_tick))
    ids = [block["market_id"] for block in present["markets"]]
    assert ids, "no market block, the assertion below would be vacuous"
    assert target in ids
    block = next(b for b in present["markets"] if b["market_id"] == target)
    assert block["resolution_tick"] == resolution_tick
    assert block["status"] == "open"

    arena.exchange.cancel_all(tick=resolution_tick + 1, market_id=target, reason=CancelReason.MARKET_RESOLVED)
    arena.exchange.close_market(tick=resolution_tick + 1, market_id=target, status=MarketStatus.RESOLVED)
    arena.state.tick = resolution_tick + 1
    after = observation_to_json(arena.observation("A1", tick=resolution_tick + 1))
    validate_observation(after)
    assert target not in [block["market_id"] for block in after["markets"]]


def test_observation_valid_when_all_markets_resolved() -> None:
    """An empty ``markets`` array is legal (FR-5.2.3, ``minItems: 0``)."""
    arena = _arena()
    assert _events(arena.journal, OrderPlaced)
    tick = TICKS
    for market_id in arena.world.market_ids():
        arena.exchange.cancel_all(tick=tick, market_id=market_id, reason=CancelReason.MARKET_RESOLVED)
        arena.exchange.close_market(tick=tick, market_id=market_id, status=MarketStatus.RESOLVED)
    arena.state.tick = tick
    payload = observation_to_json(arena.observation("A1", tick=tick))
    validate_observation(payload)
    assert payload["markets"] == []
    assert payload["signals"] == [], "a signal about a closed market would dangle"
    assert payload["free_cash_cents"] == arena.accounts.free_cash_cents("A1")


def test_signals_are_never_leaked_across_agents() -> None:
    """Only the recipient's own signals appear, and only about open markets."""
    arena = _arena()
    assert _events(arena.journal, OrderPlaced)
    raw = arena.info.signals_for_tick(MEDIAN_TICK)
    assert raw, "the info engine delivered nothing at the median tick, this test would be vacuous"
    for agent_id in arena.agent_ids():
        payload = observation_to_json(arena.observation(agent_id))
        ids = {signal["signal_id"] for signal in payload["signals"]}
        mine = {s.signal_id for s in raw if s.agent_id == agent_id}
        assert ids == mine, agent_id
        open_ids = set(arena.state.open_market_ids())
        assert all(signal["market_id"] in open_ids for signal in payload["signals"])


# ---------------------------------------------------------------------------
# FR-5.2.4: the public prior
# ---------------------------------------------------------------------------
def test_prior_visible_at_tick_one() -> None:
    """Every market shows its public prior, and it is the tick 1 reference price."""
    config = _config()
    world = generate_world(template_id="election", seed=SEED, ticks_total=TICKS, n_markets=MARKETS)
    journal = Journal("m-election-20260827-01")
    agent_ids = tuple(make_agent_id(index) for index in range(1, AGENTS + 1))
    accounts = AccountBook(agent_ids=agent_ids, market_ids=world.market_ids(), config=config)
    exchange = Exchange(config=config, scenario=world.scenario, accounts=accounts, journal=journal)
    exchange.begin_tick(1)
    state = StubMatchState(
        config=config,
        scenario=world.scenario,
        match_id=journal.match_id,
        tick=1,
        accounts=accounts,
        exchange=exchange,
    )
    obs = build_observation(config=config, state=state, agent_id="A1", tick=1, news=(), signals=(), messages=())
    payload = observation_to_json(obs)
    validate_observation(payload)

    priors = {spec.market_id: spec.prior_price for spec in world.scenario.markets}
    assert len(payload["markets"]) == MARKETS
    for block in payload["markets"]:
        assert block["prior_price"] == priors[block["market_id"]]
        # Nothing has traded and the book is empty, so FR-5.4.6 falls back to
        # the prior: that is what makes the prior "visible" and not merely
        # present.
        assert block["ref_price"] == block["prior_price"]
        assert block["best_bid"] is None
        assert block["best_ask"] is None
        assert block["mid_price"] is None
        assert block["last_price"] is None
        assert block["ref_history"] == []
        assert block["my_orders"] == []
        assert block["position_qty"] == 0
        assert block["my_last_prediction"] == prob_from_ppm(DEFAULT_PREDICTION_PPM)


# ---------------------------------------------------------------------------
# Compaction levers: depth, ref_history, text
# ---------------------------------------------------------------------------
def test_depth_is_capped_at_three_levels() -> None:
    """Depth is a legal compaction lever, and three is the schema ceiling."""
    arena = _arena()
    assert _events(arena.journal, OrderPlaced)
    payload = observation_to_json(arena.observation("A1"))
    deep = [b for b in payload["markets"] if len(b["bid_depth"]) == DEPTH_LEVELS]
    assert deep, "the arena must rest more than three bid levels somewhere"
    for block in payload["markets"]:
        assert len(block["bid_depth"]) <= DEPTH_LEVELS
        assert len(block["ask_depth"]) <= DEPTH_LEVELS
        assert all(len(level) == 2 for level in block["bid_depth"] + block["ask_depth"])
        prices = [level[0] for level in block["bid_depth"]]
        assert prices == sorted(prices, reverse=True), "bids are best first"
        asks = [level[0] for level in block["ask_depth"]]
        assert asks == sorted(asks), "asks are best first"


def test_ref_history_is_capped_at_the_config_length() -> None:
    """``ref_history_len`` is the second lever, and the payload echoes it."""
    arena = _arena()
    assert _events(arena.journal, OrderPlaced)
    payload = observation_to_json(arena.observation("A1"))
    lengths = {len(block["ref_history"]) for block in payload["markets"]}
    assert lengths == {arena.config.ref_history_len}, lengths
    assert all(PRICE_MIN <= price <= PRICE_MAX for block in payload["markets"] for price in block["ref_history"])

    short = _arena(ref_history_len=3)
    assert {len(b["ref_history"]) for b in observation_to_json(short.observation("A1"))["markets"]} == {3}


def test_limits_echo_the_config_and_never_exceed_the_action_schema() -> None:
    """``limits`` is how an agent self polices (CONTRACTS section 8.2)."""
    arena = _arena()
    limits = observation_to_json(arena.observation("A1"))["limits"]
    assert limits == {
        "max_active_orders_per_market": arena.config.max_active_orders_per_market,
        "price_min": PRICE_MIN,
        "price_max": PRICE_MAX,
        "market_band_cents": arena.config.market_band_cents,
        "taker_fee_bps": arena.config.taker_fee_bps,
        "message_max_chars": arena.config.message_max_chars,
        "max_orders_per_action": arena.config.max_orders_per_action,
    }
    assert limits["max_orders_per_action"] <= 20


# ---------------------------------------------------------------------------
# FR-5.6.1: the public channel
# ---------------------------------------------------------------------------
def test_messages_are_empty_when_talking_mode_is_off() -> None:
    """Talking mode off means an empty channel, whatever the runner hands over."""
    arena = _arena()
    message = PublicMessage(agent_id="A2", tick=MEDIAN_TICK - 1, text="buy M1", deliver_tick=MEDIAN_TICK)
    payload = observation_to_json(arena.observation("A1", messages=(message,)))
    validate_observation(payload)
    assert payload["messages"] == []


def test_messages_of_this_tick_are_delivered_to_the_other_agents() -> None:
    """A message posted at ``t`` reaches the others at ``t + 1``, never its author.

    The ``deliver_tick`` bound is inclusive, which is the predicate the runner
    itself uses to drain the queue: an item already due cannot be popped by the
    runner and dropped here. An item still ahead is never shown.
    """
    arena = _arena(talking_mode=True)
    mine = PublicMessage(agent_id="A1", tick=MEDIAN_TICK - 1, text="mine", deliver_tick=MEDIAN_TICK)
    theirs = PublicMessage(agent_id="A3", tick=MEDIAN_TICK - 1, text="theirs", deliver_tick=MEDIAN_TICK)
    overdue = PublicMessage(agent_id="A2", tick=MEDIAN_TICK - 3, text="overdue", deliver_tick=MEDIAN_TICK - 2)
    future = PublicMessage(agent_id="A4", tick=MEDIAN_TICK, text="not yet", deliver_tick=MEDIAN_TICK + 1)
    payload = observation_to_json(arena.observation("A1", messages=(theirs, mine, future, overdue)))
    validate_observation(payload)
    assert payload["messages"] == [
        {"agent_id": "A2", "text": "overdue"},
        {"agent_id": "A3", "text": "theirs"},
    ]


def test_messages_are_truncated_and_capped() -> None:
    """Text length is the third compaction lever, and eight is the item ceiling."""
    arena = _arena(talking_mode=True, message_max_chars=16)
    messages = tuple(
        PublicMessage(
            agent_id=make_agent_id(index),
            tick=MEDIAN_TICK - 1,
            text="z" * 200,
            deliver_tick=MEDIAN_TICK,
        )
        for index in range(2, AGENTS + 1)
    )
    payload = observation_to_json(arena.observation("A1", messages=messages))
    validate_observation(payload)
    assert len(payload["messages"]) <= MESSAGES_MAX_ITEMS
    assert payload["messages"], "no message survived, the assertion below would be vacuous"
    assert all(len(entry["text"]) == 16 for entry in payload["messages"])
    authors = [entry["agent_id"] for entry in payload["messages"]]
    assert authors == list(sorted_ids(tuple(authors)))


# ---------------------------------------------------------------------------
# Decision 11: the digest lives outside the journal
# ---------------------------------------------------------------------------
def test_hash_and_bytes_are_stable_and_agree_with_the_payload() -> None:
    """Two renderings of the same observation give the same digest and size."""
    arena = _arena()
    assert _events(arena.journal, OrderPlaced)
    left = arena.observation("A1")
    right = arena.observation("A1")
    assert observation_hash(left) == observation_hash(right)
    assert len(observation_hash(left)) == 64
    assert observation_bytes(left) == len(stable_json(observation_to_json(left)).encode("utf-8"))
    assert observation_bytes(left) > 0
    other = arena.observation("A2")
    assert observation_hash(other) != observation_hash(left), "two seats see two payloads"


def test_observation_built_event_carries_no_digest() -> None:
    """``ObservationBuilt`` has no ``obs_hash`` and no ``obs_bytes`` (section 3.5)."""
    fields = set(ObservationBuilt.__dataclass_fields__)
    assert "obs_hash" not in fields
    assert "obs_bytes" not in fields
    assert {"agent_id", "obs_version", "n_markets", "n_news", "n_signals"} <= fields


def test_write_observation_appends_the_five_contracted_keys(tmp_path) -> None:
    """``observations.jsonl`` holds the five keys of section 7.13, LF terminated."""
    arena = _arena()
    assert _events(arena.journal, OrderPlaced)
    path = tmp_path / "runs" / arena.state.match_id / "observations.jsonl"
    first = arena.observation("A1")
    second = arena.observation("A2")
    write_observation(path, first)
    write_observation(path, second)

    raw = path.read_bytes()
    assert b"\r" not in raw, "CONTRACTS section 4.2: no carriage return in an artefact"
    lines = raw.decode("utf-8").split("\n")
    assert lines[-1] == "", "every line is newline terminated"
    records = [json.loads(line) for line in lines[:-1]]
    assert len(records) == 2
    assert set(records[0]) == {"agent_id", "tick", "obs_hash", "obs_bytes", "payload"}
    assert records[0]["agent_id"] == "A1"
    assert records[1]["agent_id"] == "A2"
    assert records[0]["tick"] == MEDIAN_TICK
    assert records[0]["obs_hash"] == observation_hash(first)
    assert records[0]["obs_bytes"] == observation_bytes(first)
    assert records[0]["payload"] == observation_to_json(first)
    validate_observation(records[0]["payload"])


# ---------------------------------------------------------------------------
# validate_observation is the engine bug guard
# ---------------------------------------------------------------------------
def test_validate_observation_accepts_what_the_builder_produces() -> None:
    """Every seat, at three different ticks, produces a schema valid payload."""
    arena = _arena()
    assert _events(arena.journal, OrderPlaced)
    checked = 0
    for tick in (1, MEDIAN_TICK, TICKS):
        arena.state.tick = tick
        for agent_id in arena.agent_ids():
            validate_observation(observation_to_json(arena.observation(agent_id, tick=tick)))
            checked += 1
    assert checked == 3 * AGENTS


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ({"obs_version": "9.9"}, "wrong version"),
        ({"tick": 0}, "tick is 1 based"),
        ({"agent_id": "MM"}, "MM never receives an observation"),
        ({"cash_cents": -1}, "cash is never negative"),
        ({"limits": {}}, "limits is fully required"),
        ({"unknown": 1}, "additionalProperties is false"),
    ],
)
def test_validate_observation_rejects_a_broken_payload(mutation: dict[str, Any], reason: str) -> None:
    """A payload the schema refuses is an engine bug and must raise."""
    arena = _arena()
    payload = observation_to_json(arena.observation("A1"))
    validate_observation(payload)  # the baseline must be valid, or this proves nothing
    payload.update(mutation)
    with pytest.raises(ObservationValidationError):
        validate_observation(payload)


def test_prediction_carry_is_echoed_back() -> None:
    """``my_last_prediction`` shows the carried value (FR-6.2.4)."""
    arena = _arena()
    payload = observation_to_json(arena.observation("A1"))
    assert payload["markets"], "vacuous otherwise"
    assert all(block["my_last_prediction"] == 0.375 for block in payload["markets"])
    # A seat that never declared anything sees the 500_000 ppm default.
    other = observation_to_json(arena.observation("A6"))
    assert all(block["my_last_prediction"] == prob_from_ppm(DEFAULT_PREDICTION_PPM) for block in other["markets"])


# ---------------------------------------------------------------------------
# A09 integration: the real MatchState
# ---------------------------------------------------------------------------
def test_build_observation_accepts_the_contracted_match_state() -> None:
    """The builder runs against the real ``MatchState`` of section 7.12.

    Skips until A09 lands ``pxe/runner/state.py``, which is what section 10's
    marker rule asks for: never a test that silently passes on nothing.
    """
    from pxe.runner import state as state_mod

    arena = _arena()
    assert _events(arena.journal, OrderPlaced)
    state = state_mod.MatchState(
        config=arena.config,
        scenario=arena.world.scenario,
        match_id=arena.state.match_id,
        tick=MEDIAN_TICK,
        accounts=arena.accounts,
        exchange=arena.exchange,
        outcomes={},
        last_prediction_ppm=dict(arena.state.last_prediction_ppm),
        pending_messages=(),
        frozen_agent_ids=frozenset(),
    )
    obs = build_observation(
        config=arena.config,
        state=state,
        agent_id="A1",
        tick=MEDIAN_TICK,
        news=arena.info.news_for_tick(MEDIAN_TICK),
        signals=arena.info.signals_for_tick(MEDIAN_TICK),
        messages=(),
    )
    payload = observation_to_json(obs)
    validate_observation(payload)
    assert estimate_tokens(payload) < TOKEN_BUDGET
    stub_payload = observation_to_json(arena.observation("A1"))
    assert payload == stub_payload, "the real MatchState and the contracted surface must agree"
