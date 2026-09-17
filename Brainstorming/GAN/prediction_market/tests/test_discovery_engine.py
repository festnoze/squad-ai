"""Offline discovery: causal proposals, actual engine fills, isolation and frozen selection."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from tests.test_observation import DAY, a_dataset, a_market, demo_manifest, one_observation

from pmx.agents.registry import PARAMETERS, ScriptedGenome, make_agent
from pmx.engine.runner import replay
from pmx.journal import EquityMarked, read_journal
from pmx.optimizer import discovery
from pmx.optimizer.discovery import DiscoveryConfig, evaluate_candidate, plan_periods, run_campaign
from pmx.optimizer.features import blocks_for_view, training_table
from pmx.optimizer.strategies import DiscoveryAgent, RuleAgent, RuleGenome
from pmx.rules.rule import Predicate, RuleClaim, RuleScope, make_rule
from pmx.types import Dataset, DatasetSplit, DatasetWindow, Market, RunConfig, meta_of


def research_dataset(*, poisoned_validation: bool = False, poisoned_future: bool = False) -> Dataset:
    markets = []
    for index in range(20):
        end = 9 if index < 6 else 19 if index < 11 else 29 if index < 16 else 39 if index < 19 else 49
        prices = [2100 + (bar % 4) * 100 + index * 5 for bar in range(end + 1)]
        market = a_market(f"demo-p{index:02d}", created_day=0, n_bars=end + 1, prices=prices)
        market = replace(market, description="Fixture", first_price_bp=prices[0])
        if (poisoned_validation and 16 <= index < 19) or (poisoned_future and index >= 6):
            market = replace(market, resolution=0)
        markets.append(market)
    split = DatasetSplit((), 30 * DAY, 40 * DAY, 16, 3, 1)
    manifest = replace(
        demo_manifest(), name="research_fixture", purpose="research", window=DatasetWindow(0, 50 * DAY),
        split=split,
    )
    return a_dataset(
        markets, manifest=manifest, metas=[meta_of(m, fold=split.fold_of(m.resolved_at_ms)) for m in markets]
    )


def config(**kwargs: Any) -> DiscoveryConfig:
    return DiscoveryConfig(provider="demo", n_trials=4, max_markets=30, n_splits=2, finalists=1,
                           mining_budget=200, **kwargs)


def test_parameter_changes_are_effective_and_strictly_validated() -> None:
    obs = one_observation([a_market("demo-alpha", prices=[1000, 2000, 3000, 4000, 5000, 6000], n_bars=6)],
                          now_ms=4 * DAY)
    decisions = []
    for strength in (250, 1000):
        params = {**PARAMETERS["trend"], "strength_permille": strength, "max_edge_bp": 3000}
        agent = make_agent("candidate", ScriptedGenome("trend", tuple(sorted(params.items()))))
        agent.observe(obs)
        decisions.append(agent.decide().markets[0])
    assert decisions[0].prob_ppm != decisions[1].prob_ppm
    assert decisions[0].target_position != decisions[1].target_position
    for value in (True, 10_000, -1):
        params = {**PARAMETERS["trend"], "max_position": value}
        with pytest.raises(ValueError, match="max_position"):
            make_agent("candidate", ScriptedGenome("trend", tuple(sorted(params.items()))))


def test_fit_does_not_load_future_or_validation_and_sensor_parity() -> None:
    dataset = research_dataset()
    cutoff = 10 * DAY
    original_loader = dataset.market_loader
    assert original_loader is not None
    loaded = []

    def guarded_loader(market_id: str) -> Market:
        meta = dataset.meta(market_id)
        assert meta.fold == "train" and meta.resolved_at_ms < cutoff
        loaded.append(market_id)
        market = original_loader(market_id)
        assert isinstance(market, Market)
        return market

    guarded = replace(dataset, market_loader=guarded_loader, _markets={}, _whole={})
    table = training_table(guarded, guarded.metas, provider="demo", fit_t1_ms=cutoff)
    assert len(table.markets) == len(loaded) == 6
    poisoned = research_dataset(poisoned_future=True)
    other = training_table(poisoned, poisoned.metas, provider="demo", fit_t1_ms=cutoff)
    assert table == other
    row = table.markets[0].bars[4]
    market = original_loader(table.markets[0].meta.id)
    observation = one_observation([market], now_ms=row.t_ms + DAY)
    blocks = blocks_for_view(observation.markets[0], now_ms=observation.now_ms, interval=DAY)
    assert blocks == row.blocks


def test_zero_volume_carried_rows_do_not_supply_mining_support() -> None:
    dataset = research_dataset()
    original = dataset.market_loader
    assert original is not None

    def zero_volume(market_id: str) -> Market:
        market = original(market_id)
        assert isinstance(market, Market)
        return replace(market, bars=tuple(replace(bar, volume_milli=0, n_trades=0) for bar in market.bars))

    empty = replace(dataset, market_loader=zero_volume)
    table = training_table(empty, empty.metas, provider="demo", fit_t1_ms=10 * DAY)
    assert table.markets == ()


def test_discovery_waits_until_first_bar_completes() -> None:
    market = a_market("demo-alpha", n_bars=6)
    agent = DiscoveryAgent("candidate", ScriptedGenome("level", tuple(sorted(PARAMETERS["level"].items()))))
    for first_price in (100, 9000):
        agent.observe(one_observation([replace(market, first_price_bp=first_price)], now_ms=0))
        assert agent.decide().markets == ()
    agent.observe(one_observation([market], now_ms=DAY))
    assert len(agent.decide().markets) == 1


def test_true_conjunctions_are_mined_and_every_enumeration_is_recorded(tmp_path: Path) -> None:
    dataset = research_dataset()
    periods = plan_periods(dataset, config())
    rules, details = discovery._mine_rules(dataset, config(), periods[0], tmp_path)
    audit = [json.loads(line) for line in (tmp_path / "mining-candidates.jsonl").read_text().splitlines()]
    assert rules and any(len(rule.condition) > 1 for rule in rules)
    assert len(audit) == details["n_enumerated"] <= 200
    assert any(row["status"] == "rejected" for row in audit)
    assert any(row["status"] == "accepted" for row in audit)
    assert details["n_rules_used"] == len(rules)


def test_disjoint_periods_and_validation_never_replays_training_history() -> None:
    periods = plan_periods(research_dataset(), config())
    assert [p.name for p in periods] == ["fit", "train_1", "train_2", "validation"]
    assert all(left.t1_ms == right.t0_ms for left, right in zip(periods, periods[1:], strict=False))
    assert periods[-1].t0_ms == 30 * DAY
    assert periods[1].t0_ms == 10 * DAY
    assert all(not market_id.endswith("19") for p in periods for market_id in p.market_ids)


def test_rule_cannot_execute_before_it_was_fitted_and_ignores_future_prices() -> None:
    rule = make_rule(
        author_kind="miner", author_id="miner", born_at_ms=4 * DAY,
        scope=RuleScope(), condition=(Predicate("last_price_bp", "le", 5000),),
        claim=RuleClaim("bias", 1, 100, 0), horizon_bars=0, min_support=30,
    )
    genome = RuleGenome("rule", (("edge_min_bp", 50), ("max_edge_bp", 1000), ("max_position", 20)), rule, 4 * DAY)
    market = a_market("demo-alpha", n_bars=6, prices=[2000, 3000, 4000, 4500, 5000, 6000])
    agent = RuleAgent("candidate", genome)
    agent.reset(rng=object(), memory=None, config=RunConfig(seed=1))
    agent.observe(one_observation([market], now_ms=3 * DAY))
    with pytest.raises(ValueError, match="before"):
        agent.decide()
    actions = []
    for tape in (market, replace(market, resolution=0, bars=(*market.bars[:4], *[
        replace(bar, close_bp=9000) for bar in market.bars[4:]
    ]))):
        agent.observe(one_observation([tape], now_ms=4 * DAY))
        actions.append(agent.decide())
    assert actions[0] == actions[1]
    assert actions[0].markets[0].target_position == 20


def test_window_pnl_is_actual_marked_equity_and_candidates_are_isolated(tmp_path: Path) -> None:
    dataset = research_dataset()
    period = plan_periods(dataset, config())[1]
    genome = ScriptedGenome("level", tuple(sorted(PARAMETERS["level"].items())))
    first = evaluate_candidate(dataset, config(), genome, "candidate", period, tmp_path / "first")
    second = evaluate_candidate(dataset, config(), genome, "candidate", period, tmp_path / "second")
    assert first["journal_hash"] == second["journal_hash"]
    events = read_journal(Path(first["run_dir"]) / "journal.jsonl")
    last_mark = [event for event in events if isinstance(event, EquityMarked)][-1]
    assert first["pnl_cents"] == last_mark.equity_cents - 100_000
    assert first["n_fills"] > 0
    assert first["n_markets"] > first["n_settled_markets"]
    assert replay(Path(first["run_dir"])).run_id == first["run_id"]


def test_campaign_frozen_selection_validation_poisoning_and_restart(tmp_path: Path) -> None:
    def execute(dataset: Dataset, output: Path) -> dict[str, Any]:
        original = dataset.market_loader
        assert original is not None
        campaign_id = discovery.campaign_id_for(dataset, config())

        def guard(market_id: str) -> Market:
            meta = dataset.meta(market_id)
            assert meta.fold != "sealed", "sealed market was loaded"
            if meta.fold == "validation":
                assert (output / campaign_id / "selection.json").exists()
            market = original(market_id)
            assert isinstance(market, Market)
            return market

        return run_campaign(replace(dataset, market_loader=guard), config(), output)

    first = execute(research_dataset(), tmp_path / "first")
    changed = execute(research_dataset(poisoned_validation=True), tmp_path / "changed")
    assert first["status"] == changed["status"] == "completed"
    assert first["progress"] == {"completed_trials": 4, "total_trials": 4}
    assert first["selected_candidate_ids"] == changed["selected_candidate_ids"]
    symbolic = next(row for row in first["candidates"] if row["family"] == "rule")
    assert len(symbolic["rule"]["condition"]) > 1
    assert symbolic["status"] != "failed"
    assert replay(Path(symbolic["train_results"][0]["run_dir"])).run_id == symbolic["train_results"][0]["run_id"]
    for left, right in zip(first["candidates"], changed["candidates"], strict=True):
        assert (left["parameters"], left["objective"], left["selected"]) == (
            right["parameters"], right["objective"], right["selected"]
        )
    selected = [row for row in first["candidates"] if row["selected"]]
    assert selected and all(row["validation_status"] == "completed" for row in selected)
    assert all(not row["validation_results"] for row in first["candidates"] if not row["selected"])
    # Results survive a new reader; repeated execution returns the persisted artifact verbatim.
    assert run_campaign(research_dataset(), config(), tmp_path / "first") == first


def test_failed_trials_are_persisted_without_stopping_other_trials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def fail_once(*args: Any, **kwargs: Any) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("deliberate candidate failure")
        return {"pnl_cents": 0, "n_fills": 0, "max_drawdown_bp": 0, "traded_market_ids": []}

    monkeypatch.setattr(discovery, "evaluate_candidate", fail_once)
    result = run_campaign(research_dataset(), config(), tmp_path)
    assert len(result["candidates"]) == 4
    assert result["candidates"][0]["status"] == "failed"
    assert "deliberate" in result["candidates"][0]["error"]
    assert all(row["status"] == "rejected" for row in result["candidates"][1:])
    saved = discovery.read_campaign(tmp_path / result["campaign_id"] / "campaign.json")
    assert saved == result


def test_one_traded_market_does_not_qualify_as_executed_support(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    def sparse_fill(*args: Any, **kwargs: Any) -> dict[str, Any]:
        period = args[4]
        return {
            "pnl_cents": 100, "n_fills": 1 if period.name == "train_1" else 0,
            "max_drawdown_bp": 0, "traded_market_ids": ["demo-p06"] if period.name == "train_1" else [],
        }

    monkeypatch.setattr(discovery, "evaluate_candidate", sparse_fill)
    result = run_campaign(research_dataset(), config(), tmp_path)
    assert result["selected_candidate_ids"] == []
    for candidate in result["candidates"]:
        assert candidate["status"] == "rejected"
        assert set(candidate["rejection_reasons"]) == {
            "no_trades_in_at_least_one_train_period", "fewer_than_5_distinct_traded_markets",
        }


@pytest.mark.parametrize("kwargs", [{"n_trials": 101}, {"n_splits": 1}, {"mining_budget": 1001}, {"seed": True}])
def test_budgets_are_enforced(kwargs: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        DiscoveryConfig(provider="demo", **kwargs)
