"""Style guard: the em-dash character is banned repo-wide (CONTRACTS golden rules, section 15).

The em-dash (U+2014) is a well known "written by an AI" tell and the contract forbids it in any produced
content. This test scans every ``.py`` and ``.md`` file under the repo and fails with the exact
file:line of any offender. The forbidden character is built with ``chr(0x2014)`` so this test file does
not trip its own scan.
"""

from __future__ import annotations

from pathlib import Path

# The banned character, built by code point so its literal glyph never appears in this source file.
EM_DASH = chr(0x2014)

REPO_ROOT = Path(__file__).resolve().parents[1]

# Directories that are not "produced content": dependencies, VCS metadata, caches, build outputs.
SKIP_DIRS = frozenset(
    {
        ".venv",
        ".git",
        "__pycache__",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        "node_modules",
        "build",
        "dist",
        ".eggs",
    }
)

SCANNED_SUFFIXES = frozenset({".py", ".md"})


def _iter_source_files() -> list[Path]:
    """Collect every scanned source file under the repo, skipping non-authored directories."""
    files: list[Path] = []
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in SCANNED_SUFFIXES:
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(REPO_ROOT).parts):
            continue
        files.append(path)
    return files


def test_no_em_dash_anywhere() -> None:
    """Every authored ``.py``/``.md`` file must be free of the em-dash character."""
    offenders: list[str] = []
    for path in _iter_source_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if EM_DASH in line:
                rel = path.relative_to(REPO_ROOT).as_posix()
                offenders.append(f"{rel}:{lineno}")

    assert not offenders, "em-dash (U+2014) found in produced content:\n" + "\n".join(offenders)


def test_scan_actually_covers_the_repo() -> None:
    """Guard against a vacuously green scan: the walk must find our own source and the contract doc."""
    scanned = {p.relative_to(REPO_ROOT).as_posix() for p in _iter_source_files()}
    assert "tests/test_style_rules.py" in scanned
    assert any(p.startswith("src/ala/") and p.endswith(".py") for p in scanned)
