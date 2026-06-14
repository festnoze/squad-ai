"""Tests of the factory metrics aggregation (U2)."""

from autospec.metrics import compute_metrics
from autospec.models import ProjectState, StoryStatus, UserStory


def test_compute_metrics_empty():
    m = compute_metrics([])
    assert m["projects"] == 0
    assert m["success_rate"] == 0
    assert m["avg_quality"] is None
    assert m["cost_per_story"] == 0.0


def test_compute_metrics_aggregates():
    s1 = ProjectState(
        id="a", name="a", goal="g",
        stories=[
            UserStory(id="US-1", epic_id="E", title="t", status=StoryStatus.DONE,
                      attempts=1, quality_score=80),
            UserStory(id="US-2", epic_id="E", title="t", status=StoryStatus.FAILED, attempts=2),
        ],
    )
    s1.usage.cost_usd = 1.0
    s1.usage.agent_calls = 5
    m = compute_metrics([s1])
    assert m["projects"] == 1
    assert m["total_stories"] == 2
    assert m["stories_done"] == 1
    assert m["stories_failed"] == 1
    assert m["success_rate"] == 50
    assert m["cost_per_story"] == 1.0
    assert m["avg_quality"] == 80
    assert m["avg_attempts"] == 1.5
    assert m["total_agent_calls"] == 5
