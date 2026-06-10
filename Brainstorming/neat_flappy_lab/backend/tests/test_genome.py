"""Unit tests for the genome representation and innovation tracking."""

from __future__ import annotations

import numpy as np

from nfl.neat.genome import (
    InnovationTracker,
    NodeType,
    create_initial_genome,
)


def _build_genome(num_inputs: int = 3, num_outputs: int = 1, initial_hidden: int = 0):
    rng = np.random.default_rng(0)
    first_free = 1 + num_inputs + num_outputs
    tracker = InnovationTracker(first_free)
    g = create_initial_genome(
        num_inputs=num_inputs,
        num_outputs=num_outputs,
        activation="sigmoid",
        tracker=tracker,
        rng=rng,
        initial_hidden=initial_hidden,
        weight_sigma=1.0,
    )
    return g, tracker


def test_create_initial_genome_structure():
    num_inputs, num_outputs = 3, 1
    g, _ = _build_genome(num_inputs, num_outputs)

    # bias is id 0
    assert g.bias_id == 0
    assert g.nodes[0].type == NodeType.BIAS
    assert g.nodes[0].activation == "identity"

    # N input nodes, ids 1..num_inputs
    assert g.input_ids == [1, 2, 3]
    for nid in g.input_ids:
        assert g.nodes[nid].type == NodeType.INPUT
        assert g.nodes[nid].activation == "identity"

    # M output nodes follow the inputs
    assert g.output_ids == [4]
    for nid in g.output_ids:
        assert g.nodes[nid].type == NodeType.OUTPUT
        assert g.nodes[nid].activation == "sigmoid"

    # total node count = bias + inputs + outputs
    assert g.num_nodes == 1 + num_inputs + num_outputs


def test_create_initial_genome_fully_connected():
    num_inputs, num_outputs = 3, 1
    g, _ = _build_genome(num_inputs, num_outputs)

    inputs_incl_bias = num_inputs + 1
    expected = inputs_incl_bias * num_outputs

    enabled = g.enabled_connections()
    assert len(enabled) == expected
    assert g.num_connections == expected

    # every (bias|input) -> output edge present, all enabled
    sources = g.input_and_bias_ids()
    for a in sources:
        for b in g.output_ids:
            conn = g.connection_between(a, b)
            assert conn is not None
            assert conn.enabled is True


def test_genome_copy_is_deep():
    g, _ = _build_genome()
    clone = g.copy()

    inv = next(iter(g.connections))
    original_weight = g.connections[inv].weight

    # mutate the clone
    clone.connections[inv].weight = original_weight + 100.0

    # original unchanged
    assert g.connections[inv].weight == original_weight
    # node dicts are distinct objects
    assert g.nodes is not clone.nodes
    assert g.connections is not clone.connections


def test_to_dict_round_trips_structure():
    g, _ = _build_genome()
    d = g.to_dict()

    assert len(d["nodes"]) == g.num_nodes
    assert len(d["connections"]) == g.num_connections
    assert d["inputs"] == g.input_ids
    assert d["outputs"] == g.output_ids
    assert d["bias"] == g.bias_id

    node_ids = {n["id"] for n in d["nodes"]}
    assert node_ids == set(g.nodes.keys())
    inno_set = {c["innovation"] for c in d["connections"]}
    assert inno_set == set(g.connections.keys())


def test_innovation_tracker_connection_innovation_is_stable():
    tracker = InnovationTracker(first_free_node_id=10)

    first = tracker.connection_innovation(1, 5)
    second = tracker.connection_innovation(1, 5)
    assert first == second  # same edge -> same number

    other = tracker.connection_innovation(2, 5)
    assert other != first  # different edge -> different number

    # asking again still stable
    assert tracker.connection_innovation(2, 5) == other


def test_innovation_tracker_node_split_caches():
    tracker = InnovationTracker(first_free_node_id=10)

    nid_a = tracker.node_split(split_connection_innovation=3)
    nid_b = tracker.node_split(split_connection_innovation=3)
    assert nid_a == nid_b  # same split -> cached id

    nid_c = tracker.node_split(split_connection_innovation=4)
    assert nid_c != nid_a  # different split -> fresh id
