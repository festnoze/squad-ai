"""Tests of deployment-artifact generation (D1)."""

import pytest

from autospec.agents.runner import FakeRunner
from autospec.models import PipelinePhase, ProjectState
from autospec.orchestrator.deploy import write_deploy_artifacts
from autospec.orchestrator.pipeline import Pipeline


def test_write_deploy_artifacts(tmp_path):
    created = write_deploy_artifacts(tmp_path)
    assert "Dockerfile" in created
    assert ".github/workflows/ci.yml" in created
    assert (tmp_path / "Dockerfile").exists()
    assert (tmp_path / ".github" / "workflows" / "ci.yml").exists()
    assert "uv run pytest" in (tmp_path / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )


def test_write_deploy_idempotent(tmp_path):
    write_deploy_artifacts(tmp_path)
    assert write_deploy_artifacts(tmp_path) == []


async def test_adeploy_creates_artifacts():
    state = ProjectState(id="p-dep", name="m", goal="g", phase=PipelinePhase.DONE)
    pipeline = Pipeline(state, FakeRunner([]))
    result = await pipeline.adeploy()
    assert "Dockerfile" in result["created"]


async def test_adeploy_rejected_while_building():
    state = ProjectState(id="p-dep2", name="m", goal="g", phase=PipelinePhase.BUILD)
    pipeline = Pipeline(state, FakeRunner([]))
    with pytest.raises(ValueError):
        await pipeline.adeploy()
