"""Canonical repo-relative claims, checked before any worker may write."""

from __future__ import annotations

import fnmatch
import os
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Iterable

from .independence import globs_overlap


class ClaimError(ValueError):
    pass


def canonical_path(raw: str, *, windows: bool | None = None, allow_empty: bool = False) -> str:
    """Normalize separators/case, without stripping away traversal or drives."""
    if not isinstance(raw, str) or "\x00" in raw:
        raise ClaimError("invalid claim path")
    raw = raw.strip().replace("\\", "/")
    if not raw and allow_empty:
        return ""
    if not raw or raw.startswith("/") or PureWindowsPath(raw).drive or ":" in raw:
        raise ClaimError("claims must be relative, without drives/UNC/ADS")
    parts = raw.split("/")
    if ".." in parts:
        raise ClaimError("claim traversal is forbidden")
    parts = [part for part in parts if part not in ("", ".")]
    if not parts:
        raise ClaimError("empty claim")
    windows = os.name == "nt" if windows is None else windows
    if windows and any(part.endswith((" ", ".")) for part in parts):
        raise ClaimError("ambiguous Windows path segment")
    path = "/".join(parts)
    return path.casefold() if windows else path


@dataclass(frozen=True)
class CanonicalClaim:
    path: str
    stream_root: str
    owner: str
    mode: str = "exclusive"
    reason: str = ""
    version: int = 1
    project_root: str = ""


def canonical_claim(raw: str, *, project_root: Path, owner: str, stream_root: str = "",
                    mode: str = "exclusive", reason: str = "", windows: bool | None = None,
                    incompatible_prefixes: Iterable[str] = ()) -> CanonicalClaim:
    """Claims are always workspace-relative (including any stream prefix).

    ``stream_root`` is the actual scaffold's workspace-relative root, never
    inferred from a language/framework name. ``incompatible_prefixes`` are
    layout constraints supplied by that scaffold, not guesses from existence.
    Globs/future files are valid; static ancestors still must not escape via a
    symlink/junction. Paths containing wildcard roots remain relative patterns.
    """
    if not owner or mode not in {"exclusive", "read"}:
        raise ClaimError("owner and a valid claim mode are required")
    path = canonical_path(raw, windows=windows)
    zone = canonical_path(stream_root, windows=windows, allow_empty=True)
    if any(c in zone for c in "*?["):
        raise ClaimError("stream root cannot be a glob")
    if zone and path != zone and not path.startswith(zone + "/"):
        raise ClaimError(f"claim {path} is outside real stream root {zone}")
    for prefix in incompatible_prefixes:
        wrong = canonical_path(prefix, windows=windows)
        if path == wrong or path.startswith(wrong + "/"):
            raise ClaimError(f"claim {path} contradicts scaffold layout {wrong}")
    root = Path(project_root).resolve()
    resolved_zone = (root / zone).resolve()
    if not resolved_zone.is_relative_to(root):
        raise ClaimError("stream root escapes the workspace")
    # Validate the longest literal ancestor, even if the final file is future.
    literal = []
    for part in path.split("/"):
        if any(c in part for c in "*?["):
            break
        literal.append(part)
    actual = root.joinpath(*literal).resolve()
    if not actual.is_relative_to(root) or not actual.is_relative_to(resolved_zone):
        raise ClaimError("claim escapes through a symlink/junction")
    return CanonicalClaim(path, str(resolved_zone), owner, mode, reason, project_root=str(root))


def path_matches(path: str, pattern: str) -> bool:
    """Segment-aware glob matching; ** includes zero or more directories."""
    parts, globs = path.split("/"), pattern.split("/")

    def match(i: int, j: int) -> bool:
        if j == len(globs):
            return i == len(parts)
        if globs[j] == "**":
            return match(i, j + 1) or (i < len(parts) and match(i + 1, j))
        return i < len(parts) and fnmatch.fnmatchcase(parts[i], globs[j]) and match(i + 1, j + 1)

    return match(0, 0)


def file_in_scope(path: str, globs: Iterable[str], *, project_root: Path, owner: str,
                  stream_root: str = "", windows: bool | None = None) -> bool:
    try:
        target = canonical_claim(path, project_root=project_root, owner=owner,
                                 stream_root=stream_root, windows=windows)
        patterns = [canonical_claim(g, project_root=project_root, owner=owner,
                                   stream_root=stream_root, windows=windows).path for g in globs]
    except ClaimError:
        return False
    return any(path_matches(target.path, pattern) for pattern in patterns)


def claims_conflict(a: CanonicalClaim, b: CanonicalClaim) -> bool:
    # Paths are canonical WORKSPACE relative, so stream names do not disjoint a
    # shared file. Two readers may coexist; a writer is exclusive.
    return (a.project_root == b.project_root and a.owner != b.owner and
            not (a.mode == b.mode == "read") and globs_overlap(a.path, b.path))
