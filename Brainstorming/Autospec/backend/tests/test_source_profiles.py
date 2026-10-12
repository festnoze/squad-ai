"""Source expectations and operational binding metadata stay separate."""
import json
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from autospec.validation.browser_contracts import BrowserVerifier, browser_generation_requirements
from autospec.validation.security_contracts import SecurityVerifier, security_generation_requirements
from autospec.validation.support_adapter import AdapterUnavailable
from tests.fixtures.browser.app import BrowserSubject, browser_contract
from tests.fixtures.security.app import SecurityApplication, security_contract
from tests.test_browser_contracts import run_browser
from tests.test_browser_harness_boundary import harness


def test_generation_oracle_does_not_copy_operational_fixture_markers_or_labels():
    browser=browser_generation_requirements(browser_contract())["formal_profile"]
    assert set(browser)=={"timeout_ms","desktop_width","mobile_width","client_ticket_count","staff_ticket_count"}
    assert browser==dict(timeout_ms=15000,desktop_width=1280,mobile_width=390,client_ticket_count=6,staff_ticket_count=12)
    security=security_generation_requirements(security_contract())["formal_profile"]
    assert security["session"]["min_entropy_bits"]==256 and "min_token_chars" not in security["session"]
    assert "db_fault" not in security["statuses"] and security["statuses"]["db_busy"]==503


def test_old_oracle_marker_fields_do_not_supply_missing_reviewed_fixture_metadata():
    contract=browser_contract()
    owner=SimpleNamespace(adapter=SimpleNamespace(manifest=SimpleNamespace(metadata={})))
    verifier=BrowserVerifier(contract,owner)
    verifier.profile["search_a"]="oracle-only-not-a-binding"
    with pytest.raises(AdapterUnavailable,match="metadata"):
        verifier.operational_probe("search_a")


@pytest.mark.parametrize("kind,field",[("browser_profile","search_a"),("browser_profile","french_action_labels"),
    ("security_profile","min_token_chars"),("security_profile","db_fault")])
def test_generation_rejects_deprecated_operational_or_invented_oracle_fields(kind,field):
    from autospec.contracts import ContractFact, import_contract
    original=browser_contract() if kind=="browser_profile" else security_contract()
    facts=[]
    for fact in original.facts:
        expected=fact.expected
        if fact.kind==kind:
            target=expected["session"] if field=="min_token_chars" else expected["statuses"] if field=="db_fault" else expected
            target[field]="deprecated"
        facts.append(ContractFact.create(fact.id,fact.kind,expected,fact.requirement_ids,fact.source_excerpt))
    contract=import_contract(original.brief,original.reference,reviewed_by="meta-test",facts=facts)
    with pytest.raises(AdapterUnavailable):
        (browser_generation_requirements if kind=="browser_profile" else security_generation_requirements)(contract)


async def test_guards_can_be_installed_before_first_navigation_without_weakening_defaults():
    owner,browser,case,checks,events=harness()
    await owner.page(case,1280,auto_navigate=False)
    assert "new_page" in events and "http_guard" in events and "ws_guard" in events and "goto" not in events
    owner,browser,case,checks,events=harness()
    await owner.page(case,1280)
    assert "goto" in events
    for value in (None,1,"false"):
        owner,browser,case,checks,events=harness()
        with pytest.raises(ValueError):await owner.page(case,1280,auto_navigate=value)
        assert events==[]


async def test_old_connected_browser_is_closed_and_never_adopts_restarted_namespace():
    owner,browser,case,checks,events=harness()
    closed=[]
    class OldNamespace:
        @property
        def endpoint(self): raise AdapterUnavailable("pinned parent identity changed")
        def close(self): closed.append("container")
    owner.docker_browser=OldNamespace()
    with pytest.raises(AdapterUnavailable,match="namespace adoption"):
        await owner.page(case,1280)
    assert "context" not in events and closed==["container"] and owner.browser is None
    assert owner.browser_environment==dict(qualified=False,runtime_changed=True)
    with pytest.raises(AdapterUnavailable):await owner.page(case,1280)
    assert "context" not in events and owner._runtime_invalidated is True


@pytest.mark.parametrize("rid", ["UX-01","UX-06"])
async def test_real_browser_source_profile_without_operational_fields_runs_from_fixture_bindings(tmp_path,rid):
    report,_=await run_browser(tmp_path,rid)
    assert report["requirements"][0]["status"]=="PASS",report


async def test_missing_operational_search_fixture_metadata_is_explicitly_not_verified(tmp_path):
    contract=browser_contract();subject=BrowserSubject(tmp_path/"product",contract)
    original=subject.adapter._ports["prepare"]
    async def prepare(*args,**kwargs):
        manifest=await original(*args,**kwargs);manifest.metadata.pop("browser_probes",None);return manifest
    subject.adapter._ports["prepare"]=prepare
    subject.start_http()
    try:
        report=await BrowserVerifier(contract,subject.harness()).verify(subject.snapshot,ids=["UX-06"])
        row=report["requirements"][0]
        assert row["status"]=="NOT_VERIFIED",row
        assert any("metadata" in limit for limit in row["limits"])
    finally:subject.stop_http()


@pytest.mark.parametrize("bug,status", [("db_fault_502","PASS"),("db_busy_503","PASS"),
    ("db_busy_500","FAIL"),("db_fault_success","FAIL"),("db_fault_html","FAIL")])
async def test_other_database_errors_are_generic_but_db_busy_keeps_exact_source_status(tmp_path,bug,status):
    contract=security_contract();app=SecurityApplication(tmp_path/"product",broken=bug,only="SEC-15")
    adapter,snapshot,_=app.adapter(contract)
    rows=await SecurityVerifier(contract,adapter).verify(snapshot)
    row=next(row for row in rows if row["id"]=="SEC-15")
    assert row["status"]==status,row


def test_campaign_facts_candidate_has_exact_immutable_source_anchors_and_no_operational_oracle():
    from autospec.contracts import ContractFact, import_contract
    root=Path(__file__).resolve().parents[2]
    artifact=json.loads((root/"artifacts/remediation/REM-25/source-facts-v02.json").read_text(encoding="utf-8"))
    docs={name:(root/"docs/validation/support-client"/name).read_bytes() for name in artifact["sources"]}
    assert {name:hashlib.sha256(raw).hexdigest() for name,raw in docs.items()}==artifact["sources"]
    for anchor in artifact["anchors"]:
        assert anchor["verbatim"] in docs[anchor["document"]].decode("utf-8"),anchor
    facts=[ContractFact.create(**fact) for fact in artifact["acceptance_facts"]]
    contract=import_contract(docs["01_specification.md"].decode("utf-8"),docs["02_requirements_verification.md"].decode("utf-8"),
        facts=facts,reviewed_by="source-extraction meta-test; parent campaign review still required")
    assert len(contract.requirements)==57 and len({row.id for row in contract.requirements})==57
    profile=browser_generation_requirements(contract)["formal_profile"]
    assert set(profile)=={"timeout_ms","desktop_width","mobile_width","client_ticket_count","staff_ticket_count"}
    security=security_generation_requirements(contract)["formal_profile"]
    assert security["session"]["min_entropy_bits"]==256 and "db_fault" not in security["statuses"]
