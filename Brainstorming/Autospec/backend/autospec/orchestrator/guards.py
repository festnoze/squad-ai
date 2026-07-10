"""Anti-cheating detectors (Wave 0.5 of VERIFIED_SWARM_UPGRADE.md).

A worker agent, asked to make a story green, can "succeed" for the wrong
reasons: it edits the tests that judge it, touches files it never claimed,
ships a hollow skeleton (``pass``/``raise NotImplementedError``/a hardcoded
``return 42``), skips the very tests that would catch it, or imports a package
that does not exist. The video's "worker that cheated" is exactly this class of
failure — green on paper, empty in fact.

This module makes those moves *structurally catchable*. Every function here is
PURE: it takes plain strings / lists (a source blob, a list of changed paths, a
set of declared dependencies…) and returns a list of findings. There is NO git,
NO filesystem access, and NO pipeline import — the git-diff and file-read
plumbing that feeds these detectors is wired separately by the caller. That
keeps the detectors trivially unit-testable and side-effect free.

Detectors (numbered after the upgrade doc):

- ``modified_test_files``   (T05) — did the worker touch its own judge?
- ``out_of_scope_paths``    (T06) — did it edit outside what it claimed?
- ``detect_skeleton``       (T07) — is the "implementation" hollow / a skip?
- ``unresolved_imports``    (T10) — does it import packages that don't exist?

Conservative by design: when a detector cannot *prove* a violation (a file it
cannot parse, an empty set of claims meaning "nothing declared to enforce") it
stays silent rather than raising a false alarm. The caller decides whether a
finding is fatal or a warning.
"""

from __future__ import annotations

import ast
import fnmatch
import posixpath
import sys

__all__ = [
    "modified_test_files",
    "out_of_scope_paths",
    "detect_skeleton",
    "unresolved_imports",
    "default_stdlib",
]

# Fallback stdlib set for interpreters without ``sys.stdlib_module_names``
# (added in 3.10). Small on purpose — it only needs to cover the modules a
# generated project is likely to import so ``unresolved_imports`` does not flag
# a genuine standard-library import as hallucinated.
_FALLBACK_STDLIB = frozenset({
    "abc", "argparse", "ast", "asyncio", "base64", "collections", "contextlib",
    "copy", "csv", "dataclasses", "datetime", "decimal", "enum", "functools",
    "glob", "hashlib", "heapq", "hmac", "html", "http", "importlib", "inspect",
    "io", "itertools", "json", "logging", "math", "os", "pathlib", "pickle",
    "queue", "random", "re", "secrets", "shutil", "signal", "socket", "sqlite3",
    "ssl", "statistics", "string", "struct", "subprocess", "sys", "tempfile",
    "textwrap", "threading", "time", "traceback", "types", "typing", "unittest",
    "urllib", "uuid", "warnings", "weakref", "xml", "zipfile", "zlib",
})


def _norm(path: str) -> str:
    """Normalise a path to forward slashes with no leading ``./`` so Windows and
    POSIX diffs, and globs written either way, compare consistently."""
    return path.strip().replace("\\", "/").lstrip("./")


# --------------------------------------------------------------------- T05 tamper

def modified_test_files(changed_paths: list[str], test_globs: list[str]) -> list[str]:
    """T05 — the subset of ``changed_paths`` that look like TEST files.

    A worker must not edit the tests that grade it. This returns every changed
    path that a caller should treat as a test-file touch, so the caller can
    reject or flag the change.

    A path counts as a test file when either:

    - it matches any glob in ``test_globs`` (``fnmatch`` semantics, evaluated on
      both the full path and its basename so ``tests/*`` and ``*_test.py`` both
      work); OR
    - ``test_globs`` is empty, in which case a default heuristic applies: the
      path has a ``tests`` (or ``test``) path segment, or its basename matches
      ``test_*.py`` / ``*_test.py``.

    Order and de-duplication follow ``changed_paths`` (stable, first occurrence
    kept). Paths are matched normalised to forward slashes.
    """
    globs = [_norm(g) for g in (test_globs or []) if g and g.strip()]
    out: list[str] = []
    seen: set[str] = set()
    for raw in changed_paths:
        path = _norm(raw)
        if path in seen:
            continue
        base = posixpath.basename(path)
        is_test = False
        if globs:
            is_test = any(
                fnmatch.fnmatch(path, g) or fnmatch.fnmatch(base, g) for g in globs
            )
        else:
            segments = path.split("/")
            is_test = (
                "tests" in segments
                or "test" in segments
                or fnmatch.fnmatch(base, "test_*.py")
                or fnmatch.fnmatch(base, "*_test.py")
            )
        if is_test:
            seen.add(path)
            out.append(raw)
    return out


# ---------------------------------------------------------------------- T06 scope

def out_of_scope_paths(changed_paths: list[str], declared_claims: list[str]) -> list[str]:
    """T06 — changed paths NOT covered by any declared claim.

    A worker declares up front which files/areas it will touch (its claims). Any
    file it actually changed that no claim covers is out of scope — a sign it
    wandered into another task's territory (and a merge-conflict risk).

    A claim covers a changed path when it is, after normalisation:

    - an exact path match; OR
    - a directory prefix of the path (``src/`` or ``src`` both cover
      ``src/app.py`` — a bare directory name is treated segment-wise, so
      ``src`` does NOT cover ``srcutil.py``); OR
    - a glob that ``fnmatch``-matches the path.

    ``declared_claims`` empty ⇒ NOTHING is enforced (the worker declared no
    scope, so there is nothing to violate): returns ``[]``. Result order and
    de-duplication follow ``changed_paths``.
    """
    claims = [_norm(c) for c in (declared_claims or []) if c and c.strip()]
    if not claims:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for raw in changed_paths:
        path = _norm(raw)
        if path in seen:
            continue
        if not any(_claim_covers(claim, path) for claim in claims):
            seen.add(path)
            out.append(raw)
    return out


def _claim_covers(claim: str, path: str) -> bool:
    """Whether a single (normalised) claim covers a (normalised) changed path."""
    if not claim:
        return False
    if claim == path:
        return True
    # Glob claim: any wildcard char means match by fnmatch.
    if any(ch in claim for ch in "*?["):
        if fnmatch.fnmatch(path, claim):
            return True
        # A directory-glob like ``src/*`` should also cover deeper paths.
        if claim.endswith("/*") and fnmatch.fnmatch(path, claim[:-2] + "/**"):
            return True
        return fnmatch.fnmatch(path, claim.rstrip("/") + "/**")
    # Directory-prefix claim (segment-wise): ``src`` or ``src/`` covers
    # ``src/app.py`` but not ``srcutil.py``.
    prefix = claim if claim.endswith("/") else claim + "/"
    return path.startswith(prefix)


# ------------------------------------------------------------------- T07 skeleton

def detect_skeleton(source: str, filename: str = "") -> list[str]:
    """T07 — flag hollow implementations and test-skips in Python ``source``.

    Parses ``source`` with :mod:`ast` and reports:

    - **skeleton body** — a function/method whose body is ONLY ``pass`` /
      ``...`` (``Ellipsis``) / a bare docstring / ``raise NotImplementedError``;
    - **hardcoded return** — a non-dunder function whose ONLY statement is
      ``return <literal>`` (a constant, or a literal list/tuple/dict/set) — the
      classic "make the test pass by returning the expected value" cheat;
    - **test skip** — a ``pytest.skip(...)`` call, or a ``@pytest.mark.skip`` /
      ``@pytest.mark.xfail`` decorator, which disables the judging test.

    Findings are human-readable, e.g. ``"skeleton body: foo() at line 12"``.

    ``filename`` that is not a ``.py`` file ⇒ ``[]`` (nothing to parse). A
    :class:`SyntaxError` ⇒ ``[]`` as well: we cannot judge code we cannot parse,
    and staying silent avoids false positives on partial/invalid blobs.
    """
    if filename and not filename.endswith(".py"):
        return []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    findings: list[str] = []

    for node in ast.walk(tree):
        # -- pytest skip/xfail decorators on any def/class -----------------
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            for dec in node.decorator_list:
                mark = _pytest_mark(dec)
                if mark in ("skip", "xfail"):
                    findings.append(
                        f"test skip: @pytest.mark.{mark} on {node.name} "
                        f"at line {dec.lineno}"
                    )

        # -- pytest.skip(...) call anywhere --------------------------------
        if isinstance(node, ast.Call) and _is_pytest_skip_call(node.func):
            findings.append(f"test skip: pytest.skip() call at line {node.lineno}")

        # -- function bodies -----------------------------------------------
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            body = _body_without_docstring(node)
            reason = _skeleton_reason(node, body)
            if reason:
                findings.append(f"{reason}: {node.name}() at line {node.lineno}")

    return findings


def _body_without_docstring(node) -> list:
    """The function body with a leading bare-docstring statement stripped."""
    body = list(node.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(
        body[0].value, ast.Constant
    ) and isinstance(body[0].value.value, str):
        body = body[1:]
    return body


def _skeleton_reason(node, body: list) -> str:
    """Classify a function body; ``""`` when it is a real implementation.

    Returns ``"skeleton body"`` for pass/.../docstring-only/NotImplementedError,
    or ``"hardcoded return"`` for a lone ``return <literal>`` in a non-dunder.
    """
    if not body:
        # Docstring-only (docstring already stripped) counts as a skeleton.
        return "skeleton body"
    if len(body) == 1:
        stmt = body[0]
        # pass
        if isinstance(stmt, ast.Pass):
            return "skeleton body"
        # bare ... (Ellipsis expression statement)
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) \
                and stmt.value.value is Ellipsis:
            return "skeleton body"
        # raise NotImplementedError [ (...) ]
        if isinstance(stmt, ast.Raise) and _raises_not_implemented(stmt):
            return "skeleton body"
        # return <literal> as the sole statement (non-dunder only)
        if isinstance(stmt, ast.Return) and not _is_dunder(node.name):
            if stmt.value is not None and _is_literal(stmt.value):
                return "hardcoded return"
    return ""


def _raises_not_implemented(stmt: ast.Raise) -> bool:
    exc = stmt.exc
    if exc is None:
        return False
    if isinstance(exc, ast.Call):
        exc = exc.func
    if isinstance(exc, ast.Name):
        return exc.id == "NotImplementedError"
    if isinstance(exc, ast.Attribute):
        return exc.attr == "NotImplementedError"
    return False


def _is_literal(value: ast.expr) -> bool:
    """A hardcoded constant or literal container (all-literal contents)."""
    if isinstance(value, ast.Constant):
        return True
    if isinstance(value, (ast.List, ast.Tuple, ast.Set)):
        return all(_is_literal(e) for e in value.elts)
    if isinstance(value, ast.Dict):
        return all(
            (k is None or _is_literal(k)) and _is_literal(v)
            for k, v in zip(value.keys, value.values)
        )
    return False


def _is_dunder(name: str) -> bool:
    return name.startswith("__") and name.endswith("__")


def _dotted_name(node) -> str:
    """Reconstruct a dotted attribute/name expression, e.g. ``pytest.mark.skip``.
    Returns ``""`` for anything that is not a plain Name/Attribute chain."""
    parts: list[str] = []
    cur = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
        return ".".join(reversed(parts))
    return ""


def _pytest_mark(dec: ast.expr) -> str:
    """If ``dec`` is a ``pytest.mark.<name>`` decorator (bare or called), return
    ``<name>`` (e.g. ``skip``, ``xfail``); else ``""``."""
    target = dec.func if isinstance(dec, ast.Call) else dec
    dotted = _dotted_name(target)
    parts = dotted.split(".")
    if len(parts) >= 3 and parts[-3] == "pytest" and parts[-2] == "mark":
        return parts[-1]
    # Also handle ``mark.skip`` when imported as ``from pytest import mark``.
    if len(parts) == 2 and parts[0] == "mark":
        return parts[1]
    return ""


def _is_pytest_skip_call(func: ast.expr) -> bool:
    """Whether a call target is ``pytest.skip`` (or a bare ``skip`` imported
    from pytest, e.g. ``from pytest import skip``)."""
    dotted = _dotted_name(func)
    parts = dotted.split(".")
    if len(parts) >= 2 and parts[-2] == "pytest" and parts[-1] == "skip":
        return True
    return dotted == "skip"


# ------------------------------------------------------------------- T10 imports

def default_stdlib() -> set[str]:
    """The set of standard-library top-level module names for this interpreter.

    Uses :data:`sys.stdlib_module_names` (Python 3.10+); falls back to a small
    hardcoded set on older interpreters where that attribute is unavailable."""
    names = getattr(sys, "stdlib_module_names", None)
    if names:
        return set(names)
    return set(_FALLBACK_STDLIB)


def unresolved_imports(
    source: str,
    declared_deps: set[str],
    stdlib_modules: set[str],
    local_modules: set[str] = frozenset(),
) -> list[str]:
    """T10 — top-level imports that resolve to NOTHING known.

    Parses every ``import`` / ``from ... import`` in ``source`` and returns the
    top-level package names that appear in NONE of:

    - ``declared_deps``   — packages the task declared it depends on;
    - ``stdlib_modules``  — the standard library (see :func:`default_stdlib`);
    - ``local_modules``   — first-party modules of the project being built.

    Dotted imports are normalised to their top package
    (``import a.b.c`` → ``a``; ``from a.b import c`` → ``a``). Relative imports
    (``from . import x``) are project-local and never flagged. A finding is the
    bare unresolved package name; the list is de-duplicated and sorted for
    stable output.

    A :class:`SyntaxError` ⇒ ``[]`` (cannot judge unparsable source).
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    known = set(declared_deps or ()) | set(stdlib_modules or ()) | set(local_modules or ())
    unresolved: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".", 1)[0]
                if top and top not in known:
                    unresolved.add(top)
        elif isinstance(node, ast.ImportFrom):
            # Relative import (level > 0) → project-local, never unresolved.
            if node.level and node.level > 0:
                continue
            if not node.module:
                continue
            top = node.module.split(".", 1)[0]
            if top and top not in known:
                unresolved.add(top)

    return sorted(unresolved)
