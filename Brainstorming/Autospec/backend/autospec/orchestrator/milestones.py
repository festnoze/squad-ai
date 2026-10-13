"""Supervisor evidence required before any feature beyond the first vertical slice."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ..contracts import AcceptanceContract
from ..models import ProjectState, StoryStatus
from ..validation.final_gate import _valid_proof
from . import streams
from .dependencies import atomic_json


class MilestoneError(ValueError):
    pass


def strict_graph(state: ProjectState) -> streams.WorkGraph:
    ids = [story.id for story in state.stories] + [task.id for story in state.stories for task in story.tasks]
    if len(ids) != len(set(ids)):
        raise MilestoneError("duplicate story/task identity after plan admission")
    for story in state.stories:
        for node in (story, *story.tasks):
            if node.id in node.depends_on:
                raise MilestoneError("self dependency after plan admission: " + node.id)
    graph = streams.build_work_graph(state, break_cycles=False)
    if graph.warnings or streams.detect_cycle(graph):
        raise MilestoneError("raw plan graph invalid: " + "; ".join(graph.warnings) +
                             str(streams.detect_cycle(graph) or ""))
    return graph


def milestone_owners(state: ProjectState, graph: streams.WorkGraph) -> tuple[set[str], str]:
    admission = state.plan_admission_public
    if admission.get("status") != "pass" or admission.get("contract_hash") != state.acceptance_contract_hash:
        raise MilestoneError("no current admitted plan")
    values = state.plan_structure.get("milestones", {})
    foundation, vertical = set(values.get("foundation", [])), values.get("vertical", "")
    if not foundation or not foundation <= graph.items.keys() or vertical not in graph.items or vertical in foundation:
        raise MilestoneError("foundation/vertical owners unavailable")
    def reaches(source, target):
        todo, seen = list(graph.items[source].depends_on), set()
        while todo:
            item = todo.pop()
            if item == target:
                return True
            if item not in seen:
                seen.add(item)
                todo.extend(graph.items[item].depends_on)
        return False
    if not all(reaches(vertical, owner) for owner in foundation):
        raise MilestoneError("vertical no longer depends on every foundation owner")
    declared = set()
    for lot in state.plan_structure.get("lots", []):
        for member in lot.get("members", []):
            matches = {item.id for item in graph if item.id == member or item.story_id == member}
            if not matches:
                raise MilestoneError("admitted lot member disappeared: " + str(member))
            declared.update(matches)
    if not foundation | {vertical} <= declared:
        raise MilestoneError("milestone owners are outside the admitted lots")
    if any(not reaches(item.id, vertical) for item in graph if item.id in declared and
           item.id not in foundation and item.id != vertical):
        raise MilestoneError("feature work bypasses the vertical milestone")
    current = {story.id for story in state.stories_of_iteration(state.iteration)}
    if any(item.id not in declared and item.story_id in current and item.status != StoryStatus.DONE for item in graph):
        raise MilestoneError("new work is outside the admitted lots; re-admission required")
    return foundation, vertical


def admit_vertical(contract: AcceptanceContract, result: dict, *, snapshot_hash: str, evidence_root: Path) -> dict:
    """A health endpoint, a producer assertion or a partial chain never passes."""
    profiles = [fact.expected for fact in contract.facts if fact.kind == "vertical_profile"]
    if any(fact.kind == "security_profile" for fact in contract.facts):
        auth = True
    elif len(profiles) == 1 and isinstance(profiles[0], dict) and type(profiles[0].get("auth")) is bool:
        auth = profiles[0]["auth"]
    else:
        raise MilestoneError("reviewed vertical authentication profile missing")
    expected = {"schema", "browser_create", "api_read", "db_committed"}
    if auth:
        expected.update({"bootstrap", "argon2", "browser_login"})
    errors, stages = [], {}
    if result.get("snapshot_hash") != snapshot_hash or result.get("contract_hash") != contract.contract_hash:
        errors.append("vertical result identity differs")
    for stage in result.get("stages", []):
        name = stage.get("name") if isinstance(stage, dict) else None
        if name not in expected or name in stages:
            errors.append("unknown/duplicate vertical stage: " + str(name))
            continue
        proofs = [proof for proof in stage.get("proofs", []) if isinstance(proof, dict) and
                  _valid_proof(proof, "VERTICAL", root=Path(evidence_root).resolve(),
                               snapshot=snapshot_hash, contract=contract.contract_hash) and
                  "VERTICAL:" + name in proof["checks"]]
        kinds = {proof["type"] for proof in proofs}
        if stage.get("passed") is not True or "X" not in kinds or name.startswith("browser_") and "V" not in kinds:
            errors.append("vertical stage unproven: " + name)
        stages[name] = dict(stage, admitted_proofs=proofs)
    if expected - stages.keys():
        errors.append("vertical stages missing: " + ",".join(sorted(expected - stages.keys())))
    return {"version": 1, "status": "NOT_VERIFIED" if errors else "PASS",
            "contract_hash": contract.contract_hash, "snapshot_hash": snapshot_hash,
            "stages": list(stages.values()), "findings": errors}


def save_receipt(receipt: dict, store: Path) -> str:
    if receipt.get("status") != "PASS":
        raise MilestoneError("cannot store a green milestone from unproven stages")
    digest = hashlib.sha256(json.dumps(receipt, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    atomic_json(Path(store) / "milestones" / (digest + ".json"), receipt)
    return digest


def load_receipt(state: ProjectState, contract: AcceptanceContract, store: Path) -> dict | None:
    digest = state.plan_structure.get("vertical_receipt_hash", "")
    if not digest:
        return None
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise MilestoneError("invalid milestone receipt identity")
    receipt = json.loads((Path(store) / "milestones" / (digest + ".json")).read_text(encoding="utf-8"))
    actual = hashlib.sha256(json.dumps(receipt, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    if actual != digest:
        raise MilestoneError("milestone receipt modified")
    admitted = admit_vertical(contract, receipt, snapshot_hash=receipt["snapshot_hash"], evidence_root=store)
    if admitted["status"] != "PASS":
        raise MilestoneError("milestone proof no longer intact")
    return admitted


def vertical_complete(graph: streams.WorkGraph, foundation: set[str], vertical: str) -> bool:
    return all(graph.items[item].status == StoryStatus.DONE for item in foundation | {vertical})
