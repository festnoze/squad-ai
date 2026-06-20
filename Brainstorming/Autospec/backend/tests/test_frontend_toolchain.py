"""ST-6/ST-7/ST-8: frontend stream toolchain, scaffold, dev routing & run.

Hermetic: no real node/vite/vitest is invoked. The toolchain functions are pure
(command building + JSON parsing); the scaffold writes files to a tmp workspace;
the dev-agent green path runs with `fake_agents` so Vitest/build are
short-circuited exactly like the backend pytest path.
"""

from __future__ import annotations

import json

from autospec.config import settings
from autospec.models import (
    AcceptanceCriterion,
    Epic,
    ProjectState,
    Stream,
    StreamKind,
    StoryStatus,
    UserStory,
)
from autospec.orchestrator import toolchain, workspace
from autospec.orchestrator.pipeline import Pipeline
from autospec.agents.scripted import ScriptedRunner


# --------------------------------------------------------------- toolchain (ST-6)

def test_is_frontend_recognizes_react_keys():
    for key in ("frontend", "react", "React", "vite", "ts", "typescript"):
        assert toolchain.is_frontend(key)
    assert not toolchain.is_frontend("python")
    assert not toolchain.is_frontend("go")
    assert not toolchain.is_frontend("")
    # normalize() must NOT map a frontend key to a backend language.
    assert toolchain.normalize("react") == "python"  # unknown backend -> python default


def test_frontend_test_command_shape():
    cmd = toolchain.test_command("react", "/tmp/vitest.json")
    assert cmd[0] == settings.npm_cmd
    assert "vitest" in cmd and "run" in cmd
    assert "--reporter=json" in cmd
    assert "--outputFile=/tmp/vitest.json" in cmd


def test_frontend_build_and_run_command_shape():
    assert toolchain.frontend_build_command() == [settings.npm_cmd, "run", "build"]
    assert toolchain.run_command("react") == [settings.npm_cmd, "run", "preview"]
    assert toolchain.run_command("frontend", ["--port", "5050"]) == [
        settings.npm_cmd, "run", "preview", "--", "--port", "5050",
    ]


_VITEST_PASS = json.dumps(
    {
        "numTotalTests": 2,
        "testResults": [
            {
                "name": "src/Counter.test.tsx",
                "assertionResults": [
                    {"ancestorTitles": ["Counter"], "title": "renders", "status": "passed"},
                    {"ancestorTitles": ["Counter"], "title": "increments", "status": "passed"},
                ],
            }
        ],
    }
)

_VITEST_FAIL = json.dumps(
    {
        "testResults": [
            {
                "name": "src/Counter.test.tsx",
                "assertionResults": [
                    {"ancestorTitles": ["Counter"], "title": "renders", "status": "passed"},
                    {"ancestorTitles": ["Counter"], "title": "increments", "status": "failed"},
                    {"ancestorTitles": [], "title": "todo case", "status": "todo"},
                ],
            }
        ],
    }
)


def test_parse_vitest_pass(tmp_path):
    report = tmp_path / "v.json"
    report.write_text(_VITEST_PASS, encoding="utf-8")
    res = toolchain.parse_results("react", "noise on stdout", str(report))
    assert res == {
        "src/Counter.test.tsx::Counter > renders": "passed",
        "src/Counter.test.tsx::Counter > increments": "passed",
    }


def test_parse_vitest_fail(tmp_path):
    report = tmp_path / "v.json"
    report.write_text(_VITEST_FAIL, encoding="utf-8")
    res = toolchain.parse_results("react", "", str(report))
    assert res["src/Counter.test.tsx::Counter > increments"] == "failed"
    assert res["src/Counter.test.tsx::todo case"] == "skipped"


def test_parse_vitest_from_stdout_when_no_report_file():
    # No report path -> parse the JSON off stdout.
    res = toolchain.parse_frontend_results(_VITEST_PASS, "")
    assert len(res) == 2 and all(v == "passed" for v in res.values())


def test_parse_vitest_build_failure_yields_no_tests():
    # A failed `tsc && vite build` prints no JSON report.
    assert toolchain.parse_frontend_results("src/App.tsx(3,5): error TS2322: ...", "") == {}


def test_parse_build_errors_extracts_ts_errors():
    out = "\n".join(
        [
            "vite v5.2.0 building for production...",
            "src/App.tsx(7,3): error TS2322: Type 'number' is not assignable to type 'string'.",
            "Found 1 error.",
        ]
    )
    errs = toolchain.parse_build_errors(out)
    assert "TS2322" in errs and "error" in errs


# ----------------------------------------------------------------- scaffold (ST-6)

def _fe_state() -> ProjectState:
    return ProjectState(
        id="proj-fe",
        name="Mon App",
        goal="g",
        streams=[
            Stream(id="backend", kind=StreamKind.BACKEND, language="python", primary=True),
            Stream(id="frontend", kind=StreamKind.FRONTEND, language="react", file_root="frontend"),
        ],
    )


def test_frontend_scaffold_writes_expected_files(monkeypatch):
    monkeypatch.setattr(settings, "streams_enabled", True)
    state = _fe_state()
    workspace.scaffold(state)
    root = workspace.stream_root(state, state.stream("frontend"))
    for rel in (
        "package.json", "tsconfig.json", "vite.config.ts", "index.html",
        "src/main.tsx", "src/App.tsx", "src/App.test.tsx", "src/setupTests.ts",
    ):
        assert (root / rel).exists(), rel
    pkg = json.loads((root / "package.json").read_text(encoding="utf-8"))
    assert pkg["scripts"]["build"] == "tsc && vite build"
    assert "vitest" in pkg["devDependencies"]
    # Backend skeleton still present at the repo root.
    from autospec.storage import workspace_dir

    assert (workspace_dir(state.id) / "pyproject.toml").exists()


def test_scaffold_flag_off_skips_frontend(monkeypatch):
    monkeypatch.setattr(settings, "streams_enabled", False)
    state = _fe_state()
    workspace.scaffold(state)
    root = workspace.stream_root(state, state.stream("frontend"))
    assert not (root / "package.json").exists()


# --------------------------------------------------------- dev agent green (ST-7)

def test_scripted_runner_recognizes_frontend_dev_prompt():
    from autospec.agents import prompts

    story = UserStory(id="US-F1", epic_id="E1", title="Compteur", gherkin="Feature: x")
    prompt = prompts.dev_story_frontend(story, "app", "features/us_f1.feature")
    assert "PROCESSUS OBLIGATOIRE FRONTEND" in prompt
    reply = json.loads(ScriptedRunner._reply_for(prompt))
    assert reply["status"] == "green"
    # The backend dev prompt still maps to the backend canned reply.
    backend_prompt = prompts.dev_story(story, "app", "features/us_f1.feature")
    backend_reply = json.loads(ScriptedRunner._reply_for(backend_prompt))
    assert "tests/unit" in backend_reply["files"][1]


async def test_frontend_story_builds_green_in_demo_mode(monkeypatch):
    monkeypatch.setattr(settings, "streams_enabled", True)
    monkeypatch.setattr(settings, "fake_agents", True)
    state = ProjectState(
        id="proj-fe-build",
        name="App",
        goal="g",
        streams=[
            Stream(id="backend", kind=StreamKind.BACKEND, language="python", primary=True),
            Stream(id="frontend", kind=StreamKind.FRONTEND, language="react", file_root="frontend"),
        ],
        epics=[Epic(id="E1", title="Cœur")],
        stories=[
            UserStory(
                id="US-F1",
                epic_id="E1",
                title="Afficher un compteur",
                stream="frontend",
                acceptance_criteria=[AcceptanceCriterion(id="AC-1", text="le compteur s'affiche")],
                gherkin="Feature: Compteur\n  Scenario: x\n    Given y\n    When z\n    Then w",
            )
        ],
    )
    workspace.scaffold(state)
    pipe = Pipeline(state, ScriptedRunner())
    story = state.stories[0]
    assert pipe._is_frontend_story(story)

    # In demo mode the real vitest/build is short-circuited (green without node).
    ok, output, real = await pipe._arun_frontend_tests()
    assert ok and "court-circuit" in output

    await pipe._abuild_story(story)
    assert story.status == StoryStatus.DONE


async def test_flag_off_keeps_story_on_backend_path(monkeypatch):
    # streams OFF: a story tagged frontend is NOT routed to the frontend agent.
    monkeypatch.setattr(settings, "streams_enabled", False)
    state = ProjectState(
        id="proj-off",
        name="App",
        goal="g",
        stories=[UserStory(id="US-1", epic_id="E1", title="x", stream="frontend")],
    )
    pipe = Pipeline(state, ScriptedRunner())
    assert pipe._is_frontend_story(state.stories[0]) is False
