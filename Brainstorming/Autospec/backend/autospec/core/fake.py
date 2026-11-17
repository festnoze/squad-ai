"""Scripted agents for tests and the --fake demo. They really write files, like native agents do."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from .ports import AgentCall, AgentResult

Handler = Callable[[AgentCall], str] | str | BaseException


class FakeRunner:
    """``handlers[role]`` is an answer, a callable, an exception, or a list consumed in order."""

    def __init__(self, handlers: dict[str, Handler | list[Handler]]):
        self.handlers = handlers
        self.calls: list[AgentCall] = []

    async def arun(self, call: AgentCall) -> AgentResult:
        self.calls.append(call)
        handler = self.handlers[call.role]
        if isinstance(handler, list):
            handler = handler.pop(0) if len(handler) > 1 else handler[0]
        if isinstance(handler, BaseException):
            raise handler
        text = handler(call) if callable(handler) else handler
        return AgentResult(text=text, session_id=f"fake-{call.role}-{len(self.calls)}", cost_usd=0.01,
                           input_tokens=100, output_tokens=50, duration_ms=5, num_turns=1)

    def roles(self) -> list[str]:
        return [call.role for call in self.calls]


def write(call: AgentCall, files: dict[str, str]) -> None:
    for rel, content in files.items():
        target = Path(call.cwd) / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def demo_plan(package: str) -> str:
    return json.dumps({
        "profile": "lib",
        "epics": [{"id": "EPIC-1", "title": "Greetings", "description": "Say hello."}],
        "stories": [
            {"id": "US-1", "epic_id": "EPIC-1", "title": "Greet someone", "priority": 1, "depends_on": [],
             "criteria": [f"{package}.greet.greet('Ada') returns 'Hello, Ada!'",
                          "an empty name greets the world"],
             "gherkin": "Scenario: greet\n  When I greet Ada\n  Then I get 'Hello, Ada!'"},
            {"id": "US-2", "epic_id": "EPIC-1", "title": "Shout a greeting", "priority": 2,
             "depends_on": ["US-1"], "criteria": ["shout('Ada') returns 'HELLO, ADA!'"],
             "gherkin": "Scenario: shout\n  When I shout at Ada\n  Then I get 'HELLO, ADA!'"},
        ],
    })


_TESTS = {
    "US-1": ("from {pkg}.greet import greet\n\n\n"
             "def test_ac1_greets_by_name():\n    assert greet('Ada') == 'Hello, Ada!'\n\n\n"
             "def test_ac2_empty_name_greets_the_world():\n    assert greet('') == 'Hello, world!'\n"),
    "US-2": ("from {pkg}.greet import shout\n\n\n"
             "def test_ac1_shouts():\n    assert shout('Ada') == 'HELLO, ADA!'\n"),
}
_CODE = {
    "US-1": "def greet(name: str) -> str:\n    return f\"Hello, {name or 'world'}!\"\n",
    "US-2": ("def greet(name: str) -> str:\n    return f\"Hello, {name or 'world'}!\"\n\n\n"
             "def shout(name: str) -> str:\n    return greet(name).upper()\n"),
}


def _story_id(prompt: str) -> str:
    return "US-2" if "US-2" in prompt else "US-1"


def demo_qa(package: str) -> Callable[[AgentCall], str]:
    def handler(call: AgentCall) -> str:
        sid = _story_id(call.prompt)
        n = sid.split("-")[1]
        rel = f"tests/acceptance/test_us_{n}.py"
        write(call, {rel: _TESTS[sid].format(pkg=package)})
        names = [line[4:].split("(")[0] for line in _TESTS[sid].splitlines() if line.startswith("def test_")]
        return json.dumps({"tests": [{"ac_id": f"{sid}.AC-{i + 1}", "nodeids": [f"{rel}::{name}"]}
                                     for i, name in enumerate(names)]})
    return handler


def demo_dev(package: str) -> Callable[[AgentCall], str]:
    def handler(call: AgentCall) -> str:
        sid = "US-2" if "shout" in call.prompt.lower() else "US-1"
        write(call, {f"{package}/greet.py": _CODE[sid]})
        return json.dumps({"summary": f"implemented {sid}", "dependencies_added": []})
    return handler


def demo_runner(package: str) -> FakeRunner:
    return FakeRunner({
        "pm": json.dumps({"brief": "# Greeter\nA tiny library that greets people."}),
        "po": demo_plan(package),
        "qa": demo_qa(package),
        "dev": demo_dev(package),
    })
