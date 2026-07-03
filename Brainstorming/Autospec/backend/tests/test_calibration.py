"""§8 — observability & calibration counters (PlanCalibration): the per-build
signals that tell whether the plan sized the work correctly and whether the
recovery machinery (P2b, infra retries, orphan resets) is a rarely-used safety
net or a permanent crutch."""

import asyncio
from pathlib import Path

import pytest

from autospec.agents.runner import AgentError
from autospec.agents.scripted import ScriptedRunner
from autospec.config import settings
from autospec.models import Epic, ProjectState, StoryStatus, Stream, StreamKind, UserStory
from autospec.orchestrator.pipeline import Pipeline


def _state(stories, project_id):
    st = ProjectState(id=project_id, name="calib", goal="g")
    st.epics.append(Epic(id="EPIC-1", title="E"))
    st.streams = [Stream(id="backend", kind=StreamKind.BACKEND, language="python", primary=True)]
    st.stories = stories
    return st


def _us(sid):
    return UserStory(
        id=sid, epic_id="EPIC-1", title=sid, stream="backend",
        gherkin="Feature: F\n  Scenario: S\n    Given a\n    When b\n    Then c",
    )


@pytest.fixture
def streams_setup(monkeypatch):
    monkeypatch.setattr(settings, "streams_enabled", True)
    monkeypatch.setattr(settings, "fake_agents", True)


async def test_real_footprint_over_budget_is_counted(streams_setup, monkeypatch):
    """The dev's commit touches more files than the leaf budget → the item still
    ships (indicative budget) but the calibration records the overrun."""
    monkeypatch.setattr(settings, "task_file_budget", 3)
    state = _state([_us("US-1")], "calib-budget")
    pipeline = Pipeline(state, ScriptedRunner())

    async def _fat_dev(subject, worktree, pkg, is_frontend):
        for i in range(5):  # budget is 3
            (Path(worktree) / f"gen_{i}.py").write_text(f"# {i}\n", encoding="utf-8")
        return True, ""

    monkeypatch.setattr(pipeline, "_arun_item_dev", _fat_dev)
    await asyncio.wait_for(pipeline._abuild_phase(), timeout=40)

    assert state.story("US-1").status == StoryStatus.DONE
    assert state.calibration_for().over_budget_tasks == 1


async def test_footprint_within_budget_not_counted(streams_setup, monkeypatch):
    monkeypatch.setattr(settings, "task_file_budget", 3)
    state = _state([_us("US-1")], "calib-ok")
    pipeline = Pipeline(state, ScriptedRunner())

    async def _lean_dev(subject, worktree, pkg, is_frontend):
        (Path(worktree) / "gen.py").write_text("# ok\n", encoding="utf-8")
        return True, ""

    monkeypatch.setattr(pipeline, "_arun_item_dev", _lean_dev)
    await asyncio.wait_for(pipeline._abuild_phase(), timeout=40)

    assert state.calibration_for().over_budget_tasks == 0


async def test_merge_requeue_and_p2b_resume_are_counted(streams_setup, monkeypatch):
    """A merge conflict counts a requeue; the preserved branch shipping without
    a dev rebuild counts a P2b resume — the ratio proves what P2b saves."""
    monkeypatch.setattr(settings, "dev_max_attempts", 2)
    state = _state([_us("US-1")], "calib-p2b")
    pipeline = Pipeline(state, ScriptedRunner())
    merges = []

    async def _dev(subject, worktree, pkg, is_frontend):
        return True, ""

    async def _merge(repo, branch, wid, worktree=None):
        merges.append(wid)
        return len(merges) > 1, []

    async def _verify(subject, worktree, is_frontend):
        subject.status = StoryStatus.GREEN
        return True, ""

    monkeypatch.setattr(pipeline, "_arun_item_dev", _dev)
    monkeypatch.setattr(pipeline, "_amerge_work_item", _merge)
    monkeypatch.setattr(pipeline, "_averify_resumed", _verify)
    await asyncio.wait_for(pipeline._abuild_phase(), timeout=40)

    calib = state.calibration_for()
    assert calib.merge_requeues == 1
    assert calib.p2b_resumes == 1


async def test_infra_retry_is_counted(streams_setup, monkeypatch):
    monkeypatch.setattr(settings, "infra_max_retries", 2)
    state = _state([_us("US-1")], "calib-infra")
    pipeline = Pipeline(state, ScriptedRunner())
    calls = []

    async def _flaky(subject, worktree, pkg, is_frontend):
        calls.append(1)
        if len(calls) == 1:
            raise AgentError("transport down")
        return True, ""

    monkeypatch.setattr(pipeline, "_arun_item_dev", _flaky)
    await asyncio.wait_for(pipeline._abuild_phase(), timeout=40)

    assert state.calibration_for().infra_retries == 1


def test_orphan_reset_is_counted():
    story = _us("US-1")
    story.status = StoryStatus.IN_PROGRESS
    state = _state([story], "calib-orphan")
    pipeline = Pipeline(state, ScriptedRunner())
    assert pipeline._reset_orphan_items() == 1
    assert state.calibration_for().orphan_resets == 1
