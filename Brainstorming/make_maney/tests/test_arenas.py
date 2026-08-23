import math
import random
import unittest

from moneyrace.agents import Agent
from moneyrace.arenas import AuctionArena, MarketArena, PredictionArena
from moneyrace.genome import Genome


def make_agents(count, rng, wealth=100.0):
    return [Agent(Genome.random(rng), wealth, 0) for _ in range(count)]


class ArenaAccountingTests(unittest.TestCase):
    """Every arena must report exactly the money it created or destroyed.
    This is the guard against arenas silently printing or leaking money."""

    def assert_accounting(self, arena, seed):
        rng = random.Random(seed)
        agents = make_agents(12, rng)
        before = sum(a.wealth for a in agents)
        report = arena.run(agents, rng)
        after = sum(a.wealth for a in agents)
        self.assertAlmostEqual(after - before, report["system_delta"], places=6)
        for agent in agents:
            self.assertTrue(math.isfinite(agent.wealth))
        return agents, report

    def test_auction_accounting(self):
        agents, report = self.assert_accounting(AuctionArena(), seed=11)
        self.assertGreater(report["sales"], 0)
        # An auction can never bankrupt anyone: the winner pays at most its
        # capped bid and always receives the item's positive true value.
        for agent in agents:
            self.assertGreater(agent.wealth, 0.0)

    def test_market_accounting_across_regimes(self):
        for seed in range(20, 26):
            agents, _ = self.assert_accounting(MarketArena(), seed=seed)
            # Losses are capped at the allocated capital (at most half wealth)
            for agent in agents:
                self.assertGreater(agent.wealth, 0.0)

    def test_prediction_accounting_and_no_overdraft(self):
        agents, report = self.assert_accounting(PredictionArena(events=6), seed=31)
        self.assertGreater(report["bets"], 0)
        for agent in agents:
            self.assertGreaterEqual(agent.wealth, 0.0)

    def test_arenas_skip_dead_agents(self):
        rng = random.Random(41)
        agents = make_agents(6, rng)
        agents[0].wealth = 0.0
        for arena in (AuctionArena(), MarketArena(), PredictionArena()):
            arena.run(agents, rng)
        self.assertEqual(agents[0].wealth, 0.0)
        self.assertEqual(agents[0].lifetime_pnl, 0.0)


if __name__ == "__main__":
    unittest.main()
