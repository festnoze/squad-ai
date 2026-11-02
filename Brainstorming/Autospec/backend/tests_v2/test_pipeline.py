"""End-to-end pipeline tests: real uv, real git, real clean suites, scripted agents."""

import json
import shutil
import subprocess
import textwrap
from dataclasses import replace

import pytest

from autospec.core import fake, profiles
from autospec.core.fake import FakeRunner, demo_dev, demo_plan, demo_qa, write
from autospec.core.models import Phase, ProjectState, Profile, StoryStatus
from autospec.core.pipeline import Pipeline
from autospec.core.ports import AgentError
from autospec.core.settings import Settings
from autospec.core.store import Store

PKG = "greeter"
BRIEF = "# Greeter\nA library that greets people."


@pytest.fixture(scope="module")
def template(tmp_path_factory):
    ws = tmp_path_factory.mktemp("template") / "greeter"
    ws.mkdir()
    profiles.scaffold(ws, project_name="Greeter", package=PKG, profile=Profile.LIB)
    return ws


@pytest.fixture
def ws(template, tmp_path):
    target = tmp_path / "greeter"
    shutil.copytree(template, target, ignore=shutil.ignore_patterns(".venv", ".autospec"))
    return target


@pytest.fixture
def settings(tmp_path):
    return Settings(workspace_root=tmp_path, qa_max_attempts=2, dev_max_attempts=2,
                    suite_timeout_s=300, smoke_timeout_s=60, project_budget_usd=100, call_budget_usd=5)


def _state(**kwargs):
    base = dict(id="greeter-1", name="Greeter", package=PKG, profile=Profile.LIB, brief=BRIEF)
    return ProjectState(**{**base, **kwargs})


def _runner(**overrides):
    handlers = {"pm": json.dumps({"brief": BRIEF}), "po": demo_plan(PKG), "qa": demo_qa(PKG), "dev": demo_dev(PKG)}
    handlers.update(overrides)
    return FakeRunner(handlers)


def _git_log(ws):
    out = subprocess.run(["git", "log", "--format=%s"], cwd=ws, capture_output=True, text=True, check=True)
    return out.stdout.split("\n")[::-1][1:]


async def test_project_is_built_story_by_story_and_delivered(ws, settings):
    runner = _runner()
    state = await Pipeline(_state(), ws, runner, settings).arun()

    assert state.phase == Phase.DONE, state.error
    assert [(s.id, s.status, s.attempts) for s in state.stories] == [
        ("US-1", StoryStatus.DONE, 1), ("US-2", StoryStatus.DONE, 1)]
    assert runner.roles() == ["po", "qa", "dev", "qa", "dev"]
    assert _git_log(ws) == ["scaffold", "US-1: acceptance tests", "US-1 done",
                            "US-2: acceptance tests", "US-2 done"]
    assert state.usage.calls == 5
    assert state.stories[0].test_fingerprint, "QA tests are fingerprinted"
    persisted = Store(ws).load()
    assert persisted.phase == Phase.DONE
    assert any(e["type"] == "smoke" and e["ok"] for e in Store(ws).events())


async def test_brief_is_written_by_the_pm_when_only_a_goal_is_given(ws, settings):
    runner = _runner()
    state = await Pipeline(_state(brief="", goal="greet people"), ws, runner, settings).arun()

    assert state.phase == Phase.DONE, state.error
    assert runner.roles()[0] == "pm" and state.brief == BRIEF


async def test_invalid_plan_gets_one_correction_in_the_same_session(ws, settings):
    runner = _runner(po=["this is not a plan", demo_plan(PKG)])
    state = await Pipeline(_state(), ws, runner, settings).arun()

    assert state.phase == Phase.DONE, state.error
    po_calls = [c for c in runner.calls if c.role == "po"]
    assert len(po_calls) == 2
    assert po_calls[1].resume_session_id == "fake-po-1"
    assert "rejected" in po_calls[1].prompt


async def test_acceptance_tests_that_never_touch_the_product_are_rejected(ws, settings):
    def vacuous(call):
        write(call, {"tests/acceptance/test_us_1.py": textwrap.dedent("""
            def test_ac1_x():
                assert True


            def test_ac2_y():
                assert True
            """)})
        return json.dumps({"tests": [{"ac_id": "US-1.AC-1", "nodeids": ["tests/acceptance/test_us_1.py::test_ac1_x"]},
                                     {"ac_id": "US-1.AC-2", "nodeids": ["tests/acceptance/test_us_1.py::test_ac2_y"]}]})

    runner = _runner(qa=[vacuous, demo_qa(PKG)])
    state = await Pipeline(_state(), ws, runner, settings).arun()

    assert state.phase == Phase.DONE, state.error
    qa_calls = [c for c in runner.calls if c.role == "qa"]
    assert "never references the package" in qa_calls[1].prompt
    assert qa_calls[1].resume_session_id is not None


async def test_a_story_already_delivered_by_earlier_ones_skips_the_dev(ws, settings):
    def dev_does_both(call):
        write(call, {f"{PKG}/greet.py": fake._CODE["US-2"]})
        return json.dumps({"summary": "greet and shout"})

    runner = _runner(dev=dev_does_both)
    state = await Pipeline(_state(), ws, runner, settings).arun()

    assert state.phase == Phase.DONE, state.error
    assert runner.roles() == ["po", "qa", "dev", "qa"], "no dev session for US-2"
    assert state.story("US-2").status == StoryStatus.DONE and state.story("US-2").attempts == 0
    assert "US-2: acceptance tests" in _git_log(ws)


async def test_a_test_already_green_thanks_to_earlier_code_is_kept(ws, settings):
    def partly_green(call):
        answer = demo_qa(PKG)(call)
        write(call, {"tests/acceptance/test_us_1.py": textwrap.dedent(f"""
            def test_ac1_greets_by_name():
                from {PKG}.greet import greet
                assert greet('Ada') == 'Hello, Ada!'


            def test_ac2_empty_name_greets_the_world():
                assert 1 + 1 == 2
            """)})
        return answer

    runner = _runner(qa=[partly_green, demo_qa(PKG)])
    state = await Pipeline(_state(), ws, runner, settings).arun()

    assert state.phase == Phase.DONE, state.error
    assert [c.role for c in runner.calls].count("qa") == 2, "no QA retry for US-1"
    green = [e for e in Store(ws).events() if e["type"] == "already_green"]
    assert green and green[0]["nodeids"] == ["tests/acceptance/test_us_1.py::test_ac2_empty_name_greets_the_world"]


async def test_qa_writing_product_code_is_reverted(ws, settings):
    def sneaky(call):
        write(call, {f"{PKG}/greet.py": "def greet(name):\n    return 'Hello, Ada!'\n"})
        return demo_qa(PKG)(call)

    runner = _runner(qa=[sneaky, demo_qa(PKG)])
    state = await Pipeline(_state(), ws, runner, settings).arun()

    assert state.phase == Phase.DONE, state.error
    second_prompt = [c for c in runner.calls if c.role == "qa"][1].prompt
    assert f"{PKG}/greet.py" in second_prompt and "outside" in second_prompt


async def test_dev_editing_acceptance_tests_is_reverted_then_retried(ws, settings):
    def cheat(call):
        write(call, {"tests/acceptance/test_us_1.py": "def test_ac1_greets_by_name():\n    assert True\n"})
        return json.dumps({"summary": "done"})

    runner = _runner(dev=[cheat, demo_dev(PKG)])
    state = await Pipeline(_state(), ws, runner, settings).arun()

    assert state.phase == Phase.DONE, state.error
    us1 = state.story("US-1")
    assert us1.attempts == 2
    dev_calls = [c for c in runner.calls if c.role == "dev"]
    assert dev_calls[1].resume_session_id == "fake-dev-3", "the retry continues the same session"
    assert "acceptance tests" in dev_calls[1].prompt
    original = (ws / "tests/acceptance/test_us_1.py").read_text(encoding="utf-8")
    assert "Hello, Ada!" in original


async def test_dev_conftest_hook_forcing_green_is_rejected(ws, settings):
    hook = textwrap.dedent("""
        import pytest


        @pytest.hookimpl(hookwrapper=True)
        def pytest_runtest_makereport(item, call):
            outcome = yield
            report = outcome.get_result()
            report.outcome = "passed"
        """)

    def cheat(call):
        write(call, {"tests/conftest.py": hook})
        return json.dumps({"summary": "done"})

    runner = _runner(dev=[cheat, demo_dev(PKG)])
    state = await Pipeline(_state(), ws, runner, settings).arun()

    assert state.phase == Phase.DONE, state.error
    assert state.story("US-1").attempts == 2
    assert "conftest.py" in [c for c in runner.calls if c.role == "dev"][1].prompt
    assert not (ws / "tests/conftest.py").exists()


async def test_dev_changing_pytest_options_is_rejected(ws, settings):
    def cheat(call):
        pyproject = ws / "pyproject.toml"
        text = pyproject.read_text(encoding="utf-8")
        tampered = '[tool.pytest.ini_options]\naddopts = "--ignore=tests/acceptance"'
        pyproject.write_text(text.replace("[tool.pytest.ini_options]", tampered), encoding="utf-8")
        return json.dumps({"summary": "done"})

    def honest(call):
        subprocess.run(["git", "checkout", "--", "pyproject.toml"], cwd=ws, check=True)
        return demo_dev(PKG)(call)

    runner = _runner(dev=[cheat, honest])
    state = await Pipeline(_state(), ws, runner, settings).arun()

    assert state.phase == Phase.DONE, state.error
    assert "[tool.pytest]" in [c for c in runner.calls if c.role == "dev"][1].prompt


async def test_story_that_never_goes_green_parks_the_project(ws, settings):
    def wrong(call):
        write(call, {f"{PKG}/greet.py": "def greet(name):\n    return 'nope'\n"})
        return json.dumps({"summary": "done"})

    runner = _runner(dev=wrong)
    state = await Pipeline(_state(), ws, runner, settings).arun()

    assert state.phase == Phase.NEEDS_ATTENTION
    assert state.story("US-1").status == StoryStatus.FAILED
    assert state.story("US-1").attempts == settings.dev_max_attempts
    assert state.story("US-2").status == StoryStatus.TODO
    assert "US-1" in state.error and "not green" in state.error

    # A human fixes nothing but resumes with a working agent: QA is not redone.
    resumed_runner = _runner()
    resumed = await Pipeline(Store(ws).load(), ws, resumed_runner, settings).arun()
    assert resumed.phase == Phase.DONE, resumed.error
    assert resumed_runner.roles() == ["dev", "qa", "dev"]


async def test_agent_timeout_costs_an_attempt_and_restarts_a_fresh_session(ws, settings):
    runner = _runner(dev=[AgentError("too slow", "timeout"), demo_dev(PKG)])
    state = await Pipeline(_state(), ws, runner, settings).arun()

    assert state.phase == Phase.DONE, state.error
    assert state.story("US-1").attempts == 2
    dev_calls = [c for c in runner.calls if c.role == "dev"]
    assert dev_calls[1].resume_session_id is None


async def test_project_budget_parks_before_overspending(ws, settings):
    runner = _runner()
    state = await Pipeline(_state(), ws, runner, replace(settings, project_budget_usd=0.025)).arun()

    assert state.phase == Phase.NEEDS_ATTENTION
    assert "budget" in state.error
    assert len(runner.calls) == 3


async def test_a_done_project_is_left_alone(ws, settings):
    runner = _runner()
    state = await Pipeline(_state(phase=Phase.DONE), ws, runner, settings).arun()
    assert state.phase == Phase.DONE and runner.calls == []


def test_cli_fake_run_prints_a_json_summary_last(tmp_path):
    import sys
    brief = tmp_path / "brief.md"
    brief.write_text(BRIEF, encoding="utf-8")
    out = subprocess.run(
        [sys.executable, "-m", "autospec.core", "run", "--name", "Greeter", "--profile", "lib",
         "--brief-file", str(brief), "--workspace-root", str(tmp_path / "root"), "--fake"],
        capture_output=True, text=True, encoding="utf-8", timeout=600)
    summary = json.loads(out.stdout.strip().splitlines()[-1])

    assert out.returncode == 0, out.stderr[-3000:]
    assert summary["phase"] == "done"
    assert [s["status"] for s in summary["stories"]] == ["done", "done"]
    assert summary["usage"]["calls"] == 5
