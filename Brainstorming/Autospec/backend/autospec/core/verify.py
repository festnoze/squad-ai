"""Independent verification of a product workspace: the factory never trusts the dev agent.

Clean environment rebuilt from manifest + lock, full suite (pytest, plus the npm build and
vitest for a fullstack workspace), QA test fingerprints, criteria traceability, product
smoke, and the git operations the pipeline needs. Every child process has a wall-clock
timeout and is killed with its whole tree when the awaiting task is cancelled (an API stop,
Ctrl-C); only processes started here are ever killed.
"""

from __future__ import annotations

import asyncio
import hashlib
import http.client
import json
import os
import re
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from autospec.core.models import Profile, Story
from autospec.core.procs import ProcResult, arun_capped, kill_tree, popen
from autospec.core.profiles import (
    FRONTEND_DIR,
    UNTRACKED_DIRS,
    VERIFY_VENV,
    npm_command,
    npm_env,
    run_git,
    uv_env,
)

TAIL_CHARS = 4000
_EXCLUDE_UNTRACKED = [f":(exclude){path}" for path in UNTRACKED_DIRS]
_OUTCOME_ALIASES = {"xfailed": "skipped", "xpassed": "passed"}
_NPM_BUILD_TIMEOUT_S = 600.0  # building frontend/dist for a smoke, apart from the server timeout
_SCRIPT_SRC = re.compile(r'<script\b[^>]*\bsrc="(/[^"]*)"')


@dataclass
class SuiteResult:
    ok: bool  # env built, every part green (pytest exit 0 or 5, npm build, vitest), no collection error
    returncode: int | None  # of the first failing part, else pytest's (vitest's for a frontend-only run)
    outcomes: dict[str, str]  # nodeid -> "passed" | "failed" | "error" | "skipped"
    collection_errors: list[str]  # files that failed to collect (or to load, for vitest)
    output_tail: str  # last ~4000 chars of the failing part(s), the useful part for a retry prompt
    env_error: str = ""  # `uv sync --locked` or `npm ci` failed: lock out of date, unresolvable dep
    duration_s: float = 0.0


@dataclass
class SmokeResult:
    ok: bool
    detail: str


def tail(text: str, limit: int = TAIL_CHARS) -> str:
    """The end of a process output: the summary and the traceback live there."""
    return text[-limit:]


async def _arun(argv: list[str], ws: Path, env: dict[str, str], timeout_s: float) -> ProcResult:
    """A capped child; cancelling the awaiting task kills its whole tree (procs.arun_capped)."""
    try:
        return await arun_capped(argv, cwd=ws, env=env, timeout_s=timeout_s)
    except OSError as exc:  # executable not found
        return ProcResult(returncode=127, stdout="", stderr=f"{argv[0]}: {exc}",
                          timed_out=False, duration_s=0.0)


def _output(proc: ProcResult, timeout_s: float) -> str:
    text = proc.stdout + proc.stderr
    if proc.timed_out:
        text += f"\n[autospec] killed after the {timeout_s:.0f}s timeout"
    return tail(text)


def _remaining(deadline: float) -> float:
    return max(deadline - time.time(), 1.0)  # wall clock: a machine sleep counts


def _env_failure(message: str) -> SuiteResult:
    return SuiteResult(ok=False, returncode=None, outcomes={}, collection_errors=[],
                       output_tail=message, env_error=message)


async def arun_suite(ws: Path, *, select: list[str] | None = None, clean: bool = True,
                     timeout_s: float = 600) -> SuiteResult:
    """Run the product suite: pytest in the verify-venv (rebuilt from scratch when
    ``clean``), plus, when ``frontend/package.json`` exists, ``npm ci`` (when ``clean`` or
    node_modules is missing) and ``npm run build`` BEFORE pytest (a Python test may GET /
    through TestClient, which needs frontend/dist), then vitest after it.

    A dependency missing from pyproject or package.json therefore fails here even when the
    dev environment has it. ``select`` restricts the run to nodeids or paths (None or [] =
    the whole suite); ``frontend/...`` entries go to vitest (a nodeid selects its whole
    file), the others to pytest; npm and vitest run only when the frontend is selected.
    ``timeout_s`` caps the whole run in wall-clock time.
    """
    ws, select = Path(ws), list(select or [])
    started = time.time()
    deadline = started + timeout_s
    has_frontend = (ws / FRONTEND_DIR / "package.json").is_file()
    front = [item for item in select if has_frontend and _is_frontend_path(item)]
    python = [item for item in select if item not in front]
    run_front = bool(front) or (has_frontend and not select)
    build = await _afrontend_build(ws, clean, deadline) if run_front else None
    runs: list[SuiteResult] = []  # the test runners, in order: pytest, vitest
    if build is None or not build.env_error:
        if python or not select:
            runs.append(await _apython_suite(ws, python, clean, deadline))
        if run_front and not (runs and runs[0].env_error):
            runs.append(await _avitest_suite(ws, front, deadline))
    parts = ([build] if build else []) + runs
    failed = [part for part in parts if not part.ok]
    outcomes: dict[str, str] = {}
    for part in runs:
        outcomes.update(part.outcomes)
    return SuiteResult(
        ok=not failed, returncode=(failed or runs)[0].returncode, outcomes=outcomes,
        collection_errors=[error for part in runs for error in part.collection_errors],
        output_tail=_join_tails([part.output_tail for part in failed or runs]),
        env_error="\n".join(part.env_error for part in parts if part.env_error),
        duration_s=round(time.time() - started, 3))


def _join_tails(texts: list[str]) -> str:
    """Several outputs within TAIL_CHARS: each keeps its own end."""
    texts = [text for text in texts if text]
    if len(texts) <= 1:
        return "".join(texts)
    return "\n".join(tail(text, TAIL_CHARS // len(texts) - 1) for text in texts)


async def _apython_suite(ws: Path, select: list[str], clean: bool, deadline: float) -> SuiteResult:
    env = uv_env(ws)
    # `uv sync` is exact: it removes every package the lock does not declare, so the
    # verify-venv is clean without being deleted (deleting a fresh venv races with
    # Windows scanners holding its files). It is rebuilt only when the sync fails.
    timeout = _remaining(deadline)
    sync = await _arun(["uv", "sync", "--locked"], ws, env, timeout)
    if sync.returncode != 0 and clean and await asyncio.to_thread(_remove_tree, ws / VERIFY_VENV):
        timeout = _remaining(deadline)
        sync = await _arun(["uv", "sync", "--locked"], ws, env, timeout)
    if sync.returncode != 0:
        return _env_failure(tail(f"`uv sync --locked` failed\n{_output(sync, timeout)}"))
    timeout = _remaining(deadline)
    # A cancelled run must not trade its CancelledError for a cleanup error on a locked file.
    with tempfile.TemporaryDirectory(prefix="autospec-report-", ignore_cleanup_errors=True) as tmp:
        report_file = Path(tmp) / "report.json"
        # `python -m pytest`, not `pytest`: a pytest missing from the verify-venv must fail,
        # never fall back to another one found on PATH.
        argv = ["uv", "run", "--locked", "python", "-m", "pytest", "-q", "--json-report",
                f"--json-report-file={report_file}", *select]
        proc = await _arun(argv, ws, env, timeout)
        report = _load_report(report_file)
    output = _output(proc, timeout)
    if report is None:
        output = tail(output + "\n[autospec] no readable pytest-json-report")
    outcomes, errors = _parse_report(report or {})
    ok = report is not None and not errors and proc.returncode in (0, 5)
    return SuiteResult(ok=ok, returncode=proc.returncode, outcomes=outcomes, collection_errors=errors,
                       output_tail=output)


def _remove_tree(path: Path) -> bool:
    """Delete a directory, retrying briefly (Windows releases file handles lazily)."""
    for _ in range(3):
        shutil.rmtree(path, ignore_errors=True)
        if not path.exists():
            return True
        time.sleep(0.5)
    return False


def _load_report(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _parse_report(report: dict) -> tuple[dict[str, str], list[str]]:
    outcomes: dict[str, str] = {}
    for test in report.get("tests") or []:
        if isinstance(test, dict) and isinstance(test.get("nodeid"), str):
            outcome = str(test.get("outcome", "error"))
            outcomes[test["nodeid"]] = _OUTCOME_ALIASES.get(outcome, outcome)
    errors = [str(c.get("nodeid") or "<session>") for c in report.get("collectors") or []
              if isinstance(c, dict) and c.get("outcome") == "failed"]
    return outcomes, errors


# --------------------------------------------------------------------------- _frontend


def _is_frontend_path(item: str) -> bool:
    path = item.replace("\\", "/").split("::", 1)[0]
    return path == FRONTEND_DIR or path.startswith(FRONTEND_DIR + "/")


async def _afrontend_build(ws: Path, clean: bool, deadline: float) -> SuiteResult:
    """``npm ci`` (an env error when it fails) then ``npm run build`` in frontend/. A failed
    build fails the suite, yet the test runners still run: their outcomes stay traceable."""
    front, env, npm = _frontend(ws), npm_env(), npm_command()
    if clean or not (front / "node_modules").is_dir():
        timeout = _remaining(deadline)
        install = await _arun([npm, "ci"], front, env, timeout)
        if install.returncode != 0:
            return _env_failure(tail(f"`npm ci` failed in {FRONTEND_DIR}/ (package-lock.json out of "
                                     f"date with package.json?)\n{_output(install, timeout)}"))
    timeout = _remaining(deadline)
    build = await _arun([npm, "run", "build"], front, env, timeout)
    ok = build.returncode == 0
    return SuiteResult(ok=ok, returncode=build.returncode, outcomes={}, collection_errors=[],
                       output_tail="" if ok else tail(f"`npm run build` failed in {FRONTEND_DIR}/\n"
                                                      f"{_output(build, timeout)}"))


async def _avitest_suite(ws: Path, select: list[str], deadline: float) -> SuiteResult:
    front, timeout = _frontend(ws), _remaining(deadline)
    with tempfile.TemporaryDirectory(prefix="autospec-vitest-", ignore_cleanup_errors=True) as tmp:
        report_file = Path(tmp) / "vitest.json"
        argv = _vitest_argv(front, report_file, _vitest_filters(select))
        proc = await _arun(argv, front, npm_env(), timeout) if argv else ProcResult(
            returncode=127, stdout="", stderr=f"vitest is not installed in {FRONTEND_DIR}/node_modules",
            timed_out=False, duration_s=0.0)
        report = _load_report(report_file)
    output = _output(proc, timeout)
    if report is None:
        output = tail(output + "\n[autospec] no readable vitest JSON report")
    outcomes, errors = _parse_vitest(report or {}, front)
    return SuiteResult(ok=report is not None and not errors and proc.returncode == 0,
                       returncode=proc.returncode, outcomes=outcomes, collection_errors=errors,
                       output_tail=output)


def _frontend(ws: Path) -> Path:
    """frontend/, resolved: Vite cannot load modules under a Windows 8.3 short-name cwd."""
    return (ws / FRONTEND_DIR).resolve()


def _vitest_filters(select: list[str]) -> list[str]:
    """Vitest file filters (substrings of paths relative to frontend/); [] = every test file."""
    filters: list[str] = []
    for item in select:
        path = _posix(item.split("::", 1)[0])
        if path == FRONTEND_DIR:
            return []
        filters.append(path[len(FRONTEND_DIR) + 1:])
    return list(dict.fromkeys(filters))


def _vitest_argv(front: Path, report: Path, filters: list[str]) -> list[str] | None:
    """Node on vitest's own entry point: no npm.cmd, so no cmd.exe parsing the arguments."""
    package = front / "node_modules" / "vitest"
    try:
        bins = json.loads((package / "package.json").read_text(encoding="utf-8")).get("bin")
    except (OSError, ValueError, AttributeError):
        return None
    entry = bins.get("vitest") if isinstance(bins, dict) else bins
    if not isinstance(entry, str):
        return None
    return [shutil.which("node") or "node", str(package / entry), "run", "--reporter=default",
            "--reporter=json", f"--outputFile.json={report}", "--passWithNoTests", *filters]


def _parse_vitest(report: dict, front: Path) -> tuple[dict[str, str], list[str]]:
    """Outcomes keyed ``frontend/<file>::<describe titles > test title>`` (CONTRACTS.md 8.2);
    a file that failed to load (no test result at all) is a collection error."""
    outcomes: dict[str, str] = {}
    errors: list[str] = []
    root = os.path.realpath(front)
    for file in report.get("testResults") or []:
        if not isinstance(file, dict) or not isinstance(file.get("name"), str):
            continue
        path = _vitest_path(file["name"], root)
        tests = [test for test in file.get("assertionResults") or [] if isinstance(test, dict)]
        if file.get("status") == "failed" and not tests:
            errors.append(path)
        for test in tests:
            titles = [*(test.get("ancestorTitles") or []), test.get("title", "")]
            nodeid = f"{path}::{' > '.join(map(str, titles))}"
            outcome = {"passed": "passed", "failed": "failed"}.get(test.get("status"), "skipped")
            if outcomes.get(nodeid, "passed") == "passed":  # a duplicate title never hides a failure
                outcomes[nodeid] = outcome
    return outcomes, errors


def _vitest_path(name: str, root: str) -> str:
    """Vitest's absolute file path as ``frontend/<relative POSIX path>`` (both sides resolved:
    8.3 short names and case differences must not leak into nodeids)."""
    real = os.path.realpath(name)
    if os.path.normcase(real).startswith(os.path.normcase(root) + os.sep):
        return f"{FRONTEND_DIR}/{_posix(real[len(root) + 1:])}"
    return _posix(name)


async def _abuild_dist(ws: Path) -> str:
    """Build frontend/dist when absent (installing node_modules first when missing).
    Returns "" when the build is there, else what went wrong."""
    front = _frontend(ws)
    if (front / "dist" / "index.html").is_file():
        return ""
    steps = ([] if (front / "node_modules").is_dir() else [["ci"]]) + [["run", "build"]]
    for args in steps:
        proc = await _arun([npm_command(), *args], front, npm_env(), _NPM_BUILD_TIMEOUT_S)
        if proc.returncode != 0:
            return f"`npm {' '.join(args)}` failed in {FRONTEND_DIR}/\n{_output(proc, _NPM_BUILD_TIMEOUT_S)}"
    return ""


def _check_frontend(base: str) -> tuple[bool, str]:
    """GET / must serve the built index.html, and the script it loads must be served too."""
    opener = _opener()
    status, body = _http_get(opener, base + "/")
    if status != 200 or '<div id="root">' not in body:
        return False, f'GET / -> {status}, expected 200 with the built index.html (<div id="root">)'
    script = _SCRIPT_SRC.search(body)
    if script:
        status, _ = _http_get(opener, base + script.group(1))
        if status != 200:
            return False, f"GET {script.group(1)} (loaded by index.html) -> {status}"
    return True, 'GET / -> 200 with <div id="root">'


# --------------------------------------------------------------------------- traceability


def red_check(result: SuiteResult, nodeids: list[str]) -> list[str]:
    """Nodeids that PASSED (the caller wants []); an absent nodeid did not pass."""
    return [nodeid for nodeid in nodeids if result.outcomes.get(nodeid) == "passed"]


def missing_criteria(story: Story, result: SuiteResult) -> list[str]:
    """Criterion ids without at least one passed nodeid (unmapped criteria included)."""
    passed = {nodeid for nodeid, outcome in result.outcomes.items() if outcome == "passed"}
    covered = {test.ac_id for test in story.acceptance_tests
               if any(nodeid in passed for nodeid in test.nodeids)}
    ids = [c.id for c in story.criteria] + [t.ac_id for t in story.acceptance_tests]
    return [ac_id for ac_id in dict.fromkeys(ids) if ac_id not in covered]


# --------------------------------------------------------------------------- smoke


async def asmoke(ws: Path, *, package: str, profile: Profile, timeout_s: float = 60) -> SmokeResult:
    """Start the product the way a user would, in the verify-venv (not rebuilt here).

    lib: import the package; cli: ``python -m <package> --help`` exits 0 with stdout;
    api: ``python -m <package>`` on a free $PORT answers ``GET /health`` with 200;
    fullstack: frontend/dist built when absent (outside ``timeout_s``), then the api check
    plus ``GET /`` 200 with ``<div id="root">`` and the script it loads served.
    """
    ws = Path(ws)
    if not all(part.isidentifier() for part in package.split(".")):
        return SmokeResult(False, f"invalid package name {package!r}")
    env = uv_env(ws)
    python = ["uv", "run", "--locked", "python"]
    if profile is Profile.LIB:
        proc = await _arun([*python, "-c", f"import {package}"], ws, env, timeout_s)
        return _exit_verdict(proc, f"import {package}", timeout_s)
    if profile is Profile.CLI:
        label = f"python -m {package} --help"
        proc = await _arun([*python, "-m", package, "--help"], ws, env, timeout_s)
        verdict = _exit_verdict(proc, label, timeout_s)
        if verdict.ok and not proc.stdout.strip():
            return SmokeResult(False, f"{label}: exit 0 but nothing on stdout\n{_output(proc, timeout_s)}")
        return verdict
    if profile in (Profile.API, Profile.FULLSTACK):
        frontend = profile is Profile.FULLSTACK
        problem = await _abuild_dist(ws) if frontend else ""
        if problem:
            return SmokeResult(False, problem)
        return await _asmoke_api(ws, env, [*python, "-m", package], timeout_s, frontend=frontend)
    raise NotImplementedError(f"smoke for profile {profile.value!r} is not available yet")


def _exit_verdict(proc: ProcResult, label: str, timeout_s: float) -> SmokeResult:
    if proc.returncode == 0:
        return SmokeResult(True, f"{label}: exit 0")
    status = "timed out" if proc.timed_out else f"exit {proc.returncode}"
    return SmokeResult(False, f"{label}: {status}\n{_output(proc, timeout_s)}")


async def _asmoke_api(ws: Path, env: dict[str, str], argv: list[str], timeout_s: float, *,
                      frontend: bool = False) -> SmokeResult:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    started = time.time()
    with tempfile.TemporaryFile() as log:
        try:
            proc = popen(argv, cwd=ws, env={**env, "PORT": str(port)}, stdout=log,
                         stderr=subprocess.STDOUT)
        except OSError as exc:
            return SmokeResult(False, f"cannot start {argv[0]}: {exc}")
        try:
            ok, detail = await _apoll_health(proc, base + "/health", started, timeout_s)
            if ok and frontend:
                ok, page = await asyncio.to_thread(_check_frontend, base)
                detail = f"{detail}\n{page}"
        finally:
            kill_tree(proc)  # also on a cancellation; uv is a wrapper, the server a grandchild
        if not ok:
            log.seek(0)
            detail += "\n" + tail(log.read().decode("utf-8", errors="replace"))
    return SmokeResult(ok, detail)


async def _apoll_health(proc: subprocess.Popen, url: str, started: float,
                        timeout_s: float) -> tuple[bool, str]:
    opener = _opener()
    last: int | str = "no answer"
    while time.time() - started < timeout_s:
        if proc.poll() is not None:
            return False, f"server exited with code {proc.returncode} before GET /health answered"
        last = (await asyncio.to_thread(_http_get, opener, url))[0]
        if last == 200:
            return True, f"GET {url} -> 200 after {time.time() - started:.1f}s"
        await asyncio.sleep(0.25)
    return False, f"GET {url} gave no 200 within {timeout_s:.0f}s (last: {last})"


def _opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))  # never via a proxy


def _http_get(opener: urllib.request.OpenerDirector, url: str) -> tuple[int | str, str]:
    """(status, body) of a GET; (exception name, "") when nothing answered."""
    try:
        with opener.open(url, timeout=5) as response:
            return int(response.status), response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, ""
    except (OSError, http.client.HTTPException, ValueError) as exc:
        return type(exc).__name__, ""


# --------------------------------------------------------------------------- git


def _is_untracked_path(path: str) -> bool:
    return any(path == top or path.startswith(top + "/") for top in UNTRACKED_DIRS)


def _posix(path: str) -> str:
    return PurePosixPath(path.replace("\\", "/")).as_posix()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fingerprint(ws: Path, paths: list[str]) -> dict[str, str]:
    """sha256 of each file ("" when missing). A directory expands to every file under it,
    so a file added there (a tampering conftest.py) changes the fingerprint too."""
    ws = Path(ws)
    result: dict[str, str] = {}
    for rel in map(_posix, paths):
        target = ws / rel
        if target.is_dir():
            for file in sorted(target.rglob("*")):
                rel_file = file.relative_to(ws)
                if (file.is_file() and not {"__pycache__", "node_modules"} & set(rel_file.parts)
                        and not _is_untracked_path(rel_file.as_posix())):
                    result[rel_file.as_posix()] = _sha256(file)
        else:
            result[rel] = _sha256(target) if target.is_file() else ""
    return result


def changed_paths(ws: Path) -> list[str]:
    """Modified, deleted and untracked files vs HEAD (POSIX, repo-relative, ignored files,
    ``.autospec/``, ``frontend/node_modules/`` and ``frontend/dist/`` excluded)."""
    proc = run_git(ws, "status", "--porcelain=v1", "-uall", "-z", "--", ".", *_EXCLUDE_UNTRACKED)
    entries = iter(proc.stdout.split("\0"))
    paths: set[str] = set()
    for entry in entries:
        if len(entry) > 3:
            paths.add(entry[3:].rstrip("/"))
            if "R" in entry[:2]:  # a rename carries its source in the next entry
                paths.add(next(entries, ""))
    return sorted(p for p in paths if p and not _is_untracked_path(p))


def discard_changes(ws: Path, paths: list[str] | None = None) -> None:
    """Restore files or directories (None = everything) to HEAD: tracked files restored,
    files absent from HEAD deleted. Only entries of ``changed_paths`` are touched, so
    ``.autospec/``, npm's directories, git-ignored files and clean paths are left alone."""
    ws = Path(ws)
    changed = changed_paths(ws)
    if paths is not None:
        wanted = [_posix(p).rstrip("/") for p in paths]
        changed = [c for c in changed if any(w in (".", c) or c.startswith(w + "/") for w in wanted)]
    if not changed:
        return
    head = run_git(ws, "ls-tree", "-r", "--name-only", "-z", "HEAD", check=False)
    in_head = set(head.stdout.split("\0")) if head.returncode == 0 else set()
    restore = [p for p in changed if p in in_head]
    remove = [p for p in changed if p not in in_head]
    if restore:
        run_git(ws, "--literal-pathspecs", "checkout", "HEAD", "--", *restore)
    if remove:
        run_git(ws, "--literal-pathspecs", "rm", "-q", "--cached", "--ignore-unmatch", "--", *remove)
        for rel in remove:
            target = ws / rel
            if target.is_file() or target.is_symlink():
                target.unlink()
            parent = target.parent
            while parent != ws and parent.is_dir() and not any(parent.iterdir()):
                parent.rmdir()
                parent = parent.parent


def git_commit(ws: Path, message: str) -> str:
    """Stage everything .gitignore allows (never ``.autospec/`` nor npm's directories),
    commit and return the sha, or "" when nothing changed."""
    ws = Path(ws)
    run_git(ws, "add", "-A")
    # Unstage the factory and npm directories whatever .gitignore says. (An exclude
    # pathspec on `git add` exits 1 as soon as the excluded directory is also git-ignored.)
    run_git(ws, "reset", "-q", "--", *UNTRACKED_DIRS)
    if run_git(ws, "diff", "--cached", "--quiet", check=False).returncode == 0:
        return ""
    identity: list[str] = []
    if not run_git(ws, "config", "user.email", check=False).stdout.strip():
        identity = ["-c", "user.name=autospec", "-c", "user.email=autospec@localhost"]
    run_git(ws, *identity, "commit", "-q", "-F", "-", input_text=message)
    return run_git(ws, "rev-parse", "HEAD").stdout.strip()


def repo_tree(ws: Path, limit: int = 200) -> str:
    """Tracked + untracked non-ignored files, sorted, one per line, for prompts (never
    ``.autospec/`` nor npm's thousands of files)."""
    ws = Path(ws)
    proc = run_git(ws, "ls-files", "--cached", "--others", "--exclude-standard", "-z",
                   "--", ".", *_EXCLUDE_UNTRACKED)
    files = sorted({p for p in proc.stdout.split("\0")
                    if p and not _is_untracked_path(p) and (ws / p).exists()})
    lines = files[:limit]
    if len(files) > limit:
        lines.append(f"... {len(files) - limit} more")
    return "\n".join(lines)
