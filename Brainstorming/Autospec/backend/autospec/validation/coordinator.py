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
    cookie_mode={"type":"object","additionalProperties":False,"required":["environment","tls"],
        "properties":{"environment":mapping({"type":"string"}),"tls":{"type":"boolean"}}}
    security_observations={"type":["object","null"],"additionalProperties":False,
        "required":["cookie_name","fixture_case","actor","app_module","app_attribute","modes","artifact_roots"],
        "properties":{"cookie_name":{"type":"string"},"fixture_case":{"type":"string"},"actor":identifier,
            "app_module":{"type":"string"},"app_attribute":identifier,
            "modes":{"type":"object","additionalProperties":False,
                "required":["https","http_local_explicit","http_without_exception"],
                "properties":{name:cookie_mode for name in ("https","http_local_explicit","http_without_exception")}},
            "artifact_roots":{"type":"array","minItems":1,"uniqueItems":True,"items":{"type":"string"}}}}
    fields={"database_path":{"type":"string","const":"/var/lib/autospec-validation/support.sqlite"},
        "tables":mapping(table),"commands":mapping(command),"runtime_command":argv,
        "auth_path":{"type":"string"},"csrf_field":identifier,"ticket_path":{"type":"string"},
        "auth_required":{"type":"boolean"},"internal_port":{"type":"integer","minimum":1,"maximum":65535},
        "local_cookie_mode":{"type":"boolean"},"browser_bindings":mapping({"type":"string"}),
        "browser_routes":mapping({"type":"string"}),"query_plans":mapping({"type":"array","minItems":2,"maxItems":2}),
        "instrumentation":{"type":["object","null"]},"security_observations":security_observations}
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
    known names -> X Proof (or list of X Proofs for distinct parameters) for a
    JSON payload {name,parameters,value, hashes}.
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
        values=index.get("observations",{}).get(name)
        if values is None: raise AdapterUnavailable("native observation absent: "+name)
        if not isinstance(values,list): values=[values]
        matched=[]
        for value in values:
            proof=self._proof(value,"OBS:"+name)
            if proof.type!="X" or not proof.passed: raise AdapterUnavailable("native observation was not obtained")
            payload=self._read(proof.path)
            if payload.get("name")!=name or (payload.get("snapshot_hash"),payload.get("contract_hash"))!=(self.snapshot,self.contract) or "value" not in payload:
                raise AdapterUnavailable("native payload observation identity mismatch")
            if payload.get("parameters",{})==params: matched.append(payload["value"])
        if len(matched)!=1: raise AdapterUnavailable("native observation parameters absent or ambiguous")
        return matched[0]

    async def record_native_observation(self,name,value,*,parameters=None,source_proofs=()):
        """Supervisor runner publication, never a producer-command callback.

        Every observation must cite already obtained external native artifacts.
        ``passed`` on the wrapper means obtained, not that its value is green;
        failed test/coverage/E2E values are retained and checked by the pack.
        This API does not issue R or infer missing measurements.
        """
        if name not in EXTERNAL_OBSERVATIONS or not source_proofs:
            raise AdapterUnavailable("named native observation and actual artifacts required")
        parameters={} if parameters is None else parameters
        if not isinstance(parameters,dict): raise AdapterUnavailable("explicit observation parameters required")
        for proof in source_proofs:
            if not isinstance(proof,Proof) or proof.type not in {"X","V"} or not Path(proof.path).resolve().is_relative_to(self.root) or not proof.intact(snapshot_hash=self.snapshot,contract_hash=self.contract):
                raise AdapterUnavailable("native source artifact absent, outside root, or stale")
        from ..orchestrator.dependencies import atomic_json
        payload=dict(name=name,parameters=parameters,value=value,snapshot_hash=self.snapshot,
            contract_hash=self.contract,source_proofs=[asdict(p) for p in source_proofs],
            scope="obtained native observation; no independent review or requirement PASS issued")
        path=self.root/"native-observations"/(name+"-"+uuid4().hex+".json")
        atomic_json(path,payload)
        proof=Proof("X",str(path),hashlib.sha256(path.read_bytes()).hexdigest(),self.snapshot,self.contract,("OBS:"+name,))
        index_path=self.root/"observations.json"
        index=self._read(index_path) if index_path.exists() else dict(snapshot_hash=self.snapshot,contract_hash=self.contract,observations={})
        if (index.get("snapshot_hash"),index.get("contract_hash"))!=(self.snapshot,self.contract):
            raise AdapterUnavailable("native index cannot cross snapshot/contract identities")
        values=index["observations"].get(name,[])
        if not isinstance(values,list): values=[values]
        kept=[]
        for previous in values:
            old=self._proof(previous,"OBS:"+name);data=self._read(old.path)
            if data.get("parameters",{})!=parameters: kept.append(previous)
        index["observations"][name]=kept+[asdict(proof)]
        atomic_json(index_path,index)
        return proof

    async def publish_native_proof(self,rid,proof):
        """Append an already obtained X/V, never manufacture independent R."""
        if proof.type not in {"X","V"}: raise AdapterUnavailable("native publication cannot issue review authority")
        self._proof(asdict(proof),rid)
        from ..orchestrator.dependencies import atomic_json
        path=self.root/"proofs.json"
        index=self._read(path) if path.exists() else dict(snapshot_hash=self.snapshot,contract_hash=self.contract,proofs={})
        if (index.get("snapshot_hash"),index.get("contract_hash"))!=(self.snapshot,self.contract):
            raise AdapterUnavailable("proof publication cannot cross identities")
        rows=index["proofs"].setdefault(rid,[])
        if not any(row.get("path")==proof.path and row.get("sha256")==proof.sha256 for row in rows): rows.append(asdict(proof))
        atomic_json(path,index)
        return proof


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


async def sqlite_quality_probe(state,contract,snapshot_root,snapshot_hash,evidence_root)->dict:
    """NativeQualityCollector SQLite port with its own actual Linux lifetime.

    A callback on an active shared runtime cannot attest future cleanup. This
    function creates a distinct owned DB, runs real HTTP transactions, exports
    it, restarts the app on that DB, then verifies cleanup before returning.
    The case and actor are independently reviewed fixture inputs, not defaults.
    """
    import asyncio
    from dataclasses import replace
    context,store=_context(contract,snapshot_root,snapshot_hash,evidence_root,
        instrumented=True,phase="quality-sqlite")
    async with context as h:
        await h.adapter.prepare_case("TST-04")
        actor=h.manifest.metadata.get("quality_actor")
        if actor not in h.manifest.accounts: raise AdapterUnavailable("explicit real SQLite fixture actor absent")
        payload=dict(title="Independent SQLite quality "+uuid4().hex,
            description="Real isolated HTTP transaction, owned SQLite restart and cleanup probe",client_request_id=str(uuid4()))
        response=await h.adapter.request(actor,"POST","/api/tickets",json=payload)
        if response.status_code!=201 or not isinstance(response.json().get("id"),str):
            raise AdapterUnavailable("real SQLite quality transaction unavailable")
        connection_ids=sorted({row["connection_id"] for row in await h.observe("app_connection_pragmas")})
        if len(connection_ids)<2: raise AdapterUnavailable("actual distinct application connections were not observed")
        persistence=await h.verify_persistence(snapshot_hash,contract.contract_hash,ticket_id=response.json()["id"],actor=actor)
        export=await h.export_sqlite(h.evidence_root/("quality-"+uuid4().hex+".sqlite"))
        rt=h.runtime;identifier=rt.identifier;volume=rt.volume_name
        inspect=await asyncio.to_thread(rt.inspect_configuration)
        if inspect.get("container_id")!=identifier or inspect.get("volume",{}).get("Name")!=volume:
            raise AdapterUnavailable("quality runtime ownership attestation missing")
        native=[replace(Proof(**p),checks=("TST-04:real_restart",)+tuple(p["checks"])) for p in persistence["proofs"]]
    # close completed above. Inspect the exact remembered IDs; never prune,
    # adopt a replacement or infer absence from a Docker daemon timeout.
    from ..orchestrator.sandbox import _docker_call
    result=await asyncio.to_thread(_docker_call,[rt.docker,"container","inspect",identifier],
        capture_output=True,text=True,check=False,timeout=3)
    container_absent=result.returncode!=0 and "no such" in result.stderr.lower()
    volume_absent=await asyncio.to_thread(rt._volume_attestation) is None
    cleanup=rt.closed and container_absent and volume_absent and not rt.volume_requested
    if not cleanup: raise AdapterUnavailable("exact owned SQLite runtime cleanup could not be verified")
    value=dict(database_path=str(export),isolated_root=str(context.evidence_root.resolve()),isolated=True,
        connection_ids=connection_ids,restart_verified=persistence["status"]=="PASS",cleanup_owned_only=cleanup,
        database_sha256=hashlib.sha256(export.read_bytes()).hexdigest(),
        scope="actual application transactions on a distinct reviewed owned validation DB; native suite fixture assertions require separate R")
    path=context.evidence_root/("TST-04-"+uuid4().hex+".json")
    path.write_bytes(json.dumps(dict(snapshot_hash=snapshot_hash,contract_hash=contract.contract_hash,
        observed=value,container_id=identifier,volume=volume,container_absent=container_absent,
        volume_absent=volume_absent),sort_keys=True).encode())
    native.append(Proof("X",str(path),hashlib.sha256(path.read_bytes()).hexdigest(),snapshot_hash,contract.contract_hash,
        ("TST-04:real_sqlite_connections_restart_cleanup",),value["restart_verified"]))
    for proof in native: await store.publish_native_proof("TST-04",proof)
    await store.record_native_observation("real_sqlite_test_environment",value,source_proofs=native)
    return value


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


async def _execute_e2e(contract,harness,store,snapshot_hash,*,modes=("alone","together"),scenario_ids=None,image_id=None):
    """Execute browser-owned source scenarios, publish their actual artifacts.

    Native and image runs are sequential; each scenario uses the verifier's
    explicit independent fixture reset. No browser receipt substitutes SEC/FUN
    probes, and a missing mapping remains a recorded NOT_VERIFIED scenario.
    """
    from .browser_contracts import PlaywrightHarness,BrowserVerifier
    from .quality_contracts import source_e2e_scenarios
    expected={s["id"]:s["expected"] for s in source_e2e_scenarios(contract)}
    selected=set(scenario_ids or expected);runs=[];proofs=[];quality_proofs=[]
    if not selected<=set(expected): raise AdapterUnavailable("unknown source E2E scenario requested")
    requests=[(mode,group) for mode in modes for group in ([[sid] for sid in sorted(selected)] if mode=="alone" else [sorted(selected)])]
    for mode,group in requests:
        browser=PlaywrightHarness(EvidenceAdapter(harness.adapter,store),
            bindings=harness.bindings.browser_bindings,routes=harness.bindings.browser_routes)
        report=await BrowserVerifier(contract,browser).verify_e2e(snapshot_hash,mode=mode,scenario_ids=group)
        if (report.get("snapshot_hash"),report.get("contract_hash"))!=(snapshot_hash,contract.contract_hash):
            raise AdapterUnavailable("native browser E2E identity changed")
        rows=report.get("scenarios",[])
        if len(rows)!=len(group) or {r.get("id") for r in rows}!=set(group):
            raise AdapterUnavailable("native E2E IDs missing/duplicated")
        for row in rows:
            if row.get("expected")!=expected[row["id"]] or row.get("mode")!=mode or (row.get("snapshot_hash"),row.get("contract_hash"))!=(snapshot_hash,contract.contract_hash):
                raise AdapterUnavailable("E2E source expectation/mode/identity drift")
            if row.get("status") not in {"PASS","FAIL","NOT_VERIFIED"}: raise AdapterUnavailable("invalid native E2E status")
            if row["status"]=="PASS" and (row.get("real_ui_api_db") is not True or row.get("nominal_mocks") is not False
                    or row.get("fixture_reset_before") is not True or row.get("nonblank") is not True
                    or row.get("unhandled_console_errors")!=[] or not row.get("observed")
                    or any(c.get("passed") is not True for c in row["observed"])
                    or not {"X","V"}<={p.get("type") for p in row.get("proofs",[])}
                    or any(p.get("passed") is not True or not p.get("checks") for p in row.get("proofs",[]))):
                raise AdapterUnavailable("incomplete native E2E success claim rejected")
            for value in row.get("proofs",[]):
                proof=Proof(**value)
                if not Path(proof.path).resolve().is_relative_to(store.root) or not proof.intact(snapshot_hash=snapshot_hash,contract_hash=contract.contract_hash):
                    raise AdapterUnavailable("native E2E artifact unavailable or outside supervisor")
                proofs.append(proof)
                if row["status"]!="NOT_VERIFIED" and any(tag.startswith("TST-05:") for tag in proof.checks):
                    quality_proofs.append(proof)
            if image_id: row={**row,"image_id":image_id}
            runs.append(row)
    await store.record_native_observation("browser_e2e",runs,parameters={"image_id":image_id} if image_id else {},source_proofs=proofs)
    store.contributions.setdefault("TST-05",[]).extend(quality_proofs)
    return runs


def _quality_seal(store,seal,source_root):
    """Reverify the exact candidate plan/mapping/source and external R bytes."""
    from .quality_contracts import NativeSuiteSpec,AuthorizationMutationSpec,native_quality_plan_hash,NativeQualityCollector
    path=Path(seal["path"]).resolve()
    if not path.is_relative_to(store.root) or hashlib.sha256(path.read_bytes()).hexdigest()!=seal["sha256"]:
        raise AdapterUnavailable("quality plan seal changed/outside supervisor")
    data=store._read(path)
    if (data.get("snapshot_hash"),data.get("contract_hash"))!=(store.snapshot,store.contract):
        raise AdapterUnavailable("quality plan identity drift")
    mapping=Path(data["mapping_path"]).resolve()
    if not mapping.is_relative_to(store.root) or hashlib.sha256(mapping.read_bytes()).hexdigest()!=data["mapping_sha256"]:
        raise AdapterUnavailable("quality assertion mapping changed")
    records=data.get("suites")
    fields={"name","root","ecosystem","source_inventory","domains","test_args","coverage_source"}
    if (not isinstance(records,list) or not 1<=len(records)<=3 or any(not isinstance(s,dict) or set(s)!=fields for s in records)):
        raise AdapterUnavailable("typed native suites with exact fields required")
    suites=[]
    for record in records:
        if any(not isinstance(record[field],list) for field in ("source_inventory","domains","test_args")):
            raise AdapterUnavailable("typed native suite JSON arrays required")
        if (len(record["domains"])>200 or any(not isinstance(domain,str) or len(domain)>4096 or "\x00" in domain for domain in record["domains"])):
            raise AdapterUnavailable("typed native suite domain values required")
        try:
            suites.append(NativeSuiteSpec(**{**record,**{field:tuple(record[field]) for field in ("source_inventory","domains","test_args")}}))
        except (ValueError,TypeError) as exc:
            raise AdapterUnavailable("typed native suite values invalid") from exc
    suites=tuple(suites)
    if len({suite.name for suite in suites})!=len(suites):
        raise AdapterUnavailable("distinct native suite names required")
    mutation=AuthorizationMutationSpec(**data["mutation"]) if data.get("mutation") else None
    mode=data.get("e2e_mode")
    if not isinstance(mode,str) or mode not in {"native","supervisor_browser"}:
        raise AdapterUnavailable("explicit reviewed native E2E mode required")
    digest=native_quality_plan_hash(suites,mapping,mutation,e2e_mode=mode)
    if digest!=data["plan_hash"]: raise AdapterUnavailable("quality plan content/fingerprint mismatch")
    proof=store._proof(seal["review"],"QUALITY:plan:"+digest)
    if proof.type!="R" or not proof.passed: raise AdapterUnavailable("quality plan independent R missing")
    if mode=="supervisor_browser" and "QUALITY:e2e:supervisor_browser" not in proof.checks:
        raise AdapterUnavailable("supervisor browser mode needs its exact independent R tag")
    root=Path(source_root).resolve()
    for suite in suites:
        suite_root=(root/suite.root).resolve()
        if not suite_root.is_relative_to(root): raise AdapterUnavailable("quality suite root escaped source")
        actual={p:hashlib.sha256(NativeQualityCollector._source(suite_root,p).read_bytes()).hexdigest() for p in suite.source_inventory}
        if actual!=data["source_inventory"][suite.name]: raise AdapterUnavailable("quality reviewed source inventory changed")
    return proof


async def publish_reviewed_e2e(store,runs,*,plan_path,review,source_root):
    """Root collection handoff: seal actual twelve X/V rows for one reuse.

    A source-reviewed plan is checked here and again at reuse. No annotations
    from a producer are trusted and no image-stage receipts reuse source runs.
    """
    path=Path(plan_path).resolve()
    seal=dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),review=asdict(review))
    _quality_seal(store,seal,source_root)
    rows=[dict(row,quality_plan=seal) for row in runs]
    proofs=[Proof(**p) for row in rows for p in row.get("proofs",[])]
    await store.record_native_observation("browser_e2e",rows,source_proofs=proofs)
    return rows


async def _reuse_reviewed_e2e(contract,store,source_root):
    """Cached native observations only; narration/missing mode/proof => rerun."""
    from .quality_contracts import source_e2e_scenarios
    rows=await store.observe("browser_e2e")
    expected={r["id"]:r["expected"] for r in source_e2e_scenarios(contract)}
    if not isinstance(rows,list) or len(rows)!=12 or {(r.get("id"),r.get("mode")) for r in rows}!={(rid,mode) for rid in expected for mode in ("alone","together")}:
        raise AdapterUnavailable("exact twelve source scenario/mode observations required")
    seals=[r.get("quality_plan") for r in rows]
    if any(not isinstance(s,dict) or s!=seals[0] for s in seals): raise AdapterUnavailable("uniform independent quality plan seal absent")
    _quality_seal(store,seals[0],source_root)
    proofs=[]
    for row in rows:
        if row.get("image_id") or row.get("expected")!=expected[row["id"]] or (row.get("snapshot_hash"),row.get("contract_hash"))!=(store.snapshot,store.contract) or row.get("status") not in {"PASS","FAIL"}:
            raise AdapterUnavailable("native E2E source expectation/identity/scope drift")
        if row.get("real_ui_api_db") is not True or row.get("nominal_mocks") is not False or row.get("fixture_reset_before") is not True or not row.get("observed"):
            raise AdapterUnavailable("real independent E2E execution absent")
        scoped=[];actual=[]
        for raw in row.get("proofs",[]):
            proof=store._proof(raw,"TST-05:"+row["id"])
            if proof.type not in {"X","V"}: continue
            scoped.append(proof)
            if proof.type=="X":
                body=store._read(proof.path)
                if body.get("mode")==row["mode"] and body.get("source_expected")==expected[row["id"]] and body.get("checks")==row["observed"]:
                    actual.append(proof)
        if not actual or not {"X","V"}<={p.type for p in scoped}:
            raise AdapterUnavailable("exact mode/source/observed native X+V required")
        if row["status"]=="PASS" and (row.get("nonblank") is not True or row.get("unhandled_console_errors")!=[] or any(c.get("passed") is not True for c in row["observed"]) or any(p.passed is not True for p in scoped)):
            raise AdapterUnavailable("incomplete native E2E success claim")
        if row["status"]=="FAIL" and not (any(c.get("passed") is False for c in row["observed"]) or any(p.passed is False for p in scoped) or row.get("nonblank") is False or row.get("unhandled_console_errors")):
            raise AdapterUnavailable("native E2E failure is not backed by observations")
        proofs.extend(scoped)
    store.contributions.setdefault("TST-05",[]).extend(proofs)
    return rows


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
        import asyncio
        from .delivery_evidence import delivery_build_checks
        checks.extend(await asyncio.to_thread(delivery_build_checks,build,Path(snapshot_root),snapshot_hash))
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
        from .delivery_evidence import REQUIRED_DOC_OBLIGATIONS
        if not REQUIRED_DOC_OBLIGATIONS<={c.get("obligation") for c in commands}:
            raise AdapterUnavailable("complete source README obligations unavailable")
        if not isinstance(commands,list) or not commands or any(not c.get("argv") or (type(c.get("return_code")) is not int and not (c.get("return_code") is None and c.get("execution") in {"attested-cache","attested-layer","failed-build","observed-runtime"} and type(c.get("passed")) is bool)) for c in commands):
            raise AdapterUnavailable("documented isolated command executions unavailable")
        check(checks,"README_reproduction",all(c["return_code"]==0 if type(c.get("return_code")) is int else c["passed"] is True for c in commands),commands)
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
        from .delivery_evidence import audit_disposition_checks
        checks.extend(audit_disposition_checks(audit, evidence_root=supervisor_root,
            snapshot_hash=snapshot_hash, contract_hash=contract.contract_hash))
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
            if vertical["status"]=="NOT_VERIFIED": limits.extend(vertical["limits"])
            else: check(checks,"production_vertical",vertical["status"]=="PASS",{"status":vertical["status"],"stages":[dict(name=s["name"],passed=s["passed"]) for s in vertical["stages"]]})
            for stage in vertical["stages"]:
                extra.extend(replace(Proof(**p),checks=("OPS-03:"+stage["name"],)+tuple(p["checks"])) for p in stage["proofs"])
            response=await h.adapter.request(None,"GET","/api/health",authenticate=False)
            check(checks,"health",response.status_code==200,{"status":response.status_code})
            response=await h.adapter.request(None,"GET","/api/tickets",authenticate=False)
            check(checks,"private_API_anonymous",response.status_code==401,{"status":response.status_code})
            try:
                runs=await _execute_e2e(contract,h,store,snapshot_hash,modes=("alone",),
                    scenario_ids=("E2E-01","E2E-02"),image_id=build["image_id"])
                for eid in ("E2E-01","E2E-02"):
                    rows=[r for r in runs if r.get("id")==eid and r.get("image_id")==build["image_id"]]
                    if not rows: raise AdapterUnavailable("production-image E2E scenario absent: "+eid)
                    if any(r.get("status") not in {"PASS","FAIL"} for r in rows): raise AdapterUnavailable("production E2E scenario unavailable")
                    check(checks,eid,all(r["status"]=="PASS" and r.get("real_ui_api_db") is True and r.get("nominal_mocks") is False and r.get("unhandled_console_errors")==[] for r in rows),rows)
                    extra.extend(replace(Proof(**p),checks=("OPS-03:"+eid,)+tuple(p["checks"])) for row in rows for p in row["proofs"])
            except Exception as exc: limits.append("production image source E2E unavailable: "+type(exc).__name__)
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


def _current_rows(report, expected, snapshot, oracle):
    """Reject mixed/partial pack identities before publishing any receipts."""
    if isinstance(report, dict):
        if (report.get("snapshot_hash"), report.get("contract_hash")) != (snapshot, oracle):
            raise AdapterUnavailable("pack snapshot/oracle identity differs")
        rows = report["requirements"]
    else:
        rows = report
    if (not isinstance(rows, list) or len(rows) != len(expected) or
            {row.get("id") for row in rows} != set(expected)):
        raise AdapterUnavailable("pack IDs missing, unknown or duplicated")
    result = []
    for row in rows:
        if (row.get("snapshot_hash", snapshot), row.get("contract_hash", oracle)) != (snapshot, oracle):
            raise AdapterUnavailable("requirement snapshot/oracle identity differs")
        result.append({**row, "snapshot_hash": snapshot, "contract_hash": oracle})
    return result


async def _native_browser_packs(contract, harness, store, snapshot_hash):
    """Execute native probes, actual UI contributions, then bounded native joins.

    A first NV caused only by not-yet-observed UI may be admitted only after a
    fresh complete native execution consumes those exact current X/V. Native
    FAIL, missing execution and absent retained native artifacts never promote.
    ARC's narrow client contribution is published before its full native pack.
    """
    from .security_contracts import SecurityVerifier
    from .business_contracts import BusinessContractVerifier
    from .architecture_contracts import ArchitectureContractVerifier
    from .architecture_browser import collect_architecture_client
    from .browser_contracts import PlaywrightHarness, BrowserVerifier, BROWSER_IDS
    from .evidence_join import (CROSSED_IDS, publish_backend_receipt,
                               publish_browser_receipts, join_rechecked_native)
    known = {r.id for r in contract.requirements}
    records, limits, published = {}, [], set()
    adapter = EvidenceAdapter(harness.adapter, store)
    builders = {"SEC-": lambda: SecurityVerifier(contract, adapter),
                "FUN-": lambda: BusinessContractVerifier(adapter, contract),
                "ARC-": lambda: ArchitectureContractVerifier(adapter, contract)}
    for prefix, build in builders.items():
        if prefix == "ARC-" and "ARC-06" in known:
            try:
                browser = PlaywrightHarness(adapter, bindings=harness.bindings.browser_bindings,
                                            routes=harness.bindings.browser_routes)
                report = await collect_architecture_client(contract, browser, snapshot_hash)
                rows = _current_rows(report, {"ARC-06"}, snapshot_hash, contract.contract_hash)
                tagged = any(p.get("type") == "X" and "ARC-06:error_client" in p.get("checks", ())
                             for p in rows[0].get("proofs", ()))
                if not tagged or rows[0]["status"] == "NOT_VERIFIED":
                    raise AdapterUnavailable("complete native ARC-06 client contribution absent")
                await publish_browser_receipts(store, rows)
            except Exception as exc:
                limits.append("architecture client unavailable: " + type(exc).__name__)
        expected = {rid for rid in known if rid.startswith(prefix)}
        if not expected:
            continue
        try:
            rows = _current_rows(await build().verify(snapshot_hash), expected, snapshot_hash, contract.contract_hash)
            for row in rows:
                rid = row["id"]
                if rid in records:
                    raise AdapterUnavailable("duplicate native requirement")
                if rid in CROSSED_IDS:
                    try:
                        if await publish_backend_receipt(store, row):
                            published.add(rid)
                        elif row.get("native_complete") is True:
                            raise AdapterUnavailable("intact actual native artifact absent")
                    except Exception as exc:
                        row["native_complete"] = False
                        row["limits"] = list(row.get("limits", ())) + ["native backend receipt unavailable: " + type(exc).__name__]
                        if row["status"] != "FAIL":
                            row["status"] = "NOT_VERIFIED"
                records[rid] = row
        except Exception as exc:
            limits.append(prefix + " native pack unavailable: " + type(exc).__name__)
    browser_rows = {}
    try:
        browser = PlaywrightHarness(adapter, bindings=harness.bindings.browser_bindings,
                                    routes=harness.bindings.browser_routes)
        report = await BrowserVerifier(contract, browser).verify(snapshot_hash)
        rows = _current_rows(report, set(BROWSER_IDS) & known, snapshot_hash, contract.contract_hash)
        await publish_browser_receipts(store, rows)
        browser_rows = {row["id"]: row for row in rows}
    except Exception as exc:
        limits.append("browser unavailable: " + type(exc).__name__)
    for prefix in ("SEC-", "FUN-"):
        selected = sorted(rid for rid in CROSSED_IDS & published & browser_rows.keys()
                          if rid.startswith(prefix) and records[rid]["status"] != "FAIL")
        if not selected:
            continue
        try:
            rows = _current_rows(await builders[prefix]().verify(snapshot_hash, ids=selected),
                                 set(selected), snapshot_hash, contract.contract_hash)
            for row in rows:
                rid = row["id"]
                records[rid] = join_rechecked_native(records[rid], row, browser_rows.pop(rid))
        except Exception as exc:
            limits.append(prefix + " cross-layer native replay unavailable: " + type(exc).__name__)
            for rid in selected:
                records[rid]["limits"].append("current cross-layer native replay unavailable")
                if records[rid]["status"] != "FAIL":
                    records[rid]["status"] = "NOT_VERIFIED"
    for rid, row in browser_rows.items():
        if rid in records:
            _merge(records[rid], row)
        else:
            records[rid] = row
    return records, limits


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
            from .quality_contracts import QualityVerifier
            adapter=EvidenceAdapter(harness.adapter,store)
            native_records,native_limits=await _native_browser_packs(contract,harness,store,snapshot_hash)
            records.update(native_records);limits.extend(native_limits)
            try:
                try: await _reuse_reviewed_e2e(contract,store,snapshot_root)
                except Exception: await _execute_e2e(contract,harness,store,snapshot_hash)
            except Exception as exc: limits.append("source six-scenario E2E execution unavailable: "+type(exc).__name__)
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
