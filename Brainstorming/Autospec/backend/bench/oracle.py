"""Independent judge of a generated product (metrics M5, M6, M7 of docs/REFONTE_V2.md 5.2).

Never imports a factory: the product is copied, its environment is rebuilt from
pyproject.toml + uv.lock only (plus frontend/package.json + package-lock.json with
`npm ci` then `npm run build` for a fullstack product), then it is driven through
its public interface.
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
NOT_AUTOMATED = "NOT_AUTOMATED"  # Check.detail of a listed criterion the oracle cannot verify
_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


@dataclass
class Check:
    id: str
    passed: bool
    detail: str = ""


def _ignore(directory: str, names: list[str]) -> list[str]:
    """Copy filter: tool caches and envs, plus a frontend build the bench must redo itself."""
    skipped = [n for n in names if n in _SKIP]
    if Path(directory).name == "frontend":
        skipped += [n for n in names if n == "dist"]
    return skipped


def npm_command() -> str:
    """The npm executable (npm.cmd on Windows, started without a shell)."""
    return shutil.which("npm") or ("npm.cmd" if sys.platform == "win32" else "npm")


@dataclass
class Product:
    dir: Path
    env_dir: Path
    package: str
    lock_present: bool
    sync_ok: bool
    sync_detail: str = ""
    frontend: bool = False      # frontend/package.json present
    frontend_ok: bool = False   # `npm ci` and `npm run build` both succeeded
    frontend_detail: str = ""
    timings: dict[str, float] = field(default_factory=dict)  # seconds per bench step (uv sync, npm ci...)
    suite: dict = field(default_factory=dict)                 # the M5 report, for oracles judging tests

    @property
    def python(self) -> str:
        scripts = "Scripts" if sys.platform == "win32" else "bin"
        suffix = ".exe" if sys.platform == "win32" else ""
        return str(self.env_dir / scripts / f"python{suffix}")

    @property
    def frontend_dir(self) -> Path:
        return self.dir / "frontend"

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
    shutil.copytree(workspace, target, ignore=_ignore)
    product = Product(dir=target, env_dir=work / "env", package=package,
                      lock_present=(target / "uv.lock").is_file(), sync_ok=False)
    argv = ["uv", "sync", "--locked"] if product.lock_present else ["uv", "sync"]
    result = proc.run(argv, cwd=target, env=product.env(), timeout_s=600)
    product.timings["uv sync"] = result.duration_s
    product.sync_ok = result.returncode == 0
    product.sync_detail = proc.tail(result.stderr + result.stdout, 1500)
    if (product.frontend_dir / "package.json").is_file():
        prepare_frontend(product)
    return product


def prepare_frontend(product: Product) -> None:
    """`npm ci` (from package-lock.json only) then `npm run build` in the copy's frontend/."""
    product.frontend = True
    for args in (["ci", "--no-audit", "--no-fund"], ["run", "build"]):
        result = proc.run([npm_command(), *args], cwd=product.frontend_dir,
                          env=product.env(CI="1", NO_COLOR="1"), timeout_s=900)
        product.timings[f"npm {args[0] if args[0] == 'ci' else 'run build'}"] = result.duration_s
        if result.returncode != 0:
            output = _ANSI.sub("", result.stderr + "\n" + result.stdout)
            timeout = ", timeout" if result.timed_out else ""
            product.frontend_detail = (f"npm {' '.join(args)} failed (rc={result.returncode}{timeout}): "
                                       f"{proc.tail(output, 1500)}")
            return
    product.frontend_ok = True


_SUMMARY = re.compile(r"(\d+) (passed|failed|errors?|skipped|xfailed|xpassed)\b")
_VITEST_TESTS = re.compile(r"^\s*Tests\s+(.*)$", re.MULTILINE)
_VITEST_COUNT = re.compile(r"(\d+) (passed|failed|skipped|todo)\b")


def product_suite(product: Product) -> dict:
    """M5: the product's own suite in the clean environment (pytest, plus frontend tests).

    The top-level counts add both layers; `backend` (and `frontend`) keep each layer's own
    counts, skipped and xfailed tests included, and the duration of the run.
    """
    if not product.sync_ok:
        return {"green": False, "passed": 0, "failed": 0, "detail": "environment not built"}
    result = proc.run(["uv", "run", "--locked" if product.lock_present else "--frozen", "pytest", "-q"],
                      cwd=product.dir, env=product.env(), timeout_s=900)
    product.timings["pytest"] = result.duration_s
    counts = {kind: int(n) for n, kind in _SUMMARY.findall(result.stdout[-3000:])}
    failed = counts.get("failed", 0) + counts.get("error", 0) + counts.get("errors", 0)
    suite = {"green": result.returncode == 0 and counts.get("passed", 0) > 0,
             "passed": counts.get("passed", 0), "failed": failed,
             "detail": proc.tail(result.stdout, 800)}
    suite["backend"] = {"green": suite["green"], "passed": suite["passed"], "failed": failed,
                        "skipped": counts.get("skipped", 0),
                        "xfailed": counts.get("xfailed", 0) + counts.get("xpassed", 0),
                        "duration_s": result.duration_s}
    if product.frontend:
        front = frontend_suite(product)
        suite["frontend"] = front
        suite["passed"] += front["passed"]
        suite["failed"] += front["failed"]
        suite["green"] = suite["green"] and front["green"]
    return suite


def frontend_suite(product: Product) -> dict:
    """`npm test` in frontend/ (vitest per the fullstack contract), counted from its summary.

    A run that fails without a readable summary counts as one failure, and a frontend
    that could not be installed or built counts as one failure: never a silent green.
    """
    if not product.frontend_ok:
        return {"green": False, "passed": 0, "failed": 1, "detail": product.frontend_detail}
    result = proc.run([npm_command(), "test"], cwd=product.frontend_dir,
                      env=product.env(CI="1", NO_COLOR="1"), timeout_s=900)
    product.timings["npm test"] = result.duration_s
    output = _ANSI.sub("", result.stdout + "\n" + result.stderr)
    counts: dict[str, int] = {}
    summary = _VITEST_TESTS.findall(output)
    if summary:
        counts = {kind: int(n) for n, kind in _VITEST_COUNT.findall(summary[-1])}
    passed, failed = counts.get("passed", 0), counts.get("failed", 0)
    if result.returncode != 0 and failed == 0:
        failed = 1
    return {"green": result.returncode == 0 and passed > 0 and failed == 0,
            "passed": passed, "failed": failed, "skipped": counts.get("skipped", 0) + counts.get("todo", 0),
            "duration_s": result.duration_s, "detail": proc.tail(output, 800)}


@dataclass
class Server:
    product: Product
    port: int = field(default_factory=proc.free_port)
    extra_env: dict[str, str] = field(default_factory=dict)
    health_path: str = "/health"
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
                if self.request("GET", self.health_path)[0] == 200:
                    return self
            except OSError:
                pass
            time.sleep(0.5)
        self.__exit__(None, None, None)
        raise RuntimeError(f"server never answered GET {self.health_path}")

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
                raw = resp.read().decode("utf-8", errors="replace")
                status = resp.status
        except urllib.error.HTTPError as exc:
            raw, status = exc.read().decode("utf-8", errors="replace"), exc.code
        try:
            return status, json.loads(raw) if raw else None
        except json.JSONDecodeError:
            return status, raw


def smoke(product: Product, profile: str, health_path: str = "/health") -> tuple[bool, str]:
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
    smoke_db = str(product.dir / "smoke.db")
    try:
        with Server(product, health_path=health_path,
                    extra_env={"NOTES_DB": smoke_db, "COUNTER_DB": smoke_db, "RELAIS_DB": smoke_db}) as server:
            if profile == "fullstack":
                status, body = server.request("GET", "/")
                has_root = isinstance(body, str) and '<div id="root">' in body
                detail = f"GET / -> {status}" + ("" if has_root else ', no <div id="root"> in the body')
                if product.frontend and not product.frontend_ok:
                    detail += f"; {product.frontend_detail[:300]}"
                return status == 200 and has_root, detail
            return True, f"GET {health_path} -> 200"
    except RuntimeError as exc:
        return False, str(exc)


def judge(project_id: str, workspace: Path, package: str, profile: str) -> dict:
    """Run M5, M6 and M7 on a workspace. Returns a JSON-serializable report."""
    started = time.monotonic()
    module = importlib.import_module(f"bench.oracles.{project_id}")
    with tempfile.TemporaryDirectory(prefix="bench-oracle-", ignore_cleanup_errors=True) as raw_tmp:
        # Windows hands out 8.3 short temp paths (E6FB4~1.MIL) on which Vite/Vitest fail to
        # resolve modules: always work on the long form.
        tmp = Path(raw_tmp).resolve()
        product = prepare(Path(workspace), package, tmp)
        suite = product.suite = product_suite(product)
        smoke_ok, smoke_detail = smoke(product, profile, getattr(module, "HEALTH_PATH", "/health"))
        checks: list[Check] = []
        if product.sync_ok:
            try:
                checks = module.checks(product, tmp)
            except Exception as exc:  # an oracle crash must not hide the other metrics
                checks = [Check("oracle_crash", False, f"{type(exc).__name__}: {exc}")]
    passed = sum(c.passed for c in checks)
    not_automated = sum(1 for c in checks if c.detail == NOT_AUTOMATED)
    m6: dict = {"passed": passed, "total": len(checks),
                "rate": round(passed / len(checks), 3) if checks else 0.0}
    if not_automated:
        m6["not_automated"] = not_automated  # counted as failures in total: the rate stays honest
    m6["checks"] = [asdict(c) for c in checks]
    report: dict = {
        "lock_present": product.lock_present,
        "env_built": product.sync_ok,
        "env_detail": "" if product.sync_ok else product.sync_detail,
    }
    if product.frontend:
        report["frontend_built"] = product.frontend_ok
        report["frontend_detail"] = product.frontend_detail
    report.update({
        "m5_suite": suite,
        "m6_oracle": m6,
        "m7_smoke": {"ok": smoke_ok, "detail": smoke_detail},
        "timings_s": product.timings,
        "duration_s": round(time.monotonic() - started, 1),
    })
    return report
