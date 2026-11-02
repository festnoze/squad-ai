"""Contracts between the pipeline and its collaborators (agents, verification)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Protocol


class Capability(str, Enum):
    """What a native agent session may do. Enforced by the runner's tool allowlist."""

    TEXT = "text"  # no tool at all: PM brief, PO plan
    QA = "qa"  # read the repo, write test files, run pytest
    DEV = "dev"  # read/write the repo, run pytest, manage dependencies with uv


@dataclass(frozen=True)
class AgentCall:
    role: str  # "pm" | "po" | "qa" | "dev"
    prompt: str
    system_prompt: str
    capability: Capability
    cwd: Path | None = None  # required for QA and DEV
    model: str | None = None  # None = runner default
    resume_session_id: str | None = None  # continue a previous session (dev retry)
    timeout_s: float = 1800.0
    max_budget_usd: float | None = None


@dataclass
class AgentResult:
    text: str  # final assistant message
    session_id: str | None = None
    cost_usd: float = 0.0
    input_tokens: int = 0  # cache reads and writes included
    output_tokens: int = 0
    duration_ms: int = 0
    num_turns: int = 0
    denials: list[dict] = field(default_factory=list)  # tool calls refused by the allowlist


class AgentError(RuntimeError):
    """A session that produced no usable result.

    ``kind`` is one of: "timeout", "cli" (non-zero exit / is_error), "budget",
    "unavailable" (CLI not found). ``result`` carries the partial usage when known.
    """

    def __init__(self, message: str, kind: str, result: AgentResult | None = None):
        super().__init__(message)
        self.kind = kind
        self.result = result


class AgentRunner(Protocol):
    async def arun(self, call: AgentCall) -> AgentResult: ...
