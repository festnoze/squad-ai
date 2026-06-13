import json
import subprocess

import pytest

from autospec.agents.runner import AgentError, ClaudeCliRunner, extract_json


def test_extract_json_plain():
    assert extract_json('{"type": "brief", "n": 1}') == {"type": "brief", "n": 1}


def test_extract_json_with_prose_around():
    text = 'Voici ma réponse :\n{"type": "question", "message": "Pourquoi ?"}\nMerci.'
    assert extract_json(text)["type"] == "question"


def test_extract_json_fenced():
    text = 'Bla\n```json\n{"status": "green", "files": []}\n```'
    assert extract_json(text)["status"] == "green"


def test_extract_json_nested_objects():
    text = '{"epics": [{"id": "E1", "stories": [{"id": "US-1"}]}]}'
    assert extract_json(text)["epics"][0]["stories"][0]["id"] == "US-1"


def test_extract_json_braces_inside_strings():
    text = '{"a": "contient } et { dedans", "b": 1}'
    assert extract_json(text) == {"a": "contient } et { dedans", "b": 1}


def test_extract_json_escaped_quote_inside_string():
    text = '{"g": "a \\"quote\\" and }", "n": 2}'
    assert extract_json(text) == {"g": 'a "quote" and }', "n": 2}


def test_extract_json_missing_raises():
    with pytest.raises(AgentError):
        extract_json("pas de json ici")


def test_extract_json_skips_brace_laden_prose_before_json():
    # A non-JSON brace block (code sample) precedes the actual JSON object.
    text = (
        "Exemple :\n```python\ndef f():\n    return {x: 1}\n```\n"
        'Ma réponse :\n{"type": "brief", "brief": "ok"}'
    )
    assert extract_json(text)["type"] == "brief"


def test_extract_json_falls_back_when_fence_is_invalid():
    text = '```json\n{oups}\n```\n{"ok": true}'
    assert extract_json(text) == {"ok": True}


def test_extract_json_invalid_object_raises_agent_error_not_jsondecodeerror():
    with pytest.raises(AgentError):
        extract_json("voici {pas: du json} fin")


# --------------------------------------------------------- ClaudeCliRunner


def _patch_cli(monkeypatch, *, stdout="", stderr="", returncode=0):
    def fake_run(args, **kwargs):
        return subprocess.CompletedProcess(args, returncode, stdout=stdout, stderr=stderr)

    monkeypatch.setattr("autospec.agents.runner.subprocess.run", fake_run)


async def test_cli_runner_tolerates_missing_usage_and_cost(monkeypatch):
    _patch_cli(monkeypatch, stdout=json.dumps({"result": "ok", "session_id": "s1"}))
    res = await ClaudeCliRunner().arun("prompt", "system")
    assert res.text == "ok"
    assert res.session_id == "s1"
    assert res.cost_usd == 0.0
    assert res.input_tokens == 0 and res.output_tokens == 0


async def test_cli_runner_null_result_yields_empty_text(monkeypatch):
    _patch_cli(monkeypatch, stdout=json.dumps({"result": None, "session_id": "s1"}))
    res = await ClaudeCliRunner().arun("prompt", "system")
    assert res.text == ""


async def test_cli_runner_error_payload_raises(monkeypatch):
    payload = {"is_error": True, "subtype": "error_during_execution", "result": "boom"}
    _patch_cli(monkeypatch, stdout=json.dumps(payload))
    with pytest.raises(AgentError, match="boom"):
        await ClaudeCliRunner().arun("prompt", "system")


async def test_cli_runner_nonzero_exit_raises(monkeypatch):
    _patch_cli(monkeypatch, stdout="", stderr="crash", returncode=3)
    with pytest.raises(AgentError, match="exited with 3"):
        await ClaudeCliRunner().arun("prompt", "system")


async def test_cli_runner_non_json_output_degrades_to_raw_text(monkeypatch):
    _patch_cli(monkeypatch, stdout="plain text, not json")
    res = await ClaudeCliRunner().arun("prompt", "system")
    assert res.text == "plain text, not json"
