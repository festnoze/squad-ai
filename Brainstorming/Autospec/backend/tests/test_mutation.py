"""Tests of the built-in mutation testing (Q1): the AST mutation engine and the
pipeline scoring (kill rate), env-gated and best-effort, restoring source."""

from autospec.agents.runner import FakeRunner
from autospec.config import settings as cfg
from autospec.models import ProjectState, UserStory
from autospec.orchestrator import mutation, workspace
from autospec.orchestrator.pipeline import Pipeline

CALC_SRC = '''def is_one(a):
    return a == 1
'''


def test_generate_mutants_flips_comparison():
    mutants = mutation.generate_mutants(CALC_SRC)
    assert len(mutants) == 1
    desc, code = mutants[0]
    assert "Eq->NotEq" in desc
    assert "!=" in code


def test_generate_mutants_no_targets():
    assert mutation.generate_mutants("x = 1\n") == []


def test_generate_mutants_syntax_error():
    assert mutation.generate_mutants("def (:") == []


def test_generate_mutants_respects_cap():
    src = '''def f(a, b):
    return a == 1 and b > 0 or a < 5
'''
    assert len(mutation.generate_mutants(src, max_mutants=2)) == 2


def _build_ws(state):
    ws = workspace.scaffold(state)
    pkg = workspace.package_name(state)
    pkg_dir = ws / pkg
    pkg_dir.mkdir(parents=True, exist_ok=True)
    (pkg_dir / "__init__.py").write_text("", encoding="utf-8")
    (pkg_dir / "calc.py").write_text(CALC_SRC, encoding="utf-8")
    return ws, pkg, pkg_dir


async def test_mutation_score_all_killed(monkeypatch):
    monkeypatch.setattr(cfg, "mutation_enabled", True)
    monkeypatch.setattr(cfg, "fake_agents", False)
    state = ProjectState(id="p-mut1", name="calc", goal="g")
    pipeline = Pipeline(state, FakeRunner([]))
    ws, pkg, pkg_dir = _build_ws(state)
    story = UserStory(id="US-1", epic_id="E1", title="t")

    async def _kill(self):
        return (False, "boom", {})

    monkeypatch.setattr(Pipeline, "_arun_pytest", _kill)

    await pipeline._arun_mutation_test(story, pkg, ws)
    assert story.mutation_score == 100
    assert (pkg_dir / "calc.py").read_text(encoding="utf-8") == CALC_SRC


async def test_mutation_score_all_survived(monkeypatch):
    monkeypatch.setattr(cfg, "mutation_enabled", True)
    monkeypatch.setattr(cfg, "fake_agents", False)
    state = ProjectState(id="p-mut2", name="calc", goal="g")
    pipeline = Pipeline(state, FakeRunner([]))
    ws, pkg, _ = _build_ws(state)
    story = UserStory(id="US-1", epic_id="E1", title="t")

    async def _survive(self):
        return (True, "", {})

    monkeypatch.setattr(Pipeline, "_arun_pytest", _survive)

    await pipeline._arun_mutation_test(story, pkg, ws)
    assert story.mutation_score == 0


async def test_mutation_disabled_noop(monkeypatch):
    monkeypatch.setattr(cfg, "mutation_enabled", False)
    state = ProjectState(id="p-mut3", name="calc", goal="g")
    pipeline = Pipeline(state, FakeRunner([]))
    ws, pkg, _ = _build_ws(state)
    story = UserStory(id="US-1", epic_id="E1", title="t")
    await pipeline._arun_mutation_test(story, pkg, ws)
    assert story.mutation_score == -1
