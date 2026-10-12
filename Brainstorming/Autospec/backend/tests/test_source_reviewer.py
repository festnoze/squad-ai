"""Offline reviewer boundary tests; no provider/network/product execution.

Fake review responses test admission mechanics, never attest a real product.
"""
import hashlib
import json
import shutil
from dataclasses import asdict

import pytest

from autospec.contracts import ContractFact, import_contract
from autospec.orchestrator.dependencies import atomic_json
from autospec.validation.final_gate import source_snapshot
from autospec.validation.source_reviewer import (ensure_reviewed_configuration, expand_fixture_inputs,
    source_bundle, validate_citations, ReviewPending)
from autospec.validation.support_adapter import AdapterUnavailable
from tests.test_product_harness import ROOT, fixture_definition, make_bindings


def setup(tmp_path):
    source=tmp_path/"product";shutil.copytree(ROOT,source)
    snapshot=source_snapshot(source).digest
    brief="Five fictional actors and twelve tickets require independent authentication."
    contract=import_contract(brief,"| SAMPLE-01 | B / X+R | Authentication required |",reviewed_by="offline test",
        facts=[ContractFact.create("auth","security_profile",{},["SAMPLE-01"],brief)])
    control=tmp_path/"supervisor"
    binding=asdict(make_bindings(control,source,snapshot))
    for key in ("snapshot_hash","contract_hash","source_files","review","fixture_fingerprint"):binding.pop(key)
    candidate={"source_files":["main.py","pyproject.toml","uv.lock"],"bindings":binding}
    cases={"VERTICAL":{},"SAMPLE-01":{},**{f"E2E-{n:02d}":{} for n in range(1,7)}}
    proposal={"candidate":candidate,"fixtures":{"base_fixture":fixture_definition(),"cases":cases}}
    citation={"file":"main.py","start":1,"end":1,"reason":"offline mechanical source citation"}
    review={"bindings":{"approved":True,"citations":[citation],"findings":[]},
        "fixtures":{"approved":True,"citations":[citation],"findings":[]},
        "requirements":[{"id":"SAMPLE-01","status":"PASS","citations":[citation],"reason":"source-only offline metatest"}],
        "test_mapping":{"SAMPLE-01":{"backend":["test_auth.py::test_login"],"frontend":[]}}}
    return source,snapshot,contract,control,proposal,review


def test_source_bundle_hash_bound_and_never_truncated(tmp_path):
    source,snapshot,_,_,_,_=setup(tmp_path)
    bundle=source_bundle(source,snapshot)
    assert bundle["files"]["main.py"]["sha256"]==hashlib.sha256((source/"main.py").read_bytes()).hexdigest()
    assert bundle["files"]["uv.lock"]["text"] is None
    with pytest.raises(AdapterUnavailable):source_bundle(source,"0"*64)
    with pytest.raises(AdapterUnavailable,match="bounded"):source_bundle(source,snapshot,max_chars=2)


@pytest.mark.parametrize("citation",[[],[{"file":"missing.py","start":1,"end":1,"reason":"x"}],
    [{"file":"main.py","start":0,"end":1,"reason":"x"}],
    [{"file":"uv.lock","start":1,"end":1,"reason":"x"}],
    [{"file":"main.py","start":True,"end":1,"reason":"x"}]])
def test_positive_source_review_cannot_cite_absent_or_unsupplied_text(tmp_path,citation):
    source,snapshot,_,_,_,_=setup(tmp_path)
    with pytest.raises(AdapterUnavailable):validate_citations(citation,source_bundle(source,snapshot))


def test_unknown_fixture_case_has_no_nominal_fallback():
    with pytest.raises(AdapterUnavailable):expand_fixture_inputs({"base_fixture":{},"cases":{"VERTICAL":{}}},{"VERTICAL","SEC-01"})
    assert expand_fixture_inputs({"base_fixture":{"accounts":{},"metadata":{"x":1}},"cases":{"VERTICAL":{"metadata":{"x":2}}}},{"VERTICAL"})["cases"]["VERTICAL"]["metadata"]=={"x":2}


def external_response(control, snapshot, contract, filename, answer, agent):
    atomic_json(control/"source-reviews"/snapshot/filename, {
        "snapshot_hash":snapshot,"contract_hash":contract.contract_hash,
        "model":"gpt-6.1-sol","reasoning":"medium","agent_id":agent,"answer":answer})


async def admit_proposal(source, snapshot, contract, control, proposal):
    with pytest.raises(ReviewPending) as pending:
        await ensure_reviewed_configuration(contract,source,snapshot,control)
    assert pending.value.stage=="operational_proposal"
    packet=json.loads((control/"source-reviews"/snapshot/"review-request.json").read_bytes())
    assert packet["packet"]["oracle"]["brief"]==contract.brief
    assert packet["required_model"]=="gpt-6.1-sol"
    external_response(control,snapshot,contract,"proposal-response.json",proposal,"offline-proposer")
    with pytest.raises(ReviewPending) as pending:
        await ensure_reviewed_configuration(contract,source,snapshot,control)
    assert pending.value.stage=="independent_review"
    return json.loads((control/"source-reviews"/snapshot/"review-request.json").read_bytes())


async def test_two_different_external_agents_install_only_intact_reviewed_facts(tmp_path):
    source,snapshot,contract,control,proposal,review=setup(tmp_path)
    before=source_snapshot(source)
    packet=await admit_proposal(source,snapshot,contract,control,proposal)
    assert "INDEPENDENT" in packet["system_prompt"]
    external_response(control,snapshot,contract,"independent-response.json",review,"offline-reviewer")
    result=await ensure_reviewed_configuration(contract,source,snapshot,control)
    assert result["status"]=="REVIEWED"
    index=json.loads((control/"proofs.json").read_bytes())
    assert {p["type"] for proofs in index["proofs"].values() for p in proofs}=={"R"}
    assert source_snapshot(source)==before
    cached=await ensure_reviewed_configuration(contract,source,snapshot,control)
    assert cached["cached"]


@pytest.mark.parametrize("problem",["rejected","self_approve","bad_citation","unknown_id","missing_id","source_drift","wrong_model","wrong_reasoning"])
async def test_rejected_review_cannot_publish_configuration(tmp_path,problem):
    source,snapshot,contract,control,proposal,review=setup(tmp_path)
    await admit_proposal(source,snapshot,contract,control,proposal)
    if problem=="rejected":review["bindings"]["approved"]=False
    elif problem=="bad_citation":review["fixtures"]["citations"]=[]
    elif problem=="unknown_id":review["requirements"][0]["id"]="UNKNOWN-01"
    elif problem=="missing_id":review["requirements"]=[]
    elif problem=="source_drift":(source/"main.py").write_text("changed")
    external_response(control,snapshot,contract,"independent-response.json",review,
                      "offline-proposer" if problem=="self_approve" else "offline-reviewer")
    response_path=control/"source-reviews"/snapshot/"independent-response.json"
    if problem in {"wrong_model","wrong_reasoning"}:
        response=json.loads(response_path.read_bytes())
        response["model" if problem=="wrong_model" else "reasoning"]="claude" if problem=="wrong_model" else "low"
        atomic_json(response_path,response)
    with pytest.raises(AdapterUnavailable):await ensure_reviewed_configuration(contract,source,snapshot,control)
    assert not (control/"product-bindings.json").exists()
