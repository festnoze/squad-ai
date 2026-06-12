import json

import pytest

from autospec.agents.runner import FakeRunner
from autospec.config import settings
from autospec.orchestrator import refine


@pytest.fixture
def refine_on(monkeypatch):
    monkeypatch.setattr(settings, "refine_enabled", True)
    monkeypatch.setattr(settings, "refine_po", True)
    monkeypatch.setattr(settings, "refine_max_rounds", 2)
    monkeypatch.setattr(settings, "refine_quality_threshold", 80)


def judge(score: int) -> str:
    return json.dumps({"score": score, "verdict": f"score {score}"})


def critic(suggestions=("améliore X",)) -> str:
    return json.dumps({"reflection": "analyse", "issues": ["i"], "suggestions": list(suggestions)})


def critic_empty() -> str:
    return json.dumps({"reflection": "rien à signaler", "issues": [], "suggestions": []})


async def run(runner, **kw):
    calls = {"revise": 0}

    async def _revise(prev, critique):
        calls["revise"] += 1
        return f"{prev}+rev{calls['revise']}"

    kw.setdefault("revise", _revise)
    outcome = await refine.arefine(
        runner, role="po", kind="artefact", criteria="critères",
        initial_text="v0", emit=None, **kw,
    )
    return outcome, calls


async def test_disabled_returns_initial_untouched(monkeypatch):
    monkeypatch.setattr(settings, "refine_enabled", False)
    outcome, calls = await run(FakeRunner([]))
    assert outcome.text == "v0"
    assert outcome.rounds == 0 and outcome.score == -1
    assert outcome.stopped_reason == "disabled"
    assert calls["revise"] == 0


async def test_stops_immediately_when_judge_passes(refine_on):
    outcome, calls = await run(FakeRunner([judge(90)]))
    assert outcome.stopped_reason == "threshold"
    assert outcome.rounds == 0 and outcome.score == 90
    assert calls["revise"] == 0  # no critic, no revise


async def test_hard_cap_on_rounds(refine_on):
    # Judge never satisfied: must stop exactly at max_rounds (2).
    runner = FakeRunner([judge(50), critic(), judge(55), critic(), judge(60)])
    outcome, calls = await run(runner)
    assert outcome.rounds == 2
    assert outcome.stopped_reason == "max_rounds"
    assert calls["revise"] == 2
    assert outcome.text == "v0+rev1+rev2"
    assert not runner.replies  # all replies consumed, no extra calls


async def test_stops_early_when_threshold_reached_mid_loop(refine_on):
    # 50 -> revise -> 85 (>=80): stop after one round.
    outcome, calls = await run(FakeRunner([judge(50), critic(), judge(85)]))
    assert outcome.rounds == 1 and outcome.score == 85
    assert outcome.stopped_reason == "threshold"


async def test_satisfied_critic_stops(refine_on):
    outcome, calls = await run(FakeRunner([judge(40), critic_empty()]))
    assert outcome.stopped_reason == "critic_empty"
    assert calls["revise"] == 0


async def test_rejected_revision_is_rolled_back(refine_on):
    state = {"rolled_back": False}

    async def _accept(_revised):
        return False

    async def _rollback():
        state["rolled_back"] = True

    outcome, calls = await run(
        FakeRunner([judge(50), critic()]), accept=_accept, rollback=_rollback
    )
    assert outcome.stopped_reason == "rejected"
    assert outcome.text == "v0"  # revision discarded
    assert state["rolled_back"] is True


async def test_unparseable_judge_treated_as_pass(refine_on):
    # Judge returns garbage -> treated as threshold -> stop (no infinite loop).
    outcome, _ = await run(FakeRunner(["pas un json"]))
    assert outcome.stopped_reason == "threshold"
    assert outcome.score == 80
