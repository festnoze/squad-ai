"""Failure-signature normalization — stable keys for recurring-failure detection.

Wave 0.5 / task W0.5-SIG. The Wave 1 recovery state machine (``recovery.py``,
T1.1) reacts to a task that stays red *in the same way* across attempts: retry
same rung → escalate model → classify → split/arbitrate/amend → fail. To do that
it must be able to answer one deceptively hard question — *"is this the SAME
failure I saw last attempt, or a different one?"* — cheaply and deterministically.

A raw pytest failure is a terrible identity key: the same logical bug prints a
different assertion line number after an edit, a fresh ``tmp_path`` (``/tmp/…``,
``C:\\Users\\…\\Temp\\pytest-of-…``) every run, a new object ``id`` / memory
address (``0x7fa3...``) in each repr. Comparing those verbatim would make every
attempt look "new" and the machine would never notice it is stuck — "same
signature ≥K times" (v1) never fires (the exact failure this rationale in
``VERIFIED_SWARM_UPGRADE.md`` T1.3 calls out).

This module is the normalizer that feeds that machine. It is intentionally
**pure and stdlib-only**: it takes plain dicts/strings (the pytest-json-report
shape parsed by ``pytest_report.py`` / ``toolchain.parse_results``) and returns
strings/lists. It performs NO file, git, subprocess or pipeline I/O and imports
nothing from the orchestrator — so it is trivially unit-testable and safe to call
from anywhere in the recovery/guard plumbing.

Two signature families live here:

* **Test-failure signatures** — ``normalize_signature`` / ``signatures_from_report``:
  collapse a pytest node id (+ optional exception type) into a stable key with
  all volatile bits (line numbers, temp paths, hex ids/addresses, whitespace,
  path separators) stripped, so the same logical failure yields the same key
  across attempts.

* **Guard-verdict signatures** — the anti-cheating guards (W0.5: test-tamper
  T0.5, scope T0.6, skeleton T0.7, and the flake quarantine T0.8) are *also*
  failure classes the recovery machine reacts to — "cheating is a failure class
  the machine reacts to, not a bypass" (T1.1). ``guard_signature`` mints a stable
  ``guard:<verdict>:<detail>`` key from the module-level verdict constants so a
  recurring tamper/scope/skeleton flag is comparable exactly like a test failure.
"""

from __future__ import annotations

import re

__all__ = [
    "normalize_signature",
    "signatures_from_report",
    "same_failure",
    "guard_signature",
    "TAMPERED",
    "OUT_OF_SCOPE",
    "SKELETON",
    "FLAKE",
]

# --------------------------------------------------------------------------- #
# Guard-verdict constants (W0.5 anti-cheating guards).
#
# These are the failure-class labels the recovery machine (W1) sees alongside
# real test failures. Kept as module-level string constants so every producer
# (the tamper/scope/skeleton/flake guards) and consumer (recovery, scorecard)
# agree on the exact spelling — a typo'd verdict would silently never match.
# --------------------------------------------------------------------------- #

TAMPERED = "tampered"        # T0.5 — dev edited QA-authored test files.
OUT_OF_SCOPE = "out_of_scope"  # T0.6 — diff touched files outside declared claims.
SKELETON = "skeleton"        # T0.7 — pass-only / hardcoded / skip-inserted impl.
FLAKE = "flake"              # T0.8 — check flip-flopped on rerun (not counted, but tracked).


# --------------------------------------------------------------------------- #
# Volatile-substring scrubbers.
#
# Order matters: address/hex ids first (they can sit inside path-looking text),
# then filesystem paths, then trailing ``:<line>`` line numbers, then generic
# standalone numbers, and finally whitespace. Each replaces the volatile bit
# with a fixed placeholder so two runs that differ ONLY in that bit collapse to
# the same key.
# --------------------------------------------------------------------------- #

# 0x7fa3b21c… memory addresses / object ids (case-insensitive).
_RE_ADDR = re.compile(r"0x[0-9a-fA-F]+")
# Bare long hex blobs (e.g. sha/uuid fragments, ``object at deadbeef``): >=8 hex chars.
_RE_HEX = re.compile(r"\b[0-9a-fA-F]{8,}\b")
# Temp/absolute paths: a run of path-ish chars containing a separator. Handles
# POSIX (``/tmp/pytest-of-x/...``) and Windows (``C:\Users\...\Temp\...``). Used
# ONLY on free-text (exception messages, guard details) — NOT on a node id,
# whose ``dir/file.py`` prefix is load-bearing identity, not a volatile path.
_RE_PATH = re.compile(r"[A-Za-z]:[\\/][^\s:]*|/[^\s:]+/[^\s:]*|[^\s:]*[\\/][^\s:]+")
# Trailing ``:123`` (or ``:123:``) line/column markers on a node id / location.
_RE_LINE = re.compile(r":\d+(?=:|$)")
# Any remaining standalone integer (line refs inside messages, sizes, counts).
_RE_NUM = re.compile(r"\b\d+\b")
# Collapse all whitespace runs to nothing (the key is a compact token).
_RE_WS = re.compile(r"\s+")
# Volatile content INSIDE parametrize brackets — e.g. ``test_a[/tmp/x/f]`` or
# ``test_a[0x7f-3]``: strip paths, addresses, hex and numbers between ``[`` and
# ``]`` while keeping the brackets (so a param'd test stays distinct from its
# unparametrized sibling, but two runs with different tmp params collapse).
_RE_BRACKET = re.compile(r"\[[^\]]*\]")


def _scrub_text(text: str) -> str:
    """Aggressively strip volatile substrings from FREE TEXT and lower-case it.

    For exception messages / guard details, where a ``/tmp/...`` path, a memory
    address or a line number is pure noise. NOT for node ids (see ``_scrub_nodeid``).
    """
    if not text:
        return ""
    out = _RE_ADDR.sub("", text)
    out = _RE_HEX.sub("", out)
    out = _RE_PATH.sub("", out)
    out = _RE_LINE.sub("", out)
    out = _RE_NUM.sub("", out)
    out = _RE_WS.sub("", out)
    return out.strip().lower()


def _scrub_bracket(match: re.Match) -> str:
    inner = match.group(0)
    inner = _RE_ADDR.sub("", inner)
    inner = _RE_HEX.sub("", inner)
    inner = _RE_PATH.sub("", inner)
    inner = _RE_NUM.sub("", inner)
    return inner


def _scrub_nodeid(nodeid: str) -> str:
    """Normalize a pytest node id, PRESERVING its ``dir/file.py::test`` skeleton.

    Only the volatile bits are stripped: content inside parametrize brackets
    (tmp paths, addresses, ids, numbers) and any trailing ``:line`` marker.
    Whitespace collapsed, lower-cased. The file-path prefix and ``::`` structure
    are kept — they are the test's identity, not noise.
    """
    if not nodeid:
        return ""
    out = _RE_BRACKET.sub(_scrub_bracket, nodeid)
    out = _RE_LINE.sub("", out)
    out = _RE_WS.sub("", out)
    return out.strip().lower()


def normalize_signature(nodeid: str, exc_type: str = "") -> str:
    """Collapse a pytest node id (+ optional exception type) into a stable key.

    The same logical failure must produce the SAME string across attempts even
    when the run's line numbers, temp paths, memory addresses / hex ids or
    whitespace differ. The node id is kept as the primary identity (which test
    broke) and the exception type refines it (how it broke), both scrubbed of
    volatile bits.

    Examples (all → identical key)::

        normalize_signature("tests/test_x.py::test_a", "AssertionError")
        normalize_signature("tests/test_x.py::test_a", "assertionerror")

    The ``tmp`` path / line-number in a parametrized id or a raw traceback line
    is stripped, so ``test_a[/tmp/pytest-abc/f]`` and ``test_a[/tmp/pytest-xyz/f]``
    collapse together.

    Returns an empty string only when both inputs are empty/blank.
    """
    node = _scrub_nodeid(nodeid or "")
    exc = _scrub_text(exc_type or "")
    if node and exc:
        return f"{node}|{exc}"
    return node or exc


def _extract_exc_type(test: dict) -> str:
    """Best-effort exception type for a failed test from a json-report entry.

    pytest-json-report shapes the failing detail under the ``call`` phase (and
    sometimes ``setup``/``teardown``) with a ``longrepr`` that is either a plain
    traceback string or a structured object carrying ``crash.message`` /
    ``reprcrash.message``. We pull the leading ``SomeError`` token from whatever
    we find. Tolerant of every key being absent — returns "" then.
    """
    longrepr = ""
    for phase in ("call", "setup", "teardown"):
        info = test.get(phase)
        if isinstance(info, dict):
            lr = info.get("longrepr")
            if isinstance(lr, str) and lr.strip():
                longrepr = lr
                break
            if isinstance(lr, dict):
                # Structured longrepr (reprcrash) — prefer its crash message.
                crash = lr.get("reprcrash") or lr.get("crash") or {}
                if isinstance(crash, dict):
                    msg = crash.get("message")
                    if isinstance(msg, str) and msg.strip():
                        longrepr = msg
                        break
    if not longrepr:
        # Some reporters put a top-level ``longrepr`` string on the test entry.
        lr = test.get("longrepr")
        if isinstance(lr, str):
            longrepr = lr
    # The exception type is the leading ``Word.Word...Error`` token of the crash
    # message (e.g. ``AssertionError: assert 1 == 2`` → ``AssertionError``).
    m = re.search(r"\b([A-Za-z_][\w.]*(?:Error|Exception|Warning))\b", longrepr or "")
    return m.group(1) if m else ""


def signatures_from_report(report: dict) -> list[str]:
    """Normalized signatures of the FAILED tests in a pytest-json-report dict.

    ``report`` follows the pytest-json-report shape parsed elsewhere
    (``pytest_report.parse``): a top-level ``"tests"`` list, each entry a dict
    with ``"nodeid"`` and ``"outcome"`` and optional per-phase ``"call"`` info
    carrying a ``"longrepr"``. Only ``failed``/``error`` outcomes contribute.

    The result is **de-duplicated and order-preserving** (first occurrence wins):
    two failed tests → two signatures; a repeated logical failure → one. Fully
    tolerant of a missing/partial/corrupt report — returns ``[]`` for anything
    that is not a dict with a ``tests`` list, and skips malformed entries.
    """
    if not isinstance(report, dict):
        return []
    tests = report.get("tests")
    if not isinstance(tests, list):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for test in tests:
        if not isinstance(test, dict):
            continue
        if test.get("outcome") not in ("failed", "error"):
            continue
        nodeid = test.get("nodeid")
        if not nodeid:
            continue
        sig = normalize_signature(str(nodeid), _extract_exc_type(test))
        if sig and sig not in seen:
            seen.add(sig)
            out.append(sig)
    return out


def same_failure(a: list[str], b: list[str]) -> bool:
    """True if two signature sets overlap — the "recurring failure" test.

    The recovery machine calls this to decide whether the current attempt failed
    the *same way* as a prior one (share at least one signature). Empty on either
    side means "nothing to compare" → not a recurrence (``False``).
    """
    if not a or not b:
        return False
    return not set(a).isdisjoint(b)


def guard_signature(verdict: str, detail: str = "") -> str:
    """Stable ``guard:<verdict>:<detail>`` key for an anti-cheating guard verdict.

    The W0.5 guards (tamper/scope/skeleton/flake) surface failures the recovery
    machine treats as a failure class alongside real test failures. This mints a
    signature comparable to ``normalize_signature`` output — a recurring
    ``tampered`` on the same file, say, is as detectable as a recurring test
    failure. ``detail`` (e.g. the offending path) is scrubbed of volatile bits so
    it stays stable across attempts; it is optional.

    Examples::

        guard_signature(TAMPERED)                       -> "guard:tampered:"
        guard_signature(OUT_OF_SCOPE, "src/other.py")   -> "guard:out_of_scope:src/other.py"
    """
    v = _scrub_text(verdict or "")
    # Preserve path separators in the detail (they carry identity) but strip the
    # volatile bits and whitespace; keep it lower-cased for stable comparison.
    d = _RE_WS.sub("", (detail or "").strip()).lower()
    d = _RE_ADDR.sub("", d)
    d = _RE_HEX.sub("", d)
    d = _RE_LINE.sub("", d)
    d = _RE_NUM.sub("", d)
    return f"guard:{v}:{d}"
