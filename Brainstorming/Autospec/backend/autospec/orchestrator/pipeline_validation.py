"""Supervisor-owned native verification; generated code never runs on host."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from dataclasses import asdict
from pathlib import Path

from ..agents.file_broker import ExecutionContext, FileBroker
from .dependencies import atomic_json, file_lock
from .isolated_validation import IsolatedValidator
from .test_integrity import capture_baseline, evaluate_run, load_baseline, save_baseline
from .toolchain import frontend_failure_digest


def critical_test_files(root: Path, ecosystem: str) -> list[str]:
    broker = FileBroker(ExecutionContext("critical-native-tests", root))
    files = []
    ignored = {".git", ".venv", "venv", "node_modules", "dist", "build", "__pycache__"}
    for parent, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = [name for name in dirs if name not in ignored and not name.startswith(".autospec")]
        for name in names:
            relative = (Path(parent) / name).relative_to(root).as_posix()
            python_test = (name in {"conftest.py", "pytest.ini", ".coveragerc", "setup.cfg", "tox.ini"}
                           or name.startswith("test_") and name.endswith(".py"))
            node_test = (".test." in name or ".spec." in name or
                         name.startswith(("vitest.config.", "vite.config.", "tsconfig")) or
                         name.casefold().startswith(("setuptests.", "testsetup.")))
            support = relative.startswith(("tests/", "test/", "src/test/", "src/tests/"))
            if (python_test if ecosystem == "python" else node_test) or support:
                broker.path(relative)
                files.append(relative)
    return sorted(files)


def run_native(root: Path, ecosystem: str, supervisor: Path, *, owner: str,
               project_root: Path, docker: str, timeout: float, build: bool = False,
               logical_prefix: str = ""):
    """Run, retain original collection and enforce the immutable checker baseline.

    Initial RED tests are allowed to establish the baseline; changing an old
    checker, losing collection, or skipping does not become a green run.
    """
    root, supervisor = Path(root).absolute(), Path(supervisor).absolute()
    if supervisor.resolve().is_relative_to(root.resolve()):
        raise ValueError("supervisor evidence cannot live inside product")
    validator = IsolatedValidator(supervisor / "environments", docker=docker, timeout=timeout)
    identity = hashlib.sha256(f"{owner}:{ecosystem}".encode()).hexdigest()[:24]
    report = supervisor / "native" / identity / (uuid.uuid4().hex + ".json")
    baseline_path = supervisor / "native-baselines" / (identity + ".json")
    collected_ids = None
    collection = None
    if not baseline_path.exists() and ecosystem == "python":
        collected_ids, collection = validator.collect_python(root, report.with_suffix(".collection.json"))
        if (not collection.evidence.report_valid or collection.evidence.exit_code
                or collection.evidence.collection_errors or not collected_ids
                or len(set(collected_ids)) != len(collected_ids)
                or collection.evidence.collected != len(collected_ids)):
            return False, collection.output + "\nNATIVE_BASELINE_UNAVAILABLE: incomplete collection", {}
    result = validator.run_suite(root, ecosystem, "test", report)
    output = result.output
    if ecosystem == "node" and result.evidence.exit_code:
        digest = frontend_failure_digest(str(report))
        if digest:
            output += "\n--- échecs Vitest (rapport JSON) ---\n" + digest
    if not result.evidence.collected:
        output += "\nSANS test collecté : aucune preuve native admissible"
    if not baseline_path.exists():
        if (not result.evidence.report_valid or result.evidence.collection_errors
                or result.evidence.collected == 0 or not result.evidence.outcomes
                or result.evidence.collected != len(result.evidence.outcomes)
                or collected_ids is not None and set(result.evidence.outcomes) != set(collected_ids)
                or collection is not None and collection.source_fingerprint != result.source_fingerprint):
            return False, output + "\nNATIVE_BASELINE_UNAVAILABLE: no reliable collection", result.evidence.outcomes
        paths = critical_test_files(root, ecosystem)
        baseline = capture_baseline(root, paths, list(collected_ids or result.evidence.outcomes))
        save_baseline(baseline, baseline_path, root)
        # Physical worktree paths change; the protected paths use logical roots.
        prefix = logical_prefix.strip("/") + "/" if logical_prefix else ""
        protected = supervisor / "protected-test-files.json"
        with file_lock(supervisor / "protected-tests.lock"):
            existing = json.loads(protected.read_text(encoding="utf-8")) if protected.exists() else {"files": {}}
            for path, digest in baseline.files.items():
                logical = prefix + path
                previous = existing["files"].get(logical)
                if previous is not None and previous != digest:
                    return False, output + f"\nCRITICAL_TEST_CHANGED_UNREVIEWED: {logical}", result.evidence.outcomes
                existing["files"][logical] = digest
            atomic_json(protected, existing)
    else:
        baseline = load_baseline(baseline_path)
    verdict = evaluate_run(baseline, root, result.evidence, platform="linux")
    atomic_json(report.with_suffix(".integrity.json"), {
        "version": 1, "owner": owner, "ecosystem": ecosystem,
        "fingerprint": result.fingerprint, "image": result.image,
        "baseline_hash": baseline.digest, "integrity": asdict(verdict),
    })
    if not verdict.green:
        output += "\nNATIVE_INTEGRITY_FAILED: " + "; ".join(verdict.findings)
    green = verdict.green
    if green and build:
        code, details, dist, _ = validator.build_frontend(root)
        try:
            output += "\n--- isolated production build ---\n" + details
            green = code == 0
        finally:
            shutil.rmtree(dist)
    return green, output, result.evidence.outcomes


def run_coverage(root: Path, supervisor: Path, *, owner: str, source: str,
                 docker: str, timeout: float) -> tuple[float | None, str]:
    """Coverage is native evidence, not a best-effort percent after a bad run."""
    identity = hashlib.sha256(f"{owner}:python".encode()).hexdigest()[:24]
    baseline_path = supervisor / "native-baselines" / (identity + ".json")
    if not baseline_path.is_file():
        return None, "NATIVE_BASELINE_UNAVAILABLE: coverage requires a prior native baseline"
    validator = IsolatedValidator(supervisor / "environments", docker=docker, timeout=timeout)
    report = supervisor / "coverage" / identity / (uuid.uuid4().hex + ".json")
    result = validator.run_suite(root, "python", "test", report,
        coveragepath=report.with_suffix(".coverage.json"), coverage_source=source)
    verdict = evaluate_run(load_baseline(baseline_path), root, result.evidence, platform="linux")
    atomic_json(report.with_suffix(".integrity.json"), {
        "version": 1, "owner": owner, "source": source, "fingerprint": result.fingerprint,
        "source_fingerprint": result.source_fingerprint, "image": result.image, "integrity": asdict(verdict),
    })
    if not verdict.green or not result.coverage:
        return None, result.output + "\nCOVERAGE_NOT_ADMITTED: " + "; ".join(verdict.findings)
    totals = result.coverage["totals"]
    statements, branches = totals["num_statements"], totals["num_branches"]
    if statements == 0:
        return None, result.output + "\nCOVERAGE_NOT_ADMITTED: zero measured source statements"
    percent = 100 * (totals["covered_lines"] + totals["covered_branches"]) / (statements + branches)
    return percent, result.output
