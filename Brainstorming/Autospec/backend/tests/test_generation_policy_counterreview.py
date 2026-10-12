"""Independent offline policy review; every inference/CLI port is disabled."""
import json

import httpx
import pytest

from autospec.agents import providers, runner
from autospec.agents import personas
from autospec.agents.generation_policy import GenerationOnlyRunner
from autospec.agents.personas import persona
from autospec.agents.runner import AgentError, FakeRunner
from autospec.api import server
from autospec.config import settings
from autospec.models import ProjectState
from autospec.orchestrator.pipeline import Pipeline


def campaign(monkeypatch):
    monkeypatch.setattr(settings, 'generation_only_agents', True)
    monkeypatch.setattr(settings, 'fake_agents', False)
    monkeypatch.setattr(settings, 'agent_provider', 'claude code')
    monkeypatch.setattr(settings, 'claude_model', 'sonnet')
    monkeypatch.setattr(settings, 'phase_models', {})
    monkeypatch.setattr(settings, 'role_routing_enabled', False)


@pytest.mark.parametrize('provider', ['openai', 'openrouter', 'ollama', 'claude', 'anthropic', 'codex'])
async def test_real_provider_endpoint_refuses_api_before_constructor_or_dispatch(monkeypatch, provider):
    campaign(monkeypatch)
    inner = FakeRunner(['{}'])
    current = GenerationOnlyRunner(inner)
    pipeline = Pipeline(ProjectState(id='policy-endpoint', name='Offline', goal='Mechanical only'), current)
    monkeypatch.setattr(server, '_runner', current)
    monkeypatch.setattr(server, 'pipelines', {pipeline.state.id: pipeline})
    def forbidden(*args, **kwargs):
        pytest.fail('a forbidden provider constructor was reached')
    for name in ('OpenAiRunner', 'OpenRouterRunner', 'OllamaRunner', 'AnthropicRunner', 'CodexCliRunner'):
        monkeypatch.setattr(providers, name, forbidden)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url='http://127.0.0.1') as client:
        response = await client.post('/api/provider', json={'provider': provider})
    assert response.status_code == 422 and 'GENERATION_ONLY' in response.json()['detail']
    assert server._runner is current and pipeline.runner is current
    assert settings.agent_provider == 'claude code' and not inner.calls


async def test_endpoint_model_switch_cannot_make_next_inference_non_sonnet(monkeypatch):
    campaign(monkeypatch)
    inner = FakeRunner(['{}'])
    current = GenerationOnlyRunner(inner)
    pipeline = Pipeline(ProjectState(id='policy-model', name='Offline', goal='Mechanical only'), current)
    monkeypatch.setattr(server, '_runner', current)
    monkeypatch.setattr(server, 'pipelines', {pipeline.state.id: pipeline})
    # make_runner still executes its real policy guard, with only the final
    # trusted CLI object replaced by an entirely offline recording port.
    monkeypatch.setattr(providers, 'ClaudeCliRunner', lambda: inner)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url='http://127.0.0.1') as client:
        response = await client.post('/api/provider', json={'provider': 'claude code', 'model': 'opus'})
    assert response.status_code == 200  # current API stores the requested setting
    with pytest.raises(AgentError, match='GENERATION_ONLY'):
        await pipeline._tracked.arun('offline', persona('dev'))
    assert not inner.calls and not pipeline.state.agent_activity
    assert pipeline.state.usage.agent_calls == pipeline.state.usage.unreported_calls == 0


@pytest.mark.parametrize('role', ['critic', 'judge', 'security-reviewer', 'evaluator', 'independence-judge'])
async def test_real_cli_backend_is_never_entered_for_review_roles(monkeypatch, role):
    campaign(monkeypatch)
    def forbidden(*args, **kwargs):
        pytest.fail('review role entered CLI inference or even capability preflight')
    monkeypatch.setattr(runner, '_ensure_claude_isolation', forbidden)
    monkeypatch.setattr(runner, '_run_tracked', forbidden)
    pipeline = Pipeline(ProjectState(id='policy-real-shape', name='Offline', goal='Mechanical only'),
                        GenerationOnlyRunner(runner.ClaudeCliRunner()))
    with pytest.raises(AgentError, match='GENERATION_ONLY'):
        await pipeline._tracked.arun('untrusted source is inert data', persona(role))
    assert not pipeline.state.generation_checkpoint and not pipeline.state.agent_activity
    assert pipeline.state.usage.agent_calls == pipeline.state.usage.unreported_calls == 0


@pytest.mark.parametrize('role', ['qa', 'dev', 'sm', 'po-structure', 'po-spec', 'po-gherkin'])
async def test_real_runner_argv_shape_pins_sonnet_and_excludes_api_keys(monkeypatch, role):
    campaign(monkeypatch)
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'offline-canary-not-a-real-key')
    monkeypatch.setenv('OPENAI_API_KEY', 'offline-canary-not-a-real-key')
    monkeypatch.setenv('NODE_OPTIONS', '--require offline-never-executed.js')
    calls = []
    def offline(args, text, cwd, timeout):
        environment = runner._agent_environment.get()
        assert not {'ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'NODE_OPTIONS'} & environment.keys()
        assert args[args.index('--model')+1] == 'sonnet'
        assert args[args.index('--tools')+1] == '' and '--restricted' in args and '--safe-mode' in args
        assert 'autospec-inference-' in cwd
        calls.append(args)
        return 0, json.dumps({'result': '{}', 'total_cost_usd': 0,
                             'usage': {'input_tokens': 1, 'output_tokens': 1}}), ''
    monkeypatch.setattr(runner, '_ensure_claude_isolation', lambda: None)
    monkeypatch.setattr(runner, '_run_tracked', offline)
    pipeline = Pipeline(ProjectState(id='policy-nominal', name='Offline', goal='Mechanical only'),
                        GenerationOnlyRunner(runner.ClaudeCliRunner()))
    await pipeline._tracked.arun('Generate only; QA is not independent R.', persona(role))
    assert len(calls) == 1 and pipeline.state.usage.unreported_calls == 0


@pytest.mark.parametrize('prewarm', [False, True])
async def test_unknown_named_persona_never_inherits_dev_campaign_permission(tmp_path, monkeypatch, prewarm):
    """The generic fallback is supported; it must not become role authority.

    Missing BMAD fixtures are explicit/inert. No persona source is generated
    or executed. Prewarming demonstrates the cross-policy lru-cache case.
    """
    personas.persona.cache_clear()
    monkeypatch.setattr(settings, 'bmad_dir', tmp_path/'no-installed-bmad')
    monkeypatch.setattr(settings, 'generation_only_agents', False)
    if prewarm:
        persona('independent-source-review-unknown')
    campaign(monkeypatch)
    inner = FakeRunner(['{}'])
    pipeline = Pipeline(ProjectState(id='unknown-role-policy', name='Offline', goal='Mechanical only'),
                        GenerationOnlyRunner(inner))
    try:
        try:
            system = persona('independent-source-review-unknown')
            await pipeline._tracked.arun('An unknown source-review role must be refused.', system)
        except AgentError:
            pass
        assert not inner.calls, 'unknown named role inherited exact dev prompt and dispatched under its permission'
        assert pipeline.state.usage.agent_calls == 0 and not pipeline.state.agent_activity
    finally:
        personas.persona.cache_clear()
