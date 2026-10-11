from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from subprocess import CompletedProcess
import json
import time

import pytest

from autospec.orchestrator.dependencies import DependencyCoordinator, DependencyError, DependencyRequest


def request(task="AUTH", package="argon2-cffi", scope="runtime", ecosystem="python"):
    return DependencyRequest(task, ecosystem, package, ">=23" if ecosystem == "python" else "^1.0.0", scope, "pyproject.toml" if ecosystem == "python" else "package.json", "uv.lock" if ecosystem == "python" else "package-lock.json", "required primitive")


def python_project(path):
    path.mkdir()
    (path / "pyproject.toml").write_text('[project]\nname="fixture"\nversion="0.1.0"\ndependencies=[]\n', encoding="utf-8")
    (path / "uv.lock").write_text('version=1\n', encoding="utf-8")


class PythonResolver:
    def __init__(self):
        self.runtime, self.dev = [], []
        self.active = 0

    def __call__(self, argv, *, cwd, env=None):
        if "add" in argv:
            self.active += 1
            assert self.active == 1, "manifest writers overlapped"
            time.sleep(0.01)
            (self.dev if "--optional" in argv else self.runtime).append(argv[-1])
            (cwd / "pyproject.toml").write_text('[project]\nname="fixture"\nversion="0.1.0"\ndependencies=' + json.dumps(self.runtime) + '\n[project.optional-dependencies]\ndev=' + json.dumps(self.dev) + '\n', encoding="utf-8")
            packages = self.runtime + self.dev
            (cwd / "uv.lock").write_text('version=1\n' + ''.join('[[package]]\nname="' + p.split(">=")[0] + '"\nversion="23.1.0"\n' for p in packages), encoding="utf-8")
            self.active -= 1
        return CompletedProcess(argv, 0, "", "")


def test_argon2_request_pending_blocks_green_then_manifest_lock_runtime(tmp_path):
    root = tmp_path / "product"
    python_project(root)
    coordinator = DependencyCoordinator(root, tmp_path / "supervisor", PythonResolver())
    record = coordinator.submit(request())
    assert record["status"] == "pending"
    with pytest.raises(DependencyError, match="DEPENDENCY_UNRESOLVED"):
        coordinator.require_ready("AUTH")
    assert coordinator.resolve_pending("manifest-owner")[0]["status"] == "applied"
    coordinator.require_ready("AUTH")
    assert "argon2-cffi>=23" in (root / "pyproject.toml").read_text()
    assert 'name="argon2-cffi"' in (root / "uv.lock").read_text()


def test_two_concurrent_requests_survive_serialized_lock(tmp_path):
    root = tmp_path / "product"
    python_project(root)
    state = tmp_path / "supervisor"
    resolver = PythonResolver()
    a, b = DependencyCoordinator(root, state, resolver), DependencyCoordinator(root, state, resolver)
    with ThreadPoolExecutor(2) as pool:
        list(pool.map(lambda p: p[0].submit(p[1]), [(a, request("AUTH")), (b, request("TEST", "pytest", "dev"))]))
        list(pool.map(lambda c: c.resolve_pending("owner"), [a, b]))
    assert len(a.records()) == 2
    assert all(r["status"] == "applied" for r in a.records())
    a.require_ready("AUTH")
    b.require_ready("TEST")
    assert 'name="argon2-cffi"' in (root / "uv.lock").read_text()
    assert 'name="pytest"' in (root / "uv.lock").read_text()


def test_resolver_failure_and_manifest_drift_block_green(tmp_path):
    root = tmp_path / "product"
    python_project(root)
    coordinator = DependencyCoordinator(root, tmp_path / "supervisor", lambda argv, **kw: CompletedProcess(argv, 1, "", ""))
    coordinator.submit(request())
    assert coordinator.resolve_pending("owner")[0]["status"] == "rejected"
    with pytest.raises(DependencyError):
        coordinator.require_ready("AUTH")
    other = DependencyCoordinator(root, tmp_path / "other-state", PythonResolver())
    other.submit(request())
    other.resolve_pending("owner")
    (root / "uv.lock").write_text("version=1\n", encoding="utf-8")
    with pytest.raises(DependencyError, match="DRIFT"):
        other.require_ready("AUTH")


def test_runtime_dependency_only_in_dev_is_rejected(tmp_path):
    root = tmp_path / "product"
    python_project(root)
    def wrong(argv, *, cwd, env=None):
        (cwd / "pyproject.toml").write_text('[project]\ndependencies=[]\n[project.optional-dependencies]\ndev=["argon2-cffi>=23"]\n', encoding="utf-8")
        (cwd / "uv.lock").write_text('[[package]]\nname="argon2-cffi"\n', encoding="utf-8")
        return CompletedProcess(argv, 0, "", "")
    coordinator = DependencyCoordinator(root, tmp_path / "supervisor", wrong)
    coordinator.submit(request())
    assert coordinator.resolve_pending("owner")[0]["status"] == "rejected"


def test_rejected_resolver_restores_manifest_and_lock_pair(tmp_path):
    root = tmp_path / "product"
    python_project(root)
    before = {name: (root / name).read_bytes() for name in ("pyproject.toml", "uv.lock")}
    def partial(argv, *, cwd, env=None):
        (cwd / "pyproject.toml").write_text('[project]\ndependencies=["malformed replacement"]\n', encoding="utf-8")
        (cwd / "uv.lock").write_text("corrupt lock", encoding="utf-8")
        return CompletedProcess(argv, 1, "", "")
    coordinator = DependencyCoordinator(root, tmp_path / "state", partial)
    coordinator.submit(request())
    result = coordinator.resolve_pending("owner")[0]
    assert result["status"] == "rejected" and result["rolled_back"]
    assert {name: (root / name).read_bytes() for name in before} == before


def test_rejected_resolution_removes_only_new_owned_lock(tmp_path):
    root = tmp_path / "product"
    python_project(root)
    (root / "uv.lock").unlink()
    manifest = (root / "pyproject.toml").read_bytes()
    def partial(argv, *, cwd, env=None):
        (cwd / "uv.lock").write_text("partial lock", encoding="utf-8")
        return CompletedProcess(argv, 1, "", "")
    coordinator = DependencyCoordinator(root, tmp_path / "state", partial)
    coordinator.submit(request())
    assert coordinator.resolve_pending("owner")[0]["status"] == "rejected"
    assert not (root / "uv.lock").exists()
    assert (root / "pyproject.toml").read_bytes() == manifest


def test_node_manifest_lock_runtime_dev_and_ignore_scripts(tmp_path):
    root = tmp_path / "node"
    root.mkdir()
    (root / "package.json").write_text('{"name":"fixture"}', encoding="utf-8")
    calls = []
    def resolver(argv, *, cwd, env=None):
        calls.append(argv)
        data = json.loads((cwd / "package.json").read_text())
        field = "devDependencies" if "--save-dev" in argv else "dependencies"
        spec = argv[-1].rsplit("@", 1)
        data.setdefault(field, {})[spec[0]] = spec[1]
        (cwd / "package.json").write_text(json.dumps(data), encoding="utf-8")
        packages = {"": {f: data[f] for f in ("dependencies", "devDependencies") if f in data}}
        for f in ("dependencies", "devDependencies"):
            packages.update({"node_modules/" + k: {"version": "1.0.0"} for k in data.get(f, {})})
        (cwd / "package-lock.json").write_text(json.dumps({"lockfileVersion": 3, "packages": packages}), encoding="utf-8")
        return CompletedProcess(argv, 0, "", "")
    coordinator = DependencyCoordinator(root, tmp_path / "state", resolver)
    coordinator.submit(request("API", "bcrypt", ecosystem="node"))
    coordinator.submit(request("TEST", "vitest", "dev", "node"))
    assert all(r["status"] == "applied" for r in coordinator.resolve_pending("owner"))
    coordinator.require_ready("API")
    assert all("--ignore-scripts" in argv and "--package-lock-only" in argv for argv in calls)


@pytest.mark.parametrize("kwargs", [{"manifest": "../pyproject.toml"}, {"lock": "other/uv.lock"}, {"package": "--evil"}, {"constraint": "https://evil"}, {"scope": "local"}])
def test_request_validation(kwargs):
    data = request().__dict__ | kwargs
    with pytest.raises(DependencyError):
        DependencyRequest(**data)


def test_supervisor_state_cannot_live_in_product_root(tmp_path):
    with pytest.raises(DependencyError, match="outside"):
        DependencyCoordinator(tmp_path, tmp_path / "state")
