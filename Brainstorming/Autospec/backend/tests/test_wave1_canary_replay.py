"""P0-A (GENERATION_FUSION_REVIEW): a post-merge canary that is RED while having
executed ZERO test is NOT evidence of a semantic conflict - the suite never ran.

Before this wave such a red (empty ``results`` + no known infra signature) went
straight to the ``semantic`` verdict and reverted a merge that was green. The
contract now is: repair the environment, replay ONCE, and only then believe the
semantic verdict. Gated by ``settings.canary_replay_on_empty`` (env
``CANARY_REPLAY_ON_EMPTY``), whose OFF value restores the historic behaviour.
"""

from autospec.agents.runner import FakeRunner
from autospec.config import settings
from autospec.models import Epic, ProjectState, StoryStatus, Stream, StreamKind, UserStory
from autospec.orchestrator.pipeline import Pipeline
from autospec.orchestrator.streams import WorkItem


def _item(wid: str = "US-1") -> WorkItem:
    return WorkItem(
        id=wid, kind="story", story_id=wid, stream="backend",
        title="S", status=StoryStatus.IN_PROGRESS, depends_on=(),
    )


def _pipeline(pid: str, monkeypatch) -> tuple[Pipeline, list[tuple[str, dict]]]:
    """A pipeline whose monitor events are captured (the timeline is the only
    place the canary verdict is recorded)."""
    # This file retains the explicitly fake legacy replay state machine. Real
    # execution must never purge/reinstall a shared host environment.
    monkeypatch.setattr(settings, "fake_agents", True)
    state = ProjectState(id=pid, name="canary", goal="g")
    state.epics.append(Epic(id="EPIC-1", title="E"))
    state.streams = [
        Stream(id="backend", kind=StreamKind.BACKEND, language="python", primary=True)
    ]
    state.stories = [UserStory(id="US-1", epic_id="EPIC-1", title="S", stream="backend")]
    pipeline = Pipeline(state, FakeRunner([]))
    events: list[tuple[str, dict]] = []
    original = pipeline.monitor.event

    def _event(kind, **fields):
        events.append((kind, fields))
        return original(kind, **fields)

    monkeypatch.setattr(pipeline.monitor, "event", _event)
    monkeypatch.setattr(settings, "post_merge_canary", True)
    return pipeline, events


def _verdicts(events: list[tuple[str, dict]]) -> list[str]:
    return [f.get("verdict", "") for k, f in events if k == "canary"]


# --------------------------------------------------------------- backend canary

async def test_empty_red_is_repaired_replayed_and_kept(tmp_path, monkeypatch):
    """Red with NO test executed and NO known signature: purge + ONE replay.
    Green on the replay = infra, the merge is KEPT and infra_retries counts it."""
    monkeypatch.setattr(settings, "canary_replay_on_empty", True)
    pipeline, events = _pipeline("canary-empty-healed", monkeypatch)
    calls: list[int] = []
    purged: list[object] = []

    async def _pytest(ws=None):
        calls.append(1)
        if len(calls) == 1:
            return False, "weird unknown failure", {}
        return True, "", {}

    monkeypatch.setattr(pipeline, "_arun_pytest", _pytest)
    monkeypatch.setattr(Pipeline, "_purge_venv_dir", staticmethod(lambda ws: purged.append(ws) or True))

    ok, kind, _tail = await pipeline._apost_merge_canary(_item(), False)

    assert (ok, kind) == (True, "infra")           # merge kept, no revert
    assert len(calls) == 2                          # exactly ONE replay
    assert purged                                   # the environment was rebuilt
    assert pipeline.state.calibration_for().infra_retries == 1
    assert _verdicts(events) == ["empty_replay", "infra_healed"]


async def test_empty_red_twice_is_semantic(tmp_path, monkeypatch):
    """Still red after the repair, with no infra signature: the project's own
    code IS broken (the ModuleNotFoundError case the docstring protects) -
    semantic verdict, the caller reverts."""
    monkeypatch.setattr(settings, "canary_replay_on_empty", True)
    pipeline, events = _pipeline("canary-empty-semantic", monkeypatch)
    calls: list[int] = []

    async def _pytest(ws=None):
        calls.append(1)
        return False, "ModuleNotFoundError: No module named 'app.services'", {}

    monkeypatch.setattr(pipeline, "_arun_pytest", _pytest)
    monkeypatch.setattr(Pipeline, "_purge_venv_dir", staticmethod(lambda ws: True))

    ok, kind, tail = await pipeline._apost_merge_canary(_item(), False)

    assert (ok, kind) == (False, "semantic")
    assert len(calls) == 2
    assert "ModuleNotFoundError" in tail
    assert _verdicts(events) == ["empty_replay", "semantic"]


async def test_red_with_executed_tests_is_semantic_without_any_replay(tmp_path, monkeypatch):
    """Tests actually ran and failed: that IS the semantic conflict the canary
    exists for. No repair, no replay - a single suite run."""
    monkeypatch.setattr(settings, "canary_replay_on_empty", True)
    pipeline, events = _pipeline("canary-real-red", monkeypatch)
    calls: list[int] = []

    async def _pytest(ws=None):
        calls.append(1)
        return False, "1 failed", {"test_a": "failed"}

    monkeypatch.setattr(pipeline, "_arun_pytest", _pytest)

    ok, kind, _tail = await pipeline._apost_merge_canary(_item(), False)

    assert (ok, kind) == (False, "semantic")
    assert len(calls) == 1
    assert _verdicts(events) == ["semantic"]


async def test_flag_off_keeps_the_legacy_semantic_verdict(tmp_path, monkeypatch):
    """CANARY_REPLAY_ON_EMPTY=0: byte-identical historic behaviour."""
    monkeypatch.setattr(settings, "canary_replay_on_empty", False)
    pipeline, events = _pipeline("canary-flag-off", monkeypatch)
    calls: list[int] = []

    async def _pytest(ws=None):
        calls.append(1)
        return False, "weird unknown failure", {}

    monkeypatch.setattr(pipeline, "_arun_pytest", _pytest)

    ok, kind, _tail = await pipeline._apost_merge_canary(_item(), False)

    assert (ok, kind) == (False, "semantic")
    assert len(calls) == 1
    assert _verdicts(events) == ["semantic"]


async def test_known_signature_path_is_unchanged(tmp_path, monkeypatch):
    """A red carrying a KNOWN infra signature keeps its own (older) path:
    infra_suspected then infra_healed, and still exactly ONE replay."""
    monkeypatch.setattr(settings, "canary_replay_on_empty", True)
    pipeline, events = _pipeline("canary-signature", monkeypatch)
    calls: list[int] = []

    async def _pytest(ws=None):
        calls.append(1)
        if len(calls) == 1:
            return False, "No module named pytest", {}
        return True, "", {}

    monkeypatch.setattr(pipeline, "_arun_pytest", _pytest)
    monkeypatch.setattr(Pipeline, "_purge_venv_dir", staticmethod(lambda ws: True))

    ok, kind, _tail = await pipeline._apost_merge_canary(_item(), False)

    assert (ok, kind) == (True, "infra")
    assert len(calls) == 2
    assert _verdicts(events) == ["infra_suspected", "infra_healed"]


async def test_replay_red_with_a_signature_keeps_the_merge(tmp_path, monkeypatch):
    """The repair uncovers a NAMED toolchain outage: reverting repairs nothing,
    so the merge is kept and the red is shouted as infra (not semantic)."""
    monkeypatch.setattr(settings, "canary_replay_on_empty", True)
    pipeline, events = _pipeline("canary-outage", monkeypatch)
    calls: list[int] = []

    async def _pytest(ws=None):
        calls.append(1)
        if len(calls) == 1:
            return False, "weird unknown failure", {}
        return False, "failed to spawn: `pytest`", {}

    monkeypatch.setattr(pipeline, "_arun_pytest", _pytest)
    monkeypatch.setattr(Pipeline, "_purge_venv_dir", staticmethod(lambda ws: True))

    ok, kind, _tail = await pipeline._apost_merge_canary(_item(), False)

    assert (ok, kind) == (False, "infra")
    assert len(calls) == 2
    assert _verdicts(events) == ["empty_replay", "infra_persistent"]


# -------------------------------------------------------------- frontend canary

async def test_frontend_empty_red_is_replayed_once(tmp_path, monkeypatch):
    """Same contract for the Vitest canary: the frontend runner carries its own
    ``npm ci`` heal, so the replay alone is the repair."""
    monkeypatch.setattr(settings, "canary_replay_on_empty", True)
    pipeline, events = _pipeline("canary-front-healed", monkeypatch)
    calls: list[int] = []

    async def _front(ws=None):
        calls.append(1)
        if len(calls) == 1:
            return False, "unknown vitest crash", {}
        return True, "", {}

    monkeypatch.setattr(pipeline, "_arun_frontend_tests", _front)

    ok, kind, _tail = await pipeline._apost_merge_canary(_item(), True)

    assert (ok, kind) == (True, "infra")
    assert len(calls) == 2
    assert pipeline.state.calibration_for().infra_retries == 1
    assert _verdicts(events) == ["empty_replay", "infra_healed"]


async def test_frontend_empty_red_twice_is_semantic(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "canary_replay_on_empty", True)
    pipeline, events = _pipeline("canary-front-semantic", monkeypatch)
    calls: list[int] = []

    async def _front(ws=None):
        calls.append(1)
        return False, "unknown vitest crash", {}

    monkeypatch.setattr(pipeline, "_arun_frontend_tests", _front)

    ok, kind, _tail = await pipeline._apost_merge_canary(_item(), True)

    assert (ok, kind) == (False, "semantic")
    assert len(calls) == 2
    assert _verdicts(events) == ["empty_replay", "semantic"]


async def test_real_empty_failure_never_runs_legacy_host_repair(tmp_path, monkeypatch):
    pipeline, events = _pipeline("canary-real-empty-boundary", monkeypatch)
    monkeypatch.setattr(settings, "fake_agents", False)
    calls = []
    async def run(ws=None):
        calls.append(1)
        return False, "ISOLATION_UNAVAILABLE: Docker pipe unreachable", {}
    monkeypatch.setattr(pipeline, "_arun_pytest", run)
    monkeypatch.setattr(Pipeline, "_purge_venv_dir", staticmethod(lambda ws: (_ for _ in ()).throw(
        AssertionError("legacy host purge forbidden in real execution"))))
    ok, kind, tail = await pipeline._apost_merge_canary(_item(), False)
    assert (ok, kind) == (False, "infra") and len(calls) == 1
    assert "ISOLATION_UNAVAILABLE" in tail and _verdicts(events) == ["infra_persistent"]


async def test_real_product_collection_error_is_not_a_toolchain_outage(tmp_path, monkeypatch):
    pipeline, events = _pipeline("canary-real-collection-boundary", monkeypatch)
    monkeypatch.setattr(settings, "fake_agents", False)
    calls = []
    async def run(ws=None):
        calls.append(1)
        return False, "SyntaxError: invalid product syntax during collection", {}
    monkeypatch.setattr(pipeline, "_arun_pytest", run)
    assert (await pipeline._apost_merge_canary(_item(), False))[:2] == (False, "semantic")
    assert len(calls) == 1 and _verdicts(events) == ["semantic"]
