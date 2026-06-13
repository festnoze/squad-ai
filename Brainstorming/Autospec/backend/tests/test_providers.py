"""Tests of the LangChain provider backends (M1): tool protocol, runner
selection and the session/tool loop — the chat model itself is stubbed."""

import json

import pytest

from autospec.agents.providers import (
    OllamaRunner,
    OpenAiRunner,
    _apply_tool,
    make_runner,
    provider_model,
)
from autospec.agents.runner import AgentError, ClaudeCliRunner
from autospec.config import settings


def test_make_runner_mapping():
    assert isinstance(make_runner("claude"), ClaudeCliRunner)
    assert isinstance(make_runner(""), ClaudeCliRunner)
    assert isinstance(make_runner("OpenAI"), OpenAiRunner)
    assert isinstance(make_runner("ollama"), OllamaRunner)
    with pytest.raises(ValueError):
        make_runner("gemini")


def test_provider_model_reads_settings(monkeypatch):
    monkeypatch.setattr(settings, "openai_model", "gpt-test")
    monkeypatch.setattr(settings, "ollama_model", "llama-test")
    monkeypatch.setattr(settings, "claude_model", None)
    assert provider_model("openai") == "gpt-test"
    assert provider_model("ollama") == "llama-test"
    assert provider_model("claude") == "(défaut CLI)"


def test_apply_tool_write_then_read(tmp_path):
    _apply_tool(
        tmp_path,
        {"tool": "write_files", "files": [{"path": "pkg/mod.py", "content": "x = 1\n"}]},
    )
    assert (tmp_path / "pkg" / "mod.py").read_text(encoding="utf-8") == "x = 1\n"
    out = _apply_tool(tmp_path, {"tool": "read_files", "paths": ["pkg/mod.py", "absent.py"]})
    assert "x = 1" in out
    assert "introuvable" in out


def test_apply_tool_rejects_path_traversal(tmp_path):
    with pytest.raises(AgentError):
        _apply_tool(
            tmp_path,
            {"tool": "write_files", "files": [{"path": "../evil.py", "content": ""}]},
        )
    with pytest.raises(AgentError):
        _apply_tool(tmp_path, {"tool": "unknown"})


class _StubChatRunner(OllamaRunner):
    """Replaces the LangChain model call with queued canned replies."""

    def __init__(self, replies: list[str]):
        super().__init__()
        self.replies = list(replies)
        self.calls: list[list] = []

    async def _achat(self, messages):
        self.calls.append(list(messages))
        return self.replies.pop(0), 10, 5


async def test_runner_returns_final_answer_and_usage():
    runner = _StubChatRunner([json.dumps({"type": "brief", "brief": "ok"})])
    res = await runner.arun("tâche", "persona")
    assert json.loads(res.text)["brief"] == "ok"
    assert (res.input_tokens, res.output_tokens) == (10, 5)
    assert res.session_id


async def test_runner_session_replays_history():
    runner = _StubChatRunner(["première réponse", "seconde réponse"])
    first = await runner.arun("question 1", "persona")
    await runner.arun("question 2", "persona", session_id=first.session_id)
    # The second call must replay the first exchange before the new question.
    contents = [m.content for m in runner.calls[1]]
    assert any("question 1" in c for c in contents)
    assert any("première réponse" in c for c in contents)
    assert any("question 2" in c for c in contents)


async def test_runner_tool_loop_writes_files(tmp_path):
    final = json.dumps({"status": "green", "summary": "ok"})
    runner = _StubChatRunner(
        [
            json.dumps(
                {"tool": "write_files", "files": [{"path": "main.py", "content": "print(1)\n"}]}
            ),
            final,
        ]
    )
    res = await runner.arun("implémente", "persona dev", cwd=tmp_path)
    assert (tmp_path / "main.py").read_text(encoding="utf-8") == "print(1)\n"
    assert json.loads(res.text)["status"] == "green"
    # Both rounds' tokens are accumulated.
    assert (res.input_tokens, res.output_tokens) == (20, 10)


async def test_runner_tool_loop_cap(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "provider_tool_rounds", 2)
    tool_call = json.dumps({"tool": "read_files", "paths": []})
    runner = _StubChatRunner([tool_call, tool_call, tool_call])
    with pytest.raises(AgentError, match="tours d'outils"):
        await runner.arun("tâche", "persona", cwd=tmp_path)


def test_openai_cost_estimate(monkeypatch):
    monkeypatch.setattr(settings, "openai_price_in", 1.0)   # $1 / 1M input tokens
    monkeypatch.setattr(settings, "openai_price_out", 2.0)  # $2 / 1M output tokens
    runner = OpenAiRunner()
    assert runner._cost(1_000_000, 500_000) == pytest.approx(2.0)
    assert OllamaRunner()._cost(1_000_000, 500_000) == 0.0
