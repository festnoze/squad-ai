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
    # Agent provider: "claude" (CLI harness), "openai" (API key) or "ollama"
    # (local models). Switchable at runtime through POST /api/provider.
    agent_provider: str = field(
        default_factory=lambda: os.environ.get("AUTOSPEC_AGENT_PROVIDER", "claude").strip().lower()
    )
    openai_api_key: str = field(
        default_factory=lambda: os.environ.get("AUTOSPEC_OPENAI_API_KEY")
        or os.environ.get("OPENAI_API_KEY", "")
    )
    openai_base_url: str = field(
        default_factory=lambda: os.environ.get(
            "AUTOSPEC_OPENAI_BASE_URL", "https://api.openai.com/v1"
        ).rstrip("/")
    )
    openai_model: str = field(
        default_factory=lambda: os.environ.get("AUTOSPEC_OPENAI_MODEL", "gpt-4o-mini")
    )
    # USD per 1M tokens, used to estimate cost (the OpenAI API does not return
    # a price). 0 = don't estimate.
    openai_price_in: float = field(
        default_factory=lambda: _env_float("AUTOSPEC_OPENAI_PRICE_IN", 0.0, minimum=0.0)
    )
    openai_price_out: float = field(
        default_factory=lambda: _env_float("AUTOSPEC_OPENAI_PRICE_OUT", 0.0, minimum=0.0)
    )
    ollama_base_url: str = field(
        default_factory=lambda: os.environ.get(
            "AUTOSPEC_OLLAMA_BASE_URL", "http://localhost:11434"
        ).rstrip("/")
    )
    ollama_model: str = field(
        default_factory=lambda: os.environ.get("AUTOSPEC_OLLAMA_MODEL", "llama3.1")
    )
    # Cap on the write/read tool-loop rounds of the LangChain providers (OpenAI
    # / Ollama are plain chat models: file edits go through a bounded JSON
    # protocol).
    provider_tool_rounds: int = field(
        default_factory=lambda: _env_int("AUTOSPEC_PROVIDER_TOOL_ROUNDS", 8, minimum=1)
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
    # Component proposal phase (solution agent right after the brief) and its
    # setup executor. Real dependency installs stay behind an extra flag so the
    # default behaviour remains demo-safe (folders + manifests only).
    components_enabled: bool = field(
        default_factory=lambda: _env_bool("AUTOSPEC_COMPONENTS", False)
    )
    setup_install: bool = field(
        default_factory=lambda: _env_bool("AUTOSPEC_SETUP_INSTALL", False)
    )
    npm_cmd: str = field(default_factory=lambda: os.environ.get("AUTOSPEC_NPM_CMD", "npm"))
    # Claude usage-window watchdog (M2): when the Claude harness reports an
    # exhausted usage window, schedule an automatic resume when a fresh session
    # opens. Reset time read from the CLI error, else from ccusage's active
    # billing block, else now + fallback. Only active for the claude provider.
    session_monitor_enabled: bool = field(
        default_factory=lambda: _env_bool("AUTOSPEC_SESSION_MONITOR", True)
    )
    ccusage_cmd: str = field(
        default_factory=lambda: os.environ.get("AUTOSPEC_CCUSAGE_CMD", "npx --yes ccusage")
    )
    resume_fallback_min: float = field(
        default_factory=lambda: _env_float("AUTOSPEC_RESUME_FALLBACK_MIN", 60.0, minimum=1.0)
    )
    # Tech-writer phase after each build (README + launch instructions for the
    # GENERATED project). OFF by default; also triggerable via POST /document.
    tech_writer_enabled: bool = field(
        default_factory=lambda: _env_bool("AUTOSPEC_TECH_WRITER", False)
    )
    # Playwright UI acceptance tests for UI-flagged stories. Requires browsers
    # installed in the workspace venv; OFF by default.
    ui_tests_enabled: bool = field(
        default_factory=lambda: _env_bool("AUTOSPEC_UI_TESTS", False)
    )
    # Closed-loop product evaluator (E6): after each delivered iteration (before
    # the analyze phase) an agent actually exercises the generated product and
    # turns the run into structured findings, fed into the feedback-impact
    # pipeline. OFF by default; also triggerable via POST /evaluate.
    evaluator_enabled: bool = field(
        default_factory=lambda: _env_bool("AUTOSPEC_EVALUATOR", False)
    )
    # Wall-clock cap on the untrusted `main.py` run the evaluator observes. A
    # long-running server simply hits this timeout (we keep its startup output).
    evaluator_run_timeout_s: float = field(
        default_factory=lambda: _env_float("AUTOSPEC_EVALUATOR_RUN_TIMEOUT_S", 20.0, minimum=1.0)
    )
    # Factory retrospective (E7): a meta-learning agent runs between iterations,
    # mines the collected build signals (attempts, red→green, refine scores,
    # cost) and produces durable lessons injected into the QA/Dev prompts plus
    # tuning recommendations. OFF by default; also triggerable via POST /retro.
    retro_enabled: bool = field(
        default_factory=lambda: _env_bool("AUTOSPEC_RETRO", False)
    )
    # Cap on the durable lessons carried across iterations (bounds prompt growth).
    retro_max_lessons: int = field(
        default_factory=lambda: _env_int("AUTOSPEC_RETRO_MAX_LESSONS", 12, minimum=1)
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
