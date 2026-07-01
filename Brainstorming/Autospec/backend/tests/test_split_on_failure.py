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


def test_split_task_extracts_technical_story_when_container_has_others(streams_on):
    # RFC technical-stories: US-1 keeps T-2, so the failed T-1 is EXTRACTED into a
    # named Technical Story (not flattened into US-1's tasks).
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
    # T-1 left US-1; US-1 keeps T-2 only.
    assert [t.id for t in state.story("US-1").tasks] == ["T-2"]
    # A Technical Story was created with the finer sub-tasks.
    ts = next(s for s in state.stories if s.technical)
    assert ts.parent_id == "US-1"
    assert ts.contract  # technical contract carried over
    assert len(ts.tasks) == 2
    # T-2 (depended on T-1) now depends on the TS (resolved to its tasks by the graph).
    t2 = state.task("T-2")
    assert "T-1" not in t2.depends_on
    assert ts.id in t2.depends_on


def test_split_task_in_place_when_only_task(streams_on):
    # The failed task is the container's ONLY one → in-place sibling split, no TS.
    state = _streams_state([_us("US-1", tasks=[_task("T-1", "US-1", stream="backend")])])
    pipeline = Pipeline(state, ScriptedRunner())
    raw = [
        {"id": "a", "title": "A", "file_globs": ["a.py"]},
        {"id": "b", "title": "B", "file_globs": ["b.py"], "depends_on": ["a"]},
    ]
    assert pipeline._split_task("T-1", raw) is True
    assert not any(s.technical for s in state.stories)   # no TS created
    ids = [t.id for t in state.story("US-1").tasks]
    assert "T-1" not in ids and len(ids) == 2


def _ts(sid, parent_id, tasks):
    s = _us(sid, tasks=tasks)
    s.technical = True
    s.parent_id = parent_id
    return s


def test_work_graph_resolves_child_ts_tasks(streams_on):
    from autospec.orchestrator import streams as work_streams

    state = _streams_state([
        _us("US-1", tasks=[_task("T-2", "US-1", stream="backend")]),
        _us("US-2", stream="backend"),
        _ts("TS-x", "US-1", [_task("F1", "TS-x", stream="backend"), _task("F2", "TS-x", stream="backend")]),
    ])
    state.story("US-2").depends_on = ["US-1"]
    graph = work_streams.build_work_graph(state)
    # Depending on US-1 = depending on its task T-2 AND its child TS' tasks F1/F2.
    assert set(graph.items["US-2"].depends_on) >= {"T-2", "F1", "F2"}


def test_recursion_ts_task_splits_into_deeper_ts(streams_on):
    state = _streams_state([
        _us("US-1", tasks=[_task("T-keep", "US-1", stream="backend")]),
        _ts("TS-1", "US-1", [
            _task("F1", "TS-1", stream="backend"),
            _task("F2", "TS-1", stream="backend"),
        ]),
    ])
    pipeline = Pipeline(state, ScriptedRunner())
    raw = [
        {"id": "x", "title": "X", "file_globs": ["x.py"]},
        {"id": "y", "title": "Y", "file_globs": ["y.py"]},
    ]
    assert pipeline._split_task("F1", raw) is True
    assert [t.id for t in state.story("TS-1").tasks] == ["F2"]   # TS-1 keeps F2
    deeper = [s for s in state.stories if s.technical and s.parent_id == "TS-1"]
    assert len(deeper) == 1 and len(deeper[0].tasks) == 2        # nested TS (depth+1)


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
