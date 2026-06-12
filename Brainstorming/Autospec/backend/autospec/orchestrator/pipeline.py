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
from . import scheduler, workspace
from .events import bus


class Pipeline:
    def __init__(self, state: ProjectState, runner: AgentRunner):
        self.state = state
        self.runner = runner
        self._pm_session: str | None = None
        self._user_messages: asyncio.Queue[str] = asyncio.Queue()
        self._stop_requested = False
        self._task: asyncio.Task | None = None
        self._run_proc: subprocess.Popen | None = None

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
        else:
            # Outside the interview, user messages are feedback for the next cycle.
            self.state.feedback.append(text)
            self._sync()

    async def astop(self) -> None:
        self._stop_requested = True
        # Unblock a PM interview waiting for user input.
        await self._user_messages.put("")
        self._chat(ChatRole.SYSTEM, "Arrêt demandé : la boucle se terminera après l'étape en cours.")

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
                await self._aplan_phase()
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
            result = await self.runner.arun(
                prompts.pm_interview(self.state),
                system_prompt=persona("pm"),
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
        result = await self.runner.arun(
            prompts.po_plan(self.state, pkg),
            system_prompt=persona("sm"),
        )
        plan = extract_json(result.text)
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

    # ------------------------------------------------------------ BUILD (Dev)

    async def _abuild_phase(self) -> None:
        self.state.phase = PipelinePhase.BUILD
        self._sync()
        semaphore = asyncio.Semaphore(settings.max_parallel_devs)
        iteration_stories = self.state.stories_of_iteration(self.state.iteration)

        while not self._stop_requested:
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
            result = await self.runner.arun(
                prompts.dev_story(story, pkg, workspace.feature_rel_path(story)),
                system_prompt=persona("dev"),
                cwd=ws,
            )
            reply = extract_json(result.text)
            self._chat(ChatRole.DEV, f"[{story.id}] {reply.get('summary', '(pas de résumé)')}")
            self._apply_test_results(story, reply.get("test_results", []))
            story.status = StoryStatus.GREEN if reply.get("status") == "green" else StoryStatus.RED
            self._sync()

            # Trust but verify: the orchestrator reruns the full test suite itself.
            ok, output = await self._arun_pytest()
            tail = output[-2000:]
            if ok:
                story.status = StoryStatus.DONE
                # A green suite means every planned test for this story is green.
                for test in story.test_plan:
                    test.status = TestState.GREEN
                self._log(f"dev:{story.id}", f"✅ Suite de tests verte — {story.id} terminé.")
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

    async def _adesign_tests(self, story: UserStory, pkg: str) -> None:
        """QA agent decomposes the acceptance test outside-in (London style)
        into per-layer unit tests, BEFORE any implementation. Non-fatal: a QA
        failure just means the dev works from the Gherkin alone."""
        self._log(f"qa:{story.id}", f"Architecte QA : décomposition outside-in des tests de {story.id}…")
        try:
            result = await self.runner.arun(
                prompts.qa_test_plan(story, pkg),
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

    def _apply_test_results(self, story: UserStory, results: list[dict]) -> None:
        """Update planned-test states from the dev agent's per-test report."""
        by_id = {t.id: t for t in story.test_plan}
        for item in results:
            test = by_id.get(item.get("id"))
            if test is None:
                continue
            reported = item.get("status")
            if reported == "green":
                test.status = TestState.GREEN
            elif reported == "red":
                test.status = TestState.RED

    async def _arun_pytest(self) -> tuple[bool, str]:
        # Run in a worker thread via subprocess: asyncio's subprocess support is
        # unavailable on Windows' SelectorEventLoop (used by uvicorn), so we stay
        # off the event loop entirely for child processes.
        ws = workspace_dir(self.state.id)
        env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}

        def _run() -> tuple[bool, str]:
            proc = subprocess.run(
                [settings.uv_cmd, "run", "pytest", "-q"],
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

    # ------------------------------------------------- AUTO-SPEC next cycle

    async def _anext_feature_phase(self) -> None:
        """Analyst explores/prioritizes the backlog and picks the next feature,
        then the PM writes the brief for it."""
        selected = await self._aanalyze_phase()
        self.state.phase = PipelinePhase.SPEC
        self._sync()
        result = await self.runner.arun(
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

        result = await self.runner.arun(
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
        env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
        self.state.running = True
        self._sync()
        self._log("run", "▶ Lancement de l'application générée (uv run python main.py)…")
        # Stream the child's output from a worker thread, marshaling each line
        # back onto the event loop (asyncio subprocesses are unsupported on the
        # Windows SelectorEventLoop that uvicorn runs).
        loop = asyncio.get_running_loop()
        asyncio.create_task(asyncio.to_thread(self._stream_run_output, ws, env, loop))

    def _stream_run_output(self, ws, env, loop: asyncio.AbstractEventLoop) -> None:
        try:
            proc = subprocess.Popen(
                [settings.uv_cmd, "run", "python", "main.py"],
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

    def _on_run_finished(self, code: int, error: str) -> None:
        self.state.running = False
        self._sync()
        if error:
            self._log("run", f"■ Échec du lancement : {error}")
        else:
            self._log("run", f"■ Application terminée (code {code}).")
