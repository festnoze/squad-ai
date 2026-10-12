"""P3 (GENERATION_FUSION_REVIEW) + D11 / FACTORY_IMPROVEMENTS.

P3 - observability of the fusion loop. The review's headline number ("120 test
suites for 17 items") could only be reconstructed by hand from the logs. Three
counters now live in ``PlanCalibration`` (per iteration, via
``state.calibration_for()``):

* ``suite_runs`` - every REAL suite execution, counted inside the two runners
  (``_arun_pytest`` / ``_arun_frontend_tests``), never by their callers, so the
  dev verification, the canary, the resume re-verify and the mutation rerun all
  land in the same number. Demo mode (``fake_agents``) executes nothing and is
  not counted.
* ``canary_verdicts`` - a durable histogram of the post-merge canary verdicts
  (the timeline events are volatile).
* ``items_delivered`` - items that reached DONE with their merge on the shared
  HEAD, i.e. the denominator of the ``suites_per_item`` ratio.

D11 - the stored status of a task-decomposed story was never consolidated: the
board showed TODO for a fully built story, and the ``story <id> done`` commit
could be emitted while the rollup was still incomplete. Gated by
``CONSOLIDATE_STORY_STATUS`` (``settings.consolidate_story_status``), whose OFF
value restores the historic behaviour.
"""

import asyncio
import subprocess
from pathlib import Path

import pytest

from autospec.agents.scripted import ScriptedRunner
from autospec.config import settings
from autospec.models import (
    Epic,
    PlanCalibration,
    ProjectState,
    StoryStatus,
    Stream,
    StreamKind,
    Task,
    UserStory,
)
from autospec.orchestrator import pipeline as pipeline_mod
from autospec.orchestrator.pipeline import Pipeline

_GHERKIN = "Feature: F\n  Scenario: S\n    Given a\n    When b\n    Then c"
_IDS = ("T-A", "T-B")


def _state(pid: str) -> ProjectState:
    """One backend story decomposed into two INDEPENDENT tasks."""
    st = ProjectState(id=pid, name="obsapp", goal="g")
    st.epics.append(Epic(id="EPIC-1", title="E"))
    st.streams = [
        Stream(id="backend", kind=StreamKind.BACKEND, language="python", primary=True)
    ]
    st.stories = [
        UserStory(
            id="US-1", epic_id="EPIC-1", title="US-1", stream="backend",
            gherkin=_GHERKIN,
            tasks=[
                Task(id=tid, story_id="US-1", stream="backend", title=tid,
                     gherkin=_GHERKIN)
                for tid in _IDS
            ],
        )
    ]
    return st


@pytest.fixture
def build_env(monkeypatch, tmp_path):
    """Stream build path, scripted agents, ONE dev slot (so the two tasks build
    and merge strictly one after the other), post-merge canary ON."""
    monkeypatch.setattr("autospec.config.settings.workspace_root", tmp_path)
    monkeypatch.setattr(settings, "streams_enabled", True)
    monkeypatch.setattr(settings, "fake_agents", True)
    monkeypatch.setattr(settings, "post_merge_canary", True)
    monkeypatch.setattr(settings, "max_parallel_devs", 1)


class _Harness:
    """A pipeline whose dev, merge and suite are faked, with everything the
    build records kept in order."""

    def __init__(self, pipeline: Pipeline, monkeypatch) -> None:
        self.pipeline = pipeline
        self.suites: list[object] = []       # one entry per faked suite run (its ws)
        self.merged: list[str] = []
        self.commits: list[tuple[str, tuple[StoryStatus, ...]]] = []
        self.dev_snapshots: list[tuple[str, StoryStatus, int]] = []
        story = pipeline.state.story("US-1")

        async def _dev(subject, worktree, pkg, is_frontend):
            # Snapshot the CONTAINER's stored status at the moment each task
            # starts: when T-B starts, T-A is already DONE and merged.
            self.dev_snapshots.append((
                subject.id, story.status, len(self.rollup_commits()),
            ))
            (Path(worktree) / f"{subject.id.lower()}.py").write_text(
                "x = 1\n", encoding="utf-8"
            )
            return True, ""

        async def _merge(repo, branch, wid, worktree=None):
            self.merged.append(wid)
            return True, []

        async def _apytest(ws=None):
            # Stand-in for the real runner: it goes through the SAME counting
            # seam `_arun_pytest` calls right after its demo short-circuit, so
            # this build measures the WIRING (every suite lands on the CURRENT
            # iteration's calibration). The counting SITE itself is pinned by
            # test_the_real_runner_counts_one_execution_and_demo_mode_counts_none.
            pipeline._count_suite_run()
            self.suites.append(ws)
            return True, "", {}

        real_commit = pipeline._acommit_story

        async def _commit(ws, sid):
            self.commits.append((sid, tuple(t.status for t in story.tasks)))
            return await real_commit(ws, sid)

        monkeypatch.setattr(pipeline, "_arun_item_dev", _dev)
        monkeypatch.setattr(pipeline, "_amerge_work_item", _merge)
        monkeypatch.setattr(pipeline, "_arun_pytest", _apytest)
        monkeypatch.setattr(pipeline, "_acommit_story", _commit)

    def rollup_commits(self) -> list[tuple[str, tuple[StoryStatus, ...]]]:
        """Only the ``story US-1 done`` commits (the scaffold and per-item
        commits share the same helper)."""
        return [c for c in self.commits if c[0] == "US-1"]


def _pipeline(pid: str) -> Pipeline:
    return Pipeline(_state(pid), ScriptedRunner())


# ------------------------------------------- (a) the three P3 counters


async def test_a_build_counts_its_suites_its_deliveries_and_its_verdicts(
    build_env, monkeypatch
):
    """A two-task stream build fills the three P3 counters of the CURRENT
    iteration: every suite run, every delivered (green AND merged) item, and
    every canary verdict."""
    pipeline = _pipeline("p3-counters")
    h = _Harness(pipeline, monkeypatch)

    await asyncio.wait_for(pipeline._abuild_phase(), timeout=180)

    state = pipeline.state
    assert sorted(h.merged) == list(_IDS)
    assert all(state.task(t).status == StoryStatus.DONE for t in _IDS)

    cal = state.calibration_for()
    # Deliveries: an item counts once, when it is green AND merged.
    assert cal.items_delivered == 2
    # Suites: every run went through the counting seam, none was lost, and the
    # counter belongs to the iteration the build ran in (not a fresh bucket).
    assert cal.suite_runs == len(h.suites)
    # The faked dev owns the per-worktree verification, so the suites left are
    # the post-merge canaries: ONE per merge, the very ratio P1-A attacks.
    assert cal.suite_runs == 2
    assert all(ws is None for ws in h.suites)   # all on the SHARED HEAD
    assert state.calibration[state.iteration] is cal
    # Verdicts: no contention (one dev slot), so each merge got its own green
    # canary - the historic one-suite-per-merge shape P1-A attacks.
    assert cal.canary_verdicts == {"green": 2}
    # The ratio the review is about.
    assert cal.suites_per_item == round(cal.suite_runs / 2, 2)


async def test_the_real_runner_counts_one_execution_and_demo_mode_counts_none(
    tmp_path, monkeypatch
):
    """The counting site is INSIDE ``_arun_pytest`` (not in its callers), and it
    sits AFTER the demo short-circuit: a fake-agents run executes nothing, so it
    must not inflate the ratio."""
    monkeypatch.setattr("autospec.config.settings.workspace_root", tmp_path)
    monkeypatch.setattr(settings, "sandbox_enabled", False)
    monkeypatch.setattr(settings, "flaky_rerun_enabled", False)
    monkeypatch.setattr(settings, "fake_agents", False)
    pipeline = _pipeline("p3-runner")
    worktree = tmp_path / "wt"
    worktree.mkdir()

    class _Proc:
        returncode = 0
        stdout = "1 passed"

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Proc())
    from autospec.orchestrator import pipeline_validation
    monkeypatch.setattr(pipeline_validation, "run_native", lambda *a, **k: (True, "1 passed", {"native": "passed"}))

    ok, _out, _res = await pipeline._arun_pytest(ws=worktree)

    assert ok is True
    assert pipeline.state.calibration_for().suite_runs == 1

    # Demo mode: short-circuited BEFORE the counter.
    monkeypatch.setattr(settings, "fake_agents", True)
    await pipeline._arun_pytest(ws=worktree)
    assert pipeline.state.calibration_for().suite_runs == 1


def test_suites_per_item_is_safe_before_anything_is_delivered():
    """The ratio floors its denominator at 1, so it is readable from the first
    suite run (and stays exact once items land)."""
    cal = PlanCalibration()
    assert cal.suites_per_item == 0.0
    cal.suite_runs = 7
    assert cal.suites_per_item == 7.0       # nothing delivered yet
    cal.items_delivered = 3
    assert cal.suites_per_item == 2.33
    assert cal.model_dump()["suites_per_item"] == 2.33


# --------------------------------- (b) the story rollup is emitted ONCE, last


async def test_b_the_story_is_consolidated_only_when_its_last_task_lands(
    build_env, monkeypatch
):
    """D11: after the FIRST task the container is still not done (no stored
    DONE, no ``story US-1 done`` commit); the SECOND one consolidates it, once."""
    pipeline = _pipeline("d11-rollup")
    h = _Harness(pipeline, monkeypatch)
    story = pipeline.state.story("US-1")

    await asyncio.wait_for(pipeline._abuild_phase(), timeout=180)

    # The two tasks were built one after the other (a single dev slot), so the
    # SECOND one started with its sibling already DONE and merged. At that exact
    # moment the container was still not consolidated: no stored DONE, and no
    # rollup commit had been emitted yet.
    assert len(h.dev_snapshots) == 2
    assert [s[0] for s in h.dev_snapshots] == h.merged
    _sid, status_when_second_started, rollups_so_far = h.dev_snapshots[1]
    assert status_when_second_started != StoryStatus.DONE
    assert rollups_so_far == 0

    # Once the last task merged: stored status consolidated, ONE rollup commit,
    # emitted with every task already DONE.
    assert story.status == StoryStatus.DONE
    assert story.effective_status() == StoryStatus.DONE
    rollups = h.rollup_commits()
    assert len(rollups) == 1
    assert rollups[0][1] == (StoryStatus.DONE, StoryStatus.DONE)


async def test_b_the_flag_off_leaves_the_stored_status_untouched(
    build_env, monkeypatch
):
    """Flag OFF = historic behaviour: the tasks are done, the DERIVED status says
    DONE, but nothing writes the container's stored status and no rollup commit
    is emitted."""
    monkeypatch.setattr(settings, "consolidate_story_status", False)
    pipeline = _pipeline("d11-off")
    h = _Harness(pipeline, monkeypatch)
    story = pipeline.state.story("US-1")

    await asyncio.wait_for(pipeline._abuild_phase(), timeout=180)

    assert all(pipeline.state.task(t).status == StoryStatus.DONE for t in _IDS)
    assert story.effective_status() == StoryStatus.DONE   # derived: done
    assert story.status != StoryStatus.DONE               # stored: untouched
    assert h.rollup_commits() == []


async def test_an_incomplete_container_never_claims_a_rollup_commit():
    """The OTHER emitters of ``story <id> done`` (the legacy sequential build and
    the wrong-test arbiter) share one guard: a container whose tasks are not all
    done is never committed as delivered."""
    pipeline = _pipeline("d11-guard")
    story = pipeline.state.story("US-1")

    assert pipeline._story_rollup_incomplete(story) is True
    for task in story.tasks:
        task.status = StoryStatus.DONE
    assert pipeline._story_rollup_incomplete(story) is False
    # A taskless story is never a container: the guard must not block it.
    assert pipeline._story_rollup_incomplete(
        UserStory(id="US-9", epic_id="EPIC-1", title="solo")
    ) is False


# ------------------------------------------- (c) a rebuild un-consolidates


async def test_c_rebuilding_a_task_sends_its_consolidated_story_back_to_todo(
    build_env, monkeypatch
):
    """D11: the stored status must never contradict ``effective_status()``. A
    task queued again by ``arebuild_task`` rolls its parent back to TODO."""
    pipeline = _pipeline("d11-rebuild")
    h = _Harness(pipeline, monkeypatch)
    story = pipeline.state.story("US-1")

    await asyncio.wait_for(pipeline._abuild_phase(), timeout=180)
    assert story.status == StoryStatus.DONE
    assert len(h.rollup_commits()) == 1

    async def _noop(task_id):
        return None

    monkeypatch.setattr(pipeline, "_arebuild_one_task", _noop)
    pipeline.state.phase = pipeline_mod.PipelinePhase.DONE

    await pipeline.arebuild_task("T-A")
    await asyncio.wait_for(pipeline._task, timeout=30)

    assert pipeline.state.task("T-A").status == StoryStatus.TODO
    assert story.effective_status() == StoryStatus.TODO
    assert story.status == StoryStatus.TODO   # the consolidated DONE is gone
