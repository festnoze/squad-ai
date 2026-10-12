"""Actual uv/npm locked installs; no LLM/provider and no historical snapshot.

These small integration fixtures intentionally require the supported tools and
registry/cache availability. A missing environment is a failure, not fake GREEN.
"""
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from autospec.orchestrator.dependencies import DependencyCoordinator, DependencyRequest, run_command
from autospec.orchestrator.environments import CleanEnvironmentManager, minimal_environment
from autospec.orchestrator.test_integrity import capture_baseline, evaluate_run, pytest_evidence, tap_evidence


@pytest.mark.parametrize("nested_repository", [False, True])
def test_real_argon2_runtime_request_and_clean_lock_validation(tmp_path, nested_repository):
    if nested_repository:
        # A distinct ancestor config is sufficient to reproduce pytest's root
        # discovery in a nested repository. No Git command or hostile hook runs.
        ancestor = tmp_path / "repo"
        ancestor.mkdir()
        (ancestor / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
        tmp_path = ancestor / "run"
        tmp_path.mkdir()
    root = tmp_path / "product"
    root.mkdir()
    (root / "pyproject.toml").write_text('[project]\nname="argon2-fixture"\nversion="0.1.0"\nrequires-python=">=3.12"\ndependencies=[]\n[project.optional-dependencies]\ndev=["pytest>=8", "pytest-json-report>=1.5"]\n', encoding="utf-8")
    proc = run_command(["uv", "lock", "--python", sys.executable], cwd=root, env=minimal_environment())
    assert proc.returncode == 0, proc.stdout + proc.stderr
    manager = CleanEnvironmentManager(tmp_path / "supervisor/cache")
    bad = manager.prepare(root, "python")
    # This is the critical anti-false-green regression: required Argon2 isn't
    # declared, but importorskip makes the native suite report success.
    source = 'import pytest\ndef test_hash():\n    argon2 = pytest.importorskip("argon2")\n    hasher = argon2.PasswordHasher()\n    assert hasher.verify(hasher.hash("fixture secret"), "fixture secret")\n\ndef test_smoke():\n    assert True\n'
    (root / "test_crypto.py").write_text(source, encoding="utf-8")
    baseline = capture_baseline(root, ["test_crypto.py"], ["test_crypto.py::test_hash", "test_crypto.py::test_smoke"])
    bad_run = bad.stage_project(root, tmp_path / "bad-run")
    report = tmp_path / "bad-report.json"
    native = run_command(bad.test_command(str(report)), cwd=bad_run, env=minimal_environment())
    assert native.returncode == 0, native.stdout + native.stderr
    evidence = pytest_evidence(report, native.returncode)
    assert evidence.counts["skipped"] == 1
    assert not evaluate_run(baseline, bad_run, evidence).green
    assert run_command([str(bad.python), "-c", "import argon2"], cwd=bad_run, env=minimal_environment()).returncode != 0

    # This historical tool-only integration fixture explicitly opts into a
    # minimal host environment. Production defaults never select this runner.
    coordinator = DependencyCoordinator(root, tmp_path / "supervisor/requests", lambda argv, **kw: run_command(argv, **kw, env=minimal_environment()))
    coordinator.submit(DependencyRequest("AUTH", "python", "argon2-cffi", ">=23", "runtime", "pyproject.toml", "uv.lock", "real password hashing"))
    records = coordinator.resolve_pending("manifest-owner")
    assert records[0]["status"] == "applied", records
    coordinator.require_ready("AUTH")
    good = manager.prepare(root, "python")
    assert good.fingerprint != bad.fingerprint
    good_run = good.stage_project(root, tmp_path / "good-run")
    report = tmp_path / "good-report.json"
    native = run_command(good.test_command(str(report)), cwd=good_run, env=minimal_environment())
    assert native.returncode == 0, native.stdout + native.stderr
    observed = pytest_evidence(report, native.returncode)
    assert set(observed.outcomes) == set(baseline.expected_test_ids)
    assert Path(json.loads(report.read_text())["root"]).resolve() == good_run.resolve()
    assert evaluate_run(baseline, good_run, observed).green
    # Explicitly synthetic negative report: a matching basename/suffix is not
    # a collected independent test. Keep the strict evaluator/parser unchanged.
    foreign = json.loads(report.read_text())
    for test in foreign["tests"]:
        test["nodeid"] = "foreign-root/" + test["nodeid"]
    foreign_report = tmp_path / "foreign-id-metatest-report.json"
    foreign_report.write_text(json.dumps(foreign), encoding="utf-8")
    assert not evaluate_run(baseline, good_run, pytest_evidence(foreign_report, 0)).green
    runtime = manager.prepare(root, "python", "runtime")
    primitive = run_command([str(runtime.python), "-c", 'from argon2 import PasswordHasher; p=PasswordHasher(); assert p.verify(p.hash("fixture secret"), "fixture secret"); print("real Argon2 OK")'], cwd=root, env=minimal_environment())
    assert primitive.returncode == 0 and "real Argon2 OK" in primitive.stdout, primitive.stdout + primitive.stderr
    assert run_command([str(runtime.python), "-c", "import pytest"], cwd=root, env=minimal_environment()).returncode != 0
    # Enriching the producer environment from the valid one still cannot alter
    # the old incomplete-lock cache. Fresh validation uses the lock, not .venv.
    shutil.copytree(good.cache_path / ".venv", root / ".venv")
    assert run_command([str(root / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")), "-c", "import argon2"], cwd=root, env=minimal_environment()).returncode == 0
    assert run_command([str(bad.python), "-c", "import argon2"], cwd=bad_run, env=minimal_environment()).returncode != 0
    good.verify()


def test_real_node_clean_install_cannot_reuse_product_modules(tmp_path):
    root = tmp_path / "node-product"
    root.mkdir()
    (root / "package.json").write_text(json.dumps({"name": "node-fixture", "version": "1.0.0", "type": "module"}), encoding="utf-8")
    result = run_command(["npm", "install", "--package-lock-only", "--ignore-scripts"], cwd=root, env=minimal_environment())
    assert result.returncode == 0, result.stdout + result.stderr
    (root / "node_modules/undeclared").mkdir(parents=True)
    (root / "node_modules/undeclared/index.js").write_text("module.exports = true", encoding="utf-8")
    (root / "hash.test.js").write_text('import test from "node:test";\nimport assert from "node:assert/strict";\ntest("required package", async () => { await import("undeclared"); });\ntest("smoke", () => assert.equal(1,1));\n', encoding="utf-8")
    manager = CleanEnvironmentManager(tmp_path / "supervisor/cache")
    clean = manager.prepare(root, "node")
    run = clean.stage_project(root, tmp_path / "node-run")
    result = run_command(clean.test_command(""), cwd=run, env=minimal_environment())
    assert result.returncode != 0, result.stdout + result.stderr
    assert tap_evidence(result.stdout, result.returncode).outcomes["required package"] == "failed"
    coordinator = DependencyCoordinator(root, tmp_path / "supervisor/requests", lambda argv, **kw: run_command(argv, **kw, env=minimal_environment()))
    coordinator.submit(DependencyRequest("NODE", "node", "is-number", "^7", "runtime", "package.json", "package-lock.json", "small registry dependency fixture"))
    records = coordinator.resolve_pending("node-manifest-owner")
    assert records[0]["status"] == "applied", records
    coordinator.require_ready("NODE")
    (root / "hash.test.js").write_text('import test from "node:test";\nimport assert from "node:assert/strict";\nimport isNumber from "is-number";\ntest("real primitive", () => { assert.equal(isNumber(42),true); assert.equal(isNumber("not a number"),false); });\n', encoding="utf-8")
    good = manager.prepare(root, "node")
    assert good.fingerprint != clean.fingerprint
    run = good.stage_project(root, tmp_path / "node-good-run")
    result = run_command(good.test_command(""), cwd=run, env=minimal_environment())
    assert result.returncode == 0, result.stdout + result.stderr
    assert tap_evidence(result.stdout, result.returncode).outcomes == {"real primitive": "passed"}
