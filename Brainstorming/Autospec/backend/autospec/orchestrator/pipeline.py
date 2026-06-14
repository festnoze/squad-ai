"""The Autospec pipeline: PM (spec) -> PO (plan) -> Dev agents (BDD/TDD build).

One Pipeline instance per project. The whole lifecycle runs as a background
asyncio task; the API talks to it through asend_user_message / astop / arun_app.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import time

from ..agents import prompts
from ..agents.runner import AgentError, AgentRunner, extract_json
from ..agents.personas import persona
from ..config import settings
from .. import observability
from ..models import (
    AcceptanceCriterion,
    ChatMessage,
    ChatRole,
    Component,
    ComponentStatus,
    Epic,
    FeatureHypothesis,
    Finding,
    HypothesisStatus,
    PipelinePhase,
    PlannedTest,
    ProjectState,
    StoryStatus,
    TestState,
    UserStory,
)
from ..storage import save_state, workspace_dir
from . import mutation, pytest_report, refine, scheduler, session_monitor, setup_exec, workspace
from . import lessons as lesson_store
from . import regression
from . import deploy
from . import brownfield
from . import sandbox
from .events import bus

_REFINE_ROLE_TO_CHAT = {"critic": ChatRole.CRITIC, "judge": ChatRole.JUDGE}

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


class _UsageTracker:
    """Wraps a pipeline's runner to accumulate token/cost usage on the project
    state. Its `arun` matches the AgentRunner Protocol, so it can be passed to
    `refine.arefine` to also count critic/judge/revise calls."""

    def __init__(self, pipeline: "Pipeline"):
        self.pipeline = pipeline

    async def arun(self, prompt, system_prompt, cwd=None, session_id=None, model=None):
        try:
            chosen = model or settings.model_for_phase(self.pipeline.state.phase.value)
            res = await self.pipeline.runner.arun(
                prompt, system_prompt, cwd=cwd, session_id=session_id, model=chosen
            )
        except AgentError as exc:
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
        self.pipeline._sync()  # persist + broadcast usage as it accrues
        return res


class Pipeline:
    def __init__(self, state: ProjectState, runner: AgentRunner):
        self.state = state
        self.runner = runner
        self._tracked = _UsageTracker(self)
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
        # Strong ref to the app-output streaming task (asyncio keeps only weak
        # refs to tasks: an unreferenced task may be garbage-collected mid-run).
        self._stream_task: asyncio.Task | None = None
        # Serializes the workspace-mutating section of story builds. Parallel dev
        # workers share one workspace directory, so writing code, running the
        # whole pytest suite and committing/refining git must not interleave
        # (else pytest sees half-written trees and git stages the wrong files).
        self._build_lock = asyncio.Lock()
        # U4: cleared while the pipeline waits for human approval before build.
        self._approval_event = asyncio.Event()
        self._approval_event.set()

    # ------------------------------------------------------------- events

    def _sync(self) -> None:
        save_state(self.state)
        bus.publish(
            {
                "type": "state",
                "project_id": self.state.id,
                "state": self.state.model_dump(mode="json"),
            }
        )

    def _log(self, source: str, line: str) -> None:
        bus.publish(
            {"type": "log", "project_id": self.state.id, "source": source, "line": line}
        )

    def _chat(self, role: ChatRole, content: str) -> None:
        self.state.chat.append(ChatMessage(role=role, content=content))
        self._sync()

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
        if self._run_proc and self._run_proc.poll() is None:
            self._run_proc.terminate()
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

    async def astop(self) -> None:
        self._stop_requested = True
        self._resume_event.set()  # unblock a paused pipeline so it can finish
        # Unblock a PM interview waiting for user input.
        await self._user_messages.put("")
        self._chat(ChatRole.SYSTEM, "Arrêt demandé : la boucle se terminera après l'étape en cours.")

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
        if story.status == StoryStatus.IN_PROGRESS:
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
        if story is None or story.status not in (StoryStatus.TODO, StoryStatus.FAILED):
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
        """Apply an impact decision that plans a new epic and/or new stories."""
        items = reply.get("stories") or []
        if not items:
            self._chat(ChatRole.ANALYST, f"🔍 Impact : {message or 'aucune story proposée.'}")
            return
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
        taken_ids = {s.id for s in self.state.stories}
        new_stories: list[UserStory] = []
        for story_data in items:
            story_id = _unique_id(
                story_data.get("id") or f"US-{len(taken_ids) + 1}", "US", taken_ids
            )
            taken_ids.add(story_id)
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
                    depends_on=story_data.get("depends_on", []),
                    priority=_clamp_1_5(story_data.get("priority", 2)),
                    ui=bool(story_data.get("ui", False)),
                    iteration=self.state.iteration,
                )
            )
        scheduler.sanitize_dependencies(self.state.stories + new_stories)
        self.state.stories.extend(new_stories)
        workspace.write_feature_files(self.state, new_stories)
        self._chat(
            ChatRole.ANALYST,
            f"🔍 Impact : {message}\n➕ {len(new_stories)} nouvelle(s) story(ies) planifiée(s) "
            "— « ▶ Continuer le build » pour les développer.",
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
        cmd = self._maybe_sandbox([settings.uv_cmd, "run", "python", "main.py"], ws)

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
            workspace.scaffold(self.state)
            await self._abrownfield_init()
            brief = await self._aspec_phase()
            if brief is None:  # stopped during interview
                self.state.phase = PipelinePhase.STOPPED
                self._sync()
                return
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
        except Exception as exc:  # surface any pipeline failure to the UI
            self.state.phase = PipelinePhase.ERROR
            # Some exceptions stringify to "" (e.g. bare TimeoutError); fall back
            # to repr/type so the UI never shows a detail-less "Erreur pipeline :".
            detail = str(exc) or repr(exc) or type(exc).__name__
            self.state.error = detail
            self._chat(ChatRole.SYSTEM, f"Erreur pipeline : {detail}")
            self._notify("error", "Erreur pipeline", f"{self.state.name} : {detail}"[:200])

    # ------------------------------------------------------------ SPEC (PM)

    async def _aspec_phase(self) -> str | None:
        self.state.phase = PipelinePhase.SPEC
        self._sync()
        if self.state.brief.strip():
            # I3: an imported / pre-seeded brief skips the PM interview.
            self._chat(ChatRole.PM, "📥 Brief importé — passage direct à la planification.")
            return self.state.brief
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
                planned.append((epic_id, story_id, story_data))
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
                iteration=self.state.iteration,
            )
            for epic_id, story_id, story_data in planned
        ]
        # Deps may point to already-done stories from previous iterations.
        scheduler.sanitize_dependencies(self.state.stories + new_stories)
        self.state.stories.extend(new_stories)
        workspace.write_feature_files(self.state, new_stories)
        self._chat(
            ChatRole.PO,
            f"Plan de l'itération {self.state.iteration} : "
            f"{len(plan.get('epics', []))} epic(s), {len(new_stories)} user story(ies).",
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
            ok, _, _ = await self._arun_pytest()
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
        report = workspace_dir(self.state.id) / ".autospec-cov.json"
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
        (%). Env-gated, best-effort (never downgrades a green story). Runs inside
        the build lock held by the caller, so pytest stays serialized."""
        if not settings.mutation_enabled or settings.fake_agents:
            return
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
                    ok, _, _ = await self._arun_pytest()
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
        """Make sure ``ws`` is a git work tree, initializing it (with an Autospec
        identity) if needed. Returns False only if ``git init`` fails."""
        code, _ = await self._agit(ws, "rev-parse", "--is-inside-work-tree")
        if code != 0:
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

    async def _abuild_phase(self) -> None:
        self.state.phase = PipelinePhase.BUILD
        self._sync()
        semaphore = asyncio.Semaphore(settings.max_parallel_devs)

        while not self._stop_requested:
            await self._checkpoint()  # honour pause between story batches
            if self._stop_requested:
                break
            # Recomputed every batch: the user may add stories mid-build.
            iteration_stories = self.state.stories_of_iteration(self.state.iteration)
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

        # Build directives are per-iteration; the next analysis uses `feedback`.
        self.state.build_guidance.clear()

    async def _abuild_story(self, story: UserStory) -> None:
        story.status = StoryStatus.IN_PROGRESS
        story.attempts += 1
        self._sync()
        ws = workspace_dir(self.state.id)
        pkg = workspace.package_name(self.state)
        if story.attempts == 1:
            await self._adesign_tests(story, pkg)
        self._log(f"dev:{story.id}", f"Agent dev assigné à {story.id} — {story.title}")
        try:
            # All workspace mutations (dev write, full-suite pytest, git commit,
            # code refinement) are serialized: parallel workers share one
            # workspace dir and must not interleave.
            async with self._build_lock:
                result = await self._tracked.arun(
                    prompts.dev_story(
                        story, pkg, workspace.feature_rel_path(story), self.state.architecture,
                        "\n".join(self.state.build_guidance),
                        ui_tests=self._ui_mode(story),
                        lessons="\n".join(self._effective_lessons()),
                    ),
                    system_prompt=persona("dev"),
                    cwd=ws,
                )
                reply = extract_json(result.text)
                self._chat(ChatRole.DEV, f"[{story.id}] {reply.get('summary', '(pas de résumé)')}")
                story.status = StoryStatus.GREEN if reply.get("status") == "green" else StoryStatus.RED
                story.ui_tests = [str(p) for p in reply.get("ui_test_files") or []]
                self._sync()

                # Trust but verify: the orchestrator reruns the full test suite
                # itself and grounds per-test states on the REAL pytest outcomes.
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
                if ok and settings.coverage_enabled:
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
                    if settings.refine_for("dev"):
                        await self._arefine_code(story, pkg, ws)
                    await self._arun_mutation_test(story, pkg, ws)
                else:
                    story.last_error = tail
                    self._log(f"dev:{story.id}", f"❌ Tests rouges après passage du dev:\n{tail}")
                    if story.attempts < settings.dev_max_attempts:
                        story.status = StoryStatus.TODO  # will be rescheduled
                    else:
                        story.status = StoryStatus.FAILED
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
        self._log(f"dev:{story.id}", f"Relance de {story.id}…")
        try:
            await self._abuild_story(story)
        except Exception as exc:  # never leave the pipeline in a broken state
            self._chat(ChatRole.SYSTEM, f"Erreur lors de la relance de {story.id} : {exc}")
        finally:
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
        to_build = [
            s
            for s in self.state.stories_of_iteration(self.state.iteration)
            if s.status in (StoryStatus.TODO, StoryStatus.RED)
        ]
        if not to_build:
            raise ValueError("aucune story à construire pour cette itération")
        # The scheduler only picks TODO stories: revert the ones stranded in
        # RED (e.g. persisted mid-attempt before a restart) so they are rebuilt.
        for story in to_build:
            story.status = StoryStatus.TODO
        self._stop_requested = False
        # Set BUILD synchronously BEFORE launching the task so a second
        # concurrent call is rejected by the phase guard (closes the TOCTOU).
        self.state.phase = PipelinePhase.BUILD
        self._sync()
        self._task = asyncio.create_task(self._aresume_build_run())

    async def _aresume_build_run(self) -> None:
        """Background task: re-run the build phase and restore a terminal phase."""
        self._chat(ChatRole.SYSTEM, "▶ Reprise du build de l'itération…")
        try:
            await self._abuild_phase()
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

    async def _arun_pytest(self) -> tuple[bool, str, dict[str, str]]:
        """Run the suite. Returns (suite_green, output, {nodeid: outcome}).

        The per-node outcomes come from a real pytest-json-report run, so test
        states reflect the actual execution rather than the agent's self-report.
        """
        if settings.fake_agents:
            # Demo / e2e mode: no real code is written, trust the scripted dev.
            return True, "mode démo : vérification pytest court-circuitée", {}
        # Run in a worker thread via subprocess: asyncio's subprocess support is
        # unavailable on Windows' SelectorEventLoop (used by uvicorn), so we stay
        # off the event loop entirely for child processes.
        ws = workspace_dir(self.state.id)
        env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}

        def _run() -> tuple[bool, str, dict[str, str]]:
            import tempfile

            fd, report_path = tempfile.mkstemp(suffix=".json", prefix="autospec-report-")
            os.close(fd)
            try:
                proc = subprocess.run(
                    [settings.uv_cmd, "run", "pytest", "-q",
                     "--json-report", f"--json-report-file={report_path}"],
                    cwd=str(ws),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    env=env,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                results = pytest_report.parse(report_path)
                return proc.returncode == 0, proc.stdout, results
            finally:
                try:
                    os.remove(report_path)
                except OSError:
                    pass

        return await asyncio.to_thread(_run)

    # ------------------------------------------------- AUTO-SPEC next cycle

    async def _anext_feature_phase(self) -> None:
        """Analyst explores/prioritizes the backlog and picks the next feature,
        then the PM writes the brief for it."""
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

    async def arun_app(self) -> None:
        if self._run_proc and self._run_proc.poll() is None:
            self._log("run", "L'application tourne déjà.")
            return
        ws = workspace_dir(self.state.id)
        # The generated app is untrusted agent code — give it OS essentials only,
        # never the server's full environment (which may hold secrets).
        env = _minimal_env()
        self.state.running = True
        self._sync()
        self._log("run", "▶ Lancement de l'application générée (uv run python main.py)…")
        # Stream the child's output from a worker thread, marshaling each line
        # back onto the event loop (asyncio subprocesses are unsupported on the
        # Windows SelectorEventLoop that uvicorn runs).
        loop = asyncio.get_running_loop()
        self._stream_task = asyncio.create_task(
            asyncio.to_thread(self._stream_run_output, ws, env, loop)
        )

    def _stream_run_output(self, ws, env, loop: asyncio.AbstractEventLoop) -> None:
        import sys

        # In demo mode run with the current interpreter (hermetic, no uv venv
        # build); otherwise use `uv run` so the workspace's deps are available.
        cmd = [sys.executable, "main.py"] if settings.fake_agents else [settings.uv_cmd, "run", "python", "main.py"]
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
        if self._run_proc is not None and self._run_proc.poll() is None:
            self._run_proc.terminate()
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
