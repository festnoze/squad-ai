"""P2 — never lose green work on a merge conflict: ``_amerge_work_item`` rebases
the green branch onto the updated HEAD inside its worktree before giving up, and
a failed rebase aborts cleanly so the green branch stays intact (recoverable),
leaving neither the repo nor the worktree in a half-merged/rebasing state."""

from pathlib import Path

from autospec.agents.scripted import ScriptedRunner
from autospec.models import Epic, ProjectState, Stream, StreamKind
from autospec.orchestrator.pipeline import Pipeline
from autospec.storage import workspace_dir


def _state(pid):
    st = ProjectState(id=pid, name="mp", goal="g")
    st.epics.append(Epic(id="EPIC-1", title="E"))
    st.streams = [Stream(id="backend", kind=StreamKind.BACKEND, language="python", primary=True)]
    return st


async def _init_repo(pipeline, ws):
    ws.mkdir(parents=True, exist_ok=True)
    assert await pipeline._agit_ensure_repo(ws)
    (ws / "F.txt").write_text("line\n", encoding="utf-8")
    await pipeline._agit(ws, "add", "-A")
    await pipeline._agit(ws, "commit", "-m", "base")
    _, sha = await pipeline._agit(ws, "rev-parse", "HEAD")
    return sha.strip()


async def test_merge_succeeds_and_lands_green(tmp_path, monkeypatch):
    monkeypatch.setattr("autospec.config.settings.workspace_root", tmp_path)
    pipeline = Pipeline(_state("mp-ok"), ScriptedRunner())
    ws = workspace_dir("mp-ok")
    await _init_repo(pipeline, ws)
    wt = await pipeline._aworktree_add(ws, "autospec/wi-x")
    assert wt is not None
    (Path(wt) / "feature.txt").write_text("hello", encoding="utf-8")
    await pipeline._acommit_story(wt, "x")

    merged, conflicts = await pipeline._amerge_work_item(ws, "autospec/wi-x", "x", wt)
    assert merged is True and conflicts == []
    assert (ws / "feature.txt").exists()              # green landed in main


async def test_merge_conflict_returns_false_clean_and_preserves_green(tmp_path, monkeypatch):
    monkeypatch.setattr("autospec.config.settings.workspace_root", tmp_path)
    pipeline = Pipeline(_state("mp-conf"), ScriptedRunner())
    ws = workspace_dir("mp-conf")
    base = await _init_repo(pipeline, ws)

    # Branch A (off base) changes F's only line, then merges into main.
    wtA = Path(tmp_path) / "wtA"
    await pipeline._agit(ws, "worktree", "add", str(wtA), "-b", "wa", base)
    (wtA / "F.txt").write_text("A-version\n", encoding="utf-8")
    await pipeline._agit(wtA, "add", "-A")
    await pipeline._agit(wtA, "commit", "-m", "A")
    assert (await pipeline._agit(ws, "merge", "--no-ff", "-m", "merge A", "wa"))[0] == 0

    # Branch B, ALSO off the base, changes the SAME line → genuine conflict.
    wtB = Path(tmp_path) / "wtB"
    await pipeline._agit(ws, "worktree", "add", str(wtB), "-b", "wb", base)
    (wtB / "F.txt").write_text("B-version\n", encoding="utf-8")
    await pipeline._agit(wtB, "add", "-A")
    await pipeline._agit(wtB, "commit", "-m", "B")

    merged, conflicts = await pipeline._amerge_work_item(ws, "wb", "B", wtB)
    assert merged is False                                  # truly conflicting → not merged
    assert conflicts == ["F.txt"]                           # the clashing file is NAMED

    # The repo is clean: no half-finished merge.
    assert not (ws / ".git" / "MERGE_HEAD").exists()
    _, status = await pipeline._agit(ws, "status", "--porcelain")
    assert status.strip() == ""
    # Main kept A's version (B was NOT silently dropped on top).
    assert (ws / "F.txt").read_text(encoding="utf-8") == "A-version\n"
    # Green work is PRESERVED on B's branch (rebase --abort restored it).
    assert (wtB / "F.txt").read_text(encoding="utf-8") == "B-version\n"


# ------------------------------------------- P2b: resume a preserved green branch


async def test_worktree_remove_keep_branch_preserves_ref(tmp_path, monkeypatch):
    monkeypatch.setattr("autospec.config.settings.workspace_root", tmp_path)
    pipeline = Pipeline(_state("mp-keep"), ScriptedRunner())
    ws = workspace_dir("mp-keep")
    await _init_repo(pipeline, ws)
    wt = await pipeline._aworktree_add(ws, "autospec/wi-k")
    assert wt is not None
    (Path(wt) / "k.txt").write_text("k", encoding="utf-8")
    await pipeline._acommit_story(wt, "k")

    await pipeline._aworktree_remove(ws, wt, "autospec/wi-k", keep_branch=True)
    code, _ = await pipeline._agit(
        ws, "rev-parse", "--verify", "--quiet", "refs/heads/autospec/wi-k"
    )
    assert code == 0                                   # the ref survived…
    assert not Path(wt).exists()                       # …but the directory is gone


async def test_resume_green_branch_rebases_then_merges(tmp_path, monkeypatch):
    """The merge-conflict requeue path: green branch preserved, HEAD advanced
    (sibling, other file) → resume returns a worktree rebased on HEAD, and the
    merge lands the preserved work WITHOUT any dev rebuild."""
    monkeypatch.setattr("autospec.config.settings.workspace_root", tmp_path)
    pipeline = Pipeline(_state("mp-res"), ScriptedRunner())
    ws = workspace_dir("mp-res")
    await _init_repo(pipeline, ws)
    wt = await pipeline._aworktree_add(ws, "autospec/wi-r")
    assert wt is not None
    (Path(wt) / "green.txt").write_text("green", encoding="utf-8")
    await pipeline._acommit_story(wt, "r")
    await pipeline._aworktree_remove(ws, wt, "autospec/wi-r", keep_branch=True)

    # A sibling advances HEAD on a DIFFERENT file meanwhile.
    (ws / "sibling.txt").write_text("s", encoding="utf-8")
    await pipeline._agit(ws, "add", "-A")
    await pipeline._agit(ws, "commit", "-m", "sibling")

    resumed = await pipeline._aresume_green_branch(ws, "autospec/wi-r")
    assert resumed is not None
    assert (Path(resumed) / "green.txt").exists()      # preserved work is there
    assert (Path(resumed) / "sibling.txt").exists()    # rebased on the updated HEAD

    merged, _ = await pipeline._amerge_work_item(ws, "autospec/wi-r", "r", resumed)
    assert merged is True
    assert (ws / "green.txt").exists()                 # landed without a rebuild
    await pipeline._aworktree_remove(ws, resumed, "autospec/wi-r")


async def test_resume_green_branch_none_when_absent(tmp_path, monkeypatch):
    monkeypatch.setattr("autospec.config.settings.workspace_root", tmp_path)
    pipeline = Pipeline(_state("mp-none"), ScriptedRunner())
    ws = workspace_dir("mp-none")
    await _init_repo(pipeline, ws)
    assert await pipeline._aresume_green_branch(ws, "autospec/wi-nope") is None


async def test_resume_green_branch_drops_empty_branch(tmp_path, monkeypatch):
    """A branch with no commit beyond HEAD (crash before the green commit) is
    useless: resume drops it so the caller builds fresh."""
    monkeypatch.setattr("autospec.config.settings.workspace_root", tmp_path)
    pipeline = Pipeline(_state("mp-empty"), ScriptedRunner())
    ws = workspace_dir("mp-empty")
    await _init_repo(pipeline, ws)
    await pipeline._agit(ws, "branch", "autospec/wi-e")   # ref at HEAD, nothing ahead
    assert await pipeline._aresume_green_branch(ws, "autospec/wi-e") is None
    code, _ = await pipeline._agit(
        ws, "rev-parse", "--verify", "--quiet", "refs/heads/autospec/wi-e"
    )
    assert code != 0                                      # dropped


async def test_resume_green_branch_drops_conflicting_branch(tmp_path, monkeypatch):
    """A genuine line-level conflict with what landed meanwhile cannot be
    replayed: resume aborts the rebase, drops the branch and returns None —
    the caller falls back to a fresh rebuild, the repo stays clean."""
    monkeypatch.setattr("autospec.config.settings.workspace_root", tmp_path)
    pipeline = Pipeline(_state("mp-cf"), ScriptedRunner())
    ws = workspace_dir("mp-cf")
    await _init_repo(pipeline, ws)
    wt = await pipeline._aworktree_add(ws, "autospec/wi-c")
    assert wt is not None
    (Path(wt) / "F.txt").write_text("branch-version\n", encoding="utf-8")
    await pipeline._acommit_story(wt, "c")
    await pipeline._aworktree_remove(ws, wt, "autospec/wi-c", keep_branch=True)

    (ws / "F.txt").write_text("main-version\n", encoding="utf-8")  # same line moved on main
    await pipeline._agit(ws, "add", "-A")
    await pipeline._agit(ws, "commit", "-m", "main moved")

    assert await pipeline._aresume_green_branch(ws, "autospec/wi-c") is None
    code, _ = await pipeline._agit(
        ws, "rev-parse", "--verify", "--quiet", "refs/heads/autospec/wi-c"
    )
    assert code != 0                                      # dropped → fresh rebuild path
    _, status = await pipeline._agit(ws, "status", "--porcelain")
    assert status.strip() == ""                           # repo stayed clean
