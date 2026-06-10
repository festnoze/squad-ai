"""Population — one generation of the NEAT loop.

A :class:`Population` owns the genomes, the shared :class:`InnovationTracker`,
and the species book-keeping. The :class:`~nfl.engine.runner.Runner` evaluates
the genomes (assigns ``.fitness``) and then calls :meth:`Population.evolve`,
which speciates, shares fitness, allocates offspring per species and breeds the
next generation via elitism + crossover + mutation.

The population is deliberately agnostic about *how* fitness was obtained (pure
evolution or evolution + lifetime gradient descent): it only reads ``.fitness``.
"""

from __future__ import annotations

import math

import numpy as np

from ..config import SimConfig
from .crossover import crossover
from .genome import Genome, InnovationTracker, create_initial_genome
from .mutations import enforce_acyclic, mutate
from .speciation import Species, adjust_compat_threshold, share_fitness, speciate

# Flappy has a single output neuron (flap / no-flap).
NUM_OUTPUTS = 1


class Population:
    """A NEAT population with speciation-based reproduction."""

    def __init__(self, config: SimConfig, rng: np.random.Generator) -> None:
        self.config = config
        self.rng = rng

        self.num_inputs = len(config.active_sensors)  # sensors only; bias is separate
        self.num_outputs = NUM_OUTPUTS
        # Node ids: bias=0, inputs=1..S, outputs=S+1..S+O, hidden after that.
        first_free_node_id = 1 + self.num_inputs + self.num_outputs
        self.tracker = InnovationTracker(first_free_node_id)

        self.genomes: list[Genome] = [self._new_genome() for _ in range(config.pop_size)]
        self.species: list[Species] = []
        self.next_species_id = 0
        self.generation = 0

    # ------------------------------------------------------------------ helpers --
    def _new_genome(self) -> Genome:
        return create_initial_genome(
            num_inputs=self.num_inputs,
            num_outputs=self.num_outputs,
            activation=self.config.activation.value,
            tracker=self.tracker,
            rng=self.rng,
            initial_hidden=self.config.initial_hidden,
            weight_sigma=1.0,
        )

    def _tournament(self, pool: list[Genome]) -> Genome:
        """Pick the fitter of two random genomes from ``pool``."""
        a = pool[self.rng.integers(len(pool))]
        b = pool[self.rng.integers(len(pool))]
        return a if a.fitness >= b.fitness else b

    def best_genome(self) -> Genome:
        return max(self.genomes, key=lambda g: g.fitness)

    def assign_camps(self, gd_ratio: float) -> None:
        """Tag genomes for confrontation: the last ``gd_ratio`` fraction is camp "gd".

        The GD camp's topologies are frozen from this point on — they will only
        ever change weights (by gradient descent); the NEAT camp keeps evolving.
        """
        n_gd = int(round(len(self.genomes) * gd_ratio))
        n_neat = len(self.genomes) - n_gd
        for i, genome in enumerate(self.genomes):
            genome.camp = "neat" if i < n_neat else "gd"

    # ------------------------------------------------------------------- evolve --
    def evolve(self) -> None:
        """Build the next generation from the current (already-evaluated) one."""
        self.genomes = self._breed(self.genomes, self.config.pop_size)
        self.generation += 1

    def evolve_confrontation(self) -> None:
        """Confrontation step: breed the NEAT camp; the GD camp persists as-is.

        The NEAT camp reproduces only within itself (speciation, crossover,
        mutation) and keeps its head-count. GD-camp genomes carry over unchanged
        — their weights were already updated in place by lifetime gradient
        descent (the runner persists them into the genome). The two lineages
        therefore never mix: every bird is fully NEAT-bred or fully GD-trained.
        """
        neat = [g for g in self.genomes if g.camp == "neat"]
        gd = [g for g in self.genomes if g.camp == "gd"]

        if neat:
            children = self._breed(neat, len(neat))
            for child in children:
                child.camp = "neat"
        else:
            children = []
            self.species = []

        # Stable ordering: NEAT camp first, GD camp after — bird indices keep
        # their camp across generations.
        self.genomes = children + gd
        self.generation += 1

    def _breed(self, genomes: list[Genome], pop: int) -> list[Genome]:
        """Speciate + reproduce ``genomes`` into exactly ``pop`` offspring.

        Updates the species bookkeeping (``self.species``) as a side effect so
        stats and the δ_t auto-adjustment stay meaningful.
        """
        cfg = self.config

        # 1. Speciate the evaluated genomes and apply fitness sharing.
        self.species, self.next_species_id = speciate(
            genomes, self.species, cfg, self.next_species_id
        )
        share_fitness(self.species)

        # 2. Allocate offspring proportionally to each species' summed adjusted fitness.
        species_adj = [sum(m.adjusted_fitness for m in s.members) for s in self.species]
        total_adj = sum(species_adj)
        if total_adj <= 0.0:
            # Degenerate (all-zero fitness): split evenly.
            base = pop // max(len(self.species), 1)
            alloc = [base for _ in self.species]
        else:
            alloc = [int(round(pop * a / total_adj)) for a in species_adj]
        self._fix_allocation(alloc, pop, species_adj)

        # 3. Breed each species: carry elites, then crossover+mutate the survivors.
        children: list[Genome] = []
        for species, n_off in zip(self.species, alloc):
            if n_off <= 0 or not species.members:
                continue
            ranked = sorted(species.members, key=lambda g: g.fitness, reverse=True)

            n_elite = min(cfg.elitism_per_species, n_off, len(ranked))
            for i in range(n_elite):
                children.append(ranked[i].copy())

            n_survivors = max(1, math.ceil(len(ranked) * cfg.survival_threshold))
            pool = ranked[:n_survivors]
            for _ in range(n_off - n_elite):
                parent_a = self._tournament(pool)
                parent_b = self._tournament(pool)
                child = crossover(parent_a, parent_b, self.rng)
                mutate(child, cfg, self.tracker, self.rng)
                # Crossover can merge two acyclic parents into a cyclic child;
                # repair before the genome is ever compiled into a network.
                enforce_acyclic(child)
                children.append(child)

        # 4. Guarantee the champion of this pool survives, and pin size to pop.
        champion = max(genomes, key=lambda g: g.fitness).copy()
        if not children:
            children.append(champion)
        children = self._resize(children, pop, champion)

        adjust_compat_threshold(cfg, len(self.species))
        return children

    def advance_without_reproduction(self) -> None:
        """Bump the generation while KEEPING the current genomes (no breeding).

        Used by ``gradient_only`` mode: the population's topology is frozen and
        only its weights change (via gradient descent, applied elsewhere). We
        still speciate + share fitness so the stats/visuals stay meaningful, but
        we never select, cross over or mutate.
        """
        self.species, self.next_species_id = speciate(
            self.genomes, self.species, self.config, self.next_species_id
        )
        share_fitness(self.species)
        self.generation += 1

    # --------------------------------------------------------------- internals ---
    def _fix_allocation(self, alloc: list[int], pop: int, weights: list[float]) -> None:
        """Adjust ``alloc`` in place so it sums exactly to ``pop``."""
        if not alloc:
            return
        # Add/remove offspring from the species with the largest weight until exact.
        order = sorted(range(len(alloc)), key=lambda i: weights[i], reverse=True)
        diff = pop - sum(alloc)
        i = 0
        while diff != 0 and order:
            idx = order[i % len(order)]
            if diff > 0:
                alloc[idx] += 1
                diff -= 1
            elif alloc[idx] > 0:
                alloc[idx] -= 1
                diff += 1
            i += 1

    def _resize(self, children: list[Genome], pop: int, champion: Genome) -> list[Genome]:
        """Trim or pad ``children`` to exactly ``pop`` genomes."""
        if len(children) > pop:
            return children[:pop]
        while len(children) < pop:
            # Pad by mutating copies of the champion (cheap, keeps diversity moving).
            clone = champion.copy()
            mutate(clone, self.config, self.tracker, self.rng)
            enforce_acyclic(clone)
            children.append(clone)
        return children
