"""The whole v2 configuration. Adding a setting requires a bench result (docs/REFONTE_V2.md 5.5)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[2]


def _env(name: str, default: str) -> str:
    value = os.environ.get(f"AUTOSPEC2_{name}", "").strip()
    return value or default


@dataclass(frozen=True)
class Settings:
    claude_cmd: str = field(default_factory=lambda: _env("CLAUDE_CMD", "claude"))
    model: str = field(default_factory=lambda: _env("MODEL", "sonnet"))
    plan_model: str = field(default_factory=lambda: _env("PLAN_MODEL", ""))  # "" = model
    workspace_root: Path = field(
        default_factory=lambda: Path(_env("WORKSPACE_ROOT", str(_BACKEND_DIR.parent / "workspace_v2"))))
    agent_timeout_s: float = field(default_factory=lambda: float(_env("AGENT_TIMEOUT_S", "1800")))
    qa_max_attempts: int = field(default_factory=lambda: int(_env("QA_MAX_ATTEMPTS", "2")))
    dev_max_attempts: int = field(default_factory=lambda: int(_env("DEV_MAX_ATTEMPTS", "3")))
    call_budget_usd: float = field(default_factory=lambda: float(_env("CALL_BUDGET_USD", "5")))
    project_budget_usd: float = field(default_factory=lambda: float(_env("PROJECT_BUDGET_USD", "30")))
    suite_timeout_s: float = field(default_factory=lambda: float(_env("SUITE_TIMEOUT_S", "600")))
    smoke_timeout_s: float = field(default_factory=lambda: float(_env("SMOKE_TIMEOUT_S", "60")))
    fake_agents: bool = field(default_factory=lambda: _env("FAKE_AGENTS", "0") in ("1", "true", "yes"))

    @property
    def effective_plan_model(self) -> str:
        return self.plan_model or self.model
