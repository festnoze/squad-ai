"""Infra vs dev attempts: a transient provider/CLI failure (AgentError that is
not a usage-limit) refunds the dev attempt and consumes a SEPARATE infra budget
(`AUTOSPEC_INFRA_MAX_RETRIES`) — infra flakiness alone can never FAIL an item,
never consumes dev attempts, and never triggers the adaptive split."""

import asyncio

import pytest

from autospec.agents.runner import AgentError
from autospec.agents.scripted import ScriptedRunner
from autospec.config import settings
from autospec.models import Epic, PipelinePhase, ProjectState, StoryStatus, Stream, StreamKind, UserStory
from autospec.orchestrator import session_monitor
from autospec.orchestrator.pipeline import Pipeline


def _state(stories, project_id="infra-proj"):
    st = ProjectState(id=project_id, name="infraapp", goal="g")
    st.epics.append(Epic(id="EPIC-1", title="E"))
    st.streams = [Stream(id="backend", kind=StreamKind.BACKEND, language="python", primary=True)]
    st.stories = stories
    return st


def _us(sid):
    return UserStory(
        id=sid, epic_id="EPIC-1", title=sid, stream="backend",
        gherkin="Feature: F\n  Scenario: S\n    Given a\n    When b\n    Then c",
    )


@pytest.fixture
def streams_setup(monkeypatch):
    monkeypatch.setattr(settings, "streams_enabled", True)
    monkeypatch.setattr(settings, "fake_agents", True)
    monkeypatch.setattr(settings, "split_on_failure_enabled", True)


async def test_transient_infra_error_is_retried_then_succeeds(streams_setup, monkeypatch):
    """Two AgentErrors then green: the story ships, the dev attempts were
    refunded (only the successful run counts) and the infra budget was used."""
    monkeypatch.setattr(settings, "dev_max_attempts", 1)
    monkeypatch.setattr(settings, "infra_max_retries", 2)
    state = _state([_us("US-1")])
    pipeline = Pipeline(state, ScriptedRunner())
    calls = []

    async def _flaky(subject, worktree, pkg, is_frontend):
        calls.append(subject.id)
        if len(calls) <= 2:
            raise AgentError("claude CLI exited with 1073807364")
        return True, ""

    monkeypatch.setattr(pipeline, "_arun_item_dev", _flaky)
    await asyncio.wait_for(pipeline._abuild_phase(), timeout=40)

    story = state.story("US-1")
    assert story.status == StoryStatus.DONE
    assert len(calls) == 3
    assert story.attempts == 1        # only the real (green) run consumed a dev attempt
    assert story.infra_attempts == 2  # the two crashes hit the infra budget


async def test_infra_budget_exhausted_fails_without_split(streams_setup, monkeypatch):
    """Persistent infra failure: the item ends FAILED once the infra budget is
    exhausted — with dev attempts intact and NO adaptive split (a crash is not
    a sizing problem)."""
    monkeypatch.setattr(settings, "dev_max_attempts", 3)
    monkeypatch.setattr(settings, "infra_max_retries", 1)
    state = _state([_us("US-1")], project_id="infra-fail")
    pipeline = Pipeline(state, ScriptedRunner())
    split_calls = []

    async def _always_down(subject, worktree, pkg, is_frontend):
        raise AgentError("provider unreachable")

    async def _spy_split(item, subject, target, *, force=False):
        split_calls.append(item.id)
        return False

    monkeypatch.setattr(pipeline, "_arun_item_dev", _always_down)
    monkeypatch.setattr(pipeline, "_amaybe_split_on_failure", _spy_split)
    await asyncio.wait_for(pipeline._abuild_phase(), timeout=40)

    story = state.story("US-1")
    assert story.status == StoryStatus.FAILED
    assert story.infra_attempts == 2  # initial try + 1 retry, then budget out
    assert story.attempts == 0        # every dev attempt was refunded
    assert split_calls == []          # infra failure never triggers a split
    assert "provider unreachable" in story.last_error


def test_claude_session_limit_messages_are_usage_limit_errors():
    samples = [
        "You've hit your session limit · resets 2:40am (Europe/Paris)",
        '{"status":429,"message":"rate limited"}',
        "SessionEnd hook failed after Claude usage limit",
    ]

    assert all(session_monitor.is_usage_limit_error(text) for text in samples)


async def test_claude_session_limit_stops_retryable_without_split(streams_setup, monkeypatch):
    monkeypatch.setattr(settings, "dev_max_attempts", 1)
    monkeypatch.setattr(settings, "infra_max_retries", 1)
    state = _state([_us("US-1")], project_id="claude-limit")
    pipeline = Pipeline(state, ScriptedRunner())
    split_calls = []

    async def _session_limited(subject, worktree, pkg, is_frontend):
        raise AgentError("You've hit your session limit · resets 2:40am (Europe/Paris)")

    async def _spy_split(item, subject, target, *, force=False):
        split_calls.append(item.id)
        return False

    monkeypatch.setattr(pipeline, "_arun_item_dev", _session_limited)
    monkeypatch.setattr(pipeline, "_amaybe_split_on_failure", _spy_split)
    await asyncio.wait_for(pipeline._abuild_phase(), timeout=40)

    story = state.story("US-1")
    assert story.status == StoryStatus.TODO
    assert story.attempts == 0
    assert story.infra_attempts == 0
    assert split_calls == []
    assert state.phase == PipelinePhase.NEEDS_ATTENTION
