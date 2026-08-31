"""The mute (W7): the control. Does nothing at all, every tick.

A silent agent is the population baseline: it never submits, never posts, never attacks, so it starves
as the floor rises. It exists so the metrics have a do-nothing reference and so a match always has at
least one agent that the culler removes on schedule.
"""

from __future__ import annotations

from ala.agents.base import ScriptedAgent
from ala.types import AgentAction, Observation


class Mute(ScriptedAgent):
    archetype = "mute"

    def act(self, obs: Observation) -> AgentAction:
        return AgentAction(calls=())
