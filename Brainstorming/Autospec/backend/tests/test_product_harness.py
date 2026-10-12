"""Supervisor binding regression + opt-in genuine Linux/SQLite/Chromium proof.

No product import, ASGI transport, auth mock or synthesized positive browser.
Run with AUTOSPEC_REAL_PRODUCT_HARNESS=1; Docker is mandatory in that run.
"""
import asyncio
import hashlib
import json
import os
from dataclasses import asdict,replace
from pathlib import Path
import shutil
import sqlite3
from uuid import UUID,uuid4,uuid5

import pytest

from autospec.validation.product_harness import (CommandBinding,InstrumentationBinding,
    OwnedProductHarnessSession,ProductHarness,ReviewedFixtureFactory,ReviewedProductBindings,TableBinding)
from autospec.validation.support_adapter import AdapterUnavailable,Proof

ROOT=Path(__file__).parent/"fixtures/product_harness"
NS=UUID("c19d306b-34cb-466d-bc23-7fbd42bd726c")
CONTRACT="c"*64
TABLE_COLUMNS={
 "users":"id email email_normalized password_hash role active",
 "tickets":"id owner_id title description status priority assignee_id version created_at updated_at",
 "messages":"id ticket_id author_id content visibility created_at",
 "ticket_events":"id ticket_id event_type created_at",
 "idempotency_keys":"actor_id kind client_request_id result_id",
 "sessions":"token_hash user_id csrf expires_at",
}


def write_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(json.dumps(value,sort_keys=True,ensure_ascii=True).encode())


def fixture_definition():
    accounts={name:dict(id=str(uuid5(NS,name)),email=name+"@example.test",password="$generated",role=role)
        for name,role in zip(("alice","bob","camille","dylan","emma"),("client","client","agent","agent","admin"))}
    tickets={name+str(i):str(uuid5(NS,name+str(i))) for name in ("alice","bob") for i in range(6)}
    tickets.update(alice_open=tickets["alice0"],alice_second=tickets["alice1"],bob=tickets["bob0"])
    rows=[dict(id=tickets[name+str(i)],owner_id={"$ref":"accounts."+name+".id"},
        title="Fixture "+name+str(i),description="Independent fixture description") for name in ("alice","bob") for i in range(6)]
    return dict(accounts=accounts,tickets=tickets,metadata=dict(provisioning=["migrate_fresh","bootstrap","seed"],
        bootstrap_actor="emma",vertical_actor="alice",fixture_scope="independent metatest, not benchmark product"),
        commands=dict(migrate_fresh={},bootstrap=dict(credentials={"$ref":"accounts.emma"}),
                      seed=dict(payload=dict(accounts={"$ref":"accounts"},tickets=rows))))


def reviewed_fixture_file(root,source,snapshot,definition=None):
    definition=definition or fixture_definition()
    content=dict(snapshot_hash=snapshot,contract_hash=CONTRACT,cases={"VERTICAL":definition,"INSTRUMENTED":definition,"ARC-03":definition})
    digest=hashlib.sha256(json.dumps(content,sort_keys=True,ensure_ascii=True).encode()).hexdigest()
    review_path=root/"fixture-review.json"; write_json(review_path,{"scope":"independent test fixture-input review","fingerprint":digest})
    proof=Proof("R",str(review_path),hashlib.sha256(review_path.read_bytes()).hexdigest(),snapshot,CONTRACT,
        ("PRODUCT:fixtures","PRODUCT:fixtures:"+digest))
    path=root/"reviewed-fixtures.json"; write_json(path,{**content,"review":asdict(proof)})
    return path


def make_bindings(root,source,snapshot):
    files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir() if p.is_file()}
    tables={name:TableBinding(name,{c:c for c in columns.split()}) for name,columns in TABLE_COLUMNS.items()}
    review_path=root/"bindings-review.json"; write_json(review_path,{"scope":"independent test fixture bindings, not benchmark review"})
    proof=Proof("R",str(review_path),hashlib.sha256(review_path.read_bytes()).hexdigest(),snapshot,CONTRACT,("PRODUCT:bindings",))
    commands={name:CommandBinding(("/opt/venv/bin/python","main.py",name),parameters)
        for name,parameters in (("migrate_fresh",("fault",)),("bootstrap",("credentials",)),("seed",("payload",)),("reject",()))}
    hook=InstrumentationBinding("main","app",clock_module="main",clock_attribute="now",
        business_tables=("tickets","messages"),audit_table="ticket_events",
        races={"ticket_patch":(("PATCH",r"/api/tickets/[a-f0-9-]+"),),"ticket_create":(("POST","/api/tickets"),)},proxy_headers=False)
    binding=ReviewedProductBindings(snapshot,CONTRACT,files,proof,"/var/lib/autospec-validation/support.sqlite",
        tables,commands,("/opt/venv/bin/python","main.py"),"/api/auth/login","csrf_token","/api/tickets/{id}",
        instrumentation=hook,local_cookie_mode=True,query_plans={"tickets":("SELECT * FROM tickets WHERE owner_id=?",("owner",))},
        browser_bindings=dict(email="#email",password="#password",login="#login",ticket_list="#tickets",create="#create",title="#title",description="#description",submit="#submit",detail="#detail"),
        browser_routes=dict(home="/",ticket="/tickets/{id}",admin="/admin"))
    return replace(binding,review=replace(proof,checks=("PRODUCT:bindings","PRODUCT:bindings:"+binding.fingerprint())))


@pytest.fixture
def simple_profile(tmp_path):
    source=tmp_path/"source";source.mkdir();shutil.copyfile(ROOT/"main.py",source/"main.py")
    snapshot="a"*64
    bindings=make_bindings(tmp_path,source,snapshot)
    return tmp_path,source,snapshot,bindings


def test_profile_mapping_mutation_requires_new_independent_review(simple_profile):
    root,source,snapshot,b=simple_profile;b.validate(source)
    with pytest.raises(AdapterUnavailable): replace(b,ticket_path="/fake/{id}").validate(source)
    b.tables["tickets"].columns["version"]="priority"
    with pytest.raises(AdapterUnavailable): b.validate(source)


def test_review_artifact_and_source_hash_drift_are_fail_closed(simple_profile):
    root,source,snapshot,b=simple_profile
    (source/"main.py").write_bytes(b"altered source")
    with pytest.raises(AdapterUnavailable): b.validate(source)


@pytest.mark.asyncio
async def test_reviewed_json_fixture_inputs_are_usable_and_not_product_derived(simple_profile):
    root,source,snapshot,b=simple_profile
    path=reviewed_fixture_file(root,source,snapshot)
    factory=ReviewedFixtureFactory(path,snapshot_hash=snapshot,contract_hash=CONTRACT,source_root=source)
    a,p=await factory("VERTICAL");a2,p2=await factory("VERTICAL")
    assert len(a.accounts)==5 and len(p["seed"]["payload"]["tickets"])==12
    assert p["bootstrap"]["credentials"]["password"]==a.accounts["emma"].password
    assert a.accounts["alice"].password!=a2.accounts["alice"].password
    assert a.tickets==a2.tickets
    assert "password=" not in repr(a.accounts["alice"])
    with pytest.raises(AdapterUnavailable): await factory("UNKNOWN")
    with pytest.raises(AdapterUnavailable): await factory("VERTICAL",query_count=17)
    path.write_bytes(path.read_bytes()+b" ")
    with pytest.raises(AdapterUnavailable): await factory("VERTICAL")


def test_no_product_python_import_happens_on_host(simple_profile):
    root,source,snapshot,b=simple_profile
    assert "main" not in __import__("sys").modules
    assert b.commands["bootstrap"].argv[0]=="/opt/venv/bin/python"
    with pytest.raises(ValueError): CommandBinding(("python","main.py")).validate()


REAL=pytest.mark.skipif(os.environ.get("AUTOSPEC_REAL_PRODUCT_HARNESS")!="1",reason="opt-in real Linux/Chromium fixture campaign")


@pytest.fixture(scope="module")
def linux_fixture_source(tmp_path_factory):
    from autospec.orchestrator.validation_environment import LinuxEnvironmentManager
    base=tmp_path_factory.mktemp("product-harness-linux")
    source=base/"source"; source.mkdir()
    for name in ("main.py","pyproject.toml","uv.lock"): shutil.copyfile(ROOT/name,source/name)
    manager=LinuxEnvironmentManager(base/"cache",timeout=300)
    manager.ensure_lock(source,"python")
    manager.prepare(source,"python","runtime")
    from autospec.validation.final_gate import source_snapshot
    snapshot=source_snapshot(source).digest
    return base,source,snapshot


def session(linux,case_root,*,instrumented=False,definition=None,image_id=None):
    base,source,snapshot=linux
    binding=make_bindings(case_root,source,snapshot)
    fixtures=reviewed_fixture_file(case_root,source,snapshot,definition)
    path=case_root/"product-bindings.json"; write_json(path,asdict(binding))
    async def identity(): return snapshot
    async def oracle(): return CONTRACT
    return OwnedProductHarnessSession.from_bindings(path,source_root=source,stage_root=case_root/"stage",
        evidence_root=case_root/"proofs",cache_root=base/"cache",fixtures_path=fixtures,
        snapshot_hash=identity,contract_hash=oracle,instrumented=instrumented,image_id=image_id)


async def actual_browser_smoke(adapter,snapshot,contract):
    from autospec.validation.browser_contracts import PlaywrightHarness,browser_smoke
    harness=PlaywrightHarness(adapter,bindings=dict(email="#email",password="#password",login="#login",ticket_list="#tickets",
        create="#create",title="#title",description="#description",submit="#submit",detail="#detail"),
        routes=dict(home="/",ticket="/tickets/{id}",admin="/admin"))
    return await browser_smoke(harness,snapshot,contract,adapter.manifest.accounts["alice"],
        title="Genuine Linux browser creation",description="Actual Argon2 HTTP and committed SQLite audit")


@REAL
@pytest.mark.asyncio
async def test_real_linux_vertical_and_owned_volume_persistence(linux_fixture_source,tmp_path):
    async with session(linux_fixture_source,tmp_path) as h:
        await h.adapter.prepare_case("VERTICAL")
        receipt=await h.verify_vertical(h.bindings.snapshot_hash,CONTRACT,browser_smoke=actual_browser_smoke)
        assert receipt["status"]=="PASS",receipt
        assert [s["name"] for s in receipt["stages"]]==["schema","bootstrap","argon2","browser_login","browser_create","api_read","db_committed"]
        for stage in receipt["stages"]:
            assert stage["passed"] and stage["proofs"]
            for p in stage["proofs"]: assert Proof(**p).intact(snapshot_hash=h.bindings.snapshot_hash,contract_hash=CONTRACT)
        tickets=(await h.observe("business_state"))["tickets"]
        created=next(t for t in tickets if t["title"]=="Genuine Linux browser creation")
        first_id=h.runtime.identifier;origin=h.runtime.origin
        persisted=await h.verify_persistence(h.bindings.snapshot_hash,CONTRACT,ticket_id=created["id"])
        assert persisted["status"]=="PASS",persisted
        assert h.runtime.identifier!=first_id and h.runtime.origin==origin
        exported=await h.export_sqlite(h.evidence_root/"schema-copy.sqlite")
        with sqlite3.connect(exported) as con: assert con.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]==13
        if os.environ.get("AUTOSPEC_PRODUCT_HARNESS_EVIDENCE_ROOT"):
            dest=Path(os.environ["AUTOSPEC_PRODUCT_HARNESS_EVIDENCE_ROOT"])/"nominal"
            dest.mkdir(parents=True,exist_ok=True)
            # No credential/session/DB export: only independent native receipts.
            for p in h.evidence_root.iterdir():
                if p.suffix in {".json",".png"}: shutil.copyfile(p,dest/p.name)
            for result in (receipt,persisted):
                values=result.get("proofs",[])+[p for stage in result.get("stages",[]) for p in stage["proofs"]]
                for proof in values: proof["path"]=str(dest/Path(proof["path"]).name)
            write_json(dest/"receipt.json",receipt);write_json(dest/"persistence.json",persisted)


@REAL
@pytest.mark.asyncio
async def test_real_baked_image_has_no_stage_overlay_and_persists(linux_fixture_source,tmp_path):
    from autospec.orchestrator.isolated_validation import build_delivery_image
    from autospec.orchestrator.sandbox import _docker_call
    _,source,snapshot=linux_fixture_source
    tag="autospec/harness-fixture:"+uuid4().hex
    ok,output=await asyncio.to_thread(build_delivery_image,source,tag)
    assert ok,output
    inspected=_docker_call(["docker","image","inspect",tag],capture_output=True,text=True,check=True,timeout=10)
    image=json.loads(inspected.stdout)[0]["Id"]
    try:
        async with session(linux_fixture_source,tmp_path,image_id=image) as h:
            assert h.runtime.mount_stage is False
            actual=await h.verify_image_source(snapshot,CONTRACT)
            assert actual["status"]=="PASS",actual
            await h.adapter.prepare_case("VERTICAL")
            receipt=await h.verify_vertical(snapshot,CONTRACT,browser_smoke=actual_browser_smoke)
            assert receipt["status"]=="PASS",receipt
            persisted=await h.verify_persistence(snapshot,CONTRACT,ticket_id=receipt["ticket_id"])
            assert persisted["status"]=="PASS" and h.runtime.mount_stage is False
            config=await asyncio.to_thread(h.runtime.inspect_configuration)
            assert config["user"]=="65532:65532" and config["read_only"] and not config["privileged"]
            assert not any(m["type"]=="bind" for m in config["mounts"])
            ops=await h.verify_operations_persistence(snapshot,CONTRACT)
            assert ops["status"]=="PASS",ops
            if os.environ.get("AUTOSPEC_PRODUCT_HARNESS_EVIDENCE_ROOT"):
                dest=Path(os.environ["AUTOSPEC_PRODUCT_HARNESS_EVIDENCE_ROOT"])/"baked"
                dest.mkdir(parents=True,exist_ok=True)
                for p in h.evidence_root.iterdir():
                    if p.suffix in {".json",".png"}: shutil.copyfile(p,dest/p.name)
                for result in (receipt,persisted,actual,ops):
                    proofs=result.get("proofs",[])+[p for s in result.get("stages",[]) for p in s["proofs"]]
                    for proof in proofs: proof["path"]=str(dest/Path(proof["path"]).name)
                write_json(dest/"receipt.json",receipt);write_json(dest/"persistence.json",persisted);write_json(dest/"image.json",actual)
                write_json(dest/"ops04.json",ops)
            # Both deliberately defective real DB subjects must be detected on
            # the same immutable app image and independently reset fixtures.
            for bug in ("lost_note","reset_on_start"):
                definition=fixture_definition();definition["commands"]["seed"]["payload"]["bug"]=bug
                root=tmp_path/bug;root.mkdir()
                async with session(linux_fixture_source,root,definition=definition,image_id=image) as bad:
                    await bad.adapter.prepare_case("VERTICAL")
                    verdict=await bad.verify_operations_persistence(snapshot,CONTRACT)
                    assert verdict["status"]=="FAIL",(bug,verdict)
    finally:
        # Only this UUID tag; never prune or remove an unknown shared image.
        _docker_call(["docker","image","rm",tag],capture_output=True,text=True,check=False,timeout=10)


@REAL
@pytest.mark.asyncio
async def test_real_linux_instrumentation_connections_clock_fault_race_busy(linux_fixture_source,tmp_path):
    async with session(linux_fixture_source,tmp_path,instrumented=True) as h:
        await h.adapter.prepare_case("INSTRUMENTED")
        assert (await h.adapter.login("alice")).status_code==200
        tid=h.manifest.tickets["alice_open"]
        await h.command("sql_trace_start")
        assert (await h.adapter.request("alice","GET","/api/tickets")).status_code==200
        assert await h.observe("sql_trace")
        assert await h.observe("query_plan")
        before=await h.observe("business_state")
        for changes in ({"id":None},{"id":str(uuid4()),"version":1.5}):
            probe=await h.command("constraint_probe",table="tickets",changes=changes)
            assert probe["rejected"] and probe["rolled_back"] and probe["foreign_keys"]==1
        allowed=await h.command("constraint_probe",table="tickets",changes={"id":str(uuid4()),"version":2})
        assert not allowed["rejected"] and allowed["rolled_back"]
        assert await h.observe("business_state")==before
        before=await h.observe("business_state")
        await h.set_fault("after_business_before_audit",True)
        r=await h.adapter.request("alice","PATCH",f"/api/tickets/{tid}",json=dict(expected_version=1,priority="high"))
        await h.set_fault("after_business_before_audit",False)
        assert r.status_code==500
        assert await h.observe("business_state")==before
        await h.arm_race("ticket_patch",2)
        a,b=await asyncio.gather(*(h.adapter.request("alice","PATCH",f"/api/tickets/{tid}",json=dict(expected_version=1,priority=p)) for p in ("high","low")))
        assert sorted((a.status_code,b.status_code))==[200,409]
        assert len(set(await h.observe("race_connections")))>=2
        pragmas=await h.observe("app_connection_pragmas")
        assert len(pragmas)>=2 and all(p["foreign_keys"]==1 for p in pragmas)
        assert await h.observe("db_busy_timeout_ms")==150
        before=await h.observe("business_state")
        lock=await h.hold_write_lock();assert lock["held"]
        try:
            r=await h.adapter.request("alice","PATCH",f"/api/tickets/{tid}",json=dict(expected_version=2,priority="normal"))
            assert r.status_code==503 and r.json()["error"]["code"]=="DB_BUSY"
        finally: await h.release_write_lock()
        assert await h.observe("business_state")==before
        assert (await h.observe("db_busy_waits"))[-1]["elapsed_seconds"]<1
        await h.advance_clock(28800)
        assert (await h.adapter.request("alice","GET","/api/auth/me",authenticate=False)).status_code==401
        with pytest.raises(AdapterUnavailable): await h.observe("cookie_modes")
        receipt=await h.verify_vertical(h.bindings.snapshot_hash,CONTRACT,browser_smoke=actual_browser_smoke)
        assert receipt["status"]=="NOT_VERIFIED" and not receipt["stages"]


@REAL
@pytest.mark.asyncio
async def test_architecture_arc03_uses_owned_live_lock_port_not_export(linux_fixture_source,tmp_path):
    from autospec.contracts import import_contract
    from autospec.validation.architecture_contracts import ArchitectureContractVerifier
    docs=Path(__file__).resolve().parents[2]/"docs/validation/support-client"
    contract=import_contract((docs/"01_specification.md").read_text(encoding="utf-8"),
        (docs/"02_requirements_verification.md").read_text(encoding="utf-8"),reviewed_by="independent native-port metatest")
    async with session(linux_fixture_source,tmp_path,instrumented=True) as h:
        verifier=ArchitectureContractVerifier(h.adapter,contract)
        # Exercise this source-fixed native probe without manufacturing a full
        # same-contract R proof or a 9-requirement compliance report.
        verifier._rid="ARC-03";verifier._observed={"ARC-03":[]};verifier._limits={"ARC-03":[]}
        await verifier._ARC03()
        rows={r["check"]:r for r in verifier._observed["ARC-03"]}
        assert set(rows)=={"distinct_connections","busy","rollback"}
        assert all(r["passed"] for r in rows.values()),rows
        assert rows["busy"]["observed"]["status"]==503
        with pytest.raises(AdapterUnavailable): verifier.connect()


@REAL
@pytest.mark.asyncio
async def test_rate_buckets_use_actual_linux_socket_ips_not_forwarded_header(linux_fixture_source,tmp_path):
    async with session(linux_fixture_source,tmp_path,instrumented=True) as h:
        await h.adapter.prepare_case("INSTRUMENTED")
        a=h.manifest.accounts["alice"]; statuses=[]
        for _ in range(10):
            response=await h.adapter.request(None,"POST",h.bindings.auth_path,
                json=dict(email=a.email,password="wrong"),ip="127.0.0.2")
            statuses.append(response.status_code)
        assert statuses==[401]*10
        body=dict(email=a.email,password=a.password)
        limited=await h.adapter.request(None,"POST",h.bindings.auth_path,json=body,ip="127.0.0.2",headers={"X-Forwarded-For":"127.0.0.9"})
        other=await h.adapter.request(None,"POST",h.bindings.auth_path,json=body,ip="127.0.0.3")
        assert limited.status_code==429 and other.status_code==200
        await h.advance_clock(59)
        assert (await h.adapter.request(None,"POST",h.bindings.auth_path,json=body,ip="127.0.0.2")).status_code==429
        await h.advance_clock(1)
        assert (await h.adapter.request(None,"POST",h.bindings.auth_path,json=body,ip="127.0.0.2")).status_code==200
        scope=await h.observe("ip_transport_scope")
        assert scope["actual_source_ips"]==["127.0.0.2","127.0.0.3"] and scope["limits"]
        assert "real-linux-kernel" in scope["alternate"]


@REAL
@pytest.mark.asyncio
@pytest.mark.parametrize("bug,stage",[("weak_hash","argon2"),("lost_commit","db_committed")])
async def test_real_linux_bad_fixture_cannot_pass_vertical(linux_fixture_source,tmp_path,bug,stage):
    definition=fixture_definition();definition["commands"]["seed"]["payload"]["bug"]=bug
    async with session(linux_fixture_source,tmp_path,definition=definition) as h:
        await h.adapter.prepare_case("VERTICAL")
        receipt=await h.verify_vertical(h.bindings.snapshot_hash,CONTRACT,browser_smoke=actual_browser_smoke)
        assert receipt["status"]!="PASS",receipt
        assert not next(s for s in receipt["stages"] if s["name"]==stage)["passed"]


@REAL
@pytest.mark.asyncio
async def test_real_linux_health_only_and_failed_provision_are_non_green(linux_fixture_source,tmp_path):
    async with session(linux_fixture_source,tmp_path) as h:
        await h.adapter.prepare_case("VERTICAL")
        receipt=await h.verify_vertical(h.bindings.snapshot_hash,CONTRACT)
        assert receipt["status"]=="NOT_VERIFIED"
        assert not next(s for s in receipt["stages"] if s["name"]=="browser_login")["passed"]
        # Unknown source command is not a fallback seed, even with old good DB.
        with pytest.raises(AdapterUnavailable): await h.command("unknown")
        assert (await h.command("reject"))["exit_code"]==9


@REAL
@pytest.mark.asyncio
@pytest.mark.parametrize("fault,changes",[("null_id",{"id":None}),("fractional_version",{"id":str(uuid4()),"version":1.5})])
async def test_real_live_constraint_bad_schema_not_hidden_by_export(linux_fixture_source,tmp_path,fault,changes):
    definition=fixture_definition();definition["commands"]["migrate_fresh"]={"fault":fault}
    async with session(linux_fixture_source,tmp_path,definition=definition) as h:
        await h.adapter.prepare_case("VERTICAL")
        before=await h.observe("business_state")
        result=await h.command("constraint_probe",table="tickets",changes=changes)
        assert result["rejected"] is False and result["rolled_back"] is True
        assert await h.observe("business_state")==before
