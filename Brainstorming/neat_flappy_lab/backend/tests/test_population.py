"""Unit tests for the NEAT Population evolution loop."""

from __future__ import annotations

import numpy as np

from nfl.config import Sensor, SimConfig
from nfl.neat.population import Population


def _config(pop_size: int = 12, **overrides) -> SimConfig:
    base = dict(
        pop_size=pop_size,
        active_sensors=[Sensor.dy_gap, Sensor.dx_pipe, Sensor.vy],
        activation="sigmoid",
        max_nodes=30,
        max_connections=100,
        add_node_rate=0.1,
        add_connection_rate=0.2,
        elitism_per_species=1,
        survival_threshold=0.3,
        compat_threshold=3.0,
    )
    base.update(overrides)
    return SimConfig(**base)


def test_population_creates_pop_size_genomes():
    rng = np.random.default_rng(0)
    config = _config(pop_size=15)
    pop = Population(config, rng)
    assert len(pop.genomes) == 15
    assert pop.generation == 0


def test_evolve_preserves_pop_size_and_increments_generation():
    rng = np.random.default_rng(1)
    config = _config(pop_size=12)
    pop = Population(config, rng)

    for i, g in enumerate(pop.genomes):
        g.fitness = float(rng.uniform(0.1, 10.0))

    gen_before = pop.generation
    pop.evolve()

    assert len(pop.genomes) == config.pop_size
    assert pop.generation == gen_before + 1


def test_evolve_preserves_champion_complexity():
    rng = np.random.default_rng(2)
    config = _config(pop_size=20)
    pop = Population(config, rng)

    # Assign random fitness; make one genome a clear champion with a distinct,
    # larger complexity by growing its structure.
    for g in pop.genomes:
        g.fitness = float(rng.uniform(0.1, 5.0))

    # Grow the champion so its complexity is identifiable.
    from nfl.neat.mutations import mutate_add_node, mutate_add_connection

    champ = pop.genomes[0]
    for _ in range(4):
        mutate_add_node(champ, config, pop.tracker, rng)
        mutate_add_connection(champ, config, pop.tracker, rng)
    champ.fitness = 1000.0  # clearly the best
    champ_complexity = champ.complexity
    champ_nodes = champ.num_nodes

    # sanity: champion is the max-fitness genome
    assert pop.best_genome().fitness == 1000.0

    pop.evolve()

    # The champion (max fitness) must survive unchanged as an elite/global champion:
    # at least one genome in the new generation matches its complexity and node count.
    preserved = any(
        g.complexity == champ_complexity and g.num_nodes == champ_nodes
        for g in pop.genomes
    )
    assert preserved
