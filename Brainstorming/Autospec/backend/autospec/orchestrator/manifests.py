"""Fusion déterministe des MANIFESTES de dépendances (séparation inter-stream).

Deux tâches parallèles qui ajoutent chacune une dépendance éditent le même
``pyproject.toml`` / ``package.json`` : c'est un conflit de merge STRUCTUREL —
aucune découpe en zones disjointes ne peut l'éviter, car le manifeste est par
nature partagé. Plutôt que de sérialiser (ou de rejouer) le travail vert, ces
fichiers sont **auto-fusionnables** : quand les DEUX versions ne diffèrent que
par leurs listes de dépendances, l'union est calculée déterministiquement et le
merge aboutit. Les lockfiles (``uv.lock``, ``package-lock.json``) associés sont
résolus côté HEAD — ils sont RÉGÉNÉRÉS par l'outillage (``uv run`` re-résout le
lock ; ``npm install`` le met à jour), pas fusionnés ligne à ligne.

Prudence avant tout : si les versions divergent AUTREMENT que par les
dépendances (ou qu'un fichier ne se parse pas), la fusion est refusée
(``None``) et le chemin de conflit normal reprend la main.
"""

from __future__ import annotations

import json
import re
import tomllib

__all__ = [
    "MERGEABLE_MANIFESTS",
    "LOCKFILES",
    "is_manifest_conflict",
    "merge_pyproject",
    "merge_package_json",
]

MERGEABLE_MANIFESTS = ("pyproject.toml", "package.json")
LOCKFILES = ("uv.lock", "package-lock.json")


def _basename(path: str) -> str:
    return path.strip().replace("\\", "/").rsplit("/", 1)[-1]


def is_manifest_conflict(conflict_files: list[str]) -> bool:
    """True when EVERY conflicted file is a dependency manifest or a lockfile —
    the only case the auto-resolution is allowed to take over the merge."""
    if not conflict_files:
        return False
    return all(
        _basename(f) in MERGEABLE_MANIFESTS + LOCKFILES for f in conflict_files
    )


# ------------------------------------------------------------- pyproject.toml

_DEP_NAME_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def _dist_name(requirement: str) -> str:
    """The canonical distribution name of a PEP 508 requirement string
    (``"HTTPX>=0.27"`` → ``"httpx"``), for duplicate detection."""
    m = _DEP_NAME_RE.match(requirement)
    return (m.group(1) if m else requirement).lower().replace("_", "-").replace(".", "-")


def _without_deps(data: dict) -> dict:
    """A pyproject dict with every dependency list blanked — what must be
    IDENTICAL between ours/theirs for the union merge to be safe."""
    out = json.loads(json.dumps(data))  # deep copy of plain toml types
    out.get("project", {}).pop("dependencies", None)
    if "dependency-groups" in out:
        out["dependency-groups"] = sorted(out["dependency-groups"].keys())
    return out


def _union(ours: list[str], theirs: list[str]) -> list[str]:
    """Ours first (its pins win on a same-name clash), then theirs' new dists."""
    known = {_dist_name(d) for d in ours}
    merged = list(ours)
    for dep in theirs:
        if _dist_name(dep) not in known:
            merged.append(dep)
            known.add(_dist_name(dep))
    return merged


def _replace_toml_array(text: str, anchor: str, values: list[str]) -> str | None:
    """Rewrite the ``<anchor> = [...]`` array of a TOML text with ``values``
    (one entry per line). Text-level on purpose: it preserves the rest of the
    file byte-for-byte. None when the anchor's array cannot be located."""
    m = re.search(rf"(?m)^({re.escape(anchor)}\s*=\s*\[)", text)
    if m is None:
        return None
    start = m.end(1)
    depth = 1
    i = start
    while i < len(text) and depth:
        if text[i] == "[":
            depth += 1
        elif text[i] == "]":
            depth -= 1
        i += 1
    if depth:
        return None
    body = "" if not values else "\n" + "\n".join(f'    "{v}",' for v in values) + "\n"
    return text[: m.end(1)] + body + text[i - 1 :]


def merge_pyproject(ours: str, theirs: str) -> str | None:
    """Union merge of two pyproject.toml texts that only diverge by their
    dependency lists (``project.dependencies`` + each ``dependency-groups``
    list). Returns the merged text (ours' formatting preserved), or None when
    the divergence goes beyond dependencies — unsafe to auto-resolve."""
    try:
        ours_data = tomllib.loads(ours)
        theirs_data = tomllib.loads(theirs)
        if _without_deps(ours_data) != _without_deps(theirs_data):
            return None
    except (tomllib.TOMLDecodeError, TypeError, ValueError):
        return None  # unparseable / non-JSON-serializable TOML types: hands off
    merged = ours
    union = _union(
        list(ours_data.get("project", {}).get("dependencies", [])),
        list(theirs_data.get("project", {}).get("dependencies", [])),
    )
    merged_or_none = _replace_toml_array(merged, "dependencies", union)
    if merged_or_none is None:
        return None
    merged = merged_or_none
    for group, theirs_list in (theirs_data.get("dependency-groups") or {}).items():
        ours_list = list((ours_data.get("dependency-groups") or {}).get(group, []))
        union = _union(ours_list, list(theirs_list))
        if union != ours_list:
            merged_or_none = _replace_toml_array(merged, group, union)
            if merged_or_none is None:
                return None
            merged = merged_or_none
    try:  # the result must still parse — never commit a broken manifest
        tomllib.loads(merged)
    except tomllib.TOMLDecodeError:
        return None
    return merged


# -------------------------------------------------------------- package.json

_NPM_DEP_KEYS = ("dependencies", "devDependencies")


def merge_package_json(ours: str, theirs: str) -> str | None:
    """Union merge of two package.json texts that only diverge by their
    ``dependencies``/``devDependencies`` maps (ours' version wins on a clash).
    None when anything else differs."""
    try:
        ours_data = json.loads(ours)
        theirs_data = json.loads(theirs)
    except json.JSONDecodeError:
        return None
    stripped_ours = {k: v for k, v in ours_data.items() if k not in _NPM_DEP_KEYS}
    stripped_theirs = {k: v for k, v in theirs_data.items() if k not in _NPM_DEP_KEYS}
    if stripped_ours != stripped_theirs:
        return None
    merged = dict(ours_data)
    for key in _NPM_DEP_KEYS:
        ours_map = dict(ours_data.get(key) or {})
        for name, version in (theirs_data.get(key) or {}).items():
            ours_map.setdefault(name, version)
        if ours_map:
            merged[key] = dict(sorted(ours_map.items()))
    return json.dumps(merged, indent=2, ensure_ascii=False) + "\n"
