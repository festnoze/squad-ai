"""Supervisor-owned acceptance sources and deterministic planning policy."""
from __future__ import annotations

import re
from pathlib import Path

from ..contracts import AcceptanceContract, ContractError, ContractStore
from ..models import ProjectState
from ..storage import workspace_dir
from .plan_gates import PlanPolicy, vertical_contract_checks


def supervisor_root(project_id: str) -> Path:
    # workspace_dir validates the untrusted project ID; no path from producer
    # state can redirect the store into another project or its writable tree.
    product = workspace_dir(project_id).resolve()
    return product.parent / ".autospec-supervisor" / project_id


def contract_store(project_id: str) -> ContractStore:
    return ContractStore(supervisor_root(project_id) / "contracts",
                         product_write_roots=[workspace_dir(project_id)])


def load_contract(state: ProjectState) -> AcceptanceContract | None:
    digest = state.acceptance_contract_hash
    if not digest:
        return None
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ContractError("invalid acceptance contract identity")
    store = contract_store(state.id)
    contract = store.load(store.root / f"{digest}.json")
    if state.brief != contract.brief:
        raise ContractError("editable brief differs from the frozen acceptance source")
    validate_plan_limits(contract, state.acceptance_max_lots)
    return contract


def source_plan_max_lots(contract: AcceptanceContract) -> int | None:
    """Explicit reviewed source fact only; never parse/reinterpret brief prose.

    This is a global plan constraint, not an additional acceptance verdict.
    No fact preserves legacy opt-in behavior. A fact cannot be supplied twice,
    silently extended or mapped to only some requirements.
    """
    facts = [fact for fact in contract.facts if fact.kind == "plan_limits"]
    if not facts:
        return None
    if len(facts) != 1:
        raise ContractError("plan_limits must be a unique frozen source fact")
    fact = facts[0]
    expected = fact.expected
    if (not isinstance(expected, dict) or set(expected) != {"max_lots"} or
            type(expected["max_lots"]) is not int or expected["max_lots"] < 1):
        raise ContractError("plan_limits requires exactly one positive strict-integer max_lots")
    ids = tuple(fact.requirement_ids)
    if len(ids) != len(set(ids)) or set(ids) != {row.id for row in contract.requirements}:
        raise ContractError("global plan_limits must map every frozen requirement exactly once")
    return expected["max_lots"]


def validate_plan_limits(contract: AcceptanceContract, max_lots: int) -> int:
    """Also callable by the API before persistence, pipeline or provider work."""
    frozen = source_plan_max_lots(contract)
    if frozen is None:
        return max_lots
    if type(max_lots) is not int or max_lots != frozen:
        raise ContractError("mutable max_lots differs from the frozen source plan_limits")
    return frozen


def plan_policy(state: ProjectState, contract: AcceptanceContract) -> PlanPolicy:
    shared = tuple(str(f.expected["name"]) for f in contract.facts
                   if f.kind == "shared_contract" and isinstance(f.expected, dict)
                   and isinstance(f.expected.get("name"), str))
    return PlanPolicy(max_lots=validate_plan_limits(contract, state.acceptance_max_lots),
                      required_shared_contracts=shared,
                      expected_stack_sha256=state.technical_stack.get("decision_sha256", ""),
                      expected_stack=dict(state.technical_stack),
                      required_vertical_checks=vertical_contract_checks(contract, state.technical_stack))
