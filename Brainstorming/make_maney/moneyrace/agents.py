"""Agents: a genome, a wallet, and a lineage."""

import itertools

from .policy import GenomePolicy

_GLOBAL_IDS = itertools.count(1)


class Agent:
    __slots__ = ("id", "genome", "policy", "wealth", "generation_born",
                 "parents", "lifetime_pnl")

    def __init__(self, genome, wealth, generation_born, parents=(), agent_id=None):
        self.id = next(_GLOBAL_IDS) if agent_id is None else agent_id
        self.genome = genome
        self.policy = GenomePolicy(genome)
        self.wealth = float(wealth)
        self.generation_born = generation_born
        self.parents = tuple(parents)
        self.lifetime_pnl = 0.0

    @property
    def alive(self):
        return self.wealth > 0.0

    def credit(self, amount):
        """Arena profit or loss. Living costs and endowments bypass this so
        lifetime_pnl only measures money the agent actually earned or lost."""
        self.wealth += amount
        self.lifetime_pnl += amount
