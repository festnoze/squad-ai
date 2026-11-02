"""Well-known locations of the bench (all absolute, derived from this file)."""

from __future__ import annotations

from pathlib import Path

BENCH_DIR = Path(__file__).resolve().parent
BACKEND_DIR = BENCH_DIR.parent
REPO_DIR = BACKEND_DIR.parent
BRIEFS_DIR = BENCH_DIR / "briefs"
DOCS_BENCH_DIR = REPO_DIR / "docs" / "bench"
WORKSPACE_BENCH_DIR = REPO_DIR / "workspace_bench"
