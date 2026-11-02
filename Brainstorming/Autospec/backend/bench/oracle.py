"""Independent judge of a generated product (metrics M5, M6, M7 of docs/REFONTE_V2.md 5.2).

Never imports a factory: the product is copied, its environment is rebuilt from
pyproject.toml + uv.lock only, then it is driven through its public interface.
"""

from __future__ import annotations

import importlib
import json
import os
import re
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path

from bench import proc

_SKIP = {".venv", ".autospec", "node_modules", "__pycache__", ".git", ".pytest_cache", "workspace"}


@dataclass
class Check:
    id: str
    passed: bool
    detail: str = ""


@dataclass
class Product:
    dir: Path
    env_dir: Path
    package: str
    lock_present: bool
    sync_ok: bool
    sync_detail: str = ""

    @property
    def python(self) -> str:
        scripts = "Scripts" if sys.platform == "win32" else "bin"
        suffix = ".exe" if sys.platform == "win32" else ""
        return str(self.env_dir / scripts / f"python{suffix}")

    def env(self, **extra: str) -> dict[str, str]:
        env = {k: v for k, v in os.environ.items() if k not in ("VIRTUAL_ENV", "PYTHONPATH")}
        env.update({"UV_PROJECT_ENVIRONMENT": str(self.env_dir), "PYTHONUTF8": "1",
                    "PYTHONIOENCODING": "utf-8", "PYTHONPATH": str(self.dir)})
        env.update(extra)
        return env

    def run(self, args: list[str], *, cwd: Path | None = None, timeout_s: float = 60,
            env: dict[str, str] | None = None) -> proc.Result:
        return proc.run([self.python, *args], cwd=cwd or self.dir, env=env or self.env(),
                        timeout_s=timeout_s)


def prepare(workspace: Path, package: str, work: Path) -> Product:
    """Copy the product and rebuild its environment from manifest + lock."""
    target = work / "product"
    shutil.copytree(workspace, target, ignore=lambda _d, names: [n for n in names if n in _SKIP])
    product = Product(dir=target, env_dir=work / "env", package=package,
                      lock_present=(target / "uv.lock").is_file(), sync_ok=False)
    argv = ["uv", "sync", "--locked"] if product.lock_present else ["uv", "sync"]
    result = proc.run(argv, cwd=target, env=product.env(), timeout_s=600)
    product.sync_ok = result.returncode == 0
    product.sync_detail = proc.tail(result.stderr + result.stdout, 1500)
    return product


_SUMMARY = re.compile(r"(\d+) (passed|failed|error|errors|skipped)")


def product_suite(product: Product) -> dict:
    """M5: the product's own suite in the clean environment."""
    if not product.sync_ok:
        return {"green": False, "passed": 0, "failed": 0, "detail": "environment not built"}
    result = proc.run(["uv", "run", "--locked" if product.lock_present else "--frozen", "pytest", "-q"],
                      cwd=product.dir, env=product.env(), timeout_s=900)
    counts = {kind: int(n) for n, kind in _SUMMARY.findall(result.stdout[-3000:])}
    failed = counts.get("failed", 0) + counts.get("error", 0) + counts.get("errors", 0)
    return {"green": result.returncode == 0 and counts.get("passed", 0) > 0,
            "passed": counts.get("passed", 0), "failed": failed,
            "detail": proc.tail(result.stdout, 800)}


@dataclass
class Server:
    product: Product
    port: int = field(default_factory=proc.free_port)
    extra_env: dict[str, str] = field(default_factory=dict)
    handle: object = None

    def __enter__(self) -> "Server":
        env = self.product.env(PORT=str(self.port), **self.extra_env)
        self.handle = proc.popen([self.product.python, "-m", self.product.package],
                                 cwd=self.product.dir, env=env)
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if self.handle.poll() is not None:
                raise RuntimeError(f"server exited with {self.handle.returncode}")
            try:
                if self.request("GET", "/health")[0] == 200:
                    return self
            except OSError:
                pass
            time.sleep(0.5)
        self.__exit__(None, None, None)
        raise RuntimeError("server never answered GET /health")

    def __exit__(self, *_exc) -> None:
        if self.handle is not None:
            proc.kill_tree(self.handle)
            self.handle = None

    def request(self, method: str, path: str, body: dict | None = None) -> tuple[int, object]:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read().decode("utf-8")
                status = resp.status
        except urllib.error.HTTPError as exc:
            raw, status = exc.read().decode("utf-8", errors="replace"), exc.code
        try:
            return status, json.loads(raw) if raw else None
        except json.JSONDecodeError:
            return status, raw


def smoke(product: Product, profile: str) -> tuple[bool, str]:
    """M7: the product starts through its declared entry point."""
    if not product.sync_ok:
        return False, "environment not built"
    if profile == "lib":
        result = product.run(["-c", f"import {product.package}"], timeout_s=60)
        return result.returncode == 0, proc.tail(result.stderr, 500)
    if profile == "cli":
        result = product.run(["-m", product.package, "--help"], timeout_s=60)
        ok = result.returncode == 0 and bool(result.stdout.strip())
        return ok, proc.tail(result.stdout + result.stderr, 500)
    try:
        with Server(product, extra_env={"NOTES_DB": str(product.dir / "smoke.db"),
                                        "COUNTER_DB": str(product.dir / "smoke.db")}) as server:
            if profile == "fullstack":
                status, _ = server.request("GET", "/")
                return status == 200, f"GET / -> {status}"
            return True, "GET /health -> 200"
    except RuntimeError as exc:
        return False, str(exc)


def judge(project_id: str, workspace: Path, package: str, profile: str) -> dict:
    """Run M5, M6 and M7 on a workspace. Returns a JSON-serializable report."""
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="bench-oracle-", ignore_cleanup_errors=True) as tmp:
        product = prepare(Path(workspace), package, Path(tmp))
        suite = product_suite(product)
        smoke_ok, smoke_detail = smoke(product, profile)
        checks: list[Check] = []
        if product.sync_ok:
            module = importlib.import_module(f"bench.oracles.{project_id}")
            try:
                checks = module.checks(product, Path(tmp))
            except Exception as exc:  # an oracle crash must not hide the other metrics
                checks = [Check("oracle_crash", False, f"{type(exc).__name__}: {exc}")]
    passed = sum(c.passed for c in checks)
    return {
        "lock_present": product.lock_present,
        "env_built": product.sync_ok,
        "env_detail": "" if product.sync_ok else product.sync_detail,
        "m5_suite": suite,
        "m6_oracle": {"passed": passed, "total": len(checks),
                      "rate": round(passed / len(checks), 3) if checks else 0.0,
                      "checks": [asdict(c) for c in checks]},
        "m7_smoke": {"ok": smoke_ok, "detail": smoke_detail},
        "duration_s": round(time.monotonic() - started, 1),
    }
