"""The evolution engine: money in, selection pressure out.

Generation loop:
1. Every enabled arena runs once; agents earn or lose money.
2. Everyone burns the living cost.
3. Agents at or below zero wealth die (recorded in the graveyard).
4. Free population slots are refilled: parents are drawn with probability
   proportional to wealth and PAY the child's endowment out of their own
   pocket, so reproduction is a real economic decision, not free fitness.
   A small immigrant rate injects fresh random genomes to keep diversity.
"""

import itertools
import statistics

from .agents import Agent
from .arenas import ARENA_REGISTRY
from .genome import GENE_NAMES, Genome


class World:
    def __init__(self, config, rng, strategist=None):
        self.config = config
        self.rng = rng
        self.strategist = strategist
        self.arenas = [ARENA_REGISTRY[name]() for name in config.arenas]
        self.generation = 0
        self.graveyard = []
        self.history = []
        # Local id counter so identically seeded worlds are bit-identical
        self._ids = itertools.count(1)
        self.agents = [
            Agent(Genome.random(rng), config.start_wealth, 0, agent_id=next(self._ids))
            for _ in range(config.population)
        ]

    def step(self):
        cfg = self.config
        arena_reports = [arena.run(self.agents, self.rng) for arena in self.arenas]

        for agent in self.agents:
            agent.wealth -= cfg.living_cost

        survivors = []
        deaths = 0
        for agent in self.agents:
            if agent.alive:
                survivors.append(agent)
            else:
                deaths += 1
                self.graveyard.append(self.record(agent, died=self.generation))

        births = 0
        immigrants = 0
        while len(survivors) < cfg.population:
            child = self._spawn(survivors)
            if child.parents:
                births += 1
            else:
                immigrants += 1
            survivors.append(child)

        self.agents = survivors
        stats = self._stats(arena_reports, deaths, births, immigrants)
        self.history.append(stats)
        self.generation += 1
        return stats

    def _spawn(self, survivors):
        cfg, rng = self.config, self.rng
        eligible = [a for a in survivors if a.wealth > cfg.child_endowment * 2]
        if not eligible or rng.random() < cfg.immigrant_rate:
            return Agent(Genome.random(rng), cfg.start_wealth,
                         self.generation + 1, agent_id=next(self._ids))

        weights = [a.wealth for a in eligible]
        parent = rng.choices(eligible, weights=weights)[0]
        genome = parent.genome
        parents = (parent.id,)
        if len(eligible) > 1 and rng.random() < cfg.crossover_rate:
            mate = rng.choices(eligible, weights=weights)[0]
            if mate is not parent:
                genome = Genome.crossover(parent.genome, mate.genome, rng)
                parents = (parent.id, mate.id)
        genome = genome.mutated(rng, cfg.mutation_rate, cfg.mutation_sigma)

        if self.strategist is not None and rng.random() < cfg.strategist_share:
            proposed = self.strategist.propose(self.history, genome.as_dict())
            if proposed:
                genome = Genome(proposed)

        parent.wealth -= cfg.child_endowment
        return Agent(genome, cfg.child_endowment, self.generation + 1,
                     parents=parents, agent_id=next(self._ids))

    def _stats(self, arena_reports, deaths, births, immigrants):
        wealths = [a.wealth for a in self.agents]
        best = max(self.agents, key=lambda a: a.wealth)
        gene_means = {
            name: statistics.fmean(a.genome[name] for a in self.agents)
            for name in GENE_NAMES
        }
        return {
            "generation": self.generation,
            "population": len(self.agents),
            "deaths": deaths,
            "births": births,
            "immigrants": immigrants,
            "total_wealth": sum(wealths),
            "mean_wealth": statistics.fmean(wealths),
            "median_wealth": statistics.median(wealths),
            "max_wealth": max(wealths),
            "best_agent": best.id,
            "gene_means": gene_means,
            "arenas": arena_reports,
        }

    def leaderboard(self, top=10):
        ranked = sorted(self.agents, key=lambda a: a.wealth, reverse=True)
        return [self.record(a) for a in ranked[:top]]

    def record(self, agent, died=None):
        return {
            "id": agent.id,
            "wealth": round(agent.wealth, 2),
            "lifetime_pnl": round(agent.lifetime_pnl, 2),
            "born": agent.generation_born,
            "died": died,
            "age": (died if died is not None else self.generation) - agent.generation_born,
            "parents": list(agent.parents),
            "genes": {k: round(v, 3) for k, v in agent.genome.as_dict().items()},
        }
