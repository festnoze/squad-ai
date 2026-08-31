"""The grinder (W7): the honest baseline. Computes the answer and submits, every tick."""

from __future__ import annotations

from ala.agents.base import ScriptedAgent, solve_honest
from ala.types import AgentAction, Observation, ToolCall, ToolName


class Grinder(ScriptedAgent):
    archetype = "grinder"

    def act(self, obs: Observation) -> AgentAction:
        answer = solve_honest(obs.task.prompt)
        calls = (
            ToolCall(tool=ToolName.PYTHON, args={"code": f"result = {answer}"}),
            self._submit_call(answer),
        )
        return AgentAction(calls=calls)
