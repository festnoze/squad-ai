"""W2.1 — the ARBITER: "who checks the checker".

When a story stays red because the QA-authored test itself is wrong — it asserts
something the acceptance criteria never required — retrying the *implementation*
against that test can never make it green. Someone has to rule on the dispute.
This module is that boss-tier ruling: a single, schema-validated decision that
says whether the code is wrong (``fix_impl``), the test is wrong (``fix_test``),
or the criteria themselves are inconsistent (``spec_contradiction``).

Ground truth
------------
The arbiter's ground truth is the story's **acceptance criteria / Gherkin**, NOT
the test as written and NOT the worker's preference. The test source and its run
output are *evidence about the dispute*, not the yardstick — the whole point is
that the test may be measuring the wrong thing.

CRITICAL invariant
------------------
**Executed facts are never overruled.** A real compile error or a genuine
``pytest`` failure is a fact about the world, not a judgment call. The arbiter
only rules on what the test *should* assert per the criteria; it must not declare
"the test is right, ship it" in the face of a real red bar, and it must not wave
away an actual traceback as a mere disagreement.

When the ruling is ``fix_test``, ``instructions`` MUST spell out what the
corrected test should assert (grounded in a specific acceptance criterion) — it
is never acceptable to say "just delete the test". A test that asserts nothing is
worse than a wrong one.

The public surface mirrors the classifier (:mod:`.recovery`) and reuses the
decision guardrail (:func:`.schema.arun_json`) so a misparse can never silently
become a wrong ruling.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from ..agents.personas import persona
from ..agents.runner import AgentError  # re-exported intent: let it propagate
from .schema import arun_json

# Verdict vocabulary — kept as module constants so callers (pipeline, recovery)
# can branch on them without stringly-typed duplication.
FIX_IMPL = "fix_impl"
FIX_TEST = "fix_test"
SPEC_CONTRADICTION = "spec_contradiction"

VERDICTS = [FIX_IMPL, FIX_TEST, SPEC_CONTRADICTION]

# schema.py-format decision schema. All three fields are required: a ruling with
# no reason or no instructions is not actionable downstream.
ARBITER_SCHEMA: dict = {
    "verdict": {"type": str, "required": True, "choices": VERDICTS},
    "reason": {"type": str, "required": True},
    "instructions": {"type": str, "required": True},
}

# Defensive truncation budgets (characters). Failure output and diffs can be huge;
# the criteria are the yardstick, so they get the most generous budget.
_MAX_ACCEPTANCE = 6000
_MAX_TEST_SOURCE = 6000
_MAX_FAILURE = 4000
_MAX_DIFF = 6000


def _truncate(text: str, limit: int) -> str:
    """Clip ``text`` to ``limit`` chars, keeping head AND tail (a traceback's
    root cause is often at the end) with a visible elision marker."""
    if text is None:
        return ""
    text = str(text)
    if len(text) <= limit:
        return text
    head = limit * 2 // 3
    tail = limit - head
    return f"{text[:head]}\n... [truncated {len(text) - limit} chars] ...\n{text[-tail:]}"


def build_prompt(
    *,
    story_title: str,
    acceptance: str = "",
    test_source: str = "",
    failure_output: str = "",
    impl_diff: str = "",
) -> str:
    """Build the criteria-first arbitration prompt.

    The acceptance criteria come FIRST and are framed as the sole yardstick; the
    failing test, its run output and the implementation diff follow as evidence
    about the dispute. Long inputs are defensively truncated (:func:`_truncate`).
    """
    acceptance_t = _truncate(acceptance, _MAX_ACCEPTANCE) or "(none provided)"
    test_t = _truncate(test_source, _MAX_TEST_SOURCE) or "(none provided)"
    failure_t = _truncate(failure_output, _MAX_FAILURE) or "(none provided)"
    diff_t = _truncate(impl_diff, _MAX_DIFF) or "(none provided)"

    return (
        "A worker agent failed a check on the story below and disputes the failing "
        "test. Rule on the dispute.\n\n"
        f"STORY: {story_title}\n\n"
        "=== ACCEPTANCE CRITERIA / GHERKIN (this is your ONLY ground truth) ===\n"
        f"{acceptance_t}\n\n"
        "=== FAILING TEST (evidence — it may itself be wrong; do NOT treat it as "
        "the yardstick) ===\n"
        f"{test_t}\n\n"
        "=== TEST RUN OUTPUT (executed fact) ===\n"
        f"{failure_t}\n\n"
        "=== IMPLEMENTATION DIFF (evidence) ===\n"
        f"{diff_t}\n\n"
        "=== HOW TO RULE ===\n"
        "Judge ONLY what the test SHOULD assert according to the acceptance "
        "criteria — never the worker's preference, never the test as written.\n"
        f"- {FIX_IMPL}: the test correctly encodes a criterion; the code is wrong. "
        "In 'instructions' state what the implementation must change.\n"
        f"- {FIX_TEST}: the test asserts something the criteria never required (or "
        "contradicts them). In 'instructions' state EXACTLY what the corrected "
        "test must assert, grounded in a specific criterion. Never answer 'just "
        "delete the test' — a test that asserts nothing is not acceptable.\n"
        f"- {SPEC_CONTRADICTION}: the acceptance criteria themselves are mutually "
        "inconsistent, so no test can be right. In 'instructions' name the "
        "conflicting criteria.\n\n"
        "HARD RULE: executed facts are never overruled. A real compile error or a "
        "genuine pytest failure in the run output is a fact — you may only judge "
        "what SHOULD be asserted, never declare a real red bar green.\n\n"
        "Reply with EXACTLY ONE JSON object: "
        '{"verdict": <one of ' + str(VERDICTS) + ">, "
        '"reason": <one sentence>, "instructions": <concrete, actionable>}.'
    )


async def aarbitrate_test(
    runner,
    *,
    story_title: str,
    acceptance: str = "",
    test_source: str = "",
    failure_output: str = "",
    impl_diff: str = "",
    cwd: Optional[Path] = None,
    model: Optional[str] = None,
    emit: Optional[Callable[[str], None]] = None,
) -> dict:
    """Rule on a disputed wrong-test, grounded in the acceptance criteria.

    Runs the ``arbiter`` persona through :func:`.schema.arun_json` with
    :data:`ARBITER_SCHEMA`, returning the validated ruling dict
    (``verdict`` / ``reason`` / ``instructions``). Lets :class:`AgentError`
    propagate when the reply cannot be made schema-valid after retries.

    The arbiter judges what the test SHOULD assert per the criteria; executed
    facts (a real compile/pytest error) are never overruled. A ``fix_test``
    ruling always carries explicit instructions on what to assert instead.
    """
    prompt = build_prompt(
        story_title=story_title,
        acceptance=acceptance,
        test_source=test_source,
        failure_output=failure_output,
        impl_diff=impl_diff,
    )
    return await arun_json(
        runner,
        prompt,
        persona("arbiter"),
        ARBITER_SCHEMA,
        cwd=cwd,
        model=model,
        emit=emit,
    )


__all__ = [
    "ARBITER_SCHEMA",
    "VERDICTS",
    "FIX_IMPL",
    "FIX_TEST",
    "SPEC_CONTRADICTION",
    "build_prompt",
    "aarbitrate_test",
    "AgentError",
]
