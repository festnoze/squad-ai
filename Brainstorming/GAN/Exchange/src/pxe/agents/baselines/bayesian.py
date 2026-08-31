"""The Bayesian baseline: the FR-5.3.1 information value reference.

FR-5.3.1 requires that a scripted Bayesian agent exploiting its private signals
beats a random agent over 1 000 matches. This is that agent, and it is the
reason the whole private signal channel exists: if this baseline does not beat
``noise`` and ``zero_intelligence``, the information the info engine
distributes has no value and FR-5.3.1 is unmet.

How it forms a belief
---------------------
One posterior per market, carried across the ticks of a match and cleared by
``reset``. The posterior is the **precision weighted mean** of everything the
agent has been told about that market:

1. the public prior (FR-5.2.4) enters as one full precision observation, so the
   first tick already has an opinion;
2. every private signal enters with its own self declared ``precision_ppm`` as
   its weight: a signal with zero precision moves nothing, a signal with full
   precision counts as much as the prior;
3. a ``POINT_ESTIMATE`` and a ``THRESHOLD`` contribute an absolute level, while
   a ``DIRECTION`` contributes a level relative to the current posterior,
   because a sign says "higher than you think", not "exactly 0.75";
4. the total weight is capped, which turns the estimator into a bounded memory
   one. That is deliberate: the latent process of a market **moves** over the
   ticks (FR-5.2.1), so an estimator that never forgets would keep averaging in
   observations of a state that no longer holds.

Why this and not multiplied likelihood ratios
---------------------------------------------
Repeated signals about one market are repeated noisy observations of the *same*
latent quantity, not independent pieces of evidence. Multiplying a likelihood
ratio per signal (the textbook spelling) saturates the posterior against its
own clamp after a handful of ticks and makes the agent worse calibrated than an
agent that always says 0.5, which is the opposite of what FR-5.3.1 asks for.
The precision weighted mean is the conjugate answer to the actual question and
it converges to the latent value instead of to certainty.

Why there is no logarithm and no float here
-------------------------------------------
The whole update is integer arithmetic in parts per million. ``log``, ``exp``
and ``pow`` would be the natural spelling of the textbook update and they are
banned in this package: they call the platform libm, which is not bit identical
between glibc, msvcrt and macOS, so a posterior landing within one ulp of a ppm
boundary would quantise differently on two machines and AC-P1 would fail on the
second one only (CONTRACTS section 3.2).
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
from pxe.types import (
    PPM_ONE,
    MarketObservation,
    MatchConfig,
    Observation,
    SignalKind,
)

#: Weight the public prior enters with: one full precision observation.
PRIOR_WEIGHT_PPM: int = PPM_ONE
#: Largest total weight the posterior remembers. Six full precision
#: observations: enough to average the noise out, little enough to follow a
#: latent process that moves.
WEIGHT_CAP_PPM: int = 6 * PPM_ONE
#: How far a full precision ``DIRECTION`` signal moves the posterior, as a
#: fraction (in ppm) of the lean :func:`signal_evidence` reports.
DIRECTION_NUDGE_PPM: int = 600_000
#: How much of the market implied probability the acted belief keeps, in ppm.
#: The public price is information too, and it is the only information this
#: agent has about what the *other* agents know.
MARKET_ANCHOR_PPM: int = 100_000
#: Smallest disagreement, in cents, worth crossing the spread for.
MIN_EDGE_CENTS: int = 2
#: Size unit of a Bayesian order, in contracts, before the edge scaling.
BASE_QTY: int = 30


class BayesianAgent(BaselineAgent):
    """Carries a per market, precision weighted posterior fed by its own signals."""

    name: ClassVar[str] = "bayesian"

    def __init__(self, *, agent_id: str, config: MatchConfig, rng: random.Random) -> None:
        """Bind the agent to a seat and start with no posterior at all.

        Args:
            agent_id: The seat, ``A1``..``A8``.
            config: Configuration of the match.
            rng: The agent's own substream (unused: the update is deterministic).
        """
        super().__init__(agent_id=agent_id, config=config, rng=rng)
        self._weighted_sum: dict[str, int] = {}
        self._weight: dict[str, int] = {}

    def reset(self, *, config: MatchConfig, rng: random.Random) -> None:
        """Drop every posterior and take the new substream (CONTRACTS section 3.1).

        Args:
            config: Configuration of the match about to start.
            rng: A freshly built substream for this match.
        """
        super().reset(config=config, rng=rng)
        self._weighted_sum = {}
        self._weight = {}

    def posterior_ppm(self, observation: Observation, market: MarketObservation) -> int:
        """Fold this tick's signals into the market's posterior and return it.

        Args:
            observation: The current observation, for this tick's signals.
            market: The market block being updated.

        Returns:
            The posterior probability in ppm, inside the belief band.
        """
        weighted_sum = self._weighted_sum.get(market.market_id)
        if weighted_sum is None:
            weighted_sum = ppm_from_price(market.prior_price) * PRIOR_WEIGHT_PPM
            weight = PRIOR_WEIGHT_PPM
        else:
            weight = self._weight[market.market_id]
        for signal in signals_for_market(observation, market.market_id):
            implied_ppm, weight_ppm = signal_evidence(signal)
            if weight_ppm <= 0:
                continue
            if signal.kind is SignalKind.DIRECTION:
                lean = implied_ppm - PPM_ONE // 2
                level = clamp_belief_ppm(weighted_sum // weight + (lean * DIRECTION_NUDGE_PPM) // PPM_ONE)
            else:
                level = implied_ppm
            weighted_sum += level * weight_ppm
            weight += weight_ppm
            if weight > WEIGHT_CAP_PPM:
                weighted_sum = weighted_sum * WEIGHT_CAP_PPM // weight
                weight = WEIGHT_CAP_PPM
        self._weighted_sum[market.market_id] = weighted_sum
        self._weight[market.market_id] = weight
        return clamp_belief_ppm(weighted_sum // weight)

    def belief_ppm(self, observation: Observation, market: MarketObservation) -> int:
        """Anchor the freshly updated posterior toward the market price.

        Args:
            observation: The current observation.
            market: The market block to form a belief about.

        Returns:
            The acted belief in ppm.
        """
        posterior = self.posterior_ppm(observation, market)
        return blend_ppm(posterior, ppm_from_price(market.ref_price), MARKET_ANCHOR_PPM)

    def plan_orders(
        self,
        observation: Observation,
        *,
        planner: OrderPlanner,
        beliefs: Mapping[str, int],
    ) -> None:
        """Cross the spread whenever the book is at least two cents away.

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
                base_qty=BASE_QTY,
            )
