"""Calibration metrics: Brier score and reliability curves (PRD 7.2, CONTRACTS 7.17, A16).

This module is one half of AC-P4. It reads exactly one row family of the
projection, ``predictions`` (the ``PredictionRecorded`` events), plus the
realised ``outcomes``, and it cannot see a trade, an order, a settlement or an
equity series. :mod:`pxe.metrics.performance` is the mirror image: it reads the
executions and the outcomes and cannot see a declared probability. Neither score
enters the computation of the other, which is the PRD section 7.2 anti hacking
principle stated structurally rather than by convention, and
``tests/test_metrics_decoupling.py`` proves it by mutating one event family at a
time.

**The Brier score, exactly as section 9 defines it.** A uniform mean of
``brier_term_ppm(p_declared, outcome)`` over the ``PredictionRecorded`` events of
one agent, carried values (FR-6.2.4) included. Nothing is recomputed and nothing
is inferred: **one event, one term**, and the denominator is the number of those
events, reported as ``n_terms``.

**The resolution tick boundary, which is where an off-by-one would live.** By
CONTRACTS section 5.0 a market whose ``resolution_tick`` is ``r`` is open and
tradable for the whole of tick ``r`` and is resolved in P1 of tick ``r + 1``, so
the runner emits a ``PredictionRecorded`` for it on ticks ``1..r`` **inclusive**.
The resolution tick term, which is the most informative one and the one PRD
section 7.2 asks for ("un marche cesse de compter **apres** son tick de
resolution"), is therefore present, and for an agent that played every tick::

    n_terms == sum over markets of resolution_tick

This module gets that boundary for free and must keep it that way: it counts
events and never derives a tick range from ``resolution_ticks``. Deriving one
would reintroduce the off-by-one the contract spent a section removing, and it
would also silently misreport a frozen agent, whose predictions stop at its
freeze tick, and an agent facing zero open markets, which produces no term at
all that tick (both are legal, section 9).

**A market that never resolved has no term.** A cancelled market (FR-5.4.5) has
no outcome, so ``(p - y)^2`` is not defined for it and its rows are excluded from
both the numerator and the denominator. That is the one place where "one event,
one term" cannot be taken literally, because the contract does not give a ``y``;
see the CONTRACT ISSUES note of this work package.
"""

from __future__ import annotations

from dataclasses import dataclass

from pxe.errors import InvalidConfigError
from pxe.metrics.projection import MatchProjection, PredictionRow
from pxe.types import (
    DEFAULT_PREDICTION_PPM,
    PPM_ONE,
    Outcome,
    brier_term_ppm,
)

__all__ = ["CalibrationMetrics", "compute_calibration", "reliability_curve"]

#: The Brier reported for an agent with **no** term at all, that is
#: ``n_terms == 0``. It is the score of the FR-6.2.4 default declaration
#: (0.50 ppm), which is the value the runner itself carries when an agent has
#: never declared anything, so an agent that produced no prediction is scored as
#: uninformative rather than as perfectly calibrated. A plain ``0`` would make
#: silence the best possible score, which is a reward hacking vector in a
#: document whose section 7.5 is about exactly that. Reports still normalise with
#: ``n_terms`` (section 9), so the two cases stay distinguishable.
UNMEASURED_BRIER_PPM: int = brier_term_ppm(DEFAULT_PREDICTION_PPM, Outcome.YES)

#: ``observed_yes_ppm`` of an **empty** reliability bin. An empty bin carries no
#: observation, and 0 is the only value that cannot be mistaken for one, because
#: ``n_predictions == 0`` sits next to it in the same row.
_EMPTY_BIN_OBSERVED_PPM = 0


@dataclass(frozen=True)
class CalibrationMetrics:
    """The PRD section 7.2 block for one ranked seat.

    Attributes:
        agent_id: The ranked seat.
        brier_ppm: Uniform mean of ``brier_term_ppm(p, outcome)`` over this
            seat's counted terms, in parts per million, rounded half up. Lower is
            better; ``0`` is a perfect forecaster and ``1_000_000`` a perfectly
            wrong one. :data:`UNMEASURED_BRIER_PPM` when ``n_terms == 0``.
        n_terms: The denominator: the number of ``PredictionRecorded`` events of
            this seat on a market that resolved. Section 9's identity
            ``n_terms == sum over markets of resolution_tick`` holds for a seat
            that played every tick of a fully resolved match.
        n_carried: How many of those terms were carried (FR-6.2.4) rather than
            declared this tick, including the 500 000 ppm default of a first
            tick. Always ``<= n_terms``, and it is what tells a report whether a
            good Brier came from forecasting or from silence.
    """

    agent_id: str
    brier_ppm: int
    n_terms: int
    n_carried: int


def compute_calibration(projection: MatchProjection) -> tuple[CalibrationMetrics, ...]:
    """Compute the PRD section 7.2 block of every ranked seat.

    Args:
        projection: The folded journal. Only ``predictions``, ``outcomes`` and
            ``agent_ids`` are read.

    Returns:
        One block per ranked seat, in canonical agent order (section 2.3), which
        is already the order of ``projection.agent_ids``.
    """
    return tuple(_metrics_for(projection, agent_id) for agent_id in projection.agent_ids)


def reliability_curve(
    projection: MatchProjection, agent_id: str, *, n_bins: int = 10
) -> tuple[tuple[int, int, int], ...]:
    """(bin_upper_ppm, n_predictions, observed_yes_ppm).

    The declared probabilities of one seat are bucketed into ``n_bins`` equal
    width bins of ``[0, 1_000_000]`` ppm, and each bin reports how often the
    market actually resolved YES. A well calibrated agent has
    ``observed_yes_ppm`` close to the middle of every populated bin, which is the
    diagonal the UI draws.

    The counted terms are exactly the ones :func:`compute_calibration` averages,
    so the curve and the Brier can never disagree about which predictions exist:
    same rows, same resolution tick boundary, same treatment of a carried value
    and of a market that never resolved.

    Exactly ``n_bins`` rows are always returned, empty bins included, so the
    curve has a fixed shape a plot can rely on and a consumer never has to guess
    which bucket a missing row belonged to.

    Bin membership is, exactly and without a float,
    ``min(n_bins - 1, p_yes_ppm * n_bins // 1_000_000)``: the bins are half open
    from below, the last one is closed so that ``p_yes_ppm == 1_000_000`` is
    counted rather than dropped, and ``bin_upper_ppm`` is
    ``(index + 1) * 1_000_000 // n_bins``, that is the bin's upper boundary,
    exclusive, and exact whenever ``n_bins`` divides ``1_000_000`` (it does for
    the default 10, giving the 100 000, 200 000, ..., 1 000 000 edges a plot
    expects).

    Args:
        projection: The folded journal.
        agent_id: A ranked seat of this match.
        n_bins: Number of equal width bins. Must be strictly positive.

    Returns:
        One ``(bin_upper_ppm, n_predictions, observed_yes_ppm)`` triple per bin,
        ascending by ``bin_upper_ppm``, the last edge being exactly
        ``1_000_000``. ``observed_yes_ppm`` is ``0`` for an empty bin.

    Raises:
        InvalidConfigError: If ``n_bins`` is not strictly positive, or if
            ``agent_id`` is not a ranked seat of this match. A silently empty
            curve would be published as a measurement.
    """
    if n_bins <= 0:
        raise InvalidConfigError("n_bins must be > 0", agent_id=agent_id, n_bins=n_bins)
    counted = counted_terms(projection, agent_id)
    totals = [0] * n_bins
    yes = [0] * n_bins
    for row, outcome in counted:
        index = _bin_index(row.p_yes_ppm, n_bins=n_bins)
        totals[index] += 1
        if outcome is Outcome.YES:
            yes[index] += 1
    return tuple(
        (
            _bin_upper_ppm(index, n_bins=n_bins),
            totals[index],
            _ratio_ppm(yes[index], totals[index]) if totals[index] else _EMPTY_BIN_OBSERVED_PPM,
        )
        for index in range(n_bins)
    )


def counted_terms(projection: MatchProjection, agent_id: str) -> tuple[tuple[PredictionRow, Outcome], ...]:
    """Return the Brier terms of one seat, each paired with its realised outcome.

    This is the one definition of "a term" in this module, shared by
    :func:`compute_calibration` and :func:`reliability_curve` so the two cannot
    drift into two different denominators. One row per ``PredictionRecorded`` of
    that seat on a market that resolved, in projection order, that is ascending
    by ``(tick, agent_id, market_id)``.

    Rows on a market that never resolved (a cancellation, FR-5.4.5, or a journal
    that stops early) are excluded: without an outcome there is no ``y`` and
    ``(p - y)^2`` does not exist.

    Args:
        projection: The folded journal.
        agent_id: A ranked seat of this match.

    Returns:
        The ``(row, outcome)`` pairs, possibly empty.

    Raises:
        InvalidConfigError: If ``agent_id`` is not a ranked seat of this match.
    """
    projection.agent_index(agent_id)  # Refuses a seat this match never had.
    resolved = dict(projection.outcomes)
    return tuple(
        (row, resolved[row.market_id])
        for row in projection.predictions
        if row.agent_id == agent_id and row.market_id in resolved
    )


def brier_ppm_of(terms: tuple[tuple[PredictionRow, Outcome], ...]) -> int:
    """Return the uniform mean Brier of already counted terms, in ppm.

    Args:
        terms: What :func:`counted_terms` returned.

    Returns:
        The mean of ``brier_term_ppm(p, outcome)``, rounded half up, or
        :data:`UNMEASURED_BRIER_PPM` when there is no term.
    """
    if not terms:
        return UNMEASURED_BRIER_PPM
    total = sum(brier_term_ppm(row.p_yes_ppm, outcome) for row, outcome in terms)
    return _mean_half_up(total, len(terms))


def _metrics_for(projection: MatchProjection, agent_id: str) -> CalibrationMetrics:
    """Build the calibration block of one seat.

    Args:
        projection: The folded journal.
        agent_id: The ranked seat.

    Returns:
        Its :class:`CalibrationMetrics`.
    """
    terms = counted_terms(projection, agent_id)
    return CalibrationMetrics(
        agent_id=agent_id,
        brier_ppm=brier_ppm_of(terms),
        n_terms=len(terms),
        n_carried=sum(1 for row, _outcome in terms if row.carried),
    )


def _bin_index(p_yes_ppm: int, *, n_bins: int) -> int:
    """Return the reliability bin of one declared probability.

    Args:
        p_yes_ppm: Declared probability in ppm, in ``[0, 1_000_000]``.
        n_bins: Number of equal width bins, strictly positive.

    Returns:
        The 0 based bin index. ``p_yes_ppm == 1_000_000`` lands in the last bin
        rather than in a phantom bin past the end.
    """
    return min(n_bins - 1, (p_yes_ppm * n_bins) // PPM_ONE)


def _bin_upper_ppm(index: int, *, n_bins: int) -> int:
    """Return the upper boundary of one reliability bin, in ppm.

    The boundary is exclusive (the last bin is closed instead, so a declaration
    of exactly ``1_000_000`` ppm is counted), and it is exact whenever ``n_bins``
    divides ``1_000_000``.

    Args:
        index: 0 based bin index.
        n_bins: Number of equal width bins, strictly positive.

    Returns:
        ``(index + 1) * 1_000_000 // n_bins``, which is exactly ``1_000_000`` for
        the last bin whatever ``n_bins`` is.
    """
    return ((index + 1) * PPM_ONE) // n_bins


def _mean_half_up(total: int, count: int) -> int:
    """Return ``total / count`` rounded half up, without a float.

    Both arguments are non negative here (a Brier term is in ``[0, 1_000_000]``
    and a count is a cardinality), so half up and half away from zero coincide
    and no signed division asymmetry can appear (section 2.1).

    Args:
        total: Non negative numerator.
        count: Strictly positive denominator.

    Returns:
        The rounded mean.

    Raises:
        InvalidConfigError: If ``count`` is not strictly positive.
    """
    if count <= 0:
        raise InvalidConfigError("mean denominator must be > 0", count=count)
    return (2 * total + count) // (2 * count)


def _ratio_ppm(part: int, whole: int) -> int:
    """Return ``part / whole`` in parts per million, rounded half up.

    Args:
        part: Non negative numerator.
        whole: Strictly positive denominator.

    Returns:
        The ratio in ppm, in ``[0, 1_000_000]``.

    Raises:
        InvalidConfigError: If ``whole`` is not strictly positive.
    """
    return _mean_half_up(part * PPM_ONE, whole)
