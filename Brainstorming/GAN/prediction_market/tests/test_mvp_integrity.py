"""MVP regressions: independent run identities and results that really exist as of a timestamp."""

from dataclasses import replace
from pathlib import Path

from tests.stub_roster import StubGenome, contrarian, market_follower
from tests.test_rules import _drift_rule, _table, _template
from tests.test_runner import BREXIT, DEMO, _narrow, _run

from pmx.data.loader import load_dataset
from pmx.engine.runner import replay
from pmx.journal import journal_hash_of_file
from pmx.rng import RngTree
from pmx.rules.rule import Predicate, RuleClaim, make_rule
from pmx.rules.tester import RuleLedger, RuleTester, rolling_pair
from pmx.types import MS_PER_HOUR


def test_population_identity_covers_members_genomes_and_canonical_order(tmp_path: Path) -> None:
    dataset = _narrow(load_dataset(DEMO), BREXIT)
    alone = _run(dataset, tmp_path, roster=[market_follower()])
    original_bytes = alone.journal_path.read_bytes()
    paired = _run(dataset, tmp_path, roster=[market_follower(), contrarian()])
    assert alone.run_id != paired.run_id
    assert alone.journal_path.read_bytes() == original_bytes, "another population must not overwrite this run"

    changed = market_follower()
    changed.genome = StubGenome(family="follower", genes=(("edge_min_bp", 15),))
    mutant = _run(dataset, tmp_path, roster=[changed])
    assert mutant.run_id != alone.run_id, "same agent name with a different genome is another experiment"

    reordered = _run(dataset, tmp_path / "repeat", roster=[contrarian(), market_follower()])
    assert paired.run_id == reordered.run_id
    assert paired.journal_path.read_bytes() == reordered.journal_path.read_bytes()
    assert replay(paired.run_dir).to_dict() == paired.projection.to_dict()
    assert journal_hash_of_file(paired.journal_path) == paired.journal_hash


def test_live_rule_record_waits_for_resolution_and_ignores_future_outcome(tmp_path: Path) -> None:
    table = _table()
    pair = rolling_pair(table, 4)
    original = RuleTester(table, rng=RngTree(5), ledger=RuleLedger(tmp_path / "promotion", table.dataset_hash))
    promoted = original.run_family(
        [_drift_rule(pair.registered_at_ms)], template=_template(), pair=pair, n_candidates=1
    ).promotions[0]
    market = table.markets[0]
    trigger = market.bars[0].t_ms
    bias = make_rule(
        author_kind="miner", author_id="miner", born_at_ms=0,
        scope=promoted.rule.scope,
        condition=[Predicate(feature="last_price_bp", op="gt", value=0)],
        claim=RuleClaim(kind="bias", direction=1, magnitude_bp=100, factor_ppm=0),
        horizon_bars=0,
    )
    promotion = replace(promoted, rule=bias, visible_from_ms=trigger)
    first = replace(table, markets=(market,))
    changed = replace(
        first, markets=(replace(market, meta=replace(market.meta, resolution=1 - market.meta.resolution)),)
    )
    records = []
    for index, source in enumerate((first, changed)):
        tester = RuleTester(source, rng=RngTree(9), ledger=RuleLedger(tmp_path / str(index), table.dataset_hash))
        records.append(tester.live_record(promotion, pair, at_ms=trigger + 1))
    assert records[0] == records[1], "changing only a future resolution cannot change the past record"
    assert records[0].live_support == 0
    tester = RuleTester(first, rng=RngTree(9), ledger=RuleLedger(tmp_path / "ready", table.dataset_hash))
    before = tester.live_record(promotion, pair, at_ms=market.meta.resolved_at_ms)
    ready = tester.live_record(promotion, pair, at_ms=market.meta.resolved_at_ms + MS_PER_HOUR)
    assert before.live_support == 0, "the settlement bar is not yet visible to its observation"
    assert ready.live_support == len(market.bars), "resolved evidence must become usable, not disappear"


def test_live_drift_waits_until_its_target_bar_has_completed(tmp_path: Path) -> None:
    table = _table()
    pair = rolling_pair(table, 4)
    tester = RuleTester(table, rng=RngTree(5), ledger=RuleLedger(tmp_path / "promotion", table.dataset_hash))
    promoted = tester.run_family(
        [_drift_rule(pair.registered_at_ms)], template=_template(), pair=pair, n_candidates=1
    ).promotions[0]
    market = table.markets[0]
    trigger = market.bars[0].t_ms
    rule = make_rule(
        author_kind="miner", author_id="miner", born_at_ms=0,
        scope=promoted.rule.scope,
        condition=[Predicate(feature="last_price_bp", op="gt", value=0)],
        claim=RuleClaim(kind="drift", direction=1, magnitude_bp=100, factor_ppm=0),
        horizon_bars=1,
    )
    promotion = replace(promoted, rule=rule, visible_from_ms=trigger)
    single = replace(table, markets=(market,))
    tester = RuleTester(single, rng=RngTree(9), ledger=RuleLedger(tmp_path / "live", table.dataset_hash))
    target_close = market.bars[1].t_ms + MS_PER_HOUR
    before = tester.live_record(promotion, pair, at_ms=target_close - 1)
    ready = tester.live_record(promotion, pair, at_ms=target_close)
    assert before.live_support == 0
    assert ready.live_support == 1
    assert ready.live_interval.point == market.bars[1].close_bp - market.bars[0].close_bp
