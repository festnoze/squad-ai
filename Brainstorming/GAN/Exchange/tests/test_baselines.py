"""Acceptance tests for pxe.agents (A12, CONTRACTS sections 7.15 and 13).

What is asserted here, and why it is asserted without the engine
----------------------------------------------------------------
A baseline is a pure function of ``(observation, its own substream)``, so it can
be tested against observations built by hand. That is what this file does: it
carries a small ``ToyMatch`` harness that builds real ``pxe.types.Observation``
objects, feeds them to a real agent, applies the returned orders against a crude
one level book and settles at a real outcome. The harness is deliberately not a
second exchange: it does not price-time match, it charges no fee and it knows
nothing about ticks that A05 owns. It exists so that T2.2's "100 matches per
baseline with no error" and "the fundamentalist beats the noise trader" can be
checked today, from the agent side, with a non empty result asserted first
(CONTRACTS section 10, anti vacuous rule).

The engine side of the same claims belongs to work packages that are not landed
yet and is not duplicated here: ``test_determinism.py`` (A09) owns
``test_reused_agent_objects_replay_identically`` over real journals, and
``test_info_value.py`` (A04) owns the FR-5.3.1 1 000 match test over the real
info engine. The two tests marked ``skip`` below are the hand-off points and
name their missing module through ``importorskip`` rather than passing on
nothing.
"""

import ast
import json
import random
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from pxe.agents.base import (
    BASELINES,
    BaselineAgent,
    OrderPlanner,
    ScriptedAgent,
    blend_ppm,
    clamp_belief_ppm,
    make_baseline,
    ppm_from_price,
    price_from_ppm,
    signal_evidence,
)
from pxe.errors import InvalidConfigError
from pxe.events import canonical_json
from pxe.rng import RngTree, bernoulli, randint
from pxe.types import (
    DEFAULT_PREDICTION_PPM,
    MILLI_ONE,
    PPM_ONE,
    AgentAction,
    AgentSource,
    MarketObservation,
    MarketStatus,
    MatchConfig,
    Observation,
    ObservationLimits,
    Order,
    OrderStatus,
    OrderType,
    Outcome,
    PublicMessage,
    Side,
    Signal,
    SignalKind,
    TimeInForce,
    action_to_journal_dict,
    action_to_payload,
    brier_term_ppm,
    clamp_price,
    make_market_id,
    make_signal_id,
    order_collateral_cents,
    position_collateral_cents,
)

AGENTS_DIR = Path(__file__).resolve().parent.parent / "src" / "pxe" / "agents"
SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "schemas"

#: Half spread of the toy book, in cents.
TOY_HALF_SPREAD = 2
#: Quantity available at each side of the toy touch, in contracts.
TOY_DEPTH_QTY = 200
#: Precision the toy info channel declares on its point estimates.
TOY_PRECISION_PPM = 600_000


# ---------------------------------------------------------------------------
# The toy match harness
# ---------------------------------------------------------------------------
@dataclass
class ToyMarket:
    """One synthetic market: a latent probability the reference price drifts to."""

    market_id: str
    latent_ppm: int
    prior_price: int
    ref_price: int
    outcome: Outcome
    resolution_tick: int
    history: list[int] = field(default_factory=list)

    @property
    def best_bid(self) -> int:
        """Best bid of the toy book."""
        return clamp_price(self.ref_price - TOY_HALF_SPREAD)

    @property
    def best_ask(self) -> int:
        """Best ask of the toy book."""
        return clamp_price(self.ref_price + TOY_HALF_SPREAD)


@dataclass
class ToySeat:
    """Everything the harness tracks for one seat."""

    agent_id: str
    agent: Any
    cash_cents: int
    positions: dict[str, int] = field(default_factory=dict)
    cost_basis_cents: dict[str, int] = field(default_factory=dict)
    resting: list[Order] = field(default_factory=list)
    brier_terms: list[int] = field(default_factory=list)
    actions: list[AgentAction] = field(default_factory=list)
    placed: int = 0
    cancelled: int = 0
    fills: int = 0

    def reserved_cents(self) -> int:
        """Collateral locked by resting orders and short positions (FR-5.5.1)."""
        total = sum(order_collateral_cents(o.side, o.price, o.remaining_qty) for o in self.resting)
        return total + sum(position_collateral_cents(qty) for qty in self.positions.values())


class ToyMatch:
    """A crude, self contained stand-in for one match, from the agent's side.

    It is not the engine: there is no price-time matching, no fee, no market
    maker and no journal. It is exactly enough market for a baseline to have an
    observation to read, a touch to trade against and an outcome to be scored
    on, which is what makes the T2.2 criteria checkable before A05 and A09 land.
    """

    def __init__(
        self,
        *,
        seed: int,
        agents: Mapping[str, Any],
        config: MatchConfig,
        n_markets: int = 3,
        signal_seats: Sequence[str] = (),
    ) -> None:
        """Build the world of one toy match and seat the agents.

        Args:
            seed: Root seed of the match. Everything below derives from it.
            agents: Agent per seat id.
            config: The match configuration the agents were reset with.
            n_markets: Number of synthetic markets.
            signal_seats: Seats the toy info channel delivers signals to.
        """
        self.config = config
        self.ticks_total = config.ticks_total
        self.match_id = f"m-toy-{seed}-01"
        self.rng = RngTree(seed).substream(f"test.toy.{seed}")
        self.signal_seats = tuple(signal_seats)
        self.markets: list[ToyMarket] = []
        for index in range(1, n_markets + 1):
            # A decisive latent probability, high or low, never a coin flip: the
            # comparison between an informed and an uninformed baseline has to
            # be dominated by information and not by settlement variance.
            if bernoulli(self.rng, 0.5):
                latent_ppm = randint(self.rng, 750_000, 920_000)
            else:
                latent_ppm = randint(self.rng, 80_000, 250_000)
            prior_price = clamp_price(latent_ppm // 10_000 + randint(self.rng, -15, 15))
            outcome = Outcome.YES if bernoulli(self.rng, latent_ppm / PPM_ONE) else Outcome.NO
            self.markets.append(
                ToyMarket(
                    market_id=make_market_id(index),
                    latent_ppm=latent_ppm,
                    prior_price=prior_price,
                    ref_price=prior_price,
                    outcome=outcome,
                    resolution_tick=self.ticks_total,
                )
            )
        self.seats: dict[str, ToySeat] = {
            agent_id: ToySeat(agent_id=agent_id, agent=agents[agent_id], cash_cents=config.initial_cash_cents)
            for agent_id in sorted(agents)
        }
        self._order_seq = 0
        self.tape: list[dict[str, int]] = []

    # -- world -----------------------------------------------------------
    def _drift(self) -> None:
        """Walk every reference price one cent toward its latent probability."""
        for market in self.markets:
            target = clamp_price(market.latent_ppm // 10_000)
            bias = 0.5 + 0.03 * (target - market.ref_price)
            probability_up = max(0.1, min(0.9, bias))
            step = 1 if bernoulli(self.rng, probability_up) else -1
            market.history.append(market.ref_price)
            market.ref_price = max(3 + TOY_HALF_SPREAD, min(97 - TOY_HALF_SPREAD, market.ref_price + step))

    def _signals(self, tick: int, agent_id: str) -> tuple[Signal, ...]:
        """Draw this tick's private signals for one seat.

        Args:
            tick: Current tick.
            agent_id: Seat the signals are for.

        Returns:
            Zero or one noisy point estimate about one market.
        """
        if agent_id not in self.signal_seats or not self.markets:
            return ()
        market = self.markets[(tick + len(agent_id)) % len(self.markets)]
        noisy_milli = market.latent_ppm // (PPM_ONE // MILLI_ONE) + randint(self.rng, -100, 100)
        value_milli = max(20, min(MILLI_ONE - 20, noisy_milli))
        return (
            Signal(
                signal_id=make_signal_id(tick, agent_id, 0),
                tick=tick,
                agent_id=agent_id,
                market_id=market.market_id,
                kind=SignalKind.POINT_ESTIMATE,
                value_milli=value_milli,
                precision_ppm=TOY_PRECISION_PPM,
            ),
        )

    def _observation(self, tick: int, seat: ToySeat) -> Observation:
        """Build the observation of one seat at one tick.

        Args:
            tick: Current tick.
            seat: The seat to build for.

        Returns:
            A fully populated observation, faithful on orders and positions.
        """
        blocks: list[MarketObservation] = []
        for market in self.markets:
            my_orders = tuple(o for o in seat.resting if o.market_id == market.market_id)
            blocks.append(
                MarketObservation(
                    market_id=market.market_id,
                    question=f"toy question {market.market_id}",
                    status=MarketStatus.OPEN,
                    prior_price=market.prior_price,
                    resolution_tick=market.resolution_tick,
                    ref_price=market.ref_price,
                    mid_price=market.ref_price,
                    best_bid=market.best_bid,
                    best_ask=market.best_ask,
                    bid_depth=((market.best_bid, TOY_DEPTH_QTY),),
                    ask_depth=((market.best_ask, TOY_DEPTH_QTY),),
                    last_price=market.history[-1] if market.history else None,
                    ref_history=tuple(market.history[-self.config.ref_history_len :]),
                    position_qty=seat.positions.get(market.market_id, 0),
                    cost_basis_cents=seat.cost_basis_cents.get(market.market_id, 0),
                    my_orders=my_orders,
                    my_last_prediction_ppm=DEFAULT_PREDICTION_PPM,
                )
            )
        reserved = seat.reserved_cents()
        return Observation(
            obs_version=self.config.obs_version,
            match_id=self.match_id,
            tick=tick,
            ticks_total=self.ticks_total,
            agent_id=seat.agent_id,
            cash_cents=seat.cash_cents,
            reserved_cents=reserved,
            free_cash_cents=seat.cash_cents - reserved,
            equity_cents=seat.cash_cents,
            news=(),
            signals=self._signals(tick, seat.agent_id),
            markets=tuple(blocks),
            messages=(),
            limits=ObservationLimits(
                max_active_orders_per_market=self.config.max_active_orders_per_market,
                price_min=1,
                price_max=99,
                market_band_cents=self.config.market_band_cents,
                taker_fee_bps=self.config.taker_fee_bps,
                message_max_chars=self.config.message_max_chars,
                max_orders_per_action=self.config.max_orders_per_action,
            ),
        )

    # -- execution -------------------------------------------------------
    def _fill(self, seat: ToySeat, *, market: ToyMarket, side: Side, price: int, qty: int) -> None:
        """Apply one execution to a seat's ledger.

        Args:
            seat: The seat being filled.
            market: The market traded.
            side: Side of the seat's order.
            price: Execution price in cents.
            qty: Executed quantity.
        """
        signed = qty if side is Side.BUY else -qty
        seat.positions[market.market_id] = seat.positions.get(market.market_id, 0) + signed
        seat.cost_basis_cents[market.market_id] = seat.cost_basis_cents.get(market.market_id, 0) + signed * price
        seat.cash_cents -= signed * price
        seat.fills += 1

    def _apply(self, seat: ToySeat, action: AgentAction, tick: int) -> None:
        """Apply one action: cancels, then places, in submission order.

        Args:
            seat: The acting seat.
            action: The action to apply.
            tick: Current tick.
        """
        by_id = {m.market_id: m for m in self.markets}
        for intent in action.orders:
            if intent.op == "cancel":
                before = len(seat.resting)
                seat.resting = [o for o in seat.resting if o.order_id != intent.order_id]
                seat.cancelled += before - len(seat.resting)
                continue
            assert intent.market_id is not None
            assert intent.side is not None
            assert intent.price is not None
            assert intent.qty is not None
            market = by_id[intent.market_id]
            seat.placed += 1
            crossing_qty = 0
            if intent.side is Side.BUY and intent.price >= market.best_ask:
                crossing_qty = min(intent.qty, TOY_DEPTH_QTY)
                self._fill(seat, market=market, side=Side.BUY, price=market.best_ask, qty=crossing_qty)
            elif intent.side is Side.SELL and intent.price <= market.best_bid:
                crossing_qty = min(intent.qty, TOY_DEPTH_QTY)
                self._fill(seat, market=market, side=Side.SELL, price=market.best_bid, qty=crossing_qty)
            remaining = intent.qty - crossing_qty
            if remaining > 0:
                self._order_seq += 1
                seat.resting.append(
                    Order(
                        order_id=f"o-{self._order_seq:06d}",
                        agent_id=seat.agent_id,
                        market_id=intent.market_id,
                        side=intent.side,
                        order_type=OrderType.LIMIT,
                        price=intent.price,
                        qty=intent.qty,
                        remaining_qty=remaining,
                        status=OrderStatus.OPEN,
                        tif=TimeInForce.GTC,
                        created_tick=tick,
                        seq=self._order_seq,
                    )
                )

    def _sweep_resting(self, seat: ToySeat) -> None:
        """Fill the resting orders the drifting touch has walked through.

        Args:
            seat: The seat whose book side is swept.
        """
        by_id = {m.market_id: m for m in self.markets}
        still_resting: list[Order] = []
        for order in seat.resting:
            market = by_id[order.market_id]
            if order.side is Side.BUY and order.price >= market.best_ask:
                self._fill(seat, market=market, side=Side.BUY, price=market.best_ask, qty=order.remaining_qty)
            elif order.side is Side.SELL and order.price <= market.best_bid:
                self._fill(seat, market=market, side=Side.SELL, price=market.best_bid, qty=order.remaining_qty)
            else:
                still_resting.append(order)
        seat.resting = still_resting

    def run(self) -> None:
        """Play every tick, then settle every market at its real outcome."""
        for tick in range(1, self.ticks_total + 1):
            self._drift()
            self.tape.append({m.market_id: m.ref_price for m in self.markets})
            for agent_id in sorted(self.seats):
                seat = self.seats[agent_id]
                self._sweep_resting(seat)
                observation = self._observation(tick, seat)
                action = seat.agent.act(observation)
                seat.actions.append(action)
                for prediction in action.predictions:
                    outcome = next(m.outcome for m in self.markets if m.market_id == prediction.market_id)
                    seat.brier_terms.append(brier_term_ppm(prediction.p_yes_ppm, outcome))
                self._apply(seat, action, tick)
                assert seat.cash_cents >= 0, f"{agent_id} went cash negative at tick {tick}"
                assert seat.reserved_cents() <= seat.cash_cents, f"{agent_id} over committed at tick {tick}"
        for seat in self.seats.values():
            seat.resting = []
            for market in self.markets:
                qty = seat.positions.get(market.market_id, 0)
                seat.cash_cents += qty * market.outcome.payout_cents
                seat.positions[market.market_id] = 0

    # -- results ---------------------------------------------------------
    def pnl_cents(self, agent_id: str) -> int:
        """Settled profit and loss of one seat, in cents.

        Args:
            agent_id: Seat of interest.

        Returns:
            ``final_cash - initial_cash``.
        """
        return self.seats[agent_id].cash_cents - self.config.initial_cash_cents

    def mean_brier_ppm(self, agent_id: str) -> int:
        """Mean Brier term of one seat, in ppm.

        Args:
            agent_id: Seat of interest.

        Returns:
            The mean of every recorded term, or ``0`` when nothing was declared.
        """
        terms = self.seats[agent_id].brier_terms
        return sum(terms) // len(terms) if terms else 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def toy_config(**overrides: Any) -> MatchConfig:
    """Build the configuration the toy matches use.

    Args:
        **overrides: Fields to override.

    Returns:
        A legal ``MatchConfig`` with a short horizon and three markets.
    """
    base: dict[str, Any] = {"seed": 4242, "ticks_total": 24, "n_agents": 6, "n_markets": 3}
    base.update(overrides)
    return MatchConfig(**base)


def build_agent(name: str, *, agent_id: str, config: MatchConfig, seed: int) -> Any:
    """Build one baseline with the substream CONTRACTS section 3.1 prescribes.

    Args:
        name: Baseline name.
        agent_id: Seat.
        config: Match configuration.
        seed: Root seed of the match.

    Returns:
        The agent.
    """
    rng = RngTree(seed).child(f"agent/{agent_id}").substream(f"agent.{agent_id}")
    return make_baseline(name, agent_id=agent_id, config=config, rng=rng)


def play(
    name: str,
    *,
    seed: int,
    config: MatchConfig | None = None,
    with_signals: bool = True,
    agents: Mapping[str, Any] | None = None,
) -> ToyMatch:
    """Run one toy match, either over one baseline or over a given population.

    Args:
        name: Baseline name, used when ``agents`` is not given.
        seed: Root seed of the match.
        config: Match configuration, defaults to :func:`toy_config`.
        with_signals: Whether the toy info channel delivers private signals.
        agents: Explicit population, seat id to agent.

    Returns:
        The finished match, ready to be queried.
    """
    cfg = config or toy_config()
    population = dict(agents) if agents is not None else {"A1": build_agent(name, agent_id="A1", config=cfg, seed=seed)}
    match = ToyMatch(
        seed=seed,
        agents=population,
        config=cfg,
        n_markets=cfg.n_markets,
        signal_seats=tuple(sorted(population)) if with_signals else (),
    )
    match.run()
    return match


def encode(actions: Iterable[AgentAction]) -> str:
    """Encode a sequence of actions the way the journal would.

    Args:
        actions: The actions to encode.

    Returns:
        One canonical JSON string, float free by construction.
    """
    return canonical_json([action_to_journal_dict(a) for a in actions])


# ---------------------------------------------------------------------------
# The protocol and the factory (CONTRACTS section 7.15)
# ---------------------------------------------------------------------------
def test_baselines_tuple_is_the_contracted_six() -> None:
    assert BASELINES == ("fundamentalist", "momentum", "noise", "zero_intelligence", "bayesian", "mute")


@pytest.mark.parametrize("name", BASELINES)
def test_make_baseline_returns_a_scripted_agent(name: str, standard_config: MatchConfig) -> None:
    agent = build_agent(name, agent_id="A3", config=standard_config, seed=7)
    assert isinstance(agent, ScriptedAgent)
    assert agent.name == name
    assert agent.agent_id == "A3"
    assert type(agent).name == name, "name must be a class level constant, per the protocol"


def test_make_baseline_rejects_an_unknown_name(standard_config: MatchConfig) -> None:
    with pytest.raises(InvalidConfigError):
        build_agent("oracle_cheater", agent_id="A1", config=standard_config, seed=1)


@pytest.mark.parametrize("name", BASELINES)
def test_reset_takes_a_config_and_a_substream(name: str, standard_config: MatchConfig) -> None:
    agent = build_agent(name, agent_id="A1", config=standard_config, seed=3)
    other = MatchConfig(seed=1, ticks_total=24, n_markets=2)
    agent.reset(config=other, rng=random.Random(0))
    assert agent.config is other


def test_the_baseline_package_imports_nothing_but_the_anchor() -> None:
    """An agent sees an Observation and nothing else (CONTRACTS section 13, A12 row)."""
    allowed = {
        "pxe.types",
        "pxe.rng",
        "pxe.errors",
        "pxe.agents.base",
        "random",
        "importlib",
        "collections.abc",
        "typing",
    }
    files = sorted(AGENTS_DIR.rglob("*.py"))
    assert len(files) == 9, f"expected the nine A12 files, found {[f.name for f in files]}"
    seen: list[str] = []
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                seen.append(node.module)
                assert node.module in allowed, f"{path.name} imports {node.module}"
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    seen.append(alias.name)
                    assert alias.name in allowed, f"{path.name} imports {alias.name}"
    assert seen, "the import scan saw no import at all"
    assert "pxe.agents.base" in seen, "the baselines must reach the shared skeleton"


# ---------------------------------------------------------------------------
# Determinism (O1, AC-P1, the scripted half)
# ---------------------------------------------------------------------------
@pytest.mark.determinism
@pytest.mark.parametrize("name", BASELINES)
def test_the_same_seed_produces_the_same_actions(name: str) -> None:
    first = play(name, seed=99)
    second = play(name, seed=99)
    assert first.seats["A1"].actions, "the harness produced no action at all"
    assert encode(first.seats["A1"].actions) == encode(second.seats["A1"].actions)


@pytest.mark.determinism
@pytest.mark.parametrize("name", BASELINES)
def test_reset_makes_a_reused_agent_replay_identically(name: str) -> None:
    """The A12 side of test_determinism.py::test_reused_agent_objects_replay_identically."""
    config = toy_config()
    fresh_first = play(name, seed=515)
    reused = build_agent(name, agent_id="A1", config=config, seed=515)
    match_one = ToyMatch(seed=515, agents={"A1": reused}, config=config, n_markets=3, signal_seats=("A1",))
    match_one.run()
    assert match_one.seats["A1"].actions
    assert encode(match_one.seats["A1"].actions) == encode(fresh_first.seats["A1"].actions)

    reused.reset(config=config, rng=RngTree(515).child("agent/A1").substream("agent.A1"))
    match_two = ToyMatch(seed=515, agents={"A1": reused}, config=config, n_markets=3, signal_seats=("A1",))
    match_two.run()
    assert encode(match_two.seats["A1"].actions) == encode(fresh_first.seats["A1"].actions), (
        "a reused agent must replay identically after reset"
    )


@pytest.mark.determinism
def test_without_reset_a_reused_agent_diverges() -> None:
    """The test above is only meaningful because this one holds."""
    config = toy_config()
    agent = build_agent("fundamentalist", agent_id="A1", config=config, seed=808)
    first = ToyMatch(seed=808, agents={"A1": agent}, config=config, n_markets=3, signal_seats=("A1",))
    first.run()
    second = ToyMatch(seed=808, agents={"A1": agent}, config=config, n_markets=3, signal_seats=("A1",))
    second.run()
    assert first.seats["A1"].actions and second.seats["A1"].actions
    assert encode(first.seats["A1"].actions) != encode(second.seats["A1"].actions), (
        "a half consumed generator must change the second match, or reset would be untestable"
    )


# ---------------------------------------------------------------------------
# Action shape and engine limits
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("name", BASELINES)
def test_every_action_validates_against_the_action_schema(name: str) -> None:
    schema = json.loads((SCHEMAS_DIR / "action.v1.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    match = play(name, seed=31)
    actions = match.seats["A1"].actions
    assert len(actions) == 24, "the harness must produce one action per tick"
    for action in actions:
        validator.validate(action_to_payload(action))


@pytest.mark.parametrize("name", BASELINES)
def test_actions_respect_every_engine_limit(name: str) -> None:
    config = toy_config(max_orders_per_action=6, max_active_orders_per_market=5)
    match = play(name, seed=77, config=config)
    actions = match.seats["A1"].actions
    assert actions
    for action in actions:
        assert action.agent_id == "A1"
        assert action.source is AgentSource.SCRIPTED
        assert action.action_version == config.action_version
        assert action.message_public is None, "a baseline never speaks, so TALKING_MODE_OFF cannot fire"
        assert len(action.predictions) <= 8
        assert len({p.market_id for p in action.predictions}) == len(action.predictions), "no duplicate prediction"
        assert all(0 <= p.p_yes_ppm <= PPM_ONE for p in action.predictions)
        assert len(action.orders) <= config.max_orders_per_action
        for intent in action.orders:
            assert intent.op in ("place", "cancel")
            if intent.op == "place":
                assert intent.market_id is not None
                assert intent.side is not None
                assert intent.order_type is OrderType.LIMIT
                assert intent.price is not None and 1 <= intent.price <= 99
                assert intent.qty is not None and 1 <= intent.qty <= 100_000
            else:
                assert intent.order_id is not None


@pytest.mark.parametrize("name", BASELINES)
def test_predictions_cover_every_open_market_in_canonical_order(name: str) -> None:
    match = play(name, seed=12)
    actions = match.seats["A1"].actions
    assert actions
    expected = tuple(make_market_id(i) for i in range(1, 4))
    for action in actions:
        declared = tuple(p.market_id for p in action.predictions)
        assert declared == expected, "one prediction per open market, ascending, so FR-6.2.4 never carries"


def test_an_action_never_asks_for_more_collateral_than_the_free_cash() -> None:
    """The planner promise: no baseline can earn an INSUFFICIENT_COLLATERAL."""
    checked = 0
    for name in BASELINES:
        config = toy_config()
        agent = build_agent(name, agent_id="A1", config=config, seed=606)
        match = ToyMatch(seed=606, agents={"A1": agent}, config=config, n_markets=3, signal_seats=("A1",))
        match.run()
        seat = match.seats["A1"]
        for action in seat.actions:
            demanded = sum(
                order_collateral_cents(i.side, i.price, i.qty)
                for i in action.orders
                if i.op == "place" and i.side is not None and i.price is not None and i.qty is not None
            )
            assert demanded <= config.initial_cash_cents
            checked += 1
    assert checked >= len(BASELINES) * 24, "the collateral scan saw fewer actions than it should"


# ---------------------------------------------------------------------------
# Per baseline behaviour
# ---------------------------------------------------------------------------
def test_mute_declares_predictions_and_places_no_order() -> None:
    """AC-P9: the population that leaves the book to the market maker alone."""
    match = play("mute", seed=5)
    seat = match.seats["A1"]
    assert seat.actions, "the harness produced no action at all"
    assert sum(len(a.predictions) for a in seat.actions) == 24 * 3
    assert all(a.orders == () for a in seat.actions)
    assert seat.placed == 0
    assert match.pnl_cents("A1") == 0, "an agent that never trades ends at its initial cash"


def test_mute_declares_the_market_implied_probability() -> None:
    match = play("mute", seed=6)
    actions = match.seats["A1"].actions
    assert actions and match.tape
    for tick, action in enumerate(actions, start=1):
        assert action.predictions
        for prediction in action.predictions:
            assert prediction.p_yes_ppm == ppm_from_price(match.tape[tick - 1][prediction.market_id])


def test_zero_intelligence_has_no_opinion_and_ignores_the_book() -> None:
    match = play("zero_intelligence", seed=8)
    seat = match.seats["A1"]
    assert seat.actions
    assert {p.p_yes_ppm for a in seat.actions for p in a.predictions} == {DEFAULT_PREDICTION_PPM}
    prices = [i.price for a in seat.actions for i in a.orders if i.op == "place"]
    assert len(prices) >= 10, "zero intelligence must actually trade"
    assert max(prices) - min(prices) > 40, "its prices must span the band, not hug the touch"


def test_the_noise_trader_quotes_near_the_reference_price() -> None:
    match = play("noise", seed=9)
    seat = match.seats["A1"]
    assert seat.placed >= 10, "the noise trader must actually trade"
    distances = []
    for tick, action in enumerate(seat.actions, start=1):
        for intent in action.orders:
            if intent.op != "place" or intent.price is None or intent.market_id is None:
                continue
            reference = match.tape[tick - 1][intent.market_id]
            distances.append(abs(intent.price - reference))
    assert distances
    assert max(distances) <= 5, "a noise quote stays within the quote span of the reference price"


def test_momentum_follows_the_trend_it_is_shown() -> None:
    config = toy_config()
    agent = build_agent("momentum", agent_id="A1", config=config, seed=4)
    rising = [40, 42, 44, 46]
    for tick, price in enumerate(rising, start=1):
        action = agent.act(_single_market_observation(config, tick=tick, ref_price=price, ref_history=()))
    assert action.predictions[0].p_yes_ppm > ppm_from_price(rising[-1]), "a rising tape must lift the belief"
    assert any(i.side is Side.BUY for i in action.orders), "and must buy the rise"

    falling = [60, 58, 56, 54]
    agent.reset(config=config, rng=RngTree(4).child("agent/A1").substream("agent.A1"))
    for tick, price in enumerate(falling, start=1):
        action = agent.act(_single_market_observation(config, tick=tick, ref_price=price, ref_history=()))
    assert action.predictions[0].p_yes_ppm < ppm_from_price(falling[-1]), "a falling tape must lower the belief"
    assert any(i.side is Side.SELL for i in action.orders), "and must sell the fall"


def test_the_bayesian_moves_toward_its_signals() -> None:
    config = toy_config()
    agent = build_agent("bayesian", agent_id="A1", config=config, seed=2)
    up = agent
    belief_before = up.act(_single_market_observation(config, tick=1, ref_price=50, ref_history=())).predictions[0]
    for tick in range(2, 8):
        action = up.act(
            _single_market_observation(
                config,
                tick=tick,
                ref_price=50,
                ref_history=(),
                signal=_point_estimate(tick, value_milli=900),
            )
        )
    assert action.predictions[0].p_yes_ppm > belief_before.p_yes_ppm + 50_000, "YES signals must lift the posterior"

    agent.reset(config=config, rng=RngTree(2).child("agent/A1").substream("agent.A1"))
    for tick in range(1, 8):
        action = agent.act(
            _single_market_observation(
                config,
                tick=tick,
                ref_price=50,
                ref_history=(),
                signal=_point_estimate(tick, value_milli=100),
            )
        )
    assert action.predictions[0].p_yes_ppm < belief_before.p_yes_ppm - 50_000, "NO signals must lower it"


def test_a_zero_precision_signal_moves_nothing() -> None:
    config = toy_config()
    agent = build_agent("bayesian", agent_id="A1", config=config, seed=2)
    reference = agent.act(_single_market_observation(config, tick=1, ref_price=50, ref_history=()))
    agent.reset(config=config, rng=RngTree(2).child("agent/A1").substream("agent.A1"))
    with_signal = agent.act(
        _single_market_observation(
            config,
            tick=1,
            ref_price=50,
            ref_history=(),
            signal=_point_estimate(1, value_milli=950, precision_ppm=0),
        )
    )
    assert with_signal.predictions[0].p_yes_ppm == reference.predictions[0].p_yes_ppm


# ---------------------------------------------------------------------------
# The shared helpers
# ---------------------------------------------------------------------------
def test_signal_evidence_reads_the_three_kinds() -> None:
    point = _point_estimate(1, value_milli=800)
    implied, weight = signal_evidence(point)
    assert implied == 800_000
    assert weight == point.precision_ppm

    up = Signal(
        signal_id=make_signal_id(1, "A1", 1),
        tick=1,
        agent_id="A1",
        market_id="M1",
        kind=SignalKind.DIRECTION,
        value_milli=MILLI_ONE,
        precision_ppm=800_000,
    )
    implied_up, weight_up = signal_evidence(up)
    down_implied, _ = signal_evidence(
        Signal(
            signal_id=make_signal_id(1, "A1", 2),
            tick=1,
            agent_id="A1",
            market_id="M1",
            kind=SignalKind.DIRECTION,
            value_milli=-MILLI_ONE,
            precision_ppm=800_000,
        )
    )
    assert implied_up > 500_000 > down_implied
    assert weight_up == 400_000, "a sign is worth half an estimate"

    lower_bound, _ = signal_evidence(
        Signal(
            signal_id=make_signal_id(1, "A1", 3),
            tick=1,
            agent_id="A1",
            market_id="M1",
            kind=SignalKind.THRESHOLD,
            value_milli=600,
            precision_ppm=500_000,
        )
    )
    assert lower_bound > 600_000, "a lower bound points into the half above it"


def test_price_and_ppm_round_trip_inside_the_band() -> None:
    for price in range(1, 100):
        assert price_from_ppm(ppm_from_price(price)) == price
    assert price_from_ppm(0) == 1
    assert price_from_ppm(PPM_ONE) == 99
    assert clamp_belief_ppm(-5) == 10_000
    assert clamp_belief_ppm(PPM_ONE) == 990_000


def test_blend_ppm_is_monotone_and_bounded() -> None:
    assert blend_ppm(200_000, 800_000, 0) == 200_000
    assert blend_ppm(200_000, 800_000, PPM_ONE) == 800_000
    middle = blend_ppm(200_000, 800_000, 500_000)
    assert 400_000 < middle < 600_000


def test_the_planner_refuses_what_the_free_cash_cannot_cover() -> None:
    config = toy_config()
    observation = _single_market_observation(config, tick=1, ref_price=50, ref_history=(), cash_cents=1_000)
    planner = OrderPlanner(observation, config)
    assert planner.place_limit(market_id="M1", side=Side.BUY, price=50, qty=10_000) is True
    intent = planner.intents[0]
    assert intent.qty is not None and intent.qty <= 1_000 // 50
    assert planner.budget_cents >= 0


def test_the_planner_honours_the_per_market_cap() -> None:
    config = toy_config(max_active_orders_per_market=5, max_orders_per_action=10)
    observation = _single_market_observation(config, tick=1, ref_price=50, ref_history=())
    planner = OrderPlanner(observation, config)
    placed = [planner.place_limit(market_id="M1", side=Side.BUY, price=40, qty=10) for _ in range(8)]
    assert placed.count(True) == 5, "the FR-5.4.2 cap is enforced before the intent exists"


def test_the_baseline_skeleton_requires_a_belief() -> None:
    class Incomplete(BaselineAgent):
        pass

    agent = Incomplete(agent_id="A1", config=toy_config(), rng=random.Random(0))
    with pytest.raises(NotImplementedError):
        agent.act(_single_market_observation(toy_config(), tick=1, ref_price=50, ref_history=()))


# ---------------------------------------------------------------------------
# T2.2: 100 matches per baseline, and the fundamentalist beats the noise trader
# ---------------------------------------------------------------------------
@pytest.mark.slow
@pytest.mark.parametrize("name", BASELINES)
def test_each_baseline_plays_one_hundred_matches(name: str) -> None:
    """T2.2: 100 matches with no error, no rejectable intent and a settled book."""
    config = toy_config(ticks_total=24, n_markets=2)
    actions = 0
    predictions = 0
    fills = 0
    for seed in range(1, 101):
        agent = build_agent(name, agent_id="A1", config=config, seed=seed)
        match = ToyMatch(seed=seed, agents={"A1": agent}, config=config, n_markets=2, signal_seats=("A1",))
        match.run()
        seat = match.seats["A1"]
        assert len(seat.actions) == config.ticks_total
        actions += len(seat.actions)
        predictions += sum(len(a.predictions) for a in seat.actions)
        fills += seat.fills
        assert seat.cash_cents >= 0
    assert actions == 100 * config.ticks_total
    assert predictions == 100 * config.ticks_total * config.n_markets
    if name != "mute":
        assert fills > 0, f"{name} traded nothing over a hundred matches"


@pytest.mark.slow
@pytest.mark.statistical
def test_fundamentalist_beats_noise_trader() -> None:
    """T2.2 exit criterion, from the agent side.

    Fifty toy matches, one fundamentalist and one noise trader per match, both
    receiving the same kind of private signal. Fixed seeds, so the tolerance is
    a plain inequality on the total: the fundamentalist trades toward a signal
    correlated with the outcome while the noise trader pays the spread at
    random, and the toy reference price drifts to the latent probability, so the
    gap is structural and not a lucky sample.
    """
    config = toy_config(ticks_total=24, n_markets=3)
    fundamentalist_pnl = 0
    noise_pnl = 0
    fundamentalist_brier = 0
    noise_brier = 0
    trades = 0
    for seed in range(1, 51):
        agents = {
            "A1": build_agent("fundamentalist", agent_id="A1", config=config, seed=seed),
            "A2": build_agent("noise", agent_id="A2", config=config, seed=seed),
        }
        match = ToyMatch(seed=seed, agents=agents, config=config, n_markets=3, signal_seats=("A1", "A2"))
        match.run()
        fundamentalist_pnl += match.pnl_cents("A1")
        noise_pnl += match.pnl_cents("A2")
        fundamentalist_brier += match.mean_brier_ppm("A1")
        noise_brier += match.mean_brier_ppm("A2")
        trades += match.seats["A1"].fills + match.seats["A2"].fills
    # Measured on these fixed seeds: fundamentalist +154 000 cents against
    # +19 995 for the noise trader, mean Brier 120 616 ppm against 126 835 ppm.
    # The tolerance is therefore a plain inequality plus "the informed agent is
    # profitable at all", which the uninformed one is not reliably.
    assert trades > 0, "no trade happened, so the comparison would be vacuous"
    assert fundamentalist_pnl > 0, f"using the signals must pay, got {fundamentalist_pnl}"
    assert fundamentalist_pnl > 2 * noise_pnl, f"fundamentalist {fundamentalist_pnl} vs noise {noise_pnl}"
    assert fundamentalist_brier < noise_brier, "and its declared probabilities must be better calibrated too"


@pytest.mark.slow
@pytest.mark.statistical
def test_the_bayesian_beats_the_uninformed_baselines_on_brier() -> None:
    """The A12 side of FR-5.3.1: using the signals must pay in calibration.

    The engine side (1 000 matches through the real info engine) is
    ``test_info_value.py::test_information_has_value``, owned by A04.
    """
    config = toy_config(ticks_total=24, n_markets=3)
    bayesian_brier = 0
    zi_brier = 0
    for seed in range(1, 41):
        agents = {
            "A1": build_agent("bayesian", agent_id="A1", config=config, seed=seed),
            "A2": build_agent("zero_intelligence", agent_id="A2", config=config, seed=seed),
        }
        match = ToyMatch(seed=seed, agents=agents, config=config, n_markets=3, signal_seats=("A1", "A2"))
        match.run()
        bayesian_brier += match.mean_brier_ppm("A1")
        zi_brier += match.mean_brier_ppm("A2")
    # Measured on these fixed seeds: 118 246 ppm against 250 000 ppm, that is
    # less than half. Zero intelligence always declares 500 000 ppm, so its
    # Brier is exactly 250 000 ppm by construction and the tolerance below is a
    # factor of two rather than a hand tuned epsilon.
    assert bayesian_brier > 0 and zi_brier > 0, "no prediction was scored, so the comparison would be vacuous"
    assert 2 * bayesian_brier < zi_brier, f"bayesian {bayesian_brier} vs zero intelligence {zi_brier}"


# ---------------------------------------------------------------------------
# Hand-off to the packages that are not landed yet (CONTRACTS section 10)
# ---------------------------------------------------------------------------
@pytest.mark.e2e
def test_all_six_baselines_drive_one_real_match(tmp_path: Path) -> None:
    """Every baseline plays one real match through the real runner (T2.2).

    This is the A12 versus A09 seam, and it used to be an unconditional
    ``pytest.skip`` waiting on a runner that has since landed: a test that never
    runs asserts nothing, which CONTRACTS section 10 forbids. It now seats all
    six baselines at once (a mix no unit test produces) and makes four claims
    against the journal the match actually wrote, each anti-vacuous:

    * the journal is non empty and carries one ``agent_action_received`` per
      seat per tick, so every brain was really consulted;
    * no scripted agent ever timed out (``AgentTimedOut`` means the gateway
      swallowed an exception a baseline raised);
    * no scripted agent ever produced an ``agent_action_rejected``, which is the
      authoritative statement that a baseline emits only actions
      ``validate_action`` accepts, made against the runner's single call site
      rather than against a validator a test called itself;
    * the trading baselines actually traded, so the run is not six mute agents
      passing through a no-op engine.
    """
    from pxe.gateway.scripted import ScriptedGateway
    from pxe.rng import RngTree
    from pxe.runner.match_runner import run_match
    from pxe.types import AgentSpec, HarnessConfig, InfoProfile, InfoProfileKind, sorted_ids
    from pxe.world.generator import generate_world

    config = MatchConfig(seed=20260827, ticks_total=24, n_markets=3, n_agents=len(BASELINES))
    world = generate_world(
        template_id="election",
        seed=config.seed,
        ticks_total=config.ticks_total,
        n_markets=config.n_markets,
    )
    tree = RngTree(config.seed)
    seats = sorted_ids(tuple(f"A{index}" for index in range(1, len(BASELINES) + 1)))
    seat_of_baseline = dict(zip(seats, BASELINES, strict=True))
    agents = {
        agent_id: make_baseline(
            seat_of_baseline[agent_id],
            agent_id=agent_id,
            config=config,
            rng=tree.child(f"agent/{agent_id}").substream(f"agent.{agent_id}"),
        )
        for agent_id in seats
    }
    specs = tuple(
        AgentSpec(
            agent_id=agent_id,
            harness=HarnessConfig(harness_id=seat_of_baseline[agent_id], version="1.0.0", kind="scripted"),
            info_profile=InfoProfile(kind=InfoProfileKind.GENERALIST),
        )
        for agent_id in seats
    )
    run_match(
        config=config,
        world=world,
        agents=specs,
        gateway=ScriptedGateway(agents=agents),
        out_dir=tmp_path,
        rng=tree,
    )

    with open(tmp_path / "journal.jsonl", encoding="utf-8", newline="\n") as handle:
        events = [json.loads(line) for line in handle]
    assert events, "the match produced an empty journal"
    by_type: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        by_type.setdefault(event["type"], []).append(event)

    received = by_type.get("agent_action_received", [])
    assert len(received) == len(seats) * config.ticks_total, (
        f"expected one action per seat per tick, got {len(received)}"
    )
    assert {event["agent_id"] for event in received} == set(seats), "a seat was never consulted"
    assert not by_type.get("agent_timed_out"), "a scripted agent must never time out"
    assert not by_type.get("agent_action_rejected"), (
        f"a baseline produced an action the runner's validator refused: {by_type.get('agent_action_rejected', [])[:3]}"
    )
    trades = by_type.get("trade_executed", [])
    assert trades, "no trade happened, so the engine did nothing this match"
    traders = {event["taker_agent_id"] for event in trades} | {event["maker_agent_id"] for event in trades}
    assert traders & set(seats), f"only the market maker traded: {sorted(traders)}"


# ---------------------------------------------------------------------------
# Small observation builders used by the unit tests above
# ---------------------------------------------------------------------------
def _point_estimate(tick: int, *, value_milli: int, precision_ppm: int = TOY_PRECISION_PPM) -> Signal:
    """Build one point estimate signal about ``M1``.

    Args:
        tick: Tick of delivery.
        value_milli: Noisy probability in thousandths.
        precision_ppm: Self declared reliability.

    Returns:
        The signal.
    """
    return Signal(
        signal_id=make_signal_id(tick, "A1", 0),
        tick=tick,
        agent_id="A1",
        market_id="M1",
        kind=SignalKind.POINT_ESTIMATE,
        value_milli=value_milli,
        precision_ppm=precision_ppm,
    )


def _single_market_observation(
    config: MatchConfig,
    *,
    tick: int,
    ref_price: int,
    ref_history: Sequence[int],
    signal: Signal | None = None,
    cash_cents: int | None = None,
    my_orders: Sequence[Order] = (),
    position_qty: int = 0,
) -> Observation:
    """Build a one market observation for a unit test.

    Args:
        config: Match configuration to echo in ``limits``.
        tick: Current tick.
        ref_price: Reference price of the single market.
        ref_history: Reference price history, oldest first.
        signal: Optional private signal about that market.
        cash_cents: Cash of the agent, defaults to the configured initial cash.
        my_orders: Resting orders of the agent on that market.
        position_qty: Signed net position of the agent.

    Returns:
        A fully populated observation over exactly one open market.
    """
    cash = config.initial_cash_cents if cash_cents is None else cash_cents
    reserved = sum(order_collateral_cents(o.side, o.price, o.remaining_qty) for o in my_orders)
    reserved += position_collateral_cents(position_qty)
    market = MarketObservation(
        market_id="M1",
        question="unit test question",
        status=MarketStatus.OPEN,
        prior_price=50,
        resolution_tick=config.ticks_total,
        ref_price=ref_price,
        mid_price=ref_price,
        best_bid=clamp_price(ref_price - TOY_HALF_SPREAD),
        best_ask=clamp_price(ref_price + TOY_HALF_SPREAD),
        bid_depth=((clamp_price(ref_price - TOY_HALF_SPREAD), TOY_DEPTH_QTY),),
        ask_depth=((clamp_price(ref_price + TOY_HALF_SPREAD), TOY_DEPTH_QTY),),
        last_price=ref_price,
        ref_history=tuple(ref_history),
        position_qty=position_qty,
        cost_basis_cents=0,
        my_orders=tuple(my_orders),
        my_last_prediction_ppm=DEFAULT_PREDICTION_PPM,
    )
    return Observation(
        obs_version=config.obs_version,
        match_id="m-toy-1-01",
        tick=tick,
        ticks_total=config.ticks_total,
        agent_id="A1",
        cash_cents=cash,
        reserved_cents=reserved,
        free_cash_cents=cash - reserved,
        equity_cents=cash,
        news=(),
        signals=() if signal is None else (signal,),
        markets=(market,),
        messages=(),
        limits=ObservationLimits(
            max_active_orders_per_market=config.max_active_orders_per_market,
            price_min=1,
            price_max=99,
            market_band_cents=config.market_band_cents,
            taker_fee_bps=config.taker_fee_bps,
            message_max_chars=config.message_max_chars,
            max_orders_per_action=config.max_orders_per_action,
        ),
    )


def test_a_public_message_is_never_produced(standard_config: MatchConfig) -> None:
    """Talking mode on or off, a baseline stays silent, so no message is rejected."""
    talking = toy_config(talking_mode=True)
    seen = 0
    for name in BASELINES:
        agent = build_agent(name, agent_id="A1", config=talking, seed=17)
        action = agent.act(_single_market_observation(talking, tick=1, ref_price=50, ref_history=()))
        assert action.message_public is None
        seen += 1
    assert seen == len(BASELINES)


def test_unused_public_message_helper_keeps_the_type_import_honest() -> None:
    """PublicMessage is part of an observation; assert the empty case is legal."""
    config = toy_config()
    observation = _single_market_observation(config, tick=2, ref_price=50, ref_history=())
    assert observation.messages == ()
    message = PublicMessage(agent_id="A2", tick=1, text="hello", deliver_tick=2)
    assert message.deliver_tick == 2


# ---------------------------------------------------------------------------
# Edge cases of the shared machinery
# ---------------------------------------------------------------------------
def test_signal_evidence_reads_an_upper_bound_threshold() -> None:
    """A negative threshold asserts "at most this much" (documented reading)."""
    upper, weight = signal_evidence(
        Signal(
            signal_id=make_signal_id(1, "A1", 4),
            tick=1,
            agent_id="A1",
            market_id="M1",
            kind=SignalKind.THRESHOLD,
            value_milli=-400,
            precision_ppm=500_000,
        )
    )
    assert upper < 400_000, "an upper bound points into the half below it"
    assert weight == 250_000


def test_the_bayesian_follows_a_direction_signal() -> None:
    config = toy_config()
    agent = build_agent("bayesian", agent_id="A1", config=config, seed=21)
    flat = agent.act(_single_market_observation(config, tick=1, ref_price=50, ref_history=()))
    agent.reset(config=config, rng=RngTree(21).child("agent/A1").substream("agent.A1"))
    action = flat
    for tick in range(1, 6):
        action = agent.act(
            _single_market_observation(
                config,
                tick=tick,
                ref_price=50,
                ref_history=(),
                signal=Signal(
                    signal_id=make_signal_id(tick, "A1", 0),
                    tick=tick,
                    agent_id="A1",
                    market_id="M1",
                    kind=SignalKind.DIRECTION,
                    value_milli=MILLI_ONE,
                    precision_ppm=PPM_ONE,
                ),
            )
        )
    assert action.predictions[0].p_yes_ppm > flat.predictions[0].p_yes_ppm, "an up direction must lift the posterior"


def test_the_bayesian_forgets_old_observations() -> None:
    """The weight cap is what lets the posterior follow a latent that moves."""
    config = toy_config()
    agent = build_agent("bayesian", agent_id="A1", config=config, seed=22)
    action = agent.act(_single_market_observation(config, tick=1, ref_price=50, ref_history=()))
    for tick in range(1, 21):
        action = agent.act(
            _single_market_observation(
                config, tick=tick, ref_price=50, ref_history=(), signal=_point_estimate(tick, value_milli=900)
            )
        )
    high = action.predictions[0].p_yes_ppm
    for tick in range(21, 41):
        action = agent.act(
            _single_market_observation(
                config, tick=tick, ref_price=50, ref_history=(), signal=_point_estimate(tick, value_milli=100)
            )
        )
    low = action.predictions[0].p_yes_ppm
    assert high > 700_000, f"twenty YES estimates must convince it, got {high}"
    assert low < 300_000, f"twenty NO estimates must convince it back, got {low}"


def test_the_planner_drops_an_order_no_cash_can_cover() -> None:
    config = toy_config()
    observation = _single_market_observation(config, tick=1, ref_price=50, ref_history=(), cash_cents=0)
    planner = OrderPlanner(observation, config)
    assert planner.place_limit(market_id="M1", side=Side.BUY, price=50, qty=10) is False
    assert planner.intents == ()
    assert planner.affordable_qty(Side.BUY, 50, 0) == 0


def test_the_planner_refuses_anything_once_the_action_is_full() -> None:
    config = toy_config(max_orders_per_action=1)
    order = Order(
        order_id="o-000001",
        agent_id="A1",
        market_id="M1",
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        price=40,
        qty=10,
        remaining_qty=10,
        status=OrderStatus.OPEN,
        tif=TimeInForce.GTC,
        created_tick=1,
        seq=1,
    )
    observation = _single_market_observation(config, tick=2, ref_price=50, ref_history=(), my_orders=(order,))
    planner = OrderPlanner(observation, config)
    assert planner.place_limit(market_id="M1", side=Side.BUY, price=40, qty=10) is True
    assert planner.place_limit(market_id="M1", side=Side.BUY, price=41, qty=10) is False
    assert planner.cancel(market_id="M1", order_id="o-000001") is False


def test_a_taker_fee_shrinks_the_affordable_quantity() -> None:
    free_config = toy_config(taker_fee_bps=0)
    paid_config = toy_config(taker_fee_bps=200)
    free = OrderPlanner(
        _single_market_observation(free_config, tick=1, ref_price=50, ref_history=(), cash_cents=10_000), free_config
    )
    paid = OrderPlanner(
        _single_market_observation(paid_config, tick=1, ref_price=50, ref_history=(), cash_cents=10_000), paid_config
    )
    assert paid.affordable_qty(Side.BUY, 50, 10_000) < free.affordable_qty(Side.BUY, 50, 10_000)


def test_a_cancel_frees_a_slot_on_a_capped_market() -> None:
    """make_room pulls the oldest order so a full market can still be traded."""
    config = toy_config(max_active_orders_per_market=5, max_orders_per_action=6)
    orders = tuple(
        Order(
            order_id=f"o-{index:06d}",
            agent_id="A1",
            market_id="M1",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            price=30,
            qty=5,
            remaining_qty=5,
            status=OrderStatus.OPEN,
            tif=TimeInForce.GTC,
            created_tick=1,
            seq=index,
        )
        for index in range(1, 6)
    )
    agent = build_agent("bayesian", agent_id="A1", config=config, seed=33)
    observation = _single_market_observation(
        config,
        tick=2,
        ref_price=20,
        ref_history=(),
        my_orders=orders,
        signal=_point_estimate(2, value_milli=900),
    )
    action = agent.act(observation)
    ops = [intent.op for intent in action.orders]
    assert ops[:2] == ["cancel", "place"], f"expected a cancel then a place, got {ops}"
    assert action.orders[0].order_id == "o-000001", "the oldest resting order is the one pulled"


@pytest.mark.parametrize("name", BASELINES)
def test_no_baseline_action_is_ever_rejected_by_the_real_validator(name: str) -> None:
    """The strongest form of the "no rejected action" claim (CONTRACTS 7.14).

    A scripted agent reaches ``validate_action`` through the same door as an LLM
    (``ScriptedGateway`` wraps the action with ``action_to_payload``), so the
    authoritative check of "this baseline cannot earn an ``AgentActionRejected``"
    is the validator itself. Skips with a named reason until A11 is present.
    """
    from pxe.runner import action_validator as validator_mod

    config = toy_config()
    agent = build_agent(name, agent_id="A1", config=config, seed=404)
    match = ToyMatch(seed=404, agents={"A1": agent}, config=config, n_markets=3, signal_seats=("A1",))
    match.run()
    seat = match.seats["A1"]
    assert seat.actions, "the harness produced no action at all"
    open_market_ids = tuple(m.market_id for m in match.markets)
    checked = 0
    for tick, action in enumerate(seat.actions, start=1):
        resting_ids = tuple(sorted({i.order_id for i in action.orders if i.op == "cancel" and i.order_id is not None}))
        outcome = validator_mod.validate_action(
            action_to_payload(action),
            agent_id="A1",
            tick=tick,
            config=config,
            open_market_ids=open_market_ids,
            resting_order_ids=resting_ids,
            source=AgentSource.SCRIPTED,
        )
        assert outcome.rejections == (), f"{name} tick {tick} rejected: {outcome.rejections}"
        assert len(outcome.action.orders) == len(action.orders)
        assert len(outcome.action.predictions) == len(action.predictions)
        checked += 1
    assert checked == config.ticks_total
