"""End-to-end *feature-factory* tests — the smart, LLM-free, closed loop.

The existing ``test_scripted_runner_drives_full_pipeline`` proves the
**orchestration** reaches DONE, but it sets ``fake_agents=True`` which
short-circuits the real ``uv run pytest`` — and the ``ScriptedRunner`` writes
**no real code**. So today the pipeline's green is *asserted by the agent*, never
*earned by running code*. That leaves the most important question untested: does
spec → plan → build actually yield a **working feature**?

These tests close that loop **deterministically, with no LLM and no UI**:

1. ``FixtureRunner`` plays the scripted agents (same canned PM/PO/QA replies as
   ``ScriptedRunner``) BUT, when the Dev agent runs, it materialises a **real,
   runnable app + real pytest tests** into the workspace (the runner receives the
   workspace as ``cwd`` — `pipeline.py:2645`).
2. ``_hermetic_pytest`` replaces ``Pipeline._arun_pytest`` so the orchestrator's
   own **"trust but verify"** step genuinely runs the produced suite — with the
   *current interpreter* (``python -m pytest``), so it's fast and hermetic (no
   ``uv`` venv build), mirroring the demo-mode app runner at `pipeline.py:3906`.

The pair matters: the **positive** test proves a correct factory ships a working
feature; the **negative** test feeds a buggy implementation and proves the verify
gate has *teeth* — it rejects red code (story → FAILED) instead of rubber-stamping
the agent's self-reported "green". Without the negative case, a closed loop that
always passes proves nothing.
"""

from __future__ import annotations

import asyncio
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from autospec.agents.runner import AgentResult
from autospec.agents.scripted import ScriptedRunner
from autospec.config import settings
from autospec.models import PipelinePhase, ProjectState, StoryStatus
from autospec.orchestrator import pytest_report
from autospec.orchestrator.pipeline import Pipeline
from autospec.storage import workspace_dir

from .conftest import wait_until

# --- The golden app the scripted PO plan asks for (US-1 add, US-2 subtract) ----

_GOOD_CORE = '''"""Calculatrice générée (fixture e2e)."""


def add(a, b):
    return a + b


def subtract(a, b):
    return a - b
'''

# A single, plausible bug: addition is wrong. US-1's tests must go red while
# US-2's subtraction tests stay green — proving the gate fails the *right* story.
_BROKEN_CORE = _GOOD_CORE.replace("return a + b", "return a - b  # bug injecté")

_TEST_ADD = '''from {pkg}.core import add


def test_addition_simple():
    assert add(2, 3) == 5


def test_addition_commutative():
    assert add(2, 3) == add(3, 2)
'''

_TEST_SUB = '''from {pkg}.core import subtract


def test_soustraction_simple():
    assert subtract(5, 3) == 2
'''

_STORY_RE = re.compile(r"User story à implémenter : (\S+)")


def _package_dir(ws: Path) -> Path:
    """The scaffolded package directory (the one holding ``__init__.py`` that
    isn't ``tests``). Avoids re-deriving the slug ``package_name`` produces."""
    for child in sorted(ws.iterdir()):
        if child.is_dir() and (child / "__init__.py").exists() and child.name != "tests":
            return child
    raise AssertionError(f"aucun package scaffoldé trouvé dans {ws}")


class FixtureRunner:
    """Scripted agents, but the Dev agent writes a **real** app into the workspace.

    Every non-Dev prompt routes to the exact same canned reply as
    ``ScriptedRunner`` (so plan/spec/QA behaviour is unchanged). On a backend Dev
    prompt it writes ``<pkg>/core.py`` plus the story's real pytest file under
    ``tests/`` into ``cwd`` (the workspace), then returns the green JSON. With
    ``broken=True`` it writes a buggy ``add`` to exercise the verify gate.
    """

    def __init__(self, broken: bool = False) -> None:
        self.broken = broken
        self.dev_calls = 0

    async def arun(
        self,
        prompt: str,
        system_prompt: str,
        cwd: Path | None = None,
        session_id: str | None = None,
        model: str | None = None,
    ) -> AgentResult:
        # Backend Dev prompt only (frontend dev / revise reuse the same marker but
        # we keep this e2e on the default backend path).
        if "PROCESSUS OBLIGATOIRE" in prompt and "FRONTEND" not in prompt and cwd:
            self._materialise(Path(cwd), prompt)
        return AgentResult(text=ScriptedRunner._reply_for(prompt), session_id="fixture-session")

    def _materialise(self, ws: Path, prompt: str) -> None:
        self.dev_calls += 1
        pkg = _package_dir(ws)
        (pkg / "core.py").write_text(
            _BROKEN_CORE if self.broken else _GOOD_CORE, encoding="utf-8"
        )
        match = _STORY_RE.search(prompt)
        story_id = match.group(1) if match else "US-1"
        if story_id == "US-2":
            (ws / "tests" / "test_soustraction.py").write_text(
                _TEST_SUB.format(pkg=pkg.name), encoding="utf-8"
            )
        else:
            (ws / "tests" / "test_addition.py").write_text(
                _TEST_ADD.format(pkg=pkg.name), encoding="utf-8"
            )


def _patch_hermetic_pytest(monkeypatch) -> None:
    """Make the orchestrator's verify step run the produced suite **for real**,
    with the current interpreter (no ``uv`` venv), parsing outcomes via the same
    ``pytest_report`` the production path uses — so per-test states are grounded
    on a genuine run, exactly like real mode."""

    async def _arun_pytest(self, ws=None):
        ws = workspace_dir(self.state.id) if ws is None else ws
        fd, report = tempfile.mkstemp(suffix=".json", prefix="e2e-report-")
        os.close(fd)

        def _run():
            env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
            proc = subprocess.run(
                [
                    sys.executable, "-m", "pytest", "-q",
                    "-p", "no:cacheprovider",
                    "--json-report", f"--json-report-file={report}",
                ],
                cwd=str(ws),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
            )
            return proc.returncode == 0, proc.stdout, pytest_report.parse(report)

        try:
            return await asyncio.to_thread(_run)
        finally:
            try:
                os.remove(report)
            except OSError:
                pass

    monkeypatch.setattr(Pipeline, "_arun_pytest", _arun_pytest)


async def test_pipeline_delivers_a_genuinely_working_feature(monkeypatch):
    """Spec → plan → build yields an app whose **real** tests pass and whose
    functions actually compute the right answers — no LLM, no UI, no ``uv``."""
    monkeypatch.setattr(settings, "fake_agents", True)  # hermetic everywhere else
    _patch_hermetic_pytest(monkeypatch)  # …except the verify step, which is real

    runner = FixtureRunner()
    state = ProjectState(id="e2e-calc-ok", name="calc", goal="une calculatrice")
    pipeline = Pipeline(state, runner)
    pipeline.start()

    await wait_until(lambda: pipeline.state.phase == PipelinePhase.DONE, timeout=60)

    # Orchestration completed with both stories accepted…
    assert {s.id for s in pipeline.state.stories} == {"US-1", "US-2"}
    assert all(s.status == StoryStatus.DONE for s in pipeline.state.stories)

    # …and DONE was *earned*: the factory wrote real code that a real pytest ran.
    ws = workspace_dir(state.id)
    pkg = _package_dir(ws)
    assert (pkg / "core.py").exists()
    assert runner.dev_calls >= 2  # the Dev agent actually built each story
    # green_tests is grounded on the genuine run (not the agent's self-report).
    assert any("test_addition" in n for n in pipeline.state.green_tests)
    assert any("test_soustraction" in n for n in pipeline.state.green_tests)

    # Strongest proof of a working *feature*: exercise the produced code directly.
    check = subprocess.run(
        [
            sys.executable, "-c",
            f"from {pkg.name}.core import add, subtract; "
            "assert add(2, 3) == 5; assert add(3, 2) == 5; "
            "assert subtract(5, 3) == 2; print('OK')",
        ],
        cwd=str(ws), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    assert check.returncode == 0, check.stdout
    assert "OK" in check.stdout


async def test_verify_gate_rejects_a_broken_feature(monkeypatch):
    """Feed a buggy ``add``: the orchestrator's real verify step must catch the
    red suite and mark the story FAILED — never DONE. Proves the green is earned,
    not rubber-stamped from the agent's self-reported status."""
    monkeypatch.setattr(settings, "fake_agents", True)
    _patch_hermetic_pytest(monkeypatch)

    runner = FixtureRunner(broken=True)
    state = ProjectState(id="e2e-calc-ko", name="calc", goal="une calculatrice")
    pipeline = Pipeline(state, runner)
    pipeline.start()

    # US-1's real tests are red, so after `dev_max_attempts` it terminates FAILED.
    # (Guard the lookup: the predicate is polled before the PO has planned US-1.)
    def _us1_failed() -> bool:
        try:
            return pipeline.state.story("US-1").status == StoryStatus.FAILED
        except KeyError:
            return False

    await wait_until(_us1_failed, timeout=60)
    us1 = pipeline.state.story("US-1")
    assert us1.status == StoryStatus.FAILED
    assert us1.status != StoryStatus.DONE
    # It retried before giving up (the gate didn't fail open on the first run).
    assert us1.attempts == settings.dev_max_attempts
    # The broken addition never entered the verified-green set.
    assert not any("test_addition" in n for n in pipeline.state.green_tests)
