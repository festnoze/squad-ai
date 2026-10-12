"""Pipeline-owned collection ports; native facts precede independent verdicts.

Every command executes through the Linux isolation boundary. This module does
not repair a product, call a model, issue R, or equate obtained facts with PASS.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from ..config import settings
from ..orchestrator.dependencies import atomic_json
from ..orchestrator.isolated_validation import build_delivery_image
from .coordinator import SupervisorEvidenceStore, _context
from .delivery_evidence import (NativeDeliveryCollector, NativeTimingRecorder,
                               NativeTimingUnavailable, delivery_build_checks)
from .final_gate import source_snapshot
from .native_quality_raccord import collect_native_quality
from .review_delivery import delivery_required, load_reviewed_delivery_plan
from .review_plans import quality_required
from .support_adapter import AdapterUnavailable, Proof


def native_timing_recorder(contract, snapshot, root):
    return NativeTimingRecorder(evidence_root=root,snapshot_hash=snapshot,
        contract_hash=contract.contract_hash,docker=settings.docker_cmd)


async def collect_native_delivery_build(contract, source, snapshot, root, *, timing_recorder=None):
    """Cold or attested-cache real image, exact source label, native X receipt."""
    source,root=Path(source).resolve(),Path(root).resolve()
    if root.is_relative_to(source) or source_snapshot(source).digest!=snapshot:
        raise AdapterUnavailable("delivery collection needs exact frozen external roots")
    if not any(r.id in {"OPS-01","OPS-02","OPS-03","OPS-04"} for r in contract.requirements):
        return {"status":"NOT_REQUIRED","receipt":None,"limits":[]}
    output=root/"native-delivery"/snapshot/uuid4().hex
    tag="autospec/qualification:"+uuid4().hex
    from .product_harness import ReviewedProductBindings
    binding=ReviewedProductBindings.from_dict(json.loads((root/"product-bindings.json").read_bytes()))
    if (binding.snapshot_hash,binding.contract_hash)!=(snapshot,contract.contract_hash):
        raise AdapterUnavailable("image command requires exact current reviewed bindings")
    binding.validate(source)
    # No producer Dockerfile or host dependency tree is executed. The factory
    # builder consumes filtered source only after manifest-only locked install.
    ok,_=await asyncio.to_thread(build_delivery_image,source,tag,
        docker=settings.docker_cmd,timeout=settings.test_suite_timeout_s,
        evidence_root=output,snapshot_hash=snapshot,runtime_command=list(binding.runtime_command))
    path=output/"delivery-build.json"
    if not path.is_file() or path.stat().st_size>16_000_000:
        raise AdapterUnavailable("native build receipt unavailable")
    receipt=json.loads(path.read_bytes())
    if receipt.get("status")!=("PASS" if ok else "FAIL"):
        raise AdapterUnavailable("native build result contradicts actual receipt")
    checks=await asyncio.to_thread(delivery_build_checks,receipt,source,snapshot)
    proof=Proof("X",str(path),hashlib.sha256(path.read_bytes()).hexdigest(),snapshot,
        contract.contract_hash,("OBS:delivery_build","OPS-01:native_build"),True,
        "Actual factory build observation; failed status/rc preserved, not acceptance")
    await SupervisorEvidenceStore(root,snapshot,contract.contract_hash).record_native_observation(
        "delivery_build",receipt,source_proofs=[proof])
    limits=[]
    if timing_recorder is not None and ok:
        ingest=getattr(timing_recorder,"ingest_delivery",None)
        if ingest is None: limits.append("split native build timing ingestion unavailable")
        else:
            try:
                ingest(receipt,proof,source_root=source)
            except NativeTimingUnavailable:
                # The actual operation's X is retained. A diagnostic clock gap
                # cannot erase it or fabricate OPS-06; provenance contradictions
                # and source/image drift deliberately remain fatal.
                limits.append("usable native build subclocks unavailable")
    return dict(status="PARTIAL" if limits else "OBTAINED",receipt=receipt,
                proof=asdict(proof),checks=checks,limits=limits)


async def collect_native_final_facts(state,contract,source,snapshot,root,*,build=None,timing_recorder=None):
    """Actual native quality + fresh direct README operations before final gate.

    A missing collector capability leaves an explicit limit while independent
    packs still return every frozen requirement. No producer fixes are invoked.
    """
    root,source=Path(root).resolve(),Path(source).resolve()
    if root.is_relative_to(source) or source_snapshot(source).digest!=snapshot:
        raise AdapterUnavailable("final native facts require exact frozen external roots")
    result={"snapshot_hash":snapshot,"contract_hash":contract.contract_hash,
            "limits":list(build.get("limits",[])) if build else []}
    quality={}
    if quality_required(contract):
        try:
            quality=await collect_native_quality(state,contract,source,snapshot,root,timing_recorder=timing_recorder)
            result["quality"]=quality
            result["limits"].extend(quality.get("limits",[]))
        except asyncio.CancelledError: raise
        except Exception as exc: result["limits"].append("native quality unavailable: "+type(exc).__name__)
    if delivery_required(contract):
        try:
            reviewed=load_reviewed_delivery_plan(contract,source,snapshot,root)
            context,_=_context(contract,source,snapshot,root,phase="readme-"+uuid4().hex)
            async with context as harness:
                collector=NativeDeliveryCollector(reviewed["plan"],source_root=source,evidence_root=root,
                    snapshot_hash=snapshot,contract_hash=contract.contract_hash)
                result["documentation"]=await collector.collect(harness,
                    build_receipt=build.get("receipt") if build else None,
                    native_receipts=quality.get("native_receipts",{}),audit=reviewed["audit"])
        except asyncio.CancelledError: raise
        except Exception as exc: result["limits"].append("source-reviewed README execution unavailable: "+type(exc).__name__)
    if timing_recorder is not None:
        try: result["timings"]=await timing_recorder.publish()
        except asyncio.CancelledError: raise
        except Exception as exc: result["limits"].append("complete native phase timings unavailable: "+type(exc).__name__)
    if source_snapshot(source).digest!=snapshot:
        raise AdapterUnavailable("source changed during native final facts")
    result["status"]="PARTIAL" if result["limits"] else "OBTAINED"
    atomic_json(root/"reports"/snapshot/"native-facts.json",result)
    return result
