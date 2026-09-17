"""Fixed strategies use completed observations and produce actual bounded engine actions."""

from dataclasses import replace

import pytest
from tests.test_observation import DAY, a_market, one_observation

from pmx.agents.registry import DEFAULT_ROSTER, ScriptedGenome, make_agent
from pmx.types import RunConfig


def test_fixed_roster_baseline_and_opposing_forecasts() -> None:
    market = a_market("demo-alpha", created_day=0, n_bars=6, prices=[2000, 3000, 4000, 5000, 9000, 100])
    obs = one_observation([market], now_ms=4 * DAY)
    actions = {}
    for agent_id, genome in DEFAULT_ROSTER:
        agent = make_agent(agent_id, genome)
        agent.reset(rng=object(), memory=None, config=RunConfig(seed=7))
        agent.observe(obs)
        actions[agent_id] = agent.decide().markets[0]
    assert actions["follower"].prob_ppm == 500_000
    assert actions["follower"].kind == "hold"
    assert actions["trend"].prob_ppm == 650_000
    assert actions["trend"].target_position == 25
    assert actions["revert"].prob_ppm == 387_500
    assert actions["revert"].target_position == -19


@pytest.mark.parametrize("agent_id", ["follower", "trend", "revert"])
def test_future_tape_and_outcome_do_not_change_a_past_action(agent_id: str) -> None:
    market = a_market("demo-alpha", created_day=0, n_bars=6, prices=[2000, 3000, 4000, 5000, 9000, 100])
    changed = replace(
        market,
        resolution=1 - market.resolution,
        bars=(*market.bars[:4], *(replace(bar, close_bp=9999) for bar in market.bars[4:])),
    )
    decisions = []
    for tape in (market, changed):
        agent = make_agent(agent_id)
        agent.observe(one_observation([tape], now_ms=4 * DAY))
        decisions.append(agent.decide())
    assert decisions[0] == decisions[1]


def test_unknown_and_changed_genomes_fail_and_reset_clears_observation() -> None:
    with pytest.raises(ValueError, match="Unknown"):
        make_agent("unknown")
    with pytest.raises(ValueError, match="fixed"):
        make_agent("trend", ScriptedGenome("trend"))
    agent = make_agent("trend")
    agent.observe(one_observation([a_market("demo-alpha")], now_ms=DAY))
    agent.reset(rng=object(), memory=None, config=RunConfig(seed=7))
    with pytest.raises(RuntimeError, match="observation"):
        agent.decide()
