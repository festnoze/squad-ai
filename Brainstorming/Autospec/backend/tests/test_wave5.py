"""Wave 5 tests: human-gated amendment wiring, arbitration->lessons, and the
per-model scorecard (the amendment module itself is in test_amendment.py)."""

from __future__ import annotations

import json

from autospec.agents.runner import FakeRunner
from autospec.config import settings as cfg
from autospec.models import AcceptanceCriterion, ProjectState, UserStory
from autospec.orchestrator import scorecard, workspace
from autospec.orchestrator.pipeline import Pipeline


def _story():
    return UserStory(
        id="US-1", epic_id="E-1", title="feature",
        acceptance_criteria=[AcceptanceCriterion(id="AC1", text="returns 42")],
    )


def _pipeline(pid, replies):
    state = ProjectState(id=pid, name="g", goal="g")
    pipeline = Pipeline(state, FakeRunner(list(replies)))
    workspace.scaffold(state)
    return pipeline


# --------------------------------------------------------------------------- #
# W5.1 — human-gated amendment                                                 #
# --------------------------------------------------------------------------- #

async def test_amendment_safe_queued_human_pending(monkeypatch):
    monkeypatch.setattr(cfg, "design_amendment_enabled", True)
    monkeypatch.setattr(cfg, "amendment_auto", False)
    monkeypatch.setattr(cfg, "amendment_max_depth", 1)
    proposal = json.dumps({
        "target": "acceptance_criteria", "before": "AC1 & AC2 conflict",
        "after": "AC1 clarified", "rationale": "remove the contradiction",
    })
    weakening = json.dumps({"weakens": False, "reason": "scope preserved"})
    pipeline = _pipeline("p-w5a", [proposal, weakening])
    story = _story()
    await pipeline._amaybe_propose_amendment(story, "AC1: returns 42", "contradiction")
    assert len(pipeline.state.pending_amendments) == 1
    assert pipeline.state.pending_amendments[0]["approved_safe"] is True


async def test_amendment_weakening_rejected(monkeypatch):
    monkeypatch.setattr(cfg, "design_amendment_enabled", True)
    monkeypatch.setattr(cfg, "amendment_max_depth", 1)
    proposal = json.dumps({
        "target": "acceptance_criteria", "before": "must validate input",
        "after": "skip validation", "rationale": "make it pass",
    })
    weakening = json.dumps({"weakens": True, "reason": "drops a real requirement"})
    pipeline = _pipeline("p-w5b", [proposal, weakening])
    story = _story()
    await pipeline._amaybe_propose_amendment(story, "AC1", "contradiction")
    # Recorded (for the audit trail) but flagged unsafe — never applied.
    assert pipeline.state.pending_amendments[0]["approved_safe"] is False


async def test_amendment_disabled_noop(monkeypatch):
    monkeypatch.setattr(cfg, "design_amendment_enabled", False)
    pipeline = _pipeline("p-w5c", [])
    await pipeline._amaybe_propose_amendment(_story(), "AC1", "reason")
    assert pipeline.state.pending_amendments == []


# --------------------------------------------------------------------------- #
# W5.6 — arbitration -> lessons                                                #
# --------------------------------------------------------------------------- #

def test_arbitration_lesson_recorded():
    pipeline = _pipeline("p-w5d", [])
    pipeline._record_arbitration_lesson()
    assert any("FAUX" in l or "critères" in l for l in pipeline.state.lessons)
    # idempotent — not duplicated
    pipeline._record_arbitration_lesson()
    assert len([l for l in pipeline.state.lessons if "critères" in l]) == 1


# --------------------------------------------------------------------------- #
# W5.2 — per-model scorecard from the timeline                                 #
# --------------------------------------------------------------------------- #

def test_model_scorecard_attributes_outcomes():
    events = [
        {"kind": "agent", "role": "dev", "item": "US-1", "model": "cheap", "ok": True},
        {"kind": "pytest", "item": "US-1", "ok": True},                      # cheap: green@1
        {"kind": "agent", "role": "dev", "item": "US-2", "model": "cheap", "ok": True},
        {"kind": "pytest", "item": "US-2", "ok": False},                     # cheap failed US-2
        {"kind": "escalate", "item": "US-2", "model": "boss"},
        {"kind": "agent", "role": "dev", "item": "US-2", "model": "boss", "ok": True},
        {"kind": "pytest", "item": "US-2", "ok": True},
    ]
    scores = scorecard.model_scorecard(events)
    # US-2's FIRST dev attempt was on "cheap", so its outcome attributes to cheap.
    assert scores["cheap"].dev_stories == 2
    assert scores["cheap"].green_at_first == 1      # US-1 only
    assert scores["cheap"].green_eventually == 2    # US-2 eventually green (any pass)
    assert abs(scores["cheap"].green_at_1_rate - 0.5) < 1e-6
