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


# ------------------------------------------------- P5: partial delivery


def _failed_story(story_id="US-2") -> UserStory:
    return UserStory(
        id=story_id,
        epic_id="E1",
        title="Ratée",
        status=StoryStatus.FAILED,
        acceptance_criteria=[AcceptanceCriterion(id="AC-1", text="x")],
        gherkin="Feature: F\n  Scenario: S\n    Given a\n    When b\n    Then c",
    )


def test_partial_delivery_ships_around_failed_story():
    """P5: ≥1 story DONE → the FAILED one downgrades to a warning, the gate
    passes and the result is flagged partial."""
    state = ProjectState(
        id="dod-part", name="n", goal="g", stories=[_green_story(), _failed_story()]
    )
    result = evaluate_definition_of_done(state, partial=True)
    assert result.ready is True
    assert result.partial is True
    assert not result.blockers
    assert any(i.code == "story_failed_partial" for i in result.warnings)
    assert any(i.code == "partial_delivery" for i in result.warnings)


def test_partial_delivery_blocked_when_nothing_shipped():
    """P5: ZERO story DONE → nothing to ship around, failures stay blockers."""
    state = ProjectState(id="dod-zero", name="n", goal="g", stories=[_failed_story()])
    result = evaluate_definition_of_done(state, partial=True)
    assert result.ready is False
    assert result.partial is False
    assert any(i.code == "story_not_done" for i in result.blockers)


def test_partial_delivery_still_blocks_unfinished_items():
    """P5: TODO/IN_PROGRESS mean the orchestration didn't finish — they block
    even in partial mode (only FAILED ships around)."""
    todo = _failed_story("US-3")
    todo.status = StoryStatus.TODO
    state = ProjectState(
        id="dod-unfinished", name="n", goal="g", stories=[_green_story(), todo]
    )
    result = evaluate_definition_of_done(state, partial=True)
    assert result.ready is False
    assert result.partial is False
    assert any(i.code == "story_not_done" for i in result.blockers)


def test_partial_delivery_off_keeps_all_or_nothing():
    state = ProjectState(
        id="dod-off", name="n", goal="g", stories=[_green_story(), _failed_story()]
    )
    result = evaluate_definition_of_done(state, partial=False)
    assert result.ready is False
    assert result.partial is False


def test_partial_delivery_failed_task_downgrades_with_the_story():
    """A FAILED task (and its container story) ships around like a failed story."""
    story = _green_story("US-4")
    story.status = StoryStatus.TODO  # container: status derives from tasks
    story.tasks = [
        Task(id="T-1", story_id=story.id, title="ok", status=StoryStatus.DONE),
        Task(id="T-2", story_id=story.id, title="ko", status=StoryStatus.FAILED),
    ]
    state = ProjectState(
        id="dod-task", name="n", goal="g", stories=[_green_story("US-1"), story]
    )
    result = evaluate_definition_of_done(state, partial=True)
    assert result.ready is True
    assert result.partial is True
    assert any(i.code == "task_failed_partial" for i in result.warnings)


def test_pipeline_partial_delivery_sets_state_flag(monkeypatch):
    monkeypatch.setattr(settings, "definition_of_done_enabled", True)
    monkeypatch.setattr(settings, "partial_delivery_enabled", True)
    state = ProjectState(
        id="dod-flag", name="n", goal="g", stories=[_green_story(), _failed_story()]
    )
    pipeline = Pipeline(state, FakeRunner([]))
    assert pipeline._apply_definition_of_done() is True
    assert state.delivery_ready is True
    assert state.delivery_partial is True
    assert any("Livraison partielle" in issue for issue in state.delivery_issues)
