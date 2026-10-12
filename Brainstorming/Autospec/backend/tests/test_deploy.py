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
    assert "uv run --no-sync pytest" in (tmp_path / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )


def test_write_deploy_idempotent(tmp_path):
    write_deploy_artifacts(tmp_path)
    assert write_deploy_artifacts(tmp_path) == []


# ---------------------------------------------------- dockerfile_text variants

def _assert_header(text: str) -> None:
    """Docker only honors ``# syntax=`` as the very FIRST line; the managed
    marker sits on line 2."""
    lines = text.splitlines()
    assert lines[0] == "# syntax=docker/dockerfile:1"
    assert lines[1] == MANAGED_MARKER


def test_dockerfile_backend_exposes_port():
    """Backend kind : python image running main.py with EXPOSE {port}."""
    text = dockerfile_text(8123, "backend")
    _assert_header(text)
    assert "python:3.12-slim" in text
    assert "EXPOSE 8123" in text
    # A pure backend has no frontend build stage / nginx.
    assert "node:22-alpine" not in text
    assert "nginx" not in text


def test_dockerfile_fullstack_is_multi_stage_one_image():
    """Fullstack kind : node build stage + python stage serving frontend/dist."""
    text = dockerfile_text(9001, "fullstack")
    _assert_header(text)
    assert "FROM node:22-alpine AS fe" in text
    assert "npm run build" in text
    assert "python:3.12-slim" in text
    assert "COPY --from=fe /fe/dist /app/frontend/dist" in text
    assert "EXPOSE 9001" in text


def test_dockerfile_frontend_only_serves_via_unprivileged_nginx():
    """The frontend binds an unprivileged port, compatible with cap-drop ALL."""
    text = dockerfile_text(1234, "frontend")
    _assert_header(text)
    assert "FROM node:22-alpine AS fe" in text
    assert "FROM nginxinc/nginx-unprivileged:" in text
    assert "COPY --from=fe /fe/dist /usr/share/nginx/html" in text
    assert "EXPOSE 8080" in text
    assert "USER 101" in text
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
    assert "FROM nginxinc/nginx-unprivileged:" in body


def test_unknown_legacy_marker_does_not_authorize_overwrite(tmp_path):
    """An unsigned marker cannot tell a user repair from generated content."""
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text(
        f"{MANAGED_MARKER}\n# syntax=docker/dockerfile:1\nFROM python:3.12-slim\n",
        encoding="utf-8",
    )
    created = write_deploy_artifacts(tmp_path, port=8000, kind="backend")
    assert "Dockerfile" not in created
    lines = dockerfile.read_text(encoding="utf-8").splitlines()
    assert lines[0] == MANAGED_MARKER
    assert lines[1] == "# syntax=docker/dockerfile:1"


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
