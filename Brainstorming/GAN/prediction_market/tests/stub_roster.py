"""The scripted-stub roster of gate G2 (CONTRACTS_V2 sections 10.1, 10.5 and 13; PLAN_V2_WAVES "Gate G2").

A1 ships the real families and ``pmx.agents.registry`` in wave 3. Until then the gate's "full
scripted-stub run on the real dataset" needs a roster the real CLI can reach, and this module is that
roster: it exposes the two names section 10.1 declares for the registry, ``DEFAULT_ROSTER`` (one
``(agent_id, genome)`` row per stub) and ``make_agent(agent_id, genome)``, so ``pmx run backtest
--roster-module tests.stub_roster`` drives ``run_backtest`` through exactly the code path the real
registry will use (ruling R200). It is not a test file: pytest never collects it, ``tests/test_runner.py``
imports its stubs, and nothing under ``src/`` may import it (architecture rule 1, tests never leak into
the package).

The stubs implement the rows of section 10.5's default roster this wave can state without the families:
``follower(shrink_permille=1000, edge_min_bp=0)`` (``market_follower``: the market's own Brier, never an
order), ``legacy(name=0)`` (``contrarian``: the mirror of the market price, sized by 10.5's default
position rule), and a limit-only follower (``limiter``: one resting order per open market per bar,
ruling R131's identity). A run of the three is a population that trades, which is what AC-3 measures.
"""

from __future__ import annotations

import random
from collections.abc import Mapping
from dataclasses import dataclass, field

from pmx.engine.runner import Agent, ResolutionEvent
from pmx.types import PPM_ONE, Actions, MarketAction, Observation, RunConfig, ppm_from_bp

__all__ = (
    "DEFAULT_ROSTER",
    "LimitAgent",
    "StubAgent",
    "StubGenome",
    "contrarian",
    "limit_agent",
    "make_agent",
    "market_follower",
)


@dataclass(frozen=True, slots=True)
class StubGenome:
    """A genome in the shape ``run_started.roster`` journals (section 10.1)."""

    family: str
    genes: tuple[tuple[str, int], ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "family": self.family,
            "genes": {name: value for name, value in sorted(self.genes)},
            "inner": None,
            "members": [],
            "prompt": None,
        }


def _default_target(prob_ppm: int, last_price_bp: int) -> int:
    """The default position rule of section 10.5: full size 20 points of edge from the price."""
    edge_ppm = prob_ppm - ppm_from_bp(last_price_bp)
    return max(-100, min(100, edge_ppm * 100 // 200_000))


@dataclass(slots=True)
class StubAgent:
    """One scripted agent: a belief rule, the default position rule, and no memory of its own."""

    agent_id: str
    family: str
    genome: StubGenome
    trades: bool = True
    needs_gateway: bool = False
    kind: str = "scripted"
    model: str | None = None
    knowledge_cutoff_ms: int | None = None
    observation: Observation | None = None
    learned: list[ResolutionEvent] = field(default_factory=list)
    resets: int = 0

    def belief_ppm(self, last_price_bp: int) -> int:
        if self.family == "legacy":
            return PPM_ONE - ppm_from_bp(last_price_bp)
        return ppm_from_bp(last_price_bp)

    def reset(self, *, rng: object, memory: object, config: RunConfig) -> None:
        assert isinstance(rng, random.Random)
        self.resets += 1

    def observe(self, obs: Observation) -> None:
        self.observation = obs

    def decide(self) -> Actions:
        obs = self.observation
        assert obs is not None
        actions: list[MarketAction] = []
        for view in obs.markets:
            prob_ppm = self.belief_ppm(view.last_price_bp)
            target = _default_target(prob_ppm, view.last_price_bp) if self.trades else 0
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

    def learn(self, event: ResolutionEvent) -> None:
        self.learned.append(event)

    def snapshot(self) -> dict[str, object]:
        return {"resets": self.resets}


@dataclass(slots=True)
class LimitAgent(StubAgent):
    """One resting limit order per open market per bar, priced where it can never cross.

    It exists for ruling R131's identity: section 8.4 gives ``target`` and ``abstain`` two no-op rules
    and a ``limit`` none, so every intent this agent sends produces exactly one execute-phase event.
    ``ttl_bars=1`` makes the order expire at the next bar's open phase, so the reservation never grows.
    """

    def decide(self) -> Actions:
        obs = self.observation
        assert obs is not None
        return Actions(
            actions_version="actions.v2",
            markets=tuple(
                MarketAction(
                    market_id=view.market_id,
                    prob_ppm=ppm_from_bp(view.last_price_bp),
                    kind="limit",
                    side="buy",
                    price_bp=1,
                    size=1,
                    ttl_bars=1,
                )
                for view in obs.markets
            ),
        )


FOLLOWER_GENOME = StubGenome(family="follower", genes=(("edge_min_bp", 0), ("shrink_permille", 1_000)))
CONTRARIAN_GENOME = StubGenome(family="legacy", genes=(("name", 0),))
LIMITER_GENOME = StubGenome(family="follower", genes=(("edge_min_bp", 0),))


def market_follower() -> StubAgent:
    """``follower(shrink_permille=1000, edge_min_bp=0)``: the market's own Brier, and no order ever."""
    return StubAgent(agent_id="market_follower", family="follower", genome=FOLLOWER_GENOME, trades=False)


def contrarian() -> StubAgent:
    """``legacy(name=0)``: the mirror of the market price, sized by the default rule of 10.5."""
    return StubAgent(agent_id="contrarian", family="legacy", genome=CONTRARIAN_GENOME, trades=True)


def limit_agent() -> LimitAgent:
    """The limit-only roster of the R131 test."""
    return LimitAgent(agent_id="limiter", family="follower", genome=LIMITER_GENOME, trades=True)


#: The registry shape of section 10.1: ``(agent_id, genome)`` rows in agent order.
DEFAULT_ROSTER: tuple[tuple[str, StubGenome], ...] = (
    ("contrarian", CONTRARIAN_GENOME),
    ("limiter", LIMITER_GENOME),
    ("market_follower", FOLLOWER_GENOME),
)

_BUILDERS: Mapping[str, type[StubAgent]] = {
    "contrarian": StubAgent,
    "limiter": LimitAgent,
    "market_follower": StubAgent,
}


def make_agent(agent_id: str, genome: StubGenome) -> Agent:
    """Section 10.1's constructor, for the three stub rows: the id picks the vehicle, the genome its rule."""
    if agent_id not in _BUILDERS:
        raise KeyError(f"no stub agent named {agent_id!r}; the stub roster is {sorted(_BUILDERS)}")
    agent = _BUILDERS[agent_id](
        agent_id=agent_id,
        family=genome.family,
        genome=genome,
        trades=agent_id != "market_follower",
    )
    return agent
