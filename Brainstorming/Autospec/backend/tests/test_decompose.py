"""SK-2: story decomposition into layered sub-tasks (built by the parallel
worktree engine, then aggregated). These cover the decomposer itself — the
worktree build/aggregate substrate is exercised by the existing streams tests."""

from __future__ import annotations

import json

from autospec.agents.runner import FakeRunner
from autospec.models import AcceptanceCriterion, Epic, ProjectState, StoryStatus, UserStory
from autospec.orchestrator.pipeline import Pipeline


def _state_with(*stories: UserStory) -> ProjectState:
    state = ProjectState(id="proj-decomp", name="n", goal="g")
    state.epics = [Epic(id="E1", title="e1", iteration=1)]
    state.stories = list(stories)
    return state


def _story(sid="US-1", status=StoryStatus.TODO, tasks=None) -> UserStory:
    return UserStory(
        id=sid, epic_id="E1", title=f"{sid} titre", description="desc", status=status,
        acceptance_criteria=[AcceptanceCriterion(id="AC-1", text="critère")],
        gherkin="Feature: F\n  Scenario: S\n    Given a\n    When b\n    Then c",
        tasks=tasks or [],
    )


DECOMPOSE = json.dumps(
    {
        "message": "Découpage par couche.",
        "tasks": [
            {"id": "A", "layer": "application", "skill": "service-search-or-create",
             "title": "Service de calcul", "description": "svc",
             "acceptance_criteria": ["AC-1"], "gherkin": "Feature: svc", "depends_on": []},
            {"id": "B", "layer": "facade", "skill": "endpoint-search-or-create",
             "title": "Endpoint", "description": "ep",
             "acceptance_criteria": ["AC-1", "AC-UNKNOWN"], "gherkin": "Feature: ep",
             "depends_on": ["A"]},
        ],
    }
)


async def test_decompose_story_materializes_layered_tasks():
    story = _story()
    state = _state_with(story)
    pipe = Pipeline(state, FakeRunner([DECOMPOSE]))

    await pipe._adecompose_story(story)

    assert len(story.tasks) == 2
    # Agent-local ids ("A"/"B") are remapped to project-wide-unique ids…
    assert [t.id for t in story.tasks] == ["US-1-T1", "US-1-T2"]
    # …and depends_on is remapped to the new ids (B depends on A).
    assert story.tasks[1].depends_on == ["US-1-T1"]
    # Tasks land on the project's primary (backend) stream.
    assert all(t.stream == state.primary_stream_id for t in story.tasks)
    # Unknown criterion id is dropped; the valid one is kept.
    assert [c.id for c in story.tasks[1].acceptance_criteria] == ["AC-1"]
    # Layer + skill are surfaced in the task description (focuses the subagent).
    assert story.tasks[0].description.startswith("[couche application · skill `service-search-or-create`]")


async def test_trivial_decomposition_leaves_story_whole():
    story = _story()
    one_task = json.dumps({"message": "trivial", "tasks": [
        {"id": "A", "layer": "service", "title": "x", "acceptance_criteria": ["AC-1"]}]})
    pipe = Pipeline(_state_with(story), FakeRunner([one_task]))

    await pipe._adecompose_story(story)
    assert story.tasks == []          # <2 tasks → not decomposed


async def test_decompose_failure_is_non_fatal():
    story = _story()
    pipe = Pipeline(_state_with(story), FakeRunner([]))  # no reply → AgentError

    await pipe._adecompose_story(story)   # must not raise
    assert story.tasks == []


async def test_decompose_pending_only_eligible_backend_stories():
    from autospec.models import Task

    todo = _story("US-1", StoryStatus.TODO)
    done = _story("US-2", StoryStatus.DONE)
    # US-3 already has a task → already decomposed, must be skipped.
    already = _story("US-3", StoryStatus.TODO,
                     tasks=[Task(id="US-3-T1", story_id="US-3", stream="backend", title="pre")])
    state = _state_with(todo, done, already)
    # Exactly one eligible story (US-1) → exactly one decompose reply needed.
    pipe = Pipeline(state, FakeRunner([DECOMPOSE]))

    await pipe._adecompose_pending()

    assert len(state.story("US-1").tasks) == 2     # decomposed
    assert state.story("US-2").tasks == []         # done → skipped
    assert [t.id for t in state.story("US-3").tasks] == ["US-3-T1"]  # had tasks → untouched


async def test_build_phase_routes_through_decompose_then_streams(monkeypatch):
    from autospec.config import settings

    state = _state_with(_story())
    pipe = Pipeline(state, FakeRunner([]))
    calls: list[str] = []

    async def _fake_decompose(self, all_iterations=False):
        calls.append("decompose")

    async def _fake_streams(self, all_iterations=False):
        calls.append("streams")

    monkeypatch.setattr(settings, "decompose_enabled", True)
    monkeypatch.setattr(Pipeline, "_adecompose_pending", _fake_decompose)
    monkeypatch.setattr(Pipeline, "_abuild_phase_streams", _fake_streams)

    await pipe._abuild_phase()
    # decompose runs first, then the parallel worktree engine aggregates.
    assert calls == ["decompose", "streams"]

