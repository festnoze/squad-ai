"""Tests of the direct Anthropic API provider (M4) — exposed as "claude" in the
provider list ("anthropic" survives as a legacy alias)."""

import pytest

from autospec.agents.providers import (
    PROVIDERS,
    AnthropicRunner,
    make_runner,
    provider_model,
)
from autospec.agents.runner import AgentError
from autospec.config import settings as cfg


def test_claude_api_in_providers():
    # The API entry is listed as "claude"; the CLI harness as "claude code".
    assert "claude" in PROVIDERS
    assert "claude code" in PROVIDERS
    assert "anthropic" not in PROVIDERS  # replaced by "claude" (kept as alias)


def test_make_runner_anthropic():
    assert isinstance(make_runner("claude"), AnthropicRunner)
    assert isinstance(make_runner("anthropic"), AnthropicRunner)  # legacy alias


def test_provider_model_anthropic(monkeypatch):
    monkeypatch.setattr(cfg, "anthropic_model", "claude-sonnet-4-6")
    assert provider_model("claude") == "claude-sonnet-4-6"
    assert provider_model("anthropic") == "claude-sonnet-4-6"


def test_anthropic_no_key_raises(monkeypatch):
    monkeypatch.setattr(cfg, "anthropic_api_key", "")
    with pytest.raises(AgentError):
        AnthropicRunner()._build_model()
