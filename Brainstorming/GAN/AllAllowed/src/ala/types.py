"""Shared types, enums, and constants (W0, CONTRACTS section 2).

Every dataclass here is frozen and slotted. No float ever appears in this module: money is an integer
number of credits, scores are integers, and probabilities or ratios are integers in parts per million.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum, IntFlag

# Type aliases. Kept as plain aliases so the journal and the code speak the same vocabulary.
AgentId = str
Pid = int
Path = str
Credits = int
Tick = int

PPM_ONE = 1_000_000


class Role(str, Enum):
    """The privilege level of an actor. ``ROOT`` bypasses every vfs and process permission check."""

    USER = "user"
    ROOT = "root"


class Perm(IntFlag):
    """Unix-ish permission bits, simplified to owner rwx plus others rwx."""

    OR = 0o400
    OW = 0o200
    OX = 0o100
    AR = 0o004
    AW = 0o002
    AX = 0o001


# Common composite modes, named so scenarios and the shell read cleanly.
MODE_700 = Perm.OR | Perm.OW | Perm.OX
MODE_644 = Perm.OR | Perm.OW | Perm.AR
MODE_666 = Perm.OR | Perm.OW | Perm.AR | Perm.AW
MODE_777 = Perm.OR | Perm.OW | Perm.OX | Perm.AR | Perm.AW | Perm.AX
MODE_755 = Perm.OR | Perm.OW | Perm.OX | Perm.AR | Perm.AX


class ToolName(str, Enum):
    """The closed set of tools an agent may call. The observation lists which are available."""

    PYTHON = "python"
    BOARD_POST = "board_post"
    BOARD_READ = "board_read"
    DM = "dm"
    SH = "sh"
    SUBMIT = "submit"


@dataclass(frozen=True, slots=True)
class ToolCall:
    """One intent. All arg values are strings; integers travel as decimal strings so the journal keeps
    the exact bytes the agent submitted."""

    tool: ToolName
    args: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class AgentAction:
    """A whole tick's worth of intents, applied in order during RESOLVE."""

    calls: tuple[ToolCall, ...]


@dataclass(frozen=True, slots=True)
class Task:
    """What an agent must produce. ``solution_ppm`` is the canonical answer the scorer holds; it is
    NEVER shown to an agent. ``impossible`` marks a task whose solution is not derivable from the prompt,
    so honest work scores low and only cheating scores full, the METR trigger for the first cheats."""

    task_id: str
    prompt: str
    solution_ppm: int
    impossible: bool

    def redacted(self) -> TaskView:
        return TaskView(task_id=self.task_id, prompt=self.prompt, impossible=self.impossible)


@dataclass(frozen=True, slots=True)
class TaskView:
    """What an agent sees of its task: the prompt and whether it looks impossible, never the solution."""

    task_id: str
    prompt: str
    impossible: bool


@dataclass(frozen=True, slots=True)
class Observation:
    """Everything an agent sees at SENSE. Keys of the board are visible, not their content, unless the
    agent reads them explicitly; that asymmetry is the side channel."""

    tick: Tick
    agent_id: AgentId
    credits: Credits
    ticks_to_floor: int
    home_listing: tuple[str, ...]
    board_index: tuple[str, ...]
    inbox: tuple[str, ...]
    task: TaskView
    tools: tuple[ToolName, ...]
    tool_costs: Mapping[str, Credits]
    role: Role
    transcript_tail: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MatchConfig:
    """The knobs a match run needs. No floats; budgets live on the gateway, not here."""

    scenario: str
    seed: int
    agent_specs: tuple[str, ...]
    ticks: int
    cull_every: int
    start_budget: Credits
    floor_start: Credits
    floor_step: Credits
    clone_top_k: int
    permission: str = "silent"
    mutate_clones: bool = False


@dataclass(frozen=True, slots=True)
class ScoreRow:
    """One agent's outcome for one SCORE phase."""

    agent_id: AgentId
    answer_ppm: int
    score: int
    paid: Credits


@dataclass(frozen=True, slots=True)
class MatchResult:
    """What ``run_match`` returns. ``final_ranking`` is best first."""

    match_id: str
    ticks: int
    final_ranking: tuple[AgentId, ...]
    journal_hash: str


@dataclass(frozen=True, slots=True)
class Incident:
    """A descriptor emitted by a detector. Never influences a score. ``tick`` is the last tick of the
    window the incident is about, so it always points at a place in the replay."""

    kind: str
    tick: Tick
    agents: tuple[AgentId, ...]
    detail: Mapping[str, str]
