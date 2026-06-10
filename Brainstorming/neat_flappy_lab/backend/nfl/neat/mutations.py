"""Mutation operators for the NEAT engine.

These functions implement the *variation* half of neuroevolution: they take a
single :class:`~nfl.neat.genome.Genome` and modify it **in place**, drawing all
randomness from a numpy :class:`~numpy.random.Generator` so runs are
reproducible from a seed.

Two families live here:

* **Weight mutations** (:func:`mutate_weights`, :func:`mutate_toggle_enable`)
  tweak existing genes without changing topology.
* **Structural mutations** (:func:`mutate_add_connection`,
  :func:`mutate_add_node`) grow the network. New genes get globally consistent
  innovation numbers / node ids from the shared
  :class:`~nfl.neat.genome.InnovationTracker`.

Hard invariant
--------------
The encoded network must stay **acyclic** (strictly feed-forward). Connections
never point *into* a bias/input node, and :func:`mutate_add_connection` rejects
any edge that would close a cycle (see :func:`would_create_cycle`). Add-node
mutations split an existing edge, which can never introduce a cycle.
"""

from __future__ import annotations

import numpy as np

from .genome import ConnectionGene, Genome, NodeGene, NodeType

# Cap on how many random (src, dst) pairs we sample before giving up on
# add-connection: the network may be fully/near-fully connected.
_MAX_ADD_CONNECTION_TRIES = 32


def mutate_weights(genome: Genome, config, rng: np.random.Generator) -> None:
    """Perturb or replace each connection weight, independently.

    For every connection, with probability ``config.weight_perturb_rate`` add
    Gaussian noise (std ``config.weight_sigma``); otherwise, with probability
    ``config.weight_replace_rate``, draw a fresh weight from ``N(0, 1)``. Each
    connection is decided by its own independent draws.
    """
    for conn in genome.connections.values():
        if rng.random() < config.weight_perturb_rate:
            conn.weight += float(rng.normal(0.0, config.weight_sigma))
        elif rng.random() < config.weight_replace_rate:
            conn.weight = float(rng.normal(0.0, 1.0))


def would_create_cycle(genome: Genome, in_node: int, out_node: int) -> bool:
    """Return ``True`` if adding edge ``in_node -> out_node`` makes a cycle.

    Adding the edge closes a cycle exactly when ``out_node`` can already reach
    ``in_node`` through the existing connections (a self-loop, ``in_node ==
    out_node``, also counts). We walk the graph forward from ``out_node`` over
    *all* connections — enabled and disabled alike — since a disabled gene can be
    re-enabled later and must not become part of a cycle.
    """
    if in_node == out_node:
        return True

    # Forward adjacency over every connection regardless of enabled state.
    visited: set[int] = set()
    stack: list[int] = [out_node]
    while stack:
        current = stack.pop()
        if current == in_node:
            return True
        if current in visited:
            continue
        visited.add(current)
        for conn in genome.connections.values():
            if conn.in_node == current and conn.out_node not in visited:
                stack.append(conn.out_node)
    return False


def mutate_add_connection(genome: Genome, config, tracker, rng: np.random.Generator) -> bool:
    """Add one new enabled connection between two unconnected, valid nodes.

    A candidate edge ``src -> dst`` is valid when:

    * ``src`` is a bias, input or hidden node (never an output),
    * ``dst`` is a hidden or output node (never a bias/input),
    * no connection ``src -> dst`` already exists, and
    * it does not create a cycle (:func:`would_create_cycle`).

    The new weight is drawn from ``N(0, 1)`` and the innovation number comes from
    ``tracker.connection_innovation``. Returns ``True`` on success, ``False`` if
    the complexity cap is hit or no valid pair is found after a bounded number of
    random tries.
    """
    if genome.num_connections >= config.max_connections:
        return False

    # Sources may emit signal: bias, inputs and hidden nodes.
    sources = genome.input_and_bias_ids() + genome.hidden_ids()
    # Destinations may receive signal: hidden nodes and outputs.
    destinations = genome.hidden_ids() + list(genome.output_ids)

    if not sources or not destinations:
        return False

    for _ in range(_MAX_ADD_CONNECTION_TRIES):
        src = int(sources[rng.integers(len(sources))])
        dst = int(destinations[rng.integers(len(destinations))])

        if src == dst:
            continue
        if genome.connection_between(src, dst) is not None:
            continue
        if would_create_cycle(genome, src, dst):
            continue

        innovation = tracker.connection_innovation(src, dst)
        genome.add_connection(
            ConnectionGene(
                in_node=src,
                out_node=dst,
                weight=float(rng.normal(0.0, 1.0)),
                enabled=True,
                innovation=innovation,
            )
        )
        return True

    return False


def mutate_add_node(genome: Genome, config, tracker, rng: np.random.Generator) -> bool:
    """Split a random enabled connection, inserting a new hidden node.

    The chosen connection ``src -> dst`` is disabled and replaced by two new
    connections through a fresh hidden node ``new_id``:

    * ``src -> new_id`` with weight ``1.0`` (preserves the incoming signal), and
    * ``new_id -> dst`` carrying the original connection's weight.

    The hidden-node id is obtained from ``tracker.node_split`` (keyed by the split
    connection's innovation) so the same split yields the same id across genomes
    in a generation. Returns ``False`` if the node cap is reached or there are no
    enabled connections to split, ``True`` otherwise.
    """
    if genome.num_nodes >= config.max_nodes:
        return False

    enabled = genome.enabled_connections()
    if not enabled:
        return False

    conn = enabled[int(rng.integers(len(enabled)))]
    conn.enabled = False

    new_id = tracker.node_split(conn.innovation)
    genome.add_node(
        NodeGene(id=new_id, type=NodeType.HIDDEN, activation=config.activation.value)
    )

    # src -> new_id : weight 1.0 keeps the original signal scale.
    in_innovation = tracker.connection_innovation(conn.in_node, new_id)
    genome.add_connection(
        ConnectionGene(
            in_node=conn.in_node,
            out_node=new_id,
            weight=1.0,
            enabled=True,
            innovation=in_innovation,
        )
    )

    # new_id -> dst : original weight, so behaviour starts ~unchanged.
    out_innovation = tracker.connection_innovation(new_id, conn.out_node)
    genome.add_connection(
        ConnectionGene(
            in_node=new_id,
            out_node=conn.out_node,
            weight=conn.weight,
            enabled=True,
            innovation=out_innovation,
        )
    )

    return True


def mutate_toggle_enable(genome: Genome, config, rng: np.random.Generator) -> None:
    """With probability ``config.toggle_enable_rate``, flip one connection's
    ``enabled`` flag (chosen uniformly at random)."""
    if not genome.connections:
        return
    if rng.random() < config.toggle_enable_rate:
        conns = list(genome.connections.values())
        conn = conns[int(rng.integers(len(conns)))]
        conn.enabled = not conn.enabled


def mutate(genome: Genome, config, tracker, rng: np.random.Generator) -> None:
    """Apply the full mutation pipeline to ``genome`` in place.

    Order matters: structural mutations run first (so the subsequent weight pass
    also touches any freshly created connections), then per-weight mutation, then
    the connection toggle.

    * with prob ``config.add_node_rate`` -> :func:`mutate_add_node`
    * with prob ``config.add_connection_rate`` -> :func:`mutate_add_connection`
    * always -> :func:`mutate_weights`
    * always -> :func:`mutate_toggle_enable`
    """
    if rng.random() < config.add_node_rate:
        mutate_add_node(genome, config, tracker, rng)
    if rng.random() < config.add_connection_rate:
        mutate_add_connection(genome, config, tracker, rng)
    mutate_weights(genome, config, rng)
    mutate_toggle_enable(genome, config, rng)


def enforce_acyclic(genome: Genome) -> None:
    """Repair a genome into a strict DAG by disabling cycle-closing connections.

    Single mutations are cycle-safe (see :func:`would_create_cycle`), but
    **crossover can merge two individually-acyclic parents into a cyclic child**
    (parent A contributes ``X -> Y`` while parent B contributes ``Y -> X``). The
    network builder requires a DAG, so we run an iterative DFS over the enabled
    connections and disable every *back edge* (an edge into a node currently on
    the recursion stack), which is the minimal repair to break all cycles.
    """
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[int, int] = {nid: WHITE for nid in genome.nodes}

    # Successor adjacency over enabled connections only.
    adj: dict[int, list[ConnectionGene]] = {nid: [] for nid in genome.nodes}
    for conn in genome.connections.values():
        if conn.enabled and conn.in_node in adj and conn.out_node in adj:
            adj[conn.in_node].append(conn)

    for root in list(genome.nodes.keys()):
        if color[root] != WHITE:
            continue
        color[root] = GRAY
        stack: list[tuple[int, "Iterator"]] = [(root, iter(adj[root]))]  # type: ignore[name-defined]
        while stack:
            node, it = stack[-1]
            descended = False
            for conn in it:
                if not conn.enabled:
                    continue
                target = conn.out_node
                state = color[target]
                if state == GRAY:
                    # Back edge -> would close a cycle: disable it.
                    conn.enabled = False
                elif state == WHITE:
                    color[target] = GRAY
                    stack.append((target, iter(adj[target])))
                    descended = True
                    break
                # BLACK target: already fully explored, safe cross/forward edge.
            if not descended:
                color[node] = BLACK
                stack.pop()
