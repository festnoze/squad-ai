"""A09 acceptance tests for the P1..P4 tick loop (CONTRACTS sections 5 and 7.12).

This module also holds the **shared scripted match builder** the other three
A09 test files import (``test_determinism.py``, ``test_e2e_scripted_match.py``,
``test_replay.py``) and the three golden recipes of ``tests/golden/``. It lives
here rather than in a ``tests/helpers.py`` because A09 owns exactly four test
files plus ``tests/golden/`` (CONTRACTS section 13) and a fifth module would be
a file outside its row.

Every test below asserts on a non empty journal holding at least one event of
the type under test before it claims anything (section 10's anti-vacuous rule).
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

from pxe.agents.base import make_baseline
from pxe.errors import InvalidConfigError, PhaseOrderError
from pxe.events import (
    AgentActionReceived,
    AgentFrozen,
    AgentTimedOut,
    Event,
    MarketCancelled,
    MarkToMarket,
    MatchEnded,
    MatchStarted,
    ObservationBuilt,
    OrderPlaced,
    OrderRejected,
    PositionSnapshot,
    PredictionRecorded,
    SignalDelivered,
    STPCancelled,
    TickStarted,
)
from pxe.gateway.protocol import AgentReply
from pxe.gateway.scripted import ScriptedGateway
from pxe.info.profiles import build_profile, default_profile_kinds
from pxe.journal import Journal, verify_journal
from pxe.rng import RngTree
from pxe.runner.match_runner import MatchRunner, run_match
from pxe.types import (
    AgentAction,
    AgentSource,
    AgentSpec,
    HarnessConfig,
    InfoProfileKind,
    LiquidityProfileName,
    MatchConfig,
    MatchResult,
    Observation,
    OrderIntent,
    OrderType,
    PredictionIntent,
    RejectReason,
    Side,
    liquidity_profile,
    make_agent_id,
)
from pxe.world.generator import generate_world
from pxe.world.templates.base import World

# ---------------------------------------------------------------------------
# The shared builder
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Recipe:
    """A fully scripted match, reproducible from these six fields alone."""

    name: str
    template_id: str
    seed: int
    ticks_total: int
    n_markets: int
    baselines: tuple[str, ...]


#: The reference match: the PRD section 5.7 defaults and the ``standard_config``
#: seed, six baselines, forty-eight ticks, five markets. Every market of this
#: world resolves at ``T``, so it settles entirely in finalisation.
REFERENCE = Recipe(
    name="election_reference",
    template_id="election",
    seed=20260827,
    ticks_total=48,
    n_markets=5,
    baselines=("fundamentalist", "momentum", "noise", "zero_intelligence", "bayesian", "mute"),
)

#: The smallest legal match: four seats, three markets, twenty-four ticks.
SMALL = Recipe(
    name="harvest_small",
    template_id="harvest",
    seed=424242,
    ticks_total=24,
    n_markets=3,
    baselines=("fundamentalist", "bayesian", "momentum", "mute"),
)

#: The widest table, and the one whose world resolves a market **mid match**
#: (``M4`` at tick 22), so the P1 step 4 resolution path, its ``NewsPublished``
#: and its settlement are inside a golden hash rather than only in a unit test.
WIDE = Recipe(
    name="league_wide",
    template_id="league",
    seed=987654321,
    ticks_total=24,
    n_markets=4,
    baselines=(
        "fundamentalist",
        "momentum",
        "noise",
        "zero_intelligence",
        "bayesian",
        "mute",
        "fundamentalist",
        "momentum",
    ),
)

#: The three frozen scenarios of ``tests/golden/`` (CONTRACTS section 10).
GOLDEN_RECIPES: tuple[Recipe, ...] = (REFERENCE, SMALL, WIDE)

#: Directory holding the frozen journals and their hashes.
GOLDEN_DIR = Path(__file__).resolve().parent / "golden"


def match_id_of(recipe: Recipe) -> str:
    """Return the ``m-<template>-<seed>-01`` id of a recipe."""
    return f"m-{recipe.template_id}-{recipe.seed}-01"


def config_of(recipe: Recipe, **overrides: object) -> MatchConfig:
    """Build the ``MatchConfig`` of a recipe, with optional field overrides."""
    config = MatchConfig(
        seed=recipe.seed,
        ticks_total=recipe.ticks_total,
        n_agents=len(recipe.baselines),
        n_markets=recipe.n_markets,
    )
    return replace(config, **overrides) if overrides else config


def world_of(recipe: Recipe) -> World:
    """Generate the world of a recipe. A function of the seed alone."""
    return generate_world(
        template_id=recipe.template_id,
        seed=recipe.seed,
        ticks_total=recipe.ticks_total,
        n_markets=recipe.n_markets,
    )


def specs_of(recipe: Recipe, world: World) -> tuple[AgentSpec, ...]:
    """Build one ``AgentSpec`` per seat, with the default profile rotation."""
    kinds = default_profile_kinds(len(recipe.baselines))
    market_ids = world.market_ids()
    specs: list[AgentSpec] = []
    for index, name in enumerate(recipe.baselines, start=1):
        kind = kinds[index - 1]
        focus = market_ids[index % len(market_ids)] if kind is InfoProfileKind.SPECIALIST else None
        specs.append(
            AgentSpec(
                agent_id=make_agent_id(index),
                harness=HarnessConfig(harness_id=name, version="1.0.0", kind="scripted"),
                info_profile=build_profile(kind, market_ids=market_ids, focus_market_id=focus),
            )
        )
    return tuple(specs)


def agents_of(recipe: Recipe, config: MatchConfig, rng: RngTree) -> dict[str, object]:
    """Build one scripted baseline per seat, each on its own substream."""
    built: dict[str, object] = {}
    for index, name in enumerate(recipe.baselines, start=1):
        agent_id = make_agent_id(index)
        built[agent_id] = make_baseline(
            name,
            agent_id=agent_id,
            config=config,
            rng=rng.child(f"agent/{agent_id}").substream(f"agent.{agent_id}"),
        )
    return built


def build_runner(
    recipe: Recipe,
    *,
    journal: Journal,
    gateway: object | None = None,
    config: MatchConfig | None = None,
    world: World | None = None,
    rng: RngTree | None = None,
) -> MatchRunner:
    """Assemble a ``MatchRunner`` for a recipe, overriding any collaborator."""
    resolved_config = config if config is not None else config_of(recipe)
    resolved_world = world if world is not None else world_of(recipe)
    resolved_rng = rng if rng is not None else RngTree(resolved_config.seed)
    resolved_gateway = (
        gateway if gateway is not None else ScriptedGateway(agents=agents_of(recipe, resolved_config, resolved_rng))  # type: ignore[arg-type]
    )
    return MatchRunner(
        config=resolved_config,
        world=resolved_world,
        agents=specs_of(recipe, resolved_world),
        gateway=resolved_gateway,  # type: ignore[arg-type]
        journal=journal,
        match_id=journal.match_id,
        rng=resolved_rng,
    )


def play(
    recipe: Recipe,
    *,
    path: Path | None = None,
    gateway: object | None = None,
    config: MatchConfig | None = None,
    world: World | None = None,
    rng: RngTree | None = None,
) -> tuple[MatchResult, tuple[Event, ...]]:
    """Play a whole match and return its result together with its journal."""
    journal = Journal(match_id_of(recipe), path)
    runner = build_runner(recipe, journal=journal, gateway=gateway, config=config, world=world, rng=rng)
    result = runner.run()
    return result, journal.events


# ---------------------------------------------------------------------------
# Scripted agents that reach a specific engine state through real order flow
# ---------------------------------------------------------------------------
class Spendthrift:
    """Buys as much as it can afford every tick, so its free cash drains.

    It never forges an ``AccountState``: the state the FR-5.5.5 predicate sees
    is produced by real market orders matched by the real exchange.
    """

    def __init__(self, *, agent_id: str, config: MatchConfig, rng: object) -> None:
        self.agent_id = agent_id
        self._config = config

    def reset(self, *, config: MatchConfig, rng: object) -> None:
        self._config = config

    def act(self, observation: Observation) -> AgentAction:
        orders = tuple(
            OrderIntent(op="place", market_id=block.market_id, side=Side.BUY, order_type=OrderType.MARKET, qty=50)
            for block in observation.markets
        )
        return AgentAction(
            agent_id=self.agent_id,
            tick=observation.tick,
            action_version=self._config.action_version,
            predictions=tuple(
                PredictionIntent(market_id=block.market_id, p_yes_ppm=600_000) for block in observation.markets
            ),
            orders=orders,
        )


class SelfCrosser:
    """Rests a bid, then crosses it itself and cancels it in the same block.

    The self trade prevention of P3 step 11 removes the resting bid, so the
    cancel that follows in the very same block refers to an order the book no
    longer holds: exactly the "gone between P2 and P3" situation CONTRACTS
    section 7.14 says the **exchange** must reject, never the validator.
    """

    def __init__(self, *, agent_id: str, config: MatchConfig, rng: object) -> None:
        self.agent_id = agent_id
        self._config = config

    def reset(self, *, config: MatchConfig, rng: object) -> None:
        self._config = config

    def act(self, observation: Observation) -> AgentAction:
        orders: list[OrderIntent] = []
        for block in observation.markets[:1]:
            sells = [order for order in block.my_orders if order.side is Side.SELL]
            bids = [order for order in block.my_orders if order.side is Side.BUY]
            if sells:
                # Clear the residual of the previous crossing so the next bid
                # is the only resting order of this account.
                orders.extend(OrderIntent(op="cancel", order_id=order.order_id) for order in sells)
            elif bids:
                target = bids[0]
                orders.append(
                    OrderIntent(
                        op="place",
                        market_id=block.market_id,
                        side=Side.SELL,
                        order_type=OrderType.LIMIT,
                        price=target.price,
                        qty=target.remaining_qty,
                    )
                )
                orders.append(OrderIntent(op="cancel", order_id=target.order_id))
            else:
                # At the reference price the bid is strictly inside the market
                # maker spread, so it becomes the best bid and rests: the next
                # tick's sell at the same price therefore reaches it first and
                # self trade prevention removes it.
                orders.append(
                    OrderIntent(
                        op="place",
                        market_id=block.market_id,
                        side=Side.BUY,
                        order_type=OrderType.LIMIT,
                        price=min(98, max(2, block.ref_price)),
                        qty=5,
                    )
                )
        return AgentAction(
            agent_id=self.agent_id,
            tick=observation.tick,
            action_version=self._config.action_version,
            orders=tuple(orders),
        )


class Chatterbox:
    """Declares a prediction and posts a public message on every tick.

    Without it nothing in the suite exercises FR-5.6.1 end to end: not one of
    the six baselines ever sets ``message_public``, so ``MessagePosted``,
    ``MatchState.pending_messages`` and the next tick delivery would all be
    dead code that every test still passed over.
    """

    def __init__(self, *, agent_id: str, config: MatchConfig, rng: object) -> None:
        self.agent_id = agent_id
        self._config = config

    def reset(self, *, config: MatchConfig, rng: object) -> None:
        self._config = config

    def act(self, observation: Observation) -> AgentAction:
        return AgentAction(
            agent_id=self.agent_id,
            tick=observation.tick,
            action_version=self._config.action_version,
            predictions=tuple(
                PredictionIntent(market_id=block.market_id, p_yes_ppm=500_000) for block in observation.markets
            ),
            message_public=f"{self.agent_id} at tick {observation.tick}",
        )


class FailingGateway(ScriptedGateway):
    """A scripted gateway whose first seat always fails to answer (FR-5.1.1)."""

    def __init__(self, *, agents: dict[str, object], failing_agent_id: str) -> None:
        super().__init__(agents=agents)  # type: ignore[arg-type]
        self._failing = failing_agent_id

    async def acall_agent(self, *, agent_id: str, observation: Observation, tick: int) -> AgentReply:
        if agent_id == self._failing:
            from pxe.errors import ProviderError

            raise ProviderError("scripted provider outage", agent_id=agent_id)
        return await super().acall_agent(agent_id=agent_id, observation=observation, tick=tick)


def custom_recipe(*, baselines: tuple[str, ...], seed: int, ticks: int, markets: int, template: str) -> Recipe:
    """Build a one-off recipe for a test that needs a specific table."""
    return Recipe(
        name="custom",
        template_id=template,
        seed=seed,
        ticks_total=ticks,
        n_markets=markets,
        baselines=baselines,
    )


def play_with_agents(
    recipe: Recipe,
    *,
    factories: dict[str, object],
    config: MatchConfig | None = None,
    world: World | None = None,
    rng: RngTree | None = None,
) -> tuple[MatchResult, tuple[Event, ...]]:
    """Play a match whose seats are the given agent objects, keyed by seat id."""
    resolved_config = config if config is not None else config_of(recipe)
    resolved_world = world if world is not None else world_of(recipe)
    resolved_rng = rng if rng is not None else RngTree(resolved_config.seed)
    journal = Journal(match_id_of(recipe))
    runner = MatchRunner(
        config=resolved_config,
        world=resolved_world,
        agents=specs_of(recipe, resolved_world),
        gateway=ScriptedGateway(agents=factories),  # type: ignore[arg-type]
        journal=journal,
        match_id=journal.match_id,
        rng=resolved_rng,
    )
    return runner.run(), journal.events


def of_type(events: tuple[Event, ...], kind: type[Event]) -> list[Event]:
    """Return every event of one concrete class, in ``seq`` order."""
    return [event for event in events if isinstance(event, kind)]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
def test_the_journal_of_a_scripted_match_is_well_formed() -> None:
    result, events = play(SMALL)
    assert events, "the reference match produced an empty journal"
    verify_journal(list(events))
    assert isinstance(events[0], MatchStarted)
    assert events[0].seq == 1
    assert events[0].tick == 0
    assert isinstance(events[-1], MatchEnded)
    assert events[-1].tick == SMALL.ticks_total + 1
    assert result.event_count == len(events)
    assert result.rankings and len(result.rankings) == len(SMALL.baselines)


def test_config_and_scenario_agree() -> None:
    """CONTRACTS section 2.6: all five disagreements are fatal."""
    world = world_of(SMALL)
    base = config_of(SMALL)
    journal = Journal(match_id_of(SMALL))
    broken = (
        replace(base, ticks_total=48),
        replace(base, talking_mode=True),
        replace(
            base,
            liquidity_profile_name=LiquidityProfileName.ILLIQUID,
            mm=liquidity_profile(LiquidityProfileName.ILLIQUID).mm,
        ),
        replace(base, mm=replace(base.mm, quote_qty=base.mm.quote_qty + 1)),
        replace(base, n_markets=SMALL.n_markets - 1),
    )
    for config in broken:
        with pytest.raises(InvalidConfigError):
            MatchRunner(
                config=config,
                world=world,
                agents=specs_of(SMALL, world),
                gateway=ScriptedGateway(agents=agents_of(SMALL, base, RngTree(base.seed))),
                journal=journal,
                match_id=journal.match_id,
                rng=RngTree(base.seed),
            )
    # The unbroken config is accepted, so the five raises above are not a
    # constructor that refuses everything.
    MatchRunner(
        config=base,
        world=world,
        agents=specs_of(SMALL, world),
        gateway=ScriptedGateway(agents=agents_of(SMALL, base, RngTree(base.seed))),
        journal=journal,
        match_id=journal.match_id,
        rng=RngTree(base.seed),
    )


def test_phase_called_out_of_order_raises() -> None:
    journal = Journal(match_id_of(SMALL))
    runner = build_runner(SMALL, journal=journal)
    with pytest.raises(PhaseOrderError):
        runner.phase_p2_decision(1, ())
    observations = runner.phase_p1_diffusion(1)
    with pytest.raises(PhaseOrderError):
        runner.phase_p1_diffusion(2)
    with pytest.raises(PhaseOrderError):
        runner.phase_p4_close(1)
    actions = runner.phase_p2_decision(1, observations)
    runner.phase_p3_execution(1, actions)
    runner.phase_p4_close(1)
    with pytest.raises(PhaseOrderError):
        runner.phase_p1_diffusion(1)
    assert journal.events, "the aborted phase calls left an empty journal"


def test_run_twice_is_refused() -> None:
    journal = Journal(match_id_of(SMALL))
    runner = build_runner(SMALL, journal=journal)
    runner.run()
    assert journal.events
    with pytest.raises(PhaseOrderError):
        runner.run()


def test_tick_started_is_first_and_never_advertises_a_resolving_market() -> None:
    _result, events = play(WIDE)
    starts = of_type(events, TickStarted)
    assert len(starts) == WIDE.ticks_total
    resolved_at = {market.market_id: market.resolution_tick for market in world_of(WIDE).scenario.markets}
    assert any(tick < WIDE.ticks_total for tick in resolved_at.values()), (
        "the WIDE recipe must resolve a market mid match or this test is vacuous"
    )
    for start in starts:
        assert isinstance(start, TickStarted)
        for market_id in start.open_market_ids:
            assert start.tick <= resolved_at[market_id], (
                f"{market_id} was advertised at tick {start.tick} but resolves at {resolved_at[market_id]}"
            )
    # TickStarted opens every tick (section 4.4).
    by_tick: dict[int, Event] = {}
    for event in events:
        if event.tick not in by_tick:
            by_tick[event.tick] = event
    for tick in range(1, WIDE.ticks_total + 1):
        assert isinstance(by_tick[tick], TickStarted)


def test_mtm_each_tick() -> None:
    """FR-5.5.4: one MarkToMarket per open market, on every tick."""
    _result, events = play(SMALL)
    marks = of_type(events, MarkToMarket)
    assert marks, "no MarkToMarket event was emitted"
    starts = {event.tick: event for event in of_type(events, TickStarted)}
    per_tick: dict[int, list[str]] = {}
    for mark in marks:
        assert isinstance(mark, MarkToMarket)
        per_tick.setdefault(mark.tick, []).append(mark.market_id)
    for tick in range(1, SMALL.ticks_total + 1):
        start = starts[tick]
        assert isinstance(start, TickStarted)
        assert per_tick[tick] == sorted(per_tick[tick], key=lambda mid: int(mid[1:]))
        assert per_tick[tick] == list(start.open_market_ids)
        assert 1 <= marks[0].ref_price <= 99


def test_position_snapshot_uses_the_canonical_account_order() -> None:
    _result, events = play(SMALL)
    snapshots = of_type(events, PositionSnapshot)
    assert snapshots
    expected = [make_agent_id(i) for i in range(1, len(SMALL.baselines) + 1)] + ["MM", "FEES"]
    per_tick: dict[int, list[str]] = {}
    for snapshot in snapshots:
        assert isinstance(snapshot, PositionSnapshot)
        per_tick.setdefault(snapshot.tick, []).append(snapshot.account_id)
    assert per_tick
    for order in per_tick.values():
        assert order == expected


def test_prediction_block_follows_its_own_action() -> None:
    """CONTRACTS section 5 P2: rejections, action, predictions, message, per agent."""
    _result, events = play(SMALL)
    predictions = of_type(events, PredictionRecorded)
    actions = of_type(events, AgentActionReceived)
    assert predictions and actions
    last_action: dict[int, str] = {}
    for event in events:
        if isinstance(event, AgentActionReceived):
            last_action[event.tick] = event.agent_id
        elif isinstance(event, PredictionRecorded):
            assert last_action.get(event.tick) == event.agent_id, "a PredictionRecorded escaped its own agent block"


def test_bankruptcy_freezes_agent() -> None:
    """FR-5.5.5, reached through real order flow and never by forging state.

    ``bankruptcy_free_cash_floor_cents`` is set above zero on purpose. With
    integer prices an agent that keeps buying stops one indivisible order short
    of exactly zero free cash, so the reachable state is "a few cents left and
    nothing resting"; the floor is the field CONTRACTS section 5 P4 step 14
    provides for exactly that, and the predicate under test is unchanged.
    """
    recipe = custom_recipe(
        baselines=("spendthrift", "fundamentalist", "momentum", "bayesian"),
        seed=11,
        ticks=24,
        markets=2,
        template="election",
    )
    config = config_of(recipe, initial_cash_cents=20_000, bankruptcy_free_cash_floor_cents=3_000)
    rng = RngTree(config.seed)
    seats = agents_of(
        Recipe(
            name="tail",
            template_id=recipe.template_id,
            seed=recipe.seed,
            ticks_total=recipe.ticks_total,
            n_markets=recipe.n_markets,
            baselines=("fundamentalist", "fundamentalist", "momentum", "bayesian"),
        ),
        config,
        rng,
    )
    seats["A1"] = Spendthrift(agent_id="A1", config=config, rng=rng.child("agent/A1").substream("agent.A1"))
    _result, events = play_with_agents(recipe, factories=seats, config=config)

    frozen = of_type(events, AgentFrozen)
    assert frozen, "no agent was frozen: the scenario no longer exhausts free cash"
    freeze = frozen[0]
    assert isinstance(freeze, AgentFrozen)
    assert freeze.agent_id == "A1"
    assert 1 <= freeze.tick <= recipe.ticks_total
    # The freeze takes effect from tick + 1: no observation afterwards.
    later = [
        event
        for event in of_type(events, ObservationBuilt)
        if isinstance(event, ObservationBuilt) and event.agent_id == "A1" and event.tick > freeze.tick
    ]
    assert later == []
    # And it is permanent: exactly one AgentFrozen for that seat.
    assert sum(1 for event in frozen if isinstance(event, AgentFrozen) and event.agent_id == "A1") == 1
    # Its PositionSnapshot says frozen from that tick on.
    flags = [
        event.frozen
        for event in of_type(events, PositionSnapshot)
        if isinstance(event, PositionSnapshot) and event.account_id == "A1" and event.tick >= freeze.tick + 1
    ]
    assert flags and all(flags)


def test_stale_cancel_is_rejected_by_the_exchange() -> None:
    """CONTRACTS section 7.14: P2 validation is advisory, P3 liveness is law."""
    recipe = custom_recipe(
        baselines=("selfcrosser", "fundamentalist", "momentum", "bayesian"),
        seed=13,
        ticks=24,
        markets=2,
        template="election",
    )
    config = config_of(recipe)
    rng = RngTree(config.seed)
    seats = agents_of(
        Recipe(
            name="tail",
            template_id=recipe.template_id,
            seed=recipe.seed,
            ticks_total=recipe.ticks_total,
            n_markets=recipe.n_markets,
            baselines=("fundamentalist", "fundamentalist", "momentum", "bayesian"),
        ),
        config,
        rng,
    )
    seats["A1"] = SelfCrosser(agent_id="A1", config=config, rng=rng.child("agent/A1").substream("agent.A1"))
    _result, events = play_with_agents(recipe, factories=seats, config=config)

    stp = of_type(events, STPCancelled)
    assert stp, "the self crossing never happened, so the stale cancel cannot exist"
    stale = [
        event
        for event in of_type(events, OrderRejected)
        if isinstance(event, OrderRejected)
        and event.agent_id == "A1"
        and event.reason == RejectReason.UNKNOWN_ORDER.value
    ]
    assert stale, "the stale cancel was not rejected by the exchange"
    # And P2 did not reject it: the order was resting when the observation was
    # built, so there is no AgentActionRejected carrying UNKNOWN_ORDER for A1.
    from pxe.events import AgentActionRejected

    p2_unknown = [
        event
        for event in of_type(events, AgentActionRejected)
        if isinstance(event, AgentActionRejected)
        and event.agent_id == "A1"
        and event.reason == RejectReason.UNKNOWN_ORDER.value
    ]
    assert p2_unknown == []


def test_timeout_does_not_stop_match() -> None:
    """FR-5.1.1: a non answering agent produces no action and the match goes on."""
    config = config_of(SMALL)
    rng = RngTree(config.seed)
    gateway = FailingGateway(agents=agents_of(SMALL, config, rng), failing_agent_id="A1")
    result, events = play(SMALL, gateway=gateway, config=config, rng=rng)

    timeouts = of_type(events, AgentTimedOut)
    assert timeouts, "no AgentTimedOut was emitted"
    assert all(isinstance(event, AgentTimedOut) and event.agent_id == "A1" for event in timeouts)
    assert len(timeouts) == SMALL.ticks_total
    assert isinstance(events[-1], MatchEnded)
    # The failing seat still produced an action (the FR-5.1.1 fallback) and a
    # full prediction block, so the match kept a complete Brier series.
    fallbacks = [
        event
        for event in of_type(events, AgentActionReceived)
        if isinstance(event, AgentActionReceived) and event.agent_id == "A1"
    ]
    assert fallbacks
    assert all(event.source == AgentSource.FALLBACK.value for event in fallbacks)
    assert result.rankings


def test_engine_has_no_llm_dependency() -> None:
    """FR-5.1.2: nothing in the runner's import closure can reach a provider."""
    src = Path(__file__).resolve().parent.parent / "src"
    forbidden = {
        "subprocess",
        "socket",
        "http",
        "http.client",
        "urllib.request",
        "httpx",
        "requests",
        "anthropic",
        "openai",
    }
    seen: set[str] = set()
    stack = ["pxe.runner.match_runner"]
    edges: dict[str, set[str]] = {}
    while stack:
        module = stack.pop()
        if module in seen:
            continue
        seen.add(module)
        path = src / Path(*module.split(".")).with_suffix(".py")
        if not path.exists():
            path = src / Path(*module.split(".")) / "__init__.py"
        if not path.exists():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None and node.level == 0:
                names.add(node.module)
        edges[module] = names
        stack.extend(name for name in names if name.startswith("pxe."))

    assert "pxe.runner.match_runner" in edges
    assert "pxe.exchange.exchange" in seen, "the walk did not reach the exchange, so it proves nothing"
    assert "pxe.gateway.claude_cli" not in seen
    assert "pxe.gateway.prompt" not in seen
    for module, names in edges.items():
        assert not (names & forbidden), f"{module} imports {sorted(names & forbidden)}"


def test_run_match_writes_the_artefacts(tmp_path: Path) -> None:
    config = config_of(SMALL)
    world = world_of(SMALL)
    rng = RngTree(config.seed)
    result = run_match(
        config=config,
        world=world,
        agents=specs_of(SMALL, world),
        gateway=ScriptedGateway(agents=agents_of(SMALL, config, rng)),
        out_dir=tmp_path,
        rng=rng,
    )
    journal_path = tmp_path / "journal.jsonl"
    meta_path = tmp_path / "meta.json"
    assert journal_path.exists()
    assert meta_path.exists()
    assert result.journal_path == str(journal_path)
    raw = journal_path.read_bytes()
    assert raw, "the journal file is empty"
    assert b"\r" not in raw
    import json

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["match_id"] == match_id_of(SMALL)
    assert meta["journal_hash"] == result.journal_hash
    assert meta["seed"] == SMALL.seed
    assert meta["ticks_total"] == SMALL.ticks_total


def test_mm_is_out_of_ranking_and_its_pnl_is_reported() -> None:
    result, events = play(SMALL)
    assert events
    assert all(row.agent_id not in ("MM", "FEES") for row in result.rankings)
    snapshots = [
        event
        for event in of_type(events, PositionSnapshot)
        if isinstance(event, PositionSnapshot) and event.account_id == "MM"
    ]
    assert snapshots
    placed = [
        event for event in of_type(events, OrderPlaced) if isinstance(event, OrderPlaced) and event.agent_id == "MM"
    ]
    assert placed, "the market maker never quoted, so mm_pnl_cents would be trivially zero"
    # The published cost of liquidity is measured on cash AFTER the final
    # settlement, never on the last mark to market: the MM still held
    # inventory at the last P4 and its settlement lines land at T + 1.
    from pxe.events import SettlementApplied

    mm_lines = [
        event
        for event in of_type(events, SettlementApplied)
        if isinstance(event, SettlementApplied) and event.account_id == "MM"
    ]
    assert mm_lines, "the market maker settled nothing, so its PnL would be trivially zero"
    assert result.mm_pnl_cents == mm_lines[-1].cash_after_cents - config_of(SMALL).mm_initial_cash_cents
    assert result.mm_pnl_cents != 0


# ---------------------------------------------------------------------------
# Section 5.0: a cancelled market is not tradable on its cancellation tick
# ---------------------------------------------------------------------------
def test_a_cancelled_market_is_not_tradable_on_its_cancellation_tick() -> None:
    """``TickStarted`` subtracts the cancellations as well as the resolutions.

    Section 5.0 defines ``TickStarted.open_market_ids`` as the open markets minus
    ``due_market_ids(tick)`` **and** minus the market ids of
    ``due_cancellations(tick)``. An earlier draft named only the first
    subtraction, which contradicted P1 step 5 of the same document ("the market
    is not tradable on the tick it is cancelled") and produced two observable
    defects at the cancellation tick: ``TickStarted`` advertised a market no
    agent could touch, and a ``SignalDelivered`` was journalled for a market the
    observation does not carry, which is the dangling reference the step 3 filter
    exists to prevent.

    No shipped template scripts a cancellation (ruling R13), so this drives a
    hand built ``ScenarioSpec``. It also asserts the cancellation really happened
    and that a signal about that market really was in the draw, otherwise both
    claims below would hold on a match where nothing was cancelled at all.
    """
    cancel_tick, cancelled_market = 8, "M2"
    config = config_of(SMALL, n_markets=3)
    base = world_of(SMALL)
    world = replace(
        base,
        scenario=replace(
            base.scenario,
            cancellations=((cancel_tick, cancelled_market, "scripted_probe"),),
        ),
    )
    _result, events = play(SMALL, config=config, world=world)
    assert events, "the match produced an empty journal"

    cancellations = [event for event in events if isinstance(event, MarketCancelled)]
    assert [(event.tick, event.market_id) for event in cancellations] == [(cancel_tick, cancelled_market)], (
        "the scripted cancellation did not fire, so nothing below is being tested"
    )

    started = [event for event in of_type(events, TickStarted) if event.tick == cancel_tick]
    assert len(started) == 1
    assert isinstance(started[0], TickStarted)
    assert cancelled_market not in started[0].open_market_ids, (
        f"TickStarted advertised {cancelled_market} as tradable on the tick it is cancelled: "
        f"{started[0].open_market_ids}"
    )
    # The market is still one of the world's markets, so the exclusion is real
    # and not an artefact of a two market world.
    assert cancelled_market in {market.market_id for market in world.scenario.markets}
    assert started[0].open_market_ids, "every market vanished, so the assertion above is vacuous"

    leaked = [
        event
        for event in of_type(events, SignalDelivered)
        if isinstance(event, SignalDelivered) and event.tick == cancel_tick and event.market_id == cancelled_market
    ]
    assert not leaked, f"a signal was delivered about a market cancelled this very tick: {leaked}"
    # Teeth: the info engine really does draw signals at this tick, so "no
    # signal leaked" is a statement about a filter and not about an empty draw.
    drawn = [
        event
        for event in of_type(events, SignalDelivered)
        if isinstance(event, SignalDelivered) and event.tick == cancel_tick
    ]
    assert drawn, "no signal at all was delivered at the cancellation tick, so the filter is untested"

    # And nothing traded on it afterwards.
    late = [
        event
        for event in of_type(events, OrderPlaced)
        if isinstance(event, OrderPlaced) and event.market_id == cancelled_market and event.tick >= cancel_tick
    ]
    assert not late, f"an order was accepted on a cancelled market: {late}"


# ---------------------------------------------------------------------------
# Section 4.6 and ruling R39: the observations artefact has a producer
# ---------------------------------------------------------------------------
def test_run_match_writes_the_observations_artefact(tmp_path: Path) -> None:
    """``run_match`` writes ``observations.jsonl`` and it stays out of the hash.

    Section 4.6 gives A10 the artefact and section 7.13 calls
    ``write_observation`` "the one writer of that artefact", but until ruling R39
    added ``MatchRunner(obs_path=...)`` nothing anywhere called it, so the file
    had an owner and no producer. Two claims, and the second is the one that
    keeps AC-P1 safe: the file exists with one line per observation, and adding
    it did not move the journal hash.
    """
    result, events = play(SMALL, path=tmp_path / "journal.jsonl")
    hash_without_observations = result.journal_hash
    assert events

    out = tmp_path / "with_obs"
    written = run_match(
        config=config_of(SMALL),
        world=world_of(SMALL),
        agents=specs_of(SMALL, world_of(SMALL)),
        gateway=ScriptedGateway(agents=agents_of(SMALL, config_of(SMALL), RngTree(SMALL.seed))),  # type: ignore[arg-type]
        out_dir=out,
        rng=RngTree(SMALL.seed),
    )
    path = out / "observations.jsonl"
    assert path.is_file(), "run_match did not write the observations artefact"

    # LF, like every other artefact (section 4.2), and never universal newlines.
    with open(path, encoding="utf-8", newline="\n") as handle:
        raw = handle.read()
    assert "\r" not in raw, "the observation artefact carries a carriage return"
    rows = [json.loads(line) for line in raw.splitlines()]
    assert rows, "the observation artefact is empty"

    built = of_type(events, ObservationBuilt)
    assert built, "no ObservationBuilt was emitted, so the count below is vacuous"
    assert len(rows) == len(built), f"{len(rows)} observation lines against {len(built)} ObservationBuilt events"
    assert set(rows[0]) == {"agent_id", "tick", "obs_hash", "obs_bytes", "payload"}, sorted(rows[0])
    assert all(row["obs_bytes"] > 0 for row in rows)
    assert {row["agent_id"] for row in rows} == set(config_and_seats(SMALL)), "a seat produced no observation line"

    # The artefact is explicitly outside AC-P1 (section 3.5): writing it changes
    # no journal byte. This is the assertion that lets A10 recompact the
    # observation without regenerating tests/golden/.
    assert written.journal_hash == hash_without_observations, (
        "writing observations.jsonl moved the journal hash, so it is inside AC-P1"
    )


def config_and_seats(recipe: Recipe) -> tuple[str, ...]:
    """Return the ranked seat ids of a recipe, ascending.

    Args:
        recipe: The scenario.

    Returns:
        One seat id per baseline of the recipe.
    """
    return tuple(make_agent_id(index) for index in range(1, len(recipe.baselines) + 1))
