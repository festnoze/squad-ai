"""The momentum baseline (PRD section 8, T2.2).

It ignores its private signals entirely and reads the public tape only: the
reference price history of each market. Its belief is a one step extrapolation
of the recent trend, and it buys a rising market and sells a falling one. It is
the population's trend follower, which is what makes the price series of a
scripted match look like a market rather than a random walk around the prior.

It keeps its own per market reference price memory instead of relying on
``MarketObservation.ref_history``, because ``MatchConfig.ref_history_len`` may
legally be ``0`` (CONTRACTS section 8.2 only caps it at ``REF_HISTORY_MAX``) and
a trend follower with no history is a mute agent. That memory is exactly what
``reset`` has to clear between two matches.
"""

import random
from collections.abc import Mapping
from typing import ClassVar

from pxe.agents.base import (
    BaselineAgent,
    OrderPlanner,
    ppm_from_price,
)
from pxe.types import MarketObservation, MatchConfig, Observation, clamp_price

#: Number of reference prices the trend is measured over, current one included.
TREND_WINDOW: int = 4
#: Smallest absolute trend, in cents, that counts as a trend at all.
MIN_TREND_CENTS: int = 2
#: Smallest disagreement, in cents, worth crossing the spread for.
MIN_EDGE_CENTS: int = 1


class MomentumAgent(BaselineAgent):
    """Extrapolates the recent reference price trend by one tick."""

    name: ClassVar[str] = "momentum"

    def __init__(self, *, agent_id: str, config: MatchConfig, rng: random.Random) -> None:
        """Bind the agent to a seat and start with an empty tape.

        Args:
            agent_id: The seat, ``A1``..``A8``.
            config: Configuration of the match.
            rng: The agent's own substream (unused: momentum draws nothing).
        """
        super().__init__(agent_id=agent_id, config=config, rng=rng)
        self._tape: dict[str, tuple[int, ...]] = {}

    def reset(self, *, config: MatchConfig, rng: random.Random) -> None:
        """Drop the tape and take the new substream (CONTRACTS section 3.1).

        Args:
            config: Configuration of the match about to start.
            rng: A freshly built substream for this match.
        """
        super().reset(config=config, rng=rng)
        self._tape = {}

    def _record(self, market: MarketObservation) -> tuple[int, ...]:
        """Append this tick's reference price to the market's private tape.

        Args:
            market: The market block being read.

        Returns:
            The tape after the append, oldest first, at most
            :data:`TREND_WINDOW` entries long.
        """
        tape = self._tape.get(market.market_id)
        if tape is None:
            tape = tuple(market.ref_history)
        tape = (*tape, market.ref_price)[-TREND_WINDOW:]
        self._tape[market.market_id] = tape
        return tape

    def trend_cents(self, market: MarketObservation) -> int:
        """Signed change of the reference price over the trend window.

        Args:
            market: The market block being read.

        Returns:
            ``ref_price(now) - ref_price(window start)``, zero on the first tick.
        """
        tape = self._record(market)
        if len(tape) < 2:
            return 0
        return tape[-1] - tape[0]

    def belief_ppm(self, observation: Observation, market: MarketObservation) -> int:
        """Extrapolate the trend one tick forward.

        Args:
            observation: The current observation.
            market: The market block to form a belief about.

        Returns:
            The implied probability of the extrapolated price, in ppm.
        """
        trend = self.trend_cents(market)
        if abs(trend) < MIN_TREND_CENTS:
            return ppm_from_price(market.ref_price)
        return ppm_from_price(clamp_price(market.ref_price + trend))

    def plan_orders(
        self,
        observation: Observation,
        *,
        planner: OrderPlanner,
        beliefs: Mapping[str, int],
    ) -> None:
        """Buy a rising market and sell a falling one, at the touch.

        Args:
            observation: The current observation.
            planner: The budget aware intent builder.
            beliefs: The belief of this tick per market id.
        """
        for market in self.open_markets(observation):
            belief = beliefs.get(market.market_id, ppm_from_price(market.ref_price))
            tape = self._tape.get(market.market_id, ())
            if len(tape) < 2 or abs(tape[-1] - tape[0]) < MIN_TREND_CENTS:
                continue
            self.trade_on_edge(
                market,
                planner=planner,
                belief=belief,
                min_edge_cents=MIN_EDGE_CENTS,
            )
