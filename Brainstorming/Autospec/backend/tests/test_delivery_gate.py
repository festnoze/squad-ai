"""Delivery gate: Definition of Done and effective delivery status."""

import json

from autospec.agents.runner import FakeRunner
from autospec.config import settings
from autospec.models import (
    AcceptanceCriterion,
    PipelinePhase,
    PlannedTest,
    ProjectState,
    StoryStatus,
    Task,
    TestState,
    UserStory,
)
from autospec.orchestrator.delivery_gate import evaluate_definition_of_done
from autospec.orchestrator.pipeline import Pipeline
from .conftest import wait_until


def _green_story(story_id="US-1") -> UserStory:
    return UserStory(
        id=story_id,
        epic_id="E1",
        title="Livrer",
        status=StoryStatus.DONE,
        acceptance_criteria=[AcceptanceCriterion(id="AC-1", text="visible")],
        gherkin="Feature: F\n  Scenario: S\n    Given a\n    When b\n    Then visible",
        test_plan=[PlannedTest(id="UT-1", criteria=["AC-1"], status=TestState.GREEN)],
    )


def test_definition_of_done_passes_green_story():
    state = ProjectState(id="dod-ok", name="n", goal="g", stories=[_green_story()])
    result = evaluate_definition_of_done(state)
    assert result.ready is True
    assert result.blockers == ()


def test_definition_of_done_blocks_effective_status_not_done():
    story = _green_story()
    story.tasks = [
        Task(id="T-1", story_id=story.id, title="done", status=StoryStatus.DONE),
        Task(id="T-2", story_id=story.id, title="todo", status=StoryStatus.TODO),
    ]
    state = ProjectState(id="dod-half", name="n", goal="g", stories=[story])
    result = evaluate_definition_of_done(state)
    assert result.ready is False
    assert any(i.code == "story_not_done" for i in result.blockers)
    assert any(i.code == "task_not_done" for i in result.blockers)


def test_definition_of_done_requires_ui_evidence_when_enabled():
    story = _green_story()
    story.ui = True
    state = ProjectState(id="dod-ui", name="n", goal="g", stories=[story])
    result = evaluate_definition_of_done(state, require_ui_evidence=True)
    assert result.ready is False
    assert any(i.code == "ui_tests_missing" for i in result.blockers)


def test_definition_of_done_strict_criteria_blocks_missing_green_evidence():
    story = _green_story()
    story.test_plan = [PlannedTest(id="UT-1", criteria=["AC-1"], status=TestState.NONEXISTENT)]
    state = ProjectState(id="dod-strict", name="n", goal="g", stories=[story])
    soft = evaluate_definition_of_done(state, strict_criteria=False)
    strict = evaluate_definition_of_done(state, strict_criteria=True)
    assert soft.ready is True
    assert soft.warnings
    assert strict.ready is False
    assert any(i.code == "criterion_not_green" for i in strict.blockers)


def test_pipeline_delivery_gate_sets_serialized_state(monkeypatch):
    monkeypatch.setattr(settings, "definition_of_done_enabled", True)
    story = _green_story()
    story.tasks = [Task(id="T-1", story_id=story.id, title="todo", status=StoryStatus.TODO)]
    state = ProjectState(id="dod-pipeline", name="n", goal="g", stories=[story])
    pipeline = Pipeline(state, FakeRunner([]))
    assert pipeline._apply_definition_of_done() is False
    assert state.delivery_ready is False
    assert state.delivery_issues
    dumped = story.model_dump(mode="json")
    assert dumped["effective_status_value"] == "todo"


async def test_delivery_gate_blocked_lifecycle_needs_attention(monkeypatch):
    monkeypatch.setattr(settings, "definition_of_done_enabled", True)
    state = ProjectState(id="dod-lifecycle", name="n", goal="g")
    pm_brief = json.dumps({"type": "brief", "message": "OK", "brief": "# Brief"})
    empty_plan = json.dumps({"epics": []})
    pipeline = Pipeline(state, FakeRunner([pm_brief, empty_plan]))

    pipeline.start()
    await wait_until(lambda: state.phase == PipelinePhase.NEEDS_ATTENTION)

    assert state.error == ""
    assert state.delivery_ready is False
    assert any("Aucune user story" in issue for issue in state.delivery_issues)
