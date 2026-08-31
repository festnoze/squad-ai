"""Automatic tournament reports (A23, CONTRACTS section 7.24, WBS T3.6).

The end of a tournament produces a Markdown **and** an HTML report with no
manual action: :class:`~pxe.tournament.orchestrator.TournamentOrchestrator`
calls :func:`write_report` as soon as this module is importable, and
``pxe report build`` calls it again on demand.

Everything published here is a **projection**. Nothing reads engine state: the
per match numbers are folded from ``runs/<match_id>/journal.jsonl`` through
:func:`pxe.metrics.projection.project`, the incidents come from the store's
``incident`` table (itself written from ``incidents.jsonl``), and the ratings,
costs and tasks come from the store. That is what makes a report reproducible
from the artefacts alone.

The five sections PRD T3.6 mandates (classement, deltas, couts, incidents, cout
de la liquidite) are fields of :class:`ReportSections` and not prose, so a test
can walk them. Three more product criteria ride on the same object: AC-P3 (the
report exists at all and is automatic), T5.6 (the reliability curves and the
published Brier versus PnL analysis) and AC-P5 (the train set and the held-out
set are reported separately, in two directories).

This module is a leaf: it imports :mod:`pxe.store`, :mod:`pxe.metrics`,
:mod:`pxe.types` and the three sibling modules of its own package that own the
report's data (``latin_square`` for the FR-5.3.2 balance, ``ratings`` for the
bootstrap interval), and nothing imports it.
"""

from __future__ import annotations

import html
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pxe.events import JOURNAL_ENCODING, JOURNAL_NEWLINE, Event, MatchStarted
from pxe.metrics.aggregate import compute_all
from pxe.metrics.calibration import reliability_curve
from pxe.metrics.projection import MatchProjection
from pxe.rng import RngTree
from pxe.store.db import Store
from pxe.tournament.latin_square import BalanceReport, verify_balance
from pxe.tournament.ratings import RatingService, bootstrap_ci
from pxe.types import (
    LIQUIDITY_PROFILES,
    PPM_ONE,
    Incident,
    IncidentKind,
    InfoProfileKind,
    MatchResult,
    RatingRecord,
    TournamentResult,
    bps_ratio,
    round_half_up,
    sorted_ids,
)

__all__ = [
    "REPORT_MARKDOWN_NAME",
    "REPORT_HTML_NAME",
    "HELDOUT_DIRNAME",
    "INITIAL_MU",
    "INITIAL_SIGMA",
    "SIGMA_SHRINK_MIN_MATCHES",
    "KPI_NAMES",
    "MANDATED_SECTIONS",
    "ReportSections",
    "build_sections",
    "render_markdown",
    "render_html",
    "write_report",
]

#: File names of the two artefacts, in the directory the caller names.
REPORT_MARKDOWN_NAME = "report.md"
REPORT_HTML_NAME = "report.html"

#: Sub-directory of ``out_dir`` receiving the held-out pair (AC-P5, T3.5).
HELDOUT_DIRNAME = "heldout"

#: TrueSkill prior of :class:`~pxe.tournament.ratings.RatingService`. The mu
#: delta of a harness is measured from it: a harness that never played sits
#: exactly on the prior and its delta is zero, which is the only reading of
#: "delta" that does not depend on who else entered the tournament.
INITIAL_MU: float = 25.0

#: Prior sigma of the same service, the denominator of ``sigma_shrink_ppm``.
INITIAL_SIGMA: float = 8.333

#: Matches a harness must have played before its sigma counts toward
#: ``sigma_shrink_ppm`` (PRD section 15: "after 20 matches").
SIGMA_SHRINK_MIN_MATCHES: int = 20

#: Substream the bootstrap resampling draws from (CONTRACTS section 3.3). The
#: root seed is a constant so two runs of ``pxe report build`` over the same
#: store publish the same interval: a report that moved between two renders of
#: the same data would be unusable as evidence.
_BOOTSTRAP_SUBSTREAM = "metrics.bootstrap"
_BOOTSTRAP_ROOT_SEED = 0

#: Line separator of both rendered documents. Both writers open their file
#: with newline=JOURNAL_NEWLINE, so the bytes on disk carry LF on every
#: platform (CONTRACTS section 4.2).
_NEWLINE: str = JOURNAL_NEWLINE

#: Number of reliability bins, the default of
#: :func:`pxe.metrics.calibration.reliability_curve`.
_RELIABILITY_BINS = 10

#: The seven PRD section 15 KPIs, in the order section 7.24 tabulates them.
KPI_NAMES: tuple[str, ...] = (
    "cost_per_match_usd_milli",
    "cost_per_tournament_usd_milli",
    "matches_per_night",
    "clean_completion_ppm",
    "sigma_shrink_ppm",
    "heldout_gain_mu_milli",
    "liquidity_cost_cents_per_match",
)

#: The five headings PRD T3.6 mandates, in English, exactly as both renderers
#: spell them. ``test_report.py::test_five_mandated_sections_present`` walks
#: this tuple against the two documents.
MANDATED_SECTIONS: tuple[str, ...] = (
    "Leaderboard",
    "Deltas",
    "Costs",
    "Incidents",
    "Cost of liquidity",
)


@dataclass(frozen=True)
class ReportSections:
    """The whole report as data, so a test walks fields and not prose.

    Attributes:
        title: Human readable title, already carrying the train or held-out
            marker.
        held_out: True when this is the held-out half of the pair (AC-P5).
        leaderboard: TrueSkill ranking, best ``mu`` first.
        deltas: ``(harness_key, mu_delta, ci_width)``. ``mu_delta`` is measured
            from :data:`INITIAL_MU`; ``ci_width`` is the width of the
            percentile bootstrap interval of that harness's per match
            ``pnl_bps`` (PRD section 7.3), ``0.0`` when it played nothing.
        costs_usd: ``(harness_key, provider cost)``, from the store.
        incidents: Integrity incidents of the reported matches.
        liquidity_cost_cents: ``(liquidity profile name, market maker PnL)``,
            the FR-5.8.5 cost of liquidity, one row per preset that played.
        calibration: ``(harness_key, brier_ppm, reliability curve)`` with the
            curve as ``(bin_upper_ppm, n, observed_yes_ppm)`` triples (T5.6).
        kpis: ``(name, value_ppm, unit)``, the seven of PRD section 15.
        profile_balance: The FR-5.3.2 Latin square residual, measured over the
            reported matches.
        brier_vs_pnl: ``(harness_key, brier_ppm, pnl_bps)``, the published
            decoupling analysis of T5.6.
    """

    title: str
    held_out: bool
    leaderboard: tuple[RatingRecord, ...]
    deltas: tuple[tuple[str, float, float], ...]
    costs_usd: tuple[tuple[str, float], ...]
    incidents: tuple[Incident, ...]
    liquidity_cost_cents: tuple[tuple[str, int], ...]
    calibration: tuple[tuple[str, int, tuple[tuple[int, int, int], ...]], ...]
    kpis: tuple[tuple[str, int, str], ...]
    profile_balance: BalanceReport
    brier_vs_pnl: tuple[tuple[str, int, int], ...]


@dataclass(frozen=True)
class _MatchView:
    """One reported match, already folded (private).

    Attributes:
        match_id: The match.
        harness_of: Ranked seat to harness key, from ``MatchStarted.agents``.
        profiles: ``(agent_id, kind)`` of every ranked seat, sorted by seat.
        projection: The folded journal.
        brier_ppm: Per ranked seat Brier score in ppm.
        n_terms: Per ranked seat Brier denominator.
        pnl_bps: Per ranked seat PnL in basis points.
        curves: Per ranked seat reliability curve.
        mm_pnl_cents: The match's cost of liquidity.
        liquidity_profile_name: The preset that produced it.
        technical: True when the match carries a technical incident.
    """

    match_id: str
    harness_of: Mapping[str, str]
    profiles: tuple[tuple[str, InfoProfileKind], ...]
    projection: MatchProjection
    brier_ppm: Mapping[str, int]
    n_terms: Mapping[str, int]
    pnl_bps: Mapping[str, int]
    curves: Mapping[str, tuple[tuple[int, int, int], ...]]
    mm_pnl_cents: int
    liquidity_profile_name: str
    technical: bool


# --------------------------------------------------------------------------
# Journal side helpers. Everything below reads the journal and nothing else.
# --------------------------------------------------------------------------
def _match_started_of(events: Sequence[Event]) -> MatchStarted:
    """Return the first event of a journal.

    Args:
        events: The journal, in file order.

    Returns:
        The :class:`~pxe.events.MatchStarted`.

    Raises:
        ValueError: If the journal holds none, which means it is not a journal.
    """
    for event in events:
        if isinstance(event, MatchStarted):
            return event
    raise ValueError("journal holds no match_started event")


def _harness_key_of(entry: Mapping[str, Any]) -> str:
    """Rebuild the harness key of one ``MatchStarted.agents`` entry.

    The journal carries ``harness_id``, ``harness_version`` and ``config_hash``
    and not the key itself, and section 2.2 spells the key as
    ``<harness_id>@<version>+<config_hash[:8]>``. Rebuilding it here is what
    lets a report group seats by brain without a database join, and it is the
    same string :func:`pxe.types.harness_key` produces from the three fields.

    Args:
        entry: One mapping of ``MatchStarted.agents``.

    Returns:
        The harness key.
    """
    digest = str(entry.get("config_hash", ""))
    return f"{entry['harness_id']}@{entry['harness_version']}+{digest[:8]}"


def _view_of(store: Store, result: MatchResult) -> _MatchView:
    """Fold one match into everything the report needs from it.

    Args:
        store: The projection database plus artefact directory.
        result: The match, as the runner returned it.

    Returns:
        The private view. Only the journal, the incident table and the metrics
        computed from the projection are read.
    """
    match_id = result.match_id
    events = store.load_journal(match_id)
    started = _match_started_of(events)
    projection = store.load_projection(match_id)
    metrics = compute_all(projection)
    ranked = {str(entry["agent_id"]): entry for entry in started.agents if bool(entry.get("ranked", True))}
    seats = sorted_ids(tuple(ranked))
    harness_of = {agent_id: _harness_key_of(ranked[agent_id]) for agent_id in seats}
    profiles = tuple((agent_id, InfoProfileKind(str(ranked[agent_id]["info_profile_kind"]))) for agent_id in seats)
    incidents = store.load_incidents(match_id=match_id)
    return _MatchView(
        match_id=match_id,
        harness_of=harness_of,
        profiles=profiles,
        projection=projection,
        brier_ppm={row.agent_id: row.brier_ppm for row in metrics.calibration},
        n_terms={row.agent_id: row.n_terms for row in metrics.calibration},
        pnl_bps={row.agent_id: row.pnl_bps for row in metrics.performance},
        curves={
            agent_id: reliability_curve(projection, agent_id, n_bins=_RELIABILITY_BINS)
            for agent_id in projection.agent_ids
        },
        mm_pnl_cents=int(result.mm_pnl_cents),
        liquidity_profile_name=str(result.scenario.liquidity_profile_name),
        technical=any(item.kind is IncidentKind.TECHNICAL for item in incidents),
    )


# --------------------------------------------------------------------------
# Section builders
# --------------------------------------------------------------------------
def _leaderboard(
    result: TournamentResult, views: Sequence[_MatchView], selected: Sequence[MatchResult]
) -> tuple[RatingRecord, ...]:
    """Return the ranking to publish for this half of the pair.

    When the report covers the whole tournament, and it played at least one
    match, the tournament's own leaderboard is published verbatim: recomputing it would be a second
    definition of the headline number, and an exhibition tournament
    deliberately has none (section 7.19). When it covers a subset (the AC-P5
    held-out half) the same :class:`~pxe.tournament.ratings.RatingService` is
    folded over that subset only, in playing order.

    Args:
        result: The finished tournament.
        views: The folded matches, aligned with ``selected``.
        selected: The matches this half reports on.

    Returns:
        The ranking, best ``mu`` first.
    """
    if selected and len(selected) == len(result.match_results):
        return tuple(result.ratings)
    service = RatingService()
    for view, match_result in zip(views, selected, strict=True):
        if not view.harness_of:
            continue
        service.update(match_result.rankings, harness_of=view.harness_of)
    return service.leaderboard()


def _pnl_bps_by_harness(views: Sequence[_MatchView]) -> dict[str, list[int]]:
    """Collect every per match, per seat ``pnl_bps`` under its harness key.

    Args:
        views: The folded matches.

    Returns:
        Harness key to the observations behind it, in playing order.
    """
    collected: dict[str, list[int]] = {}
    for view in views:
        for agent_id in view.projection.agent_ids:
            key = view.harness_of.get(agent_id)
            if key is None:
                continue
            collected.setdefault(key, []).append(int(view.pnl_bps.get(agent_id, 0)))
    return collected


def _deltas(
    leaderboard: Sequence[RatingRecord], observations: Mapping[str, Sequence[int]]
) -> tuple[tuple[str, float, float], ...]:
    """Build the ``(harness_key, mu_delta, ci_width)`` rows.

    ``ci_width`` is the width of the 95 % percentile bootstrap interval of the
    harness's per match ``pnl_bps``, which is the PRD section 7.3 requirement
    that every published comparison carries an interval. It is ``0.0`` for a
    harness with no observation, which is the honest answer rather than a
    fabricated band.

    Args:
        leaderboard: The ranking, best first.
        observations: Harness key to its ``pnl_bps`` observations.

    Returns:
        One row per leaderboard entry, in leaderboard order.
    """
    rows: list[tuple[str, float, float]] = []
    for record in leaderboard:
        values = observations.get(record.harness_key, ())
        width = 0.0
        if values:
            rng = RngTree(_BOOTSTRAP_ROOT_SEED).fresh_substream(_BOOTSTRAP_SUBSTREAM)
            low, high = bootstrap_ci([float(value) for value in values], rng=rng)
            width = high - low
        rows.append((record.harness_key, record.mu - INITIAL_MU, width))
    return tuple(rows)


def _liquidity_cost(views: Sequence[_MatchView]) -> tuple[tuple[str, int], ...]:
    """Sum the market maker PnL of the reported matches, per preset.

    Args:
        views: The folded matches.

    Returns:
        ``(profile name, mm_pnl_cents)`` in the fixed order of
        :data:`pxe.types.LIQUIDITY_PROFILES`, presets that never played omitted.
    """
    totals: dict[str, int] = {}
    for view in views:
        totals[view.liquidity_profile_name] = totals.get(view.liquidity_profile_name, 0) + view.mm_pnl_cents
    ordered = [str(profile.name) for profile in LIQUIDITY_PROFILES]
    rows = [(name, totals[name]) for name in ordered if name in totals]
    rows.extend((name, totals[name]) for name in sorted(totals) if name not in ordered)
    return tuple(rows)


def _weighted_brier_ppm(pairs: Sequence[tuple[int, int]]) -> int:
    """Aggregate per seat Brier scores weighted by their own denominators.

    A seat that produced ten terms and one that produced a hundred are not the
    same evidence, so the mean is weighted by ``n_terms``. That keeps the
    aggregate identical to the Brier of the pooled terms, which is what
    section 9 defines the score to be.

    Args:
        pairs: ``(brier_ppm, n_terms)`` per seat.

    Returns:
        The weighted mean in ppm, ``0`` when nothing was measured.
    """
    weight = sum(n for _ppm, n in pairs)
    if weight <= 0:
        return 0
    total = sum(ppm * n for ppm, n in pairs)
    return round_half_up(total / weight)


def _merge_curves(curves: Sequence[tuple[tuple[int, int, int], ...]]) -> tuple[tuple[int, int, int], ...]:
    """Pool several reliability curves of the same shape into one.

    Args:
        curves: One curve per seat, every one holding the same bins.

    Returns:
        The pooled curve, one row per bin, ``observed_yes_ppm`` re-weighted by
        the bin populations. Empty when there is nothing to pool.
    """
    if not curves:
        return ()
    edges = [upper for upper, _n, _obs in curves[0]]
    counts = [0] * len(edges)
    observed = [0] * len(edges)
    for curve in curves:
        for index, (_upper, n, obs) in enumerate(curve):
            if index >= len(counts):
                break
            counts[index] += n
            observed[index] += obs * n
    return tuple(
        (edges[index], counts[index], round_half_up(observed[index] / counts[index]) if counts[index] else 0)
        for index in range(len(edges))
    )


def _calibration(
    views: Sequence[_MatchView], keys: Sequence[str]
) -> tuple[tuple[str, int, tuple[tuple[int, int, int], ...]], ...]:
    """Build the T5.6 calibration block, one row per harness key.

    Args:
        views: The folded matches.
        keys: The harness keys to publish, in publication order.

    Returns:
        ``(harness_key, brier_ppm, reliability curve)`` rows.
    """
    scores: dict[str, list[tuple[int, int]]] = {}
    curves: dict[str, list[tuple[tuple[int, int, int], ...]]] = {}
    for view in views:
        for agent_id in view.projection.agent_ids:
            key = view.harness_of.get(agent_id)
            if key is None:
                continue
            scores.setdefault(key, []).append(
                (int(view.brier_ppm.get(agent_id, 0)), int(view.n_terms.get(agent_id, 0)))
            )
            curves.setdefault(key, []).append(view.curves.get(agent_id, ()))
    return tuple(
        (key, _weighted_brier_ppm(scores.get(key, ())), _merge_curves(tuple(curves.get(key, ())))) for key in keys
    )


def _brier_vs_pnl(
    calibration: Sequence[tuple[str, int, tuple[tuple[int, int, int], ...]]],
    observations: Mapping[str, Sequence[int]],
) -> tuple[tuple[str, int, int], ...]:
    """Publish the Brier against the PnL, per harness key (T5.6, AC-P4).

    The two numbers come from two disjoint families of events (section 9's
    decoupling rule), which is precisely why publishing them side by side is
    informative: a harness can be well calibrated and still lose money.

    Args:
        calibration: The calibration rows, already aggregated.
        observations: Harness key to its per match ``pnl_bps``.

    Returns:
        ``(harness_key, brier_ppm, pnl_bps)`` with ``pnl_bps`` the mean over
        the harness's matches, rounded half away from zero.
    """
    rows: list[tuple[str, int, int]] = []
    for key, brier_ppm, _curve in calibration:
        values = observations.get(key, ())
        mean_bps = bps_ratio(sum(values), len(values) * 10_000) if values else 0
        rows.append((key, brier_ppm, mean_bps))
    return tuple(rows)


def _sigma_shrink_ppm(store: Store, leaderboard: Sequence[RatingRecord]) -> int:
    """Median sigma after 20 matches over the prior sigma, in ppm.

    The series comes from :meth:`pxe.store.db.Store.load_rating_series`, which
    section 7.24 names as the source, so the KPI covers every version of every
    harness the store knows and not only the ones in this leaderboard.

    Args:
        store: The projection database.
        leaderboard: The published ranking, used only for the harness ids.

    Returns:
        The ratio in ppm, ``0`` when no harness has reached twenty matches.
    """
    harness_ids: list[str] = []
    for record in leaderboard:
        harness_id = record.harness_key.split("@", 1)[0]
        if harness_id not in harness_ids:
            harness_ids.append(harness_id)
    sigmas: list[float] = []
    for harness_id in harness_ids:
        for _key, _mu, sigma, matches in store.load_rating_series(harness_id):
            if matches >= SIGMA_SHRINK_MIN_MATCHES:
                sigmas.append(sigma)
    if not sigmas:
        return 0
    return round_half_up(statistics.median(sigmas) / INITIAL_SIGMA * PPM_ONE)


def _kpis(
    *,
    store: Store,
    result: TournamentResult,
    views: Sequence[_MatchView],
    leaderboard: Sequence[RatingRecord],
    costs_usd: Sequence[tuple[str, float]],
    liquidity_cost_cents: Sequence[tuple[str, int]],
) -> tuple[tuple[str, int, str], ...]:
    """Build the seven PRD section 15 KPIs, in :data:`KPI_NAMES` order.

    ``heldout_gain_mu_milli`` is reported as ``0``: section 7.24 names
    :mod:`pxe.evolve` through the store as its supplier, that package is not
    part of this work package and no store reader exposes the quantity. The
    replay API reports the same ``0`` for the same reason, so the two agree
    rather than inventing two different numbers. See CONTRACT ISSUES.

    Args:
        store: The projection database.
        result: The finished tournament.
        views: The folded matches of this half.
        leaderboard: The published ranking.
        costs_usd: Provider cost per harness key.
        liquidity_cost_cents: Market maker PnL per preset.

    Returns:
        ``(name, value_ppm, unit)`` rows.
    """
    n_matches = max(1, len(views))
    total_usd = (
        float(result.total_cost_usd)
        if len(views) == len(result.match_results)
        else sum(cost for _key, cost in costs_usd)
    )
    clean = sum(1 for view in views if not view.technical)
    mm_total = sum(cents for _name, cents in liquidity_cost_cents)
    return (
        ("cost_per_match_usd_milli", round_half_up(total_usd * 1000.0 / n_matches), "milli_usd"),
        ("cost_per_tournament_usd_milli", round_half_up(total_usd * 1000.0), "milli_usd"),
        ("matches_per_night", len(views), "count"),
        ("clean_completion_ppm", clean * PPM_ONE // n_matches, "ppm"),
        ("sigma_shrink_ppm", _sigma_shrink_ppm(store, leaderboard), "ppm"),
        ("heldout_gain_mu_milli", 0, "milli"),
        ("liquidity_cost_cents_per_match", bps_ratio(mm_total, n_matches * 10_000), "cents"),
    )


def build_sections(*, result: TournamentResult, store: Store, held_out: bool) -> ReportSections:
    """Fold a finished tournament into the report's data (section 7.24).

    Only the matches whose scenario carries the requested ``held_out`` flag are
    reported, which is how AC-P5 keeps the training evidence and the sealed
    bank evidence apart: two calls, two documents, no shared row.

    Args:
        result: The finished tournament.
        store: The projection database plus artefact directory. Every number is
            read from it or from the journals it points at.
        held_out: Report the held-out matches (True) or the training ones.

    Returns:
        The sections, ready for :func:`render_markdown` and
        :func:`render_html`.
    """
    selected = tuple(item for item in result.match_results if bool(item.scenario.held_out) is bool(held_out))
    views = tuple(_view_of(store, item) for item in selected)
    leaderboard = _leaderboard(result, views, selected)
    observations = _pnl_bps_by_harness(views)
    keys = [record.harness_key for record in leaderboard]
    keys.extend(key for key in sorted(observations) if key not in keys)
    costs_usd = store.load_costs_usd(result.tournament_id)
    incidents: list[Incident] = []
    for view in views:
        incidents.extend(store.load_incidents(match_id=view.match_id))
    liquidity_cost_cents = _liquidity_cost(views)
    calibration = _calibration(views, keys)
    marker = "held-out" if held_out else "train"
    return ReportSections(
        title=f"Tournament {result.tournament_id} ({marker})",
        held_out=bool(held_out),
        leaderboard=leaderboard,
        deltas=_deltas(leaderboard, observations),
        costs_usd=costs_usd,
        incidents=tuple(incidents),
        liquidity_cost_cents=liquidity_cost_cents,
        calibration=calibration,
        kpis=_kpis(
            store=store,
            result=result,
            views=views,
            leaderboard=leaderboard,
            costs_usd=costs_usd,
            liquidity_cost_cents=liquidity_cost_cents,
        ),
        profile_balance=verify_balance([list(view.profiles) for view in views if view.profiles]),
        brier_vs_pnl=_brier_vs_pnl(calibration, observations),
    )


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------
def _balance_line(report: BalanceReport) -> str:
    """One sentence describing the FR-5.3.2 residual (section 7.19, rule 4).

    Args:
        report: The measured balance.

    Returns:
        The sentence, including the section 7.19 rule 6 advice when the square
        is not exact.
    """
    if report.seeds == 0:
        return "no assignment was played, so profile balance is not measured."
    if report.exact:
        return f"exact profile balance over {report.seeds} assignments and {report.seats} seats."
    return (
        f"approximate profile balance (max deviation {report.max_deviation} over {report.seeds} seeds). "
        "Use a seed count that is a multiple of both the seat count and the number of profile kinds."
    )


def _curve_cells(curve: Sequence[tuple[int, int, int]]) -> str:
    """Render one reliability curve inline, as ``upper:n/observed`` cells.

    Args:
        curve: The ``(bin_upper_ppm, n, observed_yes_ppm)`` triples.

    Returns:
        A single cell safe string, ``-`` when the curve is empty.
    """
    populated = [f"{upper}:{n}/{observed}" for upper, n, observed in curve if n > 0]
    return " ".join(populated) if populated else "-"


@dataclass(frozen=True)
class _Block:
    """One rendered section, shared by both renderers (private).

    Attributes:
        heading: The section heading, stated exactly once for both documents.
        lead: One sentence of context printed above the table.
        header: Column titles.
        rows: The body, already stringified.
        empty: The sentence printed instead of an empty table, because a header
            with no row reads as a rendering bug rather than as "nothing here".
    """

    heading: str
    lead: str
    header: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    empty: str


def _blocks(sections: ReportSections) -> tuple[_Block, ...]:
    """Return every section of the document, in order, renderer independent.

    Building the two documents from one list is what keeps the Markdown and the
    HTML report the same report: a section added here appears in both, and
    :data:`MANDATED_SECTIONS` can be checked against either.

    Args:
        sections: What :func:`build_sections` produced.

    Returns:
        The blocks, in document order.
    """
    kinds = tuple(InfoProfileKind)
    return (
        _Block(
            heading="Leaderboard",
            lead=_balance_line(sections.profile_balance),
            header=("Rank", "Harness", "mu", "sigma", "Matches"),
            rows=tuple(
                (str(index), record.harness_key, f"{record.mu:.3f}", f"{record.sigma:.3f}", str(record.matches))
                for index, record in enumerate(sections.leaderboard, start=1)
            ),
            empty="No rated harness.",
        ),
        _Block(
            heading="Deltas",
            lead="TrueSkill mu against the prior, with the PRD section 7.3 bootstrap interval of the PnL.",
            header=("Harness", "mu delta", "Bootstrap CI width (pnl bps)"),
            rows=tuple((key, f"{delta:+.3f}", f"{width:.1f}") for key, delta, width in sections.deltas),
            empty="No delta to report.",
        ),
        _Block(
            heading="Costs",
            lead="Provider cost per harness, summed from the LLM traces.",
            header=("Harness", "Provider cost (USD)"),
            rows=tuple((key, f"{cost:.4f}") for key, cost in sections.costs_usd),
            empty="No provider cost: every seat was scripted.",
        ),
        _Block(
            heading="Incidents",
            lead=f"{len(sections.incidents)} incident(s) raised by the offline detectors.",
            header=("Id", "Kind", "Severity", "Tick", "Agents", "Markets", "Score (ppm)"),
            rows=tuple(
                (
                    item.incident_id,
                    str(item.kind),
                    item.severity,
                    str(item.tick),
                    " ".join(item.agent_ids) or "-",
                    " ".join(item.market_ids) or "-",
                    str(item.score_ppm),
                )
                for item in sections.incidents
            ),
            empty="No integrity incident.",
        ),
        _Block(
            heading="Cost of liquidity",
            lead="The reference market maker PnL (FR-5.8.5), excluded from the ranking and from the ratings.",
            header=("Liquidity profile", "MM PnL (cents)"),
            rows=tuple((name, str(cents)) for name, cents in sections.liquidity_cost_cents),
            empty="No match reported, so no cost of liquidity.",
        ),
        _Block(
            heading="Calibration and reliability curves",
            lead="Brier per harness and the T5.6 reliability curve as bin_upper_ppm:n/observed_yes_ppm.",
            header=("Harness", "Brier (ppm)", "Reliability curve"),
            rows=tuple((key, str(brier), _curve_cells(curve)) for key, brier, curve in sections.calibration),
            empty="No prediction was recorded.",
        ),
        _Block(
            heading="Brier versus PnL",
            lead="Two disjoint families of events (AC-P4): calibration is not profit.",
            header=("Harness", "Brier (ppm)", "Mean PnL (bps)"),
            rows=tuple((key, str(brier), str(pnl)) for key, brier, pnl in sections.brier_vs_pnl),
            empty="Nothing to compare.",
        ),
        _Block(
            heading="KPIs",
            lead="The seven success indicators of PRD section 15.",
            header=("KPI", "Value", "Unit"),
            rows=tuple((name, str(value), unit) for name, value, unit in sections.kpis),
            empty="No KPI could be computed.",
        ),
        _Block(
            heading="Profile balance",
            lead=_balance_line(sections.profile_balance),
            header=("Seat", *(str(kind) for kind in kinds)),
            rows=tuple(
                (seat, *(str(value) for value in list(counts) + [0] * (len(kinds) - len(counts))))
                for seat, counts in sections.profile_balance.counts
            ),
            empty="No seat assignment was reported.",
        ),
    )


def render_markdown(sections: ReportSections) -> str:
    """Render the report as Markdown (T3.6).

    Args:
        sections: What :func:`build_sections` produced.

    Returns:
        The whole document, ending with a newline. Never contains the em-dash
        character (contract rule 4).
    """
    marker = "held-out" if sections.held_out else "train"
    lines: list[str] = [
        f"# {sections.title}",
        "",
        "Generated by `pxe report build`. Do not edit by hand.",
        "",
        f"Set: **{marker}**. Money is integer cents, probabilities and ratios are parts per million.",
        "",
    ]
    for block in _blocks(sections):
        lines += [f"## {block.heading}", "", block.lead, ""]
        if block.rows:
            lines.append("| " + " | ".join(block.header) + " |")
            lines.append("|" + "---|" * len(block.header))
            lines.extend("| " + " | ".join(row) + " |" for row in block.rows)
        else:
            lines.append(block.empty)
        lines.append("")
    return _NEWLINE.join(lines)


def _html_table(header: Sequence[str], rows: Sequence[Sequence[str]], *, empty: str) -> list[str]:
    """Render one HTML table, every cell escaped, or a sentence when empty.

    Args:
        header: Column titles.
        rows: The body, already stringified.
        empty: The sentence printed instead of an empty table.

    Returns:
        The lines of the block.
    """
    if not rows:
        return [f"<p>{html.escape(empty)}</p>"]
    out = ["<table>", "<thead><tr>" + "".join(f"<th>{html.escape(cell)}</th>" for cell in header) + "</tr></thead>"]
    out.append("<tbody>")
    out.extend("<tr>" + "".join(f"<td>{html.escape(cell)}</td>" for cell in row) + "</tr>" for row in rows)
    out += ["</tbody>", "</table>"]
    return out


def render_html(sections: ReportSections) -> str:
    """Render the same report as a standalone HTML document (T3.6).

    The document embeds its own style and references nothing external, so it
    can be opened straight from the runs directory. It carries exactly the
    sections :func:`render_markdown` carries, because both walk
    :func:`_blocks`.

    Args:
        sections: What :func:`build_sections` produced.

    Returns:
        The whole document, ending with a newline.
    """
    title = html.escape(sections.title)
    marker = "held-out" if sections.held_out else "train"
    out: list[str] = [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        f"<title>{title}</title>",
        "<style>",
        "body{font-family:system-ui,sans-serif;margin:2rem auto;max-width:64rem;line-height:1.5}",
        "table{border-collapse:collapse;margin:0 0 1.5rem}",
        "th,td{border:1px solid #ccc;padding:.25rem .6rem;text-align:left;font-variant-numeric:tabular-nums}",
        "th{background:#f3f3f3}",
        "</style>",
        "</head>",
        "<body>",
        f"<h1>{title}</h1>",
        "<p>Generated by <code>pxe report build</code>. Do not edit by hand.</p>",
        f"<p>Set: <strong>{marker}</strong>. Money is integer cents, probabilities and ratios "
        "are parts per million.</p>",
    ]
    for block in _blocks(sections):
        out.append(f"<h2>{html.escape(block.heading)}</h2>")
        out.append(f"<p>{html.escape(block.lead)}</p>")
        out.extend(_html_table(block.header, block.rows, empty=block.empty))
    out += ["</body>", "</html>", ""]
    return _NEWLINE.join(out)


def _write_pair(*, result: TournamentResult, store: Store, out_dir: Path, held_out: bool) -> tuple[Path, Path]:
    """Write one Markdown plus HTML pair into ``out_dir``.

    Args:
        result: The finished tournament.
        store: The projection database.
        out_dir: Destination directory, created if absent.
        held_out: Which half of the pair to render.

    Returns:
        ``(markdown path, html path)``.
    """
    sections = build_sections(result=result, store=store, held_out=held_out)
    out_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = out_dir / REPORT_MARKDOWN_NAME
    html_path = out_dir / REPORT_HTML_NAME
    with open(markdown_path, "w", encoding=JOURNAL_ENCODING, newline=JOURNAL_NEWLINE) as handle:
        handle.write(render_markdown(sections))
    with open(html_path, "w", encoding=JOURNAL_ENCODING, newline=JOURNAL_NEWLINE) as handle:
        handle.write(render_html(sections))
    return markdown_path, html_path


def write_report(*, result: TournamentResult, store: Store, out_dir: Path) -> tuple[Path, Path]:
    """Write ``report.md`` and ``report.html`` for the train and held-out sets.

    Writes the train pair into ``out_dir`` and, separately, the held-out pair
    into ``out_dir / "heldout"`` (AC-P5, PRD T3.5). Both pairs are always
    written, including when one of the two halves is empty: a missing file
    reads as "the report was not generated", which is exactly the failure
    AC-P3 is about, while an empty section reads as "nothing was played there".

    Args:
        result: The finished tournament.
        store: The projection database plus artefact directory.
        out_dir: The tournament's directory, normally ``runs/<tournament_id>``.

    Returns:
        The two **train** paths, ``(report.md, report.html)``. The held-out
        pair sits in ``out_dir / "heldout"`` under the same two names.
    """
    destination = Path(out_dir)
    train = _write_pair(result=result, store=store, out_dir=destination, held_out=False)
    _write_pair(result=result, store=store, out_dir=destination / HELDOUT_DIRNAME, held_out=True)
    return train
