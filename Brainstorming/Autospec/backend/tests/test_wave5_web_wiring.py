"""Wave 5 (supervised run 2026-09-22): the web-bootstrap task guard.

Observed factory defect on a fullstack "Counter webapp": the 8 planned tasks all
merged green, yet ``main.py`` was never touched and no file mentioned
``uvicorn`` - every feature published its routes through the auto-discovery
convention and waited for a mounter no task owned. The smoke run then failed
with "the process exited (code 0) without listening on 127.0.0.1:8000".

These tests cover the deterministic guard that closes the hole
(``Pipeline._ensure_web_wiring_task``, flag ``WEB_WIRING_TASK``) and the prompt
reminders that make the planner carry the task itself.
"""

from __future__ import annotations

import pytest

from autospec.agents import prompts
from autospec.agents.scripted import ScriptedRunner
from autospec.config import settings
from autospec.models import (
    ChatRole,
    Epic,
    ProjectState,
    Stream,
    StreamKind,
    StoryStatus,
    Task,
    UserStory,
)
from autospec.orchestrator.pipeline import Pipeline


# --------------------------------------------------------------------- setup

@pytest.fixture(autouse=True)
def _guard_on(monkeypatch):
    """The guard is pinned OFF by the hermetic conftest; this module opts in."""
    monkeypatch.setattr(settings, "web_wiring_task", True)
    monkeypatch.setattr(settings, "fake_agents", True)


def _task(tid, story_id, *, stream="backend", globs=(), deps=()):
    return Task(
        id=tid,
        story_id=story_id,
        stream=stream,
        title=tid,
        gherkin="Feature: F\n  Scenario: S\n    Given a\n    When b\n    Then c",
        depends_on=list(deps),
        files_hint=list(globs),
        status=StoryStatus.TODO,
    )


def _us(sid, *, stream="", tasks=None):
    return UserStory(
        id=sid,
        epic_id="EPIC-1",
        title=sid,
        gherkin="Feature: F\n  Scenario: S\n    Given a\n    When b\n    Then c",
        stream=stream,
        tasks=list(tasks or []),
    )


def _state(stories, *, profile="auto", with_frontend=True, project_id="web-wiring"):
    st = ProjectState(id=project_id, name="counterwebapp", goal="compter")
    st.product_profile = profile
    st.epics.append(Epic(id="EPIC-1", title="E"))
    st.streams = [Stream(id="backend", kind=StreamKind.BACKEND, language="python", primary=True)]
    if with_frontend:
        st.streams.append(
            Stream(id="frontend", kind=StreamKind.FRONTEND, language="react", file_root="frontend")
        )
    st.stories = stories
    return st


def _pipeline(state):
    return Pipeline(state, ScriptedRunner())


def _web_tasks(state):
    return [t for t in state.all_tasks() if t.id.endswith("-WEB")]


# --------------------------------------------------------------- (a) the hole

def test_adds_web_task_when_nobody_claims_main_py():
    """The real defect shape: two green backend tasks, no `main.py` anywhere."""
    state = _state([
        _us("US-1", tasks=[
            _task("T-1", "US-1", globs=("counter_webapp/features/count.py",)),
            _task("T-2", "US-1", globs=("counter_webapp/features/increment.py",)),
        ]),
    ])
    pipe = _pipeline(state)
    pipe._ensure_web_wiring_task()

    added = _web_tasks(state)
    assert len(added) == 1
    web = added[0]
    assert web.id == "US-1-WEB"
    assert web.story_id == "US-1"
    assert web.stream == "backend"
    # It CLOSES the backend chain: it waits for every other backend task.
    assert set(web.depends_on) == {"T-1", "T-2"}
    assert "main.py" in web.files_hint
    assert "pyproject.toml" in web.files_hint
    assert any(g.endswith("/app.py") for g in web.files_hint)
    # The contract the smoke gate checks is spelled out in the criteria.
    texts = " ".join(c.text for c in web.acceptance_criteria)
    assert "127.0.0.1:8000" in texts
    assert "--help" in texts
    assert web.gherkin.startswith("Feature:")
    assert web.complexity == "simple"
    # The operator is told, in the chat, that the plan was completed.
    assert any(
        m.role == ChatRole.SYSTEM and "amor" in m.content.lower() for m in state.chat
    )


def test_guard_is_idempotent():
    state = _state([
        _us("US-1", tasks=[_task("T-1", "US-1", globs=("counter_webapp/features/a.py",))]),
    ])
    pipe = _pipeline(state)
    pipe._ensure_web_wiring_task()
    pipe._ensure_web_wiring_task()
    assert len(_web_tasks(state)) == 1


def test_fullstack_profile_without_frontend_stream_still_guarded():
    """Intent, not artifact: the `fullstack` profile alone expects a server."""
    state = _state(
        [_us("US-1", tasks=[_task("T-1", "US-1", globs=("pkg/features/a.py",))])],
        profile="fullstack",
        with_frontend=False,
    )
    pipe = _pipeline(state)
    pipe._ensure_web_wiring_task()
    assert len(_web_tasks(state)) == 1


def test_creates_a_technical_story_when_no_container_exists():
    """No task container in the pool: the guard must NOT turn a taskless (leaf)
    story into a container, so it creates a technical story instead."""
    state = _state([_us("US-1"), _us("US-2")])
    pipe = _pipeline(state)
    pipe._ensure_web_wiring_task()

    added = _web_tasks(state)
    assert len(added) == 1
    ts = next(s for s in state.stories if s.id == added[0].story_id)
    assert ts.technical is True
    assert ts.contract
    assert ts.iteration == state.iteration
    # It closes the chain at the STORY level too (no backend task to wait for).
    assert set(ts.depends_on) == {"US-1", "US-2"}
    assert state.stories[0].tasks == [] and state.stories[1].tasks == []


# ------------------------------------------------- (b) the plan already owns it

def test_no_task_when_a_unit_already_claims_main_py():
    state = _state([
        _us("US-1", tasks=[
            _task("T-1", "US-1", globs=("counter_webapp/features/a.py",)),
            _task("T-2", "US-1", globs=("main.py", "pyproject.toml")),
        ]),
    ])
    pipe = _pipeline(state)
    pipe._ensure_web_wiring_task()
    assert _web_tasks(state) == []


def test_no_task_when_a_taskless_story_names_main_py():
    story = _us("US-1")
    story.description = "Exposer l'API et faire que main.py démarre le serveur."
    state = _state([story])
    pipe = _pipeline(state)
    pipe._ensure_web_wiring_task()
    assert _web_tasks(state) == []


# -------------------------------------------------- (c) non-web / (d) flag OFF

def test_no_task_for_a_cli_product():
    state = _state(
        [_us("US-1", tasks=[_task("T-1", "US-1", globs=("pkg/a.py",))])],
        profile="cli",
        with_frontend=False,
    )
    pipe = _pipeline(state)
    pipe._ensure_web_wiring_task()
    assert _web_tasks(state) == []


def test_no_task_when_flag_is_off(monkeypatch):
    monkeypatch.setattr(settings, "web_wiring_task", False)
    state = _state([_us("US-1", tasks=[_task("T-1", "US-1", globs=("pkg/a.py",))])])
    pipe = _pipeline(state)
    pipe._ensure_web_wiring_task()
    assert _web_tasks(state) == []


def test_no_task_for_a_non_python_backend():
    from autospec.models import BackendLanguage

    state = _state([_us("US-1", tasks=[_task("T-1", "US-1", globs=("pkg/a.go",))])])
    state.backend_language = BackendLanguage.GO
    pipe = _pipeline(state)
    pipe._ensure_web_wiring_task()
    assert _web_tasks(state) == []


def test_frontend_only_tasks_are_not_counted_as_backend(monkeypatch):
    monkeypatch.setattr(settings, "streams_enabled", True)
    state = _state([
        _us("US-1", stream="frontend", tasks=[
            _task("T-FE", "US-1", stream="frontend", globs=("frontend/src/App.tsx",)),
        ]),
        _us("US-2", tasks=[_task("T-BE", "US-2", globs=("pkg/features/a.py",))]),
    ])
    pipe = _pipeline(state)
    pipe._ensure_web_wiring_task()

    added = _web_tasks(state)
    assert len(added) == 1
    assert added[0].story_id == "US-2"
    assert set(added[0].depends_on) == {"T-BE"}  # the frontend task is NOT a dep


# ------------------------------------------------------- (e) independence floor

def test_guard_survives_the_independence_floor(monkeypatch):
    """The WEB task declares `pyproject.toml`, which another task also claims:
    the global floor must SERIALIZE them (no crash, no cycle)."""
    monkeypatch.setattr(settings, "streams_enabled", True)
    state = _state([
        _us("US-1", tasks=[
            _task("T-1", "US-1", globs=("pyproject.toml", "pkg/features/a.py")),
            _task("T-2", "US-1", globs=("pkg/features/b.py",)),
        ]),
    ])
    pipe = _pipeline(state)
    pipe._ensure_web_wiring_task()
    pipe._enforce_global_independence()

    web = _web_tasks(state)[0]
    assert "T-1" in web.depends_on          # the pyproject overlap is ordered
    assert web.id not in state.task("T-1").depends_on  # and never the other way
    assert web.id not in state.task("T-2").depends_on


# ------------------------------------------------------------- (f) the prompts

def test_prompts_require_a_web_bootstrap_task():
    state = _state([_us("US-1")])
    streams_block = prompts._streams_plan_block(state).lower()
    sizing = prompts.sizing_rules().lower()
    assert "amor" in streams_block and "app factory" in streams_block
    assert "amor" in sizing and "app factory" in sizing

    story = _us("US-1")
    decompose = prompts.decompose_story(story, "pkg").lower()
    assert "amor" in decompose and "main.py" in decompose

    dev = prompts.dev_story(story, "pkg", "features/us-1.feature")
    assert "SI TA TÂCHE PORTE `main.py` DANS SON PÉRIMÈTRE" in dev
    assert "ne lie AUCUN port" in dev


def test_main_template_documents_the_web_contract():
    from autospec.orchestrator.workspace import MAIN_TEMPLATE

    assert "WEB PRODUCT" in MAIN_TEMPLATE
    assert "BARE entry point MUST" in MAIN_TEMPLATE
    assert "create_app()" in MAIN_TEMPLATE
