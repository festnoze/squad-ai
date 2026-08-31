r"""The ``runs/<match_id>/`` artefact directory (CONTRACTS sections 4.6 and 7.20).

This module is the **one** builder of every artefact path. A reader that joins
``runs_dir / match_id / "journal.jsonl"`` by hand is a second spelling of the
layout, and the day one of the six names changes only one of the two spellings
gets fixed. Everything goes through :func:`artefact_paths`, keyed by artefact
name, or through :func:`match_dir` for the directory itself.

Nothing here touches the database: the artefact side and the projection side of
:mod:`pxe.store` are deliberately independent, so a caller that only wants to
read ``metrics.json`` never opens an engine.

``meta.json`` is written with :func:`~pxe.events.canonical_json`, the same
encoder and the same ``open()`` arguments (``encoding="utf-8"``,
``newline="\n"``) that ``MatchRunner`` uses at finalisation step 19. Two writers
of one file must produce the same bytes, so this one refuses a float exactly as
that one does: the artefact is small, integral, and comparable across platforms.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any

from pxe.errors import StoreError
from pxe.events import JOURNAL_ENCODING, JOURNAL_NEWLINE, canonical_json

__all__ = [
    "ARTEFACT_FILENAMES",
    "match_dir",
    "write_meta",
    "read_meta",
    "artefact_paths",
]

#: The six artefacts of CONTRACTS section 4.6, keyed by artefact name. The key is
#: the name a caller asks for (``artefact_paths(...)["journal"]``) and the value
#: is the file name inside ``runs/<match_id>/``. Only ``journal.jsonl`` is hashed
#: and only it is required to replay.
ARTEFACT_FILENAMES: Mapping[str, str] = MappingProxyType(
    {
        "journal": "journal.jsonl",
        "observations": "observations.jsonl",
        "llm_trace": "llm_trace.jsonl",
        "incidents": "incidents.jsonl",
        "metrics": "metrics.json",
        "meta": "meta.json",
    }
)


def match_dir(runs_dir: Path, match_id: str) -> Path:
    """Return the artefact directory of one match.

    The directory is **not** created: a reader must be able to ask for the path
    of a match that does not exist without leaving an empty directory behind.
    Writers create it themselves (:func:`write_meta` does).

    Args:
        runs_dir: The runs root, normally ``runs/``.
        match_id: Match id, section 2.2.

    Returns:
        ``runs_dir / match_id``.
    """
    return Path(runs_dir) / match_id


def artefact_paths(runs_dir: Path, match_id: str) -> Mapping[str, Path]:
    """Return the six artefact paths of one match, keyed by artefact name.

    Every reader of an artefact goes through this instead of joining paths by
    hand (section 7.20). The keys are exactly those of
    :data:`ARTEFACT_FILENAMES`: ``journal``, ``observations``, ``llm_trace``,
    ``incidents``, ``metrics`` and ``meta``.

    Args:
        runs_dir: The runs root.
        match_id: Match id.

    Returns:
        An immutable mapping from artefact name to absolute-or-relative path,
        following ``runs_dir``. Nothing is created and nothing is checked for
        existence: a match that never called an LLM has no ``llm_trace.jsonl``
        and the path is still the right answer to "where would it be".
    """
    directory = match_dir(runs_dir, match_id)
    return MappingProxyType({name: directory / filename for name, filename in ARTEFACT_FILENAMES.items()})


def write_meta(path: Path, meta: Mapping[str, Any]) -> None:
    r"""Write one ``meta.json``, canonically encoded.

    The parent directory is created on demand, because the caller passes a path
    inside a run directory that may not exist yet.

    Args:
        path: Destination file, normally ``artefact_paths(...)["meta"]``.
        meta: The metadata mapping. Keys are sorted by
            :func:`~pxe.events.canonical_json`, so no writer chooses a key
            order and section 2.3's mapping rule is satisfied structurally.

    Raises:
        NonCanonicalValueError: If ``meta`` holds a float, a set or any value
            outside the JSON scalar set. ``meta.json`` is written by two
            modules (``MatchRunner`` and this one) and they must agree byte for
            byte, which a float would silently break.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding=JOURNAL_ENCODING, newline=JOURNAL_NEWLINE) as handle:
        handle.write(canonical_json(dict(meta)) + JOURNAL_NEWLINE)


def read_meta(path: Path) -> Mapping[str, Any]:
    """Read back what :func:`write_meta` wrote.

    Args:
        path: The ``meta.json`` file.

    Returns:
        The metadata mapping, immutable.

    Raises:
        StoreError: If the file is missing or does not hold a JSON object. A
            silently defaulted ``{}`` would make a rebuilt database claim a
            match has no seed and no journal hash.
    """
    if not path.exists():
        raise StoreError("missing meta.json", path=str(path))
    with open(path, encoding=JOURNAL_ENCODING, newline=JOURNAL_NEWLINE) as handle:
        raw = json.load(handle)
    if not isinstance(raw, dict):
        raise StoreError("meta.json does not hold a JSON object", path=str(path))
    return MappingProxyType(dict(raw))
