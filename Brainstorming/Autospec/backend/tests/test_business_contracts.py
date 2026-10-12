from pathlib import Path

import pytest

from autospec.contracts import import_contract
from autospec.validation.business_contracts import BusinessContractVerifier, BUSINESS_CHECKS
from autospec.validation.support_adapter import AdapterUnavailable, Proof
from tests.support_contract_fixture import SQLiteSupportSubject, retain_fixture_report


@pytest.fixture
def support_contract():
    root=Path(__file__).resolve().parents[2]/"docs/validation/support-client"
    return import_contract((root/"01_specification.md").read_text(encoding="utf-8"),
        (root/"02_requirements_verification.md").read_text(encoding="utf-8"),reviewed_by="independent fixture test")


async def run_pack(subject):
    try:
        report=await BusinessContractVerifier(subject.adapter,subject.contract).verify(subject.snapshot)
        retain_fixture_report(report,subject)
        return {r["id"]:r for r in report["requirements"]}
    finally: await subject.adapter.close()


@pytest.mark.asyncio
async def test_real_good_business_fixture(tmp_path,support_contract):
    subject=SQLiteSupportSubject(tmp_path,support_contract)
    results=await run_pack(subject)
    assert set(results)==set(BUSINESS_CHECKS)
    failures={rid:r for rid,r in results.items() if r["status"]=="FAIL"}
    assert not failures,failures
    for rid in ("FUN-01","FUN-04","FUN-05","FUN-10","FUN-11","FUN-13"):
        assert results[rid]["status"]=="PASS",results[rid]
    for rid in ("FUN-02","FUN-06","FUN-07","FUN-08","FUN-09","FUN-12"):
        assert results[rid]["status"]=="NOT_VERIFIED",results[rid]
    # Missing UI/source review never becomes PASS through native green HTTP.
    assert any("ui_clear" in limit for limit in results["FUN-02"]["limits"])
    assert any("append_only" in limit for limit in results["FUN-08"]["limits"])
    matrix=[e for e in results["FUN-04"]["observed"] if e["check"]=="matrix"]
    assert len(matrix)==16
    assert len({(e["observed"]["from"],e["observed"]["to"]) for e in matrix})==16


@pytest.mark.parametrize("bug,rid,check",[("agent_creation","FUN-01","roles"),
    ("open_resolved","FUN-04","matrix"),("ignored_filters","FUN-11","filters")])
@pytest.mark.asyncio
async def test_deliberate_business_counterexamples(tmp_path,support_contract,bug,rid,check):
    results=await run_pack(SQLiteSupportSubject(tmp_path,support_contract,bug))
    assert results[rid]["status"]=="FAIL",results[rid]
    assert any(e["check"]==check and not e["passed"] for e in results[rid]["observed"])
    assert results[rid]["reproduction"]
    assert all(p["snapshot_hash"]=="a"*64 and Path(p["path"]).is_file() for p in results[rid]["proofs"])


@pytest.mark.asyncio
async def test_no_auth_bypass_and_no_secret_evidence(tmp_path,support_contract):
    subject=SQLiteSupportSubject(tmp_path,support_contract)
    await subject.adapter.prepare_case("auth")
    response=await subject.adapter.request(None,"GET","/api/tickets")
    assert response.status_code==401
    manifest=subject.adapter.manifest
    subject.adapter.manifest=type(manifest)({**manifest.accounts,"alice":type(manifest.accounts["alice"])(
        manifest.accounts["alice"].id,manifest.accounts["alice"].email,"incorrect-secret", "client")},manifest.tickets,manifest.metadata)
    response=await subject.adapter.request("alice","GET","/api/tickets")
    assert response.status_code==401
    await subject.adapter.close()
    results=await run_pack(subject)
    for path in (tmp_path/"proofs").rglob("*.json"):
        data=path.read_text(encoding="utf-8")
        for account in subject.manifest.accounts.values(): assert account.password not in data
        assert "incorrect-secret" not in data
        assert "pbkdf2" not in data
    assert results["FUN-04"]["status"]=="PASS"


@pytest.mark.asyncio
async def test_identity_and_missing_ports_are_not_verified(tmp_path,support_contract):
    subject=SQLiteSupportSubject(tmp_path,support_contract)
    report=await BusinessContractVerifier(subject.adapter,support_contract).verify("b"*64)
    assert report["status"]=="NOT_VERIFIED"
    assert all(not r["observed"] for r in report["requirements"])
    async def absent(*args,**kw): raise AdapterUnavailable("fixture cannot be reset")
    subject.adapter._ports["prepare"]=absent
    report=await BusinessContractVerifier(subject.adapter,support_contract).verify(subject.snapshot)
    assert all(r["status"]=="NOT_VERIFIED" for r in report["requirements"])


@pytest.mark.asyncio
async def test_null_observation_is_not_proof_of_unchanged_database(tmp_path,support_contract):
    subject=SQLiteSupportSubject(tmp_path,support_contract)
    original=subject.adapter._ports["observe"]
    async def missing(name,**params):
        return None if name=="business_state" else await original(name,**params)
    subject.adapter._ports["observe"]=missing
    results=await run_pack(subject)
    assert results["FUN-13"]["status"]=="NOT_VERIFIED"
    assert not results["FUN-13"]["observed"]


@pytest.mark.asyncio
async def test_tampered_proof_cannot_upgrade_unverified_or_failure(tmp_path,support_contract):
    subject=SQLiteSupportSubject(tmp_path,support_contract,"agent_creation")
    path=tmp_path/"not-proof.json"; path.write_text("{}",encoding="utf-8")
    proof=Proof("R",str(path),"f"*64,subject.snapshot,support_contract.contract_hash,("FUN-08:append_only",))
    async def supplied(rid): return [proof]
    subject.adapter._ports["proofs"]=supplied
    results=await run_pack(subject)
    assert results["FUN-08"]["status"]=="NOT_VERIFIED"
    assert results["FUN-01"]["status"]=="FAIL"


def test_documents_are_pinned(support_contract,tmp_path):
    from dataclasses import replace
    with pytest.raises(ValueError,match="pinned"):
        BusinessContractVerifier(None,replace(support_contract,brief=support_contract.brief+"\nchanged"))
    fake=replace(support_contract.requirements[0],expected="always green")
    with pytest.raises(ValueError,match="pinned source"):
        BusinessContractVerifier(None,replace(support_contract,requirements=(fake,)+support_contract.requirements[1:]))
