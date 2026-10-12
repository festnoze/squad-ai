"""Factory lifecycle admission tests; no generated source executes on host."""
import pytest

from autospec.agents.runner import FakeRunner
from autospec.models import ProjectState
from autospec.orchestrator import docker_deploy
from autospec.orchestrator.pipeline import Pipeline
from autospec.validation import delivery_raccord


@pytest.mark.parametrize("status", ["stopped", "destroyed", "failed", "uncertain", None])
def test_startup_never_revives_non_active_publication_journal(tmp_path, monkeypatch, status):
    from autospec.orchestrator import owned_publication
    class Registry:
        def __init__(self, root):pass
        def status(self, project):return {"registered":status is not None,"status":status}
        def recover(self, *args, **kwargs):pytest.fail("non-active publication must not restart")
    monkeypatch.setattr(owned_publication,"PublicationRegistry",Registry)
    result=docker_deploy.recover_publication("synthetic-project",tmp_path,intended_active_only=True)
    assert not result.ok and result.skipped is (status in {"stopped","destroyed",None})


async def test_crash_after_running_journal_before_state_flush_recovers_owned_cid(tmp_path, monkeypatch):
    state=ProjectState(id="crash-before-state-flush",name="meta",goal="meta",acceptance_contract_hash="a"*64)
    pipeline=Pipeline(state,FakeRunner());calls=[]
    def status(*args,**kwargs):return docker_deploy.DockerDeployResult(False,"owned ingress lost")
    def recover(*args,**kwargs):
        assert kwargs["intended_active_only"] is True
        calls.append(args)
        return docker_deploy.DockerDeployResult(True,"exact owned journal recovered",image="sha256:"+"b"*64,
            container="c"*64,host_port=19231)
    monkeypatch.setattr(docker_deploy,"inspect_deployment",status)
    monkeypatch.setattr(docker_deploy,"recover_publication",recover)
    await pipeline.arecover_publication()
    assert len(calls)==1 and state.deployed_container=="c"*64 and state.deploy_status=="deployed"
    assert state.deploy_host_port==19231 and not pipeline.runner.calls


@pytest.mark.parametrize("cancel_after_return", [False, True])
async def test_failed_update_preserves_previous_service_but_cancel_removes_new_owned_runtime(tmp_path, monkeypatch, cancel_after_return):
    previous="" if cancel_after_return else "c"*64
    state=ProjectState(id="owned-attempt",name="meta",goal="meta",acceptance_contract_hash="a"*64,
        deployed_container=previous,deployed_image="sha256:"+"d"*64 if previous else "",
        deploy_host_port=19232 if previous else 0)
    pipeline=Pipeline(state,FakeRunner());calls=[]
    qualified=dict(image_id="sha256:"+"e"*64,snapshot_hash="f"*64,runtime_command=["/opt/venv/bin/python","main.py"],
        internal_port=8000,local_cookie_mode=True,database_path="/var/lib/autospec-validation/support.sqlite",
        health_path="/api/health",migration_command=None)
    async def load(*args):return qualified
    monkeypatch.setattr(delivery_raccord,"load_qualified_delivery_image",load)
    monkeypatch.setattr(pipeline,"_acceptance_contract",lambda:object())
    def publish(*args,**kwargs):
        if cancel_after_return:pipeline._stop_requested=True
        return docker_deploy.DockerDeployResult(cancel_after_return,"synthetic refused update or late cancel",
            image=qualified["image_id"],container="b"*64 if cancel_after_return else "",host_port=19300)
    def stop(*args,**kwargs):calls.append((args,kwargs));return docker_deploy.DockerDeployResult(True,"owned DB retained")
    monkeypatch.setattr(docker_deploy,"deploy_and_verify",publish)
    monkeypatch.setattr(docker_deploy,"undeploy",stop)
    assert not await pipeline._adocker_qualified_delivery(tmp_path,kind="fullstack")
    assert state.deployed_container==previous and state.deploy_status=="failed" and not state.delivery_ready
    assert state.deployed_image==("sha256:"+"d"*64 if previous else "")
    assert state.deploy_host_port==(19232 if previous else 0) and len(calls)==int(cancel_after_return)
