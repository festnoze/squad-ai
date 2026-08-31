"""The noisy fundamentalist baseline (PRD section 8, T2.2).

It is the signal driven member of the population: it keeps one running estimate
per market, moves it toward every private signal it receives (weighted by the
signal's self declared precision), and trades when the book disagrees with that
estimate by enough cents to be worth crossing the spread. The "noisy" half of
the name is literal: the estimate it acts on is its running estimate plus a
bounded random perturbation drawn from its own substream, so it is a plausible
but imperfect trader rather than an oracle.

It is the reference the T2.2 exit criterion compares against the noise trader:
using signals must pay, or the information channel of FR-5.3.1 is decoration.
"""

import random
from collections.abc import Mapping
from typing import ClassVar

from pxe.agents.base import (
    BaselineAgent,
    OrderPlanner,
    blend_ppm,
    clamp_belief_ppm,
    ppm_from_price,
    signal_evidence,
    signals_for_market,
)
from pxe.rng import randint
from pxe.types import MarketObservation, MatchConfig, Observation

#: Widest perturbation, in ppm, added to the running estimate before acting.
#: 40_000 ppm is four cents of price: enough to make the agent miss thin edges,
#: small enough that a strong signal still dominates.
NOISE_PPM: int = 40_000
#: Weight given to the public prior the first time a market is seen, against the
#: market implied probability of the current reference price.
PRIOR_WEIGHT_PPM: int = 700_000
#: Smallest disagreement, in cents, worth crossing the spread for.
MIN_EDGE_CENTS: int = 3


class FundamentalistAgent(BaselineAgent):
    """Trades a running, signal fed estimate of each market's probability."""

    name: ClassVar[str] = "fundamentalist"

    def __init__(self, *, agent_id: str, config: MatchConfig, rng: random.Random) -> None:
        """Bind the agent to a seat and start with no estimate at all.

        Args:
            agent_id: The seat, ``A1``..``A8``.
            config: Configuration of the match.
            rng: The agent's own substream.
        """
        super().__init__(agent_id=agent_id, config=config, rng=rng)
        self._estimate_ppm: dict[str, int] = {}

    def reset(self, *, config: MatchConfig, rng: random.Random) -> None:
        """Drop every estimate and take the new substream (CONTRACTS section 3.1).

        Args:
            config: Configuration of the match about to start.
            rng: A freshly built substream for this match.
        """
        super().reset(config=config, rng=rng)
        self._estimate_ppm = {}

    def belief_ppm(self, observation: Observation, market: MarketObservation) -> int:
        """Update the running estimate with this tick's signals, then perturb it.

        Args:
            observation: The current observation.
            market: The market block to form a belief about.

        Returns:
            The perturbed estimate in ppm.
        """
        estimate = self._estimate_ppm.get(market.market_id)
        if estimate is None:
            estimate = blend_ppm(
                ppm_from_price(market.ref_price),
                ppm_from_price(market.prior_price),
                PRIOR_WEIGHT_PPM,
            )
        for signal in signals_for_market(observation, market.market_id):
            implied_ppm, weight_ppm = signal_evidence(signal)
            estimate = blend_ppm(estimate, implied_ppm, weight_ppm)
        self._estimate_ppm[market.market_id] = estimate
        return clamp_belief_ppm(estimate + randint(self.rng, -NOISE_PPM, NOISE_PPM))

    def plan_orders(
        self,
        observation: Observation,
        *,
        planner: OrderPlanner,
        beliefs: Mapping[str, int],
    ) -> None:
        """Cross the spread on every market where the edge is at least three cents.

        Args:
            observation: The current observation.
            planner: The budget aware intent builder.
            beliefs: The belief of this tick per market id.
        """
        for market in self.open_markets(observation):
            belief = beliefs.get(market.market_id, ppm_from_price(market.ref_price))
            self.trade_on_edge(
                market,
                planner=planner,
                belief=belief,
                min_edge_cents=MIN_EDGE_CENTS,
            )
