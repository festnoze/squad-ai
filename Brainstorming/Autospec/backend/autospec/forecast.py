"""Iteration cost forecast (O2): estimate the cost of a project's pending stories
from its own per-story history, falling back to a cross-project average."""

from __future__ import annotations

from .models import ProjectState, StoryStatus

_PENDING = (
    StoryStatus.TODO,
    StoryStatus.RED,
    StoryStatus.IN_PROGRESS,
    StoryStatus.GREEN,
)


def forecast_iteration_cost(state: ProjectState, fallback_cost_per_story: float = 0.0) -> dict:
    """Estimate the remaining cost: per-story cost (this project's history, else a
    fallback average) times the number of pending stories."""
    done = sum(1 for st in state.stories if st.status == StoryStatus.DONE)
    pending = sum(1 for st in state.stories if st.status in _PENDING)
    if done and state.usage.cost_usd > 0:
        per_story = state.usage.cost_usd / done
        based_on = "history"
    else:
        per_story = max(0.0, fallback_cost_per_story)
        based_on = "fallback"
    return {
        "cost_per_story": round(per_story, 4),
        "pending_stories": pending,
        "forecast_usd": round(per_story * pending, 4),
        "based_on": based_on,
    }
