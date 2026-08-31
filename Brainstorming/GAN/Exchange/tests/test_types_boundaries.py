"""Boundary tests for :mod:`pxe.types` (A01).

Everything here guards a seam between two workstreams: the journal and wire
encodings of an agent action, the harness identity four workstreams consume and
none used to produce, the error to reject reason mapping, the incident detail
shapes, and the read only inventory view the market maker needs. A boundary
without a test is a boundary two agents implement differently.
"""

import dataclasses
import inspect

import pytest

from pxe import errors
from pxe.errors import InvalidConfigError, PxeError
from pxe.events import canonical_json
from pxe.types import (
    ACTION_VERSION,
    AgentAction,
    AgentSource,
    HarnessConfig,
    Incident,
    IncidentKind,
    InventoryView,
    MarketSpec,
    MatchConfig,
    MatchTask,
    OrderIntent,
    OrderType,
    PredictionIntent,
    RejectReason,
    ScenarioSpec,
    Side,
    action_to_journal_dict,
    action_to_payload,
    harness_config_hash,
    harness_key,
    incident_detail_from_dict,
    incident_detail_to_dict,
    market_spec_from_dict,
    market_spec_to_dict,
    order_intent_from_dict,
    order_intent_to_dict,
    prediction_intent_to_dict,
    prediction_intent_to_wire_dict,
    reject_reason_of,
    scenario_from_journal_dict,
    scenario_to_journal_dict,
)


def _intent() -> OrderIntent:
    return OrderIntent(
        op="place",
        market_id="M1",
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        price=42,
        qty=7,
    )


def _action() -> AgentAction:
    return AgentAction(
        agent_id="A1",
        tick=3,
        action_version=ACTION_VERSION,
        predictions=(PredictionIntent(market_id="M1", p_yes_ppm=250_000),),
        orders=(_intent(), OrderIntent(op="cancel", order_id="o-000001")),
        message_public="hello",
        rationale="because",
        source=AgentSource.LLM,
    )


def _scenario() -> ScenarioSpec:
    return ScenarioSpec(
        template_id="election",
        template_version="1.0.0",
        seed=7,
        ticks_total=48,
        markets=(
            MarketSpec(
                market_id="M1",
                question="Does it?",
                prior_price=50,
                resolution_tick=48,
                latent_key="k1",
                correlation_group="g",
                tags=("a",),
            ),
            MarketSpec(
                market_id="M2",
                question="And that?",
                prior_price=30,
                resolution_tick=24,
                latent_key="k2",
            ),
        ),
        correlations=(("M1", "M2", 600),),
        cancellations=((12, "M2", "scripted"),),
        notes="n",
    )


# --------------------------------------------------------------------------
# Section 7.1: the journal shape and the wire shape are two shapes
# --------------------------------------------------------------------------
def test_order_intent_uses_the_wire_key_type() -> None:
    payload = order_intent_to_dict(_intent())
    assert "type" in payload
    assert "order_type" not in payload
    assert set(payload) == {"op", "market_id", "side", "type", "price", "qty", "order_id"}


def test_order_intent_keeps_the_null_fields() -> None:
    payload = order_intent_to_dict(OrderIntent(op="cancel", order_id="o-000002"))
    assert payload["market_id"] is None
    assert payload["side"] is None
    assert payload["type"] is None
    assert payload["price"] is None
    assert payload["qty"] is None


def test_order_intent_round_trip() -> None:
    intent = _intent()
    assert order_intent_from_dict(order_intent_to_dict(intent)) == intent


def test_prediction_has_a_ppm_journal_shape_and_a_float_wire_shape() -> None:
    intent = PredictionIntent(market_id="M1", p_yes_ppm=250_000)
    assert prediction_intent_to_dict(intent) == {"market_id": "M1", "p_yes_ppm": 250_000}
    assert prediction_intent_to_wire_dict(intent) == {"market_id": "M1", "p_yes": 0.25}


@pytest.mark.determinism
def test_action_journal_dict_is_canonical_json_encodable() -> None:
    line = canonical_json(action_to_journal_dict(_action(), n_rejected=2))
    assert '"p_yes_ppm":250000' in line
    assert 'p_yes":' not in line.replace("p_yes_ppm", "")
    assert '"n_rejected":2' in line


def test_action_payload_is_the_wire_shape() -> None:
    payload = action_to_payload(_action())
    assert set(payload) == {
        "action_version",
        "predictions",
        "orders",
        "message_public",
        "rationale",
    }
    assert payload["predictions"][0]["p_yes"] == 0.25
    # The wire shape has no agent_id and no source: the engine knows both.
    assert "agent_id" not in payload
    assert "source" not in payload


# --------------------------------------------------------------------------
# Section 7.1: MarketSpec and ScenarioSpec round trips (replay_journal needs them)
# --------------------------------------------------------------------------
def test_market_spec_round_trip() -> None:
    spec = _scenario().markets[0]
    assert market_spec_from_dict(market_spec_to_dict(spec)) == spec


def test_scenario_round_trip() -> None:
    scenario = _scenario()
    assert scenario_from_journal_dict(scenario_to_journal_dict(scenario)) == scenario


@pytest.mark.determinism
def test_scenario_journal_dict_is_canonical_json_encodable() -> None:
    canonical_json(scenario_to_journal_dict(_scenario()))


# --------------------------------------------------------------------------
# Section 2.2: the harness key and hash have one producer
# --------------------------------------------------------------------------
def test_harness_config_hash_is_filled_and_stable() -> None:
    harness = HarnessConfig(harness_id="h", version="1.0", kind="llm", model="m", system_prompt="p")
    assert harness.config_hash == harness_config_hash(harness)
    assert len(harness.config_hash) == 16
    twin = HarnessConfig(harness_id="h", version="1.0", kind="llm", model="m", system_prompt="p")
    assert twin.config_hash == harness.config_hash


def test_harness_key_separates_two_prompts_under_one_version() -> None:
    a = HarnessConfig(harness_id="h", version="1.0", kind="llm", model="m", system_prompt="one")
    b = HarnessConfig(harness_id="h", version="1.0", kind="llm", model="m", system_prompt="two")
    assert a.key != b.key
    assert a.key == harness_key(a)
    assert a.key.startswith("h@1.0+")


def test_harness_config_hash_ignores_the_stored_hash() -> None:
    harness = HarnessConfig(harness_id="h", version="1.0", kind="scripted")
    stamped = dataclasses.replace(harness, config_hash="0" * 16)
    assert harness_config_hash(stamped) == harness_config_hash(harness)


# --------------------------------------------------------------------------
# Section 2.4: every exchange and gateway error maps to a RejectReason
# --------------------------------------------------------------------------
def _leaf_subclasses(root: type) -> list[type]:
    out: list[type] = []
    for obj in vars(errors).values():
        if inspect.isclass(obj) and issubclass(obj, root) and obj is not root:
            out.append(obj)
    return out


def test_every_exchange_error_maps() -> None:
    families = (errors.ExchangeError, errors.GatewayError)
    classes = [cls for family in families for cls in _leaf_subclasses(family)]
    assert classes, "the error module lost its exchange and gateway families"
    for cls in classes:
        reason = reject_reason_of(cls("boom"))
        assert isinstance(reason, RejectReason)


def test_reject_reason_of_refuses_an_unmapped_code() -> None:
    class UnmappedError(PxeError):
        code = "NOT_A_REASON"

    with pytest.raises(InvalidConfigError):
        reject_reason_of(UnmappedError("boom"))


# --------------------------------------------------------------------------
# Section 7.18: the two incident detail shapes convert through one pair
# --------------------------------------------------------------------------
def test_incident_detail_round_trip_is_sorted() -> None:
    incident = Incident(
        incident_id="i-0001",
        kind=IncidentKind.COLLUSION,
        severity="high",
        tick=5,
        agent_ids=("A1", "A2"),
        market_ids=("M1",),
        score_ppm=800_000,
        detail=(("pair_index_ppm", 812_000), ("a_first", True)),
        detector_version="1.0.0",
    )
    mapping = incident_detail_to_dict(incident.detail)
    assert canonical_json(mapping)
    assert incident_detail_from_dict(mapping) == (
        ("a_first", True),
        ("pair_index_ppm", 812_000),
    )


def test_incident_detail_refuses_a_duplicate_key() -> None:
    with pytest.raises(InvalidConfigError):
        incident_detail_to_dict((("k", 1), ("k", 2)))


# --------------------------------------------------------------------------
# Section 7.10: the inventory view is read only and sorted
# --------------------------------------------------------------------------
def test_inventory_view_reads_positions() -> None:
    view = InventoryView(
        account_id="MM",
        cash_cents=10_000_000,
        reserved_cents=1_000,
        free_cash_cents=9_999_000,
        inventory_qty_by_market=(("M1", -25), ("M2", 40)),
    )
    assert view.inventory_qty("M1") == -25
    assert view.inventory_qty("M2") == 40
    assert view.inventory_qty("M3") == 0


def test_inventory_view_rejects_an_unsorted_market_list() -> None:
    with pytest.raises(InvalidConfigError):
        InventoryView(
            account_id="MM",
            cash_cents=0,
            reserved_cents=0,
            free_cash_cents=0,
            inventory_qty_by_market=(("M2", 1), ("M1", 1)),
        )


# --------------------------------------------------------------------------
# Section 7: the tournament carriers live here, so store and tournament do not
# import each other
# --------------------------------------------------------------------------
def test_tournament_carriers_are_importable_from_types() -> None:
    task = MatchTask(
        task_id="t-1",
        match_id="m-election-1-00",
        template_id="election",
        seed=1,
        agent_ids=("A1", "A2"),
        harness_keys=("h@1.0+aaaaaaaa", "h@1.1+bbbbbbbb"),
        profile_assignment=(),
    )
    assert task.agent_ids == ("A1", "A2")


def test_match_task_rejects_a_seat_without_a_harness() -> None:
    with pytest.raises(InvalidConfigError):
        MatchTask(
            task_id="t-1",
            match_id="m-election-1-00",
            template_id="election",
            seed=1,
            agent_ids=("A1", "A2"),
            harness_keys=("h@1.0+aaaaaaaa",),
            profile_assignment=(),
        )


# --------------------------------------------------------------------------
# Section 8.2: the schema is the hard ceiling, the config may only lower it
# --------------------------------------------------------------------------
def test_max_orders_per_action_cannot_exceed_the_schema_ceiling() -> None:
    with pytest.raises(InvalidConfigError):
        MatchConfig(max_orders_per_action=40)
