from pathlib import Path

import pytest

from autospec.contracts import import_contract
from autospec.validation.architecture_contracts import ArchitectureContractVerifier, ARCHITECTURE_CHECKS
from tests.support_contract_fixture import SQLiteSupportSubject, retain_fixture_report


@pytest.fixture
def support_contract():
    root=Path(__file__).resolve().parents[2]/"docs/validation/support-client"
    return import_contract((root/"01_specification.md").read_text(encoding="utf-8"),
        (root/"02_requirements_verification.md").read_text(encoding="utf-8"),reviewed_by="independent fixture test")


async def run_pack(subject):
    try:
        report=await ArchitectureContractVerifier(subject.adapter,subject.contract).verify(subject.snapshot)
        retain_fixture_report(report,subject)
        return {r["id"]:r for r in report["requirements"]}
    finally: await subject.adapter.close()


@pytest.mark.asyncio
async def test_good_sqlite_fixture_has_no_false_constraint_failure(tmp_path,support_contract):
    results=await run_pack(SQLiteSupportSubject(tmp_path,support_contract))
    assert set(results)==set(ARCHITECTURE_CHECKS)
    for rid in ("ARC-02","ARC-03","ARC-04","ARC-05","ARC-07","ARC-08"):
        assert results[rid]["status"]!="FAIL",results[rid]
        assert results[rid]["observed"],results[rid]
    assert results["ARC-02"]["status"]=="NOT_VERIFIED"  # executable constraints do not invent a source review
    assert results["ARC-04"]["status"]=="PASS",results["ARC-04"]
    assert results["ARC-07"]["status"]=="PASS",results["ARC-07"]
    # Minimal catch-all fixture does not pretend to have complete OpenAPI public DTOs.
    assert results["ARC-06"]["status"]=="FAIL"
    assert results["ARC-01"]["status"]=="NOT_VERIFIED"
    assert results["ARC-09"]["status"]=="NOT_VERIFIED"


@pytest.mark.parametrize("bug,check",[("null_id","null_ids"),("fractional_version","integer_versions")])
@pytest.mark.asyncio
async def test_bad_database_domains_are_detected_by_real_inserts(tmp_path,support_contract,bug,check):
    subject=SQLiteSupportSubject(tmp_path,support_contract,bug)
    results=await run_pack(subject)
    result=results["ARC-02"]
    assert result["status"]=="FAIL",result
    assert any(e["check"]==check and not e["passed"] for e in result["observed"])
    # Rejected OR accepted probes leave no counterexample row behind.
    con=subject.connect()
    assert con.execute("SELECT count(*) FROM tickets WHERE id IS NULL OR version=1.5").fetchone()[0]==0
    con.close()


@pytest.mark.asyncio
async def test_full_rollback_and_distinct_connections_really_observed(tmp_path,support_contract):
    results=await run_pack(SQLiteSupportSubject(tmp_path,support_contract))
    arc3=results["ARC-03"]
    checks={e["check"]:e for e in arc3["observed"]}
    assert checks["distinct_connections"]["passed"]
    assert checks["busy"]["passed"],checks["busy"]
    assert checks["busy"]["observed"]["status"]==503
    assert checks["rollback"]["observed"]["before_digest"]==checks["rollback"]["observed"]["after_digest"]


@pytest.mark.asyncio
async def test_replayed_destructive_migration_is_fail(tmp_path,support_contract):
    results=await run_pack(SQLiteSupportSubject(tmp_path,support_contract,"migration_reset"))
    assert results["ARC-04"]["status"]=="FAIL"
    assert any(e["check"]=="replay" and not e["passed"] for e in results["ARC-04"]["observed"])


@pytest.mark.asyncio
async def test_real_query_trace_detects_per_ticket_n_plus_one(tmp_path,support_contract):
    results=await run_pack(SQLiteSupportSubject(tmp_path,support_contract,"n_plus_one"))
    assert results["ARC-05"]["status"]=="FAIL",results["ARC-05"]
    assert any(e["observed"].get("scaled_related_queries") for e in results["ARC-05"]["observed"])


@pytest.mark.asyncio
async def test_harness_fk_does_not_hide_disabled_product_connections(tmp_path,support_contract):
    results=await run_pack(SQLiteSupportSubject(tmp_path,support_contract,"app_foreign_keys_off"))
    assert results["ARC-02"]["status"]=="FAIL"
    assert any(e["check"]=="foreign_keys" and not e["passed"] for e in results["ARC-02"]["observed"])
