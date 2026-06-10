"""Genome representation — the shared contract for the whole engine.

A genome is a direct encoding of a neural network: a set of *node genes* and a
set of *connection genes*, in the NEAT style. Connections are keyed by their
**innovation number** so two genomes can be aligned gene-by-gene during
crossover and compared for speciation distance.

Conventions every other module relies on:

* Node ids are stable integers. The **bias** node always has id ``0``. Input
  nodes take ids ``1 .. num_inputs``. Output nodes follow. Hidden nodes get
  fresh ids from the :class:`InnovationTracker`.
* ``Genome.connections`` is a ``dict[int, ConnectionGene]`` keyed by innovation.
* Input and bias nodes use the ``"identity"`` activation; hidden/output nodes
  carry the activation chosen in the config.
* A genome is pure data + structural helpers. Evaluation lives in ``nn`` and
  variation lives in ``neat.mutations`` / ``neat.crossover``.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum

import numpy as np


class NodeType(str, Enum):
    BIAS = "bias"
    INPUT = "input"
    OUTPUT = "output"
    HIDDEN = "hidden"


@dataclass
class NodeGene:
    id: int
    type: NodeType
    activation: str = "identity"  # "identity" for bias/input; sigmoid/tanh/relu otherwise

    def copy(self) -> "NodeGene":
        return replace(self)


@dataclass
class ConnectionGene:
    in_node: int
    out_node: int
    weight: float
    enabled: bool
    innovation: int

    def copy(self) -> "ConnectionGene":
        return replace(self)


@dataclass
class Genome:
    """A network encoding. ``nodes`` keyed by node id, ``connections`` by innovation."""

    nodes: dict[int, NodeGene] = field(default_factory=dict)
    connections: dict[int, ConnectionGene] = field(default_factory=dict)
    input_ids: list[int] = field(default_factory=list)   # excludes bias
    output_ids: list[int] = field(default_factory=list)
    bias_id: int = 0

    # Filled in during evaluation; not part of the genetic encoding.
    fitness: float = 0.0
    adjusted_fitness: float = 0.0

    # Training camp this genome belongs to. Only meaningful in confrontation
    # mode ("neat" vs "gd"); everywhere else it stays at the default.
    camp: str = "neat"

    # --- structural helpers ------------------------------------------------------
    def copy(self) -> "Genome":
        """Deep copy of the genetic material (fitness reset to 0)."""
        return Genome(
            nodes={nid: n.copy() for nid, n in self.nodes.items()},
            connections={inv: c.copy() for inv, c in self.connections.items()},
            input_ids=list(self.input_ids),
            output_ids=list(self.output_ids),
            bias_id=self.bias_id,
            camp=self.camp,
        )

    def add_node(self, node: NodeGene) -> None:
        self.nodes[node.id] = node

    def add_connection(self, conn: ConnectionGene) -> None:
        self.connections[conn.innovation] = conn

    def enabled_connections(self) -> list[ConnectionGene]:
        return [c for c in self.connections.values() if c.enabled]

    def connection_between(self, in_node: int, out_node: int) -> ConnectionGene | None:
        for c in self.connections.values():
            if c.in_node == in_node and c.out_node == out_node:
                return c
        return None

    def hidden_ids(self) -> list[int]:
        return [nid for nid, n in self.nodes.items() if n.type == NodeType.HIDDEN]

    def input_and_bias_ids(self) -> list[int]:
        return [self.bias_id, *self.input_ids]

    @property
    def num_nodes(self) -> int:
        return len(self.nodes)

    @property
    def num_connections(self) -> int:
        return len(self.connections)

    @property
    def complexity(self) -> int:
        """Number of enabled connections — the headline 'size' metric."""
        return sum(1 for c in self.connections.values() if c.enabled)

    def max_innovation(self) -> int:
        return max(self.connections, default=-1)

    # --- serialization (for snapshots / WebSocket) -------------------------------
    def to_dict(self) -> dict:
        return {
            "nodes": [
                {"id": n.id, "type": n.type.value, "activation": n.activation}
                for n in self.nodes.values()
            ],
            "connections": [
                {
                    "in": c.in_node,
                    "out": c.out_node,
                    "weight": c.weight,
                    "enabled": c.enabled,
                    "innovation": c.innovation,
                }
                for c in self.connections.values()
            ],
            "inputs": list(self.input_ids),
            "outputs": list(self.output_ids),
            "bias": self.bias_id,
            "fitness": self.fitness,
            "camp": self.camp,
        }


class InnovationTracker:
    """Hands out globally consistent innovation numbers and split node ids.

    Within a generation, the *same* structural mutation (same ``(in, out)`` edge,
    or the same connection being split) must receive the *same* innovation number
    / node id across all genomes — otherwise crossover alignment breaks. This
    tracker memoizes those decisions.
    """

    def __init__(self, first_free_node_id: int) -> None:
        self._next_innovation = 0
        self._next_node_id = first_free_node_id
        self._conn_innovations: dict[tuple[int, int], int] = {}
        self._node_splits: dict[int, int] = {}  # split-connection innovation -> new node id

    def connection_innovation(self, in_node: int, out_node: int) -> int:
        key = (in_node, out_node)
        if key not in self._conn_innovations:
            self._conn_innovations[key] = self._next_innovation
            self._next_innovation += 1
        return self._conn_innovations[key]

    def new_node_id(self) -> int:
        nid = self._next_node_id
        self._next_node_id += 1
        return nid

    def node_split(self, split_connection_innovation: int) -> int:
        """Return the (cached) hidden-node id created by splitting a connection."""
        if split_connection_innovation not in self._node_splits:
            self._node_splits[split_connection_innovation] = self.new_node_id()
        return self._node_splits[split_connection_innovation]


def create_initial_genome(
    *,
    num_inputs: int,
    num_outputs: int,
    activation: str,
    tracker: InnovationTracker,
    rng: np.random.Generator,
    initial_hidden: int = 0,
    weight_sigma: float = 1.0,
) -> Genome:
    """Build a starting genome: bias + inputs fully connected to outputs.

    Node ids: bias=0, inputs=1..num_inputs, outputs=next, optional hidden after.
    With ``initial_hidden > 0``, hidden nodes are inserted fully connected between
    the input layer and the outputs.
    """
    g = Genome()
    g.bias_id = 0
    g.add_node(NodeGene(id=0, type=NodeType.BIAS, activation="identity"))

    g.input_ids = list(range(1, num_inputs + 1))
    for nid in g.input_ids:
        g.add_node(NodeGene(id=nid, type=NodeType.INPUT, activation="identity"))

    g.output_ids = list(range(num_inputs + 1, num_inputs + 1 + num_outputs))
    for nid in g.output_ids:
        g.add_node(NodeGene(id=nid, type=NodeType.OUTPUT, activation=activation))

    hidden_ids: list[int] = []
    for _ in range(initial_hidden):
        hid = tracker.new_node_id()
        g.add_node(NodeGene(id=hid, type=NodeType.HIDDEN, activation=activation))
        hidden_ids.append(hid)

    sources = g.input_and_bias_ids()
    targets = hidden_ids if hidden_ids else g.output_ids

    def connect(a: int, b: int) -> None:
        inv = tracker.connection_innovation(a, b)
        g.add_connection(
            ConnectionGene(
                in_node=a,
                out_node=b,
                weight=float(rng.normal(0.0, weight_sigma)),
                enabled=True,
                innovation=inv,
            )
        )

    for a in sources:
        for b in targets:
            connect(a, b)
    # If we inserted a hidden layer, wire it to the outputs too.
    if hidden_ids:
        for h in hidden_ids:
            for o in g.output_ids:
                connect(h, o)

    return g
