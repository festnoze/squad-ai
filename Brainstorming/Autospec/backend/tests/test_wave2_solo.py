"""P2-A (GENERATION_FUSION_REVIEW): a SOLO rebuild is the last resort before the
adaptive split, on a PERSISTENT merge conflict.

An item whose own branch is green but whose merge keeps colliding with the
siblings landing beside it used to be split or FAILED once ``requeue_max`` was
spent - working code thrown away for a scheduling problem. With
``SOLO_ON_CONFLICT`` (``settings.solo_on_conflict``) it is granted ONE extra try
in SOLO mode instead: re-queued without consuming any budget, started only when
NO other worker is in flight, and while it runs nothing else starts. Rebased on
the FINAL HEAD with no rival, it cannot conflict any more.

The grant is recorded on the item (``solo_attempted``), so a solo try that fails
again falls straight through to the historic ending (split, then FAILED) - no
loop is possible.
"""

import asyncio

import pytest

from autospec.agents.scripted import ScriptedRunner
from autospec.config import settings
from autospec.models import (
    BuildStage,
    Epic,
    ProjectState,
    StoryStatus,
    Stream,
    StreamKind,
    Task,
    UserStory,
)
from autospec.orchestrator.pipeline import Pipeline

from .conftest import wait_until

_GHERKIN = "Feature: F\n  Scenario: S\n    Given a\n    When b\n    Then c"


def _task(tid, *, files=None, depends_on=None):
    return Task(
        id=tid, story_id="US-1", stream="backend", title=tid, gherkin=_GHERKIN,
        files_hint=list(files or []), depends_on=list(depends_on or []),
    )


def _state(project_id: str, tasks=None) -> ProjectState:
    st = ProjectState(id=project_id, name="soloapp", goal="g")
    st.epics.append(Epic(id="EPIC-1", title="E"))
    st.streams = [
        Stream(id="backend", kind=StreamKind.BACKEND, language="python", primary=True)
    ]
    st.stories = [
        UserStory(
            id="US-1", epic_id="EPIC-1", title="US-1", stream="backend",
            gherkin=_GHERKIN, tasks=list(tasks or []),
        )
    ]
    return st


@pytest.fixture
def streams_on(monkeypatch):
    """Stream build path with scripted agents. ``solo_on_conflict`` is pinned OFF
    by the conftest (it would change the historic conflict counts of the wave-1
    tests), so every test here opts in or out explicitly."""
    monkeypatch.setattr(settings, "streams_enabled", True)
    monkeypatch.setattr(settings, "fake_agents", True)


def _trace_workers(pipeline, monkeypatch):
    """Wrap the REAL ``_abuild_work_item`` so the test can see which workers are
    in flight together. Returns (starts, solo_snapshots, rivals_during_solo):

    * ``starts`` - every worker launch, in order;
    * ``solo_snapshots`` - the set of workers already in flight when a SOLO
      rebuild started (must always be empty: it owns the HEAD alone);
    * ``rivals_during_solo`` - any worker launched WHILE a solo rebuild was
      running (must always be empty).
    """
    original = pipeline._abuild_work_item
    inflight: set[str] = set()
    solo_inflight: set[str] = set()
    starts: list[str] = []
    solo_snapshots: list[set[str]] = []
    rivals: list[str] = []

    async def _traced(item):
        # `solo_attempted` is stamped by the scheduler just before the launch,
        # so it is already True on the solo pass and still False before it.
        is_solo = bool(getattr(pipeline._item_target(item), "solo_attempted", False))
        starts.append(item.id)
        if is_solo:
            solo_snapshots.append(set(inflight))
            solo_inflight.add(item.id)
        elif solo_inflight:
            rivals.append(item.id)
        inflight.add(item.id)
        try:
            return await original(item)
        finally:
            inflight.discard(item.id)
            solo_inflight.discard(item.id)

    monkeypatch.setattr(pipeline, "_abuild_work_item", _traced)
    return starts, solo_snapshots, rivals


# --------------------------------------------------- (a) conflict -> solo -> DONE


async def test_a_a_persistent_conflict_is_rebuilt_solo_instead_of_failing(
    streams_on, monkeypatch
):
    """``requeue_max`` = 1, so T-A's merge conflicts 1 + 1 times and the historic
    code ended it FAILED. It now gets ONE solo rebuild on the final HEAD, where
    the mocked merge lands - and it is DONE."""
    monkeypatch.setattr(settings, "solo_on_conflict", True)
    monkeypatch.setattr(settings, "requeue_max", 1)
    state = _state("solo-conflict", [_task("T-A", files=["a.py"]),
                                     _task("T-B", files=["b.py"])])
    pipeline = Pipeline(state, ScriptedRunner())
    starts, solo_snapshots, rivals = _trace_workers(pipeline, monkeypatch)
    merges: list[str] = []
    devs: list[str] = []

    async def _dev(subject, worktree, pkg, is_frontend):
        devs.append(subject.id)
        return True, ""

    async def _verify(subject, worktree, is_frontend):
        subject.status = StoryStatus.GREEN
        return True, ""

    async def _merge(repo, branch, wid, worktree=None):
        merges.append(wid)
        if wid != "T-A":
            return True, []
        return merges.count("T-A") > 2, ["a.py"]

    monkeypatch.setattr(pipeline, "_arun_item_dev", _dev)
    monkeypatch.setattr(pipeline, "_averify_resumed", _verify)
    monkeypatch.setattr(pipeline, "_amerge_work_item", _merge)
    await asyncio.wait_for(pipeline._abuild_phase(), timeout=60)

    task_a = state.task("T-A")
    assert task_a.status == StoryStatus.DONE        # never FAILED on a fusion clash
    assert state.task("T-B").status == StoryStatus.DONE
    assert merges.count("T-A") == 3                 # 2 conflicts, then the solo merge
    assert task_a.solo_attempted is True            # the one grant was spent
    assert task_a.requeue_attempts == 2             # budget exhausted BEFORE the solo
    assert devs.count("T-A") == 1                   # the solo pass ran NO dev at all
    calib = state.calibration_for()
    assert calib.solo_requeues == 1
    # P2b: what the solo pass merges is the PRESERVED green branch, rebased and
    # re-verified with no re-generation (p2b_resumes counts merges without a dev
    # run, so only the landing solo pass shows up here).
    assert calib.p2b_resumes == 1
    assert calib.merge_requeues == 2
    # The solo rebuild really owned the HEAD: nothing in flight when it started,
    # nothing launched while it ran.
    assert solo_snapshots == [set()]
    assert rivals == []
    assert starts.count("T-A") == 3


# ------------------------------------------------------------ (b) the flag is OFF


async def test_b_the_flag_off_fails_the_item_as_before(streams_on, monkeypatch):
    """``SOLO_ON_CONFLICT=0`` restores the historic ending: the exhausted requeue
    budget goes straight to the split (pinned OFF by the conftest), then FAILED -
    with NO extra merge attempt."""
    monkeypatch.setattr(settings, "solo_on_conflict", False)
    monkeypatch.setattr(settings, "requeue_max", 1)
    state = _state("solo-flag-off", [_task("T-A", files=["a.py"])])
    pipeline = Pipeline(state, ScriptedRunner())
    merges: list[str] = []

    async def _dev(subject, worktree, pkg, is_frontend):
        return True, ""

    async def _verify(subject, worktree, is_frontend):
        subject.status = StoryStatus.GREEN
        return True, ""

    async def _merge(repo, branch, wid, worktree=None):
        merges.append(wid)
        return False, ["a.py"]

    monkeypatch.setattr(pipeline, "_arun_item_dev", _dev)
    monkeypatch.setattr(pipeline, "_averify_resumed", _verify)
    monkeypatch.setattr(pipeline, "_amerge_work_item", _merge)
    await asyncio.wait_for(pipeline._abuild_phase(), timeout=60)

    task_a = state.task("T-A")
    assert task_a.status == StoryStatus.FAILED
    assert len(merges) == 2                 # one requeue, then the terminal pass
    assert task_a.solo_attempted is False
    assert state.calibration_for().solo_requeues == 0


# ------------------------------------------- (c) the grant is spent only once


async def test_c_a_solo_that_conflicts_again_fails_without_looping(
    streams_on, monkeypatch
):
    """A merge that conflicts forever: the solo rebuild is granted ONCE and the
    item then ends FAILED on the historic path. Exactly one extra merge attempt
    compared to the flag-off run - no loop."""
    monkeypatch.setattr(settings, "solo_on_conflict", True)
    monkeypatch.setattr(settings, "requeue_max", 1)
    state = _state("solo-once", [_task("T-A", files=["a.py"])])
    pipeline = Pipeline(state, ScriptedRunner())
    merges: list[str] = []

    async def _dev(subject, worktree, pkg, is_frontend):
        return True, ""

    async def _verify(subject, worktree, is_frontend):
        subject.status = StoryStatus.GREEN
        return True, ""

    async def _merge(repo, branch, wid, worktree=None):
        merges.append(wid)
        return False, ["a.py"]

    monkeypatch.setattr(pipeline, "_arun_item_dev", _dev)
    monkeypatch.setattr(pipeline, "_averify_resumed", _verify)
    monkeypatch.setattr(pipeline, "_amerge_work_item", _merge)
    await asyncio.wait_for(pipeline._abuild_phase(), timeout=60)

    task_a = state.task("T-A")
    assert task_a.status == StoryStatus.FAILED
    assert len(merges) == 3                 # requeue, solo, then FAILED
    assert task_a.solo_attempted is True
    assert state.calibration_for().solo_requeues == 1
    assert pipeline._solo_ids == set()      # no pending solo left behind


# ------------------------------------------------------ (d) the scheduler gate


async def test_d_the_scheduler_holds_a_solo_item_until_everything_has_landed(
    streams_on, monkeypatch
):
    """The scheduling contract, both directions, with stubbed workers:

    * a solo item does NOT start while ANY worker is in flight, even with a free
      dev slot;
    * once it runs, NO other ready item starts beside it.
    """
    monkeypatch.setattr(settings, "solo_on_conflict", True)
    monkeypatch.setattr(settings, "max_parallel_devs", 3)
    # Declaration order is the topological order: the solo item is picked AFTER
    # the two workers that must hold it back, so a free slot is really available.
    state = _state("solo-gate", [
        _task("T-B", files=["b.py"]),
        _task("T-C", files=["c.py"]),
        _task("T-A", files=["a.py"]),
        _task("T-D", files=["d.py"]),
    ])
    pipeline = Pipeline(state, ScriptedRunner())
    pipeline._solo_ids.add("T-A")           # as _mark_solo_retry would have done
    started: list[str] = []
    gates = {tid: asyncio.Event() for tid in ("T-A", "T-B", "T-C", "T-D")}

    async def _fake_build(item):
        started.append(item.id)
        await gates[item.id].wait()
        target = pipeline._item_target(item)
        target.status = StoryStatus.DONE
        pipeline._set_stage(target, BuildStage.DONE, sync=False)

    monkeypatch.setattr(pipeline, "_abuild_work_item", _fake_build)

    build = asyncio.create_task(pipeline._abuild_phase())
    try:
        # Three slots, four ready items: T-B, T-C and T-D take them while T-A is
        # HELD - the fill skips the solo item alone, so the last slot goes to the
        # NEXT ready item instead. The hold is not a missing slot, it is the rule.
        await wait_until(lambda: len(started) >= 3, timeout=20.0)
        assert "T-A" not in started
        assert set(started) == {"T-B", "T-C", "T-D"}

        # Everything lands: only then may the solo rebuild start, alone.
        for tid in ("T-B", "T-C", "T-D"):
            gates[tid].set()
        await wait_until(lambda: "T-A" in started, timeout=20.0)
        assert started[-1] == "T-A"
        assert len(started) == 4
    finally:
        for gate in gates.values():
            gate.set()
        await asyncio.wait_for(build, timeout=30)

    assert state.task("T-A").solo_attempted is True
    assert pipeline._solo_ids == set()
    assert pipeline._solo_running == set()


async def test_e_nothing_starts_beside_a_running_solo_item(streams_on, monkeypatch):
    """The solo item is picked FIRST (nothing in flight), and the three other
    ready items stay queued for as long as it runs, although two slots are free."""
    monkeypatch.setattr(settings, "solo_on_conflict", True)
    monkeypatch.setattr(settings, "max_parallel_devs", 3)
    state = _state("solo-exclusive", [
        _task("T-A", files=["a.py"]),
        _task("T-B", files=["b.py"]),
        _task("T-C", files=["c.py"]),
    ])
    pipeline = Pipeline(state, ScriptedRunner())
    pipeline._solo_ids.add("T-A")
    started: list[str] = []
    gate = asyncio.Event()

    async def _fake_build(item):
        started.append(item.id)
        if item.id == "T-A":
            await gate.wait()
        target = pipeline._item_target(item)
        target.status = StoryStatus.DONE

    monkeypatch.setattr(pipeline, "_abuild_work_item", _fake_build)

    build = asyncio.create_task(pipeline._abuild_phase())
    try:
        await wait_until(lambda: started == ["T-A"], timeout=20.0)
        # Let the scheduler run every pass it wants to: with two free slots and
        # two ready items, ONLY the solo hold can keep them out.
        for _ in range(20):
            await asyncio.sleep(0.005)
        assert started == ["T-A"]
        gate.set()
        await wait_until(lambda: len(started) == 3, timeout=20.0)
    finally:
        gate.set()
        await asyncio.wait_for(build, timeout=30)

    assert started[0] == "T-A"
    assert set(started) == {"T-A", "T-B", "T-C"}
