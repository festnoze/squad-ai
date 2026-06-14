"""Cross-project lesson library (F1).

E7 mines durable lessons per project; F1 promotes them to a shared store
(`autospec-lessons.json` under the workspace root) injected into every new
project's Dev/QA prompts, so the factory carries learnings between projects.
"""

from __future__ import annotations

import json
import os
import tempfile

from ..config import settings


def _store_path():
    return settings.workspace_root / "autospec-lessons.json"


def load_global_lessons() -> list[str]:
    """The shared lessons, or [] when the store is missing/unreadable."""
    try:
        data = json.loads(_store_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [str(x) for x in data] if isinstance(data, list) else []


def add_global_lessons(new: list[str]) -> list[str]:
    """Merge `new` into the shared store (dedup, keep the most recent N) and
    return the updated list. No-op (returns the current store) when disabled."""
    if not settings.shared_lessons_enabled:
        return load_global_lessons()
    merged = load_global_lessons()
    for item in new:
        item = str(item).strip()
        if item and item not in merged:
            merged.append(item)
    merged = merged[-settings.shared_lessons_max:]
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(merged, ensure_ascii=False, indent=2)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
        os.replace(tmp, path)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    return merged
