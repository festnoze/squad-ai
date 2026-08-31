"""Deterministic scoring: Brier on stated probability, PnL on trades. Integers only.

Brier score of a probability ``p`` against an outcome ``y in {0, 1}`` is ``(p - y)^2``. With ``p`` in
parts-per-million we compute it in micro-units so a perfect forecast scores 0 and the worst scores
1_000_000, with no float:

    brier_micro = (p_ppm - y * PPM_ONE)^2 / PPM_ONE

The division is integer and exact enough at this scale (the numerator is a product of two values below
1e6, so it fits well within 64 bits and the truncation is at most 1 micro-unit).
"""

from __future__ import annotations

from pmx.types import PPM_ONE, PRICE_MAX, PRICE_MIN


def brier_micro(prob_ppm: int, outcome: int) -> int:
    """Brier score of one probability against a 0/1 outcome, in micro-units (0 best, 1_000_000 worst)."""
    target = outcome * PPM_ONE
    diff = prob_ppm - target
    return (diff * diff) // PPM_ONE


def price_to_ppm(price_cents: int) -> int:
    """The market's implied probability: a price of 63 cents means 630_000 ppm."""
    return price_cents * (PPM_ONE // 100)


def clamp_price(price_cents: int) -> int:
    """A tradable price is always in ``[1, 99]``; the book never fills at 0 or 100."""
    return max(PRICE_MIN, min(PRICE_MAX, price_cents))
