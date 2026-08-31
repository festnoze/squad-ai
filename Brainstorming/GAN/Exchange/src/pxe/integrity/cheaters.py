"""The scripted cheater bench that calibrates the detectors (T5.5, CONTRACTS 7.18).

Four cheaters, one per detectable behaviour, reachable only through
:func:`make_cheater`:

* ``colluder`` moves wealth to an accomplice through executions far from the
  reference price, which is what :class:`~pxe.integrity.detectors.CollusionDetector`
  and :class:`~pxe.integrity.detectors.OffMarketTransferDetector` are for;
* ``washer`` passes the same contracts back and forth with an accomplice, volume
  without exposure (:class:`~pxe.integrity.detectors.WashTradingDetector`);
* ``spoofer`` quotes size it never means to trade and pulls it the next tick
  (:class:`~pxe.integrity.detectors.SpoofingDetector`);
* ``liar`` declares one probability and trades against it
  (:class:`~pxe.integrity.detectors.PredictionMismatchDetector`).

Why the bench exists at all
---------------------------
AC-P6 is quantitative: precision and recall at or above 0.9 for collusion, under
5 % false positives on an honest population. A threshold cannot be calibrated
against an intuition, so these four agents produce the positive class of the
bench while the six baselines of :mod:`pxe.agents` produce the negative one, and
``tests/test_integrity.py`` measures both on real generated matches, on a
calibration seed set held out from the evaluation seed set.

What a cheater is allowed to do
-------------------------------
Exactly what any agent is allowed to do: it sees an
:class:`~pxe.types.Observation` and returns an :class:`~pxe.types.AgentAction`
that goes through ``validate_action`` like everybody else's. There is no back
channel. Two accomplices coordinate the only way two scripted agents can, by
each computing the same public function of the tick and the observation both of
them receive: the roles come from the seat ids, the cadence from the tick number
and the target market from the observation's own market list. That is also why
the cheats are *detectable* rather than impossible: naive self execution is
blocked at engine level (FR-5.4.4), so a cheat needs an accomplice, and an
accomplice leaves a pair level footprint.

Why the transfers are large and why they sweep the book
-------------------------------------------------------
An execution far from the reference price cannot be arranged quietly. The
market maker quotes both sides within a few cents of the reference price
(FR-5.8.1), so any order that would print far from it is intercepted by better
prices first: the accomplice's resting order at 5 cents is only reached by a sell
large enough to walk through the whole book above it. The colluder therefore
sizes its sweep from the visible depth and transfers a quantity large enough that
the pair's own volume still dominates its footprint, which is exactly the
signature the detectors look for. Nothing here is a trick against the engine:
every order is a legal order, and the engine's own solvency and cap rules apply.

Determinism
-----------
No cheater draws from its ``random.Random``: each of them is a pure function of
``(observation, tick)``. The generator is still taken and still replaced by
``reset``, because the :class:`~pxe.agents.base.ScriptedAgent` protocol requires
it and because a tournament reuses agent objects across matches (CONTRACTS
section 3.1).
"""

from __future__ import annotations

import random
from typing import ClassVar

from pxe.agents.base import ScriptedAgent
from pxe.errors import InvalidConfigError
from pxe.types import (
    PAYOUT_YES_CENTS,
    PPM_ONE,
    AgentAction,
    AgentSource,
    MarketObservation,
    MarketStatus,
    MatchConfig,
    Observation,
    Order,
    OrderIntent,
    OrderType,
    PredictionIntent,
    Side,
    clamp_price,
    order_collateral_cents,
    sorted_ids,
)

__all__ = ["CHEATERS", "make_cheater"]

#: The four scripted cheaters (CONTRACTS section 7.18).
CHEATERS: tuple[str, ...] = ("colluder", "washer", "spoofer", "liar")

#: Probability, in ppm, of one cent of price.
_PPM_PER_CENT: int = PPM_ONE // PAYOUT_YES_CENTS

#: Beliefs are clamped away from the two certainties, exactly as the baselines
#: clamp theirs, so a cheater's Brier stays finite and its declared probability
#: is always a legal one.
_BELIEF_MIN_PPM: int = 10_000
_BELIEF_MAX_PPM: int = 990_000

#: A single order never locks more than ``free_cash // _BUDGET_DIVISOR`` cents.
#: A cheater that bankrupts itself at tick 4 is not a bench, it is a bankruptcy
#: test: the freeze would stop its own footprint from accumulating (FR-5.5.5).
_BUDGET_DIVISOR: int = 3

#: The price the colluding pair meets at, in cents. Far below any reference
#: price a template produces, so the print is many standard deviations from it
#: and the transfer is unambiguous.
_OFF_MARKET_PRICE: int = 5

#: One transfer every this many ticks. Not every tick: the sweep has to be large
#: to reach the accomplice, so a handful of transfers already leaves a position
#: the source has to carry to the end of the match.
_TRANSFER_PERIOD: int = 3

#: Contracts moved per transfer, split into :data:`_TRANSFER_SLICES` resting
#: orders. Two properties are wanted and both are measured on the bench: the
#: transfer has to dominate the quantity the sweep spends on the rest of the book
#: (otherwise the pair's own concentration, which is what the collusion index
#: multiplies, drops below the threshold), and the slicing has to produce several
#: executions per round so the pair clears the ``min_trades`` evidence floor
#: without needing a long match.
_TRANSFER_QTY: int = 1_200
_TRANSFER_SLICES: int = 3

#: Absolute position either accomplice will carry. Past it the cheat stops, which
#: keeps both of them solvent for the whole match: a frozen source stops trading
#: (FR-5.5.5) and a bench whose positive class goes bankrupt at tick nine
#: measures the freeze rather than the detector.
_TRANSFER_POSITION_CAP: int = 5_000

#: One wash round trip every this many ticks, and its size. The direction flips
#: every round, so the pair's position comes back to where it started and the
#: printed volume is the only trace left.
_WASH_PERIOD: int = 2
_WASH_QTY: int = 200

#: Distance from the reference price at which the spoofer quotes, in cents. Well
#: outside the market maker's spread, so the order is visible depth that cannot
#: execute against a resting quote.
_SPOOF_DISTANCE_CENTS: int = 12

#: Size of one spoofed order and how many markets the spoofer works at once.
_SPOOF_QTY: int = 300
_SPOOF_MARKETS: int = 2

#: How far the liar's declared probability sits from the market, in ppm, and how
#: many contracts it trades against it per market and per tick.
_LIE_GAP_PPM: int = 450_000
_LIAR_QTY: int = 40
_LIAR_MARKETS: int = 2
_LIAR_POSITION_CAP: int = 1_200


def _belief_from_price(price: int) -> int:
    """Return the market implied probability of one price, in ppm.

    Args:
        price: A price in cents.

    Returns:
        The implied probability, clamped into the tradable belief band.
    """
    return max(_BELIEF_MIN_PPM, min(_BELIEF_MAX_PPM, clamp_price(price) * _PPM_PER_CENT))


def _open_markets(observation: Observation) -> tuple[MarketObservation, ...]:
    """Return the tradable market blocks of an observation, ascending.

    Args:
        observation: The current observation.

    Returns:
        The open blocks in canonical market order. The builder already sorts
        them; this re-sorts through :func:`~pxe.types.sorted_ids` so no cheater
        depends on that promise.
    """
    by_id = {m.market_id: m for m in observation.markets if m.status is MarketStatus.OPEN}
    return tuple(by_id[market_id] for market_id in sorted_ids(tuple(by_id)))


def _affordable_qty(*, side: Side, price: int, free_cash_cents: int, wanted_qty: int) -> int:
    """Return the largest part of one order the free cash actually covers.

    The FR-5.5.1 collateral formula, read from the observation's own free cash so
    the intent exists only if the P3 solvency check would accept it. The taker
    fee is not modelled here because it is floored at zero by default and a
    cheater that is one cent short is a cheater that placed one contract fewer.

    Args:
        side: Order side.
        price: Limit price in cents, already inside the band.
        free_cash_cents: What the observation reports.
        wanted_qty: The quantity the cheat asked for.

    Returns:
        A quantity in ``0..wanted_qty``. Zero means the intent must not be sent.
    """
    unit_cents = order_collateral_cents(side, clamp_price(price), 1)
    if unit_cents < 1 or wanted_qty < 1:
        return 0
    budget_cents = max(0, free_cash_cents) // _BUDGET_DIVISOR
    return max(0, min(wanted_qty, budget_cents // unit_cents))


def _visible_depth_above(market: MarketObservation, price: int) -> int:
    """Return the resting bid quantity strictly better than one price.

    This is what a sweep has to spend before it reaches an accomplice's order at
    ``price``. Only the levels the observation publishes are visible
    (``DEPTH_LEVELS``), which is the whole point: a cheater sees exactly what an
    agent sees, so it undersizes rather than oversizes and never leaves a
    resting residual at the off market price for a third party to pick up.

    Args:
        market: The market block.
        price: The accomplice's price.

    Returns:
        The visible quantity resting above ``price``.
    """
    return sum(qty for level_price, qty in market.bid_depth if level_price > price)


def _cancel_intents(orders: tuple[Order, ...], *, limit: int) -> list[OrderIntent]:
    """Return one ``cancel`` intent per resting order, oldest first.

    Args:
        orders: ``MarketObservation.my_orders``, the whole truth about what this
            agent has resting there.
        limit: How many intents the caller can still afford to send.

    Returns:
        The cancels, at most ``limit`` of them.
    """
    ordered = sorted(orders, key=lambda order: order.order_id)
    return [OrderIntent(op="cancel", order_id=order.order_id) for order in ordered[: max(0, limit)]]


class _Cheater:
    """Shared skeleton of the four cheaters. Internal to :mod:`pxe.integrity`.

    It owns everything that must not vary between them: the seat binding, the
    generator handover, one prediction per open market and the action envelope.
    Subclasses override :meth:`plan` and, for the liar, :meth:`belief_ppm`.

    ``BaselineAgent`` is not reused and not subclassed: it is internal to
    ``pxe.agents`` and ruling R57 is explicit that a cheater composes what
    ``make_baseline`` returns rather than reaching into that class. None of these
    four wants a baseline's policy anyway, since a cheat is defined by what it
    does *instead* of trading a belief.
    """

    name: ClassVar[str] = "cheater"

    def __init__(
        self,
        *,
        agent_id: str,
        partner_id: str | None,
        config: MatchConfig,
        rng: random.Random,
    ) -> None:
        """Bind a cheater to one seat.

        Args:
            agent_id: The seat, ``A1``..``A8``.
            partner_id: The accomplice's seat, or ``None`` for a solo cheat.
            config: Configuration of the match.
            rng: The agent's own substream. Unused by every cheater and kept
                because the protocol has it.
        """
        self.agent_id = agent_id
        self.partner_id = partner_id
        self.config = config
        self.rng = rng

    def reset(self, *, config: MatchConfig, rng: random.Random) -> None:
        """Clear every per match state, the generator included.

        Args:
            config: Configuration of the match about to start.
            rng: A freshly built substream for this match.
        """
        self.config = config
        self.rng = rng

    # -- hooks ------------------------------------------------------------
    def belief_ppm(self, market: MarketObservation) -> int:
        """Return the probability this cheater declares for one market.

        The default is the market implied probability, which is deliberately
        *honest*: three of the four cheats are about order flow, and a cheater
        whose predictions were also wrong would raise a
        ``prediction_position_mismatch`` alert on top of its own family and make
        the per family bench numbers unreadable.

        Args:
            market: The market block.

        Returns:
            A probability in ppm.
        """
        return _belief_from_price(market.ref_price)

    def plan(self, observation: Observation) -> list[OrderIntent]:
        """Return the order intents of one tick. The default returns none.

        Args:
            observation: The current observation.

        Returns:
            The intents, in submission order.
        """
        return []

    # -- the protocol -----------------------------------------------------
    def act(self, observation: Observation) -> AgentAction:
        """Turn one observation into one action.

        Args:
            observation: Everything this agent is allowed to know.

        Returns:
            The action: one prediction per open market and whatever the cheat
            planned, capped at ``config.max_orders_per_action``.
        """
        markets = _open_markets(observation)
        predictions = tuple(
            PredictionIntent(market_id=market.market_id, p_yes_ppm=self.belief_ppm(market)) for market in markets
        )
        orders = tuple(self.plan(observation)[: self.config.max_orders_per_action])
        return AgentAction(
            agent_id=self.agent_id,
            tick=observation.tick,
            action_version=self.config.action_version,
            predictions=predictions,
            orders=orders,
            message_public=None,
            rationale=f"{self.name}: {len(predictions)} predictions, {len(orders)} orders",
            source=AgentSource.SCRIPTED,
        )

    # -- shared helpers ---------------------------------------------------
    def accomplice(self) -> str:
        """Return the accomplice's seat id.

        Returns:
            The partner id.

        Raises:
            InvalidConfigError: If this cheat needs an accomplice and was built
                without one. :func:`make_cheater` already refuses that, so
                reaching here is a programming error and not a configuration.
        """
        if self.partner_id is None:  # pragma: no cover - make_cheater refuses it
            raise InvalidConfigError("cheat needs an accomplice", name=self.name, agent_id=self.agent_id)
        return self.partner_id

    def plays_first_role(self) -> bool:
        """Return whether this seat is the canonically first of the pair.

        Both accomplices evaluate this and get complementary answers, which is
        how two agents that cannot talk to each other still agree on who does
        what.

        Returns:
            True for the canonically smaller seat id (CONTRACTS section 2.3).
        """
        return sorted_ids((self.agent_id, self.accomplice()))[0] == self.agent_id

    def target_market(self, observation: Observation) -> MarketObservation | None:
        """Return the market the pair meets on, or ``None`` when none is open.

        The first open market in canonical order. Both accomplices receive the
        same market list with the same statuses, so both pick the same one
        without exchanging anything.

        Args:
            observation: The current observation.

        Returns:
            The market block, or ``None``.
        """
        markets = _open_markets(observation)
        return markets[0] if markets else None


class _Colluder(_Cheater):
    """Transfers wealth to an accomplice through executions far from the reference price.

    Every :data:`_TRANSFER_PERIOD` ticks, on the first open market:

    * the **sink** (the canonically first seat) rests :data:`_TRANSFER_SLICES`
      buy orders at :data:`_OFF_MARKET_PRICE`, which is far below every bid and
      therefore parks safely at the bottom of the book;
    * the **source** sells the visible depth above that price plus the whole
      transfer, so the sweep walks through the market maker and lands on the
      accomplice.

    The sink ends up long contracts it paid five cents for and the source ends up
    short at five cents: the wealth moved, the print is many standard deviations
    from the reference price, and the pair's flows are exactly opposite on
    exactly the same ticks. Both accomplices cancel their own resting orders on
    that market before each round, so nothing they leave behind can be picked off
    by a third party.
    """

    name: ClassVar[str] = "colluder"

    def plan(self, observation: Observation) -> list[OrderIntent]:
        """Rest the receiving bids, or sweep the book down to them.

        Args:
            observation: The current observation.

        Returns:
            The intents of this tick.
        """
        market = self.target_market(observation)
        if market is None or observation.tick % _TRANSFER_PERIOD != 0:
            return []
        intents = _cancel_intents(market.my_orders, limit=self.config.max_orders_per_action - _TRANSFER_SLICES)
        if self.plays_first_role():
            return intents + self._receive(market, observation.free_cash_cents)
        return intents + self._send(market, observation.free_cash_cents)

    def _receive(self, market: MarketObservation, free_cash_cents: int) -> list[OrderIntent]:
        """Rest the slices the accomplice's sweep will land on.

        Args:
            market: The target market block.
            free_cash_cents: What the observation reports.

        Returns:
            Up to :data:`_TRANSFER_SLICES` buy intents at the off market price.
        """
        if market.position_qty >= _TRANSFER_POSITION_CAP:
            return []
        slice_qty = _affordable_qty(
            side=Side.BUY,
            price=_OFF_MARKET_PRICE,
            free_cash_cents=free_cash_cents,
            wanted_qty=_TRANSFER_QTY // _TRANSFER_SLICES,
        )
        if slice_qty < 1:
            return []
        return [
            OrderIntent(
                op="place",
                market_id=market.market_id,
                side=Side.BUY,
                order_type=OrderType.LIMIT,
                price=_OFF_MARKET_PRICE,
                qty=slice_qty,
            )
            for _ in range(_TRANSFER_SLICES)
        ]

    def _send(self, market: MarketObservation, free_cash_cents: int) -> list[OrderIntent]:
        """Sweep the book down to the accomplice's resting bids.

        Args:
            market: The target market block.
            free_cash_cents: What the observation reports.

        Returns:
            One sell intent, or none when the position cap is reached.
        """
        if market.position_qty <= -_TRANSFER_POSITION_CAP:
            return []
        wanted = _TRANSFER_QTY + _visible_depth_above(market, _OFF_MARKET_PRICE)
        qty = _affordable_qty(
            side=Side.SELL,
            price=_OFF_MARKET_PRICE,
            free_cash_cents=free_cash_cents,
            wanted_qty=wanted,
        )
        if qty < 1:
            return []
        return [
            OrderIntent(
                op="place",
                market_id=market.market_id,
                side=Side.SELL,
                order_type=OrderType.LIMIT,
                price=_OFF_MARKET_PRICE,
                qty=qty,
            )
        ]


class _Washer(_Cheater):
    """Passes the same contracts back and forth with an accomplice.

    Every :data:`_WASH_PERIOD` ticks the pair meets at the reference price of the
    first open market, which is inside the market maker's spread and therefore
    reachable by nobody else's resting quote, and swaps :data:`_WASH_QTY`
    contracts. The direction flips every round, so after two rounds both
    positions are back where they started while the printed volume has grown by
    four times the size: volume without exposure, which is what economic wash
    trading is.
    """

    name: ClassVar[str] = "washer"

    def plan(self, observation: Observation) -> list[OrderIntent]:
        """Post this round's leg of the round trip.

        Args:
            observation: The current observation.

        Returns:
            The intents of this tick.
        """
        market = self.target_market(observation)
        if market is None or observation.tick % _WASH_PERIOD != 0:
            return []
        intents = _cancel_intents(market.my_orders, limit=self.config.max_orders_per_action - 1)
        # On an even round the canonically first seat buys and the second sells;
        # on an odd round they swap. Both accomplices evaluate the same two
        # public facts (the tick and their own two ids) and reach complementary
        # answers, which is the only coordination two scripted agents can have.
        first_seat_buys = (observation.tick // _WASH_PERIOD) % 2 == 0
        side = Side.BUY if first_seat_buys == self.plays_first_role() else Side.SELL
        price = clamp_price(market.ref_price)
        qty = _affordable_qty(side=side, price=price, free_cash_cents=observation.free_cash_cents, wanted_qty=_WASH_QTY)
        if qty < 1:
            return intents
        intents.append(
            OrderIntent(
                op="place",
                market_id=market.market_id,
                side=side,
                order_type=OrderType.LIMIT,
                price=price,
                qty=qty,
            )
        )
        return intents


class _Spoofer(_Cheater):
    """Quotes size it never means to trade and pulls it the next tick.

    On the first :data:`_SPOOF_MARKETS` open markets it cancels everything it
    rests and posts one buy :data:`_SPOOF_DISTANCE_CENTS` below the reference
    price and one sell as far above it. Both sit well outside the market maker's
    spread, so they are visible depth that cannot execute against a resting
    quote, and both are gone by the next tick: the cancel to execution ratio goes
    to one.
    """

    name: ClassVar[str] = "spoofer"

    def plan(self, observation: Observation) -> list[OrderIntent]:
        """Pull yesterday's quotes and post today's.

        Args:
            observation: The current observation.

        Returns:
            The intents of this tick.
        """
        intents: list[OrderIntent] = []
        budget = self.config.max_orders_per_action
        for market in _open_markets(observation)[:_SPOOF_MARKETS]:
            intents.extend(_cancel_intents(market.my_orders, limit=budget - len(intents) - 2))
            for side, price in (
                (Side.BUY, market.ref_price - _SPOOF_DISTANCE_CENTS),
                (Side.SELL, market.ref_price + _SPOOF_DISTANCE_CENTS),
            ):
                limit_price = clamp_price(price)
                qty = _affordable_qty(
                    side=side,
                    price=limit_price,
                    free_cash_cents=observation.free_cash_cents,
                    wanted_qty=_SPOOF_QTY,
                )
                if qty < 1 or len(intents) >= budget:
                    continue
                intents.append(
                    OrderIntent(
                        op="place",
                        market_id=market.market_id,
                        side=side,
                        order_type=OrderType.LIMIT,
                        price=limit_price,
                        qty=qty,
                    )
                )
        return intents


class _Liar(_Cheater):
    """Declares one probability and trades against it, on purpose.

    It picks the side that contradicts the market most: under a reference price
    of fifty cents it declares a probability :data:`_LIE_GAP_PPM` *above* the
    market and sells into the bid, and above fifty cents it declares as far
    *below* and buys the offer. Either way the declared probability and the price
    it accepts disagree by roughly forty-five points, which is PRD section 7.2's
    "declarer 0,80 et vendre massivement" with the sign chosen so the cheat
    survives a market that drifts.

    Nothing about this is punished: prediction and position incoherence is a
    descriptor (PRD section 7.2), so the liar is detected and ranked exactly as
    its PnL and its Brier say it should be.
    """

    name: ClassVar[str] = "liar"

    def belief_ppm(self, market: MarketObservation) -> int:
        """Return a probability far from the market, on the contradicting side.

        Args:
            market: The market block.

        Returns:
            A probability in ppm.
        """
        implied = _belief_from_price(market.ref_price)
        if implied >= PPM_ONE // 2:
            return max(_BELIEF_MIN_PPM, implied - _LIE_GAP_PPM)
        return min(_BELIEF_MAX_PPM, implied + _LIE_GAP_PPM)

    def plan(self, observation: Observation) -> list[OrderIntent]:
        """Trade the touch on the side its own declaration disagrees with.

        Args:
            observation: The current observation.

        Returns:
            The intents of this tick.
        """
        intents: list[OrderIntent] = []
        for market in _open_markets(observation)[:_LIAR_MARKETS]:
            implied = _belief_from_price(market.ref_price)
            if implied >= PPM_ONE // 2:
                side, touch = Side.BUY, market.best_ask
                blocked = market.position_qty >= _LIAR_POSITION_CAP
            else:
                side, touch = Side.SELL, market.best_bid
                blocked = market.position_qty <= -_LIAR_POSITION_CAP
            if touch is None or blocked:
                continue
            price = clamp_price(touch)
            qty = _affordable_qty(
                side=side,
                price=price,
                free_cash_cents=observation.free_cash_cents,
                wanted_qty=_LIAR_QTY,
            )
            if qty < 1:
                continue
            intents.append(
                OrderIntent(
                    op="place",
                    market_id=market.market_id,
                    side=side,
                    order_type=OrderType.LIMIT,
                    price=price,
                    qty=qty,
                )
            )
        return intents


#: Cheater name to its class. Private: :func:`make_cheater` is the only door, so
#: no caller outside this module names a class.
_CHEATER_CLASSES: dict[str, type[_Cheater]] = {
    "colluder": _Colluder,
    "washer": _Washer,
    "spoofer": _Spoofer,
    "liar": _Liar,
}

#: The two cheats that need an accomplice. A collusion bench built with one
#: colluder and no partner would silently measure nothing.
_NEEDS_PARTNER: frozenset[str] = frozenset({"colluder", "washer"})


def make_cheater(
    name: str,
    *,
    agent_id: str,
    partner_id: str | None,
    rng: random.Random,
    config: MatchConfig,
) -> ScriptedAgent:
    """Build one scripted cheater by name (CONTRACTS section 7.18).

    Args:
        name: One of :data:`CHEATERS`.
        agent_id: The seat the cheater plays, ``A1``..``A8``.
        partner_id: The accomplice's seat for ``colluder`` and ``washer``,
            ``None`` for ``spoofer`` and ``liar``. Both accomplices are built
            with each other's id and derive their roles from the two ids alone.
        rng: The agent's own substream, that is
            ``root.child(f"agent/{agent_id}").substream(f"agent.{agent_id}")``.
            No cheater draws from it; it is taken because the protocol has it.
        config: Configuration of the match.

    Returns:
        A fresh cheater, already bound to the seat.

    Raises:
        InvalidConfigError: If ``name`` is not a registered cheater, if a cheat
            that needs an accomplice was given none, or if a cheater was made its
            own accomplice.
    """
    entry = _CHEATER_CLASSES.get(name)
    if entry is None:
        raise InvalidConfigError("unknown cheater", name=name, known=",".join(CHEATERS))
    if name in _NEEDS_PARTNER and partner_id is None:
        raise InvalidConfigError("cheat needs an accomplice", name=name, agent_id=agent_id)
    if partner_id == agent_id:
        raise InvalidConfigError("a cheater cannot be its own accomplice", name=name, agent_id=agent_id)
    return entry(agent_id=agent_id, partner_id=partner_id, config=config, rng=rng)
