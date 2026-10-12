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
from .claims import canonical_path


def read_qa_authored_files(supervisor: Path, root: Path, *, logical_prefix: str = "") -> list[str]:
    """Read supervisor-authenticated QA write intent, never producer roles/hashes.

    Entries are canonical workspace-relative paths. A frontend suite removes
    only its exact declared logical prefix. Missing future writes do not create
    fake file identities; present links, directories and malformed journals
    are refused rather than ignored. Only the supervisor authorizer writes it.
    """
    supervisor = Path(supervisor).absolute()
    if supervisor.resolve() != supervisor or supervisor.is_symlink():
        raise ValueError("canonical supervisor provenance root required")
    if not supervisor.exists():
        return []  # fresh factory root: no journal/provenance has been published
    journal = FileBroker(ExecutionContext("qa-write-provenance", supervisor)).path("qa-authored-files.json")
    if not journal.exists():
        return []
    if not journal.is_file() or journal.stat().st_size > 2_000_000:
        raise ValueError("bounded QA provenance journal required")
    value = json.loads(journal.read_bytes())
    paths = value.get("files") if isinstance(value, dict) else None
    if (not isinstance(value, dict) or set(value) != {"files"} or not isinstance(paths, list)
            or len(paths) > 20_000 or any(not isinstance(p, str) for p in paths)
            or len(set(paths)) != len(paths)):
        raise ValueError("unique bounded supervisor QA paths required")
    if logical_prefix and canonical_path(logical_prefix, windows=False) != logical_prefix:
        raise ValueError("canonical suite prefix required")
    prefix = logical_prefix + "/" if logical_prefix else ""
    broker = FileBroker(ExecutionContext("qa-checker-source", root))
    actual = []
    for path in paths:
        if len(path) > 1024 or canonical_path(path, windows=False) != path:
            raise ValueError("canonical supervisor QA path required")
        if prefix and not path.startswith(prefix):
            continue
        relative = path[len(prefix):]
        file = broker.path(relative)
        if not file.exists():
            continue
        if not file.is_file():
            raise ValueError("QA provenance names a directory instead of a checker file")
        actual.append(file.relative_to(root).as_posix())
    return sorted(set(actual))


def critical_test_files(root: Path, ecosystem: str, *, collected_ids=()) -> list[str]:
    broker = FileBroker(ExecutionContext("critical-native-tests", root))
    files = []
    ignored = {".git", ".venv", "venv", "node_modules", "dist", "build", "__pycache__"}
    for parent, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = [name for name in dirs if name not in ignored and not name.startswith(".autospec")]
        for name in names:
            relative = (Path(parent) / name).relative_to(root).as_posix()
            python_test = (name in {"conftest.py", "pytest.ini", ".coveragerc", "setup.cfg", "tox.ini"}
                           or name.endswith(".py") and (name.startswith("test_") or name.endswith("_test.py")))
            node_test = (".test." in name or ".spec." in name or
                         name.startswith(("vitest.config.", "vite.config.", "tsconfig")) or
                         name.casefold().startswith(("setuptests.", "testsetup.")))
            support = relative.startswith(("tests/", "test/", "src/test/", "src/tests/"))
            if (python_test if ecosystem == "python" else node_test) or support:
                broker.path(relative)
                files.append(relative)
    # The actual independent collection is authoritative for custom selectors
    # (pytest python_files, Vitest include). Names alone cannot seal assertions.
    for node in collected_ids:
        if not isinstance(node,str) or "::" not in node:
            raise ValueError("collected checker lacks exact source filename")
        relative=node.split("::",1)[0].replace("\\","/").removeprefix("/app/").removeprefix("/tmp/product/")
        path=broker.path(relative)
        if not path.is_file():raise ValueError("collected checker source absent")
        files.append(relative)
    return sorted(set(files))


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
    new_baseline = not baseline_path.exists()
    collected_ids = None
    collection = None
    if new_baseline and ecosystem == "python":
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
    qa_paths = read_qa_authored_files(supervisor, root, logical_prefix=logical_prefix)
    if new_baseline:
        if (not result.evidence.report_valid or result.evidence.collection_errors
                or result.evidence.collected == 0 or not result.evidence.outcomes
                or result.evidence.collected != len(result.evidence.outcomes)
                or collected_ids is not None and set(result.evidence.outcomes) != set(collected_ids)
                or collection is not None and collection.source_fingerprint != result.source_fingerprint):
            return False, output + "\nNATIVE_BASELINE_UNAVAILABLE: no reliable collection", result.evidence.outcomes
        paths = sorted(set(critical_test_files(root, ecosystem,collected_ids=collected_ids or result.evidence.outcomes)) | set(qa_paths))
        baseline = capture_baseline(root, paths, list(collected_ids or result.evidence.outcomes))
    else:
        baseline = load_baseline(baseline_path)
        if set(qa_paths) - set(baseline.files):
            return False, output + "\nCRITICAL_QA_SUPPORT_BASELINE_INCOMPLETE", result.evidence.outcomes
    # Check publication on EVERY admission, including old poisoned/interrupted
    # baselines. A refused candidate must never be saved and accepted on retry.
    # Physical worktree paths change; protected paths use the logical roots.
    prefix = logical_prefix.strip("/") + "/" if logical_prefix else ""
    protected = supervisor / "protected-test-files.json"
    with file_lock(supervisor / "protected-tests.lock"):
        existing = json.loads(protected.read_text(encoding="utf-8")) if protected.exists() else {"files": {}}
        for path, digest in baseline.files.items():
            logical = prefix + path
            previous = existing["files"].get(logical)
            if previous is not None and previous != digest:
                return False, output + f"\nCRITICAL_TEST_CHANGED_UNREVIEWED: {logical}", result.evidence.outcomes
            if not new_baseline and previous is None:
                return False, output + f"\nCRITICAL_TEST_BASELINE_UNPUBLISHED: {logical}", result.evidence.outcomes
        if new_baseline:
            # Another worker may have sealed this owner while the native suite
            # ran. Do not overwrite its collected IDs or source identity.
            if baseline_path.exists() and load_baseline(baseline_path).digest != baseline.digest:
                return False, output + "\nCRITICAL_BASELINE_CHANGED_CONCURRENTLY", result.evidence.outcomes
            existing["files"].update({prefix + path: digest for path, digest in baseline.files.items()})
            # Publishing protection first makes an interrupted baseline save
            # fail closed. Both steps occur under the same supervisor lock.
            atomic_json(protected, existing)
            if not baseline_path.exists():
                save_baseline(baseline, baseline_path, root)
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
