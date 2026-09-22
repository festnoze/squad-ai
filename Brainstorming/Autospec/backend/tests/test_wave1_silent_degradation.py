"""WORKFLOW_REVIEW P3 + P4: two silent degradations are now audible.

P3 - an Architect phase that fails leaves the WHOLE build running without any
architecture context; only a log line used to say so. It now also raises a
``notify`` event and a SYSTEM chat message.

P4 - a refinement loop that stops with ``stopped_reason == "critic_error"`` means
the critic was UNAVAILABLE: the quality harness silently fell back to no review.
Both callers (``_arefine_plan``, ``_arefine_code``) now emit a
``refine_degraded`` monitor event plus a SYSTEM chat message.
"""

import pytest
from autospec.agents.runner import AgentError, FakeRunner
from autospec.config import settings
from autospec.models import ChatRole, Epic, ProjectState, UserStory
from autospec.orchestrator import refine as refine_mod
from autospec.orchestrator.events import bus
from autospec.orchestrator.pipeline import Pipeline


def _drain(q):
    out = []
    while not q.empty():
        _seq, event = q.get_nowait()
        out.append(event)
    return out


def _pipeline(pid: str, monkeypatch) -> tuple[Pipeline, list[tuple[str, dict]]]:
    state = ProjectState(id=pid, name="degraded", goal="g")
    state.epics.append(Epic(id="EPIC-1", title="E"))
    pipeline = Pipeline(state, FakeRunner([]))
    events: list[tuple[str, dict]] = []
    original = pipeline.monitor.event

    def _event(kind, **fields):
        events.append((kind, fields))
        return original(kind, **fields)

    monkeypatch.setattr(pipeline.monitor, "event", _event)
    return pipeline, events


def _chat_texts(pipeline: Pipeline) -> list[str]:
    return [m.content for m in pipeline.state.chat]


# ------------------------------------------------- P3: architect unavailability

async def test_architect_failure_notifies_and_speaks_in_chat(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "architecture_enabled", True)
    pipeline, _events = _pipeline("arch-down", monkeypatch)

    async def _boom(prompt, system_prompt, cwd=None, session_id=None, model=None):
        raise AgentError("claude cli exited 1")

    monkeypatch.setattr(pipeline._tracked, "arun", _boom)

    q = bus.subscribe()
    try:
        await pipeline._aarchitect_phase()
        events = _drain(q)
    finally:
        bus.unsubscribe(q)

    notifs = [e for e in events if e.get("type") == "notify"]
    assert any(
        e["level"] == "warning"
        and e["title"] == "Architecture indisponible"
        and "claude cli exited 1" in e["body"]
        for e in notifs
    )
    assert any("Architecture indisponible" in t for t in _chat_texts(pipeline))
    assert pipeline.state.chat[-1].role == ChatRole.SYSTEM
    # Still non-fatal: no architecture recorded, the build goes on.
    assert pipeline.state.architecture == ""


async def test_architect_success_is_silent_on_the_notify_bus(tmp_path, monkeypatch):
    """The warning must fire ONLY on a failure (no new noise on the happy path)."""
    monkeypatch.setattr(settings, "architecture_enabled", True)
    pipeline, _events = _pipeline("arch-ok", monkeypatch)

    class _Res:
        text = '{"design": "layered", "message": "ok"}'

    async def _ok(prompt, system_prompt, cwd=None, session_id=None, model=None):
        return _Res()

    monkeypatch.setattr(pipeline._tracked, "arun", _ok)

    q = bus.subscribe()
    try:
        await pipeline._aarchitect_phase()
        events = _drain(q)
    finally:
        bus.unsubscribe(q)

    assert pipeline.state.architecture == "layered"
    assert not [
        e for e in events
        if e.get("type") == "notify" and e.get("title") == "Architecture indisponible"
    ]


# ------------------------------------------------------ P4: degraded refinement

def _outcome(reason: str) -> refine_mod.RefineOutcome:
    return refine_mod.RefineOutcome(text="artifact", rounds=0, score=-1, stopped_reason=reason)


async def test_plan_refinement_reports_an_unavailable_critic(tmp_path, monkeypatch):
    pipeline, events = _pipeline("refine-plan-degraded", monkeypatch)

    async def _arefine(runner, **kwargs):
        return _outcome("critic_error")

    monkeypatch.setattr(refine_mod, "arefine", _arefine)

    await pipeline._arefine_plan("plan text", "pkg")

    degraded = [f for k, f in events if k == "refine_degraded"]
    assert degraded == [{"role": "po", "reason": "critic_error"}]
    assert any("Revue po dégradée (critique indisponible)." in t for t in _chat_texts(pipeline))


@pytest.mark.parametrize("reason", ["threshold", "critic_empty", "max_rounds", "disabled"])
async def test_a_healthy_plan_refinement_reports_nothing(tmp_path, monkeypatch, reason):
    pipeline, events = _pipeline(f"refine-plan-{reason}", monkeypatch)

    async def _arefine(runner, **kwargs):
        return _outcome(reason)

    async def _acritique(*args, **kwargs):
        return "", [], []

    monkeypatch.setattr(refine_mod, "arefine", _arefine)
    monkeypatch.setattr(refine_mod, "_acritique", _acritique)

    await pipeline._arefine_plan("plan text", "pkg")

    assert not [f for k, f in events if k == "refine_degraded"]
    assert not any("dégradée (critique indisponible)" in t for t in _chat_texts(pipeline))


async def test_code_refinement_reports_an_unavailable_critic(tmp_path, monkeypatch):
    pipeline, events = _pipeline("refine-code-degraded", monkeypatch)
    story = UserStory(id="US-1", epic_id="EPIC-1", title="S")
    pipeline.state.stories = [story]

    async def _snapshot(ws, sid):
        return True

    async def _agit(ws, *args):
        return 0, ""

    async def _arefine(runner, **kwargs):
        return _outcome("critic_error")

    monkeypatch.setattr(pipeline, "_agit_snapshot", _snapshot)
    monkeypatch.setattr(pipeline, "_agit", _agit)
    monkeypatch.setattr(refine_mod, "arefine", _arefine)

    await pipeline._arefine_code(story, "pkg", tmp_path)

    degraded = [f for k, f in events if k == "refine_degraded"]
    assert degraded == [{"role": "dev", "reason": "critic_error"}]
    assert any("Revue dev dégradée (critique indisponible)." in t for t in _chat_texts(pipeline))
