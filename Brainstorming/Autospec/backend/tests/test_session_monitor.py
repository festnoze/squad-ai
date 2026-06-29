"""Tests of the M2 usage-window watchdog: limit detection, reset-time parsing
(error epoch / ccusage blocks), clean stop + scheduled auto-resume, restart
re-arming and user cancellation."""

import json
import time

from autospec.agents.runner import AgentError, FakeRunner
from autospec.api import server
from autospec.config import settings
from autospec.models import PipelinePhase, ProjectState, StoryStatus
from autospec.orchestrator import session_monitor
from autospec.orchestrator.pipeline import Pipeline

from .conftest import wait_until

PM_BRIEF = json.dumps({"type": "brief", "message": "OK", "brief": "# Brief"})
PO_PLAN = json.dumps(
    {"epics": [{"id": "EPIC-1", "title": "E", "stories": [
        {"id": "US-1", "title": "S", "description": "d", "acceptance_criteria": ["c"],
         "gherkin": "Feature: F\n  Scenario: s\n    Given a\n    When b\n    Then c", "depends_on": []},
    ]}]}
)
QA_TRIVIAL = json.dumps({"message": "Trivial.", "tests": []})
DEV_GREEN = json.dumps({"status": "green", "summary": "ok", "files": [], "test_results": []})


# --------------------------------------------------------------- pure parsing

def test_is_usage_limit_error_patterns():
    assert session_monitor.is_usage_limit_error("Claude AI usage limit reached|1718226000")
    assert session_monitor.is_usage_limit_error("You've reached your usage limit")
    assert session_monitor.is_usage_limit_error("5-hour limit reached ∙ resets 3am")
    assert not session_monitor.is_usage_limit_error("FakeRunner has no queued reply")
    assert not session_monitor.is_usage_limit_error("claude CLI exited with 1: boom")


def test_parse_reset_epoch_seconds_and_millis():
    assert session_monitor.parse_reset_epoch("limit reached|1718226000") == 1718226000.0
    assert session_monitor.parse_reset_epoch("limit reached|1718226000000") == 1718226000.0
    assert session_monitor.parse_reset_epoch("no epoch here") is None


def test_parse_blocks_returns_active_block_end():
    payload = {
        "blocks": [
            {"isActive": False, "endTime": "2026-06-13T00:00:00Z"},
            {"isActive": True, "endTime": "2026-06-13T07:00:00+00:00"},
        ]
    }
    at = session_monitor.parse_blocks(payload)
    assert at is not None
    from datetime import datetime, timezone

    assert datetime.fromtimestamp(at, tz=timezone.utc).hour == 7
    assert session_monitor.parse_blocks({"blocks": []}) is None
    assert session_monitor.parse_blocks({}) is None
    assert session_monitor.parse_blocks({"blocks": [{"isActive": True}]}) is None


async def test_anext_reset_fallback(monkeypatch):
    monkeypatch.setattr(settings, "resume_fallback_min", 2.0)

    async def _no_block():
        return None

    monkeypatch.setattr(session_monitor, "aget_block_reset", _no_block)
    at = await session_monitor.anext_reset("usage limit reached (sans epoch)")
    assert 100 <= at - time.time() <= 130  # ~2 minutes


def test_monitor_active_gating(monkeypatch):
    monkeypatch.setattr(settings, "session_monitor_enabled", True)
    monkeypatch.setattr(settings, "agent_provider", "claude")
    monkeypatch.setattr(settings, "fake_agents", False)
    assert session_monitor.monitor_active()
    monkeypatch.setattr(settings, "agent_provider", "codex")
    assert not session_monitor.monitor_active()
    monkeypatch.setattr(settings, "agent_provider", "claude")
    monkeypatch.setattr(settings, "fake_agents", True)
    assert not session_monitor.monitor_active()


# --------------------------------------------------------- pipeline behaviour

class _LimitOnceRunner(FakeRunner):
    """Raises a usage-limit error on the FIRST dev call, then plays the queue."""

    def __init__(self, replies):
        super().__init__(replies)
        self.limit_fired = False

    async def arun(self, prompt, system_prompt, cwd=None, session_id=None, model=None):
        if "PROCESSUS OBLIGATOIRE" in prompt and not self.limit_fired:
            self.limit_fired = True
            # Far-future reset epoch: in production a usage window reopens minutes
            # or hours later, so the pipeline durably sits in STOPPED until then.
            # (A near-immediate epoch would collapse STOPPED straight back into
            # BUILD, racing any observation of the clean stop.)
            raise AgentError(f"Claude AI usage limit reached|{int(time.time()) + 3600}")
        return await super().arun(prompt, system_prompt, cwd=cwd, session_id=session_id)


def _enable_monitor(monkeypatch):
    monkeypatch.setattr(settings, "session_monitor_enabled", True)
    monkeypatch.setattr(settings, "agent_provider", "claude")
    monkeypatch.setattr(settings, "fake_agents", False)


async def test_usage_limit_stops_then_auto_resumes(monkeypatch, green_pytest):
    _enable_monitor(monkeypatch)
    state = ProjectState(id="proj-m2", name="todo", goal="g")
    # Two QA replies: the refunded attempt makes the resumed story go through
    # the QA design step again (attempts back to 0).
    runner = _LimitOnceRunner([PM_BRIEF, PO_PLAN, QA_TRIVIAL, QA_TRIVIAL, DEV_GREEN])
    pipeline = Pipeline(state, runner)
    pipeline.start()

    # The watchdog schedules the resume and the pipeline stops cleanly. With a
    # far reset window the STOPPED state is durable, so observing it is reliable.
    await wait_until(lambda: state.resume_at > 0)
    await wait_until(lambda: state.phase == PipelinePhase.STOPPED)
    story = state.story("US-1")
    assert story.status == StoryStatus.TODO
    assert story.attempts == 0  # the lost attempt was refunded
    assert any("Fenêtre d'usage Claude épuisée" in m.content for m in state.chat)
    assert pipeline._resume_timer is not None  # auto-resume armed

    # Fire the armed timer now instead of waiting out the reset window (the
    # wall-clock sleep itself is covered by test_anext_reset): it resumes the
    # build to completion in a fresh session.
    pipeline._resume_timer.cancel()
    await pipeline._aresume_timer(0.0)
    await wait_until(lambda: state.phase == PipelinePhase.DONE)
    assert state.resume_at == 0.0
    assert state.story("US-1").status == StoryStatus.DONE
    assert any("Nouvelle fenêtre d'usage disponible" in m.content for m in state.chat)


async def test_usage_limit_ignored_for_other_providers(monkeypatch, green_pytest):
    monkeypatch.setattr(settings, "session_monitor_enabled", True)
    monkeypatch.setattr(settings, "agent_provider", "codex")
    monkeypatch.setattr(settings, "fake_agents", False)
    monkeypatch.setattr(settings, "dev_max_attempts", 1)
    state = ProjectState(id="proj-m2-off", name="todo", goal="g")

    class _AlwaysLimited(FakeRunner):
        async def arun(self, prompt, system_prompt, cwd=None, session_id=None, model=None):
            if "PROCESSUS OBLIGATOIRE" in prompt:
                raise AgentError("usage limit reached|1718226000")
            return await super().arun(prompt, system_prompt, cwd=cwd, session_id=session_id)

    pipeline = Pipeline(state, _AlwaysLimited([PM_BRIEF, PO_PLAN, QA_TRIVIAL]))
    pipeline.start()
    await wait_until(lambda: state.phase == PipelinePhase.DONE)
    # No watchdog for non-claude providers: no schedule, normal error handling
    # (the attempt is consumed and the story fails after dev_max_attempts).
    assert state.resume_at == 0.0
    assert pipeline._resume_timer is None
    assert state.story("US-1").status == StoryStatus.FAILED


async def test_cancel_resume(monkeypatch):
    state = ProjectState(id="proj-m2-cancel", name="todo", goal="g", phase=PipelinePhase.STOPPED)
    pipeline = Pipeline(state, FakeRunner([]))
    pipeline.schedule_resume(time.time() + 3600)
    assert state.resume_at > 0
    await pipeline.acancel_resume()
    assert state.resume_at == 0.0
    # Cancellation lands on the next loop tick.
    await wait_until(lambda: pipeline._resume_timer.cancelled())


async def test_recover_rearms_resume_timer(green_pytest):
    # A persisted project with a future resume_at must get its timer re-armed
    # after a backend restart (recover_projects).
    server.pipelines.clear()
    server.set_runner(FakeRunner([]))
    state = ProjectState(
        id="proj-m2-recover", name="todo", goal="g",
        phase=PipelinePhase.STOPPED, resume_at=time.time() + 3600,
    )
    from autospec.storage import save_state

    save_state(state)
    recovered = server.recover_projects()
    assert "proj-m2-recover" in recovered
    pipeline = server.pipelines["proj-m2-recover"]
    assert pipeline._resume_timer is not None and not pipeline._resume_timer.done()
    assert pipeline.state.resume_at > 0
    await pipeline.adispose()  # cleanup the armed timer


async def test_cancel_resume_endpoint(green_pytest):
    import httpx

    server.pipelines.clear()
    server.set_runner(FakeRunner([]))
    state = ProjectState(id="proj-m2-api", name="todo", goal="g", phase=PipelinePhase.STOPPED)
    pipeline = Pipeline(state, FakeRunner([]))
    server.pipelines[state.id] = pipeline
    pipeline.schedule_resume(time.time() + 3600)
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(f"/api/projects/{state.id}/cancel-resume")
        assert resp.status_code == 200
        assert state.resume_at == 0.0
        assert (await client.post("/api/projects/nope/cancel-resume")).status_code == 404
