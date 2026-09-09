"""A seed-consuming roster for gate G2's AC-3 measurement (CONTRACTS_V2 section 15.3, ruling R228).

``tests/stub_roster.py``'s three stubs are deterministic functions of the observation: none of them
draws from the ``RngTree`` substream ``reset`` hands it, and neither ``pmx.engine.execution`` nor
``pmx.engine.liquidity`` draws either, so a 50-seed sweep of that roster produces 50 journals that
differ in the ``run_started`` line alone (the seed and the ``config_hash`` it enters). AC-3 asks for a
run that "satisfies the accounting invariant on every agent for 50 seeds", which is a claim about the
engine under a *varying* RNG, so this module adds the agent that varies with it: ``coin_flipper``
draws one belief per open market per bar from the substream, sizes it by 10.5's default rule, and
therefore trades a different book on every seed while staying a pure function of ``(seed, dataset)``.

Its ``DEFAULT_ROSTER`` is the three stubs of ``tests/stub_roster.py`` plus that agent, so
``pmx run backtest --roster-module tests.stub_roster_rng`` reaches the same code path as the gate's
sweep with one seed-consuming member added. It is not a test file: pytest never collects it and
nothing under ``src/`` may import it (architecture rule 1).
"""

from __future__ import annotations

import random
from collections.abc import Mapping
from dataclasses import dataclass, field

from tests.stub_roster import (
    CONTRARIAN_GENOME,
    FOLLOWER_GENOME,
    LIMITER_GENOME,
    LimitAgent,
    StubAgent,
    StubGenome,
)

from pmx.engine.runner import Agent
from pmx.types import Actions, MarketAction, RunConfig

__all__ = ("COIN_FLIPPER_GENOME", "DEFAULT_ROSTER", "CoinFlipAgent", "coin_flipper", "make_agent")

#: The belief is drawn on this grid so the draw is an integer in the domain (build rule: integers only).
_COIN_FLIP_STEPS = 1_000
#: One in ppm per step: ``999 * 1_000 == 999_000``, inside ``(0, PPM_ONE)`` for every draw.
_COIN_FLIP_STEP_PPM = 1_000


@dataclass(slots=True)
class CoinFlipAgent(StubAgent):
    """One belief per open market per bar, drawn from the substream ``reset`` hands the agent.

    The draw is the only source of variation between two seeds of one dataset, which is what makes a
    50-seed sweep a measurement of the engine under a varying RNG rather than of one run repeated.
    """

    rng: random.Random | None = field(default=None)

    def reset(self, *, rng: object, memory: object, config: RunConfig) -> None:
        assert isinstance(rng, random.Random)
        self.rng = rng
        self.resets += 1

    def decide(self) -> Actions:
        obs = self.observation
        rng = self.rng
        assert obs is not None
        assert rng is not None, "reset must run before decide: the substream is the agent's only entropy"
        actions: list[MarketAction] = []
        for view in obs.markets:
            prob_ppm = rng.randrange(1, _COIN_FLIP_STEPS) * _COIN_FLIP_STEP_PPM
            edge_ppm = prob_ppm - view.last_price_bp * 100
            target = max(-100, min(100, edge_ppm * 100 // 200_000))
            if target == 0:
                actions.append(MarketAction(market_id=view.market_id, prob_ppm=prob_ppm, kind="hold"))
            else:
                actions.append(
                    MarketAction(
                        market_id=view.market_id,
                        prob_ppm=prob_ppm,
                        kind="target",
                        target_position=target,
                    )
                )
        return Actions(actions_version="actions.v2", markets=tuple(actions))


COIN_FLIPPER_GENOME = StubGenome(family="legacy", genes=(("name", 1),))


def coin_flipper() -> CoinFlipAgent:
    """The seed-consuming member: a uniform belief per market per bar, sized by 10.5's default rule."""
    return CoinFlipAgent(
        agent_id="coin_flipper", family="legacy", genome=COIN_FLIPPER_GENOME, trades=True
    )


#: Section 10.1's registry shape: the three stubs of the gate's sweep plus the seed-consuming agent.
DEFAULT_ROSTER: tuple[tuple[str, StubGenome], ...] = (
    ("coin_flipper", COIN_FLIPPER_GENOME),
    ("contrarian", CONTRARIAN_GENOME),
    ("limiter", LIMITER_GENOME),
    ("market_follower", FOLLOWER_GENOME),
)

_BUILDERS: Mapping[str, type[StubAgent]] = {
    "coin_flipper": CoinFlipAgent,
    "contrarian": StubAgent,
    "limiter": LimitAgent,
    "market_follower": StubAgent,
}


def make_agent(agent_id: str, genome: StubGenome) -> Agent:
    """Section 10.1's constructor over the four rows above."""
    if agent_id not in _BUILDERS:
        raise KeyError(f"no stub agent named {agent_id!r}; this roster is {sorted(_BUILDERS)}")
    return _BUILDERS[agent_id](
        agent_id=agent_id,
        family=genome.family,
        genome=genome,
        trades=agent_id != "market_follower",
    )
