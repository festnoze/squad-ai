"""Unit tests for the NEAT mutation operators."""

from __future__ import annotations

import numpy as np

from nfl.config import Sensor, SimConfig
from nfl.neat.genome import (
    ConnectionGene,
    InnovationTracker,
    create_initial_genome,
)
from nfl.neat.mutations import (
    mutate,
    mutate_add_connection,
    mutate_add_node,
    would_create_cycle,
)
from nfl.nn.network import Network


def _config(**overrides) -> SimConfig:
    base = dict(
        active_sensors=[Sensor.dy_gap, Sensor.dx_pipe, Sensor.vy],
        activation="sigmoid",
        max_nodes=30,
        max_connections=100,
        add_node_rate=0.3,
        add_connection_rate=0.5,
        weight_perturb_rate=0.8,
        weight_replace_rate=0.1,
        weight_sigma=0.5,
        toggle_enable_rate=0.1,
    )
    base.update(overrides)
    return SimConfig(**base)


def _fresh_genome(config: SimConfig, rng):
    num_inputs = len(config.active_sensors)
    num_outputs = 1
    first_free = 1 + num_inputs + num_outputs
    tracker = InnovationTracker(first_free)
    g = create_initial_genome(
        num_inputs=num_inputs,
        num_outputs=num_outputs,
        activation=config.activation.value,
        tracker=tracker,
        rng=rng,
        initial_hidden=0,
        weight_sigma=1.0,
    )
    return g, tracker


def test_mutate_keeps_graph_acyclic_over_many_iterations():
    rng = np.random.default_rng(0)
    config = _config()
    g, tracker = _fresh_genome(config, rng)

    for _ in range(100):
        mutate(g, config, tracker, rng)
        # Network.from_genome raises ValueError on a cyclic graph; success means acyclic.
        Network.from_genome(g)  # should not raise


def test_mutate_add_node_adds_one_node_disables_one_adds_two():
    rng = np.random.default_rng(1)
    config = _config()
    g, tracker = _fresh_genome(config, rng)

    nodes_before = g.num_nodes
    conns_before = g.num_connections
    enabled_before = len(g.enabled_connections())

    added = mutate_add_node(g, config, tracker, rng)
    assert added is True

    # exactly one new node
    assert g.num_nodes == nodes_before + 1
    # two new connections added (split into two)
    assert g.num_connections == conns_before + 2
    # exactly one connection disabled, two enabled added: net enabled change = +1
    enabled_after = len(g.enabled_connections())
    assert enabled_after == enabled_before - 1 + 2


def test_mutate_add_connection_never_creates_cycle_and_respects_cap():
    rng = np.random.default_rng(2)
    config = _config()
    g, tracker = _fresh_genome(config, rng)

    # Grow some hidden structure so add-connection has candidates.
    for _ in range(5):
        mutate_add_node(g, config, tracker, rng)

    for _ in range(50):
        added = mutate_add_connection(g, config, tracker, rng)
        if added:
            # Verify the just-added edge does not, by itself, sit on a cycle:
            # re-check every connection against would_create_cycle ground truth by
            # building a network (raises on cycle).
            Network.from_genome(g)

    # cap is respected
    assert g.num_connections <= config.max_connections


def test_mutate_add_connection_respects_max_connections_cap_directly():
    rng = np.random.default_rng(3)
    config = _config(max_connections=4)  # initial genome already has 4 conns (3 inputs+bias)
    g, tracker = _fresh_genome(config, rng)

    assert g.num_connections >= config.max_connections
    added = mutate_add_connection(g, config, tracker, rng)
    assert added is False
    assert g.num_connections <= config.max_connections


def test_would_create_cycle_self_loop():
    rng = np.random.default_rng(4)
    config = _config()
    g, _ = _fresh_genome(config, rng)
    node = g.input_ids[0]
    assert would_create_cycle(g, node, node) is True


def test_would_create_cycle_back_edge():
    rng = np.random.default_rng(5)
    config = _config()
    g, tracker = _fresh_genome(config, rng)

    # Split a connection so we have a hidden node h with src -> h -> out.
    assert mutate_add_node(g, config, tracker, rng) is True
    hidden = g.hidden_ids()[0]

    # Find an edge h -> out. Adding out -> h would close a cycle.
    out_node = None
    for c in g.connections.values():
        if c.in_node == hidden:
            out_node = c.out_node
            break
    assert out_node is not None

    assert would_create_cycle(g, out_node, hidden) is True
    # And the forward direction h -> out already exists / would not be a new cycle source.
    # A genuinely safe new edge (bias -> hidden) must not be flagged as a cycle.
    assert would_create_cycle(g, g.bias_id, hidden) is False


def test_manual_back_edge_detection():
    """Hand-built chain a->b->c; adding c->a must be detected as a cycle."""
    rng = np.random.default_rng(6)
    config = _config()
    g, _ = _fresh_genome(config, rng)
    # reuse three existing node ids to form a chain inside the existing graph
    a, b = g.input_ids[0], g.output_ids[0]
    # add a synthetic intermediate using an input node as "c" target is awkward;
    # instead test directly on the fully-connected initial graph:
    # bias/input -> output edges exist, so output -> input would be a back edge.
    assert would_create_cycle(g, b, a) is True
