"""Trusted Linux dependency images; no generated Dockerfile or host toolchain.

Only registry manifests/locks enter the builder. Package hooks and source builds
are disabled. Generated source enters a disposable, filtered runtime stage only.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from packaging.requirements import Requirement

from ..agents.file_broker import ExecutionContext, FileBroker, IsolationViolation
from ..agents.runner import AgentError, _run_tracked
from .dependencies import atomic_json, file_lock
from .environments import _excluded
from .sandbox import _docker_call, _unavailable

BASE_IMAGES = {"python": "ghcr.io/astral-sh/uv:python3.12-bookworm-slim",
               "node": "node:22-bookworm-slim"}
RECIPE_VERSION = 4
FACTORY_FILES = {".autospec-bootstrap.json", ".autospec-environment.json", ".mcp.json",
                 "claude.md", "agents.md", "gemini.md"}


def dependency_resolver(argv: list[str], *, cwd: Path, env=None) -> subprocess.CompletedProcess:
    """DependencyCoordinator runner: manifest-only Linux resolution/export.

    The coordinator already holds its serialized root lock. No supplied host
    environment, package config, source, script, or credentials is inherited.
    """
    from ..config import settings
    if len(argv) < 2:
        raise _unavailable("Unsupported dependency resolution command")
    operation = argv[1]
    ecosystem = "python" if operation in {"add", "lock"} else "node" if operation == "install" else ""
    if not ecosystem:
        raise _unavailable("Only coordinator uv add/lock and npm lock-only are admitted")
    if ecosystem == "python":
        if operation == "lock" and argv[2:] != ["--check", "--no-build"]:
            raise _unavailable("Only locked check is admitted")
        if operation == "add":
            options = argv[2:-1]
            if options not in (["--no-sync", "--no-build"], ["--no-sync", "--no-build", "--optional", "dev"]) or Requirement(argv[-1]).url:
                raise _unavailable("Invalid coordinator Python add")
        command = ["uv", *argv[1:], "--no-config"]
    else:
        options = argv[2:-1]
        if options not in (["--package-lock-only", "--ignore-scripts", "--save-dev"], ["--package-lock-only", "--ignore-scripts", "--save-prod"]) or not re.fullmatch(r"(?:@[a-zA-Z0-9_.-]+/)?[a-zA-Z0-9_.-]+@[0-9A-Za-z.*<>=~^|+ \-]+", argv[-1]):
            raise _unavailable("Invalid coordinator Node add")
        command = ["npm", *argv[1:], "--no-audit", "--no-fund", "--userconfig=/dev/null", "--globalconfig=/tmp/autospec-empty-global-npmrc"]
    root = Path(cwd)
    manifest, lock = admit_manifest(root, ecosystem, require_lock=False)
    manager = LinuxEnvironmentManager(Path(tempfile.gettempdir()).resolve() / "autospec-linux-environments", docker=settings.docker_cmd)
    base = manager._base(ecosystem)
    with tempfile.TemporaryDirectory(prefix="autospec-dependency-") as temporary:
        stage = Path(temporary).resolve()
        shutil.copyfile(manifest, stage / manifest.name)
        if lock.exists():
            shutil.copyfile(lock, stage / lock.name)
        from .sandbox import docker_run_cmd, _cleanup_container
        import uuid
        owner, name = uuid.uuid4().hex, "autospec-sandbox-" + uuid.uuid4().hex
        args = docker_run_cmd(command, str(stage), base["Id"], settings.docker_cmd, run_id=owner, container_name=name)
        args[args.index("--network") + 1] = "bridge"  # manifest-only networking phase
        try:
            rc, out, err = _run_tracked(args, "", str(stage), manager.timeout)
            if rc == 0:
                admit_manifest(stage, ecosystem)
                source = FileBroker(ExecutionContext("dependency-export", stage))
                target = FileBroker(ExecutionContext("dependency-target", root))
                changes = []
                for name in (manifest.name, lock.name):
                    src, dest = source.path(name), target.path(name)
                    if src.stat().st_size > 20_000_000:
                        raise _unavailable("Dependency export limit exceeded")
                    changes.append((dest, src.read_bytes()))
                from .dependencies import atomic_bytes
                for path, data in changes:
                    atomic_bytes(path, data)
            return subprocess.CompletedProcess(argv, rc, out, err)
        finally:
            _cleanup_container(settings.docker_cmd, name, owner)


def snapshot_product(root: Path, target: Path) -> Path:
    """Copy regular product files only, with no metadata/credentials/deps.

    Never copy links (even internal), junctions, hardlinks or special files.
    This is also the export policy: no unrestricted copy-back is provided.
    """
    context = ExecutionContext("linux-stage", Path(root))
    broker = FileBroker(context)
    target = Path(target).resolve()
    if target.exists() or target.resolve().is_relative_to(context.project_root):
        raise IsolationViolation("stage must be new and outside product root")
    target.mkdir(parents=True)
    target.chmod(0o777)
    try:
        for parent, dirs, files in os.walk(context.project_root, followlinks=False):
            dirs[:] = [n for n in dirs if not _excluded(n) and n.lower() not in FACTORY_FILES]
            for name in [*dirs, *files]:
                if _excluded(name) or name.lower() in FACTORY_FILES:
                    continue
                path = Path(parent) / name
                relative = path.relative_to(context.project_root).as_posix()
                broker.path(relative)
                info = path.lstat()
                if path.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
                    raise IsolationViolation(f"link/reparse denied: {relative}")
                out = target / relative
                if stat.S_ISDIR(info.st_mode):
                    out.mkdir(exist_ok=True)
                    out.chmod(0o777)
                elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
                    out.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(path, out)
                    out.chmod(0o666)
                else:
                    raise IsolationViolation(f"non-regular/hardlink denied: {relative}")
        return target
    except BaseException:
        shutil.rmtree(target)
        raise


def _registry_url(url: str, ecosystem: str) -> None:
    parsed = urlparse(url)
    allowed = {"pypi.org", "files.pythonhosted.org"} if ecosystem == "python" else {"registry.npmjs.org"}
    if parsed.scheme != "https" or parsed.hostname not in allowed or parsed.username or parsed.password:
        raise _unavailable("Only credential-free public registry dependencies are supported")


def admit_manifest(root: Path, ecosystem: str, *, require_lock: bool = True,
                   validate_existing_lock: bool = True) -> tuple[Path, Path]:
    broker = FileBroker(ExecutionContext("dependency-manifest", Path(root)))
    names = ("pyproject.toml", "uv.lock") if ecosystem == "python" else ("package.json", "package-lock.json")
    manifest, lock = (broker.path(n) for n in names)
    if not manifest.is_file() or require_lock and not lock.is_file():
        raise _unavailable("A manifest and locked dependencies are required")
    if ecosystem == "python":
        data = tomllib.loads(manifest.read_text(encoding="utf-8"))
        uv = data.get("tool", {}).get("uv", {})
        safe_uv = {"package", "managed", "dev-dependencies", "override-dependencies", "constraint-dependencies",
                   "environments", "required-environments"}
        if set(uv) - safe_uv:
            raise _unavailable("Custom/local Python sources or uv configuration are not supported in clean validation")
        dependencies = [*data.get("project", {}).get("dependencies", [])]
        for group in data.get("project", {}).get("optional-dependencies", {}).values():
            dependencies.extend(group)
        for group in data.get("dependency-groups", {}).values():
            dependencies.extend(x for x in group if isinstance(x, str))
        for key in ("dev-dependencies", "override-dependencies", "constraint-dependencies"):
            dependencies.extend(uv.get(key, []))
        if any(Requirement(value).url for value in dependencies):
            raise _unavailable("Direct URL Python dependencies are not supported")
        if lock.exists() and validate_existing_lock:
            locked = tomllib.loads(lock.read_text(encoding="utf-8"))
            for package in locked.get("package", []):
                source = package.get("source", {})
                if source == {"editable": "."} or source == {"virtual": "."}:
                    continue  # own project is deliberately NOT installed
                if set(source) != {"registry"}:
                    raise _unavailable("Local/git Python lock sources are denied")
                _registry_url(source["registry"], ecosystem)
                for distribution in [package.get("sdist", {}), *package.get("wheels", [])]:
                    if distribution.get("url"):
                        _registry_url(distribution["url"], ecosystem)
    elif ecosystem == "node":
        data = json.loads(manifest.read_text(encoding="utf-8"))
        if data.get("workspaces"):
            raise _unavailable("Node workspaces require a separate vetted builder")
        if data.get("overrides") or data.get("resolutions"):
            raise _unavailable("Node dependency overrides require a separately admitted resolver")
        for key in ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies"):
            for version in data.get(key, {}).values():
                if not isinstance(version, str) or not re.fullmatch(r"[0-9A-Za-z.*<>=~^|+ \-]+", version):
                    raise _unavailable("Non-registry Node dependencies are denied")
        if lock.exists() and validate_existing_lock:
            locked = json.loads(lock.read_text(encoding="utf-8"))
            if locked.get("lockfileVersion") not in {2, 3} or not isinstance(locked.get("packages"), dict):
                raise _unavailable("Only structured npm lock v2/v3 is supported")
            for package in locked["packages"].values():
                if package.get("link"):
                    raise _unavailable("Node lock links are denied")
                if package.get("resolved"):
                    _registry_url(package["resolved"], ecosystem)
    else:
        raise _unavailable(f"Unsupported isolated ecosystem: {ecosystem}")
    return manifest, lock


@dataclass(frozen=True)
class LinuxEnvironment:
    ecosystem: str
    mode: str
    fingerprint: str
    image: str
    attestation: dict


class LinuxEnvironmentManager:
    def __init__(self, cache_root: Path, *, docker: str = "docker", timeout: float = 300,
                 base_images: dict[str, str] | None = None):
        self.cache_root = Path(cache_root).absolute()
        self.docker = docker
        self.timeout = timeout
        self.base_images = dict(base_images or BASE_IMAGES)

    def _image(self, image: str) -> dict:
        result = _docker_call([self.docker, "image", "inspect", image], capture_output=True,
                              text=True, timeout=10, check=False)
        try:
            data = json.loads(result.stdout)[0]
            if result.returncode or data["Os"] != "linux" or not re.fullmatch(r"sha256:[a-f0-9]{64}", data["Id"]):
                raise ValueError()
            return data
        except (ValueError, KeyError, IndexError):
            raise _unavailable("Trusted Linux toolchain image missing; provision it explicitly first")

    def _base(self, ecosystem: str) -> dict:
        result = _docker_call([self.docker, "info", "--format", "{{.OSType}}"],
                              capture_output=True, text=True, timeout=10, check=False)
        if result.returncode or result.stdout.strip() != "linux":
            raise _unavailable("Linux Docker engine is required; no host fallback")
        return self._image(self.base_images[ecosystem])

    def ensure_lock(self, root: Path, ecosystem: str) -> Path:
        """Resolve only admitted public dependencies, in a manifest-only container.

        No product source/config or lifecycle scripts enter this networking phase.
        Export precisely the lockfile, never any other builder-produced file.
        """
        return self._resolve_lock(root, ecosystem, replace=False)

    def regenerate_lock(self, root: Path, ecosystem: str) -> Path:
        """Merged manifest -> new admitted Linux lock, atomic exact replacement.

        Caller must hold its project dependency lock. The old lock is never
        removed/copied into the networking builder and survives every failure.
        Source/config/hooks/credentials cannot enter this manifest-only phase.
        """
        return self._resolve_lock(root, ecosystem, replace=True)

    def _resolve_lock(self, root: Path, ecosystem: str, *, replace: bool) -> Path:
        manifest, lock = admit_manifest(root, ecosystem, require_lock=False,
                                        validate_existing_lock=not replace)
        if lock.exists() and not replace:
            return lock
        original_manifest = manifest.read_bytes()
        original_lock = lock.read_bytes() if lock.exists() else None
        base = self._base(ecosystem)
        with tempfile.TemporaryDirectory(prefix="autospec-lock-") as temporary:
            stage = Path(temporary).resolve()
            shutil.copyfile(manifest, stage / manifest.name)
            name = "autospec-sandbox-" + __import__("uuid").uuid4().hex
            owner = __import__("uuid").uuid4().hex
            from .sandbox import docker_run_cmd, _cleanup_container
            command = ["uv", "lock", "--no-build", "--no-config"] if ecosystem == "python" else ["npm", "install", "--package-lock-only", "--ignore-scripts", "--no-audit", "--no-fund", "--userconfig=/dev/null", "--globalconfig=/tmp/autospec-empty-global-npmrc"]
            argv = docker_run_cmd(command, str(stage), base["Id"], self.docker, run_id=owner, container_name=name)
            # Network exists exclusively during resolution, manifest-only stage;
            # generated code and package scripts cannot run in this phase.
            argv[argv.index("--network") + 1] = "bridge"
            try:
                rc, out, err = _run_tracked(argv, "", str(stage), self.timeout)
                if rc:
                    raise _unavailable(f"Dependency lock resolution failed: {out[-2000:]} {err[-2000:]}")
                if (stage / manifest.name).read_bytes() != original_manifest:
                    raise _unavailable("Resolver changed the merged manifest; refusing unmatched lock export")
                admit_manifest(stage, ecosystem)
                published = FileBroker(ExecutionContext("lock-export", Path(root))).path(lock.name)
                source = FileBroker(ExecutionContext("lock-source", stage)).path(lock.name)
                if source.stat().st_size > 20_000_000:
                    raise _unavailable("Lockfile exceeds export limit")
                data = source.read_bytes()
                if manifest.read_bytes() != original_manifest:
                    raise _unavailable("Manifest changed during lock resolution; refusing stale export")
                if replace:
                    current = published.read_bytes() if published.exists() else None
                    if current != original_lock:
                        raise _unavailable("Lock changed during regeneration; refusing concurrent overwrite")
                    from .dependencies import atomic_bytes
                    atomic_bytes(published, data)
                else:
                    # Initial bootstrap may not overwrite a lock published by a
                    # concurrent coordinator. Regeneration is an explicit path.
                    with published.open("xb") as output:
                        output.write(data)
                return published
            finally:
                _cleanup_container(self.docker, name, owner)

    def prepare(self, root: Path, ecosystem: str, mode: str = "test") -> LinuxEnvironment:
        if mode not in {"test", "runtime"}:
            raise _unavailable("Validation mode must be test or runtime")
        root = Path(root).absolute()
        if self.cache_root.resolve().is_relative_to(root.resolve()):
            raise _unavailable("Environment cache must be outside producer writable root")
        manifest, lock = admit_manifest(root, ecosystem)
        base = self._base(ecosystem)
        identity = {"version": RECIPE_VERSION, "ecosystem": ecosystem, "mode": mode,
                    "manifest": hashlib.sha256(manifest.read_bytes()).hexdigest(),
                    "lock": hashlib.sha256(lock.read_bytes()).hexdigest(),
                    "toolchain_image": base["Id"], "platform": "linux/" + base["Architecture"],
                    "supervisor_reporter": "pytest-json-report==1.5.0 pytest-cov==7.0.0 coverage==7.10.6" if ecosystem == "python" and mode == "test" else "native"}
        digests = base.get("RepoDigests", [])
        if not digests or not re.fullmatch(r"[a-z0-9./:_-]+@sha256:[a-f0-9]{64}", digests[0]):
            raise _unavailable("Trusted base requires its immutable registry digest")
        identity["toolchain_digest"] = digests[0]
        identity["recipe_template_sha256"] = hashlib.sha256(
            self._recipe(digests[0], ecosystem, mode, "FINGERPRINT", manifest).encode()).hexdigest()
        fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        self.cache_root.mkdir(parents=True, exist_ok=True)
        cache = self.cache_root / fingerprint
        cache.mkdir(exist_ok=True)
        tag = f"autospec/clean-env:{fingerprint}"
        attestation = cache / "attestation.json"
        with file_lock(cache / "build.lock"):
            if attestation.is_file():
                saved = json.loads(attestation.read_text(encoding="utf-8"))
                try:
                    image = self._image(saved["image"])
                except AgentError:
                    image = None  # explicit repair rebuilds a lost local image
                if image is not None and saved.get("inputs") == identity and image.get("Config", {}).get("Labels", {}).get("autospec.environment") == fingerprint:
                    return LinuxEnvironment(ecosystem, mode, fingerprint, image["Id"], saved)
            # Context consists ONLY of these manifests plus factory-owned recipe.
            with tempfile.TemporaryDirectory(prefix="autospec-image-") as temporary:
                context = Path(temporary)
                shutil.copyfile(manifest, context / manifest.name)
                shutil.copyfile(lock, context / lock.name)
                recipe = self._recipe(digests[0], ecosystem, mode, fingerprint, manifest)
                (context / "Dockerfile").write_text(recipe, encoding="utf-8")
                rc, out, err = _run_tracked([self.docker, "build", "--pull=false", "--network=default", "--label", f"autospec.environment={fingerprint}", "-t", tag, "."], "", str(context), self.timeout)
                if rc:
                    raise _unavailable(f"Clean Linux dependency image failed: {out[-3000:]} {err[-3000:]}")
            image = self._image(tag)
            saved = {"inputs": identity, "image": image["Id"], "recipe_sha256": hashlib.sha256(recipe.encode()).hexdigest()}
            atomic_json(attestation, saved)
            return LinuxEnvironment(ecosystem, mode, fingerprint, image["Id"], saved)

    @staticmethod
    def _recipe(base: str, ecosystem: str, mode: str, fingerprint: str, manifest: Path) -> str:
        common = f"FROM {base}\nWORKDIR /opt/dependencies\n"
        if ecosystem == "python":
            project = tomllib.loads(manifest.read_text(encoding="utf-8"))
            dev = " --extra dev" if "dev" in project.get("project", {}).get("optional-dependencies", {}) and mode == "test" else ""
            common += "COPY pyproject.toml uv.lock ./\nENV UV_PROJECT_ENVIRONMENT=/opt/venv UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy\n"
            common += "RUN uv sync --locked --no-build --no-install-project --no-config" + dev + (" --no-dev" if mode == "runtime" else "") + "\n"
            if mode == "test":
                # Never query an interpreter into which untrusted project
                # wheels/.pth have been installed during the network phase.
                # The base interpreter installs pinned supervisor reporters
                # into a separate directory without transitive resolution.
                common += "RUN uv pip install --python /usr/local/bin/python --target /opt/reporters --no-deps --no-build --no-config pytest-json-report==1.5.0 pytest-cov==7.0.0 coverage==7.10.6\n"
                common += "ENV PYTHONPATH=/opt/reporters\n"
            common += 'ENV PATH="/opt/venv/bin:$PATH"\n'
        else:
            common += "COPY package.json package-lock.json ./\nRUN npm ci --ignore-scripts --no-audit --no-fund --userconfig=/dev/null --globalconfig=/tmp/autospec-empty-global-npmrc" + (" --omit=dev" if mode == "runtime" else " --include=dev") + "\n"
            common += "RUN mv node_modules /opt/node_modules\n"
            common += "RUN ln -s /tmp/vite-cache /opt/node_modules/.vite\n"
        return common + f"LABEL autospec.environment={fingerprint}\nWORKDIR /app\nUSER 65532:65532\n"
