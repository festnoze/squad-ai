"""Product workspaces: layout (CONTRACTS.md section 2), toolchain plumbing and scaffold.

The scaffold is written by the factory, never by an agent, so every product starts from a
layout that already passes the factory's own checks: ``uv sync --locked``, the suite (no test
collected) and the smoke of its profile. ``uv_env`` and ``run_git`` are the only ways the
factory runs uv and git on a workspace (``verify`` uses them too).
"""

from __future__ import annotations

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
_LOCK_TIMEOUT_S = 300.0
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
    """Write the section 2 layout for ``profile``, lock it, ``git init`` and commit "scaffold".

    Refuses a workspace that already holds a project. Raises RuntimeError when uv or git
    fail, after removing everything it created: a half-made workspace (pyproject.toml but
    no lock or repository) would otherwise pass for a scaffolded one on resume.
    """
    if profile is Profile.FULLSTACK:
        raise NotImplementedError("the fullstack profile is phase 3")
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
    run_git(ws, "init", "-q", "-b", "main", require_repo=False)
    # Repo-local identity, and no CRLF conversion: fingerprints and restores see the
    # exact bytes the agents wrote.
    for key, value in (("user.name", "autospec"), ("user.email", "autospec@localhost"),
                       ("core.autocrlf", "false")):
        run_git(ws, "config", key, value)
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
    elif profile is Profile.API:
        files[f"{package}/app.py"] = _API_APP.format(title=repr(project_name))
        files[f"{package}/__main__.py"] = _API_MAIN.format(package=package)
    return files


def _toml_list(items: list[str]) -> str:
    if not items:
        return "[]"
    return "[\n" + "".join(f"    {json.dumps(item)},\n" for item in items) + "]"


def _pyproject(project_name: str, package: str, profile: Profile) -> str:
    api = profile is Profile.API
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
