import copy
import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from autospec.validation.quality_contracts import QualityVerifier, quality_generation_requirements, source_e2e_scenarios
from autospec.validation.support_adapter import AdapterUnavailable, Proof
from tests.fixtures.browser.app import browser_contract
from tests.fixtures.browser.app import BrowserSubject,retain_browser_fixture_report
from autospec.validation.browser_contracts import BrowserVerifier


class QualityFixture:
    """Synthetic admission records, not native-product execution evidence."""
    def __init__(self, root, contract, bug=""):
        self.root = root; root.mkdir(parents=True)
        self.evidence_root = root / "proofs"
        self.evidence_root.mkdir()
        self.contract, self.bug = contract, bug
        self.snapshot = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        self.database = root / "temporary.sqlite"
        one = sqlite3.connect(self.database); two = sqlite3.connect(self.database)
        self.connection_ids = [id(one),id(two)]
        one.execute("CREATE TABLE sentinels(id INTEGER PRIMARY KEY)"); one.commit(); one.close(); two.close()
        self.observations = {
            "native_suites": [{"name": name,"return_code":0,"collected":10,"passed":10,"failed":0,"skipped":0,"xfail":0,
                               "critical_skipped":0,"critical_xfail":0,"nominal_security_db_mocks":False,"assertions_reviewed":True}
                              for name in ["backend","frontend","e2e"]],
            "requirement_test_mapping": {r.id:[{"test":"fixture::"+r.id,"assertion":"fixture admission constraint", "executed":True,"assertion_reviewed":True}]
                                         for r in contract.requirements if r.gate!="D"},
            "coverage":{},
            "real_sqlite_test_environment":{"database_path":str(self.database),"isolated_root":str(root),"isolated":True,
                 "connection_ids":self.connection_ids,"restart_verified":True,"cleanup_owned_only":True},
            "browser_e2e":[{"id":s["id"],"mode":mode,"status":"PASS","real_ui_api_db":True,"nominal_mocks":False,
                 "unhandled_console_errors":[],"nonblank":True,"fixture_reset_before":True}
                 for mode in ["alone","together"] for s in source_e2e_scenarios(contract)],
            "authorization_mutation":{"temporary_copy":True,"original_before_sha256":"a"*64,"original_after_sha256":"a"*64,
                 "mutated_sha256":"b"*64,"original_status":"PASS","mutated_status":"FAIL","independent_probes":["SEC-09","SEC-10","FUN-06"]}
        }
        for suite in self.observations["native_suites"]:
            raw=self.evidence_root/(suite["name"]+"-raw-meta-report.json")
            raw.write_text(json.dumps({"scope":"synthetic admission meta-test, not actual native-product suite","counts":suite}),encoding="utf-8")
            suite.update(raw_report={"path":str(raw),"sha256":hashlib.sha256(raw.read_bytes()).hexdigest()},report_valid=True,collection_errors=[])
        original=self.root/"owned-original.txt";mutant=self.evidence_root/"owned-mutant.txt"
        original.write_text("allow(actor,owner) = actor == owner",encoding="utf-8")
        mutant.write_text("allow(actor,owner) = true",encoding="utf-8")
        original_hash=hashlib.sha256(original.read_bytes()).hexdigest();mutant_hash=hashlib.sha256(mutant.read_bytes()).hexdigest()
        self.observations["authorization_mutation"].update(original_file={"path":str(original),"sha256":original_hash},
             mutated_file={"path":str(mutant),"sha256":mutant_hash},original_before_sha256=original_hash,original_after_sha256=original_hash,mutated_sha256=mutant_hash)
        for suite,domains in [("backend",["auth","services","permissions"]),("frontend",["auth","tickets","users","http"])]:
            files={domain+".py":{"lines":{"total":100,"covered":80},"branches":{"total":100,"covered":70}} for domain in domains}
            self.observations["coverage"][suite]={"source_inventory":list(files),"files":files,"business_excluded":[],"domains":domains,
                "lines":{"total":len(files)*100,"covered":len(files)*80},"branches":{"total":len(files)*100,"covered":len(files)*70}}
            raw=self.evidence_root/(suite+"-raw-meta-coverage.json")
            raw.write_text(json.dumps(self.observations["coverage"][suite]),encoding="utf-8")
            self.observations["coverage"][suite]["raw_report"]={"path":str(raw),"sha256":hashlib.sha256(raw.read_bytes()).hexdigest()}
        if bug=="zero_collect":
            row=self.observations["native_suites"][0]; row.update(collected=0,passed=0)
        elif bug=="critical_skip":
            row=self.observations["native_suites"][0]; row.update(passed=9,skipped=1,critical_skipped=1)
        elif bug=="auth_mock": self.observations["native_suites"][0]["nominal_security_db_mocks"]=True
        elif bug=="missing_mapping": self.observations["requirement_test_mapping"].pop("SEC-09")
        elif bug=="coverage_omission": self.observations["coverage"]["backend"]["files"].pop("auth.py")
        elif bug=="coverage_low":
            report=self.observations["coverage"]["backend"];report["lines"]["covered"]=237
            for row in report["files"].values():row["lines"]["covered"]=79
        elif bug=="single_connection": self.observations["real_sqlite_test_environment"]["connection_ids"]=[1,1]
        elif bug=="e2e_missing": self.observations["browser_e2e"].pop()
        elif bug=="mutation_undetected": self.observations["authorization_mutation"]["mutated_status"]="PASS"
        elif bug=="stale_report":self.observations["native_suites"][0]["raw_report"]["sha256"]="0"*64
        elif bug=="missing_coverage_report":self.observations["coverage"]["backend"].pop("raw_report")
        elif bug=="false_green_failure":self.observations["native_suites"][0].update(passed=9,failed=1,return_code=0)
        elif bug=="impossible_file_coverage":
            self.observations["coverage"]["backend"]["files"]["auth.py"]["lines"]["covered"]=160
            self.observations["coverage"]["backend"]["files"]["permissions.py"]["lines"]["covered"]=0

    async def contract_hash(self): return self.contract.contract_hash
    async def snapshot_hash(self): return self.snapshot
    async def observe(self,name):
        if name not in self.observations: raise AdapterUnavailable("record missing")
        return copy.deepcopy(self.observations[name])
    async def proofs(self,rid):
        path=self.root/(rid+"-fixture-review.json")
        path.write_text(json.dumps({"scope":"admission meta-test, not native product execution","requirement":rid}),encoding="utf-8")
        return [Proof("R",str(path),hashlib.sha256(path.read_bytes()).hexdigest(),self.snapshot,self.contract.contract_hash,(rid,))]


async def test_good_quality_admission_fixture_cannot_fabricate_browser_visual_evidence(tmp_path):
    contract=browser_contract(); fixture=QualityFixture(tmp_path/"fixture",contract)
    report=await QualityVerifier(contract,fixture).verify(fixture.snapshot)
    results={r["id"]:r for r in report["requirements"]}
    assert results["TST-05"]["status"]=="NOT_VERIFIED"
    assert results["TST-06"]["status"]=="NOT_VERIFIED"
    assert all(r["status"]=="PASS" for rid,r in results.items() if rid not in {"TST-05","TST-06"})


@pytest.mark.parametrize("bug,rid",[("zero_collect","TST-01"),("critical_skip","TST-01"),("auth_mock","TST-01"),
    ("missing_mapping","TST-02"),("coverage_omission","TST-03"),("coverage_low","TST-03"),
    ("single_connection","TST-04"),("e2e_missing","TST-05"),("mutation_undetected","TST-06"),
    ("false_green_failure","TST-01"),("impossible_file_coverage","TST-03")])
async def test_defective_quality_observation_is_rejected(tmp_path,bug,rid):
    contract=browser_contract(); fixture=QualityFixture(tmp_path/"fixture",contract,bug)
    report=await QualityVerifier(contract,fixture).verify(fixture.snapshot)
    result=next(r for r in report["requirements"] if r["id"]==rid)
    assert result["status"]=="FAIL",result


async def test_missing_native_evidence_is_not_verified(tmp_path):
    contract=browser_contract(); fixture=QualityFixture(tmp_path/"fixture",contract)
    fixture.observations.pop("native_suites")
    report=await QualityVerifier(contract,fixture).verify(fixture.snapshot)
    assert report["requirements"][0]["status"]=="NOT_VERIFIED"


def test_quality_generation_and_scenarios_preserve_frozen_source():
    contract=browser_contract(); fragment=quality_generation_requirements(contract)
    assert len(fragment["scenarios"])==6
    assert all(s["expected"] in contract.reference for s in fragment["scenarios"])
    assert all(r["expected"]==next(source.expected for source in contract.requirements if source.id==r["id"])
               for r in fragment["requirements"])


@pytest.mark.parametrize("bug,rid",[("stale_report","TST-01"),("missing_coverage_report","TST-03")])
async def test_unproven_or_stale_raw_quality_report_is_not_verified(tmp_path,bug,rid):
    contract=browser_contract();fixture=QualityFixture(tmp_path/"fixture",contract,bug)
    report=await QualityVerifier(contract,fixture).verify(fixture.snapshot)
    assert next(r for r in report["requirements"] if r["id"]==rid)["status"]=="NOT_VERIFIED"


async def test_TST_05_admits_twelve_actual_browser_runs_and_intact_visual_proofs(tmp_path):
    """Only TST05 is qualified here; other records remain admission meta-fixtures."""
    contract=browser_contract();subject=BrowserSubject(tmp_path/"product",contract)
    fixture=QualityFixture(tmp_path/"admission-records",contract)
    fixture.snapshot=subject.snapshot;fixture.evidence_root=tmp_path
    subject.start_http();runs=[];proofs=[]
    try:
        for mode in ["alone","together"]:
            groups=[[f"E2E-{i:02d}"] for i in range(1,7)] if mode=="alone" else [None]
            for ids in groups:
                report=await BrowserVerifier(contract,subject.harness()).verify_e2e(subject.snapshot,mode=mode,scenario_ids=ids)
                retain_browser_fixture_report(report,subject)
                assert report["status"]=="PASS",report
                runs.extend(report["scenarios"])
                proofs.extend(Proof(**p) for r in report["scenarios"] for p in r["proofs"])
        fixture.observations["browser_e2e"]=runs
        base=fixture.proofs
        async def reviewed(rid):return await base(rid)+(proofs if rid=="TST-05" else [])
        fixture.proofs=reviewed
        report=await QualityVerifier(contract,fixture).verify(subject.snapshot)
        result=next(r for r in report["requirements"] if r["id"]=="TST-05")
        assert result["status"]=="PASS",result
        assert {"X","V"}<={p["type"] for p in result["proofs"]}
        assert len(runs)==12 and all(r["nonblank"] and r["unhandled_console_errors"]==[] for r in runs)
        retain_browser_fixture_report(report,subject)
        first=next(r for r in runs if r["id"]=="E2E-01" and r["mode"]=="alone")
        other=next(r for r in runs if r["id"]=="E2E-01" and r["mode"]=="together")
        first["proofs"]=other["proofs"]
        swapped=await QualityVerifier(contract,fixture).verify(subject.snapshot)
        assert next(r for r in swapped["requirements"] if r["id"]=="TST-05")["status"]=="NOT_VERIFIED"
    finally:subject.stop_http()
