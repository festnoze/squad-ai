"""Codex CLI provider (mirrors Claude) + live per-provider model discovery."""

import json
import subprocess

import pytest

from autospec.agents import discovery
from autospec.agents.runner import AgentError, CodexCliRunner, _extract_codex_text
from autospec.config import settings


# --------------------------------------------------------- Codex JSONL parsing


def test_extract_codex_text_jsonl_agent_message_and_usage():
    out = "\n".join(
        [
            json.dumps({"msg": {"type": "task_started"}}),
            json.dumps({"msg": {"type": "agent_message", "message": "première"}}),
            json.dumps({"item": {"type": "agent_message", "text": "réponse finale"}}),
            json.dumps({"type": "token_count", "usage": {"input_tokens": 42, "output_tokens": 7}}),
        ]
    )
    text, in_tok, out_tok = _extract_codex_text(out)
    assert text == "réponse finale"  # the LAST agent message wins
    assert (in_tok, out_tok) == (42, 7)


def test_extract_codex_text_plain_text_passthrough():
    text, in_tok, out_tok = _extract_codex_text("just plain output, no json")
    assert text == "just plain output, no json"
    assert (in_tok, out_tok) == (0, 0)


# --------------------------------------------------------- CodexCliRunner


def _patch_codex(monkeypatch, *, stdout="", stderr="", returncode=0):
    def fake_run(args, **kwargs):
        # Sanity: we drive `codex exec` headless and feed the prompt on stdin.
        assert args[0] == settings.codex_cmd
        assert "exec" in args and args[-1] == "-"
        assert "system" in (kwargs.get("input") or "")  # system prompt prepended
        return subprocess.CompletedProcess(args, returncode, stdout=stdout, stderr=stderr)

    monkeypatch.setattr("autospec.agents.runner.subprocess.run", fake_run)


async def test_codex_runner_parses_jsonl(monkeypatch):
    out = json.dumps({"msg": {"type": "agent_message", "message": '{"status":"green"}'}})
    _patch_codex(monkeypatch, stdout=out)
    res = await CodexCliRunner().arun("prompt", "system")
    assert json.loads(res.text)["status"] == "green"


async def test_codex_runner_passes_model(monkeypatch):
    captured = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        return subprocess.CompletedProcess(args, 0, stdout="hello", stderr="")

    monkeypatch.setattr("autospec.agents.runner.subprocess.run", fake_run)
    await CodexCliRunner().arun("p", "s", model="gpt-5.3-codex")
    assert "--model" in captured["args"]
    assert "gpt-5.3-codex" in captured["args"]


async def test_codex_runner_nonzero_exit_raises(monkeypatch):
    _patch_codex(monkeypatch, stdout="", stderr="boom", returncode=2)
    with pytest.raises(AgentError, match="exited with 2"):
        await CodexCliRunner().arun("prompt", "system")


# --------------------------------------------------------- model discovery


async def test_discover_ollama_live(monkeypatch):
    def fake_get(url, headers=None):
        assert url.endswith("/api/tags")
        return {"models": [{"name": "llama3.2:latest"}, {"name": "qwen3:8b"}]}

    monkeypatch.setattr(discovery, "_http_get_json", fake_get)
    models, source = await discovery.adiscover_models("ollama")
    assert source == "live"
    assert models == ["llama3.2:latest", "qwen3:8b"]


async def test_discover_openai_filters_to_chat_models(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")

    def fake_get(url, headers=None):
        assert url.endswith("/models")
        assert headers and headers["Authorization"] == "Bearer sk-test"
        return {"data": [
            {"id": "gpt-4.1"}, {"id": "o4-mini"},
            {"id": "text-embedding-3-small"}, {"id": "whisper-1"}, {"id": "dall-e-3"},
        ]}

    monkeypatch.setattr(discovery, "_http_get_json", fake_get)
    models, source = await discovery.adiscover_models("openai")
    assert source == "live"
    assert "gpt-4.1" in models and "o4-mini" in models
    assert "text-embedding-3-small" not in models
    assert "whisper-1" not in models and "dall-e-3" not in models


async def test_discover_falls_back_to_static_on_error(monkeypatch):
    def boom(url, headers=None):
        raise OSError("connection refused")

    monkeypatch.setattr(discovery, "_http_get_json", boom)
    models, source = await discovery.adiscover_models("ollama")
    assert source == "static"
    assert models == list(discovery.provider_models("ollama"))


async def test_discover_claude_is_static(monkeypatch):
    models, source = await discovery.adiscover_models("claude")
    assert source == "static"
    assert models == ["opus", "sonnet", "haiku"]
