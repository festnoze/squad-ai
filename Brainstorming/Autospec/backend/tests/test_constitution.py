"""Tests for autospec.orchestrator.constitution — W3 constitution compiler."""

from __future__ import annotations

import json

import pytest

from autospec.agents.runner import FakeRunner
from autospec.orchestrator import constitution as C


# --------------------------------------------------------------------------- #
# is_runnable_pytest
# --------------------------------------------------------------------------- #

def test_is_runnable_pytest_valid_test_function():
    src = "def test_ok():\n    assert 1 + 1 == 2\n"
    assert C.is_runnable_pytest(src) is True


def test_is_runnable_pytest_valid_test_class():
    src = "class TestThing:\n    def test_it(self):\n        assert True\n"
    assert C.is_runnable_pytest(src) is True


def test_is_runnable_pytest_plain_code_without_test_is_false():
    src = "x = 1\ndef helper():\n    return x\n"
    assert C.is_runnable_pytest(src) is False


def test_is_runnable_pytest_syntax_error_is_false():
    assert C.is_runnable_pytest("def test_bad(: pass") is False


def test_is_runnable_pytest_empty_is_false():
    assert C.is_runnable_pytest("") is False
    assert C.is_runnable_pytest(None) is False


# --------------------------------------------------------------------------- #
# render_pytest_file
# --------------------------------------------------------------------------- #

def test_render_pytest_file_valid_rule():
    rule = {
        "id": "No SQL Injection",
        "statement": "All queries must be parameterized.",
        "kind": "test",
        "check_code": "def test_no_raw_sql():\n    assert True\n",
    }
    result = C.render_pytest_file(rule)
    assert result is not None
    path, content = result
    assert path.startswith("tests/constitution/")
    assert path == "tests/constitution/test_no_sql_injection.py"
    # Content names the rule id and embeds the check code.
    assert "No SQL Injection" in content
    assert "def test_no_raw_sql():" in content


def test_render_pytest_file_non_runnable_returns_none():
    rule = {
        "id": "junk",
        "statement": "not a test",
        "kind": "test",
        "check_code": "just some prose, not python",
    }
    assert C.render_pytest_file(rule) is None


def test_render_pytest_file_wrong_kind_returns_none():
    rule = {"id": "x", "statement": "s", "kind": "advisory"}
    assert C.render_pytest_file(rule) is None


# --------------------------------------------------------------------------- #
# compile_rules
# --------------------------------------------------------------------------- #

def test_compile_rules_routes_each_kind():
    rules = [
        {
            "id": "test_rule",
            "statement": "runnable",
            "kind": "test",
            "check_code": "def test_a():\n    assert True\n",
        },
        {
            "id": "cmd_rule",
            "statement": "lints clean",
            "kind": "command",
            "check_cmd": "ruff check .",
        },
        {"id": "adv_rule", "statement": "feels snappy", "kind": "advisory"},
    ]
    compiled = C.compile_rules(rules)

    assert len(compiled["tests"]) == 1
    assert compiled["tests"][0][0] == "tests/constitution/test_test_rule.py"

    assert compiled["commands"] == [("cmd_rule", "ruff check .")]

    assert len(compiled["advisory"]) == 1
    assert compiled["advisory"][0]["id"] == "adv_rule"


def test_compile_rules_demotes_junk_test_to_advisory():
    rules = [
        {
            "id": "broken",
            "statement": "claims to be a test but is not",
            "kind": "test",
            "check_code": "this is not valid python at all !!!",
        }
    ]
    compiled = C.compile_rules(rules)
    # Not seeded as a test...
    assert compiled["tests"] == []
    # ...but kept as advisory (never silently dropped).
    assert len(compiled["advisory"]) == 1
    assert compiled["advisory"][0]["id"] == "broken"


# --------------------------------------------------------------------------- #
# immutable_test_paths
# --------------------------------------------------------------------------- #

def test_immutable_test_paths_returns_compiled_test_paths():
    rules = [
        {
            "id": "r1",
            "statement": "s1",
            "kind": "test",
            "check_code": "def test_one():\n    assert True\n",
        },
        {
            "id": "r2",
            "statement": "s2",
            "kind": "test",
            "check_code": "def test_two():\n    assert True\n",
        },
    ]
    compiled = C.compile_rules(rules)
    paths = C.immutable_test_paths(compiled)
    assert paths == {
        "tests/constitution/test_r1.py",
        "tests/constitution/test_r2.py",
    }


# --------------------------------------------------------------------------- #
# aderive_constitution
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_aderive_constitution_drops_invalid_rules():
    valid = {
        "id": "perf_budget",
        "statement": "Home page loads under 2s.",
        "kind": "command",
        "check_cmd": "true",
    }
    invalid = {"statement": "missing id and kind"}  # fails RULE_SCHEMA
    runner = FakeRunner()
    runner.queue(json.dumps({"rules": [valid, invalid]}))

    rules = await C.aderive_constitution(
        runner, brief="A fast web app.", project_name="Demo"
    )

    assert len(rules) == 1
    assert rules[0]["id"] == "perf_budget"
    # Ran the constitution persona.
    assert "constitution" in runner.calls[0]["system_prompt"].lower()
    # Prompt included the brief.
    assert "A fast web app." in runner.calls[0]["prompt"]


@pytest.mark.asyncio
async def test_aderive_constitution_caps_at_max_rules():
    def _rule(i: int) -> dict:
        return {
            "id": f"rule_{i}",
            "statement": f"rule number {i}",
            "kind": "advisory",
        }

    runner = FakeRunner()
    runner.queue(json.dumps({"rules": [_rule(i) for i in range(10)]}))

    rules = await C.aderive_constitution(runner, brief="brief", max_rules=3)
    assert len(rules) == 3


@pytest.mark.asyncio
async def test_aderive_constitution_empty_on_unusable_reply():
    runner = FakeRunner()
    # No `rules` list at all, twice (one retry) → arun_json raises → [] returned.
    runner.queue(json.dumps({"nope": True}))
    runner.queue(json.dumps({"nope": True}))
    rules = await C.aderive_constitution(runner, brief="brief")
    assert rules == []
