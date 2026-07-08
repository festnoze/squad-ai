"""Tests for autospec.orchestrator.schema — decision-output validation guardrail."""

from __future__ import annotations

import pytest

from autospec.agents.runner import AgentError, AgentResult, FakeRunner
from autospec.orchestrator import schema as S


# --------------------------------------------------------------------------- #
# validate
# --------------------------------------------------------------------------- #

def test_validate_happy_path():
    sc = {"score": int, "verdict": str, "ok": bool}
    ok, errors = S.validate({"score": 80, "verdict": "pass", "ok": True}, sc)
    assert ok is True
    assert errors == []


def test_validate_missing_required_key():
    sc = {"score": int, "verdict": {"type": str, "required": True}}
    ok, errors = S.validate({"score": 80}, sc)
    assert ok is False
    assert any("verdict" in e and "missing" in e for e in errors)


def test_validate_optional_key_absent_is_ok():
    sc = {"score": int, "notes": {"type": str, "required": False}}
    ok, errors = S.validate({"score": 80}, sc)
    assert ok is True
    assert errors == []


def test_validate_wrong_type():
    sc = {"score": int}
    ok, errors = S.validate({"score": "eighty"}, sc)
    assert ok is False
    assert any("score" in e and "type" in e for e in errors)


def test_validate_bool_is_not_int():
    sc = {"score": int}
    ok, errors = S.validate({"score": True}, sc)
    assert ok is False
    assert any("score" in e for e in errors)


def test_validate_int_is_valid_float():
    sc = {"ratio": float}
    ok, errors = S.validate({"ratio": 3}, sc)
    assert ok is True
    assert errors == []


def test_validate_bool_is_not_float():
    sc = {"ratio": float}
    ok, errors = S.validate({"ratio": True}, sc)
    assert ok is False


def test_validate_choices_violation():
    sc = {"verdict": {"type": str, "choices": ["pass", "fail"]}}
    ok, errors = S.validate({"verdict": "maybe"}, sc)
    assert ok is False
    assert any("choices" in e for e in errors)

    ok2, _ = S.validate({"verdict": "pass"}, sc)
    assert ok2 is True


def test_validate_min_max():
    sc = {"score": {"type": int, "min": 0, "max": 100}}
    ok_lo, err_lo = S.validate({"score": -5}, sc)
    assert ok_lo is False and any("min" in e for e in err_lo)

    ok_hi, err_hi = S.validate({"score": 150}, sc)
    assert ok_hi is False and any("max" in e for e in err_hi)

    ok_mid, _ = S.validate({"score": 50}, sc)
    assert ok_mid is True


def test_validate_unknown_keys_ignored():
    sc = {"score": int}
    ok, errors = S.validate({"score": 10, "extra": "whatever"}, sc)
    assert ok is True
    assert errors == []


def test_validate_never_raises_on_non_dict():
    ok, errors = S.validate("not a dict", {"score": int})  # type: ignore[arg-type]
    assert ok is False
    assert errors


# --------------------------------------------------------------------------- #
# coerce
# --------------------------------------------------------------------------- #

def test_coerce_string_to_int():
    sc = {"score": int}
    out = S.coerce({"score": "80"}, sc)
    assert out["score"] == 80
    assert isinstance(out["score"], int)


def test_coerce_string_to_bool():
    sc = {"ok": bool, "bad": bool}
    out = S.coerce({"ok": "true", "bad": "false"}, sc)
    assert out["ok"] is True
    assert out["bad"] is False


def test_coerce_string_to_float():
    sc = {"ratio": float}
    out = S.coerce({"ratio": "0.75"}, sc)
    assert out["ratio"] == 0.75
    assert isinstance(out["ratio"], float)


def test_coerce_returns_new_dict_and_keeps_unknown():
    sc = {"score": int}
    src = {"score": "80", "note": "keep me"}
    out = S.coerce(src, sc)
    assert out is not src
    assert out["note"] == "keep me"
    assert src["score"] == "80"  # original untouched


def test_coerce_uncoercible_left_as_is():
    sc = {"score": int}
    out = S.coerce({"score": "not-a-number"}, sc)
    assert out["score"] == "not-a-number"
    ok, _ = S.validate(out, sc)
    assert ok is False


def test_coerce_then_validate_pipeline():
    sc = {"score": {"type": int, "min": 0, "max": 100}, "ok": bool}
    out = S.coerce({"score": "80", "ok": "true"}, sc)
    ok, errors = S.validate(out, sc)
    assert ok is True, errors


# --------------------------------------------------------------------------- #
# describe_schema
# --------------------------------------------------------------------------- #

def test_describe_schema_mentions_fields_and_constraints():
    sc = {
        "score": {"type": int, "min": 0, "max": 100},
        "verdict": {"type": str, "choices": ["pass", "fail"]},
        "notes": {"type": str, "required": False},
    }
    text = S.describe_schema(sc)
    assert "score" in text and "min 0" in text and "max 100" in text
    assert "verdict" in text and "pass" in text
    assert "notes" in text and "optional" in text


# --------------------------------------------------------------------------- #
# arun_json
# --------------------------------------------------------------------------- #

DECISION_SCHEMA = {
    "verdict": {"type": str, "choices": ["pass", "fail"]},
    "score": {"type": int, "min": 0, "max": 100},
}


async def test_arun_json_valid_first_try():
    runner = FakeRunner(['{"verdict": "pass", "score": 90}'])
    out = await S.arun_json(runner, "judge this", "you are a judge", DECISION_SCHEMA)
    assert out == {"verdict": "pass", "score": 90}
    assert len(runner.calls) == 1


async def test_arun_json_coerces_before_validating():
    # A string score "80" is coerced to int and passes without a retry.
    runner = FakeRunner(['{"verdict": "pass", "score": "80"}'])
    out = await S.arun_json(runner, "judge", "sys", DECISION_SCHEMA)
    assert out["score"] == 80
    assert len(runner.calls) == 1


async def test_arun_json_invalid_then_valid_retries_once():
    runner = FakeRunner([
        '{"verdict": "maybe", "score": 200}',   # invalid: choices + max
        '{"verdict": "pass", "score": 88}',     # valid
    ])
    out = await S.arun_json(runner, "judge this", "sys", DECISION_SCHEMA)
    assert out == {"verdict": "pass", "score": 88}
    assert len(runner.calls) == 2

    # The retry prompt must carry the validation errors and schema description.
    retry_prompt = runner.calls[1]["prompt"]
    assert "previous reply was invalid" in retry_prompt
    assert "verdict" in retry_prompt
    assert "choices" in retry_prompt or "maybe" in retry_prompt


async def test_arun_json_invalid_twice_raises_agenterror():
    runner = FakeRunner([
        '{"verdict": "maybe", "score": 1}',
        '{"verdict": "nope", "score": 2}',
    ])
    with pytest.raises(AgentError):
        await S.arun_json(runner, "judge", "sys", DECISION_SCHEMA, retries=1)
    assert len(runner.calls) == 2


async def test_arun_json_no_json_raises_after_retries():
    runner = FakeRunner(["totally not json", "still no json here"])
    with pytest.raises(AgentError):
        await S.arun_json(runner, "judge", "sys", DECISION_SCHEMA, retries=1)
    assert len(runner.calls) == 2


async def test_arun_json_emit_called_on_retry():
    runner = FakeRunner([
        '{"verdict": "maybe", "score": 1}',
        '{"verdict": "pass", "score": 50}',
    ])
    seen: list[str] = []
    out = await S.arun_json(
        runner, "judge", "sys", DECISION_SCHEMA, emit=seen.append
    )
    assert out["verdict"] == "pass"
    assert seen and any("retry" in m.lower() for m in seen)


async def test_arun_json_respects_retries_zero():
    runner = FakeRunner(['{"verdict": "maybe", "score": 1}'])
    with pytest.raises(AgentError):
        await S.arun_json(runner, "judge", "sys", DECISION_SCHEMA, retries=0)
    assert len(runner.calls) == 1


async def test_arun_json_forwards_cwd_and_model():
    runner = FakeRunner(['{"verdict": "pass", "score": 10}'])
    await S.arun_json(
        runner, "judge", "sys", DECISION_SCHEMA, cwd=None, model="test-model"
    )
    assert runner.calls[0]["model"] == "test-model"
