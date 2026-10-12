"""Deterministic failure classification and bounded repair admission (REM-07)."""
from __future__ import annotations

import hashlib
import math
import re
import time
from dataclasses import dataclass, field
from enum import Enum


class PlanCorrectionKind(str, Enum):
    """Assigned at deterministic gate sites, NEVER inferred from error prose."""

    STRUCTURE = "structure"
    CONSTRAINT = "constraint"
    INDEPENDENT_REVIEW = "independent_review"
    PROVIDER = "provider"
    ENVIRONMENT = "environment"
    COST = "cost"
    UNCLASSIFIED = "unclassified"


@dataclass(frozen=True)
class PlanCorrectionIssue:
    kind: PlanCorrectionKind
    message: str


@dataclass(frozen=True)
class PlanCorrectionContext:
    """Supervisor facts for a rejected PLAN, not producer-supplied authority.

    The caller verifies the immutable receipt and current sealed contract. A
    pure policy cannot verify a filesystem, reserve money or lock a lifecycle.
    Unknown facts must remain false/unclassified, never receive nominal defaults.
    """

    admission_status: str
    issues: tuple[PlanCorrectionIssue, ...]
    contract_hash: str
    response_sha256: str
    rejection_receipt_sha256: str
    response_bytes: int
    capture_complete: bool
    rejection_persisted: bool
    independent_major_finding: bool
    usage_complete: bool
    unreported_calls: int
    budget_remaining_usd: float


@dataclass(frozen=True)
class PlanCorrectionDecision:
    """Permission for ONE maker attempt, never plan approval or review R."""

    allowed: bool
    reason: str
    next_attempt: int | None = None
    contract_hash: str = ""
    response_sha256: str = ""
    rejection_receipt_sha256: str = ""
    issues: tuple[PlanCorrectionIssue, ...] = ()
    version: int = 1


MAX_PLAN_CORRECTION_BYTES = 1024 * 1024


def decide_plan_maker_correction(
    context: PlanCorrectionContext, *, revision_limit: int = 0, attempts_used: int = 0,
) -> PlanCorrectionDecision:
    """Fail-closed, side-effect-free opt-in for a legacy PLAN maker correction.

    Only typed STRUCTURE/CONSTRAINT issues are eligible; every issue must be
    eligible, so a mixed provider/review/cost failure cannot be reclassified by
    a matching substring. There is no runner, critic, judge, loop or mutation.

    Before dispatch the caller MUST durably consume next_attempt (including
    UNKNOWN/interrupted invocations), then use the existing tracked provider
    budget/isolation boundary. Positive remaining budget is not a reservation
    or a claim that the provider has a hard financial cap. The corrected reply
    goes through the complete unchanged gate; rejection ends this attempt.
    """
    if type(revision_limit) is not int or revision_limit not in (0, 1):
        return PlanCorrectionDecision(False, "INVALID_REVISION_LIMIT")
    if type(attempts_used) is not int or attempts_used < 0:
        return PlanCorrectionDecision(False, "INVALID_ATTEMPT_COUNT")
    if revision_limit == 0:
        return PlanCorrectionDecision(False, "CORRECTION_DISABLED")
    if attempts_used >= revision_limit:
        return PlanCorrectionDecision(False, "CORRECTION_ALREADY_CONSUMED")
    if type(context) is not PlanCorrectionContext:
        return PlanCorrectionDecision(False, "INVALID_CORRECTION_CONTEXT")
    hashes = (context.contract_hash, context.response_sha256, context.rejection_receipt_sha256)
    flags = (context.capture_complete, context.rejection_persisted,
             context.independent_major_finding, context.usage_complete)
    budget = context.budget_remaining_usd
    try:
        finite_budget = type(budget) in (int, float) and math.isfinite(budget)
    except OverflowError:
        finite_budget = False
    if (
        type(context.admission_status) is not str
        or context.admission_status not in {"pass", "fail", "not_verified"}
        or any(type(value) is not str or re.fullmatch(r"[a-f0-9]{64}", value) is None for value in hashes)
        or any(type(value) is not bool for value in flags)
        or type(context.response_bytes) is not int or context.response_bytes < 0
        or type(context.unreported_calls) is not int or context.unreported_calls < 0
        or not finite_budget
        or type(context.issues) is not tuple or not context.issues
        or any(type(issue) is not PlanCorrectionIssue
               or type(issue.kind) is not PlanCorrectionKind
               or type(issue.message) is not str or not issue.message.strip()
               for issue in context.issues)
    ):
        return PlanCorrectionDecision(False, "INVALID_CORRECTION_CONTEXT")

    def decision(allowed: bool, reason: str) -> PlanCorrectionDecision:
        return PlanCorrectionDecision(
            allowed, reason, 1 if allowed else None,
            context.contract_hash, context.response_sha256,
            context.rejection_receipt_sha256, context.issues,
        )

    if context.admission_status != "fail":
        return decision(False, "PLAN_NOT_DETERMINISTICALLY_REJECTED")
    if context.independent_major_finding:
        return decision(False, "INDEPENDENT_FINDING_BLOCKS_CORRECTION")
    if any(issue.kind not in {PlanCorrectionKind.STRUCTURE, PlanCorrectionKind.CONSTRAINT}
           for issue in context.issues):
        return decision(False, "NON_MAKER_FAILURE_BLOCKS_CORRECTION")
    if not context.rejection_persisted:
        return decision(False, "REJECTION_NOT_DURABLY_RECORDED")
    if not context.capture_complete or context.response_bytes > MAX_PLAN_CORRECTION_BYTES:
        return decision(False, "REJECTED_RESPONSE_NOT_FULLY_CAPTURED")
    if not context.usage_complete or context.unreported_calls:
        return decision(False, "COST_RECONCILIATION_REQUIRED")
    if budget <= 0:
        return decision(False, "BUDGET_EXHAUSTED")
    return decision(True, "ONE_MAKER_CORRECTION_ADMITTED")


@dataclass(frozen=True)
class Failure:
    category: str
    fingerprint: str
    repairable: bool
    diagnostic: str


def classify_failure(detail: str) -> Failure:
    text = str(detail or "").strip()
    low = text.lower()
    category = "contract"
    if any(marker in low for marker in (
        "__infra__", "isolation_unavailable", "docker indisponible", "cannot connect to the docker daemon",
        "daemon lost", "process externe", "lancement impossible", "playwright manquant", "disk unavailable",
        "environment_drift", "cache_incomplete", "cache_attestation_invalid", "clean_install_failed",
        "dependency_coordinator_unavailable", "registry unavailable",
    )):
        category = "environment"
    elif any(marker in low for marker in ("dependency_unresolved", "dependency_pending")):
        category = "dependency_waiting"
    elif any(marker in low for marker in ("modulenotfounderror", "no module named", "cannot find module", "lockfile")):
        category = "dependency"
    elif any(marker in low for marker in ("provider_error", "agent de réparation indisponible", "authentication required", "rate limit")):
        category = "provider"
    elif any(marker in low for marker in ("claim_conflict", "merge conflict", "conflit de propriété")):
        category = "conflict"
    elif any(marker in low for marker in ("timed out", "timeout", "délai dépassé")):
        category = "timeout"
    # Ignore clock/UUID/addresses, but retain status codes, field names and
    # dependency names. Never confuse two different violations just because
    # both have HTTP 400 or similar prose.
    diagnostic_lines = [line.strip() for line in text.splitlines() if re.search(
        r"ModuleNotFoundError|No module named|Cannot find module|AssertionError|__INFRA__|ISOLATION_UNAVAILABLE", line, re.I)]
    canonical = "\n".join(diagnostic_lines) if diagnostic_lines else text[-2000:]
    canonical = re.sub(r"^(?:Intégration full-stack échouée|Smoke run échoué|Docker delivery échoué)\s*:\s*", "", canonical, flags=re.I)
    canonical = re.sub(r"\b[0-9a-f]{8}-[0-9a-f-]{27,}\b", "<uuid>", canonical, flags=re.I)
    canonical = re.sub(r"\b\d{4}-\d{2}-\d{2}[T ][\d:.+Z-]+", "<time>", canonical)
    canonical = re.sub(r"\b0x[0-9a-f]+\b", "<address>", canonical, flags=re.I)
    canonical = re.sub(r"(attempt|tentative)\s*#?\s*\d+", r"\1 <n>", canonical, flags=re.I)
    digest = hashlib.sha256((category + "\n" + canonical).encode()).hexdigest()
    return Failure(category, digest, category not in {"environment", "provider", "conflict", "dependency_waiting"}, canonical)


@dataclass
class RepairLedger:
    max_attempts: int
    deadline: float
    repeat_limit: int = 2
    attempts: int = 0
    failures: list[Failure] = field(default_factory=list)

    def observe(self, detail: str) -> Failure:
        failure = classify_failure(detail)
        self.failures.append(failure)
        return failure

    def denied_reason(self, *, now: float | None = None) -> str:
        if not self.failures:
            return "aucun diagnostic"
        if not self.failures[-1].repairable:
            return f"échec {self.failures[-1].category} non réparable par un agent produit"
        if self.attempts >= max(0, self.max_attempts):
            return "plafond de tentatives atteint"
        if (time.monotonic() if now is None else now) >= self.deadline:
            return "délai global de réparation atteint"
        consecutive = 0
        for failure in reversed(self.failures):
            if failure.fingerprint != self.failures[-1].fingerprint:
                break
            consecutive += 1
        if consecutive >= self.repeat_limit:
            return "même défaut répété sans progrès"
        return ""

    def admit(self) -> None:
        reason = self.denied_reason()
        if reason:
            raise ValueError(reason)
        self.attempts += 1

    @property
    def remaining_seconds(self) -> float:
        return max(0.0, self.deadline - time.monotonic())


REPAIR_INVARIANTS = """
CONTRAINTES DE RÉPARATION NON NÉGOCIABLES :
- Ne supprime, ne renomme, ne skip/xfail aucun test critique et n'affaiblis aucune assertion.
- Une dépendance manquante doit être demandée via le coordinateur, déclarée dans
  le manifest RUNTIME ou DEV approprié et dans son lock. Une installation locale
  seule n'est jamais une correction ; la validation repart d'un environnement propre.
- Préserve le contrat externe et les exigences du brief ; ne contourne pas l'auth.
- N'arrête aucun processus par nom, n'utilise aucun accès système global.
- Cite le défaut et les fichiers corrigés ; un auto-rapport « fixed » n'est pas une preuve.
"""
