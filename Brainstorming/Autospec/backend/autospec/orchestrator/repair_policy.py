"""Deterministic failure classification and bounded repair admission (REM-07)."""
from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, field


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
    )):
        category = "environment"
    elif any(marker in low for marker in ("modulenotfounderror", "no module named", "cannot find module", "dependency_pending", "lockfile")):
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
    return Failure(category, digest, category not in {"environment", "provider", "conflict"}, canonical)


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
