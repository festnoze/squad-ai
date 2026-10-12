"""Bounded public view of REM-10's private plan-admission receipt.

No maker text, provider, persistence or admission decision belongs here. The
parent checkpoints this projection before publishing SSE/monitor events, and
keeps the complete REM-10 response/context/errors outside public state.
"""
from __future__ import annotations

import hashlib
import re
from .plan_gates import PlanAdmission

MAX_DIAGNOSTICS = 64
MAX_INPUT_DIAGNOSTICS = 4096
MAX_DIAGNOSTIC_BYTES = 65536
_SHA = re.compile(r"[0-9a-f]{64}\Z")


def _digest(value: str | None, *, optional: bool = False) -> None:
    if value is None and optional:
        return
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise ValueError("telemetry identity must be a lowercase SHA256")


def _code(error: str) -> str:
    # Only catalogue codes leave this boundary; never interpolated node IDs,
    # claims, titles, paths or excerpts. This classifies, not waives, a rejection.
    if error.startswith("maker JSON"):
        return "plan_json"
    if "bounded capture/parse limit" in error:
        return "candidate_limit"
    if error.startswith("lots must be explicit_groups"):
        return "lot_definition"
    if re.fullmatch(r"\d+ explicit lots exceeds maximum \d+", error):
        return "lot_limit"
    if error.startswith("contract coverage missing:") or "unknown requirement IDs" in error:
        return "coverage"
    if error.startswith("contract invariant differs or missing:"):
        return "source_invariant"
    if error.startswith("plan stack differs"):
        return "stack"
    if error.startswith("vertical_contract"):
        return "vertical_contract"
    if "milestone" in error:
        return "milestone"
    if error.startswith("dependency request unresolved"):
        return "dependency_pending"
    if "dependency" in error:
        return "dependency_graph"
    if "claim" in error or "stream root" in error or "glob" in error:
        return "file_claims"
    if "shared contract" in error or "unknown consumer" in error:
        return "shared_contract"
    if error.startswith("confirmed ") or error == "invalid review finding":
        return "unresolved_finding"
    if "provider unavailable" in error or "judge score" in error:
        return "review_unavailable"
    if "must be" in error or "plan ID" in error or "no schedulable work" in error:
        return "plan_schema"
    return "other_constraint"


def public_plan_admission(
    admission: PlanAdmission, *, response_sha256: str | None,
    response_bytes: int | None, capture_complete: bool,
    receipt_sha256: str | None = None,
) -> dict:
    """Project exact receipt metadata without accepting a response or context.

    Digests identify the full candidate, including above the private capture
    bound. Missing capture is explicit; a partial transcript must never be used.
    The parent owns durable state and publication; failures do not grant PASS.
    """
    if not isinstance(admission, PlanAdmission) or type(admission.version) is not int or admission.version != 1:
        raise ValueError("unsupported plan admission version")
    if admission.status not in {"pass", "fail", "not_verified"}:
        raise ValueError("unsupported plan admission status")
    _digest(admission.contract_hash)
    _digest(response_sha256, optional=True)
    _digest(receipt_sha256, optional=True)
    if type(capture_complete) is not bool:
        raise ValueError("capture completeness must be boolean")
    if response_bytes is not None and (type(response_bytes) is not int or not 0 <= response_bytes <= 2**31-1):
        raise ValueError("candidate byte size outside telemetry bounds")
    if (response_sha256 is None) != (response_bytes is None) or (capture_complete and response_sha256 is None):
        raise ValueError("inconsistent candidate capture identity")
    if type(admission.lot_count) is not int or not 0 <= admission.lot_count <= MAX_INPUT_DIAGNOSTICS:
        raise ValueError("lot count outside telemetry bounds")
    if admission.status == "pass" and admission.errors:
        raise ValueError("passing admission cannot contain errors")
    rows, counts, seen = [], {}, set()
    omitted = 0
    for severity, messages in (("error", admission.errors), ("warning", admission.warnings)):
        if not isinstance(messages, (tuple, list)) or len(messages) > MAX_INPUT_DIAGNOSTICS:
            raise ValueError("diagnostic collection outside telemetry bounds")
        for message in messages:
            if not isinstance(message, str) or len(message) > MAX_DIAGNOSTIC_BYTES:
                raise ValueError("diagnostic outside telemetry bounds")
            raw = message.encode("utf-8")
            if len(raw) > MAX_DIAGNOSTIC_BYTES:
                raise ValueError("diagnostic outside telemetry bounds")
            key = (severity, message)
            if key in seen:
                continue
            seen.add(key)
            code = _code(message[:4096])
            counts[code] = counts.get(code, 0)+1
            if len(rows) == MAX_DIAGNOSTICS:
                omitted += 1
                continue
            rows.append({"code": code, "severity": severity,
                         "diagnostic_sha256": hashlib.sha256(raw).hexdigest()})
    return {"version": 1, "admission_version": admission.version,
            "status": admission.status, "reason": "constraint_rejected" if admission.status == "fail" else admission.status,
            "contract_hash": admission.contract_hash,
            "candidate_sha256": response_sha256, "candidate_bytes": response_bytes,
            "candidate_available": response_sha256 is not None, "capture_complete": capture_complete,
            "receipt_sha256": receipt_sha256, "lot_count": admission.lot_count,
            "diagnostics": rows, "diagnostic_counts": counts,
            "diagnostics_omitted": omitted}
