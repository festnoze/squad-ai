"""P6 — adaptive split-on-failure: a story/task that can't be made green after its
dev attempts is re-analyzed and split into FINER sub-tasks instead of failing
(counters the « unit too big for one agent session » problem)."""

import asyncio

import pytest

from autospec.agents.scripted import ScriptedRunner
from autospec.config import settings
from autospec.models import (
    Epic,
    ProjectState,
    Stream,
    StoryStatus,
    StreamKind,
    Task,
    UserStory,
)
from autospec.orchestrator.pipeline import Pipeline


def _streams_state(stories, project_id="split-proj"):
    st = ProjectState(id=project_id, name="splitapp", goal="g")
    st.epics.append(Epic(id="EPIC-1", title="E"))
    st.streams = [
        Stream(id="backend", kind=StreamKind.BACKEND, language="python", primary=True),
        Stream(id="frontend", kind=StreamKind.FRONTEND, language="react", file_root="frontend"),
    ]
    st.stories = stories
    return st


def _us(sid, *, stream="", tasks=None, status=StoryStatus.TODO):
    return UserStory(
        id=sid, epic_id="EPIC-1", title=sid,
        gherkin="Feature: F\n  Scenario: S\n    Given a\n    When b\n    Then c",
        stream=stream, tasks=tasks or [], status=status,
    )


def _task(tid, story_id, *, stream="", deps=(), status=StoryStatus.TODO):
    return Task(id=tid, story_id=story_id, stream=stream, title=tid, depends_on=list(deps), status=status)


@pytest.fixture
def streams_on(monkeypatch):
    monkeypatch.setattr(settings, "streams_enabled", True)
    monkeypatch.setattr(settings, "fake_agents", True)
    monkeypatch.setattr(settings, "split_on_failure_enabled", True)
    monkeypatch.setattr(settings, "split_max_depth", 1)


# --------------------------------------------------------------- unit: splitting

def test_split_story_creates_finer_tasks(streams_on):
    state = _streams_state([_us("US-1", stream="backend")])
    pipeline = Pipeline(state, ScriptedRunner())
    story = state.story("US-1")
    raw = [
        {"id": "a", "title": "A", "file_globs": ["x.py"], "depends_on": []},
        {"id": "b", "title": "B", "file_globs": ["y.py"], "depends_on": ["a"]},
    ]
    assert pipeline._split_story(story, raw) is True
    assert len(story.tasks) == 2
    assert story.split_depth == 1
    assert all(t.split_depth == 1 for t in story.tasks)
    assert story.status == StoryStatus.TODO
    # the intra-split dep was remapped to the new unique id
    assert story.tasks[1].depends_on == [story.tasks[0].id]


def test_split_task_rewires_dependents(streams_on):
    state = _streams_state([
        _us("US-1", tasks=[
            _task("T-1", "US-1", stream="backend"),
            _task("T-2", "US-1", stream="backend", deps=["T-1"]),
        ])
    ])
    pipeline = Pipeline(state, ScriptedRunner())
    raw = [
        {"id": "a", "title": "A", "file_globs": ["a.py"]},
        {"id": "b", "title": "B", "file_globs": ["b.py"], "depends_on": ["a"]},
    ]
    assert pipeline._split_task("T-1", raw) is True
    story = state.story("US-1")
    ids = [t.id for t in story.tasks]
    assert "T-1" not in ids                       # the failed task was replaced
    new_ids = [i for i in ids if i != "T-2"]
    assert len(new_ids) == 2
    # T-2 (depended on T-1) now waits for ALL the new sub-tasks, not the gone id.
    t2 = state.task("T-2")
    assert "T-1" not in t2.depends_on
    assert set(new_ids).issubset(set(t2.depends_on))


# --------------------------------------------------------------- build integration

async def test_auto_split_on_failure_then_subtasks_build_green(streams_on, monkeypatch):
    """A taskless backend US whose dev can't go green is auto-split into finer
    sub-tasks (scripted reply), which then build green → the US ships."""
    monkeypatch.setattr(settings, "dev_max_attempts", 1)
    state = _streams_state([_us("US-1", stream="backend")])
    pipeline = Pipeline(state, ScriptedRunner())

    async def _spy(subject, worktree, pkg, is_frontend):
        # The original (too-big) unit stays red; its finer sub-tasks succeed.
        return ("-S" in subject.id), ("" if "-S" in subject.id else "red")

    monkeypatch.setattr(pipeline, "_arun_item_dev", _spy)
    await asyncio.wait_for(pipeline._abuild_phase(), timeout=40)

    story = state.story("US-1")
    assert story.tasks, "US-1 should have been split into finer sub-tasks"
    assert story.split_depth == 1
    assert all(t.status == StoryStatus.DONE for t in story.tasks)
    assert story.effective_status() == StoryStatus.DONE


async def test_no_split_when_max_depth_zero_keeps_failed(streams_on, monkeypatch):
    monkeypatch.setattr(settings, "dev_max_attempts", 1)
    monkeypatch.setattr(settings, "split_max_depth", 0)  # splitting disabled by bound
    state = _streams_state([_us("US-1", stream="backend")])
    pipeline = Pipeline(state, ScriptedRunner())

    async def _spy(subject, worktree, pkg, is_frontend):
        return False, "red"

    monkeypatch.setattr(pipeline, "_arun_item_dev", _spy)
    await asyncio.wait_for(pipeline._abuild_phase(), timeout=40)

    story = state.story("US-1")
    assert story.tasks == []                       # never split
    assert story.status == StoryStatus.FAILED


async def test_manual_split_rejects_non_failed(streams_on):
    state = _streams_state([_us("US-1", stream="backend", status=StoryStatus.DONE)])
    state.phase = state.phase.__class__.DONE
    pipeline = Pipeline(state, ScriptedRunner())
    with pytest.raises(ValueError):
        await pipeline.asplit_item("US-1")
