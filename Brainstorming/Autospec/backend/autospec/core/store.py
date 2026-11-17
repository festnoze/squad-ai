"""Durable project state (one JSON file) and event journal (JSONL), under <ws>/.autospec/."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from .models import ProjectState, utcnow

STATE_FILE = "state.json"
EVENTS_FILE = "events.jsonl"
_REPLACE_ATTEMPTS = 20  # about 10 s of cumulated backoff


class Store:
    def __init__(self, ws: Path):
        self.ws = Path(ws)
        self.dir = self.ws / ".autospec"

    @property
    def state_path(self) -> Path:
        return self.dir / STATE_FILE

    @property
    def events_path(self) -> Path:
        return self.dir / EVENTS_FILE

    def exists(self) -> bool:
        return self.state_path.is_file()

    def load(self) -> ProjectState:
        return ProjectState.model_validate_json(self.state_path.read_text(encoding="utf-8"))

    def save(self, state: ProjectState) -> None:
        """Atomic replace: a crash mid-write never leaves a truncated state.

        On Windows the replace fails with a sharing violation while another process
        (antivirus, indexer, file watcher) briefly holds the target: retry a few times.
        """
        self.dir.mkdir(parents=True, exist_ok=True)
        state.updated_at = utcnow()
        tmp = self.state_path.with_suffix(".json.tmp")
        tmp.write_text(state.model_dump_json(indent=2), encoding="utf-8")
        for attempt in range(_REPLACE_ATTEMPTS):
            try:
                os.replace(tmp, self.state_path)
                return
            except PermissionError:
                if attempt == _REPLACE_ATTEMPTS - 1:
                    raise
                time.sleep(0.05 * (attempt + 1))

    def append_event(self, event: dict) -> dict:
        self.dir.mkdir(parents=True, exist_ok=True)
        record = {"ts": utcnow(), **event}
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record

    def events(self) -> list[dict]:
        if not self.events_path.is_file():
            return []
        lines = self.events_path.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines if line.strip()]
