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

    assert await pipeline._amerge_work_item(ws, "autospec/wi-x", "x", wt) is True
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

    merged = await pipeline._amerge_work_item(ws, "wb", "B", wtB)
    assert merged is False                                  # truly conflicting → not merged

    # The repo is clean: no half-finished merge.
    assert not (ws / ".git" / "MERGE_HEAD").exists()
    _, status = await pipeline._agit(ws, "status", "--porcelain")
    assert status.strip() == ""
    # Main kept A's version (B was NOT silently dropped on top).
    assert (ws / "F.txt").read_text(encoding="utf-8") == "A-version\n"
    # Green work is PRESERVED on B's branch (rebase --abort restored it).
    assert (wtB / "F.txt").read_text(encoding="utf-8") == "B-version\n"
