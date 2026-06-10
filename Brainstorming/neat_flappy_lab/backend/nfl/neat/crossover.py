"""NEAT crossover — recombine two parent genomes into a child.

Crossover in NEAT aligns the two parents gene-by-gene using **innovation
numbers** on their connection genes:

* **Matching** genes (the same innovation appears in both parents) are inherited
  from a randomly chosen parent. If the gene is disabled in *either* parent, the
  child tends to keep it disabled (with probability 0.75).
* **Disjoint / excess** genes (an innovation present in only one parent) are
  inherited from the **fitter** parent. When the parents are exactly equally fit,
  the historical NEAT behaviour is to take the union of both parents' disjoint /
  excess genes.

Node genes are then reconstructed: every node referenced by an inherited
connection is copied (preferring the fitter parent's copy), and the structural
nodes (bias / inputs / outputs) of the fitter parent are always carried over.

Parents are never mutated — every gene is ``.copy()``-ed before it lands in the
child.
"""

from __future__ import annotations

import numpy as np

from .genome import ConnectionGene, Genome, NodeGene

# Probability that a matching gene which is disabled in either parent stays
# disabled in the child. This is the classic NEAT value.
_DISABLE_INHERIT_PROB = 0.75


def _ensure_node(
    child: Genome,
    node_id: int,
    fitter: Genome,
    other: Genome,
) -> None:
    """Make sure ``node_id`` exists in ``child.nodes``.

    Pulls the :class:`NodeGene` from whichever parent has it, preferring the
    fitter parent, and stores a fresh copy so parents are never aliased.
    """
    if node_id in child.nodes:
        return
    source: NodeGene | None = fitter.nodes.get(node_id)
    if source is None:
        source = other.nodes.get(node_id)
    if source is not None:
        child.nodes[node_id] = source.copy()


def crossover(
    parent_a: Genome,
    parent_b: Genome,
    rng: np.random.Generator,
    a_is_fitter: bool | None = None,
) -> Genome:
    """Produce a child genome by recombining ``parent_a`` and ``parent_b``.

    Args:
        parent_a: First parent genome.
        parent_b: Second parent genome.
        rng: A NumPy random generator used for all stochastic choices.
        a_is_fitter: Optional override for which parent is fitter. When ``None``
            the parents' ``fitness`` attributes are compared, with ``parent_a``
            considered fitter on a tie (``a.fitness >= b.fitness``).

    Returns:
        A new :class:`Genome` with ``fitness`` reset to ``0.0``. Neither parent
        is mutated.
    """
    # --- decide which parent is fitter and whether the match is a tie ----------
    if a_is_fitter is None:
        a_is_fitter = parent_a.fitness >= parent_b.fitness
        equal_fitness = parent_a.fitness == parent_b.fitness
    else:
        # When the caller dictates the fitter parent we treat it as a strict
        # ordering: disjoint/excess genes come only from the chosen parent.
        equal_fitness = False

    fitter = parent_a if a_is_fitter else parent_b
    other = parent_b if a_is_fitter else parent_a

    child = Genome(
        input_ids=list(fitter.input_ids),
        output_ids=list(fitter.output_ids),
        bias_id=fitter.bias_id,
    )

    a_conns = parent_a.connections
    b_conns = parent_b.connections
    all_innovations = set(a_conns) | set(b_conns)

    # --- inherit connection genes ---------------------------------------------
    for innovation in all_innovations:
        gene_a = a_conns.get(innovation)
        gene_b = b_conns.get(innovation)

        if gene_a is not None and gene_b is not None:
            # Matching gene: pick a parent at random.
            chosen = gene_a if rng.random() < 0.5 else gene_b
            child_gene = chosen.copy()
            # If disabled in either parent, probably keep it disabled.
            if not gene_a.enabled or not gene_b.enabled:
                child_gene.enabled = rng.random() >= _DISABLE_INHERIT_PROB
        else:
            # Disjoint / excess gene: present in exactly one parent.
            present_in_fitter = (
                gene_a if fitter is parent_a else gene_b
            )
            if equal_fitness:
                # Equal fitness: take the union (the single gene that exists).
                source_gene = gene_a if gene_a is not None else gene_b
            else:
                # Strictly fitter parent wins; skip genes only in the other one.
                if present_in_fitter is None:
                    continue
                source_gene = present_in_fitter
            child_gene = source_gene.copy()

        child.connections[innovation] = child_gene

    # --- reconstruct the node set ---------------------------------------------
    # Always carry over the fitter parent's structural nodes (bias/in/out).
    for node_id in (fitter.bias_id, *fitter.input_ids, *fitter.output_ids):
        _ensure_node(child, node_id, fitter, other)

    # Every endpoint referenced by an inherited connection must exist.
    for conn in child.connections.values():
        _ensure_node(child, conn.in_node, fitter, other)
        _ensure_node(child, conn.out_node, fitter, other)

    child.fitness = 0.0
    return child
