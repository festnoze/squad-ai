"""Tests of the Playwright UI acceptance mode (E5): QA routing of UI stories,
workspace scaffolding and the build-time UI suite gate."""

import json

from autospec.agents import prompts
from autospec.agents.runner import FakeRunner
from autospec.config import settings
from autospec.models import PipelinePhase, ProjectState, StoryStatus, UserStory
from autospec.orchestrator import workspace
from autospec.orchestrator.pipeline import Pipeline

from .conftest import wait_until

PM_BRIEF = json.dumps({"type": "brief", "message": "OK", "brief": "# Brief"})
QA_TRIVIAL = json.dumps({"message": "Trivial.", "tests": []})
PO_PLAN_UI = json.dumps(
    {"epics": [{"id": "EPIC-1", "title": "E", "stories": [
        {"id": "US-1", "title": "Afficher le tableau", "description": "d",
         "acceptance_criteria": ["c"], "gherkin": "Feature: F\n  Scenario: s\n    Given a\n    When b\n    Then c",
         "depends_on": [], "priority": 1, "ui": True},
    ]}]}
)
DEV_GREEN_UI = json.dumps({
    "status": "green",
    "summary": "ok",
    "files": [],
    "test_results": [],
    "ui_test_files": ["tests/ui/test_us_1_ui.py"],
})


def test_dev_prompt_includes_playwright_block_for_ui_story():
    story = UserStory(id="US-1", epic_id="EPIC-1", title="Vue", ui=True)
    prompt = prompts.dev_story(story, "pkg", "features/us_1.feature", ui_tests=True)
    assert "Playwright" in prompt
    assert "tests/ui/test_us_1_ui.py" in prompt
    assert "ui_test_files" in prompt
    # Without the UI mode the block is absent.
    assert "Playwright" not in prompts.dev_story(story, "pkg", "features/us_1.feature")


def test_po_prompt_asks_for_ui_flag():
    state = ProjectState(id="p", name="n", goal="g", brief="# b")
    assert '"ui"' in prompts.po_plan(state, "pkg")


def test_scaffold_with_ui_tests_enabled(monkeypatch):
    monkeypatch.setattr(settings, "ui_tests_enabled", True)
    state = ProjectState(id="proj-ui", name="todo", goal="g")
    ws = workspace.scaffold(state)
    assert (ws / "tests" / "ui" / "__init__.py").exists()
    pyproject = (ws / "pyproject.toml").read_text(encoding="utf-8")
    assert "pytest-playwright" in pyproject
    assert 'addopts = "-m \\"not ui\\""' in pyproject or "not ui" in pyproject


def test_scaffold_without_ui_tests(monkeypatch):
    monkeypatch.setattr(settings, "ui_tests_enabled", False)
    state = ProjectState(id="proj-no-ui", name="todo", goal="g")
    ws = workspace.scaffold(state)
    assert not (ws / "tests" / "ui").exists()
    assert "pytest-playwright" not in (ws / "pyproject.toml").read_text(encoding="utf-8")


async def test_ui_story_runs_ui_suite_when_green(monkeypatch, green_pytest):
    monkeypatch.setattr(settings, "ui_tests_enabled", True)
    ui_runs = []

    async def _arun_ui_tests(self):
        ui_runs.append(True)
        return True, "1 passed"

    monkeypatch.setattr(Pipeline, "_arun_ui_tests", _arun_ui_tests)
    state = ProjectState(id="proj-ui-run", name="todo", goal="g")
    pipeline = Pipeline(state, FakeRunner([PM_BRIEF, PO_PLAN_UI, QA_TRIVIAL, DEV_GREEN_UI]))
    pipeline.start()
    await wait_until(lambda: pipeline.state.phase == PipelinePhase.DONE)
    story = pipeline.state.story("US-1")
    assert story.ui is True
    assert story.status == StoryStatus.DONE
    assert story.ui_tests == ["tests/ui/test_us_1_ui.py"]
    assert ui_runs == [True]
    # The dev prompt of the UI story carried the Playwright instructions.
    dev_prompt = pipeline.runner.calls[-1]["prompt"]
    assert "Playwright" in dev_prompt


async def test_failing_ui_suite_marks_story_red(monkeypatch, green_pytest):
    monkeypatch.setattr(settings, "ui_tests_enabled", True)
    monkeypatch.setattr(settings, "dev_max_attempts", 1)

    async def _arun_ui_tests(self):
        return False, "1 failed: assertion screenshot"

    monkeypatch.setattr(Pipeline, "_arun_ui_tests", _arun_ui_tests)
    state = ProjectState(id="proj-ui-red", name="todo", goal="g")
    pipeline = Pipeline(state, FakeRunner([PM_BRIEF, PO_PLAN_UI, QA_TRIVIAL, DEV_GREEN_UI]))
    pipeline.start()
    await wait_until(lambda: pipeline.state.phase == PipelinePhase.DONE)
    story = pipeline.state.story("US-1")
    assert story.status == StoryStatus.FAILED
    assert "failed" in story.last_error


async def test_ui_story_without_declared_ui_tests_fails(monkeypatch, green_pytest):
    monkeypatch.setattr(settings, "ui_tests_enabled", True)
    monkeypatch.setattr(settings, "dev_max_attempts", 1)
    called = []

    async def _arun_ui_tests(self):
        called.append(True)
        return True, "would pass"

    monkeypatch.setattr(Pipeline, "_arun_ui_tests", _arun_ui_tests)
    dev_green_without_ui_files = json.dumps({
        "status": "green",
        "summary": "ok",
        "files": [],
        "test_results": [],
        "ui_test_files": [],
    })
    state = ProjectState(id="proj-ui-missing", name="todo", goal="g")
    pipeline = Pipeline(
        state,
        FakeRunner([PM_BRIEF, PO_PLAN_UI, QA_TRIVIAL, dev_green_without_ui_files]),
    )
    pipeline.start()
    await wait_until(lambda: pipeline.state.phase == PipelinePhase.DONE)
    story = pipeline.state.story("US-1")
    assert story.status == StoryStatus.FAILED
    assert "Aucun test UI" in story.last_error
    assert called == []


async def test_non_ui_story_skips_ui_suite(monkeypatch, green_pytest):
    monkeypatch.setattr(settings, "ui_tests_enabled", True)
    called = []

    async def _arun_ui_tests(self):
        called.append(True)
        return True, ""

    monkeypatch.setattr(Pipeline, "_arun_ui_tests", _arun_ui_tests)
    po_plan = json.dumps(
        {"epics": [{"id": "EPIC-1", "title": "E", "stories": [
            {"id": "US-1", "title": "Logique pure", "description": "d", "acceptance_criteria": ["c"],
             "gherkin": "Feature: F\n  Scenario: s\n    Given a\n    When b\n    Then c",
             "depends_on": [], "ui": False},
        ]}]}
    )
    dev_green = json.dumps({"status": "green", "summary": "ok", "files": [], "test_results": []})
    state = ProjectState(id="proj-no-ui-run", name="todo", goal="g")
    pipeline = Pipeline(state, FakeRunner([PM_BRIEF, po_plan, QA_TRIVIAL, dev_green]))
    pipeline.start()
    await wait_until(lambda: pipeline.state.phase == PipelinePhase.DONE)
    assert called == []
    assert pipeline.state.story("US-1").status == StoryStatus.DONE
