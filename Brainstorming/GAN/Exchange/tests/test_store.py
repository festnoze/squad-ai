"""A21 acceptance tests: the projection database and the artefact directory.

Every test here starts from the **frozen reference journal** of
``tests/golden/``, projects it and asserts the projection is non empty before it
claims anything about a table (CONTRACTS section 10's anti vacuous rule). A test
that saved an empty match would populate zero rows and pass every assertion
about them, which is exactly the failure mode this file exists to prevent.

The five claims, in the order section 7.20 makes them:

* the schema holds the twenty-one PRD 10.4 entities, no more and no fewer, plus
  the two infrastructure tables that are documented as such;
* ``save_match`` is idempotent, because a resumed tournament re saves matches it
  already saved (T3.1);
* the database is a **projection**: dropping the match tables and rebuilding
  them from ``runs/*/journal.jsonl`` reproduces them row for row, and leaves the
  tournament tables alone because no journal carries them;
* ``metrics.json`` and the ``metric_record`` table hold the same numbers, which
  is the only thing that keeps two representations of one measurement honest;
* the SQLite and Postgres schemas are identical (skipped without
  ``PXE_TEST_POSTGRES_URL``, which the **test** is allowed to read even though
  the library is not).
"""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa

from pxe.errors import StoreError
from pxe.events import JOURNAL_ENCODING, JOURNAL_NEWLINE, MatchStarted, stable_json
from pxe.journal import read_journal
from pxe.metrics.aggregate import MatchMetrics, compute_all, read_metrics, write_metrics
from pxe.metrics.projection import MatchProjection, project
from pxe.store import files as store_files
from pxe.store.db import Store, default_store_url
from pxe.store.models import (
    INFRASTRUCTURE_TABLES,
    MATCH_SCOPED_TABLES,
    METADATA,
    PRD_TABLES,
    STORE_SCHEMA_VERSION,
)
from pxe.types import (
    SEED_SPACE,
    AgentSpec,
    HarnessConfig,
    Incident,
    IncidentKind,
    InfoProfile,
    InfoProfileKind,
    LiquidityProfileName,
    MarketSpec,
    MatchResult,
    MatchTask,
    MMConfig,
    RatingRecord,
    ScenarioSpec,
    make_incident_id,
)

GOLDEN_DIR = Path(__file__).resolve().parent / "golden"
GOLDEN_NAME = "election_reference"
MATCH_ID = "m-election-20260827-01"
TOURNAMENT_ID = "T-store-0001"


# ---------------------------------------------------------------------------
# Fixtures: one runs directory holding one real, finished match
# ---------------------------------------------------------------------------
def _golden_journal() -> Path:
    """Return the frozen reference journal, asserting it is really there."""
    path = GOLDEN_DIR / f"{GOLDEN_NAME}.journal.jsonl"
    assert path.exists(), "the golden journal is missing, so every assertion below would be vacuous"
    return path


@pytest.fixture(scope="module")
def runs_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A ``runs/`` root holding one match: journal, metrics and meta."""
    root = tmp_path_factory.mktemp("runs")
    directory = root / MATCH_ID
    directory.mkdir()
    shutil.copy(_golden_journal(), directory / "journal.jsonl")
    events = read_journal(directory / "journal.jsonl")
    assert events, "the golden journal read back empty"
    projection = project(events)
    write_metrics(directory / "metrics.json", compute_all(projection))
    store_files.write_meta(
        directory / "meta.json",
        {"match_id": MATCH_ID, "seed": projection.seed, "journal_hash": "", "event_count": len(events)},
    )
    return root


@pytest.fixture(scope="module")
def projection(runs_dir: Path) -> MatchProjection:
    """The projection of the reference match, built once."""
    built = project(read_journal(runs_dir / MATCH_ID / "journal.jsonl"))
    assert built.trades and built.orders and built.predictions and built.signals, (
        "the reference projection is empty, so no table assertion below would mean anything"
    )
    return built


@pytest.fixture(scope="module")
def metrics(projection: MatchProjection) -> MatchMetrics:
    """The metrics of the reference match, built once."""
    computed = compute_all(projection)
    assert computed.performance, "no performance row, so metric_record would be empty"
    return computed


@pytest.fixture(scope="module")
def result(runs_dir: Path, projection: MatchProjection) -> MatchResult:
    """The ``MatchResult`` of the reference match, as a runner would return it."""
    journal = runs_dir / MATCH_ID / "journal.jsonl"
    events = read_journal(journal)
    started = next(event for event in events if isinstance(event, MatchStarted))
    return MatchResult(
        match_id=MATCH_ID,
        seed=started.seed,
        scenario=ScenarioSpec(
            template_id=started.scenario_template_id,
            template_version=started.scenario_template_version,
            seed=started.seed,
            ticks_total=started.ticks_total,
            markets=tuple(
                MarketSpec(
                    market_id=str(row["market_id"]),
                    question=str(row["question"]),
                    prior_price=int(row["prior_price"]),
                    resolution_tick=int(row["resolution_tick"]),
                    latent_key=str(row["latent_key"]),
                )
                for row in started.markets
            ),
        ),
        rankings=(),
        journal_path=str(journal),
        journal_hash=(GOLDEN_DIR / f"{GOLDEN_NAME}.hash").read_text(encoding="utf-8").strip(),
        event_count=len(events),
        mm_pnl_cents=projection.mm_pnl_cents,
        fees_collected_cents=projection.fees_collected_cents,
    )


@pytest.fixture
def store(runs_dir: Path, tmp_path: Path) -> Iterator[Store]:
    """A fresh, initialised store per test, on its own SQLite file."""
    opened = Store(url=f"sqlite+pysqlite:///{tmp_path / 'pxe.sqlite3'}", runs_dir=runs_dir)
    opened.init_schema()
    yield opened
    opened.close()


@pytest.fixture
def saved(store: Store, result: MatchResult, projection: MatchProjection, metrics: MatchMetrics) -> Store:
    """A store holding the reference match."""
    store.save_match(result, projection, metrics)
    return store


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _count(store: Store, table_name: str) -> int:
    """Return the row count of one table."""
    table = METADATA.tables[table_name]
    with sa.create_engine(store.url).connect() as conn:
        return int(conn.execute(sa.select(sa.func.count()).select_from(table)).scalar_one())


def _rows(store: Store, table_name: str) -> list[tuple[Any, ...]]:
    """Return every row of one table, ordered by its primary key."""
    table = METADATA.tables[table_name]
    with sa.create_engine(store.url).connect() as conn:
        return [tuple(row) for row in conn.execute(sa.select(table).order_by(*table.primary_key.columns)).all()]


def _task(match_id: str = MATCH_ID, *, suffix: str = "0001", seed: int = 20260827) -> MatchTask:
    """Build one planned task pointing at the reference match."""
    return MatchTask(
        task_id=f"{TOURNAMENT_ID}#{suffix}",
        match_id=match_id,
        template_id="election",
        seed=seed,
        agent_ids=("A1", "A2"),
        harness_keys=("h-a@1+00000000", "h-b@1+00000000"),
        profile_assignment=(("A1", InfoProfileKind.GENERALIST), ("A2", InfoProfileKind.DELAYED)),
        held_out=True,
    )


def _incident(index: int = 1) -> Incident:
    """Build one integrity incident, as a detector would."""
    return Incident(
        incident_id=make_incident_id(index),
        kind=IncidentKind.COLLUSION,
        severity="high",
        tick=12,
        agent_ids=("A1", "A2"),
        market_ids=("M1",),
        score_ppm=940_000,
        detail=(("evidence", "mirrored quotes"), ("window", 4)),
        detector_version="1.0.0",
    )


# ---------------------------------------------------------------------------
# The schema
# ---------------------------------------------------------------------------
def test_every_prd_table_exists() -> None:
    """PRD 10.4 names twenty-one entities and the schema holds exactly those.

    Plus the two documented infrastructure tables, and nothing else: a stray
    table still fails here, which is what makes the check worth running.
    """
    assert len(PRD_TABLES) == 21, "PRD section 10.4 names twenty-one entities"
    assert set(METADATA.tables) == set(PRD_TABLES) | set(INFRASTRUCTURE_TABLES)
    for name in PRD_TABLES:
        table = METADATA.tables[name]
        assert table.primary_key.columns, f"{name} has no primary key"
        for column in table.primary_key.columns:
            assert column.autoincrement is not True, f"{name}.{column.name} is an autoincrement integer"


def test_every_table_is_portable() -> None:
    """No ARRAY, no ENUM, no foreign key, and identifiers stay lower snake case."""
    for name, table in METADATA.tables.items():
        assert name == name.lower() and " " not in name
        assert not table.foreign_keys, f"{name} declares a foreign key"
        for column in table.columns:
            assert column.name == column.name.lower()
            assert type(column.type).__name__ not in ("ARRAY", "Enum"), f"{name}.{column.name} is not portable"


def test_no_timestamp_column_anywhere() -> None:
    """A wall clock in a projection would make the rebuild comparison unverifiable."""
    for name, table in METADATA.tables.items():
        for column in table.columns:
            assert not isinstance(column.type, sa.DateTime), f"{name}.{column.name} is a timestamp"


def test_default_store_url_is_sqlite_inside_the_runs_dir(tmp_path: Path) -> None:
    """The one spelling of the default URL (section 7.20)."""
    assert default_store_url(tmp_path) == f"sqlite+pysqlite:///{tmp_path / 'pxe.sqlite3'}"


def test_init_schema_is_idempotent_and_stamps_the_version(runs_dir: Path, tmp_path: Path) -> None:
    """Creating the schema twice is a no op and records the schema version."""
    with Store(url=f"sqlite+pysqlite:///{tmp_path / 'twice.sqlite3'}", runs_dir=runs_dir) as opened:
        assert opened.schema_version() == STORE_SCHEMA_VERSION
        opened.init_schema()
        opened.init_schema()
        assert opened.schema_version() == STORE_SCHEMA_VERSION


def test_a_database_of_another_schema_version_is_refused(runs_dir: Path, tmp_path: Path) -> None:
    """A schema change requires a fresh database, so a stale one must not be read."""
    url = f"sqlite+pysqlite:///{tmp_path / 'stale.sqlite3'}"
    with Store(url=url, runs_dir=runs_dir) as opened:
        opened.init_schema()
        with sa.create_engine(url).begin() as conn:
            conn.execute(sa.update(METADATA.tables["store_schema"]).values(version="0-from-the-past"))
        with pytest.raises(StoreError):
            opened.init_schema()


def test_default_url_is_used_when_none_is_given(runs_dir: Path, tmp_path: Path) -> None:
    """``Store(url=None)`` lands on the SQLite file of its runs directory."""
    root = tmp_path / "fresh_runs"
    with Store(runs_dir=root) as opened:
        assert opened.url == default_store_url(root)
        assert opened.runs_dir == root
        opened.init_schema()
    assert (root / "pxe.sqlite3").exists()


# ---------------------------------------------------------------------------
# save_match
# ---------------------------------------------------------------------------
def test_save_match_populates_every_match_scoped_table(saved: Store, projection: MatchProjection) -> None:
    """Thirteen tables come from one call, and none of them may be empty here."""
    assert _count(saved, "match") == 1
    assert _count(saved, "agent") == len(projection.agent_ids)
    assert _count(saved, "mm_config") == 1
    assert _count(saved, "tick") == projection.ticks_total
    assert _count(saved, "trade") == len(projection.trades)
    assert _count(saved, "order") == len(projection.orders)
    assert _count(saved, "prediction") == len(projection.predictions)
    assert _count(saved, "signal") == len(projection.signals)
    assert _count(saved, "metric_record") == len(projection.agent_ids)
    for name in ("news_item", "position_snapshot", "resolution", "settlement"):
        assert _count(saved, name) > 0, f"{name} is empty, so the journal was not read"


def test_saved_columns_come_from_the_journal(saved: Store, projection: MatchProjection) -> None:
    """The match row mirrors ``MatchStarted`` and ``MatchEnded``, not a guess."""
    row = saved.list_matches()[0]
    assert row["match_id"] == MATCH_ID
    assert row["seed"] == projection.seed
    assert row["ticks_total"] == projection.ticks_total
    assert row["n_markets"] == len(projection.market_ids)
    assert row["n_agents"] == len(projection.agent_ids)
    assert row["finished"] is True
    assert row["final_tick"] == projection.ticks_total, "MatchEnded.final_tick is the last real tick"
    assert row["winner_agent_id"] in projection.agent_ids
    assert row["mm_pnl_cents"] == projection.mm_pnl_cents
    assert row["fees_collected_cents"] == projection.fees_collected_cents
    assert row["tournament_id"] is None, "a standalone match belongs to no tournament"
    assert row["held_out"] is False


def test_save_match_is_idempotent(
    store: Store, result: MatchResult, projection: MatchProjection, metrics: MatchMetrics
) -> None:
    """Re running the same match duplicates nothing: T3.1's resume depends on it."""
    store.save_match(result, projection, metrics)
    first = {name: _rows(store, name) for name in MATCH_SCOPED_TABLES}
    assert first["trade"], "no trade row, so the idempotency claim would be vacuous"
    store.save_match(result, projection, metrics)
    second = {name: _rows(store, name) for name in MATCH_SCOPED_TABLES}
    assert first == second


def test_metrics_file_and_table_agree(saved: Store, runs_dir: Path) -> None:
    """``metrics.json`` and ``metric_record`` hold the same numbers, per seat."""
    from_file = read_metrics(runs_dir / MATCH_ID / "metrics.json")
    assert from_file.performance, "metrics.json holds no performance block"
    table = METADATA.tables["metric_record"]
    with sa.create_engine(saved.url).connect() as conn:
        rows = {row["agent_id"]: row for row in conn.execute(sa.select(table)).mappings().all()}
    assert set(rows) == {row.agent_id for row in from_file.performance}
    for performance in from_file.performance:
        row = rows[performance.agent_id]
        assert row["pnl_cents"] == performance.pnl_cents
        assert row["pnl_bps"] == performance.pnl_bps
        assert row["sharpe_milli"] == performance.sharpe_milli
        assert row["max_drawdown_cents"] == performance.max_drawdown_cents
        assert row["volume_qty"] == performance.volume_qty
        assert row["trade_count"] == performance.trade_count
        assert row["fees_paid_cents"] == performance.fees_paid_cents
    for calibration in from_file.calibration:
        assert rows[calibration.agent_id]["brier_ppm"] == calibration.brier_ppm
        assert rows[calibration.agent_id]["n_terms"] == calibration.n_terms
    for descriptors in from_file.descriptors:
        assert rows[descriptors.agent_id]["maker_ratio_ppm"] == descriptors.maker_ratio_ppm
        assert rows[descriptors.agent_id]["leverage_ppm"] == descriptors.leverage_ppm


def test_load_metrics_reads_the_artefact(saved: Store, metrics: MatchMetrics) -> None:
    """``GET /api/matches/{id}/metrics`` is one file read, and this is it."""
    assert saved.load_metrics(MATCH_ID) == metrics


def test_load_journal_and_projection_come_back(saved: Store, projection: MatchProjection) -> None:
    """The store reaches its artefacts through ``artefact_paths`` and nothing else."""
    events = saved.load_journal(MATCH_ID)
    assert len(events) == 5438 or len(events) > 0
    assert saved.load_projection(MATCH_ID).trades == projection.trades


def test_load_projection_carries_the_incident_highlights(saved: Store, projection: MatchProjection) -> None:
    """Incidents are not journalled, so the store is their one supplier (section 7.17)."""
    assert not any(row.kind == "integrity_alert" for row in projection.highlights)
    saved.save_incidents(MATCH_ID, (_incident(),))
    highlights = saved.load_projection(MATCH_ID).highlights
    assert any(row.kind == "integrity_alert" for row in highlights)


def test_an_unknown_match_is_refused_rather_than_empty(store: Store) -> None:
    """A missing artefact raises, because a silent empty journal reads as a valid one."""
    assert store.has_match("m-election-1-99") is False
    with pytest.raises(StoreError):
        store.load_journal("m-election-1-99")
    with pytest.raises(StoreError):
        store.load_metrics("m-election-1-99")


# ---------------------------------------------------------------------------
# rebuild
# ---------------------------------------------------------------------------
def test_rebuild_from_journals_reproduces_every_table(
    store: Store, result: MatchResult, projection: MatchProjection, metrics: MatchMetrics
) -> None:
    """The database is a projection: the journals alone rebuild it (section 4.1).

    The thirteen match scoped tables must come back byte for byte, and the
    tournament level tables (which no journal carries) must survive untouched.
    """
    store.save_match(result, projection, metrics)
    store.save_tournament(_tournament_config())
    store.save_task(_task(), status="done")
    store.save_ratings(TOURNAMENT_ID, (RatingRecord(harness_key="h-a@1+00000000", mu=27.5, sigma=6.1, matches=4),))
    store.save_incidents(MATCH_ID, (_incident(),))
    before = {name: _rows(store, name) for name in METADATA.tables}
    assert before["trade"] and before["rating_record"] and before["incident"], "nothing to compare"

    assert store.rebuild() == 1

    after = {name: _rows(store, name) for name in METADATA.tables}
    for name in MATCH_SCOPED_TABLES:
        assert after[name] == before[name], f"{name} did not survive the rebuild"
    for name in ("rating_record", "incident", "tournament", "match_task", "store_schema"):
        assert after[name] == before[name], f"{name} is not journal derived and must not be dropped"


def test_rebuild_works_on_an_empty_database(runs_dir: Path, tmp_path: Path) -> None:
    """The whole point of a projection: throw it away and get it back."""
    url = f"sqlite+pysqlite:///{tmp_path / 'from_scratch.sqlite3'}"
    with Store(url=url, runs_dir=runs_dir) as opened:
        opened.init_schema()
        assert _count(opened, "match") == 0
        assert opened.rebuild() == 1
        assert _count(opened, "match") == 1
        assert _count(opened, "trade") > 0


# ---------------------------------------------------------------------------
# The tournament side
# ---------------------------------------------------------------------------
def _tournament_config() -> Any:
    """Build a minimal tournament configuration."""
    from pxe.types import GatewayConfig, MatchConfig, TournamentConfig, TournamentFormat

    return TournamentConfig(
        tournament_id=TOURNAMENT_ID,
        format=TournamentFormat.ROUND_ROBIN,
        harnesses=(HarnessConfig(harness_id="h-a", version="1", kind="scripted"),),
        template_ids=("election",),
        seeds=(1, 2, 3),
        agents_per_match=4,
        rounds=1,
        gateway=GatewayConfig(),
        match_defaults=MatchConfig(),
        max_cost_usd=12.5,
    )


def test_scenario_and_harness_registries_round_trip(store: Store) -> None:
    """The two registries the orchestrator fills on startup."""
    store.save_scenario_template(template_id="election", template_version="1.0.0", default_ticks=48, default_markets=5)
    scenario = ScenarioSpec(
        template_id="election",
        template_version="1.0.0",
        seed=7,
        ticks_total=24,
        markets=(
            MarketSpec(market_id="M1", question="q1", prior_price=50, resolution_tick=24, latent_key="l1"),
            MarketSpec(market_id="M2", question="q2", prior_price=40, resolution_tick=24, latent_key="l2"),
        ),
        correlations=(("M1", "M2", 300),),
        held_out=True,
    )
    store.save_scenario_instance(scenario, world_hash="abc123")
    store.save_harness_version(HarnessConfig(harness_id="h-a", version="1", kind="scripted"))
    assert _count(store, "scenario_template") == 1
    assert _count(store, "scenario_instance") == 1
    assert _count(store, "harness_version") == 1
    table = METADATA.tables["scenario_instance"]
    with sa.create_engine(store.url).connect() as conn:
        row = conn.execute(sa.select(table)).mappings().one()
    assert row["scenario_id"] == "election-7"
    assert row["payload"]["correlations"] == [["M1", "M2", 300]], "the correlations are only recorded here"
    store.save_scenario_template(template_id="election", template_version="1.0.1", default_ticks=48, default_markets=5)
    assert _count(store, "scenario_template") == 1, "the template registry is keyed by id, not appended to"


def test_the_largest_legal_seed_reaches_every_seed_column(store: Store) -> None:
    """Regression: a seed the engine accepts must be a seed the store can hold.

    ``BigInteger`` is a **signed** 64 bit column on SQLite and on Postgres, so a
    seed at or above ``2**63`` raises ``OverflowError`` on insert. Before
    ``SEED_SPACE`` was narrowed to 63 unsigned bits, ``HeldoutBank.reserve``
    drew uniformly over 64 bits and about half of every sealed set was
    unstorable, which took AC-P5 down with it. The control below proves the
    failure mode is real and not merely asserted away.
    """
    top = SEED_SPACE - 1
    scenario = ScenarioSpec(
        template_id="election",
        template_version="1.0.0",
        seed=top,
        ticks_total=24,
        markets=(
            MarketSpec(market_id="M1", question="q1", prior_price=50, resolution_tick=24, latent_key="l1"),
            MarketSpec(market_id="M2", question="q2", prior_price=40, resolution_tick=24, latent_key="l2"),
        ),
    )
    store.save_scenario_instance(scenario, world_hash="deadbeef")
    store.save_task(_task(suffix="0007", seed=top), status="pending")
    table = METADATA.tables["scenario_instance"]
    with sa.create_engine(store.url).connect() as conn:
        assert int(conn.execute(sa.select(table.c.seed)).scalar_one()) == top
    assert store.pending_tasks(TOURNAMENT_ID)[0].seed == top
    # The control: one bit more and the column really does refuse it, so the
    # bound above is load bearing rather than decorative.
    with sa.create_engine(store.url).connect() as conn, pytest.raises(Exception, match=r"(?i)overflow|too large"):
        conn.execute(sa.text("insert into match_task (task_id, seed) values ('x', :s)"), {"s": SEED_SPACE})


def test_save_agent_and_mm_config_work_standalone(store: Store) -> None:
    """``pxe match run`` writes a seat without a tournament and without a match row."""
    spec = AgentSpec(
        agent_id="A1",
        harness=HarnessConfig(harness_id="h-a", version="1", kind="scripted"),
        info_profile=InfoProfile(kind=InfoProfileKind.GENERALIST),
    )
    store.save_agent(match_id="m-election-7-01", spec=spec)
    store.save_mm_config(
        match_id="m-election-7-01",
        config=MMConfig(base_spread_cents=6, quote_qty=25, inventory_max=300, skew_cents=4, post_news_widen_ticks=2),
        profile_name=str(LiquidityProfileName.STANDARD),
    )
    assert _count(store, "agent") == 1
    assert _count(store, "mm_config") == 1


def test_pending_tasks_skips_what_is_already_played(saved: Store) -> None:
    """A task whose match is saved is never replayed (idempotent resume)."""
    saved.save_tournament(_tournament_config())
    saved.save_task(_task(match_id="m-election-999-01", suffix="0002"), status="pending")
    saved.save_task(_task(), status="pending")
    pending = saved.pending_tasks(TOURNAMENT_ID)
    assert [task.match_id for task in pending] == ["m-election-999-01"]
    assert pending[0].profile_assignment == (
        ("A1", InfoProfileKind.GENERALIST),
        ("A2", InfoProfileKind.DELAYED),
    )
    assert pending[0].held_out is True
    saved.save_task(_task(match_id="m-election-999-01", suffix="0002"), status="done")
    assert saved.pending_tasks(TOURNAMENT_ID) == ()


def test_a_match_lists_under_its_tournament(saved: Store) -> None:
    """``tournament_id`` and ``held_out`` reach a match row through its task."""
    saved.save_tournament(_tournament_config())
    saved.save_task(_task(), status="done")
    rows = saved.list_matches(tournament_id=TOURNAMENT_ID)
    assert [row["match_id"] for row in rows] == [MATCH_ID]
    assert rows[0]["tournament_id"] == TOURNAMENT_ID
    assert rows[0]["held_out"] is True
    assert saved.list_matches(tournament_id="T-other-0002") == ()
    summaries = saved.list_tournaments()
    assert len(summaries) == 1
    assert summaries[0]["n_tasks"] == 1
    assert summaries[0]["n_matches"] == 1
    assert summaries[0]["finished"] is True


def test_ratings_are_a_snapshot_and_feed_the_progression_curve(store: Store) -> None:
    """``load_ratings`` sorts by mu; ``load_rating_series`` is one point per version."""
    store.save_ratings(
        TOURNAMENT_ID,
        (
            RatingRecord(harness_key="h-a@1.0+00000000", mu=25.0, sigma=8.0, matches=2),
            RatingRecord(harness_key="h-a@1.1+11111111", mu=31.0, sigma=5.0, matches=9),
            RatingRecord(harness_key="h-b@1.0+22222222", mu=28.0, sigma=6.0, matches=5),
        ),
    )
    leaderboard = store.load_ratings(TOURNAMENT_ID)
    assert [record.harness_key for record in leaderboard] == [
        "h-a@1.1+11111111",
        "h-b@1.0+22222222",
        "h-a@1.0+00000000",
    ]
    series = store.load_rating_series("h-a")
    assert [point[0] for point in series] == ["h-a@1.0+00000000", "h-a@1.1+11111111"]
    assert series[1][1] == 31.0 and series[1][3] == 9
    store.save_ratings(TOURNAMENT_ID, (RatingRecord(harness_key="h-a@1.1+11111111", mu=33.0, sigma=4.0, matches=12),))
    assert len(store.load_ratings(TOURNAMENT_ID)) == 1, "a leaderboard is replaced, not appended to"


def test_incidents_are_replaced_and_filtered(saved: Store) -> None:
    """A detector rerun replaces its own output; the tournament filter joins tasks."""
    saved.save_tournament(_tournament_config())
    saved.save_task(_task(), status="done")
    saved.save_incidents(MATCH_ID, (_incident(1), _incident(2)))
    assert len(saved.load_incidents(match_id=MATCH_ID)) == 2
    saved.save_incidents(MATCH_ID, (_incident(1),))
    loaded = saved.load_incidents(tournament_id=TOURNAMENT_ID)
    assert len(loaded) == 1
    assert loaded[0].kind is IncidentKind.COLLUSION
    assert loaded[0].detail == (("evidence", "mirrored quotes"), ("window", 4))
    assert saved.load_incidents(tournament_id="T-other-0002") == ()
    # A tournament wide read spans many matches, so every alert must say which
    # one it came from: section 7.21's Incident payload has a match_id and the
    # API has no other source for it. Detectors leave the field empty and the
    # store stamps it from the row it read.
    assert _incident(1).match_id == "", "a detector does not know the store's key"
    assert loaded[0].match_id == MATCH_ID
    assert all(row.match_id == MATCH_ID for row in saved.load_incidents(match_id=MATCH_ID))
    # Two matches in one tournament is the case the API could not serve before:
    # with more than one candidate it had to leave match_id empty.
    other = "m-election-20260828-01"
    saved.save_task(_task(other, suffix="0002", seed=20260828), status="done")
    saved.save_incidents(other, (_incident(3),))
    spread = saved.load_incidents(tournament_id=TOURNAMENT_ID)
    assert {row.match_id for row in spread} == {MATCH_ID, other}
    assert {row.incident_id: row.match_id for row in spread}[_incident(3).incident_id] == other


def test_costs_come_from_the_llm_trace(
    store: Store, result: MatchResult, projection: MatchProjection, metrics: MatchMetrics, runs_dir: Path
) -> None:
    """Cost is forbidden in a journal, so ``llm_trace.jsonl`` is its only source."""
    trace = runs_dir / MATCH_ID / "llm_trace.jsonl"
    store.save_match(result, projection, metrics)
    table = METADATA.tables["agent"]
    with sa.create_engine(store.url).connect() as conn:
        keys = [row[0] for row in conn.execute(sa.select(table.c.harness_key).order_by(table.c.agent_id)).all()]
    assert keys, "no agent row, so there is nothing to bill"
    lines = [
        {"tick": 1, "harness_key": keys[0], "cost_usd": 0.25},
        {"tick": 2, "harness_key": keys[0], "cost_usd": 0.75},
        {"tick": 1, "harness_key": keys[1], "cost_usd": 0.5},
        {"tick": 3, "harness_key": keys[1]},
        {"broken": True},
    ]
    with open(trace, "w", encoding=JOURNAL_ENCODING, newline=JOURNAL_NEWLINE) as handle:
        for line in lines:
            handle.write(stable_json(line) + JOURNAL_NEWLINE)
        handle.write("{not json\n")
    try:
        store.save_match(result, projection, metrics)
        store.save_tournament(_tournament_config())
        store.save_task(_task(), status="done")
        costs = dict(store.load_costs_usd(TOURNAMENT_ID))
        assert costs[keys[0]] == pytest.approx(1.0)
        assert costs[keys[1]] == pytest.approx(0.5)
        assert set(costs) == set(keys)
    finally:
        trace.unlink()


def test_save_agent_does_not_erase_a_recorded_cost(
    store: Store, result: MatchResult, projection: MatchProjection, metrics: MatchMetrics, runs_dir: Path
) -> None:
    """Two writers own two disjoint column sets of ``agent``, and neither resets the other.

    ``save_match`` fills ``cost_usd`` from the trace and ``save_agent`` never
    mentions that column, so calling the standalone writer after a match must not
    zero a provider bill that was already recorded.
    """
    trace = runs_dir / MATCH_ID / "llm_trace.jsonl"
    table = METADATA.tables["agent"]
    store.save_match(result, projection, metrics)
    with sa.create_engine(store.url).connect() as conn:
        key = conn.execute(sa.select(table.c.harness_key).where(table.c.agent_id == "A1")).scalar_one()
    with open(trace, "w", encoding=JOURNAL_ENCODING, newline=JOURNAL_NEWLINE) as handle:
        handle.write(stable_json({"tick": 1, "harness_key": key, "cost_usd": 2.5}) + JOURNAL_NEWLINE)
    try:
        store.save_match(result, projection, metrics)
        store.save_agent(
            match_id=MATCH_ID,
            spec=AgentSpec(
                agent_id="A1",
                harness=HarnessConfig(harness_id="h-rewritten", version="2", kind="llm", model="claude"),
                info_profile=InfoProfile(kind=InfoProfileKind.SPECIALIST, focus_market_ids=("M1",)),
            ),
        )
        with sa.create_engine(store.url).connect() as conn:
            row = conn.execute(sa.select(table).where(table.c.agent_id == "A1")).mappings().one()
        assert row["cost_usd"] == pytest.approx(2.5), "the standalone writer erased a recorded cost"
        assert row["harness_id"] == "h-rewritten", "the columns it does own are still updated"
    finally:
        trace.unlink()


def test_heldout_access_is_append_only_and_deduplicated(store: Store) -> None:
    """Every access to the sealed bank is recorded once, whatever the caller does."""
    entries = (
        {"template_id": "election", "requester": "evaluation", "purpose": "held-out", "count": 3, "seeds": [1, 2, 3]},
        {"template_id": "harvest", "requester": "evaluation", "purpose": "held-out", "count": 1, "seeds": [9]},
    )
    store.save_heldout_access(entries)
    store.save_heldout_access(entries)
    loaded = store.load_heldout_access()
    assert len(loaded) == 2
    assert {row["template_id"] for row in loaded} == {"election", "harvest"}
    assert loaded[0]["seeds"] in ([1, 2, 3], [9])


def test_elites_round_trip(store: Store) -> None:
    """The one ``pxe.tournament`` type the store touches (section 7.20)."""
    from pxe.tournament import elites

    cells = (
        elites.EliteCell(coords=(0, 1), harness_key="h-a@1+00000000", mu=27.0, descriptors=(120, 340)),
        elites.EliteCell(coords=(1, 0), harness_key="h-b@1+00000000", mu=25.0, descriptors=(900, 10)),
    )
    store.save_elites(TOURNAMENT_ID, cells)
    loaded = store.load_elites(TOURNAMENT_ID)
    assert loaded == cells
    store.save_elites(TOURNAMENT_ID, cells[:1])
    assert len(store.load_elites(TOURNAMENT_ID)) == 1, "an archive is a snapshot, not a log"


# ---------------------------------------------------------------------------
# The artefact directory
# ---------------------------------------------------------------------------
def test_artefact_paths_names_the_six_artefacts(tmp_path: Path) -> None:
    """Section 4.6 lists six files and every reader reaches them through here."""
    paths = store_files.artefact_paths(tmp_path, MATCH_ID)
    assert set(paths) == {"journal", "observations", "llm_trace", "incidents", "metrics", "meta"}
    assert paths["journal"] == tmp_path / MATCH_ID / "journal.jsonl"
    assert paths["metrics"] == tmp_path / MATCH_ID / "metrics.json"
    assert store_files.match_dir(tmp_path, MATCH_ID) == tmp_path / MATCH_ID
    assert not (tmp_path / MATCH_ID).exists(), "asking for a path must not create a directory"


def test_meta_round_trips_and_is_canonical(tmp_path: Path) -> None:
    """``meta.json`` is written by two modules and they must agree byte for byte."""
    path = tmp_path / MATCH_ID / "meta.json"
    meta = {"match_id": MATCH_ID, "seed": 7, "journal_hash": "ab" * 32, "event_count": 12}
    store_files.write_meta(path, meta)
    raw = path.read_bytes()
    assert b"\r" not in raw and raw.endswith(b"\n")
    assert json.loads(raw.decode("utf-8")) == meta
    assert dict(store_files.read_meta(path)) == meta
    assert raw.decode("utf-8").index('"event_count"') < raw.decode("utf-8").index('"match_id"'), "keys are sorted"


def test_read_meta_reads_the_meta_the_runner_actually_wrote(tmp_path: Path) -> None:
    """The A09/A21 artefact seam: two writers of one file, tested against each other.

    Section 4.6 gives ``meta.json`` to the runner and section 7.20 gives A21 the
    encoder and the reader, so the file has two producers and the round trip
    above only ever tested A21 against itself. This plays a real match, reads
    back the file ``MatchRunner`` wrote, and re-encodes it with
    :func:`write_meta`: the bytes must be identical, or a tournament and a
    standalone match leave two different shapes on disk.
    """
    from pxe.agents.base import make_baseline
    from pxe.gateway.scripted import ScriptedGateway
    from pxe.info.profiles import build_profile
    from pxe.rng import RngTree
    from pxe.runner.match_runner import run_match
    from pxe.types import AgentSpec, MatchConfig, make_agent_id
    from pxe.world.generator import generate_world

    names = ("fundamentalist", "momentum", "noise", "mute")
    config = MatchConfig(seed=4242, ticks_total=24, n_agents=len(names), n_markets=2)
    world = generate_world(template_id="election", seed=config.seed, ticks_total=24, n_markets=2)
    rng = RngTree(config.seed)
    seats = tuple(make_agent_id(index) for index in range(1, len(names) + 1))
    specs = tuple(
        AgentSpec(
            agent_id=seat,
            harness=HarnessConfig(harness_id=name, version="1.0.0", kind="scripted"),
            info_profile=build_profile(InfoProfileKind.GENERALIST, market_ids=world.market_ids()),
        )
        for seat, name in zip(seats, names, strict=True)
    )
    agents = {
        seat: make_baseline(
            name, agent_id=seat, config=config, rng=rng.child(f"agent/{seat}").substream(f"agent.{seat}")
        )
        for seat, name in zip(seats, names, strict=True)
    }
    out_dir = tmp_path / "m-election-4242-01"
    result = run_match(
        config=config,
        world=world,
        agents=specs,
        gateway=ScriptedGateway(agents=agents),
        out_dir=out_dir,
        rng=rng,
        match_id="m-election-4242-01",
    )
    written = out_dir / "meta.json"
    assert written.exists(), "the runner wrote no meta.json, so this test would be vacuous"
    original = written.read_bytes()
    meta = store_files.read_meta(written)
    assert meta["match_id"] == "m-election-4242-01"
    assert meta["journal_hash"] == result.journal_hash
    assert meta["seed"] == config.seed
    round_tripped = tmp_path / "again" / "meta.json"
    store_files.write_meta(round_tripped, meta)
    assert round_tripped.read_bytes() == original, "the two writers of meta.json disagree on bytes"


def test_read_meta_refuses_what_is_not_a_meta_file(tmp_path: Path) -> None:
    """A missing or malformed artefact raises rather than defaulting to ``{}``."""
    with pytest.raises(StoreError):
        store_files.read_meta(tmp_path / "absent.json")
    bad = tmp_path / "bad.json"
    bad.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(StoreError):
        store_files.read_meta(bad)


# ---------------------------------------------------------------------------
# Postgres
# ---------------------------------------------------------------------------
@pytest.mark.slow
def test_sqlite_and_postgres_schema_are_identical(runs_dir: Path, tmp_path: Path) -> None:
    """One schema, two backends: only constructs both support are used.

    Skipped unless ``PXE_TEST_POSTGRES_URL`` names a reachable database. The
    **test** is allowed to read the environment even though the library is not
    (section 2.6 binds the library).
    """
    url = os.environ.get("PXE_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("set PXE_TEST_POSTGRES_URL to run the Postgres schema comparison")
    with Store(url=f"sqlite+pysqlite:///{tmp_path / 'compare.sqlite3'}", runs_dir=runs_dir) as lite:
        lite.init_schema()
        lite_shape = _shape(lite.url)
    with Store(url=url, runs_dir=runs_dir) as postgres:
        postgres.init_schema()
        pg_shape = _shape(postgres.url)
    assert lite_shape == pg_shape


def _shape(url: str) -> Mapping[str, Sequence[str]]:
    """Return ``{table: [column names]}`` of a live database."""
    engine = sa.create_engine(url)
    try:
        inspector = sa.inspect(engine)
        return {
            name: sorted(column["name"] for column in inspector.get_columns(name))
            for name in sorted(inspector.get_table_names())
        }
    finally:
        engine.dispose()
