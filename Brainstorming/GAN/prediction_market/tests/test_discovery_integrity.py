"""Causal archive metadata and statistically non-degenerate discovery evidence."""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from tests.test_observation import DAY, a_config, a_market
from tests.test_rules import _drift_rule, _table, _template
from tests.test_sensors import NOW_MS, Inputs, make_meta

from pmx.data.builder import market_facts
from pmx.data.schema import MarketModel
from pmx.engine.fees import FEE_SCHEDULES
from pmx.engine.liquidity import LiquidityOrder, finalise_fill
from pmx.engine.observation import market_view_fields
from pmx.errors import SchemaError
from pmx.journal import validate_event_dict
from pmx.rng import RngTree
from pmx.rules.miner import MinedCandidate, mine
from pmx.rules.rule import RuleClaim, RuleScope
from pmx.rules.tester import RuleLedger, RuleTester, _delta_bp, rolling_pair, target_available_at_ms
from pmx.sensors import calendar
from pmx.sensors.catalogue import SENSORS
from pmx.types import Market, PositionView, meta_of


def test_sparse_binary_rows_keep_clock_horizon_instead_of_next_observation() -> None:
    original = _table().markets[0]
    sparse = replace(original, bars=(original.bars[0], original.bars[2], original.bars[3]))
    claim = _drift_rule(0).claim
    assert _delta_bp(sparse, 0, 1) is None
    assert target_available_at_ms(sparse, 0, claim, 1) is None
    assert _delta_bp(sparse, 0, 2) == original.bars[2].close_bp - original.bars[0].close_bp
    assert target_available_at_ms(sparse, 0, claim, 2) == original.bars[2].t_ms + 60_000 * original.meta.interval_min


def test_binary_provider_identifier_survives_journal_symbol_validation() -> None:
    condition_id = "0x" + "a7" * 32
    market = replace(a_market(), provider_id=condition_id)
    accepted = MarketModel.model_validate(market.to_dict()).to_market()
    fixture = Path(__file__).parent / "fixtures" / "contract" / "journal.backtest.jsonl"
    listed = next(payload for line in fixture.read_text(encoding="utf-8").splitlines()
                  if (payload := json.loads(line))["type"] == "market_listed")
    listed["symbol"] = accepted.instrument.symbol
    assert listed["symbol"] == condition_id
    validate_event_dict(listed)
    validate_event_dict({**listed, "symbol": "a" * 128})
    with pytest.raises(SchemaError):
        validate_event_dict({**listed, "symbol": "a" * 129})
    with pytest.raises(SchemaError):
        validate_event_dict({**listed, "kind": "perp"})


def test_unknown_expiry_and_unobserved_first_print_cannot_predict_the_future() -> None:
    original = replace(a_market(), close_time_verified=False, currency="usdc")
    poisoned = replace(original, close_at_ms=40 * DAY, resolved_at_ms=50 * DAY, resolution=0)
    position = PositionView(position=0, avg_cost_bp=0, unrealised_cents=0)

    def view(market: Market, now: int) -> dict[str, object]:
        return market_view_fields(market, now_ms=now, config=a_config(), tradable=True, position=position)

    assert view(original, 3 * DAY) == view(poisoned, 3 * DAY)
    assert view(original, 3 * DAY)["close_at_ms"] == 0
    assert view(original, 0) == view(replace(poisoned, first_price_bp=9_999), 0)
    assert view(original, 0)["last_price_bp"] == 5_000
    assert view(original, DAY)["first_price_bp"] == original.first_price_bp
    meta = replace(make_meta(), close_time_verified=False)
    first = calendar.sense(Inputs(meta=meta), now_ms=NOW_MS, spec=SENSORS["calendar"])
    second = calendar.sense(
        Inputs(meta=replace(meta, close_at_ms=meta.close_at_ms + 200 * DAY)),
        now_ms=NOW_MS, spec=SENSORS["calendar"],
    )
    assert first == second
    assert first.values[:2] == tuple(feature.sentinel for feature in SENSORS["calendar"].features[:2])


def test_unknown_close_flag_survives_canonical_market_and_builder_facts() -> None:
    market = replace(a_market(), close_time_verified=False, currency="usdc")
    parsed = MarketModel.model_validate(market.to_dict()).to_market()
    assert parsed.currency == "usdc"
    assert not parsed.close_time_verified
    assert not meta_of(parsed, fold="train").close_time_verified
    assert not market_facts(parsed.to_dict()).close_time_verified
    assert "close_time_verified" not in a_market().to_dict()


def test_one_shared_block_cannot_promote_a_planted_positive_effect(tmp_path: Path) -> None:
    independent = _table()
    dependent = replace(independent, markets=tuple(replace(row, block="one-event") for row in independent.markets))
    pair = rolling_pair(dependent, 4)
    tester = RuleTester(
        dependent, rng=RngTree(5), ledger=RuleLedger(root=tmp_path, dataset_hash=dependent.dataset_hash),
    )
    result = tester.run_family(
        [_drift_rule(pair.registered_at_ms)], template=_template(), pair=pair, n_candidates=1,
    )
    assert result.fit[0].support >= 30
    assert not result.fit[0].passed
    assert not result.promotions


def test_mining_audit_retains_rejected_hypotheses() -> None:
    table = _table()
    attempts: list[MinedCandidate] = []
    result = mine(
        table, rolling_pair(table, 4), scope=RuleScope(kinds=("binary",), providers=("kalshi",)),
        claim=RuleClaim(kind="drift", direction=1, magnitude_bp=120, factor_ppm=0),
        horizon_bars=1, features=("ret_7b_bp",), min_support=100_000,
        on_candidate=attempts.append,
    )
    assert result.n_candidates > 0
    assert not result.candidates
    assert len(attempts) == result.n_candidates
    assert len({row.rule.rule_id for row in attempts}) == len(attempts)


def test_research_fee_charges_twenty_basis_points_on_actual_fill_notional() -> None:
    bar = replace(
        a_market().bars[0], open_bp=9000, high_bp=9000, low_bp=9000,
        close_bp=9000, vwap_bp=9000, volume_milli=1_000_000,
    )
    fill = finalise_fill(
        quoted_bp=9000, base_bp=9000,
        order=LiquidityOrder(side="buy", kind="market", size_milli=100_000),
        bar=bar, filled_milli=100_000, unfilled_reason="none", price_source="open",
        schedule=FEE_SCHEDULES["polymarket-research-2026-04"],
    )
    # 100 contracts * 0.90 USDC * 0.002 = 0.18 USDC, or 18 minor units.
    assert fill.fee_cents == 18
