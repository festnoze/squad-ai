"""Unit tests for NEAT crossover."""

from __future__ import annotations

import copy

import numpy as np

from nfl.config import Sensor, SimConfig
from nfl.neat.crossover import crossover
from nfl.neat.genome import InnovationTracker, create_initial_genome
from nfl.neat.mutations import mutate_add_connection, mutate_add_node


def _config(**overrides) -> SimConfig:
    base = dict(
        active_sensors=[Sensor.dy_gap, Sensor.dx_pipe, Sensor.vy],
        activation="sigmoid",
        max_nodes=30,
        max_connections=100,
    )
    base.update(overrides)
    return SimConfig(**base)


def _two_parents(rng):
    config = _config()
    num_inputs = len(config.active_sensors)
    first_free = 1 + num_inputs + 1
    tracker = InnovationTracker(first_free)

    def make():
        return create_initial_genome(
            num_inputs=num_inputs,
            num_outputs=1,
            activation="sigmoid",
            tracker=tracker,
            rng=rng,
            initial_hidden=0,
            weight_sigma=1.0,
        )

    a = make()
    b = make()

    # Diverge their topologies so disjoint/excess genes exist.
    for _ in range(3):
        mutate_add_node(a, config, tracker, rng)
        mutate_add_connection(a, config, tracker, rng)
    for _ in range(2):
        mutate_add_node(b, config, tracker, rng)
        mutate_add_connection(b, config, tracker, rng)

    return a, b, config


def test_child_innovations_subset_of_parents_and_endpoints_exist():
    rng = np.random.default_rng(0)
    a, b, _ = _two_parents(rng)
    a.fitness = 5.0
    b.fitness = 1.0

    child = crossover(a, b, rng)

    parent_innovations = set(a.connections) | set(b.connections)
    assert set(child.connections).issubset(parent_innovations)

    # every connection endpoint must exist as a node in the child
    for conn in child.connections.values():
        assert conn.in_node in child.nodes
        assert conn.out_node in child.nodes


def test_unequal_fitness_disjoint_excess_from_fitter_only():
    rng = np.random.default_rng(1)
    a, b, _ = _two_parents(rng)
    a.fitness = 10.0  # a is strictly fitter
    b.fitness = 0.0

    child = crossover(a, b, rng)

    matching = set(a.connections) & set(b.connections)
    only_in_b = set(b.connections) - set(a.connections)

    for inno in child.connections:
        if inno in matching:
            continue
        # any non-matching gene in the child must come from the fitter parent (a)
        assert inno not in only_in_b
        assert inno in a.connections


def test_crossover_does_not_mutate_parents():
    rng = np.random.default_rng(2)
    a, b, _ = _two_parents(rng)
    a.fitness = 3.0
    b.fitness = 7.0

    a_snapshot = copy.deepcopy(a)
    b_snapshot = copy.deepcopy(b)

    _ = crossover(a, b, rng)

    # connection sets and weights unchanged
    assert set(a.connections) == set(a_snapshot.connections)
    assert set(b.connections) == set(b_snapshot.connections)
    for inno, c in a.connections.items():
        assert c.weight == a_snapshot.connections[inno].weight
        assert c.enabled == a_snapshot.connections[inno].enabled
    for inno, c in b.connections.items():
        assert c.weight == b_snapshot.connections[inno].weight
        assert c.enabled == b_snapshot.connections[inno].enabled
    # node sets unchanged
    assert set(a.nodes) == set(a_snapshot.nodes)
    assert set(b.nodes) == set(b_snapshot.nodes)
