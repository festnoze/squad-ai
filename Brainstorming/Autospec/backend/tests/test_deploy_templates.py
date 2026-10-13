"""Behavioral contracts for exported images and generated CI workflows."""

import json
import re

import pytest
import yaml

from autospec.orchestrator.deploy import (
    MANAGED_MARKER,
    _LEGACY_CI,
    _LEGACY_DOCKERIGNORE,
    _unmodified_generated,
    dockerfile_text,
    write_deploy_artifacts,
)


@pytest.mark.parametrize("language", ["python", "go", "rust", "node"])
@pytest.mark.parametrize("kind", ["backend", "fullstack", "cli", "library"])
def test_selected_stack_produces_nonroot_self_contained_image(language, kind):
    body = dockerfile_text(9123, kind, language, "web/client")
    assert _unmodified_generated(body)
    assert "USER " in body
    if kind in {"cli", "library"}:
        assert "EXPOSE " not in body
    else:
        assert "EXPOSE 9123" in body
        assert "mkdir -p /app/data" in body
    if kind == "fullstack":
        assert "COPY web/client/ ./" in body
        assert "AUTOSPEC_STATIC_DIR=/app/web/client/dist" in body
    command = json.loads(re.search(r"^CMD (.+)$", body, re.MULTILINE)[1])
    assert "uv" not in command  # runtime must not sync/download dependencies
    assert "install" not in command
    assert "|| true" not in body
    assert "npm ci ||" not in body
    if kind == "cli":
        entrypoint = json.loads(re.search(r"^ENTRYPOINT (.+)$", body, re.MULTILINE)[1])
        assert entrypoint
        assert command == ["--help"]


@pytest.mark.parametrize("language,expected,unexpected", [
    ("python", "pytest", "go test"),
    ("go", "go test -mod=readonly ./...", "pytest"),
    ("rust", "cargo test --locked", "pytest"),
    ("node", "npm test", "pytest"),
])
def test_generated_ci_runs_native_tests_and_frontend(tmp_path, language, expected, unexpected):
    write_deploy_artifacts(tmp_path, kind="fullstack", language=language, frontend_root="web/client")
    raw = (tmp_path / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert expected in raw
    assert unexpected not in raw
    workflow = yaml.safe_load(raw)
    steps = workflow["jobs"]["test"]["steps"]
    frontend_commands = [step.get("run") for step in steps if step.get("working-directory") == "web/client"]
    assert "npm test" in frontend_commands
    assert "npm run build" in frontend_commands


def test_frontend_root_directory_supported(tmp_path):
    write_deploy_artifacts(tmp_path, kind="frontend", frontend_root=".")
    body = (tmp_path / "Dockerfile").read_text(encoding="utf-8")
    workflow = (tmp_path / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "COPY ./ ./" in body
    assert "uv " not in workflow
    assert "working-directory: ." in workflow
    assert "listen 8080" in (tmp_path / "nginx.conf").read_text(encoding="utf-8")


def test_repair_keeps_marker_but_is_not_overwritten(tmp_path):
    write_deploy_artifacts(tmp_path)
    path = tmp_path / "Dockerfile"
    repaired = path.read_text(encoding="utf-8").replace("USER app", "ENV REPAIRED=yes\nUSER app")
    assert MANAGED_MARKER in repaired
    path.write_text(repaired, encoding="utf-8")
    created = write_deploy_artifacts(tmp_path, kind="fullstack", port=9999)
    assert "Dockerfile" not in created
    assert path.read_text(encoding="utf-8") == repaired


def test_generated_ci_updates_but_custom_edits_survive(tmp_path):
    write_deploy_artifacts(tmp_path, language="python")
    write_deploy_artifacts(tmp_path, language="go")
    path = tmp_path / ".github/workflows/ci.yml"
    assert "go test" in path.read_text(encoding="utf-8")
    custom = path.read_text(encoding="utf-8") + "# extra deployment step maintained by user\n"
    path.write_text(custom, encoding="utf-8")
    write_deploy_artifacts(tmp_path, language="rust")
    assert path.read_text(encoding="utf-8") == custom


def test_known_legacy_templates_are_safely_migrated(tmp_path):
    old_dockerfile = f"""{MANAGED_MARKER}
# syntax=docker/dockerfile:1
FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir uv
COPY pyproject.toml ./
RUN uv sync --no-dev || uv sync || true
COPY . .
EXPOSE 8000
CMD ["uv", "run", "python", "main.py"]
"""
    (tmp_path / "Dockerfile").write_text(old_dockerfile, encoding="utf-8")
    (tmp_path / ".dockerignore").write_text(_LEGACY_DOCKERIGNORE, encoding="utf-8")
    ci_path = tmp_path / ".github/workflows/ci.yml"
    ci_path.parent.mkdir(parents=True)
    ci_path.write_text(_LEGACY_CI, encoding="utf-8")
    created = write_deploy_artifacts(tmp_path, language="go")
    assert set(created) == {"Dockerfile", ".dockerignore", ".github/workflows/ci.yml"}
    assert "golang:" in (tmp_path / "Dockerfile").read_text(encoding="utf-8")
    assert "go test" in ci_path.read_text(encoding="utf-8")
    assert write_deploy_artifacts(tmp_path, language="go") == []


def test_secret_exclusions_also_protect_custom_ignore(tmp_path):
    path = tmp_path / ".dockerignore"
    path.write_text("custom-folder/\n!**/.env\n", encoding="utf-8")
    write_deploy_artifacts(tmp_path)
    body = path.read_text(encoding="utf-8")
    assert body.startswith("custom-folder/\n!**/.env\n")
    assert body.index("!**/.env") < body.index("\n**/.env\n")
    for pattern in [".env", ".env.*", "**/.env.*", "**/*.key", "**/credentials.json", "**/.ssh"]:
        assert pattern in body.splitlines()
    assert write_deploy_artifacts(tmp_path) == []


@pytest.mark.parametrize("options", [
    {"language": "cobol"},
    {"kind": "ambiguous"},
    {"frontend_root": "../secret"},
    {"frontend_root": "/outside"},
    {"frontend_root": "frontend\nRUN echo injected"},
    {"port": 0},
    {"port": 65536},
    {"port": True},
])
def test_invalid_options_fail_before_writing_any_file(tmp_path, options):
    with pytest.raises(ValueError):
        write_deploy_artifacts(tmp_path, **options)
    assert list(tmp_path.iterdir()) == []


def test_lockfiles_are_required_and_inconsistent_locks_fail_closed():
    python = dockerfile_text(8000)
    node = dockerfile_text(8000, language="node")
    rust = dockerfile_text(8000, language="rust")
    go = dockerfile_text(8000, language="go")
    assert "test -f pyproject.toml && test -f uv.lock && uv sync --locked --no-dev" in python
    assert "test -f package.json && test -f package-lock.json && npm ci" in node
    assert "test -f Cargo.toml && test -f Cargo.lock && cargo build --release --locked" in rust
    assert "test -f go.mod && test -f go.sum && go mod verify" in go
    assert "go build -mod=readonly" in go
    for body in [python, node, rust, go]:
        assert "npm install" not in body
        assert "uv sync --no-dev" not in body
        assert "cargo build --release;" not in body
        assert "go mod download" not in body


@pytest.mark.parametrize("language,required", [
    ("python", ["test -f pyproject.toml", "test -f uv.lock", "uv sync --locked"]),
    ("go", ["test -f go.mod", "test -f go.sum", "go mod verify", "-mod=readonly"]),
    ("rust", ["test -f Cargo.toml", "test -f Cargo.lock", "cargo test --locked", "cargo build --release --locked"]),
    ("node", ["test -f package.json", "test -f package-lock.json", "npm ci"]),
])
def test_ci_requires_manifest_lock_pair_and_has_no_unlocked_fallback(tmp_path, language, required):
    write_deploy_artifacts(tmp_path, language=language)
    workflow = (tmp_path / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    for fragment in required:
        assert fragment in workflow
    for forbidden in ["npm install", "uv sync --extra", "uv sync ||", "cargo test;", "cargo build --release;", "go mod download"]:
        assert forbidden not in workflow


def test_frontend_docker_and_ci_require_lock_instead_of_npm_install(tmp_path):
    write_deploy_artifacts(tmp_path, kind="frontend")
    dockerfile = (tmp_path / "Dockerfile").read_text(encoding="utf-8")
    workflow = (tmp_path / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    for body in (dockerfile, workflow):
        assert "test -f package.json" in body
        assert "test -f package-lock.json" in body
        assert "npm ci" in body
        assert "npm install" not in body


def test_verified_python_and_node_build_images_are_immutable():
    python = dockerfile_text(8000, language="python")
    node = dockerfile_text(8000, language="node")
    frontend = dockerfile_text(8000, kind="frontend")
    assert "ghcr.io/astral-sh/uv@sha256:e5b65587bce7de595f299855d7385fe7fca39b8a74baa261ba1b7147afa78e58" in python
    assert "pip install" not in python
    for body in (node, frontend):
        assert "node@sha256:c3de60bf2f9dd0ac6370e6117950ff62d6e339527e7472301c9c78a017978392" in body
        assert "node:22-alpine" not in body
