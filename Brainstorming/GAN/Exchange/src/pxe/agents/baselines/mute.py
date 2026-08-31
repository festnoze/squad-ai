"""The mute baseline: the AC-P9 reference population.

It declares one probability per open market and places no order, ever. AC-P9
("guaranteed liquidity") is stated over a match where no agent is active: with
six mute seats the only orders in the book are the reference market maker's, so
the acceptance criterion (every open market two sided on at least 95 % of ticks,
the reference price defined at every tick) measures the market maker and nothing
else. ``tests/conftest.py::scripted_gateway`` builds exactly this population,
which makes ``mute`` the cheapest way to drive a whole match with no LLM.

Its declared probability is the market implied one, ``ref_price / 100``. That is
a deliberate choice over the FR-6.2.4 default of 500 000 ppm: it makes ``mute``
the market implied calibration reference, which is the natural yardstick for
"did this agent's Brier beat the price?", and it costs nothing because reading
``ref_price`` needs no state.
"""

from typing import ClassVar

from pxe.agents.base import BaselineAgent, ppm_from_price
from pxe.types import MarketObservation, Observation


class MuteAgent(BaselineAgent):
    """Predictions only, no orders and no message (AC-P9)."""

    name: ClassVar[str] = "mute"

    def belief_ppm(self, observation: Observation, market: MarketObservation) -> int:
        """Return the market implied probability of the reference price.

        Args:
            observation: The current observation, unused.
            market: The market block to form a belief about.

        Returns:
            ``ref_price`` converted to parts per million.
        """
        return ppm_from_price(market.ref_price)
