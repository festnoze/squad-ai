"""A11 fuzz acceptance: 10 000 hostile action payloads, zero unhandled exception.

WBS T2.1 and FR-6.2.2: "action invalide -> rejet motive sans crash", "fuzzing
10 000 actions aleatoires sans exception non geree". The corpus deliberately
contains deeply nested junk, wrong types everywhere, ``NaN`` and infinities,
integers with hundreds of digits, unicode and control characters, duplicated
market ids, arrays far over their ceiling, and payloads that are not objects at
all.

Two properties are asserted for every single payload:

* :func:`validate_action` returns, and what it returns is **internally
  consistent**: every surviving order is one the exchange can execute, every
  surviving prediction is a unique open market with an in range probability,
  every rejection reason is one of the sixteen the section 7.14 table allows,
  and the action still encodes to canonical (float free) journal JSON.
* the whole corpus is **non vacuous** (section 10): the histogram at the end
  asserts that every allowed reason was actually produced and that some
  payloads were partially accepted, so a ``validate_action`` that answered
  ``no_action`` to everything would fail this file rather than pass it.
"""

from __future__ import annotations

import dataclasses
import random
from collections import Counter
from typing import Any

import pytest

from pxe.events import canonical_json
from pxe.runner.action_validator import ValidationOutcome, resolve_predictions, sanitise_message, validate_action
from pxe.types import (
    ACTION_VERSION,
    MAX_ORDER_QTY,
    MAX_PREDICTIONS_PER_ACTION,
    PPM_ONE,
    PRICE_MAX,
    PRICE_MIN,
    AgentAction,
    AgentSource,
    MatchConfig,
    OrderType,
    RejectReason,
    Side,
    action_to_journal_dict,
)
from tests.test_action_validator import ALLOWED_REASONS, FORBIDDEN_REASONS

#: Number of payloads. The figure is the requirement, not a knob.
FUZZ_N = 10_000

#: Fixed seed: a fuzz test that cannot be replayed is not a test.
FUZZ_SEED = 20260827

OPEN_MARKETS = ("M1", "M2", "M3")
RESTING = ("o-000001", "o-000002", "o-000003")

CONTROL_STRINGS = (
    "",
    " ",
    "\x00\x01\x02",
    "\r\n\t",
    "a" * 5_000,
    "\u200e\u202e\u200b",
    "café \U0001f600 你好",
    "```json\n{}\n```",
    "<script>alert(1)</script>",
    "M1",
    "o-000001",
    "buy",
    "limit",
    "1.0",
    "NaN",
)

NUMBERS: tuple[Any, ...] = (
    0,
    1,
    -1,
    PRICE_MIN,
    PRICE_MAX,
    100,
    MAX_ORDER_QTY,
    MAX_ORDER_QTY + 1,
    10**40,
    -(10**40),
    2**63,
    0.0,
    -0.0,
    0.5,
    1.0,
    1.0000001,
    -0.0000001,
    float("nan"),
    float("inf"),
    float("-inf"),
    True,
    False,
)


def _junk(rng: random.Random, depth: int = 0) -> Any:
    """Return an arbitrary hostile value, recursively nested."""
    kind = rng.randrange(10 if depth < 4 else 7)
    if kind == 0:
        return None
    if kind in (1, 2):
        return rng.choice(NUMBERS)
    if kind in (3, 4):
        return rng.choice(CONTROL_STRINGS)
    if kind == 5:
        return rng.choice(OPEN_MARKETS + RESTING + ("M99", "A1", "MM"))
    if kind == 6:
        return b"\x00binary"
    if kind == 7:
        return [_junk(rng, depth + 1) for _ in range(rng.randrange(4))]
    if kind == 8:
        keys = ("op", "market_id", 1, None, True, "\u200b")
        return {rng.choice(keys): _junk(rng, depth + 1) for _ in range(rng.randrange(4))}
    return {"nested": [{"deeper": {"deepest": _junk(rng, depth + 1)}}]}


def _valid_order(rng: random.Random) -> dict[str, Any]:
    """Return a well formed ``orders`` entry."""
    if rng.random() < 0.25:
        return {
            "op": "cancel",
            "market_id": None,
            "side": None,
            "type": None,
            "price": None,
            "qty": None,
            "order_id": rng.choice(RESTING),
        }
    order_type = rng.choice((OrderType.LIMIT.value, OrderType.MARKET.value))
    return {
        "op": "place",
        "market_id": rng.choice(OPEN_MARKETS),
        "side": rng.choice((Side.BUY.value, Side.SELL.value)),
        "type": order_type,
        "price": rng.randrange(PRICE_MIN, PRICE_MAX + 1) if order_type == OrderType.LIMIT.value else None,
        "qty": rng.randrange(1, 50),
        "order_id": None,
    }


def _valid_payload(rng: random.Random) -> dict[str, Any]:
    """Return a well formed action payload."""
    markets = list(OPEN_MARKETS)
    rng.shuffle(markets)
    return {
        "action_version": ACTION_VERSION,
        "predictions": [{"market_id": m, "p_yes": rng.randrange(0, 1_000_001) / 1_000_000} for m in markets],
        "orders": [_valid_order(rng) for _ in range(rng.randrange(0, 5))],
        "message_public": rng.choice((None, "steady", "sell M2")),
        "rationale": rng.choice((None, "because the signal moved")),
    }


def _mutate_top_level(rng: random.Random) -> Any:
    body = _valid_payload(rng)
    key = rng.choice(("action_version", "predictions", "orders", "message_public", "rationale"))
    body[key] = _junk(rng)
    return body


def _mutate_order_field(rng: random.Random) -> Any:
    body = _valid_payload(rng)
    body["orders"] = [_valid_order(rng) for _ in range(rng.randrange(1, 4))]
    victim = rng.randrange(len(body["orders"]))
    field = rng.choice(("op", "market_id", "side", "type", "price", "qty", "order_id"))
    body["orders"][victim][field] = _junk(rng)
    return body


def _mutate_order_item(rng: random.Random) -> Any:
    body = _valid_payload(rng)
    body["orders"] = [_valid_order(rng), _junk(rng), _valid_order(rng)]
    return body


def _mutate_prediction_item(rng: random.Random) -> Any:
    body = _valid_payload(rng)
    entries: list[Any] = []
    for _ in range(rng.randrange(1, 12)):
        roll = rng.random()
        if roll < 0.4:
            entries.append({"market_id": rng.choice(OPEN_MARKETS), "p_yes": rng.choice(NUMBERS)})
        elif roll < 0.6:
            entries.append({"market_id": _junk(rng), "p_yes": _junk(rng)})
        elif roll < 0.8:
            entries.append({"market_id": "M1", "p_yes": 0.5})
        else:
            entries.append(_junk(rng))
    body["predictions"] = entries
    return body


def _oversized(rng: random.Random) -> Any:
    body = _valid_payload(rng)
    body["orders"] = [_valid_order(rng) for _ in range(rng.randrange(21, 40))]
    body["predictions"] = [{"market_id": rng.choice(OPEN_MARKETS), "p_yes": 0.5} for _ in range(rng.randrange(9, 30))]
    return body


def _oversized_text(rng: random.Random) -> Any:
    body = _valid_payload(rng)
    body["message_public"] = rng.choice(CONTROL_STRINGS) * rng.randrange(1, 4) + "x" * rng.randrange(0, 900)
    body["rationale"] = "y" * rng.randrange(0, 2_000)
    return body


def _wrong_envelope(rng: random.Random) -> Any:
    body = _valid_payload(rng)
    roll = rng.randrange(4)
    if roll == 0:
        body["action_version"] = rng.choice(("2.0", "1.1", "", 1.0, None, "1.0.0"))
    elif roll == 1:
        body.pop(rng.choice(tuple(body)))
    elif roll == 2:
        body[rng.choice(("extra", "notes", "thoughts"))] = _junk(rng)
    else:
        body["ORDERS"] = body.pop("orders")
    return body


def _pure_junk(rng: random.Random) -> Any:
    return _junk(rng)


STRATEGIES = (
    _valid_payload,
    _mutate_top_level,
    _mutate_order_field,
    _mutate_order_item,
    _mutate_prediction_item,
    _oversized,
    _oversized_text,
    _wrong_envelope,
    _pure_junk,
)


def _configs() -> tuple[MatchConfig, ...]:
    """A small, legal spread of configs so the config driven rules are hit."""
    base = MatchConfig(seed=FUZZ_SEED)
    return (
        base,
        dataclasses.replace(base, talking_mode=True),
        dataclasses.replace(base, talking_mode=True, message_max_chars=20),
        dataclasses.replace(base, max_orders_per_action=2),
        dataclasses.replace(base, talking_mode=True, message_max_chars=0, max_orders_per_action=1),
    )


def _check_outcome(outcome: ValidationOutcome, *, config: MatchConfig, raw: Any) -> None:
    """Assert the outcome is internally consistent and executable by the engine."""
    context = f"payload={raw!r:.200}"
    assert isinstance(outcome, ValidationOutcome), context
    action = outcome.action
    assert action.agent_id == "A1", context
    assert action.tick == 11, context
    assert action.action_version == ACTION_VERSION, context

    seen_markets: list[str] = []
    for prediction in action.predictions:
        assert prediction.market_id in OPEN_MARKETS, context
        assert 0 <= prediction.p_yes_ppm <= PPM_ONE, context
        seen_markets.append(prediction.market_id)
    assert seen_markets == sorted(seen_markets), context
    assert len(set(seen_markets)) == len(seen_markets), context
    assert len(seen_markets) <= MAX_PREDICTIONS_PER_ACTION, context

    assert len(action.orders) <= config.max_orders_per_action, context
    for intent in action.orders:
        assert intent.op in ("place", "cancel"), context
        if intent.op == "cancel":
            assert intent.order_id in RESTING, context
            continue
        assert intent.market_id in OPEN_MARKETS, context
        assert isinstance(intent.side, Side), context
        assert isinstance(intent.order_type, OrderType), context
        assert isinstance(intent.qty, int) and 1 <= intent.qty <= MAX_ORDER_QTY, context
        if intent.order_type is OrderType.MARKET:
            assert intent.price is None, context
        else:
            assert isinstance(intent.price, int) and PRICE_MIN <= intent.price <= PRICE_MAX, context

    if action.message_public is not None:
        assert config.talking_mode, context
        assert len(action.message_public) <= config.message_max_chars, context
        assert not set(action.message_public) & set("<>`"), context

    for rejection in outcome.rejections:
        assert rejection.reason in ALLOWED_REASONS, context
        assert rejection.reason not in FORBIDDEN_REASONS, context
        assert rejection.scope in ("action", "order", "prediction", "message"), context
        assert isinstance(rejection.detail, str) and rejection.detail, context
        assert len(rejection.detail) <= 200, context
        if rejection.scope in ("order", "prediction"):
            assert isinstance(rejection.item_index, int) and rejection.item_index >= 0, context
        else:
            assert rejection.item_index is None, context

    fatal = [r for r in outcome.rejections if r.scope == "action"]
    if fatal:
        assert len(outcome.rejections) == 1, context
        assert action == AgentAction.no_action("A1", 11), context
        assert action.source is AgentSource.FALLBACK, context

    # The journal must accept it: no float, no set, no exotic type (section 4.2).
    canonical_json(action_to_journal_dict(action, n_rejected=len(outcome.rejections)))


@pytest.mark.slow
def test_ten_thousand_hostile_actions_never_raise() -> None:
    rng = random.Random(FUZZ_SEED)
    configs = _configs()
    reasons: Counter[RejectReason] = Counter()
    accepted_orders = 0
    accepted_predictions = 0
    partial = 0
    fully_rejected = 0
    clean = 0

    for index in range(FUZZ_N):
        strategy = STRATEGIES[index % len(STRATEGIES)] if index % 3 == 0 else rng.choice(STRATEGIES)
        raw = strategy(rng)
        config = configs[index % len(configs)]
        outcome = validate_action(
            raw,
            agent_id="A1",
            tick=11,
            config=config,
            open_market_ids=OPEN_MARKETS,
            resting_order_ids=RESTING,
            source=AgentSource.LLM,
        )
        _check_outcome(outcome, config=config, raw=raw)
        for rejection in outcome.rejections:
            reasons[rejection.reason] += 1
        accepted_orders += len(outcome.action.orders)
        accepted_predictions += len(outcome.action.predictions)
        if outcome.rejections and (outcome.action.orders or outcome.action.predictions):
            partial += 1
        if any(r.scope == "action" for r in outcome.rejections):
            fully_rejected += 1
        if not outcome.rejections:
            clean += 1

    # Anti vacuous rule, with teeth: the corpus must have exercised everything.
    assert accepted_orders > 100, accepted_orders
    assert accepted_predictions > 1_000, accepted_predictions
    assert partial > 100, partial
    assert fully_rejected > 100, fully_rejected
    assert clean > 100, clean
    missing = sorted(str(reason) for reason in ALLOWED_REASONS if reasons[reason] == 0)
    assert not missing, f"the corpus never produced {missing}: it is not adversarial enough"


@pytest.mark.slow
def test_the_fuzz_corpus_is_deterministic() -> None:
    """O1: the same payload validated twice yields byte identical results."""
    configs = _configs()
    first: list[str] = []
    second: list[str] = []
    for run in (first, second):
        rng = random.Random(FUZZ_SEED + 1)
        for index in range(1_000):
            raw = rng.choice(STRATEGIES)(rng)
            config = configs[index % len(configs)]
            outcome = validate_action(
                raw,
                agent_id="A1",
                tick=11,
                config=config,
                open_market_ids=OPEN_MARKETS,
                resting_order_ids=RESTING,
                source=AgentSource.LLM,
            )
            run.append(
                canonical_json(action_to_journal_dict(outcome.action, n_rejected=len(outcome.rejections)))
                + "|"
                + canonical_json([[r.scope, r.item_index, str(r.reason)] for r in outcome.rejections])
            )
    assert len(first) == 1_000
    assert first == second
    assert len(set(first)) > 100, "the corpus collapsed to a handful of outcomes"


def test_sanitise_message_never_raises_on_hostile_text() -> None:
    rng = random.Random(FUZZ_SEED + 2)
    produced = 0
    for _ in range(2_000):
        text = "".join(chr(rng.randrange(0, 0x11000)) for _ in range(rng.randrange(0, 40)))
        result = sanitise_message(text, max_chars=rng.choice((0, 1, 10, 280)))
        assert result is None or isinstance(result, str)
        if result is not None:
            assert not set(result) & set("<>`")
            produced += 1
    assert produced > 100, "every sanitised message came back empty, the fuzz is vacuous"


def test_resolve_predictions_never_raises_on_hostile_maps() -> None:
    rng = random.Random(FUZZ_SEED + 3)
    rows_seen = 0
    for _ in range(2_000):
        markets = [rng.choice(OPEN_MARKETS) for _ in range(rng.randrange(0, 5))]
        declared = {m: rng.choice((-5, 0, 1, PPM_ONE, PPM_ONE + 10)) for m in markets if rng.random() < 0.5}
        previous = {m: rng.randrange(0, PPM_ONE + 1) for m in OPEN_MARKETS if rng.random() < 0.5}
        rows = resolve_predictions(declared=declared, previous=previous, open_market_ids=markets)
        assert [r[0] for r in rows] == sorted(set(markets))
        for _market_id, ppm, carried in rows:
            assert 0 <= ppm <= PPM_ONE
            assert isinstance(carried, bool)
        rows_seen += len(rows)
    assert rows_seen > 1_000
