"""Tests of the iteration cost forecast (O2)."""

from autospec.forecast import forecast_iteration_cost
from autospec.models import ProjectState, StoryStatus, UserStory


def _story(sid, status):
    return UserStory(id=sid, epic_id="E", title="t", status=status)


def test_forecast_from_history():
    state = ProjectState(id="a", name="a", goal="g", stories=[
        _story("1", StoryStatus.DONE),
        _story("2", StoryStatus.DONE),
        _story("3", StoryStatus.TODO),
        _story("4", StoryStatus.TODO),
    ])
    state.usage.cost_usd = 2.0
    f = forecast_iteration_cost(state)
    assert f["cost_per_story"] == 1.0
    assert f["pending_stories"] == 2
    assert f["forecast_usd"] == 2.0
    assert f["based_on"] == "history"


def test_forecast_fallback_when_no_history():
    state = ProjectState(id="b", name="b", goal="g", stories=[_story("1", StoryStatus.TODO)])
    f = forecast_iteration_cost(state, fallback_cost_per_story=0.5)
    assert f["cost_per_story"] == 0.5
    assert f["pending_stories"] == 1
    assert f["forecast_usd"] == 0.5
    assert f["based_on"] == "fallback"


def test_forecast_no_pending():
    state = ProjectState(id="c", name="c", goal="g", stories=[_story("1", StoryStatus.DONE)])
    state.usage.cost_usd = 1.0
    f = forecast_iteration_cost(state)
    assert f["pending_stories"] == 0
    assert f["forecast_usd"] == 0.0
