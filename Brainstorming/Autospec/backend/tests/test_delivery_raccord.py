"""Raccord metatests mock only trusted native ports; no product qualification."""
import json
from pathlib import Path

import pytest

from autospec.contracts import import_contract
from autospec.orchestrator.dependencies import atomic_json
from autospec.validation import delivery_raccord as module
from autospec.validation.final_gate import source_snapshot
from autospec.validation.support_adapter import AdapterUnavailable


def roots(tmp_path, requirement="OPS-01"):
    source=tmp_path/"source";source.mkdir()
    (source/"main.py").write_text("# untrusted inert source; never import on host\n")
    contract=import_contract("Reproducible delivery.",f"| {requirement} | M / X | Actual delivery observation |",
        reviewed_by="offline raccord metatest")
    root=tmp_path/"supervisor";root.mkdir()
    return source,source_snapshot(source).digest,contract,root


async def test_actual_failed_build_is_published_without_fake_image_or_acceptance(tmp_path,monkeypatch):
    source,snapshot,contract,root=roots(tmp_path)
    calls=[]
    # A synthetic reviewed binding isolates command provenance mechanics, not
    # an actual product's external-source approval.
    from types import SimpleNamespace
    from autospec.validation import product_harness
    atomic_json(root/"product-bindings.json",{})
    class Binding:
        @staticmethod
        def from_dict(value):
            return SimpleNamespace(snapshot_hash=snapshot,contract_hash=contract.contract_hash,
                runtime_command=("python","main.py"),validate=lambda source: None)
    monkeypatch.setattr(product_harness,"ReviewedProductBindings",Binding)
    def build(product,tag,**options):
        calls.append((product,tag,options))
        atomic_json(options["evidence_root"]/"delivery-build.json",dict(version=1,status="FAIL",
            snapshot_hash=snapshot,image_id=None,commands=[],error="synthetic native rc2"))
        return False,"withheld synthetic build output"
    monkeypatch.setattr(module,"build_delivery_image",build)
    result=await module.collect_native_delivery_build(contract,source,snapshot,root)
    assert result["status"]=="OBTAINED" and result["receipt"]["status"]=="FAIL"
    assert result["checks"][0]["passed"] is False
    assert result["proof"]["type"]=="X" and result["proof"]["passed"] is True
    assert len(calls)==1 and calls[0][2]["snapshot_hash"]==snapshot
    assert calls[0][2]["evidence_root"].is_relative_to(root)
    value=await module.SupervisorEvidenceStore(root,snapshot,contract.contract_hash).observe("delivery_build")
    assert value==result["receipt"] and source_snapshot(source).digest==snapshot


async def test_fact_collection_retains_unknown_native_ports_without_fabricating_success(tmp_path,monkeypatch):
    source,snapshot,contract,root=roots(tmp_path,"TST-01")
    async def absent(*args,**kwargs): raise AdapterUnavailable("synthetic native port absent")
    monkeypatch.setattr(module,"collect_native_quality",absent)
    result=await module.collect_native_final_facts(None,contract,source,snapshot,root)
    assert result["status"]=="PARTIAL" and "AdapterUnavailable" in result["limits"][0]
    assert "quality" not in result and "documentation" not in result and "timings" not in result


async def test_cancelled_native_collection_propagates(tmp_path,monkeypatch):
    import asyncio
    source,snapshot,contract,root=roots(tmp_path,"TST-01")
    async def cancelled(*args,**kwargs): raise asyncio.CancelledError()
    monkeypatch.setattr(module,"collect_native_quality",cancelled)
    with pytest.raises(asyncio.CancelledError): await module.collect_native_final_facts(None,contract,source,snapshot,root)


async def test_source_drift_never_builds_or_publishes_native_facts(tmp_path,monkeypatch):
    source,snapshot,contract,root=roots(tmp_path)
    (source/"main.py").write_text("# changed source\n")
    monkeypatch.setattr(module,"build_delivery_image",lambda *args,**kw: pytest.fail("stale source executed"))
    with pytest.raises(AdapterUnavailable): await module.collect_native_delivery_build(contract,source,snapshot,root)
    assert not (root/"observations.json").exists()


async def test_snapshot_without_ops_does_not_build_an_unrequested_image(tmp_path,monkeypatch):
    source,snapshot,contract,root=roots(tmp_path,"BOOK-01")
    monkeypatch.setattr(module,"build_delivery_image",lambda *args,**kw: pytest.fail("unrequired image build"))
    assert (await module.collect_native_delivery_build(contract,source,snapshot,root))["status"]=="NOT_REQUIRED"


@pytest.mark.parametrize("gap", ["clock", "provenance", "cancelled"])
async def test_build_clock_gap_preserves_actual_x_but_not_provenance_or_cancellation(tmp_path, monkeypatch, gap):
    import asyncio
    from types import SimpleNamespace
    from autospec.validation import product_harness
    source,snapshot,contract,root=roots(tmp_path)
    atomic_json(root/"product-bindings.json",{})
    binding=SimpleNamespace(snapshot_hash=snapshot,contract_hash=contract.contract_hash,
        runtime_command=("/opt/venv/bin/python","main.py"),validate=lambda _: None)
    monkeypatch.setattr(product_harness,"ReviewedProductBindings",
        SimpleNamespace(from_dict=lambda _: binding))
    def build(_,tag,**options):
        atomic_json(options["evidence_root"]/"delivery-build.json",dict(version=1,status="PASS",
            snapshot_hash=snapshot,image_id="sha256:"+"a"*64,commands=[]))
        return True,"synthetic clock protocol only"
    monkeypatch.setattr(module,"build_delivery_image",build)
    monkeypatch.setattr(module,"delivery_build_checks",lambda *args: [{"passed":True}])
    class Recorder:
        def ingest_delivery(self,*args,**kwargs):
            if gap=="clock": raise module.NativeTimingUnavailable("clock absent")
            if gap=="provenance": raise AdapterUnavailable("contradictory raw proof")
            raise asyncio.CancelledError()
    if gap=="clock":
        result=await module.collect_native_delivery_build(contract,source,snapshot,root,timing_recorder=Recorder())
        assert result["status"]=="PARTIAL" and result["limits"]
        assert result["receipt"]["status"]=="PASS" and result["proof"]["type"]=="X"
    else:
        with pytest.raises(AdapterUnavailable if gap=="provenance" else asyncio.CancelledError):
            await module.collect_native_delivery_build(contract,source,snapshot,root,timing_recorder=Recorder())
    observed=await module.SupervisorEvidenceStore(root,snapshot,contract.contract_hash).observe("delivery_build")
    assert observed["status"]=="PASS"  # actual native fact, not acceptance
    assert source_snapshot(source).digest==snapshot


@pytest.mark.parametrize("cache_change", [None,"missing_context","seal","engine","report_bytes"])
async def test_pipeline_calls_native_collection_before_independent_final_gate(tmp_path,monkeypatch,cache_change):
    from autospec.agents.runner import FakeRunner
    from autospec.config import settings
    from autospec.orchestrator.pipeline import Pipeline
    from autospec.orchestrator import acceptance
    from autospec.models import ProjectState
    from autospec.storage import workspace_dir
    from autospec.validation import coordinator
    from tests.test_milestone_delivery_raccord import proof
    contract=import_contract("Stored book.","| BOOK-01 | B / X | Stored book. |",reviewed_by="offline ordering metatest")
    state=ProjectState(id="ordering-native",name="Books",goal=contract.brief,brief=contract.brief,acceptance_contract_hash=contract.contract_hash)
    acceptance.contract_store(state.id).save(contract)
    source=workspace_dir(state.id);source.mkdir(parents=True)
    (source/"main.py").write_text("# inert synthetic source\n")
    pipeline=Pipeline(state,FakeRunner())
    order=[]
    async def build(*args,**kwargs): order.append("build");return {"receipt":None}
    async def review(*args,**kwargs): order.append("review");return {"status":"REVIEWED"}
    async def facts(*args,**kwargs): order.append("native");return {"status":"PARTIAL","limits":["synthetic observation port"]}
    async def verify(state,contract,frozen,snapshot,root):
        order.append("judge")
        return [dict(contract_hash=contract.contract_hash,snapshot_hash=snapshot,requirements=[dict(
            id="BOOK-01",gate="B",expected=contract.requirements[0].expected,status="PASS",observed="synthetic ordering only",
            reproduction=["offline mocked port"],impact="none",limits=[],proofs=[proof(root,"X","BOOK-01:actual",snapshot,contract)])])]
    monkeypatch.setattr(module,"collect_native_delivery_build",build)
    monkeypatch.setattr(module,"collect_native_final_facts",facts)
    monkeypatch.setattr(pipeline,"_await_reviewed_configuration",review)
    monkeypatch.setattr(coordinator,"verify_project",verify)
    assert await pipeline._aindependent_acceptance_phase()
    assert order==["review","build","native","judge"] and not pipeline.runner.calls
    supervisor=acceptance.supervisor_root(state.id)
    digest=source_snapshot(source).digest
    reports_path=supervisor/"reports"/digest/"verification-reports.json"
    if cache_change=="missing_context":reports_path.with_name("verification-context.json").unlink()
    elif cache_change=="seal":atomic_json(supervisor/"reviewed-fixtures.json",{"scope":"inert metatest seal changed"})
    elif cache_change=="engine":
        from autospec.validation import final_gate
        context=final_gate.verification_cache_context
        monkeypatch.setattr(final_gate,"verification_cache_context",lambda *args:{**context(*args),"metatest_engine_revision":2})
    elif cache_change=="report_bytes":reports_path.write_bytes(reports_path.read_bytes()+b"\n")
    # Revalidate source-review engine/seals FIRST, even for an intact cache.
    assert await pipeline._aindependent_acceptance_phase()
    assert order==["review","build","native","judge"]+(["review","build","native","judge"] if cache_change else ["review"])
    assert len(list(reports_path.parent.glob("verification-reports-prior-*.json")))==int(bool(cache_change))


@pytest.mark.parametrize("qualifies,publish_enabled",[(True,True),(True,False),(False,True)])
async def test_current_contract_qualifies_before_any_publication_or_legacy_repair(tmp_path,monkeypatch,qualifies,publish_enabled):
    from autospec.agents.runner import FakeRunner
    from autospec.models import ProjectState
    from autospec.orchestrator.pipeline import Pipeline
    from autospec.orchestrator import policy
    pipeline=Pipeline(ProjectState(id="ordered-publication",name="meta",goal="meta",acceptance_contract_hash="a"*64),FakeRunner())
    order=[]
    async def smoke():order.append("smoke");return True
    async def runtime():order.append("runtime");return True
    def dod(**kwargs):order.append("dod");return True
    async def independent():order.append("independent");return qualifies
    async def publish():order.append("publish");return True
    monkeypatch.setattr(pipeline,"_asmoke_phase",smoke)
    monkeypatch.setattr(pipeline,"_aruntime_acceptance_phase",runtime)
    monkeypatch.setattr(pipeline,"_apply_definition_of_done",dod)
    monkeypatch.setattr(pipeline,"_aindependent_acceptance_phase",independent)
    monkeypatch.setattr(pipeline,"_adocker_delivery_phase",publish)
    monkeypatch.setattr(pipeline,"_setting",lambda name: publish_enabled if name=="docker_delivery" else None)
    monkeypatch.setattr(policy,"decide",lambda *a,**k:policy.Decision.ALLOW)
    assert await pipeline._adelivery_gates() is qualifies
    assert order==["smoke","runtime","dod","independent"]+(["publish"] if qualifies and publish_enabled else [])
    assert not pipeline.runner.calls


@pytest.mark.parametrize("fault",[None,"failed_reports","failed_image","wrong_command","stale_binding","source_drift"])
async def test_publication_re_admits_fresh_reports_and_exact_baked_command(tmp_path,monkeypatch,fault):
    from types import SimpleNamespace
    from autospec.validation import product_harness
    source,snapshot,contract,root=roots(tmp_path)
    atomic_json(root/"reports"/snapshot/"verification-reports.json",[])
    atomic_json(root/"product-bindings.json",{})
    command=["/opt/venv/bin/python","main.py"]
    class Binding:
        @staticmethod
        def from_dict(value):
            return SimpleNamespace(snapshot_hash="f"*64 if fault=="stale_binding" else snapshot,
                contract_hash=contract.contract_hash,runtime_command=tuple(command),validate=lambda source:None,
                internal_port=8000,local_cookie_mode=True,database_path="/var/lib/autospec-validation/support.sqlite",
                browser_routes={"health":"/api/health"},commands={})
    monkeypatch.setattr(product_harness,"ReviewedProductBindings",Binding)
    monkeypatch.setattr(module,"admit_reports",lambda *a,**k:SimpleNamespace(ready=fault!="failed_reports"))
    async def observe(*args,**kwargs):
        return dict(status="PASS",image_id="sha256:"+"c"*64,runtime_command=["bad"] if fault=="wrong_command" else command)
    monkeypatch.setattr(module.SupervisorEvidenceStore,"observe",observe)
    def checks(*args):
        if fault=="source_drift":(source/"main.py").write_text("# changed after initial admission\n")
        return [dict(passed=fault!="failed_image")]
    monkeypatch.setattr(module,"delivery_build_checks",checks)
    if fault is None:
        result=await module.load_qualified_delivery_image(contract,source,root)
        assert result==dict(image_id="sha256:"+"c"*64,snapshot_hash=snapshot,runtime_command=command,
            internal_port=8000,local_cookie_mode=True,database_path="/var/lib/autospec-validation/support.sqlite",
            health_path="/api/health",migration_command=None)
    else:
        with pytest.raises(AdapterUnavailable):await module.load_qualified_delivery_image(contract,source,root)


async def test_pipeline_qualified_publication_passes_complete_native_signature_and_preserves_identity(tmp_path, monkeypatch):
    import inspect
    from autospec.agents.runner import FakeRunner
    from autospec.models import ProjectState
    from autospec.orchestrator.pipeline import Pipeline
    from autospec.orchestrator import acceptance, docker_deploy
    state=ProjectState(id="qualified-real-signature",name="metatest",goal="meta",acceptance_contract_hash="a"*64)
    pipeline=Pipeline(state,FakeRunner())
    qualified=dict(image_id="sha256:"+"b"*64,snapshot_hash="c"*64,
        runtime_command=["/opt/venv/bin/python","main.py"],internal_port=8123,
        local_cookie_mode=True,database_path="/var/lib/autospec-validation/support.sqlite",
        health_path="/api/health",migration_command=["/opt/venv/bin/python","main.py","migrate"])
    async def load(*args):return qualified
    monkeypatch.setattr(module,"load_qualified_delivery_image",load)
    monkeypatch.setattr(pipeline,"_acceptance_contract",lambda: object())
    signature=inspect.signature(docker_deploy.deploy_and_verify)
    calls=[]
    def publish(*args,**kwargs):
        bound=signature.bind(*args,**kwargs)  # catch a missing required timeout, even with mocked Docker
        calls.append(bound.arguments)
        return docker_deploy.DockerDeployResult(True,"synthetic factory raccord only",
            image=qualified["image_id"],container="d"*64,host_port=19231)
    monkeypatch.setattr(docker_deploy,"deploy_and_verify",publish)
    assert await pipeline._adocker_qualified_delivery(tmp_path,kind="fullstack")
    assert calls[0]["publication_root"]==acceptance.supervisor_root(state.id)/"publication"
    assert calls[0]["publication_contract_hash"]==state.acceptance_contract_hash
    assert calls[0]["publication_internal_port"]==8123 and calls[0]["network"]=="none"
    assert calls[0]["publication_migration_command"]==qualified["migration_command"]
    assert state.deploy_status=="deployed" and state.deployed_container=="d"*64 and state.deploy_host_port==19231
    assert not pipeline.runner.calls


async def test_contract_stop_and_factory_start_recovery_use_owned_registry_only(tmp_path, monkeypatch):
    from autospec.agents.runner import FakeRunner
    from autospec.models import ProjectState
    from autospec.orchestrator.pipeline import Pipeline
    from autospec.orchestrator import acceptance, docker_deploy
    state=ProjectState(id="registry-raccord",name="metatest",goal="meta",acceptance_contract_hash="a"*64,
        deployed_container="b"*64,deployed_image="sha256:"+"c"*64,deploy_host_port=19321,deploy_status="deployed")
    pipeline=Pipeline(state,FakeRunner());root=acceptance.supervisor_root(state.id)/"publication";calls=[]
    def status(project_id,*,publication_root):
        calls.append(("status",project_id,publication_root))
        return docker_deploy.DockerDeployResult(False,"synthetic absent ingress",container=state.deployed_container)
    def recover(project_id,publication_root,*,timeout,intended_active_only,cancel_event):
        assert intended_active_only is True
        assert cancel_event is pipeline._docker_cancel
        calls.append(("recover",project_id,publication_root))
        if not state.deployed_container:
            return docker_deploy.DockerDeployResult(False,"synthetic intentionally stopped journal",skipped=True)
        return docker_deploy.DockerDeployResult(True,"synthetic recovered ingress",
            image=state.deployed_image,container=state.deployed_container,host_port=19321)
    def stop(project_id,*,publication_root):
        calls.append(("stop",project_id,publication_root))
        return docker_deploy.DockerDeployResult(True,"synthetic stop, DB retained")
    monkeypatch.setattr(docker_deploy,"inspect_deployment",status)
    monkeypatch.setattr(docker_deploy,"recover_publication",recover)
    monkeypatch.setattr(docker_deploy,"undeploy",stop)
    await pipeline.arecover_publication()
    assert state.deploy_status=="deployed" and state.deployed_container=="b"*64
    await pipeline.aundeploy()
    assert state.deployed_container=="" and state.deploy_status=="" and state.deploy_host_port==0
    await pipeline.arecover_publication()  # intentional stop must not be revived
    assert calls==[("status",state.id,root),("recover",state.id,root),("stop",state.id,root),
        ("status",state.id,root),("recover",state.id,root)]
