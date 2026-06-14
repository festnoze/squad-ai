"""Tests of the cross-project lesson library (F1): E7 lessons promoted to a
shared store and merged into a project's effective lessons."""

from autospec.agents.runner import FakeRunner
from autospec.config import settings as cfg
from autospec.models import ProjectState
from autospec.orchestrator import lessons as lesson_store
from autospec.orchestrator.pipeline import Pipeline


def test_add_and_load(monkeypatch):
    monkeypatch.setattr(cfg, "shared_lessons_enabled", True)
    lesson_store.add_global_lessons(["lessonA", "lessonB"])
    loaded = lesson_store.load_global_lessons()
    assert "lessonA" in loaded and "lessonB" in loaded


def test_dedup_and_cap(monkeypatch):
    monkeypatch.setattr(cfg, "shared_lessons_enabled", True)
    monkeypatch.setattr(cfg, "shared_lessons_max", 3)
    lesson_store.add_global_lessons(["c1", "c2", "c3", "c4", "c5"])
    loaded = lesson_store.load_global_lessons()
    assert len(loaded) == 3  # capped to the most recent
    assert loaded == ["c3", "c4", "c5"]
    n = len(lesson_store.load_global_lessons())
    lesson_store.add_global_lessons(["c5"])  # duplicate, no growth
    assert len(lesson_store.load_global_lessons()) == n


def test_disabled_is_noop(monkeypatch):
    monkeypatch.setattr(cfg, "shared_lessons_enabled", False)
    before = lesson_store.load_global_lessons()
    result = lesson_store.add_global_lessons(["X-unique-xyz"])
    assert "X-unique-xyz" not in result
    assert lesson_store.load_global_lessons() == before


async def test_effective_lessons_combines(monkeypatch):
    monkeypatch.setattr(cfg, "shared_lessons_enabled", True)
    lesson_store.add_global_lessons(["global-lesson-1"])
    state = ProjectState(id="p-f1", name="m", goal="g", lessons=["proj-lesson-1"])
    pipeline = Pipeline(state, FakeRunner([]))
    eff = pipeline._effective_lessons()
    assert "proj-lesson-1" in eff and "global-lesson-1" in eff


async def test_effective_lessons_project_only_when_disabled(monkeypatch):
    monkeypatch.setattr(cfg, "shared_lessons_enabled", False)
    state = ProjectState(id="p-f1b", name="m", goal="g", lessons=["proj-only"])
    pipeline = Pipeline(state, FakeRunner([]))
    assert pipeline._effective_lessons() == ["proj-only"]
