"""Exact-source delivery/audit subjects for two local, independent GPT agents.

The factory collects native advisory facts before the review. Neither a fact
proposal nor an approval is execution evidence, and unavailable audits stay NV.
No generation-provider call, product import or host product command exists here.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from ..agents.file_broker import ExecutionContext, FileBroker
from ..orchestrator.dependencies import atomic_json
from .delivery_evidence import (
    ReviewedDeliveryPlan, apply_audit_review, audit_review_subject,
    collect_manifest_audit, prepare_delivery_proposal,
)
from .final_gate import source_snapshot
from .support_adapter import AdapterUnavailable, Proof


def delivery_required(contract):
    return any(r.id == "OPS-05" for r in contract.requirements)


def _read(root, relative):
    path = FileBroker(ExecutionContext("sealed-delivery-review", root)).path(relative)
    if path.stat().st_size > 16_000_000:
        raise AdapterUnavailable("bounded delivery review exceeded")
    return json.loads(path.read_bytes())


def _proof(root, name, payload, snapshot, oracle, checks, kind="R"):
    path = root / "source-reviews" / snapshot / name
    atomic_json(path, payload)
    return Proof(kind, str(path), hashlib.sha256(path.read_bytes()).hexdigest(),
                 snapshot, oracle, tuple(checks), True,
                 "Native audit facts only" if kind == "X" else
                 "Independent source assessment only; no runtime acceptance")


def _intact(proof, root, snapshot, oracle, check, kind):
    path = Path(proof.path).absolute()
    if path.resolve() != path or not path.is_relative_to(root):
        raise AdapterUnavailable("delivery artifact outside supervisor")
    FileBroker(ExecutionContext("delivery-review-proof", root)).path(path.relative_to(root).as_posix())
    if proof.type != kind or not proof.passed or check not in proof.checks or not proof.intact(
            snapshot_hash=snapshot, contract_hash=oracle):
        raise AdapterUnavailable("exact intact delivery proof absent")


def _raw_audit(root, snapshot, oracle):
    value = _read(root, f"source-reviews/{snapshot}/raw-audit.json")
    if (value.get("snapshot_hash"), value.get("contract_hash")) != (snapshot, oracle):
        raise AdapterUnavailable("raw audit source identity differs")
    proof = Proof(**value["proof"])
    raw = value["audit"]
    _intact(proof, root, snapshot, oracle, "OBS:audit_inventory", "X")
    body = _read(root, Path(proof.path).relative_to(root).as_posix())
    if body.get("audit") != raw:
        raise AdapterUnavailable("native raw audit inventory changed")
    if not isinstance(raw, dict) or raw.get("status") not in {"AVAILABLE", "UNAVAILABLE"} or not isinstance(raw.get("findings"), list):
        raise AdapterUnavailable("typed native advisory inventory absent")
    artifacts = raw.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise AdapterUnavailable("native audit collection receipts absent")
    for item in artifacts:
        _intact(Proof(**item), root, snapshot, oracle, "OBS:audit_raw", "X")
    return raw


async def obtain_review_audit(contract, source, snapshot, supervisor_root):
    """Cache only an intact dated native collection, never model facts."""
    source, root = Path(source).resolve(), Path(supervisor_root).resolve()
    if root.is_relative_to(source) or source_snapshot(source).digest != snapshot:
        raise AdapterUnavailable("audit review needs exact frozen external roots")
    try:
        return _raw_audit(root, snapshot, contract.contract_hash)
    except (OSError, ValueError, KeyError, TypeError, AdapterUnavailable):
        raw = await collect_manifest_audit(source, snapshot, contract.contract_hash, root)
        proof = _proof(root, "native-audit-inventory.json", {"audit": raw}, snapshot,
                       contract.contract_hash, ["OBS:audit_inventory"], "X")
        atomic_json(root / "source-reviews" / snapshot / "raw-audit.json", {
            "snapshot_hash": snapshot, "contract_hash": contract.contract_hash,
            "audit": raw, "proof": asdict(proof)})
        return _raw_audit(root, snapshot, contract.contract_hash)


async def prepare_delivery_subject(candidate, *, fixtures_fingerprint, contract, source, snapshot, supervisor_root):
    root = Path(supervisor_root).resolve()
    proposal = await prepare_delivery_proposal(candidate, source_root=source,
        snapshot_hash=snapshot, contract_hash=contract.contract_hash,
        fixtures_fingerprint=fixtures_fingerprint)
    audit = _raw_audit(root, snapshot, contract.contract_hash)
    return {"proposal": proposal, "audit": audit, "audit_subject": audit_review_subject(audit)}


def _decision(decision, source):
    if not isinstance(decision, dict) or decision.get("approved") is not True:
        raise AdapterUnavailable("independent delivery/audit review rejected")
    citations = decision.get("citations")
    if not isinstance(citations, list) or not citations:
        raise AdapterUnavailable("delivery review needs substantive exact-source citations")
    broker = FileBroker(ExecutionContext("delivery-source-citation", source))
    for c in citations:
        if not isinstance(c, dict) or set(c) != {"file", "start", "end", "reason"}:
            raise AdapterUnavailable("invalid delivery citation")
        text = broker.path(c["file"]).read_text(encoding="utf-8")
        if (type(c["start"]) is not int or type(c["end"]) is not int
                or not 1 <= c["start"] <= c["end"] <= len(text.splitlines())
                or not isinstance(c["reason"], str) or not c["reason"].strip()):
            raise AdapterUnavailable("invalid delivery source citation range")


async def seal_delivery_subject(subject, delivery_decision, audit_decision, *, contract, source, snapshot, supervisor_root):
    """Install independently assessed operational facts, not X/V or a PASS."""
    root, source = Path(supervisor_root).resolve(), Path(source).resolve()
    _decision(delivery_decision, source)
    _decision(audit_decision, source)
    if source_snapshot(source).digest != snapshot:
        raise AdapterUnavailable("source changed during delivery review")
    raw = _raw_audit(root, snapshot, contract.contract_hash)
    if raw != subject["audit"] or audit_review_subject(raw) != subject["audit_subject"]:
        raise AdapterUnavailable("native audit subject changed during review")
    proposal = subject["proposal"]
    if (delivery_decision.get("subject_fingerprint"),audit_decision.get("subject_fingerprint")) != (
            proposal["fingerprint"],subject["audit_subject"]):
        raise AdapterUnavailable("independent approval does not name the exact delivery/audit subject")
    review = _proof(root, "delivery-plan-review.json", {
        "subject": proposal, "review": delivery_decision,
        "configuration_assessments": delivery_decision.get("configuration_assessments")},
        snapshot, contract.contract_hash, proposal["required_review_checks"])
    plan = ReviewedDeliveryPlan(proposal["plan"], review)
    if plan.fingerprint != proposal["fingerprint"]:
        raise AdapterUnavailable("delivery proposal fingerprint changed")
    plan.validate(source, root, snapshot, contract.contract_hash)
    audit_review = _proof(root, "audit-assessment-review.json", {
        "subject": subject["audit_subject"], "review": audit_decision,
        "assessments": audit_decision.get("assessments")},
        snapshot, contract.contract_hash, ["OPS-05:audit:" + subject["audit_subject"]])
    classified = apply_audit_review(raw, audit_review, evidence_root=root,
        snapshot_hash=snapshot, contract_hash=contract.contract_hash)
    atomic_json(root / "reviewed-delivery-plan.json", {**plan.data, "review": asdict(review)})
    atomic_json(root / "reviewed-dependency-audit.json", {"snapshot_hash": snapshot,
        "contract_hash": contract.contract_hash, "audit": classified})
    return {"plan": plan, "audit": classified, "proofs": [review, audit_review]}


def load_reviewed_delivery_plan(contract, source, snapshot, supervisor_root):
    root = Path(supervisor_root).resolve()
    try:
        plan = ReviewedDeliveryPlan.from_dict(_read(root, "reviewed-delivery-plan.json"))
        plan.validate(source, root, snapshot, contract.contract_hash)
        value = _read(root, "reviewed-dependency-audit.json")
        if (value.get("snapshot_hash"), value.get("contract_hash")) != (snapshot, contract.contract_hash):
            raise AdapterUnavailable("classified audit identity changed")
        raw = _raw_audit(root, snapshot, contract.contract_hash)
        classified = value["audit"]
        review = Proof(**classified["assessment_review"])
        recomputed = apply_audit_review(raw, review, evidence_root=root,
            snapshot_hash=snapshot, contract_hash=contract.contract_hash)
        if recomputed != classified:
            raise AdapterUnavailable("classified audit assessment changed")
        return {"plan": plan, "audit": classified, "proofs": [plan.review, review]}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise AdapterUnavailable("intact independently reviewed delivery facts unavailable") from exc
