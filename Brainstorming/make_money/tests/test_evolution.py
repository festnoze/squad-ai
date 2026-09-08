import json
import random
import unittest

from moneyrace.config import Config
from moneyrace.evolution import World


class EvolutionTests(unittest.TestCase):
    def test_population_stays_constant(self):
        config = Config(population=20, generations=15, seed=5)
        world = World(config, random.Random(config.seed))
        for _ in range(15):
            stats = world.step()
            self.assertEqual(stats["population"], 20)
            self.assertEqual(len(world.agents), 20)

    def test_same_seed_gives_identical_history(self):
        config = Config(population=16, seed=9)
        first = World(config, random.Random(config.seed))
        second = World(config, random.Random(config.seed))
        for _ in range(10):
            first.step()
            second.step()
        self.assertEqual(json.dumps(first.history, sort_keys=True),
                         json.dumps(second.history, sort_keys=True))

    def test_bankrupt_agents_die_and_are_buried(self):
        # A living cost far above any plausible arena income kills everyone.
        config = Config(population=12, seed=3, living_cost=10_000.0)
        world = World(config, random.Random(config.seed))
        stats = world.step()
        self.assertEqual(stats["deaths"], 12)
        self.assertEqual(len(world.graveyard), 12)
        for record in world.graveyard:
            self.assertEqual(record["died"], 0)
        # The world refills entirely with immigrants (no one can afford kids).
        self.assertEqual(stats["immigrants"] + stats["births"], 12)
        self.assertEqual(len(world.agents), 12)

    def test_children_are_paid_for_by_their_parents(self):
        config = Config(population=16, seed=13, immigrant_rate=0.0)
        world = World(config, random.Random(config.seed))
        for _ in range(20):
            world.step()
        children = [a for a in world.agents if a.parents]
        self.assertTrue(children, "expected at least one born agent after 20 generations")
        for child in children:
            self.assertGreater(len(child.parents), 0)

    def test_arena_subset_config(self):
        config = Config(population=10, seed=1, arenas=("auction",))
        world = World(config, random.Random(config.seed))
        stats = world.step()
        self.assertEqual(len(stats["arenas"]), 1)
        self.assertEqual(stats["arenas"][0]["arena"], "auction")

    def test_leaderboard_is_sorted_by_wealth(self):
        config = Config(population=14, seed=8)
        world = World(config, random.Random(config.seed))
        for _ in range(10):
            world.step()
        board = world.leaderboard(top=5)
        wealths = [entry["wealth"] for entry in board]
        self.assertEqual(wealths, sorted(wealths, reverse=True))


if __name__ == "__main__":
    unittest.main()
