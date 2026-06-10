"""Unit tests for speciation, compatibility distance and fitness sharing."""

from __future__ import annotations

import numpy as np

from nfl.config import Sensor, SimConfig
from nfl.neat.genome import InnovationTracker, create_initial_genome
from nfl.neat.mutations import mutate_add_connection, mutate_add_node, mutate_weights
from nfl.neat.speciation import (
    compatibility_distance,
    share_fitness,
    speciate,
)


def _config(**overrides) -> SimConfig:
    base = dict(
        active_sensors=[Sensor.dy_gap, Sensor.dx_pipe, Sensor.vy],
        activation="sigmoid",
        max_nodes=30,
        max_connections=100,
        compat_threshold=3.0,
        c1=1.0,
        c2=1.0,
        c3=0.4,
    )
    base.update(overrides)
    return SimConfig(**base)


def _make(config, tracker, rng):
    return create_initial_genome(
        num_inputs=len(config.active_sensors),
        num_outputs=1,
        activation="sigmoid",
        tracker=tracker,
        rng=rng,
        initial_hidden=0,
        weight_sigma=1.0,
    )


def test_compatibility_distance_identical_is_zero():
    rng = np.random.default_rng(0)
    config = _config()
    tracker = InnovationTracker(1 + len(config.active_sensors) + 1)
    g = _make(config, tracker, rng)
    assert compatibility_distance(g, g, config) == 0.0
    assert compatibility_distance(g, g.copy(), config) == 0.0


def test_compatibility_distance_different_is_positive():
    rng = np.random.default_rng(1)
    config = _config()
    tracker = InnovationTracker(1 + len(config.active_sensors) + 1)
    g1 = _make(config, tracker, rng)
    g2 = g1.copy()

    # Diverge g2 substantially: new topology + perturbed weights.
    for _ in range(4):
        mutate_add_node(g2, config, tracker, rng)
        mutate_add_connection(g2, config, tracker, rng)
    for _ in range(5):
        mutate_weights(g2, config, rng)

    assert compatibility_distance(g1, g2, config) > 0.0


def test_speciate_groups_identical_and_separates_different():
    rng = np.random.default_rng(2)
    # Tight threshold so divergent topology lands in its own species.
    config = _config(compat_threshold=1.0)
    tracker = InnovationTracker(1 + len(config.active_sensors) + 1)

    base = _make(config, tracker, rng)
    identical = [base.copy() for _ in range(3)]

    different = base.copy()
    for _ in range(5):
        mutate_add_node(different, config, tracker, rng)
        mutate_add_connection(different, config, tracker, rng)

    genomes = [*identical, different]
    species, next_id = speciate(genomes, [], config, next_species_id=0)

    assert next_id == len(species)
    # identical genomes share one species; the divergent one is separate.
    assert len(species) == 2
    sizes = sorted(len(s.members) for s in species)
    assert sizes == [1, 3]
    assert sum(len(s.members) for s in species) == len(genomes)


def test_share_fitness_divides_by_species_size():
    rng = np.random.default_rng(3)
    config = _config(compat_threshold=10.0)  # force everything into one species
    tracker = InnovationTracker(1 + len(config.active_sensors) + 1)

    genomes = [_make(config, tracker, rng) for _ in range(4)]
    for i, g in enumerate(genomes):
        g.fitness = float(i + 1)  # 1, 2, 3, 4

    species, _ = speciate(genomes, [], config, next_species_id=0)
    assert len(species) == 1
    n = len(species[0].members)
    assert n == 4

    share_fitness(species)
    for member in species[0].members:
        assert member.adjusted_fitness == member.fitness / n
