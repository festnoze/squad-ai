"""P0-B (GENERATION_FUSION_REVIEW) + P1 (WORKFLOW_REVIEW): only a failure that
is IMPUTABLE to the generated code may debit the dev budget.

Two leaks are closed here:

* a merge conflict (or a post-merge canary revert) used to consume a
  ``dev_max_attempts`` unit although the item's own branch was green - the
  collision belongs to the FUSION, so the dev attempt is refunded and the
  separate ``requeue_max`` budget is spent instead;
* a RED verification that executed ZERO test used to consume a dev attempt
  although nothing ever ran - the worktree environment is now repaired and the
  suite replayed ONCE, and a red that still runs no test refunds the dev attempt
  onto the ``infra_max_retries`` budget (flag ``EMPTY_RED_IS_INFRA``).
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
    UserStory,
)
from autospec.orchestrator.pipeline import Pipeline


def _state(project_id: str) -> ProjectState:
    st = ProjectState(id=project_id, name="budget", goal="g")
    st.epics.append(Epic(id="EPIC-1", title="E"))
    st.streams = [
        Stream(id="backend", kind=StreamKind.BACKEND, language="python", primary=True)
    ]
    st.stories = [
        UserStory(
            id="US-1", epic_id="EPIC-1", title="US-1", stream="backend",
            gherkin="Feature: F\n  Scenario: S\n    Given a\n    When b\n    Then c",
        )
    ]
    return st


@pytest.fixture
def streams_on(monkeypatch):
    monkeypatch.setattr(settings, "streams_enabled", True)
    monkeypatch.setattr(settings, "fake_agents", True)


# --------------------------------------------- (a) merge conflicts never debit dev

async def test_two_merge_conflicts_keep_requeuing_without_burning_the_dev_budget(
    streams_on, monkeypatch
):
    """TWO consecutive conflicts with ``dev_max_attempts`` = 2: the historic code
    ended FAILED on the second one. The fusion budget now carries them and the
    third pass merges cleanly."""
    state = _state("budget-conflict-twice")
    pipeline = Pipeline(state, ScriptedRunner())
    merges: list[str] = []

    async def _dev(subject, worktree, pkg, is_frontend):
        return True, ""

    async def _verify(subject, worktree, is_frontend):
        subject.status = StoryStatus.GREEN
        return True, ""

    async def _merge(repo, branch, wid, worktree=None):
        merges.append(wid)
        return len(merges) > 2, ["app.py"]

    monkeypatch.setattr(pipeline, "_arun_item_dev", _dev)
    monkeypatch.setattr(pipeline, "_averify_resumed", _verify)
    monkeypatch.setattr(pipeline, "_amerge_work_item", _merge)
    await asyncio.wait_for(pipeline._abuild_phase(), timeout=60)

    story = state.story("US-1")
    assert story.status == StoryStatus.DONE          # never FAILED on a fusion clash
    assert len(merges) == 3
    # The two conflicting passes were refunded; only the merging pass is charged
    # to the dev budget (and it stays under dev_max_attempts == 2).
    assert story.attempts == 1
    assert story.requeue_attempts == 2
    calib = state.calibration_for()
    assert calib.requeue_refunds == 2
    assert calib.merge_requeues == 2


async def test_requeue_budget_exhausted_ends_failed(streams_on, monkeypatch):
    """Past ``requeue_max`` the historic ending is restored (split-on-failure is
    pinned OFF by the conftest, so: FAILED) - the loop stays bounded."""
    monkeypatch.setattr(settings, "requeue_max", 1)
    state = _state("budget-conflict-exhausted")
    pipeline = Pipeline(state, ScriptedRunner())
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
    await asyncio.wait_for(pipeline._abuild_phase(), timeout=60)

    story = state.story("US-1")
    assert story.status == StoryStatus.FAILED
    assert len(merges) == 2                 # one requeue, then the terminal pass
    assert story.requeue_attempts == 2      # the second spend blew the budget
    assert story.attempts == 0              # not ONE dev attempt was debited
    assert state.calibration_for().requeue_refunds == 2


async def test_requeue_max_zero_fails_on_the_first_conflict(streams_on, monkeypatch):
    """``REQUEUE_MAX=0`` = no fusion requeue at all (the strictest setting)."""
    monkeypatch.setattr(settings, "requeue_max", 0)
    state = _state("budget-conflict-zero")
    pipeline = Pipeline(state, ScriptedRunner())
    merges: list[str] = []

    async def _dev(subject, worktree, pkg, is_frontend):
        return True, ""

    async def _merge(repo, branch, wid, worktree=None):
        merges.append(wid)
        return False, ["app.py"]

    monkeypatch.setattr(pipeline, "_arun_item_dev", _dev)
    monkeypatch.setattr(pipeline, "_amerge_work_item", _merge)
    await asyncio.wait_for(pipeline._abuild_phase(), timeout=60)

    story = state.story("US-1")
    assert story.status == StoryStatus.FAILED
    assert len(merges) == 1
    assert story.requeue_attempts == 1


# ------------------------------------- (b) a red with zero test executed is infra

async def test_red_without_any_executed_test_refunds_the_dev_attempt(
    streams_on, monkeypatch
):
    """First pass: red with NO parsed outcome -> the env is purged, the suite
    replayed ONCE, still nothing runs -> dev attempt refunded, infra budget spent
    and the item re-queued. The next pass runs green and merges."""
    monkeypatch.setattr(settings, "empty_red_is_infra", True)
    state = _state("budget-empty-red")
    pipeline = Pipeline(state, ScriptedRunner())
    calls: list[object] = []
    purged: list[object] = []

    async def _pytest(ws=None):
        calls.append(ws)
        if len(calls) <= 2:
            return False, "error: no python interpreter found", {}
        return True, "", {"tests/test_a.py::test_a": "passed"}

    monkeypatch.setattr(pipeline, "_arun_pytest", _pytest)
    monkeypatch.setattr(
        Pipeline, "_purge_venv_dir",
        staticmethod(lambda ws: purged.append(ws) or True),
    )
    await asyncio.wait_for(pipeline._abuild_phase(), timeout=60)

    story = state.story("US-1")
    assert story.status == StoryStatus.DONE
    assert len(purged) == 1          # exactly ONE repair+replay, on the empty red
    assert purged[0] is not None     # the WORKTREE env was rebuilt, not the shared one
    assert story.infra_attempts == 1
    assert story.attempts == 1       # the refunded pass left only the green one
    assert state.calibration_for().infra_retries == 1


async def test_red_without_any_executed_test_fails_as_infra_when_budget_is_out(
    streams_on, monkeypatch
):
    """Nothing ever runs: the item ends FAILED on the INFRA budget, with an
    explicit diagnosis - never on an imaginary dev failure."""
    monkeypatch.setattr(settings, "empty_red_is_infra", True)
    monkeypatch.setattr(settings, "infra_max_retries", 1)
    state = _state("budget-empty-red-out")
    pipeline = Pipeline(state, ScriptedRunner())
    calls: list[object] = []
    purged: list[object] = []

    async def _pytest(ws=None):
        calls.append(ws)
        return False, "error: no python interpreter found", {}

    monkeypatch.setattr(pipeline, "_arun_pytest", _pytest)
    monkeypatch.setattr(
        Pipeline, "_purge_venv_dir",
        staticmethod(lambda ws: purged.append(ws) or True),
    )
    await asyncio.wait_for(pipeline._abuild_phase(), timeout=60)

    story = state.story("US-1")
    assert story.status == StoryStatus.FAILED
    assert story.attempts == 0                    # every dev attempt refunded
    assert story.infra_attempts == 2              # budget 1 -> the 2nd is terminal
    assert "aucun test exécuté" in story.last_error
    assert len(purged) == 2                       # ONE repair+replay per pass
    assert state.calibration_for().infra_retries == 2


async def test_a_replay_that_goes_green_merges_the_item(streams_on, monkeypatch):
    """The repair WORKS on the replay: the item is green, merged and DONE without
    ever re-running the dev (the first red never was a code failure)."""
    monkeypatch.setattr(settings, "empty_red_is_infra", True)
    state = _state("budget-empty-red-healed")
    pipeline = Pipeline(state, ScriptedRunner())
    calls: list[object] = []
    purged: list[object] = []

    async def _pytest(ws=None):
        calls.append(ws)
        if len(calls) == 1:
            return False, "no interpreter found", {}
        return True, "", {"tests/test_a.py::test_a": "passed"}

    monkeypatch.setattr(pipeline, "_arun_pytest", _pytest)
    monkeypatch.setattr(
        Pipeline, "_purge_venv_dir",
        staticmethod(lambda ws: purged.append(ws) or True),
    )
    await asyncio.wait_for(pipeline._abuild_phase(), timeout=60)

    story = state.story("US-1")
    assert story.status == StoryStatus.DONE
    assert len(purged) == 1           # ONE repair+replay, and it was enough
    assert story.attempts == 1
    assert story.infra_attempts == 0


async def test_red_with_real_failures_still_debits_the_dev_budget(
    streams_on, monkeypatch
):
    """The control case: tests DID run and failed - that is the dev's
    responsibility, so the historic dev-attempt accounting is untouched and NO
    replay is attempted."""
    monkeypatch.setattr(settings, "empty_red_is_infra", True)
    state = _state("budget-real-red")
    pipeline = Pipeline(state, ScriptedRunner())
    calls: list[object] = []
    purged: list[object] = []

    async def _pytest(ws=None):
        calls.append(ws)
        return False, "assert 4 == 5", {"tests/test_a.py::test_a": "failed"}

    monkeypatch.setattr(pipeline, "_arun_pytest", _pytest)
    monkeypatch.setattr(
        Pipeline, "_purge_venv_dir",
        staticmethod(lambda ws: purged.append(ws) or True),
    )
    await asyncio.wait_for(pipeline._abuild_phase(), timeout=60)

    story = state.story("US-1")
    assert story.status == StoryStatus.FAILED
    assert story.attempts == 2                    # dev_max_attempts (conftest)
    assert story.infra_attempts == 0
    assert purged == []                           # real failures: NO replay
    assert state.calibration_for().infra_retries == 0


async def test_flag_off_keeps_the_legacy_empty_red_accounting(streams_on, monkeypatch):
    """``EMPTY_RED_IS_INFRA=0`` restores the historic behaviour byte for byte: no
    replay, and the empty red costs dev attempts until FAILED."""
    monkeypatch.setattr(settings, "empty_red_is_infra", False)
    state = _state("budget-empty-red-off")
    pipeline = Pipeline(state, ScriptedRunner())
    calls: list[object] = []
    purged: list[object] = []

    async def _pytest(ws=None):
        calls.append(ws)
        return False, "error: no python interpreter found", {}

    monkeypatch.setattr(pipeline, "_arun_pytest", _pytest)
    monkeypatch.setattr(
        Pipeline, "_purge_venv_dir",
        staticmethod(lambda ws: purged.append(ws) or True),
    )
    await asyncio.wait_for(pipeline._abuild_phase(), timeout=60)

    story = state.story("US-1")
    assert story.status == StoryStatus.FAILED
    assert story.attempts == 2
    assert story.infra_attempts == 0
    assert purged == []                           # flag off: not one replay


# --------------------------------------------------- (c) bookkeeping invariants

def test_requeue_attempts_is_reset_like_the_infra_budget():
    """Every place that gives an item a fresh start must clear the fusion budget
    too, else a rebuilt item inherits an exhausted one and fails instantly."""
    import re
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "autospec" / "orchestrator" / "pipeline.py"
    text = src.read_text(encoding="utf-8")
    infra_resets = re.findall(r"(\w+)\.infra_attempts = 0", text)
    requeue_resets = re.findall(r"(\w+)\.requeue_attempts = 0", text)
    assert infra_resets and infra_resets == requeue_resets
