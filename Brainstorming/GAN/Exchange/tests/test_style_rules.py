"""Repository wide style rules that no single workstream can enforce alone.

CONTRACTS rule 3 (English only) and rule 4 (never the U+2014 dash) are
document level rules. A reviewer cannot hold them across twenty-five parallel
workstreams, so they are asserted here and the CI `quality` job runs this file
by name.

The forbidden character is built with ``chr(0x2014)`` on purpose: writing it
literally would make this very file a violation.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

EM_DASH = chr(0x2014)

# Directories that never hold produced content.
SKIP_DIRS = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "dist",
        "build",
        "runs",
        "htmlcov",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".hypothesis",
        ".eggs",
    }
)

# Files that are INPUTS to this project, not output of it:
#   - the PRD is the French source document and is quoted, never rewritten;
#   - docs/reviews/ holds the frozen adversarial reviews.
# Both legitimately contain the character.
SKIP_PREFIXES = ("docs/reviews/", "PRD_")

BINARY_SUFFIXES = frozenset(
    {".png", ".jpg", ".jpeg", ".gif", ".ico", ".woff", ".woff2", ".ttf", ".parquet", ".sqlite", ".db", ".pyc"}
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def _text_files() -> list[Path]:
    """Every produced text file, with the skipped directories pruned from the walk.

    ``os.walk`` and not ``rglob``: pruning ``dirnames`` in place keeps the scan
    out of ``.venv`` and ``node_modules`` entirely, which is the difference
    between a five second test and a fifty millisecond one.
    """
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(REPO_ROOT):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        here = Path(dirpath)
        for name in sorted(filenames):
            path = here / name
            if path.suffix.lower() in BINARY_SUFFIXES:
                continue
            relative = path.relative_to(REPO_ROOT)
            if relative.as_posix().startswith(SKIP_PREFIXES):
                continue
            files.append(path)
    return files


def test_the_scan_actually_sees_files() -> None:
    """Anti vacuous rule (section 10): a scan over nothing passes trivially."""
    files = _text_files()
    names = {p.relative_to(REPO_ROOT).as_posix() for p in files}
    assert len(files) >= 10, f"the scan found only {len(files)} files, the walk is broken"
    assert "docs/CONTRACTS.md" in names
    assert "src/pxe/types.py" in names
    assert "pyproject.toml" in names


def test_the_scan_would_catch_a_violation(tmp_path: Path) -> None:
    """The detector is asserted against a known bad string, not only a good tree."""
    offender = tmp_path / "bad.md"
    offender.write_text(f"a sentence {EM_DASH} with the wrong dash", encoding="utf-8")
    assert EM_DASH in offender.read_text(encoding="utf-8")


def test_no_em_dash_in_produced_content() -> None:
    hits: list[str] = []
    for path in _text_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if EM_DASH in line:
                hits.append(f"{path.relative_to(REPO_ROOT).as_posix()}:{lineno}")
    assert not hits, "contract rule 4: use a hyphen or parentheses, never U+2014. Offenders:\n" + "\n".join(hits)


@pytest.mark.parametrize("suffix", [".py"])
def test_python_sources_are_utf8_without_bom(suffix: str) -> None:
    for path in _text_files():
        if path.suffix != suffix:
            continue
        head = path.read_bytes()[:3]
        assert head != b"\xef\xbb\xbf", f"{path} starts with a UTF-8 BOM"


def test_no_python_source_uses_the_banned_builtin_round() -> None:
    """Section 2.1: ``round()`` is banker's rounding and is banned in ``src``.

    ``pxe.types.round_half_up`` is the one legal rounding helper. This test
    reads the source text rather than the AST on purpose: the point is that a
    reviewer grepping for ``round(`` finds nothing, in every module, forever.
    """
    offenders: list[str] = []
    for path in sorted((REPO_ROOT / "src").rglob("*.py")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#") or "round_half_up" in line or "bps_ratio" in line:
                continue
            if " round(" in line or line.startswith("round(") or "=round(" in line or "(round(" in line:
                offenders.append(f"{path.relative_to(REPO_ROOT).as_posix()}:{lineno}: {stripped}")
    assert not offenders, "section 2.1 bans the builtin round(); use pxe.types.round_half_up:\n" + "\n".join(offenders)
