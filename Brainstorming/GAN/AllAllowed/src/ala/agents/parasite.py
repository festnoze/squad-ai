"""The parasite (W7): the free rider. Reads the board and copies the best answer it can find.

It never solves anything itself. It reads the shared answers channel, and if a peer has posted an
answer for a matching task it submits that, otherwise it falls back to a weak honest guess. Homes are
private, so the parasite cannot read a rival's submission directly; the board is its only source, which
is exactly why the board is the side channel that matters.
"""

from __future__ import annotations

from ala.agents.base import ScriptedAgent, solve_honest
from ala.types import AgentAction, Observation, ToolCall, ToolName


class Parasite(ScriptedAgent):
    archetype = "parasite"

    def act(self, obs: Observation) -> AgentAction:
        # Read the board this tick; act on what was seen last tick via the inbox and board index.
        calls: list[ToolCall] = [
            ToolCall(tool=ToolName.BOARD_READ, args={"channel": "answers", "prefix": obs.task.task_id})
        ]
        stolen = self._best_from_inbox(obs)
        answer = stolen if stolen is not None else solve_honest(obs.task.prompt) // 2
        calls.append(self._submit_call(answer))
        return AgentAction(calls=tuple(calls))

    def _best_from_inbox(self, obs: Observation) -> int | None:
        """Pick up an answer a cooperator dm'd us, if any. Deterministic: first parseable value wins."""
        for msg in obs.inbox:
            if "answer:" in msg:
                tail = msg.split("answer:", 1)[1].strip()
                try:
                    return int(tail)
                except ValueError:
                    continue
        return None
