"""Offline policy guards; rejected calls never invoke a CLI or provider."""
import pytest

from autospec.agents.generation_policy import GENERATION_ROLES, GenerationOnlyRunner
from autospec.agents.personas import FALLBACK_PERSONAS, persona
from autospec.agents.providers import make_runner, provider_capabilities
from autospec.agents.runner import AgentError, FakeRunner
from autospec.config import settings
from autospec.models import ProjectState
from autospec.orchestrator.pipeline import Pipeline, _FORCE_MODEL


@pytest.mark.parametrize("role", sorted(FALLBACK_PERSONAS))
async def test_campaign_role_allowlist_precedes_usage_and_dispatch(role):
    inner=FakeRunner(['{}'])
    pipeline=Pipeline(ProjectState(id="generation-policy",name="meta",goal="meta"),GenerationOnlyRunner(inner))
    if role in GENERATION_ROLES:
        await pipeline._tracked.arun("inert offline fixture",persona(role))
        assert len(inner.calls)==1 and inner.calls[0]["model"]=="sonnet"
    else:
        with pytest.raises(AgentError,match="GENERATION_ONLY"):
            await pipeline._tracked.arun("inert offline fixture",persona(role))
        assert not inner.calls and pipeline.state.usage.agent_calls==0
        assert not pipeline.state.generation_checkpoint and not pipeline.state.agent_activity
        assert pipeline.state.usage.unreported_calls==0


@pytest.mark.parametrize("system,model", [("unknown role",None),(persona("critic"),"sonnet"),(persona("dev"),"opus")])
async def test_direct_wrapper_cannot_bypass_role_or_model_admission(system, model):
    inner=FakeRunner()
    with pytest.raises(AgentError,match="GENERATION_ONLY"):
        await GenerationOnlyRunner(inner).arun("inert",system,model=model)
    assert not inner.calls


@pytest.mark.parametrize("provider", ["openai","openrouter","ollama","claude","anthropic","codex"])
def test_campaign_cannot_switch_to_direct_api_or_another_provider(monkeypatch, provider):
    monkeypatch.setattr(settings,"generation_only_agents",True)
    with pytest.raises(ValueError,match="GENERATION_ONLY"):
        make_runner(provider)


def test_campaign_claude_code_is_guarded_but_generic_installation_is_unchanged(monkeypatch):
    monkeypatch.setattr(settings,"generation_only_agents",True)
    assert isinstance(make_runner("claude code"),GenerationOnlyRunner)
    monkeypatch.setattr(settings,"generation_only_agents",False)
    assert not isinstance(make_runner("claude code"),GenerationOnlyRunner)


def test_capability_inventory_stays_read_only_with_campaign_guard(monkeypatch):
    monkeypatch.setattr(settings, "generation_only_agents", True)
    capabilities = provider_capabilities("claude code")
    assert capabilities.execution_model == "restricted_tools"
    assert capabilities.can_edit_files and not capabilities.can_run_shell
    assert provider_capabilities("openai").execution_model == "langchain_file_tools"


@pytest.mark.parametrize("route", ["role", "ladder", "override"])
async def test_model_routing_cannot_escape_sonnet_before_activity(monkeypatch, route):
    inner = FakeRunner(['{}'])
    pipeline = Pipeline(ProjectState(id="generation-model", name="meta", goal="meta"),
                        GenerationOnlyRunner(inner))
    monkeypatch.setattr(settings, "model_for_role", lambda role, phase: "haiku" if route == "role" else "sonnet")
    token = _FORCE_MODEL.set("opus" if route == "ladder" else None)
    try:
        with pytest.raises(AgentError, match="GENERATION_ONLY"):
            await pipeline._tracked.arun("inert", persona("dev"), model="opus" if route == "override" else None)
    finally:
        _FORCE_MODEL.reset(token)
    assert not inner.calls and pipeline.state.usage.agent_calls == 0
    assert not pipeline.state.generation_checkpoint and not pipeline.state.agent_activity
    assert pipeline.state.usage.unreported_calls == 0
