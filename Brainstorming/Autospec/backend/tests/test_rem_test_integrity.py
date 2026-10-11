import hashlib
import json
import subprocess
import sys

import pytest

from autospec.orchestrator import constitution, toolchain
from autospec.orchestrator.test_integrity import ChangeApproval, SkipAllowance, SuiteEvidence, capture_baseline, evaluate_run, load_baseline, pytest_evidence, save_baseline, tap_evidence, vitest_evidence


def baseline(tmp_path):
    source = tmp_path / "test_critical.py"
    source.write_text("def test_hash():\n    assert 1 == 1\n", encoding="utf-8")
    return capture_baseline(tmp_path, ["test_critical.py"], ["test_critical.py::test_hash"])


def test_green_requires_actual_critical_collection(tmp_path):
    b = baseline(tmp_path)
    passed = SuiteEvidence({"test_critical.py::test_hash": "passed"}, 1, 0)
    assert evaluate_run(b, tmp_path, passed).green
    assert not evaluate_run(b, tmp_path, SuiteEvidence({}, 0, 0)).green
    assert not evaluate_run(b, tmp_path, SuiteEvidence({"test_else.py::test_fake": "passed"}, 1, 0)).green
    assert not evaluate_run(b, tmp_path, SuiteEvidence(passed.outcomes, 1, 0, report_valid=False)).green
    assert not evaluate_run(b, tmp_path, SuiteEvidence(passed.outcomes, 100, 0)).green


@pytest.mark.parametrize("outcome", ["skipped", "xfailed", "xpassed", "failed", "error"])
def test_critical_nonpass_never_green_by_default(tmp_path, outcome):
    b = baseline(tmp_path)
    result = evaluate_run(b, tmp_path, SuiteEvidence({"test_critical.py::test_hash": outcome}, 1, 0))
    assert not result.green
    assert result.counts[outcome] == 1


def test_explicit_reviewed_platform_skip_is_allowed(tmp_path):
    b = baseline(tmp_path)
    evidence = SuiteEvidence({"test_critical.py::test_hash": "skipped"}, 1, 0, reasons={"test_critical.py::test_hash": "Windows-only primitive"})
    allow = SkipAllowance("test_critical.py::test_hash", "Windows-only primitive", "independent reviewer", platform="linux")
    assert evaluate_run(b, tmp_path, evidence, allowances=(allow,), platform="linux").green
    assert not evaluate_run(b, tmp_path, evidence, allowances=(allow,), platform="windows").green
    assert not evaluate_run(b, tmp_path, evidence, allowances=(SkipAllowance(allow.test_id, allow.reason, ""),)).green


def test_assertion_weakening_removal_and_exact_review(tmp_path):
    b = baseline(tmp_path)
    evidence = SuiteEvidence({"test_critical.py::test_hash": "passed"}, 1, 0)
    source = tmp_path / "test_critical.py"
    source.write_text("def test_hash():\n    assert True\n", encoding="utf-8")
    assert not evaluate_run(b, tmp_path, evidence).green
    approved = ChangeApproval("test_critical.py", b.files["test_critical.py"], hashlib.sha256(source.read_bytes()).hexdigest(), "reviewed deliberate checker correction", "reviewer")
    assert evaluate_run(b, tmp_path, evidence, approvals=(approved,)).green
    source.unlink()
    assert "CRITICAL_TEST_REMOVED" in "\n".join(evaluate_run(b, tmp_path, evidence).findings)


def test_oracle_is_external_and_versioned(tmp_path):
    product = tmp_path / "product"
    product.mkdir()
    b = baseline(product)
    with pytest.raises(ValueError, match="outside"):
        save_baseline(b, product / "oracle.json", product)
    path = tmp_path / "supervisor/oracle.json"
    save_baseline(b, path, product)
    assert load_baseline(path).digest == b.digest


def test_report_collects_module_importorskip_and_xfail_counts(tmp_path):
    path = tmp_path / "report.json"
    path.write_text(json.dumps({"summary": {"collected": 0}, "tests": [], "collectors": [{"nodeid": "test_hash.py", "outcome": "skipped"}]}), encoding="utf-8")
    evidence = pytest_evidence(path, 0)
    assert evidence.collection_skips == ("test_hash.py",)
    assert not evaluate_run(baseline(tmp_path), tmp_path, evidence).green
    assert not pytest_evidence(tmp_path / "absent", 0).report_valid


def test_tap_and_vitest_skips_preserved(tmp_path):
    output = "TAP version 13\nok 1 - real hash\nok 2 - platform # SKIP Windows-only\nnot ok 3 - todo # TODO future\n# tests 3\n"
    evidence = tap_evidence(output, 0)
    assert evidence.outcomes == {"real hash": "passed", "platform": "skipped", "todo": "xfailed"}
    assert evidence.counts["collected"] == 3
    assert toolchain.parse_results("node", output, "")["platform"] == "skipped"
    path = tmp_path / "vitest.json"
    path.write_text(json.dumps({"numTotalTests": 1, "testResults": [{"name": "critical.test.js", "assertionResults": [{"title": "real hash", "status": "pending"}]}]}), encoding="utf-8")
    assert vitest_evidence(path, 0).outcomes == {"critical.test.js::real hash": "skipped"}


def test_importorskip_exit_zero_does_not_make_critical_suite_green(tmp_path):
    # A native suite can exit zero: one smoke test passes while the required
    # crypto primitive silently skips. The integrity gate still refuses it.
    (tmp_path / "test_native.py").write_text("import pytest\ndef test_required():\n    pytest.importorskip('autospec_deliberately_missing_crypto')\n\ndef test_smoke():\n    assert True\n", encoding="utf-8")
    b = capture_baseline(tmp_path, ["test_native.py"], ["test_native.py::test_required", "test_native.py::test_smoke"])
    report = tmp_path / "report.json"
    proc = subprocess.run([sys.executable, "-m", "pytest", "test_native.py", "-q", "--json-report", f"--json-report-file={report}", "-p", "no:cacheprovider"], cwd=tmp_path, capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    evidence = pytest_evidence(report, proc.returncode)
    assert evidence.counts["skipped"] == 1 and evidence.counts["passed"] == 1
    assert not evaluate_run(b, tmp_path, evidence).green


def test_compiler_requires_collectable_function_not_helper_or_empty_class():
    assert not constitution.is_runnable_pytest("def helper():\n    def test_nested(): pass\n")
    assert not constitution.is_runnable_pytest("class TestEmpty: pass\n")
    assert not constitution.is_runnable_pytest("def testing_only(): pass\n")
