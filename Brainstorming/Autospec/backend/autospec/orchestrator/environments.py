"""REM-05: locked clean environments and attested cache reuse.

The supervisor cache must be outside the product's writable root (REM-01 owns
enforcement of that boundary). Each use verifies installed-file hashes, not an
agent's claim that a venv is clean. Source is copied to a disposable run root;
no product venv/node_modules is ever reused. No provider credentials are copied.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import sys
import tomllib
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .dependencies import atomic_json, file_lock, run_command


class EnvironmentError(RuntimeError):
    pass


def minimal_environment() -> dict[str, str]:
    allowed = ("PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP", "HOME", "USERPROFILE", "LOCALAPPDATA")
    env = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    env.update(PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1", UV_NO_CONFIG="1", UV_LINK_MODE="copy", npm_config_ignore_scripts="true", npm_config_audit="false", npm_config_fund="false")
    return env


def tree_hashes(root: Path) -> dict[str, str]:
    out = {}
    if not root.exists():
        raise EnvironmentError(f"environment content missing: {root.name}")
    for path in sorted(root.rglob("*")):
        # Python bytecode is incidental, never installed source. All other
        # package/executable files and additional distributions are attested.
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        if path.is_symlink() and path.is_dir():
            raise EnvironmentError("symlinked environment directory is not attestable")
        if path.is_file():
            out[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def source_hash(root: Path) -> str:
    entries = []
    for path in sorted(root.rglob("*")):
        if any(_excluded(part) for part in path.relative_to(root).parts):
            continue
        if path.is_file():
            entries.append((path.relative_to(root).as_posix(), hashlib.sha256(path.read_bytes()).hexdigest()))
    return hashlib.sha256(json.dumps(entries, separators=(",", ":")).encode()).hexdigest()


_EXCLUDED = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "artifacts", ".claude", ".codex", ".agents", ".aws", ".ssh", ".azure", ".npmrc", ".pypirc", ".netrc", "credentials", "credentials.json", ".credentials.json", "secrets", "auth.json", "tokens.json", "id_rsa", "id_ed25519", ".autospec", "autospec-state.json", "build-monitor.jsonl", "autospec-interactions.jsonl", "acceptance-contract.json", "contract-baseline.json", "independent-oracle", "verification-snapshot"}


def _excluded(name: str) -> bool:
    name = name.lower()
    return name in _EXCLUDED or name.startswith(".env")


@dataclass(frozen=True)
class CleanEnvironment:
    ecosystem: str
    mode: str
    fingerprint: str
    cache_path: Path
    attestation: dict
    reused: bool

    @property
    def python(self) -> Path:
        return self.cache_path / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")

    def verify(self) -> None:
        content = self.cache_path / (".venv" if self.ecosystem == "python" else "node_modules")
        if tree_hashes(content) != self.attestation["installed_files"]:
            raise EnvironmentError("ENVIRONMENT_DRIFT: cached installed files changed")

    def stage_project(self, project_root: Path, run_root: Path) -> Path:
        """Copy a fresh source snapshot, excluding producer environments/secrets.

        The caller owns/deletes run_root and must place independent tests outside
        writable agent scope. It must keep agent execution out of the cache.
        """
        self.verify()
        project_root, run_root = Path(project_root).resolve(), Path(run_root).resolve()
        if run_root.exists() or run_root.is_relative_to(project_root) or project_root.is_relative_to(run_root):
            raise EnvironmentError("run root must be a new separate disposable directory")
        names = ("pyproject.toml", "uv.lock") if self.ecosystem == "python" else ("package.json", "package-lock.json")
        for name in names:
            digest = hashlib.sha256((project_root / name).read_bytes()).hexdigest()
            if digest != self.attestation["inputs"]["files"][name]:
                raise EnvironmentError("ENVIRONMENT_INPUT_CHANGED: prepare the new manifest/lock first")
        def ignore(directory, names):
            return [n for n in names if _excluded(n)]
        # Refuse links escaping the source snapshot instead of following a
        # product-created link into another project or supervisor credentials.
        for path in project_root.rglob("*"):
            if any(_excluded(part) for part in path.relative_to(project_root).parts):
                continue
            stat = path.lstat()
            if path.is_symlink() or getattr(path, "is_junction", lambda: False)() or getattr(stat, "st_file_attributes", 0) & 0x400:
                raise EnvironmentError("source symlink/reparse point is not admissible")
            if path.is_file() and stat.st_nlink > 1:
                raise EnvironmentError("source hardlink is not admissible")
        shutil.copytree(project_root, run_root, ignore=ignore)
        if self.ecosystem == "node":
            shutil.copytree(self.cache_path / "node_modules", run_root / "node_modules")
        atomic_json(run_root / ".autospec-environment.json", {"version": 1, "fingerprint": self.fingerprint, "snapshot_hash": source_hash(project_root), "mode": self.mode, "inputs": self.attestation["inputs"]})
        return run_root

    def test_command(self, report_path: str, *, frontend: bool = False, node_cmd: str = "node") -> list[str]:
        if self.mode != "tests":
            raise EnvironmentError("runtime environment cannot attest a test suite")
        if self.ecosystem == "python":
            return [str(self.python), "-m", "pytest", "-q", "--json-report", f"--json-report-file={report_path}"]
        if frontend:
            return [node_cmd, "node_modules/vitest/vitest.mjs", "run", "--reporter=default", "--reporter=json", f"--outputFile.json={report_path}"]
        return [node_cmd, "--test", "--test-reporter=tap"]


class CleanEnvironmentManager:
    def __init__(self, cache_root: Path, runner: Callable = run_command, *, uv_cmd: str = "uv", npm_cmd: str = "npm", node_cmd: str = "node", python_cmd: str = sys.executable):
        self.cache_root = Path(cache_root).resolve()
        self.runner = runner
        self.uv_cmd, self.npm_cmd, self.node_cmd, self.python_cmd = uv_cmd, npm_cmd, node_cmd, python_cmd

    def tool_versions(self, ecosystem: str) -> dict[str, str]:
        commands = {"uv": [self.uv_cmd, "--version"], "python": [self.python_cmd, "--version"]} if ecosystem == "python" else {"node": [self.node_cmd, "--version"], "npm": [self.npm_cmd, "--version"]}
        versions = {}
        for tool, argv in commands.items():
            result = self.runner(argv, cwd=self.cache_root, env=minimal_environment())
            if result.returncode or not result.stdout.strip():
                raise EnvironmentError(f"TOOLCHAIN_UNAVAILABLE: {tool}")
            versions[tool] = result.stdout.strip()
        return versions

    def prepare(self, project_root: Path, ecosystem: str, mode: str = "tests", *, tool_versions: dict[str, str] | None = None, platform_id: str | None = None) -> CleanEnvironment:
        root = Path(project_root).resolve()
        if ecosystem not in ("python", "node") or mode not in ("runtime", "tests"):
            raise EnvironmentError("unsupported ecosystem or environment mode")
        if self.cache_root.is_relative_to(root) or root.is_relative_to(self.cache_root):
            raise EnvironmentError("cache must be outside producer writable root")
        self.cache_root.mkdir(parents=True, exist_ok=True)
        names = ("pyproject.toml", "uv.lock") if ecosystem == "python" else ("package.json", "package-lock.json")
        for name in names:
            if not (root / name).is_file() or not (root / name).resolve().is_relative_to(root):
                raise EnvironmentError(f"DECLARATION_MISSING: {name}")
        versions = tool_versions or self.tool_versions(ecosystem)
        required = {"uv", "python"} if ecosystem == "python" else {"node", "npm"}
        if not required <= versions.keys() or any(not versions[key] for key in required):
            raise EnvironmentError("toolchain versions are required")
        inputs = {"ecosystem": ecosystem, "mode": mode, "files": {n: hashlib.sha256((root / n).read_bytes()).hexdigest() for n in names}, "tool_versions": versions, "tool_commands": {"uv": self.uv_cmd, "npm": self.npm_cmd, "node": self.node_cmd, "python": self.python_cmd}, "platform": platform_id or f"{sys.platform}/{platform.machine()}/{platform.python_implementation()}"}
        fingerprint = hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()
        # Full identity stays in the attestation. Compact names avoid uv's
        # Windows MAX_PATH failures for wheel metadata under deep test roots;
        # any theoretical prefix collision fails the exact-input check below.
        cache = self.cache_root / fingerprint[:24]
        with file_lock(self.cache_root / f"{fingerprint}.lock", timeout=180):
            marker = cache / "attestation.json"
            if marker.exists():
                attestation = json.loads(marker.read_text(encoding="utf-8"))
                if attestation.get("version") != 1 or attestation.get("inputs") != inputs or attestation.get("clean_creation") is not True:
                    raise EnvironmentError("CACHE_ATTESTATION_INVALID")
                env = CleanEnvironment(ecosystem, mode, fingerprint, cache, attestation, True)
                env.verify()
                return env
            # Create at its FINAL absolute path: Python virtualenv launchers
            # embed their location and must never be renamed after creation.
            # Failed/incomplete paths are never reused or promoted to ready.
            if cache.exists():
                raise EnvironmentError("CACHE_INCOMPLETE: supervisor cleanup required")
            cache.mkdir()
            for name in names:
                shutil.copy2(root / name, cache / name)
            child_env = minimal_environment()
            if ecosystem == "python":
                child_env["UV_PROJECT_ENVIRONMENT"] = str(cache / ".venv")
                data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
                optional_dev = "dev" in data.get("project", {}).get("optional-dependencies", {})
                flags = ["--extra", "dev"] if mode == "tests" and optional_dev else ["--no-dev"] if mode == "runtime" else []
                # uv also includes a declared PEP 735 dev group by default.
                command = [self.uv_cmd, "sync", "--locked", "--no-build", "--no-install-project", "--python", self.python_cmd, *flags]
            else:
                command = [self.npm_cmd, "ci", "--ignore-scripts", *(["--include=dev"] if mode == "tests" else ["--omit=dev"])]
            try:
                result = self.runner(command, cwd=cache, env=child_env)
                if result.returncode:
                    diagnostics = (result.stdout or "") + (getattr(result, "stderr", "") or "")
                    raise EnvironmentError(f"CLEAN_INSTALL_FAILED: exit {result.returncode}; {diagnostics[-2000:]}")
                content = cache / (".venv" if ecosystem == "python" else "node_modules")
                if ecosystem == "node" and not content.exists():
                    # npm legitimately creates no node_modules for no deps.
                    content.mkdir()
                if ecosystem == "python":
                    cfg = (content / "pyvenv.cfg").read_text(encoding="utf-8").lower()
                    if "include-system-site-packages = false" not in cfg:
                        raise EnvironmentError("venv inherits host site packages")
                attestation = {"version": 1, "fingerprint": fingerprint, "inputs": inputs, "clean_creation": True, "creation_id": uuid.uuid4().hex, "command": command, "installed_files": tree_hashes(content)}
                atomic_json(marker, attestation)
            except Exception:
                # Preserve failed files for diagnostics; no recursive cleanup
                # of a computed path and no reuse of half-built environments.
                raise
            return CleanEnvironment(ecosystem, mode, fingerprint, cache, attestation, False)
