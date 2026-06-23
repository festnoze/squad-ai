"""Lot 4 (ST-9/ST-10/ST-11): the parallel, stream-aware build path that runs
each work item in its own git worktree and merges it back into the project repo.

These tests turn ``streams_enabled`` ON (the conftest pins it OFF) and use
``fake_agents`` so the dev / pytest / vitest steps short-circuit green — but the
git worktree + merge operations run for real against a temp project repo.
"""

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
from autospec.orchestrator import streams as work_streams
from autospec.orchestrator.pipeline import Pipeline
from autospec.storage import workspace_dir


def _streams_state(stories, project_id="wt-proj"):
    st = ProjectState(id=project_id, name="wtapp", goal="g")
    st.epics.append(Epic(id="EPIC-1", title="E"))
    st.streams = [
        Stream(id="backend", kind=StreamKind.BACKEND, language="python", primary=True),
        Stream(id="frontend", kind=StreamKind.FRONTEND, language="react", file_root="frontend"),
    ]
    st.stories = stories
    return st


def _us(sid, *, stream="", tasks=None, depends_on=None, gherkin="Feature: F\n  Scenario: S\n    Given a\n    When b\n    Then c"):
    return UserStory(
        id=sid, epic_id="EPIC-1", title=sid, gherkin=gherkin,
        stream=stream, tasks=tasks or [], depends_on=depends_on or [],
    )


def _task(tid, story_id, *, stream="", depends_on=None, gherkin="Feature: F\n  Scenario: S\n    Given a\n    When b\n    Then c"):
    return Task(
        id=tid, story_id=story_id, stream=stream, title=tid,
        gherkin=gherkin, depends_on=depends_on or [],
    )


@pytest.fixture
def streams_on(monkeypatch):
    monkeypatch.setattr(settings, "streams_enabled", True)
    monkeypatch.setattr(settings, "fake_agents", True)


# --------------------------------------------------------------- (a) parallel

async def test_independent_cross_stream_items_build_in_parallel_and_reach_done(streams_on):
    # A backend taskless US and an independent frontend task (under another US):
    # no dependency between them, so both build in parallel and reach DONE/merged.
    back = _us("US-1", stream="backend")
    front_task = _task("T-front", "US-2", stream="frontend")
    front_us = _us("US-2", stream="frontend", tasks=[front_task])
    state = _streams_state([back, front_us])
    pipeline = Pipeline(state, ScriptedRunner())

    await pipeline._abuild_phase()

    assert state.story("US-1").status == StoryStatus.DONE
    assert state.task("T-front").status == StoryStatus.DONE
    # The US-2 container is DONE via its tasks (effective status).
    assert state.story("US-2").effective_status() == StoryStatus.DONE


async def test_parallel_items_actually_overlap(streams_on, monkeypatch):
    # Two independent backend items must build TRULY in parallel (each in its own
    # worktree, no shared build lock). Deterministic proof via a 2-party barrier:
    # each item's dev work waits for the OTHER to also be in its dev work. If the
    # path were serialized, the first item would block forever and the gather
    # would time out — so reaching the assertions at all proves overlap.
    state = _streams_state([_us("US-1", stream="backend"), _us("US-2", stream="backend")])
    monkeypatch.setattr(settings, "max_parallel_devs", 2)
    pipeline = Pipeline(state, ScriptedRunner())

    both_in_dev = asyncio.Event()
    arrived = 0
    orig = pipeline._arun_item_dev

    async def _spy(subject, worktree, pkg, is_frontend):
        nonlocal arrived
        arrived += 1
        if arrived >= 2:
            both_in_dev.set()
        # Block until BOTH items have entered their dev work — only possible if
        # they run concurrently (semaphore=2, no serializing build lock).
        await asyncio.wait_for(both_in_dev.wait(), timeout=10.0)
        return await orig(subject, worktree, pkg, is_frontend)

    monkeypatch.setattr(pipeline, "_arun_item_dev", _spy)
    await pipeline._abuild_phase()

    assert both_in_dev.is_set()  # both reached dev concurrently
    assert state.story("US-1").status == StoryStatus.DONE
    assert state.story("US-2").status == StoryStatus.DONE


# ----------------------------------------------- (b) cross-stream dep ordering

async def test_frontend_task_starts_only_after_backend_dep_is_merged(streams_on, monkeypatch):
    # US-1 has a backend task and a frontend task that depends on it. The front
    # task must NOT start until the back task is DONE (merged into the repo).
    back = _task("T-back", "US-1", stream="backend")
    front = _task("T-front", "US-1", stream="frontend", depends_on=["T-back"])
    state = _streams_state([_us("US-1", tasks=[back, front])])
    pipeline = Pipeline(state, ScriptedRunner())

    start_order = []
    orig = pipeline._arun_item_dev

    async def _spy(subject, worktree, pkg, is_frontend):
        start_order.append(subject.id)
        return await orig(subject, worktree, pkg, is_frontend)

    monkeypatch.setattr(pipeline, "_arun_item_dev", _spy)
    await pipeline._abuild_phase()

    assert start_order == ["T-back", "T-front"]  # strict ordering across batches
    assert state.task("T-back").status == StoryStatus.DONE
    assert state.task("T-front").status == StoryStatus.DONE
    # When the front task started, the back task was already DONE (merged).
    assert start_order.index("T-front") > start_order.index("T-back")


# --------------------------------------------------- (c) merge conflict policy

async def test_merge_conflict_marks_item_failed_and_aborts_cleanly(streams_on, monkeypatch):
    state = _streams_state([_us("US-1", stream="backend")])
    pipeline = Pipeline(state, ScriptedRunner())

    aborts = []
    real_agit = pipeline._agit

    async def _agit(ws, *args):
        if args[:1] == ("merge",) and "--abort" not in args:
            # Simulate a merge conflict on every merge attempt.
            return 1, "CONFLICT (content): merge conflict in app.py"
        if args[:2] == ("merge", "--abort"):
            aborts.append(ws)
            return await real_agit(ws, *args)
        return await real_agit(ws, *args)

    monkeypatch.setattr(pipeline, "_agit", _agit)
    await pipeline._abuild_phase()

    story = state.story("US-1")
    assert story.status == StoryStatus.FAILED
    assert story.last_error == "conflit de merge inter-stream non résolu"
    # Retried once → two failed merges → two aborts (clean abort each time).
    assert len(aborts) == 2


async def test_merge_is_serialized_by_lock(streams_on, monkeypatch):
    # Two independent items merging into the same repo must never merge
    # concurrently — assert the merge critical section never overlaps.
    state = _streams_state([_us("US-1", stream="backend"), _us("US-2", stream="backend")])
    monkeypatch.setattr(settings, "max_parallel_devs", 2)
    pipeline = Pipeline(state, ScriptedRunner())

    # Spy on the real git `merge` invocations (which run INSIDE _merge_lock):
    # they must never overlap, proving the lock serializes the merges even
    # though the two items build in parallel worktrees.
    in_merge = 0
    overlap = False
    real_agit = pipeline._agit

    async def _agit(ws, *args):
        nonlocal in_merge, overlap
        if args[:1] == ("merge",) and "--abort" not in args:
            in_merge += 1
            if in_merge > 1:
                overlap = True
            await asyncio.sleep(0.02)
            try:
                return await real_agit(ws, *args)
            finally:
                in_merge -= 1
        return await real_agit(ws, *args)

    monkeypatch.setattr(pipeline, "_agit", _agit)
    await pipeline._abuild_phase()

    assert overlap is False
    assert state.story("US-1").status == StoryStatus.DONE
    assert state.story("US-2").status == StoryStatus.DONE


# ------------------------------------------------------ (d) flag OFF = legacy

async def test_flag_off_uses_legacy_path(monkeypatch):
    # streams_enabled is OFF (conftest default): _abuild_phase must call the
    # legacy _abuild_story, never the worktree path.
    state = ProjectState(id="legacy-proj", name="x", goal="g")
    state.epics.append(Epic(id="EPIC-1", title="E"))
    state.stories = [_us("US-1")]
    pipeline = Pipeline(state, ScriptedRunner())
    monkeypatch.setattr(settings, "fake_agents", True)

    used_streams = False

    async def _boom(*a, **kw):
        nonlocal used_streams
        used_streams = True

    monkeypatch.setattr(pipeline, "_abuild_phase_streams", _boom)
    await pipeline._abuild_phase()

    assert used_streams is False
    assert state.story("US-1").status == StoryStatus.DONE


async def test_dynamic_scheduler_starts_dependent_before_slow_sibling(streams_on, monkeypatch):
    """Dynamic dataflow: a dependent item starts as soon as its dependency merges,
    WITHOUT waiting for a slow independent sibling to finish — proof there is no
    batch barrier. The old batched gather() would deadlock this exact shape (A
    waits for C, but C couldn't start until A's batch finished)."""
    # One story, three tasks: A (slow, independent), B (fast, independent),
    # C (depends on B). cap = max_parallel_devs = 2 (conftest) → A and B start
    # together; C must slot in the instant B merges, while A is still running.
    state = _streams_state([
        _us("US-1", tasks=[
            _task("T-A", "US-1", stream="backend"),
            _task("T-B", "US-1", stream="backend"),
            _task("T-C", "US-1", stream="backend", depends_on=["T-B"]),
        ])
    ])
    pipeline = Pipeline(state, ScriptedRunner())

    started: list[str] = []
    c_started = asyncio.Event()

    async def _spy(subject, worktree, pkg, is_frontend):
        started.append(subject.id)
        if subject.id == "T-C":
            c_started.set()
        if subject.id == "T-A":
            # The slow sibling blocks until the dependent C has started. Under a
            # batch barrier C can't start while A runs → this would time out.
            await asyncio.wait_for(c_started.wait(), timeout=20)
        return True, ""

    monkeypatch.setattr(pipeline, "_arun_item_dev", _spy)

    await asyncio.wait_for(pipeline._abuild_phase(), timeout=40)

    assert c_started.is_set(), "the dependent item C must have started"
    assert set(started) == {"T-A", "T-B", "T-C"}
    assert all(t.status == StoryStatus.DONE for t in state.story("US-1").tasks)


async def test_worktree_add_recovers_from_stale_leftover(streams_on):
    """An interrupted build (crash/reload) can leave a worktree still checked out
    on the per-item branch. Re-adding that branch (e.g. a manual « Relancer ») must
    succeed by pruning/removing the orphan first, instead of failing with
    « git worktree add a échoué … branch already exists / used by worktree »."""
    state = _streams_state([_us("US-1")], project_id="wt-stale")
    pipeline = Pipeline(state, ScriptedRunner())
    ws = workspace_dir(state.id)
    ws.mkdir(parents=True, exist_ok=True)
    assert await pipeline._agit_ensure_repo(ws)
    # A commit so HEAD exists for `worktree add … HEAD`.
    (ws / "seed.txt").write_text("x", encoding="utf-8")
    await pipeline._agit(ws, "add", "-A")
    await pipeline._agit(ws, "commit", "-m", "seed")

    branch = "autospec/wi-stale"
    first = await pipeline._aworktree_add(ws, branch)
    assert first is not None
    # Simulate the interruption: the worktree + branch are left behind (the
    # cleanup in `finally` never ran). A naive `branch -D` would now fail
    # ("used by worktree"); the next add must still succeed.
    second = await pipeline._aworktree_add(ws, branch)
    assert second is not None, "re-add should recover from the stale worktree"
    assert second != first

    await pipeline._aworktree_remove(ws, second, branch)


async def test_work_item_built_in_a_worktree_not_the_main_workspace(streams_on, monkeypatch):
    # The dev agent for a work item runs with cwd set to a git worktree path,
    # NOT the project workspace dir — proving per-item isolation.
    state = _streams_state([_us("US-1", stream="backend")])
    pipeline = Pipeline(state, ScriptedRunner())
    main_ws = workspace_dir(state.id)

    seen_cwds = []
    orig = pipeline._arun_item_dev

    async def _spy(subject, worktree, pkg, is_frontend):
        seen_cwds.append(worktree)
        return await orig(subject, worktree, pkg, is_frontend)

    monkeypatch.setattr(pipeline, "_arun_item_dev", _spy)
    await pipeline._abuild_phase()

    assert seen_cwds and all(c != main_ws for c in seen_cwds)
    assert state.story("US-1").status == StoryStatus.DONE


# ------------------------------------------------------ (e) BUG10 dep cycle

async def test_dependency_cycle_surfaces_precise_path_in_last_error(streams_on):
    """BUG10: when nothing is ready because two work items depend on each other
    (a CYCLE), the failed items' ``last_error`` names the cycle path instead of
    the generic 'dépendance non satisfaite' upstream-failure message."""
    back = _task("T-back", "US-1", stream="backend", depends_on=["T-front"])
    front = _task("T-front", "US-1", stream="frontend", depends_on=["T-back"])
    state = _streams_state([_us("US-1", tasks=[back, front])])
    pipeline = Pipeline(state, ScriptedRunner())

    await pipeline._abuild_phase()

    # Both cyclic tasks fail with the cycle-specific message (not the generic one).
    for tid in ("T-back", "T-front"):
        task = state.task(tid)
        assert task.status == StoryStatus.FAILED
        assert "Cycle" in task.last_error, task.last_error
        assert "→" in task.last_error
    # The precise path was surfaced to the chat too.
    assert any("Cycle de dépendances détecté" in c.content for c in state.chat)


# ------------------------------------------------ (f) BUG9 frontend task refs

async def test_frontend_stream_tasks_tracked_and_cleared_by_dispose():
    """BUG9: frontend preview streaming tasks are kept in a strong-ref list (so
    asyncio can't GC them mid-run) and that list is cancelled + cleared on
    dispose."""
    state = _streams_state([_us("US-1", stream="backend")])
    pipeline = Pipeline(state, ScriptedRunner())
    # The attribute exists and starts empty.
    assert pipeline._frontend_stream_tasks == []

    async def _never():
        await asyncio.sleep(3600)

    task = asyncio.create_task(_never())
    pipeline._frontend_stream_tasks.append(task)

    await pipeline.adispose()

    assert pipeline._frontend_stream_tasks == []  # cleared
    assert task.cancelled() or task.done()  # cancelled by teardown
