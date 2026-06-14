"""Tests of brownfield mode (B1): seed the workspace from an existing repo and
inject a layout summary into the architecture context."""

from autospec.agents.runner import FakeRunner
from autospec.models import ProjectState
from autospec.orchestrator import brownfield, workspace
from autospec.orchestrator.pipeline import Pipeline
from autospec.storage import workspace_dir


def test_summarize_repo(tmp_path):
    (tmp_path / "main.py").write_text("x = 1", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("z", encoding="utf-8")
    summary = brownfield.summarize_repo(tmp_path)
    assert "main.py" in summary
    assert ".git" not in summary


def test_summarize_repo_missing():
    assert brownfield.summarize_repo("/no/such/dir") == ""


def test_seed_workspace_from(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text("a", encoding="utf-8")
    (repo / "__pycache__").mkdir()
    (repo / "__pycache__" / "x.pyc").write_text("junk", encoding="utf-8")
    ws = tmp_path / "ws"
    ws.mkdir()
    copied = brownfield.seed_workspace_from(repo, ws)
    assert copied == 1
    assert (ws / "a.py").exists()
    assert not (ws / "__pycache__").exists()
    # Idempotent: an existing file is not overwritten / recounted.
    assert brownfield.seed_workspace_from(repo, ws) == 0


async def test_brownfield_init_seeds_and_contextualizes(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "main.py").write_text("print('hi')", encoding="utf-8")
    state = ProjectState(id="p-bf", name="m", goal="g", brownfield_path=str(repo))
    pipeline = Pipeline(state, FakeRunner([]))
    workspace.scaffold(state)
    await pipeline._abrownfield_init()
    ws = workspace_dir(state.id)
    assert (ws / "main.py").exists()
    assert "Contexte brownfield" in state.architecture
    assert "main.py" in state.architecture


async def test_brownfield_init_noop_without_path():
    state = ProjectState(id="p-bf2", name="m", goal="g")
    pipeline = Pipeline(state, FakeRunner([]))
    workspace.scaffold(state)
    await pipeline._abrownfield_init()
    assert state.architecture == ""
