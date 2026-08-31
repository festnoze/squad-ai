"""Noise models: how an observation deviates from the latent truth (A04).

Everything here happens in **latent space**, the signed ``_milli`` scale the
world's :class:`pxe.world.latent.LatentProcess` is expressed in, and only the
last step converts to a probability. That order matters and is not cosmetic:

* the latent to probability map is an algebraic sigmoid, so adding noise on the
  probability side would compress it near ``0`` and ``1`` and make a signal
  about a near certain market *more* precise than a signal about a coin flip,
  which is the opposite of the truth;
* a Gaussian perturbation of the latent value is exactly the observation model a
  Kalman style update inverts, so a scripted Bayesian agent (FR-5.3.1) can
  actually exploit :attr:`pxe.types.Signal.precision_ppm` instead of guessing
  what it means.

No draw here touches a clock or the ``random`` module state: every function
takes the ``random.Random`` its caller obtained from a registered
:class:`pxe.rng.RngTree` substream, and only ``getrandbits`` derived helpers of
:mod:`pxe.rng` are used (CONTRACTS section 3.2).

Nothing in this module is part of the public API of CONTRACTS section 7.6: it is
the private machinery :mod:`pxe.info.engine` and :mod:`pxe.info.profiles` share.
"""

from __future__ import annotations

import random

from pxe.errors import InvalidConfigError
from pxe.rng import normal
from pxe.types import PPM_ONE, round_half_up
from pxe.world.latent import LATENT_SCALE_MILLI, milli_from_probability_ppm, probability_ppm_from_milli

__all__ = [
    "BASE_SIGNAL_SIGMA_MILLI",
    "BASE_PUBLIC_SIGMA_MILLI",
    "PURE_NOISE_SIGMA_MILLI",
    "FOCUS_NOISE_SCALE_PPM",
    "OUTSIDE_FOCUS_NOISE_SCALE_PPM",
    "DELAY_SIGMA_PENALTY_MILLI",
    "SIGMA_MIN_MILLI",
    "SIGMA_MAX_MILLI",
    "MILLI_PROBABILITY_ONE",
    "THRESHOLD_STEP_MILLI",
    "scaled_sigma_milli",
    "noisy_latent_milli",
    "pure_noise_latent_milli",
    "precision_ppm_for_sigma",
    "sigma_milli_for_precision",
    "probability_milli_from_latent",
    "latent_milli_from_probability_milli",
    "direction_milli",
    "threshold_milli",
]

#: Standard deviation, in latent ``_milli``, of a nominal private signal. The
#: stationary spread of a template latent path is a few hundred ``_milli``, so a
#: signal at this level is informative without being an oracle.
BASE_SIGNAL_SIGMA_MILLI = 200

#: Standard deviation, in latent ``_milli``, of a public news reading. Public
#: information is deliberately coarser than a private signal: that gap is the
#: edge FR-5.3.1 measures.
BASE_PUBLIC_SIGMA_MILLI = 380

#: Spread of a **pure noise** observation. Such an observation is drawn around
#: the neutral latent value and is statistically independent of the truth, so it
#: carries exactly zero information (PRD section 5.3, "certaines sont du bruit
#: pur"). It is wide on purpose: a narrow noise item would look like a precise
#: reading and mislead more than it should.
PURE_NOISE_SIGMA_MILLI = 900

#: Noise multiplier applied on a specialist's focus market (FR-5.3.2). Below
#: ``1_000_000``: the specialist sees its own event more sharply than anybody.
FOCUS_NOISE_SCALE_PPM = 400_000

#: Noise multiplier applied to a specialist **outside** its focus. Above
#: ``1_000_000``: expertise is a trade off, not a free bonus, otherwise the
#: Latin square of FR-5.3.2 would be permuting one strictly better profile
#: across seats and the balance it buys would be meaningless.
OUTSIDE_FOCUS_NOISE_SCALE_PPM = 1_300_000

#: Extra standard deviation added per tick of :attr:`pxe.types.InfoProfile.delay_ticks`.
#: A delayed signal is stale, and staleness is uncertainty about *today*: the
#: latent has drifted since the observation was taken.
DELAY_SIGMA_PENALTY_MILLI = 30

#: Clamps on any computed sigma. The floor keeps a signal from becoming a
#: noiseless oracle, the ceiling keeps ``precision_ppm`` inside its range.
SIGMA_MIN_MILLI = 20
SIGMA_MAX_MILLI = 4_000

#: Full scale of a probability expressed in thousandths, which is the unit
#: :attr:`pxe.types.Signal.value_milli` uses for a ``POINT_ESTIMATE``.
MILLI_PROBABILITY_ONE = 1_000

#: Granularity of a ``THRESHOLD`` signal, in probability thousandths. A
#: threshold is a round number an agent can reason about ("above 60 percent"),
#: not a full precision reading dressed up as a bound.
THRESHOLD_STEP_MILLI = 100


def scaled_sigma_milli(base_sigma_milli: int, *, scale_ppm: int) -> int:
    """Scale a base standard deviation by a ppm multiplier, then clamp it.

    Args:
        base_sigma_milli: Nominal standard deviation in latent ``_milli``,
            ``>= 0``.
        scale_ppm: Multiplier in parts per million. ``1_000_000`` is the nominal
            level, below it sharpens the observation and above it blurs it.

    Returns:
        The scaled standard deviation, clamped to
        ``[SIGMA_MIN_MILLI, SIGMA_MAX_MILLI]``.

    Raises:
        InvalidConfigError: If either argument is negative.
    """
    if base_sigma_milli < 0:
        raise InvalidConfigError("sigma must be >= 0", base_sigma_milli=base_sigma_milli)
    if scale_ppm < 0:
        raise InvalidConfigError("noise scale must be >= 0", scale_ppm=scale_ppm)
    scaled = (base_sigma_milli * scale_ppm + PPM_ONE // 2) // PPM_ONE
    return min(SIGMA_MAX_MILLI, max(SIGMA_MIN_MILLI, scaled))


def noisy_latent_milli(rng: random.Random, *, truth_milli: int, sigma_milli: int) -> int:
    """Observe a latent value through Gaussian noise.

    Args:
        rng: Generator from a registered substream.
        truth_milli: The true latent value in signed thousandths.
        sigma_milli: Standard deviation of the observation error, ``>= 0``.

    Returns:
        The observed latent value in signed thousandths.

    Raises:
        InvalidConfigError: If ``sigma_milli`` is negative.
    """
    if sigma_milli < 0:
        raise InvalidConfigError("sigma must be >= 0", sigma_milli=sigma_milli)
    return truth_milli + round_half_up(normal(rng) * sigma_milli)


def pure_noise_latent_milli(rng: random.Random) -> int:
    """Draw an observation that is statistically independent of the truth.

    This is what "pure noise" means in PRD section 5.3: the item looks exactly
    like any other reading, its value is simply drawn around the neutral latent
    value and never sees the latent process. An agent cannot tell it apart from
    a genuine reading item by item, only in aggregate, which is the point.

    Args:
        rng: Generator from a registered substream.

    Returns:
        A latent value in signed thousandths, centred on ``0``.
    """
    return round_half_up(normal(rng) * PURE_NOISE_SIGMA_MILLI)


def precision_ppm_for_sigma(sigma_milli: int) -> int:
    """Turn an observation sigma into the self declared reliability of a signal.

    The map is ``s / (s + sigma)`` with ``s`` the latent scale, so precision is
    ``500_000`` when the noise equals the latent scale, tends to ``1_000_000``
    for a sharp observation and to ``0`` for a useless one. It is monotone
    decreasing in ``sigma_milli``, which is the only property an agent may rely
    on, and it is exactly invertible, which is what lets a Bayesian agent
    recover the variance it needs (FR-5.3.1).

    Args:
        sigma_milli: Standard deviation of the observation error, ``>= 0``.

    Returns:
        Reliability in parts per million, ``0..1_000_000``.

    Raises:
        InvalidConfigError: If ``sigma_milli`` is negative.
    """
    if sigma_milli < 0:
        raise InvalidConfigError("sigma must be >= 0", sigma_milli=sigma_milli)
    return min(PPM_ONE, (PPM_ONE * LATENT_SCALE_MILLI) // (LATENT_SCALE_MILLI + sigma_milli))


def sigma_milli_for_precision(precision_ppm: int) -> int:
    """Invert :func:`precision_ppm_for_sigma`.

    An agent reading :attr:`pxe.types.Signal.precision_ppm` needs the variance
    behind it, and the inverse is published rather than left for every consumer
    to re-derive from the docstring.

    Args:
        precision_ppm: Reliability in parts per million, ``1..1_000_000``.

    Returns:
        The standard deviation in latent ``_milli``, ``>= 0``.

    Raises:
        InvalidConfigError: If ``precision_ppm`` is outside ``1..1_000_000``.
    """
    if not 1 <= precision_ppm <= PPM_ONE:
        raise InvalidConfigError("precision out of range", precision_ppm=precision_ppm)
    return (LATENT_SCALE_MILLI * (PPM_ONE - precision_ppm)) // precision_ppm


def probability_milli_from_latent(value_milli: int) -> int:
    """Convert a latent value to a probability in thousandths.

    Args:
        value_milli: Latent value in signed thousandths.

    Returns:
        A probability in thousandths, ``0..1_000``.
    """
    ppm = probability_ppm_from_milli(value_milli)
    return min(MILLI_PROBABILITY_ONE, max(0, (ppm + 500) // MILLI_PROBABILITY_ONE))


def latent_milli_from_probability_milli(probability_milli: int) -> int:
    """Convert a probability in thousandths back to a latent value.

    The two extremes are unbounded under the inverse sigmoid, so they are pulled
    one thousandth inside the open interval rather than raising: a consumer
    inverting a published signal must never be handed an exception for a value
    the engine itself produced.

    Args:
        probability_milli: Probability in thousandths, ``0..1_000``.

    Returns:
        The latent value in signed thousandths.

    Raises:
        InvalidConfigError: If ``probability_milli`` is outside ``0..1_000``.
    """
    if not 0 <= probability_milli <= MILLI_PROBABILITY_ONE:
        raise InvalidConfigError("probability out of range", probability_milli=probability_milli)
    clamped = min(MILLI_PROBABILITY_ONE - 1, max(1, probability_milli))
    return milli_from_probability_ppm(clamped * MILLI_PROBABILITY_ONE)


def direction_milli(observed_milli: int) -> int:
    """Reduce an observation to a ``DIRECTION`` signal value.

    Args:
        observed_milli: The observed latent value in signed thousandths.

    Returns:
        ``+1_000`` when the observation is at or above the neutral latent value,
        ``-1_000`` otherwise, as :class:`pxe.types.Signal` documents.
    """
    return MILLI_PROBABILITY_ONE if observed_milli >= 0 else -MILLI_PROBABILITY_ONE


def threshold_milli(observed_milli: int) -> int:
    """Reduce an observation to a ``THRESHOLD`` signal value.

    The convention, which CONTRACTS section 7.6 leaves open and which is
    therefore stated here once: the **magnitude** is a probability level in
    thousandths and the **sign** is the direction of the bound, exactly as the
    sign of a ``DIRECTION`` value is its direction. A positive ``600`` reads
    "the probability is at least 60 percent", a negative ``-400`` reads "the
    probability is at most 40 percent". The level is rounded to
    :data:`THRESHOLD_STEP_MILLI` away from the observation, so the bound is
    always true of the observation itself and is never a full precision reading
    in disguise.

    Args:
        observed_milli: The observed latent value in signed thousandths.

    Returns:
        A signed threshold in probability thousandths, magnitude in
        ``[THRESHOLD_STEP_MILLI, 1_000 - THRESHOLD_STEP_MILLI]``.
    """
    probability_milli = probability_milli_from_latent(observed_milli)
    step = THRESHOLD_STEP_MILLI
    lowest = step
    highest = MILLI_PROBABILITY_ONE - step
    if probability_milli >= MILLI_PROBABILITY_ONE // 2:
        level = min(highest, max(lowest, (probability_milli // step) * step))
        return level
    level = min(highest, max(lowest, -(-probability_milli // step) * step))
    return -level
