"""Factory-wide metrics aggregation (U2): success rate, cost per story, average
attempts / quality / mutation / coverage across all projects."""

from __future__ import annotations

from .models import ProjectState, StoryStatus


def _avg(values: list) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


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
    }
