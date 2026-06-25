"""The Autospec pipeline: PM (spec) -> PO (plan) -> Dev agents (BDD/TDD build).

One Pipeline instance per project. The whole lifecycle runs as a background
asyncio task; the API talks to it through asend_user_message / astop / arun_app.
"""

from __future__ import annotations

import asyncio
import contextvars
import json
import os
import re
import shlex
import shutil
import subprocess
import time
from pathlib import Path

from ..agents import prompts
from ..agents.runner import (
    AgentError,
    AgentRunner,
    ProcessRegistry,
    active_processes,
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
from ..storage import append_interaction, load_interactions, save_state_payload, workspace_dir
from .interactions import InteractionStore
from . import mutation, refine, scheduler, session_monitor, setup_exec, streams as work_streams, toolchain, workspace
from . import lessons as lesson_store
from . import regression
from .build_monitor import BuildMonitor
from . import deploy
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

# Reverse map: the exact system-prompt string ``persona(name)`` returns → the
# persona name. Lets ``_UsageTracker`` label every call's agent role without
# touching the ~25 call sites. Built lazily (personas are lru_cached, so the same
# string object/content comes back each time).
_PERSONA_BY_PROMPT: dict[str, str] = {}


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
        _t0 = time.monotonic()
        try:
            chosen = model or settings.model_for_phase(phase)
            res = await self.pipeline.runner.arun(
                prompt, system_prompt, cwd=cwd, session_id=session_id, model=chosen
            )
        except AgentError as exc:
            # Capture the failed round-trip too — a red/failed item's last call is
            # exactly what the operator wants to inspect.
            self.pipeline._record_interaction(
                item_id=item_id, phase=phase, persona=role, prompt=prompt,
                response="", ok=False, error=str(exc),
            )
            self.pipeline.monitor.agent_call(
                role=role, item_id=item_id,
                duration_ms=(time.monotonic() - _t0) * 1000,
                ok=False, error=str(exc),
            )
            # Usage-window watchdog (M2): an exhausted Claude session window
            # triggers a clean stop + scheduled auto-resume, then the error
            # still propagates to the caller's normal handling.
            await self.pipeline._aon_agent_error(exc)
            raise
        usage = self.pipeline.state.usage
        usage.cost_usd += res.cost_usd
        usage.input_tokens += res.input_tokens
        usage.output_tokens += res.output_tokens
        usage.agent_calls += 1
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
            model=settings.claude_model or settings.agent_provider,
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
            response=res.text, ok=True,
            input_tokens=res.input_tokens, output_tokens=res.output_tokens,
            cost_usd=res.cost_usd, duration_ms=res.duration_ms,
        )
        self.pipeline.monitor.agent_call(
            role=role, item_id=item_id,
            duration_ms=res.duration_ms or (time.monotonic() - _t0) * 1000,
            ok=True, in_tokens=res.input_tokens, out_tokens=res.output_tokens,
        )
        self.pipeline._sync()  # persist + broadcast usage as it accrues
        return res


class Pipeline:
    def __init__(self, state: ProjectState, runner: AgentRunner):
        self.state = state
        self.runner = runner
        self._tracked = _UsageTracker(self)
        # Opt-in build monitor (AUTOSPEC_BUILD_MONITOR): JSONL timeline for
        # post-mortem failure analysis. No-op when disabled.
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
        self._resume_event = asyncio.Event()
        self._resume_event.set()  # set = running, cleared = paused
        self._task: asyncio.Task | None = None
        # Background side-tasks (feedback impact analysis, component setup):
        # strong refs, one at a time each.
        self._impact_task: asyncio.Task | None = None
        self._setup_task: asyncio.Task | None = None
        self._doc_task: asyncio.Task | None = None
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
        # B5 (UX): heartbeat tick publisher, started on BUILD entry, cancelled on
        # stop/dispose. ~10s compact item-status broadcast (never replayed).
        self._tick_task: asyncio.Task | None = None
        # U4: cleared while the pipeline waits for human approval before build.
        self._approval_event = asyncio.Event()
        self._approval_event.set()
        # B-IDEA: set when the user resolves the brainstorming offer.
        self._brainstorm_event = asyncio.Event()
        self._brainstorm_accepted = False

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
        self._task = asyncio.create_task(self._alifecycle())

    async def adispose(self) -> None:
        """Hard-stop everything (used when the project is deleted): cancel the
        lifecycle task and terminate the generated app if it runs."""
        self._stop_requested = True
        self._stop_tick()  # B5: never tick after dispose
        # Kill any in-flight agent CLI call (claude/codex) and its sub-tree, so it
        # never survives the process as an orphan (cost/resource leak).
        self._agent_procs.terminate_all()
        if self._run_proc and self._run_proc.poll() is None:
            self._run_proc.terminate()
        for proc in self._frontend_procs:  # ST-8
            if proc and proc.poll() is None:
                proc.terminate()
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
        streams_on = settings.streams_enabled
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
        AUTOSPEC_LANGUAGE_SELECTOR — OFF keeps Python as the safe default (no
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
        Env-gated by AUTOSPEC_STREAMS — OFF is a strict no-op (``state.streams``
        stays empty → one implicit backend stream, the pre-streams behaviour).
        Always forces a primary backend stream carrying the backend language;
        ids are deduplicated. Non-fatal: any agent/parse failure falls back to a
        lone backend stream. First time only (already-chosen streams are kept)."""
        if not settings.streams_enabled or self.state.streams:
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
        if not settings.components_enabled or self.state.components:
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
        generated product (D1). Idempotent; returns the created files. Raises
        ValueError (-> 409) while the pipeline is actively building."""
        if self.state.phase in (
            PipelinePhase.SPEC, PipelinePhase.ANALYZE, PipelinePhase.PLAN,
            PipelinePhase.ARCHITECT, PipelinePhase.BUILD,
        ):
            raise ValueError(
                "la pipeline est active : attends la fin avant de générer le déploiement"
            )
        ws = workspace.scaffold(self.state)
        created = await asyncio.to_thread(deploy.write_deploy_artifacts, ws)
        self._chat(
            ChatRole.SYSTEM,
            "🚀 Artefacts de déploiement générés : "
            + (", ".join(created) if created else "déjà présents."),
        )
        return {"created": created}

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

    async def _alifecycle(self) -> None:
        try:
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
            workspace.scaffold(self.state)
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
            self.state.phase = (
                PipelinePhase.STOPPED if self._stop_requested else PipelinePhase.DONE
            )
            self._chat(
                ChatRole.SYSTEM,
                "Itération terminée." if self.state.phase == PipelinePhase.DONE
                else "Boucle arrêtée par l'utilisateur.",
            )
            if self.state.phase == PipelinePhase.DONE:
                self._notify("success", "Itération terminée", self.state.name)
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

    async def _aplan_phase(self) -> None:
        self.state.phase = PipelinePhase.PLAN
        self._sync()
        pkg = workspace.package_name(self.state)
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
                if settings.streams_enabled:
                    for n, task_data in enumerate(story_data.get("tasks") or [], start=1):
                        raw_tid = str(task_data.get("id") or f"T-{len(taken_task_ids) + 1}")
                        tid = _unique_id(raw_tid, "T", taken_task_ids)
                        taken_task_ids.add(tid)
                        task_id_map.setdefault(raw_tid, tid)
                planned.append((epic_id, story_id, story_data))

        def _build_tasks(story_id: str, story_data: dict) -> list[Task]:
            """ST-5: parse a US's decomposition into Task models, remapping task
            depends_on through the project-wide rename. Empty unless streams on."""
            if not settings.streams_enabled:
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
                        acceptance_criteria=[
                            AcceptanceCriterion(id=f"AC-{i}", text=str(text))
                            for i, text in enumerate(task_data.get("acceptance_criteria", []), start=1)
                        ],
                        gherkin=task_data.get("gherkin", ""),
                        depends_on=[task_id_map.get(d, d) for d in task_data.get("depends_on", [])],
                    )
                )
            return out

        new_stories = [
            UserStory(
                id=story_id,
                epic_id=epic_id,
                title=story_data.get("title", "Story"),
                description=story_data.get("description", ""),
                acceptance_criteria=[
                    AcceptanceCriterion(id=f"AC-{i}", text=str(text))
                    for i, text in enumerate(story_data.get("acceptance_criteria", []), start=1)
                ],
                gherkin=story_data.get("gherkin", ""),
                # Deps use the PO's ids: follow renames for the plan's own
                # stories; ids of previous-iteration stories pass through.
                depends_on=[id_map.get(d, d) for d in story_data.get("depends_on", [])],
                priority=_clamp_1_5(story_data.get("priority", 3)),
                ui=bool(story_data.get("ui", False)),
                # ST-5: stream tagging + optional task decomposition (gated; "" /
                # [] when off, so the flag-off parse is byte-identical to today).
                stream=str(story_data.get("stream") or "") if settings.streams_enabled else "",
                tasks=_build_tasks(story_id, story_data),
                iteration=self.state.iteration,
            )
            for epic_id, story_id, story_data in planned
        ]
        # Deps may point to already-done stories from previous iterations.
        scheduler.sanitize_dependencies(self.state.stories + new_stories)
        self.state.stories.extend(new_stories)
        workspace.write_feature_files(self.state, new_stories)
        # ST-5: sanity-check the produced work graph (dangling deps / cycle).
        if settings.streams_enabled:
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
        if not settings.architecture_enabled:
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
            self._chat(
                ChatRole.SYSTEM,
                f"Plan raffiné en {outcome.rounds} tour(s) — qualité {outcome.score}/100 "
                f"(arrêt : {outcome.stopped_reason}).",
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

        try:
            outcome = await refine.arefine(
                self._tracked,
                role="dev",
                kind=f"le code produit pour la story {story.id} (fichiers dans le répertoire courant)",
                criteria=prompts.CODE_CRITERIA,
                initial_text=f"Code de la story {story.id} — lis les fichiers du répertoire courant.",
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
            return True
        if (await self._agit(ws, "init"))[0] != 0:
            return False
        await self._agit(ws, "config", "user.email", "autospec@local")
        await self._agit(ws, "config", "user.name", "Autospec")
        return True

    async def _agit_snapshot(self, ws, label: str) -> bool:
        if not await self._agit_ensure_repo(ws):
            return False
        await self._agit(ws, "add", "-A")
        code, _ = await self._agit(ws, "commit", "-m", f"green {label}", "--allow-empty")
        return code == 0

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
        if settings.streams_enabled:
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
                # Remaining stories depend on failed work: mark them failed.
                for story in pending:
                    story.status = StoryStatus.FAILED
                    story.last_error = "Dépendance non satisfaite (story échouée en amont)."
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
                    )
                    dev_persona = persona("dev")
                result = await self._tracked.arun(
                    dev_prompt,
                    system_prompt=dev_persona,
                    cwd=ws,
                )
                reply = extract_json(result.text)
                self._chat(ChatRole.DEV, f"[{story.id}] {reply.get('summary', '(pas de résumé)')}")
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
                    else:
                        story.status = StoryStatus.FAILED
                        self._set_stage(story, BuildStage.FAILED, sync=False)  # B1
        except AgentError as exc:
            story.last_error = str(exc)
            if session_monitor.monitor_active() and session_monitor.is_usage_limit_error(
                str(exc)
            ):
                # Usage-window exhaustion is not the story's fault: refund the
                # attempt and requeue as-is for the scheduled fresh session.
                # Only with the watchdog active (it stops the build loop) —
                # otherwise the refund would retry the same wall forever.
                story.attempts = max(0, story.attempts - 1)
                story.status = StoryStatus.TODO
            else:
                story.status = (
                    StoryStatus.TODO
                    if story.attempts < settings.dev_max_attempts
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
            """Remove finished workers (freeing their slots). An unexpected worker
            failure is surfaced (the lifecycle turns it into ERROR) after the rest
            are cancelled + drained — matching the old gather()'s propagation."""
            for wid in [k for k, v in running.items() if v.done()]:
                finished = running.pop(wid)
                exc = finished.exception()
                if exc is not None and not isinstance(exc, asyncio.CancelledError):
                    for other in running.values():
                        other.cancel()
                    await asyncio.gather(*running.values(), return_exceptions=True)
                    running.clear()
                    raise exc

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
                for it in items:
                    if len(running) >= cap:
                        break
                    if it.id in running or not work_streams.is_ready(it, graph.items):
                        continue
                    await _acommit_feature(it)
                    running[it.id] = asyncio.create_task(self._abuild_work_item(it))

                if not running:
                    # Nothing ready and nothing in flight: a defensive in-flight
                    # remnant, a dependency CYCLE, or everything left depends on
                    # failed work — mirror the batch loop's terminal handling.
                    if any(p.status == StoryStatus.IN_PROGRESS for p in pending):
                        break  # defensive: a worker left an item in-flight
                    cycle = work_streams.detect_cycle(graph)
                    cycle_error = (
                        f"Cycle de dépendances détecté : {' → '.join(cycle)}"
                        if cycle else None
                    )
                    if cycle_error:
                        self._chat(ChatRole.SYSTEM, f"⛔ {cycle_error}")
                    for item in pending:
                        blockers = work_streams.blocked_by(item, graph.items)
                        self._set_item_status(
                            item, StoryStatus.FAILED,
                            last_error=cycle_error
                            or "Dépendance non satisfaite (work item échoué en amont).",
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
        try:
            worktree = await self._aworktree_add(ws, branch)
            if worktree is None:
                raise RuntimeError("git worktree indisponible")
            if subject.attempts == 1 and not is_frontend:
                self._set_stage(target, BuildStage.ANALYZING, "qa")  # N4/B1
                await self._adesign_tests(subject, pkg)
            label = "dev frontend" if is_frontend else "dev"
            self._log(f"dev:{item.id}", f"Agent {label} assigné à {item.id} — {subject.title}")

            ok, tail = await self._arun_item_dev(subject, worktree, pkg, is_frontend)

            if ok:
                # ST-10/11: commit in the worktree, then merge into the repo. The
                # item is DONE only after a successful merge (so dependents only
                # start once this item's code is in the base HEAD).
                await self._acommit_story(worktree, item.id)
                # B1/B6: green → waiting for the merge lock, then merging.
                self._set_stage(target, BuildStage.MERGE_WAIT, "")
                merged = await self._amerge_work_item(ws, branch, item.id)
                if merged:
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
                    # _amerge_work_item) can never resolve it. Re-queue the item
                    # like a red build so the next scheduler pass rebuilds it in a
                    # worktree branched from the now-updated HEAD — which already
                    # contains the sibling's code — and merges cleanly. Bounded by
                    # dev_max_attempts; only a persistent conflict ends FAILED.
                    target.last_error = "conflit de merge inter-stream"
                    if subject.attempts < settings.dev_max_attempts:
                        target.status = subject.status = StoryStatus.TODO
                        self._set_stage(target, BuildStage.QUEUED, sync=False)  # B1: requeue
                        self._log(
                            f"dev:{item.id}",
                            f"⚠️ Conflit de merge {item.id} — rebuild sur HEAD à jour "
                            f"(tentative {subject.attempts + 1}/{settings.dev_max_attempts}).",
                        )
                    else:
                        target.status = subject.status = StoryStatus.FAILED
                        self._set_stage(target, BuildStage.FAILED, sync=False)  # B1
            else:
                target.last_error = tail
                self._log(f"dev:{item.id}", f"❌ Tests rouges après passage du dev:\n{tail}")
                if subject.attempts < settings.dev_max_attempts:
                    target.status = StoryStatus.TODO
                    self._set_stage(target, BuildStage.QUEUED, sync=False)  # B1: requeue
                else:
                    target.status = StoryStatus.FAILED
                    self._set_stage(target, BuildStage.FAILED, sync=False)  # B1
        except AgentError as exc:
            target.last_error = str(exc)
            if session_monitor.monitor_active() and session_monitor.is_usage_limit_error(
                str(exc)
            ):
                target.attempts = max(0, target.attempts - 1)
                target.status = StoryStatus.TODO
            else:
                target.status = (
                    StoryStatus.TODO
                    if subject.attempts < settings.dev_max_attempts
                    else StoryStatus.FAILED
                )
            self._log(f"dev:{item.id}", f"Erreur agent : {exc}")
        except Exception:
            if target.status in (StoryStatus.IN_PROGRESS, StoryStatus.GREEN, StoryStatus.RED):
                target.status = StoryStatus.TODO
            raise
        finally:
            if worktree is not None:
                await self._aworktree_remove(ws, worktree, branch)
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
        if is_frontend:
            stream = self._story_stream(subject)
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
            )
            dev_persona = persona("dev")
        result = await self._tracked.arun(dev_prompt, system_prompt=dev_persona, cwd=worktree)
        reply = extract_json(result.text)
        self._chat(ChatRole.DEV, f"[{subject.id}] {reply.get('summary', '(pas de résumé)')}")
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
                    await self._agit(repo, "worktree", "remove", "--force", path)
                    path = None
            await self._agit(repo, "worktree", "prune")

    async def _aworktree_add_locked(self, repo, branch: str):
        import tempfile

        worktree = Path(tempfile.mkdtemp(prefix="autospec-wt-"))
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

    async def _aworktree_remove(self, repo, worktree, branch: str) -> None:
        """Always-runs cleanup: remove the worktree and delete its branch.
        Serialized by ``_merge_lock`` (shared-repo ``.git`` mutation)."""
        async with self._merge_lock:
            await self._agit(repo, "worktree", "remove", "--force", str(worktree))
            await self._agit(repo, "branch", "-D", branch)
        # Defensive: if `worktree remove` could not delete the dir, drop it.
        try:
            if Path(worktree).exists():
                import shutil

                shutil.rmtree(worktree, ignore_errors=True)
        except OSError:
            pass

    async def _amerge_work_item(self, repo, branch: str, wid: str) -> bool:
        """ST-10: merge a green work item's branch into the project repo's main
        branch. Merges MUST be serialized (``_merge_lock``) even though builds
        run in parallel — concurrent merges race on the shared index/HEAD.

        Conflict policy: a `--no-ff` merge that reports a conflict is retried
        once (still under the lock, so nothing else mutates the repo in between);
        if it still conflicts, abort cleanly and signal failure to the caller."""
        # B6: hold the merge lock under this item's id so the tick can report
        # ``merge_lock_held:<wid>`` while others wait.
        async with self._merge_lock.ahold(wid):
            code, out = await self._agit(
                repo, "merge", "--no-ff", "-m", f"merge work item {wid}", branch
            )
            if code == 0:
                return True
            # Conflict (or other merge failure): abort, then retry once.
            await self._agit(repo, "merge", "--abort")
            self._log(
                "streams",
                f"⚠️ Conflit de merge pour {wid} — nouvelle tentative sérialisée.",
            )
            code, out = await self._agit(
                repo, "merge", "--no-ff", "-m", f"merge work item {wid} (retry)", branch
            )
            if code == 0:
                return True
            await self._agit(repo, "merge", "--abort")
            self._log("streams", f"⛔ Merge de {wid} impossible (conflit) : {out.strip()[:200]}")
            return False

    # ------------------------------------------------ per-story actions

    async def arebuild_story(self, sid: str) -> None:
        """Reset a finished story and rebuild it from scratch in the background.

        Raises KeyError if the story is unknown, ValueError (-> 409) if the
        pipeline is still active or the story is already being developed."""
        story = self.state.story(sid)  # KeyError if absent
        if self.state.phase not in (
            PipelinePhase.DONE,
            PipelinePhase.STOPPED,
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
        story.last_error = ""
        for t in story.test_plan:
            t.status = TestState.NONEXISTENT
        self._stop_requested = False
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
        except Exception as exc:  # never leave the pipeline in a broken state
            self._chat(ChatRole.SYSTEM, f"Erreur lors de la relance de {story.id} : {exc}")
        finally:
            self._stop_tick()  # B5: rebuild done
            self.state.phase = (
                PipelinePhase.STOPPED if self._stop_requested else PipelinePhase.DONE
            )
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
            PipelinePhase.ERROR,
        ):
            raise ValueError("la pipeline est déjà active")
        if self._task and not self._task.done():
            raise ValueError("une tâche est déjà en cours")
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
            PipelinePhase.ERROR,
        ):
            raise ValueError("la pipeline est déjà active")
        if self._task and not self._task.done():
            raise ValueError("une tâche est déjà en cours")
        # Effective status so a task-decomposed US that is failed via its tasks is
        # also caught (its stored status may be TODO); reset those tasks too.
        failed = [s for s in self.state.stories if s.effective_status() == StoryStatus.FAILED]
        if not failed:
            raise ValueError("aucune story en échec à relancer")
        for story in failed:
            story.status = StoryStatus.TODO
            story.attempts = 0
            story.last_error = ""
            for t in story.test_plan:
                t.status = TestState.NONEXISTENT
            for task in story.tasks:
                if task.status == StoryStatus.FAILED:
                    task.status = StoryStatus.TODO
                    task.attempts = 0
                    task.last_error = ""
        self._stop_requested = False
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

    async def _aresume_build_run(self, all_iterations: bool = False) -> None:
        """Background task: re-run the build phase and restore a terminal phase.

        ``all_iterations`` builds every still-to-build story across all iterations
        (retry-failed / resume-build), not just the current one."""
        self._chat(ChatRole.SYSTEM, "▶ Reprise du build…")
        try:
            await self._abuild_phase(all_iterations=all_iterations)
        except Exception as exc:  # never leave the pipeline in a broken state
            self._chat(ChatRole.SYSTEM, f"Erreur lors de la reprise du build : {exc}")
        finally:
            self.state.phase = (
                PipelinePhase.STOPPED if self._stop_requested else PipelinePhase.DONE
            )
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
        task.last_error = ""
        self._stop_requested = False
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
        except Exception as exc:  # never leave the pipeline in a broken state
            self._chat(ChatRole.SYSTEM, f"Erreur lors de la relance de {task_id} : {exc}")
        finally:
            self.state.phase = (
                PipelinePhase.STOPPED if self._stop_requested else PipelinePhase.DONE
            )
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

    @staticmethod
    def _ui_mode(story: UserStory) -> bool:
        """Whether this story goes through the Playwright UI acceptance mode."""
        return settings.ui_tests_enabled and story.ui

    async def _arun_ui_tests(self) -> tuple[bool, str]:
        """Run the workspace's replayable Playwright UI suite (`pytest -m ui`).

        Exit code 5 (no test collected) counts as green: a UI story whose dev
        produced no UI test file simply has nothing to replay yet.
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
            return proc.returncode in (0, 5), proc.stdout

        return await asyncio.to_thread(_run)

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

        ok, output, results = await asyncio.to_thread(_run)
        self.monitor.pytest(
            item_id=_BUILD_ITEM.get() or f"phase:{self.state.phase.value}",
            ok=ok, summary=(output or "")[-500:],
        )
        return ok, output, results

    # ------------------------------------------------- Frontend stream (ST-7)

    def _story_stream(self, story: UserStory):
        """Resolve the Stream a story belongs to (ST-7). ``""`` → primary."""
        return self.state.stream(getattr(story, "stream", "") or "")

    def _is_frontend_story(self, story: UserStory) -> bool:
        """Whether this story builds in a frontend stream — only when streams
        are enabled (flag OFF keeps every story on the backend path)."""
        if not settings.streams_enabled:
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
    def _link_node_modules(link: Path, target: Path) -> None:
        """Best-effort: create ``link`` as a directory junction/symlink to
        ``target`` so a worktree shares the main install. Junctions need no admin
        rights on Windows (unlike symlinks)."""
        try:
            link.parent.mkdir(parents=True, exist_ok=True)
            if os.name == "nt":
                subprocess.run(
                    ["cmd", "/c", "mklink", "/J", str(link), str(target)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
                )
            else:
                os.symlink(target, link, target_is_directory=True)
        except OSError:
            pass

    async def _aensure_frontend_node_modules(self, root: Path) -> None:
        """Make ``node_modules`` available in a frontend ``root`` before Vitest /
        ``vite build`` run.

        The streams build runs frontend items in git worktrees, which never carry
        ``node_modules`` (gitignored, and ``npm install`` is NOT part of the
        autonomous lifecycle — only the separate component-setup action installs).
        Without this, every frontend item fails with ``Cannot find package 'vite'``.
        Fix: install ONCE in the project's main frontend root, then link it into
        the worktree via a junction so all worktrees share a single install.
        Best-effort — any failure is logged and left to surface downstream."""
        if settings.fake_agents or (root / "node_modules").exists():
            return
        stream = next(iter(workspace.frontend_streams(self.state)), None)
        if stream is None:
            return
        main_root = workspace.stream_root(self.state, stream)
        if not (main_root / "package.json").exists():
            return
        async with self._npm_lock:
            if not (main_root / "node_modules").exists():
                self._log("streams", "📦 npm install (frontend) — première fois…")

                def _install():
                    env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
                    return subprocess.run(
                        self._resolve_cmd(
                            [settings.npm_cmd, "install", "--no-audit", "--no-fund"]
                        ),
                        cwd=str(main_root), stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT, env=env, text=True,
                        encoding="utf-8", errors="replace", timeout=900,
                    )

                try:
                    proc = await asyncio.to_thread(_install)
                    ok = proc.returncode == 0
                    self._log(
                        "streams",
                        f"📦 npm install {'OK' if ok else 'ÉCHEC : ' + proc.stdout[-200:]}",
                    )
                except (OSError, subprocess.TimeoutExpired) as exc:
                    self._log("streams", f"📦 npm install indisponible : {exc}")
                    return
        # Link the shared install into the worktree root (when distinct).
        if root.resolve() != main_root.resolve() and (main_root / "node_modules").exists():
            await asyncio.to_thread(
                self._link_node_modules, root / "node_modules", main_root / "node_modules"
            )

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

        ok, output, results = await asyncio.to_thread(_run)
        self.monitor.event(
            "frontend_verify",
            item=_BUILD_ITEM.get() or f"phase:{self.state.phase.value}",
            ok=ok, summary=(output or "")[-500:],
        )
        return ok, output, results

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
        if settings.streams_enabled and not settings.fake_agents:
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
        cmd = toolchain.frontend_run_command()
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

    async def astop_app(self) -> None:
        """Stop the running generated app, if any.

        Terminates the child subprocess; the streaming worker thread then sees
        it exit and calls ``_on_run_finished``, which resets ``running=False``.
        Safe to call when no app is running (logged no-op, never raises).
        """
        stopped = False
        if self._run_proc is not None and self._run_proc.poll() is None:
            self._run_proc.terminate()
            stopped = True
        for proc in self._frontend_procs:  # ST-8: stop the frontend previews too
            if proc and proc.poll() is None:
                proc.terminate()
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
