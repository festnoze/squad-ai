"""Cancellation receipt counterproof; only a trusted inert worker thread runs."""
import asyncio
import threading

import pytest

from autospec.agents.runner import FakeRunner
from autospec.config import settings
from autospec.models import ProjectState
from autospec.orchestrator import docker_deploy
from autospec.orchestrator.pipeline import Pipeline
from autospec.validation import delivery_raccord

pytestmark = pytest.mark.asyncio


async def test_cancelled_contract_publication_is_drained_before_outer_task_returns(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workspace_root", tmp_path / "workspace")
    pipeline = Pipeline(ProjectState(id="cancel-meta", name="meta", goal="no generation",
        acceptance_contract_hash="a" * 64), FakeRunner())
    monkeypatch.setattr(pipeline, "_sync", lambda: None)
    monkeypatch.setattr(pipeline, "_acceptance_contract", lambda: object())
    started, release, finished = threading.Event(), threading.Event(), threading.Event()
    async def load(*args):
        return dict(image_id="sha256:"+"b"*64, snapshot_hash="c"*64,
            runtime_command=["/opt/venv/bin/python","main.py"], internal_port=8000,
            local_cookie_mode=True, database_path="/var/lib/autospec-validation/support.sqlite",
            health_path="/api/health", migration_command=None)
    def publish(*args, **kwargs):
        started.set()
        assert release.wait(5), "trusted worker release deadline"
        finished.set()
        return docker_deploy.DockerDeployResult(False, "cancelled inert worker", cancelled=True)
    async def run(*args, **kwargs):
        return await pipeline._adocker_qualified_delivery(tmp_path, kind="fullstack")
    monkeypatch.setattr(delivery_raccord, "load_qualified_delivery_image", load)
    monkeypatch.setattr(docker_deploy, "deploy_and_verify", publish)
    monkeypatch.setattr(docker_deploy, "release_host_port", lambda *args: None)
    monkeypatch.setattr(pipeline, "_adocker_delivery_run", run)
    task = asyncio.create_task(pipeline._adocker_delivery_phase(force=True))
    try:
        assert await asyncio.to_thread(started.wait, 2)
        task.cancel()
        await asyncio.sleep(.1)
        assert not task.done(), "outer cancellation returned while publication worker was still running"
        assert pipeline._docker_cancel.is_set()
    finally:
        release.set()
        try:
            await task
        except asyncio.CancelledError:
            pass
        assert await asyncio.to_thread(finished.wait, 2)
