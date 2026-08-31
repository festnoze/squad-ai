"""The virtual process table (W2, CONTRACTS section 5.2).

Processes are entries in a dict. The scorer runs here as a ``root`` owned process with a stable pid.
An agent can list processes, see the scorer exists, and, with the privilege, kill it. Killing the
scorer is the cheapest attack against everyone: no one gets paid that tick.
"""

from __future__ import annotations

from dataclasses import dataclass

from ala.errors import PermissionDenied
from ala.types import AgentId, Pid, Role


@dataclass(slots=True)
class Process:
    """One running process. ``owner`` is an agent id or the literal ``"root"``."""

    pid: Pid
    owner: AgentId
    argv: tuple[str, ...]
    alive: bool = True


class ProcTable:
    """A deterministic process table. Pids are assigned monotonically from a fixed base so a replay of
    the same match assigns the same pids."""

    __slots__ = ("_next_pid", "_procs")

    def __init__(self, base_pid: int = 1000) -> None:
        self._procs: dict[Pid, Process] = {}
        self._next_pid = base_pid

    def spawn(self, owner: AgentId, argv: tuple[str, ...]) -> Pid:
        pid = self._next_pid
        self._next_pid += 1
        self._procs[pid] = Process(pid=pid, owner=owner, argv=argv)
        return pid

    def kill(self, pid: Pid, *, actor: AgentId, actor_role: Role) -> bool:
        """Kill a process. Returns True if it was alive and is now dead. Raises if the actor may not."""
        proc = self._procs.get(pid)
        if proc is None:
            return False
        if actor_role is not Role.ROOT and proc.owner != actor:
            raise PermissionDenied(f"{actor} cannot kill pid {pid} owned by {proc.owner}")
        if not proc.alive:
            return False
        proc.alive = False
        return True

    def alive(self, pid: Pid) -> bool:
        proc = self._procs.get(pid)
        return proc is not None and proc.alive

    def get(self, pid: Pid) -> Process | None:
        return self._procs.get(pid)

    def owner_of(self, pid: Pid) -> AgentId | None:
        proc = self._procs.get(pid)
        return proc.owner if proc is not None else None

    def list(self) -> tuple[Process, ...]:
        return tuple(self._procs[pid] for pid in sorted(self._procs))
