"""Typed JSON round-trip probes; not native product quality evidence."""
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import pytest

from autospec.validation.coordinator import SupervisorEvidenceStore,_quality_seal
from autospec.validation.quality_contracts import NativeSuiteSpec,write_quality_review_package
from autospec.validation.final_gate import source_snapshot
from autospec.validation.support_adapter import AdapterUnavailable,Proof


@pytest.fixture
def seal(tmp_path):
    source=tmp_path/"source";source.mkdir();(source/"main.py").write_bytes(b"# independent JSON protocol fixture only\n")
    snapshot=source_snapshot(source).digest;root=tmp_path/"supervisor"
    contract=SimpleNamespace(contract_hash="c"*64,brief_hash="b"*64,reference_hash="d"*64,requirements=[])
    package=write_quality_review_package(contract,product_root=source,destination=root/"quality",snapshot_hash=snapshot,
        suites=(NativeSuiteSpec("backend",".","python",("main.py",),("metatest",)),),
        requirements_mapping={},nominal_security_db_mocks=False)
    path=root/"protocol-review.json";path.write_text(json.dumps(dict(scope="Synthetic format review, not product evidence")))
    review=Proof("R",str(path),hashlib.sha256(path.read_bytes()).hexdigest(),snapshot,contract.contract_hash,tuple(package["required_review_checks"]))
    plan=Path(package["plan_path"])
    return source,SupervisorEvidenceStore(root,snapshot,contract.contract_hash),dict(path=str(plan),sha256=hashlib.sha256(plan.read_bytes()).hexdigest(),review=asdict(review))


def test_native_quality_spec_json_lists_restore_tuple_without_changing_seal(seal):
    from pathlib import Path
    source,store,value=seal;before=value.copy()
    assert _quality_seal(store,value,source).type=="R"
    assert value==before and hashlib.sha256(Path(value["path"]).read_bytes()).hexdigest()==value["sha256"]


@pytest.mark.parametrize("fault",["suites_string","inventory_string","domains_dict","selectors_string","selector_boolean","inventory_boolean","domain_integer","extra_field","unknown_suite","duplicate_suite"])
def test_native_quality_json_rejects_bad_types_and_extra_fields(seal,fault):
    from pathlib import Path
    source,store,value=seal;path=Path(value["path"]);data=json.loads(path.read_bytes());row=data["suites"][0]
    if fault=="suites_string":data["suites"]="backend"
    elif fault=="inventory_string":row["source_inventory"]="main.py"
    elif fault=="domains_dict":row["domains"]={"metatest":True}
    elif fault=="selectors_string":row["test_args"]="--all"
    elif fault=="selector_boolean":row["test_args"]=[True]
    elif fault=="inventory_boolean":row["source_inventory"]=[True]
    elif fault=="domain_integer":row["domains"]=[42]
    elif fault=="extra_field":row["pass_anyway"]=True
    elif fault=="unknown_suite":row["name"]="invented"
    elif fault=="duplicate_suite":data["suites"].append(row.copy())
    path.write_text(json.dumps(data));value["sha256"]=hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(AdapterUnavailable,match="typed native|distinct native"):_quality_seal(store,value,source)
