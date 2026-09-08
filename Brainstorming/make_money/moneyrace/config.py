"""Run configuration for the evolutionary money race."""

from dataclasses import dataclass, asdict


@dataclass
class Config:
    # Population
    population: int = 32
    generations: int = 80
    seed: int = 42

    # Which arenas run each generation (see arenas.ARENA_REGISTRY)
    arenas: tuple = ("auction", "market", "prediction")

    # Economy: money is the survival currency
    start_wealth: float = 100.0     # endowment of founders and immigrants
    living_cost: float = 4.0        # burned every generation; broke agents die
    child_endowment: float = 50.0   # a parent transfers this to each child

    # Evolution
    immigrant_rate: float = 0.06    # chance a free slot goes to a random newcomer
    mutation_rate: float = 0.25     # per-gene chance of gaussian mutation
    mutation_sigma: float = 0.12    # gaussian mutation width
    crossover_rate: float = 0.5     # chance a child mixes two parents
    strategist_share: float = 0.25  # share of births designed by the LLM strategist (when enabled)

    def as_dict(self):
        data = asdict(self)
        data["arenas"] = list(self.arenas)
        return data
