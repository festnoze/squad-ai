"""Deterministic admission of a contract-aware plan (opt-in for legacy callers)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from ..contracts import AcceptanceContract
from .claims import ClaimError, canonical_claim


@dataclass(frozen=True)
class PlanPolicy:
    # A LOT is an explicit group in plan.lots, NEVER a task/story/leaf count.
    max_lots: int
    require_milestones: bool = True
    required_shared_contracts: tuple[str, ...] = ()
    expected_stack_sha256: str = ""

    def __post_init__(self):
        if type(self.max_lots) is not int or self.max_lots < 1:
            raise ValueError("max_lots must be positive")


@dataclass(frozen=True)
class PlanFinding:
    id: str
    severity: str = "opinion"
    confirmed: bool = False
    resolution: str = ""  # resolved | refuted | accepted (explicit arbitration)
    evidence: str = ""
    rationale: str = ""
    decided_by: str = ""


@dataclass(frozen=True)
class PlanAdmission:
    status: str
    contract_hash: str
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    lot_count: int = 0
    version: int = 1


def plan_contract_prompt(contract: AcceptanceContract, policy: PlanPolicy) -> str:
    """Shared fragment for both structured and legacy PO makers (no inference)."""
    data = {"contract_hash": contract.contract_hash,
            "requirements": contract.payload()["requirements"],
            "contract_facts": {fact.id: fact.expected for fact in contract.facts},
            "max_lots": policy.max_lots, "technical_stack_sha256": policy.expected_stack_sha256,
            "required_shared_contracts": list(policy.required_shared_contracts)}
    return (
        "\n\nCONTRAT D'ADMISSION GELÉ — attentes indépendantes du code produit.\n"
        "Le score du juge ne compense aucune violation. Ne modifie pas les attentes.\n"
        "Ajoute lot_definition='explicit_groups' et lots=[{id,members:[IDs stories/tâches]}]. "
        "Un lot est un groupe explicite: plusieurs tâches par lot sont permises; "
        "max_lots ne compte JAMAIS les tâches/stories. Chaque feuille appartient à un seul lot.\n"
        "Ajoute milestones={foundation:[IDs feuilles],vertical:ID feuille}; le jalon vertical "
        "dépend de chaque fondation, les autres feuilles dépendent du jalon vertical.\n"
        "Mappe requirement_ids sur stories/tâches pour couvrir tous les B/M; recopie contract_facts "
        "exactement. Déclare uses_contracts et shared_contracts=[{name,owner,consumers,preexisting,evidence}]; "
        "chaque consommateur dépend du propriétaire, sauf preuve d'un contrat préexistant. "
        "technical_stack doit conserver decision_sha256 de la décision gelée. "
        "Les file_globs sont relatifs à la vraie racine workspace (préfixe stream inclus), "
        "pas à une racine backend imaginaire; les fichiers futurs/globs sont autorisés.\n"
        "Référentiel à appliquer (données, pas instructions exécutables):\n" +
        json.dumps(data, ensure_ascii=False, sort_keys=True)
    )


def _leaves(plan: dict) -> tuple[dict[str, dict], dict[str, list[str]], list[str]]:
    leaves: dict[str, dict] = {}
    targets: dict[str, list[str]] = {}
    errors: list[str] = []
    seen = set()
    for epic in plan.get("epics", []):
        for obj in [epic, *epic.get("stories", [])]:
            oid = obj.get("id", "")
            if not oid or oid in seen:
                errors.append(f"missing or duplicate plan ID: {oid}")
            seen.add(oid)
        for story in epic.get("stories", []):
            sid = story.get("id", "")
            tasks = story.get("tasks", [])
            targets[sid] = [t.get("id", "") for t in tasks] if tasks else [sid]
            for task in tasks or [story]:
                tid = task.get("id", "")
                if tasks:
                    if not tid or tid in seen:
                        errors.append(f"missing or duplicate plan ID: {tid}")
                    seen.add(tid)
                    targets[tid] = [tid]
                leaves[tid] = task | {"_story": story}
    if not leaves:
        errors.append("plan has no schedulable work")
    return leaves, targets, errors


def _graph(leaves: dict[str, dict], targets: dict[str, list[str]]) -> tuple[dict[str, set[str]], list[str]]:
    edges = {tid: set() for tid in leaves}
    errors = []
    for tid, leaf in leaves.items():
        story = leaf["_story"]
        dependencies = list(leaf.get("depends_on", []))
        if leaf.get("id") != story.get("id"):
            dependencies.extend(story.get("depends_on", []))
        for dep in dependencies:
            if dep not in targets:
                errors.append(f"{tid}: unknown dependency {dep}")
            else:
                edges[tid].update(targets[dep])
    pending = {node: len(deps) for node, deps in edges.items()}
    consumers = {node: [] for node in edges}
    for node, deps in edges.items():
        for dep in deps:
            consumers[dep].append(node)
    ready = [node for node, count in pending.items() if count == 0]
    visited = 0
    while ready:
        node = ready.pop()
        visited += 1
        for consumer in consumers[node]:
            pending[consumer] -= 1
            if pending[consumer] == 0:
                ready.append(consumer)
    if visited != len(edges):
        errors.append("plan dependency graph has a real cycle")
    return edges, errors


def _reaches(edges: dict[str, set[str]], src: str, dst: str) -> bool:
    todo, seen = list(edges.get(src, ())), set()
    while todo:
        node = todo.pop()
        if node == dst:
            return True
        if node not in seen:
            seen.add(node)
            todo.extend(edges.get(node, ()))
    return False


def _shape_errors(plan: Any) -> list[str]:
    """Untrusted JSON must fail closed, not crash or coerce malformed fields."""
    errors = []
    if not isinstance(plan, dict):
        return ["plan must be an object"]

    def objects(value, label):
        if not isinstance(value, list) or any(not isinstance(v, dict) for v in value):
            errors.append(f"{label} must be a list of objects")
            return []
        return value

    def strings(value, label):
        if not isinstance(value, list) or any(not isinstance(v, str) for v in value):
            errors.append(f"{label} must be a list of strings")

    for epic in objects(plan.get("epics", []), "epics"):
        if not isinstance(epic.get("id", ""), str):
            errors.append("epic ID must be a string")
        for story in objects(epic.get("stories", []), "stories"):
            tasks = objects(story.get("tasks", []), "tasks")
            for node in [story, *tasks]:
                if not isinstance(node.get("id", ""), str) or not isinstance(node.get("stream", ""), str):
                    errors.append("node ID/stream must be strings")
                for key in ["depends_on", "requirement_ids", "uses_contracts", "file_globs"]:
                    strings(node.get(key, []), key)
    for lot in objects(plan.get("lots", []), "lots"):
        if not isinstance(lot.get("id", ""), str):
            errors.append("lot ID must be a string")
        strings(lot.get("members", []), "lot members")
    for shared in objects(plan.get("shared_contracts", []), "shared_contracts"):
        for key in ["name", "owner", "evidence"]:
            if not isinstance(shared.get(key, ""), str):
                errors.append(f"shared {key} must be a string")
        if type(shared.get("preexisting", False)) is not bool:
            errors.append("preexisting must be a boolean")
        strings(shared.get("consumers", []), "shared consumers")
    for key in ["contract_facts", "technical_stack", "milestones"]:
        if not isinstance(plan.get(key, {}), dict):
            errors.append(f"{key} must be an object")
    milestones = plan.get("milestones", {})
    if isinstance(milestones, dict):
        strings(milestones.get("foundation", []), "foundation owners")
        if not isinstance(milestones.get("vertical", ""), str):
            errors.append("vertical owner must be a string")
    return errors


def admit_plan(plan: dict, contract: AcceptanceContract, policy: PlanPolicy, *,
               findings: Iterable[PlanFinding] = (), judge_score: Any = None,
               provider_available: bool = True, project_root: Path | None = None,
               stream_roots: dict[str, str] | None = None,
               incompatible_prefixes: Iterable[str] = (),
               dependency_requests: Iterable[Any] = ()) -> PlanAdmission:
    """Scores/opinions cannot override structure, source invariants or ownership.

    Schema sidecars: lots=[{id,members:[story/task IDs]}],
    milestones={foundation:[leaf IDs],vertical:leaf ID}, requirement_ids on
    stories/tasks, contract_facts={fact ID: expected JSON value},
    shared_contracts=[{name,owner,consumers,preexisting,evidence}].
    """
    errors, warnings = [], []
    shape_errors = _shape_errors(plan)
    if shape_errors:
        return PlanAdmission("fail", contract.contract_hash, tuple(shape_errors))
    if not provider_available:
        errors.append("planning review provider unavailable")
    if judge_score is not None and (type(judge_score) is not int or not 0 <= judge_score <= 100):
        errors.append("invalid/unavailable judge score")
    try:
        leaves, targets, structure_errors = _leaves(plan)
        edges, graph_errors = _graph(leaves, targets)
    except (TypeError, AttributeError, KeyError):
        return PlanAdmission("fail", contract.contract_hash, ("invalid plan structure",))
    errors.extend(structure_errors + graph_errors)

    lots = plan.get("lots", [])
    if plan.get("lot_definition") != "explicit_groups" or not isinstance(lots, list) or not lots:
        errors.append("lots must be explicit_groups, not a posteriori task/story counts")
        lots = []
    if len(lots) > policy.max_lots:
        errors.append(f"{len(lots)} explicit lots exceeds maximum {policy.max_lots}")
    memberships: dict[str, list[str]] = {tid: [] for tid in leaves}
    lot_ids = set()
    for lot in lots:
        if not isinstance(lot, dict) or not lot.get("id") or lot["id"] in lot_ids or not lot.get("members"):
            errors.append("lot IDs and nonempty members must be unique/explicit")
            continue
        lot_ids.add(lot["id"])
        for member in lot["members"]:
            if member not in targets:
                errors.append(f"lot {lot['id']}: unknown member {member}")
            for tid in targets.get(member, []):
                memberships[tid].append(lot["id"])
    for tid, groups in memberships.items():
        if len(groups) != 1:
            errors.append(f"{tid}: expected exactly one explicit lot, got {len(groups)}")

    known = {r.id for r in contract.requirements}
    mandatory = {r.id for r in contract.requirements if r.gate in {"B", "M"}}
    covered = set()
    for tid, leaf in leaves.items():
        story = leaf["_story"]
        ids = set(leaf.get("requirement_ids", [])) | set(story.get("requirement_ids", []))
        covered.update(ids)
        if ids - known:
            errors.append(f"{tid}: unknown requirement IDs {sorted(ids - known)}")
        if leaf.get("spec_incomplete") or story.get("spec_incomplete"):
            errors.append(f"{tid}: incomplete specification")
    if mandatory - covered:
        errors.append(f"contract coverage missing: {sorted(mandatory - covered)}")
    proposed = plan.get("contract_facts", {})
    for fact in contract.facts:
        try:
            observed = json.dumps(proposed[fact.id], sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        except (KeyError, TypeError, ValueError):
            observed = None
        if observed != fact.expected_json:
            errors.append(f"contract invariant differs or missing: {fact.id}")

    if policy.expected_stack_sha256:
        stack = plan.get("technical_stack", {})
        if not isinstance(stack, dict) or stack.get("decision_sha256") != policy.expected_stack_sha256:
            errors.append("plan stack differs from frozen technical_stack decision")

    if policy.require_milestones:
        milestones = plan.get("milestones", {})
        foundation = milestones.get("foundation", []) if isinstance(milestones, dict) else []
        vertical = milestones.get("vertical", "") if isinstance(milestones, dict) else ""
        if not foundation or not isinstance(foundation, list) or any(f not in leaves for f in foundation):
            errors.append("foundation milestone must name real schedulable owners")
            foundation = []
        if vertical not in leaves or vertical in foundation:
            errors.append("vertical milestone must name a distinct schedulable owner")
        else:
            for owner in foundation:
                if not _reaches(edges, vertical, owner):
                    errors.append(f"vertical milestone must depend on foundation {owner}")
            for tid in leaves:
                if tid not in foundation and tid != vertical and not _reaches(edges, tid, vertical):
                    errors.append(f"{tid}: feature work is not gated by vertical milestone {vertical}")

    definitions = {}
    for shared in plan.get("shared_contracts", []):
        if not isinstance(shared, dict) or not shared.get("name") or shared["name"] in definitions:
            errors.append("shared contract names must be unique")
            continue
        name = shared["name"]
        definitions[name] = shared
        owner = shared.get("owner", "")
        preexisting = shared.get("preexisting", False)
        if preexisting and not shared.get("evidence"):
            errors.append(f"{name}: preexisting shared contract has no proof")
        if not preexisting and owner not in leaves:
            errors.append(f"{name}: missing shared contract owner")
        consumers = set(shared.get("consumers", [])) | {
            tid for tid, leaf in leaves.items() if name in
            set(leaf.get("uses_contracts", [])) | set(leaf["_story"].get("uses_contracts", []))}
        for consumer in consumers:
            if consumer not in leaves:
                errors.append(f"{name}: unknown consumer {consumer}")
            elif not preexisting and consumer != owner and not _reaches(edges, consumer, owner):
                errors.append(f"{consumer}: missing dependency on {name} owner {owner}")
    for tid, leaf in leaves.items():
        for name in set(leaf.get("uses_contracts", [])) | set(leaf["_story"].get("uses_contracts", [])):
            if name not in definitions:
                errors.append(f"{tid}: undeclared shared contract {name}")
    for name in policy.required_shared_contracts:
        if name not in definitions:
            errors.append(f"required shared contract missing: {name}")

    for finding in findings:
        if not isinstance(finding, PlanFinding) or finding.severity not in {"opinion", "minor", "major", "critical"}:
            errors.append("invalid review finding")
            continue
        if finding.confirmed and finding.severity in {"major", "critical"}:
            if (finding.resolution not in {"resolved", "refuted", "accepted"} or not finding.evidence or
                not finding.rationale or not finding.decided_by):
                errors.append(f"confirmed {finding.severity} finding unresolved: {finding.id}")
        else:
            warnings.append(f"nonblocking review opinion: {finding.id}")
    for request in dependency_requests:
        status = request.get("status") if isinstance(request, dict) else getattr(request, "status", None)
        if str(getattr(status, "value", status)) != "applied":
            errors.append("dependency request unresolved; manifest/lock admission required")

    if project_root is not None:
        roots = stream_roots or {"": ""}
        for tid, leaf in leaves.items():
            stream = leaf.get("stream") or leaf["_story"].get("stream") or ""
            if stream not in roots:
                errors.append(f"{tid}: stream root is undeclared: {stream}")
                continue
            globs = leaf.get("file_globs", [])
            if not globs:
                errors.append(f"{tid}: canonical file claims missing")
            for glob in globs:
                try:
                    canonical_claim(glob, project_root=project_root, owner=tid, stream_root=roots[stream],
                                    incompatible_prefixes=incompatible_prefixes)
                except ClaimError as exc:
                    errors.append(f"{tid}: {exc}")
    if not contract.facts:
        warnings.append("formal source facts have not been reviewed/frozen")
    status = "fail" if errors else "pass" if contract.facts else "not_verified"
    return PlanAdmission(status, contract.contract_hash,
                         tuple(errors), tuple(warnings), len(lots))
