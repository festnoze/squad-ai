"""core/profiles.py: package names and the scaffold, checked with real uv, git and npm."""

from __future__ import annotations

import json
import keyword
import shutil
import textwrap
from pathlib import Path

import pytest
import tomllib
from autospec.core import profiles
from autospec.core.models import Profile
from autospec.core.procs import ProcResult, run_capped
from autospec.core.profiles import (
    FRONTEND_GITIGNORE,
    GITIGNORE,
    PYTHON_VERSION,
    UNTRACKED_DIRS,
    npm_command,
    package_name,
    run_git,
    scaffold,
    uv_env,
)
from autospec.core.verify import arun_suite, asmoke, changed_paths

PROFILES = [Profile.LIB, Profile.CLI, Profile.API, Profile.FULLSTACK]
COMMON_FILES = {".gitignore", ".python-version", "pyproject.toml", "uv.lock", "tests/__init__.py",
                "tests/acceptance/__init__.py", "tests/unit/__init__.py"}
API_FILES = {"todo/__init__.py", "todo/__main__.py", "todo/app.py"}
FRONTEND_FILES = {f"frontend/{rel}" for rel in (
    "package.json", "package-lock.json", "tsconfig.json", "vite.config.ts", "index.html",
    "src/main.tsx", "src/App.tsx", "src/App.test.tsx", "src/acceptance/.gitkeep")}
PROFILE_FILES = {
    Profile.LIB: {"todo/__init__.py"},
    Profile.CLI: {"todo/__init__.py", "todo/__main__.py"},
    Profile.API: API_FILES,
    Profile.FULLSTACK: API_FILES | FRONTEND_FILES,
}
WEB = (Profile.API, Profile.FULLSTACK)


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
    expected_ignore = FRONTEND_GITIGNORE if profile is Profile.FULLSTACK else GITIGNORE
    assert (ws / ".gitignore").read_text(encoding="utf-8") == expected_ignore
    exclude = (ws / ".git" / "info" / "exclude").read_text(encoding="utf-8").splitlines()
    assert all(f"/{path}/" in exclude for path in UNTRACKED_DIRS)

    project = tomllib.loads((ws / "pyproject.toml").read_text(encoding="utf-8"))
    assert project["project"]["name"] == "todo"
    assert project["project"]["description"] == f"Todo {profile.value} Crème"
    assert project["project"]["requires-python"] == ">=3.12"
    assert project["tool"]["pytest"]["ini_options"] == {"pythonpath": ["."], "testpaths": ["tests"]}
    dev = " ".join(project["dependency-groups"]["dev"])
    runtime = " ".join(project["project"]["dependencies"])
    assert "pytest>=" in dev and "pytest-json-report" in dev
    assert ("httpx" in dev) == (profile in WEB)
    assert ("fastapi" in runtime and "uvicorn" in runtime) == (profile in WEB)


@pytest.mark.parametrize("profile", PROFILES, ids=lambda p: p.value)
async def test_scaffold_passes_suite_and_smoke_out_of_the_box(workspaces: dict, profile: Profile) -> None:
    ws = workspaces[profile]
    suite = await arun_suite(ws)  # `uv sync --locked` from a deleted venv (and `npm ci`), then the tests
    assert suite.ok, suite.output_tail
    frontend = {"frontend/src/App.test.tsx::App > renders the title": "passed"}
    expected = frontend if profile is Profile.FULLSTACK else {}
    assert (suite.returncode, suite.outcomes, suite.collection_errors, suite.env_error) == (5, expected, [], "")
    smoke = await asmoke(ws, package="todo", profile=profile)
    assert smoke.ok, smoke.detail
    assert changed_paths(ws) == []  # verification never dirties the repository


def test_scaffold_api_wiring(workspaces: dict) -> None:
    for profile in WEB:
        ws = workspaces[profile]
        main = (ws / "todo" / "__main__.py").read_text(encoding="utf-8")
        assert 'os.environ.get("PORT", "8000")' in main and 'host="127.0.0.1"' in main
        assert "proxy_headers=False" in main
        app = (ws / "todo" / "app.py").read_text(encoding="utf-8")
        assert "def create_app() -> FastAPI:" in app and 'openapi_url="/openapi.json"' in app


# Serves the scaffold through its own `python -m` entry point (uvicorn.run as generated), with
# one extra route that echoes the peer address uvicorn hands to the app.
_SERVED_PROBE = textwrap.dedent("""
    import os, socket, sys, threading, time
    sys.path.insert(0, sys.argv[1])
    import httpx
    from fastapi import Request
    import todo.__main__ as entry

    make_app = entry.create_app

    def create_app():
        app = make_app()

        @app.get("/peer")
        def peer(request: Request) -> dict:
            return {"host": request.client.host}

        return app

    entry.create_app = create_app
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    os.environ["PORT"] = str(port)
    threading.Thread(target=entry.main, daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    with httpx.Client(trust_env=False, timeout=10) as client:
        deadline = time.monotonic() + 60
        while True:
            try:
                peer = client.get(base + "/peer", headers={"X-Forwarded-For": "203.0.113.9"})
                break
            except httpx.TransportError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.1)
        schema = client.get(base + "/openapi.json")
        print("PEER", peer.json()["host"], "OPENAPI", schema.status_code,
              "/health" in schema.json().get("paths", {}), flush=True)
    os._exit(0)  # the server thread never returns on its own
""")


@pytest.mark.parametrize("profile", WEB, ids=lambda p: p.value)
def test_scaffold_server_ignores_forwarded_headers_and_serves_openapi(
        workspaces: dict, profile: Profile, tmp_path: Path) -> None:
    """B5 SEC-04: uvicorn trusts X-Forwarded-For from 127.0.0.1 unless proxy_headers=False, so
    a forged header escaped a per-client login rate limit. B5 ARC-06: the OpenAPI document."""
    ws = workspaces[profile]
    probe = tmp_path / "probe.py"
    probe.write_text(_SERVED_PROBE, encoding="utf-8")
    proc = run_capped(["uv", "run", "--locked", "python", str(probe), str(ws)], cwd=ws,
                      env=uv_env(ws), timeout_s=300)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "PEER 127.0.0.1 OPENAPI 200 True" in proc.stdout, proc.stdout + proc.stderr
    assert changed_paths(ws) == []


def test_scaffold_fullstack_frontend(workspaces: dict) -> None:
    front = workspaces[Profile.FULLSTACK] / "frontend"
    package = json.loads((front / "package.json").read_text(encoding="utf-8"))
    assert package["name"] == "todo-frontend" and package["type"] == "module"
    assert package["scripts"]["build"].endswith("vite build") and package["scripts"]["test"] == "vitest run"
    assert set(package["dependencies"]) == {"react", "react-dom"}
    assert {"vite", "vitest", "jsdom", "@testing-library/react", "@vitejs/plugin-react",
            "typescript"} <= set(package["devDependencies"])
    lock = json.loads((front / "package-lock.json").read_text(encoding="utf-8"))
    assert lock["packages"]["node_modules/vitest"]["version"].startswith("5.")
    config = (front / "vite.config.ts").read_text(encoding="utf-8")
    assert "react()" in config and 'environment: "jsdom"' in config
    assert '"/api": "http://127.0.0.1:8000"' in config
    tsconfig = json.loads((front / "tsconfig.json").read_text(encoding="utf-8"))
    assert "src/acceptance" in tsconfig["exclude"]  # an acceptance test never breaks the build
    assert '<div id="root"></div>' in (front / "index.html").read_text(encoding="utf-8")
    assert "Cr\\u00e8me" in (front / "src" / "App.tsx").read_text(encoding="utf-8")
    assert (front / "node_modules").is_dir()  # installed, yet neither tracked nor changed


async def test_scaffold_fullstack_serves_dist_whatever_the_cwd(workspaces: dict, tmp_path: Path) -> None:
    """create_app() finds frontend/dist from its own file, not from the current directory."""
    ws = tmp_path / "ws"
    shutil.copytree(workspaces[Profile.FULLSTACK], ws,
                    ignore=shutil.ignore_patterns(".autospec", "node_modules", "dist"))
    (ws / "frontend" / "dist" / "assets").mkdir(parents=True)
    (ws / "frontend" / "dist" / "index.html").write_text('<div id="root"></div>', encoding="utf-8")
    (ws / "frontend" / "dist" / "assets" / "app.js").write_text("built()", encoding="utf-8")
    probe = tmp_path / "probe.py"
    probe.write_text(textwrap.dedent("""
        import os, sys
        sys.path.insert(0, sys.argv[1])
        from fastapi.testclient import TestClient
        from todo.app import create_app

        client = TestClient(create_app())
        print(os.getcwd(), client.get("/").status_code, client.get("/").text,
              client.get("/assets/app.js").text, client.get("/health").json())
    """), encoding="utf-8")
    elsewhere = ws / "frontend"  # uv still finds the project from here, python runs here
    proc = run_capped(["uv", "run", "--locked", "python", str(probe), str(ws)], cwd=elsewhere,
                      env=uv_env(ws), timeout_s=300)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert proc.stdout.strip().endswith("""200 <div id="root"></div> built() {'status': 'ok'}"""), proc.stdout

    shutil.rmtree(ws / "frontend" / "dist")  # without a build, the API alone
    proc = run_capped(["uv", "run", "--locked", "python", str(probe), str(ws)], cwd=elsewhere,
                      env=uv_env(ws), timeout_s=300)
    assert " 404 " in proc.stdout, proc.stdout + proc.stderr


def test_scaffold_refuses_an_existing_project(tmp_path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    with pytest.raises(FileExistsError):
        scaffold(tmp_path, project_name="X", package="x", profile=Profile.LIB)


def test_scaffold_rejects_bad_input(tmp_path) -> None:
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

    def npm_offline(argv, **kwargs) -> ProcResult:
        if argv[0] == npm_command():
            return no_network()
        return run_capped(argv, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(profiles, "run_capped", npm_offline)
        with pytest.raises(RuntimeError, match="npm install failed"):
            scaffold(tmp_path, project_name="X", package="x", profile=Profile.FULLSTACK)
    assert [p.name for p in tmp_path.iterdir()] == [".autospec"]  # frontend/ and uv.lock removed

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
