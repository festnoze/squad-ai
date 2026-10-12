"""Source-only global lot bound, independent of stories/tasks and state drift."""
import json
from pathlib import Path

import pytest

from autospec.contracts import ContractError, ContractFact, import_contract
from autospec.models import ProjectState
from autospec.orchestrator import acceptance


def contract_with_limit(expected=None, *, fact_count=1, mapping=None):
    brief="Example application: at most four explicit delivery lots; many leaf tasks permitted."
    reference="| OTHER-01 | B / X | Nominal API |\n| OTHER-02 | M / R | Explicit organization |"
    facts=[ContractFact.create("limits-"+str(i),"plan_limits",{"max_lots":4} if expected is None else expected,
        ["OTHER-01","OTHER-02"] if mapping is None else mapping,"at most four explicit delivery lots") for i in range(fact_count)]
    return import_contract(brief,reference,reviewed_by="source-only meta-test",facts=facts)


def state_for(contract, limit=4):
    return ProjectState(id="source-plan-limits",name="Another application",goal="Another application",
        brief=contract.brief,acceptance_contract_hash=contract.contract_hash,acceptance_max_lots=limit)


def test_generic_source_fact_not_hardcoded_to_support_seven_and_hash_bound():
    contract=contract_with_limit();state=state_for(contract)
    assert acceptance.source_plan_max_lots(contract)==4
    assert acceptance.plan_policy(state,contract).max_lots==4
    assert acceptance.validate_plan_limits(contract,4)==4
    assert contract.contract_hash!=contract_with_limit({"max_lots":5}).contract_hash


@pytest.mark.parametrize("expected", [{"max_lots":True},{"max_lots":4.0},{"max_lots":"4"},{"max_lots":None},
    {"max_lots":0},{"max_lots":-1},{},{"max_lots":4,"max_tasks":4},4])
def test_malformed_source_fact_fails_both_policy_and_load_before_execution(expected):
    contract=contract_with_limit(expected);state=state_for(contract)
    acceptance.contract_store(state.id).save(contract)
    for action in (lambda:acceptance.plan_policy(state,contract),lambda:acceptance.load_contract(state)):
        with pytest.raises(ContractError,match="strict-integer"):action()


@pytest.mark.parametrize("count,mapping",[(2,None),(1,["OTHER-01"]),(1,["OTHER-01","OTHER-02","OTHER-02"])])
def test_ambiguous_or_partial_global_fact_is_not_admitted(count,mapping):
    contract=contract_with_limit(fact_count=count,mapping=mapping)
    with pytest.raises(ContractError):acceptance.source_plan_max_lots(contract)


@pytest.mark.parametrize("changed",[3,5,7,100,True,"4",4.0])
def test_state_limit_cannot_override_or_expand_sealed_source(changed):
    contract=contract_with_limit();state=state_for(contract)
    acceptance.contract_store(state.id).save(contract)
    # Mutation after model coercion is representative of a resumed state drift.
    state.acceptance_max_lots=changed
    with pytest.raises(ContractError,match="frozen source"):acceptance.load_contract(state)
    with pytest.raises(ContractError,match="frozen source"):acceptance.plan_policy(state,contract)
    with pytest.raises(ContractError):acceptance.validate_plan_limits(contract,changed)


def test_exact_import_load_and_legacy_no_fact_behavior_remain():
    contract=contract_with_limit();state=state_for(contract)
    acceptance.contract_store(state.id).save(contract)
    assert acceptance.load_contract(state)==contract
    legacy=contract_with_limit(fact_count=0);state=state_for(legacy,12)
    acceptance.contract_store(state.id).save(legacy)
    assert acceptance.load_contract(state)==legacy and acceptance.source_plan_max_lots(legacy) is None
    assert acceptance.plan_policy(state,legacy).max_lots==12
    state.acceptance_contract_hash=""
    assert acceptance.load_contract(state) is None


def test_source_exact_support_fact_maps_all_57_without_an_extra_verdict():
    root=Path(__file__).resolve().parents[2]
    artifact=json.loads((root/"artifacts/remediation/REM-25/source-facts-v02.json").read_text(encoding="utf-8"))
    docs=root/"docs/validation/support-client"
    brief=(docs/"01_specification.md").read_bytes().decode("utf-8")
    reference=(docs/"02_requirements_verification.md").read_bytes().decode("utf-8")
    contract=import_contract(brief,reference,reviewed_by="source extraction meta-test; parent review required",
        facts=[ContractFact.create(**fact) for fact in artifact["acceptance_facts"]])
    fact=next(f for f in contract.facts if f.kind=="plan_limits")
    assert fact.expected=={"max_lots":7} and fact.source_excerpt in brief
    assert len(fact.requirement_ids)==57 and set(fact.requirement_ids)=={r.id for r in contract.requirements}
    assert acceptance.plan_policy(state_for(contract,7),contract).max_lots==7
    assert len(contract.requirements)==57
