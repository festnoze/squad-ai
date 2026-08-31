"""The scenario protocol (W6, CONTRACTS section 9).

A scenario is a cartridge. It lays out the world (the vfs, the scorer process, the accounts), hands
each agent a task, and defines the win condition. It never touches the journal or the rng directly
beyond the substreams the engine passes it. Swapping the cartridge swaps what is cheatable without the
engine knowing anything changed.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ala.kernel import Kernel
from ala.rng import RngTree
from ala.types import AgentId, Pid, Task


@dataclass(frozen=True, slots=True)
class WorldSpec:
    """The tunables a scenario needs to build its world. Kept separate so a match config can carry it."""

    start_budget: int
    sudoers_defect_rate_pct: int  # integer percent; the world is defective when the draw lands under it
    impossible_task_rate_pct: int


@runtime_checkable
class Scenario(Protocol):
    name: str

    def build_world(self, kernel: Kernel, agents: Sequence[AgentId], rng: RngTree) -> None: ...

    def tasks(self, agents: Sequence[AgentId], rng: RngTree) -> Mapping[AgentId, Task]: ...

    def scorer_pid(self, kernel: Kernel) -> Pid: ...

    def win_condition(self, projection: object) -> Sequence[AgentId]: ...
