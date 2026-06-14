"""Tests of per-phase model routing (M3): a per-phase override (else claude_model)
is selected by the usage tracker and passed down to the runner."""

from autospec.agents.runner import FakeRunner
from autospec.config import settings as cfg
from autospec.models import PipelinePhase, ProjectState
from autospec.orchestrator.pipeline import Pipeline


def test_model_for_phase_override(monkeypatch):
    monkeypatch.setattr(cfg, "phase_models", {"build": "strong-model"})
    monkeypatch.setattr(cfg, "claude_model", "default-model")
    assert cfg.model_for_phase("build") == "strong-model"
    assert cfg.model_for_phase("spec") == "default-model"


def test_model_for_phase_no_override(monkeypatch):
    monkeypatch.setattr(cfg, "phase_models", {})
    monkeypatch.setattr(cfg, "claude_model", None)
    assert cfg.model_for_phase("build") is None


async def test_tracker_routes_model_by_phase(monkeypatch):
    monkeypatch.setattr(cfg, "phase_models", {"plan": "cheap-model"})
    state = ProjectState(id="p-m3", name="m", goal="g", phase=PipelinePhase.PLAN)
    runner = FakeRunner(["{}"])
    pipeline = Pipeline(state, runner)
    await pipeline._tracked.arun("p", "s")
    assert runner.calls[-1]["model"] == "cheap-model"
