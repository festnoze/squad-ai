"""Git history analysis: churn, authorship, bus factor, hotspots.

All numbers here are deterministic given the repository state; agents never
compute them, only narrate them.
"""

import os
import subprocess
from collections import Counter


def _subtree_prefix(root):
    """If root is a subdirectory of its git repo, paths in `git log` are
    relative to the git toplevel; return the prefix to strip."""
    try:
        proc = subprocess.run(["git", "-C", root, "rev-parse", "--show-toplevel"],
                              capture_output=True, text=True, timeout=30,
                              encoding="utf-8", errors="ignore")
    except (OSError, subprocess.TimeoutExpired):
        return None
    top = proc.stdout.strip()
    if proc.returncode != 0 or not top:
        return None
    rel = os.path.relpath(os.path.abspath(root), top).replace(os.sep, "/")
    return "" if rel == "." else rel + "/"


def collect(root, max_commits=5000):
    """Parse `git log --numstat` (scoped to root's subtree). None if absent."""
    prefix = _subtree_prefix(root)
    try:
        proc = subprocess.run(
            ["git", "-C", root, "log", f"-n{max_commits}", "--numstat",
             "--no-renames", "--date=short", "--format=@@%H|%an|%ad",
             "--", "."],
            capture_output=True, text=True, timeout=120, encoding="utf-8",
            errors="ignore")
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return None

    per_file = {}
    commit_dates = []
    author = date = None
    for line in proc.stdout.splitlines():
        if line.startswith("@@"):
            _, author, date = line[2:].split("|", 2)
            commit_dates.append(date)
            continue
        parts = line.split("\t")
        if len(parts) != 3 or author is None or date is None:
            continue
        added, deleted, path = parts
        path = path.replace("\\", "/")
        if prefix:
            if not path.startswith(prefix):
                continue
            path = path[len(prefix):]
        entry = per_file.setdefault(path, {
            "commits": 0, "authors": Counter(), "churn": 0, "last": ""})
        entry["commits"] += 1
        entry["authors"][author] += 1
        try:
            entry["churn"] += int(added) + int(deleted)
        except ValueError:
            pass  # binary files show "-"
        entry["last"] = max(entry["last"], date)

    return {"files": per_file, "commit_dates": sorted(commit_dates)}


def bus_factor(author_counter):
    """Smallest number of authors covering >= 50% of a scope's commits."""
    total = sum(author_counter.values())
    if total == 0:
        return 0
    covered = 0
    for i, (_, count) in enumerate(author_counter.most_common(), start=1):
        covered += count
        if covered * 2 >= total:
            return i
    return len(author_counter)


def rollup(stats, paths):
    """Aggregate per-file git stats over a set of paths (one module)."""
    authors = Counter()
    commits = churn = 0
    last = ""
    if not stats:
        return None
    for path in paths:
        entry = stats["files"].get(path)
        if not entry:
            continue
        authors.update(entry["authors"])
        commits += entry["commits"]
        churn += entry["churn"]
        last = max(last, entry["last"])
    if commits == 0:
        return None
    return {"commits": commits, "churn": churn, "last": last,
            "bus_factor": bus_factor(authors),
            "top_author_share": round(authors.most_common(1)[0][1] / commits, 2)}


def hotspots(stats, file_sizes, top=10):
    """Rank files by churn x size: where change pressure meets mass."""
    if not stats:
        return []
    scored = []
    for path, entry in stats["files"].items():
        size = file_sizes.get(path)
        if size is None:
            continue  # deleted or excluded files
        score = entry["commits"] * (1 + size / 400.0)
        scored.append({"path": path, "commits": entry["commits"],
                       "churn": entry["churn"], "lines": size,
                       "bus_factor": bus_factor(entry["authors"]),
                       "last": entry["last"], "score": round(score, 1)})
    scored.sort(key=lambda h: -h["score"])
    return scored[:top]
