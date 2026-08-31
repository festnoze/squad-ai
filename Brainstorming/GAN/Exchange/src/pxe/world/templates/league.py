"""The fictional league template (PRD section 5.2, mode A).

Hidden team strengths plus intermediate match results, which is the PRD's own
example of "marches a resolution anticipee": a derby played on match day nine is
settled long before the title race is. Several slots are therefore eligible for
an early resolution tick (FR-5.2.3), and the news calendar runs faster than in
the other templates because a league produces a result every few ticks.

The head cluster ties the two strongest teams together ("RAVENS win the title",
"RAVENS finish above the FOXES", "FOXES qualify"): those three cannot move
independently, which is the coherence arbitrage of FR-5.2.1.

The template refuses to express fewer than three markets: with two it would be
a single fixture and nothing about a league table would be visible.
"""

from __future__ import annotations

from pxe.rng import RngTree
from pxe.world.templates.base import MarketBlueprint, World, assemble_world, check_market_count

__all__ = ["LeagueTemplate"]

_BLUEPRINTS: tuple[MarketBlueprint, ...] = (
    MarketBlueprint(
        question="Will the RAVENS win the championship?",
        latent_key="league.ravens_strength",
        design_probability_ppm=420_000,
        volatility_milli=125,
        tags=("league", "title"),
    ),
    MarketBlueprint(
        question="Will the RAVENS finish above the FOXES?",
        latent_key="league.ravens_above_foxes",
        design_probability_ppm=550_000,
        volatility_milli=130,
        tags=("league", "head_to_head"),
    ),
    MarketBlueprint(
        question="Will the FOXES qualify for the play-offs?",
        latent_key="league.foxes_strength",
        design_probability_ppm=600_000,
        volatility_milli=120,
        tags=("league", "playoffs"),
    ),
    MarketBlueprint(
        question="Will the RAVENS beat the FOXES on match day nine?",
        latent_key="league.derby_day_nine",
        design_probability_ppm=500_000,
        volatility_milli=150,
        tags=("league", "fixture"),
        allow_early_resolution=True,
    ),
    MarketBlueprint(
        question="Will the BADGERS avoid relegation?",
        latent_key="league.badgers_survival",
        design_probability_ppm=650_000,
        volatility_milli=115,
        tags=("league", "relegation"),
    ),
    MarketBlueprint(
        question="Will the top scorer pass twenty goals?",
        latent_key="league.top_scorer",
        design_probability_ppm=380_000,
        volatility_milli=135,
        tags=("league", "player"),
        allow_early_resolution=True,
    ),
    MarketBlueprint(
        question="Will the OTTERS win three matches in a row?",
        latent_key="league.otters_streak",
        design_probability_ppm=280_000,
        volatility_milli=145,
        tags=("league", "streak"),
        allow_early_resolution=True,
    ),
    MarketBlueprint(
        question="Will the league attendance record be broken?",
        latent_key="league.attendance_record",
        design_probability_ppm=310_000,
        volatility_milli=120,
        tags=("league", "off_pitch"),
        allow_early_resolution=True,
    ),
)


class LeagueTemplate:
    """Fictional championship with hidden team strengths and early resolving fixtures."""

    template_id: str = "league"
    template_version: str = "1.0.0"
    default_ticks: int = 48
    default_markets: int = 6
    min_markets: int = 3
    max_markets: int = 8

    def build(self, *, seed: int, ticks_total: int, n_markets: int, rng: RngTree) -> World:
        """Build one league world.

        Args:
            seed: Match seed, copied into the scenario.
            ticks_total: Horizon ``T``.
            n_markets: Number of markets, ``3..8`` for this template.
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
            notes="Fictional league: hidden team strengths, intermediate results, early resolving fixtures.",
            early_resolution_ppm=700_000,
            news_period=3,
        )
