"""The scripted agent protocol and the baseline factory (CONTRACTS section 7.15).

Three names are public and they are the whole contract of this package:
:class:`ScriptedAgent`, :data:`BASELINES` and :func:`make_baseline`. Five other
work packages type against the protocol, so its shape is literal.

What a scripted agent may see
-----------------------------
An agent sees an :class:`~pxe.types.Observation` and nothing else. It never
imports the world, the latent process, the info engine or another agent's
state, and it draws only from the :class:`random.Random` it was handed, namely
``root.child(f"agent/{agent_id}").substream(f"agent.{agent_id}")``. Every
baseline is therefore a deterministic function of
``(observation, its own substream)``, which is what makes AC-P1 provable for a
scripted match.

Why ``reset`` is not decoration
-------------------------------
The runner calls ``agent.reset(config=config, rng=<that same substream>)`` for
every scripted seat in ascending ``agent_id``, immediately after
``MatchStarted`` and before tick 1 (CONTRACTS section 3.1). A tournament reuses
agent objects across matches, so an agent that keeps a half consumed generator
or a stale price history makes the second match a function of the first.
``reset`` clears **all** per match state, the generator included.

Determinism inside an agent
---------------------------
Beliefs are computed with integer arithmetic wherever possible, and where a
float is unavoidable (the Bayesian posterior) only the four IEEE-754
operations ``+ - * /`` are used. ``log``, ``exp`` and ``pow`` are deliberately
absent from this package: they call the platform libm, which is not bit
identical between glibc, msvcrt and macOS, and a belief landing within one ulp
of a ppm boundary would then quantise differently on two machines
(CONTRACTS section 3.2).

No rejected action, ever
------------------------
A baseline that gets rejected teaches nothing, and 100 clean matches per
baseline is the T2.2 exit criterion. Every order intent therefore goes through
:class:`OrderPlanner`, which enforces the price band, the per market active
order cap, the per action order cap and the FR-5.5.1 collateral formula
against the free cash the observation reports, before the intent exists.
"""

import importlib
import random
from collections.abc import Callable, Mapping
from typing import ClassVar, Protocol, runtime_checkable

from pxe.errors import InvalidConfigError
from pxe.types import (
    BPS_ONE,
    MAX_ORDER_QTY,
    MAX_PREDICTIONS_PER_ACTION,
    MILLI_ONE,
    PAYOUT_YES_CENTS,
    PPM_ONE,
    AgentAction,
    AgentSource,
    MarketObservation,
    MarketStatus,
    MatchConfig,
    Observation,
    OrderIntent,
    OrderType,
    PredictionIntent,
    Side,
    Signal,
    SignalKind,
    clamp_price,
    max_taker_fee_cents,
    order_collateral_cents,
    round_half_up,
    sorted_ids,
)

__all__ = [
    "ScriptedAgent",
    "BASELINES",
    "make_baseline",
]


# --------------------------------------------------------------------------
# Internal tuning constants. None of them is part of the public contract, but
# all of them are part of the journal of a scripted match: changing one moves
# every golden hash, exactly like a change to a baseline's policy.
# --------------------------------------------------------------------------
#: Parts per million of probability per cent of price. A price of ``p`` cents is
#: the market implied probability ``p / 100``.
PPM_PER_CENT: int = PPM_ONE // PAYOUT_YES_CENTS
#: Parts per million per thousandth, for ``Signal.value_milli`` conversions.
PPM_PER_MILLI: int = PPM_ONE // MILLI_ONE
#: Beliefs are clamped away from 0 and 1: a tradable price always exists and a
#: single wrong market cannot dominate a Brier average.
BELIEF_MIN_PPM: int = 10_000
BELIEF_MAX_PPM: int = 990_000
#: Probability a ``DIRECTION`` signal implies on its own, before its precision
#: weight is applied.
DIRECTION_UP_PPM: int = 750_000
DIRECTION_DOWN_PPM: int = 250_000
#: Baseline order size, in contracts, before the edge scaling of
#: :meth:`BaselineAgent.trade_on_edge` and before the collateral cap.
DEFAULT_ORDER_QTY: int = 20
#: Highest multiple of ``DEFAULT_ORDER_QTY`` a single edge may ask for.
MAX_EDGE_MULTIPLE: int = 5
#: Absolute per market position a baseline stops adding to. Keeps a baseline
#: solvent for a whole match and keeps I10 style blowups out of the population.
MAX_BASELINE_POSITION_QTY: int = 400
#: A single order may lock at most ``free_cash / ORDER_BUDGET_DIVISOR`` cents.
ORDER_BUDGET_DIVISOR: int = 8


# --------------------------------------------------------------------------
# The protocol (CONTRACTS section 7.15, literal)
# --------------------------------------------------------------------------
@runtime_checkable
class ScriptedAgent(Protocol):
    """A deterministic, LLM free player of one seat.

    Attributes:
        agent_id: The seat this instance plays, ``A1``..``A8``.
        name: The baseline name, a class level constant so a caller can label a
            seat without instantiating anything.
    """

    agent_id: str
    name: ClassVar[str]

    def reset(self, *, config: MatchConfig, rng: random.Random) -> None:
        """Clear every per match state, including the generator.

        Args:
            config: Configuration of the match about to start.
            rng: The agent's own substream, rebuilt by the caller.
        """
        ...

    def act(self, observation: Observation) -> AgentAction:
        """Decide what to do for one tick.

        Args:
            observation: Everything this agent is allowed to know.

        Returns:
            The action for that tick. It still goes through
            ``validate_action`` like any LLM action.
        """
        ...


#: The six baseline names, in the order they are documented. ``make_baseline``
#: accepts exactly these.
BASELINES: tuple[str, ...] = (
    "fundamentalist",
    "momentum",
    "noise",
    "zero_intelligence",
    "bayesian",
    "mute",
)


# --------------------------------------------------------------------------
# Shared pure helpers
# --------------------------------------------------------------------------
def clamp_belief_ppm(p_yes_ppm: int) -> int:
    """Clamp a probability in ppm into the tradable belief band.

    Args:
        p_yes_ppm: Any integer probability in parts per million.

    Returns:
        The value clamped to ``[BELIEF_MIN_PPM, BELIEF_MAX_PPM]``.
    """
    return max(BELIEF_MIN_PPM, min(BELIEF_MAX_PPM, int(p_yes_ppm)))


def price_from_ppm(p_yes_ppm: int) -> int:
    """Convert a probability in ppm to the nearest tradable price in cents.

    Args:
        p_yes_ppm: Probability in parts per million.

    Returns:
        A price in ``[1, 99]``.
    """
    return clamp_price(round_half_up(p_yes_ppm / PPM_PER_CENT))


def ppm_from_price(price: int) -> int:
    """Convert a price in cents to the market implied probability in ppm.

    Args:
        price: Price in cents.

    Returns:
        The implied probability, clamped to the belief band.
    """
    return clamp_belief_ppm(clamp_price(price) * PPM_PER_CENT)


def signal_evidence(signal: Signal) -> tuple[int, int]:
    """Reduce any private signal to ``(implied_probability_ppm, weight_ppm)``.

    The three shapes of :class:`~pxe.types.SignalKind` are read exactly as
    ``pxe.types.Signal`` documents them:

    * ``POINT_ESTIMATE``: ``value_milli`` is a noisy probability in thousandths,
      so the implied probability is ``value_milli * 1000`` ppm and the weight is
      the signal's own ``precision_ppm``.
    * ``DIRECTION``: ``value_milli`` is ``+1000`` or ``-1000``; the implied
      probability is a lean, not an estimate, and the weight is halved because a
      sign carries strictly less than a value.
    * ``THRESHOLD``: ``value_milli`` is a threshold in thousandths, read as a
      one sided bound. A non negative value asserts "the probability is at least
      this", a negative value asserts "at most this much", and the implied
      probability is the midpoint of the asserted half. The weight is halved for
      the same reason as ``DIRECTION``.

    Args:
        signal: One private signal, already filtered to a tradable market.

    Returns:
        The implied probability in ppm (clamped to the belief band) and the
        weight to give it, in ppm of full trust.
    """
    if signal.kind is SignalKind.POINT_ESTIMATE:
        return clamp_belief_ppm(signal.value_milli * PPM_PER_MILLI), signal.precision_ppm
    if signal.kind is SignalKind.DIRECTION:
        implied = DIRECTION_UP_PPM if signal.value_milli >= 0 else DIRECTION_DOWN_PPM
        return implied, signal.precision_ppm // 2
    bound_ppm = clamp_belief_ppm(abs(signal.value_milli) * PPM_PER_MILLI)
    if signal.value_milli >= 0:
        implied = clamp_belief_ppm((bound_ppm + PPM_ONE) // 2)
    else:
        implied = clamp_belief_ppm(bound_ppm // 2)
    return implied, signal.precision_ppm // 2


def signals_for_market(observation: Observation, market_id: str) -> tuple[Signal, ...]:
    """Return this tick's private signals about one market, in delivery order.

    Args:
        observation: The current observation.
        market_id: Market of interest.

    Returns:
        The matching signals, in the order the engine delivered them.
    """
    return tuple(s for s in observation.signals if s.market_id == market_id)


def blend_ppm(current_ppm: int, implied_ppm: int, weight_ppm: int) -> int:
    """Move a belief toward a piece of evidence, in integer parts per million.

    Args:
        current_ppm: The belief before the update.
        implied_ppm: The probability the evidence implies.
        weight_ppm: How much of the way to move, in ppm of full trust.

    Returns:
        The updated belief, clamped to the belief band.
    """
    weight = max(0, min(PPM_ONE, weight_ppm))
    moved = current_ppm * (PPM_ONE - weight) + implied_ppm * weight
    return clamp_belief_ppm(moved // PPM_ONE)


# --------------------------------------------------------------------------
# The order planner
# --------------------------------------------------------------------------
class OrderPlanner:
    """Builds the ``orders`` array of one action without ever being rejected.

    Internal to ``pxe.agents``: it is not part of the section 7.15 public
    surface. It enforces, from the observation alone, everything P2 and P3 would
    otherwise reject: the ``[1, 99]`` price band, the per market active order
    cap, the per action order cap, ``MAX_ORDER_QTY``, and the FR-5.5.1
    collateral formula plus the worst case taker fee against the free cash the
    observation reports.

    Collateral freed by a ``cancel`` intent in the same action is deliberately
    **not** credited back to the budget: the P3 solvency check of CONTRACTS
    section 6.1 is evaluated order by order and the engine is free to fill a
    resting order between P2 and P3, so counting that cash twice is how a
    baseline earns an ``INSUFFICIENT_COLLATERAL``.
    """

    def __init__(self, observation: Observation, config: MatchConfig) -> None:
        """Snapshot the budget and the caps of one tick.

        Args:
            observation: The observation the action answers.
            config: The match configuration the agent was reset with.
        """
        limits = observation.limits
        self._fee_bps = limits.taker_fee_bps
        self._budget_cents = max(0, observation.free_cash_cents)
        self._per_order_cap_cents = max(0, observation.free_cash_cents // ORDER_BUDGET_DIVISOR)
        self._max_intents = max(0, min(config.max_orders_per_action, limits.max_orders_per_action))
        self._max_per_market = max(0, min(config.max_active_orders_per_market, limits.max_active_orders_per_market))
        self._resting_count: dict[str, int] = {m.market_id: len(m.my_orders) for m in observation.markets}
        self._intents: list[OrderIntent] = []

    @property
    def intents(self) -> tuple[OrderIntent, ...]:
        """The intents planned so far, in submission order."""
        return tuple(self._intents)

    @property
    def budget_cents(self) -> int:
        """Collateral still unspent by this action, in cents."""
        return self._budget_cents

    def has_slot(self) -> bool:
        """True while another intent fits in this action.

        Returns:
            Whether ``max_orders_per_action`` has room left.
        """
        return len(self._intents) < self._max_intents

    def has_room(self, market_id: str) -> bool:
        """True while another resting order fits on one market.

        Args:
            market_id: Market to check.

        Returns:
            Whether the FR-5.4.2 per market cap has room left.
        """
        return self._resting_count.get(market_id, 0) < self._max_per_market

    def affordable_qty(self, side: Side, price: int, wanted_qty: int) -> int:
        """Largest quantity of one intent the free cash actually covers.

        Args:
            side: Order side.
            price: Limit price in cents, already inside ``[1, 99]``.
            wanted_qty: The quantity the policy asked for.

        Returns:
            A quantity in ``[0, min(wanted_qty, MAX_ORDER_QTY)]``. Zero means
            the intent must not be sent.
        """
        wanted = min(int(wanted_qty), MAX_ORDER_QTY)
        if wanted < 1:
            return 0
        cap_cents = min(self._budget_cents, self._per_order_cap_cents)
        unit_cents = order_collateral_cents(side, price, 1)
        if unit_cents < 1:
            return 0
        # Closed form of "collateral(qty) + max_taker_fee(qty) <= cap", with the
        # fee expressed at its worst case price of 100 cents. Both sides are
        # integer, and the floor keeps the result on the safe side.
        denominator = unit_cents * BPS_ONE + self._fee_bps * PAYOUT_YES_CENTS
        return max(0, min(wanted, (cap_cents * BPS_ONE) // denominator))

    def place_limit(self, *, market_id: str, side: Side, price: int, qty: int) -> bool:
        """Plan one ``limit`` order, shrinking or dropping it when it does not fit.

        Args:
            market_id: Target market.
            side: Order side.
            qty: Desired quantity in contracts.
            price: Desired limit price in cents; it is clamped into the band.

        Returns:
            True when an intent was appended.
        """
        if not self.has_slot() or not self.has_room(market_id):
            return False
        limit_price = clamp_price(price)
        final_qty = self.affordable_qty(side, limit_price, qty)
        if final_qty < 1:
            return False
        cost = order_collateral_cents(side, limit_price, final_qty) + max_taker_fee_cents(self._fee_bps, final_qty)
        self._budget_cents -= cost
        self._resting_count[market_id] = self._resting_count.get(market_id, 0) + 1
        self._intents.append(
            OrderIntent(
                op="place",
                market_id=market_id,
                side=side,
                order_type=OrderType.LIMIT,
                price=limit_price,
                qty=final_qty,
            )
        )
        return True

    def cancel(self, *, market_id: str, order_id: str) -> bool:
        """Plan one ``cancel`` intent.

        Args:
            market_id: Market the order rests on, used for the per market count.
            order_id: The order to pull, taken from ``MarketObservation.my_orders``
                so it is always an order this agent owns.

        Returns:
            True when an intent was appended.
        """
        if not self.has_slot():
            return False
        self._intents.append(OrderIntent(op="cancel", order_id=order_id))
        self._resting_count[market_id] = max(0, self._resting_count.get(market_id, 0) - 1)
        return True


# --------------------------------------------------------------------------
# The shared skeleton of the six baselines
# --------------------------------------------------------------------------
class BaselineAgent:
    """Shared skeleton of the six baselines. Internal to ``pxe.agents``.

    Subclasses override :meth:`belief_ppm` (mandatory) and :meth:`plan_orders`
    (optional: the default plans nothing, which is what ``mute`` wants). This
    class owns everything that must not vary between baselines: the canonical
    market order, one prediction per open market, the action envelope and the
    ``AgentSource.SCRIPTED`` tag.
    """

    name: ClassVar[str] = "baseline"

    def __init__(self, *, agent_id: str, config: MatchConfig, rng: random.Random) -> None:
        """Bind a baseline to one seat.

        Args:
            agent_id: The seat, ``A1``..``A8``.
            config: Configuration of the match.
            rng: The agent's own substream.
        """
        self.agent_id = agent_id
        self.config = config
        self.rng = rng

    def reset(self, *, config: MatchConfig, rng: random.Random) -> None:
        """Clear every per match state, the generator included.

        Subclasses that keep memory override this and call ``super().reset``.

        Args:
            config: Configuration of the match about to start.
            rng: A freshly built substream for this match.
        """
        self.config = config
        self.rng = rng

    # -- hooks ------------------------------------------------------------
    def belief_ppm(self, observation: Observation, market: MarketObservation) -> int:
        """Return this agent's probability for one open market, in ppm.

        Args:
            observation: The full observation, for news, signals and cash.
            market: The market block to form a belief about.

        Returns:
            A probability in parts per million.

        Raises:
            NotImplementedError: Always, in this class.
        """
        raise NotImplementedError

    def plan_orders(
        self,
        observation: Observation,
        *,
        planner: OrderPlanner,
        beliefs: Mapping[str, int],
    ) -> None:
        """Add order intents to ``planner``. The default adds none.

        Args:
            observation: The full observation.
            planner: The budget aware intent builder to append to.
            beliefs: The belief of this tick per market id, for lookup only.
        """

    # -- the protocol -----------------------------------------------------
    def act(self, observation: Observation) -> AgentAction:
        """Turn one observation into one action.

        Args:
            observation: Everything this agent is allowed to know.

        Returns:
            An action carrying one prediction per open market (FR-6.2.4 never
            has to carry a value for a baseline) and the planned orders.
        """
        by_id = {m.market_id: m for m in observation.markets if m.status is MarketStatus.OPEN}
        beliefs: dict[str, int] = {}
        predictions: list[PredictionIntent] = []
        for market_id in sorted_ids(tuple(by_id)):
            belief = clamp_belief_ppm(self.belief_ppm(observation, by_id[market_id]))
            beliefs[market_id] = belief
            predictions.append(PredictionIntent(market_id=market_id, p_yes_ppm=belief))
        planner = OrderPlanner(observation, self.config)
        self.plan_orders(observation, planner=planner, beliefs=beliefs)
        orders = planner.intents
        return AgentAction(
            agent_id=self.agent_id,
            tick=observation.tick,
            action_version=self.config.action_version,
            predictions=tuple(predictions[:MAX_PREDICTIONS_PER_ACTION]),
            orders=orders,
            message_public=None,
            rationale=f"{self.name}: {len(predictions)} predictions, {len(orders)} orders",
            source=AgentSource.SCRIPTED,
        )

    # -- shared policy helpers -------------------------------------------
    def open_markets(self, observation: Observation) -> tuple[MarketObservation, ...]:
        """The tradable market blocks of an observation, in ascending market id.

        Args:
            observation: The current observation.

        Returns:
            The open blocks. The builder already sorts them; this re-sorts
            through ``sorted_ids`` so no baseline depends on that promise.
        """
        by_id = {m.market_id: m for m in observation.markets if m.status is MarketStatus.OPEN}
        return tuple(by_id[market_id] for market_id in sorted_ids(tuple(by_id)))

    def make_room(self, market: MarketObservation, *, planner: OrderPlanner) -> None:
        """Cancel the oldest resting order of a market that is at its cap.

        Args:
            market: The market block, whose ``my_orders`` is the whole truth
                about what this agent has resting there (T2.4 fidelity rule).
            planner: The planner to append the cancel to.
        """
        if planner.has_room(market.market_id) or not market.my_orders:
            return
        oldest = min(market.my_orders, key=lambda order: order.order_id)
        planner.cancel(market_id=market.market_id, order_id=oldest.order_id)

    def position_allows(self, market: MarketObservation, side: Side) -> bool:
        """True while adding to one side keeps the position inside the baseline cap.

        Args:
            market: The market block, whose ``position_qty`` is exact (T2.4).
            side: The side about to be added to.

        Returns:
            Whether the resulting position stays within
            ``MAX_BASELINE_POSITION_QTY``.
        """
        if side is Side.BUY:
            return market.position_qty < MAX_BASELINE_POSITION_QTY
        return market.position_qty > -MAX_BASELINE_POSITION_QTY

    def trade_on_edge(
        self,
        market: MarketObservation,
        *,
        planner: OrderPlanner,
        belief: int,
        min_edge_cents: int,
        base_qty: int = DEFAULT_ORDER_QTY,
    ) -> bool:
        """Take the touch when the book disagrees with a belief by enough cents.

        The order is a ``limit`` at the touch price, never a ``market`` order:
        the price is then exactly what the agent decided, the protection band of
        FR-5.4.3 cannot surprise it, and the fill happens at the maker price
        anyway (FR-5.4.1).

        Args:
            market: The market block to trade.
            planner: The planner to append to.
            belief: This agent's probability for the market, in ppm.
            min_edge_cents: Smallest edge worth crossing the spread for.
            base_qty: Size unit, scaled by the edge up to
                ``MAX_EDGE_MULTIPLE`` times.

        Returns:
            True when an order intent was planned.
        """
        target = price_from_ppm(belief)
        buy_edge = target - market.best_ask if market.best_ask is not None else 0
        sell_edge = market.best_bid - target if market.best_bid is not None else 0
        if market.best_ask is not None and buy_edge >= min_edge_cents and self.position_allows(market, Side.BUY):
            side, price, edge = Side.BUY, market.best_ask, buy_edge
        elif market.best_bid is not None and sell_edge >= min_edge_cents and self.position_allows(market, Side.SELL):
            side, price, edge = Side.SELL, market.best_bid, sell_edge
        else:
            return False
        self.make_room(market, planner=planner)
        return planner.place_limit(
            market_id=market.market_id,
            side=side,
            price=price,
            qty=base_qty * min(edge, MAX_EDGE_MULTIPLE),
        )


# --------------------------------------------------------------------------
# The factory
# --------------------------------------------------------------------------
#: Baseline name -> (module, class). The modules are imported lazily by
#: :func:`make_baseline` through :mod:`importlib` and never at module scope:
#: every baseline imports :class:`BaselineAgent` from this module, so a module
#: level import here would be a circular import.
_BASELINE_CLASSES: Mapping[str, tuple[str, str]] = {
    "fundamentalist": ("pxe.agents.baselines.fundamentalist", "FundamentalistAgent"),
    "momentum": ("pxe.agents.baselines.momentum", "MomentumAgent"),
    "noise": ("pxe.agents.baselines.noise", "NoiseTraderAgent"),
    "zero_intelligence": ("pxe.agents.baselines.zero_intelligence", "ZeroIntelligenceAgent"),
    "bayesian": ("pxe.agents.baselines.bayesian", "BayesianAgent"),
    "mute": ("pxe.agents.baselines.mute", "MuteAgent"),
}


def make_baseline(name: str, *, agent_id: str, rng: random.Random, config: MatchConfig) -> ScriptedAgent:
    """Build one scripted baseline by name.

    This is the only way a baseline is reached: nothing outside ``pxe.agents``
    imports a baseline module (CONTRACTS section 7.15).

    Args:
        name: One of :data:`BASELINES`.
        agent_id: The seat the agent plays, ``A1``..``A8``.
        rng: The agent's own substream, that is
            ``root.child(f"agent/{agent_id}").substream(f"agent.{agent_id}")``.
        config: Configuration of the match.

    Returns:
        A fresh agent, already bound to the seat and the substream.

    Raises:
        InvalidConfigError: If ``name`` is not a registered baseline.
    """
    entry = _BASELINE_CLASSES.get(name)
    if entry is None:
        raise InvalidConfigError("unknown baseline", name=name, known=",".join(BASELINES))
    module_name, class_name = entry
    module = importlib.import_module(module_name)
    factory: Callable[..., ScriptedAgent] = getattr(module, class_name)
    return factory(agent_id=agent_id, config=config, rng=rng)
