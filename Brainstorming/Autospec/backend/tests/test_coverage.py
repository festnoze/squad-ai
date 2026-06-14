"""Tests of the coverage gate (Q2): run the suite under coverage, record the % on
story.coverage_score; best-effort (unavailable -> -1, disabled -> noop)."""

import json
import subprocess
from pathlib import Path

from autospec.agents.runner import FakeRunner
from autospec.config import settings as cfg
from autospec.models import ProjectState, UserStory
from autospec.orchestrator import workspace
from autospec.orchestrator.pipeline import Pipeline


def _pipeline(pid):
    state = ProjectState(id=pid, name="cov", goal="g")
    pipeline = Pipeline(state, FakeRunner([]))
    ws = workspace.scaffold(state)
    pkg = workspace.package_name(state)
    return pipeline, ws, pkg


async def test_coverage_score_parsed(monkeypatch):
    monkeypatch.setattr(cfg, "coverage_enabled", True)
    monkeypatch.setattr(cfg, "fake_agents", False)
    pipeline, ws, pkg = _pipeline("p-cov1")

    def _fake_run(cmd, cwd, **kw):
        Path(cwd, ".autospec-cov.json").write_text(
            json.dumps({"totals": {"percent_covered": 87.0}}), encoding="utf-8"
        )
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr("autospec.orchestrator.pipeline.subprocess.run", _fake_run)
    story = UserStory(id="US-1", epic_id="E1", title="t")
    score = await pipeline._arun_coverage(story, pkg, ws)
    assert score == 87
    assert story.coverage_score == 87


async def test_coverage_unavailable_returns_minus1(monkeypatch):
    monkeypatch.setattr(cfg, "coverage_enabled", True)
    monkeypatch.setattr(cfg, "fake_agents", False)
    pipeline, ws, pkg = _pipeline("p-cov2")

    def _boom(*a, **k):
        raise OSError("pytest-cov absent")

    monkeypatch.setattr("autospec.orchestrator.pipeline.subprocess.run", _boom)
    story = UserStory(id="US-1", epic_id="E1", title="t")
    assert await pipeline._arun_coverage(story, pkg, ws) == -1
    assert story.coverage_score == -1


async def test_coverage_disabled_noop(monkeypatch):
    monkeypatch.setattr(cfg, "coverage_enabled", False)
    pipeline, ws, pkg = _pipeline("p-cov3")
    story = UserStory(id="US-1", epic_id="E1", title="t")
    assert await pipeline._arun_coverage(story, pkg, ws) == -1
    assert story.coverage_score == -1
