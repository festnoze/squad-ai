"""Independent delivery receipt predicates; protocol fixtures are not app PASS."""
import copy
import hashlib
import json
import os
import uuid
from pathlib import Path

import pytest

from autospec.validation.delivery_evidence import delivery_build_checks
from autospec.validation.final_gate import source_snapshot
from autospec.validation.support_adapter import AdapterUnavailable
from autospec.orchestrator.validation_environment import LinuxEnvironmentManager, RECIPE_VERSION
from autospec.orchestrator.isolated_validation import _node_command, build_delivery_image


def _export_native(case,value,*directories):
    """Optional test-proof export; never copy DB, passwords or fixture inputs."""
    destination=os.environ.get("AUTOSPEC_DELIVERY_EVIDENCE_ROOT")
    if not destination:return
    import shutil
    target=Path(destination).resolve()/case;target.mkdir(parents=True,exist_ok=True)
    (target/"result.json").write_bytes(json.dumps(value,sort_keys=True,ensure_ascii=True).encode())
    for directory in directories:
        for path in Path(directory).rglob("*.json"):
            relative=path.relative_to(directory)
            if relative.parts[0] not in {"delivery-evidence","native-observations"} and path.name not in {"delivery-build.json","observations.json"}:
                continue
            file=target/relative;file.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,file)


@pytest.fixture
def receipt_fixture(tmp_path):
    root = tmp_path / "source"; root.mkdir()
    (root / "pyproject.toml").write_text('[project]\nname="receipt-meta"\nversion="1"\ndependencies=[]\n')
    (root / "uv.lock").write_text('version=1\nrevision=3\n')
    (root / "main.py").write_text('# NEVER execute product code on host\n')
    front=root / "frontend"; front.mkdir()
    (front / "package.json").write_text('{"name":"receipt-meta-front"}')
    (front / "package-lock.json").write_text('{"lockfileVersion":3,"packages":{}}')
    (front / "tsconfig.json").write_text('{"compilerOptions":{"strict":true}}')
    snapshot=source_snapshot(root).digest
    images={}; commands=[]
    for kind, path, eco, mode, char in (("backend_install",root,"python","runtime","a"),("frontend_install",front,"node","test","b")):
        manifest=path / ("pyproject.toml" if eco=="python" else "package.json")
        lock=path / ("uv.lock" if eco=="python" else "package-lock.json")
        digest="factory/base@sha256:"+"e"*64
        sha=lambda data:hashlib.sha256(data).hexdigest()
        inputs=dict(version=RECIPE_VERSION,ecosystem=eco,mode=mode,manifest=sha(manifest.read_bytes()),lock=sha(lock.read_bytes()),
            toolchain_image="sha256:"+"c"*64,platform="linux/amd64",supervisor_reporter="native",toolchain_digest=digest,
            recipe_template_sha256=sha(LinuxEnvironmentManager._recipe(digest,eco,mode,"FINGERPRINT",manifest).encode()))
        fingerprint=sha(json.dumps(inputs,sort_keys=True).encode())
        recipe=LinuxEnvironmentManager._recipe(digest,eco,mode,fingerprint,manifest)
        image="sha256:"+char*64;attestation=dict(inputs=inputs,image=image,recipe_sha256=sha(recipe.encode()))
        builder=dict(inputs=inputs,fingerprint=fingerprint,attestation=attestation,image_id=image,status="cache_attested",rc=None,argv=None)
        import shlex
        install=next(line[4:] for line in recipe.splitlines() if line.startswith(("RUN uv sync ","RUN npm ci ")))
        commands.append(dict(kind=kind,argv=shlex.split(install),rc=None,execution="attested-cache",environment_fingerprint=fingerprint,
            image_id=image,attestation=attestation,builder=builder))
        images[image]=dict(Id=image,Config=dict(Labels={"autospec.environment":fingerprint}))
    commands.append(dict(kind="typecheck_frontend_build",components=["typecheck","frontend_build"],rc=0,isolated=True,
        image_id=commands[1]["image_id"],environment_fingerprint=commands[1]["environment_fingerprint"],
        argv=_node_command(["/bin/sh","-c","node /opt/node_modules/typescript/bin/tsc -b --pretty false && exec node /opt/node_modules/vite/bin/vite.js build"],dist=True)))
    image="sha256:"+"d"*64
    runtime=["/opt/venv/bin/python","main.py"]
    recipe=f'FROM autospec/clean-env:{commands[0]["environment_fingerprint"]}\nWORKDIR /app\nCOPY --chown=65532:65532 product/ /app/\nENV HOME=/tmp PYTHONDONTWRITEBYTECODE=1\nUSER 65532:65532\nENTRYPOINT []\nCMD {json.dumps(runtime)}\nLABEL autospec.snapshot={snapshot}\n'
    commands.append(dict(kind="image_build",rc=0,isolated=True,argv=["docker","build","--pull=false","--network=none","-t","meta/image","."],recipe_sha256=hashlib.sha256(recipe.encode()).hexdigest()))
    images[image]=dict(Id=image,Config=dict(Labels={"autospec.snapshot":snapshot},Cmd=runtime,Entrypoint=[]))
    receipt=dict(version=1,status="PASS",snapshot_hash=snapshot,image_id=image,image_tag="meta/image",isolated=True,
        runtime_command=runtime,runtime_command_mode="explicit-factory",
        no_host_dependencies=True,manifest_only_install=True,locks_sha256={"uv.lock":hashlib.sha256((root/"uv.lock").read_bytes()).hexdigest(),
        "frontend/package-lock.json":hashlib.sha256((front/"package-lock.json").read_bytes()).hexdigest()},commands=commands,
        frontend_files={"frontend/dist/index.html":"f"*64})
    return root,snapshot,receipt,images


def test_attested_cache_does_not_need_or_manufacture_install_rc0(receipt_fixture):
    root,snapshot,receipt,images=receipt_fixture
    before=copy.deepcopy(receipt)
    rows=delivery_build_checks(receipt,root,snapshot,image_lookup=images.__getitem__)
    assert rows and all(row["passed"] for row in rows)
    assert receipt==before and all(c["rc"] is None for c in receipt["commands"][:2])


def test_native_layer_builder_is_observed_not_install_exit_code(receipt_fixture):
    root,snapshot,receipt,images=receipt_fixture
    command=receipt["commands"][0];fingerprint=command["environment_fingerprint"]
    command["execution"]="attested-layer"
    command["builder"].update(status="build_attested",rc=0,recipe_sha256=command["attestation"]["recipe_sha256"],
        argv=["docker","build","--pull=false","--network=default","--label","autospec.environment="+fingerprint,"-t","autospec/clean-env:"+fingerprint,"."])
    assert all(r["passed"] for r in delivery_build_checks(receipt,root,snapshot,image_lookup=images.__getitem__))
    assert command["rc"] is None
    command["builder"]["rc"]=1
    assert not all(r["passed"] for r in delivery_build_checks(receipt,root,snapshot,image_lookup=images.__getitem__))


@pytest.mark.parametrize("fault",["missing_command","legacy_default","shell","different_cmd","inherited_entrypoint","recipe_legacy_cmd"])
def test_baked_runtime_identity_not_an_overridden_or_legacy_launcher(receipt_fixture,fault):
    root,snapshot,receipt,images=receipt_fixture
    if fault=="missing_command":receipt.pop("runtime_command")
    elif fault=="legacy_default":receipt["runtime_command_mode"]="legacy-default"
    elif fault=="shell":receipt["runtime_command"]=["/bin/sh","-c","python main.py"]
    elif fault=="different_cmd":images[receipt["image_id"]]["Config"]["Cmd"]=["/opt/venv/bin/python","another.py"]
    elif fault=="inherited_entrypoint":images[receipt["image_id"]]["Config"]["Entrypoint"]=["docker-entrypoint.sh"]
    elif fault=="recipe_legacy_cmd":
        receipt["commands"][-1]["recipe_sha256"]=hashlib.sha256(b"old factory recipe with fixed CMD").hexdigest()
    try:rows=delivery_build_checks(receipt,root,snapshot,image_lookup=images.__getitem__)
    except AdapterUnavailable:return
    assert any(row["passed"] is False for row in rows)


def test_docker_omitted_empty_entrypoint_is_absence_not_inherited_script(receipt_fixture):
    root,snapshot,receipt,images=receipt_fixture
    images[receipt["image_id"]]["Config"].pop("Entrypoint")
    assert all(row["passed"] for row in delivery_build_checks(receipt,root,snapshot,image_lookup=images.__getitem__))


@pytest.mark.parametrize("fault",["fictional_install_rc","missing_inputs","wrong_lock","wrong_manifest","wrong_recipe","duplicate","missing_typecheck","failed_tsc","wrong_image","wrong_snapshot_label","drift_source"])
def test_faulty_receipt_never_admitted(receipt_fixture,fault):
    root,snapshot,receipt,images=receipt_fixture
    command=receipt["commands"][0]
    if fault=="fictional_install_rc":command["rc"]=0
    elif fault=="missing_inputs":command["attestation"]["inputs"].pop("platform")
    elif fault=="wrong_lock":receipt["locks_sha256"]["uv.lock"]="0"*64
    elif fault=="wrong_manifest":command["attestation"]["inputs"]["manifest"]="0"*64
    elif fault=="wrong_recipe":command["attestation"]["recipe_sha256"]="0"*64
    elif fault=="duplicate":receipt["commands"].append(copy.deepcopy(command))
    elif fault=="missing_typecheck":receipt["commands"][2]["kind"]="frontend_build"
    elif fault=="failed_tsc":receipt["commands"][2]["rc"]=2
    elif fault=="wrong_image":images[command["image_id"]]["Id"]="sha256:"+"0"*64
    elif fault=="wrong_snapshot_label":images[receipt["image_id"]]["Config"]["Labels"]["autospec.snapshot"]="0"*64
    elif fault=="drift_source":(root/"main.py").write_bytes(b"# changed after build")
    try: rows=delivery_build_checks(receipt,root,snapshot,image_lookup=images.__getitem__)
    except AdapterUnavailable: return
    assert any(r["passed"] is False for r in rows),fault


def test_failed_build_without_image_is_failure_not_missing_capability(receipt_fixture):
    root,snapshot,receipt,images=receipt_fixture
    receipt.update(status="FAIL",image_id=None,commands=[],frontend_files={})
    assert delivery_build_checks(receipt,root,snapshot,image_lookup=images.__getitem__)==[
        dict(check="native_build_status",passed=False,observed=dict(status="FAIL",error=None))]


@pytest.mark.skipif(os.environ.get("AUTOSPEC_REAL_LINUX_VALIDATION")!="1",reason="Explicit opt-in native locked Linux install/tsc/Vite/image/cache validation")
def test_real_build_and_current_image_attestations_admitted(tmp_path):
    from tests.test_delivery_build_receipts import _source
    from autospec.orchestrator.sandbox import _docker_call
    root=tmp_path/"source";_source(root,True)
    (root/"uv.lock").unlink();(root/"frontend/package-lock.json").unlink()
    manager=LinuxEnvironmentManager(tmp_path/"locks",timeout=600)
    manager.ensure_lock(root,"python");manager.ensure_lock(root/"frontend","node")
    snapshot=source_snapshot(root).digest
    tag="autospec/delivery-check:"+uuid.uuid4().hex
    try:
        ok,output=build_delivery_image(root,tag,evidence_root=tmp_path/"evidence",snapshot_hash=snapshot,timeout=600,
            runtime_command=["/opt/venv/bin/python","main.py"])
        assert ok,output
        receipt=json.loads((tmp_path/"evidence/delivery-build.json").read_text())
        rows=delivery_build_checks(receipt,root,snapshot)
        assert all(r["passed"] for r in rows),rows
        _export_native("build",dict(snapshot_hash=snapshot,contract_hash="c"*64,receipt=receipt,verification=rows,
            scope="actual tsc/Vite/baked image/cache metatest; not support-client acceptance"),tmp_path/"evidence")
        assert not (root/".venv").exists() and not (root/"frontend/node_modules").exists()
    finally:
        _docker_call(["docker","image","rm",tag],capture_output=True,text=True,timeout=10)


@pytest.mark.parametrize("fault",[None,"missing_dependency","skipped_dependency","status_contradiction","error","invalid_json"])
def test_raw_pip_audit_parser_requires_exact_complete_lock_inventory(fault):
    from autospec.validation.delivery_evidence import _audit_findings
    report=dict(dependencies=[dict(name="idna",version="3.10",vulns=[])])
    run=dict(return_code=0,stdout=json.dumps(report))
    if fault=="missing_dependency":run["stdout"]='{"dependencies":[]}'
    elif fault=="skipped_dependency":report["dependencies"][0]["skip_reason"]="not on platform";run["stdout"]=json.dumps(report)
    elif fault=="status_contradiction":run["return_code"]=1
    elif fault=="error":run["return_code"]=2
    elif fault=="invalid_json":run["stdout"]="network unavailable"
    if fault is None: assert _audit_findings("python",run,[("idna","3.10")])==[]
    else:
        with pytest.raises((AdapterUnavailable,ValueError)): _audit_findings("python",run,[("idna","3.10")])


def test_advisory_is_not_inferred_to_be_exploitable_without_exact_review(tmp_path):
    from autospec.validation.delivery_evidence import apply_audit_review,audit_review_subject
    from autospec.validation.support_adapter import Proof
    from dataclasses import asdict,replace
    snapshot,contract="a"*64,"c"*64
    raw=dict(status="AVAILABLE",findings=[dict(scope="frontend",package="dev-tool",id="npm:123",severity="high",exploitable=None,arbitration=None)],artifacts=[])
    path=tmp_path/"independent-audit-review.json"
    assessment=dict(scope="frontend",package="dev-tool",id="npm:123",severity="high",exploitable=False,arbitration=None,rationale="Independent fixture review: build-only package, no delivered runtime route imports it.")
    path.write_text(json.dumps(dict(assessments=[assessment])))
    proof=Proof("R",str(path),hashlib.sha256(path.read_bytes()).hexdigest(),snapshot,contract,("OPS-05:audit:"+audit_review_subject(raw),))
    reviewed=apply_audit_review(raw,proof,evidence_root=tmp_path,snapshot_hash=snapshot,contract_hash=contract)
    assert reviewed["findings"][0]["exploitable"] is False
    assert raw["findings"][0]["exploitable"] is None
    for bad in (replace(proof,passed=False),replace(proof,checks=("OPS-05:audit",)),replace(proof,snapshot_hash="f"*64)):
        with pytest.raises(AdapterUnavailable):apply_audit_review(raw,bad,evidence_root=tmp_path,snapshot_hash=snapshot,contract_hash=contract)
    path.write_text('{"assessments":[]}')
    with pytest.raises(AdapterUnavailable):apply_audit_review(raw,proof,evidence_root=tmp_path,snapshot_hash=snapshot,contract_hash=contract)


def _audit_disposition_fixture(tmp_path,arbitration,*,approval_fault=None):
    """Synthetic parser receipts only: no real auditor or human waiver issued."""
    from dataclasses import asdict
    from autospec.validation.delivery_evidence import apply_audit_review,audit_review_subject,audit_risk_subject
    from autospec.validation.support_adapter import Proof
    snapshot,contract="a"*64,"c"*64
    raw=dict(status="AVAILABLE",findings=[dict(scope="backend",package="fixture-risk",id="TEST:high",version="1",
        severity="unknown",exploitable=None,arbitration=None)],artifacts=[],scope="synthetic offline protocol only")
    if approval_fault is not None:
        subject=audit_risk_subject(raw["findings"][0],snapshot,contract)
        payload=dict(version=1,kind="audit_risk_acceptance",authority="human",subject=subject,snapshot_hash=snapshot,
            contract_hash=contract,approved=True,authorized_by="Synthetic protocol actor; not a real human waiver",
            rationale="Synthetic format acceptance only, never a production risk decision",date="2026-10-12T12:00:00Z")
        if approval_fault=="machine_authority":payload["authority"]="gpt_source_reviewer"
        elif approval_fault=="human_denied":payload["approved"]=False
        elif approval_fault=="different_advisory":payload["subject"]="f"*64
        elif approval_fault=="different_snapshot":payload["snapshot_hash"]="f"*64
        elif approval_fault=="different_contract":payload["contract_hash"]="f"*64
        elif approval_fault=="missing_date":payload.pop("date")
        path=tmp_path/"synthetic-risk-approval.json";path.write_text(json.dumps(payload))
        proof=Proof("R",str(path),hashlib.sha256(path.read_bytes()).hexdigest(),snapshot,contract,
            ("OPS-05:accepted_risk:"+subject,),True,"Synthetic fixture only; NOT real human approval")
        if approval_fault=="unscoped":proof=Proof(**{**asdict(proof),"checks":("OPS-05:audit",)})
        elif approval_fault=="checks_string":proof=Proof(**{**asdict(proof),"checks":"OPS-05:accepted_risk:"+subject})
        elif approval_fault=="false_proof":proof=Proof(**{**asdict(proof),"passed":False})
        elif approval_fault=="tampered_bytes":path.write_text("{}")
        arbitration["approval"]=asdict(proof)
    assessment=dict(scope="backend",package="fixture-risk",id="TEST:high",severity="high",exploitable=True,
        arbitration=arbitration,rationale="Synthetic high/reachable protocol assertion, not product evidence")
    path=tmp_path/"synthetic-assessment.json";path.write_text(json.dumps(dict(assessments=[assessment])))
    proof=Proof("R",str(path),hashlib.sha256(path.read_bytes()).hexdigest(),snapshot,contract,("OPS-05:audit:"+audit_review_subject(raw),),
        True,"Synthetic fixture only; not benchmark review")
    return apply_audit_review(raw,proof,evidence_root=tmp_path,snapshot_hash=snapshot,contract_hash=contract)


@pytest.mark.parametrize("case",["no_arbitration","rejected","pending","deny_release","fix_required","contradictory_accepted","approval_false"])
def test_known_high_audit_refusal_or_pending_is_not_shipping_permission(tmp_path,case):
    from autospec.validation.delivery_evidence import audit_disposition_checks
    arbitration=None if case=="no_arbitration" else dict(decision="audit_disposition",owner="synthetic protocol actor",
        rationale="Synthetic metatest only",date="2026-10-12T12:00:00Z",disposition="rejected",approved=False)
    if case=="pending":arbitration["disposition"]="pending"
    elif case in {"deny_release","fix_required"}:arbitration["decision"]=case
    elif case=="contradictory_accepted":arbitration.update(disposition="accepted_risk",approved=True,decision="deny_release")
    elif case=="approval_false":arbitration.update(disposition="accepted_risk",approved=False)
    audit=_audit_disposition_fixture(tmp_path,arbitration)
    checks=audit_disposition_checks(audit,evidence_root=tmp_path,snapshot_hash="a"*64,contract_hash="c"*64)
    assert len(checks)==1 and checks[0]["passed"] is False
    assert len(checks[0]["observed"]["blocking"])==1


@pytest.mark.parametrize("fault",["unknown","missing_disposition","nonbool","missing_approval_bool","accepted_without_proof"])
def test_unknown_or_unsigned_audit_permission_cannot_pass(tmp_path,fault):
    arbitration=dict(decision="audit_disposition",owner="synthetic protocol actor",rationale="Synthetic metatest only",
        date="2026-10-12T12:00:00Z",disposition="accepted_risk",approved=True)
    if fault=="unknown":arbitration["disposition"]="we_will_fix_later"
    elif fault=="missing_disposition":arbitration.pop("disposition")
    elif fault=="nonbool":arbitration["approved"]="true"
    elif fault=="missing_approval_bool":arbitration.pop("approved")
    with pytest.raises(AdapterUnavailable):_audit_disposition_fixture(tmp_path,arbitration)


@pytest.mark.parametrize("fault",["nominal","machine_authority","human_denied","different_advisory","different_snapshot","different_contract","missing_date","unscoped","checks_string","false_proof","tampered_bytes"])
def test_accepted_risk_needs_exact_existing_human_scope_R_not_classifier_bool(tmp_path,fault):
    from autospec.validation.delivery_evidence import audit_disposition_checks
    arbitration=dict(decision="accepted_by_existing_external_authority",owner="synthetic protocol actor",rationale="Synthetic metatest only",
        date="2026-10-12T12:00:00Z",disposition="accepted_risk",approved=True)
    if fault=="nominal":
        audit=_audit_disposition_fixture(tmp_path,arbitration,approval_fault=fault)
        assert audit_disposition_checks(audit,evidence_root=tmp_path,snapshot_hash="a"*64,contract_hash="c"*64)[0]["passed"] is True
        # Retained waiver bytes are rechecked, not trusted from a cached bool.
        Path(arbitration["approval"]["path"]).write_text("{}")
        with pytest.raises(AdapterUnavailable):audit_disposition_checks(audit,evidence_root=tmp_path,snapshot_hash="a"*64,contract_hash="c"*64)
    else:
        with pytest.raises(AdapterUnavailable):_audit_disposition_fixture(tmp_path,arbitration,approval_fault=fault)


def _delivery_plan(source,root,snapshot,fixture_fingerprint,*,negative=False):
    from autospec.validation.delivery_evidence import ReviewedDeliveryPlan
    from autospec.validation.support_adapter import Proof
    readme=source/"README.md";config=source/"config.py"
    commands=[dict(label="migration",obligation="migration",execution="runtime",documented_text="/opt/venv/bin/python main.py migrate_fresh",
        argv=["/opt/venv/bin/python","main.py","migrate_fresh"],action="migrate_fresh",parameters={})]
    if negative:commands.append(dict(label="negative",obligation="negative",execution="runtime",documented_text="/opt/venv/bin/python main.py reject",
        argv=["/opt/venv/bin/python","main.py","reject"],action="reject",parameters={}))
    data=dict(version=1,snapshot_hash=snapshot,contract_hash="c"*64,
        readme=dict(path="README.md",sha256=hashlib.sha256(readme.read_bytes()).hexdigest()),
        configuration=[dict(path="config.py",sha256=hashlib.sha256(config.read_bytes()).hexdigest())],commands=commands,
        migration_label="migration",fixture_case="VERTICAL",fixtures_fingerprint=fixture_fingerprint)
    review_path=root/"delivery-review.json";review_path.parent.mkdir(parents=True,exist_ok=True)
    review_path.write_text(json.dumps(dict(scope="Independent delivery fixture review only; not benchmark acceptance",
        configuration_assessments={"config.py":dict(source_sha256=data["configuration"][0]["sha256"],secrets_found=[])})))
    proof=Proof("R",str(review_path),hashlib.sha256(review_path.read_bytes()).hexdigest(),snapshot,"c"*64,())
    plan=ReviewedDeliveryPlan(data,proof)
    from dataclasses import replace
    return replace(plan,review=replace(proof,checks=("PRODUCT:delivery:"+plan.fingerprint,"OPS-05:README","OPS-05:config")))


def test_delivery_plan_pins_real_readme_commands_and_config_review(tmp_path):
    import shutil
    from pathlib import Path
    source=tmp_path/"source";source.mkdir();root=tmp_path/"supervisor"
    for path in (Path(__file__).parent/"fixtures/delivery").iterdir():shutil.copyfile(path,source/path.name)
    snapshot=source_snapshot(source).digest
    plan=_delivery_plan(source,root,snapshot,"e"*64)
    with pytest.raises(AdapterUnavailable,match="obligations absent"):plan.validate(source,root,snapshot,"c"*64)
    plan.validate(source,root,snapshot,"c"*64,required_obligations={"migration"})
    assert "PASS" not in plan.data.values()
    plan.data["commands"][0]["argv"]=["python","evil.py"]
    with pytest.raises(AdapterUnavailable):plan.validate(source,root,snapshot,"c"*64)


@pytest.mark.asyncio
async def test_timing_requires_native_artifacts_and_all_phases(tmp_path):
    from autospec.validation.delivery_evidence import NativeTimingRecorder,_native_proof
    timer=NativeTimingRecorder(evidence_root=tmp_path,snapshot_hash="a"*64,contract_hash="c"*64)
    async def operation():return {"actual":"protocol measurement, not a product execution"}
    with pytest.raises(AdapterUnavailable): await timer.measure("tests",operation,lambda result:[])
    proof=_native_proof(tmp_path,"measured-protocol",dict(protocol_only=True),"a"*64,"c"*64,checks=("METATEST:timing",))
    assert await timer.measure("tests",operation,lambda result:[proof])==await operation()
    assert timer.phases[0][0]["seconds"]>=0
    with pytest.raises(AdapterUnavailable):await timer.publish()


def test_native_split_clock_ingest_does_not_invent_or_double_count_install(tmp_path):
    from autospec.validation.delivery_evidence import NativeTimingRecorder,_native_proof
    timer=NativeTimingRecorder(evidence_root=tmp_path,snapshot_hash="a"*64,contract_hash="c"*64)
    install=dict(phase="install",seconds=2.0,started_at="2026-10-12T10:00:00Z",ended_at="2026-10-12T10:00:02Z")
    tests=dict(phase="tests",seconds=1.0,started_at="2026-10-12T10:00:02Z",ended_at="2026-10-12T10:00:03Z")
    receipt=dict(argv=["protocol-fixture"],return_code=0,image_id="sha256:"+"b"*64,environment_fingerprint="d"*64,
        timing=tests,environment_preparation=install)
    proof=_native_proof(tmp_path,"split-clocks",receipt,"a"*64,"c"*64,checks=("METATEST:split_clock",))
    timer.ingest("install",install,proof);timer.ingest("tests",tests,proof)
    assert [(row["phase"],row["seconds"]) for row,_ in timer.phases]==[("install",2.0),("tests",1.0)]
    with pytest.raises(AdapterUnavailable):timer.ingest("tests",dict(tests,seconds=3.0),proof)
    with pytest.raises(AdapterUnavailable):timer.ingest("install",tests,proof)


@pytest.mark.skipif(os.environ.get("AUTOSPEC_REAL_LINUX_VALIDATION")!="1",reason="Explicit opt-in real advisory networking, locked public package facts only")
@pytest.mark.asyncio
async def test_real_manifest_only_python_audit_never_imports_product(tmp_path,monkeypatch):
    from autospec.validation.delivery_evidence import collect_manifest_audit
    source=tmp_path/"source";source.mkdir()
    (source/"pyproject.toml").write_text('[project]\nname="audit-native-fixture"\nversion="1"\nrequires-python=">=3.12"\ndependencies=["idna==3.10"]\n')
    (source/"main.py").write_bytes(b'raise RuntimeError("MUST NEVER execute while audit has network")')
    (source/"socket.py").write_bytes(b'raise RuntimeError("must never shadow audit stdlib")')
    monkeypatch.setenv("AUTOSPEC_SENTINEL_SECRET","must-not-enter-advisory-query")
    manager=LinuxEnvironmentManager(tmp_path/"cache",timeout=600);manager.ensure_lock(source,"python")
    snapshot=source_snapshot(source).digest
    raw=await collect_manifest_audit(source,snapshot,"c"*64,tmp_path/"evidence",timeout=600)
    assert raw["status"]=="AVAILABLE" and raw["report_valid"],raw
    assert raw["reports"] and raw["artifacts"]
    for proof in raw["artifacts"]:
        path=__import__("pathlib").Path(proof["path"])
        assert hashlib.sha256(path.read_bytes()).hexdigest()==proof["sha256"]
        assert b"must-not-enter-advisory-query" not in path.read_bytes()
        observed=json.loads(path.read_bytes())["value"]
        assert set(observed["context_files"])=={"requirements.txt","runner.py","Dockerfile"}
        assert observed["run"]["tool"]=="pip-audit==2.10.1"
    assert source_snapshot(source).digest==snapshot
    _export_native("python-audit",dict(snapshot_hash=snapshot,contract_hash="c"*64,audit=raw,scope="actual public lock advisory query, not source exploitability review"),tmp_path/"evidence")


@pytest.mark.skipif(os.environ.get("AUTOSPEC_REAL_LINUX_VALIDATION")!="1",reason="Explicit opt-in actual npm public lock audit, no application source networking")
@pytest.mark.asyncio
@pytest.mark.parametrize("vulnerable",[False,True])
async def test_real_node_manifest_audit_good_and_known_vulnerable_lock(tmp_path,vulnerable):
    from autospec.validation.delivery_evidence import collect_manifest_audit
    source=tmp_path/"source";source.mkdir()
    (source/"package.json").write_text(json.dumps(dict(name="native-audit-fixture",version="1",dependencies={"lodash":"4.17.11"} if vulnerable else {})))
    (source/"main.js").write_bytes(b'throw Error("MUST NOT execute application in advisory networking phase");')
    manager=LinuxEnvironmentManager(tmp_path/"cache",timeout=600);manager.ensure_lock(source,"node")
    snapshot=source_snapshot(source).digest
    raw=await collect_manifest_audit(source,snapshot,"c"*64,tmp_path/"evidence",timeout=600)
    assert raw["status"]=="AVAILABLE" and raw["report_valid"],raw
    assert bool(raw["findings"]) is vulnerable
    assert raw["return_code"]==(1 if vulnerable else 0)
    assert all(f["exploitable"] is None for f in raw["findings"])
    for proof in raw["artifacts"]:
        value=json.loads(Path(proof["path"]).read_bytes())["value"]
        assert set(value["context_files"])=={"package.json","package-lock.json","runner.cjs","Dockerfile"}
        assert value["run"]["argv"][:2]==["npm","audit"]
    _export_native("node-audit-bad" if vulnerable else "node-audit-good",dict(snapshot_hash=snapshot,contract_hash="c"*64,audit=raw),tmp_path/"evidence")


@pytest.mark.skipif(os.environ.get("AUTOSPEC_REAL_PRODUCT_HARNESS")!="1",reason="Explicit opt-in real Linux README CLI+SQLite fixture and negative rc")
@pytest.mark.asyncio
@pytest.mark.parametrize("negative",[False,True])
async def test_real_readme_collects_isolated_cli_defaults_and_negative_rc(tmp_path,negative):
    # Deliberately narrow fixture obligations. Production default additionally
    # requires install/coverage/E2E/backup/restore and cannot award OPS05 from
    # this four-command fixture. All executed source is inside Linux NETNONE.
    import shutil
    from pathlib import Path
    from autospec.validation.delivery_evidence import NativeDeliveryCollector,ReviewedDeliveryPlan
    from autospec.validation.support_adapter import Proof
    from tests.test_product_harness import ROOT,session
    from dataclasses import replace
    source=tmp_path/"source";source.mkdir();root=tmp_path/"supervisor";root.mkdir()
    for path in ROOT.iterdir():
        if path.is_file():shutil.copyfile(path,source/path.name)
    for path in (Path(__file__).parent/"fixtures/delivery").iterdir():shutil.copyfile(path,source/path.name)
    manifest=source/"pyproject.toml"
    manifest.write_text(manifest.read_text()+'\n[project.optional-dependencies]\ndev=["pytest==8.4.2"]\n')
    (source/"test_readme.py").write_text('import sqlite3\ndef test_actual_sqlite_file(tmp_path):\n p=tmp_path/"actual.sqlite"\n c=sqlite3.connect(p)\n c.execute("CREATE TABLE check_table(id INTEGER PRIMARY KEY)")\n c.execute("INSERT INTO check_table VALUES(1)")\n c.commit()\n c.close()\n with sqlite3.connect(p) as d: assert d.execute("SELECT count(*) FROM check_table").fetchone()[0]==1\n')
    readme=source/"README.md";readme.write_text(readme.read_text()+"\nReal isolated CLI: pytest -q\nLauncher: /opt/venv/bin/python main.py\nExplicit seed: /opt/venv/bin/python main.py seed\n")
    manager=LinuxEnvironmentManager(root/"cache",timeout=600);manager.regenerate_lock(source,"python")
    snapshot=source_snapshot(source).digest
    context=session((root,source,snapshot),root)
    binding=replace(context.bindings,fixture_fingerprint=context.factory.fingerprint)
    context.bindings=replace(binding,review=replace(binding.review,checks=("PRODUCT:bindings","PRODUCT:bindings:"+binding.fingerprint())))
    plan=_delivery_plan(source,root,snapshot,context.bindings.fixture_fingerprint,negative=negative)
    plan.data["commands"].extend([
        dict(label="tests",obligation="tests",execution="isolated_command",documented_text="pytest -q",argv=["pytest","-q"],root=".",ecosystem="python"),
        dict(label="launch",obligation="launch",execution="runtime_launch",documented_text="/opt/venv/bin/python main.py",argv=["/opt/venv/bin/python","main.py"]),
        dict(label="seed",obligation="seed",execution="fixture_provisioning",action="seed",documented_text="/opt/venv/bin/python main.py seed",argv=["/opt/venv/bin/python","main.py","seed"])])
    plan=replace(plan,review=replace(plan.review,checks=("PRODUCT:delivery:"+plan.fingerprint,"OPS-05:README","OPS-05:config")))
    collector=NativeDeliveryCollector(plan,source_root=source,evidence_root=root,snapshot_hash=snapshot,contract_hash="c"*64,
        required_obligations={"migration","tests","launch","seed"})
    audit=dict(status="UNAVAILABLE",date="2026-10-12T00:00:00Z",tool="not run in this README fixture",report_valid=False,return_code=None,findings=[],artifacts=[])
    async with context as harness:
        value=await collector.collect(harness,audit=audit)
    assert value["accounts_before_fixture"]==0 and value["fixtures_explicit"] is True
    tests=next(c for c in value["documented_commands"] if c["label"]=="tests")
    assert tests["argv"]==["pytest","-q"] and tests["return_code"]==0 and tests["isolated"] is True and tests["mode"]=="test"
    assert any(c.get("return_code")==9 for c in value["documented_commands"]) is negative
    # Unavailable audit remains unavailable despite real README success.
    assert value["audit"]["status"]=="UNAVAILABLE"
    _export_native("readme-bad" if negative else "readme-good",dict(snapshot_hash=snapshot,contract_hash="c"*64,docs_audit=value,
        scope="narrow real README commands, not complete production OPS-05"),root)
