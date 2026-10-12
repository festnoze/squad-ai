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
async def test_multiple_native_scopes_are_exact_and_ambiguous_scopes_rejected(tmp_path):
    from dataclasses import asdict
    snapshot="a"*64;store=SupervisorEvidenceStore(tmp_path,snapshot,CONTRACT)
    path=tmp_path/"actual-metatest-native-output.json"
    write_json(path,{"scope":"actual protocol unit output only; not product secret scan"})
    raw=Proof("X",str(path),hashlib.sha256(path.read_bytes()).hexdigest(),snapshot,CONTRACT,("METATEST:native_output",))
    with pytest.raises(AdapterUnavailable): await store.record_native_observation("secret_scan",{},parameters={"scope":"missing"})
    first=await store.record_native_observation("secret_scan",{"findings":["negative metatest"]},
        parameters={"scope":"source_image_logs"},source_proofs=(raw,))
    await store.record_native_observation("secret_scan",{"findings":[]},parameters={"scope":"logs_artifacts"},source_proofs=(raw,))
    assert await store.observe("secret_scan",scope="source_image_logs")=={"findings":["negative metatest"]}
    assert await store.observe("secret_scan",scope="logs_artifacts")=={"findings":[]}
    with pytest.raises(AdapterUnavailable): await store.observe("secret_scan")
    index=store._read(tmp_path/"observations.json")
    index["observations"]["secret_scan"].append(asdict(first));write_json(tmp_path/"observations.json",index)
    with pytest.raises(AdapterUnavailable): await store.observe("secret_scan",scope="source_image_logs")


@pytest.mark.asyncio
async def test_e2e_coordinator_executes_both_modes_and_preserves_missing_capability(tmp_path,monkeypatch):
    # Only protocol wiring is unit-replaced. These receipts explicitly say NV,
    # do not claim a real UI/API/DB and cannot award quality or product PASS.
    from autospec.validation.coordinator import _execute_e2e
    import autospec.validation.browser_contracts as browser_module
    reference="## 8. Six parcours E2E minimum\n"+"\n".join(f"{i}. Source scenario {i}" for i in range(1,7))+"\n## 9. End"
    contract=SimpleNamespace(reference=reference,contract_hash=CONTRACT)
    store=SupervisorEvidenceStore(tmp_path,"a"*64,CONTRACT);calls=[]
    monkeypatch.setattr(browser_module,"PlaywrightHarness",lambda *a,**k:None)
    class ProtocolOnlyVerifier:
        def __init__(self,*a): pass
        async def verify_e2e(self,snapshot_hash,*,mode,scenario_ids):
            calls.append((mode,scenario_ids));rows=[]
            for sid in scenario_ids:
                path=tmp_path/(sid+"-"+mode+".json");write_json(path,{"actual":"missing protocol-only port"})
                p=Proof("X",str(path),hashlib.sha256(path.read_bytes()).hexdigest(),snapshot_hash,CONTRACT,(),False)
                rows.append(dict(id=sid,expected="Source scenario "+str(int(sid[-2:])),mode=mode,
                    status="NOT_VERIFIED",proofs=[asdict(p)],snapshot_hash=snapshot_hash,contract_hash=CONTRACT,
                    real_ui_api_db=False,nominal_mocks=False,limits=["unit-only missing port"]))
            return dict(snapshot_hash=snapshot_hash,contract_hash=CONTRACT,scenarios=rows)
    from dataclasses import asdict
    monkeypatch.setattr(browser_module,"BrowserVerifier",ProtocolOnlyVerifier)
    harness=SimpleNamespace(adapter=None,bindings=SimpleNamespace(browser_bindings={},browser_routes={}))
    rows=await _execute_e2e(contract,harness,store,"a"*64)
    assert [mode for mode,_ in calls]==["alone"]*6+["together"] and len(rows)==12
    assert all(len(ids)==1 for _,ids in calls[:6]) and len(calls[-1][1])==6
    assert {r["status"] for r in rows}=={"NOT_VERIFIED"} and not store.contributions["TST-05"]
    import json
    assert await store.observe("browser_e2e")==json.loads(json.dumps(rows))


@pytest.mark.asyncio
@pytest.mark.parametrize("fault",[None,"duplicate","image_scope","unreviewed","changed_raw_mode","changed_source","changed_mapping","narrated_pass"])
async def test_e2e_reuse_requires_exact_native_12_mode_source_and_review_seal(tmp_path,fault):
    # Protocol-only fixtures: no assertion of real benchmark UI/API execution.
    # Their scoped JSON artifacts test cached receipt validation, not app PASS.
    import json
    from dataclasses import asdict,replace
    from autospec.validation.coordinator import publish_reviewed_e2e,_reuse_reviewed_e2e
    from autospec.validation.quality_contracts import write_quality_review_package,NativeSuiteSpec
    from autospec.validation.final_gate import source_snapshot
    source=tmp_path/"source";source.mkdir();(source/"main.py").write_bytes(b"# protocol receipt fixture only")
    snapshot=source_snapshot(source).digest;root=tmp_path/"supervisor";root.mkdir()
    contract=SimpleNamespace(contract_hash=CONTRACT,brief_hash="b"*64,reference_hash="d"*64,
        reference="## 8. Six parcours E2E minimum\n"+"\n".join(f"{i}. Source scenario {i}" for i in range(1,7))+"\n## 9. End",
        requirements=[SimpleNamespace(id="TST-05",expected="source exact scenarios",gate="B")])
    package=write_quality_review_package(contract,product_root=source,destination=root/"quality",snapshot_hash=snapshot,
        suites=(NativeSuiteSpec("backend",".","python",("main.py",),("metatest",)),),
        requirements_mapping={"TST-05":[dict(suite="backend",test="metatest::receipt",assertion="protocol-only receipt validation")]},nominal_security_db_mocks=False)
    review_path=root/"review.json";write_json(review_path,dict(scope="independent protocol-only review"))
    review=Proof("R",str(review_path),hashlib.sha256(review_path.read_bytes()).hexdigest(),snapshot,CONTRACT,tuple(package["required_review_checks"]))
    store=SupervisorEvidenceStore(root,snapshot,CONTRACT);rows=[]
    for mode in ("alone","together"):
        for index in range(1,7):
            eid=f"E2E-{index:02d}";expected=f"Source scenario {index}";observed=[dict(check="protocol_receipt",passed=True)]
            path=root/(mode+eid+".json")
            write_json(path,dict(mode=mode,source_expected=expected,checks=observed,scope="protocol-only, not real product execution"))
            x=Proof("X",str(path),hashlib.sha256(path.read_bytes()).hexdigest(),snapshot,CONTRACT,("TST-05:"+eid+":protocol",))
            vpath=root/(mode+eid+"-V.json");write_json(vpath,dict(scope="protocol stand-in, no browser proof issued"))
            v=Proof("V",str(vpath),hashlib.sha256(vpath.read_bytes()).hexdigest(),snapshot,CONTRACT,("TST-05:"+eid+":protocol",))
            rows.append(dict(id=eid,expected=expected,mode=mode,status="PASS",observed=observed,proofs=[asdict(x),asdict(v)],
                snapshot_hash=snapshot,contract_hash=CONTRACT,real_ui_api_db=True,nominal_mocks=False,fixture_reset_before=True,
                nonblank=True,unhandled_console_errors=[]))
    sealed=await publish_reviewed_e2e(store,rows,plan_path=package["plan_path"],review=review,source_root=source)
    if fault=="duplicate":sealed[-1]=sealed[0]
    elif fault=="image_scope":sealed[0]["image_id"]="sha256:"+"f"*64
    elif fault=="unreviewed":sealed[0]["quality_plan"]["review"]["passed"]=False
    elif fault=="changed_raw_mode":
        path=Path(sealed[0]["proofs"][0]["path"]);value=json.loads(path.read_bytes());value["mode"]="together";write_json(path,value)
        sealed[0]["proofs"][0]["sha256"]=hashlib.sha256(path.read_bytes()).hexdigest()
    elif fault=="changed_source":(source/"main.py").write_bytes(b"# source changed")
    elif fault=="changed_mapping":Path(package["mapping_path"]).write_bytes(b"{}")
    elif fault=="narrated_pass":sealed[0]["observed"]=[]
    proofs=[Proof(**p) for row in sealed for p in row["proofs"]]
    await store.record_native_observation("browser_e2e",sealed,source_proofs=proofs)
    if fault is None:
        reused=await _reuse_reviewed_e2e(contract,store,source)
        assert len(reused)==12 and len(store.contributions["TST-05"])==24
    else:
        with pytest.raises(AdapterUnavailable):await _reuse_reviewed_e2e(contract,store,source)


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
        # Typed schema-admission protocol only, not a benchmark execution.
        documented_commands=[dict(obligation=name,argv=["fixture-protocol",name],return_code=0)
            for name in ("install","tests","coverage","e2e","launch","seed","migration","backup","restore")],
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


@REAL
@pytest.mark.asyncio
async def test_real_quality_sqlite_probe_transactions_restart_and_cleanup(linux_fixture_source,tmp_path):
    from autospec.validation.coordinator import sqlite_quality_probe
    context=session(linux_fixture_source,tmp_path)
    contract=SimpleNamespace(contract_hash=CONTRACT,facts=[SimpleNamespace(kind="security_profile")])
    value=await sqlite_quality_probe(SimpleNamespace(id="independent-sqlite-quality-fixture"),contract,
        context.source_root,context.bindings.snapshot_hash,tmp_path)
    assert value["isolated"] and value["restart_verified"] and value["cleanup_owned_only"],value
    path=Path(value["database_path"])
    assert path.is_relative_to(Path(value["isolated_root"])) and path.read_bytes().startswith(b"SQLite format 3\x00")
    assert hashlib.sha256(path.read_bytes()).hexdigest()==value["database_sha256"]
    assert len(set(value["connection_ids"]))>=2
    store=SupervisorEvidenceStore(tmp_path,context.bindings.snapshot_hash,CONTRACT)
    assert await store.observe("real_sqlite_test_environment")==value
    proofs=await store.proofs("TST-04")
    assert len(proofs)>=2 and all(p.type=="X" and p.passed and p.intact(
        snapshot_hash=context.bindings.snapshot_hash,contract_hash=CONTRACT) for p in proofs)
