"""P1-C (GENERATION_FUSION_REVIEW): critical-path scheduling.

Two behaviours, both flag-gated and covered here:

 - ``FANOUT_FIRST`` (``settings.fanout_first_enabled``): among the READY work
   items, the one that transitively BLOCKS the most work is picked first. The
   flag only reorders the picks - readiness, the independence floor and the
   parallelism cap are untouched, and the topological (declaration) order stays
   the tie-break, so the flag OFF replays the historic order exactly.
 - ``FANOUT_BONUS_THRESHOLD`` (``settings.fanout_bonus_threshold``): an item
   blocking at least that many others earns ONE dev attempt more than
   ``DEV_MAX_ATTEMPTS`` before it ends FAILED. 0 disables the bonus.
"""

import asyncio

import pytest

from autospec.agents.scripted import ScriptedRunner
from autospec.config import settings
from autospec.models import (
    Epic,
    ProjectState,
    StoryStatus,
    Stream,
    StreamKind,
    Task,
    UserStory,
)
from autospec.orchestrator.pipeline import Pipeline

_GHERKIN = "Feature: F\n  Scenario: S\n    Given a\n    When b\n    Then c"


def _state(stories, project_id="fanout-proj"):
    st = ProjectState(id=project_id, name="fanoutapp", goal="g")
    st.epics.append(Epic(id="EPIC-1", title="E"))
    st.streams = [
        Stream(id="backend", kind=StreamKind.BACKEND, language="python", primary=True)
    ]
    st.stories = stories
    return st


def _us(sid, *, tasks=None, depends_on=None):
    return UserStory(
        id=sid, epic_id="EPIC-1", title=sid, stream="backend", gherkin=_GHERKIN,
        tasks=tasks or [], depends_on=depends_on or [],
    )


def _task(tid, story_id, *, depends_on=None):
    return Task(
        id=tid, story_id=story_id, stream="backend", title=tid, gherkin=_GHERKIN,
        depends_on=depends_on or [],
    )


@pytest.fixture
def streams_on(monkeypatch):
    """Stream build path, scripted agents, ONE slot at a time so the pick order
    is directly observable in the order the workers start."""
    monkeypatch.setattr(settings, "streams_enabled", True)
    monkeypatch.setattr(settings, "fake_agents", True)
    monkeypatch.setattr(settings, "max_parallel_devs", 1)


def _chain_state():
    """``T-LEAF`` blocks nobody and is DECLARED FIRST (so the historic order
    picks it first); ``T-ROOT`` transitively blocks three items."""
    return _state([
        _us("US-1", tasks=[
            _task("T-LEAF", "US-1"),
            _task("T-ROOT", "US-1"),
            _task("T-C1", "US-1", depends_on=["T-ROOT"]),
            _task("T-C2", "US-1", depends_on=["T-C1"]),
            _task("T-C3", "US-1", depends_on=["T-C2"]),
        ]),
    ])


def _record_build_order(pipeline, monkeypatch) -> list[str]:
    """Replace the worker with a stub that records the item and marks it DONE,
    so the build loop keeps advancing and the list IS the pick order."""
    built: list[str] = []

    async def _fake_build(item):
        built.append(item.id)
        pipeline._item_target(item).status = StoryStatus.DONE

    monkeypatch.setattr(pipeline, "_abuild_work_item", _fake_build)
    return built


# ------------------------------------------------------------- (a) pick order

async def test_the_item_blocking_the_most_work_is_built_first(streams_on, monkeypatch):
    state = _chain_state()
    pipeline = Pipeline(state, ScriptedRunner())
    built = _record_build_order(pipeline, monkeypatch)

    await asyncio.wait_for(pipeline._abuild_phase(), timeout=60)

    # T-ROOT (fan-out 3) is picked before the leaf declared ahead of it, then
    # its chain is drained by decreasing fan-out. T-LEAF only overtakes T-C3
    # once that one is a leaf too (fan-out 0 both): the tie falls back to the
    # declaration order, where T-LEAF comes first.
    assert built == ["T-ROOT", "T-C1", "T-C2", "T-LEAF", "T-C3"]


async def test_the_flag_off_keeps_the_historic_declaration_order(streams_on, monkeypatch):
    monkeypatch.setattr(settings, "fanout_first_enabled", False)
    state = _chain_state()
    pipeline = Pipeline(state, ScriptedRunner())
    built = _record_build_order(pipeline, monkeypatch)

    await asyncio.wait_for(pipeline._abuild_phase(), timeout=60)

    assert built == ["T-LEAF", "T-ROOT", "T-C1", "T-C2", "T-C3"]


async def test_the_pass_memorises_the_fanout_of_the_current_graph(streams_on, monkeypatch):
    state = _chain_state()
    pipeline = Pipeline(state, ScriptedRunner())
    _record_build_order(pipeline, monkeypatch)

    await asyncio.wait_for(pipeline._abuild_phase(), timeout=60)

    assert pipeline._fanout["T-ROOT"] == 3
    assert pipeline._fanout["T-C2"] == 1
    assert pipeline._fanout["T-LEAF"] == 0


async def test_ordering_never_drops_nor_duplicates_a_ready_item(streams_on, monkeypatch):
    """The reordering must never lose work: every item is built exactly once."""
    state = _chain_state()
    pipeline = Pipeline(state, ScriptedRunner())
    built = _record_build_order(pipeline, monkeypatch)

    await asyncio.wait_for(pipeline._abuild_phase(), timeout=60)

    assert sorted(built) == ["T-C1", "T-C2", "T-C3", "T-LEAF", "T-ROOT"]
    assert all(t.status == StoryStatus.DONE for t in state.story("US-1").tasks)


# ---------------------------------------------------------- (b) attempt bonus

def _red_dev(pipeline, monkeypatch) -> list[str]:
    """Always-red dev, and a preserved branch that never revalidates - so each
    attempt really goes through the dev agent."""
    calls: list[str] = []

    async def _dev(subject, worktree, pkg, is_frontend):
        calls.append(subject.id)
        return False, "AssertionError: red"

    async def _still_red(subject, worktree, is_frontend):
        return False, "still red"

    monkeypatch.setattr(pipeline, "_arun_item_dev", _dev)
    monkeypatch.setattr(pipeline, "_averify_resumed", _still_red)
    return calls


def _blocking_state():
    """US-ROOT transitively blocks two items (fan-out 2)."""
    return _state([
        _us("US-ROOT"),
        _us("US-A", depends_on=["US-ROOT"]),
        _us("US-B", depends_on=["US-ROOT"]),
    ])


async def test_a_high_fanout_item_gets_one_extra_attempt_before_failing(streams_on, monkeypatch):
    monkeypatch.setattr(settings, "dev_max_attempts", 1)
    monkeypatch.setattr(settings, "fanout_bonus_threshold", 2)
    state = _blocking_state()
    pipeline = Pipeline(state, ScriptedRunner())
    calls = _red_dev(pipeline, monkeypatch)

    await asyncio.wait_for(pipeline._abuild_phase(), timeout=90)

    assert calls.count("US-ROOT") == 2  # 1 + the fan-out bonus
    assert state.story("US-ROOT").status == StoryStatus.FAILED
    assert state.story("US-ROOT").attempts == 2


async def test_threshold_zero_keeps_the_historic_ceiling(streams_on, monkeypatch):
    monkeypatch.setattr(settings, "dev_max_attempts", 1)
    monkeypatch.setattr(settings, "fanout_bonus_threshold", 0)
    state = _blocking_state()
    pipeline = Pipeline(state, ScriptedRunner())
    calls = _red_dev(pipeline, monkeypatch)

    await asyncio.wait_for(pipeline._abuild_phase(), timeout=90)

    assert calls.count("US-ROOT") == 1
    assert state.story("US-ROOT").status == StoryStatus.FAILED
    assert state.story("US-ROOT").attempts == 1


async def test_an_item_below_the_threshold_gets_no_bonus(streams_on, monkeypatch):
    monkeypatch.setattr(settings, "dev_max_attempts", 1)
    monkeypatch.setattr(settings, "fanout_bonus_threshold", 3)  # US-ROOT blocks only 2
    state = _blocking_state()
    pipeline = Pipeline(state, ScriptedRunner())
    calls = _red_dev(pipeline, monkeypatch)

    await asyncio.wait_for(pipeline._abuild_phase(), timeout=90)

    assert calls.count("US-ROOT") == 1
    assert state.story("US-ROOT").status == StoryStatus.FAILED


# ----------------------------------------------------- (c) the ceiling helper

def test_max_attempts_for_adds_the_bonus_only_above_the_threshold(monkeypatch):
    monkeypatch.setattr(settings, "dev_max_attempts", 2)
    monkeypatch.setattr(settings, "fanout_bonus_threshold", 5)
    pipeline = Pipeline(_state([_us("US-1")]), ScriptedRunner())
    pipeline._fanout = {"hot": 5, "warm": 4, "leaf": 0}

    assert pipeline._max_attempts_for("hot") == 3
    assert pipeline._max_attempts_for("warm") == 2
    assert pipeline._max_attempts_for("leaf") == 2
    assert pipeline._max_attempts_for("unknown-id") == 2


def test_max_attempts_for_falls_back_to_the_historic_ceiling(monkeypatch):
    monkeypatch.setattr(settings, "dev_max_attempts", 2)
    monkeypatch.setattr(settings, "fanout_bonus_threshold", 0)
    pipeline = Pipeline(_state([_us("US-1")]), ScriptedRunner())
    pipeline._fanout = {"hot": 99}

    # Threshold 0 disables the bonus, and an unmeasured graph never grants one.
    assert pipeline._max_attempts_for("hot") == 2
    monkeypatch.setattr(settings, "fanout_bonus_threshold", 5)
    pipeline._fanout = {}
    assert pipeline._max_attempts_for("US-1") == 2


# ------------------------------------------- (d) the bonus on the fusion loop


def _conflicting_merges(pipeline, monkeypatch) -> list[str]:
    """Green item whose merge ALWAYS conflicts: every pass spends one unit of
    the fusion requeue budget (P0-B) and none of the dev budget."""
    merges: list[str] = []

    async def _dev(subject, worktree, pkg, is_frontend):
        return True, ""

    async def _verify(subject, worktree, is_frontend):
        subject.status = StoryStatus.GREEN
        return True, ""

    async def _merge(repo, branch, wid, worktree=None):
        merges.append(wid)
        return False, ["app.py"]

    monkeypatch.setattr(pipeline, "_arun_item_dev", _dev)
    monkeypatch.setattr(pipeline, "_averify_resumed", _verify)
    monkeypatch.setattr(pipeline, "_amerge_work_item", _merge)
    return merges


async def test_a_high_fanout_item_gets_one_extra_requeue_before_failing(
    streams_on, monkeypatch
):
    """The conflict loop is bounded by requeue_max (P0-B); a critical item is
    granted ONE unit more, exactly like on the dev budget."""
    monkeypatch.setattr(settings, "requeue_max", 1)
    monkeypatch.setattr(settings, "fanout_bonus_threshold", 2)  # US-ROOT blocks 2
    state = _blocking_state()
    pipeline = Pipeline(state, ScriptedRunner())
    merges = _conflicting_merges(pipeline, monkeypatch)

    await asyncio.wait_for(pipeline._abuild_phase(), timeout=90)

    story = state.story("US-ROOT")
    assert merges.count("US-ROOT") == 3     # 1 + 1 requeue + the bonus requeue
    assert story.requeue_attempts == 3      # the third spend blew the budget
    assert story.attempts == 0              # the fusion never debits the dev budget
    assert story.status == StoryStatus.FAILED


async def test_an_item_below_the_threshold_gets_no_extra_requeue(
    streams_on, monkeypatch
):
    monkeypatch.setattr(settings, "requeue_max", 1)
    monkeypatch.setattr(settings, "fanout_bonus_threshold", 3)  # US-ROOT blocks only 2
    state = _blocking_state()
    pipeline = Pipeline(state, ScriptedRunner())
    merges = _conflicting_merges(pipeline, monkeypatch)

    await asyncio.wait_for(pipeline._abuild_phase(), timeout=90)

    story = state.story("US-ROOT")
    assert merges.count("US-ROOT") == 2     # historic P0-B ending
    assert story.requeue_attempts == 2
    assert story.status == StoryStatus.FAILED


async def test_requeue_max_zero_stays_terminal_even_for_a_critical_item(
    streams_on, monkeypatch
):
    """An explicitly disabled fusion budget is never re-opened by the bonus."""
    monkeypatch.setattr(settings, "requeue_max", 0)
    monkeypatch.setattr(settings, "fanout_bonus_threshold", 1)
    state = _blocking_state()
    pipeline = Pipeline(state, ScriptedRunner())
    merges = _conflicting_merges(pipeline, monkeypatch)

    await asyncio.wait_for(pipeline._abuild_phase(), timeout=90)

    assert merges.count("US-ROOT") == 1
    assert state.story("US-ROOT").status == StoryStatus.FAILED


def test_requeue_max_for_mirrors_the_dev_bonus(monkeypatch):
    monkeypatch.setattr(settings, "requeue_max", 3)
    monkeypatch.setattr(settings, "fanout_bonus_threshold", 5)
    pipeline = Pipeline(_state([_us("US-1")]), ScriptedRunner())
    pipeline._fanout = {"hot": 7, "leaf": 0}

    assert pipeline._requeue_max_for("hot") == 4
    assert pipeline._requeue_max_for("leaf") == 3
    monkeypatch.setattr(settings, "fanout_bonus_threshold", 0)
    assert pipeline._requeue_max_for("hot") == 3
    monkeypatch.setattr(settings, "fanout_bonus_threshold", 5)
    monkeypatch.setattr(settings, "requeue_max", 0)
    assert pipeline._requeue_max_for("hot") == 0
