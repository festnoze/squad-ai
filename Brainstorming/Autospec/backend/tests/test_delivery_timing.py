"""Exact delivery-clock ingestion; offline receipts never prove a product run."""
import copy
import json
import os
import uuid
from collections import defaultdict
from pathlib import Path

import pytest

from autospec.validation import delivery_evidence as module
from autospec.validation.support_adapter import AdapterUnavailable
from tests.test_delivery_evidence import receipt_fixture, _export_native


def clock(phase,seconds,start):
    return dict(phase=phase,seconds=float(seconds),started_at=f"2026-10-12T10:00:{start:02d}Z",
        ended_at=f"2026-10-12T10:00:{start+seconds:02d}Z",scope="Synthetic metatest clock, not product evidence")


@pytest.fixture
def timed_receipt(receipt_fixture,monkeypatch,tmp_path):
    source,snapshot,receipt,images=receipt_fixture
    commands={c["kind"]:c for c in receipt["commands"]}
    commands["backend_install"]["builder"]["timing"]=clock("install",2,0)
    commands["frontend_install"]["builder"]["timing"]=clock("install",3,2)
    commands["typecheck_frontend_build"]["timing"]=clock("build",5,5)
    commands["image_build"]["timing"]=clock("docker",13,10)
    receipt["backend_dependency"]=copy.deepcopy(commands["backend_install"]["builder"])
    receipt["frontend_build"]=dict(copy.deepcopy(commands["typecheck_frontend_build"]),
        dependency=copy.deepcopy(commands["frontend_install"]["builder"]))
    original=module.delivery_build_checks
    monkeypatch.setattr(module,"delivery_build_checks",lambda receipt,source,snapshot:original(receipt,source,snapshot,image_lookup=images.__getitem__))
    root=tmp_path/"supervisor"
    timer=module.NativeTimingRecorder(evidence_root=root,snapshot_hash=snapshot,contract_hash="c"*64)
    return source,snapshot,receipt,images,timer,root


def proof_for(receipt,snapshot,root):
    return module._native_proof(root,"delivery-clock-metatest",receipt,snapshot,"c"*64,checks=("OBS:delivery_build",))


def test_exact_four_delivery_subclocks_not_enclosing_or_duplicated(timed_receipt):
    source,snapshot,receipt,_,timer,root=timed_receipt
    proof=proof_for(receipt,snapshot,root)
    result=timer.ingest_delivery(receipt,proof,source_root=source)
    assert len(result)==4
    assert [(r["phase"],r["seconds"]) for r,_ in timer.phases]==[("install",2),("install",3),("build",5),("docker",13)]
    assert all(r["return_code"] is None for r,_ in timer.phases if r["phase"]=="install")
    assert len({r["native_clock_path"] for r,_ in timer.phases})==4
    with pytest.raises(AdapterUnavailable,match="already ingested"):
        timer.ingest_delivery(receipt,proof,source_root=source)
    # A second wrapper file around identical raw bytes cannot double the sum.
    with pytest.raises(AdapterUnavailable,match="already ingested"):
        timer.ingest_delivery(receipt,proof_for(receipt,snapshot,root),source_root=source)
    assert len(timer.phases)==4


@pytest.mark.parametrize("fault",["phase","negative","nan","boolean","timezone","reverse","missing","raw_drift","source_drift","image_drift","duplicate_clock_copy","failed_build"])
def test_bad_delivery_clock_never_publishes_partial_phases(timed_receipt,fault):
    source,snapshot,receipt,images,timer,root=timed_receipt
    commands={c["kind"]:c for c in receipt["commands"]}
    last=commands["image_build"]["timing"]
    if fault=="phase":last["phase"]="build"
    elif fault=="negative":last["seconds"]=-1
    elif fault=="nan":last["seconds"]=float("nan")
    elif fault=="boolean":last["seconds"]=True
    elif fault=="timezone":last["ended_at"]="2026-10-12T10:00:23"
    elif fault=="reverse":last["ended_at"]="2026-10-12T09:00:00Z"
    elif fault=="missing":commands["image_build"].pop("timing")
    elif fault=="source_drift":(source/"main.py").write_text("# different source\n")
    elif fault=="image_drift":images[receipt["image_id"]]["Config"]["Labels"]["autospec.snapshot"]="f"*64
    elif fault=="duplicate_clock_copy":receipt["frontend_build"]["timing"]["seconds"]=99
    elif fault=="failed_build":receipt["status"]="FAIL"
    proof=proof_for(receipt,snapshot,root)
    if fault=="raw_drift":last["seconds"]=17
    with pytest.raises(AdapterUnavailable):timer.ingest_delivery(receipt,proof,source_root=source)
    assert timer.phases==[]


def test_layer_preparation_clock_keeps_install_rc_unknown(timed_receipt):
    source,snapshot,receipt,_,timer,root=timed_receipt
    command=receipt["commands"][0];fingerprint=command["environment_fingerprint"]
    command["execution"]="attested-layer"
    command["builder"].update(status="build_attested",rc=0,recipe_sha256=command["attestation"]["recipe_sha256"],
        argv=["docker","build","--pull=false","--network=default","--label","autospec.environment="+fingerprint,"-t","autospec/clean-env:"+fingerprint,"."])
    receipt["backend_dependency"]=copy.deepcopy(command["builder"])
    timer.ingest_delivery(receipt,proof_for(receipt,snapshot,root),source_root=source)
    row=timer.phases[0][0]
    assert row["execution"]=="attested-layer" and row["return_code"] is None
    assert row["seconds"]==2


@pytest.mark.asyncio
async def test_five_phases_publication_uses_split_tests_and_browser_only(timed_receipt,monkeypatch):
    from types import SimpleNamespace
    from autospec.orchestrator import sandbox
    source,snapshot,receipt,_,timer,root=timed_receipt
    timer.ingest_delivery(receipt,proof_for(receipt,snapshot,root),source_root=source)
    tests=clock("tests",11,23)
    execution=dict(argv=["metatest"],return_code=0,image_id="sha256:"+"a"*64,environment_fingerprint="d"*64,timing=tests)
    timer.ingest("tests",tests,proof_for(execution,snapshot,root))
    with pytest.raises(AdapterUnavailable,match="already ingested"):
        timer.ingest("tests",tests,proof_for(execution,snapshot,root))
    browser_proof=proof_for(dict(scope="Synthetic Playwright measurement only"),snapshot,root)
    timer._record("browser","2026-10-12T10:00:34Z",7,[browser_proof])
    monkeypatch.setattr(sandbox,"_docker_call",lambda *a,**k:SimpleNamespace(returncode=0,stdout=json.dumps(dict(Version="offline",Os="linux",Arch="amd64"))))
    value=await timer.publish()
    assert value["seconds"]==dict(install=5,tests=11,browser=7,build=5,docker=13)


@pytest.mark.skipif(os.environ.get("AUTOSPEC_REAL_LINUX_VALIDATION")!="1",reason="Explicit opt-in real native Docker/tsc/Vite split clocks")
def test_real_delivery_receipt_four_clocks_admitted_and_retained(tmp_path):
    from autospec.orchestrator.isolated_validation import build_delivery_image
    from autospec.orchestrator.validation_environment import LinuxEnvironmentManager
    from autospec.orchestrator.sandbox import _docker_call
    from autospec.validation.final_gate import source_snapshot
    from tests.test_delivery_build_receipts import _source
    source=tmp_path/"source";_source(source,True)
    for lock in (source/"uv.lock",source/"frontend/package-lock.json"):
        if lock.exists():lock.unlink()
    manager=LinuxEnvironmentManager(tmp_path/"cache",timeout=600)
    manager.ensure_lock(source,"python");manager.ensure_lock(source/"frontend","node")
    snapshot=source_snapshot(source).digest;root=tmp_path/"supervisor";tag="autospec/delivery-clocks:"+uuid.uuid4().hex
    try:
        ok,out=build_delivery_image(source,tag,evidence_root=root,snapshot_hash=snapshot,timeout=600)
        assert ok,out
        receipt=json.loads((root/"delivery-build.json").read_bytes())
        timer=module.NativeTimingRecorder(evidence_root=root,snapshot_hash=snapshot,contract_hash="c"*64)
        proofs=timer.ingest_delivery(receipt,proof_for(receipt,snapshot,root),source_root=source)
        assert len(proofs)==4 and [r["phase"] for r,_ in timer.phases]==["install","install","build","docker"]
        totals=defaultdict(float)
        for row,_ in timer.phases:totals[row["phase"]]+=row["seconds"]
        assert totals["build"]==receipt["frontend_build"]["timing"]["seconds"]
        _export_native("delivery-clocks",dict(snapshot_hash=snapshot,contract_hash="c"*64,phases=[row for row,_ in timer.phases],
            proofs=[p.__dict__ for p in proofs],scope="Native build subclocks only; no full OPS acceptance"),root)
    finally:
        _docker_call(["docker","image","rm",tag],capture_output=True,text=True,timeout=15)
