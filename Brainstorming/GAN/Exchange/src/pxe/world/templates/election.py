"""The fictional election template (PRD section 5.2, mode A).

Latent candidate strengths plus a turnout process, observed through noisy polls
the information engine publishes tick after tick. The first three markets form
one coherence cluster ("ADLER wins", "turnout above 60 %", "ADLER carries the
North"): they share a common latent factor, so an agent holding inconsistent
prices across them is arbitrageable, which is exactly what FR-5.2.1 asks for.

Every market of this template resolves at the last tick ``T``. That is the PRD
default of FR-5.2.3 and the reference scenario CONTRACTS section 5 relies on
when it states that with the PRD default every match settles at finalisation.
Early resolution is exercised by the harvest and league templates.
"""

from __future__ import annotations

from pxe.rng import RngTree
from pxe.world.templates.base import MarketBlueprint, World, assemble_world, check_market_count

__all__ = ["ElectionTemplate"]

_BLUEPRINTS: tuple[MarketBlueprint, ...] = (
    MarketBlueprint(
        question="Will candidate ADLER win the presidency?",
        latent_key="election.adler_strength",
        design_probability_ppm=550_000,
        volatility_milli=120,
        tags=("election", "headline"),
    ),
    MarketBlueprint(
        question="Will national turnout exceed 60 percent?",
        latent_key="election.turnout",
        design_probability_ppm=480_000,
        volatility_milli=130,
        tags=("election", "turnout"),
    ),
    MarketBlueprint(
        question="Will ADLER carry the Northern province?",
        latent_key="election.adler_north",
        design_probability_ppm=620_000,
        volatility_milli=140,
        tags=("election", "region"),
    ),
    MarketBlueprint(
        question="Will BRAND concede before the final count?",
        latent_key="election.brand_concedes",
        design_probability_ppm=350_000,
        volatility_milli=150,
        tags=("election", "reaction"),
    ),
    MarketBlueprint(
        question="Will the ruling coalition keep its majority?",
        latent_key="election.coalition_majority",
        design_probability_ppm=520_000,
        volatility_milli=110,
        tags=("election", "parliament"),
    ),
    MarketBlueprint(
        question="Will a second round runoff be needed?",
        latent_key="election.runoff",
        design_probability_ppm=300_000,
        volatility_milli=140,
        tags=("election", "process"),
    ),
    MarketBlueprint(
        question="Will turnout in the capital exceed 70 percent?",
        latent_key="election.capital_turnout",
        design_probability_ppm=440_000,
        volatility_milli=125,
        tags=("election", "turnout", "region"),
    ),
    MarketBlueprint(
        question="Will the electoral commission order a recount?",
        latent_key="election.recount",
        design_probability_ppm=220_000,
        volatility_milli=160,
        tags=("election", "process"),
    ),
)


class ElectionTemplate:
    """Fictional presidential election with correlated regional and turnout markets."""

    template_id: str = "election"
    template_version: str = "1.0.0"
    default_ticks: int = 48
    default_markets: int = 5
    min_markets: int = 2
    max_markets: int = 8

    def build(self, *, seed: int, ticks_total: int, n_markets: int, rng: RngTree) -> World:
        """Build one election world.

        Args:
            seed: Match seed, copied into the scenario.
            ticks_total: Horizon ``T``.
            n_markets: Number of markets, ``2..8`` (FR-5.2.1).
            rng: The ``world`` sub-tree, ``RngTree(seed).child("world")``.

        Returns:
            The assembled world.

        Raises:
            InvalidConfigError: If ``n_markets`` is outside this template's
                range or the horizon is too short.
        """
        check_market_count(
            template_id=self.template_id,
            n_markets=n_markets,
            min_markets=self.min_markets,
            max_markets=self.max_markets,
        )
        return assemble_world(
            template_id=self.template_id,
            template_version=self.template_version,
            seed=seed,
            ticks_total=ticks_total,
            blueprints=_BLUEPRINTS[:n_markets],
            rng=rng,
            notes="Fictional presidential election: latent candidate strength and turnout, noisy polls.",
            early_resolution_ppm=0,
            news_period=4,
        )
