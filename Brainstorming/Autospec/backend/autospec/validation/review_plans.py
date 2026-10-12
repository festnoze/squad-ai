"""Local exact-source quality plans sealed by a distinct external reviewer.

Preparing a candidate confers no authority. Mutation profiles name a real
filtered copy and its actual snapshot, never a synthetic acceptance identity.
"""
from __future__ import annotations

import hashlib
import json
import re
import tempfile
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path

from ..agents.file_broker import ExecutionContext, FileBroker
from ..orchestrator.dependencies import atomic_json
from ..orchestrator.validation_environment import snapshot_product
from .final_gate import source_snapshot
from .quality_contracts import (AuthorizationMutationSpec, NativeSuiteSpec,
    native_quality_plan_hash, write_quality_review_package)
from .support_adapter import AdapterUnavailable, Proof


QUALITY_FIELDS = {"suites", "requirements_mapping", "mutation",
                  "nominal_security_db_mocks", "e2e_mode"}


def quality_required(contract):
    return any(r.id.startswith("TST-") for r in contract.requirements)


def parse_quality_candidate(value):
    if not isinstance(value, dict) or set(value) != QUALITY_FIELDS:
        raise AdapterUnavailable("explicit native quality plan fields required")
    if (not isinstance(value["suites"], list) or not 1 <= len(value["suites"]) <= 3
            or type(value["nominal_security_db_mocks"]) is not bool
            or value["e2e_mode"] not in {"native", "supervisor_browser"}
            or not isinstance(value["requirements_mapping"], dict)):
        raise AdapterUnavailable("bounded native quality suites, mapping and mock declaration required")
    try:
        suites = []
        for row in value["suites"]:
            item = dict(row)
            for key in ("source_inventory", "domains", "test_args"):
                if key == "test_args" and key not in item: continue
                if not isinstance(item.get(key), list) or not all(isinstance(v, str) for v in item[key]):
                    raise ValueError("explicit string list required: " + key)
                item[key] = tuple(item[key])
            suites.append(NativeSuiteSpec(**item))
        if len({s.name for s in suites}) != len(suites): raise ValueError("duplicate suite")
        if value["e2e_mode"] == "supervisor_browser" and any(s.name == "e2e" for s in suites):
            raise ValueError("supervisor E2E cannot be double counted")
        mutation = AuthorizationMutationSpec(**value["mutation"]) if value["mutation"] is not None else None
    except (ValueError, TypeError) as exc:
        raise AdapterUnavailable("native quality candidate malformed") from exc
    return tuple(suites), mutation


@contextmanager
def _mutant(source, spec):
    """Exact UTF-8 replacement only in a fresh supervisor-owned filtered copy."""
    original = FileBroker(ExecutionContext("mutation-source-review", source)).path(spec.path).read_bytes()
    if hashlib.sha256(original).hexdigest() != spec.original_sha256 or original.decode("utf-8").count(spec.before) != 1:
        raise AdapterUnavailable("exact authorization mutation source/anchor differs")
    with tempfile.TemporaryDirectory(prefix="autospec-review-mutation-") as temporary:
        copy = snapshot_product(source, Path(temporary) / "product")
        target = FileBroker(ExecutionContext("mutation-owned-copy", copy)).path(spec.path)
        target.write_bytes(original.decode("utf-8").replace(spec.before, spec.after, 1).encode("utf-8"))
        yield copy, source_snapshot(copy).digest


async def prepare_quality_plan(value, *, candidate, fixtures, contract, source, snapshot, destination):
    from .coordinator import prepare_binding_proposal
    suites, mutation = parse_quality_candidate(value)
    if source_snapshot(source).digest != snapshot: raise AdapterUnavailable("quality proposal source drift")
    package = write_quality_review_package(contract, product_root=source, destination=destination,
        snapshot_hash=snapshot, suites=suites, requirements_mapping=value["requirements_mapping"],
        mutation=mutation, nominal_security_db_mocks=value["nominal_security_db_mocks"], e2e_mode=value["e2e_mode"])
    subject = json.loads(Path(package["plan_path"]).read_bytes())
    if mutation:
        with _mutant(source, mutation) as (copy, identity):
            proposed = await prepare_binding_proposal(candidate, fixtures, contract=contract,
                snapshot_root=copy, snapshot_hash=identity)
            subject["mutation_configuration"] = proposed
            subject["mutation_source"] = {"path": mutation.path, "before": mutation.before,
                "after": mutation.after, "sha256": hashlib.sha256((copy/mutation.path).read_bytes()).hexdigest(),
                "snapshot_hash": identity, "scope": "owned experimental copy; never product delivery"}
    return {"candidate": value, "package": subject}


def _receipt(path, payload, snapshot, oracle, checks):
    atomic_json(path, payload)
    return Proof("R", str(path), hashlib.sha256(path.read_bytes()).hexdigest(), snapshot, oracle,
        tuple(checks), True, "External independent exact-source plan approval; no runtime PASS issued")


async def seal_quality_plan(subject, decision, *, contract, source, snapshot, supervisor_root):
    from .coordinator import install_reviewed_configuration
    root = Path(supervisor_root).resolve()
    package = subject["package"]
    suites, mutation = parse_quality_candidate(subject["candidate"])
    if decision.get("approved") is not True: raise AdapterUnavailable("independent quality plan rejected")
    mapping = Path(package["mapping_path"]).resolve()
    if not mapping.is_relative_to(root): raise AdapterUnavailable("quality mapping outside supervisor")
    digest = native_quality_plan_hash(suites, mapping, mutation, e2e_mode=subject["candidate"]["e2e_mode"])
    if digest != package["plan_hash"] or source_snapshot(source).digest != snapshot:
        raise AdapterUnavailable("quality plan changed during review")
    checks = list(package["required_review_checks"])
    if subject["candidate"]["e2e_mode"] == "supervisor_browser": checks.append("TST-05:e2e_review")
    proof = _receipt(root/"source-reviews"/snapshot/"quality-plan-review.json",
        {"subject": subject, "review": decision}, snapshot, contract.contract_hash, checks)
    mutant_identity = None
    if mutation:
        proposal = package["mutation_configuration"]
        with _mutant(source, mutation) as (copy, mutant_identity):
            if mutant_identity != proposal["snapshot_hash"]: raise AdapterUnavailable("reviewed mutation copy drift")
            target = root/"mutation-profiles"/mutant_identity
            # The external quality approval explicitly covers the candidate
            # operational/fixture pair on these exact changed bytes.
            binding_r = _receipt(target/"binding-review.json", {"subject": proposal["bindings"], "review": decision},
                mutant_identity, contract.contract_hash, proposal["binding_checks"])
            fixture_r = _receipt(target/"fixture-review.json", {"subject": proposal["fixtures"], "review": decision},
                mutant_identity, contract.contract_hash, proposal["fixture_checks"])
            await install_reviewed_configuration(proposal, binding_review=binding_r, fixture_review=fixture_r,
                supervisor_root=target, snapshot_root=copy)
    atomic_json(root/"quality-plan.json", {"snapshot_hash": snapshot, "contract_hash": contract.contract_hash,
        "candidate": subject["candidate"], "mapping_path": str(mapping), "plan_hash": digest,
        "review": asdict(proof), "mutant_snapshot_hash": mutant_identity})
    return proof


def load_reviewed_quality_plan(contract, source_root, snapshot_hash, supervisor_root):
    root = Path(supervisor_root).resolve()
    broker = FileBroker(ExecutionContext("sealed-quality-plan", root))
    try:
        path = broker.path("quality-plan.json")
        if path.stat().st_size > 16_000_000: raise ValueError("bounded quality plan exceeded")
        value = json.loads(path.read_bytes())
        if (value["snapshot_hash"], value["contract_hash"]) != (snapshot_hash, contract.contract_hash):
            raise ValueError("quality plan identity changed")
        if source_snapshot(source_root).digest != snapshot_hash: raise ValueError("source changed")
        suites, mutation = parse_quality_candidate(value["candidate"])
        mapping = Path(value["mapping_path"]).resolve()
        if not mapping.is_relative_to(root): raise ValueError("mapping outside supervisor")
        mapping = broker.path(mapping.relative_to(root).as_posix())
        digest = native_quality_plan_hash(suites, mapping, mutation, e2e_mode=value["candidate"]["e2e_mode"])
        review = Proof(**value["review"])
        mutant = value["mutant_snapshot_hash"]
        if mutant is not None and (not isinstance(mutant, str) or not re.fullmatch(r"[a-f0-9]{64}", mutant)):
            raise ValueError("canonical mutant identity absent")
        if (digest != value["plan_hash"] or review.type != "R" or not review.passed
                or not Path(review.path).resolve().is_relative_to(root)
                or not review.intact(snapshot_hash=snapshot_hash, contract_hash=contract.contract_hash)
                or "QUALITY:plan:"+digest not in review.checks): raise ValueError("sealed quality review absent or changed")
        return dict(suites=suites, mutation=mutation, mapping_path=mapping, review=review,
            e2e_mode=value["candidate"]["e2e_mode"], mutant_snapshot_hash=value["mutant_snapshot_hash"],
            mutant_supervisor_root=root/"mutation-profiles"/value["mutant_snapshot_hash"] if value["mutant_snapshot_hash"] else None)
    except (OSError, KeyError, ValueError, TypeError) as exc:
        raise AdapterUnavailable("intact independently reviewed native quality plan unavailable") from exc
