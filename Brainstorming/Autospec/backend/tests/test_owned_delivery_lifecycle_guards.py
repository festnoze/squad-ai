"""Independent counterexamples retained as factory regression guards.

Origin: REM-24 owned-delivery-counterreview. Effects are mocks/inert threads;
none of these tests imports or executes generated application source on host.
"""
import asyncio
import threading
from types import SimpleNamespace

import httpx
import pytest

from autospec.agents.runner import FakeRunner
from autospec.api import server
from autospec.models import ProjectState
from autospec.orchestrator import acceptance, docker_deploy
from autospec.orchestrator.pipeline import Pipeline
from autospec.validation import delivery_raccord


@pytest.mark.parametrize("kind", ["fullstack", "cli"])
@pytest.mark.parametrize("flushed", [False, True])
@pytest.mark.parametrize("live", [False, True])
async def test_delete_uses_both_owned_journals_before_workspace_removal(monkeypatch, kind, flushed, live):
    state = ProjectState(id="delete-meta", name="meta", goal="no generation",
        acceptance_contract_hash="a"*64, technical_stack={"kind":kind},
        deployed_image="sha256:"+"b"*64 if flushed else "")
    calls = []
    async def dispose():calls.append("dispose")
    pipeline = SimpleNamespace(state=state, adispose=dispose)
    monkeypatch.setattr(server,"pipelines",{state.id:pipeline} if live else {})
    monkeypatch.setattr(server,"load_state",lambda _id:state)
    monkeypatch.setattr(server.bus,"publish",lambda _event:None)
    def withdraw(project_id, **options):
        assert project_id==state.id and len(options)==1
        argument = next(iter(options))
        resource = "packages" if argument=="packaging_root" else "publication"
        assert argument in {"packaging_root","publication_root"}
        assert options[argument]==acceptance.supervisor_root(state.id)/resource
        calls.append(resource)
        return SimpleNamespace(ok=True, detail="owned synthetic receipt")
    monkeypatch.setattr(server.docker_deploy,"undeploy",withdraw)
    def remove(_id):
        assert "packages" in calls and "publication" in calls
        calls.append("workspace")
        return True
    monkeypatch.setattr(server,"_force_delete_workspace",remove)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app),base_url="http://test") as client:
        assert (await client.delete("/api/projects/"+state.id)).status_code==200
    expected = ["packages","publication"] if kind=="cli" else ["publication","packages"]
    assert calls==(["dispose"] if live else [])+expected+["workspace"]


@pytest.mark.parametrize("claimed", [False, True])
@pytest.mark.parametrize("detail", ["PUBLICATION_NOT_REGISTERED", "PUBLICATION_JOURNAL_INVALID", "daemon unavailable"])
async def test_delete_absence_only_safe_when_no_resource_claimed(monkeypatch, claimed, detail):
    state=ProjectState(id="delete-absence",name="meta",goal="meta",acceptance_contract_hash="a"*64,
        deployed_image="sha256:"+"b"*64 if claimed else "",technical_stack={"kind":"fullstack"})
    async def dispose():pass
    pipeline=SimpleNamespace(state=state,adispose=dispose)
    monkeypatch.setattr(server,"pipelines",{state.id:pipeline})
    removed=[]
    monkeypatch.setattr(server,"_force_delete_workspace",lambda _:removed.append(True) or True)
    monkeypatch.setattr(server.bus,"publish",lambda _:None)
    def stop(_id, **options):
        assert options
        return SimpleNamespace(ok=False,detail=detail if "publication_root" in options else "PACKAGE_NOT_REGISTERED")
    monkeypatch.setattr(server.docker_deploy,"undeploy",stop)
    safe=not claimed and detail=="PUBLICATION_NOT_REGISTERED"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app),base_url="http://test") as client:
        response=await client.delete("/api/projects/"+state.id)
    assert response.status_code==(200 if safe else 409)
    assert bool(removed)==safe
    if not safe:assert server.pipelines[state.id] is pipeline


@pytest.mark.parametrize("created", [False, True])
async def test_cancelled_publication_drains_worker_and_only_withdraws_created_receipt(tmp_path, monkeypatch, created):
    state=ProjectState(id="cancel-meta",name="meta",goal="no generation",acceptance_contract_hash="a"*64)
    pipeline=Pipeline(state,FakeRunner())
    monkeypatch.setattr(pipeline,"_sync",lambda:None)
    monkeypatch.setattr(pipeline,"_acceptance_contract",lambda:object())
    started,release,finished=threading.Event(),threading.Event(),threading.Event()
    async def load(*args):
        return dict(image_id="sha256:"+"b"*64,snapshot_hash="c"*64,runtime_command=["/opt/venv/bin/python","main.py"],
            internal_port=8000,local_cookie_mode=True,database_path="/var/lib/autospec-validation/support.sqlite",
            health_path="/api/health",migration_command=None)
    def publish(*args,**kwargs):
        started.set()
        assert release.wait(5)
        finished.set()
        return docker_deploy.DockerDeployResult(True,"inert receipt",container="d"*64,
            created_publication_container="d"*64 if created else "")
    withdrawn=[]
    def stop(_id,**options):
        assert options["expected_publication_container"]=="d"*64
        withdrawn.append(True)
        return docker_deploy.DockerDeployResult(True,"inert withdrawal")
    async def run(**kwargs):return await pipeline._adocker_qualified_delivery(tmp_path,kind="fullstack")
    monkeypatch.setattr(delivery_raccord,"load_qualified_delivery_image",load)
    monkeypatch.setattr(docker_deploy,"deploy_and_verify",publish)
    monkeypatch.setattr(docker_deploy,"undeploy",stop)
    monkeypatch.setattr(docker_deploy,"release_host_port",lambda _:None)
    monkeypatch.setattr(pipeline,"_adocker_delivery_run",run)
    task=asyncio.create_task(pipeline._adocker_delivery_phase(force=True))
    try:
        assert await asyncio.to_thread(started.wait,2)
        task.cancel()
        await asyncio.sleep(.05)
        task.cancel()  # A second interruption cannot evade the drainage guard.
        await asyncio.sleep(.05)
        assert not task.done() and pipeline._deployment_lock.locked()
        assert pipeline._docker_cancel.is_set()
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError):await task
        assert await asyncio.to_thread(finished.wait,2)
    assert withdrawn==([True] if created else [])
    assert not pipeline._deployment_lock.locked() and not state.delivery_ready


async def test_cancelled_startup_recovery_drains_thread_without_stopping_previous_cid(monkeypatch):
    state=ProjectState(id="recover-cancel",name="meta",goal="meta",acceptance_contract_hash="a"*64)
    pipeline=Pipeline(state,FakeRunner())
    monkeypatch.setattr(pipeline,"_sync",lambda:None)
    started,release=threading.Event(),threading.Event()
    monkeypatch.setattr(docker_deploy,"inspect_deployment",lambda *a,**k:docker_deploy.DockerDeployResult(False,"ingress lost"))
    def recover(*args,**kwargs):
        assert kwargs["cancel_event"] is pipeline._docker_cancel and kwargs["intended_active_only"]
        started.set()
        assert release.wait(5)
        return docker_deploy.DockerDeployResult(True,"old CID reattached",container="b"*64,host_port=19342)
    monkeypatch.setattr(docker_deploy,"recover_publication",recover)
    monkeypatch.setattr(docker_deploy,"undeploy",lambda *a,**k:pytest.fail("prior service deleted on startup cancellation"))
    task=asyncio.create_task(pipeline.arecover_publication())
    try:
        assert await asyncio.to_thread(started.wait,2)
        task.cancel()
        await asyncio.sleep(.05)
        task.cancel()
        await asyncio.sleep(.05)
        assert not task.done() and pipeline._deployment_lock.locked()
        assert pipeline._docker_cancel.is_set()
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError):await task
    assert state.deployed_container=="b"*64 and not pipeline._deployment_lock.locked()
