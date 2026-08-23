"""Decision policies: turn genome traits plus observations into actions.

The default GenomePolicy is deterministic given its genome and inputs, which
keeps whole runs reproducible from a seed. Anything exposing the same three
methods can be plugged onto an agent (the LLM strategist instead works at the
genome level, see llm_strategist.py, because one LLM call per market tick
would be absurdly expensive).
"""

VALUE_PRIOR = 70.0  # midpoint of the auction item value range


def clamp(value, low, high):
    return low if value < low else high if value > high else value


class GenomePolicy:
    def __init__(self, genome):
        self.genome = genome

    def auction_bid(self, signal, wealth):
        """Sealed bid for an item whose noisy appraisal is `signal`."""
        shade = 0.55 + 0.60 * self.genome["auction_shade"]
        trust = 0.5 + 0.5 * self.genome["signal_trust"]
        estimate = signal * trust + VALUE_PRIOR * (1.0 - trust)
        cap = wealth * (0.35 + 0.55 * self.genome["risk"])
        return clamp(estimate * shade, 0.0, cap)

    def market_position(self, momentum_signal, reversion_signal):
        """Target position in [-1, 1] as a fraction of allocated capital."""
        raw = 22.0 * (self.genome["momentum"] * momentum_signal
                      + self.genome["reversion"] * reversion_signal)
        return clamp(raw, -1.0, 1.0) * (0.2 + 0.8 * self.genome["trade_size"])

    def prediction_bet(self, signal, price, wealth):
        """Return (bet_yes, stake) against a binary contract priced at `price`."""
        edge = signal - price
        threshold = 0.02 + 0.10 * (1.0 - self.genome["confidence"])
        if abs(edge) < threshold:
            return True, 0.0
        fraction = min(0.25, abs(edge) * (0.3 + 1.2 * self.genome["confidence"]))
        stake = wealth * fraction * (0.3 + 0.7 * self.genome["risk"])
        return edge > 0, stake
