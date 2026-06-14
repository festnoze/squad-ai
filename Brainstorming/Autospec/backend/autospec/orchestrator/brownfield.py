"""Brownfield mode (B1): build features on top of an existing repository.

Seeds the generated workspace from an existing repo and produces a bounded
summary of its layout, injected as context so the planner/dev work WITH the
existing code instead of greenfield.
"""

from __future__ import annotations

from pathlib import Path

_EXCLUDED_DIRS = {
    ".git", ".venv", "venv", "node_modules", "__pycache__", "dist", "build",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".idea", ".vscode",
}


def _excluded(rel: Path) -> bool:
    return any(part in _EXCLUDED_DIRS for part in rel.parts)


def summarize_repo(path: str | Path, max_files: int = 200, max_chars: int = 8000) -> str:
    """Bounded file-tree summary of an existing repo, or '' if the path is not a
    directory."""
    root = Path(path)
    if not root.is_dir():
        return ""
    lines = [f"Repo existant : {root.name}"]
    count = 0
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if _excluded(rel) or not p.is_file():
            continue
        try:
            size = p.stat().st_size
        except OSError:
            size = 0
        lines.append(f"  {rel.as_posix()} ({size} o)")
        count += 1
        if count >= max_files:
            lines.append("  …(tronqué)")
            break
    return "\n".join(lines)[:max_chars]


def seed_workspace_from(repo_path: str | Path, ws: str | Path) -> int:
    """Copy the existing repo's files into the workspace (excluding VCS/build
    dirs). Never overwrites an existing workspace file. Returns the copy count."""
    root = Path(repo_path)
    ws = Path(ws)
    if not root.is_dir():
        return 0
    copied = 0
    for p in root.rglob("*"):
        rel = p.relative_to(root)
        if _excluded(rel) or not p.is_file():
            continue
        dest = ws / rel
        if dest.exists():
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            dest.write_bytes(p.read_bytes())
            copied += 1
        except OSError:
            continue
    return copied
