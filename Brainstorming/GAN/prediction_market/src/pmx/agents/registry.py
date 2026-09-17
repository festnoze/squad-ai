"""Three transparent, deterministic strategies for the exploratory MVP (CONTRACTS_MVP).

Only completed bars from the engine observation enter a forecast. Validated parameters are journaled
as genomes, and no strategy learns from outcomes or uses a source outside its observation.
"""

from __future__ import annotations

from dataclasses import dataclass

from pmx.engine.runner import MemoryLike, ResolutionEvent
from pmx.types import (
    RE_AGENT_ID,
    Actions,
    MarketAction,
    MarketView,
    Observation,
    RunConfig,
    ppm_from_bp,
    round_half_up,
)


@dataclass(frozen=True, slots=True)
class ScriptedGenome:
    """Serializable fixed parameters, compatible with the runner's GenomeLike protocol."""

    family: str
    genes: tuple[tuple[str, int], ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {"family": self.family, "genes": dict(self.genes), "inner": None, "members": [], "prompt": None}


PARAMETERS = {
    "follower": {},
    "trend": {
        "lookback_bars": 4,
        "strength_permille": 500,
        "max_edge_bp": 1500,
        "edge_min_bp": 50,
        "max_position": 25,
    },
    "revert": {
        "lookback_bars": 7,
        "strength_permille": 750,
        "max_edge_bp": 1500,
        "edge_min_bp": 50,
        "max_position": 25,
    },
    "level": {
        "anchor_bp": 5000,
        "strength_permille": 500,
        "max_edge_bp": 1500,
        "edge_min_bp": 50,
        "max_position": 25,
    },
}
PARAMETER_BOUNDS = {
    "lookback_bars": (2, 90),
    "anchor_bp": (100, 9900),
    "strength_permille": (0, 2000),
    "max_edge_bp": (1, 3000),
    "edge_min_bp": (0, 3000),
    "max_position": (1, 100),
}
NAMES = {"follower": "Marché témoin", "trend": "Tendance", "revert": "Retour à la moyenne"}
DESCRIPTIONS = {
    "follower": "Reprend la probabilité du marché disponible à chaque décision. Aucun ordre.",
    "trend": "Prolonge de moitié le mouvement des quatre dernières barres complétées, avec exposition bornée.",
    "revert": "Prévoit un retour partiel vers la moyenne des sept dernières barres complétées.",
}
DEFAULT_ROSTER = tuple(
    (agent_id, ScriptedGenome(agent_id, tuple(sorted(PARAMETERS[agent_id].items()))))
    for agent_id in ("follower", "trend", "revert")
)


def _scaled_signed(value: int, numerator: int, denominator: int) -> int:
    magnitude = round_half_up(abs(value) * numerator, denominator)
    return magnitude if value >= 0 else -magnitude


@dataclass(slots=True)
class ScriptedAgent:
    """A bounded rule over past prices; the engine alone sizes and accounts for actual fills."""

    agent_id: str
    genome: ScriptedGenome
    needs_gateway: bool = False
    kind: str = "scripted"
    model: str | None = None
    knowledge_cutoff_ms: int | None = None
    observation: Observation | None = None

    @property
    def family(self) -> str:
        return self.genome.family

    def reset(self, *, rng: object, memory: MemoryLike | None, config: RunConfig) -> None:
        self.observation = None

    def observe(self, obs: Observation) -> None:
        self.observation = obs

    def belief_ppm(self, view: MarketView) -> int:
        if self.family == "follower":
            return ppm_from_bp(view.last_price_bp)
        params = dict(self.genome.genes)
        if self.family == "level":
            move = params["anchor_bp"] - view.last_price_bp
            edge = _scaled_signed(move, params["strength_permille"], 1000)
            edge = max(-params["max_edge_bp"], min(params["max_edge_bp"], edge))
            return ppm_from_bp(max(0, min(10_000, view.last_price_bp + edge)))
        closes = [bar.close_bp for bar in view.bars[-params["lookback_bars"] :]]
        if len(closes) < 2:
            return ppm_from_bp(view.last_price_bp)
        move = (
            closes[-1] - closes[0]
            if self.family == "trend"
            else (round_half_up(sum(closes), len(closes)) - view.last_price_bp)
        )
        edge = _scaled_signed(move, params["strength_permille"], 1000)
        edge = max(-params["max_edge_bp"], min(params["max_edge_bp"], edge))
        return ppm_from_bp(max(0, min(10_000, view.last_price_bp + edge)))

    def decide(self) -> Actions:
        if self.observation is None:
            raise RuntimeError("An observation is required before deciding")
        actions: list[MarketAction] = []
        params = dict(self.genome.genes)
        for view in self.observation.markets:
            probability = self.belief_ppm(view)
            if self.family == "follower" or not view.tradable:
                action = MarketAction(market_id=view.market_id, prob_ppm=probability, kind="hold")
            else:
                edge_bp = probability // 100 - view.last_price_bp
                target = (
                    0
                    if abs(edge_bp) < params["edge_min_bp"]
                    else _scaled_signed(edge_bp, params["max_position"], params["max_edge_bp"])
                )
                action = MarketAction(
                    market_id=view.market_id, prob_ppm=probability, kind="target", target_position=target
                )
            actions.append(action)
        return Actions(actions_version="actions.v2", markets=tuple(actions))

    def learn(self, event: ResolutionEvent) -> None:
        """Fixed strategies intentionally do not fit parameters to resolved outcomes."""

    def snapshot(self) -> dict[str, object]:
        return {"agent_id": self.agent_id, "genome": self.genome.to_dict()}


def make_agent(agent_id: str, genome: ScriptedGenome | None = None) -> ScriptedAgent:
    """Keep the fixed roster defaults, and permit strictly bounded discovery genomes."""
    defaults = dict(DEFAULT_ROSTER)
    if genome is None and agent_id not in defaults:
        raise ValueError(f"Unknown strategy: {agent_id}")
    selected = defaults[agent_id] if genome is None else genome
    if RE_AGENT_ID.fullmatch(agent_id) is None or selected.family not in PARAMETERS:
        raise ValueError(f"Unknown strategy: {agent_id}/{selected.family}")
    params = dict(selected.genes)
    if len(params) != len(selected.genes) or set(params) != set(PARAMETERS[selected.family]):
        raise ValueError("Genome parameters must match the documented fixed parameter names")
    for key, value in params.items():
        lo, hi = PARAMETER_BOUNDS[key]
        if type(value) is not int or not lo <= value <= hi:
            raise ValueError(f"Invalid {key}: expected integer in {lo}..{hi}")
    if params and params["edge_min_bp"] > params["max_edge_bp"]:
        raise ValueError("edge_min_bp must not exceed max_edge_bp")
    return ScriptedAgent(agent_id=agent_id, genome=selected)


def agent_summaries() -> list[dict[str, object]]:
    return [
        {
            "id": agent_id,
            "name": NAMES[agent_id],
            "description": DESCRIPTIONS[agent_id],
            "baseline": agent_id == "follower",
            "parameters": dict(genome.genes),
        }
        for agent_id, genome in DEFAULT_ROSTER
    ]
