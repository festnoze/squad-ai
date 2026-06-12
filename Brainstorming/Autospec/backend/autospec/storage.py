"""JSON persistence of project state inside each project's workspace folder."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from .config import settings
from .models import ProjectState

STATE_FILENAME = "autospec-state.json"


def _migrate(raw: dict) -> dict:
    """Coerce legacy persisted shapes to the current schema.

    - acceptance_criteria used to be a list[str]; it is now a list of
      {id, text} objects.
    """
    for story in raw.get("stories", []):
        criteria = story.get("acceptance_criteria", [])
        migrated = []
        for i, item in enumerate(criteria, start=1):
            if isinstance(item, str):
                migrated.append({"id": f"AC-{i}", "text": item})
            else:
                migrated.append(item)
        story["acceptance_criteria"] = migrated
    return raw


def workspace_dir(project_id: str) -> Path:
    return settings.workspace_root / project_id


def save_state(state: ProjectState) -> None:
    ws = workspace_dir(state.id)
    ws.mkdir(parents=True, exist_ok=True)
    (ws / STATE_FILENAME).write_text(state.model_dump_json(indent=2), encoding="utf-8")


def load_state(project_id: str) -> ProjectState | None:
    path = workspace_dir(project_id) / STATE_FILENAME
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return ProjectState.model_validate(_migrate(raw))
    except Exception:
        # A state file from an incompatible/corrupt version must never break the
        # whole project list — skip it.
        return None


def delete_workspace(project_id: str) -> bool:
    """Remove a project's workspace (state + generated code). Returns True if it
    existed."""
    ws = workspace_dir(project_id)
    if ws.exists():
        shutil.rmtree(ws, ignore_errors=True)
        return True
    return False


def list_states() -> list[ProjectState]:
    root = settings.workspace_root
    if not root.exists():
        return []
    states = []
    for child in root.iterdir():
        if (child / STATE_FILENAME).exists():
            state = load_state(child.name)
            if state:
                states.append(state)
    return sorted(states, key=lambda s: s.created_at, reverse=True)
