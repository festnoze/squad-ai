"""Tests of push notifications (U3): the pipeline emits `notify` events on the
event bus at key milestones (build done, error, budget reached, resume scheduled)."""

from autospec.agents.runner import FakeRunner
from autospec.models import ProjectState
from autospec.orchestrator.events import bus
from autospec.orchestrator.pipeline import Pipeline


def _drain(q):
    # The bus queues carry (seq, event) tuples; tests only care about the event.
    out = []
    while not q.empty():
        _seq, event = q.get_nowait()
        out.append(event)
    return out


def test_notify_publishes_event():
    state = ProjectState(id="p-notif", name="proj", goal="g")
    pipeline = Pipeline(state, FakeRunner([]))
    q = bus.subscribe()
    try:
        pipeline._notify("success", "Titre", "corps")
        events = _drain(q)
    finally:
        bus.unsubscribe(q)
    notifs = [e for e in events if e.get("type") == "notify"]
    assert len(notifs) == 1
    e = notifs[0]
    assert e["level"] == "success"
    assert e["title"] == "Titre"
    assert e["body"] == "corps"
    assert e["project_id"] == "p-notif"


def test_budget_reached_emits_notify():
    state = ProjectState(id="p-notif2", name="proj", goal="g", budget_usd=0.01)
    state.usage.cost_usd = 0.02
    pipeline = Pipeline(state, FakeRunner([]))
    q = bus.subscribe()
    try:
        pipeline._enforce_budget()
        events = _drain(q)
    finally:
        bus.unsubscribe(q)
    notifs = [e for e in events if e.get("type") == "notify"]
    assert any(e["level"] == "warning" and "Budget" in e["title"] for e in notifs)
