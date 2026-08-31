"""The projection schema: twenty-one PRD entities plus two infrastructure tables.

CONTRACTS section 7.20 decides the shape of this file and every rule below is
quoted from it rather than invented here:

* **SQLAlchemy 2.x Core, not the ORM.** Every table is a
  :class:`sqlalchemy.Table` on the single :data:`METADATA`. There is no
  declarative base, no relationship and no identity map: every read in this
  project is an explicit ``select()``, and an ORM identity map shared across a
  multiprocess tournament is a source of surprises the store does not need.
* **Portable between SQLite and Postgres.** Identifiers are lower snake case and
  never quoted by us (SQLAlchemy quotes ``match`` and ``order`` on its own,
  because both are SQL reserved words and the PRD names the entities that way).
  Every primary key is a natural id, never an autoincrement integer. A payload
  column is :class:`sqlalchemy.JSON` and is never queried by JSON path. Money is
  ``BigInteger`` cents, a probability or a ratio is ``Integer`` ppm, a duration
  is ``Integer`` ticks. There is no ``ARRAY``, no ``ENUM``, no partial index and
  no foreign key.
* **No timestamp column anywhere.** Section 7.20 allows one, written by the
  caller and never by a database default, but a wall clock in a projection makes
  ``Store.rebuild`` unverifiable: ``test_store.py::test_rebuild_from_journals_reproduces_every_table``
  compares the tables before and after a rebuild row by row, and a ``created_at``
  would differ on every one of them. Nothing in the PRD data model needs one:
  ordering is by natural id and by ``tick``, both of which are reproducible.
* **Floats appear in exactly four places** and none of them is money:
  ``rating_record.mu`` / ``.sigma`` (TrueSkill), ``elite_cell.mu``,
  ``agent.cost_usd`` and ``tournament.max_cost_usd``. They are statistics and
  provider bills, they are documented as floats in sections 7.19 and 7.21, and
  they never cross into a cents field.

Two tables are **not** PRD 10.4 entities and are listed separately in
:data:`INFRASTRUCTURE_TABLES` so the "twenty-one for twenty-one" test still
fails on a stray table:

* ``match_task`` carries ``Store.save_task`` / ``Store.pending_tasks``
  (section 7.20). The PRD has no ``match_task`` entity and the writer table of
  section 7.20 maps no table to ``save_task``, yet a resumable tournament (T3.1)
  cannot recover a planned but unplayed task from anywhere else. Folding it into
  ``match`` was the alternative and it is worse: ``GET /api/matches`` would then
  list phantom matches that never ran, and ``match`` would have two writers.
* ``store_schema`` carries the one row that makes
  ``STORE_SCHEMA_VERSION ... checked by init_schema`` (section 7.20) implementable
  at all: without a marker in the database, ``init_schema`` cannot tell a fresh
  file from one created by an older schema.

Both are reported under CONTRACT ISSUES rather than assumed to be agreed.
"""

from __future__ import annotations

import sqlalchemy as sa

__all__ = [
    "STORE_SCHEMA_VERSION",
    "METADATA",
    "PRD_TABLES",
    "INFRASTRUCTURE_TABLES",
    "MATCH_SCOPED_TABLES",
    "store_schema",
    "scenario_template",
    "scenario_instance",
    "match",
    "agent",
    "harness_version",
    "tick",
    "news_item",
    "signal",
    "order",
    "trade",
    "position_snapshot",
    "prediction",
    "resolution",
    "settlement",
    "metric_record",
    "rating_record",
    "elite_cell",
    "incident",
    "tournament",
    "heldout_registry",
    "mm_config",
    "match_task",
]

#: Bumped on any table change. There is no Alembic in v1: a schema change
#: requires a fresh database, which is acceptable because every table here is a
#: projection that ``pxe store rebuild <runs_dir>`` regenerates from the
#: journals (section 4.1). ``Store.init_schema`` refuses a database stamped with
#: a different value.
STORE_SCHEMA_VERSION = "1"

#: The one :class:`sqlalchemy.MetaData` of the project.
METADATA = sa.MetaData()

# Column shorthands. They exist so a money column cannot accidentally be
# declared as an Integer on one table and a BigInteger on another.
_ID = sa.String(64)
_SHORT = sa.String(128)
_TEXT = sa.Text()
_CENTS = sa.BigInteger()

# --------------------------------------------------------------------------
# Infrastructure
# --------------------------------------------------------------------------
#: One row, ``marker = "pxe"``, holding the schema version the database was
#: created with. Written only by ``Store.init_schema``.
store_schema = sa.Table(
    "store_schema",
    METADATA,
    sa.Column("marker", _ID, primary_key=True),
    sa.Column("version", _SHORT, nullable=False),
)

# --------------------------------------------------------------------------
# Scenarios and harnesses
# --------------------------------------------------------------------------
#: One row per world template. Written only by ``Store.save_scenario_template``.
scenario_template = sa.Table(
    "scenario_template",
    METADATA,
    sa.Column("template_id", _ID, primary_key=True),
    sa.Column("template_version", _SHORT, nullable=False),
    sa.Column("default_ticks", sa.Integer(), nullable=False),
    sa.Column("default_markets", sa.Integer(), nullable=False),
)

#: One row per generated world, that is per ``(template_id, seed)`` pair, keyed
#: by the natural composition of the two. Written only by
#: ``Store.save_scenario_instance``.
scenario_instance = sa.Table(
    "scenario_instance",
    METADATA,
    sa.Column("scenario_id", _ID, primary_key=True),
    sa.Column("template_id", _ID, nullable=False),
    sa.Column("template_version", _SHORT, nullable=False),
    sa.Column("seed", sa.BigInteger(), nullable=False),
    sa.Column("ticks_total", sa.Integer(), nullable=False),
    sa.Column("n_markets", sa.Integer(), nullable=False),
    sa.Column("world_hash", _SHORT, nullable=False),
    sa.Column("held_out", sa.Boolean(), nullable=False),
    sa.Column("talking_mode", sa.Boolean(), nullable=False),
    sa.Column("liquidity_profile_name", _SHORT, nullable=False),
    sa.Column("notes", _TEXT, nullable=False),
    sa.Column("payload", sa.JSON(), nullable=False),
)

#: One row per harness version. Keyed by the harness key of section 2.2, so two
#: prompts shipped under the same version tag are two rows. Written only by
#: ``Store.save_harness_version``.
harness_version = sa.Table(
    "harness_version",
    METADATA,
    sa.Column("harness_key", _SHORT, primary_key=True),
    sa.Column("harness_id", _ID, nullable=False),
    sa.Column("version", _SHORT, nullable=False),
    sa.Column("kind", _SHORT, nullable=False),
    sa.Column("model", _SHORT, nullable=False),
    sa.Column("config_hash", _SHORT, nullable=False),
    sa.Column("system_prompt", _TEXT, nullable=False),
    sa.Column("params", sa.JSON(), nullable=False),
)

# --------------------------------------------------------------------------
# Matches. Every column below is derived from the journal of the match, which
# is what makes Store.rebuild possible.
# --------------------------------------------------------------------------
#: One row per match. ``tournament_id`` is deliberately **absent**: the journal
#: does not carry it, ``MatchResult`` does not either, and inventing it here
#: would make the row unreproducible by ``rebuild``. ``Store.list_matches``
#: serves it (and ``held_out``) by joining ``match_task``.
match = sa.Table(
    "match",
    METADATA,
    sa.Column("match_id", _ID, primary_key=True),
    sa.Column("template_id", _ID, nullable=False),
    sa.Column("template_version", _SHORT, nullable=False),
    sa.Column("seed", sa.BigInteger(), nullable=False),
    sa.Column("ticks_total", sa.Integer(), nullable=False),
    sa.Column("n_markets", sa.Integer(), nullable=False),
    sa.Column("n_agents", sa.Integer(), nullable=False),
    sa.Column("initial_cash_cents", _CENTS, nullable=False),
    sa.Column("journal_path", _TEXT, nullable=False),
    sa.Column("journal_hash", _SHORT, nullable=False),
    sa.Column("event_count", sa.Integer(), nullable=False),
    sa.Column("finished", sa.Boolean(), nullable=False),
    sa.Column("final_tick", sa.Integer(), nullable=False),
    sa.Column("end_reason", _SHORT, nullable=False),
    sa.Column("winner_agent_id", _ID, nullable=True),
    sa.Column("winner_harness_key", _SHORT, nullable=True),
    sa.Column("mm_pnl_cents", _CENTS, nullable=False),
    sa.Column("fees_collected_cents", _CENTS, nullable=False),
    sa.Column("talking_mode", sa.Boolean(), nullable=False),
    sa.Column("liquidity_profile_name", _SHORT, nullable=False),
    sa.Column("config", sa.JSON(), nullable=False),
    sa.Column("rankings", sa.JSON(), nullable=False),
)

#: One row per seat of one match, including ``MM`` (``ranked`` is False there).
#: ``cost_usd`` is the provider bill of that seat in that match, summed from
#: ``runs/<match_id>/llm_trace.jsonl``; it is ``0.0`` for a scripted seat and it
#: is what ``Store.load_costs_usd`` aggregates per harness key.
agent = sa.Table(
    "agent",
    METADATA,
    sa.Column("match_id", _ID, primary_key=True),
    sa.Column("agent_id", _ID, primary_key=True),
    sa.Column("harness_key", _SHORT, nullable=False),
    sa.Column("harness_id", _ID, nullable=False),
    sa.Column("harness_version", _SHORT, nullable=False),
    sa.Column("config_hash", _SHORT, nullable=False),
    sa.Column("info_profile_kind", _SHORT, nullable=False),
    sa.Column("ranked", sa.Boolean(), nullable=False),
    sa.Column("cost_usd", sa.Float(), nullable=False, default=0.0),
)

#: One row per match, the FR-5.8.6 preset the market maker actually played with.
mm_config = sa.Table(
    "mm_config",
    METADATA,
    sa.Column("match_id", _ID, primary_key=True),
    sa.Column("profile_name", _SHORT, nullable=False),
    sa.Column("base_spread_cents", sa.Integer(), nullable=False),
    sa.Column("quote_qty", sa.Integer(), nullable=False),
    sa.Column("inventory_max", sa.Integer(), nullable=False),
    sa.Column("skew_cents", sa.Integer(), nullable=False),
    sa.Column("post_news_widen_ticks", sa.Integer(), nullable=False),
    sa.Column("widen_multiplier", sa.Integer(), nullable=False),
    sa.Column("enabled", sa.Boolean(), nullable=False),
)

#: One row per played tick, from the per tick series of ``MatchProjection``.
#: ``ref_price`` and ``equity_cents`` are the two series a leaderboard over time
#: needs, kept here so a chart does not have to read every
#: ``position_snapshot`` row of the match.
tick = sa.Table(
    "tick",
    METADATA,
    sa.Column("match_id", _ID, primary_key=True),
    sa.Column("tick", sa.Integer(), primary_key=True),
    sa.Column("ref_price", sa.JSON(), nullable=False),
    sa.Column("equity_cents", sa.JSON(), nullable=False),
    sa.Column("total_equity_cents", _CENTS, nullable=False),
    sa.Column("trade_count", sa.Integer(), nullable=False),
    sa.Column("volume_qty", sa.Integer(), nullable=False),
    sa.Column("news_count", sa.Integer(), nullable=False),
    sa.Column("signal_count", sa.Integer(), nullable=False),
    sa.Column("prediction_count", sa.Integer(), nullable=False),
    sa.Column("message_count", sa.Integer(), nullable=False),
)

#: One row per ``NewsPublished``. ``origin`` is one of ``info_engine``,
#: ``resolution`` or ``cancellation`` (section 5 P1).
news_item = sa.Table(
    "news_item",
    METADATA,
    sa.Column("match_id", _ID, primary_key=True),
    sa.Column("news_id", _ID, primary_key=True),
    sa.Column("tick", sa.Integer(), nullable=False),
    sa.Column("market_ids", sa.JSON(), nullable=False),
    sa.Column("headline", _TEXT, nullable=False),
    sa.Column("body", _TEXT, nullable=False),
    sa.Column("impact", _SHORT, nullable=False),
    sa.Column("is_noise", sa.Boolean(), nullable=False),
    sa.Column("origin", _SHORT, nullable=False),
)

#: One row per ``SignalDelivered``, that is per private signal that survived the
#: P1 step 3 filter.
signal = sa.Table(
    "signal",
    METADATA,
    sa.Column("match_id", _ID, primary_key=True),
    sa.Column("signal_id", _ID, primary_key=True),
    sa.Column("tick", sa.Integer(), nullable=False),
    sa.Column("agent_id", _ID, nullable=False),
    sa.Column("market_id", _ID, nullable=False),
    sa.Column("kind", _SHORT, nullable=False),
    sa.Column("value_milli", sa.BigInteger(), nullable=False),
    sa.Column("precision_ppm", sa.Integer(), nullable=False),
)

#: One row per order, its whole life folded (``OrderRecord``): what was placed,
#: how much filled, when and why it left the book.
order = sa.Table(
    "order",
    METADATA,
    sa.Column("match_id", _ID, primary_key=True),
    sa.Column("order_id", _ID, primary_key=True),
    sa.Column("agent_id", _ID, nullable=False),
    sa.Column("market_id", _ID, nullable=False),
    sa.Column("side", _SHORT, nullable=False),
    sa.Column("requested_type", _SHORT, nullable=False),
    sa.Column("price", sa.Integer(), nullable=False),
    sa.Column("qty", sa.Integer(), nullable=False),
    sa.Column("placed_tick", sa.Integer(), nullable=False),
    sa.Column("filled_qty", sa.Integer(), nullable=False),
    sa.Column("cancelled_tick", sa.Integer(), nullable=True),
    sa.Column("cancel_reason", _SHORT, nullable=True),
    sa.Column("reserved_cents", _CENTS, nullable=False),
    sa.Column("released_cents", _CENTS, nullable=False),
)

#: One row per execution (``TradeExecuted``). The two cash deltas and the taker
#: fee sum to zero (invariant I5), so a projection over this table is closed.
trade = sa.Table(
    "trade",
    METADATA,
    sa.Column("match_id", _ID, primary_key=True),
    sa.Column("trade_id", _ID, primary_key=True),
    sa.Column("tick", sa.Integer(), nullable=False),
    sa.Column("market_id", _ID, nullable=False),
    sa.Column("price", sa.Integer(), nullable=False),
    sa.Column("qty", sa.Integer(), nullable=False),
    sa.Column("maker_order_id", _ID, nullable=False),
    sa.Column("maker_agent_id", _ID, nullable=False),
    sa.Column("maker_side", _SHORT, nullable=False),
    sa.Column("taker_order_id", _ID, nullable=False),
    sa.Column("taker_agent_id", _ID, nullable=False),
    sa.Column("taker_side", _SHORT, nullable=False),
    sa.Column("taker_fee_cents", _CENTS, nullable=False),
    sa.Column("maker_cash_delta_cents", _CENTS, nullable=False),
    sa.Column("taker_cash_delta_cents", _CENTS, nullable=False),
)

#: One row per ``(tick, account)`` (``PositionSnapshot``), ``MM`` and ``FEES``
#: included: P4 emits it for every account on every tick, whatever happens.
position_snapshot = sa.Table(
    "position_snapshot",
    METADATA,
    sa.Column("match_id", _ID, primary_key=True),
    sa.Column("tick", sa.Integer(), primary_key=True),
    sa.Column("account_id", _ID, primary_key=True),
    sa.Column("cash_cents", _CENTS, nullable=False),
    sa.Column("reserved_cents", _CENTS, nullable=False),
    sa.Column("free_cash_cents", _CENTS, nullable=False),
    sa.Column("equity_cents", _CENTS, nullable=False),
    sa.Column("frozen", sa.Boolean(), nullable=False),
    sa.Column("positions", sa.JSON(), nullable=False),
    sa.Column("resting_order_count", sa.Integer(), nullable=False),
)

#: One row per ``PredictionRecorded``, carried terms included: one event, one
#: row, one Brier term (section 9).
prediction = sa.Table(
    "prediction",
    METADATA,
    sa.Column("match_id", _ID, primary_key=True),
    sa.Column("tick", sa.Integer(), primary_key=True),
    sa.Column("agent_id", _ID, primary_key=True),
    sa.Column("market_id", _ID, primary_key=True),
    sa.Column("p_yes_ppm", sa.Integer(), nullable=False),
    sa.Column("carried", sa.Boolean(), nullable=False),
)

#: One row per market that left the board: ``mode`` is ``"resolution"`` for a
#: ``MarketResolved`` and ``"cancellation"`` for a ``MarketCancelled``. A
#: cancelled market has no outcome, which is what tells a consumer to treat its
#: trades as unwound (FR-5.4.5).
resolution = sa.Table(
    "resolution",
    METADATA,
    sa.Column("match_id", _ID, primary_key=True),
    sa.Column("market_id", _ID, primary_key=True),
    sa.Column("mode", _SHORT, nullable=False),
    sa.Column("tick", sa.Integer(), nullable=False),
    sa.Column("resolution_tick", sa.Integer(), nullable=True),
    sa.Column("outcome", _SHORT, nullable=True),
    sa.Column("payout_cents", _CENTS, nullable=True),
    sa.Column("latent_value_milli", sa.BigInteger(), nullable=True),
    sa.Column("reason", _SHORT, nullable=True),
)

#: One row per ``SettlementApplied``. Keyed by the journal ``seq``, which is the
#: only natural id here: an account can be settled twice on one market (a
#: resolution and, in another match, an unwind), and ``seq`` is unique inside a
#: match by construction (section 4.4).
settlement = sa.Table(
    "settlement",
    METADATA,
    sa.Column("match_id", _ID, primary_key=True),
    sa.Column("seq", sa.Integer(), primary_key=True),
    sa.Column("tick", sa.Integer(), nullable=False),
    sa.Column("market_id", _ID, nullable=False),
    sa.Column("account_id", _ID, nullable=False),
    sa.Column("mode", _SHORT, nullable=False),
    sa.Column("position_qty", sa.Integer(), nullable=False),
    sa.Column("cash_delta_cents", _CENTS, nullable=False),
    sa.Column("cash_before_cents", _CENTS, nullable=False),
    sa.Column("cash_after_cents", _CENTS, nullable=False),
    sa.Column("released_collateral_cents", _CENTS, nullable=False),
)

#: One row per ranked seat, holding the three metric families of
#: ``MatchMetrics`` side by side. It holds the same numbers as
#: ``runs/<match_id>/metrics.json`` on purpose: the file is what
#: ``GET /api/matches/{id}/metrics`` serves (one file read, no join) and this
#: table is what a tournament report aggregates over a hundred matches (one
#: query, no hundred file reads).
metric_record = sa.Table(
    "metric_record",
    METADATA,
    sa.Column("match_id", _ID, primary_key=True),
    sa.Column("agent_id", _ID, primary_key=True),
    sa.Column("pnl_cents", _CENTS, nullable=False),
    sa.Column("pnl_bps", sa.Integer(), nullable=False),
    sa.Column("sharpe_milli", sa.Integer(), nullable=False),
    sa.Column("max_drawdown_cents", _CENTS, nullable=False),
    sa.Column("max_drawdown_bps", sa.Integer(), nullable=False),
    sa.Column("volume_qty", sa.Integer(), nullable=False),
    sa.Column("trade_count", sa.Integer(), nullable=False),
    sa.Column("maker_trade_count", sa.Integer(), nullable=False),
    sa.Column("fees_paid_cents", _CENTS, nullable=False),
    sa.Column("brier_ppm", sa.Integer(), nullable=False),
    sa.Column("n_terms", sa.Integer(), nullable=False),
    sa.Column("n_carried", sa.Integer(), nullable=False),
    sa.Column("maker_ratio_ppm", sa.Integer(), nullable=False),
    sa.Column("reaction_latency_milli", sa.Integer(), nullable=False),
    sa.Column("holding_horizon_milli", sa.Integer(), nullable=False),
    sa.Column("herfindahl_ppm", sa.Integer(), nullable=False),
    sa.Column("leverage_ppm", sa.Integer(), nullable=False),
    sa.Column("message_intensity_ppm", sa.Integer(), nullable=False),
)

#: One row per integrity incident. Incidents are **not** journalled (section
#: 4.5): they come from ``run_detectors`` over a finished journal, so a detector
#: bump changes this table and never a journal hash.
incident = sa.Table(
    "incident",
    METADATA,
    sa.Column("match_id", _ID, primary_key=True),
    sa.Column("incident_id", _ID, primary_key=True),
    sa.Column("kind", _SHORT, nullable=False),
    sa.Column("severity", _SHORT, nullable=False),
    sa.Column("tick", sa.Integer(), nullable=False),
    sa.Column("agent_ids", sa.JSON(), nullable=False),
    sa.Column("market_ids", sa.JSON(), nullable=False),
    sa.Column("score_ppm", sa.Integer(), nullable=False),
    sa.Column("detail", sa.JSON(), nullable=False),
    sa.Column("detector_version", _SHORT, nullable=False),
)

# --------------------------------------------------------------------------
# Tournaments
# --------------------------------------------------------------------------
#: One row per tournament. ``gateway`` is deliberately absent: it is wall clock
#: and cost dependent and is never persisted next to reproducible data.
tournament = sa.Table(
    "tournament",
    METADATA,
    sa.Column("tournament_id", _ID, primary_key=True),
    sa.Column("format", _SHORT, nullable=False),
    sa.Column("n_harnesses", sa.Integer(), nullable=False),
    sa.Column("agents_per_match", sa.Integer(), nullable=False),
    sa.Column("rounds", sa.Integer(), nullable=False),
    sa.Column("template_ids", sa.JSON(), nullable=False),
    sa.Column("seeds", sa.JSON(), nullable=False),
    sa.Column("harness_keys", sa.JSON(), nullable=False),
    sa.Column("background_baselines", sa.JSON(), nullable=False),
    sa.Column("max_cost_usd", sa.Float(), nullable=False),
    sa.Column("match_defaults", sa.JSON(), nullable=False),
)

#: One planned unit of tournament work. The only non PRD entity of the match
#: side, and the source of ``Store.pending_tasks``: see the module docstring.
match_task = sa.Table(
    "match_task",
    METADATA,
    sa.Column("tournament_id", _ID, primary_key=True),
    sa.Column("task_id", _ID, primary_key=True),
    sa.Column("match_id", _ID, nullable=False),
    sa.Column("template_id", _ID, nullable=False),
    sa.Column("seed", sa.BigInteger(), nullable=False),
    sa.Column("status", _SHORT, nullable=False),
    sa.Column("held_out", sa.Boolean(), nullable=False),
    sa.Column("agent_ids", sa.JSON(), nullable=False),
    sa.Column("harness_keys", sa.JSON(), nullable=False),
    sa.Column("profile_assignment", sa.JSON(), nullable=False),
)

#: One row per rated harness per tournament. ``harness_id`` and ``version`` are
#: stored next to the key because ``Store.load_rating_series`` draws the per
#: version progression curve of PRD section 9 from them and a ``LIKE`` on a key
#: prefix is not an index friendly way to ask that question.
rating_record = sa.Table(
    "rating_record",
    METADATA,
    sa.Column("tournament_id", _ID, primary_key=True),
    sa.Column("harness_key", _SHORT, primary_key=True),
    sa.Column("harness_id", _ID, nullable=False),
    sa.Column("version", _SHORT, nullable=False),
    sa.Column("mu", sa.Float(), nullable=False),
    sa.Column("sigma", sa.Float(), nullable=False),
    sa.Column("matches", sa.Integer(), nullable=False),
)

#: One MAP-Elites cell per tournament. ``coords_key`` is the dash joined
#: coordinate tuple, which is the natural id of a cell in a fixed grid; the
#: coordinates themselves are kept as JSON so the archive can be rebuilt without
#: parsing the key.
elite_cell = sa.Table(
    "elite_cell",
    METADATA,
    sa.Column("tournament_id", _ID, primary_key=True),
    sa.Column("coords_key", _SHORT, primary_key=True),
    sa.Column("coords", sa.JSON(), nullable=False),
    sa.Column("harness_key", _SHORT, nullable=False),
    sa.Column("mu", sa.Float(), nullable=False),
    sa.Column("descriptors", sa.JSON(), nullable=False),
)

#: One row per access to the held-out bank (AC-P5: "tout accès journalisé").
#: ``access_id`` is a digest of the entry, so re importing the same access log
#: twice cannot duplicate a row.
heldout_registry = sa.Table(
    "heldout_registry",
    METADATA,
    sa.Column("access_id", _ID, primary_key=True),
    sa.Column("template_id", _ID, nullable=False),
    sa.Column("requester", _SHORT, nullable=False),
    sa.Column("purpose", _SHORT, nullable=False),
    sa.Column("count", sa.Integer(), nullable=False),
    sa.Column("payload", sa.JSON(), nullable=False),
)

#: The twenty-one entities of PRD section 10.4, in the order the PRD lists them.
PRD_TABLES: tuple[str, ...] = (
    "scenario_template",
    "scenario_instance",
    "match",
    "agent",
    "harness_version",
    "tick",
    "news_item",
    "signal",
    "order",
    "trade",
    "position_snapshot",
    "prediction",
    "resolution",
    "settlement",
    "metric_record",
    "rating_record",
    "elite_cell",
    "incident",
    "tournament",
    "heldout_registry",
    "mm_config",
)

#: The two tables that are not PRD entities. See the module docstring.
INFRASTRUCTURE_TABLES: tuple[str, ...] = ("store_schema", "match_task")

#: The thirteen tables ``Store.save_match`` owns, and therefore exactly the ones
#: ``Store.rebuild`` drops and re imports from the journals. Everything else is
#: a tournament level decision that no journal carries.
MATCH_SCOPED_TABLES: tuple[str, ...] = (
    "match",
    "agent",
    "mm_config",
    "tick",
    "news_item",
    "signal",
    "order",
    "trade",
    "position_snapshot",
    "prediction",
    "resolution",
    "settlement",
    "metric_record",
)
