"""Wave 1 tests: the pure recovery state machine + the escalation-ladder wiring."""

from __future__ import annotations

from autospec.agents.runner import FakeRunner
from autospec.models import ProjectState
from autospec.orchestrator import recovery
from autospec.orchestrator.pipeline import Pipeline
from autospec.orchestrator.recovery import (
    AttemptRecord,
    TaskFailureHistory,
)


def _hist(n_dev, **kw):
    attempts = [AttemptRecord(model=f"m{i}", kind=recovery.KIND_DEV) for i in range(n_dev)]
    attempts.extend(AttemptRecord(kind=k) for k in kw.pop("extra_kinds", []))
    return TaskFailureHistory(attempts=attempts, **kw)


# --------------------------------------------------------------------------- #
# ladder_model                                                                 #
# --------------------------------------------------------------------------- #

def test_ladder_model_climbs_and_clamps():
    ladder = ["cheap", "mid", "boss"]
    assert recovery.ladder_model(1, ladder) == "cheap"
    assert recovery.ladder_model(2, ladder) == "mid"
    assert recovery.ladder_model(3, ladder) == "boss"
    assert recovery.ladder_model(9, ladder) == "boss"   # clamp to top rung
    assert recovery.ladder_model(1, []) is None
    assert recovery.ladder_model(0, ladder) is None


# --------------------------------------------------------------------------- #
# byte-identical legacy behaviour (flags off)                                  #
# --------------------------------------------------------------------------- #

def test_legacy_retry_then_fail():
    # 1 failed dev attempt, max 2, no split, no escalate → plain RETRY (same model)
    d = recovery.next_action(_hist(1, max_attempts=2))
    assert d.action == recovery.RETRY and d.model is None

    # attempts exhausted, no split available → FAIL
    d = recovery.next_action(_hist(2, max_attempts=2))
    assert d.action == recovery.FAIL


def test_legacy_retry_then_split_when_available():
    d = recovery.next_action(_hist(2, max_attempts=2, split_available=True))
    assert d.action == recovery.SPLIT


# --------------------------------------------------------------------------- #
# escalation                                                                   #
# --------------------------------------------------------------------------- #

def test_escalate_climbs_model_on_retry():
    h = _hist(1, max_attempts=3, ladder=["cheap", "mid", "boss"], escalate_enabled=True)
    # last dev attempt used "m0"; next rung (attempt 2) is "mid" → ESCALATE
    d = recovery.next_action(h)
    assert d.action == recovery.ESCALATE
    assert d.model == "mid"


def test_escalate_same_model_is_plain_retry():
    # Ladder rung equals the previous attempt's model → RETRY, not ESCALATE.
    attempts = [AttemptRecord(model="mid", kind=recovery.KIND_DEV)]
    h = TaskFailureHistory(
        attempts=attempts, max_attempts=3, ladder=["mid", "mid", "boss"],
        escalate_enabled=True,
    )
    d = recovery.next_action(h)
    assert d.action == recovery.RETRY
    assert d.model == "mid"


def test_infra_and_flake_do_not_count_as_attempts():
    # 1 dev fail + 2 infra + 1 flake, max 2 → still one dev attempt left → RETRY
    h = TaskFailureHistory(
        attempts=[
            AttemptRecord(kind=recovery.KIND_DEV),
            AttemptRecord(kind=recovery.KIND_INFRA),
            AttemptRecord(kind=recovery.KIND_INFRA),
            AttemptRecord(kind=recovery.KIND_FLAKE),
        ],
        max_attempts=2,
    )
    assert h.dev_attempts == 1
    assert recovery.next_action(h).action == recovery.RETRY


# --------------------------------------------------------------------------- #
# classification takes over at exhaustion when enabled                         #
# --------------------------------------------------------------------------- #

def test_classify_preempts_split_when_enabled():
    h = _hist(2, max_attempts=2, split_available=True, classify_enabled=True)
    assert recovery.next_action(h).action == recovery.CLASSIFY


def test_recurring_signatures():
    h = TaskFailureHistory(
        attempts=[
            AttemptRecord(kind=recovery.KIND_DEV, signatures=["a::x|E", "b::y|F"]),
            AttemptRecord(kind=recovery.KIND_DEV, signatures=["a::x|E"]),
        ],
        max_attempts=3,
    )
    assert h.recurring_signatures == ["a::x|E"]


# --------------------------------------------------------------------------- #
# escalation wiring at the chokepoint (_FORCE_MODEL precedence)                #
# --------------------------------------------------------------------------- #

async def test_force_model_honored_by_tracker():
    import autospec.orchestrator.pipeline as pipe_mod

    pipeline = Pipeline(ProjectState(id="p-esc1", name="g", goal="g"), FakeRunner(["ok"]))
    token = pipe_mod._FORCE_MODEL.set("boss-model")
    try:
        await pipeline._tracked.arun("prompt", "sys")
    finally:
        pipe_mod._FORCE_MODEL.reset(token)
    assert pipeline.runner.calls[-1]["model"] == "boss-model"


async def test_explicit_model_beats_force():
    import autospec.orchestrator.pipeline as pipe_mod

    pipeline = Pipeline(ProjectState(id="p-esc2", name="g", goal="g"), FakeRunner(["ok"]))
    token = pipe_mod._FORCE_MODEL.set("boss-model")
    try:
        await pipeline._tracked.arun("prompt", "sys", model="explicit")
    finally:
        pipe_mod._FORCE_MODEL.reset(token)
    assert pipeline.runner.calls[-1]["model"] == "explicit"


async def test_no_force_falls_back_to_router():
    pipeline = Pipeline(ProjectState(id="p-esc3", name="g", goal="g"), FakeRunner(["ok"]))
    await pipeline._tracked.arun("prompt", "sys")
    # No force set, no per-phase override → phase router resolves (may be None or
    # the default claude model); the point is it is NOT a ladder/force value.
    assert pipeline.runner.calls[-1]["model"] != "boss-model"
