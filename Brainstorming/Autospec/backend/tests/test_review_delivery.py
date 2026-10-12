"""Offline seal/admission metatests; synthetic X/R are not product proof."""
import hashlib
import json
from dataclasses import asdict

import pytest

from autospec.contracts import ContractFact, import_contract
from autospec.orchestrator.dependencies import atomic_json
from autospec.validation.final_gate import source_snapshot
from autospec.validation.support_adapter import AdapterUnavailable, Proof
from autospec.validation import review_delivery as module
from autospec.validation.delivery_evidence import REQUIRED_DOC_OBLIGATIONS
from tests.test_source_reviewer import setup as source_setup, external_response


async def setup(tmp_path, monkeypatch, *, unavailable=False, contract_override=None):
    source, _, _, root, proposal, review = source_setup(tmp_path)
    (source / "README.md").write_text("# Synthetic offline mapping\npython main.py migrate_fresh\npytest -q\n")
    (source / "config.py").write_text("# Offline metatest configuration, no actual credentials\n")
    snapshot = source_snapshot(source).digest
    contract = import_contract("Independent authentication; reproducible delivery.",
        "| OPS-05 | M / X+R | Reproducible documentation and advisory audit |",
        reviewed_by="offline seal metatest", facts=[ContractFact.create("auth", "security_profile", {},
            ["OPS-05"], "Independent authentication; reproducible delivery.")])
    if contract_override is not None:
        contract = contract_override
    raw_path = root / "synthetic-audit-raw.json"
    atomic_json(raw_path, {"scope": "synthetic offline protocol fixture; no actual auditor run"})
    raw_proof = Proof("X", str(raw_path), hashlib.sha256(raw_path.read_bytes()).hexdigest(),
        snapshot, contract.contract_hash, ("OBS:audit_raw",))
    calls = []
    async def collect(*args):
        calls.append(args)
        return dict(status="UNAVAILABLE" if unavailable else "AVAILABLE", findings=[],
            artifacts=[asdict(raw_proof)], report_valid=not unavailable,
            return_code=None if unavailable else 0, limits=["synthetic offline protocol fixture"])
    monkeypatch.setattr(module, "collect_manifest_audit", collect)
    await module.obtain_review_audit(contract, source, snapshot, root)
    commands = [dict(label="migration", obligation="migration", execution="runtime",
        documented_text="python main.py migrate_fresh", argv=["python", "main.py", "migrate_fresh"],
        action="migrate_fresh", parameters={})]
    for obligation in sorted(REQUIRED_DOC_OBLIGATIONS - {"migration"}):
        commands.append(dict(label=obligation, obligation=obligation, execution="isolated_command",
            documented_text="pytest -q", argv=["pytest", "-q"], root=".", ecosystem="python"))
    candidate = dict(readme="README.md", configuration=["config.py"], commands=commands,
        migration_label="migration", fixture_case="OPS-05")
    citation = dict(file="config.py", start=1, end=1,
        reason="Synthetic mechanical approval only; not real product qualification")
    delivery = dict(approved=True, citations=[citation], findings=[], configuration_assessments={
        "config.py": dict(source_sha256=hashlib.sha256((source / "config.py").read_bytes()).hexdigest(), secrets_found=[])})
    audit = dict(approved=True, citations=[citation], assessments=[])
    subject = await module.prepare_delivery_subject(candidate, fixtures_fingerprint="a" * 64,
        contract=contract, source=source, snapshot=snapshot, supervisor_root=root)
    delivery["subject_fingerprint"] = subject["proposal"]["fingerprint"]
    audit["subject_fingerprint"] = subject["audit_subject"]
    return source, snapshot, contract, root, candidate, delivery, audit, calls, proposal, review


async def test_exact_delivery_subject_and_raw_audit_are_scoped_independent_R_only(tmp_path, monkeypatch):
    source, snapshot, contract, root, candidate, delivery, audit, calls, *_ = await setup(tmp_path, monkeypatch)
    before = source_snapshot(source)
    subject = await module.prepare_delivery_subject(candidate, fixtures_fingerprint="a" * 64,
        contract=contract, source=source, snapshot=snapshot, supervisor_root=root)
    assert subject["proposal"]["status"] == "AWAITING_INDEPENDENT_REVIEW"
    result = await module.seal_delivery_subject(subject, delivery, audit, contract=contract,
        source=source, snapshot=snapshot, supervisor_root=root)
    cached = module.load_reviewed_delivery_plan(contract, source, snapshot, root)
    assert cached["plan"].fingerprint == result["plan"].fingerprint
    assert [p.type for p in cached["proofs"]] == ["R", "R"]
    assert source_snapshot(source) == before and len(calls) == 1


@pytest.mark.parametrize("fault", ["rejected", "missing_citation", "false_citation", "configuration_hash", "missing_assessment", "source_drift", "raw_drift", "different_delivery", "different_audit"])
async def test_delivery_rejection_or_drift_cannot_install_operational_plan(tmp_path, monkeypatch, fault):
    source, snapshot, contract, root, candidate, delivery, audit, *_ = await setup(tmp_path, monkeypatch)
    subject = await module.prepare_delivery_subject(candidate, fixtures_fingerprint="a" * 64,
        contract=contract, source=source, snapshot=snapshot, supervisor_root=root)
    if fault == "rejected": delivery["approved"] = False
    elif fault == "missing_citation": audit["citations"] = []
    elif fault == "false_citation": delivery["citations"][0]["start"] = True
    elif fault == "configuration_hash": delivery["configuration_assessments"]["config.py"]["source_sha256"] = "0" * 64
    elif fault == "missing_assessment": delivery["configuration_assessments"] = {}
    elif fault == "source_drift": (source / "config.py").write_text("# drift\n")
    elif fault == "raw_drift": (root / "synthetic-audit-raw.json").write_text("{}")
    elif fault == "different_delivery": delivery["subject_fingerprint"]="0"*64
    elif fault == "different_audit": audit["subject_fingerprint"]="0"*64
    with pytest.raises(AdapterUnavailable):
        await module.seal_delivery_subject(subject, delivery, audit, contract=contract,
            source=source, snapshot=snapshot, supervisor_root=root)
    assert not (root / "reviewed-delivery-plan.json").exists()


@pytest.mark.parametrize("fault", ["plan", "classified", "raw"])
async def test_cached_source_plan_never_bypasses_changed_assessment(tmp_path, monkeypatch, fault):
    source, snapshot, contract, root, candidate, delivery, audit, *_ = await setup(tmp_path, monkeypatch)
    subject = await module.prepare_delivery_subject(candidate, fixtures_fingerprint="a" * 64,
        contract=contract, source=source, snapshot=snapshot, supervisor_root=root)
    await module.seal_delivery_subject(subject, delivery, audit, contract=contract,
        source=source, snapshot=snapshot, supervisor_root=root)
    if fault == "plan":
        value = json.loads((root / "reviewed-delivery-plan.json").read_bytes())
        value["commands"][1]["argv"] = ["invented"]
        atomic_json(root / "reviewed-delivery-plan.json", value)
    elif fault == "classified":
        value = json.loads((root / "reviewed-dependency-audit.json").read_bytes())
        value["audit"]["report_valid"] = False
        atomic_json(root / "reviewed-dependency-audit.json", value)
    else:
        (root / "synthetic-audit-raw.json").write_text("{}")
    with pytest.raises(AdapterUnavailable): module.load_reviewed_delivery_plan(contract, source, snapshot, root)


async def test_unavailable_audit_is_not_upgraded_and_cache_does_not_requery(tmp_path, monkeypatch):
    source, snapshot, contract, root, candidate, delivery, audit, calls, *_ = await setup(tmp_path, monkeypatch, unavailable=True)
    assert (await module.obtain_review_audit(contract, source, snapshot, root))["status"] == "UNAVAILABLE"
    subject = await module.prepare_delivery_subject(candidate, fixtures_fingerprint="a" * 64,
        contract=contract, source=source, snapshot=snapshot, supervisor_root=root)
    result = await module.seal_delivery_subject(subject, delivery, audit, contract=contract,
        source=source, snapshot=snapshot, supervisor_root=root)
    assert result["audit"]["report_valid"] is False and result["audit"]["return_code"] is None
    assert len(calls) == 1


async def test_full_review_requires_delivery_and_distinct_audit_assessment(tmp_path, monkeypatch):
    from autospec.validation.source_reviewer import ensure_reviewed_configuration, ReviewPending
    source, snapshot, contract, root, candidate, delivery, audit, _, proposal, review = await setup(tmp_path, monkeypatch)
    proposal["delivery_plan"] = candidate
    proposal["fixtures"]["cases"] = {"VERTICAL": {}, "OPS-05": {}, **{f"E2E-{n:02d}": {} for n in range(1, 7)}}
    review["requirements"] = [dict(id="OPS-05", status="NOT_VERIFIED", citations=[], reason="Offline protocol mechanics only")]
    review["test_mapping"] = {}
    review.update(delivery=delivery, audit=audit)
    with pytest.raises(ReviewPending): await ensure_reviewed_configuration(contract, source, snapshot, root)
    packet = json.loads((root / "source-reviews" / snapshot / "review-request.json").read_bytes())
    assert packet["packet"]["native_dependency_audit"]["limits"] == ["synthetic offline protocol fixture"]
    external_response(root, snapshot, contract, "proposal-response.json", proposal, "offline-proposer")
    with pytest.raises(ReviewPending) as pending: await ensure_reviewed_configuration(contract, source, snapshot, root)
    assert pending.value.stage == "independent_review"
    request = json.loads((root / "source-reviews" / snapshot / "review-request.json").read_bytes())
    delivery["subject_fingerprint"] = request["packet"]["delivery_proposal"]["proposal"]["fingerprint"]
    audit["subject_fingerprint"] = request["packet"]["delivery_proposal"]["audit_subject"]
    external_response(root, snapshot, contract, "independent-response.json", review, "offline-distinct-reviewer")
    await ensure_reviewed_configuration(contract, source, snapshot, root)
    index = json.loads((root / "proofs.json").read_bytes())
    assert len(index["proofs"]["OPS-05"]) == 2
    assert all(p["type"] == "R" for p in index["proofs"]["OPS-05"])
