"""A23 acceptance tests for `pxe.tournament.report` (CONTRACTS section 7.24).

The five tests section 7.24 names by hand are all here:
``test_five_mandated_sections_present`` (T3.6), ``test_kpis_cover_prd_section_15``
(PRD section 15), ``test_reliability_curves`` and ``test_brier_vs_pnl_published``
(T5.6) and ``test_train_and_heldout_written_separately`` (AC-P5).

Everything is asserted against a **real** three match tournament, played once
per module by the fixture below through the real orchestrator, and every test
first asserts that what it is about to walk is not empty (section 10's
anti-vacuous rule).
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest

from pxe.metrics.projection import project
from pxe.store.db import Store, default_store_url
from pxe.tournament.orchestrator import TournamentOrchestrator
from pxe.tournament.report import (
    HELDOUT_DIRNAME,
    KPI_NAMES,
    MANDATED_SECTIONS,
    REPORT_HTML_NAME,
    REPORT_MARKDOWN_NAME,
    ReportSections,
    build_sections,
    render_html,
    render_markdown,
    write_report,
)
from pxe.types import (
    GatewayConfig,
    Incident,
    IncidentKind,
    MatchConfig,
    TournamentConfig,
    TournamentFormat,
    TournamentResult,
    make_incident_id,
)

#: The tournament the whole module reports on. Four scripted background
#: baselines at four seats is exactly one matchup, so three seeds are three
#: matches: small enough to play in a fixture, large enough that every section
#: of the report has rows.
TOURNAMENT_ID = "T-report-0001"
SEEDS = (11, 12, 13)


def _config() -> TournamentConfig:
    """Build the tiny round robin the module reports on.

    Returns:
        The tournament configuration.
    """
    return TournamentConfig(
        tournament_id=TOURNAMENT_ID,
        format=TournamentFormat.ROUND_ROBIN,
        harnesses=(),
        template_ids=("election",),
        seeds=SEEDS,
        agents_per_match=4,
        rounds=1,
        gateway=GatewayConfig(timeout_s=30.0),
        match_defaults=MatchConfig(ticks_total=24, n_agents=4, n_markets=2),
        background_baselines=("fundamentalist", "momentum", "noise", "bayesian"),
        max_cost_usd=0.0,
    )


@pytest.fixture(scope="module")
def played(tmp_path_factory: pytest.TempPathFactory) -> tuple[TournamentResult, Path]:
    """Play the tournament once and return its result plus the runs root.

    Args:
        tmp_path_factory: pytest's per module temporary directory factory.

    Returns:
        ``(result, runs_dir)``.
    """
    runs_dir = tmp_path_factory.mktemp("report-runs")
    with Store(url=default_store_url(runs_dir), runs_dir=runs_dir) as store:
        store.init_schema()
        result = TournamentOrchestrator(config=_config(), store=store).run(max_workers=1)
    return result, runs_dir


@pytest.fixture
def store(played: tuple[TournamentResult, Path]) -> Iterator[Store]:
    """Open the store of the played tournament.

    Args:
        played: The module fixture.

    Yields:
        An open :class:`~pxe.store.db.Store`.
    """
    _result, runs_dir = played
    opened = Store(url=default_store_url(runs_dir), runs_dir=runs_dir)
    try:
        yield opened
    finally:
        opened.close()


@pytest.fixture
def result(played: tuple[TournamentResult, Path]) -> TournamentResult:
    """Return the finished tournament.

    Args:
        played: The module fixture.

    Returns:
        The result.
    """
    return played[0]


@pytest.fixture
def sections(result: TournamentResult, store: Store) -> ReportSections:
    """Build the train sections of the played tournament.

    Args:
        result: The finished tournament.
        store: Its store.

    Returns:
        The sections.
    """
    return build_sections(result=result, store=store, held_out=False)


def _assert_the_tournament_really_played(result: TournamentResult, store: Store) -> None:
    """Refuse to make any claim about an empty tournament (section 10).

    Args:
        result: The finished tournament.
        store: Its store.
    """
    assert result.match_results, "the fixture tournament played no match"
    assert len(result.match_results) == len(SEEDS), result.match_results
    for item in result.match_results:
        events = store.load_journal(item.match_id)
        assert events, f"{item.match_id} has an empty journal"
        projection = project(events)
        assert projection.trades, f"{item.match_id} produced no trade"
        assert projection.predictions, f"{item.match_id} produced no prediction"


def _missing(text: str, headings: tuple[str, ...], *, prefix: str) -> list[str]:
    """Return the headings absent from a rendered document.

    Args:
        text: The document.
        headings: The headings that must be there.
        prefix: ``"## "`` for Markdown, ``"<h2>"`` for HTML.

    Returns:
        The missing ones, in the order they were asked for.
    """
    return [heading for heading in headings if f"{prefix}{heading}" not in text]


# ---------------------------------------------------------------------------
# T3.6: the five mandated sections
# ---------------------------------------------------------------------------
def test_five_mandated_sections_present(result: TournamentResult, store: Store, sections: ReportSections) -> None:
    """PRD T3.6: classement, deltas, couts, incidents, cout de la liquidite."""
    _assert_the_tournament_really_played(result, store)
    assert sections.leaderboard, "no rated harness: the report would be vacuous"
    assert sections.deltas
    assert sections.costs_usd
    assert sections.liquidity_cost_cents

    markdown = render_markdown(sections)
    document = render_html(sections)
    assert _missing(markdown, MANDATED_SECTIONS, prefix="## ") == []
    assert _missing(document, MANDATED_SECTIONS, prefix="<h2>") == []

    # Control: the check has teeth. Removing one heading must be detected.
    mutilated = markdown.replace("## Cost of liquidity", "## Something else", 1)
    assert _missing(mutilated, MANDATED_SECTIONS, prefix="## ") == ["Cost of liquidity"]


def test_the_leaderboard_and_the_deltas_carry_real_numbers(sections: ReportSections) -> None:
    """The ranking is the tournament's own, and every delta is measured."""
    assert len(sections.leaderboard) == 4, sections.leaderboard
    mus = [record.mu for record in sections.leaderboard]
    assert mus == sorted(mus, reverse=True), "the leaderboard is not best mu first"
    assert all(record.matches == len(SEEDS) for record in sections.leaderboard)
    keys = {record.harness_key for record in sections.leaderboard}
    assert {key for key, _delta, _width in sections.deltas} == keys
    assert any(width > 0.0 for _key, _delta, width in sections.deltas), (
        "every bootstrap interval is degenerate: the resampling did not run"
    )


def test_the_cost_of_liquidity_is_published(sections: ReportSections) -> None:
    """FR-5.8.5: the market maker PnL appears, per preset that played."""
    assert sections.liquidity_cost_cents
    names = [name for name, _cents in sections.liquidity_cost_cents]
    assert names == ["standard"], names
    assert all(isinstance(cents, int) for _name, cents in sections.liquidity_cost_cents)
    assert "| standard |" in render_markdown(sections)


def test_incidents_reach_the_report(result: TournamentResult, store: Store) -> None:
    """An incident saved for a reported match is rendered in both documents."""
    match_id = result.match_results[0].match_id
    forged = Incident(
        incident_id=make_incident_id(1),
        kind=IncidentKind.SPOOFING,
        severity="high",
        tick=7,
        agent_ids=("A1", "A2"),
        market_ids=("M1",),
        score_ppm=987_654,
        detail=(("evidence", "forged by tests/test_report.py"),),
        detector_version="test-1",
    )
    assert forged.match_id == "", "a detector does not know the store's key (section 7.1)"
    store.save_incidents(match_id, [forged])
    try:
        sections = build_sections(result=result, store=store, held_out=False)
        # The store stamps `match_id` on the way back out (ruling R109), so the
        # round trip is deliberately not an identity: compare the fields the
        # detector produced, and assert the one the store owns separately.
        assert len(sections.incidents) == 1
        loaded = sections.incidents[0]
        assert loaded.match_id == match_id, "the report cannot attribute an alert to its replay"
        assert dataclasses.replace(loaded, match_id="") == forged
        markdown = render_markdown(sections)
        assert "i-0001" in markdown and "spoofing" in markdown and "987654" in markdown
        assert "spoofing" in render_html(sections)
    finally:
        store.save_incidents(match_id, [])


# ---------------------------------------------------------------------------
# PRD section 15: the seven KPIs
# ---------------------------------------------------------------------------
def test_kpis_cover_prd_section_15(sections: ReportSections) -> None:
    """The seven names of section 7.24's KPI table are all present, once each."""
    assert sections.kpis, "no KPI was computed"
    names = tuple(name for name, _value, _unit in sections.kpis)
    assert names == KPI_NAMES, names
    assert len(set(names)) == len(names)
    units = {name: unit for name, _value, unit in sections.kpis}
    assert units["clean_completion_ppm"] == "ppm"
    assert units["matches_per_night"] == "count"
    assert all(isinstance(value, int) for _name, value, _unit in sections.kpis), "a KPI is not an integer"
    values = {name: value for name, value, _unit in sections.kpis}
    assert values["matches_per_night"] == len(SEEDS)
    assert values["clean_completion_ppm"] == 1_000_000, "no technical incident was raised, so completion is clean"
    assert values["liquidity_cost_cents_per_match"] != 0, "the market maker neither gained nor lost anything"

    markdown = render_markdown(sections)
    for name in KPI_NAMES:
        assert f"| {name} |" in markdown, name


# ---------------------------------------------------------------------------
# T5.6: reliability curves and the Brier versus PnL analysis
# ---------------------------------------------------------------------------
def test_reliability_curves(sections: ReportSections) -> None:
    """Every rated harness gets a Brier and a ten bin reliability curve."""
    assert sections.calibration, "no calibration row"
    for key, brier_ppm, curve in sections.calibration:
        assert key
        assert 0 <= brier_ppm <= 1_000_000, (key, brier_ppm)
        assert len(curve) == 10, curve
        edges = [upper for upper, _n, _observed in curve]
        assert edges == [(index + 1) * 100_000 for index in range(10)], edges
        for _upper, n, observed in curve:
            assert n >= 0
            assert 0 <= observed <= 1_000_000
    populated = sum(n for _key, _brier, curve in sections.calibration for _upper, n, _observed in curve)
    assert populated > 0, "every reliability bin is empty: no prediction was counted"
    assert any(brier > 0 for _key, brier, _curve in sections.calibration)
    assert "Reliability curve" in render_markdown(sections)


def test_brier_vs_pnl_published(sections: ReportSections) -> None:
    """T5.6: the two decoupled numbers are published side by side, per harness."""
    assert sections.brier_vs_pnl, "the analysis is empty"
    calibration = {key: brier for key, brier, _curve in sections.calibration}
    assert {key for key, _brier, _pnl in sections.brier_vs_pnl} == set(calibration)
    for key, brier_ppm, pnl_bps in sections.brier_vs_pnl:
        assert brier_ppm == calibration[key], "the two sections disagree about the Brier"
        assert isinstance(pnl_bps, int)
    assert any(pnl != 0 for _key, _brier, pnl in sections.brier_vs_pnl), "every PnL is zero"
    # AC-P4 made visible: the best calibrated harness is not automatically the
    # most profitable one, which is the whole reason this table is published.
    assert "Brier versus PnL" in render_markdown(sections)
    assert "<h2>Brier versus PnL</h2>" in render_html(sections)


# ---------------------------------------------------------------------------
# AC-P5: train and held-out are two documents
# ---------------------------------------------------------------------------
def test_train_and_heldout_written_separately(result: TournamentResult, store: Store, tmp_path: Path) -> None:
    """AC-P5: two directories, four files, and no row shared between them."""
    _assert_the_tournament_really_played(result, store)
    out_dir = tmp_path / "report"
    markdown, document = write_report(result=result, store=store, out_dir=out_dir)
    assert markdown == out_dir / REPORT_MARKDOWN_NAME
    assert document == out_dir / REPORT_HTML_NAME
    heldout_dir = out_dir / HELDOUT_DIRNAME
    for path in (markdown, document, heldout_dir / REPORT_MARKDOWN_NAME, heldout_dir / REPORT_HTML_NAME):
        assert path.is_file(), path
        assert path.read_text(encoding="utf-8").strip(), path
    assert "(train)" in markdown.read_text(encoding="utf-8")
    assert "(held-out)" in (heldout_dir / REPORT_MARKDOWN_NAME).read_text(encoding="utf-8")

    # The split is on the scenario flag and it really partitions the matches:
    # flag one half of the played matches and the two reports become disjoint.
    flagged = tuple(
        replace(item, scenario=replace(item.scenario, held_out=index == 0))
        for index, item in enumerate(result.match_results)
    )
    mixed = replace(result, match_results=flagged)
    train = build_sections(result=mixed, store=store, held_out=False)
    heldout = build_sections(result=mixed, store=store, held_out=True)
    train_matches = {name: value for name, value, _unit in train.kpis}["matches_per_night"]
    heldout_matches = {name: value for name, value, _unit in heldout.kpis}["matches_per_night"]
    assert train_matches == len(SEEDS) - 1
    assert heldout_matches == 1
    assert heldout.held_out is True and train.held_out is False
    assert heldout.liquidity_cost_cents != train.liquidity_cost_cents
    assert heldout.leaderboard, "the held-out half rated nobody"
    assert heldout.calibration, "the held-out half measured no calibration"


# ---------------------------------------------------------------------------
# Rendering rules
# ---------------------------------------------------------------------------
def test_both_documents_hold_every_section_and_no_em_dash(sections: ReportSections) -> None:
    """Contract rule 4, and the two renderers walk the same block list."""
    every = (*MANDATED_SECTIONS, "Calibration and reliability curves", "Brier versus PnL", "KPIs", "Profile balance")
    markdown = render_markdown(sections)
    document = render_html(sections)
    assert _missing(markdown, every, prefix="## ") == []
    assert _missing(document, every, prefix="<h2>") == []
    # Built by escape so this test does not itself trip tests/test_style_rules.py.
    em_dash = chr(0x2014)
    assert em_dash not in markdown
    assert em_dash not in document
    assert document.startswith("<!doctype html>")
    assert document.rstrip().endswith("</html>")


def test_the_profile_balance_is_measured_and_never_raises(sections: ReportSections) -> None:
    """FR-5.3.2 rule 4: an imperfect square is published, not an error."""
    report = sections.profile_balance
    assert report.seeds == len(SEEDS), report
    assert report.seats == 4, report
    assert report.counts, "no seat assignment was measured"
    assert sum(sum(counts) for _seat, counts in report.counts) == report.seeds * report.seats
    assert isinstance(bool(report), bool)


def test_the_report_is_a_projection_of_the_store(result: TournamentResult, store: Store) -> None:
    """Two builds over the same store are identical: nothing reads a clock."""
    first = build_sections(result=result, store=store, held_out=False)
    second = build_sections(result=result, store=store, held_out=False)
    assert first == second
    assert render_markdown(first) == render_markdown(second)
    assert render_html(first) == render_html(second)


def test_an_empty_half_still_renders_every_section(result: TournamentResult, store: Store) -> None:
    """A tournament with no held-out match still gets a held-out document."""
    empty = build_sections(result=replace(result, match_results=()), store=store, held_out=True)
    assert empty.leaderboard == ()
    assert empty.calibration == ()
    markdown = render_markdown(empty)
    assert _missing(markdown, MANDATED_SECTIONS, prefix="## ") == []
    assert "No rated harness." in markdown
    assert json.dumps([name for name, _value, _unit in empty.kpis]) == json.dumps(list(KPI_NAMES))


def test_the_orchestrator_writes_the_report_with_no_manual_action(
    result: TournamentResult, played: tuple[TournamentResult, Path]
) -> None:
    """T3.6 and AC-P3: the end of a tournament produced the four files itself."""
    _result, runs_dir = played
    out_dir = runs_dir / TOURNAMENT_ID
    assert Path(result.report_path) == out_dir / REPORT_MARKDOWN_NAME
    for path in (
        out_dir / REPORT_MARKDOWN_NAME,
        out_dir / REPORT_HTML_NAME,
        out_dir / HELDOUT_DIRNAME / REPORT_MARKDOWN_NAME,
        out_dir / HELDOUT_DIRNAME / REPORT_HTML_NAME,
    ):
        assert path.is_file(), f"{path} was not written by the orchestrator"


def test_a_match_result_of_another_tournament_is_not_reported(result: TournamentResult, store: Store) -> None:
    """``build_sections`` reports the matches it is given and nothing else."""
    one = replace(result, match_results=result.match_results[:1])
    sections = build_sections(result=one, store=store, held_out=False)
    matches = {name: value for name, value, _unit in sections.kpis}["matches_per_night"]
    assert matches == 1
    assert sections.leaderboard, "a one match subset still rates the seats that played it"


def test_the_type_of_every_field_is_the_contracted_one(sections: ReportSections) -> None:
    """Section 7.24 spells every field literally; other packages code against it."""
    assert isinstance(sections.title, str)
    assert isinstance(sections.held_out, bool)
    assert all(isinstance(item, tuple) and len(item) == 3 for item in sections.deltas)
    assert all(isinstance(item, tuple) and len(item) == 2 for item in sections.costs_usd)
    assert all(isinstance(item, tuple) and len(item) == 2 for item in sections.liquidity_cost_cents)
    assert all(isinstance(item, tuple) and len(item) == 3 for item in sections.calibration)
    assert all(isinstance(item, tuple) and len(item) == 3 for item in sections.kpis)
    assert all(isinstance(item, tuple) and len(item) == 3 for item in sections.brier_vs_pnl)
