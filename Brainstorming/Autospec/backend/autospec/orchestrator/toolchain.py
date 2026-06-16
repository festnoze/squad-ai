"""L2g: per-language build/test toolchain abstraction.

Autospec's red→green loop is language-agnostic above this module: it asks for the
*test command* to run and a *parser* that maps the run to per-test outcomes
(``{test_id: "passed"|"failed"|...}``) and a suite-green boolean. Python keeps the
pytest-json-report flow; Go uses ``go test -json``; Rust parses ``cargo test``
text output. The actual subprocess run + the demo short-circuit stay in the
pipeline; this module is pure (command building + output parsing), so it is fully
unit-testable without invoking a real compiler.
"""

from __future__ import annotations

import json
import re

from ..config import settings
from . import pytest_report

SUPPORTED = ("python", "go", "rust")


def normalize(language: str | None) -> str:
    lang = (language or "python").strip().lower()
    return lang if lang in SUPPORTED else "python"


def needs_report_file(language: str) -> bool:
    """Only the Python (pytest-json-report) path writes outcomes to a file; Go
    and Rust are parsed from stdout."""
    return normalize(language) == "python"


def test_command(language: str, report_path: str) -> list[str]:
    """The subprocess argv to run the test suite for ``language``."""
    lang = normalize(language)
    if lang == "go":
        # JSON event stream — one object per line, robust to parse.
        return [settings.go_cmd, "test", "./...", "-json"]
    if lang == "rust":
        # --no-fail-fast: report every test, not just up to the first failure.
        return [settings.cargo_cmd, "test", "--no-fail-fast", "-q"]
    return [
        settings.uv_cmd, "run", "pytest", "-q",
        "--json-report", f"--json-report-file={report_path}",
    ]


def run_command(language: str) -> list[str]:
    """The subprocess argv to launch the generated app for ``language``."""
    lang = normalize(language)
    if lang == "go":
        return [settings.go_cmd, "run", "."]
    if lang == "rust":
        return [settings.cargo_cmd, "run", "-q"]
    return [settings.uv_cmd, "run", "python", "main.py"]


def parse_results(language: str, stdout: str, report_path: str) -> dict[str, str]:
    """Map a finished test run to ``{test_id: outcome}`` (pytest vocabulary:
    ``passed``/``failed``/``error``/``skipped``)."""
    lang = normalize(language)
    if lang == "go":
        return _parse_go(stdout)
    if lang == "rust":
        return _parse_rust(stdout)
    return pytest_report.parse(report_path)


# ----------------------------------------------------------------- Go parsing

def _parse_go(stdout: str) -> dict[str, str]:
    """Parse ``go test -json``: one JSON event per line. We keep the terminal
    action (pass/fail/skip) per ``Package.Test`` id. Lines that aren't JSON
    (build errors, plain logs) are ignored — the suite-green flag (exit code)
    still catches a failed build."""
    out: dict[str, str] = {}
    mapping = {"pass": "passed", "fail": "failed", "skip": "skipped"}
    for line in stdout.splitlines():
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        action = ev.get("Action")
        test = ev.get("Test")
        if not test or action not in mapping:
            continue
        node = f"{ev.get('Package', '')}::{test}" if ev.get("Package") else test
        out[node] = mapping[action]
    return out


# --------------------------------------------------------------- Rust parsing

# Lines like: `test tests::adds_two ... ok` / `test foo::bar ... FAILED`.
_RUST_TEST_RE = re.compile(r"^test\s+(?P<name>\S+)\s+\.\.\.\s+(?P<res>ok|FAILED|ignored)\b")
_RUST_RESULT = {"ok": "passed", "FAILED": "failed", "ignored": "skipped"}


def _parse_rust(stdout: str) -> dict[str, str]:
    """Parse ``cargo test`` text output: collect each ``test <name> ... ok/FAILED``
    line. (Cargo prints these for unit, integration and doc tests.)"""
    out: dict[str, str] = {}
    for line in stdout.splitlines():
        m = _RUST_TEST_RE.match(line.strip())
        if m:
            out[m.group("name")] = _RUST_RESULT[m.group("res")]
    return out
