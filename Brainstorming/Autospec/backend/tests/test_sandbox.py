"""Tests of the untrusted-code sandbox (R1): Docker command wrapping, env-gated."""

from autospec.agents.runner import FakeRunner
from autospec.config import settings as cfg
from autospec.models import ProjectState
from autospec.orchestrator.pipeline import Pipeline
from autospec.orchestrator.sandbox import docker_run_cmd


def test_docker_run_cmd():
    cmd = docker_run_cmd(["uv", "run", "python", "main.py"], "/work", "python:3.12-slim")
    assert cmd[:3] == ["docker", "run", "--rm"]
    assert "--network" in cmd and "none" in cmd
    assert "/work:/app" in cmd
    assert cmd[-4:] == ["uv", "run", "python", "main.py"]


def test_docker_run_cmd_custom_binary():
    cmd = docker_run_cmd(["x"], "/w", "img", docker="podman")
    assert cmd[0] == "podman"
    assert cmd[-1] == "x"


def test_maybe_sandbox_passthrough_when_disabled(monkeypatch):
    monkeypatch.setattr(cfg, "sandbox_enabled", False)
    pipeline = Pipeline(ProjectState(id="p-sb", name="m", goal="g"), FakeRunner([]))
    assert pipeline._maybe_sandbox(["echo", "hi"], "/w") == ["echo", "hi"]


def test_maybe_sandbox_wraps_when_enabled(monkeypatch):
    monkeypatch.setattr(cfg, "sandbox_enabled", True)
    monkeypatch.setattr(cfg, "sandbox_image", "myimg")
    monkeypatch.setattr(cfg, "docker_cmd", "docker")
    pipeline = Pipeline(ProjectState(id="p-sb2", name="m", goal="g"), FakeRunner([]))
    wrapped = pipeline._maybe_sandbox(["echo", "hi"], "/w")
    assert wrapped[0] == "docker"
    assert "myimg" in wrapped
    assert wrapped[-2:] == ["echo", "hi"]
