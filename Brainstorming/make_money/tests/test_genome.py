import random
import unittest

from moneyrace.genome import GENE_NAMES, Genome


class GenomeTests(unittest.TestCase):
    def test_random_genome_in_bounds(self):
        rng = random.Random(1)
        genome = Genome.random(rng)
        self.assertEqual(set(genome.as_dict()), set(GENE_NAMES))
        for value in genome.as_dict().values():
            self.assertGreaterEqual(value, 0.0)
            self.assertLessEqual(value, 1.0)

    def test_mutation_stays_in_bounds_under_extreme_settings(self):
        rng = random.Random(2)
        genome = Genome.random(rng)
        for _ in range(200):
            genome = genome.mutated(rng, rate=1.0, sigma=5.0)
            for value in genome.as_dict().values():
                self.assertGreaterEqual(value, 0.0)
                self.assertLessEqual(value, 1.0)

    def test_crossover_genes_come_from_a_parent(self):
        rng = random.Random(3)
        first, second = Genome.random(rng), Genome.random(rng)
        child = Genome.crossover(first, second, rng)
        for name in GENE_NAMES:
            self.assertIn(child[name], (first[name], second[name]))

    def test_seeded_determinism(self):
        one = Genome.random(random.Random(7)).as_dict()
        two = Genome.random(random.Random(7)).as_dict()
        self.assertEqual(one, two)


if __name__ == "__main__":
    unittest.main()
