"""core/verify.py: clean suite, smoke, traceability and git helpers, with real uv and git."""

from __future__ import annotations

import os
import shutil
import sys
import textwrap
import time
from pathlib import Path

import pytest
from autospec.core.models import AcceptanceCriterion, AcceptanceTest, Profile, Story
from autospec.core.procs import run_capped
from autospec.core.profiles import VERIFY_VENV, run_git, scaffold, uv_env
from autospec.core.verify import (
    SuiteResult,
    _load_report,
    arun_suite,
    asmoke,
    changed_paths,
    discard_changes,
    fingerprint,
    git_commit,
    missing_criteria,
    red_check,
    repo_tree,
)

PROFILES = [Profile.LIB, Profile.CLI, Profile.API]


@pytest.fixture(scope="module")
def templates(tmp_path_factory) -> dict:
    root = tmp_path_factory.mktemp("templates")
    result = {}
    for profile in PROFILES:
        scaffold(root / profile.value, project_name="Shop", package="shop", profile=profile)
        result[profile] = root / profile.value
    return result


@pytest.fixture
def make_ws(templates: dict, tmp_path: Path):
    """A fresh copy of a scaffolded workspace (repository included, no verify-venv)."""
    def make(profile: Profile = Profile.LIB) -> Path:
        ws = tmp_path / profile.value
        shutil.copytree(templates[profile], ws, ignore=shutil.ignore_patterns(".autospec"))
        return ws
    return make


def write(ws: Path, rel: str, text: str) -> Path:
    target = ws / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(textwrap.dedent(text), encoding="utf-8", newline="\n")
    return target


def is_alive(pid: int) -> bool:
    if sys.platform == "win32":
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
            return code.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


# --------------------------------------------------------------------------- suite


async def test_suite_green_with_fastapi_testclient(make_ws) -> None:
    ws = make_ws(Profile.API)
    write(ws, "tests/unit/test_health.py", """
        from fastapi.testclient import TestClient
        from shop.app import create_app

        def test_health():
            assert TestClient(create_app()).get("/health").json() == {"status": "ok"}
    """)
    write(ws, "tests/acceptance/test_us_1.py", "def test_ac1_ok():\n    assert True\n")
    result = await arun_suite(ws)
    assert result.ok, result.output_tail
    assert result.returncode == 0 and result.collection_errors == [] and result.env_error == ""
    assert result.outcomes == {"tests/unit/test_health.py::test_health": "passed",
                               "tests/acceptance/test_us_1.py::test_ac1_ok": "passed"}
    assert result.duration_s > 0


async def test_suite_red_keeps_the_end_of_the_output(make_ws) -> None:
    ws = make_ws()
    write(ws, "tests/unit/test_a.py", """
        import pytest

        def test_ok():
            assert True

        def test_bad():
            print("noise " * 2000)
            assert 1 == 2

        @pytest.mark.skip
        def test_skipped():
            pass

        @pytest.mark.xfail
        def test_xfail():
            assert False
    """)
    result = await arun_suite(ws)
    assert not result.ok and result.returncode == 1
    assert result.outcomes == {"tests/unit/test_a.py::test_ok": "passed",
                               "tests/unit/test_a.py::test_bad": "failed",
                               "tests/unit/test_a.py::test_skipped": "skipped",
                               "tests/unit/test_a.py::test_xfail": "skipped"}
    assert len(result.output_tail) <= 4000
    assert "1 failed, 1 passed" in result.output_tail  # the summary is at the very end


async def test_suite_collection_error(make_ws) -> None:
    ws = make_ws()
    write(ws, "tests/acceptance/test_us_1.py", "from shop.cart import Cart\n\ndef test_ac1():\n    assert Cart\n")
    write(ws, "tests/unit/test_fine.py", "def test_fine():\n    assert True\n")
    result = await arun_suite(ws)
    assert not result.ok and result.returncode == 2
    assert result.collection_errors == ["tests/acceptance/test_us_1.py"]
    assert "shop.cart" in result.output_tail
    # A test that cannot even be collected did not pass: the red check accepts it.
    assert red_check(result, ["tests/acceptance/test_us_1.py::test_ac1"]) == []


async def test_suite_select_restricts_the_run(make_ws) -> None:
    ws = make_ws()
    write(ws, "tests/acceptance/test_us_1.py", "def test_ac1():\n    assert False\n\ndef test_ac2():\n    assert True\n")
    write(ws, "tests/unit/test_other.py", "def test_other():\n    assert False\n")
    result = await arun_suite(ws, select=["tests/acceptance/test_us_1.py::test_ac2"])
    assert result.ok, result.output_tail
    assert result.outcomes == {"tests/acceptance/test_us_1.py::test_ac2": "passed"}
    result = await arun_suite(ws, select=["tests/acceptance"], clean=False)
    assert set(result.outcomes) == {"tests/acceptance/test_us_1.py::test_ac1",
                                    "tests/acceptance/test_us_1.py::test_ac2"}


async def test_dependency_missing_from_pyproject_fails_the_clean_suite(make_ws) -> None:
    """The REM-04 lesson: green in the dev venv, red in an environment built from the lock."""
    ws = make_ws()
    write(ws, "shop/__init__.py", "import six\n\nVERSION = six.PY3\n")
    write(ws, "tests/unit/test_shop.py", "import shop\n\ndef test_version():\n    assert shop.VERSION\n")
    env = {k: v for k, v in os.environ.items() if k not in ("VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT")}
    assert run_capped(["uv", "sync"], cwd=ws, env=env, timeout_s=300).returncode == 0
    python = ws / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    installed = run_capped(["uv", "pip", "install", "--python", str(python), "six"], cwd=ws, env=env,
                           timeout_s=300)
    assert installed.returncode == 0, installed.stderr
    local = run_capped([str(python), "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=ws, env=env,
                       timeout_s=120)
    assert local.returncode == 0, local.stdout  # the dev venv says green

    result = await arun_suite(ws)
    assert not result.ok
    assert "No module named 'six'" in result.output_tail


async def test_lock_out_of_date_is_an_env_error(make_ws) -> None:
    ws = make_ws()
    pyproject = ws / "pyproject.toml"
    pyproject.write_text(pyproject.read_text(encoding="utf-8").replace(
        "dependencies = []", 'dependencies = ["six"]'), encoding="utf-8")
    result = await arun_suite(ws)
    assert not result.ok and result.returncode is None and result.outcomes == {}
    assert "uv sync --locked" in result.env_error and "uv lock" in result.env_error
    assert result.output_tail == result.env_error


async def test_missing_report_does_not_crash(make_ws) -> None:
    ws = make_ws()
    write(ws, "tests/conftest.py", "import os\n\ndef pytest_configure(config):\n    os._exit(3)\n")
    result = await arun_suite(ws)
    assert not result.ok and result.returncode == 3 and result.outcomes == {}
    assert "no readable pytest-json-report" in result.output_tail


def test_corrupt_report_is_unreadable(tmp_path: Path) -> None:
    (tmp_path / "a.json").write_text('{"tests": [', encoding="utf-8")
    (tmp_path / "b.json").write_text("[1, 2]", encoding="utf-8")
    assert _load_report(tmp_path / "a.json") is None
    assert _load_report(tmp_path / "b.json") is None
    assert _load_report(tmp_path / "missing.json") is None


async def test_clean_rebuilds_the_verify_venv(make_ws) -> None:
    ws = make_ws()
    assert (await arun_suite(ws)).ok
    marker = ws / VERIFY_VENV / "marker.txt"
    marker.write_text("stale", encoding="utf-8")
    assert (await arun_suite(ws, clean=False)).ok and marker.exists()
    assert (await arun_suite(ws, clean=True)).ok and not marker.exists()


async def test_suite_timeout(make_ws) -> None:
    ws = make_ws()
    write(ws, "tests/unit/test_slow.py", "import time\n\ndef test_slow():\n    time.sleep(120)\n")
    started = time.monotonic()
    result = await arun_suite(ws, timeout_s=10)
    assert time.monotonic() - started < 40
    assert not result.ok and result.returncode is None
    assert "timeout" in result.output_tail


def test_uv_env_isolates_the_product(monkeypatch, tmp_path: Path) -> None:
    outer = tmp_path / "outer-venv"
    scripts = outer / ("Scripts" if sys.platform == "win32" else "bin")
    monkeypatch.setenv("VIRTUAL_ENV", str(outer))
    monkeypatch.setenv("PATH", os.pathsep.join([str(scripts), "/usr/bin"]))
    monkeypatch.setenv("PYTHONPATH", "/somewhere")
    env = uv_env(tmp_path / "ws")
    assert "VIRTUAL_ENV" not in env and "PYTHONPATH" not in env
    assert str(scripts) not in env["PATH"].split(os.pathsep)
    assert env["UV_PROJECT_ENVIRONMENT"] == str((tmp_path / "ws" / VERIFY_VENV).resolve())


# --------------------------------------------------------------------------- smoke


async def test_smoke_lib_fails_on_import_error(make_ws) -> None:
    ws = make_ws(Profile.LIB)
    write(ws, "shop/__init__.py", "raise ImportError('broken on purpose')\n")
    result = await asmoke(ws, package="shop", profile=Profile.LIB)
    assert not result.ok and "broken on purpose" in result.detail


async def test_smoke_cli_needs_exit_0_and_stdout(make_ws) -> None:
    ws = make_ws(Profile.CLI)
    write(ws, "shop/__main__.py", "raise SystemExit(0)\n")
    result = await asmoke(ws, package="shop", profile=Profile.CLI)
    assert not result.ok and "nothing on stdout" in result.detail
    write(ws, "shop/__main__.py", "import sys\nprint('usage: shop')\nsys.exit(2)\n")
    result = await asmoke(ws, package="shop", profile=Profile.CLI)
    assert not result.ok and "exit 2" in result.detail


async def test_smoke_api_crash_at_startup_fails_fast(make_ws) -> None:
    ws = make_ws(Profile.API)
    write(ws, "shop/__main__.py", "raise RuntimeError('boom at startup')\n")
    started = time.monotonic()
    result = await asmoke(ws, package="shop", profile=Profile.API, timeout_s=60)
    assert time.monotonic() - started < 30
    assert not result.ok
    assert "exited with code" in result.detail and "boom at startup" in result.detail


async def test_smoke_api_unhealthy_server_is_killed_with_its_tree(make_ws) -> None:
    ws = make_ws(Profile.API)
    write(ws, "shop/__main__.py", """
        import os
        from pathlib import Path

        Path("server.pid").write_text(str(os.getpid()))

        import uvicorn
        from fastapi import FastAPI

        app = FastAPI()

        @app.get("/health")
        def health():
            raise RuntimeError("health is broken")

        uvicorn.run(app, host="127.0.0.1", port=int(os.environ["PORT"]))
    """)
    result = await asmoke(ws, package="shop", profile=Profile.API, timeout_s=15)
    assert not result.ok and "no 200" in result.detail and "last: 500" in result.detail
    pid = int((ws / "server.pid").read_text())
    deadline = time.monotonic() + 10
    while is_alive(pid) and time.monotonic() < deadline:
        time.sleep(0.2)
    assert not is_alive(pid), "the real server (grandchild of uv) survived the smoke"


async def test_smoke_rejects_a_bad_package_name(make_ws) -> None:
    result = await asmoke(make_ws(), package="shop; rm -rf /", profile=Profile.LIB)
    assert not result.ok and "invalid package name" in result.detail


# --------------------------------------------------------------------------- traceability


def _result(outcomes: dict[str, str]) -> SuiteResult:
    return SuiteResult(ok=True, returncode=0, outcomes=outcomes, collection_errors=[], output_tail="")


def test_red_check_returns_the_nodeids_that_passed() -> None:
    result = _result({"t.py::a": "passed", "t.py::b": "failed", "t.py::c": "error", "t.py::d": "skipped"})
    assert red_check(result, ["t.py::a", "t.py::b", "t.py::c", "t.py::d", "t.py::absent"]) == ["t.py::a"]
    assert red_check(result, []) == []


def test_missing_criteria() -> None:
    story = Story(
        id="US-1", epic_id="EPIC-1", title="Cart",
        criteria=[AcceptanceCriterion(id=f"US-1.AC-{n}", text="x") for n in (1, 2, 3, 4)],
        acceptance_tests=[
            AcceptanceTest(ac_id="US-1.AC-1", nodeids=["t.py::a1", "t.py::a1_bis"]),
            AcceptanceTest(ac_id="US-1.AC-2", nodeids=["t.py::a2"]),
            AcceptanceTest(ac_id="US-1.AC-3", nodeids=["t.py::a3"]),
            # US-1.AC-4 has no acceptance test at all.
        ],
    )
    result = _result({"t.py::a1": "failed", "t.py::a1_bis": "passed", "t.py::a2": "skipped"})
    assert missing_criteria(story, result) == ["US-1.AC-2", "US-1.AC-3", "US-1.AC-4"]
    everything = _result(dict.fromkeys(("t.py::a1", "t.py::a2", "t.py::a3"), "passed"))
    assert missing_criteria(story, everything) == ["US-1.AC-4"]


def test_fingerprint(tmp_path: Path) -> None:
    write(tmp_path, "tests/acceptance/test_us_1.py", "def test_a():\n    assert True\n")
    paths = ["tests/acceptance/test_us_1.py", "tests\\acceptance\\test_us_2.py"]
    first = fingerprint(tmp_path, paths)
    assert first["tests/acceptance/test_us_1.py"] != ""
    assert first["tests/acceptance/test_us_2.py"] == ""  # missing file, backslashes normalized
    assert fingerprint(tmp_path, paths) == first
    write(tmp_path, "tests/acceptance/test_us_1.py", "def test_a():\n    assert  True\n")
    assert fingerprint(tmp_path, paths) != first

    folder = fingerprint(tmp_path, ["tests/acceptance"])
    assert list(folder) == ["tests/acceptance/test_us_1.py"]
    write(tmp_path, "tests/acceptance/__pycache__/x.pyc", "bytecode")
    assert fingerprint(tmp_path, ["tests/acceptance"]) == folder
    write(tmp_path, "tests/acceptance/conftest.py", "# patches the tests\n")
    assert fingerprint(tmp_path, ["tests/acceptance/"]) != folder  # an added file shows up


# --------------------------------------------------------------------------- git


def _dirty(ws: Path) -> None:
    write(ws, "shop/__init__.py", "VALUE = 2\n")  # modified
    (ws / "tests/unit/__init__.py").unlink()  # deleted
    write(ws, "shop/extra/new.py", "NEW = 1\n")  # untracked, nested
    write(ws, "tests/acceptance/test_us_1.py", "def test_x():\n    pass\n")
    run_git(ws, "add", "tests/acceptance/test_us_1.py")  # added to the index
    write(ws, ".autospec/state.json", "{}")  # factory-owned
    write(ws, ".venv/keep.txt", "ignored")
    write(ws, "shop/__pycache__/x.pyc", "ignored")
    write(ws, "data.db", "ignored")


def test_changed_paths(make_ws) -> None:
    ws = make_ws()
    assert changed_paths(ws) == []
    _dirty(ws)
    run_git(ws, "mv", ".python-version", "python-version.txt")  # staged rename: both sides
    assert changed_paths(ws) == [".python-version", "python-version.txt", "shop/__init__.py",
                                 "shop/extra/new.py", "tests/acceptance/test_us_1.py",
                                 "tests/unit/__init__.py"]


def test_discard_changes(make_ws) -> None:
    ws = make_ws()
    original = (ws / "shop/__init__.py").read_bytes()
    _dirty(ws)
    discard_changes(ws, ["tests/acceptance/"])
    assert not (ws / "tests/acceptance/test_us_1.py").exists()
    assert "shop/__init__.py" in changed_paths(ws)  # outside the given paths: untouched
    discard_changes(ws, ["shop/__init__.py", "already/clean.py", "pyproject.toml"])
    assert (ws / "shop/__init__.py").read_bytes() == original
    discard_changes(ws)
    assert changed_paths(ws) == []
    assert (ws / "tests/unit/__init__.py").exists() and not (ws / "shop/extra").exists()
    for kept in (".autospec/state.json", ".venv/keep.txt", "shop/__pycache__/x.pyc", "data.db"):
        assert (ws / kept).exists(), kept
    discard_changes(ws)  # already clean: no error


def test_git_commit(make_ws, tmp_path: Path) -> None:
    ws = make_ws()
    assert git_commit(ws, "nothing") == ""
    write(ws, "shop/core.py", "X = 1\n")
    write(ws, ".autospec/state.json", "{}")
    # Even with .autospec/ no longer ignored, the factory directory is never committed.
    write(ws, ".gitignore", ".venv/\n__pycache__/\n")
    sha = git_commit(ws, "US-1 done\n\nsecond line")
    assert len(sha) == 40 and sha == run_git(ws, "rev-parse", "HEAD").stdout.strip()
    assert run_git(ws, "log", "-1", "--format=%B").stdout.strip() == "US-1 done\n\nsecond line"
    tracked = run_git(ws, "ls-files").stdout.split()
    assert "shop/core.py" in tracked and not any(p.startswith(".autospec") for p in tracked)
    assert git_commit(ws, "again") == ""
    (tmp_path / "plain").mkdir()
    with pytest.raises(RuntimeError, match="not a git workspace"):
        git_commit(tmp_path / "plain", "x")


def test_repo_tree(make_ws) -> None:
    ws = make_ws()
    write(ws, "shop/models.py", "")
    write(ws, ".autospec/state.json", "{}")
    write(ws, ".venv/x.py", "")
    tree = repo_tree(ws).splitlines()
    assert tree == sorted(tree)
    assert "shop/models.py" in tree and "uv.lock" in tree and "tests/unit/__init__.py" in tree
    assert not any(line.startswith((".autospec", ".venv")) for line in tree)
    short = repo_tree(ws, limit=3).splitlines()
    assert short[:3] == tree[:3] and short[3] == f"... {len(tree) - 3} more"
