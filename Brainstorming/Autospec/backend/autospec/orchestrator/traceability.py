"""Acceptance-criteria ↔ test traceability (W2.0 of VERIFIED_SWARM_UPGRADE.md).

Task W2.0 — "every task ships with an executed check" — made literal. A green
suite is not the same as a *relevant* suite: a worker can write tests that pass
while asserting behaviour no acceptance criterion (AC) ever asked for, and can
leave an AC entirely unverified. This module links each AC to the tests that
verify it so the delivery gate can prove two things:

- **coverage** — every declared AC has ≥1 test that names it;
- **no orphans** — no test verifies an AC that does not exist (a strong signal
  of a wrong/misdirected test, e.g. a typo'd id or a copy-pasted stale test).

CONVENTION
----------
A QA test declares which AC(s) it verifies with an ``AC:`` marker, placed
either in the test function's docstring OR in a ``# AC:`` comment (typically
just above the function). Multiple ids are comma-separated::

    def test_login_rejects_bad_password():
        '''AC: US-3.2'''
        ...

    # AC: US-3.2, US-3.3
    def test_login_locks_after_retries():
        ...

An AC id is a token like ``US-3.2``, ``AC1``, ``AC-12`` — letters/digits with
optional ``-``/``.`` separators. Ids are matched case-sensitively and returned
verbatim.

PURITY
------
Every function here is PURE and stdlib-only (:mod:`re`, :mod:`ast`). There is NO
pipeline/runner/filesystem import: callers pass in source blobs (strings) and
already-known AC ids (a set), and get back plain dicts/sets/lists. Functions
never raise on bad input — unparsable / empty / garbage source yields an empty
result so the gate can run over a whole tree without guarding each file.
"""

from __future__ import annotations

import ast
import re

__all__ = [
    "ac_ids_in_source",
    "test_functions_with_acs",
    "map_acs_to_tests",
    "coverage_report",
]

# An AC marker: ``AC:`` (optionally ``# AC:``) followed by one or more
# comma-separated ids. We capture the whole id list and split it afterwards so a
# single marker can declare several criteria.
_MARKER_RE = re.compile(r"AC\s*:\s*([A-Za-z0-9][\w.\-,\s]*)")

# A single AC id token inside a marker's id list. Letters/digits with optional
# ``-``/``.`` separators; must start and end alphanumeric.
_ID_RE = re.compile(r"[A-Za-z0-9](?:[\w.\-]*[A-Za-z0-9])?")


def _ids_from_marker_tail(tail: str) -> set[str]:
    """Extract AC ids from the text following an ``AC:`` marker.

    ``tail`` is the comma/space-separated id list captured by ``_MARKER_RE``.
    Splits on commas, trims each piece to its leading id token (so trailing
    prose after the last id is dropped), and drops blanks.
    """
    ids: set[str] = set()
    for piece in tail.split(","):
        m = _ID_RE.match(piece.strip())
        if m:
            ids.add(m.group(0))
    return ids


def ac_ids_in_source(source: str) -> set[str]:
    """All AC ids referenced by ``AC:`` markers anywhere in a test file.

    Scans the raw source text for every ``AC:`` marker (whether it lives in a
    docstring, a ``# AC:`` comment, or any other line) and returns the union of
    the ids it declares. This is a whole-file view; it does NOT attribute ids to
    individual functions (see :func:`test_functions_with_acs` for that).

    Tolerates anything: empty string, non-Python text, or garbage all yield
    ``set()``. Never raises.
    """
    if not source:
        return set()
    ids: set[str] = set()
    for m in _MARKER_RE.finditer(source):
        ids |= _ids_from_marker_tail(m.group(1))
    return ids


def _acs_from_text(text: str | None) -> set[str]:
    """AC ids declared inside a single blob of text (a docstring or a comment)."""
    if not text:
        return set()
    ids: set[str] = set()
    for m in _MARKER_RE.finditer(text):
        ids |= _ids_from_marker_tail(m.group(1))
    return ids


def test_functions_with_acs(source: str) -> dict[str, set[str]]:
    """Map each ``test_*`` function to the set of AC ids it declares.

    A function's ids come from two places, unioned:

    - its own docstring (an ``AC:`` marker on any line of it);
    - ``# AC:`` comments on the lines immediately preceding the ``def`` (a
      contiguous block of comment lines directly above it), plus a trailing
      ``# AC:`` comment on the ``def`` line itself.

    ast-based, so only real function definitions are considered (decorators and
    blank lines between the comment block and the ``def`` are tolerated). Only
    functions whose name starts with ``test`` are included. Every such function
    is present in the result even if it declares no AC (empty set), so callers
    can distinguish "test with no AC" from "not a test".

    A :class:`SyntaxError` (unparsable source) ⇒ ``{}``.
    """
    if not source:
        return {}
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}

    lines = source.splitlines()
    out: dict[str, set[str]] = {}

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.name.startswith("test"):
            continue

        ids = _acs_from_text(ast.get_docstring(node))

        # The ``def`` may sit below a decorator; comments live above the
        # topmost line of the whole definition.
        top_lineno = node.lineno
        if node.decorator_list:
            top_lineno = min(top_lineno, min(d.lineno for d in node.decorator_list))

        # Trailing comment on the def line itself (rare but valid).
        def_line = lines[node.lineno - 1] if 0 < node.lineno <= len(lines) else ""
        if "#" in def_line:
            ids |= _acs_from_text(def_line[def_line.index("#"):])

        # Contiguous block of comment lines directly above the definition.
        idx = top_lineno - 2  # 0-based index of the line just above ``top_lineno``
        while idx >= 0:
            stripped = lines[idx].strip()
            if not stripped:
                # A blank line breaks the contiguous comment block.
                break
            if stripped.startswith("#"):
                ids |= _acs_from_text(stripped)
                idx -= 1
                continue
            break

        out[node.name] = ids

    return out


def map_acs_to_tests(test_sources: dict[str, str]) -> dict[str, list[str]]:
    """Invert file→ACs into AC→files.

    Given ``{test_file_path: source}``, return ``{ac_id: [file_path, ...]}``
    listing, for each AC id referenced anywhere in a file, the files that
    reference it. File lists are de-duplicated and sorted for stable output.

    A file that fails to parse or contains no markers simply contributes no ids.
    Never raises.
    """
    acc: dict[str, set[str]] = {}
    for path, source in (test_sources or {}).items():
        for ac_id in ac_ids_in_source(source or ""):
            acc.setdefault(ac_id, set()).add(path)
    return {ac_id: sorted(paths) for ac_id, paths in acc.items()}


def coverage_report(all_ac_ids: set[str], test_sources: dict[str, str]) -> dict:
    """Traceability report over a set of declared ACs and a corpus of tests.

    Returns a dict with three sorted lists:

    - ``covered``   — declared AC ids that ≥1 test references;
    - ``uncovered`` — declared AC ids that NO test references (a delivery gap);
    - ``orphans``   — AC ids that tests reference but that are NOT in
      ``all_ac_ids`` (a test verifying a non-existent criterion — likely a
      wrong test or a stale/typo'd id).

    ``all_ac_ids`` empty ⇒ every referenced id is an orphan and nothing is
    covered/uncovered. Never raises.
    """
    declared = set(all_ac_ids or ())
    referenced = set(map_acs_to_tests(test_sources).keys())
    return {
        "covered": sorted(declared & referenced),
        "uncovered": sorted(declared - referenced),
        "orphans": sorted(referenced - declared),
    }
