"""The Autospec pipeline: PM (spec) -> PO (plan) -> Dev agents (BDD/TDD build).

One Pipeline instance per project. The whole lifecycle runs as a background
asyncio task; the API talks to it through asend_user_message / astop / arun_app.
"""

from __future__ import annotations

import asyncio
import contextvars
import copy
import fnmatch
import json
import os
import re
import shlex
import shutil
import subprocess
import time
from pathlib import Path

from ..agents import prompts
from ..agents.providers import provider_capabilities, provider_model
from ..agents.runner import (
    AgentError,
    AgentRunner,
    ProcessRegistry,
    active_processes,
    active_skills_enabled,
    extract_json,
)
from ..agents.personas import FALLBACK_PERSONAS, persona
from ..config import settings
from .. import observability
from ..models import (
    AcceptanceCriterion,
    AgentInteraction,
    BackendLanguage,
    BuildStage,
    ChatMessage,
    ChatRole,
    Component,
    ComponentStatus,
    DEFAULT_STREAM_CATALOG,
    Epic,
    FeatureHypothesis,
    Finding,
    GuidanceEntry,
    HypothesisStatus,
    PipelinePhase,
    PlannedTest,
    ProjectState,
    RecoveryState,
    Stream,
    StreamKind,
    StoryStatus,
    Task,
    TestState,
    Usage,
    UserStory,
    backend_stream_for,
    new_id,
)
from ..language_selector import recommend_language
from ..storage import append_interaction, force_delete_workspace, load_interactions, save_state_payload, workspace_dir
from .interactions import InteractionStore
from . import delivery_state, independence, mutation, profiles, refine, runtime_acceptance, scheduler, session_monitor, setup_exec, skill_validation, skills as skill_lib, streams as work_streams, toolchain, workspace
from . import guards, signatures  # W0.5 anti-cheating detectors + failure signatures
from . import recovery  # W1 recovery state machine + escalation ladder
from . import arbitration, traceability  # W2 wrong-test arbitration + AC traceability
from . import constitution as constitution_lib  # W3 project constitution
from . import amendment  # W5.1 human-gated design amendment
from .delivery_gate import evaluate_definition_of_done
from . import lessons as lesson_store
from . import manifests
from . import plan_pipeline
from . import regression
from .build_monitor import BuildMonitor
from . import deploy
from . import docker_deploy
from . import brownfield
from . import sandbox
from .events import bus

_REFINE_ROLE_TO_CHAT = {"critic": ChatRole.CRITIC, "judge": ChatRole.JUDGE}

# State checkpoints are written off the event loop (BUG2): save_state does
# blocking file I/O plus a retry sleep on Windows lock contention, and _sync()
# fires on every state change during a build. Running it inline starves
# uvicorn's accept loop, so the Vite proxy sees ETIMEDOUT on /api/*. A single
# worker keeps writes FIFO so an older snapshot can never clobber a newer one.
from concurrent.futures import ThreadPoolExecutor  # noqa: E402

_PERSIST_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="autospec-persist")

# OS essentials needed to launch a process, WITHOUT inheriting application
# secrets (API keys, tokens…). Used when running the UNTRUSTED generated app.
_SAFE_ENV_KEYS = {
    "PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC",
    "TEMP", "TMP", "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "HOME",
    "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "PROGRAMFILES",
    "PROGRAMFILES(X86)", "NUMBER_OF_PROCESSORS", "OS",
    "PROCESSOR_ARCHITECTURE", "LANG", "LC_ALL", "USER",
}


def _minimal_env() -> dict[str, str]:
    """Environment for running the untrusted generated app: OS essentials only,
    so the agent-written code never inherits the server's secrets."""
    env = {k: v for k, v in os.environ.items() if k.upper() in _SAFE_ENV_KEYS}
    # Force the untrusted child's stdio to UTF-8 (BUG1): on Windows the child
    # Python's stdout defaults to cp1252 (locale-derived), so a generated
    # main.py that prints non-ASCII (accents, arrows…) either crashes with
    # UnicodeEncodeError or emits cp1252 bytes we then mis-read as utf-8
    # (mojibake). Setting these makes the child write utf-8, consistent with our
    # encoding="utf-8" stream readers. Covers _aexercise_product (E6 evaluator)
    # and _stream_run_output ("Lancer le projet").
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


class _OwnedLock:
    """B6 (UX): a thin wrapper over ``asyncio.Lock`` that records WHICH work item
    currently holds it. Additive and drop-in: it supports ``async with`` exactly
    like a bare lock (existing ``async with self._merge_lock:`` sites keep working
    with ``owner`` left as ""), and a caller that wants the merge_wait/stall
    signal acquires it via ``self._merge_lock.ahold(item_id)``. ``owner`` powers
    the tick's ``stall_reason`` (``merge_lock_held:US-3``) and the per-item
    ``merge_wait`` ring."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self.owner: str = ""

    def locked(self) -> bool:
        return self._lock.locked()

    def ahold(self, owner: str):
        """Acquire the lock as an async-context-manager, stamping ``owner`` for
        the duration of the held section (restored on exit)."""
        return _OwnedLockCtx(self, owner)

    async def __aenter__(self):
        await self._lock.acquire()
        return self

    async def __aexit__(self, *exc):
        self._lock.release()
        return False


class _OwnedLockCtx:
    """The context object returned by ``_OwnedLock.ahold(owner)``."""

    def __init__(self, lock: "_OwnedLock", owner: str) -> None:
        self._lock = lock
        self._owner = owner

    async def __aenter__(self):
        await self._lock._lock.acquire()
        self._lock.owner = self._owner
        return self._lock

    async def __aexit__(self, *exc):
        self._lock.owner = ""
        self._lock._lock.release()
        return False


def _clamp_1_5(value, default: int = 3) -> int:
    """Coerce a 1..5 score (priority/value/complexity), tolerating garbage
    from agent replies (non-numeric -> default)."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return min(5, max(1, n))


# Files any dev work legitimately produces alongside its scope: per-story test
# and feature collateral (named after the story, siblings almost never collide).
_SCOPE_ALLOWED_PREFIXES = ("tests/", "features/")


def _file_in_scope(path: str, globs: list[str], zone: str) -> bool:
    """Is a repo-relative file within a work item's declared scope? In scope:
    it matches a declared glob (or lives under a directory glob), lives under
    the item's stream zone, or is test/feature collateral. Everything else —
    typically a shared entry-point/config file — is a conflict seed."""
    p = path.strip().replace("\\", "/").lstrip("./")
    if any(p.startswith(pre) for pre in _SCOPE_ALLOWED_PREFIXES):
        return True
    if ".test." in p.rsplit("/", 1)[-1]:
        return True  # colocated vitest file next to its component
    if zone and (p == zone or p.startswith(zone.rstrip("/") + "/")):
        return True
    for g in globs:
        g_norm = str(g).strip().replace("\\", "/").lstrip("./")
        if not g_norm:
            continue
        if fnmatch.fnmatch(p, g_norm):
            return True
        if g_norm.endswith("/") and p.startswith(g_norm):
            return True  # a directory-prefix glob covers its whole subtree
    return False


def _acceptance_list(raw) -> list[AcceptanceCriterion]:
    """Parse a plan's acceptance criteria. Legacy plans carry plain strings
    (ids generated AC-1..n); the PO pipeline carries dicts {id, text, kind} —
    their ids are PRESERVED because the S3 gherkin scenarios tag them."""
    out: list[AcceptanceCriterion] = []
    for i, entry in enumerate(raw or [], start=1):
        if isinstance(entry, dict):
            out.append(
                AcceptanceCriterion(
                    id=str(entry.get("id") or f"AC-{i}"),
                    text=str(entry.get("text") or ""),
                    kind=str(entry.get("kind") or ""),
                )
            )
        else:
            out.append(AcceptanceCriterion(id=f"AC-{i}", text=str(entry)))
    return out


def _unique_id(raw: str, prefix: str, taken: set[str]) -> str:
    """Return ``raw`` if free, else the first unused ``{prefix}-{n}`` id."""
    if raw not in taken:
        return raw
    n = len(taken) + 1
    while f"{prefix}-{n}" in taken:
        n += 1
    return f"{prefix}-{n}"


# The work item (user story / task id) the current agent call belongs to. Set by
# each build worker at its entry; read in ``_UsageTracker.arun`` to attribute the
# captured interaction. Each build worker runs in its own asyncio Task (which
# copies the context at creation), so a bare ``set()`` is isolated to that worker
# — it never leaks to sibling workers or to the parent lifecycle task. Unset (the
# default) means "not a build call" → attributed to the phase.
_BUILD_ITEM: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "autospec_build_item", default=None
)

# W1: a forced model id for the current build worker's calls (the escalation
# ladder sets it on a retry). Read in ``_UsageTracker.arun`` with precedence
# below an explicit per-call ``model`` arg but above the phase/role router. Set
# per build worker (own Task context, like _BUILD_ITEM), so it never leaks to
# siblings or planning-phase calls. None = no override.
_FORCE_MODEL: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "autospec_force_model", default=None
)

# Reverse map: the exact system-prompt string ``persona(name)`` returns → the
# persona name. Lets ``_UsageTracker`` label every call's agent role without
# touching the ~25 call sites. Built lazily (personas are lru_cached, so the same
# string object/content comes back each time).
_PERSONA_BY_PROMPT: dict[str, str] = {}


class DeliveryBlocked(Exception):
    """A product gate failed; this is actionable delivery work, not a crash."""


def _dep_top_name(spec: str) -> str:
    """Top-level distribution name from a dependency spec line
    (``fastapi>=0.110`` → ``fastapi``; ``uvicorn[standard]`` → ``uvicorn``).
    Underscored so it matches import names (``ruamel.yaml`` → ``ruamel``)."""
    s = spec.strip()
    for sep in (";", "@", " ", "=", ">", "<", "!", "~", "[", "("):
        idx = s.find(sep)
        if idx != -1:
            s = s[:idx]
    return s.strip().replace("-", "_").split(".")[0].lower()


def prompts_arbiter_fix_test(story, pkg: str, acceptance: str, instructions: str, test_blob: str) -> str:
    """W2.2 checker-tier prompt: correct the WRONG test to match the acceptance
    criteria, following the arbiter's instructions. The corrected test must still
    genuinely verify the behavior — never weaken coverage or delete assertions to
    force a pass; the executed rerun (not this reply) decides success."""
    return (
        "Un arbitre a jugé qu'un test en échec CONTREDIT les critères d'acceptance "
        f"de la story « {story.title} » (paquet {pkg}). Corrige le(s) test(s) "
        "concerné(s) dans le répertoire courant pour qu'ils vérifient ce que les "
        "critères exigent RÉELLEMENT — sans affaiblir la couverture, sans "
        "supprimer d'assertions pour forcer un vert, sans toucher au code de "
        "production.\n\n"
        f"Critères d'acceptance (vérité de référence) :\n{acceptance}\n\n"
        f"Instructions de l'arbitre (ce que le test DOIT affirmer) :\n{instructions}\n\n"
        f"Tests actuels :\n{test_blob[:6000]}\n\n"
        "NE MODIFIE JAMAIS les fichiers sous tests/constitution/ (règles "
        "non-négociables du projet). "
        "Édite les fichiers de test nécessaires, puis réponds avec un court JSON "
        '{\"summary\": \"...\"}.'
    )


def _persona_role(system_prompt: str) -> str:
    if not _PERSONA_BY_PROMPT:
        for name in FALLBACK_PERSONAS:
            _PERSONA_BY_PROMPT[persona(name)] = name
    return _PERSONA_BY_PROMPT.get(system_prompt, "")


class _UsageTracker:
    """Wraps a pipeline's runner to accumulate token/cost usage on the project
    state. Its `arun` matches the AgentRunner Protocol, so it can be passed to
    `refine.arefine` to also count critic/judge/revise calls."""

    def __init__(self, pipeline: "Pipeline"):
        self.pipeline = pipeline

    async def arun(self, prompt, system_prompt, cwd=None, session_id=None, model=None):
        phase = self.pipeline.state.phase.value
        item_id = _BUILD_ITEM.get() or f"phase:{phase}"
        role = _persona_role(system_prompt)
        # Track this call's CLI child process on the pipeline's registry so a
        # project switch / shutdown can kill it mid-flight. to_thread copies this
        # context into the worker thread where the process is actually spawned.
        active_processes.set(self.pipeline._agent_procs)
        skills_token = active_skills_enabled.set(bool(self.pipeline._setting("skills_enabled")))
        _t0 = time.monotonic()
        # W0.3/W0.4: resolve the model once (so both success and error telemetry
        # can attribute it) and record the prompt size for context-budget checks.
        # Precedence: explicit per-call model > escalation-ladder force >
        # role/tier router (W4) which itself falls back to the per-phase router.
        chosen = model or _FORCE_MODEL.get() or settings.model_for_role(role, phase)
        prompt_chars = len(prompt or "")
        self.pipeline._check_context_budget(role, item_id, prompt_chars, chosen)
        try:
            res = await self.pipeline.runner.arun(
                prompt, system_prompt, cwd=cwd, session_id=session_id, model=chosen
            )
        except AgentError as exc:
            # Capture the failed round-trip too — a red/failed item's last call is
            # exactly what the operator wants to inspect.
            self.pipeline._record_interaction(
                item_id=item_id, phase=phase, persona=role, prompt=prompt,
                response="", ok=False, error=str(exc), model=chosen or "",
            )
            self.pipeline.monitor.agent_call(
                role=role, item_id=item_id,
                duration_ms=(time.monotonic() - _t0) * 1000,
                ok=False, error=str(exc), model=chosen or "", prompt_chars=prompt_chars,
            )
            # Usage-window watchdog (M2): an exhausted Claude session window
            # triggers a clean stop + scheduled auto-resume, then the error
            # still propagates to the caller's normal handling.
            await self.pipeline._aon_agent_error(exc)
            raise
        finally:
            active_skills_enabled.reset(skills_token)
        usage = self.pipeline.state.usage
        usage.cost_usd += res.cost_usd
        usage.input_tokens += res.input_tokens
        usage.output_tokens += res.output_tokens
        usage.agent_calls += 1
        # W4: per-tier cost ledger. Attribute this call's tokens/cost to its cost
        # tier (boss/worker/checker). When the runner reports no cost (Codex/
        # OpenAI/Ollama), estimate it from the tier's configured per-1M prices so
        # the "$X on the meter" story holds across providers.
        tier = settings.tier_for_role(role) or "unrouted"
        tier_cost = res.cost_usd
        if tier_cost <= 0.0:
            tier_cost = (
                res.input_tokens / 1_000_000 * settings.tier_price_in.get(tier, 0.0)
                + res.output_tokens / 1_000_000 * settings.tier_price_out.get(tier, 0.0)
            )
            usage.cost_usd += tier_cost  # fold the estimate into the headline total too
        usage.cost_by_tier[tier] = usage.cost_by_tier.get(tier, 0.0) + tier_cost
        usage.input_tokens_by_tier[tier] = usage.input_tokens_by_tier.get(tier, 0) + res.input_tokens
        usage.output_tokens_by_tier[tier] = usage.output_tokens_by_tier.get(tier, 0) + res.output_tokens
        usage.calls_by_tier[tier] = usage.calls_by_tier.get(tier, 0) + 1
        # Per-iteration breakdown: mirror the same deltas into this iteration's
        # bucket (created on first use) so the UI can show cost/tokens per iteration.
        it_usage = self.pipeline.state.iteration_usage.setdefault(
            self.pipeline.state.iteration, Usage()
        )
        it_usage.cost_usd += res.cost_usd
        it_usage.input_tokens += res.input_tokens
        it_usage.output_tokens += res.output_tokens
        it_usage.agent_calls += 1
        # Optional Langfuse trace (O1): one generation per agent call. Best-effort
        # and env-gated — never affects the pipeline if tracing fails or is off.
        observability.trace_agent_call(
            name=f"agent:{self.pipeline.state.phase.value}",
            model=provider_model(settings.agent_provider) or settings.agent_provider,
            input_text=prompt,
            output_text=res.text,
            metadata={
                "project_id": self.pipeline.state.id,
                "project": self.pipeline.state.name,
                "phase": self.pipeline.state.phase.value,
                "provider": settings.agent_provider,
                "session_id": res.session_id,
            },
            cost_usd=res.cost_usd,
            input_tokens=res.input_tokens,
            output_tokens=res.output_tokens,
            duration_ms=res.duration_ms,
        )
        # Capture the round-trip for the live item-activity view (O2).
        self.pipeline._record_interaction(
            item_id=item_id, phase=phase, persona=role, prompt=prompt,
            response=res.text, ok=True, model=chosen or "",
            input_tokens=res.input_tokens, output_tokens=res.output_tokens,
            cost_usd=res.cost_usd, duration_ms=res.duration_ms,
        )
        self.pipeline.monitor.agent_call(
            role=role, item_id=item_id,
            duration_ms=res.duration_ms or (time.monotonic() - _t0) * 1000,
            ok=True, in_tokens=res.input_tokens, out_tokens=res.output_tokens,
            model=chosen or "", prompt_chars=prompt_chars,
        )
        self.pipeline._sync()  # persist + broadcast usage as it accrues
        return res


class Pipeline:
    def __init__(self, state: ProjectState, runner: AgentRunner):
        self.state = state
        self.runner = runner
        self._tracked = _UsageTracker(self)
        self._profile_overrides: dict[str, bool] = profiles.resolve_overrides(self.state)
        # Build monitor (always on): persisted JSONL timeline for post-mortem
        # failure analysis — mirrors every _log line, test run and agent call.
        self.monitor = BuildMonitor(state)
        # O2: live capture of LLM round-trips per work item. Kept out of
        # ProjectState (prompts/answers are large); in-memory ring + JSONL sidecar.
        # Seed the ring from the sidecar so history survives a backend reload.
        self.interactions = InteractionStore(persist=self._persist_interaction)
        # Live agent CLI child processes, so an in-flight chat/dev call can be
        # truly interrupted (project switch / API shutdown), not just left to
        # finish. Populated per call by _UsageTracker (via the runner contextvar).
        self._agent_procs = ProcessRegistry()
        try:
            for rec in load_interactions(state.id):
                self.interactions.add_existing(AgentInteraction.model_validate(rec))
        except Exception:  # a corrupt sidecar must never block pipeline creation
            pass
        self._pm_session: str | None = None
        self._user_messages: asyncio.Queue[str] = asyncio.Queue()
        self._stop_requested = False
        # Séparation inter-stream : items re-queués après un CONFLIT DE MERGE.
        # Le scheduler les re-planifie en mode STRICT (claims_overlap, pas
        # seulement declared_overlap) tant qu'un rival potentiel est en vol —
        # un retry ne doit jamais pouvoir re-conflicter avec un item en cours.
        self._conflict_retry_ids: set[str] = set()
        # W2: wrong-test arbitrations spent per item this run (bounded by
        # settings.arbitration_max) — a loop of test rewrites would be checker erosion.
        self._arbitration_count: dict[str, int] = {}
        self._delivery_blocked = False
        self._resume_event = asyncio.Event()
        self._resume_event.set()  # set = running, cleared = paused
        self._task: asyncio.Task | None = None
        # Background side-tasks (feedback impact analysis, component setup):
        # strong refs, one at a time each.
        self._impact_task: asyncio.Task | None = None
        self._setup_task: asyncio.Task | None = None
        self._doc_task: asyncio.Task | None = None
        self._deploy_task: asyncio.Task | None = None  # D1 on-demand docker deploy
        self._eval_task: asyncio.Task | None = None   # E6 on-demand evaluation
        self._security_task: asyncio.Task | None = None  # S1 on-demand security review
        self._retro_task: asyncio.Task | None = None  # E7 on-demand retrospective
        self._resume_timer: asyncio.Task | None = None  # M2 scheduled auto-resume
        self._run_proc: subprocess.Popen | None = None
        # ST-8: frontend `vite preview` processes launched alongside the backend.
        self._frontend_procs: list[subprocess.Popen] = []
        # Strong ref to the app-output streaming task (asyncio keeps only weak
        # refs to tasks: an unreferenced task may be garbage-collected mid-run).
        self._stream_task: asyncio.Task | None = None
        # BUG9 : idem pour les previews frontend (ST-8) — chaque task de streaming
        # frontend doit être gardée en référence forte, sinon le GC peut la collecter
        # en plein vol.
        self._frontend_stream_tasks: list[asyncio.Task] = []
        # Serializes the workspace-mutating section of story builds. Parallel dev
        # workers share one workspace directory, so writing code, running the
        # whole pytest suite and committing/refining git must not interleave
        # (else pytest sees half-written trees and git stages the wrong files).
        self._build_lock = asyncio.Lock()
        # ST-10: builds run in parallel (each work item in its OWN git worktree),
        # but merges of those worktree branches back into the shared project repo
        # MUST be serialized — concurrent `git merge` into the same repo race on
        # the index/HEAD. The streams path holds this while merging + on a merge
        # conflict retry. The legacy path never uses it (it keeps _build_lock).
        # B6 (UX): owner-tracking wrapper so the tick can report who holds it
        # (``merge_lock_held:US-3``) and stamp the holder's ``merge_wait`` ring.
        self._merge_lock = _OwnedLock()
        # Serialize the one-time `npm install` of the frontend stream so parallel
        # frontend work items don't each kick off (or race) an install.
        self._npm_lock = asyncio.Lock()
        # Serialize every test-suite run that touches the SHARED workspace (the
        # post-merge canary, the smoke run, any verify with ws=None). Two such
        # runs racing on the shared `.venv` — each `uv run` may recreate it — can
        # leave it half-built (no pyvenv.cfg / no python.exe), after which every
        # subsequent `uv run` fails at launch and a green HEAD reads as red. Runs
        # in a per-item git WORKTREE are isolated (their own `.venv`) and never
        # take this lock, so parallel builds keep their concurrency.
        self._shared_suite_lock = asyncio.Lock()
        # P0a: untrack volatile bookkeeping files from the project repo exactly
        # once per process (idempotent `git rm --cached`); guarded by this flag so
        # the per-commit `_agit_ensure_repo` hot path stays cheap.
        self._bookkeeping_ignored = False
        # B5 (UX): heartbeat tick publisher, started on BUILD entry, cancelled on
        # stop/dispose. ~10s compact item-status broadcast (never replayed).
        self._tick_task: asyncio.Task | None = None
        # U4: cleared while the pipeline waits for human approval before build.
        self._approval_event = asyncio.Event()
        self._approval_event.set()
        # B-IDEA: set when the user resolves the brainstorming offer.
        self._brainstorm_event = asyncio.Event()
        self._brainstorm_accepted = False

    def _setting(self, name: str):
        """Read a setting with this pipeline's product-profile overrides applied."""
        if name in self._profile_overrides:
            return self._profile_overrides[name]
        return getattr(settings, name)

    def _check_context_budget(self, role: str, item_id: str, prompt_chars: int, model: str | None) -> None:
        """W0.4: context-budget telemetry. Silent truncation of an over-long prompt
        is a classic source of 'mysteriously dumb' agent behaviour that would
        otherwise burn escalation-ladder rungs (W1) on an unwinnable prompt. We do
        not truncate here — just flag when a prompt approaches the configured
        budget so it surfaces in the timeline. Best-effort; never raises."""
        try:
            budget = int(getattr(settings, "context_warn_chars", 0) or 0)
            if budget <= 0 or prompt_chars < budget:
                return
            approx_tokens = prompt_chars // 4  # coarse chars→tokens heuristic
            self.monitor.event(
                "context_budget", role=role or "?", item=item_id,
                prompt_chars=prompt_chars, approx_tokens=approx_tokens,
                model=model or "", budget_chars=budget,
            )
            self._log(
                f"ctx:{item_id}",
                f"⚠️ Prompt volumineux ({prompt_chars} car. ≈ {approx_tokens} tokens) "
                f"pour {role or '?'} — proche du budget de contexte.",
            )
        except Exception:
            return

    # ------------------------------------------------- W0.5 anti-cheating guards

    _GUARD_SKIP_SEGMENTS = frozenset(
        {".venv", "venv", "node_modules", ".git", "__pycache__", ".pytest_cache", "dist", "build"}
    )

    def _iter_ws_py_files(self, ws):
        """Yield (relposix, Path) for every .py file in the workspace, skipping
        vendored / build / VCS dirs. Best-effort; swallows FS errors."""
        root = Path(ws)
        try:
            for p in root.rglob("*.py"):
                rel = p.relative_to(root).as_posix()
                if self._GUARD_SKIP_SEGMENTS & set(rel.split("/")):
                    continue
                yield rel, p
        except OSError:
            return

    def _snapshot_test_files(self, ws) -> dict[str, bytes]:
        """W0.5-T05: capture the current bytes of every QA-authored test file, so
        a dev turn that mutates one can be detected (and, in strict mode, reverted)
        afterwards. Keyed by workspace-relative posix path. Test files are small
        and few, so keeping their content in memory is cheap."""
        snap: dict[str, bytes] = {}
        if settings.test_tamper_guard == "off":
            return snap
        for rel, p in self._iter_ws_py_files(ws):
            if guards.modified_test_files([rel], []):  # classifies rel as a test file
                try:
                    snap[rel] = p.read_bytes()
                except OSError:
                    continue
        return snap

    async def _achanged_paths(self, ws) -> list[str]:
        """Workspace paths changed since HEAD (best-effort, via git porcelain).
        Empty on any failure or non-repo — the guards then simply no-op."""
        try:
            code, out = await self._agit(ws, "status", "--porcelain")
        except Exception:
            return []
        if code != 0:
            return []
        paths: list[str] = []
        for line in (out or "").splitlines():
            entry = line[3:].strip() if len(line) > 3 else ""
            if not entry:
                continue
            if "->" in entry:  # rename: keep the destination
                entry = entry.split("->")[-1].strip()
            paths.append(entry.strip('"'))
        return paths

    async def _arun_cheat_guards(self, story, ws, tests_before: dict[str, bytes]) -> list[str]:
        """W0.5-HOOK: run the enabled anti-cheating / quality guards over the dev's
        just-produced changes. Returns the list of guard verdict signatures found
        (for the recovery machine / lessons). Warn mode = detect + log; strict mode
        = additionally revert tampered tests. Fully best-effort — a guard failure
        must never break a build."""
        findings: list[str] = []
        sid = getattr(story, "id", "?")

        def _record(verdict: str, detail: str, mode: str) -> None:
            findings.append(signatures.guard_signature(verdict, detail))
            self.monitor.event("guard", item=sid, verdict=verdict, detail=detail[:200], mode=mode)
            self._log(f"guard:{sid}", f"{'⛔' if mode == 'strict' else '⚠️'} {verdict}: {detail}")

        # --- T05 test tampering ------------------------------------------------
        mode = settings.test_tamper_guard
        if mode != "off" and tests_before:
            root = Path(ws)
            for rel, original in tests_before.items():
                p = root / rel
                try:
                    now = p.read_bytes() if p.exists() else None
                except OSError:
                    now = None
                if now != original:
                    _record(signatures.TAMPERED, rel, mode)
                    if mode == "strict":
                        try:  # restore the QA-authored test verbatim
                            p.parent.mkdir(parents=True, exist_ok=True)
                            p.write_bytes(original)
                            self._log(f"guard:{sid}", f"↩️ test restauré : {rel}")
                        except OSError:
                            pass

        # The scope/skeleton/import guards operate on the dev's changed files.
        need_changed = any(
            getattr(settings, attr) != "off"
            for attr in ("scope_guard", "skeleton_guard", "import_guard")
        )
        changed = await self._achanged_paths(ws) if need_changed else []
        changed_py = [c for c in changed if c.endswith(".py")]

        # --- T06 scope (declared file claims) ---------------------------------
        mode = settings.scope_guard
        if mode != "off" and changed:
            claims = self._story_file_claims(story)
            if claims:
                for rel in guards.out_of_scope_paths(changed, claims):
                    _record(signatures.OUT_OF_SCOPE, rel, mode)

        # --- T07 skeleton implementations -------------------------------------
        mode = settings.skeleton_guard
        if mode != "off":
            root = Path(ws)
            for rel in changed_py:
                if guards.modified_test_files([rel], []):
                    continue  # skeleton check targets implementation, not tests
                try:
                    src = (root / rel).read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                for issue in guards.detect_skeleton(src, rel):
                    _record(signatures.SKELETON, f"{rel}: {issue}", mode)

        # --- T10 hallucinated imports -----------------------------------------
        mode = settings.import_guard
        if mode != "off":
            deps = self._declared_deps(ws)
            local = self._local_modules(ws)
            stdlib = guards.default_stdlib()
            root = Path(ws)
            for rel in changed_py:
                try:
                    src = (root / rel).read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                for name in guards.unresolved_imports(src, deps, stdlib, local):
                    _record("unresolved_import", f"{rel}: {name}", mode)

        return findings

    def _story_file_claims(self, story) -> list[str]:
        """Declared file scope for a story: the stream's file_root when streams are
        on, else nothing (→ scope guard no-ops). Kept defensive."""
        try:
            if not self._setting("streams_enabled"):
                return []
            stream = self._story_stream(story)
            root = getattr(stream, "file_root", "") or ""
            return [root] if root else []
        except Exception:
            return []

    def _declared_deps(self, ws) -> set[str]:
        """Top-level distribution names declared in the workspace manifests
        (pyproject [project.dependencies] + requirements*.txt). Best-effort."""
        deps: set[str] = set()
        root = Path(ws)
        try:
            pyproject = root / "pyproject.toml"
            if pyproject.exists():
                import tomllib

                data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
                proj = data.get("project", {}) if isinstance(data, dict) else {}
                for spec in proj.get("dependencies", []) or []:
                    deps.add(_dep_top_name(str(spec)))
                for group in (proj.get("optional-dependencies", {}) or {}).values():
                    for spec in group or []:
                        deps.add(_dep_top_name(str(spec)))
        except Exception:
            pass
        try:
            for req in root.glob("requirements*.txt"):
                for line in req.read_text(encoding="utf-8", errors="replace").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#"):
                        deps.add(_dep_top_name(line))
        except Exception:
            pass
        deps.discard("")
        return deps

    def _local_modules(self, ws) -> set[str]:
        """Import names that resolve to the generated project itself (its package
        plus any top-level module/package dirs in the workspace)."""
        local: set[str] = set()
        try:
            local.add(workspace.package_name(self.state).replace("-", "_"))
        except Exception:
            pass
        root = Path(ws)
        try:
            for child in root.iterdir():
                name = child.name
                if name.startswith(".") or name in self._GUARD_SKIP_SEGMENTS:
                    continue
                if child.is_dir() and (child / "__init__.py").exists():
                    local.add(name)
                elif child.is_file() and name.endswith(".py"):
                    local.add(name[:-3])
        except OSError:
            pass
        local.discard("")
        return local

    def _block_delivery(self, message: str, *, source: str = "delivery") -> None:
        self._delivery_blocked = True
        self.state.error = ""
        delivery_state.append_issue(self.state, message)
        self._log(source, f"❌ {message}")

    # ------------------------------------------------------------- events

    def _sync(self) -> None:
        self._persist()
        bus.publish(
            {
                "type": "state",
                "project_id": self.state.id,
                "state": self.state.model_dump(mode="json"),
            }
        )

    def _persist(self) -> None:
        """Persist the state without stalling the event loop (BUG2).

        Serialize on the caller's thread (cheap, and snapshots the state so it
        can't mutate mid-write), then offload the blocking atomic write +
        Windows lock-retry sleep to a worker. When no loop is running (sync
        recovery, tests) the write happens inline so callers see it immediately."""
        payload = self.state.model_dump_json(indent=2)
        sid = self.state.id
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is None:
            save_state_payload(sid, payload)
        else:
            loop.run_in_executor(_PERSIST_EXECUTOR, save_state_payload, sid, payload)

    def _log(self, source: str, line: str) -> None:
        bus.publish(
            {"type": "log", "project_id": self.state.id, "source": source, "line": line}
        )
        # Le bus SSE est volatile : sans ce miroir, le récit opérationnel du run
        # (scope gate, merges, reverts, requeues, splits…) meurt avec le process
        # et un échec devient indiagnosticable après coup.
        self.monitor.log(source, line)

    def _chat(self, role: ChatRole, content: str) -> None:
        self.state.chat.append(ChatMessage(role=role, content=content))
        self._sync()

    def _record_interaction(self, **kwargs) -> None:
        """O2: capture one LLM round-trip on the item store (in-memory ring +
        JSONL sidecar via the store's persist hook). Never raises — capture must
        not be able to break an agent call. No event is broadcast: the activity
        panel polls the REST endpoint while open, so we avoid flooding the event
        replay ring with one event per agent call during a heavy build."""
        try:
            self.interactions.record(**kwargs)
        except Exception:
            return

    def _persist_interaction(self, interaction: AgentInteraction) -> None:
        """Append a captured interaction to the JSONL sidecar, offloaded off the
        event loop (the file write must not stall uvicorn's accept loop — see
        ``_persist``). Falls back to an inline write when no loop is running."""
        payload = interaction.model_dump_json()
        sid = self.state.id
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is None:
            append_interaction(sid, payload)
        else:
            loop.run_in_executor(_PERSIST_EXECUTOR, append_interaction, sid, payload)

    def _notify(self, level: str, title: str, body: str = "") -> None:
        """Emit a push-notification event (U3): the frontend turns it into a
        browser notification + an in-app toast. level: info|success|warning|error."""
        bus.publish(
            {
                "type": "notify",
                "project_id": self.state.id,
                "level": level,
                "title": title,
                "body": body,
            }
        )

    # ------------------------------------------------------- stage tracking (B1)

    def _set_stage(
        self, item, stage: BuildStage, persona: str = "", *, sync: bool = True
    ) -> None:
        """B1/N4 (UX): stamp the fine-grained build stage + persona on a work item
        (the persistent UserStory or Task) at a real transition, and broadcast.

        ``item`` is the persistent model (``_item_target``). Passing ``persona=""``
        clears the persona (e.g. on a terminal stage). All fields default-safe so
        this never depends on the UX migration having run."""
        item.current_stage = stage
        item.stage_started_at = time.time()
        item.current_persona = persona
        if sync:
            self._sync()

    def _set_recovery(
        self, item, kind: str, attempt: int = 0, max_attempts: int = 0,
        *, sync: bool = True,
    ) -> None:
        """B1 (UX): stamp the auto-repair state on a work item at the refine/
        regression/mutation/retry call sites. ``kind=""`` clears it."""
        item.recovery = RecoveryState(
            attempt=attempt, max_attempts=max_attempts, kind=kind
        )
        if sync:
            self._sync()

    def _apply_guidance(self, target) -> str:
        """P10 (UX): collect a work item's queued guidance, mark it ``applied``,
        and return the joined directive text to inject into that item's dev prompt
        alongside the project-level ``build_guidance``. Returns "" when none."""
        texts: list[str] = []
        for entry in target.guidance:
            if entry.status == "queued":
                entry.status = "applied"
            texts.append(entry.text)
        return "\n".join(t for t in texts if t.strip())

    # ------------------------------------------------------- heartbeat tick (B5)

    def _stall_reason(self) -> str:
        """B6 (UX): a one-line "why nothing is moving" hint for the tick.

        Priority: a held merge lock (its owner) > awaiting approval > budget
        pause > everyone at the parallel cap. "" when work is flowing."""
        if self._merge_lock.locked() and self._merge_lock.owner:
            return f"merge_lock_held:{self._merge_lock.owner}"
        if self.state.awaiting_approval:
            return "awaiting_approval"
        if self.state.paused:
            return "budget_paused"
        return ""

    def _tick_payload(self) -> dict:
        """B5 (UX): the compact per-item status snapshot broadcast every ~10s
        during BUILD. Item-level only (the full ``state`` event carries the rest),
        so the churn stays bounded."""
        items: list[dict] = []
        counts = {"running": 0, "queued": 0, "done": 0, "failed": 0, "blocked": 0}
        graph = work_streams.build_work_graph(self.state)
        for wid in graph.order:
            wi = graph.items[wid]
            target = self.state.story(wi.story_id) if wi.kind == "story" else self.state.task(wi.id)
            blockers = work_streams.blocked_by(wi, graph.items)
            items.append({
                "id": target.id,
                "kind": wi.kind,
                "status": target.status.value,
                "current_stage": target.current_stage.value,
                "stage_started_at": target.stage_started_at,
                "current_persona": target.current_persona,
                "recovery": {
                    "attempt": target.recovery.attempt,
                    "max_attempts": target.recovery.max_attempts,
                    "kind": target.recovery.kind,
                },
            })
            if target.status == StoryStatus.IN_PROGRESS:
                counts["running"] += 1
            elif target.status == StoryStatus.DONE:
                counts["done"] += 1
            elif target.status == StoryStatus.FAILED:
                counts["failed"] += 1
            elif target.status == StoryStatus.TODO and blockers:
                counts["blocked"] += 1
            elif target.status == StoryStatus.TODO:
                counts["queued"] += 1
            else:  # RED / GREEN are mid-build → running
                counts["running"] += 1
        return {
            "type": "tick",
            "project_id": self.state.id,
            "ts": time.time(),
            "items": items,
            "counts": counts,
            "stall_reason": self._stall_reason(),
        }

    def _publish_tick(self) -> None:
        """Fan out one tick WITHOUT buffering it for Last-Event-ID replay (a
        stale heartbeat must never be replayed on reconnect)."""
        bus.publish_ephemeral(self._tick_payload())

    async def _atick_loop(self) -> None:
        """B5 (UX): emit a heartbeat tick ~every 10s while phase==BUILD."""
        try:
            while self.state.phase == PipelinePhase.BUILD:
                self._publish_tick()
                await asyncio.sleep(10.0)
        except asyncio.CancelledError:
            pass

    def _start_tick(self) -> None:
        """Start the heartbeat publisher on BUILD entry (idempotent)."""
        if self._tick_task and not self._tick_task.done():
            return
        try:
            self._tick_task = asyncio.create_task(self._atick_loop())
        except RuntimeError:
            # No running loop (sync test contexts): the tick is a live-only signal.
            self._tick_task = None

    def _stop_tick(self) -> None:
        """Cancel the heartbeat publisher on stop/dispose/terminal phase."""
        if self._tick_task and not self._tick_task.done():
            self._tick_task.cancel()
        self._tick_task = None

    # ------------------------------------------------------------- control

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop_requested = False
        self._delivery_blocked = False
        delivery_state.reset(self.state)
        self._task = asyncio.create_task(self._alifecycle())

    async def adispose(self) -> None:
        """Hard-stop everything (used when the project is deleted): cancel the
        lifecycle task and terminate the generated app if it runs."""
        self._stop_requested = True
        self._stop_tick()  # B5: never tick after dispose
        # Kill any in-flight agent CLI call (claude/codex) and its sub-tree, so it
        # never survives the process as an orphan (cost/resource leak).
        self._agent_procs.terminate_all()
        self._kill_tree(self._run_proc)  # tree-kill so node/esbuild orphans die too
        for proc in self._frontend_procs:  # ST-8
            self._kill_tree(proc)
        # BUG9 : annule les tasks de streaming frontend encore actives (best-effort,
        # la teardown ne doit jamais lever).
        for ftask in self._frontend_stream_tasks:
            if ftask and not ftask.done():
                ftask.cancel()
        self._frontend_stream_tasks.clear()
        for task in (
            self._task,
            self._impact_task,
            self._setup_task,
            self._doc_task,
            self._deploy_task,
            self._eval_task,
            self._security_task,
            self._retro_task,
            self._resume_timer,
        ):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
        # BUG6 : draine la file de persistance (un seul worker) avant que
        # l'appelant ne supprime le workspace. Soumettre un no-op et l'attendre
        # agit comme une barrière : toutes les écritures déjà en file (state /
        # interactions, qui ouvrent des fichiers DANS le workspace) sont
        # terminées, donc aucune ne garde un handle ouvert pendant le rmtree
        # (sinon Windows verrouille -> 409). Best-effort : dispose ne doit
        # jamais lever (executor déjà fermé, pas de loop en cours…).
        try:
            await asyncio.get_running_loop().run_in_executor(
                _PERSIST_EXECUTOR, lambda: None
            )
        except Exception:
            pass

    async def asend_user_message(self, text: str) -> None:
        self._chat(ChatRole.USER, text)
        if self.state.phase == PipelinePhase.SPEC:
            await self._user_messages.put(text)
        elif self.state.phase in (PipelinePhase.BUILD, PipelinePhase.ARCHITECT):
            # During the build, user messages steer the Dev agent's next attempts.
            self.state.build_guidance.append(text)
            self._chat(
                ChatRole.SYSTEM,
                "📝 Consigne prise en compte pour les prochaines tentatives de développement.",
            )
        else:
            # Outside the interview, user messages are feedback for the next cycle.
            self.state.feedback.append(text)
            self._sync()
            # Pipeline dormant: analyze the feedback's impact right away (update
            # an unimplemented story, or plan a new epic/stories).
            if self.state.phase in (
                PipelinePhase.DONE,
                PipelinePhase.STOPPED,
                PipelinePhase.NEEDS_ATTENTION,
                PipelinePhase.ERROR,
            ) and not (self._impact_task and not self._impact_task.done()):
                self._impact_task = asyncio.create_task(self._aimpact_analysis(text))

    def _signal_stop(self) -> int:
        """Raise the stop flags + unblock every wait the lifecycle may sit on, and
        hard-kill any in-flight agent CLI call so the current chat/dev step stops
        NOW instead of running to completion. Returns the number of killed procs.
        Synchronous so it can run from shutdown without an await."""
        self._stop_requested = True
        self._stop_tick()  # B5: stop heartbeat
        self._resume_event.set()  # unblock a paused pipeline
        self._brainstorm_event.set()  # unblock a pending brainstorming offer
        self._approval_event.set()  # unblock a pending approval gate
        # Unblock a PM interview waiting for user input (non-blocking put).
        try:
            self._user_messages.put_nowait("")
        except asyncio.QueueFull:
            pass
        # Kill the in-flight agent CLI(s): the awaiting step then returns at once.
        return self._agent_procs.terminate_all()

    def _reset_inflight_items(self) -> None:
        """On a hard stop, revert any work item left in a transient build status
        (the killed dev/qa call) to TODO and clear its live stage/persona/recovery
        — so the board shows a clean, relaunchable state, never a frozen
        « dev en cours »."""
        transient = (StoryStatus.IN_PROGRESS, StoryStatus.GREEN, StoryStatus.RED)
        for story in self.state.stories:
            items = [story, *story.tasks]
            for item in items:
                if item.status in transient:
                    item.status = StoryStatus.TODO
                    item.current_stage = BuildStage.QUEUED
                    item.current_persona = ""
                    item.recovery = RecoveryState()

    async def astop(self) -> None:
        killed = self._signal_stop()
        suffix = (
            f" {killed} appel(s) agent en cours interrompu(s)." if killed else ""
        )
        self._chat(
            ChatRole.SYSTEM,
            f"Arrêt demandé : interruption des actions en cours.{suffix}",
        )

    async def ainterrupt(self, reason: str = "") -> int:
        """Hard-interrupt this project (project switch): kill the in-flight agent
        CLI call(s), stop the generated app/previews, and let the lifecycle wind
        down to STOPPED (it reconciles in-flight items). Returns killed count.

        Idempotent and safe when nothing runs. Does NOT await the lifecycle: the
        UI switch must return immediately; the pipeline finalizes on its own."""
        killed = self._signal_stop()
        await self.astop_app()  # also stop a running generated app / previews
        if reason:
            self._chat(ChatRole.SYSTEM, reason)
        return killed

    async def apause(self) -> None:
        if self.state.paused:
            return
        self._resume_event.clear()
        self.state.paused = True
        self._chat(ChatRole.SYSTEM, "⏸ Pause demandée : la pipeline s'arrêtera au prochain point de contrôle.")

    async def aresume(self) -> None:
        if not self.state.paused:
            return
        self.state.paused = False
        self._resume_event.set()
        self._chat(ChatRole.SYSTEM, "▶ Reprise de la pipeline.")

    async def _aapproval_gate(self, stage: str) -> None:
        """U4: block before the build until a human approves. No-op when gates are
        disabled or a stop is already requested."""
        if not settings.approval_gates_enabled or self._stop_requested:
            return
        self.state.awaiting_approval = stage
        self._approval_event.clear()
        self._notify("info", "Validation requise", f"{self.state.name} : {stage}")
        self._chat(
            ChatRole.SYSTEM,
            f"⏸ Validation requise ({stage}) — approuve pour lancer le build, ou rejette.",
        )
        self._sync()
        await self._approval_event.wait()
        self.state.awaiting_approval = ""
        self._sync()

    async def aapprove(self) -> None:
        """Release a pending approval gate so the build proceeds (U4)."""
        if not self.state.awaiting_approval:
            return
        self.state.awaiting_approval = ""
        self._approval_event.set()
        self._chat(ChatRole.SYSTEM, "✅ Étape validée — poursuite du build.")

    async def areject(self) -> None:
        """Reject a pending approval gate: stop the pipeline cleanly (U4)."""
        if not self.state.awaiting_approval:
            return
        self._stop_requested = True
        self.state.awaiting_approval = ""
        self._approval_event.set()
        self._resume_event.set()
        self._chat(ChatRole.SYSTEM, "✋ Étape rejetée — arrêt de la pipeline.")

    async def _checkpoint(self) -> None:
        """Enforce the budget, then block here while the pipeline is paused
        (called between phases / story batches / auto-spec iterations)."""
        self._enforce_budget()
        if not self._resume_event.is_set() and not self._stop_requested:
            await self._resume_event.wait()

    def _budget_reached(self) -> bool:
        u = self.state.usage
        if self.state.budget_usd and u.cost_usd >= self.state.budget_usd:
            return True
        if self.state.budget_tokens and (u.input_tokens + u.output_tokens) >= self.state.budget_tokens:
            return True
        return False

    def _enforce_budget(self) -> None:
        """Request a clean stop when the project's token/cost budget is reached."""
        if not self._stop_requested and self._budget_reached():
            self._stop_requested = True
            self._resume_event.set()  # unblock a paused loop so it can finish
            u = self.state.usage
            self._chat(
                ChatRole.SYSTEM,
                f"💰 Budget atteint (coût ${u.cost_usd:.4f}, "
                f"{u.input_tokens + u.output_tokens} tokens) — arrêt propre de la pipeline.",
            )
            self._notify("warning", "Budget atteint", f"{self.state.name} : ${u.cost_usd:.4f}")

    async def aset_archived(self, value: bool) -> None:
        """Archive or unarchive the project (hide it without deleting it)."""
        self.state.archived = bool(value)
        self._sync()

    async def aset_spec_mode(self, mode: str) -> None:
        """Switch the spec facilitation: 'interview' (Socratic) or 'brainstorm'
        (re-question the need). Takes effect on the PM's next turn."""
        if mode not in ("interview", "brainstorm"):
            raise ValueError("mode de spécification invalide")
        self.state.spec_mode = mode
        self._chat(
            ChatRole.SYSTEM,
            "🧠 Mode brainstorming activé (on re-questionne le besoin)."
            if mode == "brainstorm"
            else "💬 Mode interview socratique activé.",
        )

    async def aresolve_brainstorm(self, accept: bool) -> None:
        """B-IDEA: resolve the brainstorming offer. ``accept`` → interactive
        brainstorming (the user answers); ``refuse`` → autonomous brainstorming
        (the AI plays the product owner). Raises ValueError (-> 409) when no
        offer is pending."""
        if not self.state.awaiting_brainstorm_decision:
            raise ValueError("aucune décision de brainstorming en attente")
        self._brainstorm_accepted = bool(accept)
        self.state.awaiting_brainstorm_decision = False
        self._brainstorm_event.set()

    # ------------------------------------------------ targeted guidance (P10/B4)

    def _guidance_status_for(self, target) -> str:
        """A directive that arrives after the item is terminal can no longer be
        injected into a dev run → ``too_late``; otherwise ``queued``."""
        status = target.status
        if status in (StoryStatus.DONE, StoryStatus.FAILED):
            return "too_late"
        return "queued"

    async def achat_story(self, sid: str, message: str, entry_id: str | None = None) -> GuidanceEntry:
        """P10/B4: append a targeted directive to a story's ``guidance`` (injected
        into THAT story's next dev run), echo it to the project chat, and persist.

        Idempotent: a repeated ``entry_id`` returns the existing entry without
        appending a duplicate. Raises KeyError (-> 404) if the story is unknown."""
        story = self.state.story(sid)  # KeyError if absent
        return await self._aappend_guidance(story, f"[{sid}]", message, entry_id)

    async def achat_task(self, tid: str, message: str, entry_id: str | None = None) -> GuidanceEntry:
        """P10/B4: same as ``achat_story`` for a single task."""
        task = self.state.task(tid)  # KeyError if absent
        return await self._aappend_guidance(task, f"[{tid}]", message, entry_id)

    async def _aappend_guidance(
        self, target, label: str, message: str, entry_id: str | None
    ) -> GuidanceEntry:
        if entry_id:
            for existing in target.guidance:
                if existing.id == entry_id:
                    return existing  # idempotent replay
        entry = GuidanceEntry(
            id=entry_id or new_id("g"),
            text=message,
            status=self._guidance_status_for(target),
        )
        target.guidance.append(entry)
        self._chat(ChatRole.USER, f"{label} {message}")
        self._sync()
        return entry

    async def aextend_story(self, sid: str, criteria: list[str]) -> UserStory:
        """P12/B4: append acceptance criteria to a story still in TODO (so the
        next build picks them up). Raises KeyError (-> 404) if unknown, ValueError
        (-> 409) if the story has already started (not TODO)."""
        story = self.state.story(sid)  # KeyError if absent
        # BUG8 : une US décomposée en tasks garde un ``status`` stocké à TODO même
        # une fois entièrement construite — on doit donc tester l'état EFFECTIF.
        if story.effective_status() != StoryStatus.TODO:
            raise ValueError("la story a déjà démarré : impossible d'étendre ses critères")
        start = len(story.acceptance_criteria)
        for i, text in enumerate(criteria, start=start + 1):
            if str(text).strip():
                story.acceptance_criteria.append(
                    AcceptanceCriterion(id=f"AC-{i}", text=str(text))
                )
        self._sync()
        return story

    # ------------------------------------------------------------ spec editing

    async def aedit_story(
        self,
        sid: str,
        *,
        title: str | None = None,
        description: str | None = None,
        gherkin: str | None = None,
        priority: int | None = None,
        acceptance_criteria: list[dict] | None = None,
    ) -> UserStory:
        """Edit an existing story's fields. Raises KeyError if the story is
        unknown, ValueError (-> 409) if it is currently being developed."""
        story = self.state.story(sid)  # KeyError if absent
        # BUG8 : une US décomposée en tasks reste à ``status`` TODO pendant que ses
        # tasks tournent — on teste l'état EFFECTIF pour bloquer l'édition en cours.
        if story.effective_status() == StoryStatus.IN_PROGRESS:
            raise ValueError("story en cours de développement")
        if title is not None:
            story.title = title
        if description is not None:
            story.description = description
        if priority is not None:
            story.priority = _clamp_1_5(priority)
        if acceptance_criteria is not None:
            story.acceptance_criteria = [
                AcceptanceCriterion(
                    id=item.get("id") or f"AC-{i}",
                    text=item["text"],
                )
                for i, item in enumerate(acceptance_criteria, start=1)
            ]
        gherkin_changed = gherkin is not None and gherkin != story.gherkin
        if gherkin is not None:
            story.gherkin = gherkin
        if gherkin_changed:
            workspace.write_feature_files(self.state, [story])
        self._sync()
        return story

    async def aadd_story(
        self,
        *,
        epic_id: str,
        title: str,
        description: str = "",
        gherkin: str = "",
        priority: int = 3,
        acceptance_criteria: list[str] | None = None,
        depends_on: list[str] | None = None,
    ) -> UserStory:
        """Create a new story under an existing epic. Raises KeyError if the
        epic is unknown."""
        if not any(e.id == epic_id for e in self.state.epics):
            raise KeyError(epic_id)
        existing_ids = {s.id for s in self.state.stories}
        criteria = [
            AcceptanceCriterion(id=f"AC-{i}", text=str(text))
            for i, text in enumerate(acceptance_criteria or [], start=1)
        ]
        story = UserStory(
            id=_unique_id(f"US-{len(existing_ids) + 1}", "US", existing_ids),
            epic_id=epic_id,
            title=title,
            description=description,
            acceptance_criteria=criteria,
            gherkin=gherkin,
            depends_on=depends_on or [],
            priority=_clamp_1_5(priority),
            iteration=self.state.iteration,
            status=StoryStatus.TODO,
        )
        self.state.stories.append(story)
        scheduler.sanitize_dependencies(self.state.stories)
        workspace.write_feature_files(self.state, [story])
        self._sync()
        return story

    async def adelete_story(self, sid: str) -> None:
        """Delete a story and scrub references to it. Raises KeyError if the
        story is unknown, ValueError (-> 409) if it is being developed."""
        story = self.state.story(sid)  # KeyError if absent
        if story.status == StoryStatus.IN_PROGRESS:
            raise ValueError("story en cours de développement")
        self.state.stories = [s for s in self.state.stories if s.id != sid]
        for other in self.state.stories:
            if sid in other.depends_on:
                other.depends_on = [d for d in other.depends_on if d != sid]
        try:
            (workspace_dir(self.state.id) / workspace.feature_rel_path(story)).unlink(
                missing_ok=True
            )
        except OSError:
            pass  # best-effort cleanup
        self._sync()

    async def areorder_stories(self, priorities: list[dict]) -> None:
        """Bulk-update story priorities from a list of {id, priority} entries.
        Unknown ids are ignored."""
        by_id = {s.id: s for s in self.state.stories}
        for entry in priorities:
            story = by_id.get(entry.get("id"))
            if story is not None:
                story.priority = _clamp_1_5(entry.get("priority"), default=story.priority)
        self._sync()

    # ------------------------------------------- usage-window watchdog (M2)

    async def _aon_agent_error(self, exc: AgentError) -> None:
        """When the Claude harness reports an exhausted usage window: stop the
        pipeline cleanly and schedule an automatic resume at the next fresh
        session window (error epoch → ccusage active block → fallback delay).

        Best-effort watchdog: it must never mask the original AgentError."""
        try:
            if not session_monitor.monitor_active():
                return
            if not session_monitor.is_usage_limit_error(str(exc)):
                return
            if self.state.resume_at and self._resume_timer and not self._resume_timer.done():
                return  # parallel workers hit the same wall: already scheduled
            at = await session_monitor.anext_reset(str(exc))
            self._stop_requested = True
            self._resume_event.set()  # unblock a paused loop so it can stop
            self._chat(
                ChatRole.SYSTEM,
                "⏳ Fenêtre d'usage Claude épuisée — arrêt propre de la pipeline. "
                f"Reprise automatique programmée à {time.strftime('%H:%M', time.localtime(at))} "
                "(nouvelle session disponible).",
            )
            self.schedule_resume(at)
            self._notify(
                "info",
                "Reprise programmée",
                f"{self.state.name} à {time.strftime('%H:%M', time.localtime(at))}",
            )
        except Exception:  # noqa: BLE001 — watchdog only
            pass

    def schedule_resume(self, at: float) -> None:
        """Arm (or re-arm) the auto-resume timer and persist ``resume_at`` so a
        backend restart can re-arm it (recover_projects)."""
        self.state.resume_at = at
        self._sync()
        if self._resume_timer and not self._resume_timer.done():
            self._resume_timer.cancel()
        self._resume_timer = asyncio.create_task(self._aresume_timer(at))

    async def _aresume_timer(self, at: float) -> None:
        await asyncio.sleep(max(0.0, at - time.time()))
        # The clean stop runs asynchronously: the interrupted lifecycle task only
        # unwinds (phase leaves BUILD) at its next checkpoint. Wait for it to land
        # before resuming, otherwise aresume_build's active-pipeline guard rejects
        # us. Matters when the reset window is very close to the error (a short
        # ccusage block, or an epoch only seconds out) — production windows are
        # usually minutes/hours away so the task is long gone by the time we wake.
        task = self._task
        if task is not None and not task.done():
            try:
                await task
            except Exception:  # noqa: BLE001 — the lifecycle task logs its own errors
                pass
        self.state.resume_at = 0.0
        self._chat(
            ChatRole.SYSTEM,
            "⏰ Nouvelle fenêtre d'usage disponible — reprise du travail en cours.",
        )
        try:
            await self.aresume_build()
        except ValueError as exc:
            # Nothing buildable (e.g. the window died during the spec phase):
            # leave the project dormant, the user relaunches manually.
            self._chat(ChatRole.SYSTEM, f"Reprise automatique impossible : {exc}")

    async def acancel_resume(self) -> None:
        """Cancel a scheduled auto-resume (user override)."""
        if self._resume_timer and not self._resume_timer.done():
            self._resume_timer.cancel()
        self.state.resume_at = 0.0
        self._chat(ChatRole.SYSTEM, "⏰ Reprise automatique annulée.")

    # ------------------------------------------------------ feedback impact

    async def _aimpact_analysis(self, feedback: str) -> None:
        """Analyze a feedback's impact while the pipeline is dormant: either
        update an unimplemented story, or create a new epic + stories. Errors
        are surfaced to the chat, never raised (background task)."""
        try:
            result = await self._tracked.arun(
                prompts.feedback_impact(self.state, feedback),
                system_prompt=persona("analyst"),
            )
            reply = extract_json(result.text)
        except AgentError as exc:
            self._chat(ChatRole.SYSTEM, f"Analyse d'impact du feedback impossible : {exc}")
            return
        message = reply.get("message", "")
        action = reply.get("action", "none")
        if action == "update_story":
            self._apply_story_update(reply, message)
        elif action == "new_stories":
            self._apply_new_stories(reply, message)
        else:
            self._chat(ChatRole.ANALYST, f"🔍 Impact : {message or 'aucun changement à planifier.'}")

    def _apply_story_update(self, reply: dict, message: str) -> None:
        """Apply an impact decision that amends an existing, unimplemented story."""
        sid = reply.get("story_id") or ""
        story = next((s for s in self.state.stories if s.id == sid), None)
        # BUG8 : une US décomposée et entièrement construite garde ``status`` TODO ;
        # on teste l'état EFFECTIF pour ne pas amender une story déjà implémentée.
        if story is None or story.effective_status() not in (StoryStatus.TODO, StoryStatus.FAILED):
            self._chat(
                ChatRole.ANALYST,
                f"🔍 Impact : la story visée ({sid or '?'}) est introuvable ou déjà "
                "implémentée — feedback conservé pour la prochaine analyse.",
            )
            return
        updates = reply.get("updates") or {}
        if updates.get("title"):
            story.title = str(updates["title"])
        if updates.get("description"):
            story.description = str(updates["description"])
        if updates.get("priority") is not None:
            story.priority = _clamp_1_5(updates.get("priority"), default=story.priority)
        if isinstance(updates.get("acceptance_criteria"), list):
            story.acceptance_criteria = [
                AcceptanceCriterion(id=f"AC-{i}", text=str(text))
                for i, text in enumerate(updates["acceptance_criteria"], start=1)
            ]
        gherkin = updates.get("gherkin")
        if gherkin and gherkin != story.gherkin:
            story.gherkin = str(gherkin)
            workspace.write_feature_files(self.state, [story])
        # A failed story amended by feedback deserves a fresh run.
        if story.status == StoryStatus.FAILED:
            story.status = StoryStatus.TODO
            story.attempts = 0
            story.infra_attempts = 0
            story.last_error = ""
        self._chat(ChatRole.ANALYST, f"🔍 Impact : {message}\n✏️ Story {story.id} mise à jour.")

    def _apply_new_stories(self, reply: dict, message: str) -> None:
        """Apply an impact decision that plans a new epic and/or new stories.

        ST-15: with streams enabled, the analyst may also grow the product into a
        new work area — ``add_streams`` adds streams (e.g. a web UI → the
        ``frontend`` stream) and the new stories may carry a ``stream`` and a
        task decomposition whose ``depends_on`` links the new (front) tasks to
        existing (back) tasks/US. Flag-off, the parse is byte-identical to before
        (no streams, no tasks)."""
        items = reply.get("stories") or []
        if not items:
            self._chat(ChatRole.ANALYST, f"🔍 Impact : {message or 'aucune story proposée.'}")
            return
        streams_on = self._setting("streams_enabled")
        # ST-15: materialize any newly-needed streams BEFORE tagging tasks.
        added_streams: list[str] = []
        if streams_on:
            for sid in reply.get("add_streams") or []:
                if self._ensure_stream(str(sid)):
                    added_streams.append(str(sid))

        epic_id = reply.get("epic_id") or ""
        if not any(e.id == epic_id for e in self.state.epics):
            epic_data = reply.get("epic") or {}
            taken = {e.id for e in self.state.epics}
            epic_id = _unique_id(
                epic_data.get("id") or f"EPIC-{len(taken) + 1}", "EPIC", taken
            )
            self.state.epics.append(
                Epic(
                    id=epic_id,
                    title=epic_data.get("title", "Retours utilisateur"),
                    description=epic_data.get("description", ""),
                    iteration=self.state.iteration,
                )
            )

        # First pass: assign project-wide-unique story + task ids, building rename
        # maps so depends_on (story↔story and task↔task/US) remap consistently.
        taken_story_ids = {s.id for s in self.state.stories}
        taken_task_ids = {t.id for t in self.state.all_tasks()}
        story_id_map: dict[str, str] = {}
        task_id_map: dict[str, str] = {}
        planned: list[tuple[str, dict]] = []
        for story_data in items:
            raw_sid = story_data.get("id") or f"US-{len(taken_story_ids) + 1}"
            story_id = _unique_id(raw_sid, "US", taken_story_ids)
            taken_story_ids.add(story_id)
            story_id_map.setdefault(raw_sid, story_id)
            if streams_on:
                for task_data in story_data.get("tasks") or []:
                    raw_tid = str(task_data.get("id") or f"T-{len(taken_task_ids) + 1}")
                    tid = _unique_id(raw_tid, "T", taken_task_ids)
                    taken_task_ids.add(tid)
                    task_id_map.setdefault(raw_tid, tid)
            planned.append((story_id, story_data))

        # A dep may point at a (renamed) batch task, a (renamed) batch story, or
        # an existing task/US id — pass the latter through unchanged.
        def _remap_dep(d: str) -> str:
            return task_id_map.get(d) or story_id_map.get(d) or d

        def _build_tasks(story_id: str, story_data: dict) -> list[Task]:
            if not streams_on:
                return []
            out: list[Task] = []
            for task_data in story_data.get("tasks") or []:
                raw_tid = str(task_data.get("id") or "")
                out.append(
                    Task(
                        id=task_id_map.get(raw_tid, raw_tid),
                        story_id=story_id,
                        stream=str(task_data.get("stream") or ""),
                        title=task_data.get("title", ""),
                        description=task_data.get("description", ""),
                        acceptance_criteria=[
                            AcceptanceCriterion(id=f"AC-{i}", text=str(t))
                            for i, t in enumerate(task_data.get("acceptance_criteria", []), start=1)
                        ],
                        gherkin=task_data.get("gherkin", ""),
                        depends_on=[_remap_dep(d) for d in task_data.get("depends_on", [])],
                    )
                )
            return out

        new_stories: list[UserStory] = []
        for story_id, story_data in planned:
            new_stories.append(
                UserStory(
                    id=story_id,
                    epic_id=epic_id,
                    title=story_data.get("title", "Story"),
                    description=story_data.get("description", ""),
                    acceptance_criteria=[
                        AcceptanceCriterion(id=f"AC-{i}", text=str(text))
                        for i, text in enumerate(
                            story_data.get("acceptance_criteria", []), start=1
                        )
                    ],
                    gherkin=story_data.get("gherkin", ""),
                    depends_on=[story_id_map.get(d, d) for d in story_data.get("depends_on", [])],
                    priority=_clamp_1_5(story_data.get("priority", 2)),
                    ui=bool(story_data.get("ui", False)),
                    stream=str(story_data.get("stream") or "") if streams_on else "",
                    tasks=_build_tasks(story_id, story_data),
                    iteration=self.state.iteration,
                )
            )
        scheduler.sanitize_dependencies(self.state.stories + new_stories)
        self.state.stories.extend(new_stories)
        workspace.write_feature_files(self.state, new_stories)
        if streams_on:
            for w in work_streams.validate(self.state):
                self._log("streams", f"Graphe de tâches : {w}")
        n_tasks = sum(len(s.tasks) for s in new_stories)
        task_note = f", {n_tasks} tâche(s)" if n_tasks else ""
        extra = f" 🧵 Nouveau(x) stream(s) : {', '.join(added_streams)}." if added_streams else ""
        self._chat(
            ChatRole.ANALYST,
            f"🔍 Impact : {message}{extra}\n➕ {len(new_stories)} nouvelle(s) story(ies){task_note} "
            "planifiée(s) — « ▶ Continuer le build » pour les développer.",
        )

    # ------------------------------------------------------ components (E3/E4)

    async def _abrownfield_init(self) -> None:
        """B1: seed the workspace from an existing repo and inject a summary of
        its layout into the architecture context, so the pipeline builds features
        on top of the existing code. No-op when no brownfield path is set."""
        if not self.state.brownfield_path:
            return
        ws = workspace_dir(self.state.id)
        path = self.state.brownfield_path

        def _seed():
            n = brownfield.seed_workspace_from(path, ws)
            return n, brownfield.summarize_repo(path)

        copied, summary = await asyncio.to_thread(_seed)
        if summary:
            prefix = "Contexte brownfield (code existant à étendre) :\n" + summary
            self.state.architecture = (
                prefix + "\n\n" + self.state.architecture
                if self.state.architecture
                else prefix
            )
        self._chat(
            ChatRole.SYSTEM,
            f"🧩 Mode brownfield : {copied} fichier(s) existant(s) intégrés au workspace.",
        )
        self._sync()

    async def _aselect_language(self) -> None:
        """L2: choose the backend language from the brief/goal. Env-gated by
        LANGUAGE_SELECTOR — OFF keeps Python as the safe default (no
        analysis, no panel, the existing pytest pipeline unchanged); ON runs the
        deterministic heuristic and, when the LLM is reachable, an agent that may
        refine it. First iteration only, non-fatal."""
        if not settings.language_selector_enabled:
            return
        if self.state.language_complexity >= 0:  # already analyzed
            return
        rec = recommend_language(self.state.goal, self.state.brief)
        try:
            result = await self._tracked.arun(
                prompts.language_proposal(self.state),
                system_prompt=persona("architect"),
            )
            reply = extract_json(result.text)
            lang = str(reply.get("language", "")).strip().lower()
            if lang in ("python", "go", "rust"):
                rec = {
                    "language": lang,
                    "complexity": _clamp_1_5(reply.get("complexity"), default=rec["complexity"]),
                    "criticality": _clamp_1_5(reply.get("criticality"), default=rec["criticality"]),
                    "rationale": str(reply.get("rationale") or rec["rationale"]),
                }
        except AgentError as exc:
            self._log("language", f"Sélecteur de langage indisponible ({exc}) — heuristique.")
        self.state.backend_language = BackendLanguage(rec["language"])
        self.state.language_complexity = rec["complexity"]
        self.state.language_criticality = rec["criticality"]
        self.state.language_rationale = rec["rationale"]
        self._chat(
            ChatRole.SYSTEM,
            f"🧭 Langage backend recommandé : {rec['language']} "
            f"(complexité {rec['complexity']}/5, criticité {rec['criticality']}/5) — "
            f"{rec['rationale']}",
        )

    async def _aselect_streams(self) -> None:
        """ST-4: the architect picks the project's work streams from the catalog.
        Env-gated by STREAMS — OFF is a strict no-op (``state.streams``
        stays empty → one implicit backend stream, the pre-streams behaviour).
        Always forces a primary backend stream carrying the backend language;
        ids are deduplicated. Non-fatal: any agent/parse failure falls back to a
        lone backend stream. First time only (already-chosen streams are kept)."""
        if not self._setting("streams_enabled") or self.state.streams:
            return
        back_lang = self.state.backend_language.value
        chosen: list[Stream] = []
        rationale = ""
        try:
            result = await self._tracked.arun(
                prompts.select_streams(self.state),
                system_prompt=persona("architect"),
            )
            reply = extract_json(result.text)
            rationale = str(reply.get("rationale") or "")
            seen: set[str] = set()
            for data in reply.get("streams", []):
                sid = str(data.get("id") or "").strip()
                if not sid or sid in seen:
                    continue
                try:
                    kind = StreamKind(str(data.get("kind") or "other").strip().lower())
                except ValueError:
                    kind = StreamKind.OTHER
                seen.add(sid)
                chosen.append(
                    Stream(
                        id=sid,
                        kind=kind,
                        language=str(data.get("language") or "").strip(),
                        file_root=str(data.get("file_root") or "").strip(),
                        primary=(kind == StreamKind.BACKEND),
                    )
                )
        except AgentError as exc:
            self._log("streams", f"Sélecteur de streams indisponible ({exc}) — backend seul.")

        # Always guarantee exactly one primary backend stream carrying the
        # backend language: drop any agent-declared backend, prepend ours.
        non_backend = [s for s in chosen if s.kind != StreamKind.BACKEND]
        for s in non_backend:
            s.primary = False
        self.state.streams = [backend_stream_for(back_lang)] + non_backend

        listing = ", ".join(f"{s.id} ({s.kind.value}/{s.language or '—'})" for s in self.state.streams)
        msg = f"🧵 Streams retenus : {listing}."
        if rationale:
            msg += f" {rationale}"
        self._chat(ChatRole.SYSTEM, msg)

    def _ensure_stream(self, stream_id: str) -> bool:
        """ST-15: add a stream to the project if absent (from the catalog). Used
        when a feedback evolves the product into a new work area (e.g. a web UI →
        the ``frontend`` stream). Returns True when a new stream was added.

        Materializes the implicit backend stream first when ``streams`` is still
        empty, so the project keeps exactly one primary backend stream."""
        sid = (stream_id or "").strip()
        if not sid:
            return False
        if not self.state.streams:
            self.state.streams = [backend_stream_for(self.state.backend_language.value)]
        if any(s.id == sid for s in self.state.streams):
            return False
        spec = DEFAULT_STREAM_CATALOG.get(sid)
        kind = spec["kind"] if spec else StreamKind.OTHER
        self.state.streams.append(
            Stream(
                id=sid,
                kind=kind,
                language=str(spec.get("language", "")) if spec else "",
                file_root=str(spec.get("file_root", "")) if spec else "",
                primary=False,
            )
        )
        return True

    async def aset_language(self, language: str) -> ProjectState:
        """L2: user override of the backend language. Raises ValueError (->409)
        on an unknown language."""
        try:
            self.state.backend_language = BackendLanguage(language.strip().lower())
        except ValueError:
            raise ValueError(f"langage inconnu : {language!r} (python|go|rust)")
        self._sync()
        return self.state

    async def _apropose_components(self) -> None:
        """Solution agent proposes the product's technical components right
        after the brief (first iteration only). Mandatory components are
        pre-approved; optional ones await the user. Non-fatal, env-gated."""
        if not self._setting("components_enabled") or self.state.components:
            return
        try:
            result = await self._tracked.arun(
                prompts.components_proposal(self.state),
                system_prompt=persona("architect"),
            )
            reply = extract_json(result.text)
        except AgentError as exc:
            self._log("components", f"Solutionneur indisponible ({exc}) — pas de composants.")
            return
        components: list[Component] = []
        for i, data in enumerate(reply.get("components", []), start=1):
            optional = bool(data.get("optional", False))
            components.append(
                Component(
                    id=str(data.get("id") or f"comp-{i}"),
                    kind=str(data.get("kind") or "other"),
                    name=str(data.get("name") or f"Composant {i}"),
                    technology=str(data.get("technology") or ""),
                    rationale=str(data.get("rationale") or ""),
                    optional=optional,
                    status=ComponentStatus.PROPOSED if optional else ComponentStatus.APPROVED,
                )
            )
        self.state.components = components
        listing = ", ".join(
            f"{c.name} ({c.technology}){' [optionnel]' if c.optional else ''}"
            for c in components
        )
        self._chat(
            ChatRole.ARCHITECT,
            f"🧱 {reply.get('message', '')}\nComposants proposés : {listing or '(aucun)'}",
        )

    async def aset_components(self, items: list[dict]) -> list[Component]:
        """Replace the components list (user validation/edition from the UI)."""
        self.state.components = setup_exec.components_from_payload(items)
        self._sync()
        return self.state.components

    async def asetup_components(self) -> None:
        """Run the setup executor over the approved components, in background.

        Raises ValueError (-> 409) when a setup is already running or no
        component is approved."""
        if self._setup_task and not self._setup_task.done():
            raise ValueError("un setup de composants est déjà en cours")
        if not any(
            c.status in (ComponentStatus.APPROVED, ComponentStatus.CREATED)
            for c in self.state.components
        ):
            raise ValueError("aucun composant approuvé à créer")
        self._setup_task = asyncio.create_task(self._asetup_run())

    async def _asetup_run(self) -> None:
        ws = workspace.scaffold(self.state)
        self._log("setup", "🧱 Création des composants approuvés…")
        try:
            for line in await setup_exec.aexecute(self.state, ws):
                self._log("setup", line)
        except Exception as exc:  # background task: surface, never crash silently
            self._chat(ChatRole.SYSTEM, f"Erreur du setup des composants : {exc}")
        finally:
            self._sync()

    # ------------------------------------------------------ tech-writer (I2)

    async def adeploy(self) -> dict:
        """Generate deployment artifacts (Dockerfile, .dockerignore, CI) for the
        generated product (D1) and, when the project is a deployable web app,
        kick off a background Docker build+deploy+verify+repair pass. Idempotent;
        returns ``{"created": [...], "deploy_started": bool}``. Raises ValueError
        (-> 409) while the pipeline is actively building or when a deploy pass is
        already running."""
        if self.state.phase in (
            PipelinePhase.SPEC, PipelinePhase.ANALYZE, PipelinePhase.PLAN,
            PipelinePhase.ARCHITECT, PipelinePhase.BUILD,
        ):
            raise ValueError(
                "la pipeline est active : attends la fin avant de générer le déploiement"
            )
        if self._deploy_task and not self._deploy_task.done():
            raise ValueError("un déploiement Docker est déjà en cours")
        ws = workspace.scaffold(self.state)
        # Manual trigger: bypass the DOCKER_DELIVERY gate flag but keep the
        # FAKE_AGENTS / web-candidate skips (never containerise a demo or a
        # non-web product on an explicit deploy either).
        run, _reason, kind = docker_deploy.should_run(self.state, ws, enabled=True)
        created = await asyncio.to_thread(
            deploy.write_deploy_artifacts,
            ws,
            port=self._resolve_web_port(ws),
            kind=kind or "backend",
        )
        self._chat(
            ChatRole.SYSTEM,
            "🚀 Artefacts de déploiement générés : "
            + (", ".join(created) if created else "déjà présents."),
        )
        deploy_started = False
        if run:
            self._deploy_task = asyncio.create_task(self._adeploy_task())
            deploy_started = True
        return {"created": created, "deploy_started": deploy_started}

    async def _adeploy_task(self) -> None:
        try:
            await self._adocker_delivery_phase()
        except Exception as exc:  # background task: surface, never crash silently
            self._chat(ChatRole.SYSTEM, f"Erreur de la livraison Docker : {exc}")
        finally:
            self._sync()

    async def averify_delivery(self) -> None:
        """Re-run the FULL delivery-gate chain (smoke → runtime → DoD → docker)
        on a dormant project, without rebuilding anything.

        This is the operator's exit from an INFRA park: a gate that could not
        verify (external process on the port, Docker daemon down…) leaves the
        project in needs_attention — once the environment is fixed, this replays
        the gates instead of forcing a pointless story rebuild. Raises ValueError
        (-> 409) while the pipeline is active or a task is already running."""
        if self.state.phase in (
            PipelinePhase.SPEC, PipelinePhase.ANALYZE, PipelinePhase.PLAN,
            PipelinePhase.ARCHITECT, PipelinePhase.BUILD,
        ):
            raise ValueError("la pipeline est active : attends la fin avant de re-vérifier")
        if self._task and not self._task.done():
            raise ValueError("une tâche est déjà en cours")
        if self._deploy_task and not self._deploy_task.done():
            raise ValueError("un déploiement Docker est en cours")
        self._stop_requested = False
        self._delivery_blocked = False
        delivery_state.reset(self.state)
        # Set BUILD synchronously BEFORE launching the task so a second
        # concurrent call is rejected by the phase guard (closes the TOCTOU).
        self.state.phase = PipelinePhase.BUILD
        self._sync()
        self._task = asyncio.create_task(self._averify_delivery_task())

    async def _averify_delivery_task(self) -> None:
        self._chat(ChatRole.SYSTEM, "🔁 Re-vérification de la livraison (gates)…")
        try:
            await self._adelivery_gates()
        except Exception as exc:  # never leave the pipeline in a broken state
            self._chat(ChatRole.SYSTEM, f"Erreur lors de la re-vérification : {exc}")
        finally:
            if self._stop_requested:
                self.state.phase = PipelinePhase.STOPPED
            elif self._delivery_blocked:
                self.state.phase = PipelinePhase.NEEDS_ATTENTION
            else:
                self.state.phase = PipelinePhase.DONE
            self._sync()

    async def aundeploy(self) -> None:
        """Tear down this project's Docker container/image and reset the deploy
        STATUS/DETAIL. The image/container names and the allocated host port are
        deliberately KEPT in state (stable identity across redeploys — see
        ``delivery_state.set_deploy``). Raises ValueError (-> 409) while a
        deploy pass is running."""
        if self._deploy_task and not self._deploy_task.done():
            raise ValueError("un déploiement Docker est en cours")
        await asyncio.to_thread(docker_deploy.undeploy, self.state.id)
        delivery_state.set_deploy(self.state, status="", detail="")
        self._chat(ChatRole.SYSTEM, "🐳 Conteneur retiré du réseau Docker.")
        self._sync()

    async def adocument(self) -> None:
        """Tech-writer pass in the background: write the GENERATED project's
        README (presentation, launch instructions, architecture summary).
        Raises ValueError (-> 409) while the pipeline is actively building or
        when a documentation pass is already running."""
        if self.state.phase in (
            PipelinePhase.SPEC,
            PipelinePhase.ANALYZE,
            PipelinePhase.PLAN,
            PipelinePhase.ARCHITECT,
            PipelinePhase.BUILD,
        ):
            raise ValueError("la pipeline est active : attends la fin avant de générer la doc")
        if self._doc_task and not self._doc_task.done():
            raise ValueError("une génération de doc est déjà en cours")
        self._doc_task = asyncio.create_task(self._adocument_task())

    async def _adocument_task(self) -> None:
        try:
            await self._adocument_phase(force=True)
        except Exception as exc:  # background task: surface, never crash silently
            self._chat(ChatRole.SYSTEM, f"Erreur du tech-writer : {exc}")

    async def _adocument_phase(self, force: bool = False) -> None:
        """Run the tech-writer and persist README.md in the workspace. Env-gated
        in the pipeline flow (force=True for the explicit endpoint); non-fatal."""
        if not force and not settings.tech_writer_enabled:
            return
        ws = workspace.scaffold(self.state)
        try:
            result = await self._tracked.arun(
                prompts.tech_writer(self.state, workspace.package_name(self.state)),
                system_prompt=persona("tech-writer"),
                cwd=ws,
            )
            reply = extract_json(result.text)
        except AgentError as exc:
            self._chat(ChatRole.SYSTEM, f"Tech-writer indisponible : {exc}")
            return
        readme = reply.get("readme", "")
        if readme:
            (ws / "README.md").write_text(readme, encoding="utf-8")
        self._chat(
            ChatRole.SYSTEM,
            f"📘 {reply.get('message', 'Documentation générée.')}"
            + (" README.md écrit dans le workspace." if readme else ""),
        )

    # ------------------------------------------------ product evaluator (E6)

    async def aevaluate(self) -> None:
        """Run the closed-loop evaluator on demand (background): exercise the
        generated product and feed its findings into the impact pipeline.

        Raises ValueError (-> 409) while the pipeline is actively building or
        when an evaluation is already running."""
        if self.state.phase in (
            PipelinePhase.SPEC,
            PipelinePhase.ANALYZE,
            PipelinePhase.PLAN,
            PipelinePhase.ARCHITECT,
            PipelinePhase.BUILD,
        ):
            raise ValueError("la pipeline est active : attends la fin avant d'évaluer le produit")
        if self._eval_task and not self._eval_task.done():
            raise ValueError("une évaluation est déjà en cours")
        self._eval_task = asyncio.create_task(self._aevaluate_task())

    async def _aevaluate_task(self) -> None:
        try:
            await self._aevaluate_phase(force=True)
        except Exception as exc:  # background task: surface, never crash silently
            self._chat(ChatRole.SYSTEM, f"Erreur de l'évaluateur : {exc}")

    def _maybe_sandbox(self, cmd: list, ws) -> list:
        """R1: wrap a command to run inside a no-network Docker sandbox when
        enabled, else return it unchanged."""
        if not settings.sandbox_enabled:
            return cmd
        return sandbox.docker_run_cmd(
            list(cmd), str(ws), settings.sandbox_image, docker=settings.docker_cmd
        )

    async def _aexercise_product(self) -> str:
        """Actually launch the generated app (`main.py`) and capture its output.

        The app is untrusted agent code: it runs with a minimal environment (no
        server secrets) and a wall-clock cap. A long-running server simply hits
        the timeout — we keep whatever it printed at startup. Demo mode short-
        circuits (no real process)."""
        if settings.fake_agents:
            return "mode démo : exécution réelle du produit court-circuitée"
        ws = workspace_dir(self.state.id)
        env = _minimal_env()
        timeout = settings.evaluator_run_timeout_s
        run_cmd = toolchain.run_command(toolchain.normalize(self.state.backend_language.value))
        cmd = self._maybe_sandbox(run_cmd, ws)

        def _run() -> str:
            try:
                proc = subprocess.run(
                    cmd, cwd=str(ws),
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    env=env, text=True, encoding="utf-8", errors="replace",
                    timeout=timeout,
                )
                return f"(processus terminé, code {proc.returncode})\n{proc.stdout}"
            except subprocess.TimeoutExpired as exc:
                out = exc.output or ""
                if isinstance(out, bytes):
                    out = out.decode("utf-8", errors="replace")
                return (
                    f"(toujours actif après {timeout:g}s — probablement un service de "
                    f"longue durée)\n{out}"
                )
            except OSError as exc:
                return f"(lancement impossible : {exc})"

        return await asyncio.to_thread(_run)

    async def _aevaluate_phase(self, force: bool = False) -> None:
        """Exercise the delivered product and turn the run into structured
        findings, then feed them into the feedback-impact pipeline (E2) as
        evidence. Env-gated in the pipeline flow (force=True for the explicit
        endpoint); non-fatal."""
        if not force and not settings.evaluator_enabled:
            return
        ws = workspace.scaffold(self.state)
        self._log("evaluator", "🔬 Évaluation du produit livré (exécution réelle)…")
        run_output = await self._aexercise_product()
        try:
            result = await self._tracked.arun(
                prompts.evaluator_probe(
                    self.state, workspace.package_name(self.state), run_output
                ),
                system_prompt=persona("evaluator"),
                cwd=ws,
            )
            reply = extract_json(result.text)
        except AgentError as exc:
            self._chat(ChatRole.SYSTEM, f"Évaluateur indisponible : {exc}")
            return
        message = reply.get("message", "")
        items = reply.get("findings") or []
        if not items:
            self._chat(ChatRole.QA, "🔬 " + (message or "Aucun problème détecté à l'exécution."))
            return
        taken = {f.id for f in self.state.findings}
        new_findings: list[Finding] = []
        for i, data in enumerate(items, start=1):
            fid = _unique_id(str(data.get("id") or f"FND-{len(taken) + i}"), "FND", taken)
            taken.add(fid)
            new_findings.append(
                Finding(
                    id=fid,
                    severity=str(data.get("severity") or "medium"),
                    kind=str(data.get("kind") or "bug"),
                    title=str(data.get("title") or "Finding"),
                    detail=str(data.get("detail") or ""),
                    iteration=self.state.iteration,
                )
            )
        self.state.findings.extend(new_findings)
        lines = [f"[{f.severity}/{f.kind}] {f.title} — {f.detail}" for f in new_findings]
        # Findings are evidence for the next analysis: surface them in the
        # feedback list (UI) on top of the evaluator's chat message.
        self.state.feedback.extend(lines)
        self._chat(
            ChatRole.QA,
            f"🔬 {message}\n" + "\n".join(f"• {line}" for line in lines),
        )
        self._sync()
        # Closed loop: route the findings through the impact pipeline so the
        # analyst amends an unimplemented story, plans new ones, or dismisses —
        # prioritizing observed evidence over hypotheses.
        combined = "Findings de l'évaluation du produit livré :\n" + "\n".join(
            f"- {line}" for line in lines
        )
        await self._aimpact_analysis(combined)

    # ----------------------------------------- security & supply-chain (S1)

    async def asecurity_review(self) -> None:
        """Run the security & supply-chain review on demand (background): audit
        the generated code + dependencies and feed findings into the impact
        pipeline.

        Raises ValueError (-> 409) while the pipeline is actively building or
        when a review is already running."""
        if self.state.phase in (
            PipelinePhase.SPEC,
            PipelinePhase.ANALYZE,
            PipelinePhase.PLAN,
            PipelinePhase.ARCHITECT,
            PipelinePhase.BUILD,
        ):
            raise ValueError("la pipeline est active : attends la fin avant la revue sécurité")
        if self._security_task and not self._security_task.done():
            raise ValueError("une revue sécurité est déjà en cours")
        self._security_task = asyncio.create_task(self._asecurity_task())

    async def _asecurity_task(self) -> None:
        try:
            await self._asecurity_phase(force=True)
        except Exception as exc:  # background task: surface, never crash silently
            self._chat(ChatRole.SYSTEM, f"Erreur de la revue sécurité : {exc}")

    async def _arun_dep_audit(self) -> str:
        """Best-effort supply-chain audit of the generated workspace: `pip-audit`
        for the Python project, `npm audit` when a package.json exists. These only
        read manifests/lockfiles (the untrusted app is never executed) and run
        with a minimal env + wall-clock cap. Demo mode short-circuits."""
        if settings.fake_agents:
            return "mode démo : audit des dépendances court-circuité"
        ws = workspace_dir(self.state.id)
        env = _minimal_env()
        timeout = settings.security_audit_timeout_s

        def _run() -> str:
            parts: list[str] = []
            cmds = [("pip-audit", [settings.uv_cmd, "run", "pip-audit"])]
            if (ws / "package.json").exists():
                cmds.append(("npm audit", [settings.npm_cmd, "audit"]))
            for label, cmd in cmds:
                try:
                    proc = subprocess.run(
                        cmd, cwd=str(ws),
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        env=env, text=True, encoding="utf-8", errors="replace",
                        timeout=timeout,
                    )
                    parts.append(f"$ {label} (code {proc.returncode})\n{proc.stdout[-2000:]}")
                except subprocess.TimeoutExpired:
                    parts.append(f"$ {label} : timeout après {timeout:g}s")
                except OSError as exc:
                    parts.append(f"$ {label} : indisponible ({exc})")
            return "\n\n".join(parts) or "(aucun audit de dépendances exécuté)"

        return await asyncio.to_thread(_run)

    async def _asecurity_phase(self, force: bool = False) -> None:
        """Audit the delivered code + dependencies for security weaknesses and
        turn the review into structured findings, then feed them into the
        feedback-impact pipeline (E2) as evidence. Env-gated in the pipeline flow
        (force=True for the explicit endpoint); non-fatal."""
        if not force and not settings.security_review_enabled:
            return
        ws = workspace.scaffold(self.state)
        self._log("security", "🔒 Revue sécurité & supply-chain du produit livré…")
        audit_output = await self._arun_dep_audit()
        try:
            result = await self._tracked.arun(
                prompts.security_review_probe(
                    self.state, workspace.package_name(self.state), audit_output
                ),
                system_prompt=persona("security-reviewer"),
                cwd=ws,
            )
            reply = extract_json(result.text)
        except AgentError as exc:
            self._chat(ChatRole.SYSTEM, f"Auditeur sécurité indisponible : {exc}")
            return
        message = reply.get("message", "")
        items = reply.get("findings") or []
        if not items:
            self._chat(ChatRole.QA, "🔒 " + (message or "Aucune faille de sécurité détectée."))
            return
        taken = {f.id for f in self.state.findings}
        new_findings: list[Finding] = []
        for i, data in enumerate(items, start=1):
            fid = _unique_id(str(data.get("id") or f"SEC-{len(taken) + i}"), "SEC", taken)
            taken.add(fid)
            new_findings.append(
                Finding(
                    id=fid,
                    severity=str(data.get("severity") or "medium"),
                    kind=str(data.get("kind") or "security"),
                    title=str(data.get("title") or "Finding"),
                    detail=str(data.get("detail") or ""),
                    iteration=self.state.iteration,
                )
            )
        self.state.findings.extend(new_findings)
        lines = [f"[{f.severity}/{f.kind}] {f.title} — {f.detail}" for f in new_findings]
        self.state.feedback.extend(lines)
        self._chat(
            ChatRole.QA,
            f"🔒 {message}\n" + "\n".join(f"• {line}" for line in lines),
        )
        self._sync()
        combined = "Findings de la revue sécurité du produit livré :\n" + "\n".join(
            f"- {line}" for line in lines
        )
        await self._aimpact_analysis(combined)

    # --------------------------------------------- factory retrospective (E7)

    async def aretrospect(self) -> None:
        """Run the factory retrospective on demand (background).

        Raises ValueError (-> 409) while the pipeline is actively building or
        when a retrospective is already running."""
        if self.state.phase in (
            PipelinePhase.SPEC,
            PipelinePhase.ANALYZE,
            PipelinePhase.PLAN,
            PipelinePhase.ARCHITECT,
            PipelinePhase.BUILD,
        ):
            raise ValueError("la pipeline est active : attends la fin avant la rétrospective")
        if self._retro_task and not self._retro_task.done():
            raise ValueError("une rétrospective est déjà en cours")
        self._retro_task = asyncio.create_task(self._aretro_task())

    async def _aretro_task(self) -> None:
        try:
            await self._aretro_phase(force=True)
        except Exception as exc:  # background task: surface, never crash silently
            self._chat(ChatRole.SYSTEM, f"Erreur de la rétrospective : {exc}")

    async def _aretro_phase(self, force: bool = False) -> None:
        """Mine the just-finished iteration's build signals into durable lessons
        (persisted on the state, injected into the next QA/Dev prompts) and
        tuning recommendations (surfaced in the UI). Env-gated in the pipeline
        flow (force=True for the explicit endpoint); non-fatal."""
        if not force and not settings.retro_enabled:
            return
        try:
            result = await self._tracked.arun(
                prompts.retro_review(self.state),
                system_prompt=persona("retro"),
            )
            reply = extract_json(result.text)
        except AgentError as exc:
            self._log("retro", f"Rétrospective indisponible ({exc}) — pas de leçon.")
            return
        lessons = [str(x).strip() for x in (reply.get("lessons") or []) if str(x).strip()]
        recommendations = [
            str(x).strip() for x in (reply.get("recommendations") or []) if str(x).strip()
        ]
        # The agent returns the COMPLETE lesson list to keep (it replaces the
        # previous one), deduplicated and capped to bound prompt growth.
        deduped: list[str] = []
        for lesson in lessons:
            if lesson not in deduped:
                deduped.append(lesson)
        self.state.lessons = deduped[: settings.retro_max_lessons]
        lesson_store.add_global_lessons(self.state.lessons)  # F1: shared library
        self.state.retro_recommendations = recommendations
        message = reply.get("message", "")
        body = ""
        if self.state.lessons:
            body += "\n📚 Leçons :\n" + "\n".join(f"• {l}" for l in self.state.lessons)
        if recommendations:
            body += "\n🛠 Recommandations :\n" + "\n".join(f"• {r}" for r in recommendations)
        self._chat(
            ChatRole.ANALYST,
            f"🔁 Rétrospective d'usine — {message or 'rien de notable.'}{body}",
        )
        self._sync()

    # ------------------------------------------------------------ lifecycle

    def _apply_definition_of_done(self, *, all_iterations: bool = False) -> bool:
        """Run the deterministic delivery gate and persist its latest verdict.

        The orchestrator already verifies the test suite story by story; this
        pass answers the delivery-level question before the project can be
        declared done: every planned story/task must be effectively shipped, and
        user-facing acceptance evidence must be present enough to trust.
        """
        if not self._setting("definition_of_done_enabled"):
            delivery_state.mark_ready(self.state)
            return True
        result = evaluate_definition_of_done(
            self.state,
            iteration=None if all_iterations else self.state.iteration,
            require_ui_evidence=self._setting("ui_tests_enabled"),
            strict_criteria=self._setting("definition_of_done_strict_criteria"),
            partial=self._setting("partial_delivery_enabled"),
        )
        delivery_state.apply_definition_result(self.state, result)
        self._report_traceability(all_iterations)
        self._log_cost_counterfactual()
        if result.blockers:
            self._delivery_blocked = True
            detail = "\n".join(f"- {i.message}" for i in result.blockers[:8])
            more = "" if len(result.blockers) <= 8 else f"\n- … {len(result.blockers) - 8} autre(s)"
            self.state.error = ""
            self._log("delivery", "Definition of Done bloquée.")
            self._chat(
                ChatRole.SYSTEM,
                f"⛔ Definition of Done bloquée : {len(result.blockers)} blocker(s).\n"
                f"{detail}{more}",
            )
            self._notify("error", "Livraison bloquée", result.blockers[0].message[:200])
            return False
        if result.partial:
            detail = "\n".join(f"- {i.message}" for i in result.warnings[:6])
            self._log("delivery", "Livraison PARTIELLE acceptée.")
            self._chat(
                ChatRole.SYSTEM,
                f"📦 Livraison partielle : le projet livre ses stories vertes, "
                f"les échecs restent visibles et relançables.\n{detail}",
            )
            self._notify("warning", "Livraison partielle", result.warnings[0].message[:200])
        elif result.warnings:
            detail = "\n".join(f"- {i.message}" for i in result.warnings[:5])
            self._log("delivery", "Definition of Done OK avec avertissements.")
            self._chat(ChatRole.SYSTEM, f"⚠️ Definition of Done OK avec avertissements.\n{detail}")
        else:
            self._log("delivery", "Definition of Done OK.")
        self._sync()
        return True

    async def _adelivery_gates(self, *, all_iterations: bool = False) -> bool:
        """Run the FULL delivery-gate chain on the current iteration:
        smoke run → runtime acceptance → Definition of Done → Docker delivery.

        Single source of truth for gate ORDER, shared by the main lifecycle and
        the rebuild/resume finishers — an iteration completed through a story
        rebuild or a resume-build must pass exactly the same gates as one built
        in a single run (they used to skip smoke/runtime/docker entirely).
        Returns False when a gate blocked the delivery (phase handling stays
        the caller's job)."""
        # Runnability gate: boot the delivered app; a non-runnable build fails
        # the iteration like a red test (no-op unless SMOKE_RUN).
        if not await self._asmoke_phase():
            return False
        if not await self._aruntime_acceptance_phase():
            return False
        if not self._apply_definition_of_done(all_iterations=all_iterations):
            return False
        # Docker delivery gate (D1): build the accepted delivery into an image,
        # deploy it on the shared network and network-verify it; a failure parks
        # the iteration in needs_attention (no-op unless DOCKER_DELIVERY /
        # non-web project).
        return await self._adocker_delivery_phase()

    async def _alifecycle(self) -> None:
        try:
            self._delivery_blocked = False
            self._profile_overrides = profiles.resolve_overrides(self.state)
            applied_profile = self._profile_overrides
            if applied_profile:
                self._log(
                    "profile",
                    f"Profil produit '{self.state.product_profile}' appliqué : "
                    + ", ".join(f"{k}={v}" for k, v in sorted(applied_profile.items())),
                )
            await self._abrownfield_init()
            brief = await self._aspec_phase()
            if brief is None:  # stopped during interview
                self.state.phase = PipelinePhase.STOPPED
                self._sync()
                return
            await self._aselect_language()
            # ST-4: pick the project's work streams (gated; no-op when off).
            await self._aselect_streams()
            # Scaffold the skeleton ONLY after the backend language is chosen —
            # scaffold() dispatches on it, so doing this earlier (when the
            # language is still the Python default) left a stray Python skeleton
            # (main.py, pyproject.toml, package dir) inside Go/Rust workspaces.
            workspace.scaffold(
                self.state,
                streams_enabled=self._setting("streams_enabled"),
                ui_tests_enabled=self._setting("ui_tests_enabled"),
            )
            await self._apropose_components()

            while not self._stop_requested:
                await self._checkpoint()
                if self._stop_requested:
                    break
                await self._aplan_phase()
                await self._aarchitect_phase()
                await self._aapproval_gate("plan")
                if self._stop_requested:
                    break
                await self._abuild_phase()
                if self._delivery_blocked:
                    break
                if not await self._adelivery_gates():
                    break
                await self._adocument_phase()
                # Closed-loop product evaluation (E6): exercise the delivered
                # iteration and feed findings into the impact pipeline.
                await self._aevaluate_phase()
                # Security & supply-chain review (S1): audit the delivered
                # code and dependencies, feeding findings into the impact pipeline.
                await self._asecurity_phase()
                # Factory retrospective (E7): distil this iteration's signals
                # into durable lessons before the next one starts.
                await self._aretro_phase()
                await self._asnapshot_iteration()
                if not self.state.auto_spec or self._stop_requested:
                    break
                await self._anext_feature_phase()

            if self._stop_requested:
                self._reset_inflight_items()
            if self._stop_requested:
                self.state.phase = PipelinePhase.STOPPED
            elif self._delivery_blocked:
                self.state.phase = PipelinePhase.NEEDS_ATTENTION
            else:
                self.state.phase = PipelinePhase.DONE
            self._chat(
                ChatRole.SYSTEM,
                "Itération terminée." if self.state.phase == PipelinePhase.DONE
                else (
                    "Itération à reprendre : livraison non validée."
                    if self._delivery_blocked
                    else "Boucle arrêtée par l'utilisateur."
                ),
            )
            if self.state.phase == PipelinePhase.DONE:
                self._notify("success", "Itération terminée", self.state.name)
            self.monitor.event(
                "outcome", result=self.state.phase.value,
                stories=[{"id": s.id, "status": s.status.value} for s in self.state.stories],
            )
        except DeliveryBlocked:
            self.state.phase = PipelinePhase.NEEDS_ATTENTION
            self.state.error = ""
            self._chat(ChatRole.SYSTEM, "Itération à reprendre : livraison non validée.")
            self.monitor.event(
                "outcome", result=self.state.phase.value,
                stories=[{"id": s.id, "status": s.status.value} for s in self.state.stories],
            )
        except Exception as exc:  # surface any pipeline failure to the UI
            if self._stop_requested:
                # A hard interrupt (project switch / shutdown) kills the in-flight
                # agent CLI, which surfaces here as an AgentError — that's an
                # interruption, not a failure: end cleanly as STOPPED.
                self._reset_inflight_items()
                self.state.phase = PipelinePhase.STOPPED
                self._chat(ChatRole.SYSTEM, "Boucle interrompue par l'utilisateur.")
            else:
                self.state.phase = PipelinePhase.ERROR
                # Some exceptions stringify to "" (e.g. bare TimeoutError); fall
                # back to repr/type so the UI never shows a detail-less error.
                detail = str(exc) or repr(exc) or type(exc).__name__
                self.state.error = detail
                self._chat(ChatRole.SYSTEM, f"Erreur pipeline : {detail}")
                self._notify("error", "Erreur pipeline", f"{self.state.name} : {detail}"[:200])
            self.monitor.event(
                "outcome", result=self.state.phase.value,
                error=self.state.error,
                stories=[{"id": s.id, "status": s.status.value} for s in self.state.stories],
            )

    # ------------------------------------------------------------ SPEC (PM)

    async def _aspec_phase(self) -> str | None:
        self.state.phase = PipelinePhase.SPEC
        self._sync()
        if self.state.brief.strip():
            # I3: an imported / pre-seeded brief skips the PM interview.
            self._chat(ChatRole.PM, "📥 Brief importé — passage direct à la planification.")
            return self.state.brief
        if settings.brainstorm_assist_enabled:
            # B-IDEA: classify the idea; a vague one triggers a brainstorming
            # (offered, or run autonomously) before the spec loop.
            outcome = await self._abrainstorm_assist()
            if outcome == "done":  # a brief was synthesized autonomously
                return self.state.brief
            if outcome == "stopped":
                return None
            # "interactive" -> fall through to the interview/brainstorm loop
        while not self._stop_requested:
            # Brainstorming re-questions the need itself (BMAD analyst persona);
            # interview is the Socratic spec facilitation (PM persona).
            if self.state.spec_mode == "brainstorm":
                prompt, sys_persona = prompts.pm_brainstorm(self.state), persona("analyst")
            else:
                prompt, sys_persona = prompts.pm_interview(self.state), persona("pm")
            result = await self._tracked.arun(
                prompt,
                system_prompt=sys_persona,
                session_id=self._pm_session,
            )
            self._pm_session = result.session_id
            reply = extract_json(result.text)
            message = reply.get("message", "")
            if message:
                self._chat(ChatRole.PM, message)
            if reply.get("type") == "brief":
                self.state.brief = reply.get("brief", "")
                self._sync()
                return self.state.brief
            # type == "question": wait for the user's answer (already appended
            # to the chat by asend_user_message; the PM rereads it from there).
            await self._user_messages.get()
            if self._stop_requested:
                return None
        return None

    async def _abrainstorm_assist(self) -> str:
        """B-IDEA: assess the idea's maturity; when vague, offer a brainstorming
        session (or run it autonomously). Returns ``"interactive"`` (continue the
        normal spec loop), ``"done"`` (a brief was synthesized) or ``"stopped"``.
        Non-fatal: any agent error falls back to the plain interview."""
        try:
            res = await self._tracked.arun(
                prompts.assess_idea(self.state),
                system_prompt=persona("analyst"),
                session_id=self._pm_session,
            )
            self._pm_session = res.session_id
            assess = extract_json(res.text)
        except AgentError as exc:
            self._chat(ChatRole.SYSTEM, f"Évaluation de l'idée indisponible : {exc}")
            return "interactive"

        self.state.idea_maturity = (assess.get("maturity") or "structured").strip().lower()
        self.state.idea_rationale = assess.get("rationale", "")
        self.state.brainstorm_techniques = [t for t in (assess.get("techniques") or []) if t][:5]

        if self.state.idea_maturity == "vague":
            tline = (
                " Techniques proposées : " + ", ".join(self.state.brainstorm_techniques) + "."
                if self.state.brainstorm_techniques
                else ""
            )
            self._chat(
                ChatRole.ANALYST,
                f"🔎 Idée encore ouverte — {self.state.idea_rationale}{tline}",
            )
        else:
            self._chat(
                ChatRole.ANALYST,
                f"🔎 Idée déjà cadrée — {self.state.idea_rationale} On spécifie directement.",
            )
        self._sync()

        if self.state.idea_maturity != "vague":
            return "interactive"

        # Vague idea. Auto-spec runs the brainstorming autonomously without
        # asking; otherwise we offer the choice and wait for the user.
        if not self.state.auto_spec:
            self.state.awaiting_brainstorm_decision = True
            self._chat(
                ChatRole.SYSTEM,
                "💡 Idée à affiner — veux-tu une session de brainstorming ? "
                "« Oui » : on explore ensemble (je te pose des questions). "
                "« Non » : je l'affine en autonomie.",
            )
            self._sync()
            self._brainstorm_event.clear()
            await self._brainstorm_event.wait()
            self.state.awaiting_brainstorm_decision = False
            if self._stop_requested:
                return "stopped"
            if self._brainstorm_accepted:
                self.state.spec_mode = "brainstorm"
                self._chat(
                    ChatRole.SYSTEM,
                    "🧠 Brainstorming interactif — affinons l'idée ensemble.",
                )
                self._sync()
                return "interactive"

        brief = await self._aself_brainstorm()
        return "stopped" if brief is None else "done"

    async def _aself_brainstorm(self) -> str | None:
        """B-IDEA: autonomous brainstorming. The analyst diverges/converges with
        the chosen techniques and an AI plays the product owner answering, for a
        few rounds, then the brief is synthesized. Returns the brief, or None if
        stopped."""
        self._chat(
            ChatRole.ANALYST,
            "🧠 Brainstorming autonome : j'explore et je réponds à ta place pour affiner l'idée.",
        )
        self._sync()
        rounds = settings.brainstorm_auto_rounds
        for i in range(rounds):
            if self._stop_requested:
                return None
            res = await self._tracked.arun(
                prompts.pm_brainstorm(self.state, force_brief=(i == rounds - 1)),
                system_prompt=persona("analyst"),
                session_id=self._pm_session,
            )
            self._pm_session = res.session_id
            reply = extract_json(res.text)
            message = reply.get("message", "")
            if message:
                self._chat(ChatRole.ANALYST, message)
            if reply.get("type") == "brief":
                self.state.brief = reply.get("brief", "")
                self._sync()
                return self.state.brief
            # The AI answers the analyst's question (plays the product owner).
            try:
                ans = await self._tracked.arun(
                    prompts.brainstorm_auto_answer(self.state, message),
                    system_prompt=persona("pm"),
                )
                answer = ans.text.strip()
            except AgentError:
                answer = "(pas de réponse — poursuis avec des hypothèses raisonnables.)"
            if answer:
                self._chat(ChatRole.USER, f"🤖 {answer}")
                self._sync()

        # Safety net: force a brief if the loop ended without one.
        try:
            res = await self._tracked.arun(
                prompts.pm_brainstorm(self.state, force_brief=True),
                system_prompt=persona("analyst"),
                session_id=self._pm_session,
            )
            self.state.brief = extract_json(res.text).get("brief", "") or self.state.goal
        except AgentError:
            self.state.brief = self.state.goal
        self._sync()
        return self.state.brief

    # ------------------------------------------------------------ PLAN (PO)

    async def _amaybe_build_constitution(self) -> None:
        """W3 — derive the project constitution once (after SPEC, before PLAN) and
        COMPILE it: executable rules become pytest files under tests/constitution/
        (they then ride the normal suite every round with zero new enforcement),
        command rules feed the delivery gate, and non-compilable rules become
        advisory guidance injected into the dev/QA prompts. Best-effort; a failure
        never blocks planning."""
        if not settings.constitution_enabled or self.state.constitution:
            return
        try:
            rules = await constitution_lib.aderive_constitution(
                self._tracked,
                brief=self.state.brief or self.state.goal,
                project_name=self.state.name,
                max_rules=settings.constitution_max_rules,
            )
        except AgentError as exc:
            self._log("constitution", f"Constitution indisponible ({exc}) — ignorée.")
            return
        if not rules:
            return
        compiled = constitution_lib.compile_rules(rules)
        ws = workspace_dir(self.state.id)
        written: list[str] = []
        for rel, content in compiled.get("tests", []):
            try:
                p = ws / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(content, encoding="utf-8")
                written.append(rel)
            except OSError:
                continue
        self.state.constitution = rules
        self.state.constitution_test_paths = written
        # Advisory (non-executable) rules → build guidance, so dev/QA see them.
        for r in compiled.get("advisory", []):
            g = f"[Constitution] {r.get('statement', '')}".strip()
            if g and g not in self.state.build_guidance:
                self.state.build_guidance.append(g)
        self._log(
            "constitution",
            f"Constitution : {len(written)} règle(s) exécutable(s) sous "
            f"tests/constitution/, {len(compiled.get('commands', []))} commande(s), "
            f"{len(compiled.get('advisory', []))} advisory.",
        )
        self.monitor.event(
            "constitution", rules=len(rules), tests=len(written),
            commands=len(compiled.get("commands", [])),
            advisory=len(compiled.get("advisory", [])),
        )
        self._sync()

    async def _aplan_phase(self) -> None:
        self.state.phase = PipelinePhase.PLAN
        self._sync()
        pkg = workspace.package_name(self.state)
        await self._amaybe_build_constitution()  # W3: standard-once, enforced every round
        plan: dict = {}
        # PO pipeline (RFC po-pipeline-v2): the multi-stage PO replaces the
        # mono-pass maker AND its judge-first review (_arefine_plan). Any
        # skeleton-stage failure falls back to the legacy path — a stage
        # exception never abandons the plan.
        pipeline_used = False
        if self._setting("po_pipeline") == "on":
            try:
                plan, report = await plan_pipeline.arun_po_pipeline(
                    self._tracked,
                    self.state,
                    pkg,
                    workspace_root=workspace_dir(self.state.id),
                    log=self._log,
                )
                pipeline_used = True
                self.state.calibration_for().degradations += len(report.degradations)
                if report.cross_issues:
                    # Surface the transversal review in the UI « Revue du plan » panel.
                    self.state.plan_review_issues = list(report.cross_issues)
                self._chat(
                    ChatRole.PO,
                    f"Pipeline PO ({report.mode}) : {report.leaves} feuille(s), "
                    f"{len(report.resizes)} resize, {len(report.flagged)} re-spéc ciblée(s), "
                    f"{len(report.degradations)} dégradation(s).",
                )
            except plan_pipeline.PlanPipelineError as exc:
                self._log("po-pipeline", f"Pipeline PO en échec ({exc}) — repli sur le PO mono-passe.")
        if not pipeline_used:
            result = await self._tracked.arun(
                prompts.po_plan(self.state, pkg),
                system_prompt=persona("sm"),
            )
            plan_text = await self._arefine_plan(result.text, pkg)
            plan = extract_json(plan_text)
        # The PO of a later iteration typically numbers from "US-1"/"EPIC-1"
        # again: deduplicate against previous iterations (else state.story()
        # becomes ambiguous and feature files get overwritten), remapping the
        # plan's internal depends_on through any rename.
        taken_story_ids = {s.id for s in self.state.stories}
        taken_epic_ids = {e.id for e in self.state.epics}
        id_map: dict[str, str] = {}  # PO-chosen story id -> final unique id
        planned: list[tuple[str, str, dict]] = []  # (epic_id, story_id, story_data)
        # ST-5: task ids must be unique project-wide; their depends_on (task ids)
        # are remapped through the same rename. Seed with existing project tasks.
        taken_task_ids = {t.id for t in self.state.all_tasks()}
        task_id_map: dict[str, str] = {}  # PO-chosen task id -> final unique id
        # The PO pipeline decomposes stories into tasks regardless of the
        # streams flag (S1 owns the granularity); the legacy path keeps the
        # streams gate so the flag-off parse stays byte-identical.
        parse_tasks = pipeline_used or self._setting("streams_enabled")
        for epic_data in plan.get("epics", []):
            epic_id = _unique_id(
                epic_data.get("id") or f"EPIC-{len(taken_epic_ids) + 1}",
                "EPIC",
                taken_epic_ids,
            )
            taken_epic_ids.add(epic_id)
            self.state.epics.append(
                Epic(
                    id=epic_id,
                    title=epic_data.get("title", "Epic"),
                    description=epic_data.get("description", ""),
                    iteration=self.state.iteration,
                )
            )
            for story_data in epic_data.get("stories", []):
                raw_id = story_data.get("id") or f"US-{len(taken_story_ids) + 1}"
                story_id = _unique_id(raw_id, "US", taken_story_ids)
                taken_story_ids.add(story_id)
                id_map.setdefault(raw_id, story_id)
                # First pass: register the unique id of every task so cross-task
                # depends_on (declared anywhere in the plan) remap consistently.
                if parse_tasks:
                    for n, task_data in enumerate(story_data.get("tasks") or [], start=1):
                        raw_tid = str(task_data.get("id") or f"T-{len(taken_task_ids) + 1}")
                        tid = _unique_id(raw_tid, "T", taken_task_ids)
                        taken_task_ids.add(tid)
                        task_id_map.setdefault(raw_tid, tid)
                planned.append((epic_id, story_id, story_data))

        def _build_tasks(story_id: str, story_data: dict) -> list[Task]:
            """ST-5: parse a US's decomposition into Task models, remapping task
            depends_on through the project-wide rename. Empty unless streams on
            (or the plan came from the PO pipeline, whose S1 owns granularity)."""
            if not parse_tasks:
                return []
            out: list[Task] = []
            for task_data in story_data.get("tasks") or []:
                raw_tid = str(task_data.get("id") or "")
                tid = task_id_map.get(raw_tid, raw_tid)
                out.append(
                    Task(
                        id=tid,
                        story_id=story_id,
                        stream=str(task_data.get("stream") or ""),
                        title=task_data.get("title", ""),
                        description=task_data.get("description", ""),
                        acceptance_criteria=_acceptance_list(
                            task_data.get("acceptance_criteria", [])
                        ),
                        gherkin=task_data.get("gherkin", ""),
                        depends_on=[task_id_map.get(d, d) for d in task_data.get("depends_on", [])],
                        files_hint=[
                            str(g) for g in (task_data.get("file_globs") or []) if str(g).strip()
                        ],
                        complexity=str(task_data.get("complexity") or ""),
                        estimated_files=int(task_data.get("estimated_files") or 0),
                    )
                )
            # P4b: serialize file-overlapping tasks of THIS story (the deterministic
            # floor; trusts but verifies the PO's depends_on).
            self._enforce_task_independence(out, label=story_id)
            return out

        new_stories = [
            UserStory(
                id=story_id,
                epic_id=epic_id,
                title=story_data.get("title", "Story"),
                description=story_data.get("description", ""),
                acceptance_criteria=_acceptance_list(
                    story_data.get("acceptance_criteria", [])
                ),
                gherkin=story_data.get("gherkin", ""),
                # Deps use the PO's ids: follow renames for the plan's own
                # stories; ids of previous-iteration stories pass through.
                depends_on=[id_map.get(d, d) for d in story_data.get("depends_on", [])],
                priority=_clamp_1_5(story_data.get("priority", 3)),
                ui=bool(story_data.get("ui", False)),
                # ST-5: stream tagging + optional task decomposition (gated; "" /
                # [] when off, so the flag-off parse is byte-identical to today).
                stream=str(story_data.get("stream") or "") if parse_tasks else "",
                tasks=_build_tasks(story_id, story_data),
                # PO pipeline: first-order complexity + S2 degradation marker
                # ("" / 0 / False on the legacy path — fields simply absent).
                complexity=str(story_data.get("complexity") or ""),
                estimated_files=int(story_data.get("estimated_files") or 0),
                spec_incomplete=bool(story_data.get("spec_incomplete", False)),
                iteration=self.state.iteration,
                # RFC technical-stories: the PO/critic may emit a Technical Story
                # (a non-functional container of tasks) up-front, not only via the
                # reactive split. Gated on streams (a TS without tasks is pointless).
                technical=bool(story_data.get("technical", False)) and self._setting("streams_enabled"),
                contract=str(story_data.get("contract") or "") if self._setting("streams_enabled") else "",
            )
            for epic_id, story_id, story_data in planned
        ]
        # Deps may point to already-done stories from previous iterations.
        scheduler.sanitize_dependencies(self.state.stories + new_stories)
        self.state.stories.extend(new_stories)
        workspace.write_feature_files(self.state, new_stories)
        # ST-5: sanity-check the produced work graph (dangling deps / cycle).
        if self._setting("streams_enabled"):
            for w in work_streams.validate(self.state):
                self._log("streams", f"Graphe de tâches : {w}")
        n_tasks = sum(len(s.tasks) for s in new_stories)
        task_note = f", {n_tasks} tâche(s)" if n_tasks else ""
        self._chat(
            ChatRole.PO,
            f"Plan de l'itération {self.state.iteration} : "
            f"{len(plan.get('epics', []))} epic(s), {len(new_stories)} user story(ies){task_note}.",
        )

    # ------------------------------------------------------ ARCHITECT (design)

    async def _aarchitect_phase(self) -> None:
        """Optional Architect phase: produce a concise technical design injected
        into the QA and Dev prompts. OFF by default; a design failure is
        non-fatal (the build proceeds without an architecture context)."""
        if not self._setting("architecture_enabled"):
            return
        self.state.phase = PipelinePhase.ARCHITECT
        self._sync()
        try:
            result = await self._tracked.arun(
                prompts.architect_design(self.state, workspace.package_name(self.state)),
                system_prompt=persona("architect"),
            )
            data = extract_json(result.text)
        except AgentError as exc:
            self._log("architect", f"Architecte indisponible ({exc}) — build sans design.")
            return
        self.state.architecture = data.get("design", "")
        self._chat(
            ChatRole.ARCHITECT,
            f"{data.get('message', '')}\n{self.state.architecture[:400]}",
        )

    # ----------------------------------------------------- refinement harness

    def _effective_lessons(self) -> list[str]:
        """This project's lessons (E7) plus the shared cross-project library
        (F1), deduplicated — the lessons injected into Dev/QA prompts."""
        combined = list(self.state.lessons)
        if settings.shared_lessons_enabled:
            for item in lesson_store.load_global_lessons():
                if item not in combined:
                    combined.append(item)
        return combined

    def _emit_refine(self, role: str, message: str) -> None:
        self._chat(_REFINE_ROLE_TO_CHAT.get(role, ChatRole.SYSTEM), message)

    async def _arefine_plan(self, initial_text: str, pkg: str) -> str:
        async def _revise(previous: str, critique: str) -> str:
            res = await self._tracked.arun(
                prompts.po_revise(self.state, pkg, previous, critique),
                system_prompt=persona("sm"),
            )
            return res.text

        outcome = await refine.arefine(
            self._tracked,
            role="po",
            kind="le plan produit (epics & user stories)",
            criteria=prompts.PLAN_CRITERIA,
            initial_text=initial_text,
            revise=_revise,
            emit=self._emit_refine,
        )
        if outcome.stopped_reason != "disabled":
            self.state.plan_quality = outcome.score
            self.state.plan_review_issues = list(outcome.issues)
            self.state.plan_review_suggestions = list(outcome.suggestions)
            n = len(outcome.issues)
            self._chat(
                ChatRole.SYSTEM,
                f"Revue du plan en {outcome.rounds} tour(s) — qualité {outcome.score}/100, "
                f"{n} point(s) signalé(s) (arrêt : {outcome.stopped_reason}).",
            )
        return outcome.text

    async def _arefine_code(self, story: UserStory, pkg: str, ws) -> None:
        """Critic/judge loop over a green story's code, with a git snapshot
        guard so a revision that breaks the suite is rolled back."""
        if not await self._agit_snapshot(ws, story.id):
            self._log(f"dev:{story.id}", "Raffinement code ignoré (git indisponible).")
            return

        async def _revise(previous: str, critique: str) -> str:
            res = await self._tracked.arun(
                prompts.dev_revise(
                    story, pkg, workspace.feature_rel_path(story), critique,
                    architecture=self.state.architecture,
                    guidance="\n".join(self.state.build_guidance),
                    lessons="\n".join(self._effective_lessons()),
                    available_skills=self._skills_catalog("dev"),
                ),
                system_prompt=persona("dev"),
                cwd=ws,
            )
            return res.text

        async def _accept(_revised: str) -> bool:
            ok, _, _ = await self._arun_pytest(ws=ws)
            if ok:
                await self._agit(ws, "add", "-A")
                await self._agit(ws, "commit", "-m", f"refined {story.id}", "--allow-empty")
            return ok

        async def _rollback() -> None:
            await self._agit(ws, "reset", "--hard", "HEAD")
            await self._agit(ws, "clean", "-fd")

        # W5.3 checker independence: give the critic the ACTUAL changes (the last
        # commit's diff), not the dev's self-narrative, so its review targets what
        # really changed. The critic still reads the files in cwd too.
        _, diff = await self._agit(ws, "show", "--stat", "--patch", "HEAD")
        diff_block = f"\n\nDiff des changements (git show HEAD) :\n{(diff or '')[:8000]}" if diff else ""
        try:
            outcome = await refine.arefine(
                self._tracked,
                role="dev",
                kind=f"le code produit pour la story {story.id} (fichiers dans le répertoire courant)",
                criteria=prompts.CODE_CRITERIA,
                initial_text=(
                    f"Code de la story {story.id} — lis les fichiers du répertoire "
                    f"courant.{diff_block}"
                ),
                revise=_revise,
                accept=_accept,
                rollback=_rollback,
                cwd=ws,
                emit=self._emit_refine,
            )
        except AgentError as exc:
            # Refinement is opportunistic: a failure here must never downgrade
            # a story that already reached green. Restore the snapshot (the
            # revise agent may have partially rewritten the workspace).
            await _rollback()
            self._log(
                f"dev:{story.id}",
                f"Raffinement interrompu ({exc}) — retour à l'état vert.",
            )
            return
        if outcome.stopped_reason != "disabled":
            story.quality_score = outcome.score
            self._chat(
                ChatRole.SYSTEM,
                f"[{story.id}] Code raffiné en {outcome.rounds} tour(s) — "
                f"qualité {outcome.score}/100 (arrêt : {outcome.stopped_reason}).",
            )

    async def _arun_coverage(self, story: UserStory, pkg: str, ws) -> int:
        """Coverage gate (Q2): run the suite under coverage and record the total
        percentage on story.coverage_score. Returns the integer %% (or -1 when
        unavailable). Best-effort: a coverage-tooling failure returns -1 and never
        fails the story by itself (the gate decision is made by the caller)."""
        if not settings.coverage_enabled or settings.fake_agents:
            return -1
        if toolchain.normalize(self.state.backend_language.value) != "python":
            return -1  # pytest-cov is Python-only (L2g)
        # The report is written under cwd=ws (via report.name) and read back from
        # the same dir — ``ws`` may be a per-item worktree on the streams path.
        report = Path(ws) / ".autospec-cov.json"
        env = _minimal_env()
        cmd = [
            settings.uv_cmd, "run", "pytest",
            f"--cov={pkg}", "--cov-report", f"json:{report.name}", "-q",
        ]

        def _run():
            try:
                subprocess.run(
                    cmd, cwd=str(ws),
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    env=env, text=True, encoding="utf-8", errors="replace",
                    timeout=settings.agent_timeout_s,
                )
            except (OSError, subprocess.TimeoutExpired):
                return None
            try:
                data = json.loads(report.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return None
            return (data.get("totals") or {}).get("percent_covered")

        pct = await asyncio.to_thread(_run)
        if pct is None:
            return -1
        story.coverage_score = round(pct)
        self._sync()
        return story.coverage_score

    async def _arun_mutation_test(self, story: UserStory, pkg: str, ws) -> None:
        """Mutation testing (Q1): mutate the package source one point at a time
        and rerun the suite against each mutant; story.mutation_score = kill rate
        (%). Env-gated, best-effort (never downgrades a green story). Mutates +
        reruns pytest in ``ws``: the legacy path serializes it via the build lock
        (shared workspace), the streams path runs it inside the item's private
        worktree (no lock needed). Python-only."""
        if not settings.mutation_enabled or settings.fake_agents:
            return
        if toolchain.normalize(self.state.backend_language.value) != "python":
            return  # AST mutation engine is Python-only (L2g)
        pkg_dir = ws / pkg
        if not pkg_dir.is_dir():
            return
        sources = [
            f for f in sorted(pkg_dir.glob("*.py"))
            if f.name != "__init__.py" and f.read_text(encoding="utf-8").strip()
        ]
        cap = settings.mutation_max_mutants
        total = killed = 0
        for f in sources:
            if total >= cap:
                break
            original = f.read_text(encoding="utf-8")
            for _desc, mutant in mutation.generate_mutants(original, max_mutants=cap - total):
                if total >= cap:
                    break
                total += 1
                f.write_text(mutant, encoding="utf-8")
                try:
                    ok, _, _ = await self._arun_pytest(ws=ws)
                except Exception:  # noqa: BLE001 — runner glitch: count as survived
                    ok = True
                finally:
                    f.write_text(original, encoding="utf-8")  # always restore
                if not ok:
                    killed += 1
        if total:
            story.mutation_score = round(100 * killed / total)
            self._chat(
                ChatRole.SYSTEM,
                f"[{story.id}] 🧬 Mutation testing : {story.mutation_score}/100 "
                f"({killed}/{total} mutants tués).",
            )
            self._sync()

    async def _agit(self, ws, *args: str) -> tuple[int, str]:
        def _run() -> tuple[int, str]:
            try:
                proc = subprocess.run(
                    ["git", *args], cwd=str(ws),
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace",
                )
                return proc.returncode, proc.stdout
            except OSError as exc:
                return 127, str(exc)

        return await asyncio.to_thread(_run)

    async def _agit_ensure_repo(self, ws) -> bool:
        """Make sure ``ws`` is its OWN git work tree, initializing it (with an
        Autospec identity) if needed. Returns False only if ``git init`` fails.

        We must check that ``ws`` itself is a repo — NOT merely
        ``--is-inside-work-tree``, which is also true when the workspace is
        nested inside an enclosing repository (e.g. when ``workspace_root``
        lives inside the Autospec checkout). In that case ``git init`` would be
        skipped and every ``git add -A`` / ``commit`` here would pollute the
        parent repository with the user's working changes and our scaffold
        files — committed under the user's global git identity. Anchoring on
        ``ws/.git`` guarantees an isolated repo (and respects a brownfield repo
        that already carries its own ``.git``)."""
        if (ws / ".git").exists():
            await self._aignore_bookkeeping(ws)
            return True
        if (await self._agit(ws, "init"))[0] != 0:
            return False
        await self._agit(ws, "config", "user.email", "autospec@local")
        await self._agit(ws, "config", "user.name", "Autospec")
        await self._aignore_bookkeeping(ws)
        return True

    async def _aignore_bookkeeping(self, ws) -> None:
        """P0a: keep the volatile Autospec bookkeeping files OUT of the project
        git, once per process. `git add -A` re-commits already-tracked files even
        when gitignored, so an existing repo (created before this fix, or a
        brownfield one) must have them explicitly untracked — otherwise every
        worktree commit drags `autospec-state.json` / `autospec-interactions.jsonl`
        along and parallel work items conflict on them at merge time. Idempotent
        and best-effort; `--ignore-unmatch` makes the rm a no-op when untracked."""
        if self._bookkeeping_ignored:
            return
        self._bookkeeping_ignored = True
        # Ensure the ignore rules exist even for a brownfield repo with no/partial
        # .gitignore (the scaffold templates already carry them for greenfield).
        gitignore = Path(ws) / ".gitignore"
        try:
            existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
            missing = [
                line for line in (
                    "autospec-state.json", "autospec-interactions.jsonl",
                    "build-monitor.jsonl", ".autospec/",
                )
                if line not in existing.splitlines()
            ]
            if missing:
                sep = "" if (not existing or existing.endswith("\n")) else "\n"
                gitignore.write_text(existing + sep + "\n".join(missing) + "\n", encoding="utf-8")
        except OSError:
            pass
        await self._agit(
            ws, "rm", "--cached", "--ignore-unmatch", "-q", "--",
            "autospec-state.json", "autospec-interactions.jsonl",
            "build-monitor.jsonl",
        )

    async def _agit_snapshot(self, ws, label: str) -> bool:
        if not await self._agit_ensure_repo(ws):
            return False
        await self._agit(ws, "add", "-A")
        code, _ = await self._agit(ws, "commit", "-m", f"green {label}", "--allow-empty")
        return code == 0

    async def _acommit_wip(self, worktree, wid: str) -> None:
        """P2c: commit a RED attempt's partial work in its worktree so the
        branch can be preserved and RESUMED by the next attempt (targeted
        repair) instead of regenerating everything from scratch. Best-effort."""
        await self._agit(worktree, "add", "-A")
        await self._agit(worktree, "commit", "-m", f"wip {wid} (rouge)", "--allow-empty")

    async def _acommit_story(self, ws, sid: str) -> None:
        """Commit the workspace as the green state of a finished story.

        Best-effort: ensures the repo exists, then ``git add -A`` and an empty-
        allowed commit tagged ``story <sid> done`` so ``astory_diff`` can later
        recover this story's changes via ``git show``. Never raises."""
        if not await self._agit_ensure_repo(ws):
            return
        await self._agit(ws, "add", "-A")
        await self._agit(ws, "commit", "-m", f"story {sid} done", "--allow-empty")

    async def aexport_git(self) -> dict:
        """Clean git delivery of the generated workspace: ensure the repo
        exists, stage everything and commit. Returns the HEAD commit hash.
        Raises ValueError (-> 409) when git is unavailable."""
        ws = workspace_dir(self.state.id)
        if not await self._agit_ensure_repo(ws):
            raise ValueError("git indisponible dans le workspace")
        await self._agit(ws, "add", "-A")
        await self._agit(ws, "commit", "-m", "autospec: export du projet généré", "--allow-empty")
        code, out = await self._agit(ws, "rev-parse", "HEAD")
        return {"commit": out.strip() if code == 0 else ""}

    async def _asnapshot_iteration(self) -> None:
        """R2: commit the workspace as this iteration's snapshot, for rollback."""
        ws = workspace_dir(self.state.id)
        if not await self._agit_ensure_repo(ws):
            return
        await self._agit(ws, "add", "-A")
        await self._agit(
            ws, "commit", "-m", f"iteration {self.state.iteration} snapshot", "--allow-empty"
        )

    async def aiterations(self) -> list[int]:
        """R2: iteration numbers that have a workspace snapshot."""
        ws = workspace_dir(self.state.id)
        code, out = await self._agit(ws, "log", "--format=%s")
        if code != 0:
            return []
        found = set()
        for line in out.splitlines():
            m = re.match(r"iteration (\d+) snapshot", line.strip())
            if m:
                found.add(int(m.group(1)))
        return sorted(found)

    async def arollback(self, iteration: int) -> None:
        """R2: hard-reset the workspace to an iteration's snapshot commit. Raises
        ValueError (-> 409) while the pipeline is active or when the snapshot is
        missing."""
        if self.state.phase in (
            PipelinePhase.SPEC, PipelinePhase.ANALYZE, PipelinePhase.PLAN,
            PipelinePhase.ARCHITECT, PipelinePhase.BUILD,
        ):
            raise ValueError("la pipeline est active : impossible de revenir en arrière")
        ws = workspace_dir(self.state.id)
        code, out = await self._agit(
            ws, "log", "-1", "--format=%H", f"--grep=iteration {iteration} snapshot"
        )
        commit = out.strip()
        if code != 0 or not commit:
            raise ValueError(f"aucun snapshot pour l'itération {iteration}")
        await self._agit(ws, "reset", "--hard", commit)
        await self._agit(ws, "clean", "-fd")
        self._chat(
            ChatRole.SYSTEM, f"⏪ Workspace revenu au snapshot de l'itération {iteration}."
        )
        self._sync()

    async def astory_diff(self, sid: str) -> dict:
        """Return the git diff committed when a story reached DONE.

        Looks up the ``story <sid> done`` commit and returns its ``git show``
        output. Raises KeyError if the story is unknown. The diff is truncated
        beyond 200_000 characters. Returns ``{"available": False, "diff": ""}``
        when no such commit exists (git missing, or story never finished)."""
        self.state.story(sid)  # KeyError (-> 404) if absent
        ws = workspace_dir(self.state.id)
        code, out = await self._agit(
            ws, "log", "-1", "--format=%H", f"--grep=story {sid} done"
        )
        commit = out.strip()
        if code != 0 or not commit:
            return {"available": False, "diff": ""}
        _, diff = await self._agit(ws, "show", commit)
        return {"available": True, "diff": diff[:200_000]}

    # ------------------------------------------------------------ BUILD (Dev)

    async def _abuild_phase(self, all_iterations: bool = False) -> None:
        # ST-9: when streams are enabled, build the iteration's work items
        # (taskless US + tasks) in parallel, each in its OWN git worktree, and
        # merge them back into the project repo. Flag OFF keeps the legacy path
        # below byte-identical (the only behaviour the existing suite exercises).
        #
        # ``all_iterations`` widens the build pool from the current iteration to
        # EVERY story (used by retry-failed / resume-build): failures accumulate
        # across iterations, and dependency readiness needs the DONE stories of
        # earlier iterations in the pool to resolve (scheduler.ready_stories
        # derives "done" only from the pool it is given).
        caps = provider_capabilities(settings.agent_provider)
        if not settings.fake_agents and not caps.reliable_for_build:
            msg = (
                f"Provider '{settings.agent_provider}' non fiable pour le build : "
                f"{caps.notes}"
            )
            self._block_delivery(msg, source="provider")
            self._chat(ChatRole.SYSTEM, f"⛔ {msg}")
            self._notify("error", "Provider inadapté au build", msg[:200])
            return
        if self._setting("skills_enabled"):
            # SK-1: seed the workspace's `.claude/skills/` once so the headless
            # claude agent auto-discovers the skill library (best-effort, idempotent).
            await skill_lib.aseed_skills(workspace_dir(self.state.id))
            skill_check = skill_validation.validate_seeded_skills(workspace_dir(self.state.id))
            if not skill_check.ok:
                msg = "Validation des skills échouée : " + "; ".join(skill_check.messages()[:5])
                self._block_delivery(msg, source="skills")
                self._chat(ChatRole.SYSTEM, f"⛔ {msg}")
                self._notify("error", "Validation des skills échouée", msg[:200])
                return
        if self._setting("decompose_enabled"):
            # SK-2: split eligible backend stories into layered sub-tasks, then
            # let the parallel worktree engine build + aggregate them.
            await self._adecompose_pending(all_iterations=all_iterations)
        if self._setting("streams_enabled") or self._setting("decompose_enabled"):
            # P4d: optional LLM judge completes file claims + sharpens
            # serialization before the parallel scheduler (floor already safe).
            await self._ajudge_independence()
            # P1: global declared-overlap floor across ALL stories/streams (catches
            # shared repo-root files the per-story/per-stream view misses), after
            # the judge so it benefits from any completed claims.
            self._enforce_global_independence()
            await self._abuild_phase_streams(all_iterations=all_iterations)
            return
        self.state.phase = PipelinePhase.BUILD
        self._sync()
        self._start_tick()  # B5: heartbeat while building
        semaphore = asyncio.Semaphore(settings.max_parallel_devs)

        while not self._stop_requested:
            await self._checkpoint()  # honour pause between story batches
            if self._stop_requested:
                break
            # Recomputed every batch: the user may add stories mid-build.
            iteration_stories = (
                self.state.stories
                if all_iterations
                else self.state.stories_of_iteration(self.state.iteration)
            )
            pending = scheduler.pending_stories(iteration_stories)
            if not pending:
                break
            ready = scheduler.ready_stories(iteration_stories)
            if not ready:
                if any(s.status == StoryStatus.IN_PROGRESS for s in pending):
                    break  # defensive: a worker left a story in-flight
                # Remaining stories depend on failed work: mark them failed,
                # each carrying its ROOT failure (not just "unmet dependency").
                by_id = {s.id: s for s in iteration_stories}
                for story in pending:
                    story.status = StoryStatus.FAILED
                    root = scheduler.failed_root(story, by_id)
                    detail = (root.last_error or "").strip()[:300] if root else ""
                    story.last_error = (
                        "Dépendance non satisfaite (story échouée en amont)."
                        + (f" Cause racine : {root.id}" if root else "")
                        + (f" — {detail}" if detail else "")
                    )
                self._sync()
                break

            async def _aworker(story: UserStory) -> None:
                async with semaphore:
                    await self._abuild_story(story)

            await asyncio.gather(*(_aworker(s) for s in ready))

        self._stop_tick()  # B5: build batch loop done
        # Build directives are per-iteration; the next analysis uses `feedback`.
        self.state.build_guidance.clear()

    async def _abuild_story(self, story: UserStory) -> None:
        # O2: attribute every agent call made while building this story to it.
        # Isolated to this worker's Task context (see _BUILD_ITEM), so no reset.
        _BUILD_ITEM.set(story.id)
        story.status = StoryStatus.IN_PROGRESS
        story.attempts += 1
        # B1: a retry (attempts > 1) re-entering the build is a recovery state.
        if story.attempts > 1:
            self._set_recovery(
                story, "retry", attempt=story.attempts,
                max_attempts=settings.dev_max_attempts, sync=False,
            )
        # W1: escalation ladder — a retry climbs to a stronger model, so the
        # expensive model is only reached by a task the cheaper ones failed. Set
        # per this worker's Task context (like _BUILD_ITEM); attempt 1 stays on
        # the base rung (normal routing).
        if (
            story.attempts > 1
            and settings.escalate_on_retry_enabled
            and settings.model_ladder
        ):
            forced = recovery.ladder_model(story.attempts, settings.model_ladder)
            if forced:
                _FORCE_MODEL.set(forced)
                self.monitor.event(
                    "escalate", item=story.id, attempt=story.attempts, model=forced,
                )
                self._log(
                    f"dev:{story.id}",
                    f"⬆️ Escalade modèle (tentative {story.attempts}/{settings.dev_max_attempts}) → {forced}",
                )
        self._sync()
        ws = workspace_dir(self.state.id)
        pkg = workspace.package_name(self.state)
        is_frontend = self._is_frontend_story(story)
        if story.attempts == 1 and not is_frontend:
            self._set_stage(story, BuildStage.ANALYZING, "qa")  # N4/B1
            await self._adesign_tests(story, pkg)
        label = "dev frontend" if is_frontend else "dev"
        self._log(f"dev:{story.id}", f"Agent {label} assigné à {story.id} — {story.title}")
        try:
            # All workspace mutations (dev write, full-suite pytest, git commit,
            # code refinement) are serialized: parallel workers share one
            # workspace dir and must not interleave.
            async with self._build_lock:
                self._set_stage(story, BuildStage.IMPLEMENTING, "dev")  # N4/B1
                item_guidance = self._apply_guidance(story)  # P10
                previous_failure = prompts.previous_failure_block(
                    story.last_error or "", story.attempts
                )
                if is_frontend:
                    # ST-7: route a frontend-stream story to the React dev agent;
                    # "green" = Vitest all-pass AND `tsc && vite build` succeeds.
                    stream = self._story_stream(story)
                    dev_prompt = prompts.dev_story_frontend(
                        story, pkg, workspace.feature_rel_path(story),
                        architecture=self.state.architecture,
                        guidance="\n".join(self.state.build_guidance),
                        lessons="\n".join(self._effective_lessons()),
                        file_root=stream.file_root or "frontend",
                        item_guidance=item_guidance,
                        available_skills=self._skills_catalog("dev"),
                        previous_failure=previous_failure,
                    )
                    dev_persona = persona("dev-frontend")
                else:
                    dev_prompt = prompts.dev_story(
                        story, pkg, workspace.feature_rel_path(story), self.state.architecture,
                        "\n".join(self.state.build_guidance),
                        ui_tests=self._ui_mode(story),
                        lessons="\n".join(self._effective_lessons()),
                        backend_language=self.state.backend_language.value,
                        item_guidance=item_guidance,
                        available_skills=self._skills_catalog("dev"),
                        previous_failure=previous_failure,
                    )
                    dev_persona = persona("dev")
                # W0.5-T05: snapshot QA-authored tests before the dev turn so
                # tampering (editing tests to pass) is detectable afterwards.
                tests_before = self._snapshot_test_files(ws)
                result = await self._tracked.arun(
                    dev_prompt,
                    system_prompt=dev_persona,
                    cwd=ws,
                )
                # W0.5-HOOK: anti-cheating / quality guards over the dev's changes
                # (tamper/scope/skeleton/import). Advisory by default; strict mode
                # reverts tampered tests. Findings are recorded on the story so the
                # recovery machine (W1) and lessons (W5.6) can use them.
                guard_findings = await self._arun_cheat_guards(story, ws, tests_before)
                if guard_findings:
                    story.guard_findings = list(guard_findings)
                try:
                    reply = extract_json(result.text)
                except AgentError:
                    # La réponse JSON n'est qu'informative : la VÉRITÉ est la
                    # suite rejouée ci-dessous — un dev bien codé mais mal
                    # formaté ne doit pas perdre son travail (fail inutile).
                    reply = {}
                    self._log(
                        f"dev:{story.id}",
                        "Réponse dev illisible (JSON) — la suite réelle fait foi.",
                    )
                self._chat(ChatRole.DEV, f"[{story.id}] {reply.get('summary', '(pas de résumé)')}")
                self._observe_file_budget(story, reply)
                story.status = StoryStatus.GREEN if reply.get("status") == "green" else StoryStatus.RED
                story.ui_tests = [str(p) for p in reply.get("ui_test_files") or []]
                # B1: dev declared the failing tests (RED) → contracts written.
                if story.status == StoryStatus.RED:
                    self._set_stage(story, BuildStage.CONTRACTS, "dev", sync=False)
                self._set_stage(story, BuildStage.VERIFYING, "qa")  # N4/B1: orchestrator re-runs

                # Trust but verify: the orchestrator reruns the suite itself and
                # grounds per-test states on the REAL outcomes (Vitest+build for a
                # frontend story, pytest/go/cargo otherwise).
                if is_frontend:
                    ok, output, real = await self._arun_frontend_tests()
                else:
                    ok, output, real = await self._arun_pytest()
                tail = output[-2000:]
                self._apply_test_states(story, reply.get("test_results", []), real)
                regs = regression.find_regressions(set(self.state.green_tests), real)
                if regs:
                    rmsg = (
                        f"[{story.id}] {len(regs)} test(s) précédemment verts cassés : "
                        + ", ".join(regs[:3]) + ("…" if len(regs) > 3 else "")
                    )
                    self.state.regressions.append(rmsg)
                    self._notify("warning", "Régression détectée", rmsg)
                    self._log(f"dev:{story.id}", "⚠️ " + rmsg)
                if real:
                    self.state.green_tests = sorted(n for n, o in real.items() if o == "passed")
                if ok and self._ui_mode(story):
                    if not story.ui_tests:
                        ok = False
                        tail = (
                            "Aucun test UI rejouable déclaré pour cette story UI "
                            "(ui_test_files vide)."
                        )
                        self._log(f"dev:{story.id}", f"❌ {tail}")
                    else:
                        # UI-flagged story: the replayable Playwright suite must be
                        # green too (browser run, screenshots + render assertions).
                        ok, ui_output = await self._arun_ui_tests()
                        if not ok:
                            tail = ui_output[-2000:]
                            self._log(f"dev:{story.id}", "❌ Tests d'acceptance UI rouges.")
                if ok and settings.coverage_enabled and not is_frontend:
                    cov = await self._arun_coverage(story, pkg, ws)
                    if settings.coverage_gate_threshold > 0 and 0 <= cov < settings.coverage_gate_threshold:
                        ok = False
                        tail = (
                            f"Couverture insuffisante : {cov}% < seuil "
                            f"{settings.coverage_gate_threshold}% (gate de couverture)."
                        )
                        self._log(f"dev:{story.id}", "❌ " + tail)
                if ok:
                    story.status = StoryStatus.DONE
                    # Suite green: any planned test we couldn't map to a real
                    # node is assumed green (the whole suite passed).
                    for test in story.test_plan:
                        if test.status == TestState.NONEXISTENT:
                            test.status = TestState.GREEN
                    self._log(f"dev:{story.id}", f"✅ Suite de tests verte — {story.id} terminé.")
                    # Commit the workspace as this story's green state so its diff
                    # can be exposed (git show of the "story <id> done" commit).
                    await self._acommit_story(ws, story.id)
                    # Refinement + mutation testing are Python-suite operations
                    # (they rerun pytest / mutate the package); skip them for a
                    # frontend-stream story (ST-7).
                    if not is_frontend:
                        if settings.refine_for("dev"):
                            self._set_recovery(story, "refining")  # B1: critic loop
                            await self._arefine_code(story, pkg, ws)
                        self._set_recovery(story, "mutation_rerun")  # B1
                        await self._arun_mutation_test(story, pkg, ws)
                        self._set_recovery(story, "", sync=False)  # B1: clear
                    # B1: terminal stage for the stepper.
                    self._set_stage(story, BuildStage.DONE, sync=False)
                else:
                    story.last_error = tail
                    self._log(f"dev:{story.id}", f"❌ Tests rouges après passage du dev:\n{tail}")
                    if story.attempts < settings.dev_max_attempts:
                        story.status = StoryStatus.TODO  # will be rescheduled
                        self._set_stage(story, BuildStage.QUEUED, sync=False)  # B1: requeue
                    elif await self._amaybe_arbitrate_wrong_test(
                        story, ws, pkg, tail, is_frontend
                    ):
                        # W2.2: a wrong test was corrected and the suite went green.
                        pass
                    else:
                        story.status = StoryStatus.FAILED
                        self._set_stage(story, BuildStage.FAILED, sync=False)  # B1
        except AgentError as exc:
            story.last_error = str(exc)
            if settings.agent_provider == "claude code" and session_monitor.is_usage_limit_error(str(exc)):
                # Usage-window exhaustion is not the story's fault: refund the
                # attempt and requeue as-is for the scheduled fresh session.
                story.attempts = max(0, story.attempts - 1)
                story.status = StoryStatus.TODO
                if not session_monitor.monitor_active():
                    self.state.phase = PipelinePhase.NEEDS_ATTENTION
                    self._stop_requested = True
            else:
                # Panne d'infra (pas un échec dev) : tentative dev remboursée,
                # budget infra séparé consommé — cf. le chemin work-item.
                story.attempts = max(0, story.attempts - 1)
                story.infra_attempts += 1
                self.state.calibration_for().infra_retries += 1  # §8
                story.status = (
                    StoryStatus.TODO
                    if story.infra_attempts <= settings.infra_max_retries
                    else StoryStatus.FAILED
                )
            self._log(f"dev:{story.id}", f"Erreur agent : {exc}")
        except Exception:
            # Unexpected failure (pytest runner missing, git crash…): never
            # persist a transient status; the exception itself surfaces via
            # the lifecycle task (-> ERROR phase).
            if story.status in (StoryStatus.IN_PROGRESS, StoryStatus.GREEN, StoryStatus.RED):
                story.status = StoryStatus.TODO
            raise
        finally:
            self._sync()

    # --------------------------------- ST-9/10/11: parallel worktree build path

    async def _abuild_phase_streams(self, all_iterations: bool = False) -> None:
        """ST-9: stream-aware parallel build with per-work-item git worktrees.

        Each batch picks the READY work items (taskless US + tasks whose deps are
        all merged/DONE) via the work graph, builds them TRULY in parallel — each
        in its OWN git worktree of the project repo, so they never share a
        workspace dir and need no ``_build_lock`` — then merges every green item
        back into the shared repo (serialized by ``_merge_lock``, ST-10). An item
        is only marked DONE after a successful merge, so the next batch's
        worktrees branch from the post-merge HEAD (ST-11)."""
        self.state.phase = PipelinePhase.BUILD
        self._sync()
        self._start_tick()  # B5: heartbeat while building
        ws = workspace_dir(self.state.id)
        await self._agit_ensure_repo(ws)
        # The worktree base must be a real commit: a freshly-init'd repo has an
        # unborn HEAD, so `worktree add ... HEAD` would fail. Seed the scaffold.
        await self._acommit_story(ws, "scaffold")
        cap = max(1, settings.max_parallel_devs)
        # Item ids whose acceptance feature file is already committed to the shared
        # HEAD (so a worktree can branch off it). Committed lazily, once per item.
        featured: set[str] = set()
        # Work items currently building, by id — the live set the dynamic
        # scheduler refills as slots free.
        running: dict[str, asyncio.Task] = {}

        async def _acommit_feature(item: "work_streams.WorkItem") -> None:
            """Ensure an item's acceptance feature file is at the shared repo HEAD
            before its worktree branches off it. Serialized via the merge lock
            (the shared repo index/HEAD is not concurrency-safe), and done once per
            item — so a mid-build-added story is handled exactly like the rest."""
            if item.id in featured:
                return
            featured.add(item.id)
            subject = self._item_subject(item)
            if subject.gherkin.strip():
                async with self._merge_lock.ahold(f"feature:{item.id}"):
                    workspace.write_feature_files(self.state, [subject])
                    await self._acommit_story(ws, f"feature {item.id}")

        async def _reap_done() -> None:
            """Remove finished workers (freeing their slots). P0b: a single worker
            that died with an UNEXPECTED exception must NOT tear down the whole
            build (the old behaviour cancelled every sibling and re-raised, so one
            transient crash — e.g. ``claude CLI exited with 1073807364`` — stranded
            an entire project). Instead we isolate the failure: mark that item
            FAILED (relaunchable) and let the rest keep going. Cancellation still
            propagates (cooperative stop)."""
            for wid in [k for k, v in running.items() if v.done()]:
                finished = running.pop(wid)
                exc = finished.exception()
                if exc is None or isinstance(exc, asyncio.CancelledError):
                    continue
                self._log(
                    f"dev:{wid}",
                    f"⛔ Worker {wid} a planté ({type(exc).__name__}: {exc}). "
                    "Isolé en échec ; le reste du build continue.",
                )
                self._fail_item_by_id(wid, f"crash worker : {exc}")
                self._sync()

        # Dynamic dataflow scheduler (replaces a batch barrier): each work item
        # starts the instant a slot is free AND all its deps are merged — a freed
        # slot is refilled immediately with whatever just became ready (e.g. the
        # items a just-merged dependency unblocked), instead of waiting for the
        # slowest sibling of a fixed batch. Concurrency is capped at
        # max_parallel_devs; merges stay serialized by _merge_lock (ST-10), so
        # dependencies and merges are still finely controlled.
        try:
            while not self._stop_requested:
                await self._checkpoint()  # honour pause/budget before launching more
                if self._stop_requested:
                    break
                await _reap_done()

                # Recomputed each pass: a just-landed merge changes readiness, and
                # the user may add stories mid-build (ST-11).
                iteration_ids = {
                    s.id
                    for s in (
                        self.state.stories
                        if all_iterations
                        else self.state.stories_of_iteration(self.state.iteration)
                    )
                }
                graph = work_streams.build_work_graph(self.state)
                # Surface graph sanitation loudly (unknown deps dropped, cycles
                # broken at ingestion): silent repairs hide plan defects.
                for warning in graph.warnings:
                    self._log("streams", f"⚠️ {warning}")
                    if "cycle" in warning.lower():
                        self._chat(ChatRole.SYSTEM, f"⚠️ {warning}")
                items = [
                    graph.items[i] for i in graph.order
                    if graph.items[i].story_id in iteration_ids
                ]
                pending = [
                    it for it in items
                    if it.status in (
                        StoryStatus.TODO, StoryStatus.IN_PROGRESS,
                        StoryStatus.RED, StoryStatus.GREEN,
                    )
                ]
                if not pending and not running:
                    break

                # Fill every free slot with a ready item (deps all merged/DONE).
                # P4c: independence safety floor — never co-run two items that
                # could touch the SAME files. Two same-stream tasks with no proven
                # file-disjointness (e.g. two frontend tasks both editing App.tsx)
                # would build in parallel worktrees and conflict on merge, losing
                # the green work. We hold such an item back until its in-flight
                # rival merges; the next pass branches it off the updated HEAD.
                inflight_claims = [
                    self._item_claim(graph.items[rid])
                    for rid in running if rid in graph.items
                ]
                for it in items:
                    if len(running) >= cap:
                        break
                    if it.id in running or not work_streams.is_ready(it, graph.items):
                        continue
                    claim = self._item_claim(it)
                    # Un retry APRÈS CONFLIT DE MERGE est re-planifié en mode
                    # STRICT : claims_overlap (un claim non déclaré du même
                    # stream = rival possible), pas seulement declared_overlap.
                    # Ses claims viennent d'être recalés sur les fichiers
                    # RÉELLEMENT touchés (_register_merge_conflict), donc le
                    # blocage est ciblé ; il attend au pire la fin des items en
                    # vol — jamais un deadlock (ils se terminent toujours).
                    strict = it.id in self._conflict_retry_ids
                    overlap = (
                        independence.claims_overlap
                        if strict
                        else independence.declared_overlap
                    )
                    if any(overlap(claim, other) for other in inflight_claims):
                        continue  # would clash on files with an in-flight item
                    self._conflict_retry_ids.discard(it.id)
                    await _acommit_feature(it)
                    running[it.id] = asyncio.create_task(self._abuild_work_item(it))
                    inflight_claims.append(claim)

                if not running:
                    # Nothing ready and nothing in flight: a defensive in-flight
                    # remnant, a dependency CYCLE, or everything left depends on
                    # failed work. Keep failures targeted: a local cycle or one
                    # failed upstream item must not contaminate the full backlog.
                    if any(p.status == StoryStatus.IN_PROGRESS for p in pending):
                        break  # defensive: a worker left an item in-flight
                    cycle = work_streams.detect_cycle(graph)
                    cycle_ids = work_streams.cycle_nodes(graph)
                    cycle_error = (
                        f"Cycle de dépendances détecté : {' → '.join(cycle)}"
                        if cycle else None
                    )
                    if cycle_error:
                        self._chat(ChatRole.SYSTEM, f"⛔ {cycle_error}")
                    for item in pending:
                        blockers = work_streams.blocked_by(item, graph.items)
                        if item.id in cycle_ids:
                            self._set_item_status(
                                item, StoryStatus.FAILED,
                                last_error=cycle_error,
                            )
                        else:
                            target = self._item_target(item)
                            # Name the transitive FAILED root and its error: the
                            # direct blocker of a deep item is often itself only
                            # blocked, and the operator otherwise has to walk the
                            # chain by hand to find what actually broke.
                            root = scheduler.failed_root(item, graph.items)
                            root_err = ""
                            if root is not None:
                                root_target = self._item_target(root)
                                detail = (
                                    (getattr(root_target, "last_error", "") or "")
                                    .strip()[:300]
                                )
                                root_err = f" Cause racine : {root.id}" + (
                                    f" — {detail}" if detail else ""
                                )
                            target.last_error = (
                                cycle_error
                                or "Dépendance non satisfaite (work item échoué en amont)."
                                + root_err
                            )
                        if blockers:
                            self._log(
                                f"dev:{item.id}",
                                f"⛔ {item.id} bloqué par : {', '.join(blockers)}.",
                            )
                    self._sync()
                    break

                # Block until the first worker finishes, then loop to refill its
                # slot with whatever its merge just unblocked.
                await asyncio.wait(
                    set(running.values()), return_when=asyncio.FIRST_COMPLETED
                )
        finally:
            # Stop / completion / error: let any still-running worker finish so its
            # worktree is cleaned up (its finally runs); killed agents return fast.
            if running:
                await asyncio.gather(*running.values(), return_exceptions=True)
            # H1: belt-and-suspenders — if the loop was cancelled/stopped while a
            # worker was mid-flight (or a gather swallowed a cancellation), no item
            # must be left stuck IN_PROGRESS/GREEN/RED with no worker behind it.
            # Reset such orphans to TODO so the next resume actually rebuilds them
            # (the todo_list_2 "stuck forever" symptom can never persist).
            n_orphans = self._reset_orphan_items()
            if n_orphans:
                self._log("build", f"♻️ {n_orphans} item(s) en vol réinitialisé(s) à l'arrêt du build.")
            self._sync()

        self._stop_tick()  # B5: build loop done
        self.state.build_guidance.clear()

    def _item_subject(self, item: "work_streams.WorkItem") -> UserStory:
        """Resolve a work item to the ``UserStory``-shaped object the build
        helpers consume. A taskless US is built as-is; a Task is adapted into a
        lightweight UserStory carrying the task's title/description/criteria/
        gherkin/stream so ``dev_story``/``dev_story_frontend`` work unchanged
        (the per-task status is read/written back on the real Task)."""
        if item.kind == "story":
            return self.state.story(item.story_id)
        task = self.state.task(item.id)
        return UserStory(
            id=task.id,
            epic_id=self.state.story(task.story_id).epic_id,
            title=task.title or task.id,
            description=task.description,
            acceptance_criteria=list(task.acceptance_criteria),
            gherkin=task.gherkin,
            priority=3,
            status=task.status,
            stream=task.stream,
            attempts=task.attempts,
            last_error=task.last_error,
            iteration=self.state.iteration,
        )

    def _item_target(self, item: "work_streams.WorkItem"):
        """The persistent model (UserStory or Task) whose status/attempts the
        scheduler reads — kept in sync with the per-build subject."""
        if item.kind == "story":
            return self.state.story(item.story_id)
        return self.state.task(item.id)

    def _set_item_status(self, item, status, *, last_error=None) -> None:
        target = self._item_target(item)
        target.status = status
        if last_error is not None:
            target.last_error = last_error

    def _enforce_task_independence(self, tasks: list[Task], *, label: str) -> None:
        """P4b: run the deterministic independence floor over a freshly built task
        set and INJECT the ``depends_on`` it computes, so file-overlapping tasks
        are serialized in the work graph (not just at schedule time). Mutates the
        Task objects in place. Pure + safe: it only ADDS edges, never removes one,
        and is a no-op when tasks are already disjoint/ordered."""
        if len(tasks) < 2:
            return
        claims = [
            independence.TaskClaim(
                id=t.id,
                stream=t.stream or self.state.primary_stream_id,
                file_globs=tuple(t.files_hint),
                depends_on=tuple(t.depends_on),
            )
            for t in tasks
        ]
        report = independence.analyze(claims)
        if not report.added_deps and not report.warnings:
            return
        by_id = {t.id: t for t in tasks}
        for tid, extra in report.added_deps.items():
            task = by_id.get(tid)
            if task is None:
                continue
            for dep in extra:
                if dep not in task.depends_on:
                    task.depends_on.append(dep)
        if report.conflict_pairs:
            pairs = ", ".join(f"{a}↔{b}" for a, b in report.conflict_pairs[:4])
            self._log(
                f"independence:{label}",
                f"🔗 {len(report.conflict_pairs)} paire(s) de tâches en conflit de "
                f"fichiers sérialisée(s) ({pairs}…).",
            )
        for w in report.warnings:
            self._log(f"independence:{label}", f"⚠️ {w}")

    def _enforce_global_independence(self) -> None:
        """P1: a GLOBAL deterministic pass over EVERY pending task (across all
        stories AND streams) that serializes tasks whose DECLARED file globs
        overlap — e.g. two stories both editing ``pyproject.toml``, or a backend
        and a frontend task both touching a repo-root ``README.md`` (which the
        per-stream/per-story floor would miss). Only DECLARED overlaps create
        edges, so it never over-serializes undeclared work nor deadlocks."""
        tasks = [t for s in self.state.stories for t in s.tasks]
        if len(tasks) < 2:
            return
        claims = [
            independence.TaskClaim(
                id=t.id,
                stream=t.stream or self.state.primary_stream_id,
                file_globs=tuple(t.files_hint),
                depends_on=tuple(t.depends_on),
            )
            for t in tasks
        ]
        # Zone/stream coherence (legacy plan path — the PO pipeline refuses
        # these at S1): a glob outside its stream's zone is a future
        # inter-stream conflict, surfaced here as an actionable warning.
        roots = plan_pipeline._stream_roots(self.state)
        if roots:
            for w in independence.zone_mismatches(claims, roots):
                self._log("independence", f"⚠️ {w}")
        edges = independence.declared_serialization(claims)
        if not edges:
            return
        by_id = {t.id: t for t in tasks}
        n = 0
        for tid, extra in edges.items():
            task = by_id.get(tid)
            if task is None:
                continue
            for dep in extra:
                if dep not in task.depends_on:
                    task.depends_on.append(dep)
                    n += 1
        if n:
            self._log(
                "independence",
                f"🔗 {n} arête(s) globale(s) de sérialisation (fichiers déclarés "
                "partagés inter-stories/streams).",
            )

    # ---------------------------------------- adaptive split-on-failure (P6)

    def _build_finer_tasks(
        self, subject: UserStory, raw: list[dict], *, story_id: str, stream: str, base_depth: int
    ) -> list[Task]:
        """Materialize the architect's finer-split reply into Task models: project-
        wide-unique ids, intra-split ``depends_on`` remapped, criteria restricted to
        the parent's ids, file claims carried, ``split_depth = base_depth + 1`` (so
        recursion is bounded)."""
        taken = {t.id for t in self.state.all_tasks()} | {s.id for s in self.state.stories}
        valid_ac = {c.id: c for c in subject.acceptance_criteria}
        id_map: dict[str, str] = {}
        for i, data in enumerate(raw, start=1):
            old = str(data.get("id") or f"S-{i}")
            new = f"{subject.id}-S{i}"
            while new in taken:
                new += "x"
            taken.add(new)
            id_map[old] = new
        out: list[Task] = []
        for i, data in enumerate(raw, start=1):
            old = str(data.get("id") or f"S-{i}")
            crit = [valid_ac[c] for c in (data.get("acceptance_criteria") or []) if c in valid_ac]
            deps = [id_map[d] for d in (data.get("depends_on") or []) if d in id_map]
            globs = [str(g) for g in (data.get("file_globs") or []) if str(g).strip()]
            out.append(
                Task(
                    id=id_map[old],
                    story_id=story_id,
                    stream=stream,
                    title=str(data.get("title") or old),
                    description=str(data.get("description") or ""),
                    acceptance_criteria=crit or list(subject.acceptance_criteria),
                    gherkin=str(data.get("gherkin") or subject.gherkin),
                    depends_on=deps,
                    files_hint=globs,
                    split_depth=base_depth + 1,
                )
            )
        return out

    def _log_cost_counterfactual(self) -> None:
        """W4: the "$8 vs $100" line. Report the per-tier ledger and, when the boss
        tier has a price, the counterfactual of running EVERY token through the
        boss model (frontier-only) versus the actual tiered spend. Best-effort."""
        if not settings.role_routing_enabled:
            return
        try:
            u = self.state.usage
            if not u.calls_by_tier:
                return
            parts = [
                f"{tier}: {u.calls_by_tier.get(tier, 0)} appels, "
                f"{u.cost_by_tier.get(tier, 0.0):.4f}$"
                for tier in ("boss", "worker", "checker", "unrouted")
                if u.calls_by_tier.get(tier)
            ]
            self._log("cost", "💵 Répartition par tier — " + " · ".join(parts))
            boss_out = settings.tier_price_out.get("boss", 0.0)
            boss_in = settings.tier_price_in.get("boss", 0.0)
            if boss_out or boss_in:
                frontier = (
                    u.input_tokens / 1_000_000 * boss_in
                    + u.output_tokens / 1_000_000 * boss_out
                )
                self.monitor.event(
                    "cost_counterfactual", actual=round(u.cost_usd, 4),
                    frontier_only=round(frontier, 4),
                )
                if frontier > 0:
                    self._log(
                        "cost",
                        f"💵 Contrefactuel : {u.cost_usd:.2f}$ réel vs "
                        f"{frontier:.2f}$ si tout passait par le modèle boss "
                        f"(×{frontier / u.cost_usd:.1f})" if u.cost_usd else "",
                    )
        except Exception:
            return

    def _report_traceability(self, all_iterations: bool) -> None:
        """W2.0b — advisory AC↔test coverage report. Complements the delivery
        gate's per-criterion green-evidence check with SOURCE-level traceability:
        acceptance criteria with no test that names them, and ORPHAN tests naming
        an AC id that does not exist. Best-effort; never blocks."""
        if not settings.ac_traceability_enabled:
            return
        try:
            stories = (
                self.state.stories if all_iterations
                else self.state.stories_of_iteration(self.state.iteration)
            )
            all_ac_ids = {c.id for s in stories for c in s.acceptance_criteria}
            if not all_ac_ids:
                return
            ws = workspace_dir(self.state.id)
            report = traceability.coverage_report(all_ac_ids, self._collect_test_sources(ws))
            uncovered, orphans = report.get("uncovered", []), report.get("orphans", [])
            self.monitor.event(
                "traceability", covered=len(report.get("covered", [])),
                uncovered=len(uncovered), orphans=len(orphans),
            )
            if uncovered:
                msg = f"Traçabilité : {len(uncovered)} critère(s) sans test nommé ({', '.join(uncovered[:6])})."
                delivery_state.append_issue(self.state, msg)
                self._log("traceability", "⚠️ " + msg)
            if orphans:
                self._log(
                    "traceability",
                    f"⚠️ {len(orphans)} test(s) orphelin(s) référencent un AC inexistant "
                    f"({', '.join(orphans[:6])}).",
                )
        except Exception:
            return

    async def _amaybe_propose_amendment(self, story: UserStory, acceptance: str, reason: str) -> None:
        """W5.1 — when a failure is a genuine spec contradiction, propose a MINIMAL
        amendment, run an INDEPENDENT weakening check, and queue the survivor as a
        HUMAN-PENDING proposal (never auto-applied unless AMENDMENT_AUTO). A system
        that could rewrite the criteria it fails to meet must not be able to
        legalize failure — hence the independent gate + human default. Best-effort."""
        if not settings.design_amendment_enabled:
            return
        if len(self.state.pending_amendments) >= settings.amendment_max_depth:
            return
        try:
            proposal = await amendment.apropose_safe_amendment(
                self._tracked,
                story_title=story.title,
                acceptance=acceptance,
                failure_context=reason,
                target_hint="acceptance_criteria",
            )
        except AgentError:
            return
        if not proposal:
            return
        record = {"story_id": story.id, **proposal}
        self.state.pending_amendments.append(record)
        safe = bool(proposal.get("approved_safe"))
        self.monitor.event(
            "amendment", item=story.id, target=proposal.get("target", ""),
            approved_safe=safe, auto=settings.amendment_auto,
        )
        if not safe:
            self._log(
                f"amend:{story.id}",
                "🛑 Amendement proposé REJETÉ (affaiblirait l'exigence) — "
                f"{proposal.get('weakening_reason', '')}",
            )
            return
        if settings.amendment_auto:
            # Opt-in unattended apply: record the applied change (the actual AC
            # edit is left to the next planning pass reading pending_amendments).
            self._log(f"amend:{story.id}", "✍️ Amendement sûr appliqué automatiquement (AMENDMENT_AUTO).")
            self._chat(
                ChatRole.SYSTEM,
                f"[{story.id}] ✍️ Amendement appliqué : {proposal.get('rationale', '')}",
            )
        else:
            self._notify(
                "warning", "Amendement de spec proposé",
                f"{story.id} : {proposal.get('rationale', '')} — en attente de validation humaine.",
            )
            self._log(f"amend:{story.id}", "⏸️ Amendement sûr en attente de validation humaine.")

    def _record_arbitration_lesson(self) -> None:
        """W5.6 — durable lesson from a wrong-test arbitration, injected into later
        QA/Dev prompts via ``_effective_lessons``. Bounded like the retro lessons."""
        lesson = (
            "Un test QA a été jugé FAUX (il affirmait un comportement absent des "
            "critères d'acceptance) : n'affirmer QUE ce que les critères exigent, "
            "jamais un comportement non spécifié."
        )
        if lesson not in self.state.lessons:
            self.state.lessons.append(lesson)
            self.state.lessons = self.state.lessons[-settings.retro_max_lessons:]

    def _collect_test_sources(self, ws) -> dict[str, str]:
        """Read every test file's source in the workspace (workspace-relative
        posix path → text). Best-effort; used to feed the arbiter / traceability."""
        out: dict[str, str] = {}
        for rel, p in self._iter_ws_py_files(ws):
            if guards.modified_test_files([rel], []):
                try:
                    out[rel] = p.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
        return out

    def _story_acceptance_text(self, story: UserStory) -> str:
        """The story's acceptance criteria + Gherkin as one block — the arbiter's
        ground truth (what SHOULD be asserted)."""
        parts = []
        for c in story.acceptance_criteria:
            parts.append(f"- [{c.id}] {c.text}")
        if story.gherkin.strip():
            parts.append("\nGherkin:\n" + story.gherkin.strip())
        return "\n".join(parts)

    async def _amaybe_arbitrate_wrong_test(
        self, story: UserStory, ws, pkg: str, tail: str, is_frontend: bool
    ) -> bool:
        """W2.2 — the video's "who checks the checker". A story that exhausted its
        dev attempts gets ONE boss-tier arbitration: is the failing TEST wrong
        (contradicts the acceptance criteria)? If the arbiter rules ``fix_test``, a
        checker-tier agent corrects the test per the arbiter's instructions and the
        suite is rerun; a green rerun recovers the story. ``fix_impl`` /
        ``spec_contradiction`` confirm the failure (the story stays failed; a
        spec contradiction is logged for the human-gated amendment of Wave 5).
        Executed facts are never overruled — only judgment about what the test
        SHOULD assert. Best-effort; any error falls through to the normal FAILED."""
        if not settings.dispute_escalation_enabled or is_frontend:
            return False
        if not story.acceptance_criteria:
            return False  # no ground truth to arbitrate against
        if self._arbitration_count.get(story.id, 0) >= settings.arbitration_max:
            return False
        self._arbitration_count[story.id] = self._arbitration_count.get(story.id, 0) + 1

        acceptance = self._story_acceptance_text(story)
        test_sources = self._collect_test_sources(ws)
        test_blob = "\n\n".join(f"# file: {p}\n{src}" for p, src in test_sources.items())
        try:
            _, diff = await self._agit(ws, "diff", "HEAD")
        except Exception:
            diff = ""

        self._set_recovery(story, "arbitration")  # B1 stage badge
        self._log(f"arbiter:{story.id}", "⚖️ Arbitrage : le test en échec contredit-il les critères ?")
        try:
            ruling = await arbitration.aarbitrate_test(
                self._tracked,
                story_title=story.title,
                acceptance=acceptance,
                test_source=test_blob,
                failure_output=tail,
                impl_diff=diff or "",
                cwd=ws,
            )
        except AgentError as exc:
            self._log(f"arbiter:{story.id}", f"Arbitrage indisponible ({exc}) — échec maintenu.")
            return False

        verdict = str(ruling.get("verdict") or "")
        reason = str(ruling.get("reason") or "")
        instructions = str(ruling.get("instructions") or "")
        self.monitor.event("arbitration", item=story.id, verdict=verdict, reason=reason[:200])
        self._log(f"arbiter:{story.id}", f"Verdict : {verdict} — {reason}")

        if verdict != arbitration.FIX_TEST:
            # fix_impl → the test was right, the story genuinely failed.
            # spec_contradiction → out of scope here; recorded for W5 amendment.
            if verdict == arbitration.SPEC_CONTRADICTION:
                story.last_error = (f"[arbitrage: contradiction de spec] {reason}\n" + (tail or ""))[:2000]
                self._chat(
                    ChatRole.SYSTEM,
                    f"[{story.id}] ⚖️ Arbitre : contradiction dans les critères — "
                    "proposition d'amendement (Wave 5).",
                )
                await self._amaybe_propose_amendment(story, acceptance, reason)
            return False

        # fix_test: a checker-tier agent rewrites the failing test to match the
        # acceptance criteria (per the arbiter's instructions), then we RERUN — the
        # executed suite, not the agent's word, decides success.
        self._log(f"arbiter:{story.id}", "🔧 Correction du test erroné (agent QA) puis re-vérification.")
        # W3 immutability: constitution tests are the project's non-negotiable
        # floor — snapshot them so an over-eager fix cannot weaken them.
        protected = {
            rel: (ws / rel).read_bytes()
            for rel in self.state.constitution_test_paths
            if (ws / rel).exists()
        }
        try:
            await self._tracked.arun(
                prompts_arbiter_fix_test(story, pkg, acceptance, instructions, test_blob),
                system_prompt=persona("qa"),
                cwd=ws,
            )
        except AgentError as exc:
            self._log(f"arbiter:{story.id}", f"Correction du test échouée ({exc}) — échec maintenu.")
            return False
        for rel, original in protected.items():  # restore any touched constitution test
            p = ws / rel
            try:
                if not p.exists() or p.read_bytes() != original:
                    p.write_bytes(original)
                    self._log(f"arbiter:{story.id}", f"↩️ règle de constitution protégée : {rel}")
            except OSError:
                pass

        ok, output, real = await self._arun_pytest(ws=ws)
        if not ok:
            story.last_error = (output or tail)[-2000:]
            self._log(f"arbiter:{story.id}", "❌ Suite toujours rouge après correction du test.")
            return False

        # Recovered: mark the story done exactly like the normal green path.
        self._apply_test_states(story, [], real)
        if real:
            self.state.green_tests = sorted(n for n, o in real.items() if o == "passed")
        story.status = StoryStatus.DONE
        for test in story.test_plan:
            if test.status == TestState.NONEXISTENT:
                test.status = TestState.GREEN
        await self._acommit_story(ws, story.id)
        self._set_recovery(story, "", sync=False)
        self._set_stage(story, BuildStage.DONE, sync=False)
        self._log(f"arbiter:{story.id}", "✅ Test erroné corrigé — suite verte, story livrée.")
        self._chat(
            ChatRole.SYSTEM,
            f"[{story.id}] ⚖️ Le test était faux (pas le code) — corrigé selon les "
            "critères d'acceptance, suite verte.",
        )
        # W5.6: the factory learns from its own disputes — a fix_test ruling is
        # evidence of HOW the QA agent writes wrong tests. Feed it into the durable
        # lessons that seed the QA/Dev prompts of later stories/iterations.
        self._record_arbitration_lesson()
        return True

    async def _amaybe_split_on_failure(self, item, subject: UserStory, target, *, force: bool = False) -> bool:
        """P6 — adaptive split-on-failure (the « unit too big for one agent session »
        counter). A story/task that exhausted its dev attempts is re-analyzed by the
        architect and split into FINER sub-tasks (smaller scope + finer tests)
        instead of just failing. Returns True if it split (caller must NOT mark it
        FAILED — the new sub-tasks will build); False to fall through to FAILED.
        Bounded by ``split_max_depth`` (bypassed when ``force`` — a manual user
        action); non-fatal (any error → False)."""
        if not force and not settings.split_on_failure_enabled:
            return False
        if not force and getattr(target, "split_depth", 0) >= settings.split_max_depth:
            self._log(f"split:{item.id}", "Profondeur de découpage max atteinte — échec maintenu.")
            return False
        is_frontend = self._is_frontend_story(subject)
        pkg = workspace.package_name(self.state)
        try:
            result = await self._tracked.arun(
                prompts.decompose_finer(
                    subject, pkg, reason=getattr(target, "last_error", "") or "",
                    is_frontend=is_frontend, architecture=self.state.architecture,
                    available_skills=self._skills_catalog("dev"),
                ),
                system_prompt=persona("architect"),
            )
            reply = extract_json(result.text)
        except AgentError as exc:
            self._log(f"split:{item.id}", f"Re-décomposition indisponible ({exc}) — échec maintenu.")
            return False
        raw = [t for t in (reply.get("tasks") or []) if isinstance(t, dict)]
        if len(raw) < 2:
            self._log(f"split:{item.id}", "Unité jugée indivisible — échec maintenu.")
            return False
        if item.kind == "story":
            split_ok = self._split_story(self.state.story(item.story_id), raw)
        else:
            split_ok = self._split_task(item.id, raw)
        if split_ok:
            self._record_split_calibration(subject, target, n=len(raw))
        return split_ok

    def _observe_file_budget(self, subject: UserStory, reply: dict) -> None:
        """§6: confront the dev's DECLARED touched files with the sizing budget.
        An over-budget unit at runtime means the plan sized it too big — a
        calibration signal counted on the story's iteration."""
        files = [str(f) for f in reply.get("files") or []]
        budget = self._setting("task_file_budget")
        if len(files) > budget:
            self.state.calibration_for(
                getattr(subject, "iteration", None)
            ).over_budget_tasks += 1
            self._log(
                f"dev:{subject.id}",
                f"📏 {len(files)} fichiers touchés > budget {budget} — signal de calibration (§6).",
            )

    def _register_merge_conflict(
        self,
        item: "work_streams.WorkItem",
        target,
        conflict_files: list[str],
        touched: list[str],
    ) -> None:
        """Separation loop after an inter-stream merge conflict — three effects:

        1. DIAGNOSIS: ``last_error`` names the files that actually clashed
           (the old opaque « conflit de merge inter-stream » hid the cause).
        2. RECALIBRATION: the branch's OBSERVED footprint is merged into the
           item's declared ``files_hint`` — the independence floor and the
           scheduler guard now reason on reality, not on the plan's promise.
        3. STRICT RETRY + LESSON (§6): the item is flagged for strict
           scheduling (no co-run with any possible rival) and a sizing lesson
           is emitted so the next plan declares disjoint zones or extracts a
           dedicated integration task."""
        listing = ", ".join(conflict_files[:5]) or "fichiers non identifiés"
        target.last_error = f"conflit de merge inter-stream sur : {listing}"
        self._merge_scope_hints(target, [*conflict_files, *touched])
        self._conflict_retry_ids.add(item.id)
        lesson = (
            f"Itération {self.state.iteration} : « {getattr(target, 'title', '') or item.id} » "
            f"est entrée en conflit de merge avec une unité parallèle sur {listing} — "
            "déclarer des zones de fichiers DISJOINTES par tâche, ou extraire le câblage "
            "des fichiers partagés dans une tâche d'intégration dédiée (depends_on les features)."
        )
        if lesson not in self.state.sizing_lessons:
            self.state.sizing_lessons.append(lesson)
        self.state.sizing_lessons = self.state.sizing_lessons[-12:]

    def _record_split_calibration(self, subject: UserStory, target, n: int) -> None:
        """§6 (PO évolutif, mesuré) : every reactive split is a CALIBRATION
        signal — counted per iteration and distilled into a structured sizing
        lesson injected into the next S1 prompt, so today's failure sizes
        tomorrow's plan."""
        self.state.calibration_for().reactive_splits += 1
        stream = getattr(target, "stream", "") or self.state.primary_stream_id
        zone = ", ".join(list(getattr(target, "files_hint", []))[:3]) or stream
        attempts = getattr(target, "attempts", 0)
        lesson = (
            f"Itération {self.state.iteration} : « {subject.title or subject.id} » "
            f"(zone {zone}) était sous-dimensionnée — re-découpée en {n} sous-tâches "
            f"après {attempts} tentative(s). Découper plus fin ce type de tâche dès le plan."
        )
        if lesson not in self.state.sizing_lessons:
            self.state.sizing_lessons.append(lesson)
        self.state.sizing_lessons = self.state.sizing_lessons[-12:]

    def _split_story(self, story: UserStory, raw: list[dict]) -> bool:
        """Re-decompose a taskless FAILED story into finer sub-tasks (it becomes a
        container; its status then derives from the new tasks)."""
        stream = story.stream or self.state.primary_stream_id
        new_tasks = self._build_finer_tasks(
            story, raw, story_id=story.id, stream=stream, base_depth=story.split_depth
        )
        self._enforce_task_independence(new_tasks, label=f"{story.id}/split")
        story.tasks = new_tasks
        story.split_depth += 1
        story.status = StoryStatus.TODO
        story.last_error = ""
        self._set_stage(story, BuildStage.QUEUED, sync=False)
        title_list = ", ".join(t.title or t.id for t in new_tasks)
        self._log(f"split:{story.id}", f"🪓 {story.id} re-découpée en {len(new_tasks)} sous-tâches plus fines après échec.")
        self._chat(ChatRole.ARCHITECT, f"[{story.id}] Re-découpage plus fin après échec → {title_list}.")
        return True

    def _split_task(self, task_id: str, raw: list[dict]) -> bool:
        """Re-decompose a FAILED task into finer sub-tasks. RFC technical-stories:
        when the parent container keeps ≥1 other task, the sub-tasks are EXTRACTED
        into a new **Technical Story** (a named, board-level, dependable container);
        when the failed task is the container's only one, fall back to an in-place
        sibling split (no empty container). Either way dependencies are rewired so
        nothing builds out of order."""
        story = next((s for s in self.state.stories if any(t.id == task_id for t in s.tasks)), None)
        if story is None:
            return False
        failed = next(t for t in story.tasks if t.id == task_id)
        stories_snapshot = copy.deepcopy(self.state.stories)
        stream = failed.stream or self.state.primary_stream_id
        new_tasks = self._build_finer_tasks(
            failed, raw, story_id=story.id, stream=stream, base_depth=failed.split_depth
        )
        new_ids = [t.id for t in new_tasks]
        other_tasks = [t for t in story.tasks if t.id != failed.id]
        safe_failed_deps = self._safe_split_depends(story, failed)

        if other_tasks:
            # EXTRACT into a Technical Story (the container keeps its other tasks).
            ts = self._make_technical_story(story, failed, new_tasks, depends_on=safe_failed_deps)
            # The TS's tasks live under the TS now (their story_id is rebound).
            for nt in new_tasks:
                nt.story_id = ts.id
            # Whatever depended on the failed task now depends on the TS (the graph
            # resolves « depend on a story = its tasks »), and the failed task leaves
            # the container. The TS carries the upstream deps at the story level.
            for t in self.state.all_tasks():
                if task_id in t.depends_on:
                    t.depends_on = [d for d in t.depends_on if d != task_id]
                    if ts.id not in t.depends_on:
                        t.depends_on.append(ts.id)
            for s in self.state.stories:
                if task_id in s.depends_on:
                    s.depends_on = [d for d in s.depends_on if d != task_id]
                    if ts.id not in s.depends_on:
                        s.depends_on.append(ts.id)
            story.tasks = other_tasks
            self.state.stories.append(ts)
            self._enforce_task_independence(ts.tasks, label=f"{ts.id}/split")
            if self._restore_split_snapshot_if_cycle(stories_snapshot, label=f"{task_id}/split"):
                return False
            title_list = ", ".join(t.title or t.id for t in new_tasks)
            self._log(
                f"split:{task_id}",
                f"🔧 Tâche {task_id} extraite en Technical Story {ts.id} "
                f"({len(new_tasks)} sous-tâches plus fines).",
            )
            self._chat(
                ChatRole.ARCHITECT,
                f"[{task_id}] Trop grosse → Technical Story {ts.id} : {title_list}.",
            )
            return True

        # FALLBACK — the failed task is the container's ONLY one: in-place sibling
        # split (no empty container, no extra TS node).
        for nt in new_tasks:
            for dep in safe_failed_deps:
                if dep not in nt.depends_on:
                    nt.depends_on.append(dep)
        for t in self.state.all_tasks():
            if task_id in t.depends_on:
                t.depends_on = [d for d in t.depends_on if d != task_id] + [
                    nid for nid in new_ids if nid not in t.depends_on
                ]
        idx = story.tasks.index(failed)
        story.tasks[idx : idx + 1] = new_tasks
        self._enforce_task_independence(story.tasks, label=f"{task_id}/split")
        if self._restore_split_snapshot_if_cycle(stories_snapshot, label=f"{task_id}/split"):
            return False
        title_list = ", ".join(t.title or t.id for t in new_tasks)
        self._log(f"split:{task_id}", f"🪓 Tâche {task_id} re-découpée en {len(new_tasks)} sous-tâches plus fines après échec.")
        self._chat(ChatRole.ARCHITECT, f"[{task_id}] Re-découpage plus fin après échec → {title_list}.")
        return True

    def _safe_split_depends(self, parent: UserStory, failed: Task) -> list[str]:
        """Keep only upstream deps that cannot point back into the split subtree."""
        graph = work_streams.build_work_graph(self.state)
        downstream = work_streams.transitive_dependents(graph, {failed.id})
        children: dict[str, list[UserStory]] = {}
        by_id = {s.id: s for s in self.state.stories}
        for story in self.state.stories:
            if story.parent_id:
                children.setdefault(story.parent_id, []).append(story)

        unsafe_stories: set[str] = {parent.id}
        cur = parent
        while cur.parent_id and cur.parent_id in by_id:
            unsafe_stories.add(cur.parent_id)
            cur = by_id[cur.parent_id]
        stack = [parent.id]
        while stack:
            sid = stack.pop()
            for child in children.get(sid, ()):
                if child.id not in unsafe_stories:
                    unsafe_stories.add(child.id)
                    stack.append(child.id)

        unsafe_items = {failed.id}
        for story in self.state.stories:
            if story.id in unsafe_stories:
                unsafe_items.update(t.id for t in story.tasks)

        safe: list[str] = []
        for dep in failed.depends_on:
            targets = set(work_streams.dependency_targets(dep, failed.id, self.state))
            if (
                dep in unsafe_stories
                or dep in unsafe_items
                or dep in downstream
                or targets & (unsafe_items | downstream)
            ):
                continue
            if dep not in safe:
                safe.append(dep)
        return safe

    def _restore_split_snapshot_if_cycle(self, stories_snapshot: list[UserStory], *, label: str) -> bool:
        # RAW graph (break_cycles=False): this guard's job is to DETECT the cycle
        # a split remap just created and roll the whole split back — the default
        # ingestion-time breaking would hide it.
        cycle = work_streams.detect_cycle(
            work_streams.build_work_graph(self.state, break_cycles=False)
        )
        if not cycle:
            return False
        self.state.stories = stories_snapshot
        self._log(
            f"split:{label}",
            "Split refusé : cycle de dépendances résolu détecté ("
            + " → ".join(cycle)
            + ").",
        )
        return True

    def _make_technical_story(
        self,
        parent: UserStory,
        failed: Task,
        tasks: list[Task],
        *,
        depends_on: list[str] | None = None,
    ) -> UserStory:
        """RFC technical-stories: build the TS that absorbs a too-big task's finer
        sub-tasks — a non-functional container (``technical=True``, no functional
        Gherkin, a technical ``contract``) tied to its origin via ``parent_id``,
        carrying the failed task's upstream deps at the story level (inherited by
        its tasks). Its id is unique project-wide."""
        taken = {s.id for s in self.state.stories} | {t.id for t in self.state.all_tasks()}
        tid = f"TS-{failed.id}"
        while tid in taken:
            tid += "x"
        contract = failed.description or failed.gherkin or failed.title or failed.id
        return UserStory(
            id=tid,
            epic_id=parent.epic_id,
            title=f"TS · {failed.title or failed.id}",
            technical=True,
            contract=contract,
            parent_id=parent.id,
            gherkin="",
            stream=failed.stream or parent.stream,
            tasks=tasks,
            depends_on=list(depends_on if depends_on is not None else failed.depends_on),
            split_depth=failed.split_depth + 1,
            iteration=parent.iteration,
        )

    async def _ajudge_independence(self) -> None:
        """P4d: optional LLM independence judge (INDEPENDENCE, OFF). For
        each story with ≥2 tasks it completes the tasks' file claims and may add
        serialization edges, THEN re-runs the deterministic floor so the final
        graph is safe. Non-fatal: any failure leaves the floor-only result (which
        is already safe). Runs once before the parallel scheduler."""
        if not settings.independence_enabled:
            return
        for story in self.state.stories:
            tasks = story.tasks
            if len(tasks) < 2:
                continue
            payload = [
                {
                    "id": t.id, "stream": t.stream or self.state.primary_stream_id,
                    "title": t.title, "description": t.description,
                    "file_globs": list(t.files_hint), "depends_on": list(t.depends_on),
                }
                for t in tasks
            ]
            try:
                result = await self._tracked.arun(
                    prompts.independence_judge(payload),
                    system_prompt=persona("independence-judge"),
                )
                reply = extract_json(result.text)
            except AgentError as exc:
                self._log(f"independence:{story.id}", f"Juge indisponible ({exc}) — floor déterministe seul.")
                continue
            by_id = {t.id: t for t in tasks}
            raw_claims = reply.get("claims")
            claims = raw_claims if isinstance(raw_claims, dict) else {}
            for tid, globs in claims.items():
                t = by_id.get(tid)
                if t is not None and isinstance(globs, list):
                    completed = [str(g) for g in globs if str(g).strip()]
                    if completed:
                        t.files_hint = completed
            for edge in reply.get("add_dependency") or []:
                if not isinstance(edge, dict):
                    continue
                t = by_id.get(str(edge.get("task")))
                dep = str(edge.get("depends_on") or "")
                if t is not None and dep in by_id and dep != t.id and dep not in t.depends_on:
                    t.depends_on.append(dep)
            # Re-run the floor with the completed claims (adds any edge the judge missed).
            self._enforce_task_independence(tasks, label=f"{story.id}/judge")
        self._sync()

    def _item_claim(self, item: "work_streams.WorkItem") -> "independence.TaskClaim":
        """P4c: the file-claim used by the independence floor to decide whether an
        item may co-run with the in-flight ones. A task's claims are its
        ``files_hint`` (empty ⇒ "the whole stream" ⇒ serialized by default); a
        taskless story claims its whole stream too (no per-file granularity)."""
        globs: tuple[str, ...] = ()
        if item.kind == "task":
            try:
                globs = tuple(self.state.task(item.id).files_hint)
            except KeyError:
                globs = ()
        return independence.TaskClaim(
            id=item.id,
            stream=item.stream or "",
            file_globs=globs,
            depends_on=tuple(item.depends_on),
        )

    def _find_item_target(self, wid: str):
        """Resolve a work-item id (task id or story id) to its persistent model,
        or None if it no longer exists (defensive — the plan may have changed)."""
        try:
            return self.state.task(wid)
        except KeyError:
            pass
        try:
            return self.state.story(wid)
        except KeyError:
            return None

    def _fail_item_by_id(self, wid: str, last_error: str) -> None:
        """P0b: mark a single work item FAILED by id (used when a worker crashes
        outside the per-item handler). Best-effort — never raises."""
        target = self._find_item_target(wid)
        if target is None:
            return
        target.status = StoryStatus.FAILED
        target.last_error = last_error
        self._set_stage(target, BuildStage.FAILED, sync=False)

    def _reset_orphan_items(self) -> int:
        """P0c: when no build worker is active, any story/task left mid-flight
        (IN_PROGRESS / GREEN / RED) is an ORPHAN from a crash or restart — the
        green/in-progress code lives only in a now-gone worktree. Reset them to
        TODO so resume/retry actually rebuilds them (the old resume only reset
        RED tasks, so an IN_PROGRESS orphan was silently skipped forever and the
        whole project stayed stuck). Returns the number reset."""
        transient = (StoryStatus.IN_PROGRESS, StoryStatus.GREEN, StoryStatus.RED)
        n = 0
        for story in self.state.stories:
            if story.status in transient:
                story.status = StoryStatus.TODO
                n += 1
            for task in story.tasks:
                if task.status in transient:
                    task.status = StoryStatus.TODO
                    task.last_error = ""
                    self._set_stage(task, BuildStage.QUEUED, sync=False)
                    n += 1
        if n:
            self.state.calibration_for().orphan_resets += n  # §8
        return n

    async def _abuild_work_item(self, item: "work_streams.WorkItem") -> None:
        """ST-9/10/11: build ONE work item in its own git worktree, then merge.

        Worktree lifecycle (ST-10): add a worktree on a fresh per-item branch off
        the project repo's current HEAD, run the dev → verify loop there, and on
        green commit + merge the branch back into the repo (serialized via
        ``_merge_lock``; one retry then abort+FAILED on conflict). The worktree
        and branch are always cleaned up in ``finally``."""
        # O2: attribute every agent call made while building this item to it.
        # Isolated to this worker's Task context (see _BUILD_ITEM), so no reset.
        _BUILD_ITEM.set(item.id)
        target = self._item_target(item)
        subject = self._item_subject(item)
        target.status = subject.status = StoryStatus.IN_PROGRESS
        target.attempts = subject.attempts = subject.attempts + 1
        # B1: a retry (attempts > 1) re-entering the build is a recovery state.
        if target.attempts > 1:
            self._set_recovery(
                target, "retry", attempt=target.attempts,
                max_attempts=settings.dev_max_attempts, sync=False,
            )
        self._sync()

        ws = workspace_dir(self.state.id)
        pkg = workspace.package_name(self.state)
        is_frontend = self._is_frontend_story(subject)
        # The acceptance feature files were written + committed to the shared
        # repo by the batch loop before this worker started, so they are already
        # present at the worktree's HEAD (no per-item commit here — that would
        # race other workers on the repo index).
        branch = f"autospec/wi-{item.id.lower().replace('/', '-')}"
        worktree = None
        keep_branch = False
        try:
            # P2b: a previous attempt may have left a PRESERVED green branch —
            # merge-conflict requeue (keep_branch below), or a hard crash whose
            # ``finally`` never ran (GREEN orphan). Resume it rebased onto the
            # updated HEAD instead of regenerating the code from scratch.
            resumed = await self._aresume_green_branch(ws, branch)
            worktree = resumed if resumed is not None else await self._aworktree_add(ws, branch)
            if worktree is None:
                raise RuntimeError("git worktree indisponible")
            if subject.attempts == 1 and not is_frontend:
                self._set_stage(target, BuildStage.ANALYZING, "qa")  # N4/B1
                await self._adesign_tests(subject, pkg)
            label = "dev frontend" if is_frontend else "dev"

            ok, tail = False, ""
            dev_ran = False
            if resumed is not None:
                # Re-verify the preserved work on the rebased branch: still
                # green → merge below with NO dev run at all.
                ok, tail = await self._averify_resumed(subject, worktree, is_frontend)
                self._log(
                    f"dev:{item.id}",
                    f"♻️ {item.id} : branche verte préservée revalidée sur HEAD à jour — merge sans rebuild."
                    if ok
                    else f"♻️ {item.id} : travail préservé rouge après rebase — l'agent {label} reprend depuis ce code.",
                )
            if not ok:
                if resumed is None:
                    self._log(f"dev:{item.id}", f"Agent {label} assigné à {item.id} — {subject.title}")
                dev_ran = True
                ok, tail = await self._arun_item_dev(subject, worktree, pkg, is_frontend)

            if ok:
                # ST-10/11: commit in the worktree, then merge into the repo. The
                # item is DONE only after a successful merge (so dependents only
                # start once this item's code is in the base HEAD).
                await self._acommit_story(worktree, item.id)
                if dev_ran:
                    # §8: measure the dev's REAL footprint (files in its commit)
                    # against the leaf budget — the ground truth the plan-time
                    # estimate (file_globs/estimated_files) must be judged by.
                    await self._arecord_footprint(item, worktree)
                    # Scope gate (separation loop, proactive half): out-of-scope
                    # edits are reverted-if-harmless BEFORE the merge, or kept
                    # but declared — a conflict seed never reaches HEAD unseen.
                    await self._aenforce_file_scope(
                        item, subject, target, ws, worktree, branch, is_frontend
                    )
                # P2b: from here the branch holds committed GREEN work — keep it
                # on cleanup (requeue, stop, manual retry) so the next pass can
                # resume it; dropped again once merged or split.
                keep_branch = True
                # B1/B6: green → waiting for the merge lock, then merging.
                self._set_stage(target, BuildStage.MERGE_WAIT, "")
                merged, conflict_files = await self._amerge_work_item(
                    ws, branch, item.id, worktree
                )
                # Canari : un revert post-merge est un conflit SÉMANTIQUE — il
                # partage la mécanique de requeue du conflit de merge mais pas
                # son diagnostic (pas de fichiers en collision à recalibrer).
                semantic_revert = False
                if merged:
                    # Canari post-merge : vert + vert peut faire ROUGE combiné
                    # (conflit sémantique — deux items compatibles avec HEAD
                    # mais pas entre eux). La suite est rejouée sur le HEAD
                    # fraîchement mergé ; rouge → le merge est REVERTÉ (HEAD
                    # reste toujours vert pour les items suivants) et l'item
                    # re-queué comme un conflit, branche verte préservée.
                    canary_ok, canary_kind, canary_tail = await self._apost_merge_canary(
                        item, is_frontend
                    )
                    # Seul un rouge SÉMANTIQUE (conflit de code réel) justifie un
                    # revert. Un rouge d'INFRA (venv/outil) ne se répare pas en
                    # jetant le merge — le canari a déjà tenté la reconstruction,
                    # on garde le vert et on signale.
                    if canary_kind == "semantic" and await self._arevert_head_merge(ws, item.id):
                        merged = False
                        semantic_revert = True
                        self.state.calibration_for().canary_reverts += 1  # §8
                        self._conflict_retry_ids.add(item.id)  # retry strict
                        target.last_error = (
                            "conflit sémantique post-merge (suite rouge sur le "
                            f"HEAD combiné) :\n{canary_tail}"
                        )
                        lesson = (
                            f"Itération {self.state.iteration} : « {getattr(target, 'title', '') or item.id} » "
                            "était verte isolément mais ROUGE une fois mergée avec ses voisines "
                            "(conflit sémantique) — expliciter les contrats partagés entre unités "
                            "parallèles ou prévoir une story d'intégration qui les compose."
                        )
                        if lesson not in self.state.sizing_lessons:
                            self.state.sizing_lessons.append(lesson)
                        self.state.sizing_lessons = self.state.sizing_lessons[-12:]
                    elif canary_kind == "semantic":
                        # Revert impossible : on ne peut pas mieux faire que
                        # livrer l'item en signalant BRUYAMMENT le HEAD rouge.
                        self._notify(
                            "warning", "Canari post-merge rouge",
                            f"{item.id} mergé mais la suite combinée est rouge et le revert a échoué.",
                        )
                    elif not canary_ok:  # canary_kind == "infra"
                        # Rouge d'infra persistant : le merge est conservé (le
                        # code est bon), mais l'environnement partagé est cassé —
                        # à signaler pour que le prochain run le voie.
                        self._notify(
                            "warning", "Canari post-merge : infra rouge",
                            f"{item.id} mergé mais l'outillage partagé est indisponible "
                            "(venv/toolchain), pas un conflit de code.",
                        )
                if merged:
                    keep_branch = False  # P2b: merged into HEAD — branch is useless now
                    if not dev_ran:
                        # §8: a preserved branch shipped without any dev rebuild.
                        self.state.calibration_for().p2b_resumes += 1
                    target.status = subject.status = StoryStatus.DONE
                    for test in subject.test_plan:
                        if test.status == TestState.NONEXISTENT:
                            test.status = TestState.GREEN
                    if item.kind == "story":
                        self.state.story(item.story_id).test_plan = subject.test_plan
                    self._set_recovery(target, "", sync=False)  # B1: clear
                    self._set_stage(target, BuildStage.DONE, sync=False)  # B1
                    self._log(f"dev:{item.id}", f"✅ {item.id} vert et mergé.")
                else:
                    # ST-10/11: a merge conflict means a sibling work item changed
                    # the SAME files. An immediate same-inputs retry (in
                    # _amerge_work_item) can never resolve it. Re-queue the item:
                    # the green branch is PRESERVED (keep_branch) so the next
                    # scheduler pass resumes it — rebase on the now-updated HEAD,
                    # re-verify, merge — instead of regenerating the code. Bounded
                    # by dev_max_attempts; a persistent conflict tries a finer
                    # split (disjoint file zones) before ending FAILED.
                    # Separation loop: the branch's REAL touched files recalibrate
                    # the item's declared claims, the retry is scheduled STRICTLY
                    # (no co-run with a possible rival), and a sizing lesson
                    # feeds the next plan (§6). A semantic revert (canary) took
                    # its own diagnosis above — only the requeue tail is shared.
                    if not semantic_revert:
                        self.state.calibration_for().merge_requeues += 1  # §8
                        touched = await self._abranch_files(ws, branch)
                        self._register_merge_conflict(item, target, conflict_files, touched)
                    if subject.attempts < settings.dev_max_attempts:
                        target.status = subject.status = StoryStatus.TODO
                        self._set_stage(target, BuildStage.QUEUED, sync=False)  # B1: requeue
                        self._log(
                            f"dev:{item.id}",
                            f"⚠️ Conflit de merge {item.id} — branche verte conservée, reprise "
                            f"sur HEAD à jour (tentative {subject.attempts + 1}/{settings.dev_max_attempts}).",
                        )
                    # A PERSISTENT conflict is a sizing smell: the unit claims file
                    # zones that keep colliding with its siblings. Try the adaptive
                    # finer split (smaller, disjoint sub-tasks) before failing.
                    elif await self._amaybe_split_on_failure(item, subject, target):
                        keep_branch = False  # the unit was replaced by finer sub-tasks
                    else:
                        # Terminal FAILED: keep the branch — a manual retry
                        # (aretry_failed) can still resume the green work.
                        target.status = subject.status = StoryStatus.FAILED
                        self._set_stage(target, BuildStage.FAILED, sync=False)  # B1
            else:
                target.last_error = tail
                self._log(f"dev:{item.id}", f"❌ Tests rouges après passage du dev:\n{tail}")
                # P2c — reprise incrémentale : le travail ROUGE (partiel) est
                # committé et sa branche préservée. La prochaine tentative la
                # REPREND (rebase + le dev répare dans le même worktree, avec
                # l'erreur précédente en contexte) au lieu de tout régénérer.
                await self._acommit_wip(worktree, item.id)
                keep_branch = True
                if subject.attempts < settings.dev_max_attempts:
                    target.status = StoryStatus.TODO
                    self._set_stage(target, BuildStage.QUEUED, sync=False)  # B1: requeue
                # P6: attempts exhausted → try an adaptive FINER split before failing
                # (the unit was likely too big for one agent session). If it splits,
                # the new sub-tasks build on the next scheduler pass.
                elif await self._amaybe_split_on_failure(item, subject, target):
                    keep_branch = False  # the unit was replaced by finer sub-tasks
                else:
                    # Terminal FAILED: the partial branch stays — a manual retry
                    # (aretry_failed) resumes the preserved work.
                    target.status = StoryStatus.FAILED
                    self._set_stage(target, BuildStage.FAILED, sync=False)  # B1
        except AgentError as exc:
            target.last_error = str(exc)
            if settings.agent_provider == "claude code" and session_monitor.is_usage_limit_error(str(exc)):
                target.attempts = max(0, target.attempts - 1)
                subject.attempts = max(0, subject.attempts - 1)
                target.status = subject.status = StoryStatus.TODO
                if not session_monitor.monitor_active():
                    self.state.phase = PipelinePhase.NEEDS_ATTENTION
                    self._stop_requested = True
            else:
                # Infra/provider failure (CLI killed, transport error…) : ce
                # n'est PAS un échec du dev — on rembourse la tentative dev et
                # on consomme le budget infra séparé, pour qu'une panne
                # transitoire ne puisse jamais faire FAILED un item à elle
                # seule (ni polluer la calibration de dimensionnement).
                target.attempts = subject.attempts = max(0, subject.attempts - 1)
                target.infra_attempts += 1
                self.state.calibration_for().infra_retries += 1  # §8
                if target.infra_attempts <= settings.infra_max_retries:
                    target.status = subject.status = StoryStatus.TODO
                    self._set_stage(target, BuildStage.QUEUED, sync=False)  # B1: requeue
                    self._log(
                        f"dev:{item.id}",
                        f"⚡ Panne d'infra sur {item.id} — tentative dev remboursée, "
                        f"retry infra {target.infra_attempts}/{settings.infra_max_retries}.",
                    )
                else:
                    target.status = subject.status = StoryStatus.FAILED
                    self._set_stage(target, BuildStage.FAILED, sync=False)  # B1
            self._log(f"dev:{item.id}", f"Erreur agent : {exc}")
        except Exception as exc:  # noqa: BLE001
            # P0b: an unexpected crash in ONE work item must not bubble up and
            # kill the whole build phase. Treat it like a red build: retry while
            # attempts remain, else FAIL this item only. (CancelledError is a
            # BaseException — it still propagates for cooperative stop.)
            target.last_error = f"crash worker : {exc}"
            target.status = (
                StoryStatus.TODO
                if subject.attempts < settings.dev_max_attempts
                else StoryStatus.FAILED
            )
            self._set_stage(
                target,
                BuildStage.QUEUED if target.status == StoryStatus.TODO else BuildStage.FAILED,
                sync=False,
            )
            self._log(f"dev:{item.id}", f"⛔ Crash worker {item.id} isolé : {exc}")
        finally:
            if worktree is not None:
                await self._aworktree_remove(ws, worktree, branch, keep_branch=keep_branch)
            self._sync()

    def _persistent_for(self, subject: UserStory):
        """Resolve the build subject back to its persistent model (UserStory or
        Task) so B1 stage/persona/recovery stamps land on the stored item. A
        taskless US's subject IS the stored story; a task's subject is a transient
        adapter, so we look the Task up by id (falling back to the subject itself
        when not found — e.g. a unit-test driving the helper directly)."""
        try:
            return self.state.task(subject.id)
        except KeyError:
            pass
        try:
            return self.state.story(subject.id)
        except KeyError:
            return subject

    async def _arun_item_dev(
        self, subject: UserStory, worktree, pkg: str, is_frontend: bool
    ) -> tuple[bool, str]:
        """Run the dev agent for one work item INSIDE its worktree, then verify
        the real suite there. Returns (green, tail). No ``_build_lock``: the
        worktree is private to this item, so parallel items never interleave.

        The persistent model (UserStory/Task) is resolved from ``subject`` and
        stamped with the B1 stage + persona at each real transition."""
        target = self._persistent_for(subject)
        self._set_stage(target, BuildStage.IMPLEMENTING, "dev")  # N4/B1
        item_guidance = self._apply_guidance(target)  # P10
        # Séparation inter-stream : le dev reçoit son PÉRIMÈTRE FICHIERS (globs
        # déclarés — recalés sur l'observé après un conflit — sinon la zone de
        # son stream) pour ne jamais éditer les fichiers d'une unité parallèle.
        stream = self._story_stream(subject)
        file_scope = prompts.file_scope_block(
            list(getattr(target, "files_hint", []) or []),
            stream_zone=stream.file_root or "",
        )
        # Retry informé : l'échec de la tentative précédente entre dans le
        # prompt (sinon le retry rejoue la même loterie à l'aveugle).
        previous_failure = prompts.previous_failure_block(
            getattr(target, "last_error", "") or "", subject.attempts
        )
        # Anti-conflit sémantique proactif : les contrats des dépendances (déjà
        # mergées dans HEAD) sont pointés au dev — lire avant d'écrire.
        dependency_contracts = self._dependency_contracts(target)
        if is_frontend:
            # The frontend dev agent runs Vitest/`vite build` in its worktree —
            # ensure `node_modules` is present (shared install + junction) first,
            # else every frontend item fails with "Cannot find package 'vite'".
            await self._aensure_frontend_node_modules(
                Path(worktree) / (stream.file_root or "frontend")
            )
            dev_prompt = prompts.dev_story_frontend(
                subject, pkg, workspace.feature_rel_path(subject),
                architecture=self.state.architecture,
                guidance="\n".join(self.state.build_guidance),
                lessons="\n".join(self._effective_lessons()),
                file_root=stream.file_root or "frontend",
                item_guidance=item_guidance,
                available_skills=self._skills_catalog("dev"),
                file_scope=file_scope,
                previous_failure=previous_failure,
                dependency_contracts=dependency_contracts,
            )
            dev_persona = persona("dev-frontend")
        else:
            dev_prompt = prompts.dev_story(
                subject, pkg, workspace.feature_rel_path(subject), self.state.architecture,
                "\n".join(self.state.build_guidance),
                ui_tests=self._ui_mode(subject),
                lessons="\n".join(self._effective_lessons()),
                backend_language=self.state.backend_language.value,
                item_guidance=item_guidance,
                available_skills=self._skills_catalog("dev"),
                file_scope=file_scope,
                previous_failure=previous_failure,
                dependency_contracts=dependency_contracts,
            )
            dev_persona = persona("dev")
        result = await self._tracked.arun(dev_prompt, system_prompt=dev_persona, cwd=worktree)
        try:
            reply = extract_json(result.text)
        except AgentError:
            # La reponse JSON n'est qu'INFORMATIVE (resume, mapping des tests) :
            # la verite, c'est la suite executee ci-dessous. Un dev qui a bien
            # travaille mais repond mal formate ne perd pas son worktree.
            reply = {}
            self._log(
                f"dev:{subject.id}",
                "Reponse dev illisible (JSON) - la suite reelle fait foi.",
            )
        self._chat(ChatRole.DEV, f"[{subject.id}] {reply.get('summary', '(pas de résumé)')}")
        self._observe_file_budget(subject, reply)
        subject.status = StoryStatus.GREEN if reply.get("status") == "green" else StoryStatus.RED
        subject.ui_tests = [str(p) for p in reply.get("ui_test_files") or []]
        # B1: dev declared the failing tests (RED) → contracts written.
        if subject.status == StoryStatus.RED:
            self._set_stage(target, BuildStage.CONTRACTS, "dev", sync=False)
        self._set_stage(target, BuildStage.VERIFYING, "qa")  # N4/B1
        self._sync()

        if is_frontend:
            ok, output, real = await self._arun_frontend_tests(ws=worktree)
        else:
            ok, output, real = await self._arun_pytest(ws=worktree)
        tail = output[-2000:]
        self._apply_test_states(subject, reply.get("test_results", []), real)
        regs = regression.find_regressions(set(self.state.green_tests), real)
        if regs:
            rmsg = (
                f"[{subject.id}] {len(regs)} test(s) précédemment verts cassés : "
                + ", ".join(regs[:3]) + ("…" if len(regs) > 3 else "")
            )
            self.state.regressions.append(rmsg)
            self._notify("warning", "Régression détectée", rmsg)
            self._log(f"dev:{subject.id}", "⚠️ " + rmsg)
        if real:
            self.state.green_tests = sorted(n for n, o in real.items() if o == "passed")
        if ok and self._ui_mode(subject):
            if not subject.ui_tests:
                ok = False
                tail = (
                    "Aucun test UI rejouable déclaré pour cette story UI "
                    "(ui_test_files vide)."
                )
                self._log(f"dev:{subject.id}", f"❌ {tail}")
            else:
                ok, ui_output = await self._arun_ui_tests()
                if not ok:
                    tail = ui_output[-2000:]
                    self._log(f"dev:{subject.id}", "❌ Tests d'acceptance UI rouges.")
        if ok and settings.coverage_enabled and not is_frontend:
            cov = await self._arun_coverage(subject, pkg, worktree)
            if settings.coverage_gate_threshold > 0 and 0 <= cov < settings.coverage_gate_threshold:
                ok = False
                tail = (
                    f"Couverture insuffisante : {cov}% < seuil "
                    f"{settings.coverage_gate_threshold}% (gate de couverture)."
                )
                self._log(f"dev:{subject.id}", "❌ " + tail)
        if ok and not is_frontend:
            # Refinement + mutation testing run inside the item's worktree (they
            # rerun pytest / mutate the package) before the merge — Python only.
            if settings.refine_for("dev"):
                self._set_recovery(target, "refining")  # B1: critic loop
                await self._arefine_code(subject, pkg, worktree)
            self._set_recovery(target, "mutation_rerun")  # B1
            await self._arun_mutation_test(subject, pkg, worktree)
            self._set_recovery(target, "", sync=False)  # B1: clear
        return ok, tail

    # ------------------------------------------------ worktree lifecycle (ST-10)

    async def _aworktree_add(self, repo, branch: str):
        """Add a fresh git worktree on ``branch`` off the repo's HEAD and return
        its path, or None if git worktree is unavailable. Cleans up any stale
        branch/worktree of the same name first (a previous attempt).

        Serialized by ``_merge_lock``: ``git worktree add`` mutates the shared
        repo's ``.git`` metadata (and grabs its index lock), so concurrent adds
        from parallel workers would race — only the post-add dev/test work runs
        truly in parallel (in the now-private worktree)."""
        async with self._merge_lock:
            # Drop a leftover branch from an earlier attempt so `-b` cannot fail.
            # An interrupted build (crash/reload/cancel — the same kind that
            # leaves a task stuck IN_PROGRESS) can leave a stale worktree still
            # holding `branch` checked out; then a plain `branch -D` fails with
            # "used by worktree" and the fresh `worktree add -b` fails because the
            # branch still exists. So first unregister/remove any worktree on this
            # branch, THEN delete the branch.
            await self._aclear_stale_worktree(repo, branch)
            await self._agit(repo, "branch", "-D", branch)
            return await self._aworktree_add_locked(repo, branch)

    @staticmethod
    def _unlink_node_modules_junctions(worktree) -> None:
        """Detach every ``node_modules`` JUNCTION from a worktree before its
        directory is deleted. ``git worktree remove --force`` (and any naive
        recursive delete) follows the junction on Windows and destroys the
        SHARED frontend install it points to — the messagerie2 churn where the
        main ``node_modules`` was wiped after every item and a sibling's suite
        died mid-run on "Cannot find package 'vite'". ``os.rmdir`` on a
        junction removes only the reparse point, never the target."""
        root = Path(worktree)
        if not root.exists():
            return
        for pattern in ("node_modules", "*/node_modules", "*/*/node_modules"):
            for nm in root.glob(pattern):
                try:
                    is_junction = getattr(nm, "is_junction", lambda: False)()
                    if is_junction or nm.is_symlink():
                        os.rmdir(nm)
                except OSError:
                    pass

    async def _aclear_stale_worktree(self, repo, branch: str) -> None:
        """Remove any leftover git worktree checked out on ``branch`` (and prune
        dead admin records), so the branch becomes deletable and re-addable.
        Best-effort: every git call is tolerated. Caller holds ``_merge_lock``."""
        # Drop admin records of worktrees whose directory no longer exists.
        await self._agit(repo, "worktree", "prune")
        # Force-remove any worktree still registered on this branch (dir present).
        code, out = await self._agit(repo, "worktree", "list", "--porcelain")
        if code == 0:
            path: str | None = None
            for line in out.splitlines():
                if line.startswith("worktree "):
                    path = line[len("worktree ") :].strip()
                elif line.strip() == f"branch refs/heads/{branch}" and path:
                    # Detach shared node_modules junctions BEFORE git deletes
                    # the tree (it would recurse through them).
                    await asyncio.to_thread(self._unlink_node_modules_junctions, path)
                    await self._agit(repo, "worktree", "remove", "--force", path)
                    path = None
            await self._agit(repo, "worktree", "prune")

    @staticmethod
    def _new_worktree_path() -> Path:
        """A fresh directory path for a git worktree, NEXT TO the workspaces —
        never in ``%TEMP%``: Windows exposes the temp dir as an 8.3 SHORT path
        (``C:\\Users\\E6FB4~1.MIL\\…``) and Vite/Vitest percent-encode the ``~``
        when mapping file paths to module URLs, so setupFiles fail to load
        ("Failed to load url …%7E…setupTests.ts" — messagerie2 T5-S1-S1 : même
        branche, même commande, verte sous un chemin sans ``~``). ``resolve()``
        normalise tout composant court restant ; même volume que le repo, donc
        ``git worktree add`` est aussi moins coûteux."""
        import tempfile

        wt_root = settings.workspace_root / "_worktrees"
        wt_root.mkdir(parents=True, exist_ok=True)
        return Path(tempfile.mkdtemp(prefix="autospec-wt-", dir=str(wt_root))).resolve()

    async def _aworktree_add_locked(self, repo, branch: str):
        worktree = self._new_worktree_path()
        # mkdtemp creates the dir, but `git worktree add` wants to create it.
        try:
            worktree.rmdir()
        except OSError:
            pass
        # `-B` (create-or-reset to HEAD) rather than `-b`: if cleanup left the
        # branch behind (e.g. a Windows file lock blocked the worktree removal),
        # `-b` would fail "already exists"; `-B` resets it to the same start point
        # we want anyway, so the add is resilient.
        code, out = await self._agit(repo, "worktree", "add", str(worktree), "-B", branch, "HEAD")
        if code != 0:
            self._log("streams", f"git worktree add a échoué : {out.strip()[:200]}")
            return None
        return worktree

    async def _aworktree_remove(self, repo, worktree, branch: str, *, keep_branch: bool = False) -> None:
        """Always-runs cleanup: remove the worktree and delete its branch.
        Serialized by ``_merge_lock`` (shared-repo ``.git`` mutation).

        P2b: with ``keep_branch`` the branch ref survives (only the worktree
        directory goes) — used when the branch holds committed GREEN work that
        could not merge yet, so a later pass can resume it instead of
        regenerating the code."""
        async with self._merge_lock:
            # Detach shared node_modules junctions BEFORE git deletes the tree:
            # `git worktree remove --force` recurses through junctions on
            # Windows and would wipe the shared frontend install.
            await asyncio.to_thread(self._unlink_node_modules_junctions, worktree)
            await self._agit(repo, "worktree", "remove", "--force", str(worktree))
            if not keep_branch:
                await self._agit(repo, "branch", "-D", branch)
        # Defensive: if `worktree remove` could not delete the dir, drop it.
        try:
            if Path(worktree).exists():
                import shutil

                shutil.rmtree(worktree, ignore_errors=True)
        except OSError:
            pass

    async def _apost_merge_canary(
        self, item: "work_streams.WorkItem", is_frontend: bool
    ) -> tuple[bool, str, str]:
        """Rejoue la suite du stream de l'item sur le HEAD PARTAGÉ fraîchement
        mergé (POST_MERGE_CANARY, ON). Deux items verts chacun dans
        leur worktree peuvent être rouges COMBINÉS — le canari attrape ce
        conflit sémantique immédiatement.

        Retourne ``(ok, kind, tail)`` où ``kind`` ∈ {``"green"``, ``"semantic"``,
        ``"infra"``}. La distinction est CAPITALE : un rouge d'INFRA (venv
        partagée cassée, outil absent) n'est PAS un conflit de code — reverter le
        merge jetterait du travail vert sans rien réparer. Deux garde-fous :

        1. ``_arun_pytest`` purge d'abord une ``.venv`` invalide et sérialise le
           run (le rouge d'infra le plus courant s'auto-répare dès le 1er essai) ;
        2. si le rouge SUBSISTE et ressemble à de l'infra (aucun test collecté +
           signature d'outil), on force une purge de l'environnement et on rejoue
           UNE fois. Vert → c'était l'infra (``infra``, pas de revert). Toujours
           rouge, ou rouge avec des tests réellement en échec → ``semantic`` (le
           merge est reverté par l'appelant)."""
        if not self._setting("post_merge_canary"):
            return True, "green", ""
        run = self._arun_frontend_tests if is_frontend else self._arun_pytest
        ok, output, results = await run()
        if ok:
            return True, "green", ""
        # Rouge. Est-ce l'environnement plutôt que le code ?
        if not is_frontend and self._looks_like_infra_failure(output, results):
            self._log(
                f"dev:{item.id}",
                f"🐤 Canari ROUGE après {item.id} mais SANS test exécuté — "
                "suspicion d'infra (venv/outil). Réparation puis nouvel essai.",
            )
            self.monitor.event("canary", item=item.id, verdict="infra_suspected")
            await asyncio.to_thread(self._purge_venv_dir, workspace_dir(self.state.id))
            ok2, output2, _ = await self._arun_pytest()
            if ok2:
                self.state.calibration_for().infra_retries += 1  # §8
                self._log(
                    f"dev:{item.id}",
                    "✅ Canari VERT après reconstruction de l'environnement — "
                    f"le rouge de {item.id} venait de l'infra, PAS d'un conflit. "
                    "Merge conservé.",
                )
                self.monitor.event("canary", item=item.id, verdict="infra_healed")
                return True, "infra", output2[-1500:]
            # Toujours rouge après un environnement neuf : outage profond de
            # l'outillage. Reverter ne répare rien — on conserve le merge et on
            # signale bruyamment (kind infra) plutôt que de jeter du vert.
            self._log(
                f"dev:{item.id}",
                f"⛔ Canari toujours ROUGE après reconstruction — outillage "
                f"indisponible, pas un conflit de code. Merge de {item.id} conservé.",
            )
            self.monitor.event("canary", item=item.id, verdict="infra_persistent")
            return False, "infra", output2[-1500:]
        # Des tests ont réellement échoué → vrai conflit sémantique.
        self._log(
            f"dev:{item.id}",
            f"🐤 Canari post-merge ROUGE après le merge de {item.id} — "
            "conflit sémantique (vert+vert=rouge), revert du merge.",
        )
        self.monitor.event("canary", item=item.id, verdict="semantic")
        return False, "semantic", output[-1500:]

    async def _arevert_head_merge(self, repo, wid: str) -> bool:
        """Revert le commit de merge en tête de HEAD (celui de ``wid``), sous le
        merge lock — l'invariant « HEAD toujours vert » est restauré pour les
        items suivants. Best-effort : False si git refuse (HEAD reste rouge,
        signalé bruyamment par l'appelant)."""
        async with self._merge_lock.ahold(f"revert:{wid}"):
            code, out = await self._agit(repo, "revert", "-m", "1", "--no-edit", "HEAD")
            if code != 0:
                await self._agit(repo, "revert", "--abort")
                self._log(
                    "streams",
                    f"⛔ Revert du merge de {wid} impossible : {out.strip()[:200]}",
                )
                return False
        self._log("streams", f"↩️ Merge de {wid} reverté — HEAD redevient vert.")
        return True

    async def _aconflict_files(self, repo) -> list[str]:
        """The unmerged paths of the in-progress (failed) merge — read BEFORE
        ``merge --abort`` wipes the state. Best-effort: [] when git fails."""
        code, out = await self._agit(repo, "diff", "--name-only", "--diff-filter=U")
        if code != 0:
            return []
        return [line.strip() for line in out.splitlines() if line.strip()]

    async def _aresolve_manifest_conflicts(self, repo, conflict_files: list[str]) -> bool:
        """Auto-resolve a merge whose ONLY conflicts are dependency MANIFESTS
        (union of the dependency lists) and their lockfiles (kept at HEAD —
        regenerated by the toolchain, not line-merged). Runs INSIDE the
        conflicted merge state, before any abort: each resolved file is staged;
        True → the caller commits the merge. Conservative: any file it cannot
        confidently merge → False, nothing staged is trusted, normal conflict
        handling resumes."""
        if not manifests.is_manifest_conflict(conflict_files):
            return False
        for path in conflict_files:
            rel = path.strip().replace("\\", "/")
            name = rel.rsplit("/", 1)[-1]
            if name in manifests.LOCKFILES:
                code, _ = await self._agit(repo, "checkout", "--ours", "--", rel)
                if code != 0:
                    return False
            else:
                ours_code, ours = await self._agit(repo, "show", f":2:{rel}")
                theirs_code, theirs = await self._agit(repo, "show", f":3:{rel}")
                if ours_code != 0 or theirs_code != 0:
                    return False
                merged = (
                    manifests.merge_pyproject(ours, theirs)
                    if name == "pyproject.toml"
                    else manifests.merge_package_json(ours, theirs)
                )
                if merged is None:
                    return False
                try:
                    (Path(repo) / rel).write_text(merged, encoding="utf-8")
                except OSError:
                    return False
            code, _ = await self._agit(repo, "add", "--", rel)
            if code != 0:
                return False
        return True

    async def _abranch_files(self, repo, branch: str) -> list[str]:
        """Every file the item's branch REALLY touched since it diverged from
        HEAD (all its commits, not just the last) — the observed footprint that
        recalibrates the item's declared file claims after a merge conflict.
        Best-effort: [] when git fails."""
        code, out = await self._agit(repo, "diff", "--name-only", f"HEAD...{branch}")
        if code != 0:
            return []
        return [line.strip() for line in out.splitlines() if line.strip()]

    def _dependency_contracts(self, target) -> str:
        """The prompt block naming the CONTRACTS of the item's dependencies
        (already merged into HEAD when it starts): technical-story ``contract``
        when present, else description/title, plus their touched files — so the
        dev READS them before writing instead of redefining them (the root of
        green+green=red semantic conflicts)."""
        deps: list[dict] = []
        for dep_id in list(getattr(target, "depends_on", None) or []):
            dep = self._find_item_target(dep_id)
            if dep is None:
                continue
            summary = (
                (getattr(dep, "contract", "") or "").strip()
                or (getattr(dep, "description", "") or "").strip()
                or (getattr(dep, "title", "") or "").strip()
            )
            deps.append(
                {
                    "id": dep_id,
                    "title": getattr(dep, "title", "") or "",
                    "summary": summary,
                    "files": list(getattr(dep, "files_hint", None) or []),
                }
            )
        return prompts.dependency_contracts_block(deps)

    def _merge_scope_hints(self, target, files: list[str]) -> None:
        """Fold OBSERVED files into the item's declared claims (``files_hint``)
        so the independence floor and the scheduler guard reason on reality."""
        if not hasattr(target, "files_hint"):
            return  # taskless UserStory: no per-file claims to recalibrate
        hints = list(target.files_hint)
        for f in files:
            if f and f not in hints:
                hints.append(f)
        target.files_hint = hints

    async def _aenforce_file_scope(
        self,
        item: "work_streams.WorkItem",
        subject: UserStory,
        target,
        ws,
        worktree,
        branch: str,
        is_frontend: bool,
    ) -> None:
        """Deterministic pre-merge SCOPE GATE (separation loop, proactive half).

        The dev prompt's « PÉRIMÈTRE FICHIERS » is only an instruction; this
        turns it into a verified contract. The branch's REAL footprint is
        compared to the item's declared scope (its file globs, else its stream
        zone). Out-of-scope edits — the raw material of inter-stream merge
        conflicts — get the « revert if harmless » treatment:

        - revert the strayed files to their base version and re-run the real
          suite in the worktree: still green → the edits were gratuitous and
          the conflict seed is removed BEFORE it can collide with a sibling;
        - suite red → the edits are load-bearing (e.g. a new dependency in
          ``pyproject.toml``): restore them, but DECLARE them (folded into
          ``files_hint``) so the scheduler guard serializes any rival.

        Either way the violation is counted (§8) and distilled into a sizing
        lesson for the next plan. Best-effort: on any git failure the branch is
        left as-is (the merge-conflict path stays the safety net); no declared
        scope at all (legacy taskless backend story) → nothing to enforce."""
        globs = [
            str(g) for g in (getattr(target, "files_hint", None) or []) if str(g).strip()
        ]
        stream = self._story_stream(subject)
        zone = (stream.file_root or "").strip().strip("/")
        if not globs and not zone:
            return
        observed = await self._abranch_files(ws, branch)
        out = [f for f in observed if not _file_in_scope(f, globs, zone)]
        if not out:
            return
        # Les MANIFESTES de dépendances (pyproject.toml / package.json + lockfiles)
        # ne sont JAMAIS strippés : leur retrait est un faux vert STRUCTUREL — la
        # .venv du worktree a déjà installé la dépendance, donc la suite reste
        # verte SANS la ligne du manifeste, mais le HEAD combiné, lui, ne peut
        # plus l'importer (c'est exactement le bug qui a fait tourner en rond une
        # génération entière). On les DÉCLARE (les rivaux se sérialisent) et
        # l'auto-fusion des manifestes règle la collision au moment du merge.
        manifest_out = [f for f in out if manifests.is_manifest_conflict([f])]
        if manifest_out:
            out = [f for f in out if f not in manifest_out]
            self._merge_scope_hints(target, manifest_out)
            self._log(
                f"dev:{item.id}",
                f"📦 Manifeste(s) hors périmètre DÉCLARÉ(s) plutôt que retiré(s) : "
                f"{', '.join(manifest_out[:5])} — les retirer serait un faux vert "
                "(dépendance déjà installée dans la venv), l'auto-fusion s'en charge.",
            )
        if not out:
            return
        listing = ", ".join(out[:5])
        self.state.calibration_for().scope_violations += 1  # §8
        self._log(
            f"dev:{item.id}",
            f"🚧 {item.id} a modifié {len(out)} fichier(s) HORS de son périmètre "
            f"({listing}) — tentative de retrait avant merge.",
        )
        code, base = await self._agit(ws, "merge-base", "HEAD", branch)
        _, tip = await self._agit(worktree, "rev-parse", "HEAD")
        base, tip = base.strip(), tip.strip()
        if code != 0 or not base or not tip:
            self._merge_scope_hints(target, out)
            return
        for f in out:
            restored, _ = await self._agit(worktree, "checkout", base, "--", f)
            if restored != 0:  # the file did not exist at base: a stray NEW file
                await self._agit(worktree, "rm", "-f", "--ignore-unmatch", "--", f)
        if is_frontend:
            ok, _, _ = await self._arun_frontend_tests(ws=worktree)
        else:
            ok, _, _ = await self._arun_pytest(ws=worktree)
        if ok:
            await self._agit(worktree, "add", "-A")
            await self._agit(
                worktree, "commit", "-m",
                f"scope gate: retire les fichiers hors périmètre de {item.id}",
            )
            self._log(
                f"dev:{item.id}",
                f"✂️ Hors-périmètre retiré ({listing}) — la suite reste verte, la "
                "graine de conflit est éliminée avant merge.",
            )
            action = "modifications superflues, retirées avant merge"
        else:
            await self._agit(worktree, "reset", "--hard", tip)
            await self._agit(worktree, "clean", "-fd")
            self._merge_scope_hints(target, out)
            self._log(
                f"dev:{item.id}",
                f"⚠️ Retrait impossible (suite rouge sans {listing}) — fichiers "
                "conservés mais DÉCLARÉS : les rivaux seront sérialisés.",
            )
            action = "modifications porteuses, conservées et déclarées"
        lesson = (
            f"Itération {self.state.iteration} : « {getattr(target, 'title', '') or item.id} » "
            f"a débordé de son périmètre fichiers sur {listing} ({action}) — déclarer des "
            "file_globs complets dès le plan, ou prévoir une tâche d'intégration dédiée."
        )
        if lesson not in self.state.sizing_lessons:
            self.state.sizing_lessons.append(lesson)
        self.state.sizing_lessons = self.state.sizing_lessons[-12:]

    async def _arecord_footprint(self, item: "work_streams.WorkItem", worktree) -> None:
        """§8 — ground the sizing calibration on the dev's REAL footprint: count
        the files of the item's green commit and flag it over-budget when it
        exceeds ``task_file_budget``. The plan promised small disjoint leaves;
        this is the measurement that promise is judged by. Best-effort."""
        code, out = await self._agit(worktree, "show", "--name-only", "--format=", "HEAD")
        if code != 0:
            return
        files = [line for line in out.splitlines() if line.strip()]
        if len(files) > settings.task_file_budget:
            self.state.calibration_for().over_budget_tasks += 1
            self._log(
                f"dev:{item.id}",
                f"📏 {item.id} a touché {len(files)} fichiers (budget "
                f"{settings.task_file_budget}) — compté hors budget (calibration).",
            )

    async def _aresume_green_branch(self, repo, branch: str):
        """P2b/P2c — resume a PRESERVED branch from an earlier attempt (green
        work held back by a merge conflict, or a RED attempt's partial work).

        A merge-conflict requeue (``keep_branch``) or a hard crash (the worker's
        ``finally`` never ran) can leave ``branch`` behind with the item's green
        commits. Check it out in a fresh worktree and rebase it onto the repo's
        current HEAD, so the caller can re-verify and merge WITHOUT regenerating
        the code. Returns the worktree path, or None when there is nothing
        usable to resume — any stale branch is dropped so the caller falls back
        to a normal fresh build."""
        async with self._merge_lock:
            code, _ = await self._agit(
                repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"
            )
            if code != 0:
                return None
            code, out = await self._agit(repo, "rev-list", "--count", f"HEAD..{branch}")
            if code != 0 or not out.strip().isdigit() or int(out.strip()) == 0:
                # The branch carries nothing beyond HEAD (crash before commit,
                # or already merged): useless — drop it and build fresh.
                await self._aclear_stale_worktree(repo, branch)
                await self._agit(repo, "branch", "-D", branch)
                return None
            # A crashed worker may still hold the branch checked out in a dead
            # worktree — clear it or `worktree add` fails "already checked out".
            await self._aclear_stale_worktree(repo, branch)
            worktree = self._new_worktree_path()
            try:
                worktree.rmdir()
            except OSError:
                pass
            code, out = await self._agit(repo, "worktree", "add", str(worktree), branch)
            if code != 0:
                self._log("streams", f"Reprise de {branch} impossible : {out.strip()[:200]}")
                return None
            _, head = await self._agit(repo, "rev-parse", "HEAD")
        rb, _ = await self._agit(worktree, "rebase", head.strip())
        if rb != 0:
            # Genuine line-level conflict with what landed meanwhile: the old
            # work cannot be replayed — clean up fully and regenerate.
            await self._agit(worktree, "rebase", "--abort")
            await self._aworktree_remove(repo, worktree, branch)
            self._log("streams", f"♻️ Branche préservée {branch} en conflit réel — régénération.")
            return None
        self._log("streams", f"♻️ Branche verte préservée {branch} reprise (rebasée sur HEAD).")
        return worktree

    async def _averify_resumed(self, subject: UserStory, worktree, is_frontend: bool) -> tuple[bool, str]:
        """P2b: re-run the real suite on a resumed (rebased) green branch — no
        dev agent involved. Green means the preserved work is still valid on the
        updated HEAD and can merge as-is; red hands the worktree to the dev,
        which then starts from the preserved code instead of an empty slate."""
        target = self._persistent_for(subject)
        self._set_stage(target, BuildStage.VERIFYING, "qa")  # B1
        if is_frontend:
            stream = self._story_stream(subject)
            await self._aensure_frontend_node_modules(
                Path(worktree) / (stream.file_root or "frontend")
            )
            ok, output, _ = await self._arun_frontend_tests(ws=worktree)
        else:
            ok, output, _ = await self._arun_pytest(ws=worktree)
        if ok:
            subject.status = StoryStatus.GREEN
        return ok, output[-2000:]

    async def _amerge_work_item(
        self, repo, branch: str, wid: str, worktree=None
    ) -> tuple[bool, list[str]]:
        """ST-10: merge a green work item's branch into the project repo's main
        branch. Merges MUST be serialized (``_merge_lock``) even though builds
        run in parallel — concurrent merges race on the shared index/HEAD.

        Conflict policy (P2 — never lose green work): a ``--no-ff`` merge that
        conflicts means main moved ahead (a sibling merged a change to the same
        area). Rather than throwing the green branch away and regenerating it, we
        **rebase the branch onto the updated HEAD inside its worktree** then merge
        again — preserving the green work whenever the real edits don't truly
        conflict. Only a genuine line-level conflict (rebase fails) falls through
        to failure, where the caller re-queues for a fresh rebuild.

        Returns ``(merged, conflict_files)`` — the files that actually clashed
        (empty on success), so the caller can diagnose the collision, recalibrate
        the item's file claims and serialize the retry (inter-stream separation)."""
        # B6: hold the merge lock under this item's id so the tick can report
        # ``merge_lock_held:<wid>`` while others wait.
        conflict_files: list[str] = []
        async with self._merge_lock.ahold(wid):
            code, out = await self._agit(
                repo, "merge", "--no-ff", "-m", f"merge work item {wid}", branch
            )
            if code == 0:
                return True, []
            conflict_files = await self._aconflict_files(repo)
            # Manifest conflicts (pyproject/package.json/lockfiles) are the one
            # STRUCTURAL collision no zone separation can avoid — two parallel
            # tasks legitimately adding a dependency each. Union-merge them
            # deterministically instead of requeuing green work.
            if await self._aresolve_manifest_conflicts(repo, conflict_files):
                code, _ = await self._agit(repo, "commit", "--no-edit")
                if code == 0:
                    self._log(
                        "streams",
                        f"🧩 {wid} : conflit de manifeste auto-résolu (union des "
                        f"dépendances de {', '.join(conflict_files[:3])}).",
                    )
                    return True, []
            await self._agit(repo, "merge", "--abort")
            # P2: preserve the green branch — rebase it onto the now-updated HEAD
            # (which holds the sibling's commits), then merge the rebased branch.
            if worktree is not None:
                _, head = await self._agit(repo, "rev-parse", "HEAD")
                head = head.strip()
                rb, _ = await self._agit(worktree, "rebase", head)
                if rb == 0:
                    code, out = await self._agit(
                        repo, "merge", "--no-ff", "-m", f"merge work item {wid} (rebased)", branch
                    )
                    if code == 0:
                        self._log(
                            "streams",
                            f"✅ {wid} préservé : rebase sur HEAD à jour puis merge.",
                        )
                        return True, []
                    for f in await self._aconflict_files(repo):
                        if f not in conflict_files:
                            conflict_files.append(f)
                    await self._agit(repo, "merge", "--abort")
                else:
                    await self._agit(worktree, "rebase", "--abort")
                    self._log(
                        "streams",
                        f"⚠️ Rebase de {wid} en conflit réel (mêmes lignes) — régénération nécessaire.",
                    )
            listing = ", ".join(conflict_files[:5]) or "(fichiers non identifiés)"
            self._log(
                "streams",
                f"⛔ Merge de {wid} impossible — conflit sur : {listing}. {out.strip()[:200]}",
            )
            return False, conflict_files

    # ------------------------------------------------ per-story actions

    async def arebuild_story(self, sid: str) -> None:
        """Reset a finished story and rebuild it from scratch in the background.

        Raises KeyError if the story is unknown, ValueError (-> 409) if the
        pipeline is still active or the story is already being developed."""
        story = self.state.story(sid)  # KeyError if absent
        if self.state.phase not in (
            PipelinePhase.DONE,
            PipelinePhase.STOPPED,
            PipelinePhase.NEEDS_ATTENTION,
            PipelinePhase.ERROR,
        ):
            raise ValueError(
                "la pipeline est active : mets-la en pause ou attends la fin avant de relancer une story"
            )
        if self._task and not self._task.done():
            raise ValueError("une tâche est déjà en cours")
        if story.status == StoryStatus.IN_PROGRESS:
            raise ValueError("story déjà en cours")
        story.status = StoryStatus.TODO
        story.attempts = 0
        story.infra_attempts = 0
        story.last_error = ""
        for t in story.test_plan:
            t.status = TestState.NONEXISTENT
        # A decomposed story builds through its TASKS: without resetting them a
        # rebuild is a no-op — tasks still carry attempts == DEV_MAX_ATTEMPTS and
        # a stale last_error, so they re-fail instantly without any agent run.
        for task in story.tasks:
            task.status = StoryStatus.TODO
            task.attempts = 0
            task.infra_attempts = 0
            task.last_error = ""
        self._stop_requested = False
        self._delivery_blocked = False
        delivery_state.reset(self.state)
        # Set BUILD synchronously BEFORE launching the task so a second
        # concurrent call is rejected by the phase guard (closes the TOCTOU).
        self.state.phase = PipelinePhase.BUILD
        self._sync()
        self._task = asyncio.create_task(self._arebuild_one(story))

    async def _arebuild_one(self, story: UserStory) -> None:
        """Background task: build a single story and restore a terminal phase."""
        self.state.phase = PipelinePhase.BUILD
        self._sync()
        self._start_tick()  # B5: heartbeat during the rebuild
        self._log(f"dev:{story.id}", f"Relance de {story.id}…")
        try:
            await self._abuild_story(story)
            if not self._delivery_blocked:
                # Same gates as a full lifecycle run — an iteration finished
                # through a rebuild must not skip smoke/runtime/docker.
                await self._adelivery_gates()
        except Exception as exc:  # never leave the pipeline in a broken state
            self._chat(ChatRole.SYSTEM, f"Erreur lors de la relance de {story.id} : {exc}")
        finally:
            self._stop_tick()  # B5: rebuild done
            if self._stop_requested:
                self.state.phase = PipelinePhase.STOPPED
            elif self._delivery_blocked:
                self.state.phase = PipelinePhase.NEEDS_ATTENTION
            else:
                self.state.phase = PipelinePhase.DONE
            self._sync()

    async def aresume_build(self) -> None:
        """Resume the build phase of a dormant iteration in the background.

        After a backend restart, in-progress stories are reverted to TODO and
        the phase is set to STOPPED, but the iteration was never finished. This
        re-runs the build over the iteration's still-to-build stories (TODO or
        RED), then restores a terminal phase.

        Raises ValueError (-> 409) if the pipeline is still active, or if the
        current iteration has no story left to build."""
        if self.state.phase not in (
            PipelinePhase.STOPPED,
            PipelinePhase.DONE,
            PipelinePhase.NEEDS_ATTENTION,
            PipelinePhase.ERROR,
        ):
            raise ValueError("la pipeline est déjà active")
        if self._task and not self._task.done():
            raise ValueError("une tâche est déjà en cours")
        # P0c: no worker is active here (guards above), so any IN_PROGRESS/GREEN/RED
        # story or task is a crash/restart ORPHAN whose code is gone with its
        # worktree — reset it to TODO FIRST, otherwise an IN_PROGRESS orphan keeps
        # its parent US effective_status IN_PROGRESS, the filter below skips it, and
        # the project stays stuck forever (the exact todo_list_2 symptom).
        n_orphans = self._reset_orphan_items()
        if n_orphans:
            self._log("build", f"♻️ {n_orphans} item(s) orphelin(s) réinitialisé(s) avant reprise.")
        # Across ALL iterations: a dormant build can leave still-to-build stories
        # in any iteration, and the work pool must include earlier-iteration DONE
        # stories so dependencies resolve.
        # Effective status so a task-decomposed US that is half-built via its
        # tasks (some done, some pending) is also caught — its stored status may
        # be IN_PROGRESS/DONE even though work remains (the BUG3 « ▶ Continuer le
        # build » regression).
        to_build = [
            s
            for s in self.state.stories
            if s.effective_status() in (StoryStatus.TODO, StoryStatus.RED)
        ]
        if not to_build:
            raise ValueError("aucune story à construire")
        # The scheduler only picks TODO stories: revert the ones stranded in
        # RED (e.g. persisted mid-attempt before a restart) so they are rebuilt.
        # Resume = continuer (pas relancer) : on ne réinitialise QUE les tâches
        # pendantes (RED) d'une US décomposée, les tâches DONE sont préservées.
        for story in to_build:
            story.status = StoryStatus.TODO
            for task in story.tasks:
                if task.status == StoryStatus.RED:
                    task.status = StoryStatus.TODO
                    task.last_error = ""
        self._stop_requested = False
        self._delivery_blocked = False
        delivery_state.reset(self.state)
        # Set BUILD synchronously BEFORE launching the task so a second
        # concurrent call is rejected by the phase guard (closes the TOCTOU).
        self.state.phase = PipelinePhase.BUILD
        self._sync()
        self._task = asyncio.create_task(self._aresume_build_run(all_iterations=True))

    async def aretry_failed(self) -> None:
        """Reset every FAILED story (across ALL iterations) to TODO and rebuild
        them in one go (« relancer tous les échecs »). Reuses the resume-build
        run. Raises ValueError (-> 409) if the pipeline is active or there is no
        failed story to retry.

        Failures accumulate across iterations (a done project may carry failed
        stories from iterations 1..N), and the UI's failed count spans them all —
        so the retry must too, not just the current iteration."""
        if self.state.phase not in (
            PipelinePhase.STOPPED,
            PipelinePhase.DONE,
            PipelinePhase.NEEDS_ATTENTION,
            PipelinePhase.ERROR,
        ):
            raise ValueError("la pipeline est déjà active")
        if self._task and not self._task.done():
            raise ValueError("une tâche est déjà en cours")
        # H2: « relancer les échecs » must also unstick crash/restart ORPHANS
        # (IN_PROGRESS/GREEN/RED with no worker) — otherwise a project stuck on an
        # orphan (not a clean FAILED) reports "no failure to retry" and is dead.
        n_orphans = self._reset_orphan_items()
        if n_orphans:
            self._log("build", f"♻️ {n_orphans} item(s) orphelin(s) réinitialisé(s) avant relance.")
        # Effective status so a task-decomposed US that is failed via its tasks is
        # also caught (its stored status may be TODO); reset those tasks too.
        failed = [s for s in self.state.stories if s.effective_status() == StoryStatus.FAILED]
        if not failed and not n_orphans:
            raise ValueError("aucune story en échec à relancer")
        for story in failed:
            story.status = StoryStatus.TODO
            story.attempts = 0
            story.infra_attempts = 0
            story.last_error = ""
            for t in story.test_plan:
                t.status = TestState.NONEXISTENT
            for task in story.tasks:
                if task.status == StoryStatus.FAILED:
                    task.status = StoryStatus.TODO
                    task.attempts = 0
                    task.infra_attempts = 0
                    task.last_error = ""
        self._stop_requested = False
        self._delivery_blocked = False
        delivery_state.reset(self.state)
        # Phase -> BUILD synchronously before the task (closes the TOCTOU, like
        # aresume_build); the resume-build run rebuilds the now-TODO stories.
        self.state.phase = PipelinePhase.BUILD
        self._sync()
        self._chat(
            ChatRole.SYSTEM,
            f"🔄 Relance de {len(failed)} story(ies) en échec : "
            f"{', '.join(s.id for s in failed)}.",
        )
        self._task = asyncio.create_task(self._aresume_build_run(all_iterations=True))

    async def arestart_from_scratch(self) -> None:
        """« Relancer from scratch » : efface TOUT le travail dérivé (code généré,
        epics, user stories, tâches, streams, composants, backlog, leçons, usage…)
        SAUF le brief initial et l'identité/config du projet, puis relance la
        pipeline complète. Comme le brief est déjà présent, la phase spec saute
        l'interview PM (chemin I3) et enchaîne directement la planification PO puis
        le build global — exactement « ré-analyse PO + dev » demandé.

        Raises ValueError (-> 409) si la pipeline est active ou s'il n'y a aucun
        brief à partir duquel relancer."""
        if self.state.phase not in (
            PipelinePhase.STOPPED,
            PipelinePhase.DONE,
            PipelinePhase.NEEDS_ATTENTION,
            PipelinePhase.ERROR,
        ):
            raise ValueError("la pipeline est déjà active")
        if self._task and not self._task.done():
            raise ValueError("une tâche est déjà en cours")
        if not self.state.brief.strip():
            raise ValueError("aucun brief : lancez d'abord la spec avant de relancer from scratch")
        # The generated app may still hold file handles in the workspace, which
        # would block the wipe — stop its whole process tree first (node/esbuild
        # children keep node_modules open), then let the OS release the handles.
        await self.astop_app()
        await asyncio.sleep(0.3)  # grace: Windows frees handles shortly after taskkill
        # Wipe the generated workspace (code + git repo), defeating git's read-only
        # packs. Best-effort: a cache dir (node_modules/.venv) briefly held by a
        # just-killed process must NOT block the restart — the source + .git get
        # removed and any harmless cache remnant is tolerated (re-used/regenerated).
        fully = await asyncio.to_thread(force_delete_workspace, self.state.id, best_effort=True)
        if not fully:
            self._log(
                "build",
                "⚠️ Workspace partiellement verrouillé (cache node_modules/.venv ?) — "
                "réinitialisation poursuivie ; le cache résiduel est inoffensif.",
            )
        # Reset every DERIVED field; keep id/name/goal/config/brief/created_at.
        s = self.state
        s.epics = []
        s.stories = []
        s.streams = []
        s.components = []
        s.backlog = []
        s.feedback = []
        s.findings = []
        s.lessons = []
        s.green_tests = []
        s.regressions = []
        s.retro_recommendations = []
        s.build_guidance = []
        s.chat = []
        s.architecture = ""
        s.plan_quality = -1
        s.language_complexity = -1
        s.language_criticality = -1
        s.language_rationale = ""
        s.idea_maturity = ""
        s.idea_rationale = ""
        s.brainstorm_techniques = []
        s.awaiting_brainstorm_decision = False
        s.iteration = 1
        s.usage = Usage()
        s.iteration_usage = {}
        s.delivery_ready = False
        s.delivery_issues = []
        s.resume_at = 0.0
        s.error = ""
        s.running = False
        s.paused = False
        s.awaiting_approval = ""
        self._pm_session = None
        self._stop_requested = False
        self._delivery_blocked = False
        # P2: the interactions endpoint serves this LIVE in-memory store first, so
        # without clearing it the old items' activity would resurface after a
        # restart until the backend restarts.
        self.interactions.clear()
        delivery_state.reset(s)
        s.phase = PipelinePhase.SPEC
        self._sync()  # recreates the wiped workspace dir + persists the reset state
        self._chat(
            ChatRole.SYSTEM,
            "♻️ Projet relancé from scratch : brief conservé, code et plan régénérés "
            "(planification PO puis build global).",
        )
        # Reuse the normal lifecycle: spec sees the brief → skips the interview →
        # PO plan → architect → build, exactly like a fresh project with a brief.
        self.start()

    async def _aresume_build_run(self, all_iterations: bool = False) -> None:
        """Background task: re-run the build phase and restore a terminal phase.

        ``all_iterations`` builds every still-to-build story across all iterations
        (retry-failed / resume-build), not just the current one."""
        self._chat(ChatRole.SYSTEM, "▶ Reprise du build…")
        try:
            await self._abuild_phase(all_iterations=all_iterations)
            if not self._delivery_blocked:
                # Same gates as a full lifecycle run — an iteration finished
                # through resume-build must not skip smoke/runtime/docker.
                await self._adelivery_gates(all_iterations=all_iterations)
        except Exception as exc:  # never leave the pipeline in a broken state
            self._chat(ChatRole.SYSTEM, f"Erreur lors de la reprise du build : {exc}")
        finally:
            if self._stop_requested:
                self.state.phase = PipelinePhase.STOPPED
            elif self._delivery_blocked:
                self.state.phase = PipelinePhase.NEEDS_ATTENTION
            else:
                self.state.phase = PipelinePhase.DONE
            self._sync()

    async def aforce_done(self, sid: str) -> None:
        """Force a story to DONE (user override), marking its planned tests green.

        Raises KeyError if the story is unknown, ValueError (-> 409) if it is
        currently being developed."""
        story = self.state.story(sid)  # KeyError if absent
        if story.status == StoryStatus.IN_PROGRESS:
            raise ValueError("story en cours")
        story.status = StoryStatus.DONE
        story.last_error = ""
        for t in story.test_plan:
            t.status = TestState.GREEN
        self._sync()

    # --------------------------------------------------------- TASK actions (ST-13)

    async def arebuild_task(self, task_id: str) -> None:
        """ST-13: reset a single task and rebuild it from scratch in its own git
        worktree (reusing Lot 4's ``_abuild_work_item``), in the background.

        The per-task equivalent of ``arebuild_story``: same dormant-pipeline guard
        and TOCTOU phase handling. Raises KeyError if the task is unknown,
        ValueError (-> 409) if the pipeline is active or the task is in progress."""
        task = self.state.task(task_id)  # KeyError if absent
        if self.state.phase not in (
            PipelinePhase.DONE,
            PipelinePhase.STOPPED,
            PipelinePhase.NEEDS_ATTENTION,
            PipelinePhase.ERROR,
        ):
            raise ValueError(
                "la pipeline est active : mets-la en pause ou attends la fin avant de relancer une tâche"
            )
        if self._task and not self._task.done():
            raise ValueError("une tâche est déjà en cours")
        if task.status == StoryStatus.IN_PROGRESS:
            raise ValueError("tâche déjà en cours")
        task.status = StoryStatus.TODO
        task.attempts = 0
        task.infra_attempts = 0
        task.last_error = ""
        self._stop_requested = False
        self._delivery_blocked = False
        delivery_state.reset(self.state)
        # Set BUILD synchronously BEFORE launching the task so a second
        # concurrent call is rejected by the phase guard (closes the TOCTOU).
        self.state.phase = PipelinePhase.BUILD
        self._sync()
        self._task = asyncio.create_task(self._arebuild_one_task(task_id))

    async def _arebuild_one_task(self, task_id: str) -> None:
        """Background task: build a single task via the worktree build engine, then
        restore a terminal phase. Reuses ``_abuild_work_item`` (Lot 4) so the task
        is built in its own worktree and merged back exactly like a normal batch."""
        self.state.phase = PipelinePhase.BUILD
        self._sync()
        self._log(f"dev:{task_id}", f"Relance de {task_id}…")
        try:
            ws = workspace_dir(self.state.id)
            await self._agit_ensure_repo(ws)
            # Seed a base commit so the worktree can branch off a real HEAD.
            await self._acommit_story(ws, "scaffold")
            # Resolve the task to a WorkItem (RESOLVED deps) via the work graph.
            graph = work_streams.build_work_graph(self.state)
            item = graph.items.get(task_id)
            if item is None:
                raise KeyError(task_id)
            # Write the task's acceptance feature file to the shared repo before
            # the worktree branches off HEAD (mirrors the batch loop).
            subject = self._item_subject(item)
            if subject.gherkin.strip():
                workspace.write_feature_files(self.state, [subject])
                await self._acommit_story(ws, f"feature {task_id}")
            await self._abuild_work_item(item)
            if not self._delivery_blocked:
                self._apply_definition_of_done()
        except Exception as exc:  # never leave the pipeline in a broken state
            self._chat(ChatRole.SYSTEM, f"Erreur lors de la relance de {task_id} : {exc}")
        finally:
            if self._stop_requested:
                self.state.phase = PipelinePhase.STOPPED
            elif self._delivery_blocked:
                self.state.phase = PipelinePhase.NEEDS_ATTENTION
            else:
                self.state.phase = PipelinePhase.DONE
            self._sync()

    async def aforce_done_task(self, task_id: str) -> None:
        """ST-13: force a single task to DONE (user override). The per-task
        equivalent of ``aforce_done``. Raises KeyError if the task is unknown,
        ValueError (-> 409) if it is currently being developed."""
        task = self.state.task(task_id)  # KeyError if absent
        if task.status == StoryStatus.IN_PROGRESS:
            raise ValueError("tâche en cours")
        task.status = StoryStatus.DONE
        task.last_error = ""
        self._sync()

    async def asplit_item(self, item_id: str) -> None:
        """P6 — manual « découper plus finement » on a FAILED story or task: re-
        decompose it into finer sub-tasks (forced — bypasses the auto flag/depth),
        then resume the build so they get built. Raises ValueError(→409) if the
        pipeline is active or the item is not eligible (must be effectively
        FAILED), KeyError(→404) if unknown."""
        if self.state.phase not in (
            PipelinePhase.STOPPED,
            PipelinePhase.DONE,
            PipelinePhase.NEEDS_ATTENTION,
            PipelinePhase.ERROR,
        ):
            raise ValueError("la pipeline est déjà active")
        if self._task and not self._task.done():
            raise ValueError("une tâche est déjà en cours")
        graph = work_streams.build_work_graph(self.state)
        item = graph.items.get(item_id)
        if item is None:
            raise KeyError(item_id)
        target = self._item_target(item)
        if target.status != StoryStatus.FAILED:
            raise ValueError("seule une unité en échec peut être re-découpée")
        subject = self._item_subject(item)
        split = await self._amaybe_split_on_failure(item, subject, target, force=True)
        if not split:
            raise ValueError("unité jugée indivisible : aucun découpage plus fin possible")
        self._stop_requested = False
        self._delivery_blocked = False
        delivery_state.reset(self.state)
        self.state.phase = PipelinePhase.BUILD
        self._sync()
        self._task = asyncio.create_task(self._aresume_build_run(all_iterations=True))

    async def atask_diff(self, task_id: str) -> dict:
        """ST-13: the git diff committed when a task reached its green/merged
        state. A task's green commit is tagged ``story <task_id> done`` (see
        ``_abuild_work_item`` -> ``_acommit_story(worktree, item.id)``), so the
        story-diff lookup works unchanged on a task id. Raises KeyError if the
        task is unknown."""
        self.state.task(task_id)  # KeyError (-> 404) if absent
        ws = workspace_dir(self.state.id)
        code, out = await self._agit(
            ws, "log", "-1", "--format=%H", f"--grep=story {task_id} done"
        )
        commit = out.strip()
        if code != 0 or not commit:
            return {"available": False, "diff": ""}
        _, diff = await self._agit(ws, "show", commit)
        return {"available": True, "diff": diff[:200_000]}

    def _skills_catalog(self, role: str) -> str:
        """SK-1: compact "available skills" block for a QA/Dev prompt, or "" when
        skills are off for that role (so the prompt stays byte-identical)."""
        role_enabled = bool(getattr(settings, f"skills_{role}", True))
        return skill_lib.catalog_block(role) if self._setting("skills_enabled") and role_enabled else ""

    async def _adecompose_pending(self, all_iterations: bool = False) -> None:
        """SK-2: decompose each not-yet-decomposed backend story of the build
        pool into layered sub-tasks (best-effort, per story)."""
        pool = (
            self.state.stories
            if all_iterations
            else self.state.stories_of_iteration(self.state.iteration)
        )
        for story in pool:
            if (
                story.status in (StoryStatus.TODO, StoryStatus.RED)
                and not story.tasks
                and not self._is_frontend_story(story)
            ):
                await self._adecompose_story(story)

    async def _adecompose_story(self, story: UserStory) -> None:
        """Ask the architect to split a backend story into layered sub-tasks
        (entity → service → endpoint → tests), materialized as the story's Tasks
        so the parallel worktree engine builds each in a focused subagent (tiny
        context window) and aggregates them. Non-fatal and conservative: a failure
        or a trivial (<2 tasks) split leaves the story taskless (built whole)."""
        pkg = workspace.package_name(self.state)
        self._log(f"decompose:{story.id}", f"Décomposition de {story.id} en sous-tâches par couche…")
        try:
            result = await self._tracked.arun(
                prompts.decompose_story(
                    story, pkg, self.state.architecture,
                    available_skills=self._skills_catalog("dev"),
                ),
                system_prompt=persona("architect"),
            )
            reply = extract_json(result.text)
        except AgentError as exc:
            self._log(
                f"decompose:{story.id}",
                f"Décomposition indisponible ({exc}) — story construite en bloc.",
            )
            return
        raw = [t for t in (reply.get("tasks") or []) if isinstance(t, dict)]
        if len(raw) < 2:
            self._log(f"decompose:{story.id}", "Story non décomposée (triviale) — construite en bloc.")
            return
        # Project-wide-unique task ids; remap the agent's local ids in depends_on.
        taken = {t.id for t in self.state.all_tasks()} | {s.id for s in self.state.stories}
        valid_ac = {c.id: c for c in story.acceptance_criteria}
        id_map: dict[str, str] = {}
        for i, data in enumerate(raw, start=1):
            old = str(data.get("id") or f"T-{i}")
            new = f"{story.id}-T{i}"
            while new in taken:
                new += "x"
            taken.add(new)
            id_map[old] = new
        primary = self.state.primary_stream_id
        tasks: list[Task] = []
        for i, data in enumerate(raw, start=1):
            old = str(data.get("id") or f"T-{i}")
            crit = [valid_ac[c] for c in (data.get("acceptance_criteria") or []) if c in valid_ac]
            deps = [id_map[d] for d in (data.get("depends_on") or []) if d in id_map]
            layer = str(data.get("layer") or "")
            skill = str(data.get("skill") or "")
            desc = str(data.get("description") or "")
            tag = " · ".join(
                p for p in (f"couche {layer}" if layer else "", f"skill `{skill}`" if skill else "") if p
            )
            file_globs = [str(g) for g in (data.get("file_globs") or []) if str(g).strip()]
            tasks.append(
                Task(
                    id=id_map[old],
                    story_id=story.id,
                    stream=primary,
                    title=str(data.get("title") or old),
                    description=(f"[{tag}] {desc}" if tag else desc),
                    acceptance_criteria=crit or list(story.acceptance_criteria),
                    gherkin=str(data.get("gherkin") or story.gherkin),
                    depends_on=deps,
                    files_hint=file_globs,
                )
            )
        # P4b: deterministic independence floor — serialize any tasks that
        # overlap on files but have no ordering, so the parallel build can never
        # lose green work to a merge conflict (the LLM's depends_on are trusted
        # but verified; missing file claims default to whole-stream = serialized).
        self._enforce_task_independence(tasks, label=story.id)
        story.tasks = tasks
        chain = " → ".join((t.title or t.id) for t in tasks)
        self._chat(
            ChatRole.ARCHITECT,
            f"[{story.id}] {reply.get('message', 'Décomposition en sous-tâches')}\n"
            f"{len(tasks)} sous-tâches (subagents parallèles) : {chain}.",
        )
        self._sync()

    async def _adesign_tests(self, story: UserStory, pkg: str) -> None:
        """QA agent decomposes the acceptance test outside-in (London style)
        into per-layer unit tests, BEFORE any implementation. Non-fatal: a QA
        failure just means the dev works from the Gherkin alone."""
        self._log(f"qa:{story.id}", f"Architecte QA : décomposition outside-in des tests de {story.id}…")
        try:
            result = await self._tracked.arun(
                prompts.qa_test_plan(
                    story, pkg, self.state.architecture,
                    lessons="\n".join(self._effective_lessons()),
                    backend_language=self.state.backend_language.value,
                    available_skills=self._skills_catalog("qa"),
                ),
                system_prompt=persona("qa"),
            )
            reply = extract_json(result.text)
            valid_criteria = {c.id for c in story.acceptance_criteria}
            story.test_plan = [
                PlannedTest(
                    id=data.get("id", f"UT-{i}"),
                    layer=data.get("layer", ""),
                    description=data.get("description", ""),
                    mocks=data.get("mocks", []),
                    file_hint=data.get("file_hint", ""),
                    criteria=[c for c in data.get("criteria", []) if c in valid_criteria],
                )
                for i, data in enumerate(reply.get("tests", []), start=1)
            ]
            summary = reply.get("message", "")
            if story.test_plan:
                layers = " → ".join(t.layer or "?" for t in story.test_plan)
                self._chat(
                    ChatRole.QA,
                    f"[{story.id}] {summary}\nPlan outside-in : {len(story.test_plan)} "
                    f"test(s) unitaire(s) ({layers}).",
                )
            else:
                self._chat(
                    ChatRole.QA,
                    f"[{story.id}] {summary or 'Story triviale : le Gherkin seul suffit.'}",
                )
        except AgentError as exc:
            self._log(f"qa:{story.id}", f"QA indisponible ({exc}) — le dev partira du Gherkin seul.")
        self._sync()

    def _apply_test_states(
        self, story: UserStory, reported: list[dict], real: dict[str, str]
    ) -> None:
        """Set each planned test's state, preferring REAL pytest outcomes.

        The dev reports, per planned test, the pytest nodeids it wrote
        (`{"id", "status", "nodeids"}`). We look up those nodeids' real
        outcomes in the json-report: all passed -> green, any failed/errored ->
        red. If no nodeid is found in the report, fall back to the dev's
        self-reported status (structural link only, outcome unknown).
        """
        by_id = {t.id: t for t in story.test_plan}
        for item in reported:
            test = by_id.get(item.get("id"))
            if test is None:
                continue
            nodeids = item.get("nodeids") or []
            outcomes = [real[n] for n in nodeids if n in real]
            if outcomes:
                test.status = (
                    TestState.GREEN
                    if all(o == "passed" for o in outcomes)
                    else TestState.RED
                )
            elif item.get("status") == "green":
                test.status = TestState.GREEN
            elif item.get("status") == "red":
                test.status = TestState.RED

    def _ui_mode(self, story: UserStory) -> bool:
        """Whether this story goes through the Playwright UI acceptance mode."""
        return self._setting("ui_tests_enabled") and story.ui

    async def _arun_ui_tests(self) -> tuple[bool, str]:
        """Run the workspace's replayable Playwright UI suite (`pytest -m ui`).

        Only exit code 0 is accepted. Pytest exit code 5 (no tests collected)
        means the UI story did not produce replayable acceptance evidence and
        must stay red.
        """
        if settings.fake_agents:
            return True, "mode démo : tests UI court-circuités"
        ws = workspace_dir(self.state.id)
        env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}

        def _run() -> tuple[bool, str]:
            proc = subprocess.run(
                [settings.uv_cmd, "run", "pytest", "-q", "-m", "ui"],
                cwd=str(ws),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            return proc.returncode == 0, proc.stdout

        return await asyncio.to_thread(_run)

    def _is_shared_ws(self, ws) -> bool:
        """Does ``ws`` designate the project's SHARED workspace (not a per-item
        git worktree)? Only shared runs contend on the shared ``.venv`` and thus
        need the venv guard + serialization lock."""
        if ws is None:
            return True
        try:
            return Path(ws).resolve() == workspace_dir(self.state.id).resolve()
        except OSError:
            return False

    @staticmethod
    def _venv_is_valid(ws) -> bool:
        """Is ``ws/.venv`` a USABLE virtualenv? Absent is fine (``uv run`` will
        create one). Present-but-broken — no ``pyvenv.cfg`` or no interpreter,
        the exact half-deleted state a race between two ``uv run`` recreations
        leaves behind on Windows — is NOT: uv then refuses both to use it and to
        recreate it, and every launch fails."""
        venv = Path(ws) / ".venv"
        if not venv.exists():
            return True
        if not (venv / "pyvenv.cfg").exists():
            return False
        return (venv / "Scripts" / "python.exe").exists() or (venv / "bin" / "python").exists()

    @staticmethod
    def _purge_venv_dir(ws) -> bool:
        """Remove ``ws/.venv`` entirely, retrying on Windows file locks: an open
        ``python.exe`` makes a single ``rmtree(ignore_errors=True)`` leave a
        half-deleted tree that uv refuses both to use AND to recreate ("not a
        valid Python environment"). Returns True when the directory is gone."""
        import shutil
        import time as _time

        venv = Path(ws) / ".venv"
        for attempt in range(3):
            if attempt:
                _time.sleep(0.5 * attempt)  # let a dying process release its lock
            shutil.rmtree(venv, ignore_errors=True)
            if not venv.exists():
                return True
        return not venv.exists()

    def _guard_shared_venv(self, ws) -> bool:
        """Purge a broken shared ``.venv`` so the next ``uv run`` rebuilds it from
        scratch. Returns True if it removed one (a repair happened). No-op when
        the venv is valid or absent. Python only; best-effort (never raises)."""
        if toolchain.normalize(self.state.backend_language.value) != "python":
            return False
        if self._venv_is_valid(ws):
            return False
        if not self._purge_venv_dir(ws):
            # A locked file survived every attempt: the next uv run WILL fail
            # (infra). Say it loudly instead of letting the red read as code.
            self._log(
                "streams",
                "⛔ .venv partagée invalide et impossible à purger (fichier "
                "verrouillé) — le prochain run échouera pour cause d'infra.",
            )
            self.monitor.event("env_repair", scope="shared", reason="purge_failed")
            return False
        self._log(
            "streams",
            "🩹 .venv partagée invalide (à moitié détruite) — purgée pour "
            "reconstruction par uv.",
        )
        self.monitor.event("env_repair", scope="shared", reason="invalid_venv")
        return True

    @staticmethod
    def _looks_like_infra_failure(output: str, results: dict[str, str]) -> bool:
        """Does a RED run look like a broken environment rather than a real test
        failure? True only when NO test outcome was parsed (nothing ran) AND the
        output carries a toolchain/venv signature. Deliberately narrow: a
        project-level ``ModuleNotFoundError`` (a genuine post-merge semantic
        conflict) is NOT matched here, so it still reverts."""
        if results:
            return False  # tests were collected and ran → a real red
        low = (output or "").lower()
        signatures = (
            "no module named pytest",
            "no module named 'pytest",
            "failed to spawn",
            "unable to create virtualenv",
            "pyvenv.cfg",
            "no interpreter found",
            "does not appear to be a python project",
            "the system cannot find the file specified",
            "cannot find the path",
            "failed to install",
            # uv refusing a half-deleted .venv (locked python.exe survived a
            # purge): "Project virtual environment directory ... cannot be used
            # because it is not a valid Python environment (no Python
            # executable was found)" — the messagerie2 outage signature.
            "not a valid python environment",
            "no python executable",
        )
        return any(s in low for s in signatures)

    async def _arun_pytest(self, ws=None) -> tuple[bool, str, dict[str, str]]:
        """Run the test suite for the project's backend language (L2g).

        Returns (suite_green, output, {test_id: outcome}). The command and the
        result parsing are dispatched by language via ``toolchain`` (Python =
        pytest-json-report, Go = `go test -json`, Rust = `cargo test`); per-test
        outcomes reflect the real run, not the agent's self-report. (Name kept
        for the `green_pytest` test fixture; covers all languages.)

        ``ws`` defaults to the project workspace; the streams build path (ST-9)
        passes a per-item git worktree so each item's suite runs in isolation.
        """
        if settings.fake_agents:
            # Demo / e2e mode: no real code is written, trust the scripted dev.
            return True, "mode démo : vérification des tests court-circuitée", {}
        # Run in a worker thread via subprocess: asyncio's subprocess support is
        # unavailable on Windows' SelectorEventLoop (used by uvicorn), so we stay
        # off the event loop entirely for child processes.
        lang = toolchain.normalize(self.state.backend_language.value)
        ws = workspace_dir(self.state.id) if ws is None else ws
        env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
        shared = self._is_shared_ws(ws)

        def _run() -> tuple[bool, str, dict[str, str]]:
            import tempfile

            report_path = ""
            if toolchain.needs_report_file(lang):
                fd, report_path = tempfile.mkstemp(suffix=".json", prefix="autospec-report-")
                os.close(fd)
            try:
                cmd = self._maybe_sandbox(toolchain.test_command(lang, report_path), ws)
                proc = subprocess.run(
                    cmd,
                    cwd=str(ws),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    env=env,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                results = toolchain.parse_results(lang, proc.stdout, report_path)
                return proc.returncode == 0, proc.stdout, results
            finally:
                if report_path:
                    try:
                        os.remove(report_path)
                    except OSError:
                        pass

        # Shared workspace: purge a broken `.venv` first (so `uv run` rebuilds a
        # valid one) and serialize the whole run so no sibling suite mutates the
        # shared venv underneath it. Worktree runs are isolated → no lock.
        if shared:
            async with self._shared_suite_lock:
                self._guard_shared_venv(ws)
                ok, output, results = await asyncio.to_thread(_run)
        else:
            ok, output, results = await asyncio.to_thread(_run)
        # W0.5-T08: flaky-check quarantine. A red suite is rerun once; if it now
        # passes, the failure was non-deterministic (a flake), not real — we keep
        # the green result and record the flake so the recovery ladder (W1) never
        # escalates a model over a test that just needed a second run. A suite that
        # stays red is a real failure and is returned untouched.
        if not ok and settings.flaky_rerun_enabled:
            if shared:
                async with self._shared_suite_lock:
                    self._guard_shared_venv(ws)
                    ok2, output2, results2 = await asyncio.to_thread(_run)
            else:
                ok2, output2, results2 = await asyncio.to_thread(_run)
            if ok2:
                item = _BUILD_ITEM.get() or f"phase:{self.state.phase.value}"
                self.monitor.event("flaky", item=item, note="red suite passed on rerun")
                self._log(item, "⚠️ Suite rouge devenue verte au 2ᵉ passage — flaky (non comptée comme échec).")
                ok, output, results = ok2, output2, results2
        self.monitor.pytest(
            item_id=_BUILD_ITEM.get() or f"phase:{self.state.phase.value}",
            ok=ok, summary=(output or "")[-500:],
        )
        return ok, output, results

    # ------------------------------- Integration repair loop (fix-until-green)

    async def _arepair_delivery(
        self, source: str, report: str, averify, *, prompt_builder=None
    ) -> tuple[bool, str]:
        """Fix-until-green loop for the delivery gates (smoke run, runtime
        integration). The delivered app failed a REAL execution check while its
        test suite is green — a wiring problem (static mount vs asset paths,
        unregistered router, uninitialised DB…) that no mocked unit test sees.
        Dispatch a Dev agent with the gate's failure report, require the suite
        to STAY green (git rollback otherwise), then re-run the gate — up to
        ``INTEGRATION_FIX_ATTEMPTS`` times. Returns ``(ok, latest detail)``."""
        detail = report
        attempts = int(self._setting("integration_fix_attempts") or 0)
        if attempts <= 0 or settings.fake_agents:
            return False, detail
        # Finding 4 : une panne d'INFRA (lancement impossible, port tenu par un
        # tiers) ne se répare pas par un agent — on ne gaspille aucune tentative.
        if self._smoke_looks_like_infra(report):
            self._log(source, "Échec de forme infra — aucune tentative de réparation dépensée.")
            return False, detail
        ws = workspace_dir(self.state.id)
        if not await self._agit_snapshot(ws, f"pre integration-fix ({source})"):
            self._log(source, "Réparation impossible (git indisponible) — gate en échec.")
            return False, detail
        pkg = workspace.package_name(self.state)
        for attempt in range(1, attempts + 1):
            await self._checkpoint()
            if self._stop_requested:
                return False, detail
            self._log(
                source,
                f"🔧 Réparation du câblage par un agent Dev (tentative {attempt}/{attempts})…",
            )
            self._chat(
                ChatRole.SYSTEM,
                f"🔧 Gate {source} en échec — agent Dev dépêché pour réparer "
                f"(tentative {attempt}/{attempts}).",
            )
            self.monitor.event(
                "integration_fix", source=source, attempt=attempt, detail=detail[:300]
            )
            try:
                await self._tracked.arun(
                    (prompt_builder or prompts.dev_fix_integration)(
                        pkg,
                        detail,
                        architecture=self.state.architecture,
                        attempt=attempt,
                        max_attempts=attempts,
                    ),
                    system_prompt=persona("dev"),
                    cwd=ws,
                )
            except AgentError as exc:
                self._log(source, f"Agent de réparation indisponible : {exc}")
                return False, detail
            green, pytest_out, _ = await self._arun_pytest()
            suite_out, suite_name = pytest_out, "pytest"
            # Finding 3 : le filet de sécurité ne doit pas être backend-only. Si le
            # projet a un frontend, sa suite Vitest + build doit AUSSI rester verte,
            # sinon la réparation a pu casser l'UI sans qu'un test backend le voie.
            if green and self._has_frontend():
                fe_green, fe_out, _ = await self._arun_frontend_tests()
                if not fe_green:
                    green, suite_out, suite_name = False, fe_out, "frontend (Vitest + build)"
            if not green:
                await self._agit(ws, "reset", "--hard", "HEAD")
                await self._agit(ws, "clean", "-fd")
                self._log(source, f"La réparation a cassé la suite {suite_name} — rollback.")
                detail = (
                    f"{detail}\n\n⚠️ Ta tentative précédente a CASSÉ la suite {suite_name} "
                    f"(rollback effectué). Sortie {suite_name} :\n{suite_out[-1500:]}"
                )
                continue
            await self._agit(ws, "add", "-A")
            await self._agit(ws, "commit", "-m", f"integration fix {source} #{attempt}", "--allow-empty")
            ok, new_detail = await averify()
            self.monitor.event(
                "integration_fix_verify",
                source=source, attempt=attempt, ok=ok, detail=(new_detail or "")[:300],
            )
            if ok:
                self._log(source, f"✅ Câblage réparé (tentative {attempt}) — gate {source} vert.")
                self._chat(
                    ChatRole.SYSTEM,
                    f"🔧 Gate {source} réparé et revalidé (tentative {attempt}).",
                )
                return True, new_detail
            detail = new_detail or detail
        return False, detail

    # ------------------------------------------------- Smoke-run gate (runnability)

    @staticmethod
    def _smoke_looks_like_infra(detail: str) -> bool:
        """Un échec de smoke a-t-il une forme INFRA (env cassé) plutôt qu'un bug
        de câblage réparable ? On ne dépense pas de tentative d'agent pour ça
        (finding 4) : lancement impossible (uv/python absent) ou port déjà tenu
        par un process externe. Le miroir sémantique-vs-infra du canari
        post-merge (``_looks_like_infra_failure``)."""
        low = (detail or "").lower()
        return (
            "lancement impossible" in low
            or "process externe" in low
            or "docker indisponible" in low
            # Daemon-down markers shared with the docker gate (single source).
            or any(marker in low for marker in docker_deploy.DOCKER_INFRA_MARKERS)
        )

    def _apark_infra(self, source: str, detail: str) -> None:
        """Gare la livraison en needs_attention pour une panne d'INFRA (finding 4).

        Un rouge d'infra (playwright/node absent, venv cassée, port occupé par un
        tiers) n'est pas un défaut de code : on ne dépêche PAS d'agent Dev, on
        bloque la livraison avec un message clair et on notifie bruyamment."""
        msg = f"{source} : vérification impossible (infra) — {detail}"
        self._block_delivery(msg, source=source)
        self.state.regressions.append(msg)
        self.monitor.event(source, ok=False, infra=True, detail=detail[:300])
        self._chat(
            ChatRole.SYSTEM,
            f"⚠️ Gate {source} : condition d'infra (non réparable par un agent) — "
            f"{detail[:200]}",
        )
        self._notify("error", f"{source} : infra", msg[:200])

    async def _aensure_own_port_free(self, source: str, port: int) -> tuple[bool, str]:
        """Avant de booter, arrête l'app PROPRE du projet puis vérifie que le port
        est libre (finding 1). Si le port reste occupé, tente d'abord de tuer les
        processus ORPHELINS de CE workspace qui le tiennent (finding 10 : sous
        Windows un superviseur uvicorn/reload survit au taskkill du wrapper uv —
        le gate suivant le prenait pour un tiers et se parquait en infra). Ce
        n'est qu'après ce nettoyage ciblé qu'un port toujours occupé est déclaré
        process EXTERNE : condition d'infra (vérification impossible), pas un
        échec de code.

        Retourne ``(free, detail)`` — ``free=False`` => port tenu par un tiers."""
        await self.astop_app()
        # Laisse le TIME_WAIT / la fermeture du socket se résorber, sinon on
        # confondrait notre propre serveur à peine arrêté avec un tiers.
        for _ in range(6):
            if self._port_is_free(port):
                return True, ""
            await asyncio.sleep(0.5)
        # Le port est tenu : si c'est par un orphelin de l'USINE — n'importe quel
        # process lancé depuis ``workspace/`` (smoke-run fuité d'un AUTRE projet
        # inclus, finding 13), jamais un vrai tiers — on le tue et on re-teste.
        killed = await asyncio.to_thread(
            self._kill_workspace_port_holders, port, Path(settings.workspace_root)
        )
        if killed:
            self._log(
                source,
                f"♻️ {killed} processus orphelin(s) du workspace tué(s) sur :{port}.",
            )
            for _ in range(6):
                if self._port_is_free(port):
                    return True, ""
                await asyncio.sleep(0.5)
        detail = (
            f"port :{port} déjà occupé par un process externe — "
            f"vérification impossible"
        )
        self._log(source, f"⚠️ {detail}")
        return False, detail

    @staticmethod
    def _topmost_workspace_ancestors(
        listeners: list[int], workspace_procs: dict[int, int]
    ) -> list[int]:
        """For each listening pid, walk UP the parent chain while the parent is
        also a workspace process, and return the TOPMOST ancestors (deduped).

        Killing only the listener is not enough: a uvicorn reload SUPERVISOR
        does not hold the port itself and respawns a fresh worker right after
        the kill — the gate then races a zombie factory. ``workspace_procs``
        maps pid → ppid for every process whose command line points inside the
        workspace. Pure function (testable without subprocess)."""
        tops: list[int] = []
        for pid in listeners:
            if pid not in workspace_procs:
                continue
            seen = {pid}
            top = pid
            while True:
                parent = workspace_procs.get(top)
                if parent is None or parent not in workspace_procs or parent in seen:
                    break
                seen.add(parent)
                top = parent
            if top not in tops:
                tops.append(top)
        return tops

    @staticmethod
    def _kill_workspace_port_holders(port: int, ws: Path) -> int:
        """Kill the process TREES of this workspace that hold ``port`` — from
        their topmost workspace ancestor (supervisor included), never a third
        party. By construction a process whose command line points inside ``ws``
        is this project's own orphan (leaked smoke run, uvicorn reload
        supervisor…). Returns the number of trees killed. Best-effort, never
        raises."""
        needle = str(ws).lower()
        killed = 0
        try:
            if os.name == "nt":
                script = (
                    f"$l = Get-NetTCPConnection -LocalPort {int(port)} -State Listen "
                    "-ErrorAction SilentlyContinue | "
                    "Select-Object -ExpandProperty OwningProcess -Unique; "
                    "'LISTEN:' + ($l -join ','); "
                    "Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | "
                    "Where-Object { $_.CommandLine -and "
                    f"$_.CommandLine.ToLower().Contains('{needle}') }} | "
                    "ForEach-Object { \"$($_.ProcessId)|$($_.ParentProcessId)\" }"
                )
                proc = subprocess.run(
                    ["powershell", "-NoProfile", "-Command", script],
                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    text=True, encoding="utf-8", errors="replace", timeout=25,
                )
                listeners: list[int] = []
                workspace_procs: dict[int, int] = {}
                for line in (proc.stdout or "").splitlines():
                    line = line.strip()
                    if line.startswith("LISTEN:"):
                        listeners = [
                            int(p) for p in line[len("LISTEN:"):].split(",")
                            if p.strip().isdigit()
                        ]
                    elif "|" in line:
                        pid_s, _, ppid_s = line.partition("|")
                        if pid_s.strip().isdigit() and ppid_s.strip().isdigit():
                            workspace_procs[int(pid_s)] = int(ppid_s)
                for top in Pipeline._topmost_workspace_ancestors(listeners, workspace_procs):
                    subprocess.run(
                        ["taskkill", "/PID", str(top), "/T", "/F"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        check=False, timeout=15,
                    )
                    killed += 1
            else:
                lsof = subprocess.run(
                    ["lsof", "-ti", f"tcp:{int(port)}", "-sTCP:LISTEN"],
                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    text=True, timeout=20,
                )
                listeners = [int(p) for p in (lsof.stdout or "").split() if p.isdigit()]
                ps = subprocess.run(
                    ["ps", "-eo", "pid=,ppid=,command="],
                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    text=True, timeout=20,
                )
                workspace_procs = {}
                for line in (ps.stdout or "").splitlines():
                    parts = line.split(None, 2)
                    if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit() \
                            and needle in parts[2].lower():
                        workspace_procs[int(parts[0])] = int(parts[1])
                for top in Pipeline._topmost_workspace_ancestors(listeners, workspace_procs):
                    # Kill the whole subtree: children first via pkill -P, then top.
                    subprocess.run(["pkill", "-9", "-P", str(top)], check=False, timeout=10)
                    subprocess.run(["kill", "-9", str(top)], check=False, timeout=10)
                    killed += 1
        except Exception:  # noqa: BLE001 — cleanup must never break a gate
            return killed
        return killed

    async def _asmoke_phase(self) -> bool:
        """Deterministic runnability gate (``SMOKE_RUN``): once the suite
        is green, actually BOOT the delivered app and require it to start, so a
        non-runnable build pauses the iteration in needs_attention. No-op when
        off / demo mode / nothing delivered.

        Catches the exact gap a passing test suite misses: e.g. a ``main.py`` that
        only prints launch instructions instead of starting the server."""
        if not self._setting("smoke_run") or settings.fake_agents:
            return True
        if not any(s.status == StoryStatus.DONE for s in self.state.stories):
            return True
        lang = toolchain.normalize(self.state.backend_language.value)
        ws = workspace_dir(self.state.id)
        if lang != "python" or not (ws / "main.py").exists() or not (ws / "pyproject.toml").exists():
            # Finding 6 : un backend web NON-python saute les deux gates de boot.
            # Ce n'est pas un skip silencieux : on AVERTIT que la vérification à
            # l'exécution est indisponible pour ce langage (sans hard-bloquer).
            if lang != "python" and self._expects_web_app():
                warn = (
                    f"⚠️ Vérification à l'exécution indisponible pour un backend "
                    f"{lang} — le smoke/runtime gate ne pilote que python. "
                    f"La runnabilité de cette app n'est PAS vérifiée."
                )
                self._log("smoke", warn)
                self._chat(ChatRole.SYSTEM, warn)
                self.monitor.event("smoke", ok=True, skipped=True, lang=lang)
            else:
                self._log("smoke", f"Smoke run ignoré (langage {lang} non supporté ou pas de main.py).")
            return True
        self.monitor.phase("smoke")
        # Finding 1 : arrête l'app PROPRE du projet et vérifie que le port est
        # libre AVANT de booter, sinon le gate validerait un serveur périmé/tiers.
        port = self._resolve_web_port(ws)
        if self._expects_web_app() or runtime_acceptance._backend_web_candidate(ws):
            free, port_detail = await self._aensure_own_port_free("smoke", port)
            if not free:
                self._apark_infra("smoke", port_detail)
                return False
        self._log("smoke", "🚀 Smoke run : démarrage de l'application livrée…")
        ok, detail = await asyncio.to_thread(self._smoke_run_python, ws)
        self.monitor.event("smoke", ok=ok, detail=detail[:300])
        if not ok:
            # Finding 4 : un échec de forme INFRA (lancement impossible) ne se
            # répare pas par un agent — on gare directement en needs_attention.
            if self._smoke_looks_like_infra(detail):
                self._apark_infra("smoke", detail)
                return False

            async def _averify() -> tuple[bool, str]:
                return await asyncio.to_thread(self._smoke_run_python, ws)

            ok, detail = await self._arepair_delivery(
                "smoke", f"Smoke run échoué : {detail}", _averify
            )
        if ok:
            self._log("smoke", f"✅ Smoke run OK — {detail}")
            self._chat(ChatRole.SYSTEM, f"🚀 Smoke run : l'application démarre ({detail}).")
            return True
        msg = f"Smoke run échoué : {detail}"
        self._block_delivery(msg, source="smoke")
        self.state.regressions.append(msg)
        self._notify("error", "Smoke run échoué", msg[:200])
        return False

    async def _aruntime_acceptance_phase(self) -> bool:
        """Optional browser/runtime acceptance gate for web/fullstack products."""
        ws = workspace_dir(self.state.id)
        result = await runtime_acceptance.arun_runtime_acceptance(
            self.state,
            ws,
            enabled=self._setting("runtime_acceptance_enabled"),
            timeout_s=settings.runtime_acceptance_timeout_s,
        )
        if result.skipped:
            if self._setting("runtime_acceptance_enabled"):
                self._log("runtime", f"Runtime acceptance ignoré : {result.detail}.")
            return True
        self.monitor.event("runtime_acceptance", ok=result.ok, detail=result.detail[:300])
        # Finding 1 : avant de (re)vérifier, arrête l'app PROPRE et exige le port
        # libre — le gate ne doit jamais valider un serveur périmé/tiers. Si un
        # process EXTERNE tient le port : condition d'infra (non réparable).
        port = self._resolve_web_port(ws)
        free, port_detail = await self._aensure_own_port_free("runtime", port)
        if not free:
            self._apark_infra("runtime", port_detail)
            return False
        # Finding 4 : un résultat de forme INFRA (playwright/node absent, port
        # tiers signalé par le gate JS via exit 2) ne se répare pas par un agent.
        if not result.ok and result.infra:
            self._apark_infra("runtime", result.detail)
            return False
        ok, detail = result.ok, result.detail
        if not ok:

            async def _averify() -> tuple[bool, str]:
                await self._aensure_own_port_free("runtime", port)
                res = await runtime_acceptance.arun_runtime_acceptance(
                    self.state,
                    ws,
                    enabled=self._setting("runtime_acceptance_enabled"),
                    timeout_s=settings.runtime_acceptance_timeout_s,
                )
                if not res.ok and res.infra:
                    # Bascule tardive vers l'infra : signalée via un préfixe pour
                    # que la boucle ne la prenne ni pour un vert ni pour un bug
                    # réparable — on garera après la boucle.
                    return False, f"__INFRA__{res.detail}"
                return res.ok, res.detail

            ok, detail = await self._arepair_delivery(
                "runtime", f"Intégration full-stack échouée : {detail}", _averify
            )
            if not ok and detail.startswith("__INFRA__"):
                self._apark_infra("runtime", detail[len("__INFRA__"):])
                return False
        if ok:
            self._log("runtime", "✅ Runtime acceptance OK.")
            self._chat(ChatRole.SYSTEM, "🧪 Runtime acceptance : parcours navigateur OK.")
            return True
        msg = f"Runtime acceptance échoué : {detail}"
        self._block_delivery(msg, source="runtime")
        self.state.regressions.append(msg)
        self._notify("error", "Runtime acceptance échoué", msg[:200])
        return False

    async def _adocker_delivery_phase(self) -> bool:
        """Docker delivery gate (D1): build the DoD-accepted delivery into an
        image, deploy it on the shared ``autospec-net`` network and network-verify
        it (health + cross-container reachability), repairing in a fix-until-green
        loop. Infra conditions (daemon down, network unavailable) park the
        iteration in needs_attention without burning any repair attempt. No-op
        when the gate is off / demo mode / non-web product."""
        ws = workspace_dir(self.state.id)
        enabled = bool(self._setting("docker_delivery"))
        run, reason, kind = docker_deploy.should_run(self.state, ws, enabled=enabled)
        if not run:
            # A non-web product cannot be containerised: when the gate is enabled
            # we WARN loudly (this app is not delivered as a container) and mark
            # the deploy as skipped; every other skip stays quiet.
            if enabled and "non applicable" in reason:
                warn = (
                    f"⚠️ Livraison Docker ignorée — {reason}. Cette application n'est "
                    f"PAS empaquetée en conteneur."
                )
                self._log("docker", warn)
                self._chat(ChatRole.SYSTEM, warn)
                delivery_state.set_deploy(self.state, status="skipped", detail=reason)
                self._sync()
            return True

        self.monitor.phase("docker")
        port = self._resolve_web_port(ws)
        # Regenerate the managed Dockerfile for the resolved kind (container port
        # is 80 for a frontend-only nginx image).
        await asyncio.to_thread(
            deploy.write_deploy_artifacts, ws, port=port, kind=kind
        )

        if self._stop_requested:
            return False

        # --- infra pre-check : Docker daemon reachable ? ----------------------
        avail, out = await asyncio.to_thread(docker_deploy.docker_available)
        if not avail:
            self._apark_infra("docker", f"docker indisponible — {out}")
            return False

        network = self._setting("docker_network")
        host_port = await asyncio.to_thread(docker_deploy.allocate_host_port, self.state)
        delivery_state.set_deploy(self.state, status="building", host_port=host_port)
        self._sync()

        if self._stop_requested:
            return False

        self._log(
            "docker",
            f"🐳 Livraison Docker ({kind}) — build & déploiement sur le réseau "
            f"{network} (port hôte {host_port})…",
        )

        loop = asyncio.get_running_loop()

        def _on_line(line: str) -> None:
            loop.call_soon_threadsafe(self._log, "docker", line)

        def _set_stage(stage: str) -> None:
            delivery_state.set_deploy(self.state, status=stage)
            self._sync()

        def _on_stage(stage: str) -> None:
            # Emitted on the FIRST pass and on every repair re-verify, so the UI
            # tracks building → deploying → verifying transitions throughout.
            loop.call_soon_threadsafe(_set_stage, stage)

        def _run_deploy() -> docker_deploy.DockerDeployResult:
            return docker_deploy.deploy_and_verify(
                self.state,
                ws,
                network=network,
                host_port=host_port,
                build_timeout=self._setting("docker_build_timeout_s"),
                deploy_timeout=self._setting("docker_deploy_timeout_s"),
                kind=kind,
                on_line=_on_line,
                on_stage=_on_stage,
            )

        result = await asyncio.to_thread(_run_deploy)
        self.monitor.event("docker", ok=result.ok, infra=result.infra, detail=result.detail[:300])

        if result.infra:
            delivery_state.set_deploy(
                self.state, status="failed", image=result.image,
                container=result.container, detail=result.detail,
            )
            self._sync()
            self._apark_infra("docker", result.detail)
            return False

        ok, detail = result.ok, result.detail
        if not ok:
            if self._stop_requested:
                return False

            async def _averify() -> tuple[bool, str]:
                res = await asyncio.to_thread(_run_deploy)
                return res.ok, res.detail

            dockerfile_text = ""
            try:
                dockerfile_text = (ws / "Dockerfile").read_text(
                    encoding="utf-8", errors="replace"
                )[:3000]
            except OSError:
                pass
            report = (
                f"Livraison Docker échouée : {detail}\n\n"
                f"=== Dockerfile ===\n{dockerfile_text}"
            )
            ok, detail = await self._arepair_delivery(
                "docker", report, _averify, prompt_builder=prompts.dev_fix_deploy
            )

        if ok:
            delivery_state.set_deploy(
                self.state,
                status="deployed",
                image=result.image,
                container=result.container,
                host_port=host_port,
                detail=detail,
            )
            self._log("docker", f"✅ Livraison Docker OK — {detail}")
            self._chat(
                ChatRole.SYSTEM,
                f"🐳 déployé sur http://localhost:{host_port} (réseau {network}).",
            )
            # Foreign-pair reachability warnings are surfaced but never block.
            if "avertissements (paires tierces)" in detail:
                self._chat(
                    ChatRole.SYSTEM,
                    "⚠️ Joignabilité réseau : certaines paires de conteneurs tiers "
                    "sont injoignables (voir les logs docker) — non bloquant.",
                )
            self._sync()
            return True

        delivery_state.set_deploy(
            self.state, status="failed", image=result.image,
            container=result.container, detail=detail,
        )
        msg = f"Livraison Docker échouée : {detail}"
        self._block_delivery(msg, source="docker")
        self.state.regressions.append(msg)
        self._notify("error", "Livraison Docker échouée", msg[:200])
        return False

    @staticmethod
    def _terminate_tree(proc) -> None:
        """Terminate a launched process and its children (the app may spawn a
        server child). Windows needs a tree-kill; POSIX gets terminate→kill."""
        if proc.poll() is not None:
            return
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
                )
            else:
                proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        except OSError:
            pass

    def _expects_web_app(self) -> bool:
        """Should the delivered product LISTEN on a port, by INTENT (product
        profile / streams) rather than by artifact? The messagerie2 trap: a
        fullstack app whose dev stories never added a web framework was
        classified CLI by its own pyproject — exit 0 = smoke PASS — and shipped
        as a green library + a frontend calling an API that exists nowhere.
        The gate must judge the artifact against the intent, not against the
        artifact it is validating."""
        profile = (self.state.product_profile or "").strip().lower()
        if profile in ("api", "web-ssr", "fullstack"):
            return True
        if profile in ("cli", "library-fast"):
            return False
        # auto / brownfield: a frontend stream implies a backend serving it.
        return bool(list(workspace.frontend_streams(self.state)))

    def _resolve_web_port(self, ws: Path) -> int:
        """Port the delivered web app listens on. Delegates to the single source
        of truth in ``runtime_acceptance`` so the smoke gate and the runtime gate
        never disagree on the port (finding 2)."""
        return runtime_acceptance.resolve_web_port(ws)

    @staticmethod
    def _port_is_free(port: int) -> bool:
        """Is ``127.0.0.1:<port>`` free (nothing listening)? Delegates to the
        single shared implementation in :mod:`docker_deploy`."""
        return docker_deploy.host_port_is_free(port)

    def _has_frontend(self) -> bool:
        """Le projet embarque-t-il un frontend à vérifier ? Un stream frontend
        déclaré (ST-6), ou un ``frontend/package.json`` sur le disque (finding 3)."""
        if list(workspace.frontend_streams(self.state)):
            return True
        fe = workspace_dir(self.state.id) / "frontend" / "package.json"
        return fe.exists()

    def _smoke_run_python(self, ws: Path) -> tuple[bool, str]:
        """Boot a Python project's entry point and check it is runnable.

        Web/API app (its pyproject declares a web framework, OR the project
        INTENT is web — profile/frontend stream): ``uv run python main.py``
        must open a listening TCP port within the timeout. CLI: it must
        exit 0 within the timeout. Returns (ok, human-readable detail)."""
        import socket

        pyproject = (ws / "pyproject.toml").read_text(encoding="utf-8", errors="replace").lower()
        has_framework = any(
            fw in pyproject
            for fw in ("fastapi", "flask", "starlette", "uvicorn", "aiohttp", "django")
        )
        is_web = has_framework or self._expects_web_app()
        no_fw_hint = (
            "" if has_framework
            else " (aucun framework web déclaré dans pyproject.toml — l'API n'a "
            "probablement jamais été câblée)"
        )
        env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
        cmd = self._resolve_cmd([settings.uv_cmd, "run", "python", "main.py"])
        timeout = settings.smoke_run_timeout_s

        if is_web:
            port = self._resolve_web_port(ws)
            try:
                proc = subprocess.Popen(
                    cmd, cwd=str(ws), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    env=env, text=True, encoding="utf-8", errors="replace",
                )
            except OSError as exc:
                return False, f"lancement impossible : {exc}"
            try:
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    if proc.poll() is not None:
                        out = (proc.stdout.read() if proc.stdout else "") or ""
                        return False, (
                            f"le process s'est arrêté (code {proc.returncode}) sans écouter "
                            f"sur 127.0.0.1:{port} — main.py ne démarre pas le serveur ?"
                            f"{no_fw_hint} {out[-300:].strip()}"
                        )
                    with socket.socket() as s:
                        s.settimeout(1.0)
                        if s.connect_ex(("127.0.0.1", port)) == 0:
                            return True, f"serveur à l'écoute sur 127.0.0.1:{port}"
                    time.sleep(0.5)
                return False, (
                    f"aucun serveur à l'écoute sur 127.0.0.1:{port} après "
                    f"{timeout:.0f}s{no_fw_hint}"
                )
            finally:
                self._terminate_tree(proc)
                # Double-tap (finding 13) : un superviseur uvicorn reload peut
                # survivre au taskkill du wrapper uv et respawner un worker —
                # tue tout arbre de l'usine encore accroché au port.
                self._kill_workspace_port_holders(port, Path(settings.workspace_root))

        # CLI: must run to completion with exit code 0.
        try:
            proc = subprocess.run(
                cmd, cwd=str(ws), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                env=env, text=True, encoding="utf-8", errors="replace", timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return False, f"le CLI n'a pas terminé en {timeout:.0f}s (boucle/serveur bloquant ?)"
        except OSError as exc:
            return False, f"lancement impossible : {exc}"
        if proc.returncode != 0:
            return False, f"sortie non nulle (code {proc.returncode}) : {(proc.stdout or '')[-300:].strip()}"
        return True, "CLI exécuté (code 0)"

    # ------------------------------------------------- Frontend stream (ST-7)

    def _story_stream(self, story: UserStory):
        """Resolve the Stream a story belongs to (ST-7). ``""`` → primary."""
        return self.state.stream(getattr(story, "stream", "") or "")

    def _is_frontend_story(self, story: UserStory) -> bool:
        """Whether this story builds in a frontend stream — only when streams
        are enabled (flag OFF keeps every story on the backend path)."""
        if not self._setting("streams_enabled"):
            return False
        stream = self._story_stream(story)
        return stream.kind == StreamKind.FRONTEND or toolchain.is_frontend(stream.language)

    @staticmethod
    def _resolve_cmd(cmd: list[str]) -> list[str]:
        """Resolve a launchable path for ``cmd[0]`` (Windows: ``npm`` → ``npm.cmd``).

        ``subprocess`` without a shell cannot exec a bare ``npm`` on Windows (the
        on-PATH entry is the ``npm.cmd`` shim), which raises ``[WinError 2]``.
        ``shutil.which`` honours ``PATHEXT`` and returns the real shim. Left
        unchanged when nothing resolves (the caller handles the OSError)."""
        if not cmd:
            return cmd
        exe = shutil.which(cmd[0])
        return [exe, *cmd[1:]] if exe else cmd

    @staticmethod
    def _node_modules_usable(root: Path) -> bool:
        """``node_modules`` is present AND actually resolvable — not just an empty
        or broken-junction directory. We probe ``.bin`` (the executables dir npm
        always creates) or the ``vite`` package the frontend depends on, so a
        silently-failed junction is detected instead of trusted."""
        nm = root / "node_modules"
        try:
            return nm.exists() and ((nm / ".bin").exists() or (nm / "vite").exists())
        except OSError:
            return False

    @classmethod
    def _link_node_modules(cls, link: Path, target: Path) -> bool:
        """Create ``link`` as a directory junction/symlink to ``target`` so a
        worktree shares the main install (junctions need no admin rights on
        Windows). Returns True ONLY if the link now resolves to a usable install
        — ``mklink /J`` can silently fail (different volume, policy, antivirus),
        so we never trust it blind."""
        try:
            if link.exists():
                return cls._node_modules_usable(link.parent)
            link.parent.mkdir(parents=True, exist_ok=True)
            if os.name == "nt":
                subprocess.run(
                    ["cmd", "/c", "mklink", "/J", str(link), str(target)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
                )
            else:
                os.symlink(target, link, target_is_directory=True)
        except OSError:
            return False
        return cls._node_modules_usable(link.parent)

    async def _anpm_install_in(self, root: Path, *, use_ci: bool) -> bool:
        """Run a real ``npm ci``/``npm install`` in ``root`` (blocking → thread).
        ``ci`` (reproducible, lockfile-driven) when a ``package-lock.json`` is
        present, else ``install``. Returns True on success; non-fatal."""
        ci = use_ci and (root / "package-lock.json").exists()
        args = [settings.npm_cmd, "ci" if ci else "install", "--no-audit", "--no-fund"]

        def _run():
            env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
            return subprocess.run(
                self._resolve_cmd(args), cwd=str(root), stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, env=env, text=True,
                encoding="utf-8", errors="replace", timeout=900,
            )

        try:
            proc = await asyncio.to_thread(_run)
            ok = proc.returncode == 0 and self._node_modules_usable(root)
            self._log(
                "streams",
                f"📦 npm {'ci' if ci else 'install'} ({root.name}) "
                f"{'OK' if ok else 'ÉCHEC : ' + (proc.stdout or '')[-200:]}",
            )
            return ok
        except (OSError, subprocess.TimeoutExpired) as exc:
            self._log("streams", f"📦 npm install indisponible ({root.name}) : {exc}")
            return False

    async def _aensure_frontend_node_modules(self, root: Path) -> None:
        """Make a USABLE ``node_modules`` available in a frontend ``root`` before
        Vitest / ``vite build`` run.

        The streams build runs frontend items in git worktrees, which never carry
        ``node_modules`` (gitignored). Worktrees get a REAL hermetic install
        (``npm ci``), NEVER a junction to the main install: through a junction,
        any npm/rm run inside a worktree (harness fallback or a dev agent
        repairing its environment — Git-Bash ``rm -rf`` recurses into junctions)
        destroys the SHARED node_modules, and vitest even bundles
        ``vite.config.ts`` into the junction TARGET's ``.vite-temp`` — every
        sibling suite then died mid-run on "Cannot find package 'vite'" (the
        messagerie2 churn: 6 reinstalls of the shared install in one build).
        The npm cache keeps the per-worktree install fast (~20-40 s)."""
        if settings.fake_agents or self._node_modules_usable(root):
            return
        stream = next(iter(workspace.frontend_streams(self.state)), None)
        if stream is None:
            return
        main_root = workspace.stream_root(self.state, stream)
        if not (main_root / "package.json").exists():
            return
        if root.resolve() == main_root.resolve():
            # Shared root: install once, serialized (siblings contend on it).
            async with self._npm_lock:
                if not self._node_modules_usable(main_root):
                    self._log("streams", "📦 npm install (frontend) — racine partagée…")
                    await self._anpm_install_in(main_root, use_ci=False)
            return
        # Worktree: real install. Detach any junction left by an older build
        # first — npm must never write through it into the shared install.
        await asyncio.to_thread(self._unlink_node_modules_junctions, root)
        self._log(
            "streams",
            f"📦 npm ci (frontend) — install réel (hermétique) dans {root.name}…",
        )
        await self._anpm_install_in(root, use_ci=True)

    async def _arun_frontend_tests(self, ws=None) -> tuple[bool, str, dict[str, str]]:
        """Run the frontend stream's Vitest suite AND the production build
        (`tsc && vite build`) — "green" requires BOTH (ST-7). Returns
        (green, output, {test_id: outcome}). Demo / fake-agents mode
        short-circuits (no real node/vite), exactly like ``_arun_pytest``.

        ``ws`` defaults to the project workspace; the streams build path (ST-9)
        passes a per-item git worktree so the frontend root is resolved relative
        to that worktree (the item's isolated copy of the project repo)."""
        if settings.fake_agents:
            return True, "mode démo : vérification Vitest + build court-circuitée", {}
        stream = next(iter(workspace.frontend_streams(self.state)), None)
        if stream is None:
            return True, "aucun stream frontend", {}
        root = workspace.stream_root(self.state, stream)
        if ws is not None:
            # Re-root the frontend zone onto the worktree copy of the repo.
            rel = root.relative_to(workspace_dir(self.state.id))
            root = ws / rel
        # Safety net: the verify step also needs node_modules (idempotent — the
        # dev step usually installed/linked it already).
        await self._aensure_frontend_node_modules(root)
        env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
        shared = ws is None

        def _run() -> tuple[bool, str, dict[str, str]]:
            import tempfile

            fd, report_path = tempfile.mkstemp(suffix=".json", prefix="autospec-vitest-")
            os.close(fd)
            try:
                test_cmd = self._resolve_cmd(self._maybe_sandbox(
                    toolchain.frontend_test_command(report_path), root
                ))
                try:
                    test_proc = subprocess.run(
                        test_cmd, cwd=str(root),
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        env=env, text=True, encoding="utf-8", errors="replace",
                    )
                except OSError as exc:
                    # A missing toolchain (no node/npm) must fail THIS story, not
                    # crash the whole pipeline with an unhandled OSError.
                    return False, f"toolchain frontend indisponible : {exc}", {}
                results = toolchain.parse_frontend_results(test_proc.stdout, report_path)
                tests_ok = test_proc.returncode == 0
                output = test_proc.stdout
                if not tests_ok:
                    # The json reporter keeps stdout terse: without this digest a
                    # red run's tail can be as useless as "JSON report written
                    # to …" — the dev retry prompt then carries zero signal.
                    digest = toolchain.frontend_failure_digest(report_path)
                    if digest:
                        output += "\n--- échecs Vitest (rapport JSON) ---\n" + digest
                    elif not results:
                        output += (
                            "\n(vitest s'est terminé en erreur SANS test collecté : "
                            "crash de config/setup, suite vide ou reporter muet)"
                        )
                    return False, output, results
                # Tests green → the build (tsc && vite build) gates "green" too.
                build_cmd = self._resolve_cmd(
                    self._maybe_sandbox(toolchain.frontend_build_command(), root)
                )
                try:
                    build_proc = subprocess.run(
                        build_cmd, cwd=str(root),
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        env=env, text=True, encoding="utf-8", errors="replace",
                    )
                except OSError as exc:
                    return False, output + f"\n--- build indisponible : {exc}", results
                if build_proc.returncode != 0:
                    errs = toolchain.parse_build_errors(build_proc.stdout)
                    return False, output + "\n--- build ---\n" + errs, results
                return True, output + "\n--- build OK ---", results
            finally:
                try:
                    os.remove(report_path)
                except OSError:
                    pass

        # Shared workspace: serialize so no sibling suite races on the shared
        # frontend tree / node_modules. Worktree runs are isolated → no lock.
        async def _arun_once() -> tuple[bool, str, dict[str, str]]:
            if shared:
                async with self._shared_suite_lock:
                    return await asyncio.to_thread(_run)
            return await asyncio.to_thread(_run)

        ok, output, results = await _arun_once()
        if not ok and self._looks_like_frontend_infra_failure(output, results):
            # Mirror of the shared-venv guard: a red with ZERO test executed and
            # a module-resolution signature is a broken node_modules, not code.
            # Reinstall and replay once instead of burning a dev attempt.
            self._log(
                "streams",
                "🩹 Suite frontend rouge SANS test exécuté — node_modules "
                "suspect, réinstallation puis nouvel essai.",
            )
            self.monitor.event("env_repair", scope="frontend", reason="node_modules")
            async with self._npm_lock:
                await self._anpm_install_in(root, use_ci=True)
            ok, output, results = await _arun_once()
        self.monitor.event(
            "frontend_verify",
            item=_BUILD_ITEM.get() or f"phase:{self.state.phase.value}",
            ok=ok, summary=(output or "")[-500:],
        )
        return ok, output, results

    @staticmethod
    def _looks_like_frontend_infra_failure(output: str, results: dict[str, str]) -> bool:
        """Frontend twin of ``_looks_like_infra_failure``: a red Vitest run with
        NO test outcome AND a module/toolchain-resolution signature is a broken
        ``node_modules`` (half-deleted install, dead junction), not a code red."""
        if results:
            return False  # tests ran → a real red
        low = (output or "").lower()
        signatures = (
            "cannot find package",
            "err_module_not_found",
            "failed to load config",
            "startup error",
            "could not determine executable to run",  # npm exec: vitest absent
            "vitest: not found",
            "enoent",
        )
        return any(s in low for s in signatures)

    # ------------------------------------------------- AUTO-SPEC next cycle

    def _fail_stranded_stories(self, iteration: int) -> int:
        """Mark every story of ``iteration`` left attempted-but-unfinished
        (todo/red/in_progress with a recorded attempt or error) as FAILED, so
        advancing to the next iteration never strands an ambiguous « todo with
        an error » that no action could relaunch. Returns the count."""
        stranded = [
            s
            for s in self.state.stories_of_iteration(iteration)
            if s.status in (StoryStatus.TODO, StoryStatus.RED, StoryStatus.IN_PROGRESS)
            and (s.attempts > 0 or s.last_error)
        ]
        for s in stranded:
            s.status = StoryStatus.FAILED
            if not s.last_error:
                s.last_error = "Itération clôturée sans finir cette story."
        return len(stranded)

    async def _anext_feature_phase(self) -> None:
        """Analyst explores/prioritizes the backlog and picks the next feature,
        then the PM writes the brief for it."""
        # Close the finishing iteration cleanly: any attempted-but-unfinished
        # story becomes FAILED (clear status + relaunchable) instead of a stray
        # TODO orphaned in a past iteration.
        n_failed = self._fail_stranded_stories(self.state.iteration)
        if n_failed:
            self._chat(
                ChatRole.SYSTEM,
                f"⚠️ {n_failed} story(ies) non terminée(s) marquée(s) en échec à la "
                "clôture de l'itération (relançables via « 🔄 Relancer »).",
            )
        selected = await self._aanalyze_phase()
        self.state.phase = PipelinePhase.SPEC
        self._sync()
        result = await self._tracked.arun(
            prompts.pm_brief_for_feature(self.state, selected),
            system_prompt=persona("pm"),
        )
        reply = extract_json(result.text)
        self.state.iteration += 1
        self.state.brief = reply.get("brief", "")
        self.state.feedback.clear()
        self._chat(ChatRole.PM, f"[Itération {self.state.iteration}] {reply.get('message', '')}")

    async def _aanalyze_phase(self) -> FeatureHypothesis:
        self.state.phase = PipelinePhase.ANALYZE
        # The hypothesis built during the iteration that just finished is shipped.
        for hyp in self.state.backlog:
            if hyp.status == HypothesisStatus.SELECTED:
                hyp.status = HypothesisStatus.DONE
        self._sync()

        result = await self._tracked.arun(
            prompts.analyst_explore(self.state),
            system_prompt=persona("analyst"),
        )
        reply = extract_json(result.text)
        proposals = reply.get("hypotheses", [])
        if not proposals:
            raise AgentError("L'analyste n'a proposé aucune hypothèse de feature.")

        shipped = [h for h in self.state.backlog if h.status == HypothesisStatus.DONE]
        shipped_ids = {h.id for h in shipped}
        fresh: list[FeatureHypothesis] = []
        for rank, data in enumerate(proposals, start=1):
            hyp_id = data.get("id") or f"FH-{rank}"
            if hyp_id in shipped_ids:
                continue
            fresh.append(
                FeatureHypothesis(
                    id=hyp_id,
                    title=data.get("title", hyp_id),
                    rationale=data.get("rationale", ""),
                    value=_clamp_1_5(data.get("value", 3)),
                    complexity=_clamp_1_5(data.get("complexity", 3)),
                    rank=rank,
                )
            )
        if not fresh:
            raise AgentError("L'analyste n'a proposé que des hypothèses déjà livrées.")
        selected_id = reply.get("selected") or fresh[0].id
        selected = next((h for h in fresh if h.id == selected_id), fresh[0])
        selected.status = HypothesisStatus.SELECTED
        self.state.backlog = shipped + fresh
        self._chat(
            ChatRole.ANALYST,
            f"{reply.get('message', '')}\nBacklog priorisé : "
            + ", ".join(f"{h.id} {h.title} (V{h.value}/C{h.complexity})" for h in fresh)
            + f"\n➡ Prochaine feature : {selected.id} — {selected.title}",
        )
        return selected

    # ------------------------------------------------------------ RUN app

    async def arun_app(self, args: str = "") -> None:
        if self._run_proc and self._run_proc.poll() is None:
            self._log("run", "L'application tourne déjà.")
            return
        ws = workspace_dir(self.state.id)
        # The generated app is untrusted agent code — give it OS essentials only,
        # never the server's full environment (which may hold secrets).
        env = _minimal_env()
        # Optional CLI arguments forwarded to the generated app (e.g. a
        # subcommand for a CLI app that prints usage when launched bare).
        run_args = shlex.split(args) if args else []
        self.state.running = True
        self._sync()
        hint = f" ({args})" if args else ""
        self._log("run", f"▶ Lancement de l'application générée{hint}…")
        # Stream the child's output from a worker thread, marshaling each line
        # back onto the event loop (asyncio subprocesses are unsupported on the
        # Windows SelectorEventLoop that uvicorn runs).
        loop = asyncio.get_running_loop()
        self._stream_task = asyncio.create_task(
            asyncio.to_thread(self._stream_run_output, ws, env, loop, run_args)
        )
        # ST-8: a multi-stream project launches its frontend preview alongside
        # the backend, with logs tagged per stream. Gated behind streams_enabled;
        # demo mode never spawns a real vite.
        if self._setting("streams_enabled") and not settings.fake_agents:
            self._start_frontend_previews(env, loop)

    def _start_frontend_previews(self, env, loop: asyncio.AbstractEventLoop) -> None:
        """ST-8: launch `vite preview` for each frontend stream in its own
        worker thread, tagging logs with `run:<stream-id>`. Best-effort and
        gated by the caller; a missing build/node surfaces as a run log line."""
        for stream in workspace.frontend_streams(self.state):
            root = workspace.stream_root(self.state, stream)
            source = f"run:{stream.id}"
            self._log(source, f"▶ Lancement du preview frontend ({stream.id})…")
            # BUG9 : garder une référence forte (asyncio ne garde que des weak refs).
            self._frontend_stream_tasks.append(
                asyncio.create_task(
                    asyncio.to_thread(
                        self._stream_preview_output, root, env, loop, source
                    )
                )
            )

    def _stream_preview_output(
        self, root, env, loop: asyncio.AbstractEventLoop, source: str
    ) -> None:
        """Run `vite preview` in ``root`` and stream its output under ``source``
        (ST-8). Mirrors ``_stream_run_output`` but for a frontend stream."""
        cmd = self._resolve_cmd(toolchain.frontend_run_command())
        try:
            proc = subprocess.Popen(
                cmd, cwd=str(root),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                env=env, text=True, encoding="utf-8", errors="replace",
            )
        except OSError as exc:
            loop.call_soon_threadsafe(self._log, source, f"■ Échec du lancement : {exc}")
            return
        self._frontend_procs.append(proc)
        assert proc.stdout
        for line in proc.stdout:
            loop.call_soon_threadsafe(self._log, source, line.rstrip())
        code = proc.wait()
        loop.call_soon_threadsafe(self._log, source, f"■ Preview frontend terminé (code {code}).")

    def _stream_run_output(
        self, ws, env, loop: asyncio.AbstractEventLoop, run_args: list[str] | None = None
    ) -> None:
        import sys

        # In demo mode a Python project runs with the current interpreter
        # (hermetic, no uv venv build); otherwise dispatch to the language's run
        # command (uv run / go run / cargo run) — L2g.
        lang = toolchain.normalize(self.state.backend_language.value)
        run_args = run_args or []
        if settings.fake_agents and lang == "python":
            cmd = [sys.executable, "main.py", *run_args]
        else:
            cmd = toolchain.run_command(lang, run_args)
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(ws),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except OSError as exc:
            loop.call_soon_threadsafe(self._on_run_finished, -1, str(exc))
            return
        self._run_proc = proc
        assert proc.stdout
        for line in proc.stdout:
            loop.call_soon_threadsafe(self._log, "run", line.rstrip())
        code = proc.wait()
        loop.call_soon_threadsafe(self._on_run_finished, code, "")

    @staticmethod
    def _kill_tree(proc) -> bool:
        """Kill a child process AND its whole tree. ``proc.terminate()`` only
        signals the immediate child on Windows, leaving the real workers alive
        (``uvicorn``→python, ``npm``→``node``→``vite``, and the long-lived
        ``esbuild.exe`` service) — those orphans keep ``frontend/node_modules``
        and the workspace files OPEN, which is exactly what makes a later wipe
        (restart / delete) fail with « partiellement verrouillé ». ``taskkill
        /T`` (Windows) / ``terminate`` (POSIX) takes the children down too.
        Best-effort; returns True if a live process was signalled."""
        if proc is None or proc.poll() is not None:
            return False
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
                )
            else:
                proc.terminate()
        except OSError:
            pass
        return True

    async def astop_app(self) -> None:
        """Stop the running generated app, if any.

        Terminates the child subprocess TREE; the streaming worker thread then
        sees it exit and calls ``_on_run_finished``, which resets ``running=False``.
        Safe to call when no app is running (logged no-op, never raises).
        """
        stopped = False
        if self._kill_tree(self._run_proc):
            stopped = True
        for proc in self._frontend_procs:  # ST-8: stop the frontend previews too
            if self._kill_tree(proc):
                stopped = True
        self._frontend_procs = [p for p in self._frontend_procs if p and p.poll() is None]
        # BUG9 : nettoie les tasks de streaming frontend terminées (best-effort).
        self._frontend_stream_tasks = [
            t for t in self._frontend_stream_tasks if t and not t.done()
        ]
        if stopped:
            self._log("run", "■ Arrêt de l'application demandé.")
        else:
            self._log("run", "Aucune application générée en cours d'exécution.")

    def _on_run_finished(self, code: int, error: str) -> None:
        self.state.running = False
        self._sync()
        if error:
            self._log("run", f"■ Échec du lancement : {error}")
        elif code == 0:
            self._log("run", "■ Application terminée (code 0).")
        else:
            self._log(
                "run",
                f"■ Application arrêtée/terminée avec le code {code} — "
                "voir les logs ci-dessus pour l'erreur.",
            )
