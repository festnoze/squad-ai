"""Intake: walk a repo, classify files, count lines, detect stacks.

This produces the METERS (kLOC by language, file counts) that drive pricing,
so it must be transparent and reproducible: exclusion rules live in
config.py and the full file list is written to the work dir for audit.
"""

import json
import os

from .config import (CODE_LANGS, GENERATED_FILE_NAMES, GENERATED_FILE_SUFFIXES,
                     LANG_BY_EXT)


def _is_binary(path):
    try:
        with open(path, "rb") as fh:
            return b"\0" in fh.read(1024)
    except OSError:
        return True


def _count_lines(path):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            return sum(1 for _ in fh)
    except OSError:
        return 0


def walk_repo(root, exclude_dirs):
    """Return [{path, ext, lang, lines}] with path repo-relative, posix style."""
    files = []
    root = os.path.abspath(root)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in exclude_dirs)
        for name in sorted(filenames):
            if name in GENERATED_FILE_NAMES:
                continue
            if name.endswith(GENERATED_FILE_SUFFIXES):
                continue
            ext = os.path.splitext(name)[1].lower()
            lang = LANG_BY_EXT.get(ext)
            if lang is None:
                continue
            full = os.path.join(dirpath, name)
            if _is_binary(full):
                continue
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            files.append({"path": rel, "ext": ext, "lang": lang,
                          "lines": _count_lines(full)})
    return files


def summarize(files):
    kloc_by_lang = {}
    for f in files:
        kloc_by_lang.setdefault(f["lang"], 0)
        kloc_by_lang[f["lang"]] += f["lines"]
    kloc_by_lang = {k: round(v / 1000.0, 2) for k, v in sorted(kloc_by_lang.items())}
    code_lines = sum(f["lines"] for f in files if f["lang"] in CODE_LANGS)
    return {
        "file_count": len(files),
        "code_file_count": sum(1 for f in files if f["lang"] in CODE_LANGS),
        "kloc_by_lang": kloc_by_lang,
        "code_kloc": round(code_lines / 1000.0, 2) or (0.01 if code_lines else 0.0),
    }


def detect_stacks(root, files):
    """Best-effort stack detection from manifests and file mix."""
    stacks = set()
    paths = {f["path"] for f in files}
    if any(p.endswith(".csproj") for p in paths):
        stacks.add("csharp")
    if any(f["lang"] == "python" for f in files):
        stacks.add("python")
    for f in files:
        if f["path"] == "package.json":
            try:
                with open(os.path.join(root, f["path"]), "r", encoding="utf-8") as fh:
                    pkg = json.load(fh)
                deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                if "@angular/core" in deps:
                    stacks.add("angular")
                elif "react" in deps:
                    stacks.add("react")
                elif deps:
                    stacks.add("node")
            except (OSError, ValueError):
                pass
    if not stacks and any(f["lang"] in ("typescript", "javascript") for f in files):
        stacks.add("node")
    return sorted(stacks)


def run_intake(repo_cfg, exclude_dirs, work_dir):
    files = walk_repo(repo_cfg.path, exclude_dirs)
    result = {
        "repo": repo_cfg.name,
        "path": repo_cfg.path,
        "stacks": [repo_cfg.stack_hint] if repo_cfg.stack_hint else detect_stacks(repo_cfg.path, files),
        "meters": summarize(files),
        "files": files,
    }
    out = os.path.join(work_dir, repo_cfg.name, "intake.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=1)
    return result
