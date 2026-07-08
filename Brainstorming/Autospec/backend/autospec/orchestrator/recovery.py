"""W1 — the unified recovery state machine.

A red work item today follows an ad-hoc path scattered across the dev loop:
retry the same model up to ``dev_max_attempts``, then maybe split, then fail.
This module makes that ONE explicit, pure, unit-testable decision so escalation
(retry on a *stronger* model), root-cause classification, splitting and failing
compose predictably instead of interleaving by accident.

Design invariants (see VERIFIED_SWARM_UPGRADE.md, principle 2 + Wave 1):
- **Pure & deterministic.** ``next_action`` takes a ``TaskFailureHistory`` and
  returns a ``Decision`` — no I/O, no settings reads. The pipeline builds the
  history from its own state and applies the decision.
- **Byte-identical when flags are off.** With escalation and classification
  disabled the machine yields exactly today's sequence: RETRY while dev attempts
  remain, then SPLIT if split-on-failure is available, else FAIL. Escalation only
  changes *which model* a RETRY uses; it never changes the retry/split/fail
  control flow.
- **Infra ≠ dev.** Transient provider/CLI failures and flakes do not count as
  dev attempts (they must never consume an escalation rung or push a task toward
  FAIL) — mirroring the pipeline's existing ``infra_attempts`` split.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Recovery actions. CLASSIFY/ARBITRATE/AMEND_PROPOSAL become reachable as the
# later waves land (classifier W1.3, arbitration W2, amendment W5); until then a
# flags-off machine only ever emits RETRY / SPLIT / FAIL — today's behaviour.
RETRY = "retry"
ESCALATE = "escalate"          # a RETRY that also climbs to a stronger model rung
CLASSIFY = "classify"          # attempts exhausted → ask the root-cause classifier
SPLIT = "split"                # decompose into finer sub-tasks
ARBITRATE = "arbitrate"        # wrong-test dispute → boss ruling (W2)
AMEND_PROPOSAL = "amend"       # spec contradiction → human-gated amendment (W5)
FAIL = "fail"

# Attempt kinds. Only ``dev`` counts toward exhaustion / escalation.
KIND_DEV = "dev"
KIND_INFRA = "infra"
KIND_FLAKE = "flake"


@dataclass
class AttemptRecord:
    """One build attempt's outcome, as the machine sees it."""

    model: str = ""
    signatures: list[str] = field(default_factory=list)
    kind: str = KIND_DEV


@dataclass
class Decision:
    action: str
    model: str | None = None   # forced model id for an ESCALATE (else None)
    reason: str = ""


@dataclass
class TaskFailureHistory:
    """Everything the machine needs to decide the next move for a red item."""

    attempts: list[AttemptRecord] = field(default_factory=list)
    max_attempts: int = 1
    ladder: list[str] = field(default_factory=list)   # cost-ascending model ids
    split_available: bool = False                     # split-on-failure on AND depth < max
    escalate_enabled: bool = False
    classify_enabled: bool = False

    @property
    def dev_attempts(self) -> int:
        """Attempts that count toward exhaustion (infra/flake excluded)."""
        return sum(1 for a in self.attempts if a.kind == KIND_DEV)

    @property
    def recurring_signatures(self) -> list[str]:
        """Signatures seen in ≥2 distinct dev attempts (a stuck, repeating error)."""
        seen: dict[str, int] = {}
        for a in self.attempts:
            if a.kind != KIND_DEV:
                continue
            for s in set(a.signatures):
                seen[s] = seen.get(s, 0) + 1
        return [s for s, n in seen.items() if n >= 2]


def ladder_model(next_attempt: int, ladder: list[str]) -> str | None:
    """Model id for the (1-based) attempt number, clamped to the top rung.

    Attempt 1 → cheapest rung (ladder[0]); each subsequent attempt climbs one
    rung until the strongest is reached. Empty ladder → None (normal routing)."""
    if not ladder or next_attempt < 1:
        return None
    return ladder[min(next_attempt - 1, len(ladder) - 1)]


def next_action(history: TaskFailureHistory) -> Decision:
    """Decide the next recovery move for a work item that just went red.

    Called AFTER an attempt failed. ``dev_attempts`` is how many counting attempts
    have happened; the next one (if any) is ``dev_attempts + 1``."""
    done = history.dev_attempts

    if done < history.max_attempts:
        nxt = done + 1
        if history.escalate_enabled and history.ladder:
            model = ladder_model(nxt, history.ladder)
            # Only call it an ESCALATE when the rung actually differs from the
            # previous attempt's model (else it's a plain same-model RETRY).
            prev = next((a.model for a in reversed(history.attempts)
                         if a.kind == KIND_DEV), None)
            if model and model != prev:
                return Decision(ESCALATE, model,
                                f"retry {nxt}/{history.max_attempts} on stronger model {model}")
            return Decision(RETRY, model, f"retry {nxt}/{history.max_attempts} (model {model})")
        return Decision(RETRY, None, f"retry {nxt}/{history.max_attempts}")

    # Dev attempts exhausted.
    if history.classify_enabled:
        return Decision(CLASSIFY, None,
                        "attempts exhausted → classify root cause "
                        f"(recurring: {len(history.recurring_signatures)})")
    if history.split_available:
        return Decision(SPLIT, None, "attempts exhausted → adaptive split")
    return Decision(FAIL, None, "attempts exhausted → fail")
