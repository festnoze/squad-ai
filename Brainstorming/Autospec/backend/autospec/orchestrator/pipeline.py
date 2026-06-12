"""The Autospec pipeline: PM (spec) -> PO (plan) -> Dev agents (BDD/TDD build).

One Pipeline instance per project. The whole lifecycle runs as a background
asyncio task; the API talks to it through asend_user_message / astop / arun_app.
"""

from __future__ import annotations

import asyncio
import os
import subprocess

from ..agents import prompts
from ..agents.runner import AgentError, AgentRunner, extract_json
from ..agents.personas import persona
from ..config import settings
from ..models import (
    AcceptanceCriterion,
    ChatMessage,
    ChatRole,
    Epic,
    FeatureHypothesis,
    HypothesisStatus,
    PipelinePhase,
    PlannedTest,
    ProjectState,
    StoryStatus,
    TestState,
    UserStory,
)
from ..storage import save_state, workspace_dir
from . import pytest_report, refine, scheduler, workspace
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
    return {k: v for k, v in os.environ.items() if k.upper() in _SAFE_ENV_KEYS}


class _UsageTracker:
    """Wraps a pipeline's runner to accumulate token/cost usage on the project
    state. Its `arun` matches the AgentRunner Protocol, so it can be passed to
    `refine.arefine` to also count critic/judge/revise calls."""

    def __init__(self, pipeline: "Pipeline"):
        self.pipeline = pipeline

    async def arun(self, prompt, system_prompt, cwd=None, session_id=None):
        res = await self.pipeline.runner.arun(
            prompt, system_prompt, cwd=cwd, session_id=session_id
        )
        usage = self.pipeline.state.usage
        usage.cost_usd += res.cost_usd
        usage.input_tokens += res.input_tokens
        usage.output_tokens += res.output_tokens
        usage.agent_calls += 1
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
        self._run_proc: subprocess.Popen | None = None
        # Serializes the workspace-mutating section of story builds. Parallel dev
        # workers share one workspace directory, so writing code, running the
        # whole pytest suite and committing/refining git must not interleave
        # (else pytest sees half-written trees and git stages the wrong files).
        self._build_lock = asyncio.Lock()

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
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
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
            story.priority = min(5, max(1, int(priority)))
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
        n = len(self.state.stories) + 1
        while f"US-{n}" in existing_ids:
            n += 1
        criteria = [
            AcceptanceCriterion(id=f"AC-{i}", text=str(text))
            for i, text in enumerate(acceptance_criteria or [], start=1)
        ]
        story = UserStory(
            id=f"US-{n}",
            epic_id=epic_id,
            title=title,
            description=description,
            acceptance_criteria=criteria,
            gherkin=gherkin,
            depends_on=depends_on or [],
            priority=min(5, max(1, int(priority))),
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
                story.priority = min(5, max(1, int(entry["priority"])))
        self._sync()

    # ------------------------------------------------------------ lifecycle

    async def _alifecycle(self) -> None:
        try:
            workspace.scaffold(self.state)
            brief = await self._aspec_phase()
            if brief is None:  # stopped during interview
                self.state.phase = PipelinePhase.STOPPED
                self._sync()
                return

            while not self._stop_requested:
                await self._checkpoint()
                if self._stop_requested:
                    break
                await self._aplan_phase()
                await self._aarchitect_phase()
                await self._abuild_phase()
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
        except Exception as exc:  # surface any pipeline failure to the UI
            self.state.phase = PipelinePhase.ERROR
            self.state.error = str(exc)
            self._chat(ChatRole.SYSTEM, f"Erreur pipeline : {exc}")

    # ------------------------------------------------------------ SPEC (PM)

    async def _aspec_phase(self) -> str | None:
        self.state.phase = PipelinePhase.SPEC
        self._sync()
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
            # type == "question": wait for the user's answer.
            answer = await self._user_messages.get()
            if self._stop_requested:
                return None
            # answer was already appended to chat by asend_user_message
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
        new_stories: list[UserStory] = []
        for epic_data in plan.get("epics", []):
            epic = Epic(
                id=epic_data.get("id", f"EPIC-{len(self.state.epics) + 1}"),
                title=epic_data.get("title", "Epic"),
                description=epic_data.get("description", ""),
                iteration=self.state.iteration,
            )
            self.state.epics.append(epic)
            for story_data in epic_data.get("stories", []):
                story_id = story_data.get(
                    "id", f"US-{len(self.state.stories) + len(new_stories) + 1}"
                )
                criteria = [
                    AcceptanceCriterion(id=f"AC-{i}", text=str(text))
                    for i, text in enumerate(story_data.get("acceptance_criteria", []), start=1)
                ]
                new_stories.append(
                    UserStory(
                        id=story_id,
                        epic_id=epic.id,
                        title=story_data.get("title", "Story"),
                        description=story_data.get("description", ""),
                        acceptance_criteria=criteria,
                        gherkin=story_data.get("gherkin", ""),
                        depends_on=story_data.get("depends_on", []),
                        priority=min(5, max(1, int(story_data.get("priority", 3)))),
                        iteration=self.state.iteration,
                    )
                )
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
        if outcome.stopped_reason != "disabled":
            story.quality_score = outcome.score
            self._chat(
                ChatRole.SYSTEM,
                f"[{story.id}] Code raffiné en {outcome.rounds} tour(s) — "
                f"qualité {outcome.score}/100 (arrêt : {outcome.stopped_reason}).",
            )

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
        iteration_stories = self.state.stories_of_iteration(self.state.iteration)

        while not self._stop_requested:
            await self._checkpoint()  # honour pause between story batches
            if self._stop_requested:
                break
            pending = scheduler.pending_stories(iteration_stories)
            if not pending:
                break
            ready = scheduler.ready_stories(iteration_stories)
            in_flight = [s for s in iteration_stories if s.status == StoryStatus.IN_PROGRESS]
            if not ready and not in_flight:
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
                    ),
                    system_prompt=persona("dev"),
                    cwd=ws,
                )
                reply = extract_json(result.text)
                self._chat(ChatRole.DEV, f"[{story.id}] {reply.get('summary', '(pas de résumé)')}")
                story.status = StoryStatus.GREEN if reply.get("status") == "green" else StoryStatus.RED
                self._sync()

                # Trust but verify: the orchestrator reruns the full test suite
                # itself and grounds per-test states on the REAL pytest outcomes.
                ok, output, real = await self._arun_pytest()
                tail = output[-2000:]
                self._apply_test_states(story, reply.get("test_results", []), real)
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
                else:
                    story.last_error = tail
                    self._log(f"dev:{story.id}", f"❌ Tests rouges après passage du dev:\n{tail}")
                    if story.attempts < settings.dev_max_attempts:
                        story.status = StoryStatus.TODO  # will be rescheduled
                    else:
                        story.status = StoryStatus.FAILED
        except AgentError as exc:
            story.last_error = str(exc)
            story.status = (
                StoryStatus.TODO
                if story.attempts < settings.dev_max_attempts
                else StoryStatus.FAILED
            )
            self._log(f"dev:{story.id}", f"Erreur agent : {exc}")
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
                prompts.qa_test_plan(story, pkg, self.state.architecture),
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
                    value=min(5, max(1, int(data.get("value", 3)))),
                    complexity=min(5, max(1, int(data.get("complexity", 3)))),
                    rank=rank,
                )
            )
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
        asyncio.create_task(asyncio.to_thread(self._stream_run_output, ws, env, loop))

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
