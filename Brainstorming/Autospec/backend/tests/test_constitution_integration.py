"""Wave 3 integration: the constitution phase wiring in the pipeline (the
constitution module itself is covered in test_constitution.py)."""

from __future__ import annotations

import json

from autospec.agents.runner import FakeRunner
from autospec.config import settings as cfg
from autospec.models import ProjectState
from autospec.orchestrator import workspace
from autospec.orchestrator.pipeline import Pipeline


def _pipeline(pid, replies):
    state = ProjectState(id=pid, name="proj", goal="a todo api", brief="build a todo API")
    pipeline = Pipeline(state, FakeRunner(list(replies)))
    ws = workspace.scaffold(state)
    return pipeline, ws


async def test_constitution_phase_writes_executable_rules(monkeypatch):
    monkeypatch.setattr(cfg, "constitution_enabled", True)
    envelope = json.dumps({"rules": [
        {"id": "C1", "statement": "no eval() in source", "kind": "test",
         "check_code": "def test_no_eval():\n    assert True\n"},
        {"id": "C2", "statement": "document the API", "kind": "advisory"},
    ]})
    pipeline, ws = _pipeline("p-const1", [envelope])
    await pipeline._amaybe_build_constitution()

    assert len(pipeline.state.constitution) == 2
    # 1 règle compilée + le conftest soupape (D1/D3) - protégé comme les tests.
    paths = pipeline.state.constitution_test_paths
    assert len(paths) == 2
    assert "tests/constitution/conftest.py" in paths
    assert (ws / "tests/constitution/conftest.py").exists()
    written = next(p for p in paths if "conftest" not in p)
    assert written.startswith("tests/constitution/test_") and written.endswith(".py")
    assert (ws / written).exists()
    # advisory rule surfaced as build guidance for dev/QA
    assert any("document the API" in g for g in pipeline.state.build_guidance)


async def test_constitution_disabled_is_noop(monkeypatch):
    monkeypatch.setattr(cfg, "constitution_enabled", False)
    pipeline, _ws = _pipeline("p-const2", [])
    await pipeline._amaybe_build_constitution()
    assert pipeline.state.constitution == []


async def test_constitution_built_once(monkeypatch):
    monkeypatch.setattr(cfg, "constitution_enabled", True)
    pipeline, _ws = _pipeline("p-const3", [json.dumps({"rules": [
        {"id": "C1", "statement": "s", "kind": "advisory"}]})])
    await pipeline._amaybe_build_constitution()
    assert len(pipeline.state.constitution) == 1
    # Second call is a no-op (already built) — no runner reply queued, must not call.
    await pipeline._amaybe_build_constitution()
    assert len(pipeline.state.constitution) == 1
