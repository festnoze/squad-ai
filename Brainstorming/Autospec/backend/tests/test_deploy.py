"""Tests of deployment-artifact generation (D1)."""

import pytest

from autospec.agents.runner import FakeRunner
from autospec.models import PipelinePhase, ProjectState
from autospec.orchestrator.deploy import (
    MANAGED_MARKER,
    dockerfile_text,
    write_deploy_artifacts,
)
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


# ---------------------------------------------------- dockerfile_text variants

def test_dockerfile_backend_exposes_port():
    """Backend kind : python image running main.py with EXPOSE {port}."""
    text = dockerfile_text(8123, "backend")
    assert text.startswith(MANAGED_MARKER)
    assert "python:3.12-slim" in text
    assert "EXPOSE 8123" in text
    # A pure backend has no frontend build stage / nginx.
    assert "node:20-alpine" not in text
    assert "nginx" not in text


def test_dockerfile_fullstack_is_multi_stage_one_image():
    """Fullstack kind : node build stage + python stage serving frontend/dist."""
    text = dockerfile_text(9001, "fullstack")
    assert text.startswith(MANAGED_MARKER)
    assert "FROM node:20-alpine AS fe" in text
    assert "npm run build" in text
    assert "python:3.12-slim" in text
    assert "COPY --from=fe /fe/dist ./frontend/dist" in text
    assert "EXPOSE 9001" in text


def test_dockerfile_frontend_only_serves_via_nginx_port_80():
    """Frontend-only SPA : node build stage → nginx:alpine, container port 80."""
    text = dockerfile_text(1234, "frontend")
    assert text.startswith(MANAGED_MARKER)
    assert "FROM node:20-alpine AS fe" in text
    assert "FROM nginx:alpine" in text
    assert "COPY --from=fe /fe/dist /usr/share/nginx/html" in text
    # The container listens on 80 regardless of the resolved web port.
    assert "EXPOSE 80" in text
    assert "EXPOSE 1234" not in text


# ------------------------------------------- managed-marker regeneration policy

def test_managed_dockerfile_is_regenerated_on_drift(tmp_path):
    """A Dockerfile still carrying the managed marker is safely regenerated when
    the wanted content drifts (e.g. the deploy kind changed)."""
    write_deploy_artifacts(tmp_path, port=8000, kind="backend")
    # Re-writing with a different kind must overwrite the managed Dockerfile.
    created = write_deploy_artifacts(tmp_path, port=8000, kind="frontend")
    assert "Dockerfile" in created
    body = (tmp_path / "Dockerfile").read_text(encoding="utf-8")
    assert "FROM nginx:alpine" in body


def test_user_owned_dockerfile_is_preserved(tmp_path):
    """A Dockerfile a user has taken over (marker removed) is never clobbered."""
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("FROM scratch\n# handcrafted\n", encoding="utf-8")
    created = write_deploy_artifacts(tmp_path, port=8000, kind="fullstack")
    assert "Dockerfile" not in created
    assert dockerfile.read_text(encoding="utf-8") == "FROM scratch\n# handcrafted\n"


def test_dockerignore_ignores_node_modules(tmp_path):
    """The .dockerignore drops node_modules so the frontend build stage installs
    fresh deps instead of copying a host-built tree into the image."""
    write_deploy_artifacts(tmp_path)
    ignore = (tmp_path / ".dockerignore").read_text(encoding="utf-8").splitlines()
    assert "node_modules" in ignore
    assert "**/node_modules" in ignore


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
