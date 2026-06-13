"""Runtime configuration: paths to the BMAD install, workspaces, and the Claude CLI."""

from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parent.parent

# Load backend/.env if present (shell env vars still take precedence).
load_dotenv(BACKEND_DIR / ".env")

PROJECT_DIR = BACKEND_DIR.parent  # Autospec/

_TRUTHY = ("1", "true", "yes", "on")
_FALSY = ("0", "false", "no", "off")


def _env_bool(name: str, default: bool) -> bool:
    """Parse a boolean env var (case-insensitive 1/true/yes/on, 0/false/no/off).

    Unset/empty falls back to the default; an unrecognized value logs a warning
    and falls back too — a malformed variable must never crash the import.
    """
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    value = raw.strip().lower()
    if value in _TRUTHY:
        return True
    if value in _FALSY:
        return False
    logger.warning("Invalid boolean %s=%r, using default %s", name, raw, default)
    return default


def _env_int(name: str, default: int, minimum: int | None = None) -> int:
    """Parse an integer env var, falling back to the default (with a warning)
    on a non-numeric value, and clamping to ``minimum`` when given."""
    raw = os.environ.get(name)
    value = default
    if raw is not None and raw.strip():
        try:
            value = int(raw)
        except ValueError:
            logger.warning("Invalid integer %s=%r, using default %s", name, raw, default)
    if minimum is not None and value < minimum:
        logger.warning("%s=%s below minimum, clamping to %s", name, value, minimum)
        value = minimum
    return value


def _env_float(name: str, default: float, minimum: float | None = None) -> float:
    """Parse a float env var, falling back to the default (with a warning)
    on a non-numeric value, and clamping to ``minimum`` when given."""
    raw = os.environ.get(name)
    value = default
    if raw is not None and raw.strip():
        try:
            value = float(raw)
        except ValueError:
            logger.warning("Invalid number %s=%r, using default %s", name, raw, default)
    if minimum is not None and value < minimum:
        logger.warning("%s=%s below minimum, clamping to %s", name, value, minimum)
        value = minimum
    return value


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
    claude_model: str | None = field(
        default_factory=lambda: os.environ.get("AUTOSPEC_CLAUDE_MODEL") or None
    )
    permission_mode: str = field(
        default_factory=lambda: os.environ.get("AUTOSPEC_PERMISSION_MODE", "bypassPermissions")
    )
    agent_timeout_s: float = field(
        default_factory=lambda: _env_float("AUTOSPEC_AGENT_TIMEOUT_S", 1800.0, minimum=1.0)
    )
    # Semaphore(0) would deadlock the build phase, hence the floor of 1.
    max_parallel_devs: int = field(
        default_factory=lambda: _env_int("AUTOSPEC_MAX_PARALLEL_DEVS", 2, minimum=1)
    )
    dev_max_attempts: int = field(
        default_factory=lambda: _env_int("AUTOSPEC_DEV_MAX_ATTEMPTS", 2, minimum=1)
    )
    uv_cmd: str = field(default_factory=lambda: os.environ.get("AUTOSPEC_UV_CMD", "uv"))
    # Demo / e2e mode: drive a deterministic scripted agent backend and skip the
    # real `uv run pytest` verification, so the full stack runs without the
    # Claude CLI. demo_delay_s slows scripted agents so UI transitions (and
    # pause/stop) are observable.
    fake_agents: bool = field(default_factory=lambda: _env_bool("AUTOSPEC_FAKE_AGENTS", False))
    demo_delay_s: float = field(
        default_factory=lambda: _env_float("AUTOSPEC_DEMO_DELAY_S", 0.0, minimum=0.0)
    )
    # Refinement harness (maker -> critic -> judge loop). OFF by default to save
    # tokens; enable globally with AUTOSPEC_REFINE, then per role. Deterministic
    # stop: hard round cap AND a judge quality score threshold.
    # Optional Architecture phase (BMAD `architect`) between PO and build. The
    # technical design it produces is injected into the QA and Dev prompts. OFF
    # by default, gated exactly like refine_enabled.
    architecture_enabled: bool = field(
        default_factory=lambda: _env_bool("AUTOSPEC_ARCHITECTURE", False)
    )
    refine_enabled: bool = field(default_factory=lambda: _env_bool("AUTOSPEC_REFINE", False))
    refine_po: bool = field(default_factory=lambda: _env_bool("AUTOSPEC_REFINE_PO", True))
    refine_dev: bool = field(default_factory=lambda: _env_bool("AUTOSPEC_REFINE_DEV", True))
    refine_max_rounds: int = field(
        default_factory=lambda: _env_int("AUTOSPEC_REFINE_MAX_ROUNDS", 2, minimum=0)
    )
    refine_quality_threshold: int = field(
        default_factory=lambda: _env_int("AUTOSPEC_REFINE_QUALITY_THRESHOLD", 80, minimum=0)
    )

    def refine_for(self, role: str) -> bool:
        """Is the refinement loop active for this maker role ('po' / 'dev')?"""
        return self.refine_enabled and bool(getattr(self, f"refine_{role}", True))

    def persona_path(self, agent: str) -> Path:
        return self.bmad_dir / "bmm" / "agents" / f"{agent}.md"


settings = Settings()
