"""Tests of the M2 usage-window watchdog: limit detection, reset-time parsing
(error epoch / ccusage blocks), clean stop + scheduled auto-resume, restart
re-arming and user cancellation."""

import asyncio
import time
from unittest.mock import AsyncMock

from autospec.agents.runner import AgentError, FakeRunner
from autospec.api import server
from autospec.config import settings
from autospec.models import PipelinePhase, ProjectState
from autospec.orchestrator import session_monitor
from autospec.orchestrator.pipeline import Pipeline

from .conftest import wait_until

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
    monkeypatch.setattr(settings, "agent_provider", "claude code")
    monkeypatch.setattr(settings, "fake_agents", False)
    assert session_monitor.monitor_active()
    monkeypatch.setattr(settings, "agent_provider", "codex")
    assert not session_monitor.monitor_active()
    # The key-based "claude" API provider has no subscription usage window.
    monkeypatch.setattr(settings, "agent_provider", "claude")
    assert not session_monitor.monitor_active()
    monkeypatch.setattr(settings, "agent_provider", "claude code")
    monkeypatch.setattr(settings, "fake_agents", True)
    assert not session_monitor.monitor_active()


# --------------------------------------------------------- pipeline behaviour

def _enable_monitor(monkeypatch):
    monkeypatch.setattr(settings, "session_monitor_enabled", True)
    monkeypatch.setattr(settings, "agent_provider", "claude code")
    monkeypatch.setattr(settings, "fake_agents", False)


async def test_usage_limit_requests_stop_and_arms_owned_resume(monkeypatch):
    _enable_monitor(monkeypatch)
    state = ProjectState(id="proj-m2", name="todo", goal="g", phase=PipelinePhase.BUILD)
    pipeline = Pipeline(state, FakeRunner([]))
    monkeypatch.setattr(pipeline, '_notify', lambda *a, **k: None)
    target = int(time.time()) + 3600
    try:
        await pipeline._aon_agent_error(AgentError(f'Claude AI usage limit reached|{target}'))
        assert pipeline._stop_requested and pipeline._resume_event.is_set()
        assert state.resume_at == target
        assert pipeline._resume_timer is not None and not pipeline._resume_timer.done()
        first_timer = pipeline._resume_timer
        await pipeline._aon_agent_error(AgentError(f'usage limit reached|{target}'))
        assert pipeline._resume_timer is first_timer  # sibling errors cannot arm duplicate timers
        assert any('Fenêtre d\'usage Claude épuisée' in m.content for m in state.chat)
        first_timer.cancel()
        await asyncio.gather(first_timer, return_exceptions=True)
        resume = AsyncMock()
        monkeypatch.setattr(pipeline, 'aresume_build', resume)
        monkeypatch.setattr(session_monitor, 'await_window', AsyncMock(return_value=0.0))
        await pipeline._aresume_timer(0.0)
        resume.assert_awaited_once()
        assert state.resume_at == 0.0
        assert any('Nouvelle fenêtre d\'usage disponible' in m.content for m in state.chat)
        # This watchdog test never claims DONE from a fake green suite. Product
        # admission/runtime integrity is exercised by its dedicated contract.
        assert state.phase == PipelinePhase.BUILD
    finally:
        await pipeline.adispose()


async def test_usage_limit_ignored_for_other_providers(monkeypatch):
    monkeypatch.setattr(settings, "session_monitor_enabled", True)
    monkeypatch.setattr(settings, "agent_provider", "codex")
    monkeypatch.setattr(settings, "fake_agents", False)
    state = ProjectState(id="proj-m2-off", name="todo", goal="g", phase=PipelinePhase.BUILD)
    pipeline = Pipeline(state, FakeRunner([]))
    await pipeline._aon_agent_error(AgentError('usage limit reached|1718226000'))
    # A subscription watchdog must not invent a window for another provider.
    assert state.resume_at == 0.0
    assert pipeline._resume_timer is None
    assert not pipeline._stop_requested and state.phase == PipelinePhase.BUILD


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
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        resp = await client.post(f"/api/projects/{state.id}/cancel-resume")
        assert resp.status_code == 200
        assert state.resume_at == 0.0
        assert (await client.post("/api/projects/nope/cancel-resume")).status_code == 404
