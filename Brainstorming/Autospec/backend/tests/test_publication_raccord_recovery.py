"""Factory lifecycle admission tests; no generated source executes on host."""
import pytest

from autospec.agents.runner import FakeRunner
from autospec.models import ProjectState
from autospec.orchestrator import docker_deploy
from autospec.orchestrator.pipeline import Pipeline
from autospec.orchestrator import acceptance
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


@pytest.mark.parametrize("kind", ["cli", "library"])
async def test_contract_package_uses_exact_journal_even_after_crash_before_state_flush(tmp_path, monkeypatch, kind):
    state = ProjectState(id="package-crash-"+kind, name="meta", goal="meta",
        acceptance_contract_hash="a"*64, technical_stack={"kind":kind})
    pipeline = Pipeline(state, FakeRunner())
    root = acceptance.supervisor_root(state.id)/"packages"
    calls = []
    def inspect(project_id, *, packaging_root):
        assert packaging_root == root
        calls.append(("inspect",project_id))
        return docker_deploy.DockerDeployResult(True,"journal-attested synthetic package",
            image="sha256:"+"b"*64,packaged=True)
    def stop(project_id, *, packaging_root):
        assert packaging_root == root
        calls.append(("detach",project_id))
        return docker_deploy.DockerDeployResult(True,"only owned alias detached",packaged=True)
    monkeypatch.setattr(docker_deploy,"inspect_packaged_image",inspect)
    monkeypatch.setattr(docker_deploy,"inspect_deployment",lambda *a,**k:pytest.fail("package entered web/legacy inspection"))
    monkeypatch.setattr(docker_deploy,"recover_publication",lambda *a,**k:pytest.fail("package started web runtime"))
    monkeypatch.setattr(docker_deploy,"undeploy",stop)
    await pipeline.arecover_publication()
    await pipeline.areconcile_deploy()
    assert state.deploy_status=="packaged" and state.deployed_image=="sha256:"+"b"*64
    assert not state.deployed_container and state.deploy_host_port==0
    await pipeline.aundeploy()
    assert calls==[("inspect",state.id),("detach",state.id)] and not state.deploy_status
    assert not state.deployed_image and not pipeline.runner.calls


async def test_contract_web_with_empty_cid_never_uses_legacy_removal(tmp_path, monkeypatch):
    state = ProjectState(id="web-before-state-flush", name="meta", goal="meta",
        acceptance_contract_hash="a"*64, technical_stack={"kind":"fullstack"})
    pipeline = Pipeline(state, FakeRunner())
    def stop(project_id, *, publication_root):
        assert publication_root==acceptance.supervisor_root(state.id)/"publication"
        return docker_deploy.DockerDeployResult(True,"exact owned journal stopped")
    monkeypatch.setattr(docker_deploy,"undeploy",stop)
    await pipeline.aundeploy()
    assert not state.deploy_status and not pipeline.runner.calls


@pytest.mark.parametrize("new_alias", [True, False])
async def test_late_package_cancel_detaches_only_a_fresh_call_alias(tmp_path, monkeypatch, new_alias):
    import inspect
    state = ProjectState(id="package-late-cancel", name="meta", goal="meta",
        acceptance_contract_hash="a"*64, technical_stack={"kind":"cli"})
    pipeline = Pipeline(state, FakeRunner())
    qualified = dict(image_id="sha256:"+"b"*64,snapshot_hash="c"*64,
        runtime_command=["/opt/venv/bin/python","main.py"])
    async def load(*args):return qualified
    monkeypatch.setattr(delivery_raccord,"load_qualified_delivery_image",load)
    monkeypatch.setattr(pipeline,"_acceptance_contract",lambda:object())
    signature=inspect.signature(docker_deploy.deploy_and_verify)
    alias="autospec/meta:qualified-"+"d"*32
    calls=[]
    def package(*args,**kwargs):
        signature.bind(*args,**kwargs)
        assert kwargs["packaging_root"]==acceptance.supervisor_root(state.id)/"packages"
        assert not any(k.startswith("publication_") for k in kwargs)
        pipeline._stop_requested=True
        return docker_deploy.DockerDeployResult(True,"synthetic package",image=qualified["image_id"],
            packaged=True,created_package_alias=alias if new_alias else "")
    def stop(project_id, *, packaging_root, expected_package_alias, expected_package_image_id):
        assert project_id==state.id and packaging_root==acceptance.supervisor_root(state.id)/"packages"
        assert expected_package_alias==alias and expected_package_image_id==qualified["image_id"]
        calls.append(alias)
        return docker_deploy.DockerDeployResult(True,"only new alias detached",packaged=True)
    monkeypatch.setattr(docker_deploy,"deploy_and_verify",package)
    monkeypatch.setattr(docker_deploy,"undeploy",stop)
    assert not await pipeline._adocker_qualified_delivery(tmp_path,kind="cli")
    assert calls==([alias] if new_alias else [])
    assert state.deploy_status=="failed" and not state.delivery_ready and not pipeline.runner.calls
