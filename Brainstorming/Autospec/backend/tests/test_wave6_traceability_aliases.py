"""Wave 6 (supervised run 2026-09-22): AC traceability in a MULTI-STREAM build.

Observed defect on project ``drv-p3-9ae648a7``: the monitor reported
``covered=0 uncovered=12 orphans=24`` while the generated tests were correct.
In a multi-stream build the build subject of an item is the TASK, and the
``dev_story`` prompt qualifies the AC marker with the item id, so the tests
carried ``TS1-T1.AC-1``. The report only declared STORY-qualified ids
(``TS-1.AC-1``), so every task-qualified marker was an orphan and every
criterion uncovered.

A task's acceptance criteria are a subset of its story's under the SAME bare
ids, so a task-qualified id is an ALIAS of the story-qualified one. The fix
declares both id spaces and folds the aliases back onto the canonical criteria
(:func:`autospec.orchestrator.traceability.fold_aliases`).
"""

from autospec.agents.runner import FakeRunner
from autospec.config import settings
from autospec.models import (
    AcceptanceCriterion,
    Epic,
    ProjectState,
    Task,
    UserStory,
)
from autospec.orchestrator import traceability
from autospec.orchestrator.pipeline import Pipeline


def _ac(cid: str) -> AcceptanceCriterion:
    return AcceptanceCriterion(id=cid, text=f"criterion {cid}")


def _task(tid: str, story_id: str, *criteria: str) -> Task:
    return Task(
        id=tid, story_id=story_id, stream="backend", title=tid,
        acceptance_criteria=[_ac(c) for c in criteria],
    )


def _story(sid: str, *criteria: str, tasks: list[Task] | None = None) -> UserStory:
    return UserStory(
        id=sid, epic_id="EPIC-1", title=sid, stream="backend",
        acceptance_criteria=[_ac(c) for c in criteria],
        tasks=list(tasks or []),
    )


def _pipeline(
    pid: str, stories: list[UserStory], sources: dict[str, str], monkeypatch,
) -> tuple[Pipeline, list[tuple[str, dict]]]:
    """A pipeline whose test corpus is injected and whose monitor is captured.

    ``_collect_test_sources`` / ``_collect_frontend_test_sources`` are the only
    filesystem touch points of ``_report_traceability``; stubbing them keeps the
    test hermetic and lets the corpus be written inline.
    """
    state = ProjectState(id=pid, name="trace", goal="g")
    state.epics.append(Epic(id="EPIC-1", title="E"))
    state.stories = stories
    pipeline = Pipeline(state, FakeRunner([]))
    events: list[tuple[str, dict]] = []
    original = pipeline.monitor.event

    def _event(kind, **fields):
        events.append((kind, fields))
        return original(kind, **fields)

    monkeypatch.setattr(pipeline.monitor, "event", _event)
    monkeypatch.setattr(settings, "ac_traceability_enabled", True)
    monkeypatch.setattr(pipeline, "_collect_test_sources", lambda ws: dict(sources))
    monkeypatch.setattr(pipeline, "_collect_frontend_test_sources", lambda ws: {})
    return pipeline, events


def _traceability_event(events: list[tuple[str, dict]]) -> dict:
    hits = [f for k, f in events if k == "traceability"]
    assert hits, "no traceability event emitted"
    return hits[-1]


# ------------------------------------------------------- fold_aliases (pure)


def test_fold_aliases_collapses_task_ids_onto_their_story_criterion():
    """Two aliases of one criterion, one of them covered: the criterion counts
    ONCE and counts as covered."""
    aliases = {
        "US-1.AC-1": "US-1.AC-1",
        "US1-T1.AC-1": "US-1.AC-1",
        "US-1.AC-2": "US-1.AC-2",
        "US1-T2.AC-2": "US-1.AC-2",
    }
    raw = traceability.coverage_report(
        set(aliases),
        {"tests/test_a.py": "# AC: US1-T1.AC-1\ndef test_a():\n    pass\n"},
    )
    assert raw["covered"] == ["US1-T1.AC-1"]
    folded = traceability.fold_aliases(raw, aliases)
    assert folded["covered"] == ["US-1.AC-1"]
    assert folded["uncovered"] == ["US-1.AC-2"]
    assert folded["orphans"] == []


def test_fold_aliases_keeps_orphans_and_tolerates_empty_inputs():
    raw = {"covered": [], "uncovered": [], "orphans": ["US9-T9.AC-1"]}
    assert traceability.fold_aliases(raw, {}) == {
        "covered": [], "uncovered": [], "orphans": ["US9-T9.AC-1"],
    }
    assert traceability.fold_aliases({}, {"A": "A"}) == {
        "covered": [], "uncovered": ["A"], "orphans": [],
    }


# ------------------------------------------------- _report_traceability (a..e)


def test_task_qualified_markers_cover_their_story_criteria(monkeypatch):
    """(a) US-1 (AC-1, AC-2) with tasks US1-T1 (AC-1) and US1-T2 (AC-2), tests
    marked with the TASK ids: 2 covered, 0 uncovered, 0 orphans."""
    story = _story(
        "US-1", "AC-1", "AC-2",
        tasks=[_task("US1-T1", "US-1", "AC-1"), _task("US1-T2", "US-1", "AC-2")],
    )
    sources = {
        "tests/test_a.py": "# AC: US1-T1.AC-1\ndef test_a():\n    pass\n",
        "tests/test_b.py": "# AC: US1-T2.AC-2\ndef test_b():\n    pass\n",
    }
    pipeline, events = _pipeline("trace-tasks", [story], sources, monkeypatch)
    pipeline._report_traceability(all_iterations=True)
    assert _traceability_event(events) == {
        "covered": 2, "uncovered": 0, "orphans": 0,
    }
    assert pipeline.state.delivery_issues == []


def test_story_qualified_marker_still_covers(monkeypatch):
    """(b) the historic STORY-qualified marker keeps covering its criterion."""
    story = _story(
        "US-1", "AC-1", "AC-2",
        tasks=[_task("US1-T1", "US-1", "AC-1"), _task("US1-T2", "US-1", "AC-2")],
    )
    sources = {
        "tests/test_a.py": "# AC: US-1.AC-1\ndef test_a():\n    pass\n",
        "tests/test_b.py": "# AC: US1-T2.AC-2\ndef test_b():\n    pass\n",
    }
    pipeline, events = _pipeline("trace-story-id", [story], sources, monkeypatch)
    pipeline._report_traceability(all_iterations=True)
    assert _traceability_event(events) == {
        "covered": 2, "uncovered": 0, "orphans": 0,
    }


def test_unknown_task_qualified_marker_is_an_orphan(monkeypatch):
    """(c) a marker qualified by a task that does not exist stays an ORPHAN:
    the fold must not turn the orphan check into a rubber stamp."""
    story = _story("US-1", "AC-1", tasks=[_task("US1-T1", "US-1", "AC-1")])
    sources = {
        "tests/test_a.py": "# AC: US1-T1.AC-1\ndef test_a():\n    pass\n",
        "tests/test_z.py": "# AC: US9-T9.AC-1\ndef test_z():\n    pass\n",
    }
    pipeline, events = _pipeline("trace-orphan", [story], sources, monkeypatch)
    pipeline._report_traceability(all_iterations=True)
    assert _traceability_event(events) == {
        "covered": 1, "uncovered": 0, "orphans": 1,
    }


def test_bare_marker_is_neither_covered_nor_orphan(monkeypatch):
    """(d) an UNQUALIFIED marker (legacy style) is ambiguous: it covers nothing
    and is not reported as an orphan either."""
    story = _story("US-1", "AC-1", tasks=[_task("US1-T1", "US-1", "AC-1")])
    sources = {"tests/test_a.py": "# AC: AC-1\ndef test_a():\n    pass\n"}
    pipeline, events = _pipeline("trace-bare", [story], sources, monkeypatch)
    pipeline._report_traceability(all_iterations=True)
    assert _traceability_event(events) == {
        "covered": 0, "uncovered": 1, "orphans": 0,
    }


def test_task_only_criterion_is_declared_on_its_own(monkeypatch):
    """(e) a task criterion whose bare id the story does NOT declare is a
    criterion in its own right: declared under the task id, covered when marked,
    uncovered (not orphan) when not."""
    story = _story(
        "US-1", "AC-1",
        tasks=[_task("US1-T1", "US-1", "AC-1", "AC-7"), _task("US1-T2", "US-1", "AC-8")],
    )
    sources = {
        "tests/test_a.py": "# AC: US1-T1.AC-1, US1-T1.AC-7\ndef test_a():\n    pass\n",
    }
    pipeline, events = _pipeline("trace-task-only", [story], sources, monkeypatch)
    pipeline._report_traceability(all_iterations=True)
    # Declared canonicals: US-1.AC-1, US1-T1.AC-7, US1-T2.AC-8.
    assert _traceability_event(events) == {
        "covered": 2, "uncovered": 1, "orphans": 0,
    }
    assert any("US1-T2.AC-8" in i for i in pipeline.state.delivery_issues)


# --------------------------------------------------- the real run, reproduced


def _real_run_stories() -> list[UserStory]:
    """drv-p3-9ae648a7 shape: 3 stories, 8 tasks, 24 task-qualified criteria."""
    shape = {
        "TS-1": {"TS1-T1": 4, "TS1-T2": 3, "TS1-T3": 3},
        "US-1": {"US1-T1": 3, "US1-T2": 4, "US1-T3": 2},
        "US-2": {"US2-T1": 3, "US2-T2": 2},
    }
    stories: list[UserStory] = []
    for sid, tasks in shape.items():
        widest = max(tasks.values())
        story = _story(sid, *[f"AC-{i}" for i in range(1, widest + 1)])
        story.tasks = [
            _task(tid, sid, *[f"AC-{i}" for i in range(1, n + 1)])
            for tid, n in tasks.items()
        ]
        stories.append(story)
    return stories


def test_real_multi_stream_run_has_no_orphan(monkeypatch):
    """All 24 task-qualified markers of the real run resolve to a criterion:
    orphans drop from 24 to 0 and every marked criterion is covered."""
    stories = _real_run_stories()
    markers = [
        f"{t.id}.{c.id}" for s in stories for t in s.tasks for c in t.acceptance_criteria
    ]
    assert len(markers) == 24
    sources = {
        f"tests/test_{i}.py": f"# AC: {m}\ndef test_x():\n    pass\n"
        for i, m in enumerate(markers)
    }
    canonical_marked = set()
    for s in stories:
        bare = {c.id for c in s.acceptance_criteria}
        for t in s.tasks:
            for c in t.acceptance_criteria:
                canonical_marked.add(
                    f"{s.id}.{c.id}" if c.id in bare else f"{t.id}.{c.id}"
                )
    pipeline, events = _pipeline("trace-real-run", stories, sources, monkeypatch)
    pipeline._report_traceability(all_iterations=True)
    event = _traceability_event(events)
    assert event["orphans"] == 0
    assert event["covered"] == len(canonical_marked)
    # 4 + 4 + 3 declared criteria, all of them reachable from a task.
    assert event["covered"] == 11
    assert event["uncovered"] == 0


def test_defect_signature_before_the_fix_is_gone(monkeypatch):
    """The exact defect: STORY-only declaration against task-qualified markers
    used to yield covered=0 / orphans=N. Guard that the raw report still shows
    it (so the test proves the FOLD is what fixes it, not a corpus change)."""
    stories = _real_run_stories()
    markers = [
        f"{t.id}.{c.id}" for s in stories for t in s.tasks for c in t.acceptance_criteria
    ]
    sources = {
        f"tests/test_{i}.py": f"# AC: {m}\ndef test_x():\n    pass\n"
        for i, m in enumerate(markers)
    }
    story_only = {f"{s.id}.{c.id}" for s in stories for c in s.acceptance_criteria}
    raw = traceability.coverage_report(story_only, sources)
    assert raw["covered"] == []
    assert len(raw["uncovered"]) == 11
    assert len(raw["orphans"]) == 24
