"""Factory-wide metrics aggregation (U2): success rate, cost per story, average
attempts / quality / mutation / coverage across all projects, plus the P3
fusion-loop block (GENERATION_FUSION_REVIEW §8) that makes the cost of the
merge/canary loop readable from the outside."""

from __future__ import annotations

from collections.abc import Iterable

from .models import ProjectState, StoryStatus

# P3 (GENERATION_FUSION_REVIEW §8): the scalar fusion-loop counters carried by
# models.PlanCalibration, per iteration. Read with getattr defaults so a state
# written before P3 (or before any single counter) aggregates as zero instead
# of raising.
FUSION_COUNTERS: tuple[str, ...] = (
    "suite_runs",
    "items_delivered",
    "canary_reverts",
    "canary_batches",
    "canary_bisect_reverts",
    "merge_requeues",
    "requeue_refunds",
    "infra_retries",
    "p2b_resumes",
    "orphan_resets",
)


def _avg(values: list) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def fusion_snapshot(calibrations: Iterable) -> dict:
    """P3: sum the fusion-loop counters of a set of per-iteration calibrations.

    ``suites_per_item`` is recomputed from the SUMS (not averaged from the
    per-iteration model property) so the ratio stays exact across iterations and
    projects; its denominator floors at 1, so it is safe before anything is
    delivered. ``canary_verdicts`` is a histogram merged key by key, and it is
    open: an unknown verdict simply adds a key.

    Note: ``suite_runs`` counts suites REQUESTED (one per runner call), not
    operating-system processes - a flaky rerun or the frontend build inside the
    same call does not add a unit.
    """
    totals: dict = dict.fromkeys(FUSION_COUNTERS, 0)
    verdicts: dict[str, int] = {}
    for calibration in calibrations:
        for name in FUSION_COUNTERS:
            totals[name] += getattr(calibration, name, 0) or 0
        for verdict, count in (getattr(calibration, "canary_verdicts", None) or {}).items():
            verdicts[verdict] = verdicts.get(verdict, 0) + (count or 0)
    totals["canary_verdicts"] = verdicts
    totals["suites_per_item"] = round(totals["suite_runs"] / max(1, totals["items_delivered"]), 2)
    return totals


def compute_metrics(states: list[ProjectState]) -> dict:
    """Aggregate cross-project factory metrics from a list of project states."""
    stories = [st for s in states for st in s.stories]
    total = len(stories)
    done = sum(1 for st in stories if st.status == StoryStatus.DONE)
    failed = sum(1 for st in stories if st.status == StoryStatus.FAILED)
    total_cost = sum(s.usage.cost_usd for s in states)
    quality = [st.quality_score for st in stories if st.quality_score >= 0]
    mutation = [st.mutation_score for st in stories if getattr(st, "mutation_score", -1) >= 0]
    coverage = [st.coverage_score for st in stories if getattr(st, "coverage_score", -1) >= 0]
    attempts = [st.attempts for st in stories if st.attempts > 0]
    return {
        "projects": len(states),
        "total_cost_usd": round(total_cost, 4),
        "total_tokens": sum(s.usage.input_tokens + s.usage.output_tokens for s in states),
        "total_agent_calls": sum(s.usage.agent_calls for s in states),
        "total_stories": total,
        "stories_done": done,
        "stories_failed": failed,
        "success_rate": round(100 * done / total) if total else 0,
        "avg_attempts": _avg(attempts) or 0,
        "cost_per_story": round(total_cost / done, 4) if done else 0.0,
        "avg_quality": _avg(quality),
        "avg_mutation": _avg(mutation),
        "avg_coverage": _avg(coverage),
        "findings": sum(len(s.findings) for s in states),
        "regressions": sum(len(s.regressions) for s in states),
        # P3: fusion-loop observability, flattened over every project AND every
        # iteration (ProjectState.calibration is a dict[int, PlanCalibration]).
        "fusion": fusion_snapshot(
            calibration
            for state in states
            for calibration in (getattr(state, "calibration", None) or {}).values()
        ),
    }
