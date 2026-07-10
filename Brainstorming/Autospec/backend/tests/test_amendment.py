"""Tests for autospec.orchestrator.amendment — the safe spec-amendment proposer.

The amendment module proposes a MINIMAL fix to self-contradictory acceptance
criteria, then gates it behind an INDEPENDENT weakening check (different persona)
and marks it human-pending. Uses FakeRunner queued with JSON replies (no CLI).
"""

from __future__ import annotations

import json

import pytest

from autospec.agents.runner import AgentError, FakeRunner
from autospec.orchestrator import amendment as M


# --------------------------------------------------------------------------- #
# Schema shapes
# --------------------------------------------------------------------------- #

def test_amendment_schema_shape():
    assert set(M.AMENDMENT_SCHEMA) == {"target", "before", "after", "rationale"}
    target_spec = M.AMENDMENT_SCHEMA["target"]
    assert target_spec["choices"] == ["acceptance_criteria", "architecture", "constitution"]
    for field in ("target", "before", "after", "rationale"):
        assert M.AMENDMENT_SCHEMA[field].get("required") is True


def test_weakening_schema_shape():
    assert set(M.WEAKENING_SCHEMA) == {"weakens", "reason"}
    assert M.WEAKENING_SCHEMA["weakens"]["type"] is bool
    assert M.WEAKENING_SCHEMA["weakens"].get("required") is True
    assert M.WEAKENING_SCHEMA["reason"].get("required") is True


# --------------------------------------------------------------------------- #
# apropose_amendment
# --------------------------------------------------------------------------- #

async def test_apropose_amendment_returns_validated_proposal():
    proposal = {
        "target": "acceptance_criteria",
        "before": "AC-1: invalid -> 400. AC-3: invalid -> 200.",
        "after": "AC-1: invalid -> 400. (AC-3 removed as it contradicted AC-1)",
        "rationale": "AC-1 reflects the real intent; AC-3 was the accidental conflict.",
    }
    runner = FakeRunner([json.dumps(proposal)])
    out = await M.apropose_amendment(
        runner,
        story_title="Ambiguous validation story",
        acceptance="AC-1: invalid -> 400. AC-3: invalid -> 200.",
        failure_context="test fails: cannot return both 400 and 200",
    )
    assert out["target"] == "acceptance_criteria"
    assert out["before"] and out["after"] and out["rationale"]
    assert len(runner.calls) == 1
    assert runner.calls[0]["system_prompt"] == M.persona("architect")


async def test_apropose_amendment_invalid_target_then_valid_retries():
    invalid = {
        "target": "the_universe",  # not in choices
        "before": "x", "after": "y", "rationale": "z",
    }
    valid = {
        "target": "constitution",
        "before": "x", "after": "y", "rationale": "z",
    }
    runner = FakeRunner([json.dumps(invalid), json.dumps(valid)])
    out = await M.apropose_amendment(runner, story_title="S", acceptance="AC-1")
    assert out["target"] == "constitution"
    assert len(runner.calls) == 2


# --------------------------------------------------------------------------- #
# acheck_not_weakening
# --------------------------------------------------------------------------- #

async def test_acheck_returns_weakens_false():
    check = {"weakens": False, "reason": "The fix only reconciles a contradiction; scope preserved."}
    runner = FakeRunner([json.dumps(check)])
    out = await M.acheck_not_weakening(
        runner,
        before="AC-1: invalid -> 400. AC-3: invalid -> 200.",
        after="AC-1: invalid -> 400.",
        rationale="Removed the accidental conflicting criterion.",
    )
    assert out["weakens"] is False
    assert out["reason"]
    # uses the critic persona (independent from the architect proposer)
    assert runner.calls[0]["system_prompt"] == M.persona("critic")


async def test_acheck_returns_weakens_true():
    check = {"weakens": True, "reason": "The 'after' drops the error-handling requirement."}
    runner = FakeRunner([json.dumps(check)])
    out = await M.acheck_not_weakening(
        runner,
        before="Must validate and reject invalid input with 400.",
        after="Should accept input.",
        rationale="Simplify.",
    )
    assert out["weakens"] is True
    assert out["reason"]


# --------------------------------------------------------------------------- #
# apropose_safe_amendment — the gated orchestration
# --------------------------------------------------------------------------- #

async def test_safe_amendment_approved_when_not_weakening():
    proposal = {
        "target": "acceptance_criteria",
        "before": "AC-1: invalid -> 400. AC-3: invalid -> 200.",
        "after": "AC-1: invalid -> 400.",
        "rationale": "Remove the conflicting AC-3; keep the intended behaviour.",
    }
    check = {"weakens": False, "reason": "Contradiction resolved without reducing scope."}
    runner = FakeRunner([json.dumps(proposal), json.dumps(check)])
    out = await M.apropose_safe_amendment(
        runner,
        story_title="Story",
        acceptance="AC-1: invalid -> 400. AC-3: invalid -> 200.",
    )
    assert out is not None
    assert out["approved_safe"] is True
    assert out["weakening_reason"]
    assert out["target"] == "acceptance_criteria"
    # proposal + check = two calls
    assert len(runner.calls) == 2


async def test_safe_amendment_rejected_when_weakening():
    proposal = {
        "target": "acceptance_criteria",
        "before": "Must reject invalid input with 400 and log it.",
        "after": "May accept invalid input.",
        "rationale": "Make the story pass.",
    }
    check = {"weakens": True, "reason": "The amendment drops the rejection requirement."}
    runner = FakeRunner([json.dumps(proposal), json.dumps(check)])
    out = await M.apropose_safe_amendment(runner, story_title="Story", acceptance="...")
    assert out is not None
    assert out["approved_safe"] is False
    assert "drops" in out["weakening_reason"]


async def test_safe_amendment_returns_none_when_proposal_fails():
    # Never-valid JSON for the proposal (both attempts) -> AgentError caught -> None.
    runner = FakeRunner(["not json at all", "still not json"])
    out = await M.apropose_safe_amendment(runner, story_title="Story", acceptance="...")
    assert out is None


async def test_safe_amendment_fails_closed_when_check_fails():
    # Valid proposal, but the weakening check never yields valid JSON.
    proposal = {
        "target": "acceptance_criteria",
        "before": "x", "after": "y", "rationale": "z",
    }
    runner = FakeRunner([json.dumps(proposal), "garbage", "more garbage"])
    out = await M.apropose_safe_amendment(runner, story_title="Story", acceptance="...")
    assert out is not None
    # A broken safety check must never approve.
    assert out["approved_safe"] is False
    assert out["weakening_reason"]


# --------------------------------------------------------------------------- #
# prompts
# --------------------------------------------------------------------------- #

def test_proposal_prompt_includes_acceptance_and_intent():
    prompt = M.build_proposal_prompt(
        story_title="My Story",
        acceptance="AC-42: the widget must sparkle AND must not sparkle.",
        failure_context="cannot both sparkle and not sparkle",
        target_hint="likely acceptance_criteria",
    )
    assert "My Story" in prompt
    assert "AC-42: the widget must sparkle AND must not sparkle." in prompt
    assert "cannot both sparkle and not sparkle" in prompt
    assert "likely acceptance_criteria" in prompt
    # minimal, non-weakening intent is spelled out
    assert "minimal" in prompt.lower()
    low = prompt.lower()
    assert "weaken" in low or "reducing what the product" in low or "reduce" in low
    for t in M.TARGETS:
        assert t in prompt


def test_weakening_prompt_includes_before_after():
    prompt = M.build_weakening_prompt(
        before="Must reject invalid input with 400.",
        after="Should accept input.",
        rationale="Simplify the flow.",
    )
    assert "Must reject invalid input with 400." in prompt
    assert "Should accept input." in prompt
    assert "Simplify the flow." in prompt
    low = prompt.lower()
    assert "weaken" in low
    # the safe-default bias is present
    assert "when in doubt" in low or "default to" in low


def test_proposal_prompt_truncates_long_inputs():
    huge = "x" * 50_000
    prompt = M.build_proposal_prompt(
        story_title="S",
        acceptance=huge,
        failure_context=huge,
    )
    assert "truncated" in prompt
    assert len(prompt) < 20_000
