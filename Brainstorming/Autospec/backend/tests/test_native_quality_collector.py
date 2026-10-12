"""Collector port meta-tests; one real HTTP/SQLite/Argon2 mutation probe.

The native suite stub tests orchestration only, NOT Linux execution. The
coordinator tests IsolatedValidator separately; no product script runs here.
"""
import hashlib
import asyncio
import json
import shutil
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from autospec.validation.quality_contracts import NativeQualityCollector, NativeSuiteSpec, AuthorizationMutationSpec, QualityVerifier, write_quality_review_package, supervisor_e2e_test_id
from autospec.validation.support_adapter import AdapterUnavailable, Proof
from tests.fixtures.browser.app import BrowserSubject,browser_contract


class NativePortStub:
    def __init__(self):self.calls=[]
    def run_suite(self,root,ecosystem,mode,reportpath,**options):
        self.calls.append((root,ecosystem,mode,reportpath,options))
        reportpath.write_text(json.dumps({"scope":"native port stub, not executed product suite","tests":["fixture::native"]}),encoding="utf-8")
        counts=dict(passed=1,failed=0,error=0,xpassed=0,skipped=0,xfailed=0)
        evidence=SimpleNamespace(outcomes={"fixture::native":"passed"},counts=counts,collected=1,exit_code=0,report_valid=True,collection_errors=())
        coverage={"files":{"auth.py":{"summary":{"num_statements":10,"covered_lines":10,"num_branches":2,"covered_branches":2}}},"totals":{}}
        if options["coveragepath"]:options["coveragepath"].write_text(json.dumps(coverage),encoding="utf-8")
        return SimpleNamespace(evidence=evidence,coverage=coverage,output="unit port record only",source_fingerprint="b"*64,image="sha256:"+"c"*64,fingerprint="d"*64)


def plan(tmp_path):
    contract=browser_contract();subject=BrowserSubject(tmp_path/"runtime",contract)
    product=tmp_path/"product";(product/"backend").mkdir(parents=True)
    (product/"backend/auth.py").write_text("# trusted unit fixture source\n",encoding="utf-8")
    mapping=tmp_path/"mapping.json"
    mapping.write_text(json.dumps({"snapshot_hash":subject.snapshot,"contract_hash":contract.contract_hash,"nominal_security_db_mocks":False,
        "requirements":{r.id:[dict(suite="backend",test="fixture::native",assertion="independent unit port check")] for r in contract.requirements if r.gate!="D"}}),encoding="utf-8")
    reviewpath=tmp_path/"review.json";reviewpath.write_text('{"scope":"unit native port review only"}',encoding="utf-8")
    review=Proof("R",str(reviewpath),hashlib.sha256(reviewpath.read_bytes()).hexdigest(),subject.snapshot,contract.contract_hash,())
    runner=NativePortStub()
    collector=NativeQualityCollector(contract,subject.adapter,runner,product_root=product,evidence_root=tmp_path/"proofs",
        suites=(NativeSuiteSpec("backend","backend","python",("auth.py",),("auth","services","permissions")),),mapping_path=mapping,review=review)
    collector.review=replace(review,checks=("QUALITY:plan:"+collector.plan_hash,"TST-01:native_review","TST-02:mapping","TST-03:inventory"))
    return collector,subject,runner


async def test_collector_executes_reviewed_isolated_native_port_and_retains_raw_reports(tmp_path):
    collector,subject,runner=plan(tmp_path)
    await collector.collect(subject.snapshot)
    assert len(runner.calls)==1
    assert runner.calls[0][1:3]==("python","test")
    native=await collector.observe("native_suites")
    assert native[0]["source_files"]["auth.py"]==hashlib.sha256((collector.product_root/"backend/auth.py").read_bytes()).hexdigest()
    assert Path(native[0]["raw_report"]["path"]).is_relative_to(collector.evidence_root)
    assert native[0]["collected"]==native[0]["passed"]==1
    assert (await collector.observe("requirement_test_mapping"))["SEC-09"][0]["executed"] is True
    for missing in ["browser_e2e","real_sqlite_test_environment","authorization_mutation"]:
        with pytest.raises(AdapterUnavailable):await collector.observe(missing)


async def test_unreviewed_native_plan_cannot_execute_even_one_suite(tmp_path):
    collector,subject,runner=plan(tmp_path)
    collector.review=replace(collector.review,checks=("TST-01",))
    with pytest.raises(AdapterUnavailable):await collector.collect(subject.snapshot)
    assert runner.calls==[]


async def test_changed_mapping_cannot_reuse_previous_plan_review(tmp_path):
    collector,subject,runner=plan(tmp_path)
    collector.mapping_path.write_text('{}',encoding="utf-8")
    with pytest.raises(AdapterUnavailable):await collector.collect(subject.snapshot)
    assert runner.calls==[]


def test_local_review_package_has_exact_mapping_source_hashes_and_no_approval(tmp_path):
    collector,subject,_=plan(tmp_path)
    mapping=json.loads(collector.mapping_path.read_text())["requirements"]
    result=write_quality_review_package(collector.contract,product_root=collector.product_root,destination=tmp_path/"review-package",
        snapshot_hash=subject.snapshot,suites=collector.suites,requirements_mapping=mapping,nominal_security_db_mocks=False)
    package=json.loads(Path(result["plan_path"]).read_text(encoding="utf-8"))
    assert package["status"]=="AWAITING_INDEPENDENT_REVIEW"
    assert len(package["requirements"])==57
    assert "QUALITY:plan:"+result["plan_hash"] in result["required_review_checks"]
    assert package["source_inventory"]["backend"]["auth.py"]==hashlib.sha256((collector.product_root/"backend/auth.py").read_bytes()).hexdigest()


async def test_missing_coverage_inventory_file_is_never_removed_from_denominator(tmp_path):
    collector,subject,runner=plan(tmp_path)
    spec=replace(collector.suites[0],source_inventory=("auth.py","never_run.py"))
    result=collector._coverage(spec,{"files":{"auth.py":{"summary":{"num_statements":10,"covered_lines":10}}}},
        {"path":"unit-placeholder","sha256":"0"*64})
    assert result["source_inventory"]==["auth.py","never_run.py"]
    assert "never_run.py" not in result["files"]


@pytest.mark.parametrize("field,value",[("name","../escaped"),("name","x:y"),("root","../product"),("root","C:relative"),
    ("root","backend//src"),("source_inventory",("auth.py","auth.py")),("source_inventory",("../auth.py",)),
    ("source_inventory",("auth.py:stream",))])
def test_native_profile_rejects_unreviewable_structural_paths(field,value):
    fields=dict(name="backend",root="backend",ecosystem="python",source_inventory=("auth.py",),domains=("auth",))
    fields[field]=value
    with pytest.raises(ValueError):NativeSuiteSpec(**fields)


def test_collector_rejects_duplicate_suite_names_before_any_execution(tmp_path):
    collector,subject,runner=plan(tmp_path)
    with pytest.raises(ValueError):NativeQualityCollector(collector.contract,subject.adapter,runner,
        product_root=collector.product_root,evidence_root=tmp_path/"new-evidence",suites=collector.suites*2,
        mapping_path=collector.mapping_path,review=collector.review)


def test_supervisor_e2e_aggregation_preserves_fail_and_not_verified_without_fake_native_pass(tmp_path):
    collector,subject,_=plan(tmp_path);collector.evidence_root.mkdir()
    runs=[dict(id=f"E2E-{i:02d}",mode=mode,status="NOT_VERIFIED") for mode in ["alone","together"] for i in range(1,7)]
    runs[0]["status"]="FAIL";runs[1]["status"]="NOT_VERIFIED"
    suite=collector._browser_suite(runs,subject.snapshot)
    assert suite["scope"]=="supervisor_browser"
    assert suite["collected"]==12 and suite["passed"]==0 and suite["failed"]==1 and suite["not_verified"]==11
    assert suite["return_code"]==1
    assert suite["outcomes"][supervisor_e2e_test_id("E2E-01","alone")]=="failed"
    assert suite["outcomes"][supervisor_e2e_test_id("E2E-02","alone")]=="not_verified"
    runs[0]["status"]="NOT_VERIFIED"
    assert collector._browser_suite(runs,subject.snapshot)["return_code"] is None
    runs[0]["status"]="PASS"
    with pytest.raises(AdapterUnavailable):collector._browser_suite(runs,subject.snapshot)


async def test_exact_mutation_copy_is_executed_over_real_http_and_original_remains_intact(tmp_path):
    collector,subject,_=plan(tmp_path)
    policy=collector.product_root/"authorization-policy.json"
    policy.write_text('{"require_ownership":true}',encoding="utf-8")
    original=policy.read_bytes();original_hash=hashlib.sha256(original).hexdigest()
    collector.mutation=AuthorizationMutationSpec("authorization-policy.json",original_hash,"true","false")
    proofs=tmp_path/"mutation-proofs";proofs.mkdir()
    async def probe(root,snapshot,contract_hash):
        enabled=json.loads((Path(root)/"authorization-policy.json").read_text())["require_ownership"]
        case=BrowserSubject(tmp_path/("subject-"+uuid4().hex),collector.contract,"" if enabled else "idor_disabled")
        case.start_http();case.adapter._transport_factory=None # actual TCP ingress, never mock login/session
        try:
            manifest=await case.adapter.prepare_case("authorization-mutation")
            tid=manifest.tickets["alice_open"]
            denied=await case.adapter.request("bob","GET","/api/tickets/"+tid)
            mixed=await case.adapter.request("alice","GET","/api/tickets/"+manifest.tickets["alice_mixed"]+"/messages")
            state=await case.adapter.observe("ticket_state",ticket_id=tid)
            first,stale=await asyncio.gather(case.adapter.request("camille","PATCH","/api/tickets/"+tid,json={"expected_version":state["version"],"priority":"high"}),
                case.adapter.request("dylan","PATCH","/api/tickets/"+tid,json={"expected_version":state["version"],"priority":"low"}))
            values={"SEC-09":([denied.status_code],[404]),"SEC-10":([mixed.status_code,"INTERNAL_SEED_MIXED" in json.dumps(mixed.json())],[200,False]),
                "FUN-06":(sorted([first.status_code,stale.status_code]),[200,409])}
            rows={}
            for rid,(actual,expected) in values.items():
                check={"check":rid+":real_http_mutation_probe","observed":actual,"expected":expected,"passed":actual==expected}
                path=proofs/(rid+"-"+uuid4().hex+".json")
                path.write_text(json.dumps({"snapshot_hash":snapshot,"contract_hash":contract_hash,"checks":[check],
                    "authorization_policy_sha256":hashlib.sha256((Path(root)/"authorization-policy.json").read_bytes()).hexdigest()}),encoding="utf-8")
                proof=Proof("X",str(path),hashlib.sha256(path.read_bytes()).hexdigest(),snapshot,contract_hash,(check["check"],),check["passed"])
                rows[rid]={'status':"PASS" if check["passed"] else "FAIL","observed":[check],"proofs":[proof.__dict__]}
            return rows
        finally:await case.adapter.close();case.stop_http()
    collector.mutation_probe=probe
    collector.source_snapshotter=lambda root:SimpleNamespace(digest=hashlib.sha256(json.dumps({"version":1,
        "files":{p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path(root).rglob('*')) if p.is_file()}},sort_keys=True,separators=(',',':')).encode()).hexdigest())
    collector.copy_product=lambda source,target:Path(shutil.copytree(source,target)) # trusted fixture only; no links exist
    result=await collector._mutation(subject.snapshot)
    assert result["original_status"]=="PASS",result
    assert result["mutated_status"]=="FAIL",result
    assert result["mutated_results"]["SEC-09"]["status"]=="FAIL"
    assert policy.read_bytes()==original
    assert result["original_before_sha256"]==result["original_after_sha256"]==original_hash
    assert result["mutated_sha256"]!=original_hash
    collector.records["authorization_mutation"]=result
    collector.review=replace(collector.review,checks=collector.review.checks+("TST-06:mutation",))
    collector.evidence_root=tmp_path
    report=await QualityVerifier(collector.contract,collector).verify(subject.snapshot)
    row=next(r for r in report["requirements"] if r["id"]=="TST-06")
    assert row["status"]=="PASS",row
    # R can correctly reject the deliberately weakened source, but that is
    # not a runtime mutation kill when native X and observations stay green.
    source_only=json.loads(json.dumps(result))
    source_only["mutated_results"]=json.loads(json.dumps(source_only["original_results"]))
    for rid,item in source_only["mutated_results"].items():
        item["status"]="FAIL"
        for p in item["proofs"]:p["snapshot_hash"]=source_only["mutation_snapshot_hash"]
    collector.records["authorization_mutation"]=source_only
    false_claim=await QualityVerifier(collector.contract,collector).verify(subject.snapshot)
    assert next(r for r in false_claim["requirements"] if r["id"]=="TST-06")["status"]=="FAIL"
