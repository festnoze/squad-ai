"""The noise trader baseline (PRD section 8, T2.2).

It has beliefs, but they are noise: a random perturbation of the market implied
probability, redrawn every tick and never accumulated. It trades around the
reference price with random sides and random sizes. Its role in the population
is to be the floor: the T2.2 exit criterion is that the fundamentalist beats it
in TrueSkill, so a signal driven agent that cannot beat random noise is a bug
somewhere in the information channel, not a bad strategy.

It differs from ``zero_intelligence`` on purpose: the noise trader still looks
at the reference price (its orders are near the market and it declares a
probability near the market), while the zero intelligence trader ignores the
book completely and prices uniformly over the whole band.
"""

from collections.abc import Mapping
from typing import ClassVar

from pxe.agents.base import (
    DEFAULT_ORDER_QTY,
    BaselineAgent,
    OrderPlanner,
    clamp_belief_ppm,
    ppm_from_price,
)
from pxe.rng import bernoulli, choice, randint
from pxe.types import MarketObservation, Observation, Side

#: Widest perturbation of the market implied probability, in ppm.
BELIEF_NOISE_PPM: int = 150_000
#: Probability of touching a given market on a given tick.
TRADE_PROBABILITY: float = 0.35
#: Widest distance from the reference price, in cents, of a random quote.
QUOTE_SPAN_CENTS: int = 5
#: Size bounds of a random order, in contracts.
MIN_QTY: int = DEFAULT_ORDER_QTY // 2
MAX_QTY: int = DEFAULT_ORDER_QTY * 3


class NoiseTraderAgent(BaselineAgent):
    """Declares a noisy probability and quotes randomly around the reference price."""

    name: ClassVar[str] = "noise"

    def belief_ppm(self, observation: Observation, market: MarketObservation) -> int:
        """Perturb the market implied probability with a fresh draw every tick.

        Args:
            observation: The current observation.
            market: The market block to form a belief about.

        Returns:
            A noisy probability in ppm.
        """
        implied = ppm_from_price(market.ref_price)
        return clamp_belief_ppm(implied + randint(self.rng, -BELIEF_NOISE_PPM, BELIEF_NOISE_PPM))

    def plan_orders(
        self,
        observation: Observation,
        *,
        planner: OrderPlanner,
        beliefs: Mapping[str, int],
    ) -> None:
        """Quote a random side at a random price near the reference, sometimes.

        Args:
            observation: The current observation.
            planner: The budget aware intent builder.
            beliefs: The belief of this tick per market id, unused here.
        """
        for market in self.open_markets(observation):
            if not bernoulli(self.rng, TRADE_PROBABILITY):
                continue
            side = choice(self.rng, (Side.BUY, Side.SELL))
            price = market.ref_price + randint(self.rng, -QUOTE_SPAN_CENTS, QUOTE_SPAN_CENTS)
            qty = randint(self.rng, MIN_QTY, MAX_QTY)
            if not self.position_allows(market, side):
                continue
            self.make_room(market, planner=planner)
            planner.place_limit(market_id=market.market_id, side=side, price=price, qty=qty)
