"""Independent stale approval probes; synthetic receipts confer no acceptance."""
import copy

import pytest

from autospec.orchestrator.dependencies import atomic_json
from autospec.validation.source_reviewer import _external_response, _request
from autospec.validation.support_adapter import AdapterUnavailable
from autospec.validation import review_delivery
from tests.test_review_delivery import setup


@pytest.mark.parametrize("change",["phase","stage","proposal","raw_audit","protocol"])
def test_review_response_cannot_cross_request_subject_at_same_source(tmp_path,change):
    snapshot="a"*64;oracle="c"*64
    request=_request("independent_review","trusted reviewed protocol",{
        "proposal":{"runtime_argv":["/opt/venv/bin/python","app.py"]},
        "native_dependency_audit":{"findings":[]}},snapshot,oracle,phase="final")
    path=tmp_path/"independent-response.json"
    atomic_json(path,dict(snapshot_hash=snapshot,contract_hash=oracle,model="gpt-6.1-sol",reasoning="medium",
        request_hash=request["request_hash"],stage=request["stage"],agent_id="independent-test-agent",answer={"approved":True}))
    assert _external_response(path,snapshot=snapshot,oracle=oracle,request=request,different_agent="proposer-test-agent")
    packet=copy.deepcopy(request["packet"]);phase="final";stage="independent_review";prompt=request["system_prompt"]
    if change=="phase":phase="vertical"
    elif change=="stage":stage="operational_proposal"
    elif change=="proposal":packet["proposal"]["runtime_argv"][-1]="other.py"
    elif change=="raw_audit":packet["native_dependency_audit"]["findings"]=[{"id":"added-unassessed"}]
    elif change=="protocol":prompt="changed trusted protocol"
    current=_request(stage,prompt,packet,snapshot,oracle,phase=phase)
    with pytest.raises(AdapterUnavailable,match="exact current phase/packet"):
        _external_response(path,snapshot=snapshot,oracle=oracle,request=current,different_agent="proposer-test-agent")


@pytest.mark.asyncio
async def test_source_exact_delivery_approval_cannot_be_resealed_for_changed_argv(tmp_path,monkeypatch):
    source,snapshot,contract,root,candidate,delivery,audit,*_=await setup(tmp_path,monkeypatch)
    original=await review_delivery.prepare_delivery_subject(candidate,fixtures_fingerprint="a"*64,
        contract=contract,source=source,snapshot=snapshot,supervisor_root=root)
    delivery["subject_fingerprint"]=original["proposal"]["fingerprint"]
    audit["subject_fingerprint"]=original["audit_subject"]
    changed=copy.deepcopy(candidate);changed["commands"][1]["argv"].append("--disable-warnings")
    current=await review_delivery.prepare_delivery_subject(changed,fixtures_fingerprint="a"*64,
        contract=contract,source=source,snapshot=snapshot,supervisor_root=root)
    assert current["proposal"]["fingerprint"]!=original["proposal"]["fingerprint"]
    with pytest.raises(AdapterUnavailable,match="exact delivery/audit subject"):
        await review_delivery.seal_delivery_subject(current,delivery,audit,
            contract=contract,source=source,snapshot=snapshot,supervisor_root=root)
    assert not (root/"reviewed-delivery-plan.json").exists()
