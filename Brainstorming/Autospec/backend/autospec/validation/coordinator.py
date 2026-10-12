"""Pipeline entry points: reviewed external facts -> isolated independent packs.

No producer scripts/imports on the host, no health-only milestone and no score
compensation. Every frozen requirement is returned exactly once. Missing ports,
review, browser, native coverage or final-image evidence remain NOT_VERIFIED.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from uuid import uuid4
from dataclasses import asdict

from .final_gate import source_snapshot
from .product_harness import OwnedProductHarnessSession,ReviewedProductBindings,ReviewedFixtureFactory
from .support_adapter import AdapterUnavailable,Proof


EXTERNAL_OBSERVATIONS={"native_suites","requirement_test_mapping","coverage","real_sqlite_test_environment",
    "browser_e2e","authorization_mutation","secret_scan","cookie_modes",
    "delivery_build","docs_audit","execution_timings"}


def binding_proposal_schema()->dict:
    """Structured-output shape for a trusted reviewer, not producer authority.

    Only observed operational bindings are proposed. Expected behavior is never
    an input to this schema; frozen contract/fixture expectations remain owned
    by the independent reviewer. IDs, hashes and proof receipts are attached
    by the supervisor, not supplied by the proposer.
    """
    identifier={"type":"string","pattern":"^[A-Za-z_][A-Za-z_0-9]*$"}
    mapping=lambda schema:{"type":"object","additionalProperties":schema}
    argv={"type":"array","minItems":1,"items":{"type":"string"}}
    table={"type":"object","additionalProperties":False,"required":["name","columns"],
           "properties":{"name":identifier,"columns":mapping(identifier)}}
    command={"type":"object","additionalProperties":False,"required":["argv","parameters","timeout"],
             "properties":{"argv":argv,"parameters":{"type":"array","items":identifier},"timeout":{"type":"number","exclusiveMinimum":0,"maximum":120}}}
    fields={"database_path":{"type":"string","const":"/var/lib/autospec-validation/support.sqlite"},
        "tables":mapping(table),"commands":mapping(command),"runtime_command":argv,
        "auth_path":{"type":"string"},"csrf_field":identifier,"ticket_path":{"type":"string"},
        "auth_required":{"type":"boolean"},"internal_port":{"type":"integer","minimum":1,"maximum":65535},
        "local_cookie_mode":{"type":"boolean"},"browser_bindings":mapping({"type":"string"}),
        "browser_routes":mapping({"type":"string"}),"query_plans":mapping({"type":"array","minItems":2,"maxItems":2}),
        "instrumentation":{"type":["object","null"]}}
    return {"type":"object","additionalProperties":False,"required":["source_files","bindings"],
        "properties":{"source_files":{"type":"array","minItems":1,"uniqueItems":True,"items":{"type":"string"}},
            "bindings":{"type":"object","additionalProperties":False,"required":list(fields),"properties":fields}}}


async def prepare_binding_proposal(candidate:dict,fixtures:dict,*,contract,snapshot_root,snapshot_hash)->dict:
    """No writes/execution: validate proposed facts and create review subjects.

    Root may obtain candidate via its tracked reviewer with cwd=None. This
    function cannot approve it. Review must inspect exact source bytes and the
    immutable contract, then issue two external R artifacts with the returned
    check tags. No hidden bootstrap/selector/clock/race discovery defaults.
    """
    source=Path(snapshot_root).resolve()
    if source_snapshot(source).digest!=snapshot_hash: raise AdapterUnavailable("proposal snapshot identity changed")
    required=set(binding_proposal_schema()["properties"]["bindings"]["required"])
    if set(candidate)!={"source_files","bindings"} or set(candidate["bindings"])!=required:
        raise AdapterUnavailable("candidate operational binding keys missing/unknown")
    if not isinstance(candidate["source_files"],list) or not candidate["source_files"] or len(set(candidate["source_files"]))!=len(candidate["source_files"]):
        raise AdapterUnavailable("candidate source references must be explicit and unique")
    from ..agents.file_broker import ExecutionContext,FileBroker
    broker=FileBroker(ExecutionContext("binding-review-proposal",source))
    files={}
    for relative in candidate["source_files"]:
        path=broker.path(relative)
        if not path.is_file(): raise AdapterUnavailable("binding source reference is not a file")
        files[relative]=hashlib.sha256(path.read_bytes()).hexdigest()
    if set(fixtures)!={"cases"} or not isinstance(fixtures["cases"],dict) or "VERTICAL" not in fixtures["cases"]:
        raise AdapterUnavailable("independent fixture proposal requires explicit VERTICAL case")
    fixture_payload=dict(snapshot_hash=snapshot_hash,contract_hash=contract.contract_hash,**fixtures)
    fixture_hash=hashlib.sha256(json.dumps(fixture_payload,sort_keys=True,ensure_ascii=True).encode()).hexdigest()
    # Placeholder only to parse structure; deliberately not a review receipt.
    placeholder=Proof("R","", "0"*64,snapshot_hash,contract.contract_hash,(),False,"unreviewed proposal")
    payload={**candidate["bindings"],"snapshot_hash":snapshot_hash,"contract_hash":contract.contract_hash,
        "source_files":files,"fixture_fingerprint":fixture_hash,"review":asdict(placeholder)}
    binding=ReviewedProductBindings.from_dict(payload); binding.validate_structure(source)
    if binding.auth_required!=_auth(contract): raise AdapterUnavailable("candidate auth differs from frozen contract")
    payload=asdict(binding);payload.pop("review")
    return dict(version=1,snapshot_hash=snapshot_hash,contract_hash=contract.contract_hash,bindings=payload,
        fixtures=fixture_payload,binding_checks=["PRODUCT:bindings","PRODUCT:bindings:"+binding.fingerprint()],
        fixture_checks=["PRODUCT:fixtures","PRODUCT:fixtures:"+fixture_hash],
        limits=["operational structure only; independent source and fixture review remains required"])


async def install_reviewed_configuration(proposal:dict,*,binding_review:Proof,fixture_review:Proof,
                                        supervisor_root,snapshot_root)->dict:
    """Publish only intact independently reviewed facts, usable by both gates.

    There is no API that manufactures a positive R from a candidate. The two
    atomic JSON writes are pair-bound by fixture_fingerprint: interrupted or
    mixed publication cannot run with the previous fixture definition.
    """
    root=Path(supervisor_root).resolve();source=Path(snapshot_root).resolve()
    if root.is_relative_to(source): raise AdapterUnavailable("reviewed configuration must be outside product")
    snapshot,oracle=proposal["snapshot_hash"],proposal["contract_hash"]
    if source_snapshot(source).digest!=snapshot: raise AdapterUnavailable("reviewed proposal snapshot drift")
    for review,checks in ((binding_review,proposal["binding_checks"]),(fixture_review,proposal["fixture_checks"])):
        if review.type!="R" or not review.passed or not set(checks)<=set(review.checks) or not Path(review.path).resolve().is_relative_to(root) or not review.intact(snapshot_hash=snapshot,contract_hash=oracle):
            raise AdapterUnavailable("independent reviewed proposal artifact absent/stale/unmapped")
    binding=ReviewedProductBindings.from_dict({**proposal["bindings"],"review":asdict(binding_review)})
    binding.validate(source)
    if (binding.snapshot_hash,binding.contract_hash)!=(snapshot,oracle): raise AdapterUnavailable("proposal identity mismatch")
    fixture_payload={**proposal["fixtures"],"review":asdict(fixture_review)}
    from ..orchestrator.dependencies import atomic_json
    staging=root/"configuration-staging"/uuid4().hex
    path=staging/"reviewed-fixtures.json";atomic_json(path,fixture_payload)
    factory=ReviewedFixtureFactory(path,snapshot_hash=snapshot,contract_hash=oracle,source_root=source)
    if factory.fingerprint!=binding.fixture_fingerprint: raise AdapterUnavailable("reviewed proposal pair fingerprint differs")
    # Validate each explicit variant without executing a product command.
    for case,definition in factory.cases.items():
        await factory(case)
        for variant in definition.get("variants",[]): await factory(case,**variant["options"])
    fixtures_path=root/"reviewed-fixtures.json";bindings_path=root/"product-bindings.json"
    atomic_json(fixtures_path,fixture_payload);atomic_json(bindings_path,asdict(binding))
    return dict(status="REVIEWED",snapshot_hash=snapshot,contract_hash=oracle,
        bindings_path=str(bindings_path),fixtures_path=str(fixtures_path),
        scope="independent operational bindings; no requirement PASS awarded")


class SupervisorEvidenceStore:
    """Read-only native/review receipts in a producer-inaccessible root.

    proofs.json maps RID -> serialized Proof objects. observations.json maps
    known names -> X Proof for a JSON payload {name,parameters,value, hashes}.
    The payload itself is hashed, never an unattested success boolean from a
    product command. The independent runner owns these files, not the product.
    """
    def __init__(self,root,snapshot,contract):
        self.root=Path(root).resolve(); self.snapshot=snapshot; self.contract=contract; self.contributions={}

    def _read(self,path):
        path=Path(path).resolve()
        if not path.is_relative_to(self.root) or not path.is_file() or path.is_symlink() or path.stat().st_size>16*1024*1024:
            raise AdapterUnavailable("bounded supervisor receipt unavailable")
        try: return json.loads(path.read_bytes())
        except (ValueError,OSError) as exc: raise AdapterUnavailable("supervisor receipt JSON invalid") from exc

    def _proof(self,value,tag):
        try: proof=Proof(**value)
        except (TypeError,ValueError) as exc: raise AdapterUnavailable("supervisor Proof malformed") from exc
        if not Path(proof.path).resolve().is_relative_to(self.root) or not proof.intact(snapshot_hash=self.snapshot,contract_hash=self.contract) or not any(c==tag or c.startswith(tag+":") for c in proof.checks):
            raise AdapterUnavailable("supervisor Proof stale, outside root, or unmapped")
        return proof

    async def proofs(self,rid):
        result=list(self.contributions.get(rid,[])); path=self.root/"proofs.json"
        if path.exists():
            value=self._read(path)
            if (value.get("snapshot_hash"),value.get("contract_hash"))!=(self.snapshot,self.contract):
                raise AdapterUnavailable("supervisor proof index identity changed")
            result.extend(self._proof(v,rid) for v in value.get("proofs",{}).get(rid,[]))
        return result

    async def observe(self,name,**params):
        if name not in EXTERNAL_OBSERVATIONS: raise AdapterUnavailable("external observation name not admitted")
        index=self._read(self.root/"observations.json")
        if (index.get("snapshot_hash"),index.get("contract_hash"))!=(self.snapshot,self.contract):
            raise AdapterUnavailable("native observation index identity changed")
        value=index.get("observations",{}).get(name)
        if value is None: raise AdapterUnavailable("native observation absent: "+name)
        proof=self._proof(value,"OBS:"+name)
        if proof.type!="X" or not proof.passed: raise AdapterUnavailable("native observation was not obtained")
        payload=self._read(proof.path)
        if payload.get("name")!=name or payload.get("parameters",{})!=params or (payload.get("snapshot_hash"),payload.get("contract_hash"))!=(self.snapshot,self.contract) or "value" not in payload:
            raise AdapterUnavailable("native payload observation/parameters identity mismatch")
        return payload["value"]


class EvidenceAdapter:
    def __init__(self,adapter,store): self.native=adapter;self.store=store
    def __getattr__(self,name): return getattr(self.native,name)
    async def proofs(self,rid): return await self.store.proofs(rid)
    async def observe(self,name,**params):
        return await self.store.observe(name,**params) if name in EXTERNAL_OBSERVATIONS else await self.native.observe(name,**params)


def _auth(contract):
    if any(f.kind=="security_profile" for f in contract.facts): return True
    profiles=[f.expected for f in contract.facts if f.kind=="vertical_profile"]
    if len(profiles)!=1 or not isinstance(profiles[0],dict) or type(profiles[0].get("auth")) is not bool:
        raise AdapterUnavailable("explicit frozen vertical auth fact absent")
    return profiles[0]["auth"]


def _context(contract,snapshot_root,snapshot_hash,evidence_root,*,instrumented=False,phase="reports",image_id=None):
    source=Path(snapshot_root).resolve(); control=Path(evidence_root).resolve()
    evidence=control/phase/snapshot_hash/("harness" if phase=="reports" else "evidence")
    if control.is_relative_to(source): raise AdapterUnavailable("supervisor evidence must be outside product snapshot")
    if source_snapshot(source).digest!=snapshot_hash: raise AdapterUnavailable("snapshot bytes do not match supplied identity")
    expected_contract=contract.contract_hash
    store=SupervisorEvidenceStore(control,snapshot_hash,expected_contract)
    async def snapshot(): return source_snapshot(source).digest
    async def oracle(): return contract.contract_hash
    context=OwnedProductHarnessSession.from_bindings(control/"product-bindings.json",source_root=source,
        stage_root=control/"runtime-stages"/uuid4().hex,evidence_root=evidence,cache_root=control/"linux-cache",
        fixtures_path=control/"reviewed-fixtures.json",snapshot_hash=snapshot,contract_hash=oracle,
        proof_provider=store.proofs,instrumented=instrumented,image_id=image_id)
    if context.bindings.auth_required!=_auth(contract) or context.bindings.snapshot_hash!=snapshot_hash or context.bindings.contract_hash!=expected_contract:
        raise AdapterUnavailable("reviewed bindings differ from frozen contract/snapshot/auth fact")
    return context,store


async def _browser_smoke(harness,snapshot,contract):
    from .browser_contracts import PlaywrightHarness,browser_smoke
    if not harness.bindings.auth_required:
        raise AdapterUnavailable("source-reviewed no-auth browser creation port is not implemented")
    binding=harness.bindings
    browser=PlaywrightHarness(harness.adapter,bindings=binding.browser_bindings,routes=binding.browser_routes)
    actor=harness.manifest.metadata.get("vertical_actor")
    if actor not in harness.manifest.accounts: raise AdapterUnavailable("explicit vertical fixture actor absent")
    return await browser_smoke(browser,snapshot,contract,harness.manifest.accounts[actor],
        title="Independent vertical "+uuid4().hex,description="Independent isolated browser/API/SQLite smoke")


async def verify_vertical(state,contract,snapshot_root,snapshot_hash,evidence_root)->dict:
    """Actual schema/bootstrap/Argon2/browser/API/DB milestone; bounded lifetime."""
    try:
        context,_=_context(contract,snapshot_root,snapshot_hash,evidence_root,phase="vertical")
        async with context as harness:
            await harness.adapter.prepare_case("VERTICAL")
            async def browser(adapter,snapshot,oracle): return await _browser_smoke(harness,snapshot,oracle)
            return await harness.verify_vertical(snapshot_hash,contract.contract_hash,browser_smoke=browser)
    except Exception as exc:
        # No product exception text/argv/stdin/logs: may contain credentials.
        return dict(status="NOT_VERIFIED",snapshot_hash=snapshot_hash,contract_hash=contract.contract_hash,
            stages=[],limits=["required isolated vertical observation unavailable: "+type(exc).__name__],
            scope="no health-only or inferred milestone success")


def _unverified(requirement,snapshot,contract,limit):
    return dict(id=requirement.id,gate=requirement.gate,status="NOT_VERIFIED",expected=requirement.expected,
        observed=[],reproduction=[],proofs=[],impact="acceptance evidence unavailable",limits=[limit],
        snapshot_hash=snapshot,contract_hash=contract)


def _merge(target,contribution):
    """Supplement, but never erase a native FAIL or missing native probe."""
    target["proofs"].extend(contribution.get("proofs",[]))
    target["observed"].extend(contribution.get("observed",[]))
    target["limits"].extend(contribution.get("limits",[]))
    target.setdefault("reproduction",[]).append("independent browser contribution on identical artifact")
    if contribution.get("status")=="FAIL": target["status"]="FAIL"
    elif target["status"]=="PASS" and contribution.get("status")!="PASS": target["status"]="NOT_VERIFIED"
    # Missing native checks cannot be retroactively satisfied by a UI receipt.


async def _operation_row(requirement,store,checks,limits,*,extra_proofs=(),reproduction=()):
    """Typed native predicates + actual mapped files; review never synthesized."""
    rid=requirement.id;proofs=list(extra_proofs)
    if checks:
        path=store.root/"reports"/store.snapshot/"harness"/(rid+"-"+uuid4().hex+".json")
        path.parent.mkdir(parents=True,exist_ok=True)
        payload=dict(id=rid,snapshot_hash=store.snapshot,contract_hash=store.contract,checks=checks)
        path.write_bytes(json.dumps(payload,sort_keys=True,ensure_ascii=True).encode())
        proofs.append(Proof("X",str(path),hashlib.sha256(path.read_bytes()).hexdigest(),store.snapshot,store.contract,
            tuple(rid+":"+c["check"] for c in checks),all(c["passed"] for c in checks)))
    try: proofs.extend(await store.proofs(rid))
    except AdapterUnavailable: limits.append("independent mapped operations review unavailable")
    missing=set(requirement.required_evidence)-{p.type for p in proofs}
    if missing: limits.append("missing operations proof types: "+",".join(sorted(missing)))
    fail=any(c["passed"] is False for c in checks) or any(p.passed is False for p in proofs)
    row=_unverified(requirement,store.snapshot,store.contract,"")
    row.update(status="FAIL" if fail else "NOT_VERIFIED" if limits or not checks else "PASS",
        observed=checks,proofs=[asdict(p) for p in proofs],limits=limits,reproduction=list(reproduction),
        impact="operations source invariant violated" if fail else "")
    return row


async def _operations(contract,snapshot_root,snapshot_hash,supervisor_root):
    """Runnable OPS ports, separate from instrumented SEC/FUN/ARC diagnosis.

    Build/audit/timings are independent native-runner X records. Final-image
    identity is inspected again; source is NEVER overlaid on /app. Missing
    production E2E/review/lifecycle data is a removable capability gap, not a
    permanent invented PASS and not an accusation against unexecuted product.
    """
    import re
    from datetime import datetime
    from dataclasses import replace
    requirements={r.id:r for r in contract.requirements};store=SupervisorEvidenceStore(supervisor_root,snapshot_hash,contract.contract_hash)
    results={}; build=None
    async def finish(rid,checks,limits,extra=(),repro=()):
        if rid in requirements: results[rid]=await _operation_row(requirements[rid],store,checks,limits,extra_proofs=extra,reproduction=repro)
    def check(rows,name,passed,observed): rows.append(dict(check=name,passed=bool(passed),observed=observed))
    checks=[];limits=[]
    try:
        build=await store.observe("delivery_build")
        if not isinstance(build,dict) or not isinstance(build.get("commands"),list) or not isinstance(build.get("locks"),dict):
            raise AdapterUnavailable("typed isolated delivery build record absent")
        image=build.get("image_id","")
        if not re.fullmatch(r"sha256:[a-f0-9]{64}",image): raise AdapterUnavailable("immutable delivery image identity absent")
        check(checks,"clean_install",build.get("isolated") is True and build.get("no_host_dependencies") is True and build.get("manifest_only_install") is True,
            {k:build.get(k) for k in ("isolated","no_host_dependencies","manifest_only_install")})
        source=Path(snapshot_root).resolve()
        required={"pyproject.toml","uv.lock"}
        if (source/"frontend/package.json").exists(): required|={"frontend/package.json","frontend/package-lock.json"}
        check(checks,"locks",required<=build["locks"].keys() and all((source/path).is_file() and hashlib.sha256((source/path).read_bytes()).hexdigest()==build["locks"][path] for path in required),
            {path:build["locks"].get(path) for path in sorted(required)})
        expected={"backend_install","image_build"}|({"frontend_install","typecheck","frontend_build"} if (source/"frontend/package.json").exists() else set())
        names={c.get("kind") for c in build["commands"]}
        if not expected<=names: raise AdapterUnavailable("required clean install/typecheck/build/image command receipts missing")
        for command in build["commands"]:
            if not isinstance(command.get("argv"),list) or not command["argv"] or type(command.get("return_code")) is not int:
                raise AdapterUnavailable("literal command/return-code receipt missing")
            check(checks,"command_"+str(command["kind"]),command["return_code"]==0,{"argv":command["argv"],"return_code":command["return_code"]})
    except Exception as exc: limits.append("clean final-image build unavailable: "+type(exc).__name__)
    await finish("OPS-01",checks,limits,repro=("independent isolated manifest/lock install, native typecheck/build, trusted final-image recipe",))
    # Audits/README are their own gate. A valid image or restarted DB does not
    # prove reproducibility of documented commands or a dependency audit.
    checks=[];limits=[]
    try:
        data=await store.observe("docs_audit"); source=Path(snapshot_root).resolve()
        readme=data["readme"]; path=(source/readme["path"]).resolve()
        if not path.is_relative_to(source) or not path.is_file() or path.is_symlink(): raise AdapterUnavailable("actual README source unavailable")
        check(checks,"README_source",hashlib.sha256(path.read_bytes()).hexdigest()==readme["sha256"],readme)
        commands=data["documented_commands"]
        if not isinstance(commands,list) or not commands or any(type(c.get("return_code")) is not int or not c.get("argv") for c in commands):
            raise AdapterUnavailable("documented isolated command executions unavailable")
        check(checks,"README_reproduction",all(c["return_code"]==0 for c in commands),commands)
        configs=data["configuration"]
        if not isinstance(configs,list) or not configs: raise AdapterUnavailable("actual expurgated configuration records absent")
        from ..agents.file_broker import ExecutionContext,FileBroker
        broker=FileBroker(ExecutionContext("configuration-review",source))
        for config in configs:
            file=broker.path(config["path"])
            if not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest()!=config["source_sha256"]:
                raise AdapterUnavailable("expurgated configuration source identity changed")
        check(checks,"config_expurgated",all(c.get("secrets_found")==[] for c in configs),configs)
        check(checks,"explicit_fixture_no_defaults",data.get("fixtures_explicit") is True and data.get("accounts_before_fixture")==0,
            {k:data.get(k) for k in ("fixtures_explicit","accounts_before_fixture")})
        audit=data["audit"]
        if audit.get("status")!="AVAILABLE": raise AdapterUnavailable("dated dependency audit unavailable")
        date=datetime.fromisoformat(audit["date"].replace("Z","+00:00"))
        if date.tzinfo is None or not audit.get("tool") or not isinstance(audit.get("findings"),list) or audit.get("report_valid") is not True or type(audit.get("return_code")) is not int:
            raise AdapterUnavailable("audit date/tool/report/findings malformed")
        if not audit.get("artifacts"): raise AdapterUnavailable("raw dependency audit artifact absent")
        for raw in audit["artifacts"]:
            proof=store._proof(raw,"OBS:audit_raw")
            if proof.type!="X" or not proof.passed: raise AdapterUnavailable("raw audit observation was not obtained")
        dangerous=[f for f in audit["findings"] if f.get("severity","").lower() in {"critical","high"} and f.get("exploitable") is True and not f.get("arbitration")]
        if any(type(f.get("exploitable")) is not bool for f in audit["findings"]): raise AdapterUnavailable("audit exploitability assessment unavailable")
        check(checks,"audit_no_unarbitrated_exploitable_high",not dangerous,{"date":audit["date"],"tool":audit["tool"],"findings":audit["findings"]})
    except Exception as exc: limits.append("README/configuration/audit unavailable: "+type(exc).__name__)
    await finish("OPS-05",checks,limits,repro=("reproduce documented argv inside isolation and inspect dated dependency audit with independent source review",))
    checks=[];limits=[]
    try:
        data=await store.observe("execution_timings")
        import math
        if not isinstance(data.get("machine"),dict) or not {"os","cpu","python","docker"}<=data["machine"].keys(): raise AdapterUnavailable("identified machine missing")
        metrics=data["seconds"]
        for key in ("install","tests","browser","build","docker"):
            value=metrics[key]
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<0: raise AdapterUnavailable("measured timing missing")
        check(checks,"measured_machine_and_phases",True,data)
        if "llm_cost" in data and data.get("llm_cost_reported") is not True: raise AdapterUnavailable("unreported LLM cost cannot become measured")
    except Exception as exc: limits.append("diagnostic machine/timings unavailable: "+type(exc).__name__)
    await finish("OPS-06",checks,limits,repro=("report measured durations; <2min/<3min are diagnostics, not scenario deletion thresholds",))
    if build is None or results.get("OPS-01",{}).get("status")!="PASS":
        for rid in ("OPS-02","OPS-03","OPS-04"):
            await finish(rid,[],["clean immutable final image prerequisite not admitted"])
        return results
    try:
        context,_=_context(contract,snapshot_root,snapshot_hash,supervisor_root,image_id=build["image_id"])
        async with context as h:
            image=await h.verify_image_source(snapshot_hash,contract.contract_hash,additional_files=build.get("frontend_files",{}))
            if image["status"]!="PASS":
                for rid in ("OPS-01","OPS-02","OPS-03","OPS-04"):
                    await finish(rid,[dict(check="actual_baked_source",passed=False,observed=image)],[])
                return results
            inspect=getattr(h.runtime,"inspect_configuration",None)
            checks=[];limits=[]
            if not callable(inspect): limits.append("owned runtime configuration inspection port absent")
            else:
                import asyncio
                config=await asyncio.to_thread(inspect)
                mounts=config["mounts"]
                check(checks,"effective_confinement",config["user"] not in {"","0","0:0","root","root:root"} and config["privileged"] is False and config["read_only"] is True and config["network_mode"]=="none" and "ALL" in config["cap_drop"] and any("no-new-privileges" in o for o in config["security_opt"]),
                    {k:config[k] for k in ("user","privileged","read_only","network_mode","cap_drop","security_opt")})
                check(checks,"owned_volume_no_host_mount",not any(m["type"]=="bind" for m in mounts) and any(m["type"]=="volume" and m["name"]==h.runtime.volume_name and m["rw"] is True for m in mounts) and not config["published_ports"] and h.runtime.origin.startswith("http://127.0.0.1:"),
                    {"mount_types":[m["type"] for m in mounts],"owned_volume":h.runtime.volume_name,"origin":h.runtime.origin})
            await finish("OPS-02",checks,limits,repro=("inspect exact owned container configuration and actual baked source; external R must review exclusions/no runtime installer",))
            await h.adapter.prepare_case("VERTICAL")
            async def smoke(adapter,snapshot,oracle): return await _browser_smoke(h,snapshot,oracle)
            vertical=await h.verify_vertical(snapshot_hash,contract.contract_hash,browser_smoke=smoke)
            checks=[];limits=[];extra=[]
            check(checks,"production_vertical",vertical["status"]=="PASS",{"status":vertical["status"],"stages":[dict(name=s["name"],passed=s["passed"]) for s in vertical["stages"]]})
            if vertical["status"]=="NOT_VERIFIED": limits.extend(vertical["limits"])
            for stage in vertical["stages"]:
                extra.extend(replace(Proof(**p),checks=("OPS-03:"+stage["name"],)+tuple(p["checks"])) for p in stage["proofs"])
            response=await h.adapter.request(None,"GET","/api/health",authenticate=False)
            check(checks,"health",response.status_code==200,{"status":response.status_code})
            response=await h.adapter.request(None,"GET","/api/tickets",authenticate=False)
            check(checks,"private_API_anonymous",response.status_code==401,{"status":response.status_code})
            try:
                runs=await store.observe("browser_e2e")
                for eid in ("E2E-01","E2E-02"):
                    rows=[r for r in runs if r.get("id")==eid and r.get("image_id")==build["image_id"]]
                    if not rows: raise AdapterUnavailable("production-image E2E scenario absent: "+eid)
                    if any(r.get("status") not in {"PASS","FAIL"} for r in rows): raise AdapterUnavailable("production E2E scenario unavailable")
                    check(checks,eid,all(r["status"]=="PASS" and r.get("real_ui_api_db") is True and r.get("nominal_mocks") is False and r.get("unhandled_console_errors")==[] for r in rows),rows)
            except AdapterUnavailable as exc: limits.append(str(exc))
            await finish("OPS-03",checks,limits,extra,repro=("final baked image real UI/API/DB vertical, anonymous API 401, health 200, source E2E-01 and E2E-02 on identical image",))
            try:
                persistence=await h.verify_operations_persistence(snapshot_hash,contract.contract_hash)
                await finish("OPS-04",persistence["observed"],persistence["limits"],
                    [Proof(**p) for p in persistence["proofs"]],persistence["reproduction"])
            except Exception as exc: await finish("OPS-04",[],["complete production ticket/response/note/replay/lifecycle unavailable: "+type(exc).__name__])
    except Exception as exc:
        for rid in ("OPS-02","OPS-03","OPS-04"):
            if rid not in results: await finish(rid,[],["actual production image unavailable: "+type(exc).__name__])
    return results


async def verify_project(state,contract,snapshot_root,snapshot_hash,evidence_root)->list[dict]:
    """SEC/FUN/ARC -> browser -> quality sequentially, one row per source ID.

    OPS remains unverified without a formal complete image/docs/audit pack;
    diagnostic instrumentation is a separate runtime from the direct image.
    This entrypoint never uses native green as a substitute for external probes.
    """
    known={r.id:r for r in contract.requirements};records={};limits=[]
    try:
        context,store=_context(contract,snapshot_root,snapshot_hash,evidence_root,instrumented=True)
        async with context as harness:
            from .security_contracts import SecurityVerifier
            from .business_contracts import BusinessContractVerifier
            from .architecture_contracts import ArchitectureContractVerifier
            from .browser_contracts import PlaywrightHarness,BrowserVerifier
            from .quality_contracts import QualityVerifier
            adapter=EvidenceAdapter(harness.adapter,store)
            for name,build in (("security",lambda:SecurityVerifier(contract,adapter)),
                               ("business",lambda:BusinessContractVerifier(adapter,contract)),
                               ("architecture",lambda:ArchitectureContractVerifier(adapter,contract))):
                try:
                    report=await build().verify(snapshot_hash)
                    rows=report if isinstance(report,list) else report["requirements"]
                    for row in rows:
                        rid=row["id"]
                        if rid not in known or rid in records: raise AdapterUnavailable("unknown/duplicate native ID")
                        records[rid]=row
                except Exception as exc: limits.append(name+" unavailable: "+type(exc).__name__)
            try:
                browser=PlaywrightHarness(adapter,bindings=harness.bindings.browser_bindings,routes=harness.bindings.browser_routes)
                report=await BrowserVerifier(contract,browser).verify(snapshot_hash)
                for row in report["requirements"]:
                    rid=row["id"]
                    if rid not in known: raise AdapterUnavailable("unknown browser ID")
                    if rid in records: _merge(records[rid],row)
                    else: records[rid]=row
                # Quality can consume independently stored native records. No
                # invented coverage/E2E success if runner has not produced them.
            except Exception as exc: limits.append("browser unavailable: "+type(exc).__name__)
            try:
                report=await QualityVerifier(contract,adapter).verify(snapshot_hash)
                for row in report["requirements"]:
                    if row["id"] not in known or row["id"] in records: raise AdapterUnavailable("unknown/duplicate quality ID")
                    records[row["id"]]=row
            except Exception as exc: limits.append("quality unavailable: "+type(exc).__name__)
    except Exception as exc: limits.append("isolated runtime unavailable: "+type(exc).__name__)
    if any(rid.startswith("OPS-") for rid in known):
        try:
            ops=await _operations(contract,snapshot_root,snapshot_hash,evidence_root)
            if set(ops)&set(records): raise AdapterUnavailable("duplicate operations requirement")
            records.update(ops)
        except Exception as exc: limits.append("independent operations unavailable: "+type(exc).__name__)
    ordered=[]
    for requirement in contract.requirements:
        row=records.get(requirement.id) or _unverified(requirement,snapshot_hash,contract.contract_hash,
            "; ".join(limits) or "complete formal OPS/image/docs/audit pack not executed")
        row.setdefault("reproduction",[]);row.setdefault("impact","source invariant violated" if row["status"]=="FAIL" else "")
        if row.get("contract_hash",contract.contract_hash)!=contract.contract_hash or row.get("snapshot_hash",snapshot_hash)!=snapshot_hash:
            row=_unverified(requirement,snapshot_hash,contract.contract_hash,"report identity drift")
        ordered.append(row)
    status="FAIL" if any(r["status"]=="FAIL" for r in ordered) else "PASS" if ordered and all(r["status"]=="PASS" for r in ordered) else "NOT_VERIFIED"
    return [dict(pack="independent_coordinator",status=status,snapshot_hash=snapshot_hash,
                 contract_hash=contract.contract_hash,requirements=ordered,limits=limits)]
