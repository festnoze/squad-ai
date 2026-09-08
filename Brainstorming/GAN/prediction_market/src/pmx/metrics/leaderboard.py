"""The leaderboard: one row per slice of a run (CONTRACTS_V2 sections 12.10 and 12.11).

``build(projection)`` is a pure function of a :class:`~pmx.metrics.projection.RunProjection`, which is
itself a pure function of the journal, so a leaderboard is reproducible from ``journal.jsonl`` alone and
the UI can show the historical and the adversarial column side by side without re-running anything.

The row key of section 12.10 is ``(agent_id, kind, provider, horizon_bars, fold, category | "all",
hardness_tag | "all")``. ``kind`` is ``binary`` and ``horizon_bars`` is ``0`` until a continuous
instrument reaches a run (amendment C1b); ``provider`` and ``fold`` have no ``"all"`` value because
nothing is pooled across either (section 12.6).

The contamination hook stays a pure argument: the set of contaminated market ids arrives from the
caller, never from an import, so ``pmx.metrics`` never imports ``pmx.llm`` (section 11.5).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from pmx.errors import JournalError
from pmx.metrics.projection import AgentResult, PerMarket, RunProjection
from pmx.metrics.stats import Interval, bootstrap_lower_bound
from pmx.rng import RngTree
from pmx.types import RE_RUN_BACKTEST_ID, RE_RUN_EVOLUTION_ID, round_half_up

__all__ = ("LeaderboardRow", "build", "seed_of_run_id")

#: The value that stands for "every category" and "every hardness tag" in a row key.
ALL = "all"


@dataclass(frozen=True, slots=True)
class LeaderboardRow:
    """One slice of one agent (section 12.11).

    The field order differs from section 12.11's listing, which puts defaulted fields (``kind``,
    ``horizon_bars``, ``vendor``, ``n_units``, ``n_quantile_forecasts``, ``pinball_skill``) **before**
    required ones and is therefore not a dataclass Python can define. Every field, every name and every
    default is the contract's; only the order is legal. Reported as a contract issue.

    Nine columns are agent-level rather than slice-level: ``sharpe_milli``, ``max_drawdown_bp``,
    ``fill_ratio_ppm``, ``turnover_ppm``, ``abstention_ppm``, ``explicit_abstain_ppm``,
    ``category_coverage_ppm``, ``ece_ppm`` and ``ruined``. Section 12.3 defines all of them per agent
    per run (an equity series and a drawdown have no per-category slice), and the declared structures
    that cross into this module carry no per-slice reliability bins, so a per-slice ECE is not
    computable from a ``RunProjection``. Both facts are in the docstring rather than in a silently
    different number.

    ``n_quantile_forecasts`` is ``0`` on every row for the same reason: section 12.11 gives
    ``PerMarket`` the two pinball losses of a cell but not the count of the forecasts that stated a
    quantile, so the column is not computable from a ``RunProjection`` and is reported as a contract
    issue rather than approximated. ``vendor`` reads the row's ``provider``, which is what a binary
    provider's vendor is (17.1) and what a single-venue continuous slice carries.
    """

    agent_id: str
    provider: str
    fold: str
    category: str
    hardness_tag: str
    n_markets: int
    n_markets_traded: int
    n_markets_open: int
    brier_tw_micro: int
    skill: Interval
    pnl: Interval
    log_micronats: int
    ece_ppm: int
    sharpe_milli: int
    max_drawdown_bp: int
    fill_ratio_ppm: int
    turnover_ppm: int
    abstention_ppm: int
    explicit_abstain_ppm: int
    category_coverage_ppm: int
    ruined: bool
    n_clean: int | None
    verdict: str | None
    kind: str = "binary"
    horizon_bars: int = 0
    vendor: str = ""
    n_units: int = 0
    n_quantile_forecasts: int = 0
    pinball_skill: Interval | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "agent_id": self.agent_id,
            "provider": self.provider,
            "fold": self.fold,
            "category": self.category,
            "hardness_tag": self.hardness_tag,
            "n_markets": self.n_markets,
            "n_markets_traded": self.n_markets_traded,
            "n_markets_open": self.n_markets_open,
            "brier_tw_micro": self.brier_tw_micro,
            "skill": self.skill.to_dict(),
            "pnl": self.pnl.to_dict(),
            "log_micronats": self.log_micronats,
            "ece_ppm": self.ece_ppm,
            "sharpe_milli": self.sharpe_milli,
            "max_drawdown_bp": self.max_drawdown_bp,
            "fill_ratio_ppm": self.fill_ratio_ppm,
            "turnover_ppm": self.turnover_ppm,
            "abstention_ppm": self.abstention_ppm,
            "explicit_abstain_ppm": self.explicit_abstain_ppm,
            "category_coverage_ppm": self.category_coverage_ppm,
            "ruined": self.ruined,
            "n_clean": self.n_clean,
            "verdict": self.verdict,
            "kind": self.kind,
            "horizon_bars": self.horizon_bars,
            "vendor": self.vendor,
            "n_units": self.n_units,
            "n_quantile_forecasts": self.n_quantile_forecasts,
            "pinball_skill": None if self.pinball_skill is None else self.pinball_skill.to_dict(),
        }


def seed_of_run_id(run_id: str) -> int:
    """The seed a run id carries (section 2), so a leaderboard needs no argument the projection lacks.

    ``RunProjection`` carries ``run_id`` but no ``seed``, and the block bootstrap needs the run's
    ``RngTree`` (section 6.2). The id is ``r-<dataset8>-<seed>-<config8>``, so the seed is recoverable
    from the journal-derived id and the intervals of a rebuilt leaderboard are byte-identical to the
    original's. Reported as a contract issue: ``RunProjection`` could simply carry ``seed``.
    """
    if RE_RUN_BACKTEST_ID.fullmatch(run_id) is None and RE_RUN_EVOLUTION_ID.fullmatch(run_id) is None:
        raise JournalError("run id does not match section 2's format", run_id=run_id)
    return int(run_id.split("-")[2])


def build(
    projection: RunProjection,
    *,
    contaminated: Mapping[str, frozenset[str]] | None = None,
    tree: RngTree | None = None,
    resamples: int | None = None,
) -> tuple[LeaderboardRow, ...]:
    """Every leaderboard row of one run, sorted by the row key of section 12.10.

    Args:
        projection: The run's projection, rebuilt from its journal.
        contaminated: Contaminated market ids per key, from the caller (section 11.5). The declared
            mapping is keyed by **model** and a ``RunProjection`` carries no model per agent, so the
            key is read as an ``agent_id`` here; reported as a contract issue. An agent with no entry
            reports ``n_clean = None``.
        tree: The statistics tree, defaulting to ``RngTree(seed_of_run_id(run_id)).child("stats")``
            (a keyword-only extension under preamble rule 2, reported).
        resamples: Bootstrap resamples, defaulting to ``pmx.metrics.stats``'s own default (the same
            extension; a leaderboard over hundreds of slices is the one place the cost matters).

    Returns:
        One row per ``(agent_id, kind, provider, horizon_bars, fold, category, hardness_tag)`` slice
        that carries at least one scored market, plus the ``"all"`` rows of each. Every agent of the
        roster appears, and an agent with no scored market appears once with zeros rather than not at
        all (section 12's preamble).
    """
    stats_tree = tree if tree is not None else RngTree(seed_of_run_id(projection.run_id)).child("stats")
    rows: list[LeaderboardRow] = []
    for result in projection.agents:
        own = tuple(row for row in projection.per_market if row.agent_id == result.agent_id)
        contaminated_ids = None if contaminated is None else contaminated.get(result.agent_id)
        if not own:
            rows.append(
                _row(
                    result=result,
                    slice_rows=(),
                    provider="",
                    fold=projection.markets[0].fold if projection.markets else "all",
                    category=ALL,
                    hardness_tag=ALL,
                    contaminated_ids=contaminated_ids,
                    stats_tree=stats_tree,
                    resamples=resamples,
                )
            )
            continue
        keys = sorted(
            {(row.kind, row.provider, row.horizon_bars, row.fold) for row in own}
        )
        for kind, provider, horizon_bars, fold in keys:
            scoped = tuple(
                row
                for row in own
                if row.kind == kind
                and row.provider == provider
                and row.horizon_bars == horizon_bars
                and row.fold == fold
            )
            categories = [ALL, *sorted({row.category for row in scoped})]
            tags = [ALL, *sorted({tag for row in scoped for tag in row.hardness_tags})]
            for category in categories:
                for tag in tags:
                    slice_rows = tuple(
                        row
                        for row in scoped
                        if (category == ALL or row.category == category)
                        and (tag == ALL or tag in row.hardness_tags)
                    )
                    if not slice_rows:
                        continue
                    rows.append(
                        _row(
                            result=result,
                            slice_rows=slice_rows,
                            provider=provider,
                            fold=fold,
                            category=category,
                            hardness_tag=tag,
                            kind=kind,
                            horizon_bars=horizon_bars,
                            contaminated_ids=contaminated_ids,
                            stats_tree=stats_tree,
                            resamples=resamples,
                        )
                    )
    return tuple(
        sorted(
            rows,
            key=lambda row: (
                row.agent_id,
                row.kind,
                row.provider,
                row.horizon_bars,
                row.fold,
                row.category,
                row.hardness_tag,
            ),
        )
    )


def _bar_weighted(rows: Sequence[PerMarket], values: Sequence[int]) -> int:
    """The bar-weighted mean of a per-market score over a slice, ``0`` when the slice has no bar."""
    total_weight = sum(row.n_forecast_bars for row in rows)
    if total_weight == 0:
        return 0
    return round_half_up(
        sum(value * row.n_forecast_bars for row, value in zip(rows, values, strict=True)), total_weight
    )


def _row(
    *,
    result: AgentResult,
    slice_rows: Sequence[PerMarket],
    provider: str,
    fold: str,
    category: str,
    hardness_tag: str,
    kind: str = "binary",
    horizon_bars: int = 0,
    contaminated_ids: frozenset[str] | None,
    stats_tree: RngTree,
    resamples: int | None,
) -> LeaderboardRow:
    blocks = [row.block_key for row in slice_rows]
    skill_values = [row.skill_micro for row in slice_rows]
    pnl_values = [row.realised_pnl_cents for row in slice_rows]
    if resamples is None:
        skill = bootstrap_lower_bound(skill_values, blocks, rng=stats_tree)
        pnl = bootstrap_lower_bound(pnl_values, blocks, rng=stats_tree)
    else:
        skill = bootstrap_lower_bound(skill_values, blocks, rng=stats_tree, resamples=resamples)
        pnl = bootstrap_lower_bound(pnl_values, blocks, rng=stats_tree, resamples=resamples)
    pinball = None
    if kind != "binary" and slice_rows:
        pinball_values = [row.baseline_pinball_micro - row.pinball_micro for row in slice_rows]
        pinball = (
            bootstrap_lower_bound(pinball_values, blocks, rng=stats_tree)
            if resamples is None
            else bootstrap_lower_bound(pinball_values, blocks, rng=stats_tree, resamples=resamples)
        )
    n_clean = (
        None
        if contaminated_ids is None
        else sum(1 for row in slice_rows if row.market_id not in contaminated_ids)
    )
    return LeaderboardRow(
        agent_id=result.agent_id,
        provider=provider,
        fold=fold,
        category=category,
        hardness_tag=hardness_tag,
        n_markets=len(slice_rows),
        n_markets_traded=sum(1 for row in slice_rows if row.traded),
        n_markets_open=len({row.market_id for row in slice_rows}),
        brier_tw_micro=_bar_weighted(slice_rows, [row.agent_brier_tw_micro for row in slice_rows]),
        skill=skill,
        pnl=pnl,
        log_micronats=_bar_weighted(slice_rows, [row.log_micronats for row in slice_rows]),
        ece_ppm=result.ece_ppm,
        sharpe_milli=result.sharpe_milli,
        max_drawdown_bp=result.max_drawdown_bp,
        fill_ratio_ppm=result.fill_ratio_ppm,
        turnover_ppm=result.descriptors.turnover_ppm,
        abstention_ppm=result.abstention_ppm,
        explicit_abstain_ppm=result.explicit_abstain_ppm,
        category_coverage_ppm=result.descriptors.category_coverage_ppm,
        ruined=result.ruined,
        n_clean=n_clean,
        verdict=None,
        kind=kind,
        horizon_bars=horizon_bars,
        vendor=provider,
        n_units=len(slice_rows),
        pinball_skill=pinball,
    )
