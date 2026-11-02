"""The v2 pipeline: brief, plan, then one story at a time, then delivery.

Agents do the work with their native tools; the factory never trusts their
report and verifies every story itself (docs/REFONTE_V2.md section 4).
"""

from __future__ import annotations

import asyncio
import json
import time
import tomllib
from collections.abc import Callable
from pathlib import Path

from . import machine, plan, profiles, prompts, verify
from .models import Phase, Profile, ProjectState, Story, StoryStatus
from .ports import AgentCall, AgentError, AgentResult, AgentRunner, Capability
from .settings import Settings
from .store import Store

ACCEPTANCE_DIRS = ("tests/acceptance/", "frontend/src/acceptance/")
# Vite carries the vitest settings (included files, setup files): changing it could hide tests.
TEST_CONFIG_FILES = ("frontend/vite.config.", "frontend/vitest.config.", "frontend/vitest.setup.")
PLAN_MAX_ATTEMPTS = 2


class Parked(Exception):
    """Stop the run and hand the project to a human (phase NEEDS_ATTENTION)."""


class Pipeline:
    def __init__(self, state: ProjectState, ws: Path, runner: AgentRunner, settings: Settings,
                 *, on_event: Callable[[dict], None] | None = None):
        self.state = state
        self.ws = Path(ws)
        self.runner = runner
        self.settings = settings
        self.store = Store(self.ws)
        self._on_event = on_event

    # -- bookkeeping -------------------------------------------------------

    def _emit(self, event: str, **data) -> None:
        record = self.store.append_event({"type": event, **data})
        if self._on_event:
            self._on_event(record)

    def _save(self) -> None:
        self.store.save(self.state)

    def _phase(self, phase: Phase) -> None:
        machine.set_phase(self.state, phase)
        self._save()
        self._emit("phase", phase=phase.value)

    def _story_status(self, story: Story, status: StoryStatus, **data) -> None:
        machine.set_story_status(story, status)
        self._save()
        self._emit("story", id=story.id, status=status.value, attempts=story.attempts, **data)

    def _account(self, result: AgentResult | None) -> None:
        if result is None:
            return
        self.state.usage.add(result.cost_usd, result.input_tokens, result.output_tokens, result.duration_ms)
        self._save()

    async def _acall(self, role: str, prompt: str, capability: Capability, *,
                     resume: str | None = None, model: str | None = None) -> AgentResult:
        remaining = self.settings.project_budget_usd - self.state.usage.cost_usd
        if remaining <= 0:
            raise Parked(f"project budget of {self.settings.project_budget_usd} USD reached")
        call = AgentCall(
            role=role, prompt=prompt, system_prompt=prompts.SYSTEM[role], capability=capability,
            cwd=self.ws,
            model=model or self.settings.model, resume_session_id=resume,
            timeout_s=self.settings.agent_timeout_s,
            max_budget_usd=round(min(self.settings.call_budget_usd, remaining), 2),
        )
        self._emit("agent_start", role=role, resume=bool(resume))
        try:
            result = await self.runner.arun(call)
        except AgentError as exc:
            self._account(exc.result)
            self._emit("agent_error", role=role, kind=exc.kind, message=str(exc)[:500])
            if exc.kind in ("budget", "unavailable"):
                raise Parked(f"{role} agent: {exc}") from exc
            raise
        self._account(result)
        self._emit("agent_end", role=role, cost_usd=result.cost_usd, turns=result.num_turns,
                   denials=len(result.denials))
        return result

    # -- run ----------------------------------------------------------------

    async def arun(self) -> ProjectState:
        if self.state.phase == Phase.DONE:
            return self.state
        started = time.monotonic()
        machine.prepare_resume(self.state)
        try:
            start = machine.resume_phase(self.state)
            if start == Phase.BRIEF:
                self._phase(Phase.BRIEF)
                await self._abrief()
            if start in (Phase.BRIEF, Phase.PLAN):
                self._phase(Phase.PLAN)
                await self._aplan()
            if start != Phase.DELIVER:
                self._phase(Phase.BUILD)
                await self._abuild()
            self._phase(Phase.DELIVER)
            await self._adeliver()
        except Parked as exc:
            self.state.error = str(exc)
            self._phase(Phase.NEEDS_ATTENTION)
        except (asyncio.CancelledError, KeyboardInterrupt):
            self.state.error = "interrupted"
            self._phase(Phase.STOPPED)
            raise
        except Exception as exc:  # the state must always land somewhere a human can see
            self.state.error = f"{type(exc).__name__}: {exc}"
            self._phase(Phase.ERROR)
        self._emit("end", phase=self.state.phase.value, duration_s=round(time.monotonic() - started, 1),
                   cost_usd=self.state.usage.cost_usd)
        return self.state

    async def _abrief(self) -> None:
        result = await self._acall("pm", prompts.pm_brief(self.state.goal), Capability.TEXT,
                                   model=self.settings.effective_plan_model)
        self.state.brief = plan.parse_brief(result.text)
        self._save()

    async def _aplan(self) -> None:
        prompt = prompts.po_plan(self.state.brief, package=self.state.package, profile=self.state.profile)
        session = None
        for _ in range(PLAN_MAX_ATTEMPTS):
            result = await self._acall("po", prompt, Capability.TEXT, resume=session,
                                       model=self.settings.effective_plan_model)
            try:
                profile, epics, stories = plan.parse_plan(result.text, profile=self.state.profile)
            except plan.PlanError as exc:
                session = result.session_id
                prompt = (f"Your plan was rejected by the factory: {exc}\n"
                          "Answer again with the complete corrected JSON plan only.")
                self._emit("plan_rejected", reason=str(exc)[:500])
                continue
            self.state.profile, self.state.epics, self.state.stories = profile, epics, stories
            self._save()
            self._emit("plan", stories=[s.id for s in stories], profile=profile.value)
            return
        raise Parked("the PO could not produce a valid plan")

    def _ensure_scaffold(self) -> None:
        if not (self.ws / "pyproject.toml").exists():
            profiles.scaffold(self.ws, project_name=self.state.name, package=self.state.package,
                              profile=self.state.profile)
            self._emit("scaffold", profile=self.state.profile.value)

    async def _abuild(self) -> None:
        self._ensure_scaffold()
        while (story := plan.next_ready(self.state.stories)) is not None:
            await self._abuild_story(story)
            if story.status == StoryStatus.FAILED:
                raise Parked(f"{story.id} failed: {story.last_error[-1500:]}")
        blocked = [s.id for s in self.state.stories if s.status != StoryStatus.DONE]
        if blocked:
            raise Parked(f"stories never became ready: {', '.join(blocked)}")

    async def _abuild_story(self, story: Story) -> None:
        self._story_status(story, StoryStatus.IN_PROGRESS)
        if not story.acceptance_tests:
            failure, satisfied = await self._aqa(story)
            if failure:
                story.last_error = failure
                self._story_status(story, StoryStatus.FAILED, reason="qa")
                return
            if satisfied:
                # Earlier stories already deliver every criterion: the tests stay as guards.
                self._story_status(story, StoryStatus.DONE, reason="already_satisfied")
                return
        await self._adev(story)

    # -- QA: executable acceptance tests, verified red ------------------------

    def _reset_tree(self) -> None:
        verify.discard_changes(self.ws)

    async def _aqa(self, story: Story) -> tuple[str, bool]:
        """Commit valid acceptance tests: ("", already_satisfied) or (last failure, False)."""
        if verify.changed_paths(self.ws):
            self._reset_tree()  # leftovers of an interrupted session are unverified work
        prompt = prompts.qa_tests(story, package=self.state.package, profile=self.state.profile,
                                  repo_tree=verify.repo_tree(self.ws))
        session, failure = None, ""
        for _ in range(self.settings.qa_max_attempts):
            try:
                result = await self._acall("qa", prompt, Capability.QA, resume=session)
            except AgentError as exc:
                failure, session = f"QA session failed: {exc}", None
                prompt = prompts.qa_tests(story, package=self.state.package, profile=self.state.profile,
                                          repo_tree=verify.repo_tree(self.ws))
                continue
            session = result.session_id
            failure, tests, satisfied = await self._acheck_acceptance(story, result.text)
            if not failure:
                story.acceptance_tests = tests
                files = sorted({n.split("::", 1)[0] for t in tests for n in t.nodeids})
                story.test_fingerprint = verify.fingerprint(self.ws, files)
                verify.git_commit(self.ws, f"{story.id}: acceptance tests")
                self._save()
                self._emit("acceptance_tests", id=story.id, nodeids=sum(len(t.nodeids) for t in tests),
                           already_satisfied=satisfied)
                return "", satisfied
            self._emit("qa_rejected", id=story.id, reason=failure[:500])
            prompt = (f"The factory rejected your acceptance tests: {failure}\n"
                      "Fix them, then answer again with the final JSON only.")
        self._reset_tree()
        return failure, False

    def _acceptance_file_problem(self, rel: str, text: str) -> str:
        """Acceptance tests must be valid and exercise the product, not test themselves."""
        if rel.endswith(".py"):
            try:
                compile(text, rel, "exec")
            except SyntaxError as exc:
                return f"{rel} is not valid Python: {exc}"
            if self.state.package not in text:
                return (f"{rel} never references the package `{self.state.package}`: acceptance tests "
                        "must exercise the product through its public interface")
            return ""
        if "from '../" not in text and 'from "../' not in text:
            return f"{rel} never imports product code (relative import such as '../App')"
        return ""

    async def _acheck_acceptance(self, story: Story, answer: str) -> tuple[str, list, bool]:
        try:
            tests = plan.parse_qa(answer, story, profile=self.state.profile)
        except plan.PlanError as exc:
            return f"invalid answer: {exc}", [], False
        own_files = plan.acceptance_files(story.id, self.state.profile)
        outside = [p for p in verify.changed_paths(self.ws) if p not in own_files]
        if outside:
            verify.discard_changes(self.ws, outside)
            return (f"you changed files outside {', '.join(own_files)} (reverted): "
                    f"{', '.join(outside)}"), [], False
        files = sorted({n.split("::", 1)[0] for t in tests for n in t.nodeids})
        for rel in files:
            source = self.ws / rel
            if not source.is_file():
                return f"test file {rel} does not exist", [], False
            problem = self._acceptance_file_problem(rel, source.read_text(encoding="utf-8"))
            if problem:
                return problem, [], False
        # Fullstack: the frontend must be built before Python tests of GET / can pass.
        select = None if self.state.profile == Profile.FULLSTACK else files
        suite = await verify.arun_suite(self.ws, select=select, clean=False,
                                        timeout_s=self.settings.suite_timeout_s)
        if suite.env_error:
            raise Parked(f"clean environment cannot be built: {suite.env_error[-1000:]}")
        nodeids = [n for t in tests for n in t.nodeids]
        unknown = [n for n in nodeids if n not in suite.outcomes and not suite.collection_errors]
        if unknown:
            return f"these nodeids were not collected by pytest: {', '.join(unknown)}", [], False
        # A criterion may already hold thanks to earlier stories: such tests are kept as
        # regression guards. When ALL pass, the story is already delivered.
        passing = verify.red_check(suite, nodeids)
        if passing:
            self._emit("already_green", id=story.id, nodeids=passing)
        return "", tests, bool(passing) and len(set(passing)) == len(set(nodeids))

    # -- Dev: native TDD session, then independent verification ---------------

    async def _adev(self, story: Story) -> None:
        feedback = ""
        while story.attempts < self.settings.dev_max_attempts:
            story.attempts += 1
            self._save()
            if feedback and story.dev_session_id:
                prompt, resume = prompts.dev_retry(feedback, profile=self.state.profile), story.dev_session_id
            else:
                prompt, resume = prompts.dev_story(story, package=self.state.package, profile=self.state.profile,
                                                   repo_tree=verify.repo_tree(self.ws)), None
            try:
                result = await self._acall("dev", prompt, Capability.DEV, resume=resume)
            except AgentError as exc:
                feedback = story.last_error = f"the dev session ended with an error: {exc}"
                story.dev_session_id = None
                continue
            story.dev_session_id = result.session_id
            plan.parse_dev(result.text)
            failure = await self._averify_story(story)
            if not failure:
                verify.git_commit(self.ws, f"{story.id} done")
                story.last_error = ""
                self._story_status(story, StoryStatus.DONE)
                return
            feedback = story.last_error = failure
            self._emit("verify_failed", id=story.id, attempt=story.attempts, reason=failure[:500])
        self._story_status(story, StoryStatus.FAILED, reason="dev")

    def _section_changed(self, rel: str, load, section) -> bool:
        """Whether ``section(load(text))`` differs between HEAD and the working tree."""
        target = self.ws / rel
        head = profiles.run_git(self.ws, "show", f"HEAD:{rel}", check=False)
        if head.returncode != 0 and not target.exists():
            return False
        try:
            before = section(load(head.stdout)) if head.returncode == 0 else None
            after = section(load(target.read_text(encoding="utf-8"))) if target.exists() else None
        except (OSError, ValueError):
            return True
        return before != after

    def _test_config_changes(self) -> list[str]:
        """Test selection settings the dev must not touch: they could hide acceptance tests."""
        changed = []
        if self._section_changed("pyproject.toml", tomllib.loads,
                                 lambda d: d.get("tool", {}).get("pytest")):
            changed.append("the [tool.pytest] section of pyproject.toml")
        if self._section_changed("frontend/package.json", json.loads, lambda d: d.get("scripts")):
            changed.append("the scripts of frontend/package.json")
        return changed

    async def _averify_story(self, story: Story) -> str:
        # conftest.py hooks or pytest options could rewrite acceptance outcomes.
        touched = [p for p in verify.changed_paths(self.ws) if p.startswith(ACCEPTANCE_DIRS)
                   or p.rsplit("/", 1)[-1] == "conftest.py" or p.startswith(TEST_CONFIG_FILES)]
        if touched:
            verify.discard_changes(self.ws, touched)
            return (f"you modified acceptance tests or test configuration files, which is forbidden; "
                    f"they were restored: {', '.join(touched)}. Make the implementation pass the "
                    "original tests.")
        config = self._test_config_changes()
        if config:
            return (f"you changed {' and '.join(config)}, which is forbidden: restore it exactly as "
                    "it was and make the implementation pass the tests.")
        suite = await verify.arun_suite(self.ws, timeout_s=self.settings.suite_timeout_s)
        if suite.env_error:
            how = "`uv add`" + (" or `npm --prefix frontend install <pkg>`"
                                if self.state.profile == Profile.FULLSTACK else "")
            return ("the clean environment could not be built from the manifests and lock files "
                    f"(declare dependencies with {how}):\n{suite.env_error[-2000:]}")
        if not suite.ok:
            return f"the full suite is not green in a clean environment:\n{suite.output_tail}"
        missing = verify.missing_criteria(story, suite)
        if missing:
            return f"acceptance tests not passing for criteria: {', '.join(missing)}"
        return ""

    # -- delivery -----------------------------------------------------------

    async def _adeliver(self) -> None:
        suite = await verify.arun_suite(self.ws, timeout_s=self.settings.suite_timeout_s)
        if not suite.ok:
            raise Parked(f"final suite not green: {(suite.env_error or suite.output_tail)[-1500:]}")
        smoke = await verify.asmoke(self.ws, package=self.state.package, profile=self.state.profile,
                                    timeout_s=self.settings.smoke_timeout_s)
        self._emit("smoke", ok=smoke.ok, detail=smoke.detail[:500])
        if not smoke.ok:
            raise Parked(f"smoke failed: {smoke.detail[-1500:]}")
        verify.git_commit(self.ws, "delivery")
        self._phase(Phase.DONE)
