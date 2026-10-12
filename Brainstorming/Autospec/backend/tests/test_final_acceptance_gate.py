import hashlib
import json
from dataclasses import asdict

import pytest

from autospec.contracts import ContractFact, import_contract
from autospec.validation.final_gate import admit_reports, freeze_snapshot, source_snapshot


def source():
    return import_contract("Books: title 2..12", "| BOOK-01 | B / X+R | title 2..12 |\n| BOOK-02 | D / X | measure latency |",
        reviewed_by="reviewer", facts=[ContractFact.create("title", "bounds", [2, 12], ["BOOK-01"], "title 2..12")])


def setup_report(tmp_path):
    contract = source()
    snapshot = "a" * 64
    evidence = tmp_path / "supervisor"
    evidence.mkdir()
    rows = []
    for requirement in contract.requirements:
        proofs = []
        for kind in requirement.required_evidence:
            path = evidence / f"{requirement.id}-{kind}.json"
            path.write_text(json.dumps({"requirement_id": requirement.id, "checks": {"boundaries": True}}))
            proofs.append({"type": kind, "path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "snapshot_hash": snapshot, "contract_hash": contract.contract_hash,
                "checks": [f"{requirement.id}:boundaries"], "passed": True})
        rows.append({"id": requirement.id, "gate": requirement.gate, "expected": requirement.expected,
            "status": "PASS", "observed": "executed boundaries", "reproduction": ["run probe"],
            "proofs": proofs, "impact": "none", "limits": []})
    report = {"snapshot_hash": snapshot, "contract_hash": contract.contract_hash, "requirements": rows}
    return contract, report, snapshot, evidence


def test_only_complete_identity_bound_proofs_admit_delivery(tmp_path):
    contract, report, snapshot, evidence = setup_report(tmp_path)
    result = admit_reports(contract, [report], snapshot_hash=snapshot, evidence_root=evidence)
    assert result.ready and result.status == "PASS" and len(result.requirements) == 2
    report["requirements"][1]["status"] = "FAIL"
    assert admit_reports(contract, [report], snapshot_hash=snapshot, evidence_root=evidence).ready
    report["requirements"][0]["status"] = "FAIL"
    assert admit_reports(contract, [report], snapshot_hash=snapshot, evidence_root=evidence).status == "FAIL"


@pytest.mark.parametrize("problem", ["no_proof", "type", "hash", "snapshot", "contract", "empty_checks",
    "unrelated_checks", "outside_root", "borrowed_fixture", "missing_field", "expected", "gate", "missing", "duplicate", "extra", "report_identity"])
def test_false_green_proofs_and_incomplete_reports_are_not_verified(tmp_path, problem):
    contract, report, snapshot, evidence = setup_report(tmp_path)
    row = report["requirements"][0]
    proof = row["proofs"][0]
    if problem == "no_proof": row["proofs"] = []
    elif problem == "type": proof["type"] = "V"
    elif problem == "hash": proof["sha256"] = "b" * 64
    elif problem == "snapshot": proof["snapshot_hash"] = "b" * 64
    elif problem == "contract": proof["contract_hash"] = "b" * 64
    elif problem == "empty_checks": proof["checks"] = []
    elif problem == "unrelated_checks": proof["checks"] = ["OTHER-01:boundaries"]
    elif problem == "outside_root":
        path = tmp_path / "producer-proof.json"
        path.write_text("forged")
        proof.update(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    elif problem == "borrowed_fixture": proof["detail"] = "oracle-fixture validation only, not product acceptance"
    elif problem == "missing_field": del row["observed"]
    elif problem == "expected": row["expected"] = "title 1..20"
    elif problem == "gate": row["gate"] = "D"
    elif problem == "missing": report["requirements"] = report["requirements"][1:]
    elif problem == "duplicate": report["requirements"].append(dict(row))
    elif problem == "extra": report["requirements"].append(dict(row, id="OTHER-01"))
    elif problem == "report_identity": report["snapshot_hash"] = "b" * 64
    result = admit_reports(contract, [report], snapshot_hash=snapshot, evidence_root=evidence)
    assert not result.ready and result.status == "NOT_VERIFIED"
    assert result.requirements[0]["status"] == "NOT_VERIFIED"


def test_actual_failure_not_relabelled_green_or_missing_evidence(tmp_path):
    contract, report, snapshot, evidence = setup_report(tmp_path)
    report["requirements"][0].update(status="FAIL", proofs=[])
    result = admit_reports(contract, [report], snapshot_hash=snapshot, evidence_root=evidence)
    assert result.status == "FAIL" and result.requirements[0]["status"] == "FAIL"


def test_selected_vertical_milestone_never_requires_unrelated_diagnostic(tmp_path):
    contract, report, snapshot, evidence = setup_report(tmp_path)
    report["requirements"] = report["requirements"][:1]
    result = admit_reports(contract, [report], snapshot_hash=snapshot, evidence_root=evidence, required_ids={"BOOK-01"})
    assert result.ready and [row["id"] for row in result.requirements] == ["BOOK-01"]
    with pytest.raises(ValueError):
        admit_reports(contract, [report], snapshot_hash=snapshot, evidence_root=evidence, required_ids={"OTHER-01"})


def test_freeze_preserves_code_identity_excludes_runtime_and_never_repairs_source(tmp_path):
    root = tmp_path / "producer"
    root.mkdir()
    (root / "main.py").write_text("print('support')")
    (root / "pyproject.toml").write_text("[project]\nname='support'\nversion='0.1.0'\n")
    (root / "autospec-state.json").write_text("private harness state")
    (root / ".autospec-bootstrap.json").write_text('{"template":"fastapi-sqlite-react"}')
    (root / ".autospec-environment.json").write_text("private environment receipt")
    (root / "acceptance-contract.json").write_text("private oracle")
    (root / "data.db").write_bytes(b"fictitious isolated runtime database")
    (root / ".env").write_text("SENTINEL_SECRET=value")
    (root / ".claude").mkdir()
    (root / ".claude/settings.json").write_text("harness metadata")
    before = source_snapshot(root)
    snapshot, frozen = freeze_snapshot(root, tmp_path / "supervisor")
    assert snapshot == before and source_snapshot(frozen).digest == snapshot.digest
    assert not (frozen / ".env").exists() and not (frozen / "data.db").exists()
    assert not (frozen / ".autospec-bootstrap.json").exists()
    assert not (frozen / "acceptance-contract.json").exists()
    assert (root / ".env").read_text() == "SENTINEL_SECRET=value"
    assert (root / "main.py").read_text() == "print('support')"
    (frozen / "main.py").write_text("altered")
    with pytest.raises(ValueError, match="modified"):
        freeze_snapshot(root, tmp_path / "supervisor")


def test_snapshot_store_inside_product_and_empty_product_refused(tmp_path):
    root = tmp_path / "producer"
    root.mkdir()
    with pytest.raises(ValueError, match="empty"):
        source_snapshot(root)
    (root / "main.py").write_text("pass")
    with pytest.raises(ValueError, match="outside"):
        freeze_snapshot(root, root / "hidden")
