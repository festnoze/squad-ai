"""Tests for autospec.orchestrator.arbitration — the boss-tier wrong-test arbiter.

The arbiter rules on a disputed failing test, grounded in the acceptance criteria
rather than the test as written. Uses FakeRunner queued with JSON replies (no CLI).
"""

from __future__ import annotations

import json

import pytest

from autospec.agents.runner import AgentError, FakeRunner
from autospec.orchestrator import arbitration as A


# --------------------------------------------------------------------------- #
# ARBITER_SCHEMA shape
# --------------------------------------------------------------------------- #

def test_schema_has_required_fields_and_verdict_choices():
    assert set(A.ARBITER_SCHEMA) == {"verdict", "reason", "instructions"}
    verdict_spec = A.ARBITER_SCHEMA["verdict"]
    assert verdict_spec["choices"] == ["fix_impl", "fix_test", "spec_contradiction"]
    for field in ("verdict", "reason", "instructions"):
        assert A.ARBITER_SCHEMA[field].get("required") is True


# --------------------------------------------------------------------------- #
# aarbitrate_test — the three verdicts
# --------------------------------------------------------------------------- #

async def test_fix_test_verdict_returns_instructions():
    ruling = {
        "verdict": "fix_test",
        "reason": "The test asserts a 404 but the criteria require a 400.",
        "instructions": "Change the test to assert HTTP 400 per acceptance criterion AC-2.",
    }
    runner = FakeRunner([json.dumps(ruling)])
    out = await A.aarbitrate_test(
        runner,
        story_title="Reject invalid signup payloads",
        acceptance="AC-2: an invalid payload returns HTTP 400.",
        test_source="assert resp.status_code == 404",
        failure_output="assert 400 == 404",
        impl_diff="+ return Response(status=400)",
    )
    assert out["verdict"] == "fix_test"
    assert out["instructions"]  # non-empty, actionable
    assert "400" in out["instructions"]
    assert len(runner.calls) == 1


async def test_fix_impl_verdict():
    ruling = {
        "verdict": "fix_impl",
        "reason": "The test correctly encodes AC-1; the handler returns the wrong code.",
        "instructions": "Make the handler return HTTP 400 for invalid payloads.",
    }
    runner = FakeRunner([json.dumps(ruling)])
    out = await A.aarbitrate_test(
        runner,
        story_title="Reject invalid signup payloads",
        acceptance="AC-1: an invalid payload returns HTTP 400.",
        test_source="assert resp.status_code == 400",
        failure_output="assert 200 == 400",
    )
    assert out["verdict"] == "fix_impl"
    assert out["reason"]
    assert out["instructions"]


async def test_spec_contradiction_verdict():
    ruling = {
        "verdict": "spec_contradiction",
        "reason": "AC-1 requires 400 while AC-3 requires 200 for the same input.",
        "instructions": "Resolve the conflict between AC-1 and AC-3 before any test can pass.",
    }
    runner = FakeRunner([json.dumps(ruling)])
    out = await A.aarbitrate_test(
        runner,
        story_title="Ambiguous validation story",
        acceptance="AC-1: invalid -> 400. AC-3: invalid -> 200.",
        test_source="assert resp.status_code == 400",
        failure_output="assert 200 == 400",
    )
    assert out["verdict"] == "spec_contradiction"
    assert out["instructions"]


# --------------------------------------------------------------------------- #
# retry via arun_json
# --------------------------------------------------------------------------- #

async def test_invalid_verdict_then_valid_retries_and_succeeds():
    invalid = {
        "verdict": "delete_test",  # not in choices
        "reason": "nuke it",
        "instructions": "remove the test",
    }
    valid = {
        "verdict": "fix_test",
        "reason": "The assertion goes beyond AC-2.",
        "instructions": "Assert only the status code required by AC-2, nothing more.",
    }
    runner = FakeRunner([json.dumps(invalid), json.dumps(valid)])
    out = await A.aarbitrate_test(
        runner,
        story_title="Story",
        acceptance="AC-2: returns 400.",
        test_source="assert body == 'exactly this'",
    )
    assert out["verdict"] == "fix_test"
    assert len(runner.calls) == 2
    # The retry prompt carries the schema/validation feedback.
    retry_prompt = runner.calls[1]["prompt"]
    assert "previous reply was invalid" in retry_prompt


async def test_uses_arbiter_persona_as_system_prompt():
    runner = FakeRunner(['{"verdict": "fix_impl", "reason": "r", "instructions": "i"}'])
    await A.aarbitrate_test(runner, story_title="S", acceptance="AC-1", model="m", cwd=None)
    assert runner.calls[0]["system_prompt"] == A.persona("arbiter")
    assert runner.calls[0]["model"] == "m"


async def test_agenterror_propagates_when_never_valid():
    runner = FakeRunner([
        '{"verdict": "bogus", "reason": "r", "instructions": "i"}',
        '{"verdict": "still_bogus", "reason": "r", "instructions": "i"}',
    ])
    with pytest.raises(AgentError):
        await A.aarbitrate_test(runner, story_title="S", acceptance="AC-1")


# --------------------------------------------------------------------------- #
# build_prompt
# --------------------------------------------------------------------------- #

def test_build_prompt_includes_acceptance_and_test_source():
    prompt = A.build_prompt(
        story_title="My Story",
        acceptance="AC-42: the widget must sparkle.",
        test_source="assert widget.sparkles is True",
        failure_output="AttributeError: no attribute 'sparkles'",
        impl_diff="+ self.sparkles = False",
    )
    assert "My Story" in prompt
    assert "AC-42: the widget must sparkle." in prompt
    assert "assert widget.sparkles is True" in prompt
    # criteria framed as the ground truth, all three verdicts mentioned
    assert "ground truth" in prompt.lower()
    for v in ("fix_impl", "fix_test", "spec_contradiction"):
        assert v in prompt
    # the never-delete invariant is spelled out
    assert "delete" in prompt.lower()
    # executed-facts invariant is present
    assert "never overruled" in prompt.lower() or "executed fact" in prompt.lower()


def test_build_prompt_truncates_long_inputs():
    huge = "x" * 50_000
    prompt = A.build_prompt(
        story_title="S",
        acceptance="AC-1",
        test_source=huge,
        failure_output=huge,
        impl_diff=huge,
    )
    assert "truncated" in prompt
    # The prompt stays bounded, nowhere near 3x50k chars.
    assert len(prompt) < 40_000
