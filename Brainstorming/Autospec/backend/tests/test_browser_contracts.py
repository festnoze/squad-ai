import json
from pathlib import Path

import pytest

from autospec.contracts import import_contract
from autospec.validation.browser_contracts import (BrowserVerifier, _check_optional_no_auth_login_visibility,
    _exact_detail_bindings, browser_generation_requirements, browser_smoke)
from autospec.validation.support_adapter import AdapterUnavailable
from tests.fixtures.browser.app import BrowserSubject, browser_contract, retain_browser_fixture_report


async def run_browser(tmp_path, rid, bug=""):
    contract = browser_contract()
    subject = BrowserSubject(tmp_path / "product", contract, bug)
    subject.start_http()
    try:
        report = await BrowserVerifier(contract, subject.harness()).verify(subject.snapshot, ids=[rid])
        retain_browser_fixture_report(report,subject)
        return report, subject
    finally:
        subject.stop_http()


@pytest.mark.parametrize("rid", [f"UX-{i:02d}" for i in range(1, 9)])
async def test_real_browser_good_ux_fixture(tmp_path, rid):
    report, subject = await run_browser(tmp_path, rid)
    result = report["requirements"][0]
    assert result["status"] == "PASS", result
    assert all(check["passed"] for check in result["observed"]), result
    assert result["limits"]==[]
    assert any(p["type"] == "V" and Path(p["path"]).is_file() for p in result["proofs"])
    text = json.dumps(report)
    for account in subject.adapter.manifest.accounts.values():
        assert account.password not in text


@pytest.mark.parametrize("rid,bug", [("UX-05","callback401_unwired"), ("UX-02","uuid_changed"),
                                  ("UX-06","reverse_responses"), ("UX-07","conflict_draft_lost"),
                                  ("UX-01","english_action"),("UX-03","invisible_focus"),
                                  ("UX-04","mobile_overflow"),("UX-05","private_cache"),
                                  ("UX-02","message_uuid_changed"),("UX-02","no_timeout"),
                                  ("UX-08","internal_style")])
async def test_real_browser_adversarial_fixture_detects_actual_ui_bug(tmp_path, rid, bug):
    report, _ = await run_browser(tmp_path, rid, bug)
    result = report["requirements"][0]
    assert result["status"] == "FAIL", result
    assert any(not c["passed"] for c in result["observed"])


@pytest.mark.parametrize("rid", ["SEC-10","SEC-12","FUN-02","FUN-06","FUN-12"])
async def test_browser_contribution_cannot_claim_complete_backend_requirement(tmp_path, rid):
    report, _ = await run_browser(tmp_path, rid)
    result = report["requirements"][0]
    assert result["status"] == "NOT_VERIFIED", result
    assert all(c["passed"] for c in result["observed"]), result
    assert any("backend" in limit for limit in result["limits"])
    alias = {"FUN-02":"ui_clear", "FUN-06":"ui_draft", "FUN-12":"ui_refresh"}.get(rid)
    if alias:
        assert any(p["type"] == "X" and rid + ":" + alias in p["checks"] for p in result["proofs"])


async def test_real_browser_xss_fixture_defect_detected(tmp_path):
    report, _ = await run_browser(tmp_path, "SEC-12", "xss_raw")
    assert report["requirements"][0]["status"] == "FAIL"


async def test_empty_browser_source_facts_produce_no_pass_or_product_probe(tmp_path):
    original = browser_contract()
    contract = import_contract(original.brief, original.reference, reviewed_by="fixture review", facts=[])
    subject = BrowserSubject(tmp_path / "product", contract)
    report = await BrowserVerifier(contract, subject.harness()).verify(subject.snapshot)
    assert all(r["status"] == "NOT_VERIFIED" for r in report["requirements"])


def test_browser_generation_is_source_exact_and_six_scenarios_are_reference_anchored():
    contract = browser_contract()
    fragment = browser_generation_requirements(contract)
    assert len(fragment["scenarios"]) == 6
    assert fragment["scenarios"][0]["expected"] in contract.reference
    assert all(row["expected"] == next(r.expected for r in contract.requirements if r.id == row["id"])
               for row in fragment["requirements"])


async def test_vertical_smoke_is_real_browser_login_create_plus_server_id_and_db(tmp_path):
    contract=browser_contract(); subject=BrowserSubject(tmp_path/"product",contract)
    subject.start_http()
    try:
        manifest=await subject.adapter.prepare_case("VERTICAL")
        result=await browser_smoke(subject.harness(),subject.snapshot,contract.contract_hash,manifest.accounts["alice"],
                                  title="Narrow foundation browser probe",description="Independent fixture description for foundation probe")
        assert result["status"]=="PASS",result
        conn=subject.connect()
        try:
            row=conn.execute("SELECT * FROM tickets WHERE id=?",(result["ticket_id"],)).fetchone()
            assert row["owner_id"]==manifest.accounts["alice"].id
            assert row["title"]=="Narrow foundation browser probe"
            assert row["description"]=="Independent fixture description for foundation probe"
        finally:conn.close()
        assert {"VERTICAL:browser_login","VERTICAL:browser_create","VERTICAL:frontend_wiring"} <= {tag for proof in result["proofs"] for tag in proof.checks}
        observer=next(proof for proof in result["proofs"] if proof.type=="X")
        evidence=json.loads(Path(observer.path).read_text())
        assert next(c for c in evidence["checks"] if c["check"]=="VERTICAL:detail_get_response_matches_created_values")["passed"]
        assert next(c for c in evidence["checks"] if c["check"]=="VERTICAL:detail_matches_get_response")["passed"]
    finally:subject.stop_http()


def test_wrong_detail_without_exact_field_bindings_is_not_admissible():
    class UnreviewedDetailBinding:
        bindings={"detail":"#detail"}
    with pytest.raises(AdapterUnavailable,match="exact detail title/description browser bindings required"):
        _exact_detail_bindings(UnreviewedDetailBinding())


@pytest.mark.asyncio
async def test_no_auth_smoke_does_not_require_login_binding():
    class NoLoginHarness:
        bindings={"ticket_list":"#tickets"}
        def control(self,*args): raise AssertionError("no-auth flow must not resolve a login locator")
    class Checks:
        def check(self,*args): raise AssertionError("no login element is not a browser check")
    await _check_optional_no_auth_login_visibility(NoLoginHarness(),Checks(),object())


async def test_all_six_source_e2e_execute_together_with_fresh_independent_fixtures(tmp_path):
    contract=browser_contract();subject=BrowserSubject(tmp_path/"product",contract)
    subject.start_http()
    try:
        report=await BrowserVerifier(contract,subject.harness()).verify_e2e(subject.snapshot,mode="together")
        retain_browser_fixture_report(report,subject)
        assert report["status"]=="PASS",report
        assert len(report["scenarios"])==6
        assert all(r["fixture_reset_before"] and r["mode"]=="together" and r["real_ui_api_db"] for r in report["scenarios"])
    finally:subject.stop_http()


@pytest.mark.parametrize("sid,bug",[("E2E-01","reply_not_saved"),("E2E-02","internal_leak"),
    ("E2E-03","idor_disabled"),("E2E-04","conflict_draft_lost"),
    ("E2E-05","old_session_revived"),("E2E-06","reverse_responses")])
async def test_each_source_e2e_rejects_an_executable_defect(tmp_path,sid,bug):
    contract=browser_contract();subject=BrowserSubject(tmp_path/"product",contract,bug)
    subject.start_http()
    try:
        report=await BrowserVerifier(contract,subject.harness()).verify_e2e(subject.snapshot,mode="alone",scenario_ids=[sid])
        retain_browser_fixture_report(report,subject)
        assert report["scenarios"][0]["status"]=="FAIL",report
        assert any(not c["passed"] for c in report["scenarios"][0]["observed"])
    finally:subject.stop_http()


@pytest.mark.parametrize("sid",["E2E-01","E2E-02","E2E-03","E2E-04","E2E-05","E2E-06"])
async def test_six_source_e2e_execute_independently(tmp_path,sid):
    contract=browser_contract();subject=BrowserSubject(tmp_path/"product",contract)
    subject.start_http()
    try:
        report=await BrowserVerifier(contract,subject.harness()).verify_e2e(subject.snapshot,mode="alone",scenario_ids=[sid])
        retain_browser_fixture_report(report,subject)
        result=report["scenarios"][0]
        assert result["expected"] in contract.reference
        assert result["fixture_reset_before"] is True
        assert result["status"]=="PASS",result
        assert all(c["passed"] for c in result["observed"]),result
    finally:subject.stop_http()
