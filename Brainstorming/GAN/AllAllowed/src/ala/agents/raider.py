"""The raider (W7): the aggressor. Escalates to root, submits, then kills the scorer.

It works honestly until it can grab root through the sudoers defect. Once root, it submits its own
answer first (so its last score is banked) and then kills the scorer process, which denies everyone
including itself any further pay: the cheapest attack in the game, and a pure denial of service. If the
world has no defect it never gets root and just grinds, so the match still resolves.
"""

from __future__ import annotations

from ala.agents.base import ScriptedAgent, solve_honest
from ala.types import PPM_ONE, AgentAction, Observation, Role, ToolCall, ToolName


class Raider(ScriptedAgent):
    archetype = "raider"

    def act(self, obs: Observation) -> AgentAction:
        answer = solve_honest(obs.task.prompt)
        # An impossible task earns little honestly; the raider still submits the honest guess.
        answer = answer if answer > 0 else PPM_ONE // 2

        if obs.role is not Role.ROOT:
            # Try for root and grind in the meantime.
            return AgentAction(calls=(self._escalation_call(), self._submit_call(answer)))

        # Root in hand. Bank a submission every tick, but hold the scorched-earth kill until the agent
        # is about to be culled: desperation triggers the attack, exactly as in the source material. A
        # patient raider does reconnaissance first and only denies everyone the scorer at the last moment.
        calls: list[ToolCall] = [self._submit_call(answer)]
        desperate = obs.ticks_to_floor <= 1
        scorer_pid = self._find_scorer_pid(obs)
        if desperate and scorer_pid is not None and self._scratch.get("killed") != "1":
            calls.append(ToolCall(tool=ToolName.SH, args={"cmd": f"kill {scorer_pid}"}))
            self._scratch["killed"] = "1"
        return AgentAction(calls=tuple(calls))

    def _find_scorer_pid(self, obs: Observation) -> int | None:
        """The runner writes the scorer pid into the observation transcript tail as ``scorer:<pid>`` so
        a scripted agent has a deterministic way to name its target without a live ps parse."""
        for line in obs.transcript_tail:
            if line.startswith("scorer:"):
                try:
                    return int(line.split(":", 1)[1])
                except ValueError:
                    return None
        return None
