"""Real Git regressions: generated workspaces must not inherit factory history."""

import os
from pathlib import Path
import shutil
import subprocess

import pytest

from autospec.agents.runner import FakeRunner
from autospec.config import settings
from autospec.models import PipelinePhase, ProjectState, Task, UserStory
from autospec.orchestrator.pipeline import Pipeline
from autospec.storage import workspace_dir


pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="Git executable required")


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-c", "user.name=Isolation test", "-c", "user.email=isolation@example.invalid",
         "-c", "commit.gpgsign=false", "-c", f"core.hooksPath={repo / '.disabled-hooks'}", *args],
        cwd=repo, capture_output=True, text=True, encoding="utf-8", errors="replace",
        env={key: value for key, value in os.environ.items() if not key.startswith("GIT_")},
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def commit_file(repo: Path, filename: str, contents: str, message: str) -> None:
    (repo / filename).write_text(contents, encoding="utf-8")
    git(repo, "add", "--", filename)
    git(repo, "commit", "-m", message)


@pytest.fixture
def nested_project(tmp_path, monkeypatch):
    # This parent is intentionally a real Git repository, independent of where
    # pytest puts its basetemp. No production checkout is modified by the test.
    parent = tmp_path / "unrelated-parent"
    parent.mkdir()
    git(parent, "init")
    commit_file(parent, "parent-story.txt", "private parent story\n", "story US-1 done")
    commit_file(parent, "parent-task.txt", "private parent task\n", "story T-1 done")
    commit_file(parent, "parent-snapshot.txt", "parent snapshot\n", "iteration 1 snapshot")
    commit_file(parent, "parent-latest.txt", "keep this newer commit\n", "later parent change")
    (parent / "parent-story.txt").write_text("uncommitted parent edits\n", encoding="utf-8")
    (parent / "untracked-parent.txt").write_text("do not clean\n", encoding="utf-8")
    monkeypatch.setattr(settings, "workspace_root", parent / "projects")
    monkeypatch.setattr(Pipeline, "_sync", lambda self: None)
    for key in (
        "GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE",
        "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    ):
        monkeypatch.delenv(key, raising=False)
    state = ProjectState(
        id="nested-app", name="app", goal="a project", phase=PipelinePhase.DONE,
        stories=[UserStory(id="US-1", epic_id="E-1", title="story", tasks=[
            Task(id="T-1", story_id="US-1", title="task", stream="backend"),
        ])],
    )
    ws = workspace_dir(state.id)
    ws.mkdir(parents=True)
    return parent, ws, Pipeline(state, FakeRunner([]))


async def test_workspace_without_own_git_never_exposes_parent_diffs_or_snapshots(nested_project):
    parent, ws, pipeline = nested_project
    assert git(ws, "rev-parse", "--show-toplevel") == parent.as_posix()
    assert await pipeline.astory_diff("US-1") == {"available": False, "diff": ""}
    assert await pipeline.atask_diff("T-1") == {"available": False, "diff": ""}
    assert await pipeline.aiterations() == []
    assert not (ws / ".git").exists()  # read endpoints must not initialize a repository


async def test_refused_rollback_does_not_touch_parent_history_or_dirty_files(nested_project):
    parent, ws, pipeline = nested_project
    before_head = git(parent, "rev-parse", "HEAD")
    before_status = git(parent, "status", "--porcelain")
    before_diff = git(parent, "diff")
    with pytest.raises(ValueError, match="dépôt Git propre"):
        await pipeline.arollback(1)
    assert git(parent, "rev-parse", "HEAD") == before_head
    assert git(parent, "status", "--porcelain") == before_status
    assert git(parent, "diff") == before_diff
    assert (parent / "parent-latest.txt").read_text(encoding="utf-8") == "keep this newer commit\n"
    assert (parent / "untracked-parent.txt").read_text(encoding="utf-8") == "do not clean\n"
    assert not (ws / ".git").exists()


async def test_own_nested_repo_returns_only_its_commits_and_rolls_back_locally(nested_project):
    parent, ws, pipeline = nested_project
    before_head = git(parent, "rev-parse", "HEAD")
    before_diff = git(parent, "diff")
    git(ws, "init")
    commit_file(ws, "local-story.txt", "local story\n", "story US-1 done")
    commit_file(ws, "local-task.txt", "local task\n", "story T-1 done")
    commit_file(ws, "version.txt", "v1\n", "iteration 1 snapshot")
    commit_file(ws, "version.txt", "v2\n", "iteration 2 snapshot")
    story = await pipeline.astory_diff("US-1")
    task = await pipeline.atask_diff("T-1")
    assert story["available"] and "local-story.txt" in story["diff"]
    assert task["available"] and "local-task.txt" in task["diff"]
    assert "parent-story" not in story["diff"]
    assert "parent-task" not in task["diff"]
    assert await pipeline.aiterations() == [1, 2]
    await pipeline.arollback(1)
    assert (ws / "version.txt").read_text(encoding="utf-8") == "v1\n"
    assert git(parent, "rev-parse", "HEAD") == before_head
    assert git(parent, "diff") == before_diff
    assert (parent / "untracked-parent.txt").exists()


async def test_valid_linked_worktree_git_file_remains_supported(nested_project):
    parent, ws, pipeline = nested_project
    git(parent, "worktree", "add", "--detach", str(ws), "HEAD")
    assert (ws / ".git").is_file()
    # This time the shared history is intentional: ws is explicitly a worktree.
    assert (await pipeline.astory_diff("US-1"))["available"]
    assert await pipeline.aiterations() == [1]


async def test_inherited_git_directory_cannot_redirect_an_owned_workspace(nested_project, monkeypatch):
    parent, ws, pipeline = nested_project
    git(ws, "init")
    before_head = git(parent, "rev-parse", "HEAD")
    monkeypatch.setenv("GIT_DIR", str(parent / ".git"))
    assert await pipeline.astory_diff("US-1") == {"available": False, "diff": ""}
    assert await pipeline.atask_diff("T-1") == {"available": False, "diff": ""}
    assert await pipeline.aiterations() == []
    with pytest.raises(ValueError, match="dépôt Git propre"):
        await pipeline.arollback(1)
    assert git(parent, "rev-parse", "HEAD") == before_head


async def test_local_git_metadata_with_external_worktree_is_refused(nested_project):
    parent, ws, pipeline = nested_project
    git(ws, "init")
    git(ws, "config", "core.worktree", str(parent))
    assert (ws / ".git").is_dir()
    assert git(ws, "rev-parse", "--show-toplevel") == parent.as_posix()
    before_head = git(parent, "rev-parse", "HEAD")
    before_diff = git(parent, "diff")
    assert await pipeline.astory_diff("US-1") == {"available": False, "diff": ""}
    assert await pipeline.atask_diff("T-1") == {"available": False, "diff": ""}
    assert await pipeline.aiterations() == []
    with pytest.raises(ValueError, match="dépôt Git propre"):
        await pipeline.arollback(1)
    assert git(parent, "rev-parse", "HEAD") == before_head
    assert git(parent, "diff") == before_diff


@pytest.mark.parametrize("redirect", ["git-dir-before-init", "git-index-existing", "gitfile", "external-worktree"])
async def test_ensure_repo_refuses_redirects_before_touching_parent_index_or_config(nested_project, monkeypatch, redirect):
    parent, ws, pipeline = nested_project
    commit_file(parent, "autospec-state.json", '{"private": true}\n', "parent bookkeeping")
    if redirect == "git-dir-before-init":
        monkeypatch.setenv("GIT_DIR", str(parent / ".git"))
    elif redirect == "gitfile":
        (ws / ".git").write_text(f"gitdir: {(parent / '.git').as_posix()}\n", encoding="utf-8")
    else:
        git(ws, "init")
        if redirect == "git-index-existing":
            monkeypatch.setenv("GIT_INDEX_FILE", str(parent / ".git" / "index"))
        else:
            git(ws, "config", "core.worktree", str(parent))
    before_head = git(parent, "rev-parse", "HEAD")
    before_index = (parent / ".git" / "index").read_bytes()
    before_config = (parent / ".git" / "config").read_bytes()
    before_diff = git(parent, "diff")
    assert not await pipeline._agit_ensure_repo(ws)
    assert not pipeline._bookkeeping_ignored
    assert not (ws / ".gitignore").exists()
    assert git(parent, "rev-parse", "HEAD") == before_head
    assert (parent / ".git" / "index").read_bytes() == before_index
    assert (parent / ".git" / "config").read_bytes() == before_config
    assert git(parent, "diff") == before_diff
    assert (parent / "untracked-parent.txt").read_text(encoding="utf-8") == "do not clean\n"
    if redirect == "git-dir-before-init":
        assert not (ws / ".git").exists()


async def test_misrouted_gitfile_does_not_expose_parent_history(nested_project):
    parent, ws, pipeline = nested_project
    (ws / ".git").write_text(f"gitdir: {(parent / '.git').as_posix()}\n", encoding="utf-8")
    assert await pipeline.astory_diff("US-1") == {"available": False, "diff": ""}
    assert await pipeline.atask_diff("T-1") == {"available": False, "diff": ""}
    assert await pipeline.aiterations() == []
    with pytest.raises(ValueError, match="dépôt Git propre"):
        await pipeline.arollback(1)


@pytest.mark.parametrize("existing", [False, True])
async def test_ensure_repo_initializes_or_reuses_only_local_metadata(nested_project, existing):
    parent, ws, pipeline = nested_project
    if existing:
        git(ws, "init")
    before_index = (parent / ".git" / "index").read_bytes()
    before_config = (parent / ".git" / "config").read_bytes()
    assert await pipeline._agit_ensure_repo(ws)
    assert git(ws, "rev-parse", "--show-toplevel") == ws.as_posix()
    assert (ws / ".gitignore").exists()
    assert (parent / ".git" / "index").read_bytes() == before_index
    assert (parent / ".git" / "config").read_bytes() == before_config


async def test_ensure_repo_accepts_linked_worktree_without_touching_parent_index(nested_project):
    parent, ws, pipeline = nested_project
    git(parent, "worktree", "add", "--detach", str(ws), "HEAD")
    before_index = (parent / ".git" / "index").read_bytes()
    assert await pipeline._agit_ensure_repo(ws)
    assert (parent / ".git" / "index").read_bytes() == before_index


async def test_ensure_repo_validates_init_result_before_config_or_bookkeeping(nested_project, monkeypatch):
    parent, ws, pipeline = nested_project
    # Model an unsafe initialization configuration. All commands remain real
    # Git operations; only insert the bad setting immediately after actual init.
    original_git = pipeline._agit
    async def init_with_external_worktree(path, *args):
        result = await original_git(path, *args)
        if args == ("init",) and result[0] == 0:
            git(path, "config", "core.worktree", str(parent))
        return result
    monkeypatch.setattr(pipeline, "_agit", init_with_external_worktree)
    before_index = (parent / ".git" / "index").read_bytes()
    before_config = (parent / ".git" / "config").read_bytes()
    assert not await pipeline._agit_ensure_repo(ws)
    assert (ws / ".git").exists()
    assert not pipeline._bookkeeping_ignored
    assert not (ws / ".gitignore").exists()
    assert (parent / ".git" / "index").read_bytes() == before_index
    assert (parent / ".git" / "config").read_bytes() == before_config
    assert b"autospec@local" not in (ws / ".git" / "config").read_bytes()
