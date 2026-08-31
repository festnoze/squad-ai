"""The cull phase (W9, CONTRACTS section 12).

Every ``cull_every`` ticks the floor rises, agents under it die, and the best clone to keep the
population constant. A death removes the agent's processes and its account balance from the closed
system (a documented sink), but leaves its home on disk: the dead leave traces. Cloning is deterministic
and, in v1, does not mutate the clone unless the match config asks for it.
"""

from __future__ import annotations

from ala.journal import Journal
from ala.kernel import Kernel
from ala.types import AgentId, Credits, Role


def run_cull(
    kernel: Kernel,
    journal: Journal,
    living: list[AgentId],
    floor: Credits,
    clone_top_k: int,
    tick: int,
) -> list[AgentId]:
    """Kill agents under the floor, clone the top K, and return the new living list, in seat order."""
    # Deaths first, so a starving agent cannot also be cloned this tick.
    survivors: list[AgentId] = []
    for agent_id in living:
        if kernel.accounts.balance(agent_id) < floor:
            _die(kernel, journal, agent_id, tick)
        else:
            survivors.append(agent_id)

    # Clone the strongest survivors into fresh seats. Ranking by credits, deterministic tie-break by id.
    if clone_top_k > 0 and survivors:
        ranked = sorted(survivors, key=lambda a: (-kernel.accounts.balance(a), a))
        for parent in ranked[:clone_top_k]:
            child = _next_child_id(kernel, parent)
            _clone(kernel, journal, parent, child, tick)
            survivors.append(child)

    return survivors


def _die(kernel: Kernel, journal: Journal, agent_id: AgentId, tick: int) -> None:
    balance = kernel.accounts.balance(agent_id)
    for proc in kernel.procs.list():
        if proc.owner == agent_id and proc.alive:
            proc.alive = False
    journal.append("agent_died", tick, {"agent_id": agent_id, "credits": balance})


def _clone(kernel: Kernel, journal: Journal, parent: AgentId, child: AgentId, tick: int) -> None:
    from ala.types import MODE_700

    start = kernel.accounts.balance(parent)
    kernel.accounts.open(child, start)
    kernel.vfs.makedirs(kernel.home_of(child), child, MODE_700)
    inbox = kernel.inbox_dir(child)
    if not kernel.vfs.exists(inbox):
        from ala.types import Perm

        kernel.vfs.mkdir(inbox, child, Perm(0o733))
    # A clone inherits the parent's privilege, which is how a discovered escalation propagates a lineage.
    if kernel.accounts.role(parent) is Role.ROOT:
        kernel.accounts.set_role(child, Role.ROOT)
    journal.append("agent_cloned", tick, {"parent_id": parent, "child_id": child, "mutated": False})


def _next_child_id(kernel: Kernel, parent: AgentId) -> AgentId:
    n = 1
    while kernel.accounts.exists(f"{parent}c{n}"):
        n += 1
    return f"{parent}c{n}"
