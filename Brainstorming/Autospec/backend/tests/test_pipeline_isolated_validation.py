import asyncio
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from autospec.agents.runner import FakeRunner
from autospec.config import settings
from autospec.models import ProjectState, PipelinePhase, BackendLanguage
from autospec.orchestrator import pipeline_validation
from autospec.orchestrator.pipeline import Pipeline
from autospec.orchestrator.test_integrity import SuiteEvidence


def product(tmp_path):
    root = tmp_path / "product"
    root.mkdir()
    (root / "test_critical.py").write_text("def test_critical():\n assert True\n")
    return root


def validator(monkeypatch, evidence):
    class Validator:
        def __init__(self, *a, **kw):
            pass
        def collect_python(self, root, report):
            return tuple(evidence.outcomes), SimpleNamespace(evidence=evidence, output="collected",
                source_fingerprint="c"*64)
        def run_suite(self, root, ecosystem, mode, report, **kwargs):
            return SimpleNamespace(evidence=evidence, output="executed", fingerprint="a"*64, image="sha256:"+"b"*64,
                source_fingerprint="c"*64, coverage={"totals": {"num_statements": 4, "num_branches": 2,
                    "covered_lines": 4, "covered_branches": 1}} if kwargs.get("coveragepath") else None)
    monkeypatch.setattr(pipeline_validation, "IsolatedValidator", Validator)


def test_native_baseline_admits_initial_green_and_refuses_checker_edit(tmp_path, monkeypatch):
    root = product(tmp_path)
    proof = SuiteEvidence({"test_critical.py::test_critical": "passed"}, 1, 0)
    validator(monkeypatch, proof)
    arguments = dict(owner="T1", project_root=root, docker="docker", timeout=30)
    assert pipeline_validation.run_native(root, "python", tmp_path / "supervisor", **arguments)[0]
    (root / "test_critical.py").write_text("def test_critical():\n pass\n")
    result = pipeline_validation.run_native(root, "python", tmp_path / "supervisor", **arguments)
    assert not result[0] and "CRITICAL_TEST_CHANGED_UNREVIEWED" in result[1]


def test_coverage_isolated_and_bound_to_unchanged_baseline(tmp_path, monkeypatch):
    root = product(tmp_path)
    supervisor = tmp_path / "supervisor"
    proof = SuiteEvidence({"test_critical.py::test_critical": "passed"}, 1, 0)
    validator(monkeypatch, proof)
    arguments = dict(owner="T1", docker="docker", timeout=30)
    assert pipeline_validation.run_coverage(root, supervisor, source="app", **arguments)[0] is None
    assert pipeline_validation.run_native(root, "python", supervisor, project_root=root, **arguments)[0]
    assert pipeline_validation.run_coverage(root, supervisor, source="app", **arguments)[0] == pytest.approx(100*5/6)
    (root / "test_critical.py").write_text("pass")
    assert pipeline_validation.run_coverage(root, supervisor, source="app", **arguments)[0] is None


def test_custom_frontend_zone_protects_logical_not_physical_paths(tmp_path, monkeypatch):
    root = product(tmp_path)
    (root / "src").mkdir()
    (root / "src/setupTests.ts").write_text("import '@testing-library/jest-dom';")
    (root / "src/page.test.ts").write_text("test('page', ()=>expect(1).toBe(1))")
    proof = SuiteEvidence({"src/page.test.ts::page": "passed"}, 1, 0)
    validator(monkeypatch, proof)
    supervisor = tmp_path / "supervisor"
    assert pipeline_validation.run_native(root, "node", supervisor, owner="UI", project_root=root,
        logical_prefix="web/client", docker="docker", timeout=30)[0]
    protected = json.loads((supervisor / "protected-test-files.json").read_text())["files"]
    assert "web/client/src/setupTests.ts" in protected and "web/client/src/page.test.ts" in protected


def test_partial_collection_never_freezes_a_baseline(tmp_path, monkeypatch):
    root = product(tmp_path)
    validator(monkeypatch, SuiteEvidence({"test_critical.py::test_critical": "passed"}, 1, 0,
        collection_errors=("test_auth_import.py",)))
    supervisor = tmp_path / "supervisor"
    result = pipeline_validation.run_native(root, "python", supervisor, owner="T1", project_root=root,
        docker="docker", timeout=30)
    assert not result[0] and "incomplete collection" in result[1]
    assert not list((supervisor / "native-baselines").glob("*.json"))


def test_unowned_process_is_never_killed_by_pid(monkeypatch):
    process = SimpleNamespace(pid=12345, poll=lambda: None)
    monkeypatch.setattr("autospec.orchestrator.pipeline.subprocess.run", lambda *a, **kw: pytest.fail("PID kill prohibited"))
    assert Pipeline._kill_tree(process) is False
    Pipeline._terminate_tree(process)


@pytest.mark.parametrize("evidence", [
    SuiteEvidence({}, 0, 0),
    SuiteEvidence({"test_critical.py::test_critical": "skipped"}, 1, 0),
    SuiteEvidence({"test_critical.py::test_critical": "xfailed"}, 1, 0),
    SuiteEvidence({"test_critical.py::test_critical": "passed"}, 2, 0),
])
def test_native_false_green_rejected(tmp_path, monkeypatch, evidence):
    root = product(tmp_path)
    validator(monkeypatch, evidence)
    assert not pipeline_validation.run_native(root, "python", tmp_path / "supervisor",
        owner="T1", project_root=root, docker="docker", timeout=30)[0]


async def test_python_and_frontend_verification_use_only_isolated_facade(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "fake_agents", False)
    state = ProjectState(id="isolated-facade", name="test", goal="test", phase=PipelinePhase.BUILD)
    pipeline = Pipeline(state, FakeRunner())
    calls = []
    async def native(root, ecosystem, **kw):
        calls.append((Path(root), ecosystem, kw))
        return True, "isolated", {"test": "passed"}
    monkeypatch.setattr(pipeline, "_arun_isolated_native", native)
    monkeypatch.setattr(pipeline, "_run_suite_process", lambda *a: pytest.fail("host compatibility launcher not used"))
    assert (await pipeline._arun_pytest(ws=tmp_path))[0]
    assert calls == [(tmp_path, "python", {})]
    state.backend_language = BackendLanguage.GO
    result = await pipeline._arun_pytest(ws=tmp_path)
    assert not result[0] and "ISOLATION_UNAVAILABLE" in result[1]


@pytest.mark.skipif(os.environ.get("AUTOSPEC_REAL_LINUX_VALIDATION") != "1", reason="explicit isolated Docker test")
def test_real_native_pipeline_baseline_and_skip_refusal(tmp_path):
    from autospec.orchestrator.validation_environment import LinuxEnvironmentManager
    root = product(tmp_path)
    (root / "pyproject.toml").write_text('[project]\nname="pipeline-proof"\nversion="0.1.0"\nrequires-python=">=3.12"\ndependencies=["pytest==9.0.3"]\n')
    manager = LinuxEnvironmentManager(tmp_path / "supervisor/environments")
    manager.ensure_lock(root, "python")
    arguments = dict(owner="T1", project_root=root, docker="docker", timeout=300)
    result = pipeline_validation.run_native(root, "python", tmp_path / "supervisor", **arguments)
    assert result[0], result[1]
    assert not (root / ".venv").exists()
    (root / "test_critical.py").write_text('import pytest\n@pytest.mark.skip(reason="make green")\ndef test_critical():\n assert False\n')
    result = pipeline_validation.run_native(root, "python", tmp_path / "supervisor", **arguments)
    assert not result[0]
    assert "CRITICAL_TEST_CHANGED_UNREVIEWED" in result[1]
    assert "TEST_OUTCOME_NOT_PERMITTED" in result[1]
