"""Generic refinement harness: maker -> critic -> judge feedback loop.

A maker agent produces an artifact; a critic agent reflects-then-acts (ReAct)
to propose concrete improvements; a judge agent scores quality 0-100. The loop
is DETERMINISTIC in its stopping: it stops when the judge score reaches the
configured threshold OR after a hard cap of rounds (whichever comes first). It
is gated per maker role by env vars (off by default to save tokens).

The harness is artifact-agnostic: callers provide a `revise` coroutine (which
may have side effects, e.g. a dev rewriting code) and optional `accept`/
`rollback` coroutines to validate and undo a revision (e.g. keep the suite
green). For pure-JSON artifacts (a PO plan), accept/rollback are unused.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable

from ..agents import prompts
from ..agents.personas import persona
from ..agents.runner import AgentError, AgentRunner, extract_json
from ..config import settings

EmitFn = Callable[[str, str], None]


@dataclass
class RefineOutcome:
    text: str            # final artifact text (maker output)
    rounds: int          # number of revise rounds actually performed
    score: int           # final judge score 0-100 (-1 if not judged)
    stopped_reason: str  # threshold | max_rounds | critic_empty | rejected | disabled


async def _acritique(
    runner: AgentRunner, kind: str, artifact: str, criteria: str, cwd: Path | None, emit: EmitFn | None
) -> str:
    try:
        res = await runner.arun(
            prompts.critic_review(kind, artifact, criteria),
            system_prompt=persona("critic"),
            cwd=cwd,
        )
        data = extract_json(res.text)
    except AgentError:
        return ""
    issues = [str(i) for i in data.get("issues", [])]
    suggestions = [str(s) for s in data.get("suggestions", [])]
    reflection = str(data.get("reflection", ""))
    if not issues and not suggestions:
        return ""  # critic is satisfied -> nothing to act on
    if emit:
        head = "; ".join(suggestions[:4]) or "; ".join(issues[:4])
        emit("critic", f"{reflection}\n→ {head}".strip())
    parts = []
    if reflection:
        parts.append(f"Analyse : {reflection}")
    if issues:
        parts.append("Problèmes :\n" + "\n".join(f"- {i}" for i in issues))
    if suggestions:
        parts.append("Améliorations :\n" + "\n".join(f"- {s}" for s in suggestions))
    return "\n".join(parts)


async def _ajudge(
    runner: AgentRunner, kind: str, artifact: str, criteria: str, cwd: Path | None, emit: EmitFn | None
) -> int:
    threshold = settings.refine_quality_threshold
    try:
        res = await runner.arun(
            prompts.judge_quality(kind, artifact, criteria),
            system_prompt=persona("judge"),
            cwd=cwd,
        )
        data = extract_json(res.text)
    except AgentError:
        return threshold  # judge unavailable -> treat as pass, stop the loop
    try:
        score = int(data.get("score", threshold))
    except (TypeError, ValueError):
        score = threshold
    score = max(0, min(100, score))
    if emit:
        emit("judge", f"Score qualité {score}/100 — {data.get('verdict', '')}".strip())
    return score


async def arefine(
    runner: AgentRunner,
    *,
    role: str,
    kind: str,
    criteria: str,
    initial_text: str,
    revise: Callable[[str, str], Awaitable[str]],
    accept: Callable[[str], Awaitable[bool]] | None = None,
    rollback: Callable[[], Awaitable[None]] | None = None,
    cwd: Path | None = None,
    emit: EmitFn | None = None,
) -> RefineOutcome:
    """Run the refinement loop for `initial_text`. Returns the final artifact."""
    if not settings.refine_for(role):
        return RefineOutcome(initial_text, rounds=0, score=-1, stopped_reason="disabled")

    threshold = settings.refine_quality_threshold
    max_rounds = settings.refine_max_rounds
    current = initial_text

    score = await _ajudge(runner, kind, current, criteria, cwd, emit)
    rounds = 0
    while score < threshold and rounds < max_rounds:
        critique = await _acritique(runner, kind, current, criteria, cwd, emit)
        if not critique:
            return RefineOutcome(current, rounds, score, "critic_empty")
        revised = await revise(current, critique)
        if accept is not None and not await accept(revised):
            if rollback is not None:
                await rollback()
            if emit:
                emit("judge", "Révision rejetée (régression) — version précédente conservée.")
            return RefineOutcome(current, rounds, score, "rejected")
        current = revised
        rounds += 1
        score = await _ajudge(runner, kind, current, criteria, cwd, emit)

    reason = "threshold" if score >= threshold else "max_rounds"
    return RefineOutcome(current, rounds, score, reason)
