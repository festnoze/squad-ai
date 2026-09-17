"""Frozen symbolic conditions translated into the existing bounded target-position policy."""

from __future__ import annotations

from dataclasses import dataclass, replace

from pmx.agents.registry import ScriptedAgent, ScriptedGenome
from pmx.engine.runner import MemoryLike
from pmx.optimizer.features import blocks_for_view
from pmx.rules.rule import Rule
from pmx.types import MarketView, Observation, RunConfig, interval_ms, ppm_from_bp


@dataclass(frozen=True, slots=True)
class DiscoveryGenome(ScriptedGenome):
    def to_dict(self) -> dict[str, object]:
        payload = ScriptedGenome.to_dict(self)
        payload["genes"] = {**dict(self.genes), "discovery_completed_bar_policy": 1}
        return payload


@dataclass(slots=True)
class DiscoveryAgent(ScriptedAgent):
    def observe(self, obs: Observation) -> None:
        # A source's first observed print can lie inside the first bar. Until that bar
        # completes, even first_price_bp is unavailable. Missing forecasts are carried
        # as neutral 0.5 by the existing runner, and no order is submitted for that market.
        self.observation = replace(obs, markets=tuple(view for view in obs.markets if view.bars))


@dataclass(frozen=True, slots=True)
class RuleGenome(DiscoveryGenome):
    rule: Rule | None = None
    fitted_at_ms: int = 0

    def to_dict(self) -> dict[str, object]:
        payload = DiscoveryGenome.to_dict(self)
        genes = {**dict(self.genes), "discovery_completed_bar_policy": 1, "rule_fitted_at_ms": self.fitted_at_ms}
        if self.rule is not None:
            genes["rule_direction"] = self.rule.claim.direction
            for index, predicate in enumerate(self.rule.condition):
                genes[f"rule_{index}_{predicate.feature}_{predicate.op}"] = predicate.value
        payload["genes"] = genes
        return payload


@dataclass(slots=True)
class RuleAgent(DiscoveryAgent):
    interval: int = 86_400_000

    def reset(self, *, rng: object, memory: MemoryLike | None, config: RunConfig) -> None:
        ScriptedAgent.reset(self, rng=rng, memory=memory, config=config)
        self.interval = interval_ms(config.interval_min)

    def belief_ppm(self, view: MarketView) -> int:
        genome = self.genome
        if not isinstance(genome, RuleGenome) or genome.rule is None or self.observation is None:
            raise ValueError("A rule strategy needs its frozen rule and observation")
        now = self.observation.now_ms
        if now < genome.fitted_at_ms:
            raise ValueError("A learned rule cannot execute before its fit data became available")
        blocks = blocks_for_view(view, now_ms=now, interval=self.interval)
        edge = 0
        if view.bars and genome.rule.condition_holds(blocks):
            edge = genome.rule.claim.direction * dict(genome.genes)["max_edge_bp"]
        return ppm_from_bp(max(0, min(10_000, view.last_price_bp + edge)))
