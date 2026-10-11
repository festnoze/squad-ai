"""REM-06: evidence admission against a supervisor-owned critical baseline.

No semantic assertion-strength guesswork: any critical checker/support edit
needs an exact-hash independent review. Expected IDs come from actual trusted
collection, not from scanning arbitrary source. Exit zero alone is insufficient.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .dependencies import atomic_json, contained_path


@dataclass(frozen=True)
class TestBaseline:
    files: dict[str, str]
    expected_test_ids: tuple[str, ...]
    version: int = 1

    @property
    def digest(self):
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()


def capture_baseline(root: Path, paths: list[str], expected_test_ids: list[str]) -> TestBaseline:
    """Call BEFORE product work, using supervisor collection IDs.

    Include critical conftests/helpers/config in paths, not only test modules.
    A baseline with no expected tests is never an admissible acceptance oracle.
    """
    if not paths or not expected_test_ids or len(set(expected_test_ids)) != len(expected_test_ids):
        raise ValueError("critical paths and unique collected test IDs required")
    files = {p: hashlib.sha256(contained_path(Path(root), p).read_bytes()).hexdigest() for p in paths}
    return TestBaseline(files, tuple(sorted(expected_test_ids)))


def save_baseline(baseline: TestBaseline, oracle_path: Path, producer_root: Path) -> None:
    if Path(oracle_path).resolve().is_relative_to(Path(producer_root).resolve()):
        raise ValueError("oracle must be outside producer writable root")
    atomic_json(Path(oracle_path), asdict(baseline))


def load_baseline(path: Path) -> TestBaseline:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    baseline = TestBaseline(data["files"], tuple(data["expected_test_ids"]), data["version"])
    if baseline.version != 1 or not baseline.files or not baseline.expected_test_ids:
        raise ValueError("invalid/empty test baseline")
    return baseline


@dataclass(frozen=True)
class SkipAllowance:
    test_id: str
    reason: str
    reviewed_by: str
    outcome: str = "skipped"
    platform: str = ""


@dataclass(frozen=True)
class ChangeApproval:
    path: str
    old_sha256: str
    new_sha256: str
    reason: str
    reviewed_by: str


@dataclass(frozen=True)
class SuiteEvidence:
    outcomes: dict[str, str]
    collected: int
    exit_code: int
    collection_errors: tuple[str, ...] = ()
    collection_skips: tuple[str, ...] = ()
    reasons: dict[str, str] = field(default_factory=dict)
    report_valid: bool = True
    executed: int | None = None

    @property
    def counts(self) -> dict[str, int]:
        names = ("passed", "failed", "error", "skipped", "xfailed", "xpassed")
        executed = self.executed if self.executed is not None else sum(v in ("passed", "failed", "xfailed", "xpassed") for v in self.outcomes.values())
        return {"collected": self.collected, "reported": len(self.outcomes), "executed": executed, **{n: sum(v == n for v in self.outcomes.values()) for n in names}, "collection_skips": len(self.collection_skips), "collection_errors": len(self.collection_errors)}


def _skip_reason(test: dict) -> str:
    parts = []
    for phase in ("setup", "call", "teardown"):
        value = test.get(phase, {}).get("longrepr", "")
        if value:
            parts.append(str(value))
    return "\n".join(parts)


def pytest_evidence(report_path: Path | str, exit_code: int) -> SuiteEvidence:
    try:
        data = json.loads(Path(report_path).read_text(encoding="utf-8"))
        tests, collectors = data.get("tests"), data.get("collectors", [])
        if not isinstance(tests, list) or not isinstance(collectors, list) or not isinstance(data.get("summary"), dict):
            raise ValueError("missing report fields")
        outcomes, reasons = {}, {}
        for test in tests:
            node, outcome = test["nodeid"], test["outcome"]
            if node in outcomes:
                raise ValueError("duplicate reported test id")
            outcomes[node] = outcome
            reasons[node] = _skip_reason(test)
        errors = tuple(str(c.get("nodeid", "")) for c in collectors if c.get("outcome") == "failed")
        skips = tuple(str(c.get("nodeid", "")) for c in collectors if c.get("outcome") == "skipped")
        collected = data["summary"].get("collected")
        if not isinstance(collected, int) or collected < 0:
            raise ValueError("collected count missing")
        executed = sum(isinstance(test.get("call"), dict) for test in tests)
        return SuiteEvidence(outcomes, collected, exit_code, errors, skips, reasons, executed=executed)
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return SuiteEvidence({}, 0, exit_code, report_valid=False)


def tap_evidence(stdout: str, exit_code: int) -> SuiteEvidence:
    """Node's TAP terminal test records, retaining SKIP/TODO rather than PASS."""
    outcomes, reasons = {}, {}
    duplicate = False
    for match in re.finditer(r"^\s*(not )?ok\s+\d+\s+-\s+(.*?)(?:\s+#\s*(SKIP|TODO)\b\s*(.*))?$", stdout, re.MULTILINE | re.IGNORECASE):
        name, directive = match.group(2).strip(), (match.group(3) or "").upper()
        outcome = "skipped" if directive == "SKIP" else "xfailed" if directive == "TODO" else "failed" if match.group(1) else "passed"
        duplicate |= name in outcomes
        outcomes[name] = outcome
        reasons[name] = match.group(4) or ""
    counts = re.findall(r"^# tests\s+(\d+)\s*$", stdout, re.MULTILINE)
    collected = int(counts[-1]) if counts else len(outcomes)
    return SuiteEvidence(outcomes, collected, exit_code, reasons=reasons, report_valid=bool(outcomes) and not duplicate)


def vitest_evidence(report_path: str | Path, exit_code: int) -> SuiteEvidence:
    try:
        data = json.loads(Path(report_path).read_text(encoding="utf-8"))
        outcomes = {}
        errors = []
        for file in data["testResults"]:
            name = file.get("name") or file.get("testFilePath") or ""
            assertions = file.get("assertionResults", [])
            if file.get("status") == "failed" and not assertions:
                errors.append(name)
            for test in assertions:
                title = " > ".join(p for p in [*test.get("ancestorTitles", []), test.get("title", "")] if p) or test.get("fullName") or "test"
                node = f"{name}::{title}" if name else title
                if node in outcomes:
                    raise ValueError("duplicate test id")
                outcomes[node] = {"pending": "skipped", "todo": "skipped"}.get(test["status"], test["status"])
        collected = data.get("numTotalTests")
        if not isinstance(collected, int):
            raise ValueError("collected count missing")
        return SuiteEvidence(outcomes, collected, exit_code, tuple(errors))
    except (OSError, ValueError, TypeError, KeyError):
        return SuiteEvidence({}, 0, exit_code, report_valid=False)


@dataclass(frozen=True)
class IntegrityResult:
    status: str
    findings: tuple[str, ...]
    counts: dict[str, int]
    baseline_hash: str

    @property
    def green(self):
        return self.status == "pass"


def evaluate_run(baseline: TestBaseline, root: Path, evidence: SuiteEvidence, *, allowances: tuple[SkipAllowance, ...] = (), approvals: tuple[ChangeApproval, ...] = (), platform: str = "") -> IntegrityResult:
    findings = []
    if baseline.version != 1 or not baseline.files or not baseline.expected_test_ids:
        findings.append("BASELINE_INVALID")
    for path, expected in baseline.files.items():
        try:
            actual = hashlib.sha256(contained_path(Path(root), path).read_bytes()).hexdigest()
        except (OSError, RuntimeError):
            findings.append(f"CRITICAL_TEST_REMOVED: {path}")
            continue
        if actual != expected and not any(a.path == path and a.old_sha256 == expected and a.new_sha256 == actual and a.reason.strip() and a.reviewed_by.strip() for a in approvals):
            findings.append(f"CRITICAL_TEST_CHANGED_UNREVIEWED: {path}")
    if not evidence.report_valid:
        findings.append("TEST_REPORT_INVALID")
    if evidence.exit_code:
        findings.append(f"TEST_COMMAND_FAILED: {evidence.exit_code}")
    if evidence.collected == 0 or not evidence.outcomes:
        findings.append("ZERO_TESTS")
    if evidence.collected != len(evidence.outcomes):
        findings.append("REPORT_COUNT_MISMATCH")
    if evidence.collection_errors:
        findings.append("COLLECTION_ERRORS: " + ", ".join(evidence.collection_errors))
    # A module-level importorskip can prevent all critical IDs appearing. A
    # platform exception must identify the exact absent ID AND collector path.
    missing = set(baseline.expected_test_ids) - evidence.outcomes.keys()
    for test_id in sorted(missing):
        findings.append(f"CRITICAL_TEST_NOT_COLLECTED: {test_id}")
    for test_id, outcome in evidence.outcomes.items():
        if outcome == "passed":
            continue
        permitted = outcome in ("skipped", "xfailed") and any(a.test_id == test_id and a.outcome == outcome and a.reason.strip() and a.reviewed_by.strip() and (not a.platform or a.platform == platform) and a.reason in evidence.reasons.get(test_id, "") for a in allowances)
        if not permitted:
            findings.append(f"TEST_OUTCOME_NOT_PERMITTED: {test_id}={outcome}")
    # Collection skips are never accepted implicitly, even for native suites.
    # Put a legitimate platform skip inside a collected test with an allowance.
    if evidence.collection_skips:
        findings.append("COLLECTION_SKIPS_UNREVIEWED: " + ", ".join(evidence.collection_skips))
    return IntegrityResult("fail" if findings else "pass", tuple(findings), evidence.counts, baseline.digest)
