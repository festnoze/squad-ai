"""core/profiles.py: package names and the scaffold, checked with real uv and git."""

from __future__ import annotations

import keyword

import pytest
import tomllib
from autospec.core import profiles
from autospec.core.models import Profile
from autospec.core.procs import ProcResult
from autospec.core.profiles import GITIGNORE, PYTHON_VERSION, package_name, run_git, scaffold
from autospec.core.verify import arun_suite, asmoke, changed_paths

PROFILES = [Profile.LIB, Profile.CLI, Profile.API]
COMMON_FILES = {".gitignore", ".python-version", "pyproject.toml", "uv.lock", "tests/__init__.py",
                "tests/acceptance/__init__.py", "tests/unit/__init__.py"}
PROFILE_FILES = {
    Profile.LIB: {"todo/__init__.py"},
    Profile.CLI: {"todo/__init__.py", "todo/__main__.py"},
    Profile.API: {"todo/__init__.py", "todo/__main__.py", "todo/app.py"},
}


@pytest.fixture(scope="module")
def workspaces(tmp_path_factory) -> dict:
    root = tmp_path_factory.mktemp("scaffold")
    result = {}
    for profile in PROFILES:
        ws = root / profile.value
        # The pipeline may create its factory directory before scaffolding.
        (ws / ".autospec").mkdir(parents=True)
        (ws / ".autospec" / "state.json").write_text("{}", encoding="utf-8")
        scaffold(ws, project_name=f"Todo {profile.value} Crème", package="todo", profile=profile)
        result[profile] = ws
    return result


@pytest.mark.parametrize("project_name, expected", [
    ("Todo CLI", "todo_cli"),
    ("  Café   Crème!! ", "cafe_creme"),
    ("Straße & Œuvre", "strasse_oeuvre"),
    ("2048 Game", "app_2048_game"),
    ("class", "class_app"),
    ("json", "json_app"),
    ("Tests", "tests_app"),
    ("FastAPI", "fastapi_app"),
    ("___", "app"),
    ("日本語", "app"),
    ("", "app"),
    ("my-api.v2", "my_api_v2"),
])
def test_package_name(project_name: str, expected: str) -> None:
    assert package_name(project_name) == expected


@pytest.mark.parametrize("project_name", ["None", "import", "1", "9 lives", "_x_", "a" * 200, "Ünïcödé €", "def"])
def test_package_name_is_always_a_safe_identifier(project_name: str) -> None:
    name = package_name(project_name)
    assert name.isidentifier() and name.isascii() and not keyword.iskeyword(name)
    assert not name[0].isdigit() and len(name) <= 45


@pytest.mark.parametrize("profile", PROFILES, ids=lambda p: p.value)
def test_scaffold_layout(workspaces: dict, profile: Profile) -> None:
    ws = workspaces[profile]
    tracked = set(run_git(ws, "ls-files").stdout.split())
    assert tracked == COMMON_FILES | PROFILE_FILES[profile]
    assert run_git(ws, "log", "--format=%an|%s").stdout.strip() == "autospec|scaffold"
    assert run_git(ws, "config", "core.autocrlf").stdout.strip() == "false"
    assert changed_paths(ws) == []
    assert (ws / ".python-version").read_text(encoding="utf-8") == f"{PYTHON_VERSION}\n"
    assert (ws / ".gitignore").read_text(encoding="utf-8") == GITIGNORE

    project = tomllib.loads((ws / "pyproject.toml").read_text(encoding="utf-8"))
    assert project["project"]["name"] == "todo"
    assert project["project"]["description"] == f"Todo {profile.value} Crème"
    assert project["project"]["requires-python"] == ">=3.12"
    assert project["tool"]["pytest"]["ini_options"] == {"pythonpath": ["."], "testpaths": ["tests"]}
    dev = " ".join(project["dependency-groups"]["dev"])
    runtime = " ".join(project["project"]["dependencies"])
    assert "pytest>=" in dev and "pytest-json-report" in dev
    assert ("httpx" in dev) == (profile is Profile.API)
    assert ("fastapi" in runtime and "uvicorn" in runtime) == (profile is Profile.API)


@pytest.mark.parametrize("profile", PROFILES, ids=lambda p: p.value)
async def test_scaffold_passes_suite_and_smoke_out_of_the_box(workspaces: dict, profile: Profile) -> None:
    ws = workspaces[profile]
    suite = await arun_suite(ws)  # `uv sync --locked` from a deleted venv, then pytest
    assert suite.ok, suite.output_tail
    assert (suite.returncode, suite.outcomes, suite.collection_errors, suite.env_error) == (5, {}, [], "")
    smoke = await asmoke(ws, package="todo", profile=profile)
    assert smoke.ok, smoke.detail
    assert changed_paths(ws) == []  # verification never dirties the repository


def test_scaffold_api_wiring(workspaces: dict) -> None:
    ws = workspaces[Profile.API]
    main = (ws / "todo" / "__main__.py").read_text(encoding="utf-8")
    assert 'os.environ.get("PORT", "8000")' in main and 'host="127.0.0.1"' in main
    assert "def create_app() -> FastAPI:" in (ws / "todo" / "app.py").read_text(encoding="utf-8")


def test_scaffold_refuses_an_existing_project(tmp_path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    with pytest.raises(FileExistsError):
        scaffold(tmp_path, project_name="X", package="x", profile=Profile.LIB)


def test_scaffold_rejects_bad_input(tmp_path) -> None:
    with pytest.raises(NotImplementedError):
        scaffold(tmp_path, project_name="X", package="x", profile=Profile.FULLSTACK)
    for bad in ("my-pkg", "class", "9x", "café"):
        with pytest.raises(ValueError):
            scaffold(tmp_path, project_name="X", package=bad, profile=Profile.LIB)
    assert list(tmp_path.iterdir()) == []


def test_scaffold_failure_leaves_the_workspace_as_found(tmp_path, monkeypatch) -> None:
    state = tmp_path / ".autospec" / "state.json"
    state.parent.mkdir()
    state.write_text("{}", encoding="utf-8")

    def no_network(*args, **kwargs) -> ProcResult:
        return ProcResult(returncode=2, stdout="", stderr="no network", timed_out=False, duration_s=0.0)

    with monkeypatch.context() as patch:
        patch.setattr(profiles, "run_capped", no_network)
        with pytest.raises(RuntimeError, match="uv lock failed"):
            scaffold(tmp_path, project_name="X", package="x", profile=Profile.LIB)
    assert [p.name for p in tmp_path.iterdir()] == [".autospec"]

    real_git = profiles.run_git

    def refuse_commit(ws, *args, **kwargs):
        if "commit" in args:
            raise RuntimeError("commit refused")
        return real_git(ws, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(profiles, "run_git", refuse_commit)
        with pytest.raises(RuntimeError, match="commit refused"):
            scaffold(tmp_path, project_name="X", package="x", profile=Profile.LIB)
    # .git (read-only object files on Windows) is gone too; the factory state is kept.
    assert [p.name for p in tmp_path.iterdir()] == [".autospec"]
    assert state.read_text(encoding="utf-8") == "{}"
    scaffold(tmp_path, project_name="X", package="x", profile=Profile.LIB)  # a retry works
    assert (tmp_path / "uv.lock").is_file() and changed_paths(tmp_path) == []
