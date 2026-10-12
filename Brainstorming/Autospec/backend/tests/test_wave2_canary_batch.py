"""P1-A (GENERATION_FUSION_REVIEW): the post-merge canary runs by BURST.

Replaying the FULL suite after every single merge was the cost item n.1 of the
fusion loop (120 suites for 17 items). Merges are serialized by the merge lock,
so under contention they land back to back: a worker whose merge landed while
others were still queued no longer replays the suite for itself. It parks in the
burst being formed (stage MERGING - no dev slot, dependents still blocked) and
the LAST merger runs ONE canary per language for the whole burst.

A red burst is bisected: revert the newest merge, replay, repeat, until HEAD is
green again or the burst is exhausted. Only the merges actually reverted are
requeued; the others stay merged and DONE.

Gated by ``CANARY_BATCH`` (``settings.canary_batch_enabled``), whose OFF value
restores one canary per merge. With no contention the burst has size 1, which is
exactly the historic behaviour.
"""

import asyncio
from pathlib import Path

import pytest

from autospec.agents.scripted import ScriptedRunner
from autospec.config import settings
from autospec.models import (
    Epic,
    ProjectState,
    StoryStatus,
    Stream,
    StreamKind,
    Task,
    UserStory,
)
from autospec.orchestrator.pipeline import Pipeline, _OwnedLock

_GHERKIN = "Feature: F\n  Scenario: S\n    Given a\n    When b\n    Then c"
_IDS = ("T-A", "T-B", "T-C")


def _state(pid: str) -> ProjectState:
    """Three INDEPENDENT backend tasks: with ``max_parallel_devs`` at 3 they all
    build at once, so their merges really queue on the merge lock."""
    st = ProjectState(id=pid, name="burstapp", goal="g")
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
                     gherkin=_GHERKIN, files_hint=[f"{tid.lower()}.py"])
                for tid in _IDS
            ],
        )
    ]
    return st


@pytest.fixture
def burst_env(monkeypatch, tmp_path):
    """Stream build path, scripted agents, three dev slots, canary ON."""
    monkeypatch.setattr("autospec.config.settings.workspace_root", tmp_path)
    monkeypatch.setattr(settings, "streams_enabled", True)
    monkeypatch.setattr(settings, "fake_agents", True)
    monkeypatch.setattr(settings, "post_merge_canary", True)
    monkeypatch.setattr(settings, "max_parallel_devs", 3)


class _Harness:
    """A pipeline whose merge is faked but REALLY serialized by the merge lock.

    The three merges are held at a gate until all three workers have entered the
    merge phase, so the burst is deterministic: the first two mergers find the
    queue non-empty (they park) and the third finds it empty (it settles)."""

    def __init__(self, pipeline: Pipeline, monkeypatch, *, expected: int = 3) -> None:
        self.pipeline = pipeline
        self.merged: list[str] = []          # merge order (the burst order)
        self.present: list[str] = []         # ids whose merge is still on HEAD
        self.canary_runs: list[str] = []     # one entry per SHARED suite run
        self.reverts: list[tuple[str, str]] = []
        self.events: list[tuple[str, dict]] = []
        self._gate = asyncio.Event()
        self._expected = expected
        self._arrived = 0

        async def _dev(subject, worktree, pkg, is_frontend):
            (Path(worktree) / f"{subject.id.lower()}.py").write_text(
                "x = 1\n", encoding="utf-8"
            )
            return True, ""

        async def _merge(repo, branch, wid, worktree=None):
            self._arrived += 1
            if self._arrived >= self._expected:
                self._gate.set()
            try:
                await asyncio.wait_for(self._gate.wait(), timeout=30)
            except (asyncio.TimeoutError, TimeoutError):  # pragma: no cover - safety net
                pass
            async with pipeline._merge_lock.ahold(wid):
                await asyncio.sleep(0)  # a real suspension point under the lock
                self.merged.append(wid)
                self.present.append(wid)
                pipeline._merge_shas[wid] = f"sha-{wid}"
            return True, []

        emit = pipeline.monitor.event

        def _event(kind, **fields):
            self.events.append((kind, fields))
            return emit(kind, **fields)

        monkeypatch.setattr(pipeline, "_arun_item_dev", _dev)
        monkeypatch.setattr(pipeline, "_amerge_work_item", _merge)
        monkeypatch.setattr(pipeline, "_arun_pytest", self._apytest)
        monkeypatch.setattr(pipeline.monitor, "event", _event)

    def verdicts(self) -> list[str]:
        """Every ``canary`` verdict recorded on the timeline, in order."""
        return [f.get("verdict", "") for kind, f in self.events if kind == "canary"]

    def reopen(self, expected: int) -> None:
        """Re-arm the gate for the NEXT burst (used after a requeue)."""
        self._expected = expected
        self._arrived = 0
        self._gate = asyncio.Event()

    async def _apytest(self, ws=None):
        if ws is not None:
            return True, "", {}  # per-worktree suites (dev verify / resume)
        self.canary_runs.append("shared")
        return await self.acanary()

    async def acanary(self):
        """Overridable verdict of ONE shared-HEAD suite run. Green by default."""
        return True, "", {}


def _pipeline(pid: str) -> Pipeline:
    return Pipeline(_state(pid), ScriptedRunner())


# ------------------------------------------------ (a) one canary for the burst


async def test_a_contended_burst_is_verified_by_a_single_canary(burst_env, monkeypatch):
    pipeline = _pipeline("burst-green")
    h = _Harness(pipeline, monkeypatch)

    await asyncio.wait_for(pipeline._abuild_phase(), timeout=180)

    state = pipeline.state
    assert sorted(h.merged) == list(_IDS)          # the three merges landed
    assert len(h.canary_runs) == 1                 # ONE suite for three merges
    assert all(state.task(t).status == StoryStatus.DONE for t in _IDS)
    cal = state.calibration_for()
    assert cal.canary_batches == 1                 # a burst of size >= 2
    assert cal.canary_bisect_reverts == 0
    verdicts = h.verdicts()
    assert verdicts.count("batched") == 2          # two workers parked
    assert "batch_green" in verdicts


# ------------------------------------------------------- (b) the flag is honoured


async def test_b_the_flag_off_replays_one_canary_per_merge(burst_env, monkeypatch):
    monkeypatch.setattr(settings, "canary_batch_enabled", False)
    pipeline = _pipeline("burst-off")
    h = _Harness(pipeline, monkeypatch)

    await asyncio.wait_for(pipeline._abuild_phase(), timeout=180)

    state = pipeline.state
    assert len(h.canary_runs) == 3                 # historic: one suite per merge
    assert all(state.task(t).status == StoryStatus.DONE for t in _IDS)
    cal = state.calibration_for()
    assert cal.canary_batches == 0
    assert cal.canary_bisect_reverts == 0


# ----------------------------------------------------------- (c) the red bisect


async def test_c_a_red_burst_reverts_only_the_culprit(burst_env, monkeypatch):
    """The combined HEAD is red while the LAST merge of the burst is present.

    The bisect reverts it, replays, finds HEAD green again and stops: one revert
    only, the two older merges stay DONE, and the culprit is requeued (its green
    branch is preserved, so it merges again on the next pass)."""
    pipeline = _pipeline("burst-red")
    h = _Harness(pipeline, monkeypatch)
    culprit: dict[str, str] = {}
    armed = {"on": True}

    async def _canary():
        # The culprit is the last merge of the FIRST burst (the settler's own).
        if armed["on"] and culprit.get("id") and culprit["id"] in h.present:
            return False, "échec combiné", {"test_combo": "failed"}
        return True, "", {}

    async def _revert(repo, wid, sha="HEAD"):
        h.reverts.append((wid, sha))
        if wid in h.present:
            h.present.remove(wid)
        if wid == culprit.get("id"):
            armed["on"] = False  # the rebuilt item no longer breaks the combination
        return True

    original_merge = pipeline._amerge_work_item

    async def _merge(repo, branch, wid, worktree=None):
        result = await original_merge(repo, branch, wid, worktree)
        if len(h.merged) == 3 and "id" not in culprit:
            culprit["id"] = wid
            h.reopen(1)  # the requeued item will merge alone
        return result

    h.acanary = _canary
    monkeypatch.setattr(pipeline, "_amerge_work_item", _merge)
    monkeypatch.setattr(pipeline, "_arevert_head_merge", _revert)

    await asyncio.wait_for(pipeline._abuild_phase(), timeout=180)

    state = pipeline.state
    cal = state.calibration_for()
    assert cal.canary_bisect_reverts == 1          # ONE merge undone, not three
    # Burst canary (red) + ONE confirmation replay after the revert + the
    # requeued item's own canary: still far below one suite per merge.
    assert len(h.canary_runs) == 3
    assert cal.canary_reverts == 1                 # the culprit's semantic revert
    assert len(h.reverts) == 1
    assert h.reverts[0][0] == culprit["id"]
    assert h.reverts[0][1] == f"sha-{culprit['id']}"   # the burst reverts a SHA
    assert all(state.task(t).status == StoryStatus.DONE for t in _IDS)
    assert state.task(culprit["id"]).requeue_attempts == 1
    assert "bisect_revert" in h.verdicts()


# -------------------------------------------------------- (d) abandoned burst


async def test_d_an_abandoned_burst_never_strands_a_worker(burst_env, monkeypatch):
    """The settler blows up while running the burst's canary: every parked
    worker must wake up (None verdict) and fall back to its own canary."""
    pipeline = _pipeline("burst-abandon")
    h = _Harness(pipeline, monkeypatch)

    async def _canary():
        if len(h.canary_runs) == 1:
            raise RuntimeError("canari cassé")
        return True, "", {}

    h.acanary = _canary

    await asyncio.wait_for(pipeline._abuild_phase(), timeout=180)

    state = pipeline.state
    assert all(state.task(t).status == StoryStatus.DONE for t in _IDS)
    # The burst was abandoned, so each worker verified HEAD for itself.
    assert len(h.canary_runs) >= 2


# ------------------------------------------------------ the waiter counter


async def test_the_lock_counts_only_the_blocked_tasks():
    lock = _OwnedLock()
    assert lock.waiters == 0
    async with lock.ahold("first"):
        assert lock.waiters == 0  # the holder is not a waiter

        async def _queue(name):
            async with lock.ahold(name):
                await asyncio.sleep(0)

        tasks = [asyncio.create_task(_queue(f"w{i}")) for i in range(3)]
        for _ in range(4):
            await asyncio.sleep(0)
        assert lock.waiters == 3
    await asyncio.wait_for(asyncio.gather(*tasks), timeout=10)
    assert lock.waiters == 0


async def test_a_released_lock_still_shows_its_queue_in_the_same_step():
    """The whole batching decision rests on this: the task that RELEASES the
    lock must still see the tasks it woke up, because they have not resumed."""
    lock = _OwnedLock()
    seen: list[int] = []

    async def _queue():
        async with lock.ahold("w"):
            await asyncio.sleep(0)

    async with lock.ahold("holder"):
        task = asyncio.create_task(_queue())
        for _ in range(3):
            await asyncio.sleep(0)
    seen.append(lock.waiters)  # read WITHOUT awaiting in between

    assert seen == [1]
    await asyncio.wait_for(task, timeout=10)
    assert lock.waiters == 0
