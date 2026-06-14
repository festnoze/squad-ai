"""Tests of the direct Anthropic API provider (M4)."""

import pytest

from autospec.agents.providers import (
    PROVIDERS,
    AnthropicRunner,
    make_runner,
    provider_model,
)
from autospec.agents.runner import AgentError
from autospec.config import settings as cfg


def test_anthropic_in_providers():
    assert "anthropic" in PROVIDERS


def test_make_runner_anthropic():
    assert isinstance(make_runner("anthropic"), AnthropicRunner)


def test_provider_model_anthropic(monkeypatch):
    monkeypatch.setattr(cfg, "anthropic_model", "claude-sonnet-4-6")
    assert provider_model("anthropic") == "claude-sonnet-4-6"


def test_anthropic_no_key_raises(monkeypatch):
    monkeypatch.setattr(cfg, "anthropic_api_key", "")
    with pytest.raises(AgentError):
        AnthropicRunner()._build_model()
