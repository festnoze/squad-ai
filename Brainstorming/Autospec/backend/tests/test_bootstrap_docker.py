"""Opt-in real image builds: AUTOSPEC_REAL_DOCKER=1 pytest -q this_file.

Each run owns uniquely named containers/images and removes only those resources.
Docker must already be running; these tests never change Desktop/WSL settings.
"""
import json
import os
from pathlib import Path
import subprocess
import time
from types import SimpleNamespace
from urllib.request import urlopen
import uuid

import pytest

from autospec.orchestrator import bootstrap, deploy, docker_deploy, workspace
from autospec.models import BackendLanguage, ProjectState


pytestmark = pytest.mark.skipif(os.environ.get("AUTOSPEC_REAL_DOCKER") != "1", reason="Opt-in Docker integration")


def docker(*args, check=True):
    result = subprocess.run(["docker", *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
    if check:
        assert result.returncode == 0, result.stdout + result.stderr
    return result


@pytest.mark.parametrize("language,kind", [
    (language, kind) for language in ("python", "go", "node", "rust")
    for kind in ("backend", "fullstack")
] + [("python", "frontend")])
def test_real_bootstrap_image(tmp_path, monkeypatch, language, kind):
    database = "sqlite" if language == "python" and kind == "fullstack" else "none"
    project = SimpleNamespace(id="docker-bootstrap-validation", name="Docker bootstrap validation", streams=[], brownfield_path="", product_profile="auto",
        backend_language=SimpleNamespace(value=language), technical_stack={
            "backend": language, "framework": "", "frontend": "react" if kind in ("fullstack", "frontend") else "none",
            "database": database, "kind": "api" if kind == "backend" else kind,
        })
    monkeypatch.setattr(workspace, "workspace_dir", lambda _: tmp_path)
    workspace.scaffold(project, streams_enabled=False, ui_tests_enabled=False)
    prepared = bootstrap.prepare(project, tmp_path)
    assert prepared.ok, prepared.detail
    deploy.write_deploy_artifacts(tmp_path, kind=kind, language=language, port=8000)
    (tmp_path / ".env").write_text("BOOTSTRAP_TEST_SECRET=must-not-be-in-image\n")
    name = "autospec-test-bootstrap-" + uuid.uuid4().hex[:12]
    image = name + ":test"
    try:
        print(f"Building {language}/{kind}", flush=True)
        ok, detail = docker_deploy.build_image(tmp_path, image, timeout=600)
        assert ok, detail
        container_port = 8080 if kind == "frontend" else 8000
        docker("run", "--detach", "--name", name, "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--cpus", "1", "--memory", "256m", "--publish", f"127.0.0.1::{container_port}", image)
        info = json.loads(docker("inspect", name).stdout)[0]
        mapping = info["NetworkSettings"]["Ports"][f"{container_port}/tcp"][0]
        assert mapping["HostIp"] == "127.0.0.1"
        port = int(mapping["HostPort"])
        assert docker("exec", name, "id", "-u").stdout.strip() not in ("0", "")
        assert docker("exec", name, "test", "-e", "/app/.env", check=False).returncode == 1
        deadline = time.monotonic() + 30
        last_error = "no response"
        while time.monotonic() < deadline:
            try:
                if kind != "frontend":
                    with urlopen(f"http://127.0.0.1:{port}/api/health", timeout=2) as response:
                        body = json.load(response)
                    assert body == {"status": "ok", "service": "autospec-bootstrap", "database": "ok" if database == "sqlite" else "none"}
                if kind in ("frontend", "fullstack"):
                    with urlopen(f"http://127.0.0.1:{port}/", timeout=2) as response:
                        assert b'id="root"' in response.read()
                break
            except Exception as exc:
                last_error = str(exc)
                time.sleep(0.1)
        else:
            pytest.fail(last_error + "\n" + docker("logs", name, check=False).stdout)
        print(f"Verified {language}/{kind}: nonroot, localhost HTTP, secret exclusion", flush=True)
    finally:
        docker("rm", "-f", name, check=False)
        docker("image", "rm", "-f", image, check=False)


@pytest.mark.parametrize("language", ["python", "go", "node", "rust"])
@pytest.mark.parametrize("kind", ["cli", "library"])
def test_real_non_web_delivery_packages_without_starting_a_service(tmp_path, monkeypatch, language, kind):
    """Exercise the real orchestrator path, not only a syntactically valid image."""
    project = ProjectState(
        id="test-package-" + uuid.uuid4().hex[:12], name="Docker package validation",
        goal="Validate a deterministic non-web package", backend_language=BackendLanguage(language),
        technical_stack={"backend": language, "frontend": "none", "database": "none", "kind": kind},
    )
    monkeypatch.setattr(workspace, "workspace_dir", lambda _: tmp_path)
    workspace.scaffold(project, streams_enabled=False, ui_tests_enabled=False)
    prepared = bootstrap.prepare(project, tmp_path)
    assert prepared.ok, prepared.detail
    deploy.write_deploy_artifacts(tmp_path, kind=kind, language=language)
    (tmp_path / ".env").write_text("BOOTSTRAP_TEST_SECRET=must-not-be-in-image\n")
    image = docker_deploy.image_name(project.id)
    name = docker_deploy.container_name(project.id)
    try:
        result = docker_deploy.deploy_and_verify(
            project, tmp_path, network="unused-package-network", host_port=0,
            build_timeout=600, deploy_timeout=30, kind=kind,
        )
        assert result.ok, result.detail
        assert result.packaged and result.host_port == 0 and not result.container
        assert docker_deploy.inspect_packaged_image(project.id).ok
        info = json.loads(docker("image", "inspect", image).stdout)[0]
        assert not info["Config"].get("ExposedPorts")
        assert docker("ps", "-aq", "--filter", f"name={name}").stdout.strip() == ""
        user = docker("run", "--rm", "--network", "none", "--entrypoint", "id", image, "-u").stdout.strip()
        assert user not in ("0", "")
        assert docker("run", "--rm", "--network", "none", "--entrypoint", "test", image,
                      "-e", "/app/.env", check=False).returncode == 1
        print(f"Verified {language}/{kind}: packaged, nonroot, no service, secret exclusion", flush=True)
    finally:
        docker("rm", "-f", name, check=False)
        docker("image", "rm", "-f", image, check=False)
