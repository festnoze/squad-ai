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

# ST-6: the frontend toolchain (React+Vite+TS+Vitest) lives alongside the
# backend languages but is NOT a backend language — it is selected per stream
# (``Stream.language`` == "react"/"frontend"). ``normalize`` keeps mapping only
# backend languages (so the backend path is byte-identical); the frontend path
# is reached explicitly via ``is_frontend`` / the ``"frontend"`` key.
_FRONTEND_KEYS = ("frontend", "react", "vite", "ts", "typescript")


def normalize(language: str | None) -> str:
    lang = (language or "python").strip().lower()
    return lang if lang in SUPPORTED else "python"


def is_frontend(language: str | None) -> bool:
    """Whether ``language`` designates the React/Vite/Vitest frontend toolchain
    (ST-6). Kept separate from ``normalize`` so the backend dispatch is
    unchanged when streams are off."""
    return (language or "").strip().lower() in _FRONTEND_KEYS


def needs_report_file(language: str) -> bool:
    """Only the Python (pytest-json-report) path writes outcomes to a file; Go,
    Rust and the frontend (Vitest) are parsed from stdout."""
    return normalize(language) == "python"


def test_command(language: str, report_path: str) -> list[str]:
    """The subprocess argv to run the test suite for ``language``."""
    if is_frontend(language):
        return frontend_test_command(report_path)
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


def run_command(language: str, args: list[str] | None = None) -> list[str]:
    """The subprocess argv to launch the generated app for ``language``, with
    optional CLI ``args`` forwarded to the app (e.g. a subcommand). Cargo needs
    a ``--`` separator before program args."""
    if is_frontend(language):
        return frontend_run_command(args)
    lang = normalize(language)
    extra = list(args or [])
    if lang == "go":
        return [settings.go_cmd, "run", ".", *extra]
    if lang == "rust":
        return [settings.cargo_cmd, "run", "-q", *(["--", *extra] if extra else [])]
    return [settings.uv_cmd, "run", "python", "main.py", *extra]


def parse_results(language: str, stdout: str, report_path: str) -> dict[str, str]:
    """Map a finished test run to ``{test_id: outcome}`` (pytest vocabulary:
    ``passed``/``failed``/``error``/``skipped``)."""
    if is_frontend(language):
        return parse_frontend_results(stdout, report_path)
    lang = normalize(language)
    if lang == "go":
        return _parse_go(stdout)
    if lang == "rust":
        return _parse_rust(stdout)
    return pytest_report.parse(report_path)


# --------------------------------------------------------- Frontend (ST-6)
#
# The frontend stream (React + Vite + TypeScript + Vitest) keeps the same
# toolchain API as the backend languages: a *test command* (Vitest JSON
# reporter), a *build command* (``tsc && vite build``) whose success is part of
# "green", a *run command* (``vite preview`` for ST-8) and a *parser* mapping
# the Vitest JSON to per-test outcomes. The Vitest JSON report is written to a
# file (``--outputFile``) like pytest-json-report, so the run is robust to noise
# on stdout (build warnings, deprecation notices…).


def frontend_test_command(report_path: str) -> list[str]:
    """``vitest run`` with the JSON reporter writing to ``report_path`` (ST-6).

    ``npm exec`` runs the project-local Vitest binary; ``run`` forces a single
    non-watch pass. The JSON report is parsed by ``_parse_vitest``."""
    return [
        settings.npm_cmd, "exec", "--", "vitest", "run",
        "--reporter=json", f"--outputFile={report_path}",
    ]


def frontend_build_command() -> list[str]:
    """The frontend production build: ``tsc && vite build`` (ST-6).

    Run as a single npm script so the type-check (``tsc``) gates the bundler
    (``vite build``) — both must succeed for the stream to be "green". The
    scaffold wires this to the ``build`` script in package.json."""
    return [settings.npm_cmd, "run", "build"]


def frontend_run_command(args: list[str] | None = None) -> list[str]:
    """Launch the built frontend for preview (ST-8): ``vite preview`` (serves
    the production build). Extra ``args`` (e.g. ``--port 5050``) are forwarded
    after an npm ``--`` separator."""
    extra = list(args or [])
    return [settings.npm_cmd, "run", "preview", *(["--", *extra] if extra else [])]


def parse_frontend_results(stdout: str, report_path: str) -> dict[str, str]:
    """Map a finished frontend run to ``{test_id: outcome}`` (ST-6).

    Prefers the Vitest JSON report file; falls back to parsing ``stdout`` when
    it carries the JSON (e.g. ``--reporter=json`` without an output file). A
    build failure leaves no test report — the caller's suite-green flag (exit
    code) still catches it, and ``build_errors`` surfaces the message for
    refinement."""
    payload = ""
    if report_path:
        try:
            with open(report_path, encoding="utf-8") as fh:
                payload = fh.read()
        except OSError:
            payload = ""
    return _parse_vitest(payload or stdout)


def _parse_vitest(text: str) -> dict[str, str]:
    """Parse a Vitest JSON report into ``{test_id: outcome}``.

    Vitest's JSON reporter mirrors Jest: a top-level ``testResults`` list, one
    entry per test FILE, each carrying ``assertionResults`` with a per-test
    ``status`` (``passed``/``failed``/``pending``/``skipped``/``todo``) and an
    ``ancestorTitles`` + ``title`` we join into a stable id. Non-JSON / empty
    input yields ``{}`` (a failed build prints no report)."""
    text = (text or "").strip()
    if not text or not text.startswith("{"):
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {}
    mapping = {
        "passed": "passed",
        "failed": "failed",
        "pending": "skipped",
        "skipped": "skipped",
        "todo": "skipped",
    }
    out: dict[str, str] = {}
    for file_res in data.get("testResults") or []:
        file_name = file_res.get("name") or file_res.get("testFilePath") or ""
        for assertion in file_res.get("assertionResults") or []:
            title_parts = [*(assertion.get("ancestorTitles") or []), assertion.get("title") or ""]
            name = " > ".join(p for p in title_parts if p) or assertion.get("fullName") or "test"
            node = f"{file_name}::{name}" if file_name else name
            out[node] = mapping.get(assertion.get("status"), "failed")
    return out


def parse_build_errors(stdout: str) -> str:
    """Extract the salient build/type-check errors from a frontend build run
    (ST-6), to feed the dev refinement loop. Keeps lines that look like a TS or
    Vite error; falls back to the tail of the output."""
    lines = [ln for ln in (stdout or "").splitlines() if ln.strip()]
    errs = [
        ln for ln in lines
        if re.search(r"\berror\b", ln, re.IGNORECASE)
        or re.search(r"\bTS\d{3,5}\b", ln)
        or "✗" in ln
    ]
    picked = errs or lines[-20:]
    return "\n".join(picked[-40:])


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
