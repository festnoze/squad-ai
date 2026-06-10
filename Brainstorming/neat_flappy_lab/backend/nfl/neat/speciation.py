"""Speciation — grouping genomes by topological/weight compatibility.

NEAT protects structural innovation by partitioning the population into
*species*. Two genomes belong together when their **compatibility distance**
(:func:`compatibility_distance`) falls below ``config.compat_threshold``.

The pipeline each generation is:

1. :func:`speciate` — assign every genome to a species (reusing last
   generation's representatives where possible).
2. :func:`share_fitness` — apply explicit fitness sharing so crowded species
   don't dominate reproduction.
3. :func:`adjust_compat_threshold` — optionally nudge the threshold to steer the
   number of species toward ``config.target_species``.

A :class:`Species` carries its representative (used for the next generation's
distance checks), its current members, and book-keeping for stagnation
(``best_fitness`` / ``staleness``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import inf

import numpy as np

from .genome import Genome


def compatibility_distance(g1: Genome, g2: Genome, config) -> float:
    """Standard NEAT compatibility distance between two genomes.

    ``delta = c1*E/N + c2*D/N + c3*W_bar`` where:

    * ``E`` — number of *excess* genes (innovations beyond the larger innovation
      number present in the other genome).
    * ``D`` — number of *disjoint* genes (non-matching genes that fall within the
      overlapping innovation range).
    * ``W_bar`` — average absolute weight difference over *matching* genes
      (genes sharing an innovation number). ``0`` when nothing matches.
    * ``N`` — gene count of the larger genome, but ``1`` when both genomes have
      fewer than 20 genes (the usual NEAT normalization convention).

    Genes are aligned by innovation number via the ``connections`` dicts.
    """
    conns1 = g1.connections
    conns2 = g2.connections

    innovations1 = set(conns1)
    innovations2 = set(conns2)

    # No connections at all on either side → identical (distance 0).
    if not innovations1 and not innovations2:
        return 0.0

    max_inno1 = max(innovations1) if innovations1 else -1
    max_inno2 = max(innovations2) if innovations2 else -1

    matching = innovations1 & innovations2

    # Average weight difference over matching genes.
    if matching:
        weight_diff = sum(
            abs(conns1[inno].weight - conns2[inno].weight) for inno in matching
        )
        w_bar = weight_diff / len(matching)
    else:
        w_bar = 0.0

    # The boundary between excess and disjoint is the smaller of the two maxima:
    # any non-matching gene beyond it is excess, anything at/below it is disjoint.
    crossover_point = min(max_inno1, max_inno2)

    excess = 0
    disjoint = 0
    for inno in innovations1 ^ innovations2:  # symmetric difference = non-matching
        if inno > crossover_point:
            excess += 1
        else:
            disjoint += 1

    n_genes = max(len(conns1), len(conns2))
    if n_genes < 20:
        n = 1
    else:
        n = max(n_genes, 1)

    return config.c1 * excess / n + config.c2 * disjoint / n + config.c3 * w_bar


@dataclass
class Species:
    """A cluster of compatible genomes.

    ``representative`` anchors the species across generations: the next
    generation's genomes are compared against it. ``best_fitness`` /
    ``staleness`` support stagnation detection elsewhere in the engine.
    """

    id: int
    representative: Genome
    members: list[Genome] = field(default_factory=list)
    best_fitness: float = -inf
    staleness: int = 0

    def add(self, genome: Genome) -> None:
        """Append ``genome`` to this species' members."""
        self.members.append(genome)


def speciate(
    genomes: list[Genome],
    species: list[Species],
    config,
    next_species_id: int,
) -> tuple[list[Species], int]:
    """Partition ``genomes`` into species, reusing existing representatives.

    Each existing species keeps its representative but has its member list
    cleared. Every genome is assigned to the **first** existing species whose
    representative is within ``config.compat_threshold``; if none matches, a new
    species is created (id ``next_species_id``, which is then incremented) with
    that genome as its representative.

    Species that end up with no members are dropped. Returns the updated species
    list and the new ``next_species_id``.
    """
    # Keep representatives, reset membership for this generation.
    for s in species:
        s.members = []

    for genome in genomes:
        placed = False
        for s in species:
            if compatibility_distance(genome, s.representative, config) < config.compat_threshold:
                s.add(genome)
                placed = True
                break
        if not placed:
            new_species = Species(id=next_species_id, representative=genome)
            new_species.add(genome)
            species.append(new_species)
            next_species_id += 1

    # Drop species that attracted no members this generation.
    surviving = [s for s in species if s.members]
    return surviving, next_species_id


def share_fitness(species: list[Species]) -> None:
    """Apply explicit fitness sharing in place.

    Within each species every member's ``adjusted_fitness`` becomes its raw
    ``fitness`` divided by the species size, so larger species are penalized and
    diversity is preserved. Empty species are skipped.
    """
    for s in species:
        n = len(s.members)
        if n == 0:
            continue
        for member in s.members:
            member.adjusted_fitness = member.fitness / n


def adjust_compat_threshold(config, num_species: int) -> None:
    """Nudge ``config.compat_threshold`` toward hitting ``target_species``.

    When ``config.target_species > 0``, raise the threshold by ``0.3`` if there
    are currently too many species (merging them) or lower it by ``0.3`` if there
    are too few (splitting them). The threshold is clamped to ``>= 0.1``. No-op
    when ``target_species <= 0``. Mutates ``config`` in place.
    """
    if config.target_species <= 0:
        return

    step = 0.3
    if num_species > config.target_species:
        config.compat_threshold += step
    elif num_species < config.target_species:
        config.compat_threshold -= step

    if config.compat_threshold < 0.1:
        config.compat_threshold = 0.1
