"""The reliability curve, the expected calibration error and the sharpness (CONTRACTS_V2 12.2, 17.5).

Calibration is the one forecast metric that is **decoupled from money by construction**: this module
imports nothing from execution, reads no fill, no fee and no balance, and the architecture test (rule 2)
fails the day it does. That is not tidiness. "Well calibrated" and "profitable" are different claims, and
an agent that is one and not the other is exactly what the arena is built to expose, so the two numbers
must not be able to contaminate each other through a shared import.

What it computes, per slice and never pooled across slices (17.5, ruling R161):

* the **reliability curve**: ``CALIBRATION_BINS = 10`` bins by ``prob_ppm // 100_000`` with the top bin
  taking ``PPM_ONE``, each reporting ``n``, ``mean_prob_ppm`` and ``yes_rate_ppm``;
* the **expected calibration error** ``ece_ppm``, the ``n``-weighted mean distance between a bin's stated
  probability and its realised rate;
* the **sharpness** ``sharpness_ppm``, the ``n``-weighted mean distance from ``500_000``, which says how
  far the agent is willing to leave the fence. A perfectly calibrated agent that says ``500_000`` on
  everything has ``ece_ppm == 0`` and ``sharpness_ppm == 0``, and reporting only the first would call it a
  good forecaster.

Two rules that look like details and are not:

* **Time weighting is not applied here.** Bins count forecasts, not bar lengths (12.2). This is stated so
  that nobody "fixes" the asymmetry with 12.1 later.
* **A tie is half a yes.** On a continuous kind the realisation is a sign in ``{-1, 0, 1}``, so the ledger
  stores ``n_yes_x2`` (an up adds ``2``, a flat realisation adds ``1``) and every rate reads ``n_yes_x2``
  over ``2 * n`` through the one spelling ``yes_rate_ppm`` below (ruling R194). A consumer computing
  ``n_yes / n`` on a continuous slice would be off by two or would silently drop every tie.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from pmx.types import CALIBRATION_BINS, PPM_ONE, CalibrationBinView, round_half_up

#: The width of one reliability bin, in ppm: ``100_000`` for the contract's ten deciles.
BIN_WIDTH_PPM = PPM_ONE // CALIBRATION_BINS

#: The probability a sharpness is measured from: the statement that says nothing.
SHARPNESS_CENTRE_PPM = PPM_ONE // 2

#: What one realisation adds to ``n_yes_x2`` (ruling R194): an up or a YES is 2, a flat return is 1.
YES_X2 = 2
FLAT_X2 = 1
NO_X2 = 0



def bin_of(prob_ppm: int) -> int:
    """The reliability bin of a probability: ``prob_ppm // 100_000``, with the top bin taking ``PPM_ONE``.

    ``PPM_ONE // 100_000`` is ``10``, one past the last bin, which is why the top bin has to be named: a
    forecast of exact certainty belongs with the ``[900_000, 1_000_000)`` ones and not in an eleventh bin.
    """
    if prob_ppm >= PPM_ONE:
        return CALIBRATION_BINS - 1
    if prob_ppm <= 0:
        return 0
    return prob_ppm // BIN_WIDTH_PPM


def yes_rate_ppm(*, n: int, n_yes_x2: int) -> int:
    """``round_half_up(PPM_ONE * n_yes_x2, 2 * n)``: the one spelling of a realised rate (ruling R194).

    Every consumer reads this function rather than a division of its own, so a tie counts as half a yes
    everywhere or nowhere, and ``n == 0`` reports ``0`` instead of raising (ruling R2).
    """
    if n <= 0:
        return 0
    return round_half_up(PPM_ONE * n_yes_x2, 2 * n)


@dataclass(frozen=True, slots=True)
class CalibrationEntry:
    """One forecast to bin: its slice key, its probability and its realisation as an ``x2`` count.

    ``category`` is the market's category on a binary slice and the instrument's **kind** on a continuous
    one (17.5, ruling R161), which is what ``CalibrationBinView.category`` carries; ``horizon_bucket`` is
    one of ``HORIZON_BUCKETS`` on a binary and ``h<n>`` on a continuous horizon. Build these through
    ``binary_entry`` and ``continuous_entry`` rather than by hand, so the ``x2`` convention lives in one
    place.
    """

    category: str
    horizon_bucket: str
    prob_ppm: int
    yes_x2: int


def binary_entry(*, category: str, horizon_bucket: str, prob_ppm: int, outcome: int) -> CalibrationEntry:
    """One binary forecast: a YES adds ``2`` and a NO adds ``0``, so ``n_yes_x2 == 2 * n_yes`` (R194)."""
    return CalibrationEntry(
        category=category, horizon_bucket=horizon_bucket, prob_ppm=prob_ppm, yes_x2=YES_X2 if outcome == 1 else NO_X2
    )


def continuous_entry(
    *, kind: str, horizon_bars: int, up_probability_ppm: int, realised_sign: int
) -> CalibrationEntry:
    """One continuous horizon forecast: an up adds ``2``, a flat return ``1`` and a down ``0`` (R161)."""
    if realised_sign > 0:
        yes_x2 = YES_X2
    elif realised_sign < 0:
        yes_x2 = NO_X2
    else:
        yes_x2 = FLAT_X2
    return CalibrationEntry(
        category=kind, horizon_bucket=f"h{horizon_bars}", prob_ppm=up_probability_ppm, yes_x2=yes_x2
    )


@dataclass(frozen=True, slots=True)
class ReliabilityBin:
    """One bin of a reliability curve (section 12.2).

    ``CalibrationBinView`` (D1's, 8.3) carries the ledger's own five fields and travels in an observation;
    a reliability bin additionally carries the two numbers 12.2 asks a curve to report, ``mean_prob_ppm``
    and ``yes_rate_ppm``, which is why it is a type of its own rather than a second reading of the view.
    """

    bin: int
    n: int
    n_yes_x2: int
    mean_prob_ppm: int
    yes_rate_ppm: int

    @property
    def n_yes(self) -> int:
        """The whole-yes count of the ledger: ``n_yes_x2 // 2`` (ruling R194)."""
        return self.n_yes_x2 // 2

    def to_dict(self) -> dict[str, int]:
        return {
            "bin": self.bin,
            "n": self.n,
            "n_yes": self.n_yes,
            "n_yes_x2": self.n_yes_x2,
            "mean_prob_ppm": self.mean_prob_ppm,
            "yes_rate_ppm": self.yes_rate_ppm,
        }


@dataclass(frozen=True, slots=True)
class CalibrationSlice:
    """The calibration of one ``(category, horizon_bucket)`` slice: ten bins, an ECE and a sharpness."""

    category: str
    horizon_bucket: str
    n: int
    ece_ppm: int
    sharpness_ppm: int
    bins: tuple[ReliabilityBin, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "category": self.category,
            "horizon_bucket": self.horizon_bucket,
            "n": self.n,
            "ece_ppm": self.ece_ppm,
            "sharpness_ppm": self.sharpness_ppm,
            "bins": [item.to_dict() for item in self.bins],
        }

    def bin_views(self) -> tuple[CalibrationBinView, ...]:
        """The slice's non-empty bins as ``CalibrationBinView``s, which is what 8.3 and 12.11 carry.

        Empty bins are dropped here and only here: a curve reports all ten so that its shape is fixed
        (12.2), while a view travels inside an observation and inside ``AgentResult``, where nine rows of
        zeros per slice would be nine rows of nothing.
        """
        return tuple(
            _make_bin_view(
                category=self.category, horizon_bucket=self.horizon_bucket, bin_index=item.bin, n=item.n,
                n_yes_x2=item.n_yes_x2,
            )
            for item in self.bins
            if item.n > 0
        )


def _make_bin_view(
    *, category: str, horizon_bucket: str, bin_index: int, n: int, n_yes_x2: int
) -> CalibrationBinView:
    """Build D1's view with ``n_yes_x2`` beside ``n_yes`` (ruling R194): a tie is half a yes."""
    return CalibrationBinView(
        category=category,
        horizon_bucket=horizon_bucket,
        bin=bin_index,
        n=n,
        n_yes=n_yes_x2 // 2,
        n_yes_x2=n_yes_x2,
    )


def reliability_bins(entries: Sequence[CalibrationEntry]) -> tuple[ReliabilityBin, ...]:
    """The ten bins of section 12.2, always all ten, ascending.

    An empty bin reports ``n: 0`` with every other field ``0`` (ruling R2): nine of ten bins are empty for
    ``market_follower`` on a single market, so the empty bin is the common case and not the edge one.
    """
    counts = [0] * CALIBRATION_BINS
    sums = [0] * CALIBRATION_BINS
    yes_x2 = [0] * CALIBRATION_BINS
    for entry in entries:
        index = bin_of(entry.prob_ppm)
        counts[index] += 1
        sums[index] += entry.prob_ppm
        yes_x2[index] += entry.yes_x2
    bins: list[ReliabilityBin] = []
    for index in range(CALIBRATION_BINS):
        n = counts[index]
        bins.append(
            ReliabilityBin(
                bin=index,
                n=n,
                n_yes_x2=yes_x2[index],
                mean_prob_ppm=round_half_up(sums[index], n) if n > 0 else 0,
                yes_rate_ppm=yes_rate_ppm(n=n, n_yes_x2=yes_x2[index]),
            )
        )
    return tuple(bins)


def ece_ppm(bins: Sequence[ReliabilityBin]) -> int:
    """``sum(n_bin * abs(mean_prob - yes_rate)) // n_total``, and ``0`` on an empty slice (12.2)."""
    total = sum(item.n for item in bins)
    if total <= 0:
        return 0
    return sum(item.n * abs(item.mean_prob_ppm - item.yes_rate_ppm) for item in bins) // total


def sharpness_ppm(bins: Sequence[ReliabilityBin]) -> int:
    """``sum(n_bin * abs(mean_prob - 500_000)) // n_total``, and ``0`` on an empty slice (12.2)."""
    total = sum(item.n for item in bins)
    if total <= 0:
        return 0
    return sum(item.n * abs(item.mean_prob_ppm - SHARPNESS_CENTRE_PPM) for item in bins) // total


def calibration_slice(
    entries: Sequence[CalibrationEntry], *, category: str, horizon_bucket: str
) -> CalibrationSlice:
    """One slice's curve, ECE and sharpness over the entries it was handed (12.2)."""
    bins = reliability_bins(entries)
    return CalibrationSlice(
        category=category,
        horizon_bucket=horizon_bucket,
        n=len(entries),
        ece_ppm=ece_ppm(bins),
        sharpness_ppm=sharpness_ppm(bins),
        bins=bins,
    )


def calibration_table(entries: Sequence[CalibrationEntry]) -> tuple[CalibrationSlice, ...]:
    """One slice per ``(category, horizon_bucket)``, sorted by that key, pooling nothing (17.5, R161).

    Nothing is pooled across kinds or horizons, which is why the table is a tuple of slices and not one
    curve with a key column: a BTCUSDT one-bar direction and a Kalshi thirty-day resolution are not
    comparable statements, and a single ECE over both would be a number about nothing.

    The order is the sorted key rather than the order the entries arrived in, because an output that
    reaches a file or an event is in a canonical order and never in a dict's insertion order (section 3).
    """
    grouped: dict[tuple[str, str], list[CalibrationEntry]] = {}
    for entry in entries:
        grouped.setdefault((entry.category, entry.horizon_bucket), []).append(entry)
    slices: list[CalibrationSlice] = []
    for category, horizon_bucket in sorted(grouped):
        slices.append(
            calibration_slice(grouped[(category, horizon_bucket)], category=category, horizon_bucket=horizon_bucket)
        )
    return tuple(slices)


def calibration_bin_views(slices: Sequence[CalibrationSlice]) -> tuple[CalibrationBinView, ...]:
    """Every slice's non-empty bins, flattened in slice then bin order: ``AgentResult.calibration``."""
    views: list[CalibrationBinView] = []
    for item in slices:
        views.extend(item.bin_views())
    return tuple(views)
