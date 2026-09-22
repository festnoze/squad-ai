"""P1-B (GENERATION_FUSION_REVIEW): a merging worker does not hold a dev slot.

``MERGE_WAIT`` / ``MERGING`` - and the post-merge canary that runs right after
the merge - are serialized by ``_merge_lock``: a worker parked there is queueing,
not generating code. It used to keep a ``max_parallel_devs`` slot busy anyway,
so a single slow merge stalled the whole build.

``SLOT_RELEASE_ON_MERGE`` (``settings.slot_release_on_merge``) makes the fill
counter count only the workers whose item is in a dev/verify stage, under a HARD
ceiling of ``max_parallel_devs + 1`` workers in flight. The independence floor
is untouched: it still sees EVERY in-flight worker, because a merging item still
touches files.

WF-P7 (usage-window re-probe) is covered at the bottom: the resume timer now
goes through ``session_monitor.await_window`` and says so in the chat when the
window turns out to reopen earlier than planned.
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
from autospec.orchestrator import session_monitor
from autospec.orchestrator.pipeline import Pipeline

from .conftest import wait_until

_GHERKIN = "Feature: F\n  Scenario: S\n    Given a\n    When b\n    Then c"


def _state(tasks):
    st = ProjectState(id="slot-proj", name="slotapp", goal="g")
    st.epics.append(Epic(id="EPIC-1", title="E"))
    st.streams = [
        Stream(id="backend", kind=StreamKind.BACKEND, language="python", primary=True)
    ]
    st.stories = [
        UserStory(
            id="US-1", epic_id="EPIC-1", title="US-1", stream="backend",
            gherkin=_GHERKIN, tasks=tasks,
        )
    ]
    return st


def _task(tid, *, files=None):
    return Task(
        id=tid, story_id="US-1", stream="backend", title=tid, gherkin=_GHERKIN,
        files_hint=list(files or []),
    )


@pytest.fixture
def streams_on(monkeypatch):
    """Stream build path, scripted agents, ONE dev slot - so any second worker
    in flight can only come from the slot released by a merging item."""
    monkeypatch.setattr(settings, "streams_enabled", True)
    monkeypatch.setattr(settings, "fake_agents", True)
    monkeypatch.setattr(settings, "max_parallel_devs", 1)


def _park_in_merge(pipeline, monkeypatch, *, park_ids, gate, hold=None):
    """Stub the worker: every item in ``park_ids`` stamps MERGE_WAIT (as the real
    ``_abuild_work_item`` does once its branch is green) and then blocks on
    ``gate``; every other item blocks on ``hold`` in a dev stage when one is
    given, else completes at once. Returns the start log."""
    started: list[str] = []

    async def _fake_build(item):
        started.append(item.id)
        target = pipeline._item_target(item)
        if item.id in park_ids:
            pipeline._set_stage(target, BuildStage.MERGE_WAIT, "")
            await gate.wait()
        elif hold is not None:
            await hold.wait()
        target.status = StoryStatus.DONE
        pipeline._set_stage(target, BuildStage.DONE, sync=False)

    monkeypatch.setattr(pipeline, "_abuild_work_item", _fake_build)
    return started


async def _settle(n: int = 12) -> None:
    """Let the scheduler run every pass it wants to, without asserting on a
    delay: a fixed number of event-loop turns is enough for it to refill a slot
    (all the workers here are pure coroutines, nothing really sleeps)."""
    for _ in range(n):
        await asyncio.sleep(0.005)


# ------------------------------------------------ (a) the slot is really freed


async def test_a_merging_item_lets_an_independent_item_start(streams_on, monkeypatch):
    gate = asyncio.Event()
    hold = asyncio.Event()
    state = _state([_task("T-A"), _task("T-B"), _task("T-C")])
    pipeline = Pipeline(state, ScriptedRunner())
    started = _park_in_merge(
        pipeline, monkeypatch, park_ids={"T-A"}, gate=gate, hold=hold
    )

    build = asyncio.create_task(pipeline._abuild_phase())
    try:
        # T-A parks in MERGE_WAIT: its dev slot is free although its worker is
        # still in flight, so T-B starts with cap == 1.
        await wait_until(lambda: len(started) >= 2, timeout=20.0)
        await _settle()
        assert started == ["T-A", "T-B"]  # and T-C waits: cap + 1 in flight
    finally:
        gate.set()
        hold.set()
        await asyncio.wait_for(build, timeout=60)

    assert sorted(started) == ["T-A", "T-B", "T-C"]
    assert all(state.task(t).status == StoryStatus.DONE for t in ("T-A", "T-B", "T-C"))


async def test_the_flag_off_keeps_the_slot_busy_during_the_merge(streams_on, monkeypatch):
    monkeypatch.setattr(settings, "slot_release_on_merge", False)
    gate = asyncio.Event()
    state = _state([_task("T-A"), _task("T-B"), _task("T-C")])
    pipeline = Pipeline(state, ScriptedRunner())
    started = _park_in_merge(pipeline, monkeypatch, park_ids={"T-A"}, gate=gate)

    build = asyncio.create_task(pipeline._abuild_phase())
    try:
        await wait_until(lambda: started == ["T-A"], timeout=20.0)
        await _settle()
        assert started == ["T-A"]  # historic behaviour: the merge holds the slot
    finally:
        gate.set()
        await asyncio.wait_for(build, timeout=60)

    assert sorted(started) == ["T-A", "T-B", "T-C"]


async def test_never_more_than_cap_plus_one_workers_in_flight(streams_on, monkeypatch):
    """Two items parked in the merge queue free two dev slots, but the HARD
    ceiling of cap + 1 workers in flight forbids a third worker."""
    gate = asyncio.Event()
    state = _state([_task("T-A"), _task("T-B"), _task("T-C"), _task("T-D")])
    pipeline = Pipeline(state, ScriptedRunner())
    started = _park_in_merge(
        pipeline, monkeypatch, park_ids={"T-A", "T-B"}, gate=gate
    )

    build = asyncio.create_task(pipeline._abuild_phase())
    try:
        # Wait for BOTH to be parked: the second parking re-arms the scheduler,
        # so the pass that could have launched a third worker has run for sure.
        await wait_until(
            lambda: all(
                state.task(t).current_stage == BuildStage.MERGE_WAIT
                for t in ("T-A", "T-B")
            ),
            timeout=20.0,
        )
        await _settle()
        assert started == ["T-A", "T-B"]
    finally:
        gate.set()
        await asyncio.wait_for(build, timeout=60)

    assert sorted(started) == ["T-A", "T-B", "T-C", "T-D"]


async def test_a_bigger_cap_still_caps_the_dev_workers(streams_on, monkeypatch):
    """cap = 2: T-A parks in the merge queue, so T-B and T-C may both be dev
    workers - but that is already cap + 1 in flight, so T-D waits."""
    monkeypatch.setattr(settings, "max_parallel_devs", 2)
    gate = asyncio.Event()
    hold = asyncio.Event()
    state = _state([_task("T-A"), _task("T-B"), _task("T-C"), _task("T-D")])
    pipeline = Pipeline(state, ScriptedRunner())
    started = _park_in_merge(
        pipeline, monkeypatch, park_ids={"T-A"}, gate=gate, hold=hold
    )

    build = asyncio.create_task(pipeline._abuild_phase())
    try:
        await wait_until(lambda: len(started) >= 3, timeout=20.0)
        await _settle()
        assert started == ["T-A", "T-B", "T-C"]
    finally:
        gate.set()
        hold.set()
        await asyncio.wait_for(build, timeout=60)

    assert sorted(started) == ["T-A", "T-B", "T-C", "T-D"]


async def test_the_independence_floor_still_sees_the_merging_worker(streams_on, monkeypatch):
    """A merging item still holds files: an item whose DECLARED globs overlap it
    must stay blocked even though the dev slot is free. A disjoint item starts."""
    gate = asyncio.Event()
    hold = asyncio.Event()
    state = _state([
        _task("T-A", files=["src/app.py"]),
        _task("T-RIVAL", files=["src/app.py"]),
        _task("T-FREE", files=["src/other.py"]),
    ])
    pipeline = Pipeline(state, ScriptedRunner())
    started = _park_in_merge(
        pipeline, monkeypatch, park_ids={"T-A"}, gate=gate, hold=hold
    )

    build = asyncio.create_task(pipeline._abuild_phase())
    try:
        await wait_until(lambda: len(started) >= 2, timeout=20.0)
        await _settle()
        # T-RIVAL is declared BEFORE T-FREE: only the file overlap with the
        # merging T-A can explain it being skipped.
        assert started == ["T-A", "T-FREE"]
    finally:
        gate.set()
        hold.set()
        await asyncio.wait_for(build, timeout=60)

    assert sorted(started) == ["T-A", "T-FREE", "T-RIVAL"]


async def test_two_dev_workers_never_co_run_at_cap_one(streams_on, monkeypatch):
    """Nothing parks in the merge queue: the historic cap still holds with the
    flag ON (the release only ever applies to merge/terminal stages)."""
    gate = asyncio.Event()
    state = _state([_task("T-A"), _task("T-B")])
    pipeline = Pipeline(state, ScriptedRunner())
    started: list[str] = []

    async def _fake_build(item):
        started.append(item.id)
        await gate.wait()  # stays IMPLEMENTING-ish: never leaves the dev stages
        target = pipeline._item_target(item)
        target.status = StoryStatus.DONE
        pipeline._set_stage(target, BuildStage.DONE, sync=False)

    monkeypatch.setattr(pipeline, "_abuild_work_item", _fake_build)

    build = asyncio.create_task(pipeline._abuild_phase())
    try:
        await wait_until(lambda: started == ["T-A"], timeout=20.0)
        await _settle()
        assert started == ["T-A"]
    finally:
        gate.set()
        await asyncio.wait_for(build, timeout=60)

    assert sorted(started) == ["T-A", "T-B"]


# -------------------------------------------------- (b) the accounting helper


@pytest.mark.parametrize(
    "stage,holds",
    [
        (BuildStage.QUEUED, True),
        (BuildStage.ANALYZING, True),
        (BuildStage.CONTRACTS, True),
        (BuildStage.IMPLEMENTING, True),
        (BuildStage.VERIFYING, True),
        (BuildStage.MERGE_WAIT, False),
        (BuildStage.MERGING, False),
        (BuildStage.DONE, False),
        (BuildStage.FAILED, False),
    ],
)
def test_holds_dev_slot_maps_every_stage(stage, holds):
    state = _state([_task("T-A")])
    pipeline = Pipeline(state, ScriptedRunner())
    state.task("T-A").current_stage = stage
    assert pipeline._holds_dev_slot("T-A") is holds


def test_an_unknown_item_is_counted_as_holding_a_slot():
    """Fail CLOSED: an id that no longer resolves must never over-commit."""
    state = _state([_task("T-A")])
    pipeline = Pipeline(state, ScriptedRunner())
    assert pipeline._holds_dev_slot("T-GONE") is True


def test_entering_the_merge_queue_wakes_the_scheduler():
    state = _state([_task("T-A")])
    pipeline = Pipeline(state, ScriptedRunner())
    pipeline._slot_released.clear()
    pipeline._set_stage(state.task("T-A"), BuildStage.IMPLEMENTING, "dev", sync=False)
    assert not pipeline._slot_released.is_set()
    pipeline._set_stage(state.task("T-A"), BuildStage.MERGE_WAIT, "", sync=False)
    assert pipeline._slot_released.is_set()


# ------------------------------------------------- (c) WF-P7 resume re-probing


def _resume_pipeline(monkeypatch):
    state = ProjectState(id="reprobe-proj", name="app", goal="g")
    pipeline = Pipeline(state, ScriptedRunner())

    resumed: list[bool] = []

    async def _aresume_build():
        resumed.append(True)

    monkeypatch.setattr(pipeline, "aresume_build", _aresume_build)
    return pipeline, state, resumed


async def test_an_earlier_window_shortens_the_wait_and_is_announced(monkeypatch):
    monkeypatch.setattr(settings, "resume_reprobe_min", 30)
    monkeypatch.setattr(session_monitor, "monitor_active", lambda: True)
    pipeline, state, resumed = _resume_pipeline(monkeypatch)
    state.resume_at = 5_000.0
    seen: list[float] = []

    async def _await_window(at, *, reprobe_s):
        seen.append(reprobe_s)
        return at - 1_200.0  # the block reopened 20 minutes earlier

    monkeypatch.setattr(session_monitor, "await_window", _await_window)

    await asyncio.wait_for(pipeline._aresume_timer(5_000.0), timeout=20)

    assert seen == [1800.0]  # minutes converted to seconds
    assert resumed == [True]
    assert any("rouverte plus tôt que prévu" in m.content for m in state.chat)
    assert any("Nouvelle fenêtre d'usage disponible" in m.content for m in state.chat)
    assert state.resume_at == 0.0  # cleared once the resume actually fires


async def test_an_unchanged_window_says_nothing_extra(monkeypatch):
    monkeypatch.setattr(settings, "resume_reprobe_min", 30)
    monkeypatch.setattr(session_monitor, "monitor_active", lambda: True)
    pipeline, state, resumed = _resume_pipeline(monkeypatch)

    async def _await_window(at, *, reprobe_s):
        return at

    monkeypatch.setattr(session_monitor, "await_window", _await_window)

    await asyncio.wait_for(pipeline._aresume_timer(5_000.0), timeout=20)

    assert resumed == [True]
    assert not any("rouverte plus tôt que prévu" in m.content for m in state.chat)


async def test_the_reprobe_is_disabled_when_the_watchdog_is_inactive(monkeypatch):
    """No ccusage subprocess may be spawned from a context where the M2 watchdog
    is off (tests, non-claude providers): the helper gets reprobe_s == 0."""
    monkeypatch.setattr(settings, "resume_reprobe_min", 30)
    monkeypatch.setattr(session_monitor, "monitor_active", lambda: False)
    pipeline, _state, resumed = _resume_pipeline(monkeypatch)
    seen: list[float] = []

    async def _await_window(at, *, reprobe_s):
        seen.append(reprobe_s)
        return at

    monkeypatch.setattr(session_monitor, "await_window", _await_window)

    await asyncio.wait_for(pipeline._aresume_timer(0.0), timeout=20)

    assert seen == [0.0]
    assert resumed == [True]


async def test_zero_minutes_keeps_the_single_sleep(monkeypatch):
    monkeypatch.setattr(settings, "resume_reprobe_min", 0)
    monkeypatch.setattr(session_monitor, "monitor_active", lambda: True)
    pipeline, _state, resumed = _resume_pipeline(monkeypatch)
    seen: list[float] = []

    async def _await_window(at, *, reprobe_s):
        seen.append(reprobe_s)
        return at

    monkeypatch.setattr(session_monitor, "await_window", _await_window)

    await asyncio.wait_for(pipeline._aresume_timer(0.0), timeout=20)

    assert seen == [0.0]
    assert resumed == [True]


async def test_the_real_helper_returns_at_once_on_a_past_target(monkeypatch):
    """End to end through the REAL await_window: an elapsed target neither
    sleeps nor probes, so the existing M2 test keeps its semantics."""
    monkeypatch.setattr(settings, "resume_reprobe_min", 30)
    monkeypatch.setattr(session_monitor, "monitor_active", lambda: True)
    probed: list[bool] = []

    async def _aget_block_reset():
        probed.append(True)
        return None

    monkeypatch.setattr(session_monitor, "aget_block_reset", _aget_block_reset)
    pipeline, _state, resumed = _resume_pipeline(monkeypatch)

    await asyncio.wait_for(pipeline._aresume_timer(0.0), timeout=20)

    assert probed == []
    assert resumed == [True]
