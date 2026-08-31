"""Tests for ``schemas/*.json`` (owner A01, CONTRACTS section 8).

Two files here are handed verbatim to a provider CLI through ``--json-schema``
and mirrored by Python constants. Three classes of drift are fatal and are
each pinned below:

1. a schema that is not valid Draft 2020-12 (the provider silently ignores it
   and the agent's output stops being constrained at all);
2. a ceiling that disagrees with the ``pxe.types`` constant (a tournament asks
   for 40 orders, the agent is told 40 and rejected at 21: R1 finding 25);
3. an identifier pattern that disagrees with the ``pxe.types`` regex for the
   same concept (R1 finding 25 again).
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from pxe.errors import InvalidConfigError
from pxe.types import (
    ACTION_VERSION,
    MAX_ORDER_QTY,
    MAX_ORDERS_PER_ACTION_CEILING,
    MAX_PREDICTIONS_PER_ACTION,
    MESSAGE_MAX_CHARS_CEILING,
    OBS_VERSION,
    PRICE_MAX,
    PRICE_MIN,
    RE_AGENT_ID,
    RE_MARKET_ID,
    REF_HISTORY_MAX,
    MatchConfig,
)

SCHEMA_NAMES = ("observation.v1.json", "action.v1.json")


# ---------------------------------------------------------------------------
# The files exist, parse, and are legal Draft 2020-12
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_schema_is_valid_draft_2020_12(schemas_dir: Any, name: str) -> None:
    schema = json.loads((schemas_dir / name).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["type"] == "object"


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_schema_forbids_additional_properties_at_the_root(schemas_dir: Any, name: str) -> None:
    """Section 8.2: strict structured output needs a closed object."""
    schema = json.loads((schemas_dir / name).read_text(encoding="utf-8"))
    assert schema["additionalProperties"] is False


# ---------------------------------------------------------------------------
# Version constants agree with the schemas
# ---------------------------------------------------------------------------
def test_action_version_matches_the_schema(action_schema: dict[str, Any]) -> None:
    assert action_schema["properties"]["action_version"]["const"] == ACTION_VERSION


def test_obs_version_matches_the_schema(observation_schema: dict[str, Any]) -> None:
    assert observation_schema["properties"]["obs_version"]["const"] == OBS_VERSION


# ---------------------------------------------------------------------------
# The schema is the hard ceiling; the config may only lower it (section 8.2)
# ---------------------------------------------------------------------------
def test_orders_max_items_equals_the_ceiling_constant(action_schema: dict[str, Any]) -> None:
    assert action_schema["properties"]["orders"]["maxItems"] == MAX_ORDERS_PER_ACTION_CEILING


def test_predictions_max_items_equals_the_constant(action_schema: dict[str, Any]) -> None:
    assert action_schema["properties"]["predictions"]["maxItems"] == MAX_PREDICTIONS_PER_ACTION


def test_qty_maximum_equals_the_constant(action_schema: dict[str, Any]) -> None:
    order_item = action_schema["properties"]["orders"]["items"]
    assert order_item["properties"]["qty"]["maximum"] == MAX_ORDER_QTY


def test_message_max_length_equals_the_ceiling_constant(
    action_schema: dict[str, Any],
    observation_schema: dict[str, Any],
) -> None:
    """Both files cap a public message at MESSAGE_MAX_CHARS_CEILING (FR-5.6.1)."""
    assert action_schema["properties"]["message_public"]["maxLength"] == MESSAGE_MAX_CHARS_CEILING
    message_item = observation_schema["properties"]["messages"]["items"]
    assert message_item["properties"]["text"]["maxLength"] == MESSAGE_MAX_CHARS_CEILING
    with pytest.raises(InvalidConfigError):
        MatchConfig(message_max_chars=MESSAGE_MAX_CHARS_CEILING + 1)


def test_ref_history_max_items_equals_the_constant(observation_schema: dict[str, Any]) -> None:
    """The sparkline ceiling lives in the schema; MatchConfig may only lower it."""
    block = observation_schema["$defs"]["marketBlock"]["properties"]
    assert block["ref_history"]["maxItems"] == REF_HISTORY_MAX
    with pytest.raises(InvalidConfigError):
        MatchConfig(ref_history_len=REF_HISTORY_MAX + 1)


def test_observation_limits_cannot_advertise_more_than_the_ceiling(
    observation_schema: dict[str, Any],
) -> None:
    """R1 finding 25: ``limits.max_orders_per_action`` is bounded by the schema ceiling."""
    limits = observation_schema["properties"]["limits"]["properties"]
    assert limits["max_orders_per_action"]["maximum"] == MAX_ORDERS_PER_ACTION_CEILING


# ---------------------------------------------------------------------------
# Identifier patterns agree with pxe.types (R1 finding 25)
# ---------------------------------------------------------------------------
def test_agent_id_pattern_is_the_ranked_agent_regex(observation_schema: dict[str, Any]) -> None:
    """``$defs.agentId`` is agents only. MM and FEES never appear in an observation."""
    pattern = observation_schema["$defs"]["agentId"]["pattern"]
    assert pattern == RE_AGENT_ID.pattern
    assert "MM" not in pattern and "FEES" not in pattern


def test_market_id_pattern_is_the_market_regex(observation_schema: dict[str, Any]) -> None:
    assert observation_schema["$defs"]["marketId"]["pattern"] == RE_MARKET_ID.pattern


def test_price_bounds_agree_with_the_constants(observation_schema: dict[str, Any]) -> None:
    price = observation_schema["$defs"]["price"]
    assert price["minimum"] == PRICE_MIN
    assert price["maximum"] == PRICE_MAX


def test_action_price_bounds_agree_with_the_constants(action_schema: dict[str, Any]) -> None:
    order_item = action_schema["properties"]["orders"]["items"]
    price = order_item["properties"]["price"]
    bounds = price if "minimum" in price else next(b for b in price.get("oneOf", []) if "minimum" in b)
    assert bounds["minimum"] == PRICE_MIN
    assert bounds["maximum"] == PRICE_MAX


# ---------------------------------------------------------------------------
# FR-5.2.3: a tick with zero open markets is legal (R1 finding 16, R2 15)
# ---------------------------------------------------------------------------
def test_markets_may_be_empty(observation_schema: dict[str, Any]) -> None:
    """Every market may resolve before T, so an observation may carry no market."""
    markets = observation_schema["properties"]["markets"]
    assert markets["minItems"] == 0
    assert markets["maxItems"] == MAX_PREDICTIONS_PER_ACTION


# ---------------------------------------------------------------------------
# A real payload validates, and a broken one does not
# ---------------------------------------------------------------------------
def _minimal_observation() -> dict[str, Any]:
    return {
        "obs_version": OBS_VERSION,
        "match_id": "m-election-1-01",
        "tick": 1,
        "ticks_total": 48,
        "agent_id": "A1",
        "cash_cents": 1_000_000,
        "reserved_cents": 0,
        "free_cash_cents": 1_000_000,
        "equity_cents": 1_000_000,
        "news": [],
        "signals": [],
        "markets": [],
        "messages": [],
        "limits": {
            "max_active_orders_per_market": 10,
            "price_min": PRICE_MIN,
            "price_max": PRICE_MAX,
            "market_band_cents": 10,
            "taker_fee_bps": 0,
            "message_max_chars": 280,
            "max_orders_per_action": 20,
        },
    }


def test_minimal_observation_with_no_open_market_validates(observation_schema: dict[str, Any]) -> None:
    Draft202012Validator(observation_schema).validate(_minimal_observation())


def test_observation_with_the_mm_as_agent_id_is_rejected(observation_schema: dict[str, Any]) -> None:
    payload = _minimal_observation()
    payload["agent_id"] = "MM"
    validator = Draft202012Validator(observation_schema)
    assert list(validator.iter_errors(payload)), "MM is not a ranked agent and gets no observation"


def _minimal_action() -> dict[str, Any]:
    return {
        "action_version": ACTION_VERSION,
        "predictions": [{"market_id": "M1", "p_yes": 0.62}],
        "orders": [
            {
                "op": "place",
                "market_id": "M1",
                "side": "buy",
                "type": "limit",
                "price": 58,
                "qty": 40,
                "order_id": None,
            }
        ],
        "message_public": None,
        "rationale": None,
    }


def test_minimal_action_validates(action_schema: dict[str, Any]) -> None:
    Draft202012Validator(action_schema).validate(_minimal_action())


def test_action_with_an_unknown_key_is_rejected(action_schema: dict[str, Any]) -> None:
    payload = _minimal_action()
    payload["reasoning"] = "let me think"
    assert list(Draft202012Validator(action_schema).iter_errors(payload))


def test_action_order_uses_the_wire_spelling_type(action_schema: dict[str, Any]) -> None:
    """Section 8.2: the order key is ``type``, never ``order_type``."""
    order_item = action_schema["properties"]["orders"]["items"]
    assert "type" in order_item["properties"]
    assert "order_type" not in order_item["properties"]
    assert "type" in order_item["required"]


def test_too_many_orders_is_rejected_by_the_schema(action_schema: dict[str, Any]) -> None:
    payload = _minimal_action()
    payload["orders"] = payload["orders"] * (MAX_ORDERS_PER_ACTION_CEILING + 1)
    assert list(Draft202012Validator(action_schema).iter_errors(payload))
