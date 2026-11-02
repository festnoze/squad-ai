"""Frozen project briefs and their manifest of hashes.

A brief is a markdown file with a small front matter::

    ---
    name: Slugify lib
    package: slugify_lib
    profile: lib
    goal: one line
    ---

``manifest.json`` stores the sha256 of every brief (and of the documents a
pointer brief refers to). The runner refuses to run a project whose brief no
longer matches the manifest: a changed brief is a new bench version, compared
results must come from the same version.

Hashes are computed on the content with CRLF normalized to LF, so a Windows
checkout with ``core.autocrlf=true`` hashes like a Linux one.

CLI (from ``backend/``)::

    python -m bench.briefs            # verify every brief against the manifest
    python -m bench.briefs --write    # rewrite the manifest (bumps bench_version on change)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from bench.paths import BRIEFS_DIR, REPO_DIR

MANIFEST_NAME = "manifest.json"
_BRIEF_FILE = re.compile(r"^(B\d+)-[\w.-]+\.md$")
_REQUIRED_KEYS = ("name", "package", "profile")
PROFILES = ("lib", "cli", "api", "fullstack")


class ManifestError(RuntimeError):
    """A brief is missing, malformed, or differs from the manifest."""


@dataclass(frozen=True)
class Brief:
    id: str  # "B1"
    file: Path
    name: str
    package: str
    profile: str
    goal: str
    body: str  # markdown without the front matter: what a factory receives
    sha256: str
    meta: dict[str, str] = field(default_factory=dict)
    bench_version: int = 0

    @property
    def has_oracle(self) -> bool:
        return self.meta.get("oracle", "hidden") != "none"

    @property
    def refs(self) -> list[str]:
        raw = self.meta.get("refs", "")
        return [part.strip() for part in raw.split(",") if part.strip()]


def normalized_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    """Split the ``---`` delimited ``key: value`` lines from the markdown body."""
    text = text.replace("\r\n", "\n")
    if not text.startswith("---\n"):
        raise ManifestError("brief has no front matter (must start with '---')")
    end = text.find("\n---\n", 3)
    if end < 0:
        raise ManifestError("brief front matter is not closed by '---'")
    meta: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if not line.strip():
            continue
        key, sep, value = line.partition(":")
        if not sep:
            raise ManifestError(f"bad front matter line: {line!r}")
        meta[key.strip()] = value.strip()
    return meta, text[end + len("\n---\n"):].lstrip("\n")


def brief_files(briefs_dir: Path = BRIEFS_DIR) -> dict[str, Path]:
    found: dict[str, Path] = {}
    for path in sorted(briefs_dir.glob("B*.md")):
        match = _BRIEF_FILE.match(path.name)
        if match:
            found[match.group(1)] = path
    return found


def read_manifest(briefs_dir: Path = BRIEFS_DIR) -> dict:
    path = briefs_dir / MANIFEST_NAME
    if not path.exists():
        raise ManifestError(f"missing {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _parse(project_id: str, path: Path, sha: str, bench_version: int) -> Brief:
    meta, body = parse_front_matter(path.read_text(encoding="utf-8"))
    missing = [key for key in _REQUIRED_KEYS if not meta.get(key)]
    if missing:
        raise ManifestError(f"{path.name}: front matter misses {missing}")
    if meta["profile"] not in PROFILES:
        raise ManifestError(f"{path.name}: unknown profile {meta['profile']!r}")
    if not meta["package"].isidentifier():
        raise ManifestError(f"{path.name}: package {meta['package']!r} is not an identifier")
    return Brief(id=project_id, file=path, name=meta["name"], package=meta["package"],
                 profile=meta["profile"], goal=meta.get("goal", meta["name"]), body=body,
                 sha256=sha, meta=meta, bench_version=bench_version)


def load_brief(project_id: str, briefs_dir: Path = BRIEFS_DIR,
               repo_dir: Path = REPO_DIR) -> Brief:
    """Load a brief, refusing it when it (or a document it points to) changed."""
    manifest = read_manifest(briefs_dir)
    entry = manifest.get("briefs", {}).get(project_id)
    if entry is None:
        raise ManifestError(f"{project_id} is not in {MANIFEST_NAME}")
    path = briefs_dir / entry["file"]
    if not path.exists():
        raise ManifestError(f"brief file {path} is missing")
    sha = normalized_sha256(path)
    if sha != entry["sha256"]:
        raise ManifestError(
            f"brief {project_id} ({entry['file']}) changed: sha256 {sha[:12]} != manifest "
            f"{entry['sha256'][:12]}. A changed brief is a new bench version: run "
            f"`python -m bench.briefs --write` deliberately, results will not be comparable.")
    for ref, ref_sha in entry.get("refs", {}).items():
        ref_path = repo_dir / ref
        if not ref_path.exists():
            raise ManifestError(f"{project_id} refers to missing {ref}")
        if normalized_sha256(ref_path) != ref_sha:
            raise ManifestError(f"{project_id}: referenced document {ref} changed since the manifest")
    return _parse(project_id, path, sha, int(manifest.get("bench_version", 0)))


def build_manifest(briefs_dir: Path = BRIEFS_DIR, repo_dir: Path = REPO_DIR,
                   previous: dict | None = None) -> dict:
    """Manifest for the briefs on disk; bench_version is bumped when anything changed."""
    briefs: dict[str, dict] = {}
    for project_id, path in brief_files(briefs_dir).items():
        sha = normalized_sha256(path)
        brief = _parse(project_id, path, sha, 0)
        entry: dict = {"file": path.name, "sha256": sha, "package": brief.package,
                       "profile": brief.profile}
        if brief.refs:
            entry["refs"] = {ref: normalized_sha256(repo_dir / ref) for ref in brief.refs}
        briefs[project_id] = entry
    version = 1
    if previous:
        version = int(previous.get("bench_version", 1))
        if previous.get("briefs") != briefs:
            version += 1
    return {"bench_version": version, "hash": "sha256 of the file, CRLF normalized to LF",
            "briefs": briefs}


def verify_all(briefs_dir: Path = BRIEFS_DIR, repo_dir: Path = REPO_DIR) -> list[str]:
    """Problems found (an empty list means every brief matches the manifest)."""
    try:
        manifest = read_manifest(briefs_dir)
    except ManifestError as exc:
        return [str(exc)]
    problems: list[str] = []
    listed = set(manifest.get("briefs", {}))
    for extra in sorted(set(brief_files(briefs_dir)) - listed):
        problems.append(f"{extra} exists on disk but is not in the manifest")
    for project_id in sorted(listed):
        try:
            load_brief(project_id, briefs_dir, repo_dir)
        except ManifestError as exc:
            problems.append(str(exc))
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m bench.briefs")
    parser.add_argument("--write", action="store_true",
                        help="rewrite manifest.json from the briefs on disk")
    args = parser.parse_args(argv)
    path = BRIEFS_DIR / MANIFEST_NAME
    if args.write:
        previous = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
        manifest = build_manifest(previous=previous)
        path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(json.dumps(manifest, indent=2))
        return 0
    problems = verify_all()
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        return 1
    manifest = read_manifest()
    print(f"bench_version {manifest.get('bench_version')}")
    for project_id, entry in manifest["briefs"].items():
        print(f"{project_id} {entry['sha256']} {entry['file']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
