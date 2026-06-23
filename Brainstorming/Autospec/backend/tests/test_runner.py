import json

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
    # The runners spawn via _run_tracked (Popen-backed, so an in-flight CLI call
    # can be killed); patch that seam, which returns (returncode, stdout, stderr).
    def fake_run(args, input_text, cwd, timeout):
        return returncode, stdout, stderr

    monkeypatch.setattr("autospec.agents.runner._run_tracked", fake_run)


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


# ----------------------------------------- in-flight CLI interruption (kill)


def test_process_registry_kills_tracked_in_flight_process():
    """A long-running child registered (via the active_processes contextvar that
    _run_tracked reads) can be hard-killed mid-flight — the mechanism behind
    project-switch / shutdown interruption of agent CLI calls."""
    import sys
    import threading
    import time

    from autospec.agents.runner import (
        ProcessRegistry,
        _run_tracked,
        active_processes,
    )

    reg = ProcessRegistry()
    result: dict = {}

    def worker():
        active_processes.set(reg)  # what _UsageTracker does before a real call
        result["rc"], _, _ = _run_tracked(
            [sys.executable, "-c", "import time; time.sleep(30)"], "", None, 60
        )

    t = threading.Thread(target=worker, daemon=True)
    t.start()

    # Wait until the child is actually spawned + registered.
    for _ in range(300):
        if len(reg) >= 1:
            break
        time.sleep(0.01)
    assert len(reg) == 1, "the in-flight process should be tracked"

    killed = reg.terminate_all()
    assert killed == 1

    t.join(timeout=15)
    assert not t.is_alive(), "the blocking run must return once the child is killed"
    assert result["rc"] != 0, "a killed process never exits cleanly (0)"
    assert len(reg) == 0, "the registry is emptied once the call returns"
