import json

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


def test_workspace_dir_rejects_traversal_ids():
    for bad in ("", ".", "..", "a/b", "a\\b", "C:evil"):
        with pytest.raises(ValueError):
            storage.workspace_dir(bad)
