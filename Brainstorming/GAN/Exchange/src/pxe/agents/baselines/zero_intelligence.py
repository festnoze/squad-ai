"""The zero intelligence baseline (PRD section 8, T2.2).

The Gode and Sunder ZI-C trader, transposed to a binary contract book: it
ignores the book, the news, its signals and its own position, draws a side and a
limit price uniformly over the whole tradable band, and is constrained by
nothing except its budget. That budget constraint is the "C" of ZI-C and it is
not optional here: an agent that asks for collateral it does not have would be
answered with ``OrderRejected(INSUFFICIENT_COLLATERAL)``, which is a validation
event and not a strategy.

Its declared probability is deliberately the FR-6.2.4 default,
``DEFAULT_PREDICTION_PPM``, on every market and every tick: zero intelligence
means no opinion, and it gives the calibration metrics of A16 a known constant
reference point (its Brier is exactly the variance of the outcome frequency).
"""

from collections.abc import Mapping
from typing import ClassVar

from pxe.agents.base import (
    DEFAULT_ORDER_QTY,
    BaselineAgent,
    OrderPlanner,
)
from pxe.rng import bernoulli, choice, randint
from pxe.types import (
    DEFAULT_PREDICTION_PPM,
    PRICE_MAX,
    PRICE_MIN,
    MarketObservation,
    Observation,
    Side,
)

#: Probability of touching a given market on a given tick.
TRADE_PROBABILITY: float = 0.5
#: Size bounds of a random order, in contracts.
MIN_QTY: int = DEFAULT_ORDER_QTY // 2
MAX_QTY: int = DEFAULT_ORDER_QTY * 3


class ZeroIntelligenceAgent(BaselineAgent):
    """Uniform random side and price over the whole band, budget constrained."""

    name: ClassVar[str] = "zero_intelligence"

    def belief_ppm(self, observation: Observation, market: MarketObservation) -> int:
        """Return the no opinion probability, always.

        Args:
            observation: The current observation, unused.
            market: The market block, unused.

        Returns:
            :data:`~pxe.types.DEFAULT_PREDICTION_PPM`.
        """
        return DEFAULT_PREDICTION_PPM

    def plan_orders(
        self,
        observation: Observation,
        *,
        planner: OrderPlanner,
        beliefs: Mapping[str, int],
    ) -> None:
        """Draw a side and a price uniformly, ignoring everything the book says.

        Args:
            observation: The current observation.
            planner: The budget aware intent builder.
            beliefs: The belief of this tick per market id, unused here.
        """
        for market in self.open_markets(observation):
            if not bernoulli(self.rng, TRADE_PROBABILITY):
                continue
            side = choice(self.rng, (Side.BUY, Side.SELL))
            price = randint(self.rng, PRICE_MIN, PRICE_MAX)
            qty = randint(self.rng, MIN_QTY, MAX_QTY)
            if not self.position_allows(market, side):
                continue
            self.make_room(market, planner=planner)
            planner.place_limit(market_id=market.market_id, side=side, price=price, qty=qty)
