"""The harvest and weather template (PRD section 5.2, mode A).

A seasonal latent process (rainfall, drought, yield) read through partial
measurements. The seasonal component is a deterministic triangular wave, not a
sine: ``sin`` is a platform libm call and would put AC-P1 at the mercy of the
C library (section 3.2), while the triangle is exact integer arithmetic plus one
correctly rounded division.

The first three markets share the weather cluster, so a coherent agent cannot
price "rainfall above the median" and "drought index below the alert level"
independently. Two slots may resolve early: a quota met or a grade awarded is
known before the season closes, which is FR-5.2.3's early resolution.

This template deliberately tops out at six markets: it has six honest
questions, and inventing two more to reach eight would produce noise dressed as
a market. A request for seven or eight raises rather than clamping (decision
36).
"""

from __future__ import annotations

from pxe.rng import RngTree
from pxe.world.templates.base import MarketBlueprint, World, assemble_world, check_market_count

__all__ = ["HarvestTemplate"]

_SEASON_PERIOD_TICKS = 16

_BLUEPRINTS: tuple[MarketBlueprint, ...] = (
    MarketBlueprint(
        question="Will the regional wheat yield beat 4.2 tonnes per hectare?",
        latent_key="harvest.wheat_yield",
        design_probability_ppm=520_000,
        volatility_milli=115,
        seasonal_amplitude_milli=90,
        seasonal_period_ticks=_SEASON_PERIOD_TICKS,
        tags=("harvest", "yield"),
    ),
    MarketBlueprint(
        question="Will cumulative rainfall exceed the ten year median?",
        latent_key="harvest.rainfall",
        design_probability_ppm=470_000,
        volatility_milli=135,
        seasonal_amplitude_milli=110,
        seasonal_period_ticks=_SEASON_PERIOD_TICKS,
        tags=("harvest", "weather"),
    ),
    MarketBlueprint(
        question="Will the drought index stay below the alert level?",
        latent_key="harvest.drought_index",
        design_probability_ppm=580_000,
        volatility_milli=125,
        seasonal_amplitude_milli=80,
        seasonal_period_ticks=_SEASON_PERIOD_TICKS,
        tags=("harvest", "weather"),
    ),
    MarketBlueprint(
        question="Will the export quota be met before the season closes?",
        latent_key="harvest.export_quota",
        design_probability_ppm=400_000,
        volatility_milli=140,
        tags=("harvest", "trade"),
        allow_early_resolution=True,
    ),
    MarketBlueprint(
        question="Will the barley crop be graded premium?",
        latent_key="harvest.barley_grade",
        design_probability_ppm=440_000,
        volatility_milli=130,
        tags=("harvest", "quality"),
        allow_early_resolution=True,
    ),
    MarketBlueprint(
        question="Will the irrigation reserve fall under one third?",
        latent_key="harvest.irrigation_reserve",
        design_probability_ppm=330_000,
        volatility_milli=120,
        seasonal_amplitude_milli=70,
        seasonal_period_ticks=_SEASON_PERIOD_TICKS,
        tags=("harvest", "water"),
    ),
)


class HarvestTemplate:
    """Seasonal yield and weather process observed through partial readings."""

    template_id: str = "harvest"
    template_version: str = "1.0.0"
    default_ticks: int = 48
    default_markets: int = 4
    min_markets: int = 2
    max_markets: int = 6

    def build(self, *, seed: int, ticks_total: int, n_markets: int, rng: RngTree) -> World:
        """Build one harvest world.

        Args:
            seed: Match seed, copied into the scenario.
            ticks_total: Horizon ``T``.
            n_markets: Number of markets, ``2..6`` for this template.
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
            notes="Seasonal harvest and weather process, partial readings, two early resolving markets.",
            early_resolution_ppm=500_000,
            news_period=4,
        )
