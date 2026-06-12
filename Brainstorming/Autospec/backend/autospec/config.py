"""Runtime configuration: paths to the BMAD install, workspaces, and the Claude CLI."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent  # Autospec/


def _default_bmad_dir() -> Path:
    env = os.environ.get("AUTOSPEC_BMAD_DIR")
    if env:
        return Path(env)
    # Autospec lives next to the _bmad install (Brainstorming/_bmad)
    candidate = PROJECT_DIR.parent / "_bmad"
    return candidate


def _resolve_claude_cmd() -> str:
    env = os.environ.get("AUTOSPEC_CLAUDE_CMD")
    if env:
        return env
    # On Windows the npm shim is claude.cmd; plain "claude" resolves to a .ps1
    # that subprocess cannot exec directly.
    for name in ("claude.cmd", "claude.exe", "claude"):
        found = shutil.which(name)
        if found:
            return found
    return "claude"


@dataclass
class Settings:
    bmad_dir: Path = field(default_factory=_default_bmad_dir)
    workspace_root: Path = field(default_factory=lambda: PROJECT_DIR / "workspace")
    claude_cmd: str = field(default_factory=_resolve_claude_cmd)
    claude_model: str | None = os.environ.get("AUTOSPEC_CLAUDE_MODEL") or None
    permission_mode: str = os.environ.get("AUTOSPEC_PERMISSION_MODE", "bypassPermissions")
    agent_timeout_s: float = float(os.environ.get("AUTOSPEC_AGENT_TIMEOUT_S", "1800"))
    max_parallel_devs: int = int(os.environ.get("AUTOSPEC_MAX_PARALLEL_DEVS", "2"))
    dev_max_attempts: int = int(os.environ.get("AUTOSPEC_DEV_MAX_ATTEMPTS", "2"))
    uv_cmd: str = os.environ.get("AUTOSPEC_UV_CMD", "uv")

    def persona_path(self, agent: str) -> Path:
        return self.bmad_dir / "bmm" / "agents" / f"{agent}.md"


settings = Settings()
