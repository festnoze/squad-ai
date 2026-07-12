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

# Snapshot the keys the operator set in the actual SHELL, before .env fills the
# rest. A quality preset (PRESET=verified) overrides .env *defaults* but must
# still yield to a deliberate shell override — this set is how we tell them apart
# (mirroring load_dotenv's own "shell wins over .env" precedence).
_SHELL_ENV_KEYS = frozenset(os.environ.keys())

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


def _env_mode(name: str, default: str = "off",
              allowed: tuple[str, ...] = ("off", "warn", "strict")) -> str:
    """Parse a tri-state guard mode env var (off | warn | strict).

    A bare truthy value (1/true/yes/on) maps to ``warn`` (detect + log, the safe
    observe-first default); a falsy value to ``off``; an explicit off/warn/strict
    is honored; anything else warns and falls back."""
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    if raw in _TRUTHY:
        return "warn"
    if raw in _FALSY:
        return "off"
    if raw in allowed:
        return raw
    logger.warning("Invalid mode %s=%r, using default %s", name, raw, default)
    return default


def _default_bmad_dir() -> Path:
    env = os.environ.get("BMAD_DIR")
    if env:
        return Path(env)
    # Autospec lives next to the _bmad install (Brainstorming/_bmad)
    candidate = PROJECT_DIR.parent / "_bmad"
    return candidate


def _resolve_claude_cmd() -> str:
    env = os.environ.get("CLAUDE_CMD")
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
    env = os.environ.get("CODEX_CMD")
    if env:
        return env
    for name in ("codex.cmd", "codex.exe", "codex"):
        found = shutil.which(name)
        if found:
            return found
    return "codex"


def _default_workspace_root() -> Path:
    env = os.environ.get("WORKSPACE_ROOT")
    if env:
        p = Path(env)
        return p if p.is_absolute() else (BACKEND_DIR / p)
    return PROJECT_DIR / "workspace"


def _default_skills_dir() -> Path:
    """Source-of-truth bundled skill library (copied into each workspace's
    ``.claude/skills/`` so the headless claude agent auto-discovers them)."""
    env = os.environ.get("SKILLS_DIR")
    if env:
        p = Path(env)
        return p if p.is_absolute() else (BACKEND_DIR / p)
    return BACKEND_DIR / "autospec" / "skills"


def _default_phase_models() -> dict:
    """Per-phase model overrides (M3) from MODEL_<PHASE> env vars."""
    out = {}
    for phase in ("spec", "analyze", "plan", "architect", "build", "done"):
        val = os.environ.get(f"MODEL_{phase.upper()}")
        if val and val.strip():
            out[phase] = val.strip()
    return out


# W4: which cost tier each agent persona belongs to. boss = expensive mind
# (plans, reviews, arbitrates, rules — never codes); worker = cheap coder;
# checker = mid-tier verifier (critic/judge/qa/evaluator). Personas absent from
# the map fall through to the phase router.
PERSONA_TIERS: dict[str, str] = {
    # boss
    "pm": "boss", "sm": "boss", "po-structure": "boss", "po-spec": "boss",
    "po-gherkin": "boss", "analyst": "boss", "architect": "boss",
    "arbiter": "boss", "classifier": "boss", "constitution": "boss", "retro": "boss",
    # worker
    "dev": "worker", "dev-frontend": "worker",
    # checker
    "qa": "checker", "critic": "checker", "judge": "checker",
    "evaluator": "checker", "security-reviewer": "checker",
    "independence-judge": "checker", "tech-writer": "checker",
}


def _default_model_tiers() -> dict:
    """W4: per-tier model ids from MODEL_BOSS / MODEL_WORKER / MODEL_CHECKER."""
    out = {}
    for tier in ("boss", "worker", "checker"):
        val = os.environ.get(f"MODEL_{tier.upper()}")
        if val and val.strip():
            out[tier] = val.strip()
    return out


def _default_tier_prices(direction: str) -> dict:
    """USD per 1M tokens per tier (PRICE_BOSS_OUT, PRICE_WORKER_IN, …), used to
    estimate cost when a runner returns none (Codex/OpenAI/Ollama)."""
    out = {}
    for tier in ("boss", "worker", "checker"):
        out[tier] = _env_float(f"PRICE_{tier.upper()}_{direction.upper()}", 0.0, minimum=0.0)
    return out


def _default_model_ladder() -> list[str]:
    """W1: the escalation ladder — comma-separated model ids in COST-ASCENDING
    order (cheapest first). On a retry the recovery machine climbs one rung, so a
    task only reaches the expensive model if the cheap ones actually failed it.
    Empty (unset) → escalation is a no-op even when ESCALATE_ON_RETRY is on."""
    raw = os.environ.get("MODEL_LADDER", "") or ""
    return [m.strip() for m in raw.split(",") if m.strip()]


@dataclass
class Settings:
    bmad_dir: Path = field(default_factory=_default_bmad_dir)
    workspace_root: Path = field(default_factory=_default_workspace_root)
    claude_cmd: str = field(default_factory=_resolve_claude_cmd)
    # Default model of the Claude Code CLI harness ("claude code" provider):
    # Opus 4.8 unless CLAUDE_MODEL overrides it.
    claude_model: str | None = field(
        default_factory=lambda: os.environ.get("CLAUDE_MODEL") or "claude-opus-4-8"
    )
    # Codex CLI harness: the OpenAI counterpart of the Claude Code CLI, driven
    # headless via ``codex exec``.
    codex_cmd: str = field(default_factory=_resolve_codex_cmd)
    codex_model: str | None = field(
        default_factory=lambda: os.environ.get("CODEX_MODEL") or None
    )
    # Per-phase model routing (M3): a cheap model for spec/plan, a strong one for
    # build/refine. Populated from MODEL_<PHASE>; falls back to claude_model.
    phase_models: dict = field(default_factory=_default_phase_models)
    # W1: model-escalation ladder. When ESCALATE_ON_RETRY is on and MODEL_LADDER
    # is set, a red story's retry climbs to the next (stronger) rung — so the
    # expensive model is only reached by tasks the cheap ones actually failed.
    escalate_on_retry_enabled: bool = field(
        default_factory=lambda: _env_bool("ESCALATE_ON_RETRY", False)
    )
    model_ladder: list = field(default_factory=_default_model_ladder)
    # W4: role→tier→model routing. When on, an agent's persona maps to a cost
    # tier (boss/worker/checker) → model, so the expensive mind reviews/plans/
    # arbitrates while cheap workers code. Off → the per-phase router is unchanged.
    role_routing_enabled: bool = field(
        default_factory=lambda: _env_bool("ROLE_ROUTING", False)
    )
    model_tiers: dict = field(default_factory=_default_model_tiers)
    tier_price_in: dict = field(default_factory=lambda: _default_tier_prices("in"))
    tier_price_out: dict = field(default_factory=lambda: _default_tier_prices("out"))
    # W1.3 (wired with Wave 2): when a story exhausts its dev attempts, ask a
    # boss-tier classifier for the root cause (too_big / wrong_test /
    # spec_contradiction / genuinely_hard) instead of blindly splitting. Off by
    # default; the recovery machine falls back to split→fail when off.
    classify_on_exhaustion_enabled: bool = field(
        default_factory=lambda: _env_bool("CLASSIFY_ON_EXHAUSTION", False)
    )
    # W2: wrong-test arbitration ("who checks the checker"). When on, a story that
    # exhausted its dev attempts gets one boss-tier arbitration: if the failing
    # test contradicts the acceptance criteria, a checker-tier agent corrects the
    # TEST (never the criteria) and the suite is rerun. Executed facts are never
    # overruled. Bounded by arbitration_max per story per iteration.
    dispute_escalation_enabled: bool = field(
        default_factory=lambda: _env_bool("DISPUTE_ESCALATION", False)
    )
    arbitration_max: int = field(
        default_factory=lambda: _env_int("ARBITRATION_MAX", 1, minimum=1)
    )
    # W2.0: AC<->test traceability. When on, the delivery pipeline reports ACs with
    # no executed test and orphan tests (asserting behavior no AC required).
    ac_traceability_enabled: bool = field(
        default_factory=lambda: _env_bool("AC_TRACEABILITY", False)
    )
    # W3: project constitution. When on, a boss-tier phase after SPEC derives a
    # small set of non-negotiable project-wide rules and COMPILES them to pytest
    # files under tests/constitution/ (they then ride the normal suite every
    # round) or delivery-gate commands; non-compilable rules become advisory
    # (prompt-injected). Off by default.
    constitution_enabled: bool = field(
        default_factory=lambda: _env_bool("CONSTITUTION", False)
    )
    constitution_max_rules: int = field(
        default_factory=lambda: _env_int("CONSTITUTION_MAX", 8, minimum=1)
    )
    # W5.1: design amendment. When a failure is a genuine spec contradiction, a
    # boss-tier agent proposes a MINIMAL amendment, an INDEPENDENT check rejects
    # it if it weakens the requirement, and the survivor is queued HUMAN-PENDING
    # by default (AMENDMENT_AUTO=1 opts into unattended apply). Off by default.
    design_amendment_enabled: bool = field(
        default_factory=lambda: _env_bool("DESIGN_AMENDMENT", False)
    )
    amendment_auto: bool = field(
        default_factory=lambda: _env_bool("AMENDMENT_AUTO", False)
    )
    amendment_max_depth: int = field(
        default_factory=lambda: _env_int("AMENDMENT_MAX_DEPTH", 1, minimum=0)
    )
    # Agent provider: "claude code" (Claude Code CLI harness, the default),
    # "claude" (Anthropic API direct), "codex" (OpenAI CLI), "openai",
    # "openrouter" or "ollama". Switchable at runtime through POST /api/provider.
    agent_provider: str = field(
        default_factory=lambda: os.environ.get("AGENT_PROVIDER", "claude code").strip().lower()
    )
    # Product generation profile. "auto" keeps existing flag-driven behaviour;
    # explicit profiles (library-fast/cli/api/web-ssr/fullstack/brownfield)
    # are applied per project by the pipeline.
    product_profile: str = field(
        default_factory=lambda: os.environ.get("PRODUCT_PROFILE", "auto").strip().lower()
    )
    openai_api_key: str = field(
        default_factory=lambda: os.environ.get("OPENAI_API_KEY", "")
    )
    openai_base_url: str = field(
        default_factory=lambda: os.environ.get(
            "OPENAI_BASE_URL", "https://api.openai.com/v1"
        ).rstrip("/")
    )
    openai_model: str = field(
        default_factory=lambda: os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    )
    # USD per 1M tokens, used to estimate cost (the OpenAI API does not return
    # a price). 0 = don't estimate.
    openai_price_in: float = field(
        default_factory=lambda: _env_float("OPENAI_PRICE_IN", 0.0, minimum=0.0)
    )
    openai_price_out: float = field(
        default_factory=lambda: _env_float("OPENAI_PRICE_OUT", 0.0, minimum=0.0)
    )
    ollama_base_url: str = field(
        default_factory=lambda: os.environ.get(
            "OLLAMA_BASE_URL", "http://localhost:11434"
        ).rstrip("/")
    )
    ollama_model: str = field(
        default_factory=lambda: os.environ.get("OLLAMA_MODEL", "llama3.1")
    )
    # Anthropic API direct (M4): the "claude" provider — Claude models via the
    # API (langchain-anthropic), independent of the Claude Code CLI harness.
    anthropic_api_key: str = field(
        default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY", "")
    )
    anthropic_model: str = field(
        default_factory=lambda: os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-8")
    )
    anthropic_price_in: float = field(
        default_factory=lambda: _env_float("ANTHROPIC_PRICE_IN", 0.0, minimum=0.0)
    )
    anthropic_price_out: float = field(
        default_factory=lambda: _env_float("ANTHROPIC_PRICE_OUT", 0.0, minimum=0.0)
    )
    # OpenRouter: an OpenAI-compatible aggregator hub. Reuses the OpenAI runner
    # path with OpenRouter's base_url + key. The model dropdown is populated live
    # with the most-popular programming models (GET {base}/models?category=programming).
    openrouter_api_key: str = field(
        default_factory=lambda: os.environ.get("OPENROUTER_API_KEY") or ""
    )
    openrouter_base_url: str = field(
        default_factory=lambda: (
            os.environ.get("OPENROUTER_BASE_URL")
            or "https://openrouter.ai/api/v1"
        ).rstrip("/")
    )
    openrouter_model: str = field(
        default_factory=lambda: os.environ.get("OPENROUTER_MODEL", "")
    )
    openrouter_price_in: float = field(
        default_factory=lambda: _env_float("OPENROUTER_PRICE_IN", 0.0, minimum=0.0)
    )
    openrouter_price_out: float = field(
        default_factory=lambda: _env_float("OPENROUTER_PRICE_OUT", 0.0, minimum=0.0)
    )
    # Cap on the write/read tool-loop rounds of the LangChain providers (OpenAI
    # / Ollama are plain chat models: file edits go through a bounded JSON
    # protocol).
    provider_tool_rounds: int = field(
        default_factory=lambda: _env_int("PROVIDER_TOOL_ROUNDS", 8, minimum=1)
    )
    permission_mode: str = field(
        default_factory=lambda: os.environ.get("PERMISSION_MODE", "bypassPermissions")
    )
    agent_timeout_s: float = field(
        default_factory=lambda: _env_float("AGENT_TIMEOUT_S", 1800.0, minimum=1.0)
    )
    # W0.4 context-budget telemetry: flag (never truncate) a prompt whose size in
    # characters approaches this budget, so silent context overflow surfaces in
    # the timeline instead of degrading an agent invisibly. 0 disables the check.
    context_warn_chars: int = field(
        default_factory=lambda: _env_int("CONTEXT_WARN_CHARS", 0, minimum=0)
    )
    # W0.5 anti-cheating guards & harness hardening. Each is a tri-state mode
    # (off | warn | strict): warn = detect + log + record a failure signature
    # (advisory); strict = additionally block/revert so a cut corner cannot
    # survive its check. Default off; the `verified` preset turns them to warn.
    test_tamper_guard: str = field(
        default_factory=lambda: _env_mode("TEST_TAMPER_GUARD", "off")
    )
    scope_guard: str = field(default_factory=lambda: _env_mode("SCOPE_GUARD", "off"))
    skeleton_guard: str = field(default_factory=lambda: _env_mode("SKELETON_GUARD", "off"))
    import_guard: str = field(default_factory=lambda: _env_mode("IMPORT_GUARD", "off"))
    # Flaky-check quarantine: rerun a red suite once; a pass-on-rerun is treated
    # as a flake (logged, not a real failure), so the recovery ladder (W1) never
    # escalates a model over a non-deterministic test.
    flaky_rerun_enabled: bool = field(
        default_factory=lambda: _env_bool("FLAKY_RERUN", False)
    )
    # Semaphore(0) would deadlock the build phase, hence the floor of 1.
    max_parallel_devs: int = field(
        default_factory=lambda: _env_int("MAX_PARALLEL_DEVS", 2, minimum=1)
    )
    dev_max_attempts: int = field(
        default_factory=lambda: _env_int("DEV_MAX_ATTEMPTS", 2, minimum=1)
    )
    uv_cmd: str = field(default_factory=lambda: os.environ.get("UV_CMD", "uv"))
    # L2g: build/test toolchains for the non-Python backend languages.
    go_cmd: str = field(default_factory=lambda: os.environ.get("GO_CMD", "go"))
    cargo_cmd: str = field(default_factory=lambda: os.environ.get("CARGO_CMD", "cargo"))
    # Demo / e2e mode: drive a deterministic scripted agent backend and skip the
    # real `uv run pytest` verification, so the full stack runs without the
    # Claude CLI. demo_delay_s slows scripted agents so UI transitions (and
    # pause/stop) are observable.
    fake_agents: bool = field(default_factory=lambda: _env_bool("FAKE_AGENTS", False))
    demo_delay_s: float = field(
        default_factory=lambda: _env_float("DEMO_DELAY_S", 0.0, minimum=0.0)
    )
    # Refinement harness (maker -> critic -> judge loop). OFF by default to save
    # tokens; enable globally with REFINE, then per role. Deterministic
    # stop: hard round cap AND a judge quality score threshold.
    # Optional Architecture phase (BMAD `architect`) between PO and build. The
    # technical design it produces is injected into the QA and Dev prompts. OFF
    # by default, gated exactly like refine_enabled.
    architecture_enabled: bool = field(
        default_factory=lambda: _env_bool("ARCHITECTURE", False)
    )
    # Component proposal phase (solution agent right after the brief) and its
    # setup executor. Real dependency installs stay behind an extra flag so the
    # default behaviour remains demo-safe (folders + manifests only).
    components_enabled: bool = field(
        default_factory=lambda: _env_bool("COMPONENTS", False)
    )
    # L2: LLM backend-language selector after the brief (off -> deterministic
    # heuristic still sets the language; this just lets an agent refine it).
    language_selector_enabled: bool = field(
        default_factory=lambda: _env_bool("LANGUAGE_SELECTOR", False)
    )
    # B-IDEA: idea-maturity assessment at creation. When a goal reads as a vague
    # idea (not a structured brief), Autospec offers a BMAD brainstorming session
    # to refine it; if the user declines (or auto-spec is on) the brainstorming
    # runs autonomously with the AI playing the product owner. BMAD picks the
    # brainstorming techniques adapted to the subject. OFF by default (keeps the
    # plain Socratic interview); enable with BRAINSTORM_ASSIST.
    brainstorm_assist_enabled: bool = field(
        default_factory=lambda: _env_bool("BRAINSTORM_ASSIST", False)
    )
    # Rounds of autonomous Q&A (analyst asks ↔ AI answers) before the brief is
    # synthesized, when the brainstorming runs without the user.
    brainstorm_auto_rounds: int = field(
        default_factory=lambda: _env_int("BRAINSTORM_ROUNDS", 3, minimum=1)
    )
    # Multi-stream redesign (ST-1): split work into streams (backend/frontend/
    # cache/database) with an optional Task level under each US, so independent
    # streams build in parallel. OFF by default → one implicit backend stream,
    # no tasks (the pre-streams behaviour is unchanged).
    streams_enabled: bool = field(
        default_factory=lambda: _env_bool("STREAMS", False)
    )
    # Skills (SK-1): give the QA/Dev agents a library of reusable, progressively-
    # disclosed capability files (3-layer architecture, per-layer builders, BDD,
    # test generation) instead of inlining everything in the prompt. The claude
    # CLI auto-discovers the workspace's seeded `.claude/skills/` (native Skill
    # tool); every provider also gets a compact skill CATALOG injected into the
    # prompt. OFF by default; master flag AND per-role flag, like refine.
    skills_enabled: bool = field(default_factory=lambda: _env_bool("SKILLS", False))
    skills_qa: bool = field(default_factory=lambda: _env_bool("SKILLS_QA", True))
    skills_dev: bool = field(default_factory=lambda: _env_bool("SKILLS_DEV", True))
    skills_dir: Path = field(default_factory=_default_skills_dir)
    # Decomposition build mode (SK-2): split a non-trivial backend story into
    # layered sub-tasks (entity → repo → service → endpoint → tests), each built
    # by a focused subagent (tiny context window) via the parallel worktree
    # engine, then aggregated. Reuses the streams Task/worktree machinery. OFF by
    # default; turning it on routes eligible stories through the streams path.
    decompose_enabled: bool = field(default_factory=lambda: _env_bool("DECOMPOSE", False))
    # Adaptive split-on-failure: when a story/task can't be made green after its
    # dev attempts are exhausted, re-analyze it and split it into FINER sub-tasks
    # (smaller scope + finer tests) instead of failing — counters the "unit too
    # big for one agent session" problem. ON by default (it's pure recovery);
    # bounded by split_max_depth so it can never recurse forever.
    split_on_failure_enabled: bool = field(
        default_factory=lambda: _env_bool("SPLIT_ON_FAILURE", True)
    )
    # Depth 2 (not 1) so a task extracted into a Technical Story can itself be
    # re-split once — the "arbitrary depth via TS chains" of RFC technical-stories
    # is otherwise cut off at the first level.
    split_max_depth: int = field(
        default_factory=lambda: _env_int("SPLIT_MAX_DEPTH", 2, minimum=0)
    )
    # The ONE sizing budget (RFC technical-stories + PO pipeline §5, shared
    # "découpe" brain): max files a LEAF (task / taskless story) may touch to
    # stay buildable in one average-LLM session. Indicative for the reactive
    # architect splits; a hard S1 reject for the PO pipeline's estimated_files.
    task_file_budget: int = field(
        default_factory=lambda: _env_int("TASK_FILE_BUDGET", 3, minimum=1)
    )
    # P4: LLM "independence judge" (skill task-independence + persona
    # independence-judge). When on, before the parallel build it completes each
    # task's file claims and refines independent/serialize/merge decisions on top
    # of the deterministic floor (orchestrator/independence.py). OFF by default:
    # the deterministic floor + prompt-declared file_globs already keep the build
    # safe; the judge only sharpens parallelism. Non-fatal when it fails.
    independence_enabled: bool = field(
        default_factory=lambda: _env_bool("INDEPENDENCE", False)
    )
    setup_install: bool = field(
        default_factory=lambda: _env_bool("SETUP_INSTALL", False)
    )
    node_cmd: str = field(default_factory=lambda: os.environ.get("NODE_CMD", "node"))
    npm_cmd: str = field(default_factory=lambda: os.environ.get("NPM_CMD", "npm"))
    # Claude usage-window watchdog (M2): when the Claude harness reports an
    # exhausted usage window, schedule an automatic resume when a fresh session
    # opens. Reset time read from the CLI error, else from ccusage's active
    # billing block, else now + fallback. Only active for the claude provider.
    session_monitor_enabled: bool = field(
        default_factory=lambda: _env_bool("SESSION_MONITOR", True)
    )
    ccusage_cmd: str = field(
        default_factory=lambda: os.environ.get("CCUSAGE_CMD", "npx --yes ccusage")
    )
    resume_fallback_min: float = field(
        default_factory=lambda: _env_float("RESUME_FALLBACK_MIN", 60.0, minimum=1.0)
    )
    # Tech-writer phase after each build (README + launch instructions for the
    # GENERATED project). OFF by default; also triggerable via POST /document.
    tech_writer_enabled: bool = field(
        default_factory=lambda: _env_bool("TECH_WRITER", False)
    )
    # Playwright UI acceptance tests for UI-flagged stories. Requires browsers
    # installed in the workspace venv; OFF by default.
    ui_tests_enabled: bool = field(
        default_factory=lambda: _env_bool("UI_TESTS", False)
    )
    # Closed-loop product evaluator (E6): after each delivered iteration (before
    # the analyze phase) an agent actually exercises the generated product and
    # turns the run into structured findings, fed into the feedback-impact
    # pipeline. OFF by default; also triggerable via POST /evaluate.
    evaluator_enabled: bool = field(
        default_factory=lambda: _env_bool("EVALUATOR", False)
    )
    # Wall-clock cap on the untrusted `main.py` run the evaluator observes. A
    # long-running server simply hits this timeout (we keep its startup output).
    evaluator_run_timeout_s: float = field(
        default_factory=lambda: _env_float("EVALUATOR_RUN_TIMEOUT_S", 20.0, minimum=1.0)
    )
    # Security & supply-chain review (S1): after each build, an agent audits the
    # generated code and runs pip-audit/npm audit on its dependencies, emitting
    # security Findings into the feedback-impact pipeline. OFF by default; also
    # triggerable via POST /security-review.
    security_review_enabled: bool = field(
        default_factory=lambda: _env_bool("SECURITY_REVIEW", False)
    )
    security_audit_timeout_s: float = field(
        default_factory=lambda: _env_float("SECURITY_AUDIT_TIMEOUT_S", 60.0, minimum=1.0)
    )
    # Optional Langfuse tracing of every agent call (O1): one generation per call
    # (phase, project, model, tokens, cost, duration). OFF by default; needs the
    # `langfuse` package + LANGFUSE_* env vars. Lazily imported, no-op when
    # unavailable — never affects the pipeline.
    langfuse_enabled: bool = field(
        default_factory=lambda: _env_bool("LANGFUSE", False)
    )
    # Mutation testing (Q1): after a story turns green, mutate the package source
    # one point at a time and rerun the suite against each mutant to score test
    # robustness (kill rate). OFF by default (it reruns pytest per mutant).
    mutation_enabled: bool = field(
        default_factory=lambda: _env_bool("MUTATION", False)
    )
    mutation_max_mutants: int = field(
        default_factory=lambda: _env_int("MUTATION_MAX", 30, minimum=1)
    )
    # Coverage gate (Q2): run the suite under coverage after a story turns green,
    # recording the total %% on story.coverage_score (badge). With a gate
    # threshold > 0, a story below it is rejected (kept red) instead of done.
    coverage_enabled: bool = field(
        default_factory=lambda: _env_bool("COVERAGE", False)
    )
    coverage_gate_threshold: int = field(
        default_factory=lambda: _env_int("COVERAGE_GATE", 0, minimum=0)
    )
    # Granular approval gates (U4): when on, the pipeline blocks after planning
    # (plan + architecture) and waits for explicit human approval before building.
    approval_gates_enabled: bool = field(
        default_factory=lambda: _env_bool("APPROVAL_GATES", False)
    )
    # Smoke-run gate: after the suite is green, actually BOOT the delivered app
    # and require it to start (a web/API app must open its port; a CLI must exit
    # 0) — a non-runnable build then fails the iteration like a red test. ON by
    # default for generated apps; the library-fast profile disables it.
    smoke_run: bool = field(
        default_factory=lambda: _env_bool("SMOKE_RUN", True)
    )
    smoke_run_timeout_s: float = field(
        default_factory=lambda: _env_float("SMOKE_RUN_TIMEOUT_S", 60.0, minimum=5.0)
    )
    smoke_run_port: int = field(
        default_factory=lambda: _env_int("SMOKE_RUN_PORT", 8000, minimum=1)
    )
    # Untrusted-code sandbox (R1): run the generated app inside a no-network
    # Docker container. OFF by default; needs Docker + an image carrying the
    # project toolchain (uv). The image/binary are configurable.
    sandbox_enabled: bool = field(
        default_factory=lambda: _env_bool("SANDBOX", False)
    )
    sandbox_image: str = field(
        default_factory=lambda: os.environ.get("SANDBOX_IMAGE", "python:3.12-slim")
    )
    docker_cmd: str = field(
        default_factory=lambda: os.environ.get("DOCKER_CMD", "docker")
    )
    # Docker delivery gate: after the delivery gates pass, build each web-facing
    # project into a Docker image and deploy it to local Docker Desktop on a
    # shared network (autospec-net), then verify boot health + cross-container
    # reachability. OFF by default (requires Docker Desktop); driven by profile
    # overrides and this env var. Reuses docker_cmd and integration_fix_attempts.
    docker_delivery: bool = field(
        default_factory=lambda: _env_bool("DOCKER_DELIVERY", False)
    )
    docker_network: str = field(
        default_factory=lambda: os.environ.get("DOCKER_NETWORK", "autospec-net")
    )
    docker_build_timeout_s: float = field(
        default_factory=lambda: _env_float("DOCKER_BUILD_TIMEOUT_S", 600.0, minimum=30.0)
    )
    # Health-wait window after the container starts.
    docker_deploy_timeout_s: float = field(
        default_factory=lambda: _env_float("DOCKER_DEPLOY_TIMEOUT_S", 60.0, minimum=5.0)
    )
    # Base of the stable host-port range assigned to deployed containers.
    docker_host_port_base: int = field(
        default_factory=lambda: _env_int("DOCKER_HOST_PORT_BASE", 18000, minimum=1024)
    )
    # Cross-project lesson library (F1): promote E7 lessons to a shared store
    # injected into every new project's Dev/QA prompts. OFF by default.
    shared_lessons_enabled: bool = field(
        default_factory=lambda: _env_bool("SHARED_LESSONS", False)
    )
    shared_lessons_max: int = field(
        default_factory=lambda: _env_int("SHARED_LESSONS_MAX", 20, minimum=1)
    )
    # Factory retrospective (E7): a meta-learning agent runs between iterations,
    # mines the collected build signals (attempts, red→green, refine scores,
    # cost) and produces durable lessons injected into the QA/Dev prompts plus
    # tuning recommendations. OFF by default; also triggerable via POST /retro.
    retro_enabled: bool = field(
        default_factory=lambda: _env_bool("RETRO", False)
    )
    # Cap on the durable lessons carried across iterations (bounds prompt growth).
    retro_max_lessons: int = field(
        default_factory=lambda: _env_int("RETRO_MAX_LESSONS", 12, minimum=1)
    )
    refine_enabled: bool = field(default_factory=lambda: _env_bool("REFINE", False))
    refine_po: bool = field(default_factory=lambda: _env_bool("REFINE_PO", True))
    refine_dev: bool = field(default_factory=lambda: _env_bool("REFINE_DEV", True))
    # Plan review (critic→judge→revise on the PO's epics/US/tasks): a dedicated
    # toggle so the plan can be reviewed/right-sized WITHOUT enabling the more
    # expensive code refinement. Independent of the master `REFINE`.
    # Reviews the breakdown, task complexity and "is each unit small enough for
    # ONE agent session" — proactively, before the build (complement to the
    # reactive split-on-failure). OFF by default.
    review_plan_enabled: bool = field(
        default_factory=lambda: _env_bool("REVIEW_PLAN", False)
    )
    # PO pipeline (RFC po-pipeline-v2): the multi-stage PO — S1 structure +
    # complexity, S2 per-story specs (resize barrier + cross critic), S3 gherkin.
    # "off" (default) keeps the legacy mono-pass PO byte-identical; "on" runs
    # S1 always, then a deterministic post-S1 decision on the measured skeleton
    # size: < min_leaves → S2+S3 merged into one pass per story, else the full
    # pipeline. No brief-length "auto" mode (a poor proxy, dropped in v2).
    po_pipeline: str = field(
        default_factory=lambda: (
            os.environ.get("PO_PIPELINE", "off").strip().lower()
        )
    )
    po_pipeline_min_leaves: int = field(
        default_factory=lambda: _env_int("PO_PIPELINE_MIN_LEAVES", 4, minimum=1)
    )
    po_pipeline_gherkin: bool = field(
        default_factory=lambda: _env_bool("PO_PIPELINE_GHERKIN", True)
    )
    # Canari post-merge : rejoue la vraie suite sur le HEAD partagé juste après
    # chaque merge d'item parallèle — deux items verts chacun dans leur worktree
    # peuvent être ROUGES combinés (conflit sémantique). Un HEAD rouge est
    # immédiatement reverté et l'item re-queué. ON par défaut (l'invariant
    # « HEAD toujours vert » protège tous les items suivants) ; coupable via
    # POST_MERGE_CANARY=0 si le coût d'une suite par merge est trop haut.
    post_merge_canary: bool = field(
        default_factory=lambda: _env_bool("POST_MERGE_CANARY", True)
    )
    refine_max_rounds: int = field(
        default_factory=lambda: _env_int("REFINE_MAX_ROUNDS", 2, minimum=0)
    )
    refine_quality_threshold: int = field(
        default_factory=lambda: _env_int("REFINE_QUALITY_THRESHOLD", 80, minimum=0)
    )
    # Delivery gates: the deterministic Definition-of-Done check is ON by
    # default in production so a green subset of tests cannot mark an incomplete
    # project as delivered. Strict per-criterion evidence is opt-in because very
    # small Gherkin-only stories are still valid in the existing pipeline.
    definition_of_done_enabled: bool = field(
        default_factory=lambda: _env_bool("DEFINITION_OF_DONE", True)
    )
    # P5 — partial delivery (principle « progrès partiel = succès partiel »):
    # when ≥1 story is DONE, stories that FAILED downgrade from blockers to
    # warnings — the project ships what is green instead of appearing entirely
    # failed (C9). Unfinished items (todo/in-progress) still block, and a
    # delivery with ZERO done story stays blocked. The failed stories remain
    # visible (FAILED + delivery warnings) and retryable.
    partial_delivery_enabled: bool = field(
        default_factory=lambda: _env_bool("PARTIAL_DELIVERY", False)
    )
    # Infra vs dev attempts: a transient provider/CLI failure (AgentError that
    # is not a usage-limit) is NOT a dev failure — it refunds the dev attempt
    # and consumes this separate budget instead, so infra flakiness alone can
    # never FAIL an item (nor pollute the sizing calibration).
    infra_max_retries: int = field(
        default_factory=lambda: _env_int("INFRA_MAX_RETRIES", 3, minimum=0)
    )
    definition_of_done_strict_criteria: bool = field(
        default_factory=lambda: _env_bool("DOD_STRICT_CRITERIA", False)
    )
    # ON by default: every delivered web/fullstack build must pass the full
    # integration check (backend serving the built frontend, assets, API, DB
    # wiring) before shipping — a green unit suite alone proved able to ship a
    # blank page (messagerie2). `should_run` still auto-skips CLI/library
    # projects and demo mode, and profiles keep their explicit overrides.
    runtime_acceptance_enabled: bool = field(
        default_factory=lambda: _env_bool("RUNTIME_ACCEPTANCE", True)
    )
    runtime_acceptance_timeout_s: float = field(
        default_factory=lambda: _env_float("RUNTIME_ACCEPTANCE_TIMEOUT_S", 90.0, minimum=10.0)
    )
    # When a delivery gate (smoke run / runtime integration) fails, dispatch a
    # Dev agent with the failure report and re-run the gate, up to this many
    # attempts, before parking the project in needs_attention. 0 disables the
    # repair loop (a failing gate then blocks immediately, as before).
    integration_fix_attempts: int = field(
        default_factory=lambda: _env_int("INTEGRATION_FIX_ATTEMPTS", 2, minimum=0)
    )

    def __post_init__(self) -> None:
        # W0.1: named quality preset applied at construction. ``PRESET=verified``
        # turns ON the full existing verification gauntlet (refine, plan review,
        # coverage, mutation, evaluator, security review, runtime acceptance,
        # strict Definition-of-Done) so the "verified swarm" baseline is one flag
        # instead of eight. A preset is a QUALITY overlay, orthogonal to the
        # product-shape profiles; it never overrides a gate the operator set
        # explicitly via that gate's own env var.
        preset = os.environ.get("PRESET", "").strip().lower()
        if preset == "verified":
            self._apply_verified_preset()

    def _apply_verified_preset(self) -> None:
        gauntlet = [
            ("REFINE", "refine_enabled"),
            ("REVIEW_PLAN", "review_plan_enabled"),
            ("COVERAGE", "coverage_enabled"),
            ("MUTATION", "mutation_enabled"),
            ("EVALUATOR", "evaluator_enabled"),
            ("SECURITY_REVIEW", "security_review_enabled"),
            ("RUNTIME_ACCEPTANCE", "runtime_acceptance_enabled"),
            ("DEFINITION_OF_DONE", "definition_of_done_enabled"),
            ("DOD_STRICT_CRITERIA", "definition_of_done_strict_criteria"),
        ]
        for env_name, attr in gauntlet:
            # Override .env defaults, but respect a deliberate SHELL choice: only
            # a gate the operator pinned in their shell (not merely in .env) is
            # left untouched. Everything else the preset turns on.
            if env_name not in _SHELL_ENV_KEYS:
                setattr(self, attr, True)
        # W0.5: the anti-cheating guards default to observe-first (warn); flaky
        # rerun on. Same shell-respect rule.
        for env_name, attr in (
            ("TEST_TAMPER_GUARD", "test_tamper_guard"),
            ("SCOPE_GUARD", "scope_guard"),
            ("SKELETON_GUARD", "skeleton_guard"),
            ("IMPORT_GUARD", "import_guard"),
        ):
            if env_name not in _SHELL_ENV_KEYS:
                setattr(self, attr, "warn")
        if "FLAKY_RERUN" not in _SHELL_ENV_KEYS:
            self.flaky_rerun_enabled = True

    def preset_active(self) -> str:
        """The active quality preset name ("" when none) — for UI/telemetry."""
        return os.environ.get("PRESET", "").strip().lower()

    def po_pipeline_on(self) -> bool:
        """Is the multi-stage PO pipeline active? Anything but the explicit
        "on" (including a malformed value) is OFF — the legacy mono-pass PO
        must stay the safe default."""
        return self.po_pipeline == "on"

    def refine_for(self, role: str) -> bool:
        """Is the refinement loop active for this maker role ('po' / 'dev')?

        The PO plan review has a dedicated switch (`REVIEW_PLAN`) that
        turns it on independently of the master `REFINE`, so an operator
        can right-size the breakdown without paying for code refinement."""
        if role == "po" and self.review_plan_enabled:
            return True
        return self.refine_enabled and bool(getattr(self, f"refine_{role}", True))

    def skills_for(self, role: str) -> bool:
        """Are skills active for this agent role ('qa' / 'dev')? Master flag AND
        the per-role flag, mirroring ``refine_for``."""
        return self.skills_enabled and bool(getattr(self, f"skills_{role}", True))

    def model_for_phase(self, phase: str) -> str | None:
        """Model to use for a given pipeline phase (M3): the per-phase override
        if set, else the global claude_model — but only for the Claude Code CLI
        harness: the other runners pick their model from their own settings, so
        a Claude model id must not leak into their calls."""
        override = self.phase_models.get(phase)
        if override:
            return override
        if self.agent_provider in ("", "claude code"):
            return self.claude_model
        return None

    def tier_for_role(self, role: str) -> str:
        """The cost tier ("boss"|"worker"|"checker") for an agent persona, or ""
        when the role is unmapped."""
        return PERSONA_TIERS.get(role, "")

    def model_for_role(self, role: str, phase: str) -> str | None:
        """W4: resolve a call's model by the agent's cost tier, falling back to the
        per-phase router. Enforces "boss never codes": in the BUILD phase a
        dev/dev-frontend call can never resolve to the boss-tier model — if a
        misconfiguration points it there, it falls back to the worker tier (or the
        phase router). No-op (== ``model_for_phase``) when role routing is off."""
        if not self.role_routing_enabled:
            return self.model_for_phase(phase)
        tier = PERSONA_TIERS.get(role, "")
        if role in ("dev", "dev-frontend") and phase == "build":
            tier = "worker"  # boss never codes, regardless of the map
        model = self.model_tiers.get(tier) if tier else None
        if model:
            # Guard: a coding call must not run on the boss model.
            if phase == "build" and role in ("dev", "dev-frontend"):
                boss = self.model_tiers.get("boss")
                if boss and model == boss:
                    logger.warning("Refusing boss model %s for a build dev call; "
                                   "falling back to the phase router.", model)
                    return self.model_for_phase(phase)
            return model
        return self.model_for_phase(phase)

    def persona_path(self, agent: str) -> Path:
        return self.bmad_dir / "bmm" / "agents" / f"{agent}.md"


settings = Settings()
