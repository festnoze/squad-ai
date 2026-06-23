"""JSON persistence of project state inside each project's workspace folder."""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import time
from pathlib import Path

from .config import settings
from .models import ProjectState

logger = logging.getLogger(__name__)

STATE_FILENAME = "autospec-state.json"


def _migrate(raw: dict) -> dict:
    """Coerce legacy persisted shapes to the current schema.

    - acceptance_criteria used to be a list[str]; it is now a list of
      {id, text} objects.

    Tolerant on purpose: unexpected shapes are passed through unchanged and
    left to Pydantic validation (load_state catches and logs the failure).
    """
    stories = raw.get("stories")
    if not isinstance(stories, list):
        return raw
    for story in stories:
        if not isinstance(story, dict):
            continue
        criteria = story.get("acceptance_criteria") or []
        if not isinstance(criteria, list):
            continue
        migrated = []
        for i, item in enumerate(criteria, start=1):
            if isinstance(item, str):
                migrated.append({"id": f"AC-{i}", "text": item})
            else:
                migrated.append(item)
        story["acceptance_criteria"] = migrated
    return raw


def workspace_dir(project_id: str) -> Path:
    """Resolve a project's workspace folder under the workspace root.

    Rejects ids that would escape the root (empty, '..', path separators,
    drive letters) — project ids reach here straight from API URLs, and
    delete_workspace() rmtree's this path.
    """
    if (
        project_id in ("", ".", "..")
        or "/" in project_id
        or "\\" in project_id
        or ":" in project_id
    ):
        raise ValueError(f"Invalid project id: {project_id!r}")
    return settings.workspace_root / project_id


# Windows can briefly refuse os.replace over the destination with WinError 5
# (Access Denied) when another handle holds it transiently — an antivirus scan
# of the just-written temp file, a slow concurrent reader, the search indexer.
# Persistence is best-effort: retry the swap a few times, then log and give up.
# A missed checkpoint is recovered by the next _sync; crashing the whole
# pipeline over a transient lock is not acceptable.
_SAVE_RETRIES = 5
_SAVE_BACKOFF_S = 0.05


def save_state(state: ProjectState) -> None:
    """Persist a project state synchronously (serialize + atomic write).

    Note: the blocking write + retry sleep below must NOT run on the asyncio
    event loop (it starves uvicorn's accept loop -> ETIMEDOUT on the Vite proxy).
    Hot async callers serialize on the loop and offload the write via
    ``save_state_payload``; see ``Pipeline._sync``."""
    save_state_payload(state.id, state.model_dump_json(indent=2))


def save_state_payload(project_id: str, payload: str) -> None:
    """Atomically write a pre-serialized state ``payload`` to disk.

    Split out from ``save_state`` so the (loop-bound) JSON serialization and the
    (blocking, offloadable) file I/O can happen on different threads without the
    state mutating mid-write."""
    ws = workspace_dir(project_id)
    ws.mkdir(parents=True, exist_ok=True)
    final = ws / STATE_FILENAME
    # Atomic write: serialize to a temp file, then os.replace() into place. The
    # temp lives in a SIBLING ``.tmp/`` dir (same volume as the workspace, so the
    # replace stays atomic) rather than INSIDE the workspace — otherwise the
    # transient ``autospec-state.json.*.tmp`` leaks into everything that
    # enumerates the workspace and races a concurrent write: the /files endpoint
    # (a name containing the state filename), the zip export (a file that
    # vanishes mid-walk), the delete rmtree (a momentarily-locked temp). Keeping
    # it out of the workspace removes that whole class of intermittent failures.
    tmp_root = settings.workspace_root / ".autospec-tmp"
    tmp_root.mkdir(parents=True, exist_ok=True)
    last_exc: OSError | None = None
    for attempt in range(_SAVE_RETRIES):
        fd, tmp_name = tempfile.mkstemp(dir=tmp_root, prefix=f"{project_id}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
            os.replace(tmp_name, final)
            return
        except OSError as exc:
            last_exc = exc
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            time.sleep(_SAVE_BACKOFF_S * (attempt + 1))
    logger.warning(
        "Could not persist state for project %s after %d retries: %s",
        project_id, _SAVE_RETRIES, last_exc,
    )


INTERACTIONS_FILENAME = "autospec-interactions.jsonl"

# Keep the sidecar bounded: a long build can emit thousands of agent calls. We
# only ever serve the recent tail per item, so cap how many lines we read back.
_INTERACTIONS_READ_TAIL = 4000


def append_interaction(project_id: str, payload_line: str) -> None:
    """Append one pre-serialized interaction (a single JSON line) to the project's
    sidecar. Best-effort and append-only: a failed write just drops that record
    (the in-memory ring still has it) rather than disturbing the pipeline."""
    try:
        ws = workspace_dir(project_id)
        ws.mkdir(parents=True, exist_ok=True)
        with open(ws / INTERACTIONS_FILENAME, "a", encoding="utf-8") as fh:
            fh.write(payload_line.rstrip("\n") + "\n")
    except OSError as exc:
        logger.warning("Could not append interaction for project %s: %s", project_id, exc)


def load_interactions(
    project_id: str, item_id: str | None = None, limit: int | None = None
) -> list[dict]:
    """Read captured interactions from the sidecar (most recent last).

    Filters by ``item_id`` when given and returns at most ``limit`` (the newest).
    Tolerant of partial/corrupt lines — they are skipped, not fatal."""
    path = workspace_dir(project_id) / INTERACTIONS_FILENAME
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        logger.warning("Could not read interactions for project %s: %s", project_id, exc)
        return []
    out: list[dict] = []
    for line in lines[-_INTERACTIONS_READ_TAIL:]:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if item_id is not None and rec.get("item_id") != item_id:
            continue
        out.append(rec)
    if limit is not None and limit >= 0:
        out = out[-limit:]
    return out


def load_state(project_id: str) -> ProjectState | None:
    path = workspace_dir(project_id) / STATE_FILENAME
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return ProjectState.model_validate(_migrate(raw))
    except Exception as exc:
        # A state file from an incompatible/corrupt version must never break the
        # whole project list — log it and skip.
        logger.warning("Failed to load state for project %s: %s", project_id, exc)
        return None


def delete_workspace(project_id: str) -> bool:
    """Remove a project's workspace (state + generated code). Returns True if it
    existed."""
    ws = workspace_dir(project_id)
    if not ws.exists():
        return False
    shutil.rmtree(ws, ignore_errors=True)
    if ws.exists():
        # Typical on Windows when a file is still open (e.g. the generated app
        # is running). Don't raise: the caller already removed the project.
        logger.warning("Workspace %s only partially removed (file in use?)", ws)
    return True


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
