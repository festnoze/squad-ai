"""A11 acceptance tests: schema registry, action semantics, truncation, carry.

CONTRACTS section 7.14 and FR-6.2.2 / FR-6.2.4. Section 10's anti vacuous rule
is honoured through :func:`_assert_populated`: every test that claims something
about an outcome first asserts the outcome actually carries data, so a
``validate_action`` that returned an empty action and no rejection for every
input would fail these tests instead of passing them.
"""

from __future__ import annotations

import dataclasses
import inspect
from typing import Any

import pytest

from pxe.errors import InvalidConfigError
from pxe.events import canonical_json
from pxe.runner.action_validator import (
    Rejection,
    ValidationOutcome,
    resolve_predictions,
    sanitise_message,
    validate_action,
)
from pxe.runner.schema_registry import action_schema, load_schema, observation_schema, validator_for
from pxe.types import (
    ACTION_VERSION,
    DEFAULT_PREDICTION_PPM,
    MAX_ORDER_QTY,
    MAX_PREDICTIONS_PER_ACTION,
    PPM_ONE,
    AgentAction,
    AgentSource,
    MatchConfig,
    OrderType,
    RejectReason,
    Side,
    action_to_journal_dict,
)

OPEN_MARKETS = ("M1", "M2", "M3")
RESTING = ("o-000001", "o-000002")

#: The exhaustive list of reasons the section 7.14 table allows this module to
#: produce. Anything outside it belongs to the exchange (P3) or the gateway.
ALLOWED_REASONS = frozenset(
    {
        RejectReason.SCHEMA_INVALID,
        RejectReason.ACTION_INVALID,
        RejectReason.INVALID_ORDER,
        RejectReason.UNKNOWN_MARKET,
        RejectReason.INVALID_PRICE,
        RejectReason.INVALID_QTY,
        RejectReason.INVALID_SIDE,
        RejectReason.INVALID_TYPE,
        RejectReason.MISSING_FIELD,
        RejectReason.UNKNOWN_ORDER,
        RejectReason.TOO_MANY_ORDERS_IN_ACTION,
        RejectReason.TOO_MANY_PREDICTIONS,
        RejectReason.DUPLICATE_PREDICTION,
        RejectReason.INVALID_PROBABILITY,
        RejectReason.MESSAGE_TOO_LONG,
        RejectReason.TALKING_MODE_OFF,
    }
)

#: Reasons that belong to `Exchange.submit` (P3) or to `AgentReply.error`, and
#: that P2 validation must therefore never produce.
FORBIDDEN_REASONS = frozenset(
    {
        RejectReason.MARKET_NOT_OPEN,
        RejectReason.NOT_ORDER_OWNER,
        RejectReason.ORDER_LIMIT_EXCEEDED,
        RejectReason.INSUFFICIENT_COLLATERAL,
        RejectReason.AGENT_FROZEN,
        RejectReason.AGENT_TIMEOUT,
        RejectReason.PROVIDER_ERROR,
        RejectReason.BUDGET_EXCEEDED,
        RejectReason.MALFORMED_RESPONSE,
    }
)


def order_item(**overrides: Any) -> dict[str, Any]:
    """Return one ``orders`` entry with every schema key present."""
    item: dict[str, Any] = {
        "op": "place",
        "market_id": "M1",
        "side": "buy",
        "type": "limit",
        "price": 40,
        "qty": 10,
        "order_id": None,
    }
    item.update(overrides)
    return item


def payload(**overrides: Any) -> dict[str, Any]:
    """Return a fully valid action payload, overridable key by key."""
    body: dict[str, Any] = {
        "action_version": ACTION_VERSION,
        "predictions": [{"market_id": "M1", "p_yes": 0.4}],
        "orders": [order_item()],
        "message_public": None,
        "rationale": None,
    }
    body.update(overrides)
    return body


def run(raw: Any, *, config: MatchConfig, source: AgentSource = AgentSource.LLM) -> ValidationOutcome:
    """Call ``validate_action`` with the standard market and order context."""
    return validate_action(
        raw,
        agent_id="A1",
        tick=7,
        config=config,
        open_market_ids=OPEN_MARKETS,
        resting_order_ids=RESTING,
        source=source,
    )


def _assert_populated(outcome: ValidationOutcome) -> None:
    """Anti vacuous guard (section 10): the outcome must actually carry data.

    An implementation that returned an empty action and an empty rejection
    tuple for every payload would satisfy every type annotation in this file.
    This assertion is what makes that implementation fail.
    """
    assert isinstance(outcome, ValidationOutcome)
    assert outcome.action.agent_id == "A1"
    assert outcome.action.tick == 7
    carries_something = bool(outcome.action.orders) or bool(outcome.action.predictions) or bool(outcome.rejections)
    assert carries_something, "the outcome is empty: nothing was accepted and nothing was rejected"
    for rejection in outcome.rejections:
        assert rejection.reason in ALLOWED_REASONS
        assert rejection.reason not in FORBIDDEN_REASONS
        assert rejection.detail


@pytest.fixture
def talking_config(standard_config: MatchConfig) -> MatchConfig:
    """The reference config with talking mode on (FR-5.6.1)."""
    return dataclasses.replace(standard_config, talking_mode=True)


# ---------------------------------------------------------------------------
# Contracted signatures (section 13.1 rule 1)
# ---------------------------------------------------------------------------
def test_public_names_have_the_literal_contracted_signatures() -> None:
    assert str(inspect.signature(validate_action)) == (
        "(raw: 'Any', *, agent_id: 'str', tick: 'int', config: 'MatchConfig', "
        "open_market_ids: 'Sequence[str]', resting_order_ids: 'Sequence[str]', "
        "source: 'AgentSource') -> 'ValidationOutcome'"
    )
    assert str(inspect.signature(resolve_predictions)) == (
        "(*, declared: 'Mapping[str, int]', previous: 'Mapping[str, int]', "
        "open_market_ids: 'Sequence[str]') -> 'tuple[tuple[str, int, bool], ...]'"
    )
    assert str(inspect.signature(sanitise_message)) == "(text: 'str | None', *, max_chars: 'int') -> 'str | None'"
    assert [f.name for f in dataclasses.fields(Rejection)] == ["scope", "item_index", "reason", "detail"]
    assert [f.name for f in dataclasses.fields(ValidationOutcome)] == ["action", "rejections"]
    assert Rejection("action", None, RejectReason.SCHEMA_INVALID, "x") == Rejection(
        "action", None, RejectReason.SCHEMA_INVALID, "x"
    )


def test_schema_registry_public_names() -> None:
    assert str(inspect.signature(load_schema)) == "(name: 'str') -> 'dict[str, Any]'"
    assert str(inspect.signature(action_schema)) == "() -> 'dict[str, Any]'"
    assert str(inspect.signature(observation_schema)) == "() -> 'dict[str, Any]'"
    assert list(inspect.signature(validator_for).parameters) == ["name"]


# ---------------------------------------------------------------------------
# Schema registry
# ---------------------------------------------------------------------------
def test_schemas_load_and_match_the_repository_files(
    action_schema: dict[str, Any], observation_schema: dict[str, Any]
) -> None:
    loaded_action = load_schema("action.v1")
    assert loaded_action == action_schema
    assert load_schema("observation.v1") == observation_schema
    assert loaded_action["properties"]["orders"]["maxItems"] == 20
    assert loaded_action["properties"]["predictions"]["maxItems"] == MAX_PREDICTIONS_PER_ACTION


def test_a_schema_is_never_patched_at_runtime() -> None:
    """Section 8.2: nobody patches ``maxItems`` at runtime."""
    first = load_schema("action.v1")
    first["properties"]["orders"]["maxItems"] = 9999
    first["properties"].pop("predictions")
    second = load_schema("action.v1")
    assert second["properties"]["orders"]["maxItems"] == 20
    assert "predictions" in second["properties"]
    assert validator_for("action.v1").schema["properties"]["orders"]["maxItems"] == 20


def test_validator_is_cached_and_usable() -> None:
    validator = validator_for("action.v1")
    assert validator is validator_for("action.v1")
    assert list(validator.iter_errors(payload())) == []
    assert list(validator.iter_errors({"action_version": "1.0"})) != []


def test_unknown_schema_name_is_a_caller_bug() -> None:
    with pytest.raises(InvalidConfigError):
        load_schema("action.v2")
    with pytest.raises(InvalidConfigError):
        validator_for("nope")


# ---------------------------------------------------------------------------
# The happy path
# ---------------------------------------------------------------------------
def test_a_valid_action_survives_intact(standard_config: MatchConfig) -> None:
    raw = payload(
        predictions=[{"market_id": "M2", "p_yes": 0.75}, {"market_id": "M1", "p_yes": 0.25}],
        orders=[
            order_item(market_id="M3", side="sell", qty=3, price=61),
            order_item(op="cancel", market_id=None, side=None, type=None, price=None, qty=None, order_id="o-000002"),
            order_item(market_id="M2", type="market", price=None, qty=7),
        ],
        rationale="short reason",
    )
    outcome = run(raw, config=standard_config)
    _assert_populated(outcome)
    assert outcome.rejections == ()
    assert outcome.action.source is AgentSource.LLM
    assert outcome.action.action_version == ACTION_VERSION
    # Predictions are sorted by market_id, orders keep the submitted order (P3).
    assert [p.market_id for p in outcome.action.predictions] == ["M1", "M2"]
    assert [p.p_yes_ppm for p in outcome.action.predictions] == [250_000, 750_000]
    assert [(o.op, o.market_id, o.order_id) for o in outcome.action.orders] == [
        ("place", "M3", None),
        ("cancel", None, "o-000002"),
        ("place", "M2", None),
    ]
    assert outcome.action.orders[0].side is Side.SELL
    assert outcome.action.orders[2].order_type is OrderType.MARKET
    assert outcome.action.orders[2].price is None


def test_the_surviving_action_is_journal_encodable(standard_config: MatchConfig) -> None:
    """No float may reach ``AgentActionReceived`` (sections 2.1 and 4.2)."""
    outcome = run(payload(), config=standard_config)
    _assert_populated(outcome)
    encoded = action_to_journal_dict(outcome.action, n_rejected=len(outcome.rejections))
    text = canonical_json(encoded)
    assert '"p_yes_ppm":400000' in text
    assert encoded["n_rejected"] == 0


def test_validation_is_a_pure_function_of_its_arguments(standard_config: MatchConfig) -> None:
    raw = payload(orders=[order_item(price=0), order_item()])
    first = run(raw, config=standard_config)
    second = run(raw, config=standard_config)
    _assert_populated(first)
    assert first == second


# ---------------------------------------------------------------------------
# Whole action rejections
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        (None, RejectReason.SCHEMA_INVALID),
        (42, RejectReason.SCHEMA_INVALID),
        ("{}", RejectReason.SCHEMA_INVALID),
        ([], RejectReason.SCHEMA_INVALID),
        ({}, RejectReason.SCHEMA_INVALID),
        (
            {"action_version": "0.9", "predictions": [], "orders": [], "message_public": None, "rationale": None},
            RejectReason.ACTION_INVALID,
        ),
        (
            {"action_version": 1.0, "predictions": [], "orders": [], "message_public": None, "rationale": None},
            RejectReason.ACTION_INVALID,
        ),
        ({"predictions": [], "orders": [], "message_public": None, "rationale": None}, RejectReason.SCHEMA_INVALID),
        (
            {"action_version": "1.0", "predictions": {}, "orders": [], "message_public": None, "rationale": None},
            RejectReason.SCHEMA_INVALID,
        ),
    ],
)
def test_an_uninterpretable_payload_becomes_no_action(
    raw: Any, reason: RejectReason, standard_config: MatchConfig
) -> None:
    outcome = run(raw, config=standard_config)
    _assert_populated(outcome)
    assert outcome.action == AgentAction.no_action("A1", 7)
    assert outcome.action.source is AgentSource.FALLBACK
    assert len(outcome.rejections) == 1
    assert outcome.rejections[0].scope == "action"
    assert outcome.rejections[0].item_index is None
    assert outcome.rejections[0].reason is reason


def test_an_unknown_top_level_key_is_fatal(standard_config: MatchConfig) -> None:
    """``additionalProperties: false`` is an envelope rule, not an item rule."""
    outcome = run(payload(surprise=1), config=standard_config)
    _assert_populated(outcome)
    assert outcome.rejections[0].reason is RejectReason.SCHEMA_INVALID
    assert outcome.action.orders == ()


# ---------------------------------------------------------------------------
# The section 7.14 semantic table, row by row
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("item", "reason"),
    [
        (order_item(market_id=None), RejectReason.MISSING_FIELD),
        (order_item(side=None), RejectReason.MISSING_FIELD),
        (order_item(type=None), RejectReason.MISSING_FIELD),
        (order_item(qty=None), RejectReason.MISSING_FIELD),
        (order_item(price=None), RejectReason.MISSING_FIELD),
        (order_item(type="market"), RejectReason.INVALID_PRICE),
        (order_item(price=0), RejectReason.INVALID_PRICE),
        (order_item(price=100), RejectReason.INVALID_PRICE),
        (order_item(price=40.5), RejectReason.INVALID_PRICE),
        (order_item(price=True), RejectReason.INVALID_PRICE),
        (order_item(qty=0), RejectReason.INVALID_QTY),
        (order_item(qty=MAX_ORDER_QTY + 1), RejectReason.INVALID_QTY),
        (order_item(qty=10**40), RejectReason.INVALID_QTY),
        (order_item(qty="10"), RejectReason.INVALID_QTY),
        (order_item(side="BUY"), RejectReason.INVALID_SIDE),
        (order_item(side=1), RejectReason.INVALID_SIDE),
        (order_item(type="stop"), RejectReason.INVALID_TYPE),
        (order_item(op="amend"), RejectReason.INVALID_ORDER),
        (order_item(op=None), RejectReason.INVALID_ORDER),
        ("not an object", RejectReason.INVALID_ORDER),
        (order_item(op="cancel", order_id=None), RejectReason.MISSING_FIELD),
        (order_item(op="cancel", order_id="o-424242"), RejectReason.UNKNOWN_ORDER),
        (order_item(market_id="M8"), RejectReason.UNKNOWN_MARKET),
        (order_item(market_id="not-a-market"), RejectReason.UNKNOWN_MARKET),
    ],
)
def test_an_invalid_order_entry_is_dropped_with_its_reason(
    item: Any, reason: RejectReason, standard_config: MatchConfig
) -> None:
    """FR-6.2.2: the valid sibling survives, the bad entry is dropped."""
    outcome = run(payload(orders=[item, order_item(market_id="M2")]), config=standard_config)
    _assert_populated(outcome)
    assert len(outcome.action.orders) == 1, "the valid sibling must survive the truncation"
    assert outcome.action.orders[0].market_id == "M2"
    assert [(r.scope, r.item_index, r.reason) for r in outcome.rejections] == [("order", 0, reason)]


@pytest.mark.parametrize(
    ("item", "reason"),
    [
        ({"market_id": "M9", "p_yes": 0.5}, RejectReason.UNKNOWN_MARKET),
        ({"market_id": None, "p_yes": 0.5}, RejectReason.UNKNOWN_MARKET),
        ({"p_yes": 0.5}, RejectReason.UNKNOWN_MARKET),
        (["M1", 0.5], RejectReason.UNKNOWN_MARKET),
        ({"market_id": "M1", "p_yes": 1.5}, RejectReason.INVALID_PROBABILITY),
        ({"market_id": "M1", "p_yes": -0.1}, RejectReason.INVALID_PROBABILITY),
        ({"market_id": "M1", "p_yes": "0.5"}, RejectReason.INVALID_PROBABILITY),
        ({"market_id": "M1", "p_yes": None}, RejectReason.INVALID_PROBABILITY),
        ({"market_id": "M1", "p_yes": True}, RejectReason.INVALID_PROBABILITY),
        ({"market_id": "M1", "p_yes": float("nan")}, RejectReason.INVALID_PROBABILITY),
        ({"market_id": "M1", "p_yes": float("inf")}, RejectReason.INVALID_PROBABILITY),
        ({"market_id": "M1"}, RejectReason.INVALID_PROBABILITY),
    ],
)
def test_an_invalid_prediction_entry_is_dropped_with_its_reason(
    item: Any, reason: RejectReason, standard_config: MatchConfig
) -> None:
    outcome = run(payload(predictions=[item, {"market_id": "M3", "p_yes": 0.6}]), config=standard_config)
    _assert_populated(outcome)
    assert [p.market_id for p in outcome.action.predictions] == ["M3"]
    assert [(r.scope, r.item_index, r.reason) for r in outcome.rejections] == [("prediction", 0, reason)]


def test_integer_probabilities_zero_and_one_are_accepted(standard_config: MatchConfig) -> None:
    outcome = run(
        payload(predictions=[{"market_id": "M1", "p_yes": 0}, {"market_id": "M2", "p_yes": 1}]), config=standard_config
    )
    _assert_populated(outcome)
    assert outcome.rejections == ()
    assert [p.p_yes_ppm for p in outcome.action.predictions] == [0, PPM_ONE]


def test_a_duplicated_market_id_keeps_the_first_occurrence(standard_config: MatchConfig) -> None:
    outcome = run(
        payload(
            predictions=[
                {"market_id": "M1", "p_yes": 0.1},
                {"market_id": "M1", "p_yes": 0.9},
                {"market_id": "M1", "p_yes": 0.8},
            ]
        ),
        config=standard_config,
    )
    _assert_populated(outcome)
    assert [(p.market_id, p.p_yes_ppm) for p in outcome.action.predictions] == [("M1", 100_000)]
    assert [(r.item_index, r.reason) for r in outcome.rejections] == [
        (1, RejectReason.DUPLICATE_PREDICTION),
        (2, RejectReason.DUPLICATE_PREDICTION),
    ]


def test_too_many_orders_keeps_the_first_ones(standard_config: MatchConfig) -> None:
    config = dataclasses.replace(standard_config, max_orders_per_action=3)
    outcome = run(payload(orders=[order_item(qty=i + 1) for i in range(6)]), config=config)
    _assert_populated(outcome)
    assert [o.qty for o in outcome.action.orders] == [1, 2, 3]
    assert [(r.item_index, r.reason) for r in outcome.rejections] == [
        (3, RejectReason.TOO_MANY_ORDERS_IN_ACTION),
        (4, RejectReason.TOO_MANY_ORDERS_IN_ACTION),
        (5, RejectReason.TOO_MANY_ORDERS_IN_ACTION),
    ]


def test_too_many_predictions_keeps_the_first_eight(standard_config: MatchConfig) -> None:
    """The ceiling is the schema constant, never a config value (section 8.2)."""
    entries = [{"market_id": "M1", "p_yes": 0.5}] + [{"market_id": f"M{i}", "p_yes": 0.5} for i in range(2, 12)]
    outcome = run(payload(predictions=entries), config=standard_config)
    _assert_populated(outcome)
    over = [r for r in outcome.rejections if r.reason is RejectReason.TOO_MANY_PREDICTIONS]
    assert [r.item_index for r in over] == list(range(MAX_PREDICTIONS_PER_ACTION, len(entries)))
    assert all(
        r.item_index is not None and r.item_index < MAX_PREDICTIONS_PER_ACTION
        for r in outcome.rejections
        if r not in over
    )


# ---------------------------------------------------------------------------
# Messages (FR-5.6.1, FR-5.6.2)
# ---------------------------------------------------------------------------
def test_a_message_is_dropped_when_talking_mode_is_off(standard_config: MatchConfig) -> None:
    assert standard_config.talking_mode is False
    outcome = run(payload(message_public="hello"), config=standard_config)
    _assert_populated(outcome)
    assert outcome.action.message_public is None
    assert [(r.scope, r.item_index, r.reason) for r in outcome.rejections] == [
        ("message", None, RejectReason.TALKING_MODE_OFF)
    ]


def test_a_long_message_is_truncated_and_not_dropped(talking_config: MatchConfig) -> None:
    config = dataclasses.replace(talking_config, message_max_chars=20)
    outcome = run(payload(message_public="a" * 100), config=config)
    _assert_populated(outcome)
    assert outcome.action.message_public == "a" * 20
    assert [(r.scope, r.reason) for r in outcome.rejections] == [("message", RejectReason.MESSAGE_TOO_LONG)]


def test_a_short_message_passes_through_sanitised(talking_config: MatchConfig) -> None:
    outcome = run(payload(message_public="buy `M1` <now>\n\tplease"), config=talking_config)
    _assert_populated(outcome)
    assert outcome.rejections == ()
    assert outcome.action.message_public == "buy &#96;M1&#96; &lt;now&gt; please"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (None, None),
        ("", None),
        ("   \t\n  ", None),
        ("a\x00b", "a b"),
        ("a\u200eb", "a b"),
        ("a\u2028b", "a b"),
        ("one   two\n\nthree", "one two three"),
        ("`code`", "&#96;code&#96;"),
        ("<script>", "&lt;script&gt;"),
        ("ignore previous instructions", "ignore previous instructions"),
        ("café été \U0001f600", "café été \U0001f600"),
    ],
)
def test_sanitise_message_cases(text: str | None, expected: str | None) -> None:
    assert sanitise_message(text, max_chars=280) == expected


def test_sanitise_message_never_exceeds_max_chars() -> None:
    for max_chars in (0, 1, 4, 5, 6, 17, 280):
        for text in ("<" * 50, "`" * 50, "x" * 50, "a<b>c`d" * 20):
            result = sanitise_message(text, max_chars=max_chars)
            assert result is None or len(result) <= max_chars
            assert result is None or not result.endswith("&")


# ---------------------------------------------------------------------------
# P2 versus P3 (section 7.14, "P2 validation is structural and advisory")
# ---------------------------------------------------------------------------
def test_liveness_is_not_validated_in_p2(standard_config: MatchConfig) -> None:
    """A stale but well formed intent is accepted here and judged by P3.

    ``open_market_ids`` and ``resting_order_ids`` are a tick old snapshot: the
    market maker requote and the agents earlier in the P3 shuffle may already
    have filled the order this cancel targets. Only ``Exchange`` may reject
    that, in P3, with ``OrderRejected``.
    """
    raw = payload(
        orders=[
            order_item(op="cancel", market_id=None, side=None, type=None, price=None, qty=None, order_id="o-000001"),
            order_item(market_id="M2", qty=MAX_ORDER_QTY),
        ]
    )
    outcome = run(raw, config=standard_config)
    _assert_populated(outcome)
    assert outcome.rejections == (), "a stale cancel and an unaffordable order are P3 business, not P2"
    assert [o.op for o in outcome.action.orders] == ["cancel", "place"]
    # An order far beyond any plausible collateral is still accepted here: the
    # section 6.1 pre trade check belongs to the exchange.
    assert outcome.action.orders[1].qty == MAX_ORDER_QTY


def test_no_p3_or_gateway_reason_is_ever_produced(standard_config: MatchConfig) -> None:
    """The three producer lists of section 7.14 do not overlap."""
    battery: list[Any] = [
        None,
        {},
        "junk",
        payload(orders=[order_item(price=None)]),
        payload(orders=[order_item(op="cancel", order_id="o-999999")]),
        payload(orders=[order_item(market_id="M7")]),
        payload(predictions=[{"market_id": "M1", "p_yes": 2}]),
        payload(message_public="hi"),
        payload(orders=[order_item(qty=-1)]),
    ]
    seen: set[RejectReason] = set()
    for raw in battery:
        outcome = run(raw, config=standard_config)
        _assert_populated(outcome)
        for rejection in outcome.rejections:
            seen.add(rejection.reason)
    assert seen, "the battery produced no rejection at all, the test would be vacuous"
    assert seen <= ALLOWED_REASONS
    assert not seen & FORBIDDEN_REASONS


# ---------------------------------------------------------------------------
# FR-6.2.4 prediction carry
# ---------------------------------------------------------------------------
def test_carry_defaults_to_half_on_the_first_tick() -> None:
    rows = resolve_predictions(declared={}, previous={}, open_market_ids=["M2", "M1"])
    assert rows == (("M1", DEFAULT_PREDICTION_PPM, True), ("M2", DEFAULT_PREDICTION_PPM, True))
    assert DEFAULT_PREDICTION_PPM == 500_000


def test_carry_prefers_declared_then_previous_then_default() -> None:
    rows = resolve_predictions(
        declared={"M1": 250_000},
        previous={"M1": 900_000, "M2": 700_000},
        open_market_ids=["M3", "M2", "M1"],
    )
    assert rows == (("M1", 250_000, False), ("M2", 700_000, True), ("M3", DEFAULT_PREDICTION_PPM, True))


def test_carry_returns_one_row_per_open_market_in_canonical_order() -> None:
    ids = ["M10", "M2", "M1", "M2"]
    rows = resolve_predictions(declared={}, previous={}, open_market_ids=ids)
    assert [r[0] for r in rows] == ["M1", "M2", "M10"]
    assert len(rows) == 3


def test_carry_ignores_a_closed_market_even_when_declared() -> None:
    rows = resolve_predictions(declared={"M4": 10}, previous={"M4": 20}, open_market_ids=["M1"])
    assert rows == (("M1", DEFAULT_PREDICTION_PPM, True),)


def test_an_invalid_prediction_carries_the_previous_value(standard_config: MatchConfig) -> None:
    """FR-6.2.4 end to end: the drop in P2 is what makes the carry visible."""
    outcome = run(payload(predictions=[{"market_id": "M1", "p_yes": 7.0}]), config=standard_config)
    _assert_populated(outcome)
    assert outcome.rejections[0].reason is RejectReason.INVALID_PROBABILITY
    declared = {p.market_id: p.p_yes_ppm for p in outcome.action.predictions}
    assert declared == {}
    rows = resolve_predictions(declared=declared, previous={"M1": 620_000}, open_market_ids=["M1", "M2"])
    assert rows == (("M1", 620_000, True), ("M2", DEFAULT_PREDICTION_PPM, True))


def test_a_timed_out_agent_carries_everything(standard_config: MatchConfig) -> None:
    """FR-5.1.1: no reply means no action, and every prediction is carried."""
    outcome = run(None, config=standard_config)
    _assert_populated(outcome)
    rows = resolve_predictions(
        declared={p.market_id: p.p_yes_ppm for p in outcome.action.predictions},
        previous={"M1": 111_111},
        open_market_ids=OPEN_MARKETS,
    )
    assert all(carried for _, _, carried in rows)
    assert rows[0] == ("M1", 111_111, True)


def test_a_rejection_detail_never_exceeds_the_event_ceiling(standard_config: MatchConfig) -> None:
    """``AgentActionRejected.detail`` is documented as at most 200 characters."""
    giant = "M" + "9" * 10_000
    outcome = run(
        payload(
            predictions=[{"market_id": giant, "p_yes": "\u0000" * 5_000}],
            orders=[order_item(market_id=giant), order_item(op="cancel", order_id=giant)],
        ),
        config=standard_config,
    )
    _assert_populated(outcome)
    assert len(outcome.rejections) == 3
    for rejection in outcome.rejections:
        assert 0 < len(rejection.detail) <= 200, rejection.detail


def test_a_scripted_action_round_trips_through_the_validator(standard_config: MatchConfig) -> None:
    """A12 and A13 reach the engine through this door too (section 7.15).

    ``ScriptedGateway`` wraps the ``AgentAction`` a baseline returned with
    ``types.action_to_payload`` and puts it in ``AgentReply.raw``, so a scripted
    agent must survive ``validate_action`` unchanged. This test uses the encoder
    directly and therefore needs neither A12 nor A13 to exist.
    """
    from pxe.types import OrderIntent, PredictionIntent, action_to_payload

    original = AgentAction(
        agent_id="A1",
        tick=7,
        action_version=ACTION_VERSION,
        predictions=(
            PredictionIntent(market_id="M1", p_yes_ppm=123_456),
            PredictionIntent(market_id="M3", p_yes_ppm=0),
        ),
        orders=(
            OrderIntent(op="place", market_id="M2", side=Side.SELL, order_type=OrderType.LIMIT, price=88, qty=4),
            OrderIntent(op="cancel", order_id="o-000002"),
            OrderIntent(op="place", market_id="M1", side=Side.BUY, order_type=OrderType.MARKET, qty=1),
        ),
        source=AgentSource.SCRIPTED,
    )
    outcome = run(action_to_payload(original), config=standard_config, source=AgentSource.SCRIPTED)
    _assert_populated(outcome)
    assert outcome.rejections == ()
    assert outcome.action == original
