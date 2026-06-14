"""Tests of the optional Langfuse tracing (O1): env-gated, lazily imported, a
no-op when langfuse is unavailable, and never affecting the pipeline. The agent
seam (_UsageTracker.arun) emits one trace per call with usage + phase metadata."""

from autospec import observability
from autospec.agents.runner import FakeRunner
from autospec.config import settings
from autospec.models import PipelinePhase, ProjectState
from autospec.orchestrator.pipeline import Pipeline


def test_trace_noop_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "langfuse_enabled", False)
    observability.reset()
    # Must not raise and must not build a client when tracing is off.
    observability.trace_agent_call(
        name="x", model="m", input_text="i", output_text="o", metadata={}
    )
    assert observability._client_or_none() is None
    observability.reset()


def test_trace_never_raises_when_langfuse_missing(monkeypatch):
    # Enabled but langfuse is not installed -> graceful no-op, no exception.
    monkeypatch.setattr(settings, "langfuse_enabled", True)
    observability.reset()
    observability.trace_agent_call(
        name="x", model="m", input_text="i", output_text="o", metadata={}
    )
    assert observability._client_or_none() is None
    observability.reset()


async def test_usage_tracker_emits_trace(monkeypatch):
    calls = []
    monkeypatch.setattr(observability, "trace_agent_call", lambda **kw: calls.append(kw))

    state = ProjectState(id="p-obs", name="obs", goal="g", phase=PipelinePhase.PLAN)
    pipeline = Pipeline(state, FakeRunner(["{}"]))
    await pipeline._tracked.arun("prompt", "system")

    assert len(calls) == 1
    kw = calls[0]
    assert kw["metadata"]["phase"] == "plan"
    assert kw["metadata"]["project_id"] == "p-obs"
    assert "cost_usd" in kw
    assert "input_tokens" in kw and "output_tokens" in kw
