"""W5.1 — the SPEC AMENDMENT proposer: the most dangerous feature, made safe.

Role
----
When a story stays red because its **acceptance criteria are genuinely
self-contradictory** (the ``spec_contradiction`` verdict from :mod:`.classifier`
or :mod:`.arbitration`), no amount of retrying the implementation can make it
green — the yardstick itself is broken. This module proposes a MINIMAL amendment
to the spec that removes the contradiction.

Why this is dangerous
---------------------
A system that can rewrite the very criteria it fails to meet can *legalize its
own failure*: faced with a hard requirement it cannot satisfy, it could simply
delete or soften that requirement and declare victory. That is the single most
dangerous capability in the whole swarm. Two hard invariants keep it safe:

1. **Human-pending by default.** This module NEVER auto-applies anything. It only
   produces a vetted *proposal* — a ``before`` / ``after`` / ``rationale`` diff
   for a human (or an explicit caller) to review and apply. Nothing here writes
   to the spec, the architecture or the constitution.

2. **An INDEPENDENT weakening gate.** Every proposal is checked by a *separate*
   agent call (the ``critic`` persona, distinct from the ``architect`` that
   wrote it) whose only job is to answer: "does ``after`` weaken / reduce what
   the product must do, compared to ``before``?" The check is deliberately
   biased toward safety — it defaults to ``weakens=true`` when in doubt. A
   proposal is marked ``approved_safe`` ONLY when this independent check says
   ``weakens=false``. A proposal that reduces the requirement is rejected, never
   silently accepted.

The goal of a good amendment is to make the criteria *self-consistent* (remove
the contradiction) WITHOUT reducing the scope of what the product must deliver.
Reuses the project's decision guardrail (:func:`.schema.arun_json`) so a misparse
can never silently become an unreviewed spec change.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from ..agents.personas import persona
from ..agents.runner import AgentError  # re-exported intent: let it propagate
from .schema import arun_json

# Amendment targets — what part of the planning artefacts a proposal may touch.
ACCEPTANCE_CRITERIA = "acceptance_criteria"
ARCHITECTURE = "architecture"
CONSTITUTION = "constitution"

TARGETS = [ACCEPTANCE_CRITERIA, ARCHITECTURE, CONSTITUTION]

# schema.py-format spec for the proposed amendment. All four fields are required:
# a proposal with no before/after diff or no rationale is not reviewable.
AMENDMENT_SCHEMA: dict = {
    "target": {"type": str, "required": True, "choices": TARGETS},
    "before": {"type": str, "required": True},
    "after": {"type": str, "required": True},
    "rationale": {"type": str, "required": True},
}

# schema.py-format spec for the independent weakening check.
WEAKENING_SCHEMA: dict = {
    "weakens": {"type": bool, "required": True},
    "reason": {"type": str, "required": True},
}

# Defensive truncation budgets (characters). Keep prompts compact & evidence-first.
_MAX_ACCEPTANCE = 6000
_MAX_FAILURE = 4000
_MAX_HINT = 1000
_MAX_DIFF_SIDE = 6000
_MAX_RATIONALE = 3000


def _truncate(text: str, limit: int) -> str:
    """Clip ``text`` to ``limit`` chars, keeping head AND tail with a marker."""
    if text is None:
        return ""
    text = str(text)
    if len(text) <= limit:
        return text
    head = limit * 2 // 3
    tail = limit - head
    return f"{text[:head]}\n... [truncated {len(text) - limit} chars] ...\n{text[-tail:]}"


def build_proposal_prompt(
    *,
    story_title: str,
    acceptance: str = "",
    failure_context: str = "",
    target_hint: str = "",
) -> str:
    """Build the compact, evidence-first amendment-proposal prompt.

    The acceptance criteria come first (the thing suspected to be
    self-contradictory), then the failure evidence that surfaced the
    contradiction. The prompt demands the MINIMAL change that removes the
    contradiction WITHOUT reducing what the product must do — and is explicit
    that softening or deleting a requirement is not an acceptable amendment.
    Long inputs are defensively truncated (:func:`_truncate`).
    """
    acceptance_t = _truncate(acceptance, _MAX_ACCEPTANCE) or "(none provided)"
    failure_t = _truncate(failure_context, _MAX_FAILURE) or "(none provided)"
    hint_t = _truncate(target_hint, _MAX_HINT)
    hint_block = f"\n## Hint from triage\n{hint_t}\n" if hint_t else ""

    return (
        "A story is stuck because its acceptance criteria appear to be "
        "SELF-CONTRADICTORY — they require mutually incompatible things, so no "
        "implementation can satisfy them all. Propose the MINIMAL amendment that "
        "removes the contradiction.\n\n"
        f"## Story\n{_truncate(story_title, 500)}\n\n"
        "## Acceptance criteria (suspected self-contradictory)\n"
        f"{acceptance_t}\n\n"
        f"## Failure evidence (why it is stuck)\n{failure_t}\n"
        f"{hint_block}\n"
        "## How to propose\n"
        "Change the SMALLEST amount of text that makes the criteria "
        "self-consistent. The amendment must resolve the conflict WITHOUT "
        "reducing what the product must deliver — do NOT soften, relax or delete "
        "a genuine requirement just to make the story pass. If two criteria truly "
        "conflict, reconcile them (pick the one that reflects the real product "
        "intent, or make both consistent) rather than dropping capability.\n"
        f"- 'target': which artefact to amend, one of {TARGETS}.\n"
        "- 'before': the exact current text that is contradictory.\n"
        "- 'after': the proposed replacement text (self-consistent, same scope).\n"
        "- 'rationale': why this is the minimal, non-weakening fix.\n\n"
        "This is a PROPOSAL for human review — it will NOT be applied "
        "automatically.\n\n"
        "Reply with EXACTLY ONE JSON object: "
        '{"target": <one of ' + str(TARGETS) + ">, "
        '"before": <current text>, "after": <proposed text>, '
        '"rationale": <one or two sentences>}. No prose outside the JSON.'
    )


def build_weakening_prompt(*, before: str, after: str, rationale: str) -> str:
    """Build the INDEPENDENT weakening-check prompt.

    Frames a single, strict question: does ``after`` weaken / reduce the
    requirement compared to ``before``? The reviewer is told to judge ONLY the
    strength of the requirement (not style, not whether the fix is elegant) and
    to default to ``weakens=true`` whenever it is unclear — the safe bias, since
    a false "does not weaken" would let the system legalize its own failure.
    """
    before_t = _truncate(before, _MAX_DIFF_SIDE) or "(empty)"
    after_t = _truncate(after, _MAX_DIFF_SIDE) or "(empty)"
    rationale_t = _truncate(rationale, _MAX_RATIONALE) or "(none provided)"

    return (
        "You are an INDEPENDENT safety reviewer of a proposed spec amendment. A "
        "system that fails a requirement must not be allowed to weaken that "
        "requirement to pass. Judge ONE thing only: does the proposed 'after' "
        "text WEAKEN or REDUCE what the product must do, compared to the current "
        "'before' text?\n\n"
        "=== BEFORE (current requirement) ===\n"
        f"{before_t}\n\n"
        "=== AFTER (proposed replacement) ===\n"
        f"{after_t}\n\n"
        "=== AUTHOR'S RATIONALE (context only — do NOT take it at face value) ===\n"
        f"{rationale_t}\n\n"
        "=== HOW TO DECIDE ===\n"
        "It WEAKENS (weakens=true) if 'after' drops a capability, relaxes a "
        "constraint, narrows scope, removes an error/edge case, or makes a "
        "guarantee softer/optional. It does NOT weaken (weakens=false) only if it "
        "merely resolves an internal contradiction while preserving — or "
        "strengthening — everything the product must do.\n"
        "Judge only the STRENGTH of the requirement, not wording or style.\n"
        "DEFAULT TO weakens=true WHEN IN DOUBT: if you cannot be confident the "
        "requirement is fully preserved, answer weakens=true.\n\n"
        "Reply with EXACTLY ONE JSON object: "
        '{"weakens": <true|false>, "reason": <one sentence>}. '
        "No prose outside the JSON."
    )


async def apropose_amendment(
    runner,
    *,
    story_title: str,
    acceptance: str = "",
    failure_context: str = "",
    target_hint: str = "",
    cwd: Optional[Path] = None,
    model: Optional[str] = None,
    emit: Optional[Callable[[str], None]] = None,
) -> dict:
    """Propose a minimal spec amendment that removes a self-contradiction.

    Boss-tier call: runs the ``architect`` persona through the schema guardrail
    (:func:`.schema.arun_json`) with :data:`AMENDMENT_SCHEMA`, returning the
    validated proposal dict (``target`` / ``before`` / ``after`` / ``rationale``).
    Lets :class:`AgentError` propagate when the reply cannot be made schema-valid
    after retries. This produces a PROPOSAL only — nothing is applied.
    """
    prompt = build_proposal_prompt(
        story_title=story_title,
        acceptance=acceptance,
        failure_context=failure_context,
        target_hint=target_hint,
    )
    return await arun_json(
        runner,
        prompt,
        persona("architect"),
        AMENDMENT_SCHEMA,
        cwd=cwd,
        model=model,
        emit=emit,
    )


async def acheck_not_weakening(
    runner,
    *,
    before: str,
    after: str,
    rationale: str,
    cwd: Optional[Path] = None,
    model: Optional[str] = None,
    emit: Optional[Callable[[str], None]] = None,
) -> dict:
    """Independently check whether a proposed amendment weakens the requirement.

    Runs the ``critic`` persona — deliberately a DIFFERENT persona from the
    ``architect`` that authored the proposal — through the schema guardrail with
    :data:`WEAKENING_SCHEMA`, returning the validated decision dict
    (``weakens`` / ``reason``). The check is biased toward safety
    (``weakens=true`` when in doubt). Lets :class:`AgentError` propagate.
    """
    prompt = build_weakening_prompt(before=before, after=after, rationale=rationale)
    return await arun_json(
        runner,
        prompt,
        persona("critic"),
        WEAKENING_SCHEMA,
        cwd=cwd,
        model=model,
        emit=emit,
    )


async def apropose_safe_amendment(
    runner,
    *,
    story_title: str,
    acceptance: str = "",
    failure_context: str = "",
    target_hint: str = "",
    cwd: Optional[Path] = None,
    model: Optional[str] = None,
    emit: Optional[Callable[[str], None]] = None,
) -> Optional[dict]:
    """Produce a vetted amendment PROPOSAL, gated by an independent weakening check.

    Orchestrates the two-step, safe flow:

    1. :func:`apropose_amendment` — the ``architect`` proposes a minimal fix.
    2. :func:`acheck_not_weakening` — the ``critic`` independently rules whether
       the proposal weakens the requirement.

    Returns the proposal dict AUGMENTED with:

    * ``approved_safe`` (bool) — ``True`` ONLY when the independent check says
      ``weakens=false``; ``False`` otherwise (including when the check itself
      fails, so a broken check never approves anything).
    * ``weakening_reason`` (str) — the check's one-sentence justification.

    Returns ``None`` if the proposal call itself fails (:class:`AgentError`
    caught internally). NEVER auto-applies anything — it only yields a vetted
    proposal for a human / caller to apply.
    """
    try:
        proposal = await apropose_amendment(
            runner,
            story_title=story_title,
            acceptance=acceptance,
            failure_context=failure_context,
            target_hint=target_hint,
            cwd=cwd,
            model=model,
            emit=emit,
        )
    except AgentError:
        if emit is not None:
            try:
                emit("amendment proposal failed; no proposal produced")
            except Exception:
                pass
        return None

    result = dict(proposal)
    try:
        check = await acheck_not_weakening(
            runner,
            before=proposal.get("before", ""),
            after=proposal.get("after", ""),
            rationale=proposal.get("rationale", ""),
            cwd=cwd,
            model=model,
            emit=emit,
        )
    except AgentError:
        # A broken safety check must never approve. Fail closed.
        result["approved_safe"] = False
        result["weakening_reason"] = "independent weakening check failed to produce a verdict"
        return result

    weakens = bool(check.get("weakens", True))
    result["approved_safe"] = not weakens
    result["weakening_reason"] = check.get("reason", "")
    return result


__all__ = [
    "AMENDMENT_SCHEMA",
    "WEAKENING_SCHEMA",
    "TARGETS",
    "ACCEPTANCE_CRITERIA",
    "ARCHITECTURE",
    "CONSTITUTION",
    "build_proposal_prompt",
    "build_weakening_prompt",
    "apropose_amendment",
    "acheck_not_weakening",
    "apropose_safe_amendment",
    "AgentError",
]
