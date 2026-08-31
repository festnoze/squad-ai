"""The projection database (CONTRACTS section 7.20, A21).

``Store`` is two things behind one object: a SQLAlchemy Core connection to a
projection database, and a reader of the ``runs/<match_id>/`` artefacts that
database is projected from. The split matters because of section 4.1: **the
journal is the source of truth and every table here is disposable.**
``Store.rebuild`` drops the thirteen match scoped tables and re imports them from
``runs/*/journal.jsonl``, and ``test_store.py::test_rebuild_from_journals_reproduces_every_table``
compares the tables row by row before and after, so the claim is proven rather
than asserted in a docstring.

Three rules of section 7.20 shape every method below:

* **One writing method per table.** The table in section 7.20 is the map;
  ``models.py`` repeats it as a comment on each table. ``save_match`` writes
  thirteen of them in a single transaction, delegating the ``agent`` and
  ``mm_config`` rows to the same private row builders ``save_agent`` and
  ``save_mm_config`` use, so a standalone ``pxe match run`` and a tournament
  produce identical rows.
* **Only the orchestrator process writes.** Workers run matches in parallel and
  return a ``MatchResult`` plus paths; the orchestrator calls ``save_match``.
  With SQLite that avoids the writer lock entirely and with Postgres it keeps
  ``resume()`` idempotent for the same reason. ``Store`` is therefore **not**
  thread safe and does not pretend to be.
* **Nothing reads the environment.** The URL arrives as an argument
  (``--db-url`` in the CLI) or is built by :func:`default_store_url`. Section 2.6
  forbids a module reading ``os.environ`` on its own, and a store that silently
  points at a different database than the one the caller printed is the worst
  possible way to learn that rule.

``save_match`` reads the journal of the match it is saving. That is deliberate
and it is what the writer table of section 7.20 asks for (``news_item`` "from the
journal ``NewsPublished`` events", ``mm_config`` "from ``MatchStarted.mm_config``",
``position_snapshot`` from the events): ``MatchResult`` carries neither the seats
nor the news, and re deriving them from a live engine would make the row
unreproducible by ``rebuild``.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from hashlib import blake2b
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, TypeVar

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Connection, Engine

from pxe.errors import StoreError
from pxe.events import (
    JOURNAL_ENCODING,
    JOURNAL_NEWLINE,
    Event,
    MarketCancelled,
    MarketResolved,
    MatchEnded,
    MatchStarted,
    NewsPublished,
    PositionSnapshot,
    SettlementApplied,
    canonical_json,
    journal_hash,
)
from pxe.journal import read_journal
from pxe.metrics.aggregate import MatchMetrics, compute_all, read_metrics
from pxe.metrics.projection import MatchProjection, project
from pxe.store.files import artefact_paths
from pxe.store.models import MATCH_SCOPED_TABLES as _MATCH_SCOPED_TABLES
from pxe.store.models import (
    METADATA,
    STORE_SCHEMA_VERSION,
    agent,
    elite_cell,
    harness_version,
    heldout_registry,
    incident,
    match,
    match_task,
    metric_record,
    mm_config,
    news_item,
    order,
    position_snapshot,
    prediction,
    rating_record,
    resolution,
    scenario_instance,
    scenario_template,
    settlement,
    signal,
    store_schema,
    tick,
    tournament,
    trade,
)
from pxe.types import (
    AgentSpec,
    HarnessConfig,
    Incident,
    IncidentKind,
    InfoProfileKind,
    MatchRanking,
    MatchResult,
    MatchTask,
    MMConfig,
    RatingRecord,
    ScenarioSpec,
    TournamentConfig,
    config_from_journal_dict,
    config_to_journal_dict,
    harness_key,
    incident_detail_from_dict,
    incident_detail_to_dict,
    market_spec_from_dict,
    scenario_to_journal_dict,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    # The one `pxe.tournament` name the store is allowed to know (section 7.20).
    # It is behind TYPE_CHECKING and not a plain import so that the store never
    # pulls the tournament package in at runtime: the arrow runs store -> nothing
    # and `pxe.tournament.orchestrator` imports this module, not the reverse.
    from pxe.tournament.elites import EliteCell

__all__ = ["STORE_SCHEMA_VERSION", "default_store_url", "Store"]

#: Worst case number of bound parameters per statement. SQLite's historical
#: ceiling is 999, so rows are chunked to stay under it whatever the backend:
#: a few extra INSERT statements on a table of four hundred rows cost nothing,
#: and a "too many SQL variables" failure on someone else's SQLite build costs a
#: debugging session.
_MAX_BOUND_PARAMETERS = 900

#: The single row of ``store_schema``.
_SCHEMA_MARKER = "pxe"

#: The ``resolution`` table's ``mode``: how a market left the board.
_MODE_RESOLUTION = "resolution"
_MODE_CANCELLATION = "cancellation"

#: One event class, for the typed filter below.
E = TypeVar("E", bound=Event)


def default_store_url(runs_dir: Path) -> str:
    """Return the default database URL for a runs directory.

    This is the one spelling of it. ``Store`` calls it when ``url`` is ``None``,
    ``pxe api serve`` and ``pxe store init`` call it so their help text matches
    reality, and nobody writes the ``sqlite+pysqlite`` prefix by hand.

    Args:
        runs_dir: The runs root the database lives in.

    Returns:
        ``f"sqlite+pysqlite:///{runs_dir / 'pxe.sqlite3'}"``.
    """
    return f"sqlite+pysqlite:///{Path(runs_dir) / 'pxe.sqlite3'}"


# --------------------------------------------------------------------------
# Statement helpers. Private: the contract publishes no writer of its own.
# --------------------------------------------------------------------------
def _chunks(rows: Sequence[Mapping[str, Any]], n_columns: int) -> list[Sequence[Mapping[str, Any]]]:
    """Split ``rows`` so no statement exceeds :data:`_MAX_BOUND_PARAMETERS`.

    Args:
        rows: The rows of one INSERT.
        n_columns: Number of columns each row binds.

    Returns:
        A list of row slices, each safe to send as one statement.
    """
    size = max(1, _MAX_BOUND_PARAMETERS // max(1, n_columns))
    return [rows[start : start + size] for start in range(0, len(rows), size)]


def _upsert(conn: Connection, table: sa.Table, rows: Sequence[Mapping[str, Any]]) -> None:
    """Insert ``rows``, updating the columns they carry on a primary key clash.

    This is the one place an ``ON CONFLICT`` clause exists (section 7.20), and it
    is dialect aware because SQLite and Postgres spell it in two different
    modules. Only the keys present in ``rows`` are updated, which is what lets
    two writers own two disjoint column sets of the same table without one
    resetting the other's columns to their defaults.

    Args:
        conn: An open connection inside a transaction.
        table: Destination table.
        rows: Rows to write. Every row must carry the same keys, because a
            multi valued INSERT binds one column list.

    Raises:
        StoreError: If the rows disagree on their key set, or if the backend is
            neither SQLite nor Postgres (section 7.20 supports exactly those
            two, and a silent fallback to plain INSERT would break idempotency).
    """
    if not rows:
        return
    keys = tuple(rows[0].keys())
    if any(tuple(row.keys()) != keys for row in rows):
        raise StoreError("every row of one upsert must carry the same columns", table=table.name)
    pk_names = frozenset(column.name for column in table.primary_key.columns)
    updatable = [name for name in keys if name not in pk_names]
    dialect = conn.engine.dialect.name
    for slice_ in _chunks(rows, len(keys)):
        if dialect == "sqlite":
            sqlite_stmt = sqlite_insert(table).values([dict(row) for row in slice_])
            excluded = sqlite_stmt.excluded
            conn.execute(
                sqlite_stmt.on_conflict_do_update(
                    index_elements=sorted(pk_names),
                    set_={name: excluded[name] for name in updatable},
                )
                if updatable
                else sqlite_stmt.on_conflict_do_nothing(index_elements=sorted(pk_names))
            )
        elif dialect == "postgresql":
            pg_stmt = pg_insert(table).values([dict(row) for row in slice_])
            pg_excluded = pg_stmt.excluded
            conn.execute(
                pg_stmt.on_conflict_do_update(
                    index_elements=sorted(pk_names),
                    set_={name: pg_excluded[name] for name in updatable},
                )
                if updatable
                else pg_stmt.on_conflict_do_nothing(index_elements=sorted(pk_names))
            )
        else:
            raise StoreError("unsupported database backend", dialect=dialect)


def _insert(conn: Connection, table: sa.Table, rows: Sequence[Mapping[str, Any]]) -> None:
    """Insert ``rows`` in safe sized chunks, with no conflict handling.

    Used by ``save_match``, which deletes the rows of the match first: a plain
    INSERT after a DELETE is idempotent, and it also removes rows a shorter
    journal no longer produces, which an upsert would silently leave behind.

    Args:
        conn: An open connection inside a transaction.
        table: Destination table.
        rows: Rows to write.
    """
    if not rows:
        return
    for slice_ in _chunks(rows, len(rows[0])):
        conn.execute(sa.insert(table).values([dict(row) for row in slice_]))


def _delete_match(conn: Connection, table: sa.Table, match_id: str) -> None:
    """Delete every row of one match from a match scoped table.

    Args:
        conn: An open connection inside a transaction.
        table: A table carrying a ``match_id`` column.
        match_id: The match to clear.
    """
    conn.execute(sa.delete(table).where(table.c.match_id == match_id))


def _split_harness_key(key: str) -> tuple[str, str]:
    """Split a harness key into ``(harness_id, version)`` (section 2.2).

    The format is ``<harness_id>@<version>+<config_hash[:8]>``. A key that does
    not carry both separators yields the whole string as the id and an empty
    version rather than raising: this is a display and grouping helper, and a
    hand written key in a fixture is not a reason to refuse to persist a rating.

    Args:
        key: The harness key.

    Returns:
        The harness id and the version.
    """
    if "@" not in key:
        return (key, "")
    harness_id, rest = key.split("@", 1)
    version = rest.rsplit("+", 1)[0] if "+" in rest else rest
    return (harness_id, version)


def _llm_costs(path: Path) -> Mapping[str, float]:
    """Sum ``cost_usd`` per harness key over one ``llm_trace.jsonl``.

    The trace is the only artefact carrying a provider bill: cost is forbidden in
    a journal (section 3.5), so ``agent.cost_usd`` and therefore
    ``load_costs_usd`` have no other source. A missing file is the normal case
    for a scripted match and yields an empty mapping rather than an error.

    Args:
        path: ``runs/<match_id>/llm_trace.jsonl``.

    Returns:
        A mapping from harness key to total USD. A line without a ``harness_key``
        or without a numeric ``cost_usd`` is skipped: the trace is written by the
        gateway across retries and a truncated last line must not lose a whole
        match.
    """
    if not path.exists():
        return {}
    totals: dict[str, float] = {}
    with open(path, encoding=JOURNAL_ENCODING, newline=JOURNAL_NEWLINE) as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            try:
                entry = json.loads(text)
            except ValueError:
                continue
            if not isinstance(entry, dict):
                continue
            key = entry.get("harness_key")
            cost = entry.get("cost_usd")
            if not isinstance(key, str) or not isinstance(cost, (int, float)) or isinstance(cost, bool):
                continue
            totals[key] = totals.get(key, 0.0) + float(cost)
    return totals


def _of_type(events: Sequence[Event], kind: type[E]) -> tuple[E, ...]:
    """Return every event of one type, in journal order, correctly typed.

    ``pxe.journal.filter_events`` is the sibling of this helper but it is
    variadic and therefore returns ``tuple[Event, ...]``, which would force an
    ``isinstance`` narrowing at every field access below.

    Args:
        events: The journal, ascending by ``seq``.
        kind: The event class to keep.

    Returns:
        The matching events.
    """
    return tuple(event for event in events if isinstance(event, kind))


def _match_started_of(events: Sequence[Event]) -> MatchStarted:
    """Return the ``MatchStarted`` of a journal.

    Args:
        events: The journal.

    Returns:
        The first ``MatchStarted``.

    Raises:
        StoreError: If there is none. Without it there is no seed, no seat list
            and no config, so there is no match row to write.
    """
    for event in events:
        if isinstance(event, MatchStarted):
            return event
    raise StoreError("a journal without MatchStarted cannot be persisted (section 4.4)")


def _agent_row(match_id: str, entry: Mapping[str, Any], *, cost_usd: float | None = None) -> dict[str, Any]:
    """Build one ``agent`` row from a ``MatchStarted.agents`` entry.

    Args:
        match_id: The match.
        entry: One mapping of ``MatchStarted.agents``, that is ``agent_id``,
            ``harness_id``, ``harness_version``, ``config_hash``,
            ``info_profile_kind`` and ``ranked``.
        cost_usd: Provider bill of that seat, or ``None`` to leave the column to
            its default and to any value a previous writer already stored.

    Returns:
        The row mapping.
    """
    harness_id = str(entry["harness_id"])
    version = str(entry["harness_version"])
    config_hash = str(entry["config_hash"])
    row: dict[str, Any] = {
        "match_id": match_id,
        "agent_id": str(entry["agent_id"]),
        "harness_key": f"{harness_id}@{version}+{config_hash[:8]}",
        "harness_id": harness_id,
        "harness_version": version,
        "config_hash": config_hash,
        "info_profile_kind": str(entry["info_profile_kind"]),
        "ranked": bool(entry["ranked"]),
    }
    if cost_usd is not None:
        row["cost_usd"] = float(cost_usd)
    return row


def _mm_config_row(match_id: str, config: MMConfig, profile_name: str) -> dict[str, Any]:
    """Build the ``mm_config`` row of one match.

    Args:
        match_id: The match.
        config: The market maker parameters that were played.
        profile_name: Name of the FR-5.8.6 preset they came from.

    Returns:
        The row mapping.
    """
    return {
        "match_id": match_id,
        "profile_name": profile_name,
        "base_spread_cents": config.base_spread_cents,
        "quote_qty": config.quote_qty,
        "inventory_max": config.inventory_max,
        "skew_cents": config.skew_cents,
        "post_news_widen_ticks": config.post_news_widen_ticks,
        "widen_multiplier": config.widen_multiplier,
        "enabled": config.enabled,
    }


class Store:
    """Projection database plus artefact directory.

    Not thread safe: only the orchestrator process writes (section 7.20). Use it
    as a context manager, or call :meth:`close` when done, so the engine's
    connection pool is disposed of and a SQLite file is released on Windows.

    Attributes are private; every access goes through a method, because the API
    layer (A22) and the orchestrator (A19) code against this class and a public
    ``_engine`` would become a second, untested interface immediately.
    """

    def __init__(self, *, url: str | None = None, runs_dir: Path) -> None:
        """Open (or create) the projection database of one runs directory.

        The schema is **not** created here: :meth:`init_schema` is a separate,
        explicit call, because a reader that opens a database it did not create
        must not silently write to it.

        Args:
            url: SQLAlchemy URL. ``None`` means :func:`default_store_url`, that
                is SQLite on a file inside ``runs_dir``. Any Postgres URL is a
                drop in replacement.
            runs_dir: The artefact root, ``runs/``. Created if absent, because
                the default SQLite file lives in it.
        """
        self._runs_dir = Path(runs_dir)
        self._runs_dir.mkdir(parents=True, exist_ok=True)
        self._url = url if url is not None else default_store_url(self._runs_dir)
        self._engine: Engine = sa.create_engine(self._url)

    # ----------------------------------------------------------------------
    # Lifecycle
    # ----------------------------------------------------------------------
    @property
    def url(self) -> str:
        """The URL this store is connected to, as resolved at construction."""
        return self._url

    @property
    def runs_dir(self) -> Path:
        """The artefact root this store reads journals and metrics from."""
        return self._runs_dir

    def init_schema(self) -> None:
        """Create every table if it is missing, and stamp the schema version.

        Idempotent: ``create_all`` skips what exists. There is no Alembic in v1,
        so the version stamp is the whole migration story: a database created by
        another :data:`~pxe.store.models.STORE_SCHEMA_VERSION` is refused rather
        than half read, and the fix is to delete it and rebuild from the
        journals.

        Raises:
            StoreError: If the database was created by a different schema
                version.
        """
        METADATA.create_all(self._engine)
        with self._engine.begin() as conn:
            found = conn.execute(sa.select(store_schema.c.version)).scalars().first()
            if found is None:
                conn.execute(sa.insert(store_schema).values(marker=_SCHEMA_MARKER, version=STORE_SCHEMA_VERSION))
            elif str(found) != STORE_SCHEMA_VERSION:
                raise StoreError(
                    "database was created by another store schema version; rebuild it from the journals",
                    found=str(found),
                    expected=STORE_SCHEMA_VERSION,
                )

    def schema_version(self) -> str:
        """Return the schema version recorded in the database.

        Returns:
            The stamped version, or :data:`~pxe.store.models.STORE_SCHEMA_VERSION`
            when the schema has never been initialised (an empty database is
            about to become the current version, not an unknown one).
        """
        with self._engine.connect() as conn:
            if not sa.inspect(conn).has_table(store_schema.name):
                return STORE_SCHEMA_VERSION
            found = conn.execute(sa.select(store_schema.c.version)).scalars().first()
        return STORE_SCHEMA_VERSION if found is None else str(found)

    def close(self) -> None:
        """Dispose of the connection pool. Safe to call twice."""
        self._engine.dispose()

    def __enter__(self) -> Store:
        """Return self, so ``with Store(runs_dir=...) as store`` works."""
        return self

    def __exit__(self, *exc: Any) -> None:
        """Close the store, whatever happened inside the block."""
        self.close()

    # ----------------------------------------------------------------------
    # Writers
    # ----------------------------------------------------------------------
    def save_scenario_template(
        self, *, template_id: str, template_version: str, default_ticks: int, default_markets: int
    ) -> None:
        """Write one ``scenario_template`` row.

        Called by ``TournamentOrchestrator.__init__``, once per template id.

        Args:
            template_id: Template identifier, for example ``"election"``.
            template_version: Version of the template.
            default_ticks: Default horizon of the template.
            default_markets: Default market count of the template.
        """
        with self._engine.begin() as conn:
            _upsert(
                conn,
                scenario_template,
                [
                    {
                        "template_id": template_id,
                        "template_version": template_version,
                        "default_ticks": int(default_ticks),
                        "default_markets": int(default_markets),
                    }
                ],
            )

    def save_scenario_instance(self, scenario: ScenarioSpec, *, world_hash: str) -> None:
        """Write one ``scenario_instance`` row, keyed by ``<template_id>-<seed>``.

        The whole scenario is kept as a canonical payload as well as in extracted
        columns: correlations and scripted cancellations are what make a world
        reproducible and no journal event carries them, so this row is the only
        record of them.

        Args:
            scenario: The generated world.
            world_hash: A digest of the world, supplied by the caller (the
                orchestrator, after ``generate_world``).
        """
        with self._engine.begin() as conn:
            _upsert(
                conn,
                scenario_instance,
                [
                    {
                        "scenario_id": f"{scenario.template_id}-{scenario.seed}",
                        "template_id": scenario.template_id,
                        "template_version": scenario.template_version,
                        "seed": int(scenario.seed),
                        "ticks_total": int(scenario.ticks_total),
                        "n_markets": len(scenario.markets),
                        "world_hash": world_hash,
                        "held_out": bool(scenario.held_out),
                        "talking_mode": bool(scenario.talking_mode),
                        "liquidity_profile_name": str(scenario.liquidity_profile_name),
                        "notes": scenario.notes,
                        "payload": scenario_to_journal_dict(scenario),
                    }
                ],
            )

    def save_harness_version(self, harness: HarnessConfig) -> None:
        """Write one ``harness_version`` row.

        Called by the orchestrator on startup and by ``HallOfFame.freeze``
        (T3.4): a frozen version must be replayable, which means its prompt and
        its parameters have to survive somewhere other than the TOML that
        produced them.

        Args:
            harness: The :class:`~pxe.types.HarnessConfig` to persist.
        """
        with self._engine.begin() as conn:
            _upsert(
                conn,
                harness_version,
                [
                    {
                        "harness_key": harness_key(harness),
                        "harness_id": harness.harness_id,
                        "version": harness.version,
                        "kind": harness.kind,
                        "model": harness.model,
                        "config_hash": harness.config_hash,
                        "system_prompt": harness.system_prompt,
                        "params": [[key, value] for key, value in harness.params],
                    }
                ],
            )

    def save_agent(self, *, match_id: str, spec: AgentSpec) -> None:
        """Write one ``agent`` row from a seat definition.

        This is the standalone path, used by ``pxe match run`` before or after a
        match. ``save_match`` writes the same rows from ``MatchStarted.agents``
        inside its own transaction, adding the ``cost_usd`` column; this method
        deliberately does **not** write that column, so calling it after a
        ``save_match`` cannot zero a recorded provider bill.

        Args:
            match_id: The match the seat belongs to.
            spec: The seat.
        """
        row = _agent_row(
            match_id,
            {
                "agent_id": spec.agent_id,
                "harness_id": spec.harness.harness_id,
                "harness_version": spec.harness.version,
                "config_hash": spec.harness.config_hash,
                "info_profile_kind": str(spec.info_profile.kind),
                "ranked": spec.ranked,
            },
        )
        with self._engine.begin() as conn:
            _upsert(conn, agent, [row])

    def save_mm_config(self, *, match_id: str, config: MMConfig, profile_name: str) -> None:
        """Write the ``mm_config`` row of one match.

        Args:
            match_id: The match.
            config: The market maker parameters that were played, that is
                ``MatchConfig.mm`` and never the preset the name refers to
                (section 2.6 makes the config authoritative).
            profile_name: Name of the FR-5.8.6 preset.
        """
        with self._engine.begin() as conn:
            _upsert(conn, mm_config, [_mm_config_row(match_id, config, profile_name)])

    def save_match(self, result: MatchResult, projection: MatchProjection, metrics: MatchMetrics) -> None:
        """Mirror one finished match into the thirteen match scoped tables.

        Everything is written in a single transaction, and every row of every
        table is deleted for this ``match_id`` first, so re running the call on
        the same match duplicates nothing and leaves nothing stale behind
        (idempotent resume, T3.1).

        The journal of the match is read here: ``news_item``,
        ``position_snapshot``, ``resolution``, ``settlement``, ``agent`` and
        ``mm_config`` come from events that no ``MatchResult`` and no
        ``MatchProjection`` carries, which is exactly what the writer table of
        section 7.20 prescribes.

        Args:
            result: The result the runner returned. Only its ``match_id``,
                ``journal_path``, ``journal_hash``, ``event_count``,
                ``mm_pnl_cents`` and ``fees_collected_cents`` are used; every
                other column is derived from the journal, so a rebuilt row is
                identical to a freshly saved one.
            projection: ``project(events)`` of the same match.
            metrics: ``compute_all(projection)``, the source of ``metric_record``
                and the same numbers as ``runs/<match_id>/metrics.json``.

        Raises:
            StoreError: If the journal cannot be found, or if it holds no
                ``MatchStarted``.
        """
        match_id = result.match_id
        events = read_journal(self._journal_path(match_id, hint=result.journal_path))
        started = _match_started_of(events)
        ended_events = _of_type(events, MatchEnded)
        ended = ended_events[-1] if ended_events else None
        config = config_from_journal_dict(started.config)
        costs = _llm_costs(artefact_paths(self._runs_dir, match_id)["llm_trace"])
        agent_rows = [
            _agent_row(match_id, entry, cost_usd=costs.get(_agent_row(match_id, entry)["harness_key"], 0.0))
            for entry in started.agents
        ]
        winner = self._winner_of(ended, agent_rows)

        with self._engine.begin() as conn:
            for table_name in _MATCH_SCOPED_TABLES:
                _delete_match(conn, METADATA.tables[table_name], match_id)
            _insert(
                conn,
                match,
                [
                    {
                        "match_id": match_id,
                        "template_id": started.scenario_template_id,
                        "template_version": started.scenario_template_version,
                        "seed": int(started.seed),
                        "ticks_total": int(started.ticks_total),
                        "n_markets": len(started.markets),
                        "n_agents": sum(1 for row in agent_rows if row["ranked"]),
                        "initial_cash_cents": int(started.initial_cash_cents),
                        "journal_path": str(result.journal_path),
                        "journal_hash": result.journal_hash,
                        "event_count": int(result.event_count),
                        "finished": ended is not None,
                        "final_tick": 0 if ended is None else int(ended.final_tick),
                        "end_reason": "" if ended is None else str(ended.reason),
                        "winner_agent_id": winner[0],
                        "winner_harness_key": winner[1],
                        "mm_pnl_cents": int(result.mm_pnl_cents),
                        "fees_collected_cents": int(result.fees_collected_cents),
                        "talking_mode": bool(config.talking_mode),
                        "liquidity_profile_name": str(config.liquidity_profile_name),
                        "config": dict(started.config),
                        "rankings": [dict(row) for row in (() if ended is None else ended.rankings)],
                    }
                ],
            )
            _insert(conn, agent, agent_rows)
            _insert(conn, mm_config, [_mm_config_row(match_id, config.mm, str(config.liquidity_profile_name))])
            _insert(conn, tick, self._tick_rows(match_id, projection, events))
            _insert(conn, news_item, self._news_rows(match_id, events))
            _insert(conn, signal, self._signal_rows(match_id, projection))
            _insert(conn, order, self._order_rows(match_id, projection))
            _insert(conn, trade, self._trade_rows(match_id, projection))
            _insert(conn, position_snapshot, self._snapshot_rows(match_id, events))
            _insert(conn, prediction, self._prediction_rows(match_id, projection))
            _insert(conn, resolution, self._resolution_rows(match_id, events))
            _insert(conn, settlement, self._settlement_rows(match_id, events))
            _insert(conn, metric_record, self._metric_rows(match_id, metrics))

    def save_tournament(self, config: TournamentConfig) -> None:
        """Write one ``tournament`` row.

        ``config.gateway`` is not persisted: it is wall clock, cost and provider
        dependent (section 2.6) and has no business sitting next to reproducible
        data.

        Args:
            config: The tournament definition.
        """
        with self._engine.begin() as conn:
            _upsert(
                conn,
                tournament,
                [
                    {
                        "tournament_id": config.tournament_id,
                        "format": str(config.format),
                        "n_harnesses": len(config.harnesses),
                        "agents_per_match": int(config.agents_per_match),
                        "rounds": int(config.rounds),
                        "template_ids": list(config.template_ids),
                        "seeds": [int(seed) for seed in config.seeds],
                        "harness_keys": [harness_key(harness) for harness in config.harnesses],
                        "background_baselines": list(config.background_baselines),
                        "max_cost_usd": float(config.max_cost_usd),
                        "match_defaults": config_to_journal_dict(config.match_defaults),
                    }
                ],
            )

    def save_task(self, task: MatchTask, *, status: str) -> None:
        """Write one planned unit of tournament work and its status.

        The tournament id is taken from the task id prefix when the task carries
        one, and is otherwise the empty string: ``MatchTask`` has no
        ``tournament_id`` field, and :meth:`pending_tasks` is scoped by
        tournament, so the id has to come from somewhere. See CONTRACT ISSUES.

        Args:
            task: The planned task.
            status: Free form lifecycle marker. ``"done"`` is the one value with
                a meaning here: :meth:`pending_tasks` never returns a task that
                carries it.
        """
        with self._engine.begin() as conn:
            _upsert(
                conn,
                match_task,
                [
                    {
                        "tournament_id": _tournament_id_of(task),
                        "task_id": task.task_id,
                        "match_id": task.match_id,
                        "template_id": task.template_id,
                        "seed": int(task.seed),
                        "status": status,
                        "held_out": bool(task.held_out),
                        "agent_ids": list(task.agent_ids),
                        "harness_keys": list(task.harness_keys),
                        "profile_assignment": [[agent_id, str(kind)] for agent_id, kind in task.profile_assignment],
                    }
                ],
            )

    def save_ratings(self, tournament_id: str, records: Sequence[RatingRecord]) -> None:
        """Replace the leaderboard of one tournament.

        A leaderboard is a snapshot and not a log: every ``RatingService.update``
        publishes the whole standings, so the rows of this tournament are deleted
        and rewritten. Keeping the history would need a round index that
        ``RatingRecord`` does not carry.

        Args:
            tournament_id: The tournament.
            records: The standings.
        """
        rows = [
            {
                "tournament_id": tournament_id,
                "harness_key": record.harness_key,
                "harness_id": _split_harness_key(record.harness_key)[0],
                "version": _split_harness_key(record.harness_key)[1],
                "mu": float(record.mu),
                "sigma": float(record.sigma),
                "matches": int(record.matches),
            }
            for record in records
        ]
        with self._engine.begin() as conn:
            conn.execute(sa.delete(rating_record).where(rating_record.c.tournament_id == tournament_id))
            _insert(conn, rating_record, rows)

    def save_elites(self, tournament_id: str, cells: Sequence[EliteCell]) -> None:
        """Replace the MAP-Elites archive of one tournament (T5.2).

        Like the leaderboard, the archive is a snapshot: a cell holds the best
        ``mu`` seen, so re publishing it replaces the previous grid.

        Args:
            tournament_id: The tournament.
            cells: The occupied cells.
        """
        rows = [
            {
                "tournament_id": tournament_id,
                "coords_key": "-".join(str(int(value)) for value in cell.coords),
                "coords": [int(value) for value in cell.coords],
                "harness_key": cell.harness_key,
                "mu": float(cell.mu),
                "descriptors": [int(value) for value in cell.descriptors],
            }
            for cell in cells
        ]
        with self._engine.begin() as conn:
            conn.execute(sa.delete(elite_cell).where(elite_cell.c.tournament_id == tournament_id))
            _insert(conn, elite_cell, rows)

    def save_heldout_access(self, entries: Sequence[Mapping[str, Any]]) -> None:
        """Append the held-out bank access log to the database (AC-P5).

        Every access to the sealed bank is journalled by ``HeldoutBank.draw`` and
        mirrored here so a report can show it without reading the bank's own
        file. The primary key is a digest of the entry, so re importing the same
        log twice is a no op rather than a duplicated audit trail.

        Args:
            entries: ``HeldoutBank.access_log_entries()``. Only ``template_id``,
                ``requester``, ``purpose`` and ``count`` are extracted into
                columns; the whole entry is kept as a canonical payload, so a
                field added later is persisted without a schema change.
        """
        rows = []
        for entry in entries:
            payload = dict(entry)
            digest = blake2b(canonical_json(payload).encode(JOURNAL_ENCODING), digest_size=8).hexdigest()
            rows.append(
                {
                    "access_id": f"h-{digest}",
                    "template_id": str(payload.get("template_id", "")),
                    "requester": str(payload.get("requester", "")),
                    "purpose": str(payload.get("purpose", "")),
                    "count": int(payload.get("count", 0)),
                    "payload": payload,
                }
            )
        with self._engine.begin() as conn:
            _upsert(conn, heldout_registry, rows)

    def save_incidents(self, match_id: str, incidents: Sequence[Incident]) -> None:
        """Replace the integrity incidents of one match.

        Detectors run offline over a finished journal and their ids restart at
        ``i-0001`` on every run, so a rerun replaces the previous output instead
        of accumulating two generations of alerts under different ids.

        Args:
            match_id: The match the incidents belong to.
            incidents: What ``run_detectors`` produced.
        """
        rows = [
            {
                "match_id": match_id,
                "incident_id": item.incident_id,
                "kind": str(item.kind),
                "severity": item.severity,
                "tick": int(item.tick),
                "agent_ids": list(item.agent_ids),
                "market_ids": list(item.market_ids),
                "score_ppm": int(item.score_ppm),
                "detail": incident_detail_to_dict(item.detail),
                "detector_version": item.detector_version,
            }
            for item in incidents
        ]
        with self._engine.begin() as conn:
            conn.execute(sa.delete(incident).where(incident.c.match_id == match_id))
            _insert(conn, incident, rows)

    # ----------------------------------------------------------------------
    # Readers
    # ----------------------------------------------------------------------
    def has_match(self, match_id: str) -> bool:
        """Return whether one match has been saved.

        Args:
            match_id: The match.

        Returns:
            True when a ``match`` row exists. This is the predicate an idempotent
            resume tests: a task whose match is present is never replayed.
        """
        with self._engine.connect() as conn:
            found = conn.execute(sa.select(match.c.match_id).where(match.c.match_id == match_id)).first()
        return found is not None

    def load_journal(self, match_id: str) -> tuple[Event, ...]:
        """Read the journal of one match from the artefact directory.

        Args:
            match_id: The match.

        Returns:
            Every event, ascending by ``seq``.

        Raises:
            StoreError: If no journal can be found for that match.
        """
        return read_journal(self._journal_path(match_id))

    def load_metrics(self, match_id: str) -> MatchMetrics:
        """Read ``runs/<match_id>/metrics.json``.

        This is what ``GET /api/matches/{id}/metrics`` serves: one file read and
        no join, which is why the file and the ``metric_record`` table
        deliberately hold the same numbers.

        Args:
            match_id: The match.

        Returns:
            The metrics.

        Raises:
            StoreError: If the file is missing.
        """
        path = artefact_paths(self._runs_dir, match_id)["metrics"]
        if not path.exists():
            raise StoreError("missing metrics.json", match_id=match_id, path=str(path))
        return read_metrics(path)

    def load_projection(self, match_id: str) -> MatchProjection:
        """Project the journal of one match, incidents included.

        The API layer calls this and never :func:`pxe.metrics.projection.project`
        directly, so caching has one place to live and the ``integrity_alert``
        highlights of section 7.17 have exactly one supplier.

        Args:
            match_id: The match.

        Returns:
            The projection.
        """
        return project(self.load_journal(match_id), incidents=self.load_incidents(match_id=match_id))

    def list_matches(
        self, *, tournament_id: str | None = None, limit: int = 100, offset: int = 0
    ) -> tuple[Mapping[str, Any], ...]:
        """List saved matches, newest ids last (ordering is by ``match_id``).

        ``tournament_id`` and ``held_out`` are served from the ``match_task``
        row of the same match when there is one: the journal carries neither, so
        the ``match`` table deliberately does not either (see ``models.py``).

        Args:
            tournament_id: Restrict to the matches of one tournament. ``None``
                lists every match, standalone ones included.
            limit: Page size.
            offset: Page offset.

        Returns:
            One immutable mapping per match, holding every ``match`` column plus
            ``tournament_id``, ``held_out`` and ``task_status``.
        """
        joined = match.join(match_task, match_task.c.match_id == match.c.match_id, isouter=True)
        stmt = (
            sa.select(
                match,
                match_task.c.tournament_id,
                match_task.c.held_out,
                match_task.c.status.label("task_status"),
            )
            .select_from(joined)
            .order_by(match.c.match_id)
            .limit(limit)
            .offset(offset)
        )
        if tournament_id is not None:
            stmt = stmt.where(match_task.c.tournament_id == tournament_id)
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).mappings().all()
        return tuple(
            MappingProxyType({**dict(row), "held_out": bool(row["held_out"]) if row["held_out"] is not None else False})
            for row in rows
        )

    def list_tournaments(self, *, limit: int = 100, offset: int = 0) -> tuple[Mapping[str, Any], ...]:
        """List saved tournaments, ordered by id.

        Args:
            limit: Page size.
            offset: Page offset.

        Returns:
            One immutable mapping per tournament, holding every ``tournament``
            column plus ``n_tasks``, ``n_matches`` (how many of those tasks have
            a saved match), ``finished`` and ``total_cost_usd``.
        """
        with self._engine.connect() as conn:
            rows = (
                conn.execute(sa.select(tournament).order_by(tournament.c.tournament_id).limit(limit).offset(offset))
                .mappings()
                .all()
            )
            out: list[Mapping[str, Any]] = []
            for row in rows:
                tid = str(row["tournament_id"])
                n_tasks = conn.execute(
                    sa.select(sa.func.count()).select_from(match_task).where(match_task.c.tournament_id == tid)
                ).scalar_one()
                n_matches = conn.execute(
                    sa.select(sa.func.count())
                    .select_from(match_task.join(match, match.c.match_id == match_task.c.match_id))
                    .where(match_task.c.tournament_id == tid)
                ).scalar_one()
                out.append(
                    MappingProxyType(
                        {
                            **dict(row),
                            "n_tasks": int(n_tasks),
                            "n_matches": int(n_matches),
                            "finished": int(n_tasks) > 0 and int(n_tasks) == int(n_matches),
                            "total_cost_usd": sum(cost for _key, cost in self._costs_of(conn, tid)),
                        }
                    )
                )
        return tuple(out)

    def load_ratings(self, tournament_id: str) -> tuple[RatingRecord, ...]:
        """Return the leaderboard of one tournament, best ``mu`` first.

        Args:
            tournament_id: The tournament.

        Returns:
            The standings, sorted by descending ``mu`` then ascending
            ``harness_key`` so the order never depends on insertion order.
        """
        with self._engine.connect() as conn:
            rows = (
                conn.execute(
                    sa.select(rating_record)
                    .where(rating_record.c.tournament_id == tournament_id)
                    .order_by(sa.desc(rating_record.c.mu), rating_record.c.harness_key)
                )
                .mappings()
                .all()
            )
        return tuple(
            RatingRecord(
                harness_key=str(row["harness_key"]),
                mu=float(row["mu"]),
                sigma=float(row["sigma"]),
                matches=int(row["matches"]),
            )
            for row in rows
        )

    def load_rating_series(self, harness_id: str) -> tuple[tuple[str, float, float, int], ...]:
        """Return the per version progression of one harness id (PRD section 9).

        T4.3 draws the progression curve of a harness from this and has no other
        source. One point per **version**: when the same key was rated in several
        tournaments, the estimate backed by the most matches wins, because it is
        the one a reader would quote.

        Args:
            harness_id: The stable harness id, without the version or the hash.

        Returns:
            ``(harness_key, mu, sigma, matches)`` per version, ordered by the
            version string then by the key.
        """
        with self._engine.connect() as conn:
            rows = (
                conn.execute(
                    sa.select(rating_record)
                    .where(rating_record.c.harness_id == harness_id)
                    .order_by(rating_record.c.version, rating_record.c.harness_key, sa.desc(rating_record.c.matches))
                )
                .mappings()
                .all()
            )
        best: dict[str, tuple[str, str, float, float, int]] = {}
        for row in rows:
            key = str(row["harness_key"])
            point = (str(row["version"]), key, float(row["mu"]), float(row["sigma"]), int(row["matches"]))
            if key not in best or point[4] > best[key][4]:
                best[key] = point
        ordered = sorted(best.values(), key=lambda point: (point[0], point[1]))
        return tuple((key, mu, sigma, matches) for _version, key, mu, sigma, matches in ordered)

    def load_elites(self, tournament_id: str) -> tuple[EliteCell, ...]:
        """Return the MAP-Elites archive of one tournament.

        The :class:`~pxe.tournament.elites.EliteCell` import happens inside this
        method: it is the one ``pxe.tournament`` name the store is allowed to
        touch (section 7.20), and importing it lazily keeps ``pxe.store``'s
        module graph free of ``pxe.tournament`` entirely, so the dependency
        arrow cannot be broken by a later, less careful import.

        Args:
            tournament_id: The tournament.

        Returns:
            The cells, ordered by coordinate key.
        """
        from pxe.tournament.elites import EliteCell as Cell  # noqa: PLC0415

        with self._engine.connect() as conn:
            rows = (
                conn.execute(
                    sa.select(elite_cell)
                    .where(elite_cell.c.tournament_id == tournament_id)
                    .order_by(elite_cell.c.coords_key)
                )
                .mappings()
                .all()
            )
        return tuple(
            Cell(
                coords=tuple(int(value) for value in row["coords"]),
                harness_key=str(row["harness_key"]),
                mu=float(row["mu"]),
                descriptors=tuple(int(value) for value in row["descriptors"]),
            )
            for row in rows
        )

    def load_incidents(self, *, match_id: str | None = None, tournament_id: str | None = None) -> tuple[Incident, ...]:
        """Return integrity incidents, filtered by match or by tournament.

        Args:
            match_id: Restrict to one match.
            tournament_id: Restrict to the matches of one tournament, through the
                ``match_task`` rows of that tournament.

        Returns:
            The incidents, ordered by ``(match_id, incident_id)``.
        """
        stmt = sa.select(incident).order_by(incident.c.match_id, incident.c.incident_id)
        if match_id is not None:
            stmt = stmt.where(incident.c.match_id == match_id)
        if tournament_id is not None:
            stmt = stmt.where(
                incident.c.match_id.in_(
                    sa.select(match_task.c.match_id).where(match_task.c.tournament_id == tournament_id)
                )
            )
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).mappings().all()
        return tuple(
            Incident(
                incident_id=str(row["incident_id"]),
                kind=IncidentKind(str(row["kind"])),
                severity=str(row["severity"]),
                tick=int(row["tick"]),
                agent_ids=tuple(str(value) for value in row["agent_ids"]),
                market_ids=tuple(str(value) for value in row["market_ids"]),
                score_ppm=int(row["score_ppm"]),
                detail=incident_detail_from_dict(row["detail"]),
                detector_version=str(row["detector_version"]),
                match_id=str(row["match_id"]),
            )
            for row in rows
        )

    def load_costs_usd(self, tournament_id: str) -> tuple[tuple[str, float], ...]:
        """Return the provider cost of one tournament, per harness key.

        The numbers come from ``runs/<match_id>/llm_trace.jsonl``, summed into
        ``agent.cost_usd`` by :meth:`save_match`: cost is forbidden in a journal
        (section 3.5), so there is no other source, and a scripted harness
        legitimately reports ``0.0``.

        Args:
            tournament_id: The tournament.

        Returns:
            ``(harness_key, cost_usd)`` pairs, ordered by harness key.
        """
        with self._engine.connect() as conn:
            return self._costs_of(conn, tournament_id)

    def load_heldout_access(self, *, limit: int = 1000) -> tuple[Mapping[str, Any], ...]:
        """Return the held-out bank access log (AC-P5).

        Args:
            limit: Page size.

        Returns:
            One immutable mapping per access, ordered by ``access_id``, holding
            the whole entry as it was logged.
        """
        with self._engine.connect() as conn:
            rows = (
                conn.execute(sa.select(heldout_registry).order_by(heldout_registry.c.access_id).limit(limit))
                .mappings()
                .all()
            )
        return tuple(MappingProxyType(dict(row["payload"])) for row in rows)

    def pending_tasks(self, tournament_id: str) -> tuple[MatchTask, ...]:
        """Return the tasks of one tournament that still have to be played.

        A task is pending when its status is not ``"done"`` **and** no match with
        its ``match_id`` has been saved. The second condition is what makes
        ``resume()`` idempotent even after a crash between ``save_match`` and the
        status update.

        Args:
            tournament_id: The tournament.

        Returns:
            The pending tasks, ordered by ``task_id``.
        """
        with self._engine.connect() as conn:
            rows = (
                conn.execute(
                    sa.select(match_task)
                    .where(match_task.c.tournament_id == tournament_id)
                    .where(match_task.c.status != "done")
                    .where(match_task.c.match_id.not_in(sa.select(match.c.match_id)))
                    .order_by(match_task.c.task_id)
                )
                .mappings()
                .all()
            )
        return tuple(
            MatchTask(
                task_id=str(row["task_id"]),
                match_id=str(row["match_id"]),
                template_id=str(row["template_id"]),
                seed=int(row["seed"]),
                agent_ids=tuple(str(value) for value in row["agent_ids"]),
                harness_keys=tuple(str(value) for value in row["harness_keys"]),
                profile_assignment=tuple(
                    (str(pair[0]), InfoProfileKind(str(pair[1]))) for pair in row["profile_assignment"]
                ),
                held_out=bool(row["held_out"]),
            )
            for row in rows
        )

    # ----------------------------------------------------------------------
    # Maintenance
    # ----------------------------------------------------------------------
    def rebuild(self, *, runs_dir: Path | None = None) -> int:
        """Drop the match scoped tables and re import them from the journals.

        The database is a projection (section 4.1), so this must always be
        possible: it is the operation that makes "the journal is the source of
        truth" an executable statement rather than a claim. The thirteen tables
        of ``save_match`` are dropped and recreated; the tournament level tables
        (ratings, elites, incidents, the held-out log, the harness registry, the
        scenario registry and the task list) are left untouched, because no
        journal carries them and dropping them would destroy data that cannot be
        regenerated.

        A directory whose journal holds no ``MatchEnded`` is imported all the
        same, with ``finished = False``: a match interrupted mid flight is a
        legitimate artefact and hiding it would make it unfindable.

        Args:
            runs_dir: The runs root to scan. ``None`` means the one this store
                was built with.

        Returns:
            The number of matches imported.
        """
        root = self._runs_dir if runs_dir is None else Path(runs_dir)
        tables = [METADATA.tables[name] for name in _MATCH_SCOPED_TABLES]
        with self._engine.begin() as conn:
            for table in reversed(tables):
                table.drop(conn, checkfirst=True)
            for table in tables:
                table.create(conn, checkfirst=True)
        imported = 0
        for directory in sorted(path for path in root.iterdir() if path.is_dir()):
            journal_path = directory / "journal.jsonl"
            if not journal_path.exists():
                continue
            match_id = directory.name
            events = read_journal(journal_path)
            projection = project(events, incidents=self.load_incidents(match_id=match_id))
            metrics_path = directory / "metrics.json"
            metrics = read_metrics(metrics_path) if metrics_path.exists() else compute_all(projection)
            self.save_match(_result_of(events, projection, journal_path), projection, metrics)
            imported += 1
        return imported

    # ----------------------------------------------------------------------
    # Row builders. Private.
    # ----------------------------------------------------------------------
    def _journal_path(self, match_id: str, *, hint: str | None = None) -> Path:
        """Return the journal path of one match.

        Args:
            match_id: The match.
            hint: ``MatchResult.journal_path``, when the caller has one. It wins
                over the canonical layout, because a standalone ``pxe match run``
                may have been given an arbitrary output directory.

        Returns:
            An existing path.

        Raises:
            StoreError: If neither the hint nor the canonical path exists, and
                the database holds no recorded path either.
        """
        if hint:
            candidate = Path(hint)
            if candidate.exists():
                return candidate
        canonical = artefact_paths(self._runs_dir, match_id)["journal"]
        if canonical.exists():
            return canonical
        with self._engine.connect() as conn:
            stored = conn.execute(sa.select(match.c.journal_path).where(match.c.match_id == match_id)).scalars().first()
        if stored:
            recorded = Path(str(stored))
            if recorded.exists():
                return recorded
        raise StoreError("no journal on disk for this match", match_id=match_id, expected=str(canonical))

    def _costs_of(self, conn: Connection, tournament_id: str) -> tuple[tuple[str, float], ...]:
        """Aggregate ``agent.cost_usd`` per harness key over one tournament.

        Args:
            conn: An open connection.
            tournament_id: The tournament.

        Returns:
            ``(harness_key, cost_usd)`` pairs, ordered by harness key.
        """
        rows = conn.execute(
            sa.select(agent.c.harness_key, sa.func.sum(agent.c.cost_usd))
            .where(
                agent.c.match_id.in_(
                    sa.select(match_task.c.match_id).where(match_task.c.tournament_id == tournament_id)
                )
            )
            .group_by(agent.c.harness_key)
            .order_by(agent.c.harness_key)
        ).all()
        return tuple((str(key), float(total or 0.0)) for key, total in rows)

    def _winner_of(
        self, ended: MatchEnded | None, agent_rows: Sequence[Mapping[str, Any]]
    ) -> tuple[str | None, str | None]:
        """Return the ``(agent_id, harness_key)`` of rank 1, or two ``None``.

        Args:
            ended: The ``MatchEnded`` of the match, or ``None`` when the journal
                stops before it.
            agent_rows: The ``agent`` rows of the match, used to map the winning
                seat to its harness key.

        Returns:
            The winning seat and its harness key. Ties share the lowest rank
            (finalisation step 18) and the first row of ``rankings`` is taken, so
            a tie reports the lowest ``agent_id``, exactly as the journal orders
            it.
        """
        if ended is None or not ended.rankings:
            return (None, None)
        winner_id = str(ended.rankings[0]["agent_id"])
        for row in agent_rows:
            if row["agent_id"] == winner_id:
                return (winner_id, str(row["harness_key"]))
        return (winner_id, None)

    def _tick_rows(self, match_id: str, projection: MatchProjection, events: Sequence[Event]) -> list[dict[str, Any]]:
        """Build the ``tick`` rows from the per tick series of the projection.

        Every series has length ``ticks_total`` (section 9), so there is exactly
        one row per played tick whatever resolved when.

        Args:
            match_id: The match.
            projection: The folded journal.
            events: The journal, for the news count (no projection row carries
                news).

        Returns:
            One row per tick, ascending.
        """
        news_per_tick: dict[int, int] = {}
        for event in _of_type(events, NewsPublished):
            news_per_tick[event.tick] = news_per_tick.get(event.tick, 0) + 1
        trades_per_tick: dict[int, tuple[int, int]] = {}
        for row in projection.trades:
            count, volume = trades_per_tick.get(row.tick, (0, 0))
            trades_per_tick[row.tick] = (count + 1, volume + row.qty)
        signals_per_tick: dict[int, int] = {}
        for signal_row in projection.signals:
            signals_per_tick[signal_row.tick] = signals_per_tick.get(signal_row.tick, 0) + 1
        predictions_per_tick: dict[int, int] = {}
        for prediction_row in projection.predictions:
            predictions_per_tick[prediction_row.tick] = predictions_per_tick.get(prediction_row.tick, 0) + 1
        messages_per_tick: dict[int, int] = {}
        for message_row in projection.messages:
            messages_per_tick[message_row.tick] = messages_per_tick.get(message_row.tick, 0) + 1

        rows: list[dict[str, Any]] = []
        for index in range(projection.ticks_total):
            current = index + 1
            equity = {agent_id: series[index] for agent_id, series in projection.equity_cents}
            trade_count, volume_qty = trades_per_tick.get(current, (0, 0))
            rows.append(
                {
                    "match_id": match_id,
                    "tick": current,
                    "ref_price": {market_id: series[index] for market_id, series in projection.ref_price},
                    "equity_cents": equity,
                    "total_equity_cents": sum(equity.values()),
                    "trade_count": trade_count,
                    "volume_qty": volume_qty,
                    "news_count": news_per_tick.get(current, 0),
                    "signal_count": signals_per_tick.get(current, 0),
                    "prediction_count": predictions_per_tick.get(current, 0),
                    "message_count": messages_per_tick.get(current, 0),
                }
            )
        return rows

    def _news_rows(self, match_id: str, events: Sequence[Event]) -> list[dict[str, Any]]:
        """Build the ``news_item`` rows from the journal.

        Args:
            match_id: The match.
            events: The journal.

        Returns:
            One row per ``NewsPublished``, in publication order.
        """
        rows: list[dict[str, Any]] = []
        for event in _of_type(events, NewsPublished):
            rows.append(
                {
                    "match_id": match_id,
                    "news_id": event.news_id,
                    "tick": event.tick,
                    "market_ids": list(event.market_ids),
                    "headline": event.headline,
                    "body": event.body,
                    "impact": event.impact,
                    "is_noise": event.is_noise,
                    "origin": event.origin,
                }
            )
        return rows

    def _signal_rows(self, match_id: str, projection: MatchProjection) -> list[dict[str, Any]]:
        """Build the ``signal`` rows from ``MatchProjection.signals``.

        Args:
            match_id: The match.
            projection: The folded journal.

        Returns:
            One row per delivered signal.
        """
        return [
            {
                "match_id": match_id,
                "signal_id": row.signal_id,
                "tick": row.tick,
                "agent_id": row.agent_id,
                "market_id": row.market_id,
                "kind": row.kind,
                "value_milli": row.value_milli,
                "precision_ppm": row.precision_ppm,
            }
            for row in projection.signals
        ]

    def _order_rows(self, match_id: str, projection: MatchProjection) -> list[dict[str, Any]]:
        """Build the ``order`` rows from ``MatchProjection.orders``.

        Args:
            match_id: The match.
            projection: The folded journal.

        Returns:
            One row per order, its whole life folded.
        """
        return [
            {
                "match_id": match_id,
                "order_id": row.order_id,
                "agent_id": row.agent_id,
                "market_id": row.market_id,
                "side": row.side,
                "requested_type": row.requested_type,
                "price": row.price,
                "qty": row.qty,
                "placed_tick": row.placed_tick,
                "filled_qty": row.filled_qty,
                "cancelled_tick": row.cancelled_tick,
                "cancel_reason": row.cancel_reason,
                "reserved_cents": row.reserved_cents,
                "released_cents": row.released_cents,
            }
            for row in projection.orders
        ]

    def _trade_rows(self, match_id: str, projection: MatchProjection) -> list[dict[str, Any]]:
        """Build the ``trade`` rows from ``MatchProjection.trades``.

        Args:
            match_id: The match.
            projection: The folded journal.

        Returns:
            One row per execution.
        """
        return [
            {
                "match_id": match_id,
                "trade_id": row.trade_id,
                "tick": row.tick,
                "market_id": row.market_id,
                "price": row.price,
                "qty": row.qty,
                "maker_order_id": row.maker_order_id,
                "maker_agent_id": row.maker_agent_id,
                "maker_side": row.maker_side,
                "taker_order_id": row.taker_order_id,
                "taker_agent_id": row.taker_agent_id,
                "taker_side": row.taker_side,
                "taker_fee_cents": row.taker_fee_cents,
                "maker_cash_delta_cents": row.maker_cash_delta_cents,
                "taker_cash_delta_cents": row.taker_cash_delta_cents,
            }
            for row in projection.trades
        ]

    def _snapshot_rows(self, match_id: str, events: Sequence[Event]) -> list[dict[str, Any]]:
        """Build the ``position_snapshot`` rows from the journal.

        Args:
            match_id: The match.
            events: The journal.

        Returns:
            One row per ``(tick, account)``, in journal order, which is the
            canonical account order of section 2.3 inside each tick.
        """
        rows: list[dict[str, Any]] = []
        for event in _of_type(events, PositionSnapshot):
            rows.append(
                {
                    "match_id": match_id,
                    "tick": event.tick,
                    "account_id": event.account_id,
                    "cash_cents": event.cash_cents,
                    "reserved_cents": event.reserved_cents,
                    "free_cash_cents": event.free_cash_cents,
                    "equity_cents": event.equity_cents,
                    "frozen": event.frozen,
                    "positions": [dict(position) for position in event.positions],
                    "resting_order_count": event.resting_order_count,
                }
            )
        return rows

    def _prediction_rows(self, match_id: str, projection: MatchProjection) -> list[dict[str, Any]]:
        """Build the ``prediction`` rows from ``MatchProjection.predictions``.

        Args:
            match_id: The match.
            projection: The folded journal.

        Returns:
            One row per ``PredictionRecorded``, carried terms included: one
            event, one row, one Brier term (section 9).
        """
        return [
            {
                "match_id": match_id,
                "tick": row.tick,
                "agent_id": row.agent_id,
                "market_id": row.market_id,
                "p_yes_ppm": row.p_yes_ppm,
                "carried": row.carried,
            }
            for row in projection.predictions
        ]

    def _resolution_rows(self, match_id: str, events: Sequence[Event]) -> list[dict[str, Any]]:
        """Build the ``resolution`` rows from the journal.

        Args:
            match_id: The match.
            events: The journal.

        Returns:
            One row per market that left the board, resolutions and
            cancellations together, ordered as the journal emitted them.
        """
        rows: list[dict[str, Any]] = []
        for event in events:
            if isinstance(event, MarketResolved):
                rows.append(
                    {
                        "match_id": match_id,
                        "market_id": event.market_id,
                        "mode": _MODE_RESOLUTION,
                        "tick": event.tick,
                        "resolution_tick": event.resolution_tick,
                        "outcome": event.outcome,
                        "payout_cents": event.payout_cents,
                        "latent_value_milli": event.latent_value_milli,
                        "reason": None,
                    }
                )
            elif isinstance(event, MarketCancelled):
                rows.append(
                    {
                        "match_id": match_id,
                        "market_id": event.market_id,
                        "mode": _MODE_CANCELLATION,
                        "tick": event.tick,
                        "resolution_tick": None,
                        "outcome": None,
                        "payout_cents": None,
                        "latent_value_milli": None,
                        "reason": event.reason,
                    }
                )
        return rows

    def _settlement_rows(self, match_id: str, events: Sequence[Event]) -> list[dict[str, Any]]:
        """Build the ``settlement`` rows from the journal.

        Args:
            match_id: The match.
            events: The journal.

        Returns:
            One row per ``SettlementApplied``, keyed by its journal ``seq``.
        """
        rows: list[dict[str, Any]] = []
        for event in _of_type(events, SettlementApplied):
            rows.append(
                {
                    "match_id": match_id,
                    "seq": event.seq,
                    "tick": event.tick,
                    "market_id": event.market_id,
                    "account_id": event.account_id,
                    "mode": event.mode,
                    "position_qty": event.position_qty,
                    "cash_delta_cents": event.cash_delta_cents,
                    "cash_before_cents": event.cash_before_cents,
                    "cash_after_cents": event.cash_after_cents,
                    "released_collateral_cents": event.released_collateral_cents,
                }
            )
        return rows

    def _metric_rows(self, match_id: str, metrics: MatchMetrics) -> list[dict[str, Any]]:
        """Build the ``metric_record`` rows from the three metric families.

        The three blocks of ``MatchMetrics`` are sorted by ``agent_id`` and cover
        the same seats, so they are joined by id rather than by position: a
        family that is empty (a match where nobody predicted anything cannot
        happen, but a hand built ``MatchMetrics`` in a test can) leaves its
        columns at zero instead of shifting another family's numbers onto the
        wrong seat.

        Args:
            match_id: The match.
            metrics: The joined metrics.

        Returns:
            One row per ranked seat.
        """
        calibration = {row.agent_id: row for row in metrics.calibration}
        descriptors = {row.agent_id: row for row in metrics.descriptors}
        rows: list[dict[str, Any]] = []
        for row in metrics.performance:
            cal = calibration.get(row.agent_id)
            desc = descriptors.get(row.agent_id)
            rows.append(
                {
                    "match_id": match_id,
                    "agent_id": row.agent_id,
                    "pnl_cents": row.pnl_cents,
                    "pnl_bps": row.pnl_bps,
                    "sharpe_milli": row.sharpe_milli,
                    "max_drawdown_cents": row.max_drawdown_cents,
                    "max_drawdown_bps": row.max_drawdown_bps,
                    "volume_qty": row.volume_qty,
                    "trade_count": row.trade_count,
                    "maker_trade_count": row.maker_trade_count,
                    "fees_paid_cents": row.fees_paid_cents,
                    "brier_ppm": 0 if cal is None else cal.brier_ppm,
                    "n_terms": 0 if cal is None else cal.n_terms,
                    "n_carried": 0 if cal is None else cal.n_carried,
                    "maker_ratio_ppm": 0 if desc is None else desc.maker_ratio_ppm,
                    "reaction_latency_milli": 0 if desc is None else desc.reaction_latency_milli,
                    "holding_horizon_milli": 0 if desc is None else desc.holding_horizon_milli,
                    "herfindahl_ppm": 0 if desc is None else desc.herfindahl_ppm,
                    "leverage_ppm": 0 if desc is None else desc.leverage_ppm,
                    "message_intensity_ppm": 0 if desc is None else desc.message_intensity_ppm,
                }
            )
        return rows


def _tournament_id_of(task: MatchTask) -> str:
    """Return the tournament id a task belongs to.

    ``MatchTask`` (section 7.1) carries no ``tournament_id``, and
    ``Store.pending_tasks`` is scoped by tournament, so the id has to be read off
    the ``task_id``. The convention this reads is
    ``<tournament_id>#<anything>``, and a task id without a ``#`` belongs to the
    empty tournament, which is where a standalone task lands. See CONTRACT
    ISSUES.

    Args:
        task: The task.

    Returns:
        The tournament id, or ``""``.
    """
    return task.task_id.split("#", 1)[0] if "#" in task.task_id else ""


def _result_of(events: Sequence[Event], projection: MatchProjection, journal_path: Path) -> MatchResult:
    """Rebuild the ``MatchResult`` of a journal, for :meth:`Store.rebuild`.

    Only the fields ``save_match`` reads are meaningful here, and they all come
    from the journal: the match id, the seed, the two closing totals, the event
    count and the hash of the file on disk. ``rankings`` is taken verbatim from
    ``MatchEnded`` and ``scenario`` is the subset ``MatchStarted`` carries
    (correlations and scripted cancellations are recorded by
    ``save_scenario_instance``, which no journal can regenerate).

    Args:
        events: The journal.
        projection: Its projection, for the two closing totals.
        journal_path: Path of the file, so the rebuilt row points at it.

    Returns:
        The reconstructed result.

    Raises:
        StoreError: If the journal holds no ``MatchStarted``.
    """
    started = _match_started_of(events)
    config = config_from_journal_dict(started.config)
    ended = _of_type(events, MatchEnded)
    rankings = tuple(
        MatchRanking(
            rank=int(row["rank"]),
            agent_id=str(row["agent_id"]),
            pnl_cents=int(row["pnl_cents"]),
            final_cash_cents=int(row["final_cash_cents"]),
            pnl_pct_bps=int(row["pnl_pct_bps"]),
        )
        for row in (ended[-1].rankings if ended else ())
    )
    scenario = ScenarioSpec(
        template_id=started.scenario_template_id,
        template_version=started.scenario_template_version,
        seed=started.seed,
        ticks_total=started.ticks_total,
        markets=tuple(market_spec_from_dict(entry) for entry in started.markets),
        talking_mode=config.talking_mode,
        liquidity_profile_name=config.liquidity_profile_name,
    )
    return MatchResult(
        match_id=started.match_id,
        seed=started.seed,
        scenario=scenario,
        rankings=rankings,
        journal_path=str(journal_path),
        journal_hash=journal_hash(events),
        event_count=len(events),
        mm_pnl_cents=projection.mm_pnl_cents,
        fees_collected_cents=projection.fees_collected_cents,
    )
