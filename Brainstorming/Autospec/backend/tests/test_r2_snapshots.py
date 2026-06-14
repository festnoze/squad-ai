"""Tests of R2: anti-regression detection + iteration snapshots/rollback."""

import pytest

from autospec.agents.runner import FakeRunner
from autospec.models import PipelinePhase, ProjectState
from autospec.orchestrator import regression, workspace
from autospec.orchestrator.pipeline import Pipeline


def test_find_regressions_basic():
    prev = {"t::a", "t::b", "t::c"}
    current = {"t::a": "passed", "t::b": "failed", "t::c": "passed"}
    assert regression.find_regressions(prev, current) == ["t::b"]


def test_find_regressions_ignores_absent():
    prev = {"t::a", "t::removed"}
    current = {"t::a": "passed"}
    assert regression.find_regressions(prev, current) == []


def test_find_regressions_none_for_new_failures():
    prev = {"t::a"}
    current = {"t::a": "passed", "t::new": "failed"}
    assert regression.find_regressions(prev, current) == []


async def test_snapshot_list_rollback():
    state = ProjectState(id="p-r2", name="m", goal="g", phase=PipelinePhase.DONE, iteration=1)
    pipeline = Pipeline(state, FakeRunner([]))
    ws = workspace.scaffold(state)
    (ws / "f.txt").write_text("v1", encoding="utf-8")
    await pipeline._asnapshot_iteration()
    assert await pipeline.aiterations() == [1]
    (ws / "f.txt").write_text("v2", encoding="utf-8")
    state.iteration = 2
    await pipeline._asnapshot_iteration()
    assert await pipeline.aiterations() == [1, 2]
    await pipeline.arollback(1)
    assert (ws / "f.txt").read_text(encoding="utf-8") == "v1"


async def test_rollback_unknown_iteration():
    state = ProjectState(id="p-r2b", name="m", goal="g", phase=PipelinePhase.DONE)
    pipeline = Pipeline(state, FakeRunner([]))
    workspace.scaffold(state)
    with pytest.raises(ValueError):
        await pipeline.arollback(99)


async def test_rollback_rejected_while_building():
    state = ProjectState(id="p-r2c", name="m", goal="g", phase=PipelinePhase.BUILD)
    pipeline = Pipeline(state, FakeRunner([]))
    with pytest.raises(ValueError):
        await pipeline.arollback(1)
