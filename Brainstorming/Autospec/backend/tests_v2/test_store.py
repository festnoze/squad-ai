import json
import os

import pytest

from autospec.core import store as store_module
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


def test_a_transient_windows_sharing_violation_is_retried(tmp_path, monkeypatch):
    real_replace = os.replace
    failures = iter([PermissionError(5, "Access denied"), PermissionError(5, "Access denied")])

    def flaky_replace(src, dst):
        error = next(failures, None)
        if error:
            raise error
        real_replace(src, dst)

    monkeypatch.setattr(store_module.os, "replace", flaky_replace)
    store = Store(tmp_path)

    store.save(ProjectState(id="p", name="P", package="p"))

    assert store.load().id == "p"


def test_a_persistent_sharing_violation_still_raises(tmp_path, monkeypatch):
    def always_denied(src, dst):
        raise PermissionError(5, "Access denied")

    monkeypatch.setattr(store_module.os, "replace", always_denied)
    monkeypatch.setattr(store_module.time, "sleep", lambda _s: None)

    with pytest.raises(PermissionError):
        Store(tmp_path).save(ProjectState(id="p", name="P", package="p"))


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
