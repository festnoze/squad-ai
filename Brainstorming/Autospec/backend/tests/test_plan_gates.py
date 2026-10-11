import json

import pytest

from autospec.agents.runner import FakeRunner
from autospec.config import settings
from autospec.contracts import ContractFact, import_contract
from autospec.models import ProjectState
from autospec.orchestrator.plan_gates import PlanFinding, PlanPolicy, admit_plan, plan_contract_prompt
from autospec.orchestrator.plan_pipeline import PlanAdmissionError, PlanPipelineError, arun_po_pipeline


def contract():
    return import_contract("POST /books; title 2..12; draft -> deleted forbidden",
        "| BOOK-01 | B / X | POST /books; title 2..12; draft -> deleted forbidden |",
        reviewed_by="reviewer", facts=[
            ContractFact.create("route", "route", "POST /books", ["BOOK-01"], "POST /books"),
            ContractFact.create("bound", "bound", [2, 12], ["BOOK-01"], "title 2..12"),
            ContractFact.create("transition", "transition", False, ["BOOK-01"], "draft -> deleted forbidden"),
        ])


def plan(task_count=3):
    tasks = [{"id": f"T-{i}", "title": f"Work {i}", "file_globs": [f"books/file{i}.py"],
              "depends_on": [] if i == 0 else [f"T-{i - 1}"], "requirement_ids": ["BOOK-01"]}
             for i in range(task_count)]
    return {"epics": [{"id": "E-1", "stories": [{"id": "S-1", "title": "Books", "tasks": tasks}]}],
            "lot_definition": "explicit_groups", "lots": [{"id": "L-1", "members": ["S-1"]}],
            "milestones": {"foundation": ["T-0"], "vertical": "T-1"},
            "contract_facts": {"route": "POST /books", "bound": [2, 12], "transition": False}}


def test_high_score_does_not_compensate_source_invariant_violation():
    for key, value in [("route", "POST /library"), ("bound", [1, 20]), ("transition", True)]:
        candidate = plan()
        candidate["contract_facts"][key] = value
        result = admit_plan(candidate, contract(), PlanPolicy(7), judge_score=99)
        assert result.status == "fail"
        assert any(key in error for error in result.errors)


def test_explicit_lots_are_groups_not_27_schedulable_tasks():
    candidate = plan(27)
    result = admit_plan(candidate, contract(), PlanPolicy(7))
    assert result.status == "pass" and result.lot_count == 1
    candidate["lots"] = [{"id": f"L-{i}", "members": [f"T-{i}"]} for i in range(27)]
    assert any("exceeds maximum" in e for e in admit_plan(candidate, contract(), PlanPolicy(7)).errors)
    del candidate["lot_definition"]
    assert admit_plan(candidate, contract(), PlanPolicy(99)).status == "fail"


def test_contract_prompt_preserves_exact_fact_mapping_and_explicit_lot_definition():
    prompt = plan_contract_prompt(contract(), PlanPolicy(7))
    assert contract().contract_hash in prompt
    assert "explicit_groups" in prompt and '"max_lots": 7' in prompt
    assert '"route": "POST /books"' in prompt


def test_source_only_contract_without_reviewed_formal_facts_is_not_verified():
    original = contract()
    source_only = import_contract(original.brief, original.reference, reviewed_by="reviewer")
    assert admit_plan(plan(), source_only, PlanPolicy(7)).status == "not_verified"


@pytest.mark.parametrize("problem", ["cycle", "unknown", "coverage", "milestone", "duplicate", "empty", "double_lot"])
def test_structure_dag_coverage_and_milestones_are_hard_gates(problem):
    candidate = plan()
    tasks = candidate["epics"][0]["stories"][0]["tasks"]
    if problem == "cycle":
        tasks[0]["depends_on"] = ["T-2"]
    elif problem == "unknown":
        tasks[2]["depends_on"] = ["missing"]
    elif problem == "coverage":
        for task in tasks:
            task["requirement_ids"] = []
    elif problem == "milestone":
        tasks[2]["depends_on"] = ["T-0"]
    elif problem == "duplicate":
        tasks[2]["id"] = "T-1"
    elif problem == "empty":
        candidate["epics"] = []
    else:
        candidate["lots"].append({"id": "L-2", "members": ["T-2"]})
    assert admit_plan(candidate, contract(), PlanPolicy(7)).status == "fail"


def test_confirmed_major_finding_requires_explicit_resolution_but_opinion_does_not():
    assert admit_plan(plan(), contract(), PlanPolicy(7), findings=[PlanFinding("opinion")]).status == "pass"
    finding = PlanFinding("serious", "major", confirmed=True)
    assert admit_plan(plan(), contract(), PlanPolicy(7), findings=[finding]).status == "fail"
    refuted = PlanFinding("serious", "major", True, "refuted", "proof.json", "counterexample disproven", "reviewer")
    assert admit_plan(plan(), contract(), PlanPolicy(7), findings=[refuted]).status == "pass"
    accepted = PlanFinding("serious", "critical", True, "accepted", "decision.json", "explicit scoped arbitration", "owner")
    assert admit_plan(plan(), contract(), PlanPolicy(7), findings=[accepted]).status == "pass"


@pytest.mark.parametrize("score", [-1, 101, None, "99", True])
def test_invalid_judge_or_provider_unavailable_is_fail_closed(score):
    # None means a deterministic-only gate, so provider availability is explicit.
    result = admit_plan(plan(), contract(), PlanPolicy(7), judge_score=score, provider_available=score is not None)
    assert result.status == "fail"


def test_shared_clock_errors_db_are_owned_and_consumer_dependencies_are_kept():
    candidate = plan()
    tasks = candidate["epics"][0]["stories"][0]["tasks"]
    tasks[2]["uses_contracts"] = ["errors", "clock", "db"]
    candidate["shared_contracts"] = [{"name": name, "owner": "T-0", "consumers": ["T-2"]}
                                     for name in ["errors", "clock", "db"]]
    policy = PlanPolicy(7, required_shared_contracts=("errors", "clock", "db"))
    assert admit_plan(candidate, contract(), policy).status == "pass"
    tasks[1]["depends_on"] = []
    assert any("missing dependency" in e for e in admit_plan(candidate, contract(), policy).errors)
    assert tasks[2]["depends_on"] == ["T-1"]  # no blind removal of existing dependencies
    for shared in candidate["shared_contracts"]:
        shared.update(preexisting=True, evidence="foundation-snapshot.json")
    assert not any("missing dependency" in e for e in admit_plan(candidate, contract(), policy).errors)


def test_manifest_requests_and_frozen_stack_are_admission_inputs(tmp_path):
    candidate = plan()
    policy = PlanPolicy(7, expected_stack_sha256="chosen-stack")
    assert admit_plan(candidate, contract(), policy).status == "fail"
    candidate["technical_stack"] = {"version": 1, "decision_sha256": "chosen-stack", "rationale": "brief"}
    assert admit_plan(candidate, contract(), policy, dependency_requests=[{"status": "applied"}],
                      project_root=tmp_path).status == "pass"
    assert admit_plan(candidate, contract(), policy, dependency_requests=[{"status": "pending"}]).status == "fail"
    candidate["epics"][0]["stories"][0]["tasks"][2]["file_globs"] = ["../escape.py"]
    assert admit_plan(candidate, contract(), policy, project_root=tmp_path).status == "fail"


@pytest.mark.parametrize("field,value", [("epics", None), ("lots", {"id": "x"}),
                                        ("milestones", []), ("shared_contracts", [None]),
                                        ("contract_facts", "prose")])
def test_malformed_plan_inputs_are_rejected_without_exceptions(field, value):
    candidate = plan()
    candidate[field] = value
    assert admit_plan(candidate, contract(), PlanPolicy(7)).status == "fail"


async def test_contract_pipeline_deterministic_refusal_has_no_legacy_fallback():
    candidate = plan()
    candidate["contract_facts"]["route"] = "GET /wrong"
    runner = FakeRunner([json.dumps(candidate), json.dumps(candidate)])
    state = ProjectState(id="contract", name="books", goal="books")
    with pytest.raises(PlanAdmissionError) as caught:
        await arun_po_pipeline(runner, state, "books", contract=contract(), plan_policy=PlanPolicy(7))
    assert not isinstance(caught.value, PlanPipelineError)
    assert len(runner.calls) == 2  # S1 plus one bounded schema/constraint repair


async def test_contract_pipeline_keeps_source_metadata_and_refuses_missing_review(monkeypatch):
    monkeypatch.setattr(settings, "po_pipeline_min_leaves", 100)
    candidate = plan()
    spec = {"id": "S-1", "description": "Books", "tasks": [
        {"id": f"T-{i}", "description": "work", "acceptance_criteria": [{"id": "AC-1", "text": "works", "kind": "happy"}]}
        for i in range(3)], "acceptance_criteria": [{"id": "AC-1", "text": "works", "kind": "happy"},
                                                  {"id": "AC-2", "text": "refuses", "kind": "error"}],
        "gherkin": "Feature: books\n  @AC-1\n  Scenario: works\n    Given books\n    When create\n    Then exists\n  @AC-2\n  Scenario: refuses\n    Given bad input\n    When create\n    Then refused"}
    state = ProjectState(id="contract", name="books", goal="books")
    valid_critic = json.dumps({"issues": [], "suggestions": [], "reflection": "reviewed"})
    result, report = await arun_po_pipeline(FakeRunner([json.dumps(candidate), valid_critic, json.dumps(spec)]),
        state, "books", contract=contract(), plan_policy=PlanPolicy(7))
    assert report.admission.status == "pass"
    assert result["milestones"] == candidate["milestones"]
    assert result["lots"] == candidate["lots"]
    with pytest.raises(PlanAdmissionError, match="provider unavailable"):
        await arun_po_pipeline(FakeRunner([json.dumps(candidate), "not json", json.dumps(spec)]),
            state, "books", contract=contract(), plan_policy=PlanPolicy(7))
