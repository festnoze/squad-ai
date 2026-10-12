"""Fictional supervisor facts only: no CLI, API, product execution or LLM."""
from dataclasses import asdict, replace
import json

import pytest

from autospec.orchestrator.repair_policy import (
    MAX_PLAN_CORRECTION_BYTES, PlanCorrectionContext, PlanCorrectionIssue,
    PlanCorrectionKind, decide_plan_maker_correction,
)


def context(**changes):
    # Synthetic metadata, NOT native evidence.
    return replace(PlanCorrectionContext(
        admission_status="fail",
        issues=(PlanCorrectionIssue(PlanCorrectionKind.CONSTRAINT, "backend prefix contradicts factory root"),),
        contract_hash="a" * 64, response_sha256="b" * 64,
        rejection_receipt_sha256="c" * 64, response_bytes=1024,
        capture_complete=True, rejection_persisted=True,
        independent_major_finding=False, usage_complete=True,
        unreported_calls=0, budget_remaining_usd=39.65,
    ), **changes)


def test_default_is_off_and_never_mutates_context():
    facts=context();before=asdict(facts)
    result=decide_plan_maker_correction(facts)
    assert not result.allowed and result.reason == "CORRECTION_DISABLED"
    assert result.next_attempt is None and asdict(facts) == before


@pytest.mark.parametrize("kind", [PlanCorrectionKind.STRUCTURE, PlanCorrectionKind.CONSTRAINT])
def test_explicit_one_attempt_preserves_typed_errors_and_receipt_identity(kind):
    facts=context(issues=(PlanCorrectionIssue(kind,"exact factory gate error"),))
    result=decide_plan_maker_correction(facts,revision_limit=1)
    assert result.allowed and result.next_attempt == 1
    assert (result.contract_hash,result.response_sha256,result.rejection_receipt_sha256) == (
        facts.contract_hash,facts.response_sha256,facts.rejection_receipt_sha256)
    assert result.issues == facts.issues
    assert json.loads(json.dumps(asdict(result)))["issues"][0]["kind"] == kind.value


@pytest.mark.parametrize("kind", [PlanCorrectionKind.INDEPENDENT_REVIEW,PlanCorrectionKind.PROVIDER,
    PlanCorrectionKind.ENVIRONMENT,PlanCorrectionKind.COST,PlanCorrectionKind.UNCLASSIFIED])
def test_non_maker_issue_blocks_mixed_structural_failure_regardless_of_prose(kind):
    facts=context(issues=(PlanCorrectionIssue(PlanCorrectionKind.STRUCTURE,"bad JSON"),
        PlanCorrectionIssue(kind,"structural constraint timeout provider text")))
    result=decide_plan_maker_correction(facts,revision_limit=1)
    assert not result.allowed and result.reason == "NON_MAKER_FAILURE_BLOCKS_CORRECTION"


@pytest.mark.parametrize("count", [1,2,100])
def test_unknown_or_completed_attempt_is_consumed_without_retry(count):
    result=decide_plan_maker_correction(context(),revision_limit=1,attempts_used=count)
    assert not result.allowed and result.reason == "CORRECTION_ALREADY_CONSUMED"


@pytest.mark.parametrize("limit", [True,False,-1,2,3,1.0,"1",None])
def test_no_config_coercion_or_multiple_attempts(limit):
    result=decide_plan_maker_correction(context(),revision_limit=limit)
    assert not result.allowed and result.reason == "INVALID_REVISION_LIMIT"


@pytest.mark.parametrize("count", [True,False,-1,0.0,"0",None])
def test_attempt_count_is_known_nonnegative_integer(count):
    result=decide_plan_maker_correction(context(),revision_limit=1,attempts_used=count)
    assert not result.allowed and result.reason == "INVALID_ATTEMPT_COUNT"


@pytest.mark.parametrize("change,reason", [
    ({"admission_status":"pass"},"PLAN_NOT_DETERMINISTICALLY_REJECTED"),
    ({"admission_status":"not_verified"},"PLAN_NOT_DETERMINISTICALLY_REJECTED"),
    ({"independent_major_finding":True},"INDEPENDENT_FINDING_BLOCKS_CORRECTION"),
    ({"rejection_persisted":False},"REJECTION_NOT_DURABLY_RECORDED"),
    ({"capture_complete":False},"REJECTED_RESPONSE_NOT_FULLY_CAPTURED"),
    ({"response_bytes":MAX_PLAN_CORRECTION_BYTES+1},"REJECTED_RESPONSE_NOT_FULLY_CAPTURED"),
    ({"usage_complete":False},"COST_RECONCILIATION_REQUIRED"),
    ({"unreported_calls":1},"COST_RECONCILIATION_REQUIRED"),
    ({"budget_remaining_usd":0},"BUDGET_EXHAUSTED"),
    ({"budget_remaining_usd":-0.01},"BUDGET_EXHAUSTED"),
])
def test_fail_closed_preconditions(change,reason):
    result=decide_plan_maker_correction(context(**change),revision_limit=1)
    assert not result.allowed and result.reason == reason and result.next_attempt is None


@pytest.mark.parametrize("change", [
    {"issues":()},{"issues":[]},{"issues":("constraint",)},
    {"issues":(PlanCorrectionIssue("constraint","untyped"),)},
    {"issues":(PlanCorrectionIssue(PlanCorrectionKind.CONSTRAINT,"  "),)},
    {"admission_status":"FAIL"},{"admission_status":None},
    {"contract_hash":""},{"response_sha256":"b"*63},{"rejection_receipt_sha256":"C"*64},
    {"response_bytes":True},{"response_bytes":-1},{"response_bytes":1.0},
    {"capture_complete":1},{"rejection_persisted":"true"},{"independent_major_finding":0},
    {"usage_complete":1},{"unreported_calls":False},{"unreported_calls":-1},{"unreported_calls":0.0},
    {"budget_remaining_usd":True},{"budget_remaining_usd":"39.65"},
    {"budget_remaining_usd":float("nan")},{"budget_remaining_usd":float("inf")},
    {"budget_remaining_usd":10**1000},
])
def test_unknown_or_coerced_facts_cannot_authorize_call(change):
    result=decide_plan_maker_correction(context(**change),revision_limit=1)
    assert not result.allowed and result.reason == "INVALID_CORRECTION_CONTEXT"


@pytest.mark.parametrize("value", [None,{},"constraint"])
def test_context_cannot_be_a_producer_dictionary(value):
    result=decide_plan_maker_correction(value,revision_limit=1)
    assert not result.allowed and result.reason == "INVALID_CORRECTION_CONTEXT"


def test_mock_dispatch_journals_before_one_maker_call_without_reviews():
    calls,journal=[],[];facts=context()
    for _ in range(2):
        decision=decide_plan_maker_correction(facts,revision_limit=1,attempts_used=len(journal))
        if decision.allowed:
            journal.append({"attempt":decision.next_attempt,"status":"UNKNOWN",
                "receipt_sha256":decision.rejection_receipt_sha256})
            assert journal[-1]["status"] == "UNKNOWN"
            calls.append({"role":"maker","errors":decision.issues})
    assert len(calls) == len(journal) == 1 and calls[0]["role"] == "maker"
    # Corrected output STILL requires unchanged gate admission, not this policy.
    assert facts.budget_remaining_usd == 39.65 and facts.admission_status == "fail"
