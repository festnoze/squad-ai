"""ST-13: per-task actions (rebuild / force-done / diff) and their endpoints.

These mirror the existing story actions (rebuild/force-done/diff) but target a
single ``Task`` inside a decomposed user story. ``streams_enabled`` is turned ON
(conftest pins it OFF) with ``fake_agents`` so the worktree-based rebuild runs
its real git operations while the dev step short-circuits green.
"""

import httpx
import pytest

from autospec.agents.scripted import ScriptedRunner
from autospec.api import server
from autospec.config import settings
from autospec.models import (
    Epic,
    PipelinePhase,
    ProjectState,
    Stream,
    StoryStatus,
    StreamKind,
    Task,
    UserStory,
)
from autospec.orchestrator.pipeline import Pipeline


@pytest.fixture
def streams_on(monkeypatch):
    monkeypatch.setattr(settings, "streams_enabled", True)
    monkeypatch.setattr(settings, "fake_agents", True)


def _task(tid, story_id, *, stream="", status=StoryStatus.TODO, depends_on=None):
    return Task(
        id=tid,
        story_id=story_id,
        stream=stream,
        title=tid,
        gherkin="Feature: F\n  Scenario: S\n    Given a\n    When b\n    Then c",
        status=status,
        depends_on=depends_on or [],
    )


def _state(tasks, project_id="task-proj"):
    st = ProjectState(id=project_id, name="taskapp", goal="g")
    st.epics.append(Epic(id="EPIC-1", title="E"))
    st.streams = [
        Stream(id="backend", kind=StreamKind.BACKEND, language="python", primary=True),
        Stream(id="frontend", kind=StreamKind.FRONTEND, language="react", file_root="frontend"),
    ]
    st.stories = [UserStory(id="US-1", epic_id="EPIC-1", title="US-1", tasks=tasks)]
    st.phase = PipelinePhase.DONE
    return st


def _register(state) -> Pipeline:
    server.pipelines.clear()
    pipeline = Pipeline(state, ScriptedRunner())
    server.pipelines[state.id] = pipeline
    return pipeline


def _client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=server.app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


# --------------------------------------------------------------- force-done

async def test_force_done_task_marks_only_that_task_done(streams_on):
    state = _state([_task("T-back", "US-1"), _task("T-front", "US-1", stream="frontend")])
    _register(state)
    async with _client() as client:
        r = await client.post("/api/projects/task-proj/tasks/T-back/force-done")
        assert r.status_code == 200
    assert state.task("T-back").status == StoryStatus.DONE
    assert state.task("T-front").status == StoryStatus.TODO


async def test_force_done_unknown_task_is_404(streams_on):
    _register(_state([_task("T-back", "US-1")]))
    async with _client() as client:
        r = await client.post("/api/projects/task-proj/tasks/NOPE/force-done")
        assert r.status_code == 404


async def test_force_done_task_in_progress_is_409(streams_on):
    state = _state([_task("T-back", "US-1", status=StoryStatus.IN_PROGRESS)])
    _register(state)
    async with _client() as client:
        r = await client.post("/api/projects/task-proj/tasks/T-back/force-done")
        assert r.status_code == 409


# --------------------------------------------------------------- rebuild

async def test_rebuild_task_builds_it_to_done_via_worktree(streams_on):
    state = _state([_task("T-back", "US-1", status=StoryStatus.FAILED)])
    state.task("T-back").last_error = "boom"
    pipeline = _register(state)
    async with _client() as client:
        r = await client.post("/api/projects/task-proj/tasks/T-back/rebuild")
        assert r.status_code == 200
        # rebuild runs in a background task; await it to completion.
        if pipeline._task is not None:
            await pipeline._task
    assert state.task("T-back").status == StoryStatus.DONE
    assert state.task("T-back").last_error == ""
    assert state.phase == PipelinePhase.DONE


async def test_rebuild_task_rejected_while_pipeline_active(streams_on):
    state = _state([_task("T-back", "US-1")])
    state.phase = PipelinePhase.BUILD
    _register(state)
    async with _client() as client:
        r = await client.post("/api/projects/task-proj/tasks/T-back/rebuild")
        assert r.status_code == 409


# --------------------------------------------------------------- diff

async def test_task_diff_available_after_rebuild(streams_on):
    state = _state([_task("T-back", "US-1")])
    pipeline = _register(state)
    async with _client() as client:
        r = await client.post("/api/projects/task-proj/tasks/T-back/rebuild")
        assert r.status_code == 200
        if pipeline._task is not None:
            await pipeline._task
        d = await client.get("/api/projects/task-proj/tasks/T-back/diff")
        assert d.status_code == 200
        body = d.json()
        assert body["ok"] is True
        assert body["available"] is True


async def test_task_diff_unknown_task_is_404(streams_on):
    _register(_state([_task("T-back", "US-1")]))
    async with _client() as client:
        r = await client.get("/api/projects/task-proj/tasks/NOPE/diff")
        assert r.status_code == 404
