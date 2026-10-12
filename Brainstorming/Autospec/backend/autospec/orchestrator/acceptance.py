"""Supervisor-owned acceptance sources and deterministic planning policy."""
from __future__ import annotations

import re
from pathlib import Path

from ..contracts import AcceptanceContract, ContractError, ContractStore
from ..models import ProjectState
from ..storage import workspace_dir
from .plan_gates import PlanPolicy


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
    return contract


def plan_policy(state: ProjectState, contract: AcceptanceContract) -> PlanPolicy:
    shared = tuple(str(f.expected["name"]) for f in contract.facts
                   if f.kind == "shared_contract" and isinstance(f.expected, dict)
                   and isinstance(f.expected.get("name"), str))
    return PlanPolicy(max_lots=state.acceptance_max_lots,
                      required_shared_contracts=shared,
                      expected_stack_sha256=state.technical_stack.get("decision_sha256", ""))
