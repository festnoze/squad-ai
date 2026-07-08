"""W1.3 — the boss-tier root-cause CLASSIFIER.

Role
----
When a work item has exhausted its build attempts (across one or more models,
after the whole escalation ladder in :mod:`.recovery` is spent) and is *still*
red, the recovery machine hands it here for a single, decisive diagnosis. From
the item's failure evidence — the repeated test failure signatures, the diffs
tried, the failing test bodies and the story's acceptance criteria — the
classifier names the SINGLE most likely root cause:

* ``too_big``            — the unit is oversized → recovery SPLITs it.
* ``wrong_test``         — the failing test itself is wrong → recovery ARBITRATEs.
* ``spec_contradiction`` — the acceptance criteria contradict themselves →
                           recovery raises an AMEND_PROPOSAL (human-gated).
* ``genuinely_hard``     — none of the above; just hard → recovery FAILs it.

Boundaries
----------
This is a **bounded, rare, boss-tier** call. It only runs AFTER the escalation
ladder is exhausted (``next_action`` in :mod:`.recovery` returned ``CLASSIFY``),
so it fires at most once per red item — never on the hot retry path. It reuses
the project's own guardrail (:func:`..orchestrator.schema.arun_json`) so a
misformatted verdict is re-prompted once rather than silently poisoning the
downstream routing decision. On unrecoverable failure it lets
:class:`AgentError` propagate; the caller decides the fallback (typically FAIL).
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterable, Optional

from ..agents.personas import persona
from .recovery import AMEND_PROPOSAL, ARBITRATE, FAIL, SPLIT
from .schema import arun_json

# --------------------------------------------------------------------------- #
# Decision schema + verdict → recovery-action routing
# --------------------------------------------------------------------------- #

#: schema.py-format spec for the classifier's JSON verdict.
CLASSIFY_SCHEMA: dict = {
    "verdict": {
        "type": str,
        "required": True,
        "choices": ["too_big", "wrong_test", "spec_contradiction", "genuinely_hard"],
    },
    "reason": {"type": str, "required": True},
    "confidence": {"type": float, "required": False, "min": 0, "max": 1},
}

#: Maps each verdict to the recovery action the machine should route to.
VERDICT_TO_ACTION: dict[str, str] = {
    "too_big": SPLIT,
    "wrong_test": ARBITRATE,
    "spec_contradiction": AMEND_PROPOSAL,
    "genuinely_hard": FAIL,
}

# Defensive truncation budgets (chars). Keep the prompt compact & evidence-first:
# a boss call should reason over the salient signals, not a novel.
_MAX_ACCEPTANCE = 3000
_MAX_SIGNATURES = 12
_MAX_SIGNATURE_LEN = 400
_MAX_TEST_BODIES = 6000
_MAX_IMPL_DIFF = 6000


def _truncate(text: str, limit: int) -> str:
    """Clamp ``text`` to ``limit`` chars, marking the cut so the model knows."""
    if text is None:
        return ""
    text = str(text)
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n… [truncated, {len(text) - limit} more chars]"


def build_prompt(
    *,
    story_title: str,
    acceptance: str = "",
    failure_signatures: Iterable[str] = (),
    test_bodies: str = "",
    impl_diff: str = "",
) -> str:
    """Build a compact, evidence-first classification prompt.

    Lays out the story, its acceptance criteria and the accumulated failure
    evidence (recurring signatures, failing test bodies, last implementation
    diff), then asks for exactly one JSON verdict. Long inputs are truncated
    defensively so the prompt stays bounded regardless of how noisy the history
    is.
    """
    sigs = [_truncate(s, _MAX_SIGNATURE_LEN) for s in failure_signatures if str(s).strip()]
    sigs = sigs[:_MAX_SIGNATURES]
    if sigs:
        sig_block = "\n".join(f"  - {s}" for s in sigs)
    else:
        sig_block = "  (none recorded)"

    return (
        "A work item exhausted all its build attempts (across the escalation "
        "ladder) and is STILL failing. Diagnose the SINGLE most likely root cause.\n\n"
        f"## Story\n{_truncate(story_title, 500)}\n\n"
        f"## Acceptance criteria\n{_truncate(acceptance, _MAX_ACCEPTANCE) or '(none provided)'}\n\n"
        f"## Recurring failure signatures\n{sig_block}\n\n"
        f"## Failing test bodies\n{_truncate(test_bodies, _MAX_TEST_BODIES) or '(none provided)'}\n\n"
        f"## Last implementation diff\n{_truncate(impl_diff, _MAX_IMPL_DIFF) or '(none provided)'}\n\n"
        "## Decide\n"
        "Weigh the evidence and pick exactly ONE verdict:\n"
        "  - too_big: the unit is oversized; too many concerns to land in one session.\n"
        "  - wrong_test: the failing test itself is wrong / contradicts the acceptance criteria.\n"
        "  - spec_contradiction: the acceptance criteria are internally inconsistent.\n"
        "  - genuinely_hard: none of the above — the work is simply hard.\n\n"
        "Reply with EXACTLY ONE JSON object: "
        '{"verdict": <one of the four>, "reason": <one concise sentence>, '
        '"confidence": <0.0-1.0>}. No prose outside the JSON.'
    )


async def aclassify(
    runner,
    *,
    story_title: str,
    acceptance: str = "",
    failure_signatures: Iterable[str] = (),
    test_bodies: str = "",
    impl_diff: str = "",
    cwd: Optional[Path] = None,
    model: Optional[str] = None,
    emit: Optional[Callable[[str], None]] = None,
) -> dict:
    """Classify the single most likely root cause of an exhausted red item.

    Runs the ``classifier`` persona through the schema guardrail
    (:func:`.schema.arun_json`), which re-prompts once on a malformed verdict.
    Returns the validated decision dict (``verdict`` / ``reason`` and optionally
    ``confidence``). Lets :class:`AgentError` propagate — the caller decides the
    fallback (typically :data:`.recovery.FAIL`).
    """
    prompt = build_prompt(
        story_title=story_title,
        acceptance=acceptance,
        failure_signatures=failure_signatures,
        test_bodies=test_bodies,
        impl_diff=impl_diff,
    )
    return await arun_json(
        runner,
        prompt,
        persona("classifier"),
        CLASSIFY_SCHEMA,
        cwd=cwd,
        model=model,
        emit=emit,
    )
