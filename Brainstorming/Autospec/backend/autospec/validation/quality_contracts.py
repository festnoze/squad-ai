"""Independent quality evidence admission, never execution of product scripts.

Native suites/builds run in the coordinator-owned isolated runner. This module
checks their attested observations and exact proof files, including denominators
and the six source-defined E2E scenarios. Missing records stay NOT_VERIFIED.
"""
from __future__ import annotations

import hashlib
import json
import re
import asyncio
import inspect
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import uuid4

from .support_adapter import AdapterUnavailable, Proof

QUALITY_IDS = tuple(f"TST-{i:02d}" for i in range(1, 7))
E2E_IDS = tuple(f"E2E-{i:02d}" for i in range(1, 7))


@dataclass(frozen=True)
class NativeSuiteSpec:
    name: str
    root: str
    ecosystem: str
    source_inventory: tuple[str, ...]
    domains: tuple[str, ...]
    test_args: tuple[str, ...] = ()
    coverage_source: str = "."


@dataclass(frozen=True)
class AuthorizationMutationSpec:
    """One reviewed exact replacement, applied only in a filtered owned copy."""
    path: str
    original_sha256: str
    before: str
    after: str


def native_quality_plan_hash(suites, mapping_path, mutation=None):
    """Canonical digest reviewed independently, with the mapping's exact bytes."""
    return hashlib.sha256(json.dumps({"suites":[asdict(s) for s in suites],
        "mapping_sha256":hashlib.sha256(Path(mapping_path).read_bytes()).hexdigest(),
        "mutation":asdict(mutation) if mutation else None},sort_keys=True).encode()).hexdigest()


def write_quality_review_package(contract, *, product_root, destination, snapshot_hash,
                                 suites, requirements_mapping, mutation=None,
                                 nominal_security_db_mocks=None):
    """Prepare a local review package, never approve it or call an LLM.

    ``requirements_mapping`` is RID -> [{suite,test,assertion}]. Assertions and
    fixture/mock declarations must be independently inspected before sealing
    a Proof R; merely writing this candidate package confers no authority.
    """
    root,destination=Path(product_root).resolve(),Path(destination).resolve()
    if destination.is_relative_to(root):raise ValueError("review package must be outside product root")
    destination.mkdir(parents=True,exist_ok=True)
    ids={r.id for r in contract.requirements}
    if not set(requirements_mapping)<=ids:raise ValueError("unknown requirement in test mapping")
    names={s.name for s in suites}
    for rows in requirements_mapping.values():
        if not isinstance(rows,list) or not rows or any(not {"suite","test","assertion"}<=set(r)
                or r["suite"] not in names or not isinstance(r["test"],str) or not r["test"]
                or not isinstance(r["assertion"],str) or not r["assertion"] for r in rows):
            raise ValueError("explicit suite, collected test ID and inspected assertion required")
    mapping=destination/"reviewed-test-mapping.json"
    mapping.write_text(json.dumps({"snapshot_hash":snapshot_hash,"contract_hash":contract.contract_hash,
        "nominal_security_db_mocks":nominal_security_db_mocks,"requirements":requirements_mapping},
        ensure_ascii=False,sort_keys=True,indent=2),encoding="utf-8")
    inventory={}
    for suite in suites:
        source_root=(root/suite.root).resolve()
        if not source_root.is_relative_to(root):raise ValueError("suite root escaped product")
        inventory[suite.name]={path:hashlib.sha256(NativeQualityCollector._source(source_root,path).read_bytes()).hexdigest()
                              for path in suite.source_inventory}
    digest=native_quality_plan_hash(suites,mapping,mutation)
    checks=["QUALITY:plan:"+digest,"TST-01:native_review","TST-02:mapping","TST-03:inventory"]
    if mutation:checks.append("TST-06:mutation")
    plan=destination/"quality-review-package.json"
    plan.write_text(json.dumps({"version":1,"status":"AWAITING_INDEPENDENT_REVIEW","snapshot_hash":snapshot_hash,
        "contract_hash":contract.contract_hash,"brief_hash":contract.brief_hash,"reference_hash":contract.reference_hash,
        "suites":[asdict(s) for s in suites],"source_inventory":inventory,"mapping_path":str(mapping),
        "mapping_sha256":hashlib.sha256(mapping.read_bytes()).hexdigest(),"mutation":asdict(mutation) if mutation else None,
        "plan_hash":digest,"required_review_checks":checks,
        "requirements":[{"id":r.id,"expected":r.expected,"gate":r.gate} for r in contract.requirements],
        "instructions":["Inspect assertions and fixtures, not only test names.",
            "Review omitted business files, critical skips/xfail and service/DB mocks.",
            "Review the exact authorization mutation anchor and isolated copy runtime.",
            "Only an independently installed intact R proof can approve this candidate."]},
        ensure_ascii=False,sort_keys=True,indent=2),encoding="utf-8")
    return {"plan_path":str(plan),"mapping_path":str(mapping),"plan_hash":digest,"required_review_checks":checks}


class NativeQualityCollector:
    """Execute native suites and independent browser/mutation probes.

    ``validator`` is the coordinator's IsolatedValidator: no product command
    runs on the host. ``browser_factory()`` returns a fresh BrowserVerifier.
    ``sqlite_probe(adapter, snapshot, contract)`` must actually export a real
    temporary DB, observe distinct transaction connections/restart and cleanup.
    ``mutation_probe(root, snapshot, contract)`` runs SEC09/10/FUN06 on an owned
    isolated runtime and returns requirement rows with exact X proofs. It owns
    and closes its runtime. Missing capabilities are recorded NOT_VERIFIED.

    A sealed independent R proof reviews this exact plan/mapping/mutation;
    product-generated booleans are never used as the review authority.
    """
    def __init__(self, contract, adapter, validator, *, product_root, evidence_root,
                 suites: tuple[NativeSuiteSpec, ...], mapping_path, review: Proof,
                 browser_factory=None, sqlite_probe=None, mutation=None,
                 mutation_probe=None, copy_product=None):
        self.contract,self.adapter,self.validator=contract,adapter,validator
        self.product_root=Path(product_root).resolve()
        self.evidence_root=Path(evidence_root).resolve()
        if self.evidence_root.is_relative_to(self.product_root):
            raise ValueError("quality evidence must be outside producer writable root")
        self.suites,self.mapping_path,self.review=suites,Path(mapping_path).resolve(),review
        if self.mapping_path.is_relative_to(self.product_root):
            raise ValueError("independent test mapping must be outside product root")
        self.browser_factory,self.sqlite_probe=browser_factory,sqlite_probe
        self.mutation,self.mutation_probe,self.copy_product=mutation,mutation_probe,copy_product
        self.records,self.errors,self.extra_proofs={}, {}, {}

    @property
    def plan_hash(self):
        return native_quality_plan_hash(self.suites,self.mapping_path,self.mutation)

    async def _identity(self,snapshot):
        if await self.adapter.snapshot_hash()!=snapshot or await self.adapter.contract_hash()!=self.contract.contract_hash:
            raise ValueError("quality collection oracle/snapshot changed")
        if hasattr(self,"_pinned_plan") and self.plan_hash!=self._pinned_plan:
            raise ValueError("independent quality plan/mapping changed")

    async def collect(self,snapshot_hash):
        await self._identity(snapshot_hash)
        self.snapshot=snapshot_hash
        self._pinned_plan=self.plan_hash
        if (not self.review.passed or self.review.type!="R" or not self.review.intact(
                snapshot_hash=snapshot_hash,contract_hash=self.contract.contract_hash) or
                "QUALITY:plan:"+self.plan_hash not in self.review.checks):
            raise AdapterUnavailable("exact native plan/mapping/mutation independent review missing")
        mapping=json.loads(self.mapping_path.read_text(encoding="utf-8"))
        if (mapping.get("snapshot_hash"),mapping.get("contract_hash"))!=(snapshot_hash,self.contract.contract_hash):
            raise AdapterUnavailable("native assertion mapping belongs to another snapshot")
        self.evidence_root.mkdir(parents=True,exist_ok=True)
        suites,coverage,outcomes=[],{},{}
        for spec in self.suites:
            try:
                root=(self.product_root/spec.root).resolve()
                if not root.is_relative_to(self.product_root) or root.is_symlink() or spec.ecosystem not in {"python","node"}:
                    raise ValueError("invalid reviewed suite root/ecosystem")
                inventory={path:hashlib.sha256(self._source(root,path).read_bytes()).hexdigest() for path in spec.source_inventory}
                report=self.evidence_root/(spec.name+"-"+uuid4().hex+"-suite.json")
                cov=self.evidence_root/(spec.name+"-"+uuid4().hex+"-coverage.json")
                result=await asyncio.to_thread(self.validator.run_suite,root,spec.ecosystem,"test",report,
                    test_args=spec.test_args,coveragepath=cov if spec.name in {"backend","frontend"} else None,coverage_source=spec.coverage_source)
                await self._identity(snapshot_hash)
                if inventory!={path:hashlib.sha256(self._source(root,path).read_bytes()).hexdigest() for path in inventory}:
                    raise ValueError("native test run changed original source")
                evidence=result.evidence; counts=evidence.counts
                critical={r["test"] for rows in mapping["requirements"].values() for r in rows if r["suite"]==spec.name}
                outcomes[spec.name]=evidence.outcomes
                row=dict(name=spec.name,return_code=evidence.exit_code,collected=evidence.collected,
                    passed=counts["passed"],failed=counts["failed"]+counts["error"]+counts["xpassed"],
                    skipped=counts["skipped"],xfail=counts["xfailed"],
                    critical_skipped=sum(evidence.outcomes.get(t)=="skipped" for t in critical),
                    critical_xfail=sum(evidence.outcomes.get(t) in {"xfailed","xpassed"} for t in critical),
                    nominal_security_db_mocks=mapping["nominal_security_db_mocks"],assertions_reviewed=True,
                    report_valid=evidence.report_valid,collection_errors=list(evidence.collection_errors),
                    raw_report=self._artifact(report),source_files=inventory,source_fingerprint=result.source_fingerprint,
                    image_id=result.image,environment_fingerprint=result.fingerprint)
                suites.append(row)
                log=self.evidence_root/(spec.name+"-"+uuid4().hex+"-output.txt")
                log.write_text(result.output,encoding="utf-8");row["output"]=self._artifact(log)
                if spec.name in {"backend","frontend"}:
                    coverage[spec.name]=self._coverage(spec,result.coverage,self._artifact(cov))
            except Exception as exc:
                self.errors.setdefault("native_suites",[]).append(spec.name+":"+type(exc).__name__)
                self.errors.setdefault("coverage",[]).append(spec.name+":"+type(exc).__name__)
        self.records["native_suites"]=suites
        self.records["coverage"]=coverage
        self.records["requirement_test_mapping"]={rid:[dict(row,executed=outcomes.get(row["suite"],{}).get(row["test"])=="passed",
            assertion_reviewed=True) for row in rows] for rid,rows in mapping["requirements"].items()}
        for name,callback in [("real_sqlite_test_environment",self.sqlite_probe)]:
            if callback is None:self.errors[name]=["trusted isolated runtime probe absent"]
            else:
                try:self.records[name]=await callback(self.adapter,snapshot_hash,self.contract.contract_hash)
                except Exception as exc:self.errors[name]=[type(exc).__name__]
        if self.browser_factory is None:self.errors["browser_e2e"]=["reviewed browser bindings/runtime absent"]
        else:
            try:
                runs=[]
                for mode in ["alone","together"]:
                    groups=[[sid] for sid in E2E_IDS] if mode=="alone" else [list(E2E_IDS)]
                    for group in groups:
                        verifier=self.browser_factory()
                        if inspect.isawaitable(verifier):verifier=await verifier
                        report=await verifier.verify_e2e(snapshot_hash,mode=mode,scenario_ids=group)
                        if (report["snapshot_hash"],report["contract_hash"])!=(snapshot_hash,self.contract.contract_hash):
                            raise ValueError("E2E report identity mismatch")
                        runs.extend(report["scenarios"])
                        self.extra_proofs.setdefault("TST-05",[]).extend(Proof(**p) for r in report["scenarios"] for p in r["proofs"])
                self.records["browser_e2e"]=runs
            except Exception as exc:self.errors["browser_e2e"]=[type(exc).__name__]
        try:self.records["authorization_mutation"]=await self._mutation(snapshot_hash)
        except Exception as exc:self.errors["authorization_mutation"]=[type(exc).__name__]
        await self._identity(snapshot_hash)
        return self

    @staticmethod
    def _source(root,path):
        candidate=root/path
        source=candidate.resolve()
        if (not source.is_relative_to(root) or candidate.is_symlink() or not source.is_file()
                or source.stat().st_nlink!=1 or any(p.is_symlink() for p in candidate.parents if p!=root and p.is_relative_to(root))):
            raise ValueError("source inventory must contain confined regular files")
        return source

    @staticmethod
    def _artifact(path):
        path=Path(path)
        return {"path":str(path),"sha256":hashlib.sha256(path.read_bytes()).hexdigest()}

    def _coverage(self,spec,raw,artifact):
        if not isinstance(raw,dict) or not raw.get("files"):
            raise AdapterUnavailable("fresh isolated raw coverage report absent")
        files={}
        for name,item in raw["files"].items():
            matches=[p for p in spec.source_inventory if name.replace("\\","/")==p or name.replace("\\","/").endswith("/"+p)]
            if len(matches)!=1:continue  # exclusions remain visible in raw report; inventory review decides scope
            summary=item.get("summary",item)
            if "num_statements" in summary:
                files[matches[0]]={"lines":{"total":summary["num_statements"],"covered":summary["covered_lines"]},
                    "branches":{"total":summary.get("num_branches",0),"covered":summary.get("covered_branches",0)}}
            elif "lines" in summary:files[matches[0]]=summary
            else:raise AdapterUnavailable("unsupported fresh coverage format")
        # Never manufacture zeros for omitted never-executed files. A missing
        # file is retained in source_inventory and fails the complete-inventory check.
        return dict(source_inventory=list(spec.source_inventory),files=files,business_excluded=[],domains=list(spec.domains),
            lines={k:sum(row["lines"][k] for row in files.values()) for k in ["total","covered"]},
            branches={k:sum(row.get("branches",{}).get(k,0) for row in files.values()) for k in ["total","covered"]},
            raw_report=artifact)

    async def _mutation(self,snapshot):
        if not self.mutation or not self.mutation_probe:
            raise AdapterUnavailable("reviewed mutation/runtime probe absent")
        spec=self.mutation;source=self._source(self.product_root,spec.path)
        original=source.read_bytes();before=hashlib.sha256(original).hexdigest()
        if before!=spec.original_sha256 or original.decode("utf-8").count(spec.before)!=1 or spec.before==spec.after:
            raise ValueError("mutation exact original/hash/anchor mismatch")
        self.evidence_root.mkdir(parents=True,exist_ok=True)
        copier=self.copy_product
        if copier is None:
            from ..orchestrator.validation_environment import snapshot_product
            copier=snapshot_product
        nominal=await self.mutation_probe(self.product_root,snapshot,self.contract.contract_hash)
        with tempfile.TemporaryDirectory(prefix="autospec-owned-auth-mutation-") as temporary:
            root=copier(self.product_root,Path(temporary)/"product")
            target=self._source(Path(root).resolve(),spec.path)
            target.write_text(original.decode("utf-8").replace(spec.before,spec.after,1),encoding="utf-8")
            mutated_file=self._artifact(target)
            mutation_hash=hashlib.sha256((snapshot+mutated_file["sha256"]+self.plan_hash).encode()).hexdigest()
            mutated=await self.mutation_probe(root,mutation_hash,self.contract.contract_hash)
            # Persist only the reviewed changed source file, never a DB/cookie.
            retained=self.evidence_root/("mutation-"+uuid4().hex+".txt")
            retained.write_bytes(target.read_bytes());mutated_file=self._artifact(retained)
        await self._identity(snapshot)
        ids={"SEC-09","SEC-10","FUN-06"}
        if set(nominal)!=ids or set(mutated)!=ids:raise AdapterUnavailable("three independent authorization/concurrency probes missing")
        for rows,identity in [(nominal,snapshot),(mutated,mutation_hash)]:
            for rid,row in rows.items():
                if not row.get("observed") or not any(Proof(**p).type=="X" and Proof(**p).intact(
                        snapshot_hash=identity,contract_hash=self.contract.contract_hash) for p in row.get("proofs",[])):
                    raise AdapterUnavailable("mutation outcome without intact executed X proof: "+rid)
        after=hashlib.sha256(source.read_bytes()).hexdigest()
        nominal_status="FAIL" if any(r["status"]=="FAIL" for r in nominal.values()) else "PASS" if all(r["status"]=="PASS" for r in nominal.values()) else "NOT_VERIFIED"
        mutated_status="FAIL" if any(r["status"]=="FAIL" for r in mutated.values()) else "PASS" if all(r["status"]=="PASS" for r in mutated.values()) else "NOT_VERIFIED"
        if "NOT_VERIFIED" in {nominal_status,mutated_status}:raise AdapterUnavailable("mutation experiment lacks an executed original/copy verdict")
        return dict(temporary_copy=True,original_before_sha256=before,original_after_sha256=after,
            original_file=self._artifact(source),mutated_file=mutated_file,mutated_sha256=mutated_file["sha256"],
            mutation_snapshot_hash=mutation_hash,original_status=nominal_status,mutated_status=mutated_status,
            independent_probes=sorted(ids),original_results=nominal,mutated_results=mutated)

    async def observe(self,name):
        if name in self.errors:raise AdapterUnavailable(";".join(self.errors[name]))
        if name not in self.records:raise AdapterUnavailable("native quality record absent: "+name)
        return self.records[name]

    async def proofs(self,rid):
        proofs=list(await self.adapter.proofs(rid))+self.extra_proofs.get(rid,[])
        if rid in self.review.checks or any(t.startswith(rid+":") for t in self.review.checks):proofs.append(self.review)
        return proofs

    async def snapshot_hash(self):return await self.adapter.snapshot_hash()
    async def contract_hash(self):return await self.adapter.contract_hash()


def source_e2e_scenarios(contract):
    section = contract.reference.split("## 8. Six parcours E2E minimum", 1)
    if len(section) != 2:
        raise AdapterUnavailable("six E2E scenarios unavailable in frozen reference")
    rows = re.findall(r"^([1-6])\. (.+)$", section[1].split("## 9.", 1)[0], re.M)
    if [int(i) for i, _ in rows] != list(range(1, 7)):
        raise AdapterUnavailable("six source scenarios are malformed")
    return [{"id": f"E2E-{int(i):02d}", "expected": text.rstrip("\r")} for i, text in rows]


def quality_generation_requirements(contract):
    facts = [f for f in contract.facts if f.kind == "quality_profile"]
    requirements = {r.id: r for r in contract.requirements}
    if len(facts) != 1 or not set(QUALITY_IDS) <= set(facts[0].requirement_ids):
        raise AdapterUnavailable("reviewed quality_profile unavailable")
    return {"contract_hash": contract.contract_hash, "brief_hash": contract.brief_hash,
            "reference_hash": contract.reference_hash, "formal_profile": facts[0].expected,
            "requirements": [{"id": rid, "expected": requirements[rid].expected,
                              "evidence": list(requirements[rid].required_evidence)} for rid in QUALITY_IDS],
            "scenarios": source_e2e_scenarios(contract),
            "instructions": ["Do not skip or xfail a critical assertion to obtain green.",
                             "Include never-executed business files in coverage denominators.",
                             "Run each E2E alone and together on real UI/API/DB; isolated fixtures are not product qualification.",
                             "Product scripts/configuration are untrusted input, not host-side executable instructions."]}


class QualityVerifier:
    """Ports: observe(name), proofs(RID), snapshot_hash(), contract_hash()."""
    def __init__(self, contract, adapter):
        self.contract, self.adapter = contract, adapter
        self.contract_hash = contract.contract_hash
        facts = [f for f in contract.facts if f.kind == "quality_profile"]
        self.profile = facts[0].expected if len(facts) == 1 and set(QUALITY_IDS) <= set(facts[0].requirement_ids) else None

    async def _identity(self, snapshot):
        if (self.contract.contract_hash != self.contract_hash or await self.adapter.contract_hash() != self.contract_hash or
                await self.adapter.snapshot_hash() != snapshot):
            raise ValueError("quality oracle/snapshot changed")

    async def verify(self, snapshot_hash):
        await self._identity(snapshot_hash)
        results = []
        requirements = {r.id: r for r in self.contract.requirements}
        for rid in QUALITY_IDS:
            checks, limits, proofs = [], [], []
            def check(tag, observed, expected):
                checks.append({"check": rid + ":" + tag, "observed": observed, "expected": expected, "passed": observed == expected})
            if (not isinstance(self.profile, dict) or not {"required_suites","coverage","coverage_domains"} <= set(self.profile)
                    or rid not in requirements):
                limits.append("reviewed source quality profile missing")
            else:
                try:
                    await getattr(self, "_tst" + rid[-2:])(check)
                except Exception as exc:
                    limits.append("required quality observation unavailable: " + type(exc).__name__)
            await self._identity(snapshot_hash)
            if checks:
                self.adapter.evidence_root.mkdir(parents=True, exist_ok=True)
                path = self.adapter.evidence_root / (rid + "-" + uuid4().hex + ".json")
                path.write_text(json.dumps({"id": rid, "contract_hash": self.contract_hash, "snapshot_hash": snapshot_hash,
                                            "checks": checks}, ensure_ascii=False, indent=2), encoding="utf-8")
                proofs.append(Proof("X", str(path), hashlib.sha256(path.read_bytes()).hexdigest(), snapshot_hash,
                                    self.contract_hash, tuple(x["check"] for x in checks), all(x["passed"] for x in checks)))
            try:
                for proof in await self.adapter.proofs(rid):
                    if proof.intact(snapshot_hash=snapshot_hash, contract_hash=self.contract_hash) and any(
                            tag == rid or tag.startswith(rid + ":") for tag in proof.checks):
                        proofs.append(proof)
                    else:
                        limits.append("stale/unmapped quality proof rejected")
            except Exception as exc:
                limits.append("quality proof unavailable: " + type(exc).__name__)
            required = set(requirements[rid].required_evidence) if rid in requirements else {"X", "R"}
            missing = required - {p.type for p in proofs}
            if missing: limits.append("missing proof types: " + ",".join(sorted(missing)))
            failed = any(not c["passed"] for c in checks) or any(not p.passed for p in proofs)
            results.append({"id": rid, "gate": requirements[rid].gate if rid in requirements else "B",
                            "status": "FAIL" if failed else "NOT_VERIFIED" if limits or not checks else "PASS",
                            "expected": requirements[rid].expected if rid in requirements else "source missing",
                            "observed": checks, "proofs": [p.__dict__ for p in proofs], "limits": limits,
                            "reproduction": [{"probe":c["check"],"observed":c["observed"]} for c in checks],
                            "impact": "quality invariant violated" if failed else "",
                            "contract_hash": self.contract_hash, "snapshot_hash": snapshot_hash})
        await self._identity(snapshot_hash)
        return {"pack": "quality", "status": "FAIL" if any(r["status"] == "FAIL" for r in results) else
                "PASS" if all(r["status"] == "PASS" for r in results) else "NOT_VERIFIED",
                "contract_hash": self.contract_hash, "snapshot_hash": snapshot_hash, "requirements": results}

    async def _suites(self):
        suites = await self.adapter.observe("native_suites")
        if not isinstance(suites, list) or not suites:
            raise AdapterUnavailable("native suite records absent")
        return suites

    async def _tst01(self, check):
        suites = await self._suites()
        for suite in suites:
            name = suite["name"]
            check(name + "_exit", suite["return_code"], 0)
            check(name + "_collected", type(suite["collected"]) is int and suite["collected"] > 0, True)
            check(name + "_accounted", suite["passed"] + suite["failed"] + suite["skipped"] + suite["xfail"], suite["collected"])
            check(name + "_critical_skip", suite["critical_skipped"] + suite["critical_xfail"], 0)
            check(name + "_nominal_mocks", suite["nominal_security_db_mocks"], False)
            check(name + "_assertions_reviewed", suite["assertions_reviewed"], True)
            self._artifact_intact(suite["raw_report"])
            check(name+"_report_valid",suite.get("report_valid"),True)
            check(name+"_collection_errors",suite.get("collection_errors"),[])
        check("required_suites", set(self.profile["required_suites"]) <= {s["name"] for s in suites}, True)

    async def _tst02(self, check):
        mapping = await self.adapter.observe("requirement_test_mapping")
        expected = {r.id for r in self.contract.requirements if r.gate != "D"}
        check("all_mandatory_ids_mapped", expected <= set(mapping), True)
        for rid in sorted(expected):
            rows = mapping.get(rid, [])
            check(rid + "_assertions", bool(rows) and all(row.get("executed") is True and row.get("assertion_reviewed") is True
                   and bool(row.get("test")) and bool(row.get("assertion")) for row in rows), True)

    async def _tst03(self, check):
        reports = await self.adapter.observe("coverage")
        for suite, metrics in self.profile["coverage"].items():
            report = reports[suite]
            self._artifact_intact(report["raw_report"])
            inventory = report["source_inventory"]
            files = report["files"]
            check(suite + "_complete_inventory", bool(inventory) and set(inventory) == set(files), True)
            check(suite + "_business_exclusions", report["business_excluded"], [])
            for metric, threshold in metrics.items():
                included = sum(row[metric]["total"] for row in files.values())
                covered = sum(row[metric]["covered"] for row in files.values())
                check(suite + metric + "_denominator", report[metric]["total"], included)
                check(suite + metric + "_numerator", report[metric]["covered"], covered)
                check(suite + metric + "_nonzero", included > 0 and 0 <= covered <= included, True)
                check(suite + metric + "_threshold", included > 0 and covered * 100 >= threshold * included, True)
            check(suite + "_auth_services_http_present", set(self.profile["coverage_domains"][suite]) <= set(report["domains"]), True)

    async def _tst04(self, check):
        evidence = await self.adapter.observe("real_sqlite_test_environment")
        path, root = Path(evidence["database_path"]).resolve(), Path(evidence["isolated_root"]).resolve()
        check("temporary_owned_database", root in path.parents and evidence["isolated"] is True, True)
        check("real_sqlite_header", path.read_bytes()[:16].hex(), b"SQLite format 3\x00".hex())
        check("distinct_connections", len(set(evidence["connection_ids"])) >= 2, True)
        check("restart_exercised", evidence["restart_verified"], True)
        check("cleanup_owned_only", evidence["cleanup_owned_only"], True)

    async def _tst05(self, check):
        runs = await self.adapter.observe("browser_e2e")
        expected = {s["id"] for s in source_e2e_scenarios(self.contract)}
        for mode in ["alone", "together"]:
            rows = [r for r in runs if r["mode"] == mode]
            check(mode + "_exact_six", len(rows) == 6 and {r["id"] for r in rows} == expected, True)
            for row in rows:
                if row["status"] not in {"PASS","FAIL"}:
                    raise AdapterUnavailable("E2E scenario was not verified: " + row["id"])
                check(mode + row["id"] + "_executed", row["status"], "PASS")
                check(mode + row["id"] + "_nominal", row["real_ui_api_db"] is True and row["nominal_mocks"] is False, True)
                check(mode + row["id"] + "_console", row["unhandled_console_errors"], [])
                check(mode + row["id"] + "_not_blank", row["nonblank"], True)
                check(mode + row["id"] + "_isolated_fixture", row["fixture_reset_before"], True)

    async def _tst06(self, check):
        mutation = await self.adapter.observe("authorization_mutation")
        self._artifact_intact(mutation["mutated_file"])
        original=mutation["original_file"]
        if hashlib.sha256(Path(original["path"]).read_bytes()).hexdigest()!=original["sha256"]:
            raise AdapterUnavailable("original mutation source bytes no longer intact")
        check("actual_original_sha256",original["sha256"],mutation["original_before_sha256"])
        check("actual_mutation_sha256",mutation["mutated_file"]["sha256"],mutation["mutated_sha256"])
        check("isolated_mutation", mutation["temporary_copy"] is True, True)
        check("original_unchanged", mutation["original_before_sha256"], mutation["original_after_sha256"])
        check("mutation_distinct", mutation["mutated_sha256"] != mutation["original_before_sha256"], True)
        check("original_pass", mutation["original_status"], "PASS")
        check("mutation_detected", mutation["mutated_status"], "FAIL")
        check("independent_probes", {"SEC-09", "SEC-10", "FUN-06"} <= set(mutation["independent_probes"]), True)

    def _artifact_intact(self,ref):
        path=Path(ref["path"]).resolve()
        if (not path.is_relative_to(Path(self.adapter.evidence_root).resolve()) or not path.is_file()
                or hashlib.sha256(path.read_bytes()).hexdigest()!=ref["sha256"]):
            raise AdapterUnavailable("fresh supervisor-owned raw report/source artefact missing or stale")
