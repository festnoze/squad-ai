"""Refactor P0/P4: the failure-recovery + task-independence safety net.

Covers:
- the pure deterministic analyzer (orchestrator/independence.py),
- the scheduler's DECLARED-overlap guard (two file-overlapping items never
  co-run), reproducing the real todo_list_2 failure shape,
- the floor injecting depends_on at task creation,
- P0 hardening: orphan reset on resume, non-fatal worker, repo kept clean of
  bookkeeping files.
"""

import asyncio

import pytest

from autospec.agents.scripted import ScriptedRunner
from autospec.config import settings
from autospec.models import (
    Epic,
    ProjectState,
    Stream,
    StoryStatus,
    StreamKind,
    Task,
    UserStory,
)
from autospec.orchestrator import independence
from autospec.orchestrator.pipeline import Pipeline
from autospec.storage import workspace_dir


# --------------------------------------------------------------- pure analyzer

def _claim(cid, stream, globs=(), deps=()):
    return independence.TaskClaim(id=cid, stream=stream, file_globs=tuple(globs), depends_on=tuple(deps))


def test_globs_overlap_and_disjoint():
    assert independence.globs_overlap("frontend/src/App.tsx", "frontend/src/App.tsx")
    assert independence.globs_overlap("frontend/src/components/*.tsx", "frontend/src/components/TodoItem.tsx")
    assert not independence.globs_overlap("backend/api/router.py", "frontend/src/X.tsx")
    assert not independence.globs_overlap("frontend/src/A.tsx", "frontend/src/B.tsx")


def test_analyze_reproduces_todo_list_2_serializes_app_tsx():
    # The real failure: two frontend tasks both editing App.tsx, scheduled
    # parallel with no ordering -> must be serialized.
    tasks = [
        _claim("T-3-fe", "frontend", ("frontend/src/App.tsx",), ("T-3-be",)),
        _claim("T-4-fe", "frontend", ("frontend/src/App.tsx",), ("T-4-be",)),
    ]
    report = independence.analyze(tasks)
    assert ("T-3-fe", "T-4-fe") in report.conflict_pairs
    # The later task gains a dependency on the earlier one (stable order).
    assert report.added_deps.get("T-4-fe") == ("T-3-fe",)


def test_analyze_keeps_disjoint_components_parallel():
    tasks = [
        _claim("A", "frontend", ("frontend/src/components/TodoItem.tsx",)),
        _claim("B", "frontend", ("frontend/src/components/TodoList.tsx",)),
    ]
    report = independence.analyze(tasks)
    assert report.conflict_pairs == []
    assert report.added_deps == {}
    assert any(set(c) == {"A", "B"} for c in report.parallel_classes)


def test_analyze_empty_globs_serialized_and_warned():
    tasks = [_claim("A", "backend"), _claim("B", "backend")]
    report = independence.analyze(tasks)
    assert ("A", "B") in report.conflict_pairs
    assert len(report.warnings) == 2  # both lack file claims


def test_cross_stream_same_real_file_is_serialized():
    # P1 fix: two tasks of DIFFERENT streams that both DECLARE the same repo-root
    # file (README.md, .gitignore, main.py…) DO conflict on merge — the stream is
    # not a safe disjointer for declared paths.
    tasks = [
        _claim("be", "backend", ("README.md",)),
        _claim("fe", "frontend", ("README.md",)),
    ]
    assert ("be", "fe") in independence.analyze(tasks).conflict_pairs


def test_cross_stream_disjoint_paths_stay_parallel():
    # Different streams touching their OWN file_roots remain independent.
    tasks = [
        _claim("be", "backend", ("backend/api/router.py",)),
        _claim("fe", "frontend", ("frontend/src/App.tsx",)),
    ]
    assert independence.analyze(tasks).conflict_pairs == []


def test_cross_stream_empty_claims_presumed_disjoint():
    # Unspecified claims only span their own stream's file_root → backend ‖ frontend.
    assert not independence.claims_overlap(_claim("be", "backend"), _claim("fe", "frontend"))


def test_declared_overlap_ignores_undeclared():
    # The scheduler backstop only fires on DECLARED overlaps (never deadlocks
    # same-stream siblings whose claims are unset — the floor orders those).
    a = _claim("A", "backend")               # no globs
    b = _claim("B", "backend", ("x.py",))
    assert not independence.declared_overlap(a, b)
    c = _claim("C", "backend", ("x.py",))
    assert independence.declared_overlap(b, c)
    # Cross-stream declared overlap is caught too (shared root file).
    assert independence.declared_overlap(
        _claim("x", "backend", ("README.md",)), _claim("y", "frontend", ("README.md",))
    )


def test_declared_serialization_global_cross_story():
    # Two tasks of DIFFERENT stories both declaring pyproject.toml must be ordered.
    tasks = [
        _claim("T-A", "backend", ("pyproject.toml", "pkg/a.py")),
        _claim("T-B", "backend", ("pyproject.toml", "pkg/b.py")),
    ]
    edges = independence.declared_serialization(tasks)
    assert edges.get("T-B") == ("T-A",)
    # Disjoint declared tasks get no edge.
    assert independence.declared_serialization(
        [_claim("T-A", "backend", ("pkg/a.py",)), _claim("T-B", "backend", ("pkg/b.py",))]
    ) == {}


# --------------------------------------------------------------- pipeline wiring

def _streams_state(stories, project_id="indep-proj"):
    st = ProjectState(id=project_id, name="indepapp", goal="g")
    st.epics.append(Epic(id="EPIC-1", title="E"))
    st.streams = [
        Stream(id="backend", kind=StreamKind.BACKEND, language="python", primary=True),
        Stream(id="frontend", kind=StreamKind.FRONTEND, language="react", file_root="frontend"),
    ]
    st.stories = stories
    return st


def _us(sid, *, stream="", tasks=None, status=StoryStatus.TODO):
    return UserStory(
        id=sid, epic_id="EPIC-1", title=sid,
        gherkin="Feature: F\n  Scenario: S\n    Given a\n    When b\n    Then c",
        stream=stream, tasks=tasks or [], status=status,
    )


def _task(tid, story_id, *, stream="", globs=(), deps=(), status=StoryStatus.TODO):
    return Task(
        id=tid, story_id=story_id, stream=stream, title=tid,
        gherkin="Feature: F\n  Scenario: S\n    Given a\n    When b\n    Then c",
        depends_on=list(deps), files_hint=list(globs), status=status,
    )


@pytest.fixture
def streams_on(monkeypatch):
    monkeypatch.setattr(settings, "streams_enabled", True)
    monkeypatch.setattr(settings, "fake_agents", True)


def test_global_pass_serializes_cross_story_shared_file(streams_on):
    state = _streams_state([
        _us("US-1", tasks=[_task("T-1", "US-1", stream="backend", globs=("pyproject.toml", "pkg/a.py"))]),
        _us("US-2", tasks=[_task("T-2", "US-2", stream="backend", globs=("pyproject.toml", "pkg/b.py"))]),
    ])
    pipeline = Pipeline(state, ScriptedRunner())
    pipeline._enforce_global_independence()
    # The later-declared task (T-2) now waits for T-1 — no cross-story merge clash.
    assert "T-1" in state.task("T-2").depends_on


def test_enforce_independence_injects_depends_on(streams_on):
    state = _streams_state([_us("US-1")])
    pipeline = Pipeline(state, ScriptedRunner())
    tasks = [
        _task("T-1", "US-1", stream="frontend", globs=("frontend/src/App.tsx",)),
        _task("T-2", "US-1", stream="frontend", globs=("frontend/src/App.tsx",)),
    ]
    pipeline._enforce_task_independence(tasks, label="US-1")
    assert "T-1" in tasks[1].depends_on  # T-2 now waits for T-1


async def test_scheduler_never_coruns_declared_overlap(streams_on, monkeypatch):
    """Two same-stream tasks that DECLARE the same file must never build at the
    same time (the todo_list_2 fix), yet both still reach DONE."""
    state = _streams_state([
        _us("US-1", tasks=[
            _task("T-A", "US-1", stream="frontend", globs=("frontend/src/App.tsx",)),
            _task("T-B", "US-1", stream="frontend", globs=("frontend/src/App.tsx",)),
        ])
    ])
    # No injected deps here: prove the SCHEDULER guard alone prevents co-running.
    pipeline = Pipeline(state, ScriptedRunner())

    concurrent = {"max": 0, "now": 0}

    async def _spy(subject, worktree, pkg, is_frontend):
        concurrent["now"] += 1
        concurrent["max"] = max(concurrent["max"], concurrent["now"])
        await asyncio.sleep(0.02)
        concurrent["now"] -= 1
        return True, ""

    monkeypatch.setattr(pipeline, "_arun_item_dev", _spy)
    await asyncio.wait_for(pipeline._abuild_phase(), timeout=40)

    assert concurrent["max"] == 1, "overlapping-file tasks ran concurrently"
    assert all(t.status == StoryStatus.DONE for t in state.story("US-1").tasks)


def test_reset_orphan_items_unsticks_in_progress(streams_on):
    state = _streams_state([
        _us("US-1", tasks=[
            _task("T-done", "US-1", stream="backend", status=StoryStatus.DONE),
            _task("T-stuck", "US-1", stream="backend", status=StoryStatus.IN_PROGRESS),
        ]),
        _us("US-2", status=StoryStatus.IN_PROGRESS),
    ])
    pipeline = Pipeline(state, ScriptedRunner())
    n = pipeline._reset_orphan_items()
    assert n == 2
    assert state.task("T-stuck").status == StoryStatus.TODO
    assert state.task("T-done").status == StoryStatus.DONE   # preserved
    assert state.story("US-2").status == StoryStatus.TODO


async def test_one_worker_crash_does_not_kill_the_build(streams_on, monkeypatch):
    """P0b: a worker that raises an unexpected exception is isolated as FAILED;
    the independent sibling still reaches DONE (old behaviour tore down both)."""
    state = _streams_state([
        _us("US-1", stream="backend"),
        _us("US-2", stream="frontend"),
    ])
    pipeline = Pipeline(state, ScriptedRunner())

    async def _spy(subject, worktree, pkg, is_frontend):
        if subject.id == "US-1":
            raise RuntimeError("boom (simulated CLI crash)")
        return True, ""

    monkeypatch.setattr(pipeline, "_arun_item_dev", _spy)
    await asyncio.wait_for(pipeline._abuild_phase(), timeout=40)

    assert state.story("US-2").status == StoryStatus.DONE   # sibling survived
    assert state.story("US-1").status == StoryStatus.FAILED  # crash isolated


async def test_commit_excludes_bookkeeping_files(streams_on):
    """P0a: autospec-state.json / autospec-interactions.jsonl must never be
    committed into the generated project's git (they cause merge churn)."""
    state = _streams_state([_us("US-1")], project_id="indep-clean")
    pipeline = Pipeline(state, ScriptedRunner())
    ws = workspace_dir(state.id)
    ws.mkdir(parents=True, exist_ok=True)
    # Simulate the orchestrator having written its bookkeeping into the workspace.
    (ws / "autospec-state.json").write_text("{}", encoding="utf-8")
    (ws / "autospec-interactions.jsonl").write_text("{}\n", encoding="utf-8")
    (ws / "main.py").write_text("print('hi')\n", encoding="utf-8")

    assert await pipeline._agit_ensure_repo(ws)
    await pipeline._acommit_story(ws, "scaffold")

    code, out = await pipeline._agit(ws, "ls-files")
    tracked = out.split()
    assert "main.py" in tracked
    assert "autospec-state.json" not in tracked
    assert "autospec-interactions.jsonl" not in tracked
