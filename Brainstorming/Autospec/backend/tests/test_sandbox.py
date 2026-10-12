"""Product execution uses attested confinement, never an optional host fallback."""

import pytest

from autospec.agents.runner import AgentError, FakeRunner
from autospec.config import settings as cfg
from autospec.models import ProjectState
from autospec.orchestrator.pipeline import Pipeline
from autospec.orchestrator.sandbox import docker_run_cmd


def test_docker_run_cmd():
    cmd = docker_run_cmd(["uv", "run", "python", "main.py"], "/work", "python:3.12-slim")
    assert cmd[:3] == ["docker", "run", "--rm"]
    assert "--network" in cmd and "none" in cmd
    assert "/work:/app:rw" in cmd
    assert cmd[cmd.index("--entrypoint") + 1] == "uv"
    assert cmd[-3:] == ["run", "python", "main.py"]
    assert cmd[cmd.index('--user') + 1] == '65532:65532'
    assert '--read-only' in cmd and cmd[cmd.index('--cap-drop') + 1] == 'ALL'
    assert cmd[cmd.index('--security-opt') + 1] == 'no-new-privileges=true'
    assert '--privileged' not in cmd and '/var/run/docker.sock' not in ' '.join(cmd)
    assert {cmd[index + 1] for index, value in enumerate(cmd) if value == '--env'} == {'HOME=/tmp', 'PYTHONDONTWRITEBYTECODE=1'}
    assert '--env-file' not in cmd


def test_docker_run_cmd_custom_binary():
    cmd = docker_run_cmd(["x"], "/w", "img", docker="podman")
    assert cmd[0] == "podman"
    assert cmd[cmd.index("--entrypoint") + 1] == "x"


def test_product_network_cannot_be_enabled():
    with pytest.raises(AgentError, match='network=none'):
        docker_run_cmd(['python'], '/work', 'image', network='bridge')


@pytest.mark.parametrize('legacy_setting', [False, True])
def test_legacy_optional_sandbox_is_refused_in_both_modes(monkeypatch, legacy_setting):
    monkeypatch.setattr(cfg, "sandbox_enabled", legacy_setting)
    monkeypatch.setattr(cfg, "sandbox_image", "myimg")
    monkeypatch.setattr(cfg, "docker_cmd", "docker")
    pipeline = Pipeline(ProjectState(id="p-sb2", name="m", goal="g"), FakeRunner([]))
    with pytest.raises(AgentError, match='ISOLATION_UNAVAILABLE') as error:
        pipeline._maybe_sandbox(["echo", "hi"], "/w")
    assert error.value.code == 'ISOLATION_UNAVAILABLE'
