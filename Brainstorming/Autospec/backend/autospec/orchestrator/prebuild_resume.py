"""Explicit continuation of a verified, contracted project stopped in PLAN.

This is not restart-from-scratch or a global retry facility. Admission is
synchronous on the owning event loop; the PLAN guard is installed before a
background task is exposed. The supervisor journal remains outside product
write roots, and an unresolved UNKNOWN continuation blocks later dispatch.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import re
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

from ..config import settings
from ..models import PipelinePhase
from ..storage import save_state_checkpoint, workspace_dir
from ..validation.final_gate import source_snapshot
from . import acceptance, bootstrap, stack
from .dependencies import atomic_json, file_lock

_TERMINAL = {PipelinePhase.STOPPED, PipelinePhase.NEEDS_ATTENTION, PipelinePhase.ERROR}
_PROTECTED = (
    "id", "name", "goal", "brief", "brownfield_path", "backend_language",
    "technical_stack", "streams", "acceptance_contract_hash", "acceptance_max_lots",
    "budget_usd", "budget_tokens", "usage", "iteration", "components",
    "bootstrap_fingerprint", "bootstrap_verified_once",
)


@dataclass(frozen=True)
class PlanResumeDecision:
    """Read-only decision; permission to dispatch is never inferred from it."""
    result: str
    reason: str = ""
    identity: dict | None = None


def is_plan_candidate(state) -> bool:
    """Select the category before bootstrap-failed's legacy full restart.

    Ready/known-cost/terminal checks belong to admission, not this selector:
    a failed runtime recheck must never fall back to SPEC or scaffold.
    """
    return (not state.stories and not state.epics
            and state.generation_checkpoint.get("last_phase") == "plan")


def _protected(state) -> dict:
    payload = state.model_dump(mode="json")
    return {key: payload[key] for key in _PROTECTED}


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False).encode()).hexdigest()


def _known_cost(pipeline) -> None:
    state = pipeline.state
    values = (state.usage.cost_usd, state.budget_usd)
    counters = (state.budget_tokens, state.usage.input_tokens, state.usage.output_tokens,
                state.usage.agent_calls, state.usage.failed_calls, state.usage.unreported_calls)
    if (any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
            or v < 0 for v in values)
            or any(type(v) is not int or v < 0 for v in counters)):
        raise ValueError("Usage ou budget invalide : reprise pré-plan refusée.")
    if state.usage.unreported_calls or state.generation_checkpoint.get("cost_incomplete"):
        raise ValueError("COST_UNREPORTED : réconcilier le coût avant toute reprise.")
    if (state.budget_usd and state.usage.cost_usd >= state.budget_usd
            or state.budget_tokens and state.usage.input_tokens + state.usage.output_tokens >= state.budget_tokens):
        raise ValueError("Budget restant épuisé : aucune reprise pré-plan.")
    # The serialized PLAN continuation must not reconstruct an old concurrent
    # lane from seemingly-known totals. Its own reviewed reconciliation remains
    # authoritative even when the concurrent setting was subsequently disabled.
    if (acceptance.supervisor_root(state.id) / "budget-reservations.json").exists():
        raise ValueError("Journal provider concurrent présent : réconciliation explicite requise.")


def _identity(pipeline) -> dict:
    state = pipeline.state
    decision = stack._sealed(state.technical_stack)
    if decision is None or decision["backend"] != state.backend_language.value:
        raise ValueError("Stack non scellée ou obsolète : aucune reprise pré-plan.")
    if state.brownfield_path:
        raise ValueError("Reprise pré-plan limitée au socle déterministe existant.")
    contract = acceptance.load_contract(state)
    if contract is None or not contract.facts:
        raise ValueError("Oracle source formalisé absent : aucune reprise pré-plan.")
    ws = workspace_dir(state.id)
    manifest = bootstrap._read_manifest(ws, decision)
    if manifest["fingerprint"] != state.bootstrap_fingerprint:
        raise ValueError("Empreinte du socle obsolète : aucune reprise pré-plan.")
    if any(not bootstrap._safe_path(ws, name).is_file() for name in manifest["files"]):
        raise ValueError("Fichier du socle absent : aucune reprise pré-plan.")
    if bootstrap._runtime_dependencies_missing(state, ws):
        raise ValueError("Lock déclaré absent : aucune reprise pré-plan.")
    oracle = acceptance.contract_store(state.id).root / (contract.contract_hash + ".json")
    return dict(protected=_protected(state), snapshot_hash=source_snapshot(ws).digest,
                manifest_sha256=hashlib.sha256(bootstrap._existing_manifest(ws).read_bytes()).hexdigest(),
                oracle_sha256=hashlib.sha256(oracle.read_bytes()).hexdigest(),
                contract_hash=contract.contract_hash)


def _journal_path(state) -> Path:
    return acceptance.supervisor_root(state.id) / "prebuild-continuation.json"


def _read_journal(path: Path) -> dict:
    if not path.exists():
        return {"version": 1, "attempts": []}
    if path.resolve() != path.absolute() or path.stat().st_nlink != 1 or path.stat().st_size > 2_000_000:
        raise ValueError("Journal de continuation non sûr.")
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("version") != 1 or not isinstance(value.get("attempts"), list):
        raise ValueError("Journal de continuation invalide.")
    if any(not isinstance(row, dict) or row.get("outcome") not in
           {"UNKNOWN", "done", "needs_attention", "stopped", "error"} for row in value["attempts"]):
        raise ValueError("Historique de continuation invalide.")
    return value


def _validate(pipeline) -> dict:
    """Read-only guard; no provider, state write, ledger reset or repair."""
    state = pipeline.state
    if not is_plan_candidate(state) or state.phase not in _TERMINAL:
        raise ValueError("Reprise pré-plan : état terminal PLAN sans backlog requis.")
    if state.generation_checkpoint.get("status") == "active" or state.agent_activity:
        raise ValueError("Activité de génération encore présente : reprise refusée.")
    for name in ("_task", "_impact_task", "_setup_task", "_doc_task", "_deploy_task",
                 "_eval_task", "_security_task", "_retro_task", "_docker_worker"):
        task = getattr(pipeline, name, None)
        if task is not None and not task.done():
            raise ValueError("Une opération du projet est encore active.")
    if pipeline._deployment_lock.locked() or state.running or state.paused or state.resume_at:
        raise ValueError("Projet actif, suspendu ou reprise automatique armée : admission refusée.")
    if state.bootstrap_status != "ready" or not state.bootstrap_verified_once:
        raise ValueError("Socle vérifié ready requis : aucun restart implicite.")
    _known_cost(pipeline)
    identity = _identity(pipeline)
    path = _journal_path(state)
    journal = _read_journal(path)
    if any(row["outcome"] == "UNKNOWN" for row in journal["attempts"]):
        raise ValueError("Continuation UNKNOWN non réconciliée : nouveau dispatch refusé.")
    if len(journal["attempts"]) >= 50:
        raise ValueError("Historique de continuation borné : arbitrage explicite requis.")
    return identity


async def prebuild_resume(pipeline, *, explicit_request: bool = False) -> PlanResumeDecision:
    """Pure decision port for the parent's explicit resume-build raccord.

    A RESUME_PLAN decision proves only admission prerequisites, not execution
    or product delivery. It does not create a task, write a journal, alter phase,
    reset usage or call a provider. The caller owns explicit user authorization.
    """
    if not is_plan_candidate(pipeline.state):
        return PlanResumeDecision("NOT_APPLICABLE")
    if explicit_request is not True:
        return PlanResumeDecision("REFUSED", reason="Décision utilisateur explicite requise ; aucun timer pré-plan.")
    try:
        return PlanResumeDecision("RESUME_PLAN", identity=_validate(pipeline))
    except Exception as exc:
        # Bounded supervisor diagnostics, never dump JSON/prompt/credentials.
        reason = str(exc)[:400] if isinstance(exc, ValueError) else type(exc).__name__
        return PlanResumeDecision("REFUSED", reason=reason)


def admit(pipeline, *, explicit_request: bool = False) -> dict:
    """Explicit execution-port admission; not called by the pure decision API."""
    if explicit_request is not True:
        raise ValueError("Décision utilisateur explicite requise ; aucune continuation automatique.")
    state = pipeline.state
    identity = _validate(pipeline)
    path = _journal_path(state)
    with file_lock(path.with_suffix(".lock")):
        journal = _read_journal(path)
        if any(row["outcome"] == "UNKNOWN" for row in journal["attempts"]):
            raise ValueError("Continuation UNKNOWN non réconciliée : nouveau dispatch refusé.")
        if len(journal["attempts"]) >= 50:
            raise ValueError("Historique de continuation borné : arbitrage explicite requis.")
        receipt = dict(version=1, continuation_id=uuid.uuid4().hex, project_id=state.id,
                       owner_pid=os.getpid(), from_phase="plan", outcome="UNKNOWN",
                       admitted_at=time.time(), protected_sha256=_digest(identity["protected"]),
                       explicit_request=True,
                       usage_before=state.usage.model_dump(mode="json"),
                       budget_usd=state.budget_usd, budget_tokens=state.budget_tokens,
                       **{key: value for key, value in identity.items() if key != "protected"})
        journal["attempts"].append(receipt)
        atomic_json(path, journal)  # Durable before exposing any background task.
    return dict(receipt=receipt, identity=identity)


def start(pipeline, *, explicit_request: bool = False) -> None:
    """The tiny public-raccord helper; phase guard precedes every await."""
    ticket = admit(pipeline, explicit_request=explicit_request)
    pipeline._stop_requested = False
    pipeline._delivery_blocked = False
    pipeline.state.delivery_ready = False
    pipeline.state.generation_checkpoint = {
        **pipeline.state.generation_checkpoint,
        "continuation_id": ticket["receipt"]["continuation_id"],
    }
    pipeline.state.phase = PipelinePhase.PLAN
    try:
        pipeline._sync()
    except BaseException:
        # The durable UNKNOWN intent remains; do not enable an automatic retry.
        pipeline.state.phase = PipelinePhase.NEEDS_ATTENTION
        raise
    pipeline._task = asyncio.create_task(run(pipeline, ticket))


def _current_journal_row(journal: dict, pipeline, ticket) -> dict:
    receipt = ticket.get("receipt") if isinstance(ticket, dict) else None
    continuation_id = receipt.get("continuation_id") if isinstance(receipt, dict) else None
    if (not isinstance(continuation_id, str) or not continuation_id
            or receipt.get("project_id") != pipeline.state.id
            or receipt.get("explicit_request") is not True
            or pipeline.state.generation_checkpoint.get("continuation_id") != continuation_id):
        raise ValueError("Identité de continuation PLAN invalide.")
    rows = [row for row in journal["attempts"]
            if row.get("continuation_id") == continuation_id]
    if (len(rows) != 1 or rows[0].get("outcome") != "UNKNOWN"
            or rows[0].get("project_id") != pipeline.state.id
            or rows[0].get("explicit_request") is not True):
        raise ValueError("Continuation PLAN absente ou déjà réconciliée.")
    return rows[0]


def plan_maker_correction_attempts_used(pipeline, ticket) -> int:
    """Count every durable correction intent; UNKNOWN consumes the sole turn."""
    path = _journal_path(pipeline.state)
    with file_lock(path.with_suffix(".lock")):
        journal = _read_journal(path)
        _current_journal_row(journal, pipeline, ticket)
        used = 0
        for row in journal["attempts"]:
            correction = row.get("plan_correction")
            if correction is None:
                continue
            if (not isinstance(correction, dict) or correction.get("version") != 1
                    or correction.get("outcome") not in {"UNKNOWN", "admitted", "rejected"}
                    or correction.get("attempt") != 1):
                raise ValueError("Journal de correction PLAN invalide ; reprise refusée.")
            used += 1
        return used


def record_plan_maker_correction(pipeline, ticket, decision) -> None:
    """Consume the unique maker correction durably before its provider dispatch."""
    if (not getattr(decision, "allowed", False) or getattr(decision, "next_attempt", None) != 1
            or not getattr(decision, "issues", ())):
        raise ValueError("Admission de correction PLAN invalide.")
    path = _journal_path(pipeline.state)
    with file_lock(path.with_suffix(".lock")):
        journal = _read_journal(path)
        row = _current_journal_row(journal, pipeline, ticket)
        if any(isinstance(item, dict) and item.get("plan_correction") is not None
               for item in journal["attempts"]):
            raise ValueError("Correction maker PLAN déjà consommée ; seconde révision refusée.")
        correction = dict(
            version=1, attempt=1, outcome="UNKNOWN", admitted_at=time.time(),
            contract_hash=decision.contract_hash,
            rejected_response_sha256=decision.response_sha256,
            rejection_receipt_sha256=decision.rejection_receipt_sha256,
            issues=[asdict(issue) for issue in decision.issues],
            usage_before=pipeline.state.usage.model_dump(mode="json"),
        )
        row["plan_correction"] = correction
        atomic_json(path, journal)


def finish_plan_maker_correction(pipeline, ticket, *, outcome: str,
                                 response_sha256: str | None = None,
                                 admission_status: str | None = None) -> None:
    """Resolve a returned correction; interruption or write failure stays UNKNOWN."""
    if outcome not in {"admitted", "rejected"}:
        raise ValueError("Résultat de correction PLAN invalide.")
    if response_sha256 is not None and not re.fullmatch(r"[a-f0-9]{64}", response_sha256):
        raise ValueError("Hash de réponse corrigée invalide.")
    if admission_status not in {"pass", "fail", "not_verified"}:
        raise ValueError("Admission déterministe corrigée invalide.")
    path = _journal_path(pipeline.state)
    with file_lock(path.with_suffix(".lock")):
        journal = _read_journal(path)
        row = _current_journal_row(journal, pipeline, ticket)
        correction = row.get("plan_correction")
        if not isinstance(correction, dict) or correction.get("outcome") != "UNKNOWN":
            raise ValueError("Intention de correction PLAN absente ou déjà réconciliée.")
        correction.update(outcome=outcome, finished_at=time.time(),
                          response_sha256=response_sha256,
                          admission_status=admission_status,
                          usage_after=pipeline.state.usage.model_dump(mode="json"),
                          cost_incomplete=bool(pipeline.state.usage.unreported_calls))
        atomic_json(path, journal)


def _finish_journal(pipeline, ticket) -> None:
    path = _journal_path(pipeline.state)
    with file_lock(path.with_suffix(".lock")):
        journal = _read_journal(path)
        rows = [row for row in journal["attempts"]
                if row.get("continuation_id") == ticket["receipt"]["continuation_id"]]
        if len(rows) != 1 or rows[0]["outcome"] != "UNKNOWN":
            raise ValueError("Identité de continuation perdue : journal non réconcilié.")
        rows[0].update(outcome=pipeline.state.phase.value, finished_at=time.time(),
                       usage_after=pipeline.state.usage.model_dump(mode="json"),
                       cost_incomplete=bool(pipeline.state.usage.unreported_calls))
        atomic_json(path, journal)


async def run(pipeline, ticket) -> None:
    """One explicit PLAN pass; common build and final gate ports, no lifecycle copy."""
    from .pipeline import DeliveryBlocked
    state = pipeline.state
    succeeded = False
    cancelled = False
    try:
        # _sync queues on the pipeline's executor; drain it before the runtime
        # wait and before a tool-capable provider can ever be entered.
        from .pipeline import _PERSIST_EXECUTOR
        await asyncio.get_running_loop().run_in_executor(
            _PERSIST_EXECUTOR, save_state_checkpoint, state.id,
            state.model_dump_json(indent=2))
        pipeline._bootstrap_cancel.clear()
        result = await bootstrap.verify_runtime(state, workspace_dir(state.id),
            timeout_s=settings.bootstrap_timeout_s, cancel=pipeline._bootstrap_cancel,
            repair_dependencies=False)
        if (not result.ok or result.skipped
                or result.fingerprint != state.bootstrap_fingerprint):
            state.bootstrap_status = "failed"
            pipeline._block_delivery("Revalidation du socle refusée avant PLAN.", source="prebuild-resume")
            raise DeliveryBlocked()
        if pipeline._stop_requested:
            return
        _known_cost(pipeline)
        if _identity(pipeline) != ticket["identity"]:
            pipeline._block_delivery("Source, stack, oracle, usage ou budget changé pendant la revalidation.",
                                     source="prebuild-resume")
            raise DeliveryBlocked()
        await pipeline._checkpoint()
        if pipeline._stop_requested:
            return
        # Only an explicit pre-plan continuation opts into the single bounded
        # deterministic maker correction. Ordinary lifecycle PLAN stays off.
        await pipeline._aplan_phase(plan_maker_revision_limit=1,
                                    plan_continuation_ticket=ticket)
        await pipeline._aarchitect_phase()
        await pipeline._aapproval_gate("plan")
        if pipeline._stop_requested:
            return
        await pipeline._abuild_phase()
        if pipeline._delivery_blocked:
            raise DeliveryBlocked()
        # The existing sole delivery chain owns smoke/runtime/DoD/independent
        # qualification/publication. No local replacement or badge can pass it.
        if not await pipeline._adelivery_gates() or not state.delivery_ready:
            raise DeliveryBlocked()
        succeeded = True
    except asyncio.CancelledError:
        cancelled = True
        raise
    except DeliveryBlocked:
        pipeline._delivery_blocked = True
    except Exception as exc:
        pipeline._block_delivery("Continuation pré-plan interrompue : " + type(exc).__name__,
                                 source="prebuild-resume")
    finally:
        state.phase = (PipelinePhase.STOPPED if cancelled or pipeline._stop_requested else
                       PipelinePhase.DONE if succeeded else PipelinePhase.NEEDS_ATTENTION)
        if not succeeded:
            state.delivery_ready = False
        try:
            pipeline._sync()
            _finish_journal(pipeline, ticket)
        except Exception:
            # A completed task must not hide a journal failure behind DONE.
            state.phase = PipelinePhase.NEEDS_ATTENTION
            state.delivery_ready = False
            pipeline._block_delivery("Journal de continuation non réconcilié ; aucun nouveau dispatch.",
                                     source="prebuild-resume")
            pipeline._sync()
