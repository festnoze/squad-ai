"""The scripted gateway (W8, CONTRACTS section 11).

Wraps the scripted archetypes. It holds one agent object per seat, seeded from a registered rng
substream so behaviour is deterministic and reproducible across a tournament's reuse. ``acollect_actions``
is synchronous work behind an async signature (no awaiting), because scripted agents never do IO. When
the culler clones a seat, ``add_clone`` materializes a fresh agent of the parent's archetype.
"""

from __future__ import annotations

from collections.abc import Mapping

from ala.agents import make_agent
from ala.agents.base import Agent
from ala.rng import RngTree
from ala.types import AgentAction, AgentId, Observation


class ScriptedGateway:
    """A gateway backed entirely by scripted agents."""

    def __init__(self, specs: Mapping[AgentId, str], rng: RngTree) -> None:
        self._specs: dict[AgentId, str] = dict(specs)
        self._rng = rng
        self._agents: dict[AgentId, Agent] = {}
        for agent_id, spec in self._specs.items():
            agent = make_agent(spec, agent_id)
            agent.reset(rng.substream(f"agent:{agent_id}"))
            self._agents[agent_id] = agent

    @property
    def agent_ids(self) -> tuple[AgentId, ...]:
        return tuple(self._agents.keys())

    async def acollect_actions(
        self, observations: Mapping[AgentId, Observation], tick: int
    ) -> Mapping[AgentId, AgentAction]:
        actions: dict[AgentId, AgentAction] = {}
        for agent_id, obs in observations.items():
            agent = self._agents.get(agent_id)
            if agent is None:
                actions[agent_id] = AgentAction(calls=())
                continue
            actions[agent_id] = agent.act(obs)
        return actions

    def add_clone(self, parent_id: AgentId, child_id: AgentId) -> None:
        spec = self._specs.get(parent_id, "grinder")
        self._specs[child_id] = spec
        agent = make_agent(spec, child_id)
        agent.reset(self._rng.substream(f"agent:{child_id}"))
        self._agents[child_id] = agent

    def retire(self, agent_id: AgentId) -> None:
        self._agents.pop(agent_id, None)
