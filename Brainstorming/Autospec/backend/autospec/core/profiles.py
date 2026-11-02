"""Product workspaces: layout (CONTRACTS.md sections 2 and 8.1), toolchain plumbing, scaffold.

The scaffold is written by the factory, never by an agent, so every product starts from a
layout that already passes the factory's own checks: ``uv sync --locked``, the suite (no
Python test collected; the frontend smoke test for fullstack) and the smoke of its profile.
``uv_env``, ``run_git``, ``npm_command`` and ``npm_env`` are the only ways the factory runs
uv, git and npm on a workspace (``verify`` uses them too).
"""

from __future__ import annotations

import html
import json
import keyword
import os
import re
import shutil
import stat
import sys
import unicodedata
from pathlib import Path

from autospec.core.models import Profile
from autospec.core.procs import ProcResult, run_capped

PYTHON_VERSION = "3.12"
FACTORY_DIR = ".autospec"  # factory-owned, git-ignored, never committed nor restored
VERIFY_VENV = Path(FACTORY_DIR) / "verify-venv"
GITIGNORE = ".venv/\n__pycache__/\n.pytest_cache/\n*.db\n*.sqlite*\n.autospec/\n"
FRONTEND_DIR = "frontend"
FRONTEND_GITIGNORE = GITIGNORE + f"{FRONTEND_DIR}/node_modules/\n{FRONTEND_DIR}/dist/\n"
# Never committed, listed for prompts, fingerprinted nor restored, whatever .gitignore says.
UNTRACKED_DIRS = (FACTORY_DIR, f"{FRONTEND_DIR}/node_modules", f"{FRONTEND_DIR}/dist")
_LOCK_TIMEOUT_S = 300.0
_NPM_TIMEOUT_S = 600.0
_GIT_TIMEOUT_S = 60.0
_DROPPED_ENV = ("VIRTUAL_ENV", "PYTHONPATH", "PYTHONHOME", "UV_PYTHON", "UV_FROZEN", "UV_NO_SYNC")
_MAX_PACKAGE_LEN = 40
# Top-level names the product must not shadow: the tests directory and the toolchain
# the factory itself imports inside the product environment.
_TAKEN_NAMES = frozenset({
    "tests", "test", "conftest", "pytest", "pytest_jsonreport", "pluggy", "iniconfig",
    "packaging", "pygments", "colorama", "fastapi", "starlette", "pydantic", "pydantic_core",
    "uvicorn", "httpx", "httpcore", "anyio", "sniffio", "idna", "certifi", "h11", "click",
    "typing_extensions", "annotated_types",
}) | frozenset(sys.stdlib_module_names) | frozenset(sys.builtin_module_names)
# Letters NFKD does not decompose into ASCII.
_TRANSLITERATION = str.maketrans({"ß": "ss", "æ": "ae", "Æ": "AE", "œ": "oe", "Œ": "OE",
                                  "ø": "o", "Ø": "O", "ł": "l", "Ł": "L", "đ": "d", "Đ": "D"})


def uv_env(ws: Path) -> dict[str, str]:
    """Environment for every uv call on a workspace: the project environment is the
    verify-venv; the caller's venv (and its PATH entry), PYTHONPATH and uv overrides are
    dropped so nothing from the factory leaks into the product."""
    env = dict(os.environ)
    outer_venv = env.get("VIRTUAL_ENV", "")
    for name in _DROPPED_ENV:
        env.pop(name, None)
    if outer_venv:
        bins = {os.path.normcase(str(Path(outer_venv) / sub)) for sub in ("Scripts", "bin")}
        entries = env.get("PATH", "").split(os.pathsep)
        env["PATH"] = os.pathsep.join(
            p for p in entries if os.path.normcase(p.rstrip("\\/")) not in bins)
    env["UV_PROJECT_ENVIRONMENT"] = str((Path(ws) / VERIFY_VENV).resolve())
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def npm_command() -> str:
    """npm's executable, resolved here because no shell does it: ``npm.cmd`` on Windows."""
    return shutil.which("npm") or "npm"


def npm_env() -> dict[str, str]:
    """Environment for every npm and node call: no color codes in the outputs we keep, CI
    mode (no prompt, no progress bar, ``.only`` refused by vitest), no audit or fund noise."""
    env = dict(os.environ)
    env.pop("FORCE_COLOR", None)  # Node warns when it is set together with NO_COLOR
    env.update(CI="1", NO_COLOR="1", npm_config_audit="false", npm_config_fund="false",
               npm_config_update_notifier="false")
    return env


def run_git(ws: Path, *args: str, check: bool = True, input_text: str | None = None,
            require_repo: bool = True) -> ProcResult:
    """Run git in ``ws``, raising RuntimeError on failure when ``check``.

    Refuses a workspace without its own ``.git``: git must never fall back to an
    enclosing repository (the default workspace root lives inside the Autospec repo).
    """
    ws = Path(ws)
    if require_repo and not (ws / ".git").exists():
        raise RuntimeError(f"{ws} is not a git workspace")
    env = {k: v for k, v in os.environ.items() if k not in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE")}
    env.update(GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0")
    proc = run_capped(["git", *args], cwd=ws, env=env, timeout_s=_GIT_TIMEOUT_S, input_text=input_text)
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed ({proc.returncode}): "
                           f"{(proc.stderr or proc.stdout)[-1000:]}")
    return proc


def package_name(project_name: str) -> str:
    """ASCII snake_case identifier for the product package: "Todo CLI" -> "todo_cli".

    Never a keyword, never starts with a digit, never shadows the stdlib, the tests
    directory or the toolchain ("json" -> "json_app").
    """
    text = unicodedata.normalize("NFKD", project_name.translate(_TRANSLITERATION))
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    name = re.sub(r"[^a-z0-9]+", "_", text).strip("_")[:_MAX_PACKAGE_LEN].rstrip("_")
    if not name:
        return "app"
    if name[0].isdigit():
        name = f"app_{name}"
    if keyword.iskeyword(name) or name in _TAKEN_NAMES:
        name = f"{name}_app"
    return name


def scaffold(ws: Path, *, project_name: str, package: str, profile: Profile) -> None:
    """Write the section 2 (and 8.1 for fullstack) layout for ``profile``, lock it (``uv
    lock``, plus ``npm install`` for package-lock.json), ``git init`` and commit "scaffold".

    Refuses a workspace that already holds a project. Raises RuntimeError when uv, npm or
    git fail, after removing everything it created: a half-made workspace (pyproject.toml
    but no lock or repository) would otherwise pass for a scaffolded one on resume.
    """
    if not package.isidentifier() or keyword.iskeyword(package) or not package.isascii():
        raise ValueError(f"invalid package name {package!r}")
    ws = Path(ws)
    if (ws / "pyproject.toml").exists() or (ws / ".git").exists():
        raise FileExistsError(f"{ws} already holds a project")
    ws.mkdir(parents=True, exist_ok=True)
    before = set(os.listdir(ws))
    try:
        _build(ws, project_name, package, profile)
    except BaseException:
        for name in set(os.listdir(ws)) - before:
            _remove(ws / name)
        raise


def _build(ws: Path, project_name: str, package: str, profile: Profile) -> None:
    for rel, content in _layout(project_name, package, profile).items():
        target = ws / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")
    lock = run_capped(["uv", "lock"], cwd=ws, env=uv_env(ws), timeout_s=_LOCK_TIMEOUT_S)
    if lock.returncode != 0:
        raise RuntimeError(f"uv lock failed: {(lock.stdout + lock.stderr)[-2000:]}")
    if profile is Profile.FULLSTACK:  # writes package-lock.json, which `npm ci` then needs
        # Resolved: Vite and npm misbehave under a Windows 8.3 short-name cwd.
        install = run_capped([npm_command(), "install"], cwd=(ws / FRONTEND_DIR).resolve(),
                             env=npm_env(), timeout_s=_NPM_TIMEOUT_S)
        if install.returncode != 0:
            raise RuntimeError(f"npm install failed: {(install.stdout + install.stderr)[-2000:]}")
    run_git(ws, "init", "-q", "-b", "main", require_repo=False)
    # Repo-local identity, and no CRLF conversion: fingerprints and restores see the
    # exact bytes the agents wrote.
    for key, value in (("user.name", "autospec"), ("user.email", "autospec@localhost"),
                       ("core.autocrlf", "false")):
        run_git(ws, "config", key, value)
    # Ignored even if an agent rewrites .gitignore: `git add -A` would otherwise hash a
    # whole node_modules into the object store.
    exclude = ws / ".git" / "info" / "exclude"
    exclude.parent.mkdir(exist_ok=True)  # absent when git runs without templates
    with exclude.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write("".join(f"/{path}/\n" for path in UNTRACKED_DIRS))
    run_git(ws, "add", "-A")
    run_git(ws, "commit", "-q", "-m", "scaffold")


def _remove(path: Path) -> None:
    """Delete a file or a directory, read-only files included (git marks its objects so)."""
    def force(func, target, _exc) -> None:
        os.chmod(target, stat.S_IWRITE)
        func(target)

    if path.is_dir() and not path.is_symlink():
        handler = {"onexc": force} if sys.version_info >= (3, 12) else {"onerror": force}
        shutil.rmtree(path, **handler)
    else:
        path.unlink(missing_ok=True)


def _layout(project_name: str, package: str, profile: Profile) -> dict[str, str]:
    files = {
        "pyproject.toml": _pyproject(project_name, package, profile),
        ".python-version": f"{PYTHON_VERSION}\n",
        ".gitignore": GITIGNORE,
        f"{package}/__init__.py": f'"""{package}: the product package."""\n',
        # Packages, so a unit test and an acceptance test may share a file name.
        "tests/__init__.py": "",
        "tests/acceptance/__init__.py": "",
        "tests/unit/__init__.py": "",
    }
    if profile is Profile.CLI:
        files[f"{package}/__main__.py"] = _CLI_MAIN.format(package=package, title=repr(project_name))
    elif profile in (Profile.API, Profile.FULLSTACK):
        app = _FULLSTACK_APP if profile is Profile.FULLSTACK else _API_APP
        files[f"{package}/app.py"] = app.format(title=repr(project_name))
        files[f"{package}/__main__.py"] = _API_MAIN.format(package=package)
    if profile is Profile.FULLSTACK:
        files[".gitignore"] = FRONTEND_GITIGNORE
        files.update(_frontend_layout(project_name, package))
    return files


def _frontend_layout(project_name: str, package: str) -> dict[str, str]:
    title = json.dumps(project_name)  # a valid TypeScript string literal
    package_json = {
        "name": f"{package.replace('_', '-')}-frontend", "private": True, "version": "0.1.0",
        "type": "module",
        "scripts": {"dev": "vite", "build": "tsc --noEmit && vite build", "test": "vitest run"},
        "dependencies": NPM_DEPENDENCIES, "devDependencies": NPM_DEV_DEPENDENCIES,
    }
    files = {
        "package.json": json.dumps(package_json, indent=2) + "\n",
        "tsconfig.json": json.dumps(_TSCONFIG, indent=2) + "\n",
        "vite.config.ts": _VITE_CONFIG,
        "index.html": _INDEX_HTML.replace("__TITLE__", html.escape(project_name)),
        "src/main.tsx": _MAIN_TSX,
        "src/App.tsx": _APP_TSX.replace("__TITLE__", title),
        "src/App.test.tsx": _APP_TEST_TSX.replace("__TITLE__", title),
        "src/acceptance/.gitkeep": "",  # the QA agent's folder: us_<n>.test.tsx
    }
    return {f"{FRONTEND_DIR}/{rel}": content for rel, content in files.items()}


def _toml_list(items: list[str]) -> str:
    if not items:
        return "[]"
    return "[\n" + "".join(f"    {json.dumps(item)},\n" for item in items) + "]"


def _pyproject(project_name: str, package: str, profile: Profile) -> str:
    api = profile in (Profile.API, Profile.FULLSTACK)
    runtime = ["fastapi>=0.110", "uvicorn>=0.29"] if api else []
    dev = ["pytest>=8", "pytest-json-report>=1.5"] + (["httpx>=0.27"] if api else [])
    # json.dumps output is a valid TOML basic string.
    return (
        "[project]\n"
        f'name = "{package.replace("_", "-")}"\n'
        'version = "0.1.0"\n'
        f"description = {json.dumps(project_name)}\n"
        f'requires-python = ">={PYTHON_VERSION}"\n'
        f"dependencies = {_toml_list(runtime)}\n"
        "\n[dependency-groups]\n"
        f"dev = {_toml_list(dev)}\n"
        "\n[tool.pytest.ini_options]\n"
        'pythonpath = ["."]\n'
        'testpaths = ["tests"]\n'
    )


_CLI_MAIN = '''"""Command line entry point: `python -m {package}`."""

import argparse


def build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(prog="{package}", description={title})


def main(argv: list[str] | None = None) -> int:
    build_parser().parse_args(argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''

_API_APP = '''"""HTTP application factory."""

from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title={title})

    @app.get("/health")
    def health() -> dict[str, str]:
        return {{"status": "ok"}}

    return app
'''

_API_MAIN = '''"""HTTP entry point: `python -m {package}` serves on $PORT (default 8000)."""

import os

import uvicorn

from {package}.app import create_app


def main() -> None:
    uvicorn.run(create_app(), host="127.0.0.1", port=int(os.environ.get("PORT", "8000")))


if __name__ == "__main__":
    main()
'''

_FULLSTACK_APP = '''"""HTTP application factory: the API, plus the built frontend when it exists."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# Built by `npm --prefix frontend run build`; found from this file, never from the cwd.
DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"


def create_app() -> FastAPI:
    app = FastAPI(title={title})

    @app.get("/health")
    def health() -> dict[str, str]:
        return {{"status": "ok"}}

    # API routes go under /api/... (the Vite dev server proxies /api to port 8000).

    if (DIST / "index.html").is_file():
        @app.get("/", include_in_schema=False)
        def index() -> FileResponse:
            return FileResponse(DIST / "index.html")

        if (DIST / "assets").is_dir():
            app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    return app
'''

# Checked together on 2026-11-02 (Node 24.18, npm 11.6); `npm install` locks the newest match.
NPM_DEPENDENCIES = {"react": "^19.3.1", "react-dom": "^19.3.1"}
NPM_DEV_DEPENDENCIES = {
    "@testing-library/dom": "^10.4.2", "@testing-library/react": "^16.3.3",
    "@types/react": "^19.3.0", "@types/react-dom": "^19.3.0", "@vitejs/plugin-react": "^6.2.1",
    "jsdom": "^30.1.3", "typescript": "^7.0.2", "vite": "^8.3.5", "vitest": "^5.0.5",
}

# The build type-checks the product only: vitest transpiles the tests itself, and an
# acceptance test importing code that does not exist yet must not break the build.
_TSCONFIG = {
    "compilerOptions": {
        "target": "ES2022", "lib": ["ES2022", "DOM", "DOM.Iterable"], "module": "ESNext",
        "moduleResolution": "bundler", "jsx": "react-jsx", "types": ["vite/client"],
        "strict": True, "noEmit": True, "isolatedModules": True, "skipLibCheck": True,
        "allowImportingTsExtensions": True,
    },
    "include": ["src"],
    "exclude": ["src/**/*.test.ts", "src/**/*.test.tsx", "src/acceptance"],
}

_VITE_CONFIG = """import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
  // globals: Testing Library then unmounts what each test rendered.
  test: { environment: "jsdom", globals: true },
});
"""

_INDEX_HTML = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>__TITLE__</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
"""

_MAIN_TSX = """import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
"""

_APP_TSX = """export default function App() {
  return (
    <main>
      <h1>{__TITLE__}</h1>
    </main>
  );
}
"""

_APP_TEST_TSX = """import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import App from "./App";

describe("App", () => {
  it("renders the title", () => {
    render(<App />);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(__TITLE__);
  });
});
"""
