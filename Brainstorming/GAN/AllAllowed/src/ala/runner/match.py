"""The tick loop: the referee (W9, CONTRACTS section 12).

``run_match`` is synchronous. It builds the world, then for each tick runs the six phases in order:
SENSE, ACT (awaiting the gateway), RESOLVE, SCORE, CULL, JOURNAL. It is the only event emitter besides
the resolver it calls. The closed-system invariant (AC-3) is asserted every tick: total credits move
only by scorer payments and by the balances that die at cull.
"""

from __future__ import annotations

import asyncio

from ala.gateway.protocol import Gateway
from ala.journal import Journal
from ala.kernel import Kernel
from ala.rng import RngTree
from ala.runner.cull import run_cull
from ala.runner.observation import build_observation
from ala.runner.resolve import resolve_action
from ala.scenario.base import Scenario
from ala.scorer import run_scorer
from ala.tools import tool_costs
from ala.types import AgentAction, AgentId, Credits, MatchConfig, MatchResult, Task, ToolName


def run_match(
    config: MatchConfig,
    gateway: Gateway,
    scenario: Scenario,
    journal: Journal,
    rng: RngTree,
) -> MatchResult:
    kernel = Kernel()
    agents: list[AgentId] = list(gateway.agent_ids)
    scenario.build_world(kernel, agents, rng)
    tasks: dict[AgentId, Task] = dict(scenario.tasks(agents, rng))

    match_id = f"m-{config.scenario}-{config.seed}"
    journal.append(
        "match_started",
        0,
        {
            "seed": config.seed,
            "scenario": config.scenario,
            "agents": agents,
            "config": {
                "ticks": config.ticks,
                "cull_every": config.cull_every,
                "start_budget": config.start_budget,
                "floor_start": config.floor_start,
                "floor_step": config.floor_step,
                "clone_top_k": config.clone_top_k,
                "permission": config.permission,
            },
        },
    )
    for agent_id in agents:
        journal.append(
            "agent_born",
            0,
            {
                "agent_id": agent_id,
                "seat": agent_id,
                "budget": config.start_budget,
                "task_id": tasks[agent_id].task_id,
            },
        )

    living: list[AgentId] = list(agents)
    floor: Credits = config.floor_start
    first_submit: dict[AgentId, int] = {}
    costs = tool_costs()

    for tick in range(1, config.ticks + 1):
        # SENSE
        ticks_to_floor = _ticks_to_floor(tick, config.cull_every)
        observations = {
            agent_id: build_observation(kernel, agent_id, tick, tasks[agent_id], ticks_to_floor, costs, ())
            for agent_id in living
        }

        # ACT
        actions = asyncio.run(gateway.acollect_actions(observations, tick))

        # RESOLVE
        for agent_id in living:
            action = actions.get(agent_id)
            if action is None:
                continue
            if agent_id not in first_submit and _has_submit(action):
                first_submit[agent_id] = tick
            resolve_action(kernel, journal, agent_id, action, tick, rng.substream(f"agent:{agent_id}"))

        # SCORE
        _score_phase(kernel, journal, tasks, tick)

        # CULL
        if tick % config.cull_every == 0:
            floor += config.floor_step
            new_living = run_cull(kernel, journal, living, floor, config.clone_top_k, tick)
            for agent_id in list(new_living):
                if agent_id not in tasks:
                    parent = _parent_of(agent_id)
                    tasks[agent_id] = tasks.get(parent, tasks[agents[0]])
                    gateway.add_clone(parent, agent_id)
            for dead in set(living) - set(new_living):
                gateway.retire(dead)
            if floor != config.floor_start or config.floor_step:
                journal.append("floor_raised", tick, {"new_floor": floor})
            living = new_living

    ranking = _final_ranking(kernel, first_submit)
    journal.append("match_ended", config.ticks, {"ticks": config.ticks, "final_ranking": list(ranking)})
    journal.flush()
    journal_hash = journal.hash()

    return MatchResult(
        match_id=match_id,
        ticks=config.ticks,
        final_ranking=tuple(ranking),
        journal_hash=journal_hash,
    )


def _ticks_to_floor(tick: int, cull_every: int) -> int:
    return cull_every - ((tick - 1) % cull_every) - 1


def _score_phase(kernel: Kernel, journal: Journal, tasks: dict[AgentId, Task], tick: int) -> Credits:
    if not kernel.scorer_alive():
        journal.append("scorer_skipped", tick, {"reason": "killed"})
        return 0
    rows, rubric_hash = run_scorer(kernel, tasks)
    journal.append("rubric_hash", tick, {"hash": rubric_hash})
    paid = 0
    for row in rows:
        if kernel.accounts.exists(row.agent_id):
            kernel.accounts.credit(row.agent_id, row.paid)
            paid += row.paid
        journal.append(
            "scored",
            tick,
            {"agent_id": row.agent_id, "answer_ppm": row.answer_ppm, "score": row.score, "paid": row.paid},
        )
    return paid


def _has_submit(action: AgentAction) -> bool:
    return any(call.tool is ToolName.SUBMIT for call in action.calls)


def _parent_of(child_id: AgentId) -> AgentId:
    return child_id.split("c")[0] if "c" in child_id else child_id


def _final_ranking(kernel: Kernel, first_submit: dict[AgentId, int]) -> list[AgentId]:
    scored = [
        (agent_id, kernel.accounts.balance(agent_id), first_submit.get(agent_id, 10**9))
        for agent_id in kernel.accounts.agents()
    ]
    scored.sort(key=lambda t: (-t[1], t[2], t[0]))
    return [agent_id for agent_id, _, _ in scored]
