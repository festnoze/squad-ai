"""The latent process: the hidden ground truth a market resolves against.

CONTRACTS section 7.5. One :class:`LatentProcess` holds every latent variable
of a world, quantised to signed thousandths (``_milli``, section 2.1) at every
tick from ``0`` to ``T`` inclusive. Agents never see it; news items and private
signals (A04) are noisy observations of it and the oracle (A08) reads it to
resolve a market.

**Why the probability map is integer only.** ``probability_ppm`` is called by
the world generator to draw an outcome, so it sits inside AC-P1. A logistic map
would call the platform ``exp``, which is not bit identical between glibc,
msvcrt and macOS (section 3.2), and a latent value landing one ulp from a
quantisation boundary would then flip an outcome on one machine and not on
another. The map used here is the algebraic sigmoid

    p = 1/2 + 1/2 * v / sqrt(v**2 + s**2)

evaluated with :func:`math.isqrt` and integer division only, so it is exact on
every platform. It is strictly increasing in ``v``, symmetric around ``v = 0``
(``p = 1/2``) and never reaches ``0`` or ``1``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from pxe.errors import InvalidConfigError

__all__ = ["LatentProcess"]

#: The ``s`` of the algebraic sigmoid documented in the module docstring, in
#: ``_milli``. A latent value of ``s`` maps to about 85.4 % and ``s / sqrt(3)``
#: (577) to exactly 75 %. It is the unit in which every template expresses its
#: volatility and its shocks.
LATENT_SCALE_MILLI = 1000

PPM_ONE = 1_000_000
PPM_HALF = 500_000


def _div_half_away(numerator: int, denominator: int) -> int:
    """Divide two integers, rounding halves away from zero.

    Neither ``//`` (which rounds toward minus infinity and so treats a gain and
    the mirror loss differently, section 2.1) nor the banned builtin ``round``
    may be used here.

    Args:
        numerator: Signed numerator.
        denominator: Strictly positive denominator.

    Returns:
        The rounded quotient.

    Raises:
        InvalidConfigError: If ``denominator`` is not strictly positive.
    """
    if denominator <= 0:
        raise InvalidConfigError("denominator must be > 0", denominator=denominator)
    sign = -1 if numerator < 0 else 1
    magnitude = abs(numerator)
    return sign * ((2 * magnitude + denominator) // (2 * denominator))


def probability_ppm_from_milli(value_milli: int) -> int:
    """Map a latent value to a probability in parts per million.

    Args:
        value_milli: Latent value in signed thousandths.

    Returns:
        An integer in ``[0, 1_000_000]``, strictly increasing in
        ``value_milli`` and equal to ``500_000`` at ``0``.
    """
    scale = LATENT_SCALE_MILLI
    # The radius is computed scaled by 10**6 so the exact integer square root
    # carries the same six digits of precision as the ppm result. Without the
    # scaling, floor(sqrt(v**2 + s**2)) loses up to one unit and the map drifts
    # by tens of ppm, which is enough to make the round trip through
    # milli_from_probability_ppm visibly lossy.
    distance = math.isqrt((value_milli * value_milli + scale * scale) * PPM_ONE * PPM_ONE)
    offset = _div_half_away(PPM_HALF * value_milli * PPM_ONE, distance)
    return min(PPM_ONE, max(0, PPM_HALF + offset))


def milli_from_probability_ppm(probability_ppm: int) -> int:
    """Invert :func:`probability_ppm_from_milli`.

    Templates express a market's design probability directly (``62 %`` of a
    candidate winning) and need the latent value that produces it.

    Args:
        probability_ppm: Probability in parts per million, ``1..999_999``.

    Returns:
        The latent value in signed thousandths.

    Raises:
        InvalidConfigError: If ``probability_ppm`` is outside ``1..999_999``,
            where the map is unbounded.
    """
    if not 1 <= probability_ppm <= PPM_ONE - 1:
        raise InvalidConfigError("design probability must be in [1, 999999] ppm", ppm=probability_ppm)
    centred = 2 * probability_ppm - PPM_ONE
    remainder = (PPM_ONE * PPM_ONE - centred * centred) * PPM_ONE * PPM_ONE
    return _div_half_away(LATENT_SCALE_MILLI * centred * PPM_ONE, math.isqrt(remainder))


@dataclass(frozen=True)
class LatentProcess:
    """Every latent variable of one world, at every tick from 0 to ``T``.

    Attributes:
        keys: Latent variable names, unique, in the order the world generator
            created them (that is the order of the markets they drive).
        values_milli: ``values_milli[key_index][tick]`` in signed thousandths,
            for ``tick`` in ``0..T``. Every row has the same length.
    """

    keys: tuple[str, ...]
    values_milli: tuple[tuple[int, ...], ...]

    def __post_init__(self) -> None:
        """Validate the shape of the process.

        Raises:
            InvalidConfigError: If there is no key, if a key is duplicated, if
                the number of rows differs from the number of keys, or if two
                rows have different lengths.
        """
        if not self.keys:
            raise InvalidConfigError("a latent process holds at least one key")
        if len(set(self.keys)) != len(self.keys):
            raise InvalidConfigError("duplicate latent key", keys=list(self.keys))
        if len(self.values_milli) != len(self.keys):
            raise InvalidConfigError(
                "one row of values per key",
                keys=len(self.keys),
                rows=len(self.values_milli),
            )
        lengths = {len(row) for row in self.values_milli}
        if len(lengths) != 1:
            raise InvalidConfigError("every latent row has the same length", lengths=sorted(lengths))
        if next(iter(lengths)) < 1:
            raise InvalidConfigError("a latent row holds at least tick 0")

    def _index(self, key: str) -> int:
        """Return the row index of ``key``.

        Args:
            key: Latent variable name.

        Returns:
            The index into :attr:`keys` and :attr:`values_milli`.

        Raises:
            InvalidConfigError: If ``key`` is unknown.
        """
        try:
            return self.keys.index(key)
        except ValueError as exc:
            raise InvalidConfigError("unknown latent key", key=key) from exc

    def value_milli(self, key: str, tick: int) -> int:
        """Return the latent value of ``key`` at ``tick``.

        A tick beyond the stored horizon returns the terminal value, so a
        caller resolving at the virtual tick ``T + 1`` (finalisation, section
        5.0) reads the same ground truth as a caller resolving at ``T``.

        Args:
            key: Latent variable name.
            tick: Tick, ``0`` is the pre match state.

        Returns:
            The value in signed thousandths.

        Raises:
            InvalidConfigError: If ``key`` is unknown or ``tick`` is negative.
        """
        if tick < 0:
            raise InvalidConfigError("tick must be >= 0", tick=tick)
        row = self.values_milli[self._index(key)]
        return row[min(tick, len(row) - 1)]

    def probability_ppm(self, key: str, tick: int) -> int:
        """Return the probability implied by ``key`` at ``tick``.

        Args:
            key: Latent variable name.
            tick: Tick, ``0`` is the pre match state.

        Returns:
            The probability of the YES outcome in parts per million.

        Raises:
            InvalidConfigError: If ``key`` is unknown or ``tick`` is negative.
        """
        return probability_ppm_from_milli(self.value_milli(key, tick))

    def final_probability_ppm(self, key: str) -> int:
        """Return the probability implied by ``key`` at the last stored tick.

        Args:
            key: Latent variable name.

        Returns:
            The probability of the YES outcome in parts per million.

        Raises:
            InvalidConfigError: If ``key`` is unknown.
        """
        row = self.values_milli[self._index(key)]
        return probability_ppm_from_milli(row[-1])
