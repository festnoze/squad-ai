"""Public pipeline lifecycle regression tests with a simulated Docker worker."""

import asyncio
import threading
import time

import pytest

from autospec.agents.runner import FakeRunner
from autospec.config import settings
from autospec.models import PipelinePhase, ProjectState, StoryStatus, UserStory
from autospec.orchestrator import docker_deploy, workspace
from autospec.orchestrator.docker_deploy import DockerDeployResult
from autospec.orchestrator.pipeline import Pipeline
from autospec.storage import workspace_dir


@pytest.fixture
def project(monkeypatch):
    monkeypatch.setattr(settings, "fake_agents", False)
    monkeypatch.setattr(settings, "docker_delivery", True)
    monkeypatch.setattr(settings, "integration_fix_attempts", 3)
    state = ProjectState(id="hardened", name="app", goal="g", phase=PipelinePhase.DONE)
    state.stories = [UserStory(id="US-1", epic_id="E", title="t", status=StoryStatus.DONE)]
    ws = workspace_dir(state.id)
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "main.py").write_text("import uvicorn\napp='fastapi'\nport=8000\n", encoding="utf-8")
    (ws / "pyproject.toml").write_text("[project]\nname='app'\ndependencies=['fastapi']\n", encoding="utf-8")
    monkeypatch.setattr(workspace, "scaffold", lambda state: ws)
    monkeypatch.setattr(docker_deploy, "docker_available", lambda: (True, ""))
    monkeypatch.setattr(docker_deploy, "allocate_host_port", lambda state: 18000)
    monkeypatch.setattr(Pipeline, "_sync", lambda self: None)
    async def snapshot(*args, **kwargs):
        return True
    async def git(*args, **kwargs):
        return 0, ""
    async def suite(*args, **kwargs):
        return True, "green", {}
    monkeypatch.setattr(Pipeline, "_agit_snapshot", snapshot)
    monkeypatch.setattr(Pipeline, "_agit", git)
    monkeypatch.setattr(Pipeline, "_arun_pytest", suite)
    return state


async def test_manual_deploy_reaches_worker_when_automatic_gate_is_off(project, monkeypatch):
    monkeypatch.setattr(settings, "docker_delivery", False)
    calls = []
    def deploy(*args, **kwargs):
        calls.append(kwargs)
        return DockerDeployResult(True, "done", image="image", container="container", host_port=18000)
    monkeypatch.setattr(docker_deploy, "deploy_and_verify", deploy)
    pipeline = Pipeline(project, FakeRunner([]))
    response = await pipeline.adeploy()
    assert response["deploy_started"]
    await asyncio.wait_for(pipeline._deploy_task, timeout=2)
    assert len(calls) == 1
    assert project.deploy_status == "deployed"


async def test_dispose_awaits_worker_cleanup_before_returning(project, monkeypatch):
    started = threading.Event()
    cleaned = threading.Event()
    def deploy(*args, cancel_event, **kwargs):
        started.set()
        assert cancel_event.wait(2)
        time.sleep(0.05)  # simulate bounded rollback, not a lingering orphan
        cleaned.set()
        return DockerDeployResult(False, "cancelled", cancelled=True)
    monkeypatch.setattr(docker_deploy, "deploy_and_verify", deploy)
    pipeline = Pipeline(project, FakeRunner([]))
    pipeline._deploy_task = asyncio.create_task(pipeline._adocker_delivery_phase(force=True))
    assert await asyncio.to_thread(started.wait, 2)
    await asyncio.wait_for(pipeline.adispose(), timeout=2)
    assert cleaned.is_set()
    assert pipeline._docker_worker.done()
    assert project.deploy_status == "failed"


async def test_infra_during_repair_stops_remaining_agent_attempts(project, monkeypatch):
    outputs = iter([
        DockerDeployResult(False, "application crashed"),
        DockerDeployResult(False, "daemon lost", infra=True),
    ])
    monkeypatch.setattr(docker_deploy, "deploy_and_verify", lambda *a, **k: next(outputs))
    runner = FakeRunner(["fixed"])
    pipeline = Pipeline(project, runner)
    assert not await pipeline._adocker_delivery_phase()
    assert len(runner.calls) == 1
    assert pipeline._delivery_blocked
    assert "daemon lost" in project.deploy_detail


async def test_failed_undeploy_preserves_resource_identity(project, monkeypatch):
    project.deploy_status = "deployed"
    project.deployed_image = "old-image"
    project.deployed_container = "old-container"
    project.deploy_host_port = 18042
    monkeypatch.setattr(docker_deploy, "undeploy", lambda project_id: DockerDeployResult(False, "daemon lost", infra=True))
    pipeline = Pipeline(project, FakeRunner([]))
    with pytest.raises(ValueError, match="non confirmé"):
        await pipeline.aundeploy()
    assert project.deployed_image == "old-image"
    assert project.deployed_container == "old-container"
    assert project.deploy_host_port == 18042


async def test_successful_undeploy_clears_all_fields(project, monkeypatch):
    project.deploy_status = "deployed"
    project.deployed_image = "old-image"
    project.deployed_container = "old-container"
    project.deploy_host_port = 18042
    monkeypatch.setattr(docker_deploy, "undeploy", lambda project_id: DockerDeployResult(True, "removed"))
    await Pipeline(project, FakeRunner([])).aundeploy()
    assert not project.deploy_status and not project.deployed_image and not project.deployed_container
    assert project.deploy_host_port == 0


async def test_reconciliation_clears_a_missing_container(project, monkeypatch):
    project.deploy_status = "deployed"
    project.deployed_container = "old-container"
    monkeypatch.setattr(docker_deploy, "inspect_deployment", lambda project_id: DockerDeployResult(False, "missing", skipped=True))
    await Pipeline(project, FakeRunner([])).areconcile_deploy()
    assert project.deploy_status == "" and project.deployed_container == ""


async def test_reconciliation_preserves_a_packaged_library(project, monkeypatch):
    project.deploy_status = "packaged"
    project.deployed_image = "old-image"
    monkeypatch.setattr(docker_deploy, "inspect_packaged_image", lambda project_id: DockerDeployResult(True, "exists", packaged=True, image="old-image"))
    def unexpected(*args, **kwargs):
        raise AssertionError("A library has no running container")
    monkeypatch.setattr(docker_deploy, "inspect_deployment", unexpected)
    await Pipeline(project, FakeRunner([])).areconcile_deploy()
    assert project.deploy_status == "packaged" and project.deployed_image == "old-image"


@pytest.mark.parametrize("kind", ["cli", "library", ""])
async def test_packaged_reconciliation_recovers_after_daemon_outage(project, monkeypatch, kind):
    project.deploy_status = "packaged"
    project.deployed_image = "old-image"
    project.technical_stack = {"kind": kind} if kind else {}
    outputs = iter([
        DockerDeployResult(False, "daemon lost", infra=True, packaged=True),
        DockerDeployResult(True, "exists", packaged=True, image="old-image"),
    ])
    monkeypatch.setattr(docker_deploy, "inspect_packaged_image", lambda project_id: next(outputs))
    def unexpected(*args, **kwargs):
        raise AssertionError("A failed image inspection must not become a container inspection")
    monkeypatch.setattr(docker_deploy, "inspect_deployment", unexpected)
    pipeline = Pipeline(project, FakeRunner([]))
    await pipeline.areconcile_deploy()
    assert project.deploy_status == "failed"
    assert project.deployed_image == "old-image"
    await pipeline.areconcile_deploy()
    assert project.deploy_status == "packaged"
    assert project.deployed_image == "old-image"


async def test_reconciliation_checks_image_identity_when_verdict_was_reset(project, monkeypatch):
    project.deployed_image = "old-image"
    project.deploy_status = ""
    monkeypatch.setattr(docker_deploy, "inspect_packaged_image", lambda project_id: DockerDeployResult(True, "exists", packaged=True, image="old-image"))
    await Pipeline(project, FakeRunner([])).areconcile_deploy()
    assert project.deploy_status == "packaged"


async def test_failed_web_reconciliation_keeps_inspecting_its_container(project, monkeypatch):
    project.deploy_status = "failed"
    project.deployed_image = "old-image"
    project.deployed_container = "old-container"
    project.deploy_host_port = 18042
    monkeypatch.setattr(docker_deploy, "inspect_deployment", lambda project_id: DockerDeployResult(True, "healthy", image="old-image", container="old-container", host_port=18042))
    def unexpected(*args, **kwargs):
        raise AssertionError("A web service must still be inspected as a running container")
    monkeypatch.setattr(docker_deploy, "inspect_packaged_image", unexpected)
    await Pipeline(project, FakeRunner([])).areconcile_deploy()
    assert project.deploy_status == "deployed"
