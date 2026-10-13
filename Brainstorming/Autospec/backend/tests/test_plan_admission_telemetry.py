import hashlib
import json
from dataclasses import replace

import pytest
from autospec.orchestrator import plan_admission_telemetry
from autospec.orchestrator.plan_admission_telemetry import public_plan_admission
from autospec.orchestrator.plan_gates import PlanAdmission

BASE = PlanAdmission("fail", "a"*64, ("lots must be explicit_groups, not a posteriori task/story counts",))


def project(admission=BASE, **kwargs):
    fields = dict(response_sha256="b"*64, response_bytes=123, capture_complete=True)
    fields.update(kwargs)
    return public_plan_admission(admission, **fields)


def test_exact_identity_and_version_without_raw_candidate():
    value = project(receipt_sha256="c"*64)
    assert value["candidate_sha256"] == "b"*64 and value["contract_hash"] == "a"*64
    assert value["receipt_sha256"] == "c"*64
    assert value["version"] == value["admission_version"] == 1
    assert value["reason"] == "constraint_rejected"
    assert value["diagnostics"][0]["code"] == "lot_definition"
    assert value["diagnostics"][0]["diagnostic_sha256"] == hashlib.sha256(BASE.errors[0].encode()).hexdigest()


@pytest.mark.parametrize("message", ["contract coverage missing: SECRET_PASSWORD full brief text",
    "confirmed major finding unresolved: SECRET_PASSWORD", "SECRET_PASSWORD: stream root is undeclared: full brief text",
    "SECRET_PASSWORD <script>alert(1)</script> /private/path"])
def test_interpolated_maker_text_never_leaves_boundary(message):
    raw = json.dumps(project(replace(BASE, errors=(message,))), ensure_ascii=False)
    for text in ["SECRET_PASSWORD", "full brief", "<script>", "/private/path"]:
        assert text not in raw
    assert "response" not in json.loads(raw) and "planning_context" not in json.loads(raw)


def test_bounded_deduplicated_diagnostics_counts_and_fingerprints():
    admission = replace(BASE, errors=tuple("contract coverage missing: ID"+str(i) for i in range(100)))
    value = project(admission)
    assert len(value["diagnostics"]) == 64 and value["diagnostics_omitted"] == 36
    assert value["diagnostic_counts"] == {"coverage": 100}
    assert len(json.dumps(value).encode()) < 16000
    assert len(project(replace(BASE, errors=BASE.errors*100))["diagnostics"]) == 1
    assert project(replace(BASE, warnings=("arbitrary maker warning",)))["diagnostics"][-1]["severity"] == "warning"


@pytest.mark.parametrize(("message", "expected"), [
    ("maker JSON invalid or extraction failed", "plan_json"),
    ("maker plan exceeds bounded capture/parse limit", "candidate_limit"),
    ("lots must be explicit_groups, not inferred", "lot_definition"),
    ("9 explicit lots exceeds maximum 7", "lot_limit"),
    ("contract coverage missing: PRIVATE_REQUIREMENT", "coverage"),
    ("contract invariant differs or missing: PRIVATE_FACT", "source_invariant"),
    ("plan stack differs from frozen decision", "stack"),
    ("vertical_contract does not map all checks", "vertical_contract"),
    ("milestone order is invalid", "milestone"),
    ("dependency request unresolved: PRIVATE_PACKAGE", "dependency_pending"),
    ("dependency graph contains a cycle", "dependency_graph"),
    ("file claim escapes root: PRIVATE_PATH", "file_claims"),
    ("shared contract has unknown consumer: PRIVATE_ID", "shared_contract"),
    ("confirmed major finding remains unresolved: PRIVATE_TEXT", "unresolved_finding"),
    ("provider unavailable during required review", "review_unavailable"),
    ("plan ID must be unique", "plan_schema"),
    ("PRIVATE_TEXT arbitrary diagnostic", "other_constraint"),
])
def test_safe_reason_classification_is_complete_and_does_not_interpolate(message, expected):
    admission = replace(BASE, errors=(message,))
    value = project(admission)
    assert plan_admission_telemetry._code(message) == expected
    assert value["diagnostics"][0]["code"] == expected
    assert value["diagnostic_counts"] == {expected: 1}
    assert message not in json.dumps(value)


def test_missing_or_incomplete_capture_is_explicit():
    value = project(response_sha256=None, response_bytes=None, capture_complete=False)
    assert not value["candidate_available"] and not value["capture_complete"]
    value = project(response_bytes=2000000, capture_complete=False)
    assert value["candidate_available"] and not value["capture_complete"]


@pytest.mark.parametrize("admission", [replace(BASE, version=2), replace(BASE, version=True),
    replace(BASE, status="SECRET_PASSWORD"), replace(BASE, contract_hash="secret"), replace(BASE, lot_count=True),
    replace(BASE, errors=(None,)), replace(BASE, errors=("x",)*4097), replace(BASE, errors=("é"*40000,)),
    replace(BASE, status="pass")])
def test_malformed_unsupported_or_oversize_admission_refused(admission):
    with pytest.raises(ValueError): project(admission)


@pytest.mark.parametrize("fields", [dict(response_sha256="secret"), dict(receipt_sha256="A"*64),
    dict(response_bytes=True), dict(response_bytes=-1), dict(response_bytes=2**31),
    dict(response_sha256=None), dict(capture_complete=1)])
def test_invalid_capture_metadata_refused(fields):
    with pytest.raises(ValueError): project(**fields)


def test_plain_json_checkpoint_reload_and_no_provider_dependency(tmp_path):
    # Persistence belongs to the parent; demonstrate lossless safe state reload.
    payload = project()
    path = tmp_path/"checkpoint.json"
    path.write_text(json.dumps({"plan_admission": {"public_diagnostic": payload}}))
    assert json.loads(path.read_text())["plan_admission"]["public_diagnostic"] == payload
    assert project(replace(BASE, status="pass", errors=()))["reason"] == "pass"
    assert project(replace(BASE, status="not_verified", errors=()))["reason"] == "not_verified"
