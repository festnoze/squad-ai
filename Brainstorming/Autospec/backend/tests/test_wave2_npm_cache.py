"""P2-B (GENERATION_FUSION_REVIEW): one npm download cache shared by every
per-worktree frontend install.

The streams build gives each frontend work item its own git worktree, and each
worktree gets its OWN hermetic ``npm ci`` (a junction to the shared install is
not an option - see ``_aensure_frontend_node_modules``). Without a shared cache
every one of those installs re-downloads the same tarballs.

``NPM_SHARED_CACHE`` (``settings.npm_shared_cache``) points them all at
``<workspace_root>/_npm-cache`` and adds ``--prefer-offline``, so only the first
install of a package hits the network. ``node_modules`` stays per worktree - only
the download cache is shared, and npm's cache is concurrency-safe.
"""

import subprocess
from pathlib import Path

import pytest

from autospec.agents.scripted import ScriptedRunner
from autospec.config import settings
from autospec.models import Epic, ProjectState, Stream, StreamKind, UserStory
from autospec.orchestrator.pipeline import Pipeline


class _Completed:
    """Minimal stand-in for ``subprocess.CompletedProcess``."""

    returncode = 0
    stdout = ""


def _pipeline() -> Pipeline:
    state = ProjectState(id="npm-cache-proj", name="npmapp", goal="g")
    state.epics.append(Epic(id="EPIC-1", title="E"))
    state.streams = [
        Stream(id="frontend", kind=StreamKind.FRONTEND, language="ts", primary=True)
    ]
    state.stories = [
        UserStory(id="US-1", epic_id="EPIC-1", title="US-1", stream="frontend")
    ]
    return Pipeline(state, ScriptedRunner())


@pytest.fixture
def captured_npm(monkeypatch, tmp_path):
    """Capture the argv ``_anpm_install_in`` really launches, without running npm.

    ``_node_modules_usable`` is neutralised too: the helper probes it right after
    the run, and a tmp root has no ``node_modules``.
    """
    calls: list[list[str]] = []

    def _fake_run(self, cmd, cwd, env):
        calls.append(list(cmd))
        return _Completed()

    monkeypatch.setattr(Pipeline, "_run_suite_process", _fake_run)
    monkeypatch.setattr(Pipeline, "_resolve_cmd", staticmethod(lambda cmd: list(cmd)))
    monkeypatch.setattr(Pipeline, "_node_modules_usable", staticmethod(lambda root: True))
    monkeypatch.setattr(settings, "workspace_root", tmp_path / "ws")
    return calls


async def test_the_shared_cache_is_passed_to_every_install(captured_npm, tmp_path):
    """Flag ON (production default): ``--cache <workspace_root>/_npm-cache`` and
    ``--prefer-offline`` are on the command line, and the directory exists."""
    root = tmp_path / "wt"
    root.mkdir()
    pipeline = _pipeline()

    assert await pipeline._anpm_install_in(root, use_ci=True) is True

    argv = captured_npm[0]
    cache = (settings.workspace_root).resolve() / "_npm-cache"
    assert "--cache" in argv
    assert argv[argv.index("--cache") + 1] == str(cache)
    assert "--prefer-offline" in argv
    assert cache.is_dir()
    # The historic arguments are untouched - only the cache is added.
    assert argv[1] == "install"          # no package-lock.json in this root
    assert "--no-audit" in argv and "--no-fund" in argv


async def test_the_flag_off_restores_the_default_npm_cache(
    captured_npm, tmp_path, monkeypatch
):
    """Flag OFF: byte-identical legacy argv (npm's own per-user cache)."""
    monkeypatch.setattr(settings, "npm_shared_cache", False)
    root = tmp_path / "wt-off"
    root.mkdir()
    (root / "package-lock.json").write_text("{}", encoding="utf-8")
    pipeline = _pipeline()

    assert await pipeline._anpm_install_in(root, use_ci=True) is True

    argv = captured_npm[0]
    assert "--cache" not in argv
    assert "--prefer-offline" not in argv
    assert argv[1] == "ci"               # the lockfile still drives ci vs install
    assert not (settings.workspace_root / "_npm-cache").exists()


async def test_a_relative_workspace_root_is_resolved(captured_npm, tmp_path, monkeypatch):
    """``WORKSPACE_ROOT`` may be relative; npm is handed an ABSOLUTE cache path,
    because each install runs with its own worktree as cwd."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(settings, "workspace_root", Path("rel-ws"))
    root = tmp_path / "wt-rel"
    root.mkdir()
    pipeline = _pipeline()

    assert await pipeline._anpm_install_in(root, use_ci=False) is True

    argv = captured_npm[0]
    cache = argv[argv.index("--cache") + 1]
    assert Path(cache).is_absolute()
    assert cache.endswith("_npm-cache")
