import time

import pytest

from autospec.orchestrator.repair_policy import RepairLedger, classify_failure


@pytest.mark.parametrize("detail,category,repairable", [
    ("ModuleNotFoundError: No module named 'argon2'", "dependency", True),
    ("ISOLATION_UNAVAILABLE: daemon", "environment", False),
    ("__INFRA__ docker down", "environment", False),
    ("provider_error: rate limit", "provider", False),
    ("CLAIM_CONFLICT: errors.py", "conflict", False),
    ("runtime timeout", "timeout", True),
    ("POST /api/login returned 500", "contract", True),
    ("ENVIRONMENT_DRIFT: wheel changed", "environment", False),
    ("CACHE_INCOMPLETE", "environment", False),
    ("CLEAN_INSTALL_FAILED: registry unavailable", "environment", False),
    ("DEPENDENCY_UNRESOLVED: argon2", "dependency_waiting", False),
])
def test_classification(detail, category, repairable):
    result = classify_failure(detail)
    assert (result.category, result.repairable) == (category, repairable)


def test_repeat_stops_before_another_paid_call():
    ledger = RepairLedger(5, time.monotonic() + 30)
    ledger.observe("2026-10-11T10:12:01Z attempt 1\nModuleNotFoundError: No module named 'argon2'")
    ledger.admit()
    ledger.observe("2026-10-11T10:14:01Z attempt 2\nModuleNotFoundError: No module named 'argon2'")
    assert "répété" in ledger.denied_reason()
    with pytest.raises(ValueError):
        ledger.admit()
    assert ledger.attempts == 1


def test_distinct_contract_violation_can_be_repaired_within_cap():
    ledger = RepairLedger(2, time.monotonic() + 30)
    ledger.observe("POST /api/login 500")
    ledger.admit()
    ledger.observe("POST /api/login 403")
    assert not ledger.denied_reason()
    ledger.admit()
    assert "tentatives" in ledger.denied_reason()


def test_timeout_and_unavailable_environment_do_not_loop():
    ledger = RepairLedger(20, time.monotonic() - 1)
    ledger.observe("bad wiring")
    assert "délai" in ledger.denied_reason()
    ledger = RepairLedger(20, time.monotonic() + 1)
    ledger.observe("ISOLATION_UNAVAILABLE")
    assert "non réparable" in ledger.denied_reason()
