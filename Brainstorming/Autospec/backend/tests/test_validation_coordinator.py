import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from autospec.contracts import import_contract
from autospec.validation.coordinator import (SupervisorEvidenceStore,_merge,verify_project,verify_vertical,
    binding_proposal_schema,prepare_binding_proposal,install_reviewed_configuration)
from autospec.validation.support_adapter import AdapterUnavailable,Proof
from tests.test_product_harness import (CONTRACT,REAL,fixture_definition,make_bindings,linux_fixture_source,session,write_json)


@pytest.mark.asyncio
async def test_missing_binding_inputs_returns_exact_57_ids_without_false_pass(tmp_path):
    docs=Path(__file__).resolve().parents[2]/"docs/validation/support-client"
    contract=import_contract((docs/"01_specification.md").read_text(encoding="utf-8"),
        (docs/"02_requirements_verification.md").read_text(encoding="utf-8"),reviewed_by="independent coordinator fixture")
    source=tmp_path/"source";source.mkdir();(source/"main.py").write_bytes(b"raise RuntimeError('never execute host')")
    from autospec.validation.final_gate import source_snapshot
    snapshot=source_snapshot(source).digest
    reports=await verify_project(SimpleNamespace(id="fixture"),contract,source,snapshot,tmp_path/"proofs")
    rows=reports[0]["requirements"]
    assert len(rows)==57 and len({r["id"] for r in rows})==57
    assert {r["id"] for r in rows}=={r.id for r in contract.requirements}
    assert all(r["status"]=="NOT_VERIFIED" for r in rows)
    assert all({"expected","observed","reproduction","proofs","impact","limits"}<=r.keys() for r in rows)
    assert reports[0]["status"]=="NOT_VERIFIED"


def test_browser_supplement_cannot_erase_failure_or_missing_native_probe():
    for previous in ("FAIL","NOT_VERIFIED"):
        row=dict(status=previous,proofs=[],observed=[],limits=[])
        _merge(row,dict(status="PASS",proofs=[],observed=[],limits=[]))
        assert row["status"]==previous
    row=dict(status="PASS",proofs=[],observed=[],limits=[])
    _merge(row,dict(status="FAIL",proofs=[],observed=[],limits=[]))
    assert row["status"]=="FAIL"


@pytest.mark.asyncio
async def test_native_observation_requires_exact_intact_external_payload(tmp_path):
    snapshot="a"*64; store=SupervisorEvidenceStore(tmp_path,snapshot,CONTRACT)
    path=tmp_path/"native.json";write_json(path,dict(name="coverage",parameters={},value={"failed":True},
        snapshot_hash=snapshot,contract_hash=CONTRACT))
    proof=Proof("X",str(path),hashlib.sha256(path.read_bytes()).hexdigest(),snapshot,CONTRACT,("OBS:coverage",))
    write_json(tmp_path/"observations.json",dict(snapshot_hash=snapshot,contract_hash=CONTRACT,observations={"coverage":proof.__dict__}))
    assert await store.observe("coverage")=={"failed":True}
    with pytest.raises(AdapterUnavailable): await store.observe("coverage",arbitrary=True)
    path.write_bytes(path.read_bytes()+b" ")
    with pytest.raises(AdapterUnavailable): await store.observe("coverage")
    with pytest.raises(AdapterUnavailable): await store.observe("account_count")


@pytest.mark.asyncio
async def test_binding_proposal_can_be_reviewed_then_used_without_manual_plugin(tmp_path):
    from dataclasses import asdict
    from autospec.validation.final_gate import source_snapshot
    from autospec.validation.product_harness import OwnedProductHarnessSession
    source=tmp_path/"source";source.mkdir();(source/"main.py").write_bytes(b"# reviewed source, never imported")
    snapshot=source_snapshot(source).digest
    root=tmp_path/"supervisor";root.mkdir()
    bindings=make_bindings(root,source,snapshot)
    candidate=asdict(bindings)
    for k in ("review","snapshot_hash","contract_hash","source_files","fixture_fingerprint"): candidate.pop(k)
    assert set(candidate)==set(binding_proposal_schema()["properties"]["bindings"]["required"])
    contract=SimpleNamespace(contract_hash=CONTRACT,facts=[SimpleNamespace(kind="security_profile")])
    proposal=await prepare_binding_proposal(dict(source_files=["main.py"],bindings=candidate),
        dict(cases={"VERTICAL":fixture_definition()}),contract=contract,snapshot_root=source,snapshot_hash=snapshot)
    reviews=[]
    for kind in ("binding","fixture"):
        path=root/(kind+"-reviewed.json")
        # This independent meta-review is not a review of benchmark product.
        write_json(path,dict(scope="independent configuration metatest review",checks=proposal[kind+"_checks"]))
        reviews.append(Proof("R",str(path),hashlib.sha256(path.read_bytes()).hexdigest(),snapshot,CONTRACT,
            tuple(proposal[kind+"_checks"])))
    result=await install_reviewed_configuration(proposal,binding_review=reviews[0],fixture_review=reviews[1],
        supervisor_root=root,snapshot_root=source)
    assert result["status"]=="REVIEWED" and "PASS" not in result.values()
    async def identity(): return snapshot
    async def oracle(): return CONTRACT
    context=OwnedProductHarnessSession.from_bindings(root/"product-bindings.json",source_root=source,
        fixtures_path=root/"reviewed-fixtures.json",stage_root=root/"stage",evidence_root=root/"proofs",
        cache_root=root/"cache",snapshot_hash=identity,contract_hash=oracle)
    assert context.factory.fingerprint==context.bindings.fixture_fingerprint
    manifest,payload=await context.factory("VERTICAL")
    assert len(manifest.accounts)==5 and len(payload["seed"]["payload"]["tickets"])==12
    bad=asdict(reviews[0]);bad["passed"]=False
    with pytest.raises(AdapterUnavailable):
        await install_reviewed_configuration(proposal,binding_review=Proof(**bad),fixture_review=reviews[1],
            supervisor_root=root,snapshot_root=source)
    candidate["auth_required"]=False
    with pytest.raises(AdapterUnavailable):
        await prepare_binding_proposal(dict(source_files=["main.py"],bindings=candidate),dict(cases={"VERTICAL":fixture_definition()}),
            contract=contract,snapshot_root=source,snapshot_hash=snapshot)


@pytest.mark.asyncio
@pytest.mark.parametrize("finding,expected",[(None,"PASS"),("high","FAIL"),("unavailable","NOT_VERIFIED")])
async def test_operations_docs_audit_never_compensated_by_health_or_fixture(tmp_path,finding,expected):
    from dataclasses import asdict
    from autospec.validation.coordinator import _operations
    snapshot="a"*64;source=tmp_path/"source";source.mkdir();root=tmp_path/"supervisor";root.mkdir()
    (source/"README.md").write_bytes(b"# Independent schema-admission metatest, not benchmark product review")
    (source/"config.py").write_bytes(b"LOCAL_ONLY = True")
    def raw(name,payload,kind="X",checks=()):
        path=root/(name+".json");write_json(path,payload)
        return Proof(kind,str(path),hashlib.sha256(path.read_bytes()).hexdigest(),snapshot,CONTRACT,checks)
    audit=raw("raw-audit",{"actual":"meta unit fixture raw audit"},checks=("OBS:audit_raw",))
    value=dict(readme=dict(path="README.md",sha256=hashlib.sha256((source/"README.md").read_bytes()).hexdigest()),
        documented_commands=[dict(argv=["/opt/venv/bin/python","main.py","migrate"],return_code=0)],
        configuration=[dict(path="config.py",source_sha256=hashlib.sha256((source/"config.py").read_bytes()).hexdigest(),secrets_found=[])],
        fixtures_explicit=True,accounts_before_fixture=0,
        audit=dict(status="UNAVAILABLE" if finding=="unavailable" else "AVAILABLE",date="2026-10-12T00:00:00Z",tool="independent fixture audit",
            report_valid=True,return_code=1 if finding=="high" else 0,artifacts=[asdict(audit)],
            findings=[] if finding!="high" else [dict(severity="high",exploitable=True,arbitration=None)]))
    obs=raw("docs-audit",dict(name="docs_audit",parameters={},value=value,snapshot_hash=snapshot,contract_hash=CONTRACT),checks=("OBS:docs_audit",))
    review=raw("source-review",{"scope":"independent meta-admission only; not actual product audit"},"R",("OPS-05:README","OPS-05:audit"))
    write_json(root/"observations.json",dict(snapshot_hash=snapshot,contract_hash=CONTRACT,observations={"docs_audit":asdict(obs)}))
    write_json(root/"proofs.json",dict(snapshot_hash=snapshot,contract_hash=CONTRACT,proofs={"OPS-05":[asdict(review)]}))
    requirement=SimpleNamespace(id="OPS-05",gate="M",expected="source-exact README and dated audit",required_evidence=("X","R"))
    rows=await _operations(SimpleNamespace(contract_hash=CONTRACT,requirements=[requirement]),source,snapshot,root)
    assert rows["OPS-05"]["status"]==expected,rows
    assert rows["OPS-05"]["proofs"] and rows["OPS-05"]["reproduction"]


@REAL
@pytest.mark.asyncio
async def test_real_coordinator_vertical_public_api_nominal(linux_fixture_source,tmp_path):
    # Source expectations/auth fixture identity explicit; real HTTP and browser
    # are not mocked. This narrow fixture is not 57-ID product acceptance.
    context=session(linux_fixture_source,tmp_path)
    contract=SimpleNamespace(contract_hash=CONTRACT,facts=[SimpleNamespace(kind="security_profile")])
    state=SimpleNamespace(id="independent-linux-fixture")
    receipt=await verify_vertical(state,contract,context.source_root,context.bindings.snapshot_hash,tmp_path)
    assert receipt["status"]=="PASS",receipt
    assert receipt["ticket_id"]
    assert all(s["passed"] for s in receipt["stages"])
    assert all(Path(p["path"]).is_relative_to(tmp_path/"vertical"/context.bindings.snapshot_hash/"evidence")
               for s in receipt["stages"] for p in s["proofs"])
