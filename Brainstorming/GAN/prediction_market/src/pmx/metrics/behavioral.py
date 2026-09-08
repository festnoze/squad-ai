"""The five behavioural descriptors and the archive axes (CONTRACTS_V2 section 12.5).

E5 fills a :class:`Descriptors`; O2 bins three of its fields into the MAP-Elites grid. The dataclass
travels between the two packages so that neither reads the phrase "turnover per market" twice and gets
two integers: ``n_markets_open`` in particular is a field of ``AgentResult`` (section 12.5) precisely so
that the projection and the archive divide by the same number.

Every descriptor is ``0`` when its denominator is ``0``. That is the whole reason ``turnover_ppm`` takes
``bankroll_cents`` and ``n_markets_open`` rather than a precomputed denominator: an agent that saw no
market has a zero denominator, and the caller must not be the one to remember it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from pmx.types import PPM_ONE, round_half_up

__all__ = (
    "ABSTENTION_BINS",
    "ARCHIVE_AXES",
    "CONTRARIAN_BINS",
    "Descriptors",
    "TURNOVER_BINS",
    "category_coverage_ppm",
    "contrarian_bp",
    "descriptors",
    "holding_horizon_bars",
    "signed_mean",
    "turnover_ppm",
)

#: The archive axis edges of section 12.5, as lower bounds. ``cell_key`` is O2's; the edges are contract,
#: so they are declared once here and O2 bins against them rather than restating four numbers.
TURNOVER_BINS: tuple[int, ...] = (0, 250_000, 1_000_000, 4_000_000)
CONTRARIAN_BINS: tuple[int, ...] = (-300, 0, 300)
ABSTENTION_BINS: tuple[int, ...] = (0, 100_000, 500_000)
ARCHIVE_AXES: tuple[str, ...] = ("turnover_ppm", "contrarian_bp", "abstention_ppm")


def signed_mean(total: int, n: int) -> int:
    """The mean of a signed integer total, rounded half **away from zero**, ``0`` when ``n == 0``.

    ``//`` on a signed ratio is banned by section 1.2 (it rounds toward minus infinity and would make a
    contrarian agent look more contrarian than a symmetric one), and ``bp_ratio`` rescales by
    ``BP_ONE``, which is wrong for a quantity that is already in basis points. This is the third case
    the contract names: same rounding rule, no rescaling.
    """
    if n == 0:
        return 0
    quotient, remainder = divmod(abs(total), n)
    if 2 * remainder >= n:
        quotient += 1
    return quotient if total >= 0 else -quotient


def turnover_ppm(*, turnover_cents: int, bankroll_cents: int, n_markets_open: int) -> int:
    """Gross cash moved per market, in parts per million of the bankroll (section 12.5)."""
    denominator = bankroll_cents * n_markets_open
    if denominator <= 0:
        return 0
    return round_half_up(PPM_ONE * turnover_cents, denominator)


def contrarian_bp(deviations_bp: Sequence[int]) -> int:
    """The mean of ``prob_ppm // 100 - last_price_bp`` over the agent's forecast bars, signed.

    The comparison price is the **as-of** price the agent saw (``market_priced.last_close_bp``), never
    the bar's own close: the close of bar ``t`` has not happened when the forecast is made, and using it
    would score the agent against a price it could not read (sections 5.4 and 12.5).
    """
    return signed_mean(sum(deviations_bp), len(deviations_bp))


def holding_horizon_bars(leg_lengths_bars: Sequence[int]) -> int:
    """The mean number of bars between opening a leg and flattening it, ``0`` when no leg closed."""
    if not leg_lengths_bars:
        return 0
    return round_half_up(sum(leg_lengths_bars), len(leg_lengths_bars))


def category_coverage_ppm(*, categories_traded: int, categories_open: int) -> int:
    """The share of the categories the agent saw that it actually traded, in parts per million."""
    if categories_open <= 0:
        return 0
    return round_half_up(PPM_ONE * categories_traded, categories_open)


@dataclass(frozen=True, slots=True)
class Descriptors:
    """The five descriptors of section 12.5: three archive axes and two reported numbers.

    The payload of ``candidate_scored.descriptors`` (section 9.4) is exactly :meth:`to_dict`.
    """

    turnover_ppm: int
    contrarian_bp: int
    abstention_ppm: int
    holding_horizon_bars: int
    category_coverage_ppm: int

    def to_dict(self) -> dict[str, int]:
        return {
            "turnover_ppm": self.turnover_ppm,
            "contrarian_bp": self.contrarian_bp,
            "abstention_ppm": self.abstention_ppm,
            "holding_horizon_bars": self.holding_horizon_bars,
            "category_coverage_ppm": self.category_coverage_ppm,
        }


def descriptors(
    *,
    turnover_cents: int,
    bankroll_cents: int,
    n_markets_open: int,
    deviations_bp: Sequence[int],
    abstention_ppm: int,
    leg_lengths_bars: Sequence[int],
    categories_traded: int,
    categories_open: int,
) -> Descriptors:
    """Build the five descriptors from the vectors the journal walk produced.

    ``abstention_ppm`` arrives already computed because it is the same integer section 12.3 reports on
    the leaderboard, and two spellings of one column is how two behaviourally identical agents end up in
    different archive cells (section 12.3's own argument against the keyword-only definition).
    """
    return Descriptors(
        turnover_ppm=turnover_ppm(
            turnover_cents=turnover_cents,
            bankroll_cents=bankroll_cents,
            n_markets_open=n_markets_open,
        ),
        contrarian_bp=contrarian_bp(deviations_bp),
        abstention_ppm=abstention_ppm,
        holding_horizon_bars=holding_horizon_bars(leg_lengths_bars),
        category_coverage_ppm=category_coverage_ppm(
            categories_traded=categories_traded, categories_open=categories_open
        ),
    )
