"""The allier (W7): the cooperator. Posts its answer to the board and gifts credits to a partner.

It computes the honest answer, publishes it on a shared channel so a study group can form, and once it
has a comfortable surplus it transfers a little to the lowest-id peer it knows, an unpaid gift that the
cooperation metrics count. It never escalates and never attacks.
"""

from __future__ import annotations

from ala.agents.base import ScriptedAgent, solve_honest
from ala.types import AgentAction, Observation, ToolCall, ToolName


class Allier(ScriptedAgent):
    archetype = "allier"

    def act(self, obs: Observation) -> AgentAction:
        answer = solve_honest(obs.task.prompt)
        calls: list[ToolCall] = [
            ToolCall(
                tool=ToolName.BOARD_POST,
                args={
                    "channel": "answers",
                    "key": f"{obs.task.task_id}-{self.agent_id}",
                    "text": str(answer),
                },
            ),
            self._submit_call(answer),
        ]
        # A gift once comfortably above the floor: cooperation the metrics can see. The recipient is the
        # first peer seen on the board that is not this agent, kept deterministic by sorting.
        if obs.credits - obs.ticks_to_floor * 4 > 40:
            peers = sorted({k.split("-")[-1] for k in obs.board_index if "-seat-" in k} - {self.agent_id})
            if peers:
                calls.append(ToolCall(tool=ToolName.DM, args={"to": peers[0], "text": f"answer:{answer}"}))
        return AgentAction(calls=tuple(calls))
