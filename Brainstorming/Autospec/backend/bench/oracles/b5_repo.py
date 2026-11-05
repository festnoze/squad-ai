"""B5 checks on the product's own suites and files: TST-01, TST-03, TST-04, ARC-04, OPS-06.

- TST-01 and OPS-06 read the M5 run of the bench (`product.suite`, `product.timings`, set by
  bench.oracle.judge before the oracle runs).
- TST-03 and TST-04 come from one more run of the backend suite, measured with the coverage
  tool of the product's locked environment (pytest-cov or coverage: the bench never installs
  one), with RELAIS_DB and the working directory's relais.db pointing to sentinel "user"
  databases, and with its temporary directory watched for SQLite files. The frontend part of
  TST-03 runs Vitest with the coverage provider the product declares.
- ARC-04 reads the schema version markers of the SQLite base the API phases use, always from
  a copy: the product's files are never opened for writing.

What each check leaves to a reviewer is listed in bench/oracles/B5_COVERAGE.md.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import sqlite3
import threading
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from bench import proc
from bench.oracle import Product, npm_command
from bench.oracles.B5 import World, expect

TESTS_BUDGET_S = 120.0  # OPS-06: tests outside the browser in under 2 min after installation
BACKEND_LINES, BACKEND_BRANCHES, FRONTEND_LINES = 80.0, 70.0, 70.0  # TST-03 thresholds, in %
SQLITE_NAMES = re.compile(r"\.(db|sqlite3?)$|-(wal|journal)$", re.I)
VERSION_TABLE = re.compile(r"version|migration", re.I)
PROVIDERS = ("v8", "istanbul")


# --------------------------------------------------------------------------- TST-01, OPS-06


def tst_01(w: World) -> str:
    """Both layers ran in the clean environment, collected tests, passed, and skip nothing."""
    suite = w.product.suite
    expect(suite, "the product's own suites were not run")
    backend, frontend = suite.get("backend") or {}, suite.get("frontend") or {}
    expect(backend.get("passed", 0) > 0, "backend: no test collected and passed (zero tests is a FAIL)")
    expect(backend.get("green"), f"backend: suite not green ({backend.get('failed', 0)} failed or in error)")
    expect(frontend.get("passed", 0) > 0, "frontend: no Vitest test collected and passed")
    expect(frontend.get("green"), f"frontend: suite not green ({frontend.get('failed', 0)} failed)")
    masked = {name: count for name, count in (("backend skipped", backend.get("skipped", 0)),
                                              ("backend xfailed", backend.get("xfailed", 0)),
                                              ("frontend skipped", frontend.get("skipped", 0))) if count}
    expect(not masked, f"skipped or xfailed tests, whose criticality needs a review: {masked}")
    return f"backend {backend['passed']} passed, frontend {frontend['passed']} passed, no skip or xfail"


def ops_06(w: World) -> str:
    """Diagnostic: the bench's own durations, tests outside the browser under 2 min."""
    timings = w.product.timings
    expect("pytest" in timings, "the product's suites were not run")
    tests = timings.get("pytest", 0.0) + timings.get("npm test", 0.0)
    machine = f"{platform.system()} {platform.release()} {platform.machine()}, {os.cpu_count()} CPU"
    steps = ", ".join(f"{name} {seconds:.0f} s" for name, seconds in timings.items())
    detail = f"tests outside the browser {tests:.0f} s; {steps}; {machine}"
    expect(tests < TESTS_BUDGET_S, f"{detail} (target under {TESTS_BUDGET_S:.0f} s)")
    return detail


# --------------------------------------------------------------------------- TST-03, TST-04


@dataclass
class SuiteProbe:
    """One instrumented run of the backend suite (TST-03 backend part, TST-04)."""

    tool: str = ""  # "pytest-cov", "coverage", or "" when the environment has none
    returncode: int | None = None
    totals: dict = field(default_factory=dict)  # coverage.py JSON totals
    omitted: list[str] = field(default_factory=list)  # the product's own coverage omit patterns
    touched: list[str] = field(default_factory=list)  # sentinel user databases the suite changed
    temp_sqlite: int = 0  # SQLite files seen in the suite's temporary directory
    output: str = ""


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "missing"


def _sentinel(path: Path) -> str:
    """A small real SQLite base standing for a user's database; returns its digest."""
    path.parent.mkdir(parents=True, exist_ok=True)
    for suffix in ("", "-wal", "-shm", "-journal"):
        Path(f"{path}{suffix}").unlink(missing_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE oracle_sentinel (note TEXT)")
        conn.execute("INSERT INTO oracle_sentinel VALUES ('base utilisateur : ne pas toucher')")
        conn.commit()
    finally:
        conn.close()
    return _digest(path)


class _Watcher(threading.Thread):
    """Polls a directory for SQLite files by name only: opening them could block a test's cleanup."""

    def __init__(self, root: Path) -> None:
        super().__init__(daemon=True)
        self.root, self.found = root, set()
        self.stopped = threading.Event()

    def run(self) -> None:
        while not self.stopped.wait(0.2):
            self.scan()
        self.scan()

    def scan(self) -> None:
        try:
            self.found |= {str(p) for p in self.root.rglob("*") if SQLITE_NAMES.search(p.name)}
        except OSError:  # a directory removed while it was listed
            pass


def _omitted(root: Path) -> list[str]:
    try:
        data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return []
    return [str(p) for p in data.get("tool", {}).get("coverage", {}).get("run", {}).get("omit", [])]


def probe_suite(product: Product, work: Path) -> SuiteProbe:
    """Run the backend suite once more: with coverage when the environment has a tool for it,
    RELAIS_DB and ./relais.db on sentinel user bases, TMP watched for SQLite files."""
    probe = SuiteProbe(omitted=_omitted(product.dir))
    if not product.sync_ok:
        probe.output = "environment not built"
        return probe
    for tool, module in (("pytest-cov", "pytest_cov"), ("coverage", "coverage")):
        if product.run(["-c", f"import {module}"], timeout_s=60).returncode == 0:
            probe.tool = tool
            break
    report = work / "coverage.json"
    user_db, cwd_db = work / "user-data" / "relais.db", product.dir / "relais.db"
    sentinels = {"RELAIS_DB": (user_db, _sentinel(user_db)), "./relais.db": (cwd_db, _sentinel(cwd_db))}
    temp = work / "suite-tmp"
    temp.mkdir(parents=True, exist_ok=True)
    env = product.env(RELAIS_DB=str(user_db), TMP=str(temp), TEMP=str(temp), TMPDIR=str(temp))
    pytest = ["-m", "pytest", "-q", "-p", "no:cacheprovider"]
    if probe.tool == "pytest-cov":
        argv = [*pytest, f"--cov={product.package}", "--cov-branch", f"--cov-report=json:{report}"]
    elif probe.tool == "coverage":
        argv = ["-m", "coverage", "run", "--branch", f"--source={product.package}", *pytest]
    else:
        argv = pytest
    watcher = _Watcher(temp)
    watcher.start()
    try:
        result = product.run(argv, env=env, timeout_s=900)
        if probe.tool == "coverage":
            product.run(["-m", "coverage", "json", "-o", str(report)], env=env, timeout_s=120)
    finally:
        watcher.stopped.set()
        watcher.join(timeout=10)
    probe.returncode, probe.output = result.returncode, proc.tail(result.stdout + result.stderr, 600)
    probe.touched = [name for name, (path, digest) in sentinels.items() if _digest(path) != digest]
    probe.temp_sqlite = len(watcher.found)
    if report.is_file():
        try:
            probe.totals = json.loads(report.read_text(encoding="utf-8")).get("totals", {})
        except ValueError:
            pass
    for suffix in ("", "-wal", "-shm", "-journal"):  # the copy goes back to how the bench found it
        Path(f"{cwd_db}{suffix}").unlink(missing_ok=True)
    return probe


def frontend_coverage(product: Product, out: Path) -> tuple[str, dict]:
    """(provider, totals) of Vitest measured with the coverage provider the product installs.

    Every source file under src/ counts, executed or not (test files are left out by Vitest).
    """
    modules = product.frontend_dir / "node_modules" / "@vitest"
    provider = next((p for p in PROVIDERS if (modules / f"coverage-{p}").is_dir()), "")
    if not provider:
        return "", {}
    argv = [npm_command(), "exec", "--no", "--", "vitest", "run", "--coverage.enabled=true",
            f"--coverage.provider={provider}", "--coverage.reporter=json-summary",
            f"--coverage.reportsDirectory={out}", "--coverage.include=src/**/*.{ts,tsx,js,jsx}"]
    result = proc.run(argv, cwd=product.frontend_dir, env=product.env(CI="1", NO_COLOR="1"), timeout_s=900)
    summary = out / "coverage-summary.json"
    if not summary.is_file():
        return provider, {"error": proc.tail(result.stdout + result.stderr, 400)}
    return provider, json.loads(summary.read_text(encoding="utf-8")).get("total", {})


def _pct(covered: int, total: int) -> float:
    return 100.0 * covered / total if total else 0.0


def tst_03(w: World) -> str:
    """Backend lines and branches, frontend lines, with the product's own tools and every file."""
    probe: SuiteProbe | None = w.facts.get("suite_probe")
    expect(probe is not None, "the backend suite was not run")
    expect(probe.tool, "no coverage tool (pytest-cov or coverage) in the product's locked environment")
    totals = probe.totals
    expect(totals.get("num_statements"), f"no coverage report from {probe.tool}: {probe.output[-300:]}")
    lines = _pct(totals.get("covered_lines", 0), totals["num_statements"])
    expect(totals.get("num_branches"), "backend branch coverage not measured")
    branches = _pct(totals.get("covered_branches", 0), totals["num_branches"])
    backend = (f"backend {lines:.1f} % lines ({totals.get('covered_lines')}/{totals['num_statements']}), "
               f"{branches:.1f} % branches ({totals.get('covered_branches')}/{totals['num_branches']})"
               + (f", omit {probe.omitted}" if probe.omitted else ""))
    expect(lines >= BACKEND_LINES and branches >= BACKEND_BRANCHES,
           f"{backend}: below {BACKEND_LINES:.0f} % lines or {BACKEND_BRANCHES:.0f} % branches")
    product = w.product
    expect(product.frontend_ok, "frontend not installed and built from its lock")
    provider, front = frontend_coverage(product, w.db.parent / "frontend-coverage")
    expect(provider, f"{backend}; frontend: no coverage provider (@vitest/coverage-v8 or -istanbul) installed")
    expect("error" not in front, f"{backend}; frontend coverage failed: {front.get('error', '')}")
    covered, total = front.get("lines", {}).get("covered", 0), front.get("lines", {}).get("total", 0)
    frontend = f"frontend {_pct(covered, total):.1f} % lines ({covered}/{total})"
    expect(total and _pct(covered, total) >= FRONTEND_LINES,
           f"{backend}; {frontend}: below {FRONTEND_LINES:.0f} % lines")
    return f"{backend}; {frontend}"


def tst_04(w: World) -> str:
    """The suite leaves user databases alone and works on SQLite files in a temporary place."""
    probe: SuiteProbe | None = w.facts.get("suite_probe")
    expect(probe is not None and probe.returncode is not None, "the backend suite was not run")
    expect(not probe.touched, f"the product's suite modified a user database: {probe.touched}")
    expect(probe.temp_sqlite, "no SQLite file appeared in the suite's temporary directory "
           "(tests not run on a real SQLite file in a temporary place)")
    return f"{probe.temp_sqlite} SQLite files in the suite's temporary directory, user databases untouched"


# --------------------------------------------------------------------------- ARC-04


def schema_markers(db: Path, scratch: Path) -> dict:
    """PRAGMA user_version and the rows of the version or migration tables of a SQLite base.

    Read from a copy (base and journals), so the product's own files stay untouched.
    """
    if not db.is_file():
        return {"error": f"{db.name} was not created"}
    scratch.mkdir(parents=True, exist_ok=True)
    copy = scratch / db.name
    try:
        for suffix in ("", "-wal", "-journal"):
            if Path(f"{db}{suffix}").is_file():
                shutil.copyfile(f"{db}{suffix}", f"{copy}{suffix}")
        conn = sqlite3.connect(copy)
    except (OSError, sqlite3.Error) as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}
    try:
        tables: dict[str, list[str]] = {}
        names = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name").fetchall()
        for (name,) in names:
            if VERSION_TABLE.search(name):
                quoted = name.replace('"', '""')
                tables[name] = sorted(repr(row) for row in conn.execute(f'SELECT * FROM "{quoted}"'))[:50]
        return {"user_version": conn.execute("PRAGMA user_version").fetchone()[0], "tables": tables}
    except sqlite3.Error as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}
    finally:
        conn.close()


def _versioned(markers: dict) -> bool:
    return markers.get("user_version", 0) > 0 or any(markers.get("tables", {}).values())


def _describe(markers: dict) -> str:
    if "error" in markers:
        return markers["error"]
    tables = {name: len(rows) for name, rows in markers.get("tables", {}).items()}
    return f"user_version={markers.get('user_version')}, version tables {tables or 'none'}"


def arc_04(schema: dict[str, dict], persisted: str) -> str:
    """A versioned schema on a blank base, kept as is when the server restarts on populated data."""
    blank, populated, restarted = (schema.get(k, {"error": "not measured"}) for k in ("blank", "populated", "restarted"))
    expect(_versioned(blank), f"the blank base migrated by create-admin shows no schema version ({_describe(blank)})")
    expect(_versioned(populated), f"the populated base shows no schema version ({_describe(populated)})")
    expect(not persisted, f"data not kept across the restart (OPS-04): {persisted}")
    expect(populated == restarted, f"the schema version changed when the server restarted on the populated base: "
           f"{_describe(populated)} -> {_describe(restarted)}")
    return f"{_describe(populated)}, unchanged by a restart on the populated base"
