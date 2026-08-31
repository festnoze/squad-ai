"""Shared world building machinery every template reuses (A03).

A template declares *what* its markets mean (:class:`MarketBlueprint`: a
question, a design probability, a volatility) and this module turns that
declaration into a :class:`World`: correlated latent paths, public priors, per
market resolution ticks, a news calendar and the drawn outcomes.

Everything here is a pure function of ``(seed, ticks_total, n_markets)`` through
the ``world.*`` substreams of the tree ``generate_world`` builds, so two calls
with the same arguments return equal objects (FR-5.2.1 to FR-5.2.4, O1).

**Why :class:`World` is defined here and re-exported by
:mod:`pxe.world.generator`.** CONTRACTS section 7.5 lists ``World`` under
``generator.py`` and that is the import path every consumer uses
(``from pxe.world.generator import World``, which mypy accepts because
``generator.__all__`` names it). The class body has to live one level down
because a template must construct a ``World`` and the generator must import the
templates to build its registry; defining the carrier in the leaf module is the
only arrangement of those two facts with no import cycle and no lazy import
(``PLC0415`` is on).

**Every stream is a fresh one.** Each draw below comes from
``rng.fresh_substream(name)`` and not ``rng.substream(name)``: a cached
generator would let a caller who reuses one ``RngTree`` object for two builds
get two different worlds out of one seed, which is precisely the class of bug
section 3.1 warns about with "two trees built from the same seed in two places
is how the same substream gets consumed twice". With a fresh stream per name the
world is a function of ``(seed, ticks_total, n_markets)`` and of nothing else,
whatever state the handed tree is in.

**Correlation is real, not decorative (FR-5.2.1).** Markets in the same group
share a common factor in every shock:

    z_i(t) = sqrt(rho) * F_g(t) + sqrt(1 - rho) * E_i(t)

with ``F_g`` drawn once per group per tick and ``E_i`` drawn per market. Two
markets of the same group therefore have innovation correlation exactly ``rho``,
their latent paths and their outcomes are correlated, and coherence arbitrage
between them is possible. Independent draws per market would satisfy every type
annotation in this package and destroy the point of the arena.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from pxe.errors import InvalidConfigError
from pxe.rng import RngTree, bernoulli, normal, randint
from pxe.types import (
    LiquidityProfileName,
    MarketSpec,
    NewsImpact,
    NewsPlanItem,
    Outcome,
    ScenarioSpec,
    clamp_price,
    make_market_id,
    round_half_up,
    sorted_ids,
)
from pxe.world.latent import PPM_ONE, LatentProcess, milli_from_probability_ppm

__all__ = ["World", "MarketBlueprint", "assemble_world"]

#: Smallest and largest number of markets any template may express (FR-5.2.1).
MARKETS_MIN = 2
MARKETS_MAX = 8

#: Shortest horizon the shared builder accepts. A real match is 24 to 96 ticks
#: (``MatchConfig.__post_init__``); the floor here is deliberately lower so a
#: unit test can build a two tick world without the generator refusing it.
TICKS_MIN = 2

#: Pairwise latent correlation drawn per group, in thousandths. The floor is
#: high enough that the coherence link is visible in a single match and the
#: ceiling stays below 1 so the markets never become the same market.
RHO_MILLI_MIN = 350
RHO_MILLI_MAX = 800

#: Ticks between two scheduled news slots, unless a template overrides it.
NEWS_PERIOD_TICKS = 4

#: Probability, in ppm, that a given tick also carries a pure noise slot.
NOISE_SLOT_PPM = 220_000


@dataclass(frozen=True)
class World:
    """A generated world: the scenario, its ground truth and its calendar.

    Attributes:
        scenario: The public, journalled description (:class:`ScenarioSpec`).
        latent: The hidden process every outcome was drawn from.
        outcomes: ``(market_id, outcome)`` pairs, sorted by ``market_id``.
        news_plan: The news calendar handed to the information engine (A04),
            sorted by ``(tick, market_ids)``.
    """

    scenario: ScenarioSpec
    latent: LatentProcess
    outcomes: tuple[tuple[str, Outcome], ...]
    news_plan: tuple[NewsPlanItem, ...]

    def outcome(self, market_id: str) -> Outcome:
        """Return the drawn outcome of ``market_id``.

        Args:
            market_id: Market id, ``M1``..``M8``.

        Returns:
            The outcome the oracle will publish.

        Raises:
            InvalidConfigError: If the market is unknown.
        """
        for candidate, outcome in self.outcomes:
            if candidate == market_id:
                return outcome
        raise InvalidConfigError("unknown market", market_id=market_id)

    def market_ids(self) -> tuple[str, ...]:
        """Return every market id, ascending by numeric suffix (section 2.3).

        Returns:
            The ids, for example ``("M1", "M2", "M3")``.
        """
        return sorted_ids([market.market_id for market in self.scenario.markets])


@dataclass(frozen=True)
class MarketBlueprint:
    """One market slot a template asks :func:`assemble_world` to realise.

    Attributes:
        question: Human readable question shown to agents and spectators.
        latent_key: Name of the latent variable driving this market. Unique
            inside a world; never exposed to an agent.
        design_probability_ppm: The template's honest unconditional probability
            of YES, ``1..999_999``. It sets the starting latent level and the
            centre the process reverts to, and it is what the public prior is
            derived from (FR-5.2.4).
        volatility_milli: Standard deviation of one tick's latent shock, in
            thousandths of the latent scale.
        mean_reversion_ppm: Pull toward the centre applied every tick, in ppm of
            the remaining distance. ``0`` makes the path a random walk.
        seasonal_amplitude_milli: Amplitude of a deterministic triangular
            seasonal component added to the centre (the harvest template's
            "processus latent saisonnier"). ``0`` disables it.
        seasonal_period_ticks: Period of that component, in ticks.
        tags: Free form ordered tags copied into :attr:`MarketSpec.tags`.
        allow_early_resolution: True when this slot may be drawn a resolution
            tick before ``T`` (FR-5.2.3).
    """

    question: str
    latent_key: str
    design_probability_ppm: int
    volatility_milli: int = 120
    mean_reversion_ppm: int = 80_000
    seasonal_amplitude_milli: int = 0
    seasonal_period_ticks: int = 0
    tags: tuple[str, ...] = ()
    allow_early_resolution: bool = False

    def __post_init__(self) -> None:
        """Validate the blueprint.

        Raises:
            InvalidConfigError: If a field is out of range.
        """
        if not 1 <= self.design_probability_ppm <= PPM_ONE - 1:
            raise InvalidConfigError(
                "design probability out of range",
                latent_key=self.latent_key,
                ppm=self.design_probability_ppm,
            )
        if self.volatility_milli < 0:
            raise InvalidConfigError("volatility must be >= 0", latent_key=self.latent_key)
        if not 0 <= self.mean_reversion_ppm <= PPM_ONE:
            raise InvalidConfigError("mean reversion must be in [0, 1e6] ppm", latent_key=self.latent_key)
        if self.seasonal_amplitude_milli < 0:
            raise InvalidConfigError("seasonal amplitude must be >= 0", latent_key=self.latent_key)
        if not self.question:
            raise InvalidConfigError("a market needs a question", latent_key=self.latent_key)


def check_market_count(*, template_id: str, n_markets: int, min_markets: int, max_markets: int) -> None:
    """Refuse a market count the template cannot express (FR-5.2.1, decision 36).

    A template raises instead of clamping: a silent clamp produces a world whose
    market count contradicts the journalled ``MatchConfig.n_markets``, and the
    runner's section 2.6 agreement check would then fail with a confusing
    message far from the cause.

    Args:
        template_id: Template asking for the check, for reporting.
        n_markets: Requested number of markets.
        min_markets: Template floor.
        max_markets: Template ceiling.

    Raises:
        InvalidConfigError: If ``n_markets`` is outside the template's range.
    """
    if not min_markets <= n_markets <= max_markets:
        raise InvalidConfigError(
            "template cannot express this market count",
            template_id=template_id,
            n_markets=n_markets,
            min_markets=min_markets,
            max_markets=max_markets,
        )


def correlation_groups(n_markets: int) -> tuple[tuple[int, ...], ...]:
    """Partition market indices into correlated groups (FR-5.2.1).

    The first group holds up to three markets (the "coherence cluster", for
    example "A wins", "turnout above 60 %" and "A wins the North"), then the
    remaining markets are paired. A single trailing market stays independent, so
    a world with four or more markets always contains both a correlated cluster
    and an uncorrelated control.

    Args:
        n_markets: Number of markets, ``>= 2``.

    Returns:
        Groups of market indices, each of size ``>= 2``, ascending.
    """
    head = min(3, n_markets)
    groups: list[tuple[int, ...]] = [tuple(range(head))]
    index = head
    while n_markets - index >= 2:
        groups.append((index, index + 1))
        index += 2
    return tuple(groups)


def _triangle(tick: int, period: int) -> float:
    """Return a triangular wave in ``[-1, 1]``, ``-1`` at phase zero.

    Integer arithmetic plus one correctly rounded division, so the seasonal
    component of a latent path is bit identical on every platform (no ``sin``).

    Args:
        tick: Tick index.
        period: Period in ticks. ``<= 0`` disables the wave.

    Returns:
        The wave value.
    """
    if period <= 0:
        return 0.0
    phase = tick % period
    numerator = 4 * phase - period if 2 * phase <= period else 3 * period - 4 * phase
    return numerator / period


def _resolution_ticks(
    *,
    blueprints: Sequence[MarketBlueprint],
    ticks_total: int,
    early_resolution_ppm: int,
    rng: RngTree,
) -> tuple[int, ...]:
    """Draw one resolution tick per market (FR-5.2.3).

    The default is the last tick ``T``. A slot that allows it may be drawn an
    earlier tick, which closes trading on that market mid match and frees its
    collateral. At least one market always resolves at ``T``, so a match never
    ends with nothing to settle at finalisation.

    Args:
        blueprints: Market slots, in market order.
        ticks_total: Horizon ``T``.
        early_resolution_ppm: Probability, in ppm, that an eligible slot
            resolves early.
        rng: The ``world`` sub-tree.

    Returns:
        One tick per market, in market order, each in ``1..T``.
    """
    generator = rng.fresh_substream("world.resolution")
    earliest = max(1, ticks_total // 3)
    latest = max(earliest, ticks_total - 2)
    ticks: list[int] = []
    for blueprint in blueprints:
        tick = ticks_total
        if (
            blueprint.allow_early_resolution
            and early_resolution_ppm > 0
            and bernoulli(generator, early_resolution_ppm / PPM_ONE)
        ):
            tick = randint(generator, earliest, latest)
        ticks.append(min(tick, ticks_total))
    if all(tick != ticks_total for tick in ticks):
        ticks[-1] = ticks_total
    return tuple(ticks)


def _latent_paths(
    *,
    blueprints: Sequence[MarketBlueprint],
    market_ids: Sequence[str],
    ticks_total: int,
    groups: Sequence[Sequence[int]],
    rho_milli: Sequence[int],
    rng: RngTree,
) -> tuple[tuple[int, ...], ...]:
    """Build one correlated latent path per market, tick ``0`` to ``T``.

    Args:
        blueprints: Market slots, in market order.
        market_ids: Market ids, in the same order.
        ticks_total: Horizon ``T``.
        groups: Correlated groups of market indices.
        rho_milli: Pairwise correlation of each group, in thousandths.
        rng: The ``world`` sub-tree.

    Returns:
        ``paths[market_index][tick]`` in signed thousandths.
    """
    latent_rng = rng.fresh_substream("world.latent")
    common: list[tuple[float, ...]] = [
        tuple(normal(latent_rng) for _ in range(ticks_total)) for _ in range(len(groups))
    ]
    group_of: dict[int, int] = {}
    for position, members in enumerate(groups):
        for member in members:
            group_of[member] = position

    paths: list[tuple[int, ...]] = []
    for index, blueprint in enumerate(blueprints):
        idio_rng = rng.fresh_substream(f"world.market.{market_ids[index]}")
        centre = float(milli_from_probability_ppm(blueprint.design_probability_ppm))
        kappa = blueprint.mean_reversion_ppm / PPM_ONE
        sigma = float(blueprint.volatility_milli)
        group_index = group_of.get(index)
        if group_index is None:
            weight_common, weight_own = 0.0, 1.0
        else:
            rho = rho_milli[group_index] / 1000.0
            weight_common, weight_own = math.sqrt(rho), math.sqrt(1.0 - rho)
        value = centre
        row = [round_half_up(value)]
        for tick in range(1, ticks_total + 1):
            shock = weight_own * normal(idio_rng)
            if group_index is not None:
                shock += weight_common * common[group_index][tick - 1]
            target = centre + blueprint.seasonal_amplitude_milli * _triangle(tick, blueprint.seasonal_period_ticks)
            value = value + kappa * (target - value) + sigma * shock
            row.append(round_half_up(value))
        paths.append(tuple(row))
    return tuple(paths)


def _priors(
    *,
    blueprints: Sequence[MarketBlueprint],
    prior_jitter_cents: int,
    rng: RngTree,
) -> tuple[int, ...]:
    """Draw the public opening prior of every market (FR-5.2.4).

    The prior is the template's design probability in cents, plus a small drawn
    offset: the crowd's opening opinion is close to the truth but not equal to
    it, which is what leaves an edge for an agent that reads its signals well.

    Args:
        blueprints: Market slots, in market order.
        prior_jitter_cents: Maximum absolute offset in cents, ``>= 0``.
        rng: The ``world`` sub-tree.

    Returns:
        One price in ``1..99`` per market, in market order.
    """
    generator = rng.fresh_substream("world.prior")
    priors: list[int] = []
    for blueprint in blueprints:
        base = round_half_up(blueprint.design_probability_ppm / 10_000)
        offset = 0
        if prior_jitter_cents > 0:
            offset = randint(generator, -prior_jitter_cents, prior_jitter_cents)
        priors.append(clamp_price(base + offset))
    return tuple(priors)


def _outcomes(
    *,
    market_ids: Sequence[str],
    blueprints: Sequence[MarketBlueprint],
    resolution_ticks: Sequence[int],
    groups: Sequence[Sequence[int]],
    rho_milli: Sequence[int],
    latent: LatentProcess,
    rng: RngTree,
) -> tuple[tuple[str, Outcome], ...]:
    """Draw the outcome of every market from its own latent probability.

    Two properties have to hold at once and the coupling below is what buys
    both.

    *FR-5.2.2*: each market's outcome is a Bernoulli variable whose parameter is
    exactly ``probability_ppm`` at its resolution tick, so the YES frequency of
    that market over many seeds converges to the mean of that probability.

    *FR-5.2.1*: markets of the same group also have to be correlated **as
    events**, not only as prices. Correlating the latent paths alone is not
    enough: the terminal coin flip carries a variance of ``p(1 - p)``, which
    dilutes a latent correlation of 0.6 down to an outcome correlation near
    0.04, and "A wins" and "A carries the North" then resolve almost
    independently, which no coherence trade could ever have exploited. Each
    group therefore draws one shared resolution uniform and each member uses it
    with probability ``rho`` (and its own uniform otherwise). By the law of
    total probability the marginal stays exactly ``Bernoulli(p_i)``, so
    FR-5.2.2 is untouched, while the joint distribution becomes genuinely
    dependent.

    Args:
        market_ids: Market ids, ascending.
        blueprints: Market slots, in the same order.
        resolution_ticks: Resolution tick of each market, same order.
        groups: Correlated groups of market indices.
        rho_milli: Pairwise correlation of each group, in thousandths.
        latent: The built latent process.
        rng: The ``world`` sub-tree.

    Returns:
        ``(market_id, outcome)`` pairs, sorted by ``market_id``.
    """
    generator = rng.fresh_substream("world.outcome")
    shared = [randint(generator, 0, PPM_ONE - 1) for _ in groups]
    group_of: dict[int, int] = {}
    for position, members in enumerate(groups):
        for member in members:
            group_of[member] = position

    outcomes: list[tuple[str, Outcome]] = []
    for index, market_id in enumerate(market_ids):
        probability_ppm = latent.probability_ppm(blueprints[index].latent_key, resolution_ticks[index])
        group_index = group_of.get(index)
        draw = randint(generator, 0, PPM_ONE - 1)
        if group_index is not None and bernoulli(generator, rho_milli[group_index] / 1000.0):
            draw = shared[group_index]
        outcomes.append((market_id, Outcome.YES if draw < probability_ppm else Outcome.NO))
    return tuple(outcomes)


def _news_plan(
    *,
    market_ids: Sequence[str],
    ticks_total: int,
    groups: Sequence[Sequence[int]],
    resolution_ticks: Sequence[int],
    news_period: int,
    rng: RngTree,
) -> tuple[NewsPlanItem, ...]:
    """Build the news calendar (A03 to A04 handover).

    Three kinds of slot: a scheduled release about a whole correlated group
    every ``news_period`` ticks (a poll, a reading, a match day), a high impact
    slot the tick before a market resolves, and pure noise slots.

    Args:
        market_ids: Market ids, ascending.
        ticks_total: Horizon ``T``.
        groups: Correlated groups of market indices.
        resolution_ticks: Resolution tick of each market.
        news_period: Ticks between two scheduled releases, ``>= 1``.
        rng: The ``world`` sub-tree.

    Returns:
        The slots, sorted by ``(tick, market_ids)``.
    """
    generator = rng.fresh_substream("world.template")
    items: list[NewsPlanItem] = []
    period = max(1, news_period)
    for slot, tick in enumerate(range(period, ticks_total + 1, period)):
        members = groups[slot % len(groups)]
        ids = sorted_ids([market_ids[index] for index in members])
        impact = NewsImpact.MEDIUM if len(ids) > 1 else NewsImpact.LOW
        items.append(NewsPlanItem(tick=tick, market_ids=ids, impact=impact, is_noise=False))
    for index, resolution_tick in enumerate(resolution_ticks):
        items.append(
            NewsPlanItem(
                tick=max(1, resolution_tick - 1),
                market_ids=(market_ids[index],),
                impact=NewsImpact.HIGH,
                is_noise=False,
            )
        )
    for tick in range(1, ticks_total + 1):
        if not bernoulli(generator, NOISE_SLOT_PPM / PPM_ONE):
            continue
        target = randint(generator, 0, len(market_ids) - 1)
        items.append(
            NewsPlanItem(
                tick=tick,
                market_ids=(market_ids[target],),
                impact=NewsImpact.LOW,
                is_noise=True,
            )
        )
    items.sort(key=lambda item: (item.tick, item.market_ids, item.impact.value, item.is_noise))
    return tuple(items)


def assemble_world(
    *,
    template_id: str,
    template_version: str,
    seed: int,
    ticks_total: int,
    blueprints: Sequence[MarketBlueprint],
    rng: RngTree,
    notes: str = "",
    early_resolution_ppm: int = 0,
    news_period: int = NEWS_PERIOD_TICKS,
    prior_jitter_cents: int = 3,
) -> World:
    """Turn a template's blueprints into a complete, drawn world.

    Args:
        template_id: Template id, journalled in ``MatchStarted``.
        template_version: Template version, journalled with it. Bumping it is
            how a world generation rule legitimately moves a golden hash
            (section 10).
        seed: The match seed, copied into the scenario.
        ticks_total: Horizon ``T``.
        blueprints: Market slots, two to eight, in market order. Slot ``i``
            becomes market ``M{i + 1}``.
        rng: The ``world`` sub-tree, that is ``RngTree(seed).child("world")``.
        notes: Free form description for reports and the UI.
        early_resolution_ppm: Probability, in ppm, that a slot which allows it
            resolves before ``T`` (FR-5.2.3).
        news_period: Ticks between two scheduled news slots.
        prior_jitter_cents: Maximum absolute offset of a public prior from the
            design probability, in cents.

    Returns:
        The assembled :class:`World`.

    Raises:
        InvalidConfigError: If the horizon is under :data:`TICKS_MIN`, if the
            number of blueprints is outside ``2..8``, or if two blueprints
            share a latent key.
    """
    if ticks_total < TICKS_MIN:
        raise InvalidConfigError("ticks_total is too short for a world", ticks_total=ticks_total)
    if not MARKETS_MIN <= len(blueprints) <= MARKETS_MAX:
        raise InvalidConfigError("a world holds 2 to 8 markets", n=len(blueprints))
    keys = [blueprint.latent_key for blueprint in blueprints]
    if len(set(keys)) != len(keys):
        raise InvalidConfigError("duplicate latent key in a template", keys=keys)

    market_ids = tuple(make_market_id(index + 1) for index in range(len(blueprints)))
    groups = correlation_groups(len(blueprints))
    correlation_rng = rng.fresh_substream("world.correlation")
    rho_milli = tuple(randint(correlation_rng, RHO_MILLI_MIN, RHO_MILLI_MAX) for _ in groups)

    resolution = _resolution_ticks(
        blueprints=blueprints,
        ticks_total=ticks_total,
        early_resolution_ppm=early_resolution_ppm,
        rng=rng,
    )
    latent = LatentProcess(
        keys=tuple(keys),
        values_milli=_latent_paths(
            blueprints=blueprints,
            market_ids=market_ids,
            ticks_total=ticks_total,
            groups=groups,
            rho_milli=rho_milli,
            rng=rng,
        ),
    )
    priors = _priors(blueprints=blueprints, prior_jitter_cents=prior_jitter_cents, rng=rng)

    group_tag: dict[int, str] = {}
    for group_index, members in enumerate(groups):
        for member in members:
            group_tag[member] = f"g{group_index + 1}"
    markets = tuple(
        MarketSpec(
            market_id=market_ids[index],
            question=blueprint.question,
            prior_price=priors[index],
            resolution_tick=resolution[index],
            latent_key=blueprint.latent_key,
            correlation_group=group_tag.get(index, ""),
            tags=blueprint.tags,
        )
        for index, blueprint in enumerate(blueprints)
    )
    correlations = tuple(
        (market_ids[left], market_ids[right], rho_milli[group_index])
        for group_index, members in enumerate(groups)
        for position, left in enumerate(members)
        for right in members[position + 1 :]
    )
    scenario = ScenarioSpec(
        template_id=template_id,
        template_version=template_version,
        seed=seed,
        ticks_total=ticks_total,
        markets=markets,
        correlations=correlations,
        cancellations=(),
        talking_mode=False,
        liquidity_profile_name=LiquidityProfileName.STANDARD,
        held_out=False,
        notes=notes,
    )
    return World(
        scenario=scenario,
        latent=latent,
        outcomes=_outcomes(
            market_ids=market_ids,
            blueprints=blueprints,
            resolution_ticks=resolution,
            groups=groups,
            rho_milli=rho_milli,
            latent=latent,
            rng=rng,
        ),
        news_plan=_news_plan(
            market_ids=market_ids,
            ticks_total=ticks_total,
            groups=groups,
            resolution_ticks=resolution,
            news_period=news_period,
            rng=rng,
        ),
    )
