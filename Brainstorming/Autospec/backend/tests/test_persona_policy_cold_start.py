"""No priming by another test may be required for the first generation call."""
import pytest

from autospec.agents.generation_policy import GenerationOnlyRunner
from autospec.agents.personas import persona
from autospec.agents.runner import FakeRunner
from autospec.config import settings
from autospec.models import ProjectState
from autospec.orchestrator import pipeline as module


@pytest.mark.parametrize("prewarm_generic", [False, True])
@pytest.mark.parametrize("role", ["qa", "dev", "po-spec"])
async def test_first_campaign_call_works_without_partial_or_generic_role_map(monkeypatch, role, prewarm_generic):
    module._PERSONA_BY_PROMPT.clear()
    persona.cache_clear()
    monkeypatch.setattr(settings, "generation_only_agents", False)
    if prewarm_generic:
        assert module._persona_role(persona("critic")) == "critic"
    monkeypatch.setattr(settings, "generation_only_agents", True)
    inner = FakeRunner(['{}'])
    pipe = module.Pipeline(ProjectState(id="cold-role", name="Offline", goal="Mechanical only"),
                           GenerationOnlyRunner(inner))
    await pipe._tracked.arun("inert fixture", persona(role))
    assert len(inner.calls) == 1 and inner.calls[0]["model"] == "sonnet"
    assert pipe.state.usage.unreported_calls == 0
    assert module._persona_role(persona(role)) == role
    assert "critic" not in module._PERSONA_BY_PROMPT[True].values()


def test_failed_map_build_is_atomic_and_never_a_partial_cached_success(monkeypatch):
    module._PERSONA_BY_PROMPT.clear()
    monkeypatch.setattr(settings, "generation_only_agents", False)
    loaded = []
    def unavailable(name):
        loaded.append(name)
        if len(loaded) == 2:
            raise RuntimeError("inert persona load failure")
        return "inert persona " + name
    monkeypatch.setattr(module, "persona", unavailable)
    with pytest.raises(RuntimeError, match="load failure"):
        module._persona_role("inert")
    assert not module._PERSONA_BY_PROMPT
