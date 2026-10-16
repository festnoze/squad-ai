"""REM-03 mechanism metatests, no provider or generated product host execution.

The public pipeline raccord deliberately belongs to the parent. These tests
exercise the read-only decision and explicit execution ports on a real Pipeline,
with all operation ports mocked before they could execute a provider/product.
"""
import asyncio
import hashlib
import json
from pathlib import Path

import pytest

from autospec.agents.runner import FakeRunner
from autospec.config import settings
from autospec.contracts import ContractFact, import_contract
from autospec.models import PipelinePhase, ProjectState, Epic, UserStory
from autospec.orchestrator import acceptance, bootstrap, prebuild_resume as p, stack, workspace
from autospec.orchestrator.dependencies import atomic_json
from autospec.orchestrator.pipeline import DeliveryBlocked, Pipeline
from autospec.storage import workspace_dir


@pytest.fixture
def pending(monkeypatch):
    decision = stack.freeze(dict(backend="python", framework="fastapi", frontend="none",
        database="sqlite", kind="api", source="explicit"))
    fact = ContractFact.create("LIMIT", "plan_limits", {"max_lots": 1}, ["BOOK-01"], "One lot.")
    contract = import_contract("One lot.", "| BOOK-01 | B / X | A book is available |",
        reviewed_by="Mechanical fixture, not product proof", facts=[fact])
    state = ProjectState(id="preplan-mechanism", name="book", goal="API Python", brief=contract.brief,
        technical_stack=decision, acceptance_contract_hash=contract.contract_hash,
        acceptance_max_lots=1, budget_usd=40, phase=PipelinePhase.NEEDS_ATTENTION,
        generation_checkpoint={"status":"needs_attention", "last_phase":"plan", "run_id":"old-run"})
    state.usage.cost_usd = .347486
    state.usage.agent_calls = 2
    state.usage.input_tokens = 29956
    state.usage.output_tokens = 22767
    acceptance.contract_store(state.id).save(contract)
    # Trusted deterministic scaffold is only written/read here, never executed.
    prepared = bootstrap.prepare(state, workspace_dir(state.id))
    assert prepared.ok
    ws = workspace_dir(state.id)
    (ws / "uv.lock").write_text("# inert locked-dependency fixture, never installed\n")
    state.bootstrap_fingerprint = prepared.fingerprint
    state.bootstrap_status = "ready"
    state.bootstrap_verified_once = True
    pipeline = Pipeline(state, FakeRunner([]))
    monkeypatch.setattr(bootstrap, "prepare", lambda *a, **k: pytest.fail("prepare called by continuation"))
    monkeypatch.setattr(workspace, "scaffold", lambda *a, **k: pytest.fail("scaffold called by continuation"))
    calls = []
    async def runtime(*args, **kwargs):
        assert kwargs["repair_dependencies"] is False
        calls.append("runtime")
        return bootstrap.BootstrapResult(True, "Controlled runtime port only", fingerprint=prepared.fingerprint)
    # The continuation explicitly opts into the bounded PLAN correction path.
    async def plan(*, plan_maker_revision_limit=0, plan_continuation_ticket=None):
        assert plan_maker_revision_limit == 1
        assert plan_continuation_ticket is not None
        calls.append("plan")
        state.epics = [Epic(id="E", title="One lot")]
        state.stories = [UserStory(id="S", epic_id="E", title="Book")]
    async def architect(): calls.append("architect")
    async def approval(kind):
        assert kind == "plan"
        calls.append("approval")
    async def build(): calls.append("build")
    async def delivery():
        calls.append("common-delivery-gates")
        return False  # No synthetic product evidence can declare delivery green.
    monkeypatch.setattr(bootstrap, "verify_runtime", runtime)
    monkeypatch.setattr(pipeline, "_aplan_phase", plan)
    monkeypatch.setattr(pipeline, "_aarchitect_phase", architect)
    monkeypatch.setattr(pipeline, "_aapproval_gate", approval)
    monkeypatch.setattr(pipeline, "_abuild_phase", build)
    monkeypatch.setattr(pipeline, "_adelivery_gates", delivery)
    return pipeline, calls


def files(root):
    return {str(f.relative_to(root)):hashlib.sha256(f.read_bytes()).hexdigest()
            for f in root.rglob("*") if f.is_file()}


async def test_decision_is_readonly_and_preserves_contract_source_usage(pending):
    pipeline, calls = pending
    state = pipeline.state.model_dump(mode="json")
    root = Path(settings.workspace_root)
    before = files(root)
    result = await p.prebuild_resume(pipeline, explicit_request=True)
    assert result.result == "RESUME_PLAN" and result.identity["protected"]["usage"]["agent_calls"] == 2
    assert pipeline.state.model_dump(mode="json") == state and files(root) == before
    assert calls == [] and pipeline.runner.calls == [] and pipeline._task is None


async def test_user_intent_required_not_inferred_from_terminal_state(pending):
    pipeline, calls = pending
    assert (await p.prebuild_resume(pipeline)).result == "REFUSED"
    with pytest.raises(ValueError, match="explicite"):
        p.start(pipeline)
    assert calls == [] and pipeline._task is None


async def test_pipeline_resume_preplan_requires_explicit_request_and_never_falls_back(pending, monkeypatch):
    pipeline, calls = pending
    monkeypatch.setattr(pipeline, "start", lambda: pytest.fail("pre-plan fallback restarted lifecycle"))
    with pytest.raises(ValueError, match="explicite"):
        await pipeline.aresume_build()
    assert calls == [] and pipeline.runner.calls == [] and pipeline._task is None
    assert not p._journal_path(pipeline.state).exists()

    # Even an explicit request cannot turn a failed/stale pre-plan bootstrap
    # into the separate full-lifecycle restart path.
    pipeline.state.bootstrap_status = "failed"
    with pytest.raises(ValueError, match="Socle vérifié ready"):
        await pipeline.aresume_build(explicit_request=True)
    assert calls == [] and pipeline.runner.calls == [] and pipeline._task is None
    assert not p._journal_path(pipeline.state).exists()


async def test_pipeline_explicit_preplan_dispatch_journals_before_plan_task(pending, monkeypatch):
    pipeline, calls = pending

    async def delivery():
        calls.append("common-delivery-gates")
        pipeline.state.delivery_ready = True
        return True  # State-machine metatest only; not product delivery evidence.

    monkeypatch.setattr(pipeline, "_adelivery_gates", delivery)
    await pipeline.aresume_build(explicit_request=True)

    # aresume_build returns synchronously after helper admission; the durable
    # UNKNOWN receipt exists before its background continuation can run.
    journal = json.loads(p._journal_path(pipeline.state).read_text(encoding="utf-8"))
    assert pipeline.state.phase == PipelinePhase.PLAN and pipeline._task is not None
    assert len(journal["attempts"]) == 1 and journal["attempts"][0]["outcome"] == "UNKNOWN"
    assert journal["attempts"][0]["explicit_request"] is True

    await asyncio.wait_for(pipeline._task, timeout=5)
    journal = json.loads(p._journal_path(pipeline.state).read_text(encoding="utf-8"))
    assert journal["attempts"][0]["outcome"] == "done"
    assert calls == ["runtime", "plan", "architect", "approval", "build", "common-delivery-gates"]
    assert pipeline.state.phase == PipelinePhase.DONE and pipeline.state.delivery_ready
    assert pipeline.runner.calls == []


@pytest.mark.parametrize("value", [False, None, 1, "true"])
async def test_only_strict_true_can_attest_explicit_request(pending, value):
    pipeline, calls = pending
    assert (await p.prebuild_resume(pipeline, explicit_request=value)).result == "REFUSED"
    assert calls == []


@pytest.mark.parametrize("field,value", [
    ("phase",PipelinePhase.PLAN), ("bootstrap_status","failed"),
    ("bootstrap_verified_once",False), ("bootstrap_fingerprint","bad"),
    ("running",True), ("paused",True), ("resume_at",1), ("budget_usd",.347486),
    ("budget_usd",float("nan")), ("brief","altered"), ("acceptance_contract_hash","0"*64),
    ("agent_activity",{"x":{"phase":"provider"}}),
])
async def test_invalid_state_refused_without_mutation_or_dispatch(pending, field, value):
    pipeline, calls = pending
    setattr(pipeline.state,field,value)
    phase = pipeline.state.phase
    assert (await p.prebuild_resume(pipeline, explicit_request=True)).result == "REFUSED"
    assert pipeline.state.phase == phase and calls == [] and pipeline.runner.calls == []
    assert not p._journal_path(pipeline.state).exists()


@pytest.mark.parametrize("field,value", [("cost_incomplete",True),("status","active")])
async def test_checkpoint_unknown_or_active_refused(pending, field, value):
    pipeline, calls = pending
    pipeline.state.generation_checkpoint[field] = value
    assert (await p.prebuild_resume(pipeline, explicit_request=True)).result == "REFUSED"
    assert calls == []


async def test_unknown_usage_and_provider_ledger_refused(pending):
    pipeline, calls = pending
    pipeline.state.usage.unreported_calls = 1
    assert (await p.prebuild_resume(pipeline, explicit_request=True)).result == "REFUSED"
    pipeline.state.usage.unreported_calls = 0
    atomic_json(acceptance.supervisor_root(pipeline.state.id)/"budget-reservations.json",
                {"entries":{"paid-turn":{"status":"unreported"}}})
    assert (await p.prebuild_resume(pipeline, explicit_request=True)).result == "REFUSED"
    assert calls == [] and pipeline.state.usage.agent_calls == 2


@pytest.mark.parametrize("category", ["stories","epics","other_phase"])
async def test_other_resume_categories_are_not_applicable(pending, category):
    pipeline, calls = pending
    if category == "stories":pipeline.state.stories=[UserStory(id="S",epic_id="E",title="Book")]
    elif category == "epics":pipeline.state.epics=[Epic(id="E",title="Book")]
    else:pipeline.state.generation_checkpoint["last_phase"]="spec"
    assert (await p.prebuild_resume(pipeline, explicit_request=True)).result == "NOT_APPLICABLE"
    assert calls == []


async def test_stack_seal_manifest_oracle_and_missing_source_fail_closed(pending):
    pipeline, calls = pending
    original = dict(pipeline.state.technical_stack)
    pipeline.state.technical_stack["database"]="none"
    assert (await p.prebuild_resume(pipeline, explicit_request=True)).result == "REFUSED"
    pipeline.state.technical_stack=original
    ws=workspace_dir(pipeline.state.id)
    (ws/"main.py").unlink()
    assert (await p.prebuild_resume(pipeline, explicit_request=True)).result == "REFUSED"
    assert calls == []


async def test_unknown_continuation_journal_not_historical_recovery_marker(pending):
    pipeline, calls = pending
    # Historical launcher UNKNOWN is not a provider-cost receipt and is never
    # consumed or overwritten by the generic project helper.
    root=Path(settings.workspace_root)
    historical=root/"recovery-attempt.json"
    historical.write_text('{"outcome":"UNKNOWN","scope":"old zero-call recovery"}')
    original=historical.read_bytes()
    assert (await p.prebuild_resume(pipeline, explicit_request=True)).result == "RESUME_PLAN"
    atomic_json(p._journal_path(pipeline.state),{"version":1,"attempts":[{"outcome":"UNKNOWN"}]})
    assert (await p.prebuild_resume(pipeline, explicit_request=True)).result == "REFUSED"
    assert historical.read_bytes()==original and calls == []


async def test_explicit_start_phase_guard_is_synchronous_and_journal_precedes_operation(pending):
    pipeline, calls = pending
    p.start(pipeline, explicit_request=True)
    assert pipeline.state.phase == PipelinePhase.PLAN and calls == []
    record=json.loads(p._journal_path(pipeline.state).read_text())["attempts"][0]
    assert record["outcome"]=="UNKNOWN" and record["explicit_request"] is True
    assert record["usage_before"]["agent_calls"]==2 and record["budget_usd"]==40
    with pytest.raises(ValueError):p.start(pipeline, explicit_request=True)
    await pipeline._task
    assert calls==["runtime","plan","architect","approval","build","common-delivery-gates"]
    assert pipeline.state.phase==PipelinePhase.NEEDS_ATTENTION and not pipeline.state.delivery_ready
    assert pipeline.runner.calls==[] and pipeline.state.usage.cost_usd==.347486
    assert json.loads(p._journal_path(pipeline.state).read_text())["attempts"][0]["outcome"]=="needs_attention"


@pytest.mark.parametrize("port", ["_aplan_phase","_aarchitect_phase","_aapproval_gate","_abuild_phase","_adelivery_gates"])
async def test_exception_at_each_common_port_never_declares_done(pending,monkeypatch,port):
    pipeline,calls=pending
    async def fail(*a,**k):raise RuntimeError("controlled failure")
    monkeypatch.setattr(pipeline,port,fail)
    p.start(pipeline,explicit_request=True)
    await pipeline._task
    assert pipeline.state.phase==PipelinePhase.NEEDS_ATTENTION and not pipeline.state.delivery_ready
    assert pipeline.runner.calls==[]


async def test_cancel_runtime_stops_without_restarting_spec_or_scaffold(pending,monkeypatch):
    pipeline,calls=pending
    entered=asyncio.Event()
    async def runtime(*a,**k):
        entered.set()
        await asyncio.Event().wait()
    monkeypatch.setattr(bootstrap,"verify_runtime",runtime)
    p.start(pipeline,explicit_request=True)
    await entered.wait()
    pipeline._task.cancel()
    with pytest.raises(asyncio.CancelledError):await pipeline._task
    assert pipeline.state.phase==PipelinePhase.STOPPED and not pipeline.state.delivery_ready
    assert calls==[] and pipeline.runner.calls==[]


@pytest.mark.parametrize("mutation", ["source","oracle","budget","usage","stack"])
async def test_revalidation_cannot_change_bound_identity_before_plan(pending,monkeypatch,mutation):
    pipeline,calls=pending
    async def runtime(*a,**k):
        state=pipeline.state
        if mutation=="source":(workspace_dir(state.id)/"main.py").write_text("# changed inert fixture\n")
        elif mutation=="oracle":
            path=acceptance.contract_store(state.id).root/(state.acceptance_contract_hash+".json")
            path.write_bytes(path.read_bytes()+b" ")
        elif mutation=="budget":state.budget_usd=41
        elif mutation=="usage":state.usage.cost_usd=.3
        else:state.technical_stack["database"]="none"
        return bootstrap.BootstrapResult(True,"controlled",fingerprint=state.bootstrap_fingerprint)
    monkeypatch.setattr(bootstrap,"verify_runtime",runtime)
    p.start(pipeline,explicit_request=True)
    await pipeline._task
    assert calls==[] and pipeline.runner.calls==[]
    assert pipeline.state.phase==PipelinePhase.NEEDS_ATTENTION and not pipeline.state.delivery_ready


async def test_failed_runtime_remains_preplan_candidate_never_legacy_start(pending,monkeypatch):
    pipeline,calls=pending
    async def fail(*a,**k):return bootstrap.BootstrapResult(False,"controlled failure")
    monkeypatch.setattr(bootstrap,"verify_runtime",fail)
    p.start(pipeline,explicit_request=True)
    await pipeline._task
    assert pipeline.state.bootstrap_status=="failed" and p.is_plan_candidate(pipeline.state)
    assert (await p.prebuild_resume(pipeline,explicit_request=True)).result=="REFUSED"
    assert calls==[] and pipeline.runner.calls==[]


async def test_boolean_delivery_success_without_readiness_cannot_declare_done(pending,monkeypatch):
    pipeline,calls=pending
    async def false_green():
        calls.append("unproven-true")
        assert pipeline.state.delivery_ready is False
        return True
    monkeypatch.setattr(pipeline,"_adelivery_gates",false_green)
    p.start(pipeline,explicit_request=True)
    await pipeline._task
    assert pipeline.state.phase==PipelinePhase.NEEDS_ATTENTION
    assert not pipeline.state.delivery_ready and pipeline.runner.calls==[]


async def test_failed_bootstrap_is_refused_not_legacy_fallback(pending,monkeypatch):
    pipeline,calls=pending
    pipeline.state.bootstrap_status="failed"
    monkeypatch.setattr(pipeline,"start",lambda:pytest.fail("legacy lifecycle was started"))
    result=await p.prebuild_resume(pipeline,explicit_request=True)
    assert result.result=="REFUSED" and p.is_plan_candidate(pipeline.state)
    # Parent raccord must raise on REFUSED before its bootstrap-failed branch.
    with pytest.raises(ValueError):
        if result.result=="REFUSED":raise ValueError(result.reason)
        pipeline.start()
    assert calls==[] and pipeline.runner.calls==[]


@pytest.mark.parametrize("skipped,fingerprint",[(True,None),(False,"stale")])
async def test_runtime_without_matching_attestation_never_enters_plan(pending,monkeypatch,skipped,fingerprint):
    pipeline,calls=pending
    async def runtime(*a,**k):
        return bootstrap.BootstrapResult(True,"controlled",skipped=skipped,
            fingerprint=fingerprint or pipeline.state.bootstrap_fingerprint)
    monkeypatch.setattr(bootstrap,"verify_runtime",runtime)
    p.start(pipeline,explicit_request=True)
    await pipeline._task
    assert calls==[] and pipeline.runner.calls==[]
    assert pipeline.state.phase==PipelinePhase.NEEDS_ATTENTION


async def test_intent_storage_failure_prevents_phase_change_and_operation(pending,monkeypatch):
    pipeline,calls=pending
    def fail(*a,**k):raise OSError("controlled intent storage failure")
    monkeypatch.setattr(p,"atomic_json",fail)
    with pytest.raises(OSError):p.start(pipeline,explicit_request=True)
    assert pipeline.state.phase==PipelinePhase.NEEDS_ATTENTION
    assert pipeline._task is None and calls==[] and pipeline.runner.calls==[]


async def test_final_journal_failure_never_keeps_done_or_releases_unknown(pending,monkeypatch):
    pipeline,calls=pending
    async def accepted_port():
        pipeline.state.delivery_ready=True
        return True  # Pure state-machine metatest, NOT acceptance evidence.
    def fail(*a,**k):raise OSError("controlled final journal failure")
    monkeypatch.setattr(pipeline,"_adelivery_gates",accepted_port)
    monkeypatch.setattr(p,"_finish_journal",fail)
    p.start(pipeline,explicit_request=True)
    await pipeline._task
    assert pipeline.state.phase==PipelinePhase.NEEDS_ATTENTION
    assert pipeline.state.delivery_ready is False and pipeline.runner.calls==[]
    assert json.loads(p._journal_path(pipeline.state).read_text())["attempts"][0]["outcome"]=="UNKNOWN"


async def test_cancel_at_plan_preserves_unknown_cost_and_stops(pending,monkeypatch):
    pipeline,calls=pending
    entered=asyncio.Event()
    async def plan(**kwargs):
        entered.set()
        await asyncio.Event().wait()
    monkeypatch.setattr(pipeline,"_aplan_phase",plan)
    p.start(pipeline,explicit_request=True)
    await entered.wait()
    pipeline.state.usage.unreported_calls=1  # Controlled interrupted receipt fixture.
    pipeline._task.cancel()
    with pytest.raises(asyncio.CancelledError):await pipeline._task
    assert pipeline.state.phase==PipelinePhase.STOPPED
    assert pipeline.state.usage.unreported_calls==1 and pipeline.runner.calls==[]
    assert (await p.prebuild_resume(pipeline,explicit_request=True)).result=="REFUSED"


def _plan_for(pipeline, *, wrong_limit=False):
    return {
        "epics": [{"id": "E-1", "title": "Books", "stories": [{
            "id": "S-1", "title": "Book endpoint", "requirement_ids": ["BOOK-01"],
            "tasks": [
                {"id": "T-0", "title": "Foundation", "file_globs": ["books/foundation.py"],
                 "requirement_ids": ["BOOK-01"]},
                {"id": "T-1", "title": "Vertical", "file_globs": ["books/vertical.py"],
                 "depends_on": ["T-0"], "requirement_ids": ["BOOK-01"]},
            ],
        }]}],
        "lot_definition": "explicit_groups", "lots": [{"id": "L-1", "members": ["S-1"]}],
        "milestones": {"foundation": ["T-0"], "vertical": "T-1"},
        "contract_facts": {"LIMIT": {"max_lots": 2 if wrong_limit else 1}},
        "technical_stack": dict(pipeline.state.technical_stack),
    }


def _use_real_plan_phase(pipeline, monkeypatch):
    monkeypatch.setattr(pipeline, "_aplan_phase",
        Pipeline._aplan_phase.__get__(pipeline, Pipeline))


async def _run_plan_continuation(pipeline, calls, monkeypatch):
    async def delivery():
        calls.append("common-delivery-gates")
        pipeline.state.delivery_ready = True
        return True  # State-machine metatest; not product delivery evidence.
    monkeypatch.setattr(pipeline, "_adelivery_gates", delivery)
    _use_real_plan_phase(pipeline, monkeypatch)
    p.start(pipeline, explicit_request=True)
    await asyncio.wait_for(pipeline._task, timeout=5)


async def test_preplan_correction_is_one_deterministic_maker_call_after_durable_unknown(pending, monkeypatch):
    pipeline, calls = pending
    runner = pipeline.runner
    runner.queue(json.dumps(_plan_for(pipeline, wrong_limit=True)),
                 json.dumps(_plan_for(pipeline)))
    original_arun = runner.arun
    observed_intent = []

    async def inspect_correction_intent(prompt, system_prompt, **kwargs):
        if len(runner.calls) == 1:
            journal = json.loads(p._journal_path(pipeline.state).read_text(encoding="utf-8"))
            observed_intent.append(journal["attempts"][0]["plan_correction"]["outcome"])
        return await original_arun(prompt, system_prompt, **kwargs)

    monkeypatch.setattr(runner, "arun", inspect_correction_intent)
    await _run_plan_continuation(pipeline, calls, monkeypatch)

    journal = json.loads(p._journal_path(pipeline.state).read_text(encoding="utf-8"))
    correction = journal["attempts"][0]["plan_correction"]
    assert pipeline.state.phase == PipelinePhase.DONE and pipeline.state.delivery_ready
    assert len(runner.calls) == 2 and observed_intent == ["UNKNOWN"]
    assert correction["outcome"] == "admitted" and correction["admission_status"] == "pass"
    assert correction["rejection_receipt_sha256"]
    receipts = list((acceptance.supervisor_root(pipeline.state.id) / "plans" / "rejected").glob("*.json"))
    assert len(receipts) == 1  # The initial immutable rejection survives the correction.
    assert runner.calls[1]["system_prompt"] == runner.calls[0]["system_prompt"]
    assert "Erreurs du gate" in runner.calls[1]["prompt"]
    assert "Réponse maker rejetée" in runner.calls[1]["prompt"]
    assert not any("critic" in call["system_prompt"].lower()
                   or "judge" in call["system_prompt"].lower() for call in runner.calls)


async def test_preplan_correction_rejection_does_not_loop_or_create_backlog(pending, monkeypatch):
    pipeline, calls = pending
    runner = pipeline.runner
    initially_rejected = _plan_for(pipeline, wrong_limit=True)
    still_invalid = _plan_for(pipeline)
    still_invalid["lots"].append({"id": "L-2", "members": ["S-1"]})
    runner.queue(json.dumps(initially_rejected), json.dumps(still_invalid),
                 json.dumps(_plan_for(pipeline)))
    await _run_plan_continuation(pipeline, calls, monkeypatch)

    journal = json.loads(p._journal_path(pipeline.state).read_text(encoding="utf-8"))
    correction = journal["attempts"][0]["plan_correction"]
    assert pipeline.state.phase == PipelinePhase.NEEDS_ATTENTION
    assert not pipeline.state.stories and not pipeline.state.epics
    assert len(runner.calls) == 2  # Initial plan + sole correction, no third request.
    assert correction["outcome"] == "rejected" and correction["admission_status"] == "fail"
    assert len(list((acceptance.supervisor_root(pipeline.state.id) / "plans" / "rejected").glob("*.json"))) == 2


@pytest.mark.parametrize("blocked_fact", ["budget", "unknown_usage"])
async def test_preplan_correction_refuses_unknown_or_exhausted_cost_before_second_call(
        pending, monkeypatch, blocked_fact):
    pipeline, calls = pending
    runner = pipeline.runner
    runner.queue(json.dumps(_plan_for(pipeline, wrong_limit=True)),
                 json.dumps(_plan_for(pipeline)))
    original_arun = pipeline._tracked.arun

    async def synthesize_unreconciled_cost(*args, **kwargs):
        result = await original_arun(*args, **kwargs)
        if blocked_fact == "budget":
            pipeline.state.usage.cost_usd = pipeline.state.budget_usd
        else:
            pipeline.state.usage.unreported_calls = 1
        return result

    monkeypatch.setattr(pipeline._tracked, "arun", synthesize_unreconciled_cost)
    await _run_plan_continuation(pipeline, calls, monkeypatch)

    journal = json.loads(p._journal_path(pipeline.state).read_text(encoding="utf-8"))
    assert pipeline.state.phase == PipelinePhase.NEEDS_ATTENTION
    assert len(runner.calls) == 1
    assert "plan_correction" not in journal["attempts"][0]
    assert not pipeline.state.stories and not pipeline.state.epics


async def test_nonrepairable_plan_finding_prevents_maker_correction_dispatch(pending, monkeypatch):
    pipeline, calls = pending
    pipeline.state.plan_findings = [{"id": "security", "severity": "major", "confirmed": True,
        "resolution": "", "evidence": "review.json", "rationale": "unresolved blocker",
        "decided_by": "reviewer"}]
    pipeline.runner.queue(json.dumps(_plan_for(pipeline, wrong_limit=True)),
                          json.dumps(_plan_for(pipeline)))
    await _run_plan_continuation(pipeline, calls, monkeypatch)

    journal = json.loads(p._journal_path(pipeline.state).read_text(encoding="utf-8"))
    assert pipeline.state.phase == PipelinePhase.NEEDS_ATTENTION
    assert len(pipeline.runner.calls) == 1
    assert "plan_correction" not in journal["attempts"][0]
    assert not pipeline.state.stories and not pipeline.state.epics


@pytest.mark.parametrize("confirmed", [1, "true"])
async def test_malformed_major_finding_confirmation_fails_closed_before_correction(
        pending, monkeypatch, confirmed):
    pipeline, calls = pending
    pipeline.state.plan_findings = [{"id": "security", "severity": "major", "confirmed": confirmed,
        "resolution": "", "evidence": "review.json", "rationale": "unresolved blocker",
        "decided_by": "reviewer"}]
    pipeline.runner.queue(json.dumps(_plan_for(pipeline, wrong_limit=True)),
                          json.dumps(_plan_for(pipeline)))
    await _run_plan_continuation(pipeline, calls, monkeypatch)

    journal = json.loads(p._journal_path(pipeline.state).read_text(encoding="utf-8"))
    assert pipeline.state.phase == PipelinePhase.NEEDS_ATTENTION
    assert len(pipeline.runner.calls) == 1
    assert "plan_correction" not in journal["attempts"][0]
    assert not pipeline.state.stories and not pipeline.state.epics


async def test_preplan_correction_is_not_repeated_on_later_explicit_continuation(pending, monkeypatch):
    pipeline, calls = pending
    runner = pipeline.runner
    rejected = json.dumps(_plan_for(pipeline, wrong_limit=True))
    runner.queue(rejected, rejected, rejected)
    await _run_plan_continuation(pipeline, calls, monkeypatch)
    assert len(runner.calls) == 2

    # A completed-but-rejected revision consumes the unique project-plan turn.
    await _run_plan_continuation(pipeline, calls, monkeypatch)
    assert len(runner.calls) == 3  # Second invocation's maker only, no correction.
    journal = json.loads(p._journal_path(pipeline.state).read_text(encoding="utf-8"))
    assert len(journal["attempts"]) == 2
    assert journal["attempts"][0]["plan_correction"]["outcome"] == "rejected"
    assert "plan_correction" not in journal["attempts"][1]


async def test_ordinary_plan_default_stays_off_and_opt_in_requires_the_continuation_ticket(
        pending, monkeypatch):
    pipeline, _ = pending
    _use_real_plan_phase(pipeline, monkeypatch)
    with pytest.raises(ValueError, match="continuation journal"):
        await Pipeline._aplan_phase(pipeline, plan_maker_revision_limit=1)
    with pytest.raises(ValueError, match="0 or 1"):
        await Pipeline._aplan_phase(pipeline, plan_maker_revision_limit=2,
                                    plan_continuation_ticket={})
    forged_id = "forged-but-matching-checkpoint"
    pipeline.state.generation_checkpoint["continuation_id"] = forged_id
    forged_ticket = {"receipt": {"continuation_id": forged_id,
                                  "project_id": pipeline.state.id,
                                  "explicit_request": True}}
    with pytest.raises(ValueError, match="Continuation PLAN absente"):
        await Pipeline._aplan_phase(pipeline, plan_maker_revision_limit=1,
                                    plan_continuation_ticket=forged_ticket)
    assert pipeline.runner.calls == []

    pipeline.runner.queue(json.dumps(_plan_for(pipeline, wrong_limit=True)))
    with pytest.raises(DeliveryBlocked):
        await Pipeline._aplan_phase(pipeline)
    assert len(pipeline.runner.calls) == 1  # The legacy/default route never self-corrects.
    assert not pipeline.state.stories and not pipeline.state.epics


async def test_optin_requires_strict_explicit_flag_in_ticket_and_current_journal(pending, monkeypatch):
    pipeline, _ = pending
    ticket = p.admit(pipeline, explicit_request=True)
    continuation_id = ticket["receipt"]["continuation_id"]
    pipeline.state.generation_checkpoint["continuation_id"] = continuation_id
    path = p._journal_path(pipeline.state)
    journal = json.loads(path.read_text(encoding="utf-8"))
    journal["attempts"][0]["explicit_request"] = False
    atomic_json(path, journal)

    _use_real_plan_phase(pipeline, monkeypatch)
    with pytest.raises(ValueError, match="Continuation PLAN absente"):
        await Pipeline._aplan_phase(pipeline, plan_maker_revision_limit=1,
                                    plan_continuation_ticket=ticket)
    assert pipeline.runner.calls == []
