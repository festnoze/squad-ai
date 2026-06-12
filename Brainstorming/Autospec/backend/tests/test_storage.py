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
