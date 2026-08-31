"""World generation: the registry, ``generate_world`` and the FR-5.2.2 counter.

CONTRACTS section 7.5. Everything a match knows about its universe comes from
here, and all of it is a pure function of the seed (FR-5.2.1 to FR-5.2.4, O1):

* ``generate_world(*, template_id, seed, ...)`` takes the **seed and not a
  tree** and builds ``RngTree(seed).child("world")`` itself (section 3.1). That
  is byte for byte the tree the runner's ``root.child("world")`` would be, so
  the world needs no live object from its caller and two callers cannot consume
  the same substream twice.
* No clock, no filesystem, no network, no builtin ``hash``, no iteration over an
  unordered collection reaches an output value.

``World`` is declared in :mod:`pxe.world.templates.base` and re-exported here,
which is the import path the contract names and the one every consumer uses
(``from pxe.world.generator import World``). It is listed in :data:`__all__`, so
that import is legal under ``mypy --strict``'s ``no_implicit_reexport``. The
reason for the split is written in that module's docstring: a template has to
construct a ``World`` and this module has to import the templates for its
registry, and one of the two edges has to point down.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from pxe.errors import InvalidConfigError
from pxe.rng import RngTree
from pxe.types import SEED_SPACE, LiquidityProfileName, Outcome
from pxe.world.templates.base import World
from pxe.world.templates.election import ElectionTemplate
from pxe.world.templates.harvest import HarvestTemplate
from pxe.world.templates.league import LeagueTemplate

__all__ = [
    "World",
    "WorldTemplate",
    "list_templates",
    "get_template",
    "generate_world",
    "outcome_frequency",
]

#: Horizon used by :func:`outcome_frequency`, and the default of
#: :func:`generate_world`. It matches ``MatchConfig.ticks_total``'s default so
#: the statistical test measures the world a real match plays in.
DEFAULT_TICKS_TOTAL = 48

#: Default market count, the PRD section 5.7 value (FR-5.2.1).
DEFAULT_N_MARKETS = 5

_SEED_MAX = SEED_SPACE


class WorldTemplate(Protocol):
    """What every world template exposes (CONTRACTS section 7.5).

    Attributes:
        template_id: Stable identifier, for example ``"election"``.
        template_version: Version of the generation rules. Bumping it is the
            legitimate way a world rule moves a golden hash (section 10).
        default_ticks: Horizon the template was tuned for.
        default_markets: Market count the template was tuned for.
        min_markets: Smallest market count it can express, ``>= 2``.
        max_markets: Largest market count it can express, ``<= 8``.
    """

    template_id: str
    template_version: str
    default_ticks: int
    default_markets: int
    min_markets: int
    max_markets: int

    def build(self, *, seed: int, ticks_total: int, n_markets: int, rng: RngTree) -> World:
        """Build one world.

        Args:
            seed: Match seed.
            ticks_total: Horizon ``T``.
            n_markets: Number of markets.
            rng: The ``world`` sub-tree.

        Returns:
            The assembled world.
        """
        ...


_TEMPLATES: tuple[WorldTemplate, ...] = (ElectionTemplate(), HarvestTemplate(), LeagueTemplate())


def list_templates() -> tuple[str, ...]:
    """Return every registered template id, in a canonical order.

    Returns:
        The ids, sorted by code point so the tuple never depends on how the
        registry happens to be laid out.
    """
    return tuple(sorted(template.template_id for template in _TEMPLATES))


def get_template(template_id: str) -> WorldTemplate:
    """Return the template registered under ``template_id``.

    Args:
        template_id: Template id, one of :func:`list_templates`.

    Returns:
        The template object. Templates are stateless, so the same instance is
        handed to every caller.

    Raises:
        InvalidConfigError: If no template carries that id.
    """
    for template in _TEMPLATES:
        if template.template_id == template_id:
            return template
    raise InvalidConfigError(
        "unknown world template",
        template_id=template_id,
        known=list(list_templates()),
    )


def generate_world(
    *,
    template_id: str,
    seed: int,
    ticks_total: int = DEFAULT_TICKS_TOTAL,
    n_markets: int = DEFAULT_N_MARKETS,
    liquidity: LiquidityProfileName = LiquidityProfileName.STANDARD,
    talking_mode: bool = False,
    held_out: bool = False,
) -> World:
    """Generate a world from a seed, deterministically (FR-5.2.1 to FR-5.2.4).

    Two calls with the same arguments return equal objects, on any machine and
    in any process: the only source of randomness is
    ``RngTree(seed).child("world")``, built here.

    ``liquidity``, ``talking_mode`` and ``held_out`` are metadata: they are
    written into the returned :class:`pxe.types.ScenarioSpec` and change nothing
    about the draws, so the same seed produces the same latent process and the
    same outcomes whatever they are. The first two are the informational copies
    of ``MatchConfig`` fields and the runner raises when they disagree with it
    (section 2.6).

    Args:
        template_id: Template id, one of :func:`list_templates`.
        seed: Unsigned 64 bit match seed.
        ticks_total: Horizon ``T``, ``>= 2``.
        n_markets: Number of markets, ``2..8`` and inside the template's own
            range (FR-5.2.1).
        liquidity: Name of the market maker preset the match will use.
        talking_mode: FR-5.6.1 flag, informational copy.
        held_out: True when the scenario comes from the sealed bank.

    Returns:
        The generated :class:`World`.

    Raises:
        InvalidConfigError: If the seed does not fit in 64 unsigned bits, if the
            template is unknown, if ``n_markets`` is outside ``2..8`` or outside
            the template's range, or if the horizon is too short.
    """
    if not 0 <= seed < _SEED_MAX:
        raise InvalidConfigError("seed must fit in 64 unsigned bits", seed=seed)
    if not 2 <= n_markets <= 8:
        raise InvalidConfigError("a world holds 2 to 8 markets", n_markets=n_markets)
    template = get_template(template_id)
    world = template.build(
        seed=seed,
        ticks_total=ticks_total,
        n_markets=n_markets,
        rng=RngTree(seed).child("world"),
    )
    scenario = replace(
        world.scenario,
        talking_mode=talking_mode,
        liquidity_profile_name=liquidity,
        held_out=held_out,
    )
    return replace(world, scenario=scenario)


def outcome_frequency(
    template_id: str,
    *,
    draws: int = 10_000,
    base_seed: int = 0,
    n_markets: int = DEFAULT_N_MARKETS,
) -> dict[str, int]:
    """FR-5.2.2: returns YES frequency in ppm per market, for the statistical test.

    Draw ``i`` is the world of seed ``base_seed + i``, so a caller can rebuild
    exactly the same worlds and compare the measured frequency with the latent
    probability that produced it. That reproducibility is the whole point:
    without a documented seed sequence the convergence test would have nothing
    to converge *to* and would degrade into "roughly one half", which a
    generator that ignored the latent process entirely would also pass.

    Args:
        template_id: Template id, one of :func:`list_templates`.
        draws: Number of worlds to draw, ``>= 1``.
        base_seed: Seed of the first draw.
        n_markets: Number of markets in each drawn world.

    Returns:
        ``{market_id: yes_frequency_ppm}``, keys ascending by market index.

    Raises:
        InvalidConfigError: If ``draws`` is under one, or if any argument would
            make :func:`generate_world` raise.
    """
    if draws < 1:
        raise InvalidConfigError("draws must be >= 1", draws=draws)
    counts: list[int] = []
    market_ids: tuple[str, ...] = ()
    for index in range(draws):
        world = generate_world(
            template_id=template_id,
            seed=base_seed + index,
            ticks_total=DEFAULT_TICKS_TOTAL,
            n_markets=n_markets,
        )
        if not market_ids:
            market_ids = world.market_ids()
            counts = [0] * len(market_ids)
        for position, market_id in enumerate(market_ids):
            if world.outcome(market_id) is Outcome.YES:
                counts[position] += 1
    return {
        market_id: (2 * counts[position] * 1_000_000 + draws) // (2 * draws)
        for position, market_id in enumerate(market_ids)
    }
