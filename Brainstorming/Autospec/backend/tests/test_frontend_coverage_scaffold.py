"""Exact development provider and real isolated scaffold coverage command."""
import json
import os
from pathlib import Path
from types import SimpleNamespace
import uuid

import pytest

from autospec.orchestrator import bootstrap, workspace


COVERAGE_COMMAND = "vitest run --coverage --coverage.include=src/** --coverage.reporter=json"


def project():
    return SimpleNamespace(id="coverage-scaffold", name="Coverage scaffold", streams=[],
        brownfield_path="", product_profile="auto", backend_language=SimpleNamespace(value="python"),
        technical_stack=dict(backend="none", framework="none", frontend="react", database="none", kind="frontend"))


def prepare(root, monkeypatch):
    state = project()
    monkeypatch.setattr(workspace, "workspace_dir", lambda _: root)
    workspace.scaffold(state, streams_enabled=False, ui_tests_enabled=False)
    result = bootstrap.prepare(state, root)
    assert result.ok, result.detail
    return root / "frontend"


def assert_package(data):
    assert data["devDependencies"]["vitest"] == "4.1.11"
    assert data["devDependencies"]["@vitest/coverage-v8"] == "4.1.11"
    assert "@vitest/coverage-v8" not in data["dependencies"]
    assert data["scripts"]["test:coverage"] == COVERAGE_COMMAND
    assert "--coverage.all" not in COVERAGE_COMMAND


def test_workspace_manifest_pins_same_development_provider_and_reproducible_command():
    assert_package(json.loads(workspace.FE_PACKAGE_JSON_TEMPLATE.format(package="fixture")))


def test_bootstrap_manifest_pins_same_development_provider_and_reproducible_command(tmp_path, monkeypatch):
    root = prepare(tmp_path, monkeypatch)
    assert_package(json.loads((root / "package.json").read_text()))
    assert bootstrap.FRONTEND_VERSIONS["@vitest/coverage-v8"] == "4.1.11"


@pytest.mark.skipif(os.environ.get("AUTOSPEC_NATIVE_FRONTEND_COVERAGE") != "1",
                    reason="explicit real Linux fresh scaffold coverage opt-in")
def test_real_fresh_scaffold_coverage_script_and_qualified_collector(tmp_path, monkeypatch):
    from autospec.orchestrator.isolated_validation import IsolatedValidator, _node_command
    from autospec.orchestrator.validation_environment import snapshot_product
    from autospec.orchestrator.sandbox import run_isolated
    root = prepare(tmp_path / "source", monkeypatch)
    validator = IsolatedValidator(tmp_path / "cache", timeout=300)
    lock = validator.manager.ensure_lock(root, "node")
    locked = json.loads(lock.read_bytes())["packages"]
    assert locked["node_modules/vitest"]["version"] == "4.1.11"
    assert locked["node_modules/@vitest/coverage-v8"]["version"] == "4.1.11"
    environment = validator.manager.prepare(root, "node", "test")
    stage = snapshot_product(root, tmp_path / "script-stage")
    directory = "/tmp/autospec-coverage-" + uuid.uuid4().hex
    command = ["npm", "run", "test:coverage", "--", "--maxWorkers=1", "--fileParallelism=false",
               "--coverage.reportsDirectory=" + directory]
    actual = _node_command(command, coverage_directory=directory)
    rc, out, err = run_isolated(actual, stage, environment.image, timeout=90)
    assert rc == 0, out + err
    raw = json.loads((stage / "suite-coverage.json").read_bytes())
    assert raw and any(name.endswith("/src/App.tsx") for name in raw)
    report, coverage = tmp_path / "suite.json", tmp_path / "coverage.json"
    result = validator.run_suite(root, "node", "test", report,
                                 coveragepath=coverage, coverage_source="src")
    assert result.evidence.exit_code == 0 and result.evidence.report_valid, result.output
    assert result.coverage is not None and result.coverage["totals"]["num_statements"] > 0
    assert result.coverage["autospec_inventory"]["source_fingerprint"] == result.source_fingerprint
    assert not (root / "node_modules").exists()
    destination = os.environ.get("AUTOSPEC_FRONTEND_COVERAGE_EVIDENCE")
    if destination:
        target = Path(destination)
        target.mkdir(parents=True, exist_ok=True)
        (target / "package.json").write_bytes((root / "package.json").read_bytes())
        (target / "package-lock.json").write_bytes(lock.read_bytes())
        (target / "script-coverage.raw.json").write_text(json.dumps(raw, indent=2))
        (target / "collector-coverage.json").write_bytes(coverage.read_bytes())
        (target / "collector-suite.json").write_bytes(report.read_bytes())
        (target / "collector-execution.json").write_text(json.dumps(result.execution_receipt, indent=2))
        (target / "script-execution.json").write_text(json.dumps({"scope": "native fresh deterministic scaffold coverage capability, not TST03 acceptance",
            "command": command, "actual_isolated_argv": actual, "return_code": rc,
            "image_id": environment.image, "environment_fingerprint": environment.fingerprint,
            "installed_provider": "4.1.11", "stdout": out, "stderr": err}, indent=2))
