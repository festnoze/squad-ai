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


def test_render_pytest_file_guards_thirdparty_imports():
    """A check_code with hard third-party imports gets pytest.importorskip guards
    BEFORE the imports: compiled right after SPEC, the dependency may not have
    been delivered yet — the invariant must SKIP, not break suite collection."""
    rule = {
        "id": "health-contract",
        "statement": "GET /api/health returns 200.",
        "kind": "test",
        "check_code": (
            "import importlib\n"
            "import pytest\n"
            "from fastapi.testclient import TestClient\n"
            "import httpx\n\n"
            "def test_health():\n    assert True\n"
        ),
    }
    result = C.render_pytest_file(rule)
    assert result is not None
    _, content = result
    guard_fastapi = content.index('pytest.importorskip("fastapi")')
    guard_httpx = content.index('pytest.importorskip("httpx")')
    real_import = content.index("from fastapi.testclient import TestClient")
    assert guard_fastapi < real_import
    assert guard_httpx < real_import
    # stdlib and pytest itself are never guarded.
    assert 'importorskip("importlib")' not in content
    assert 'importorskip("pytest")' not in content


def test_render_pytest_file_guards_nested_imports_too():
    """The agent often nests the third-party import in a helper (``def _client():
    from fastapi.testclient import TestClient``): it then raises at RUN time
    instead of collection time — same red suite. Nested imports must also
    trigger the module-level importorskip guard."""
    rule = {
        "id": "title-required",
        "statement": "422 on missing title.",
        "kind": "test",
        "check_code": (
            "import importlib\n\n"
            "def _client():\n"
            "    from fastapi.testclient import TestClient\n"
            "    return TestClient(None)\n\n"
            "def test_missing_title():\n"
            "    c = _client()\n    assert c is not None\n"
        ),
    }
    result = C.render_pytest_file(rule)
    assert result is not None
    _, content = result
    assert 'pytest.importorskip("fastapi")' in content
    # Guard sits at module level, BEFORE the function defs.
    assert content.index('importorskip("fastapi")') < content.index("def _client")


def test_render_pytest_file_stdlib_only_has_no_guard():
    rule = {
        "id": "pure-invariant",
        "statement": "Pure rule.",
        "kind": "test",
        "check_code": "import json\n\ndef test_pure():\n    assert json.loads('1') == 1\n",
    }
    result = C.render_pytest_file(rule)
    assert result is not None
    _, content = result
    assert "importorskip" not in content


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
