"""REM-04: supervised, serialized manifest/lock dependency requests.

The producer never installs into its own venv to satisfy a request. The
coordinator owns this sidecar outside the product's writable root and invokes
the resolver under a manifest lock. Pending/rejected requests block admission.
Only uv/pyproject+uv.lock and npm/package+package-lock are supported explicitly.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import tomllib
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Callable


class DependencyError(RuntimeError):
    pass


def canonical_path(value: str) -> str:
    value = value.replace("\\", "/")
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ":" in value or any(p in ("", ".", "..") for p in value.split("/")):
        raise DependencyError(f"invalid relative path: {value!r}")
    return str(path)


def contained_path(root: Path, relative: str) -> Path:
    path = (root / canonical_path(relative)).resolve()
    if not path.is_relative_to(root.resolve()):
        raise DependencyError("path escapes project root")
    return path


def package_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


@dataclass(frozen=True)
class DependencyRequest:
    task_id: str
    ecosystem: str
    package: str
    constraint: str
    scope: str
    manifest: str
    lock: str
    reason: str = ""
    version: int = 1

    def __post_init__(self):
        if self.version != 1 or not self.task_id.strip() or self.ecosystem not in ("python", "node"):
            raise DependencyError("invalid dependency request identity/ecosystem/version")
        if self.scope not in ("runtime", "dev"):
            raise DependencyError("scope must be runtime or dev")
        pattern = r"[A-Za-z0-9][A-Za-z0-9_.-]*" if self.ecosystem == "python" else r"(?:@[a-z0-9_.-]+/)?[a-z0-9][a-z0-9_.-]*"
        if not re.fullmatch(pattern, self.package):
            raise DependencyError("invalid package name")
        # Registry version/range only: no URLs, paths, shell fragments or flags.
        if not re.fullmatch(r"[A-Za-z0-9.*+<>=!~^|, -]*", self.constraint) or self.constraint.startswith("-"):
            raise DependencyError("invalid version constraint")
        if self.ecosystem == "python" and self.constraint and not self.constraint.startswith(("<", ">", "=", "!", "~")):
            raise DependencyError("Python constraints must use a PEP 440 comparison")
        manifest, lock = canonical_path(self.manifest), canonical_path(self.lock)
        expected = ("pyproject.toml", "uv.lock") if self.ecosystem == "python" else ("package.json", "package-lock.json")
        if (PurePosixPath(manifest).name, PurePosixPath(lock).name) != expected or PurePosixPath(manifest).parent != PurePosixPath(lock).parent:
            raise DependencyError("unsupported manifest/lock pair")
        object.__setattr__(self, "manifest", manifest)
        object.__setattr__(self, "lock", lock)

    @property
    def request_id(self) -> str:
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()[:24]


def atomic_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, sort_keys=True, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


@contextmanager
def file_lock(path: Path, timeout: float = 30):
    """Cross-process lock, including Windows; no dependency on a provider."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as fh:
        fh.seek(0, 2)
        if fh.tell() == 0:
            fh.write(b"0")
            fh.flush()
        deadline = time.monotonic() + timeout
        while True:
            try:
                fh.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise DependencyError("manifest owner lock timed out")
                time.sleep(0.02)
        try:
            yield
        finally:
            fh.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def run_command(argv: list[str], *, cwd: Path, env: dict | None = None):
    if os.name == "nt" and Path(argv[0]).stem.lower() == "npm":
        npm_path = shutil.which(argv[0])
        if npm_path:
            cli = Path(npm_path).parent / "node_modules/npm/bin/npm-cli.js"
            node = shutil.which("node")
            if cli.is_file() and node:
                # Bypass npm.cmd's implicit shell, especially for version ranges.
                argv = [node, str(cli), *argv[1:]]
    return subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True, timeout=180, check=False)


def declared_dependencies(manifest: Path, ecosystem: str) -> dict[str, set[str]]:
    if ecosystem == "python":
        data = tomllib.loads(manifest.read_text(encoding="utf-8"))
        project = data.get("project", {})
        def names(specs):
            return {package_name(re.match(r"[A-Za-z0-9_.-]+", s).group()) for s in specs}
        runtime = names(project.get("dependencies", []))
        dev = names(project.get("optional-dependencies", {}).get("dev", []))
        dev |= names(data.get("dependency-groups", {}).get("dev", []))
        return {"runtime": runtime, "dev": dev}
    data = json.loads(manifest.read_text(encoding="utf-8"))
    return {"runtime": set(data.get("dependencies", {})), "dev": set(data.get("devDependencies", {}))}


def locked_dependencies(lock: Path, ecosystem: str) -> set[str]:
    if ecosystem == "python":
        data = tomllib.loads(lock.read_text(encoding="utf-8"))
        return {package_name(p["name"]) for p in data.get("package", [])}
    data = json.loads(lock.read_text(encoding="utf-8"))
    packages = data.get("packages", {})
    return {p.removeprefix("node_modules/") for p in packages if p.startswith("node_modules/")} | set(data.get("dependencies", {}))


class DependencyCoordinator:
    def __init__(self, project_root: Path, state_root: Path, runner: Callable = run_command, *, uv_cmd: str = "uv", npm_cmd: str = "npm"):
        self.root, self.state_root = Path(project_root).resolve(), Path(state_root).resolve()
        if self.state_root.is_relative_to(self.root):
            raise DependencyError("dependency state must be outside producer writable root")
        self.runner, self.uv_cmd, self.npm_cmd = runner, uv_cmd, npm_cmd
        self.state_file = self.state_root / "dependencies.json"
        self.lock_file = self.state_root / "dependencies.lock"

    def _load(self):
        if not self.state_file.exists():
            return {"version": 1, "project_root": str(self.root), "requests": {}}
        data = json.loads(self.state_file.read_text(encoding="utf-8"))
        if data.get("version") != 1 or data.get("project_root") != str(self.root):
            raise DependencyError("unsupported dependency sidecar version")
        return data

    def submit(self, request: DependencyRequest) -> dict:
        contained_path(self.root, request.manifest)
        contained_path(self.root, request.lock)
        with file_lock(self.lock_file):
            data = self._load()
            record = data["requests"].setdefault(request.request_id, {"request": asdict(request), "status": "pending", "reason": "awaiting manifest owner"})
            atomic_json(self.state_file, data)
            return dict(record)

    def records(self, task_id: str | None = None) -> list[dict]:
        with file_lock(self.lock_file):
            return [dict(r) for r in self._load()["requests"].values() if task_id is None or r["request"]["task_id"] == task_id]

    def resolve_pending(self, owner: str) -> list[dict]:
        if not owner.strip():
            raise DependencyError("manifest owner required")
        with file_lock(self.lock_file):
            data = self._load()
            for record in data["requests"].values():
                if record["status"] != "pending":
                    continue
                req = DependencyRequest(**record["request"])
                manifest, lock = contained_path(self.root, req.manifest), contained_path(self.root, req.lock)
                cwd = manifest.parent
                record["owner"] = owner
                try:
                    before = declared_dependencies(manifest, req.ecosystem)
                    spec = req.package + req.constraint if req.ecosystem == "python" else req.package + ("@" + req.constraint if req.constraint else "")
                    argv = [self.uv_cmd, "add", "--no-sync", "--no-build", *(["--optional", "dev"] if req.scope == "dev" else []), spec] if req.ecosystem == "python" else [self.npm_cmd, "install", "--package-lock-only", "--ignore-scripts", "--save-dev" if req.scope == "dev" else "--save-prod", spec]
                    result = self.runner(argv, cwd=cwd)
                    if result.returncode:
                        raise DependencyError(f"resolver exited {result.returncode}")
                    after = declared_dependencies(manifest, req.ecosystem)
                    target = package_name(req.package) if req.ecosystem == "python" else req.package
                    if target not in after[req.scope] or target not in locked_dependencies(lock, req.ecosystem):
                        raise DependencyError("requested dependency absent from correct manifest scope or lock")
                    if any(not before[scope] <= after[scope] for scope in before):
                        raise DependencyError("resolver removed an existing declared dependency")
                    if req.ecosystem == "python":
                        check = self.runner([self.uv_cmd, "lock", "--check", "--no-build"], cwd=cwd)
                        if check.returncode:
                            raise DependencyError("manifest/lock inconsistent")
                    else:
                        root_entry = json.loads(lock.read_text(encoding="utf-8")).get("packages", {}).get("")
                        if root_entry is None:
                            raise DependencyError("package-lock v2/v3 root entry required")
                        package_data = json.loads(manifest.read_text(encoding="utf-8"))
                        for field in ("dependencies", "devDependencies"):
                            if root_entry.get(field, {}) != package_data.get(field, {}):
                                raise DependencyError("manifest/lock root dependencies inconsistent")
                    record.update(status="applied", reason="manifest and lock resolved", manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(), lock_sha256=hashlib.sha256(lock.read_bytes()).hexdigest())
                except (OSError, ValueError, KeyError, AttributeError, DependencyError, subprocess.SubprocessError) as exc:
                    record.update(status="rejected", reason=str(exc))
                atomic_json(self.state_file, data)
            # A later serialized addition changes the same manifest/lock. All
            # previously applied requests are re-attested against the FINAL pair
            # so concurrent consumers keep their dependencies and proof identity.
            for record in data["requests"].values():
                if record["status"] != "applied":
                    continue
                req = DependencyRequest(**record["request"])
                manifest, lock = contained_path(self.root, req.manifest), contained_path(self.root, req.lock)
                name = package_name(req.package) if req.ecosystem == "python" else req.package
                if name not in declared_dependencies(manifest, req.ecosystem)[req.scope] or name not in locked_dependencies(lock, req.ecosystem):
                    record.update(status="rejected", reason="dependency lost during serialized resolution")
                else:
                    record.update(manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(), lock_sha256=hashlib.sha256(lock.read_bytes()).hexdigest())
            atomic_json(self.state_file, data)
            return [dict(r) for r in data["requests"].values()]

    def require_ready(self, task_id: str) -> None:
        for record in self.records(task_id):
            if record["status"] != "applied":
                raise DependencyError(f"DEPENDENCY_UNRESOLVED: {record['request']['package']} ({record['status']})")
            req = DependencyRequest(**record["request"])
            for field, relative in (("manifest", req.manifest), ("lock", req.lock)):
                actual = hashlib.sha256(contained_path(self.root, relative).read_bytes()).hexdigest()
                if actual != record[field + "_sha256"]:
                    raise DependencyError(f"DEPENDENCY_DRIFT: {relative}")
            name = package_name(req.package) if req.ecosystem == "python" else req.package
            if name not in declared_dependencies(contained_path(self.root, req.manifest), req.ecosystem)[req.scope] or name not in locked_dependencies(contained_path(self.root, req.lock), req.ecosystem):
                raise DependencyError(f"DEPENDENCY_DRIFT: {req.package}")
