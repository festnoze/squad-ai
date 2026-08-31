"""REST routes and the shared journal locator (W12, CONTRACTS section 14).

Every handler is read-only: it locates a match journal under ``runs_dir``, replays it into a
``MatchProjection``, and serves numbers projected from that alone. The metric families and the detectors
are reached through :func:`_family_summary` and :func:`_incidents_by_kind`, which import them lazily so a
partially built tree (metrics or detectors not yet present) degrades to empty maps rather than a failed
import. At the finished gate every family resolves and the maps fill in. No route mutates state, so there
is no POST, PUT, PATCH, or DELETE anywhere in this module.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from ala.journal import read_events
from ala.metrics.projection import MatchProjection

JOURNAL_NAME = "journal.jsonl"

# The four metric families, in the order the dashboard shows them. Each family module exposes a
# ``<name>_summary(projection) -> dict`` function by convention (see metrics/outcome.py).
METRIC_FAMILIES: tuple[str, ...] = ("cooperation", "conflict", "exploitation", "outcome")


# --- journal location -------------------------------------------------------------------------------


def _is_safe_match_id(match_id: str) -> bool:
    """A match id is a single path segment. Reject anything with separators or dot-dot traversal so a
    crafted id can never escape ``runs_dir``."""
    if not match_id or match_id in (".", ".."):
        return False
    return not ("/" in match_id or "\\" in match_id or "\x00" in match_id)


def journal_path(runs_dir: Path, match_id: str) -> Path | None:
    """Return the journal path for a match, or ``None`` when the id is unsafe or the file is absent."""
    if not _is_safe_match_id(match_id):
        return None
    candidate = runs_dir / match_id / JOURNAL_NAME
    return candidate if candidate.is_file() else None


def list_matches(runs_dir: Path) -> list[str]:
    """List match ids: subdirectories of ``runs_dir`` that hold a journal file, sorted for stable order."""
    if not runs_dir.is_dir():
        return []
    ids = [child.name for child in runs_dir.iterdir() if (child / JOURNAL_NAME).is_file()]
    return sorted(ids)


def _require_journal(runs_dir: Path, match_id: str) -> Path:
    """Resolve a journal path or raise 404. Shared by every REST handler."""
    path = journal_path(runs_dir, match_id)
    if path is None:
        raise HTTPException(status_code=404, detail=f"unknown match: {match_id!r}")
    return path


# --- metrics and detectors (reached lazily) ---------------------------------------------------------


def _family_summary(name: str, proj: MatchProjection) -> dict[str, object]:
    """Call ``ala.metrics.<name>.<name>_summary(proj)``, or return an empty map if it is not yet present.

    The lazy import keeps the API importable while the metric layer is still being built; at the gate
    every family resolves, so the map fills in without a code change here.
    """
    try:
        module = importlib.import_module(f"ala.metrics.{name}")
    except ImportError:
        return {}
    func: Any = getattr(module, f"{name}_summary", None)
    if func is None:
        return {}
    result: Any = func(proj)
    if isinstance(result, dict):
        return result
    return {}


def metric_dicts(proj: MatchProjection) -> dict[str, dict[str, object]]:
    """The four metric family summaries keyed by family name."""
    return {name: _family_summary(name, proj) for name in METRIC_FAMILIES}


def _incidents_by_kind(proj: MatchProjection) -> dict[str, int]:
    """Count detector incidents by kind, or return an empty map if detectors are not yet present."""
    try:
        detectors = importlib.import_module("ala.detectors")
    except ImportError:
        return {}
    run: Any = getattr(detectors, "run_detectors", None)
    if run is None:
        return {}
    counts: dict[str, int] = {}
    for incident in run(proj):
        kind = str(getattr(incident, "kind", ""))
        counts[kind] = counts.get(kind, 0) + 1
    return counts


# --- summary assembly -------------------------------------------------------------------------------


def match_summary(proj: MatchProjection) -> dict[str, object]:
    """The compact match report served at ``GET /matches/{id}``."""
    return {
        "scenario": proj.scenario,
        "seed": proj.seed,
        "ticks": proj.ticks,
        "final_ranking": list(proj.final_ranking),
        "incidents_by_kind": _incidents_by_kind(proj),
        "metrics": metric_dicts(proj),
    }


# --- router -----------------------------------------------------------------------------------------


def build_router(runs_dir: Path) -> APIRouter:
    """Build the REST router bound to a runs directory. All routes read; none mutate."""
    router = APIRouter()

    @router.get("/matches")
    def get_matches() -> list[str]:
        return list_matches(runs_dir)

    @router.get("/matches/{match_id}")
    def get_match(match_id: str) -> dict[str, object]:
        path = _require_journal(runs_dir, match_id)
        return match_summary(MatchProjection.from_journal(path))

    @router.get("/matches/{match_id}/journal")
    def get_journal(match_id: str) -> list[dict[str, object]]:
        path = _require_journal(runs_dir, match_id)
        return [event.to_record() for event in read_events(path)]

    @router.get("/matches/{match_id}/metrics")
    def get_metrics(match_id: str) -> dict[str, dict[str, object]]:
        path = _require_journal(runs_dir, match_id)
        return metric_dicts(MatchProjection.from_journal(path))

    return router
