"""Wave 2 integration: the wrong-test arbitration recovery path in the pipeline
(the arbiter/classifier modules themselves are covered in test_arbitration.py /
test_classifier.py)."""

from __future__ import annotations

import json

from autospec.agents.runner import FakeRunner
from autospec.config import settings as cfg
from autospec.models import AcceptanceCriterion, ProjectState, StoryStatus, UserStory
from autospec.orchestrator import workspace
from autospec.orchestrator.pipeline import Pipeline


def _story():
    return UserStory(
        id="US-1", epic_id="E-1", title="feature",
        acceptance_criteria=[AcceptanceCriterion(id="AC1", text="returns 42")],
    )


def _pipeline(pid, replies):
    state = ProjectState(id=pid, name="g", goal="g")
    pipeline = Pipeline(state, FakeRunner(list(replies)))
    ws = workspace.scaffold(state)
    (ws / "tests").mkdir(parents=True, exist_ok=True)
    (ws / "tests" / "test_feat.py").write_text(
        "def test_it():\n    assert real() == 99  # wrong per AC\n", encoding="utf-8"
    )
    return pipeline, ws


async def test_arbitration_fix_test_recovers_story(monkeypatch):
    monkeypatch.setattr(cfg, "dispute_escalation_enabled", True)
    monkeypatch.setattr(cfg, "arbitration_max", 1)
    ruling = json.dumps({
        "verdict": "fix_test", "reason": "test asserts 99 but AC says 42",
        "instructions": "assert real() == 42",
    })
    qa_fix = json.dumps({"summary": "corrected the assertion to 42"})
    pipeline, ws = _pipeline("p-arb1", [ruling, qa_fix])

    async def green_pytest(self, ws=None):
        return True, "1 passed", {"tests/test_feat.py::test_it": "passed"}

    monkeypatch.setattr(Pipeline, "_arun_pytest", green_pytest)

    story = _story()
    recovered = await pipeline._amaybe_arbitrate_wrong_test(story, ws, "pkg", "AssertionError", False)
    assert recovered is True
    assert story.status == StoryStatus.DONE


async def test_arbitration_fix_impl_does_not_recover(monkeypatch):
    monkeypatch.setattr(cfg, "dispute_escalation_enabled", True)
    ruling = json.dumps({
        "verdict": "fix_impl", "reason": "the test is right; code is wrong",
        "instructions": "make real() return 42",
    })
    pipeline, ws = _pipeline("p-arb2", [ruling])
    story = _story()
    recovered = await pipeline._amaybe_arbitrate_wrong_test(story, ws, "pkg", "AssertionError", False)
    assert recovered is False
    assert story.status != StoryStatus.DONE


async def test_arbitration_spec_contradiction_flags_for_amendment(monkeypatch):
    monkeypatch.setattr(cfg, "dispute_escalation_enabled", True)
    ruling = json.dumps({
        "verdict": "spec_contradiction", "reason": "AC1 and AC2 conflict",
        "instructions": "reconcile the criteria",
    })
    pipeline, ws = _pipeline("p-arb3", [ruling])
    story = _story()
    recovered = await pipeline._amaybe_arbitrate_wrong_test(story, ws, "pkg", "err", False)
    assert recovered is False
    assert "contradiction de spec" in story.last_error


async def test_arbitration_disabled_is_noop(monkeypatch):
    monkeypatch.setattr(cfg, "dispute_escalation_enabled", False)
    pipeline, ws = _pipeline("p-arb4", [])
    story = _story()
    assert await pipeline._amaybe_arbitrate_wrong_test(story, ws, "pkg", "err", False) is False


async def test_arbitration_bounded_by_max(monkeypatch):
    monkeypatch.setattr(cfg, "dispute_escalation_enabled", True)
    monkeypatch.setattr(cfg, "arbitration_max", 1)
    # fix_impl ruling (no recovery), consumes the single allowed arbitration.
    ruling = json.dumps({"verdict": "fix_impl", "reason": "r", "instructions": "i"})
    pipeline, ws = _pipeline("p-arb5", [ruling])
    story = _story()
    await pipeline._amaybe_arbitrate_wrong_test(story, ws, "pkg", "err", False)
    # Second call is over the cap → no runner call, returns False immediately.
    assert await pipeline._amaybe_arbitrate_wrong_test(story, ws, "pkg", "err", False) is False


async def test_arbitration_frontend_skipped(monkeypatch):
    monkeypatch.setattr(cfg, "dispute_escalation_enabled", True)
    pipeline, ws = _pipeline("p-arb6", [])
    story = _story()
    assert await pipeline._amaybe_arbitrate_wrong_test(story, ws, "pkg", "err", True) is False
