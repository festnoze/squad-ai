"""Independent verification of a product workspace: the factory never trusts the dev agent.

Clean environment rebuilt from manifest + lock, full suite, QA test fingerprints, criteria
traceability, product smoke, and the git operations the pipeline needs. Every child process
has an explicit timeout; only processes started here are ever killed.
"""

from __future__ import annotations

import asyncio
import hashlib
import http.client
import json
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
from autospec.core.procs import ProcResult, kill_tree, popen, run_capped
from autospec.core.profiles import FACTORY_DIR, VERIFY_VENV, run_git, uv_env

TAIL_CHARS = 4000
_EXCLUDE_FACTORY = f":(exclude){FACTORY_DIR}"
_OUTCOME_ALIASES = {"xfailed": "skipped", "xpassed": "passed"}


@dataclass
class SuiteResult:
    ok: bool  # env built, suite exit code 0 (or 5: nothing collected), no collection error
    returncode: int | None
    outcomes: dict[str, str]  # nodeid -> "passed" | "failed" | "error" | "skipped"
    collection_errors: list[str]  # files that failed to collect
    output_tail: str  # last ~4000 chars, the useful part for a retry prompt
    env_error: str = ""  # `uv sync --locked` failed: lock out of date, unresolvable dep
    duration_s: float = 0.0


@dataclass
class SmokeResult:
    ok: bool
    detail: str


def tail(text: str, limit: int = TAIL_CHARS) -> str:
    """The end of a process output: the summary and the traceback live there."""
    return text[-limit:]


def _run(argv: list[str], ws: Path, env: dict[str, str], timeout_s: float) -> ProcResult:
    try:
        return run_capped(argv, cwd=ws, env=env, timeout_s=timeout_s)
    except OSError as exc:  # executable not found
        return ProcResult(returncode=127, stdout="", stderr=f"{argv[0]}: {exc}",
                          timed_out=False, duration_s=0.0)


def _output(proc: ProcResult, timeout_s: float) -> str:
    text = proc.stdout + proc.stderr
    if proc.timed_out:
        text += f"\n[autospec] killed after the {timeout_s:.0f}s timeout"
    return tail(text)


async def arun_suite(ws: Path, *, select: list[str] | None = None, clean: bool = True,
                     timeout_s: float = 600) -> SuiteResult:
    """Run the product suite in the verify-venv, rebuilt from scratch when ``clean``.

    A dependency missing from pyproject therefore fails here even when the dev venv has
    it. ``select`` restricts the run to nodeids or paths (None or [] = the whole suite).
    """
    return await asyncio.to_thread(_run_suite, Path(ws), list(select or []), clean, timeout_s)


def _run_suite(ws: Path, select: list[str], clean: bool, timeout_s: float) -> SuiteResult:
    started = time.monotonic()
    env = uv_env(ws)

    def env_failure(message: str) -> SuiteResult:
        return SuiteResult(ok=False, returncode=None, outcomes={}, collection_errors=[],
                           output_tail=message, env_error=message,
                           duration_s=round(time.monotonic() - started, 3))

    if clean and not _remove_tree(ws / VERIFY_VENV):
        return env_failure(f"cannot delete {VERIFY_VENV.as_posix()}: a process still holds it")
    sync = _run(["uv", "sync", "--locked"], ws, env, timeout_s)
    if sync.returncode != 0:
        return env_failure(tail(f"`uv sync --locked` failed\n{_output(sync, timeout_s)}"))
    remaining = max(timeout_s - (time.monotonic() - started), 1.0)
    with tempfile.TemporaryDirectory(prefix="autospec-report-") as tmp:
        report_file = Path(tmp) / "report.json"
        # `python -m pytest`, not `pytest`: a pytest missing from the verify-venv must fail,
        # never fall back to another one found on PATH.
        argv = ["uv", "run", "--locked", "python", "-m", "pytest", "-q", "--json-report",
                f"--json-report-file={report_file}", *select]
        proc = _run(argv, ws, env, remaining)
        report = _load_report(report_file)
    output = _output(proc, remaining)
    if report is None:
        output = tail(output + "\n[autospec] no readable pytest-json-report")
    outcomes, errors = _parse_report(report or {})
    ok = report is not None and not errors and proc.returncode in (0, 5)
    return SuiteResult(ok=ok, returncode=proc.returncode, outcomes=outcomes, collection_errors=errors,
                       output_tail=output, duration_s=round(time.monotonic() - started, 3))


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


async def asmoke(ws: Path, *, package: str, profile: Profile, timeout_s: float = 60) -> SmokeResult:
    """Start the product the way a user would, in the verify-venv (not rebuilt here).

    lib: import the package; cli: ``python -m <package> --help`` exits 0 with stdout;
    api: ``python -m <package>`` on a free $PORT answers ``GET /health`` with 200.
    """
    ws = Path(ws)
    if not all(part.isidentifier() for part in package.split(".")):
        return SmokeResult(False, f"invalid package name {package!r}")
    env = uv_env(ws)
    python = ["uv", "run", "--locked", "python"]
    if profile is Profile.LIB:
        proc = await asyncio.to_thread(_run, [*python, "-c", f"import {package}"], ws, env, timeout_s)
        return _exit_verdict(proc, f"import {package}", timeout_s)
    if profile is Profile.CLI:
        label = f"python -m {package} --help"
        proc = await asyncio.to_thread(_run, [*python, "-m", package, "--help"], ws, env, timeout_s)
        verdict = _exit_verdict(proc, label, timeout_s)
        if verdict.ok and not proc.stdout.strip():
            return SmokeResult(False, f"{label}: exit 0 but nothing on stdout\n{_output(proc, timeout_s)}")
        return verdict
    if profile is Profile.API:
        return await _asmoke_api(ws, env, [*python, "-m", package], timeout_s)
    raise NotImplementedError(f"smoke for profile {profile.value!r} is not available yet")


def _exit_verdict(proc: ProcResult, label: str, timeout_s: float) -> SmokeResult:
    if proc.returncode == 0:
        return SmokeResult(True, f"{label}: exit 0")
    status = "timed out" if proc.timed_out else f"exit {proc.returncode}"
    return SmokeResult(False, f"{label}: {status}\n{_output(proc, timeout_s)}")


async def _asmoke_api(ws: Path, env: dict[str, str], argv: list[str], timeout_s: float) -> SmokeResult:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    url = f"http://127.0.0.1:{port}/health"
    started = time.monotonic()
    with tempfile.TemporaryFile() as log:
        try:
            proc = popen(argv, cwd=ws, env={**env, "PORT": str(port)}, stdout=log,
                         stderr=subprocess.STDOUT)
        except OSError as exc:
            return SmokeResult(False, f"cannot start {argv[0]}: {exc}")
        try:
            ok, detail = await _apoll_health(proc, url, started, timeout_s)
        finally:
            kill_tree(proc)  # uv is a wrapper: the real server is a grandchild
        if not ok:
            log.seek(0)
            detail += "\n" + tail(log.read().decode("utf-8", errors="replace"))
    return SmokeResult(ok, detail)


async def _apoll_health(proc: subprocess.Popen, url: str, started: float,
                        timeout_s: float) -> tuple[bool, str]:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # never via a proxy
    last: int | str = "no answer"
    while time.monotonic() - started < timeout_s:
        if proc.poll() is not None:
            return False, f"server exited with code {proc.returncode} before GET /health answered"
        last = await asyncio.to_thread(_http_status, opener, url)
        if last == 200:
            return True, f"GET {url} -> 200 after {time.monotonic() - started:.1f}s"
        await asyncio.sleep(0.25)
    return False, f"GET {url} gave no 200 within {timeout_s:.0f}s (last: {last})"


def _http_status(opener: urllib.request.OpenerDirector, url: str) -> int | str:
    try:
        with opener.open(url, timeout=2) as response:
            return int(response.status)
    except urllib.error.HTTPError as exc:
        return exc.code
    except (OSError, http.client.HTTPException, ValueError) as exc:
        return type(exc).__name__


def _is_factory_path(path: str) -> bool:
    return path == FACTORY_DIR or path.startswith(FACTORY_DIR + "/")


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
                if file.is_file() and "__pycache__" not in file.parts:
                    result[file.relative_to(ws).as_posix()] = _sha256(file)
        else:
            result[rel] = _sha256(target) if target.is_file() else ""
    return result


def changed_paths(ws: Path) -> list[str]:
    """Modified, deleted and untracked files vs HEAD (POSIX, repo-relative, ignored files
    and ``.autospec/`` excluded)."""
    proc = run_git(ws, "status", "--porcelain=v1", "-uall", "-z", "--", ".", _EXCLUDE_FACTORY)
    entries = iter(proc.stdout.split("\0"))
    paths: set[str] = set()
    for entry in entries:
        if len(entry) > 3:
            paths.add(entry[3:].rstrip("/"))
            if "R" in entry[:2]:  # a rename carries its source in the next entry
                paths.add(next(entries, ""))
    return sorted(p for p in paths if p and not _is_factory_path(p))


def discard_changes(ws: Path, paths: list[str] | None = None) -> None:
    """Restore files or directories (None = everything) to HEAD: tracked files restored,
    files absent from HEAD deleted. Only entries of ``changed_paths`` are touched, so
    ``.autospec/``, git-ignored files and already clean paths are left alone."""
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
    """Stage everything .gitignore allows (never ``.autospec/``), commit and return the sha,
    or "" when nothing changed."""
    ws = Path(ws)
    run_git(ws, "add", "-A")
    # Unstage the factory directory whatever .gitignore says. (An exclude pathspec on
    # `git add` exits 1 as soon as the excluded directory is also git-ignored.)
    run_git(ws, "reset", "-q", "--", FACTORY_DIR)
    if run_git(ws, "diff", "--cached", "--quiet", check=False).returncode == 0:
        return ""
    identity: list[str] = []
    if not run_git(ws, "config", "user.email", check=False).stdout.strip():
        identity = ["-c", "user.name=autospec", "-c", "user.email=autospec@localhost"]
    run_git(ws, *identity, "commit", "-q", "-F", "-", input_text=message)
    return run_git(ws, "rev-parse", "HEAD").stdout.strip()


def repo_tree(ws: Path, limit: int = 200) -> str:
    """Tracked + untracked non-ignored files, sorted, one per line, for prompts."""
    ws = Path(ws)
    proc = run_git(ws, "ls-files", "--cached", "--others", "--exclude-standard", "-z")
    files = sorted({p for p in proc.stdout.split("\0")
                    if p and not _is_factory_path(p) and (ws / p).exists()})
    lines = files[:limit]
    if len(files) > limit:
        lines.append(f"... {len(files) - limit} more")
    return "\n".join(lines)
