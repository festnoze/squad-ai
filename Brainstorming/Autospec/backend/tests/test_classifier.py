"""Tests for autospec.orchestrator.classifier — boss-tier root-cause triage."""

from __future__ import annotations

import json

import pytest

from autospec.agents.runner import AgentError, FakeRunner
from autospec.orchestrator import classifier as C
from autospec.orchestrator.recovery import AMEND_PROPOSAL, ARBITRATE, FAIL, SPLIT


# --------------------------------------------------------------------------- #
# VERDICT_TO_ACTION routing
# --------------------------------------------------------------------------- #

def test_verdict_to_action_maps_all_four():
    assert C.VERDICT_TO_ACTION == {
        "too_big": SPLIT,
        "wrong_test": ARBITRATE,
        "spec_contradiction": AMEND_PROPOSAL,
        "genuinely_hard": FAIL,
    }
    # Every schema choice is routable.
    choices = C.CLASSIFY_SCHEMA["verdict"]["choices"]
    assert set(choices) == set(C.VERDICT_TO_ACTION)


# --------------------------------------------------------------------------- #
# build_prompt
# --------------------------------------------------------------------------- #

def test_build_prompt_includes_title_and_acceptance():
    prompt = C.build_prompt(
        story_title="Add password reset flow",
        acceptance="AC1: user receives a reset email within 30s.",
        failure_signatures=["AssertionError: no email sent"],
    )
    assert "Add password reset flow" in prompt
    assert "AC1: user receives a reset email within 30s." in prompt
    assert "AssertionError: no email sent" in prompt


def test_build_prompt_truncates_long_inputs():
    huge = "x" * 50000
    prompt = C.build_prompt(story_title="s", acceptance=huge, impl_diff=huge)
    assert "truncated" in prompt
    # Bounded: nowhere near the raw 100k of inputs.
    assert len(prompt) < 30000


# --------------------------------------------------------------------------- #
# aclassify
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_aclassify_valid_verdict_and_routing():
    runner = FakeRunner()
    runner.queue(json.dumps({
        "verdict": "too_big",
        "reason": "The story bundles auth, email and templating.",
        "confidence": 0.8,
    }))
    result = await C.aclassify(runner, story_title="Big story", acceptance="lots")

    assert result["verdict"] == "too_big"
    assert C.VERDICT_TO_ACTION[result["verdict"]] == SPLIT
    # Ran the classifier persona.
    assert "root-cause" in runner.calls[0]["system_prompt"].lower() or \
        "classif" in runner.calls[0]["system_prompt"].lower()


@pytest.mark.asyncio
async def test_aclassify_invalid_then_valid_retries():
    runner = FakeRunner()
    # First reply: bad verdict choice → arun_json re-prompts.
    runner.queue(json.dumps({"verdict": "explode", "reason": "nope"}))
    runner.queue(json.dumps({"verdict": "wrong_test", "reason": "test asserts the wrong field."}))

    result = await C.aclassify(runner, story_title="Story", acceptance="ac")

    assert result["verdict"] == "wrong_test"
    assert C.VERDICT_TO_ACTION[result["verdict"]] == ARBITRATE
    assert len(runner.calls) == 2  # one retry consumed


@pytest.mark.asyncio
async def test_aclassify_propagates_agenterror_when_unrecoverable():
    runner = FakeRunner()
    runner.queue(json.dumps({"verdict": "explode", "reason": "bad"}))
    runner.queue(json.dumps({"verdict": "still_bad", "reason": "bad"}))
    with pytest.raises(AgentError):
        await C.aclassify(runner, story_title="Story")
