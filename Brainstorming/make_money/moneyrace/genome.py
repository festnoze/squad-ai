"""Genome: the heritable strategy parameters of an agent.

Every gene is a float in [0, 1]. Arenas and policies map genes onto concrete
behaviour, so the meaning of a gene lives next to the code that uses it.
"""

GENE_NAMES = [
    "risk",           # overall fraction of wealth put at stake per arena
    "auction_shade",  # bid shading: low protects against the winner's curse
    "signal_trust",   # weight of noisy signals vs the population prior
    "momentum",       # trend-following weight in the market arena
    "reversion",      # mean-reversion weight in the market arena
    "trade_size",     # position sizing in the market arena
    "confidence",     # bet threshold and sizing in the prediction arena
]


class Genome:
    __slots__ = ("genes",)

    def __init__(self, genes):
        self.genes = {name: float(genes[name]) for name in GENE_NAMES}

    @classmethod
    def random(cls, rng):
        return cls({name: rng.random() for name in GENE_NAMES})

    def mutated(self, rng, rate, sigma, reset_rate=0.03):
        genes = {}
        for name, value in self.genes.items():
            if rng.random() < reset_rate:
                genes[name] = rng.random()
            elif rng.random() < rate:
                genes[name] = min(1.0, max(0.0, value + rng.gauss(0.0, sigma)))
            else:
                genes[name] = value
        return Genome(genes)

    @classmethod
    def crossover(cls, first, second, rng):
        return cls({
            name: first.genes[name] if rng.random() < 0.5 else second.genes[name]
            for name in GENE_NAMES
        })

    def __getitem__(self, name):
        return self.genes[name]

    def as_dict(self):
        return dict(self.genes)
