import json

from autospec.core.models import Phase, ProjectState, Profile
from autospec.core.store import Store


def test_state_round_trip(tmp_path):
    store = Store(tmp_path)
    state = ProjectState(id="p1", name="P", package="p", profile=Profile.CLI, phase=Phase.PLAN)
    assert not store.exists()

    store.save(state)

    assert store.exists()
    loaded = store.load()
    assert loaded.id == "p1" and loaded.profile == Profile.CLI and loaded.phase == Phase.PLAN
    assert not list(store.dir.glob("*.tmp")), "atomic write leaves no temp file"


def test_unknown_fields_from_another_version_are_ignored(tmp_path):
    store = Store(tmp_path)
    store.dir.mkdir()
    store.state_path.write_text(json.dumps(
        {"id": "p", "name": "P", "package": "p", "streams": [], "governance": {"x": 1}}), encoding="utf-8")

    assert store.load().id == "p"


def test_events_are_appended_in_order(tmp_path):
    store = Store(tmp_path)
    store.append_event({"type": "phase", "phase": "plan"})
    store.append_event({"type": "story", "id": "US-1"})

    events = store.events()

    assert [e["type"] for e in events] == ["phase", "story"]
    assert all("ts" in e for e in events)
