"""Informational profiles: the three ways a seat is fed (A04, CONTRACTS 7.6).

PRD section 5.3 names exactly three profiles and FR-5.3.2 permutes them across
seats with a Latin square, so they have to be *different* without one of them
being strictly better: a permutation of one dominant profile would balance
nothing.

| Kind | What it buys | What it costs |
|---|---|---|
| ``GENERALIST`` | signals about any market, nominal noise | never sharp anywhere |
| ``SPECIALIST`` | very sharp on its focus, one signal per tick at least | blurrier than nominal elsewhere |
| ``DELAYED`` | sharper than nominal readings | every reading is ``delay_ticks`` old |

The numeric consequences of those three lines live in :mod:`pxe.info.noise`
(:data:`pxe.info.noise.FOCUS_NOISE_SCALE_PPM`,
:data:`pxe.info.noise.OUTSIDE_FOCUS_NOISE_SCALE_PPM`,
:data:`pxe.info.noise.DELAY_SIGMA_PENALTY_MILLI`) and are applied by
:class:`pxe.info.engine.InfoEngine`, not here: a profile is a frozen
description, never a behaviour.
"""

from __future__ import annotations

from collections.abc import Sequence

from pxe.errors import InvalidConfigError
from pxe.types import PPM_ONE, InfoProfile, InfoProfileKind, sorted_ids

__all__ = [
    "SIGNALS_MAX_PER_TICK",
    "DELAYED_DELAY_TICKS",
    "DELAYED_NOISE_SCALE_PPM",
    "build_profile",
    "default_profile_kinds",
]

#: PRD section 5.3: "chaque agent tire 0 a 2 signaux par tick". Two is the
#: ceiling for every profile and ``schemas/observation.v1.json`` allows up to
#: eight entries, so the schema can never be the binding constraint.
SIGNALS_MAX_PER_TICK = 2

#: How stale a ``DELAYED`` seat's readings are, in ticks. Two and not one: with
#: a single tick of delay the latent has barely moved and the profile would be
#: indistinguishable from ``GENERALIST`` inside one match, which would make
#: FR-5.3.2's permutation unobservable.
DELAYED_DELAY_TICKS = 2

#: Noise multiplier of a ``DELAYED`` seat. Below ``1_000_000``: the reading
#: itself is sharper (more time to check the facts), which is what makes the
#: profile a genuine trade off against its staleness rather than a handicap.
DELAYED_NOISE_SCALE_PPM = 700_000


def build_profile(
    kind: InfoProfileKind,
    *,
    market_ids: Sequence[str],
    focus_market_id: str | None = None,
) -> InfoProfile:
    """Build the canonical :class:`pxe.types.InfoProfile` of one profile kind.

    Args:
        kind: Profile family (FR-5.3.2).
        market_ids: Every market of the world, in any order. Used to validate
            ``focus_market_id`` and to pick the default focus.
        focus_market_id: For ``SPECIALIST``, the market the seat is expert on.
            Defaults to the first market in canonical order. Ignored, and
            refused when set, for the other two kinds, because a focus outside
            ``SPECIALIST`` would silently do nothing.

    Returns:
        The frozen profile.

    Raises:
        InvalidConfigError: If ``market_ids`` is empty, if ``focus_market_id``
            is not one of them, or if ``focus_market_id`` is supplied for a kind
            that has no focus.
    """
    ordered = sorted_ids(list(market_ids))
    if not ordered:
        raise InvalidConfigError("a profile needs at least one market", kind=str(kind))
    if focus_market_id is not None and focus_market_id not in ordered:
        raise InvalidConfigError(
            "focus market is not part of this world",
            focus_market_id=focus_market_id,
            market_ids=list(ordered),
        )
    if focus_market_id is not None and kind is not InfoProfileKind.SPECIALIST:
        raise InvalidConfigError(
            "only a specialist profile carries a focus market",
            kind=str(kind),
            focus_market_id=focus_market_id,
        )

    if kind is InfoProfileKind.SPECIALIST:
        focus = focus_market_id if focus_market_id is not None else ordered[0]
        return InfoProfile(
            kind=InfoProfileKind.SPECIALIST,
            focus_market_ids=(focus,),
            signals_min=1,
            signals_max=SIGNALS_MAX_PER_TICK,
            delay_ticks=0,
            noise_scale_ppm=PPM_ONE,
        )
    if kind is InfoProfileKind.DELAYED:
        return InfoProfile(
            kind=InfoProfileKind.DELAYED,
            focus_market_ids=(),
            signals_min=0,
            signals_max=SIGNALS_MAX_PER_TICK,
            delay_ticks=DELAYED_DELAY_TICKS,
            noise_scale_ppm=DELAYED_NOISE_SCALE_PPM,
        )
    return InfoProfile(
        kind=InfoProfileKind.GENERALIST,
        focus_market_ids=(),
        signals_min=0,
        signals_max=SIGNALS_MAX_PER_TICK,
        delay_ticks=0,
        noise_scale_ppm=PPM_ONE,
    )


def default_profile_kinds(n_agents: int) -> tuple[InfoProfileKind, ...]:
    """Return the default profile vector for ``n_agents`` seats.

    The vector is ``tuple(InfoProfileKind)`` cycled to length ``n_agents`` in
    **declaration order**, which is byte for byte what
    ``pxe.tournament.latin_square.expand_profile_kinds`` does (CONTRACTS section
    7.19, "FR-5.3.2 Latin square"). The two functions have to agree: A19 rotates
    this vector across seeds, and a differently ordered default here would make
    the rotation cover a different multiset than the one the report measures.
    Declaration order and not sorted order, so adding a fourth kind later
    changes the vector in one predictable place.

    Args:
        n_agents: Number of ranked seats, ``>= 1``.

    Returns:
        One kind per seat, in seat order.

    Raises:
        InvalidConfigError: If ``n_agents`` is under one.
    """
    if n_agents < 1:
        raise InvalidConfigError("a match has at least one seat", n_agents=n_agents)
    kinds = tuple(InfoProfileKind)
    return tuple(kinds[index % len(kinds)] for index in range(n_agents))
