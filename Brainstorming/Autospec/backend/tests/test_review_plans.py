"""Offline plan-admission mechanics, not qualification of a real product."""
import copy
import hashlib
import json

import pytest

from autospec.validation.final_gate import source_snapshot
from autospec.validation.review_plans import (parse_quality_candidate, prepare_quality_plan,
    seal_quality_plan, load_reviewed_quality_plan)
from autospec.validation.source_reviewer import expand_fixture_inputs
from autospec.validation.support_adapter import AdapterUnavailable
from tests.test_source_reviewer import setup


def candidate():
    return {"suites": [{"name": "backend", "root": ".", "ecosystem": "python",
        "source_inventory": ["main.py"], "domains": ["auth"], "test_args": [], "coverage_source": "."}],
        "requirements_mapping": {"SAMPLE-01": [{"suite": "backend", "test": "test_login.py::test_login",
            "assertion": "offline inspected assertion descriptor"}]}, "mutation": None,
        "nominal_security_db_mocks": False, "e2e_mode": "native"}


@pytest.mark.parametrize("bad", ["duplicate", "absolute", "string_inventory", "unknown", "fake_boolean", "double_e2e"])
def test_malformed_quality_plan_cannot_become_review_authority(bad):
    value=candidate()
    if bad=="duplicate": value["suites"]*=2
    elif bad=="absolute": value["suites"][0]["root"]="/outside"
    elif bad=="string_inventory": value["suites"][0]["source_inventory"]="main.py"
    elif bad=="unknown": value["unexpected"]="not admitted"
    elif bad=="fake_boolean": value["nominal_security_db_mocks"]=0
    elif bad=="double_e2e": value["suites"][0]["name"]="e2e";value["e2e_mode"]="supervisor_browser"
    with pytest.raises(AdapterUnavailable): parse_quality_candidate(value)


async def test_quality_subject_requires_review_and_rejects_mapping_drift(tmp_path):
    source,identity,contract,control,proposal,_=setup(tmp_path)
    fixtures=expand_fixture_inputs(proposal["fixtures"],{"VERTICAL"})
    subject=await prepare_quality_plan(candidate(),candidate=proposal["candidate"],fixtures=fixtures,
        contract=contract,source=source,snapshot=identity,destination=control/"review-package")
    with pytest.raises(AdapterUnavailable): load_reviewed_quality_plan(contract,source,identity,control)
    with pytest.raises(AdapterUnavailable): await seal_quality_plan(subject,{"approved":False},
        contract=contract,source=source,snapshot=identity,supervisor_root=control)
    await seal_quality_plan(subject,{"approved":True,"scope":"synthetic mechanics only"},
        contract=contract,source=source,snapshot=identity,supervisor_root=control)
    sealed=load_reviewed_quality_plan(contract,source,identity,control)
    assert sealed["review"].type=="R" and sealed["mutant_snapshot_hash"] is None
    sealed["mapping_path"].write_text("{}")
    with pytest.raises(AdapterUnavailable): load_reviewed_quality_plan(contract,source,identity,control)


async def test_mutation_review_profile_uses_real_copy_hash_and_preserves_nominal(tmp_path):
    source,_,contract,control,proposal,_=setup(tmp_path)
    source_file=source/"main.py"
    source_file.write_bytes(source_file.read_bytes()+b"\n# unique offline auth mutation anchor\n")
    identity=source_snapshot(source).digest;before=source_file.read_bytes()
    value=candidate()
    value["mutation"]={"path":"main.py","original_sha256":hashlib.sha256(before).hexdigest(),
        "before":"# unique offline auth mutation anchor","after":"# changed owned-copy anchor"}
    subject=await prepare_quality_plan(value,candidate=proposal["candidate"],
        fixtures=expand_fixture_inputs(proposal["fixtures"],{"VERTICAL"}),contract=contract,
        source=source,snapshot=identity,destination=control/"review-package")
    mutant=subject["package"]["mutation_source"]["snapshot_hash"]
    assert mutant!=identity and subject["package"]["mutation_configuration"]["snapshot_hash"]==mutant
    assert source_file.read_bytes()==before
    await seal_quality_plan(subject,{"approved":True,"scope":"synthetic source mechanics, no runtime acceptance"},
        contract=contract,source=source,snapshot=identity,supervisor_root=control)
    sealed=load_reviewed_quality_plan(contract,source,identity,control)
    binding=json.loads((sealed["mutant_supervisor_root"]/"product-bindings.json").read_bytes())
    assert binding["snapshot_hash"]==mutant and binding["review"]["snapshot_hash"]==mutant
    assert source_file.read_bytes()==before and source_snapshot(source).digest==identity
