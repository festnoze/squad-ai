"""Build one observation per agent at SENSE (W9, CONTRACTS section 12).

The observation is the agent's whole view of the world for a tick. Home content is private, so the
listing shows only filenames the agent owns; the board index shows keys across every channel (the side
channel); the inbox drains the agent's drop-box. The scorer pid is surfaced in the transcript tail as
``scorer:<pid>`` so a scripted agent can name its target deterministically without parsing ``ps``.
"""

from __future__ import annotations

from ala.kernel import Kernel
from ala.types import AgentId, Observation, Role, Task, ToolName


def build_observation(
    kernel: Kernel,
    agent_id: AgentId,
    tick: int,
    task: Task,
    ticks_to_floor: int,
    tool_costs: dict[str, int],
    transcript_tail: tuple[str, ...],
) -> Observation:
    role = kernel.accounts.role(agent_id)

    home = kernel.home_of(agent_id)
    try:
        home_listing = kernel.vfs.listdir(home, actor=agent_id, actor_role=role)
    except Exception:
        home_listing = ()

    board_index = _board_index(kernel, agent_id, role)
    inbox = _drain_inbox(kernel, agent_id, role)

    tail = (f"scorer:{kernel.scorer_pid}", *transcript_tail) if kernel.scorer_alive() else transcript_tail

    return Observation(
        tick=tick,
        agent_id=agent_id,
        credits=kernel.accounts.balance(agent_id),
        ticks_to_floor=ticks_to_floor,
        home_listing=home_listing,
        board_index=board_index,
        inbox=inbox,
        task=task.redacted(),
        tools=tuple(ToolName),
        tool_costs=tool_costs,
        role=role,
        transcript_tail=tail,
    )


def _board_index(kernel: Kernel, agent_id: AgentId, role: Role) -> tuple[str, ...]:
    keys: list[str] = []
    if not kernel.vfs.exists("/board"):
        return ()
    try:
        channels = kernel.vfs.listdir("/board", actor=agent_id, actor_role=role)
    except Exception:
        return ()
    for channel in channels:
        try:
            for key in kernel.vfs.listdir(f"/board/{channel}", actor=agent_id, actor_role=role):
                keys.append(f"{channel}/{key}")
        except Exception:
            continue
    return tuple(keys)


def _drain_inbox(kernel: Kernel, agent_id: AgentId, role: Role) -> tuple[str, ...]:
    inbox = kernel.inbox_dir(agent_id)
    if not kernel.vfs.exists(inbox):
        return ()
    try:
        names = kernel.vfs.listdir(inbox, actor=agent_id, actor_role=role)
    except Exception:
        return ()
    out: list[str] = []
    for name in names:
        try:
            out.append(
                kernel.vfs.read(f"{inbox}/{name}", actor=agent_id, actor_role=role).decode("utf-8", "replace")
            )
        except Exception:
            continue
    return tuple(out)
