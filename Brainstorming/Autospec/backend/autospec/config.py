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


def _resolve_codex_cmd() -> str:
    """Resolve the OpenAI Codex CLI command (mirror of _resolve_claude_cmd).

    Codex runs headless via ``codex exec`` — the OpenAI counterpart of the Claude
    Code CLI harness. On Windows the npm shim is codex.cmd."""
    env = os.environ.get("AUTOSPEC_CODEX_CMD")
    if env:
        return env
    for name in ("codex.cmd", "codex.exe", "codex"):
        found = shutil.which(name)
        if found:
            return found
    return "codex"


def _default_workspace_root() -> Path:
    env = os.environ.get("AUTOSPEC_WORKSPACE_ROOT")
    if env:
        p = Path(env)
        return p if p.is_absolute() else (BACKEND_DIR / p)
    return PROJECT_DIR / "workspace"


def _default_skills_dir() -> Path:
    """Source-of-truth bundled skill library (copied into each workspace's
    ``.claude/skills/`` so the headless claude agent auto-discovers them)."""
    env = os.environ.get("AUTOSPEC_SKILLS_DIR")
    if env:
        p = Path(env)
        return p if p.is_absolute() else (BACKEND_DIR / p)
    return BACKEND_DIR / "autospec" / "skills"


def _default_phase_models() -> dict:
    """Per-phase model overrides (M3) from AUTOSPEC_MODEL_<PHASE> env vars."""
    out = {}
    for phase in ("spec", "analyze", "plan", "architect", "build", "done"):
        val = os.environ.get(f"AUTOSPEC_MODEL_{phase.upper()}")
        if val and val.strip():
            out[phase] = val.strip()
    return out


@dataclass
class Settings:
    bmad_dir: Path = field(default_factory=_default_bmad_dir)
    workspace_root: Path = field(default_factory=_default_workspace_root)
    claude_cmd: str = field(default_factory=_resolve_claude_cmd)
    claude_model: str | None = field(
        default_factory=lambda: os.environ.get("AUTOSPEC_CLAUDE_MODEL") or None
    )
    # Codex CLI harness: the OpenAI counterpart of the Claude Code CLI, driven
    # headless via ``codex exec``.
    codex_cmd: str = field(default_factory=_resolve_codex_cmd)
    codex_model: str | None = field(
        default_factory=lambda: os.environ.get("AUTOSPEC_CODEX_MODEL") or None
    )
    # Per-phase model routing (M3): a cheap model for spec/plan, a strong one for
    # build/refine. Populated from AUTOSPEC_MODEL_<PHASE>; falls back to claude_model.
    phase_models: dict = field(default_factory=_default_phase_models)
    # Agent provider: "claude" (CLI harness), "openai" (API key) or "ollama"
    # (local models). Switchable at runtime through POST /api/provider.
    agent_provider: str = field(
        default_factory=lambda: os.environ.get("AUTOSPEC_AGENT_PROVIDER", "claude").strip().lower()
    )
    # Product generation profile. "auto" keeps existing flag-driven behaviour;
    # explicit profiles (library-fast/cli/api/web-ssr/fullstack/brownfield)
    # are applied per project by the pipeline.
    product_profile: str = field(
        default_factory=lambda: os.environ.get("AUTOSPEC_PRODUCT_PROFILE", "auto").strip().lower()
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
    # Anthropic API direct (M4): the Claude models via the API (langchain-anthropic),
    # independent of the local Claude Code CLI harness.
    anthropic_api_key: str = field(
        default_factory=lambda: os.environ.get("AUTOSPEC_ANTHROPIC_API_KEY")
        or os.environ.get("ANTHROPIC_API_KEY", "")
    )
    anthropic_model: str = field(
        default_factory=lambda: os.environ.get("AUTOSPEC_ANTHROPIC_MODEL", "claude-sonnet-4-6")
    )
    anthropic_price_in: float = field(
        default_factory=lambda: _env_float("AUTOSPEC_ANTHROPIC_PRICE_IN", 0.0, minimum=0.0)
    )
    anthropic_price_out: float = field(
        default_factory=lambda: _env_float("AUTOSPEC_ANTHROPIC_PRICE_OUT", 0.0, minimum=0.0)
    )
    # OpenRouter: an OpenAI-compatible aggregator hub. Reuses the OpenAI runner
    # path with OpenRouter's base_url + key. The model dropdown is populated live
    # with the most-popular programming models (GET {base}/models?category=programming).
    # Reads the bare OPENROUTER_* names too (as the user put them in .env).
    openrouter_api_key: str = field(
        default_factory=lambda: os.environ.get("AUTOSPEC_OPENROUTER_API_KEY")
        or os.environ.get("OPENROUTER_API_KEY")
        or ""
    )
    openrouter_base_url: str = field(
        default_factory=lambda: (
            os.environ.get("AUTOSPEC_OPENROUTER_BASE_URL")
            or os.environ.get("OPENROUTER_BASE_URL")
            or "https://openrouter.ai/api/v1"
        ).rstrip("/")
    )
    openrouter_model: str = field(
        default_factory=lambda: os.environ.get("AUTOSPEC_OPENROUTER_MODEL", "")
    )
    openrouter_price_in: float = field(
        default_factory=lambda: _env_float("AUTOSPEC_OPENROUTER_PRICE_IN", 0.0, minimum=0.0)
    )
    openrouter_price_out: float = field(
        default_factory=lambda: _env_float("AUTOSPEC_OPENROUTER_PRICE_OUT", 0.0, minimum=0.0)
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
    # L2g: build/test toolchains for the non-Python backend languages.
    go_cmd: str = field(default_factory=lambda: os.environ.get("AUTOSPEC_GO_CMD", "go"))
    cargo_cmd: str = field(default_factory=lambda: os.environ.get("AUTOSPEC_CARGO_CMD", "cargo"))
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
    # L2: LLM backend-language selector after the brief (off -> deterministic
    # heuristic still sets the language; this just lets an agent refine it).
    language_selector_enabled: bool = field(
        default_factory=lambda: _env_bool("AUTOSPEC_LANGUAGE_SELECTOR", False)
    )
    # B-IDEA: idea-maturity assessment at creation. When a goal reads as a vague
    # idea (not a structured brief), Autospec offers a BMAD brainstorming session
    # to refine it; if the user declines (or auto-spec is on) the brainstorming
    # runs autonomously with the AI playing the product owner. BMAD picks the
    # brainstorming techniques adapted to the subject. OFF by default (keeps the
    # plain Socratic interview); enable with AUTOSPEC_BRAINSTORM_ASSIST.
    brainstorm_assist_enabled: bool = field(
        default_factory=lambda: _env_bool("AUTOSPEC_BRAINSTORM_ASSIST", False)
    )
    # Rounds of autonomous Q&A (analyst asks ↔ AI answers) before the brief is
    # synthesized, when the brainstorming runs without the user.
    brainstorm_auto_rounds: int = field(
        default_factory=lambda: _env_int("AUTOSPEC_BRAINSTORM_ROUNDS", 3, minimum=1)
    )
    # Multi-stream redesign (ST-1): split work into streams (backend/frontend/
    # cache/database) with an optional Task level under each US, so independent
    # streams build in parallel. OFF by default → one implicit backend stream,
    # no tasks (the pre-streams behaviour is unchanged).
    streams_enabled: bool = field(
        default_factory=lambda: _env_bool("AUTOSPEC_STREAMS", False)
    )
    # Skills (SK-1): give the QA/Dev agents a library of reusable, progressively-
    # disclosed capability files (3-layer architecture, per-layer builders, BDD,
    # test generation) instead of inlining everything in the prompt. The claude
    # CLI auto-discovers the workspace's seeded `.claude/skills/` (native Skill
    # tool); every provider also gets a compact skill CATALOG injected into the
    # prompt. OFF by default; master flag AND per-role flag, like refine.
    skills_enabled: bool = field(default_factory=lambda: _env_bool("AUTOSPEC_SKILLS", False))
    skills_qa: bool = field(default_factory=lambda: _env_bool("AUTOSPEC_SKILLS_QA", True))
    skills_dev: bool = field(default_factory=lambda: _env_bool("AUTOSPEC_SKILLS_DEV", True))
    skills_dir: Path = field(default_factory=_default_skills_dir)
    # Decomposition build mode (SK-2): split a non-trivial backend story into
    # layered sub-tasks (entity → repo → service → endpoint → tests), each built
    # by a focused subagent (tiny context window) via the parallel worktree
    # engine, then aggregated. Reuses the streams Task/worktree machinery. OFF by
    # default; turning it on routes eligible stories through the streams path.
    decompose_enabled: bool = field(default_factory=lambda: _env_bool("AUTOSPEC_DECOMPOSE", False))
    setup_install: bool = field(
        default_factory=lambda: _env_bool("AUTOSPEC_SETUP_INSTALL", False)
    )
    node_cmd: str = field(default_factory=lambda: os.environ.get("AUTOSPEC_NODE_CMD", "node"))
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
    # Security & supply-chain review (S1): after each build, an agent audits the
    # generated code and runs pip-audit/npm audit on its dependencies, emitting
    # security Findings into the feedback-impact pipeline. OFF by default; also
    # triggerable via POST /security-review.
    security_review_enabled: bool = field(
        default_factory=lambda: _env_bool("AUTOSPEC_SECURITY_REVIEW", False)
    )
    security_audit_timeout_s: float = field(
        default_factory=lambda: _env_float("AUTOSPEC_SECURITY_AUDIT_TIMEOUT_S", 60.0, minimum=1.0)
    )
    # Optional Langfuse tracing of every agent call (O1): one generation per call
    # (phase, project, model, tokens, cost, duration). OFF by default; needs the
    # `langfuse` package + LANGFUSE_* env vars. Lazily imported, no-op when
    # unavailable — never affects the pipeline.
    langfuse_enabled: bool = field(
        default_factory=lambda: _env_bool("AUTOSPEC_LANGFUSE", False)
    )
    # Mutation testing (Q1): after a story turns green, mutate the package source
    # one point at a time and rerun the suite against each mutant to score test
    # robustness (kill rate). OFF by default (it reruns pytest per mutant).
    mutation_enabled: bool = field(
        default_factory=lambda: _env_bool("AUTOSPEC_MUTATION", False)
    )
    mutation_max_mutants: int = field(
        default_factory=lambda: _env_int("AUTOSPEC_MUTATION_MAX", 30, minimum=1)
    )
    # Coverage gate (Q2): run the suite under coverage after a story turns green,
    # recording the total %% on story.coverage_score (badge). With a gate
    # threshold > 0, a story below it is rejected (kept red) instead of done.
    coverage_enabled: bool = field(
        default_factory=lambda: _env_bool("AUTOSPEC_COVERAGE", False)
    )
    coverage_gate_threshold: int = field(
        default_factory=lambda: _env_int("AUTOSPEC_COVERAGE_GATE", 0, minimum=0)
    )
    # Granular approval gates (U4): when on, the pipeline blocks after planning
    # (plan + architecture) and waits for explicit human approval before building.
    approval_gates_enabled: bool = field(
        default_factory=lambda: _env_bool("AUTOSPEC_APPROVAL_GATES", False)
    )
    # Smoke-run gate: after the suite is green, actually BOOT the delivered app
    # and require it to start (a web/API app must open its port; a CLI must exit
    # 0) — a non-runnable build then fails the iteration like a red test. ON by
    # default for generated apps; the library-fast profile disables it.
    smoke_run: bool = field(
        default_factory=lambda: _env_bool("AUTOSPEC_SMOKE_RUN", True)
    )
    smoke_run_timeout_s: float = field(
        default_factory=lambda: _env_float("AUTOSPEC_SMOKE_RUN_TIMEOUT_S", 60.0, minimum=5.0)
    )
    smoke_run_port: int = field(
        default_factory=lambda: _env_int("AUTOSPEC_SMOKE_RUN_PORT", 8000, minimum=1)
    )
    # Untrusted-code sandbox (R1): run the generated app inside a no-network
    # Docker container. OFF by default; needs Docker + an image carrying the
    # project toolchain (uv). The image/binary are configurable.
    sandbox_enabled: bool = field(
        default_factory=lambda: _env_bool("AUTOSPEC_SANDBOX", False)
    )
    sandbox_image: str = field(
        default_factory=lambda: os.environ.get("AUTOSPEC_SANDBOX_IMAGE", "python:3.12-slim")
    )
    docker_cmd: str = field(
        default_factory=lambda: os.environ.get("AUTOSPEC_DOCKER_CMD", "docker")
    )
    # Cross-project lesson library (F1): promote E7 lessons to a shared store
    # injected into every new project's Dev/QA prompts. OFF by default.
    shared_lessons_enabled: bool = field(
        default_factory=lambda: _env_bool("AUTOSPEC_SHARED_LESSONS", False)
    )
    shared_lessons_max: int = field(
        default_factory=lambda: _env_int("AUTOSPEC_SHARED_LESSONS_MAX", 20, minimum=1)
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
    # Delivery gates: the deterministic Definition-of-Done check is ON by
    # default in production so a green subset of tests cannot mark an incomplete
    # project as delivered. Strict per-criterion evidence is opt-in because very
    # small Gherkin-only stories are still valid in the existing pipeline.
    definition_of_done_enabled: bool = field(
        default_factory=lambda: _env_bool("AUTOSPEC_DEFINITION_OF_DONE", True)
    )
    definition_of_done_strict_criteria: bool = field(
        default_factory=lambda: _env_bool("AUTOSPEC_DOD_STRICT_CRITERIA", False)
    )
    runtime_acceptance_enabled: bool = field(
        default_factory=lambda: _env_bool("AUTOSPEC_RUNTIME_ACCEPTANCE", False)
    )
    runtime_acceptance_timeout_s: float = field(
        default_factory=lambda: _env_float("AUTOSPEC_RUNTIME_ACCEPTANCE_TIMEOUT_S", 90.0, minimum=10.0)
    )

    def refine_for(self, role: str) -> bool:
        """Is the refinement loop active for this maker role ('po' / 'dev')?"""
        return self.refine_enabled and bool(getattr(self, f"refine_{role}", True))

    def skills_for(self, role: str) -> bool:
        """Are skills active for this agent role ('qa' / 'dev')? Master flag AND
        the per-role flag, mirroring ``refine_for``."""
        return self.skills_enabled and bool(getattr(self, f"skills_{role}", True))

    def model_for_phase(self, phase: str) -> str | None:
        """Model to use for a given pipeline phase (M3): the per-phase override
        if set, else the global claude_model."""
        return self.phase_models.get(phase) or self.claude_model

    def persona_path(self, agent: str) -> Path:
        return self.bmad_dir / "bmm" / "agents" / f"{agent}.md"


settings = Settings()
