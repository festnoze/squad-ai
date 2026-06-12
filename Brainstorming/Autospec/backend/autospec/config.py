"""Runtime configuration: paths to the BMAD install, workspaces, and the Claude CLI."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent

# Load backend/.env if present (shell env vars still take precedence).
load_dotenv(BACKEND_DIR / ".env")

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


def _default_workspace_root() -> Path:
    env = os.environ.get("AUTOSPEC_WORKSPACE_ROOT")
    if env:
        p = Path(env)
        return p if p.is_absolute() else (BACKEND_DIR / p)
    return PROJECT_DIR / "workspace"


@dataclass
class Settings:
    bmad_dir: Path = field(default_factory=_default_bmad_dir)
    workspace_root: Path = field(default_factory=_default_workspace_root)
    claude_cmd: str = field(default_factory=_resolve_claude_cmd)
    claude_model: str | None = os.environ.get("AUTOSPEC_CLAUDE_MODEL") or None
    permission_mode: str = os.environ.get("AUTOSPEC_PERMISSION_MODE", "bypassPermissions")
    agent_timeout_s: float = float(os.environ.get("AUTOSPEC_AGENT_TIMEOUT_S", "1800"))
    max_parallel_devs: int = int(os.environ.get("AUTOSPEC_MAX_PARALLEL_DEVS", "2"))
    dev_max_attempts: int = int(os.environ.get("AUTOSPEC_DEV_MAX_ATTEMPTS", "2"))
    uv_cmd: str = os.environ.get("AUTOSPEC_UV_CMD", "uv")
    # Demo / e2e mode: drive a deterministic scripted agent backend and skip the
    # real `uv run pytest` verification, so the full stack runs without the
    # Claude CLI. demo_delay_s slows scripted agents so UI transitions (and
    # pause/stop) are observable.
    fake_agents: bool = os.environ.get("AUTOSPEC_FAKE_AGENTS", "") not in ("", "0", "false")
    demo_delay_s: float = float(os.environ.get("AUTOSPEC_DEMO_DELAY_S", "0"))
    # Refinement harness (maker -> critic -> judge loop). OFF by default to save
    # tokens; enable globally with AUTOSPEC_REFINE, then per role. Deterministic
    # stop: hard round cap AND a judge quality score threshold.
    # Optional Architecture phase (BMAD `architect`) between PO and build. The
    # technical design it produces is injected into the QA and Dev prompts. OFF
    # by default, gated exactly like refine_enabled.
    architecture_enabled: bool = os.environ.get("AUTOSPEC_ARCHITECTURE", "") not in ("", "0", "false")
    refine_enabled: bool = os.environ.get("AUTOSPEC_REFINE", "") not in ("", "0", "false")
    refine_po: bool = os.environ.get("AUTOSPEC_REFINE_PO", "1") not in ("0", "false")
    refine_dev: bool = os.environ.get("AUTOSPEC_REFINE_DEV", "1") not in ("0", "false")
    refine_max_rounds: int = int(os.environ.get("AUTOSPEC_REFINE_MAX_ROUNDS", "2"))
    refine_quality_threshold: int = int(os.environ.get("AUTOSPEC_REFINE_QUALITY_THRESHOLD", "80"))

    def refine_for(self, role: str) -> bool:
        """Is the refinement loop active for this maker role ('po' / 'dev')?"""
        return self.refine_enabled and bool(getattr(self, f"refine_{role}", True))

    def persona_path(self, agent: str) -> Path:
        return self.bmad_dir / "bmm" / "agents" / f"{agent}.md"


settings = Settings()
