import json
from pathlib import Path

import pytest

from autospec import storage
from autospec.config import settings
from autospec.models import ProjectState


def _make_state() -> ProjectState:
    return ProjectState(id="proj-test01", name="My Project", goal="Build something great")


def test_save_load_roundtrip():
    state = _make_state()
    storage.save_state(state)

    loaded = storage.load_state(state.id)
    assert loaded is not None
    assert loaded.id == state.id
    assert loaded.name == state.name
    assert loaded.goal == state.goal

    # No temp file must survive an atomic write.
    leftover = list(settings.workspace_root.rglob("*.tmp"))
    assert leftover == [], f"leftover temp files: {leftover}"


def test_load_corrupt_state_returns_none():
    project_id = "proj-corrupt"
    ws = storage.workspace_dir(project_id)
    ws.mkdir(parents=True, exist_ok=True)
    (ws / storage.STATE_FILENAME).write_text("{pas du json", encoding="utf-8")

    assert storage.load_state(project_id) is None


def test_load_migrates_legacy_string_criteria():
    state = _make_state()
    raw = json.loads(state.model_dump_json())
    raw["stories"] = [
        {
            "id": "US-1",
            "epic_id": "EPIC-1",
            "title": "s",
            "acceptance_criteria": ["first criterion", "second criterion"],
        }
    ]
    ws = storage.workspace_dir(state.id)
    ws.mkdir(parents=True, exist_ok=True)
    (ws / storage.STATE_FILENAME).write_text(json.dumps(raw), encoding="utf-8")

    loaded = storage.load_state(state.id)
    assert loaded is not None
    criteria = loaded.stories[0].acceptance_criteria
    assert [c.id for c in criteria] == ["AC-1", "AC-2"]
    assert [c.text for c in criteria] == ["first criterion", "second criterion"]


def test_delete_workspace_semantics():
    state = _make_state()
    storage.save_state(state)

    assert storage.delete_workspace(state.id) is True
    assert not storage.workspace_dir(state.id).exists()
    assert storage.delete_workspace(state.id) is False


def test_save_state_retries_transient_lock(monkeypatch):
    """A transient os.replace failure (Windows WinError 5: file briefly locked
    by AV/indexer/reader) is retried, not propagated."""
    state = _make_state()
    real_replace = storage.os.replace
    calls = {"n": 0}

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] == 1:
            raise PermissionError("WinError 5: access denied")
        return real_replace(src, dst)

    monkeypatch.setattr(storage.os, "replace", flaky)
    monkeypatch.setattr(storage.time, "sleep", lambda *_: None)  # no real backoff

    storage.save_state(state)  # must not raise
    assert calls["n"] == 2  # failed once, retried, succeeded
    loaded = storage.load_state(state.id)
    assert loaded is not None and loaded.id == state.id
    assert list(settings.workspace_root.rglob("*.tmp")) == []  # temp cleaned up


def test_save_state_swallows_persistent_lock(monkeypatch):
    """If the destination stays locked past every retry, persistence is dropped
    (logged) rather than crashing the whole pipeline."""
    state = _make_state()

    def always_locked(src, dst):
        raise PermissionError("WinError 5: access denied")

    monkeypatch.setattr(storage.os, "replace", always_locked)
    monkeypatch.setattr(storage.time, "sleep", lambda *_: None)

    storage.save_state(state)  # must not raise
    # No half-written temp file may survive a failed atomic write.
    assert list(settings.workspace_root.rglob("*.tmp")) == []


def test_atomic_write_temp_lives_outside_the_workspace(monkeypatch):
    """Regression: the atomic-write temp must NOT be created inside the project
    workspace. A transient ``autospec-state.json.*.tmp`` there leaks into
    everything that enumerates the workspace (the /files endpoint, the zip
    export walk, the delete rmtree) and races concurrent writes — flaky failures.
    It must go to the sibling ``.autospec-tmp`` dir instead."""
    state = _make_state()
    seen: list[Path] = []
    real_mkstemp = storage.tempfile.mkstemp

    def spy(*args, **kwargs):
        seen.append(Path(kwargs.get("dir")))
        return real_mkstemp(*args, **kwargs)

    monkeypatch.setattr(storage.tempfile, "mkstemp", spy)
    storage.save_state(state)

    ws = storage.workspace_dir(state.id)
    assert seen and all(d.name == ".autospec-tmp" and d != ws for d in seen)
    # The workspace ends with ONLY the final state file (no *.tmp leaked in).
    assert [p.name for p in ws.iterdir()] == [storage.STATE_FILENAME]


def test_workspace_dir_rejects_traversal_ids():
    for bad in ("", ".", "..", "a/b", "a\\b", "C:evil"):
        with pytest.raises(ValueError):
            storage.workspace_dir(bad)
