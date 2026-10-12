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


async def test_pipeline_calls_native_collection_before_independent_final_gate(tmp_path,monkeypatch):
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
    assert order==["build","review","native","judge"] and not pipeline.runner.calls
    # Cached intact independent evidence is readmitted without executing again.
    assert await pipeline._aindependent_acceptance_phase() and len(order)==4
