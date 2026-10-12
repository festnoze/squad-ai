"""Product tests and web runtimes run only behind the Linux Docker boundary.

Runtime ingress is an owned localhost TCP proxy into docker exec, not Docker
port publishing. The product keeps network=none: no host/LAN/registry egress.
"""
from __future__ import annotations

import json
import math
import re
import shutil
import shlex
import socket
import socketserver
import subprocess
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass, replace
import hashlib
import ipaddress
from pathlib import Path

from ..agents.file_broker import ExecutionContext, FileBroker
from ..agents.runner import _run_tracked, spawn_owned_process, close_owned_process
from .dependencies import atomic_json
from .sandbox import (run_isolated, require_sandbox, docker_run_cmd, _docker_call,
                      _container_identity, _cleanup_container, _unavailable)
from .test_integrity import SuiteEvidence, pytest_evidence, vitest_evidence, tap_evidence
from .validation_environment import LinuxEnvironmentManager, LinuxEnvironment, snapshot_product


@dataclass(frozen=True)
class IsolatedSuiteResult:
    evidence: SuiteEvidence
    output: str
    fingerprint: str
    image: str
    source_fingerprint: str = ""
    coverage: dict | None = None
    execution_receipt: dict | None = None


def _timed_call(receipt, phase, operation):
    """Clock the actual factory action; never reconstruct a fictitious rc."""
    tick = time.monotonic()
    start = datetime.now(timezone.utc).isoformat()
    try:
        return operation()
    finally:
        if receipt is not None:
            receipt["timing"] = {"phase": phase, "seconds": time.monotonic()-tick,
                "started_at": start, "ended_at": datetime.now(timezone.utc).isoformat(),
                "scope": "actual elapsed supervisor action, including attestation/cache checks"}


def _node_command(command: list[str], *, report: bool = False, dist: bool = False,
                  coverage_directory: str | None = None) -> list[str]:
    # Native Linux tmpfs source avoids broken cross-filesystem symlinks in
    # Docker Desktop Windows binds. Deps stay image-owned /opt read-only, with
    # only Vite's cache redirected to /tmp. Export only selected report/dist.
    setup = 'mkdir -p /tmp/product /tmp/vite-cache; cp -r /app/. /tmp/product/; ln -s /opt/node_modules /tmp/product/node_modules; cd /tmp/product; '
    if coverage_directory is not None and not re.fullmatch(r"/tmp/autospec-coverage-[a-f0-9]{32}", coverage_directory):
        raise _unavailable("Coverage export requires a fresh factory-owned directory")
    if not report and not dist and coverage_directory is None:
        script = setup + 'exec "$@"'
    else:
        script = setup + '"$@"; status=$?; '
        if report:
            script += 'if [ -f suite-report.json ] && [ ! -L suite-report.json ]; then cp suite-report.json /app/suite-report.json; fi; '
        if dist:
            script += 'if [ "$status" = 0 ] && [ -d dist ] && [ ! -L dist ]; then cp -r dist /app/dist; fi; '
        if coverage_directory is not None:
            file = coverage_directory + "/coverage-final.json"
            script += f'if [ -f {file} ] && [ ! -L {file} ]; then cp {file} /app/suite-coverage.json; fi; '
        script += 'exit "$status"'
    return ["/bin/sh", "-c", script, "autospec", *command]


def _coverage_inventory(stage: Path, source: str, ecosystem: str = "python") -> dict[str, str]:
    if source == ".":
        location = stage
    elif isinstance(source, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:[./][A-Za-z_][A-Za-z0-9_]*)*", source):
        relative = source.replace(".", "/") if ecosystem == "python" else source
        broker = FileBroker(ExecutionContext("coverage-source", stage))
        location = broker.path(relative)
        if not location.exists() and ecosystem == "python":
            location = broker.path(relative + ".py")
    else:
        raise _unavailable("Coverage requires an explicit contained source/module")
    files = location.rglob("*") if location.is_dir() else [location]
    inventory = {}
    for path in files:
        extensions = {".py"} if ecosystem == "python" else {".js", ".jsx", ".cjs", ".mjs", ".ts", ".tsx", ".cts", ".mts"}
        if (not path.is_file() or path.suffix not in extensions or path.name == "conftest.py" or
            path.name.startswith("test_") or path.name.endswith("_test.py") or
            any(part in {"tests", "test", "__tests__", "__pycache__"} for part in path.relative_to(stage).parts) or
            ecosystem == "node" and (any(marker in path.name for marker in (".test.", ".spec.", ".config.")) or
                path.name.endswith(".d.ts") or path.name.lower().startswith(("setuptests.", "testsetup.")))):
            continue
        inventory[path.relative_to(stage).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    if not inventory:
        raise _unavailable("Coverage has no admitted production source inventory")
    return inventory


def _istanbul_coverage(data: dict, inventory: dict[str, str], line_counts: dict[str, int]) -> dict:
    """Normalize executable-line and branch-arm counts, including untouched files.

    Source-only totals are recalculated later. Test/native/helper files cannot
    inflate the denominator. Maps outside the pre-execution source fail closed.
    """
    files = {}
    for raw_path, value in data.items():
        normal = raw_path.replace("\\", "/").removeprefix("/tmp/product/").removeprefix("/app/")
        if normal not in inventory:
            continue
        if normal in files:
            raise ValueError("Duplicate Istanbul source identity")
        statements, maps, branches, branch_maps = value["s"], value["statementMap"], value["b"], value["branchMap"]
        if not all(isinstance(item, dict) for item in (statements, maps, branches, branch_maps)):
            raise ValueError("Invalid Istanbul maps")
        if set(statements) != set(maps) or set(branches) != set(branch_maps):
            raise ValueError("Istanbul statement maps incomplete")
        lines = {}
        for key, count in statements.items():
            line = maps[key]["start"]["line"]
            if type(count) is not int or count < 0 or type(line) is not int or not 1 <= line <= line_counts[normal]:
                raise ValueError("Invalid Istanbul source/count")
            lines[line] = max(lines.get(line, 0), count)
        arms = []
        for key, branch in branches.items():
            locations = branch_maps[key]["locations"]
            if not isinstance(branch, list) or not isinstance(locations, list) or len(branch) != len(locations):
                raise ValueError("Incomplete Istanbul branch arms")
            for location in locations:
                for point in ("start", "end"):
                    line = location[point]["line"]
                    if type(line) is not int or not 1 <= line <= line_counts[normal]:
                        raise ValueError("Invalid Istanbul branch source")
            arms.extend(branch)
        if any(type(count) is not int or count < 0 for count in arms):
            raise ValueError("Invalid Istanbul branch counts")
        covered = sum(count > 0 for count in lines.values())
        files[normal] = {"summary": {"covered_lines": covered, "num_statements": len(lines),
            "missing_lines": len(lines) - covered, "num_branches": len(arms),
            "covered_branches": sum(count > 0 for count in arms)},
            "executed_lines": sorted(line for line, count in lines.items() if count > 0),
            "missing_lines": sorted(line for line, count in lines.items() if count == 0)}
    return {"format": "istanbul-executable-lines-branch-arms", "files": files, "totals": {}}


def _admit_source_coverage(data: dict, inventory: dict[str, str], source: str,
                           source_fingerprint: str, environment: LinuxEnvironment) -> dict:
    wanted = {}
    for path, value in data["files"].items():
        normal = path.replace("\\", "/").removeprefix("/app/")
        if normal in inventory:
            if normal in wanted:
                raise ValueError("Duplicate coverage source identity")
            wanted[normal] = value
    if set(wanted) != set(inventory):
        raise ValueError("Coverage omitted admitted source files")
    counts = {key: 0 for key in ("covered_lines", "num_statements", "missing_lines", "num_branches", "covered_branches")}
    for value in wanted.values():
        summary = value["summary"]
        for key in counts:
            if type(summary[key]) is not int or summary[key] < 0:
                raise ValueError("Invalid per-source coverage counts")
            counts[key] += summary[key]
        if (summary["covered_lines"] > summary["num_statements"] or
            summary["missing_lines"] != summary["num_statements"] - summary["covered_lines"] or
            summary["covered_branches"] > summary["num_branches"]):
            raise ValueError("Inconsistent per-source coverage counts")
    total = counts["num_statements"] + counts["num_branches"]
    counts["percent_covered"] = 100 * (counts["covered_lines"] + counts["covered_branches"]) / total if total else 0
    return {**data, "files": wanted, "totals": counts,
            "autospec_inventory": {"version": 1, "source": source, "files": inventory,
                "source_fingerprint": source_fingerprint, "environment_fingerprint": environment.fingerprint,
                "image": environment.image}}


class IsolatedValidator:
    def __init__(self, cache_root: Path, *, docker: str = "docker", timeout: float = 300,
                 manager: LinuxEnvironmentManager | None = None):
        self.manager = manager or LinuxEnvironmentManager(cache_root, docker=docker, timeout=timeout)
        self.docker = docker
        self.timeout = timeout

    def run_suite(self, root: Path, ecosystem: str, mode: str, reportpath: Path,
                  *, test_args: tuple[str, ...] = (), coveragepath: Path | None = None,
                  coverage_source: str = ".") -> IsolatedSuiteResult:
        root, reportpath = Path(root).absolute(), Path(reportpath).absolute()
        if reportpath.resolve().is_relative_to(root.resolve()):
            raise _unavailable("Suite evidence must be stored outside producer writable root")
        if coveragepath is not None:
            coveragepath = Path(coveragepath).absolute()
            if ecosystem not in {"python", "node"} or coveragepath.resolve().is_relative_to(root.resolve()):
                raise _unavailable("Coverage evidence must be outside producer root")
        preparation = {}
        environment = _timed_call(preparation, "install", lambda: self.manager.prepare(root, ecosystem, mode))
        with tempfile.TemporaryDirectory(prefix="autospec-suite-") as temporary:
            stage = snapshot_product(root, Path(temporary) / "product")
            stale = FileBroker(ExecutionContext("suite-report-freshness", stage)).path("suite-report.json")
            if stale.exists():
                stale.unlink()  # a cached/product report is never a fresh proof
            if coveragepath is not None:
                stale_coverage = FileBroker(ExecutionContext("coverage-freshness", stage)).path("suite-coverage.json")
                if stale_coverage.exists():
                    stale_coverage.unlink()
            # Bind evidence to the exact staged pre-execution source, not merely
            # its dependency image. Mutated temporary outputs aren't hashed.
            source_files = {file.relative_to(stage).as_posix(): hashlib.sha256(file.read_bytes()).hexdigest()
                            for file in sorted(stage.rglob("*")) if file.is_file()}
            source_fingerprint = hashlib.sha256(json.dumps(source_files,sort_keys=True).encode()).hexdigest()
            coverage_inventory = _coverage_inventory(stage, coverage_source, ecosystem) if coveragepath is not None else None
            coverage_line_counts = {path: len((stage / path).read_text(encoding="utf-8").splitlines())
                                    for path in coverage_inventory} if ecosystem == "node" and coverage_inventory else None
            if ecosystem == "python":
                command = ["/opt/venv/bin/python", "-m", "pytest", "--json-report", "--json-report-file=suite-report.json", *test_args]
                command += ["-o", "addopts="]  # no product config can disable/redirect the factory recipe
                if coveragepath is not None:
                    command += [f"--cov={coverage_source}", "--cov-config=/dev/null", "--cov-branch", "--cov-report=json:suite-coverage.json", "--cov-report="]
                parser = pytest_evidence
            else:
                package = json.loads((stage / "package.json").read_text(encoding="utf-8"))
                has_vitest = "vitest" in {**package.get("dependencies", {}), **package.get("devDependencies", {})}
                if has_vitest:
                    command = ["node", "/opt/node_modules/vitest/vitest.mjs", "run", "--reporter=json", "--outputFile=suite-report.json", "--maxWorkers=2", "--minWorkers=1", *test_args]
                    parser = vitest_evidence
                    coverage_directory = None
                    if coveragepath is not None:
                        deps = {**package.get("dependencies", {}), **package.get("devDependencies", {})}
                        locked = json.loads((stage / "package-lock.json").read_text(encoding="utf-8"))["packages"]
                        version = locked["node_modules/vitest"]["version"]
                        if ("@vitest/coverage-v8" not in deps or version != "2.1.9" or
                            locked.get("node_modules/@vitest/coverage-v8", {}).get("version") != version):
                            raise _unavailable("Node coverage needs locked vitest/@vitest/coverage-v8 2.1.9; request it through the dependency coordinator")
                        coverage_directory = "/tmp/autospec-coverage-" + uuid.uuid4().hex
                        include = ("" if coverage_source == "." else coverage_source + "/") + "**/*.{js,jsx,cjs,mjs,ts,tsx,cts,mts}"
                        command += ["--coverage.enabled", "--coverage.provider=v8", "--coverage.all=true",
                                    f"--coverage.include={include}", "--coverage.exclude=**/*.{test,spec,config}.*",
                                    "--coverage.exclude=**/{test,tests,__tests__}/**", "--coverage.exclude=**/*.d.ts",
                                    "--coverage.exclude=**/{setupTests,testSetup}.*", "--coverage.reporter=json",
                                    f"--coverage.reportsDirectory={coverage_directory}", "--coverage.clean=true"]
                else:
                    if coveragepath is not None:
                        raise _unavailable("Structured Node coverage requires the qualified locked Vitest provider")
                    command = ["node", "--test", "--test-reporter=tap", *test_args]
                    parser = None
                    coverage_directory = None
                command = _node_command(command, report=has_vitest, coverage_directory=coverage_directory)
            executed = {}
            rc, out, err = _timed_call(executed, "tests", lambda: run_isolated(command, stage, environment.image, docker=self.docker, timeout=self.timeout))
            executed.update(argv=command, return_code=rc, environment_fingerprint=environment.fingerprint,
                image_id=environment.image, environment_preparation=preparation["timing"],
                source_fingerprint=source_fingerprint, scope="actual container inner argv and observed return code")
            atomic_json(reportpath.with_suffix(".execution.json"), executed)
            output = out + err
            if parser is None:
                evidence = tap_evidence(output, rc)
                atomic_json(reportpath, {"format": "tap", "output": output, "exit_code": rc})
            else:
                report = FileBroker(ExecutionContext("suite-report-export", stage)).path("suite-report.json")
                if not report.is_file() or report.stat().st_size > 20_000_000:
                    evidence = SuiteEvidence({}, 0, rc, report_valid=False)
                    atomic_json(reportpath, {"invalid_report": True, "exit_code": rc})
                else:
                    try:
                        data = json.loads(report.read_text(encoding="utf-8"))
                        atomic_json(reportpath, data)
                        evidence = parser(reportpath, rc)
                    except (OSError, ValueError, TypeError):
                        evidence = SuiteEvidence({}, 0, rc, report_valid=False)
                        atomic_json(reportpath, {"invalid_report": True, "exit_code": rc})
            coverage = None
            if coveragepath is not None:
                try:
                    report = FileBroker(ExecutionContext("coverage-export", stage)).path("suite-coverage.json")
                    if report.stat().st_size > 20_000_000:
                        raise ValueError("coverage exceeds limit")
                    coverage = json.loads(report.read_text(encoding="utf-8"))
                    if ecosystem == "node":
                        coverage = _istanbul_coverage(coverage, coverage_inventory, coverage_line_counts)
                    else:
                        totals = coverage["totals"]
                        for key in ("covered_lines", "num_statements", "missing_lines", "num_branches", "covered_branches"):
                            if type(totals[key]) is not int or totals[key] < 0:
                                raise ValueError("invalid coverage counts")
                    if not isinstance(coverage["files"], dict):
                        raise ValueError("invalid coverage files")
                    coverage = _admit_source_coverage(coverage, coverage_inventory, coverage_source,
                                                     source_fingerprint, environment)
                    atomic_json(coveragepath, coverage)
                except (OSError, KeyError, TypeError, ValueError):
                    coverage = None
                    evidence = replace(evidence, report_valid=False)
                    output += "\nCOVERAGE_EVIDENCE_INVALID: missing/invalid fresh coverage report"
                    atomic_json(coveragepath, {"invalid_report": True})
            return IsolatedSuiteResult(evidence, output, environment.fingerprint, environment.image, source_fingerprint, coverage, executed)

    def collect_python(self, root: Path, reportpath: Path) -> tuple[tuple[str, ...], IsolatedSuiteResult]:
        """Trusted pytest JSON collection, not regex/static source discovery.

        Unsupported/custom item formats or incomplete collection fail closed.
        Reports and collected IDs remain subject to supervisor baseline checks.
        """
        result = self.run_suite(root, "python", "test", reportpath, test_args=("--collect-only", "-q"))
        data = json.loads(Path(reportpath).read_text(encoding="utf-8"))
        identifiers = set()
        for collector in data.get("collectors", []):
            for item in collector.get("result", []):
                if item.get("type") in {"Function", "TestCaseFunction", "DoctestItem"}:
                    identifiers.add(item["nodeid"])
        if result.evidence.exit_code or not result.evidence.report_valid or result.evidence.collection_errors or len(identifiers) != result.evidence.collected or not identifiers:
            raise _unavailable("Incomplete/unsupported pytest collection; no baseline can be claimed")
        return tuple(sorted(identifiers)), result

    def run_command(self, root: Path, ecosystem: str, command: list[str], *, mode: str = "test",
                    exports: tuple[str, ...] = ()) -> tuple[int, str, LinuxEnvironment]:
        """Run in a filtered snapshot; only explicit regular-file exports return.

        Used for deterministic frontend builds. No arbitrary recursive sync-back.
        A caller must enumerate artefacts or use build_frontend for dist only.
        """
        environment = self.manager.prepare(Path(root), ecosystem, mode)
        if ecosystem == "node" and exports:
            raise _unavailable("Node arbitrary exports unsupported; use build_frontend for dist only")
        with tempfile.TemporaryDirectory(prefix="autospec-command-") as temporary:
            stage = snapshot_product(Path(root), Path(temporary) / "product")
            rc, out, err = run_isolated(_node_command(command) if ecosystem == "node" else command,
                                       stage, environment.image, docker=self.docker, timeout=self.timeout)
            if rc == 0:
                source = FileBroker(ExecutionContext("artifact-source", stage))
                target = FileBroker(ExecutionContext("artifact-target", Path(root)))
                batch = []
                for path in exports:
                    file = source.path(path)
                    if not file.is_file() or file.stat().st_size > 2_000_000:
                        raise _unavailable("Artifact export requires bounded regular files")
                    batch.append((target.path(path), file.read_bytes()))
                for file, data in batch:
                    file.parent.mkdir(parents=True, exist_ok=True)
                    file.write_bytes(data)
            return rc, out + err, environment

    def run_captured(self, root: Path, ecosystem: str, command: list[str], *, mode: str = "runtime") -> tuple[int, str, str, LinuxEnvironment]:
        """Filtered isolated execution, separate stdout/stderr, no exports.

        A help probe must not treat stderr-only diagnostics as a valid stdout
        response. Timeout/cancellation remains daemon-side container cleanup.
        """
        environment = self.manager.prepare(Path(root), ecosystem, mode)
        with tempfile.TemporaryDirectory(prefix="autospec-captured-") as temporary:
            stage = snapshot_product(Path(root), Path(temporary) / "product")
            rc, out, err = run_isolated(_node_command(command) if ecosystem == "node" else command,
                                       stage, environment.image, docker=self.docker, timeout=self.timeout)
            return rc, out, err, environment

    def build_frontend(self, root: Path, *, receipt: dict | None = None) -> tuple[int, str, Path, LinuxEnvironment]:
        """Vite builds inside Docker; returns a supervisor-owned temporary dist.

        Caller owns the returned directory. It contains dist only, never source,
        credentials, dependency links, or changes to generated project files.
        """
        dependency_receipt = {}
        if receipt is not None:
            receipt.clear()
            receipt.update(version=1, dependency=dependency_receipt, argv=None, rc=None)
        environment = _timed_call(dependency_receipt if receipt is not None else None, "install",
            lambda: self.manager.prepare(Path(root), "node", "test", receipt=dependency_receipt) if receipt is not None else self.manager.prepare(Path(root), "node", "test"))
        with tempfile.TemporaryDirectory(prefix="autospec-vite-") as temporary:
            stage = snapshot_product(Path(root), Path(temporary) / "product")
            stale_dist = stage / "dist"
            if stale_dist.exists():
                # snapshot_product has rejected every link/reparse/hardlink;
                # this resolved path is inside the disposable stage only.
                if not stale_dist.resolve().is_relative_to(stage):
                    raise _unavailable("Unsafe stale dist path")
                shutil.rmtree(stale_dist)
            # Never npm run: package scripts cannot change the trusted recipe.
            # tsc -b honours project references (plain --noEmit can silently
            # check zero files for a solution-style tsconfig). Vite alone only
            # transpiles and must never claim TypeScript validation success.
            build = ["node", "/opt/node_modules/vite/bin/vite.js", "build"]
            if (stage / "tsconfig.json").is_file():
                build = ["/bin/sh", "-c", "node /opt/node_modules/typescript/bin/tsc -b --pretty false && exec node /opt/node_modules/vite/bin/vite.js build"]
            command = _node_command(build, dist=True)
            if receipt is not None:
                receipt.update(kind="typecheck_frontend_build" if (stage / "tsconfig.json").is_file() else "frontend_build",
                               components=["typecheck", "frontend_build"] if (stage / "tsconfig.json").is_file() else ["frontend_build"],
                               argv=command, rc=None, environment_fingerprint=environment.fingerprint,
                               image_id=environment.image, isolated=True)
            rc, out, err = _timed_call(receipt, "build", lambda: run_isolated(command, stage, environment.image, docker=self.docker, timeout=self.timeout))
            if receipt is not None:
                receipt.update(rc=rc, output_tail=(out + err)[-16000:])
            result = Path(tempfile.mkdtemp(prefix="autospec-dist-"))
            if rc == 0:
                snapshot_product(stage / "dist", result / "dist")
            return rc, out + err, result, environment


def build_delivery_image(root: Path, image: str, *, docker: str = "docker", timeout: float = 300,
                         evidence_root: Path | None = None, snapshot_hash: str | None = None) -> tuple[bool, str]:
    """Compatible build tuple plus optional supervisor-owned snapshot receipt.

    Exact dependency caches/layers are attested, not falsely described as fresh
    uv/npm executions. An installation's rc is None unless it was observed.
    The Docker builder and combined tsc/Vite argv retain their real exit codes.
    """
    if evidence_root is None:
        if snapshot_hash is not None:
            raise _unavailable("Snapshot build receipts require an external evidence root")
        return _build_delivery_image(root, image, docker=docker, timeout=timeout)
    from ..validation.final_gate import source_snapshot
    root, evidence_root = Path(root).absolute(), Path(evidence_root).absolute()
    if (evidence_root.resolve().is_relative_to(root.resolve()) or
        evidence_root.resolve() != evidence_root or not isinstance(snapshot_hash, str) or
        not re.fullmatch(r"[a-f0-9]{64}", snapshot_hash)):
        raise _unavailable("Delivery build evidence requires an external unaliased root and exact snapshot SHA")
    if source_snapshot(root).digest != snapshot_hash:
        raise _unavailable("Delivery source differs from the requested snapshot")
    receipt = {"version": 1, "status": "FAIL", "snapshot_hash": snapshot_hash,
               "image_id": None, "image_tag": image, "isolated": True, "no_host_dependencies": True,
               "manifest_only_install": True, "locks_sha256": {}, "commands": [], "frontend_files": {}}
    try:
        ok, output = _build_delivery_image(root, image, docker=docker, timeout=timeout, receipt=receipt)
        if source_snapshot(root).digest != snapshot_hash:
            raise _unavailable("Delivery source changed during build; no matching receipt")
        receipt["status"] = "PASS" if ok else "FAIL"
        return ok, output
    except BaseException as exc:
        receipt.update(status="FAIL", error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        atomic_json(evidence_root / "delivery-build.json", receipt)


def _dependency_command_receipt(manager, root: Path, environment: LinuxEnvironment, observed: dict, kind: str) -> dict:
    inputs = environment.attestation["inputs"]
    manifest = root / ("pyproject.toml" if environment.ecosystem == "python" else "package.json")
    recipe = manager._recipe(inputs["toolchain_digest"], environment.ecosystem, environment.mode, environment.fingerprint, manifest)
    if hashlib.sha256(recipe.encode()).hexdigest() != environment.attestation["recipe_sha256"]:
        raise _unavailable("Dependency recipe differs from its immutable attestation")
    install = next(line[4:] for line in recipe.splitlines() if line.startswith(("RUN uv sync ", "RUN npm ci ")))
    return {"kind": kind, "argv": shlex.split(install), "rc": None,
            "execution": "attested-cache" if observed.get("status") == "cache_attested" else "attested-layer",
            "environment_fingerprint": environment.fingerprint, "image_id": environment.image,
            "attestation": environment.attestation, "builder": observed}


def _build_delivery_image(root: Path, image: str, *, docker: str = "docker", timeout: float = 300,
                          receipt: dict | None = None) -> tuple[bool, str]:
    """Bake filtered source into a trusted recipe, never the product Dockerfile.

    Dependency installs/builds remain in separate confined phases. The final
    image layer only copies source/dist and sets the exact runtime entrypoint.
    """
    from .validation_environment import LinuxEnvironmentManager
    root = Path(root)
    if not image or image.startswith("-") or any(c.isspace() for c in image):
        raise _unavailable("Invalid delivery image name")
    manager = LinuxEnvironmentManager(Path(tempfile.gettempdir()).resolve() / "autospec-linux-environments", docker=docker, timeout=timeout)
    validator = IsolatedValidator(manager.cache_root, docker=docker, timeout=timeout, manager=manager)
    ecosystem = "python" if (root / "pyproject.toml").is_file() else "node" if (root / "package.json").is_file() else ""
    if not ecosystem:
        raise _unavailable("Delivery requires an isolated Python or Node lockfile")
    dependency_receipt = {}
    if receipt is not None:
        receipt["backend_dependency"] = dependency_receipt
    environment = _timed_call(dependency_receipt if receipt is not None else None, "install",
        lambda: manager.prepare(root, ecosystem, "runtime", receipt=dependency_receipt) if receipt is not None else manager.prepare(root, ecosystem, "runtime"))
    if receipt is not None:
        manifest, lock = (root / "pyproject.toml", root / "uv.lock") if ecosystem == "python" else (root / "package.json", root / "package-lock.json")
        receipt["locks_sha256"][lock.relative_to(root).as_posix()] = hashlib.sha256(lock.read_bytes()).hexdigest()
        receipt["commands"].append(_dependency_command_receipt(manager, root, environment, dependency_receipt, "backend_install"))
    frontend = root / "frontend" if (root / "frontend/package.json").is_file() else None
    dist = None
    try:
        if frontend:
            frontend_receipt = {}
            if receipt is not None:
                receipt["frontend_build"] = frontend_receipt
            rc, output, dist, frontend_environment = validator.build_frontend(frontend, receipt=frontend_receipt) if receipt is not None else validator.build_frontend(frontend)
            if receipt is not None:
                receipt["locks_sha256"]["frontend/package-lock.json"] = hashlib.sha256((frontend / "package-lock.json").read_bytes()).hexdigest()
                receipt["commands"].append(_dependency_command_receipt(manager, frontend, frontend_environment, frontend_receipt["dependency"], "frontend_install"))
                receipt["commands"].append({key: value for key, value in frontend_receipt.items() if key != "dependency"})
            if rc:
                return False, output
            if receipt is not None:
                receipt["frontend_files"] = {"frontend/dist/" + file.relative_to(dist / "dist").as_posix(): hashlib.sha256(file.read_bytes()).hexdigest()
                    for file in sorted((dist / "dist").rglob("*")) if file.is_file()}
        with tempfile.TemporaryDirectory(prefix="autospec-delivery-") as temporary:
            context = Path(temporary).resolve()
            stage = snapshot_product(root, context / "product")
            if dist:
                target = stage / "frontend/dist"
                if target.exists():
                    shutil.rmtree(target)
                shutil.copytree(dist / "dist", target)
            # Reverify dependency tag identity immediately before use. Docker's
            # local image IDs cannot be used in FROM by BuildKit (treated as a
            # registry named sha256); immutable attestations pin the cache tag.
            base = "autospec/clean-env:" + environment.fingerprint
            if manager._image(base)["Id"] != environment.image:
                raise _unavailable("Dependency image tag changed identity")
            command = ["/opt/venv/bin/python", "main.py"] if ecosystem == "python" else ["node", "main.js"]
            recipe = f"FROM {base}\nWORKDIR /app\nCOPY --chown=65532:65532 product/ /app/\nENV HOME=/tmp PYTHONDONTWRITEBYTECODE=1\nUSER 65532:65532\nCMD {json.dumps(command)}\n"
            if receipt is not None:
                recipe += f'LABEL autospec.snapshot={receipt["snapshot_hash"]}\n'
            (context / "Dockerfile").write_text(recipe, encoding="utf-8")
            argv = [docker, "build", "--pull=false", "--network=none", "-t", image, "."]
            command_receipt = {"kind": "image_build", "argv": argv, "rc": None, "isolated": True,
                               "recipe_sha256": hashlib.sha256(recipe.encode()).hexdigest()}
            if receipt is not None:
                receipt["commands"].append(command_receipt)
            rc, out, err = _timed_call(command_receipt if receipt is not None else None, "docker", lambda: _run_tracked(argv, "", str(context), timeout))
            command_receipt.update(rc=rc, output_tail=(out + err)[-16000:])
            if receipt is not None and rc == 0:
                baked = manager._image(image)
                if (not re.fullmatch(r"sha256:[a-f0-9]{64}", baked["Id"]) or
                    baked.get("Config", {}).get("Labels", {}).get("autospec.snapshot") != receipt["snapshot_hash"]):
                    raise _unavailable("Delivery image snapshot identity cannot be attested")
                receipt["image_id"] = baked["Id"]
            return rc == 0, out + err
    finally:
        if dist is not None:
            shutil.rmtree(dist)


class RuntimeSession:
    """Exact owned net-none runtime, stable ingress and optional disposable DB.

    Constructing reserves a loopback socket, so origin is known BEFORE launch.
    A caller must close a constructed session even if it never enters it.
    Product code sees neither a host bind for DB nor the Docker socket. exec is
    a trusted supervisor API, not a mediated agent/model tool.
    """
    DATABASE_DIRECTORY = "/var/lib/autospec-validation"
    DATABASE_URL = "sqlite:////var/lib/autospec-validation/support.sqlite"

    def __init__(self, stage: Path, image: str, command: list[str], *, port: int = 8000,
                 ecosystem: str = "python", docker: str = "docker", env: dict[str, str] | None = None,
                 connection_timeout: float = 15, application_origin: bool = False,
                 local_cookie_mode: bool = False, persistent_database: bool = False,
                 mount_stage: bool = True):
        if not 1 <= port <= 65535 or ecosystem not in {"python", "node"}:
            raise _unavailable("Invalid runtime port/ecosystem")
        if not math.isfinite(connection_timeout) or connection_timeout <= 0:
            raise _unavailable("Invalid runtime connection timeout")
        if not command or any(not isinstance(value, str) or "\x00" in value for value in command):
            raise _unavailable("Invalid runtime command")
        if local_cookie_mode and not application_origin:
            raise _unavailable("Local cookie mode requires the controlled application origin")
        if type(mount_stage) is not bool or not mount_stage and not re.fullmatch(r"sha256:[a-f0-9]{64}", image):
            raise _unavailable("Baked runtime requires an immutable local image ID")
        self.stage, self.image, self.command = Path(stage), image, command
        self.port, self.ecosystem, self.docker = port, ecosystem, docker
        self.env = dict(env or {})
        allowed = {"PORT", "DATABASE_URL", "AUTOSPEC_STATIC_DIR", "AUTOSPEC_BOOTSTRAP_TOKEN", "HOST", "PYTHONPATH"}
        if set(self.env) - allowed or any(not isinstance(value, str) or "\x00" in value for value in self.env.values()):
            raise _unavailable("Runtime environment is factory-owned and allowlisted")
        if "DATABASE_URL" in self.env and not re.fullmatch(r"sqlite:////tmp/[A-Za-z0-9_.-]+\.(?:db|sqlite|sqlite3)", self.env["DATABASE_URL"]):
            raise _unavailable("Runtime validation DB must be disposable SQLite under /tmp")
        if persistent_database and "DATABASE_URL" in self.env:
            raise _unavailable("Persistent validation DB has a fixed factory URL, not an env override")
        for key, expected in (("PORT", str(port)), ("PYTHONPATH", "/app")):
            if key in self.env and self.env[key] != expected:
                raise _unavailable(f"Runtime {key} must use its fixed factory value")
        if "HOST" in self.env and self.env["HOST"] not in {"0.0.0.0", "127.0.0.1"}:
            raise _unavailable("Runtime HOST must be a container-local listener")
        if "AUTOSPEC_STATIC_DIR" in self.env and self.env["AUTOSPEC_STATIC_DIR"] not in {"/app/dist", "/app/frontend/dist"}:
            raise _unavailable("Runtime static directory must be a staged dist")
        self.timeout = connection_timeout
        self.owner, self.name = uuid.uuid4().hex, "autospec-sandbox-" + uuid.uuid4().hex
        self.identifier = None
        self.thread = None
        self.lock = threading.Lock()
        self.operation_lock = threading.RLock()
        self.clients: set[subprocess.Popen] = set()
        self.sockets: set[socket.socket] = set()
        self.capacity = threading.BoundedSemaphore(64)
        self.closed = False
        self.transition = True
        self.detached = False
        self.persistent_database = persistent_database
        self.mount_stage = mount_stage
        self.volume_name = "autospec-validation-" + uuid.uuid4().hex if persistent_database else None
        self.volume_identity = None
        self.volume_requested = False
        self.database_url = self.DATABASE_URL if persistent_database else self.env.get("DATABASE_URL")
        self.database_path = "/var/lib/autospec-validation/support.sqlite" if persistent_database else None
        session = self
        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                session._forward(self.request)
        class Server(socketserver.ThreadingTCPServer):
            daemon_threads = True
            allow_reuse_address = False
        self.server = Server(("127.0.0.1", 0), Handler)
        self.host_port = self.server.server_address[1]
        self.origin = f"http://127.0.0.1:{self.host_port}"
        if application_origin:
            self.env["APP_ORIGIN"] = self.origin
        if local_cookie_mode:
            self.env["SESSION_COOKIE_SECURE"] = "false"
        if persistent_database:
            self.env["DATABASE_URL"] = self.DATABASE_URL

    def __enter__(self):
        with self.operation_lock:
            return self._enter_owned()

    def _enter_owned(self):
        if self.closed or self.thread is not None:
            raise _unavailable("RuntimeSession is closed or already started")
        try:
            require_sandbox(self.stage, self.image, docker=self.docker)
            if self.persistent_database:
                self._create_volume()
            self._launch()
            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()
            return self
        except BaseException:
            self.close()
            raise

    def _volume_attestation(self) -> dict | None:
        result = _docker_call([self.docker, "volume", "inspect", self.volume_name, "--format", "{{json .}}"],
                              capture_output=True, text=True, timeout=3, check=False)
        if result.returncode:
            if "no such volume" in result.stderr.lower():
                return None
            raise _unavailable("Cannot attest whether the owned validation volume is absent")
        try:
            data = json.loads(result.stdout)
            labels = data["Labels"]
            if data["Name"] != self.volume_name or data["Driver"] != "local" or labels.get("autospec.run_id") != self.owner or labels.get("autospec.kind") != "validation-state":
                raise ValueError("Volume ownership mismatch")
            return {key: data[key] for key in ("Name", "Driver", "CreatedAt", "Labels")}
        except (KeyError, TypeError, ValueError) as exc:
            raise _unavailable("Validation volume identity cannot be verified") from exc

    def _assert_volume(self) -> None:
        if self.volume_identity is None or self._volume_attestation() != self.volume_identity:
            raise _unavailable("Validation volume identity changed; refusing access or removal")

    def _create_volume(self) -> None:
        # docker volume create adopts existing names: preflight + random name +
        # labels/CreatedAt attestation reject foreign volumes rather than adopt.
        if self._volume_attestation() is not None:
            raise _unavailable("Validation volume name is already occupied")
        self.volume_requested = True
        rc, out, err = _run_tracked([self.docker, "volume", "create", "--driver", "local",
                                     "--label", f"autospec.run_id={self.owner}", "--label", "autospec.kind=validation-state",
                                     self.volume_name], "", None, 10)
        if rc or out.strip() != self.volume_name:
            raise _unavailable(f"Validation volume creation failed: {out} {err}")
        self.volume_identity = self._volume_attestation()
        if self.volume_identity is None:
            raise _unavailable("Validation volume creation could not be attested")
        # A single trusted chown/chmod initializes a NEW empty volume. No source
        # mount, network, credentials, recursive chown, hooks or package tools.
        init_name = "autospec-sandbox-" + uuid.uuid4().hex
        argv = docker_run_cmd(["/bin/sh", "-c", "chmod 700 /var/lib/autospec-validation && chown 65532:65532 /var/lib/autospec-validation"],
                              str(self.stage), self.image, self.docker, run_id=self.owner, container_name=init_name)
        index = argv.index("-v")
        del argv[index:index + 2]
        index = argv.index("-w")
        del argv[index:index + 2]
        argv[argv.index("--user") + 1] = "0:0"
        index = argv.index("--entrypoint")
        argv[index:index] = ["--cap-add", "CHOWN", "--mount", self._volume_mount()]
        try:
            rc, out, err = _run_tracked(argv, "", None, 15)
            if rc:
                raise _unavailable(f"Validation volume initialization failed: {out} {err}")
        finally:
            _cleanup_container(self.docker, init_name, self.owner)

    def _volume_mount(self) -> str:
        self._assert_volume()
        return f"type=volume,source={self.volume_name},target={self.DATABASE_DIRECTORY},volume-nocopy"

    def _launch(self) -> None:
        if not self.mount_stage:
            result = _docker_call([self.docker, "image", "inspect", self.image, "--format", "{{.Id}} {{.Config.WorkingDir}}"],
                                  capture_output=True, text=True, timeout=3, check=False)
            if result.returncode or result.stdout.strip() != self.image + " /app":
                raise _unavailable("Baked runtime image identity/working directory differs")
        command = _node_command(self.command) if self.ecosystem == "node" else self.command
        argv = docker_run_cmd(command, str(self.stage), self.image, self.docker, run_id=self.owner, container_name=self.name)
        argv.remove("--rm")  # retain exit/log evidence until owned explicit cleanup
        argv.insert(2, "-d")
        index = argv.index("-v")
        if self.mount_stage:
            argv[index + 1] = argv[index + 1].removesuffix(":rw") + ":ro"
        else:
            del argv[index:index + 2]  # execute baked /app, not host source/config
        at = argv.index("--entrypoint")
        argv[at:at] = [piece for key, value in self.env.items() for piece in ("--env", f"{key}={value}")]
        if self.persistent_database:
            at = argv.index("--entrypoint")
            argv[at:at] = ["--mount", self._volume_mount()]
        rc, out, err = _run_tracked(argv, "", None, 15)
        if rc:
            raise _unavailable(f"Runtime container failed: {out} {err}")
        self.identifier = _container_identity(self.docker, self.name, self.owner)
        if self.identifier is None or out.strip() != self.identifier:
            raise _unavailable("Runtime container launch identity absent or mismatched")
        self.transition = False

    def _assert_owned(self) -> str:
        if self.closed or self.transition or self.identifier is None:
            raise _unavailable("Runtime is not active")
        if _container_identity(self.docker, self.identifier, self.owner) != self.identifier:
            raise _unavailable("Runtime immutable container identity is no longer owned")
        return self.identifier

    def open_control_port(self, target_port: int):
        """Factory-only browser control ingress; never exposed to model tools."""
        from .container_tunnel import OwnedControlTunnel
        tunnel = OwnedControlTunnel(self, target_port)
        try:
            return tunnel.__enter__()
        except BaseException:
            tunnel.close()
            raise

    def exec(self, argv: list[str], *, stdin: str = "", timeout: float = 30) -> tuple[int, str, str]:
        """Execute source-reviewed supervisor argv, only in the owned container.

        Never forwards env, host cwd or copy-back. Not available to model tools.
        The caller owns migration/seed authorization and interprets outputs.
        """
        if not argv or any(not isinstance(value, str) or "\x00" in value for value in argv) or argv[0].startswith("-"):
            raise _unavailable("Invalid supervisor exec argv")
        if not isinstance(stdin, str) or not math.isfinite(timeout) or timeout <= 0:
            raise _unavailable("Invalid supervisor exec input/timeout")
        with self.operation_lock:
            identifier = self._assert_owned()
            if self.persistent_database:
                self._assert_volume()
            try:
                result = _run_tracked([self.docker, "exec", "-i", identifier, *argv], stdin, None, timeout)
                if result[0] == -1:
                    self.close()
                return result
            except BaseException:
                # Killing only the host docker-exec client does NOT terminate
                # a daemon-side exec or its descendants. End the exact owned
                # container on timeout/cancellation before propagating failure.
                self.close()
                raise

    def is_running(self) -> bool:
        """Fresh exact-ID liveness; never infer running from docker run exit0."""
        with self.operation_lock:
            if self.closed or self.transition or self.identifier is None:
                return False
            if _container_identity(self.docker, self.identifier, self.owner) is None:
                return False
            result = _docker_call([self.docker, "container", "inspect", self.identifier, "--format", "{{json .State}}"],
                                  capture_output=True, text=True, timeout=3, check=False)
            try:
                return result.returncode == 0 and json.loads(result.stdout).get("Running") is True
            except (ValueError, TypeError, AttributeError) as exc:
                raise _unavailable("Runtime liveness could not be attested") from exc

    def _disconnect(self) -> None:
        with self.lock:
            clients, sockets = list(self.clients), list(self.sockets)
        for connection in sockets:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        for process in clients:
            close_owned_process(process)

    def restart(self) -> "RuntimeSession":
        """Same origin/owned DB, new independently attested container identity."""
        with self.operation_lock:
            self.detach()
            return self.attach()

    def detach(self) -> dict:
        """Remove this container only, preserve owned DB until attach/close."""
        with self.operation_lock:
            identifier = self._assert_owned()
            if self.persistent_database:
                self._assert_volume()
            self.transition = True
            self._disconnect()
            _cleanup_container(self.docker, identifier, self.owner)
            self.identifier = None
            self.detached = True
            return {"version": 1, "container_id": identifier, "origin": self.origin,
                    "volume": json.loads(json.dumps(self.volume_identity)), "database_url": self.database_url}

    def attach(self) -> "RuntimeSession":
        with self.operation_lock:
            if self.closed or not self.detached or self.thread is None:
                raise _unavailable("Runtime attach requires an owned detached session")
            if self.persistent_database:
                self._assert_volume()
            self.name = "autospec-sandbox-" + uuid.uuid4().hex
            try:
                require_sandbox(self.stage, self.image, docker=self.docker)
                self._launch()
                self.detached = False
            except BaseException:
                self.close()
                raise
            return self

    def inspect_configuration(self) -> dict:
        """Fresh owned exact-ID configuration, no secret env/source contents."""
        with self.operation_lock:
            identifier = self._assert_owned()
            if self.persistent_database:
                self._assert_volume()
            result = _docker_call([self.docker, "container", "inspect", identifier],
                                  capture_output=True, text=True, timeout=3, check=False)
            try:
                data = json.loads(result.stdout)[0]
                labels = data["Config"]["Labels"]
                if result.returncode or data["Id"] != identifier or labels.get("autospec.run_id") != self.owner or labels.get("autospec.kind") != "sandbox":
                    raise ValueError("Container identity changed")
                if self.image.startswith("sha256:") and data["Image"] != self.image:
                    raise ValueError("Runtime image differs")
                config = data["HostConfig"]
                return {"version": 1, "container_id": identifier, "owner": self.owner, "image_id": data["Image"],
                        "running": data["State"]["Running"], "user": data["Config"]["User"],
                        "read_only": config["ReadonlyRootfs"], "cap_drop": config["CapDrop"],
                        "privileged": config["Privileged"], "security_opt": config["SecurityOpt"],
                        "network_mode": config["NetworkMode"], "published_ports": config.get("PortBindings") or {},
                        "mounts": [{"type": mount["Type"], "destination": mount["Destination"], "rw": mount["RW"],
                                    "name": mount.get("Name"), "source": mount["Source"]} for mount in data["Mounts"]],
                        "volume": json.loads(json.dumps(self.volume_identity))}
            except (KeyError, TypeError, ValueError, IndexError) as exc:
                raise _unavailable("Owned runtime configuration cannot be attested") from exc

    def _forward(self, connection: socket.socket) -> None:
        if not self.capacity.acquire(blocking=False):
            return
        process = None
        connection.settimeout(self.timeout)
        with self.lock:
            self.sockets.add(connection)
        try:
            peer = str(ipaddress.IPv4Address(connection.getpeername()[0]))
            if not ipaddress.IPv4Address(peer).is_loopback:
                raise _unavailable("Runtime ingress must have a kernel-attested IPv4 loopback peer")
            # No host code from the product: argv and forwarding program are
            # factory constants, aimed at an immutable attested container ID.
            if self.ecosystem == "python":
                code = ("import socket,sys,threading; s=socket.create_connection(('127.0.0.1'," + str(self.port) + "),2,source_address=(" + repr(peer) + ",0)); "
                        "exec(\"def upload():\\n try:\\n  while True:\\n   b=sys.stdin.buffer.read1(65536)\\n   if not b: break\\n   s.sendall(b)\\n except OSError: pass\\n finally:\\n  try: s.shutdown(socket.SHUT_WR)\\n  except OSError: pass\\n\"); "
                        "threading.Thread(target=upload,daemon=True).start(); "
                        "exec(\"while True:\\n b=s.recv(65536)\\n if not b: break\\n sys.stdout.buffer.write(b); sys.stdout.buffer.flush()\\n\")")
                # Isolated BASE interpreter: generated socket.py/threading.py
                # or site customization cannot replace the ingress transport.
                bridge = ["/usr/local/bin/python", "-I", "-u", "-c", code]
            else:
                bridge = ["node", "-e", f"const s=require('net').connect({{port:{self.port},host:'127.0.0.1',localAddress:{json.dumps(peer)}}});s.on('connect',()=>{{process.stdin.pipe(s);s.pipe(process.stdout);}});s.on('error',()=>process.exit(1));s.on('close',()=>process.exit());"]
            with self.operation_lock:
                identifier = self._assert_owned()
                process = spawn_owned_process([self.docker, "exec", "--workdir", "/tmp", "-i", identifier, *bridge],
                                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
                with self.lock:
                    self.clients.add(process)
            timer = threading.Timer(self.timeout, close_owned_process, args=(process,))
            timer.start()
            def upload():
                try:
                    while data := connection.recv(65536):
                        process.stdin.write(data)
                        process.stdin.flush()
                except (OSError, ValueError):
                    pass
                finally:
                    try:
                        process.stdin.close()
                    except (OSError, ValueError):
                        pass
            uploader = threading.Thread(target=upload, daemon=True)
            uploader.start()
            try:
                while data := process.stdout.read1(65536):
                    connection.sendall(data)
            finally:
                timer.cancel()
                connection.shutdown(socket.SHUT_RDWR)
                uploader.join(timeout=1)
        except (OSError, ValueError, RuntimeError):
            pass
        finally:
            if process is not None:
                close_owned_process(process)
                with self.lock:
                    self.clients.discard(process)
                for stream in (process.stdin, process.stdout):
                    if stream is not None and not stream.closed:
                        stream.close()
            with self.lock:
                self.sockets.discard(connection)
            self.capacity.release()

    def logs(self) -> str:
        if self.closed or self.identifier is None:
            return ""
        with self.operation_lock:
            identifier = self._assert_owned()
            result = _docker_call([self.docker, "logs", "--tail", "100", identifier], capture_output=True, text=True, timeout=3, check=False)
            return (result.stdout + result.stderr)[-12000:]

    def close(self):
        with self.operation_lock:
            self._close_owned()

    def _close_owned(self):
        if self.thread is not None and self.server is not None:
            self.server.shutdown()
            self.thread.join(timeout=2)
            self.thread = None
        if self.server is not None:
            self.server.server_close()
            self.server = None
        with self.operation_lock:
            if self.closed:
                return
            self.transition = True
            self._disconnect()
            _cleanup_container(self.docker, self.identifier or self.name, self.owner)
            if self.volume_requested:
                current = self._volume_attestation()
                if current is not None:
                    # Creation may have reached the daemon before cancellation
                    # or a client timeout. Only our requested UUID/labels may
                    # be recovered; a replaced attested volume is never adopted.
                    if self.volume_identity is not None and current != self.volume_identity:
                        raise _unavailable("Validation volume identity changed; refusing removal")
                    result = _docker_call([self.docker, "volume", "rm", self.volume_name], capture_output=True, text=True, timeout=5, check=False)
                    if result.returncode:
                        raise _unavailable("Owned validation volume cleanup failed")
                self.volume_identity = None
                self.volume_requested = False
            self.closed = True

    def __exit__(self, *_):
        self.close()
