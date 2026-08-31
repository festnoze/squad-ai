"""Scripted forecasting-and-trading agents (deterministic, free).

Each agent turns an :class:`~pmx.types.Observation` into an :class:`~pmx.types.Action`: a stated
probability (scored by Brier) and, derived from it, a target YES position (scored by PnL). Belief and
trade are one decision: an agent takes a position exactly to the extent it disagrees with the market
price, so its PnL is positive only when its disagreement was right, net of the spread it paid.

The roster spans good and bad on purpose. A population needs losers for selection to have signal, and
the honest baseline is ``market_follower``: it believes the price exactly, so its Brier is the market's
own Brier, the number every other agent is trying to beat.
"""

from __future__ import annotations

from collections.abc import Callable

from pmx.scoring import price_to_ppm
from pmx.types import PPM_ONE, Action, Observation

POSITION_LIMIT = 100
#: A belief this many ppm away from the market price sizes the position to the full limit.
_FULL_SIZE_EDGE_PPM = 200_000


def _clamp_ppm(ppm: int) -> int:
    return max(0, min(PPM_ONE, ppm))


def _size_from_belief(prob_ppm: int, price_cents: int) -> int:
    """Position proportional to how far the belief sits from the price, bounded by the limit."""
    edge = prob_ppm - price_to_ppm(price_cents)
    pos = (edge * POSITION_LIMIT) // _FULL_SIZE_EDGE_PPM
    return max(-POSITION_LIMIT, min(POSITION_LIMIT, pos))


def _trend(history: tuple[int, ...], lookback: int) -> int:
    """Signed price change over the last ``lookback`` ticks, in cents."""
    if len(history) < 2:
        return 0
    past = history[max(0, len(history) - 1 - lookback)]
    return history[-1] - past


# --- belief functions: each returns a stated probability in ppm ------------------------------------


def _market_follower(obs: Observation) -> int:
    """Believe the price exactly. The baseline: its Brier is the market's Brier."""
    return price_to_ppm(obs.price)


def _stubborn(_obs: Observation) -> int:
    """Never update: a coin flip forever. A deliberately weak agent."""
    return PPM_ONE // 2


def _anchor(obs: Observation) -> int:
    """Anchor on the first price ever seen and never move. Anchoring bias, usually poor."""
    return price_to_ppm(obs.history[0])


def _mean_revert(obs: Observation) -> int:
    """Fade the market toward a coin flip: assume extremes overshoot."""
    p = price_to_ppm(obs.price)
    return _clamp_ppm(PPM_ONE // 2 + (p - PPM_ONE // 2) * 60 // 100)


def _contrarian(obs: Observation) -> int:
    """Bet against the crowd outright. Aggressive and usually wrong, on purpose."""
    return _clamp_ppm(PPM_ONE - price_to_ppm(obs.price))


def _momentum(obs: Observation) -> int:
    """Extrapolate the recent move: a rising price keeps rising."""
    p = price_to_ppm(obs.price)
    tr = _trend(obs.history, 5)
    return _clamp_ppm(p + price_to_ppm(tr) * 60 // 100)


def _calibrated(obs: Observation) -> int:
    """Shrink the price toward a coin flip by a small factor (a favorite-longshot correction).

    Empirically this nudges Brier down versus naively believing the price, so it is the honest
    'slightly smarter than the market' agent."""
    p = price_to_ppm(obs.price)
    return _clamp_ppm(PPM_ONE // 2 + (p - PPM_ONE // 2) * 88 // 100)


def _sharp(obs: Observation) -> int:
    """Believe the price but lean into a confirmed trend, as 'smart money' front-running the drift."""
    p = price_to_ppm(obs.price)
    tr = _trend(obs.history, 3)
    lean = 40_000 if tr > 0 else (-40_000 if tr < 0 else 0)
    return _clamp_ppm(p + lean)


_BELIEFS: dict[str, Callable[[Observation], int]] = {
    "market_follower": _market_follower,
    "calibrated": _calibrated,
    "sharp": _sharp,
    "momentum": _momentum,
    "mean_revert": _mean_revert,
    "contrarian": _contrarian,
    "anchor": _anchor,
    "stubborn": _stubborn,
}

AGENT_IDS: tuple[str, ...] = tuple(_BELIEFS)


class Agent:
    """A scripted agent: a named belief function plus the position sizing shared by all of them."""

    def __init__(self, agent_id: str) -> None:
        if agent_id not in _BELIEFS:
            raise ValueError(f"unknown agent {agent_id!r}; choose from {list(AGENT_IDS)}")
        self.agent_id = agent_id
        self._belief = _BELIEFS[agent_id]

    def decide(self, obs: Observation) -> Action:
        prob = _clamp_ppm(self._belief(obs))
        return Action(prob_ppm=prob, target_position=_size_from_belief(prob, obs.price))


def make_agents(agent_ids: tuple[str, ...]) -> list[Agent]:
    return [Agent(a) for a in agent_ids]
