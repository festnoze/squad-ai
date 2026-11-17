"""Stand-in for the Claude Code CLI (`claude -p --output-format json`).

Records what it received into the JSON file named by ``FAKE_CLAUDE_RECORD``, then
behaves according to ``FAKE_CLAUDE_SCENARIO``:

- ``success`` (default): a successful result with usage, cache tokens and denials;
- ``is_error``: an API error reported with ``is_error: true``, exit 1;
- ``budget``: ``subtype: error_max_budget_usd``, exit 1;
- ``sleep``: never answers, appends a tick to ``FAKE_CLAUDE_TICKS`` every 0.1 s;
- ``garbage``: prints text that is not JSON, exit 0;
- ``nonzero``: prints nothing on stdout, an error on stderr, exit 2.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

WATCHED_ENV = ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "VIRTUAL_ENV", "FAKE_CLAUDE_SCENARIO")

SUCCESS = {
    "type": "result",
    "subtype": "success",
    "is_error": False,
    "duration_ms": 4321,
    "num_turns": 7,
    "result": "All green. {\"summary\": \"done\"}",
    "session_id": "sess-123",
    "total_cost_usd": 0.0123,
    "usage": {"input_tokens": 100, "output_tokens": 50, "cache_creation_input_tokens": 20,
              "cache_read_input_tokens": 3},
    "permission_denials": [{"tool_name": "Bash", "tool_use_id": "toolu_1",
                            "tool_input": {"command": "tasklist"}}],
}


def _flag_value(argv: list[str], flag: str) -> str | None:
    return argv[argv.index(flag) + 1] if flag in argv else None


def _record(argv: list[str], stdin: str) -> None:
    target = os.environ.get("FAKE_CLAUDE_RECORD")
    if not target:
        return
    system_file = _flag_value(argv, "--append-system-prompt-file")
    system_prompt = Path(system_file).read_bytes().decode("utf-8") if system_file else None
    record = {"argv": argv, "stdin": stdin, "cwd": os.getcwd(), "pid": os.getpid(),
              "system_prompt": system_prompt,
              "env": {name: os.environ.get(name) for name in WATCHED_ENV}}
    Path(target).write_text(json.dumps(record), encoding="utf-8")


def _emit(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload) + "\n")
    sys.stdout.flush()


def main() -> int:
    argv = sys.argv[1:]
    stdin = sys.stdin.buffer.read().decode("utf-8")
    _record(argv, stdin)
    scenario = os.environ.get("FAKE_CLAUDE_SCENARIO", "success")
    if scenario == "success":
        _emit(SUCCESS)
        return 0
    if scenario == "is_error":
        _emit({**SUCCESS, "is_error": True, "result": "API Error: 529 overloaded",
               "permission_denials": []})
        return 1
    if scenario == "budget":
        _emit({**SUCCESS, "subtype": "error_max_budget_usd", "is_error": True, "total_cost_usd": 1.02,
               "result": None, "errors": ["Reached maximum budget ($1)"]})
        return 1
    if scenario == "sleep":
        ticks = os.environ.get("FAKE_CLAUDE_TICKS")
        while True:
            if ticks:
                with open(ticks, "a", encoding="utf-8") as handle:
                    handle.write(".")
            time.sleep(0.1)
    if scenario == "garbage":
        print("this is definitely not json")
        print("warning: something odd happened", file=sys.stderr)
        return 0
    if scenario == "nonzero":
        print("Error: invalid API key", file=sys.stderr)
        return 2
    print(f"unknown scenario {scenario!r}", file=sys.stderr)
    return 3


if __name__ == "__main__":
    sys.exit(main())
