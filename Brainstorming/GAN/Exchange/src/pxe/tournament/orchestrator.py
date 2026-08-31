"""The tournament orchestrator (PRD section 8, T3.1, T3.3, CONTRACTS 7.19, A19).

What this module is responsible for, and nothing else is:

* **Planning.** Turning a :class:`~pxe.types.TournamentConfig` into a tuple of
  :class:`~pxe.types.MatchTask`, one per (pairing group, template, seed), with
  the FR-5.3.2 Latin square applied over the seeds of every matchup and at least
  three seeds per matchup (T3.3, PRD section 5.7).
* **Running.** Playing those tasks, folding every ranking into the TrueSkill
  leaderboard (except for an exhibition, which never moves a rating) and
  mirroring every finished match into the store.
* **Not double counting.** A task whose match is already in the store is never
  replayed: its ranking is read back from its journal and folded exactly once,
  so a tournament that was killed mid flight and restarted produces the same
  match count and the same ratings as an uninterrupted run (T3.1).
* **Staying under the cost ceiling.** ``TournamentConfig.max_cost_usd``, or the
  gateway's per tournament cap when it is left at zero, is checked between
  matches and stops the run rather than overspending (AC-P3).

What it is deliberately not responsible for: the journal (A02 writes it), the
metrics (A15 computes them), the ratings arithmetic (A20), the report rendering
(A23) and the database schema (A21). This module calls those and adds no formula
of its own.

Determinism
-----------
The tournament owns one :class:`~pxe.rng.RngTree`, derived from
``tournament_id`` and the default match seed, and it is used for scheduling only
(the ``tournament.pairing`` substream). A match never sees it: every match builds
``RngTree(config.seed)`` from its own seed (section 3.1), so replaying one match
of a tournament needs the tournament for nothing. The plan is a pure function of
the configuration and of the standings, which is what makes ``resume()`` able to
rebuild the same schedule after a crash.

Concurrency
-----------
Matches run in parallel **processes** and only this process writes to the
database (CONTRACTS section 7.20). The pool is used when ``max_workers > 1`` and
every harness of the tournament is scripted; a tournament holding an LLM harness
runs sequentially in this process, because the budget tracker that enforces
FR-6.2.3 and the cost ceiling is a single object and a per worker copy would
enforce the cap once per worker.
"""

from __future__ import annotations

import logging
import tomllib
from collections.abc import Iterator, Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, fields, replace
from hashlib import blake2b
from pathlib import Path

from pxe.agents.base import BASELINES, make_baseline
from pxe.errors import InvalidConfigError, ResumeError, TournamentError
from pxe.events import Event, MatchEnded, MatchStarted, canonical_json, journal_hash
from pxe.gateway.budget import BudgetTracker
from pxe.gateway.claude_cli import ClaudeCliGateway
from pxe.gateway.protocol import AgentGateway
from pxe.gateway.scripted import CompositeGateway, ScriptedGateway
from pxe.info.profiles import build_profile
from pxe.journal import read_journal
from pxe.metrics.aggregate import compute_all, write_metrics
from pxe.metrics.projection import project
from pxe.rng import RngTree, derive_seed
from pxe.runner.match_runner import run_match
from pxe.store.db import Store
from pxe.store.files import artefact_paths, match_dir
from pxe.tournament.elites import DEFAULT_ELITE_AXES, DEFAULT_ELITE_BINS, EliteArchive
from pxe.tournament.heldout import HeldoutBank
from pxe.tournament.latin_square import BalanceReport, assign_profiles, verify_balance
from pxe.tournament.ratings import DEFAULT_MU, DEFAULT_SIGMA, RatingService
from pxe.tournament.report import write_report
from pxe.tournament.scheduling import format_pairings
from pxe.types import (
    SEED_SPACE,
    AgentSpec,
    GatewayConfig,
    HarnessConfig,
    InfoProfileKind,
    LiquidityProfileName,
    MatchConfig,
    MatchRanking,
    MatchResult,
    MatchTask,
    RatingRecord,
    ScenarioSpec,
    TournamentConfig,
    TournamentFormat,
    TournamentResult,
    harness_key,
    liquidity_profile,
    make_agent_id,
    market_spec_from_dict,
    scenario_to_journal_dict,
    sorted_ids,
)
from pxe.world.generator import World, generate_world, get_template

__all__ = [
    "BACKGROUND_BASELINES",
    "BACKGROUND_HARNESS_VERSION",
    "DEFAULT_MAX_WORKERS",
    "MAX_RUNS_PER_SEED",
    "MIN_SEEDS_PER_MATCHUP",
    "HELDOUT_PURPOSE",
    "background_harness",
    "load_tournament_config",
    "TournamentOrchestrator",
]

_LOG = logging.getLogger("pxe.tournament.orchestrator")

#: The four rated scripted baselines of the PRD section 8 background population.
#: They are TrueSkill floors: a harness that cannot beat them has a mu below
#: theirs, which is only meaningful if they are in the same rated population.
#: The reference market maker is the fifth member of that population and is
#: **not** listed here, because it is never a seat and never rated (FR-5.8.5):
#: every match builds it from ``MatchConfig.mm``.
BACKGROUND_BASELINES: tuple[str, ...] = ("fundamentalist", "momentum", "noise", "zero_intelligence")

#: Version stamped on a background baseline's :class:`~pxe.types.HarnessConfig`.
#: Frozen on purpose: the harness key of a floor must not move between two
#: tournaments, or its rating history splits in two (section 2.2, decision 24).
BACKGROUND_HARNESS_VERSION = "baseline-1"

#: Default worker count of :meth:`TournamentOrchestrator.run`, also used by
#: :meth:`TournamentOrchestrator.resume`.
DEFAULT_MAX_WORKERS = 4

#: PRD section 5.7 and AC-P3: at least three seeds per matchup.
MIN_SEEDS_PER_MATCHUP = 3

#: A match id ends with a two digit run index (section 2.2), so one
#: ``(template, seed)`` pair cannot carry more than 99 distinct matchups.
MAX_RUNS_PER_SEED = 99

#: The purpose a held-out draw is logged under (AC-P5). It has to be one of
#: :data:`pxe.tournament.heldout.EVALUATION_PURPOSES` or the bank refuses.
HELDOUT_PURPOSE = "evaluation"

#: Status written by :meth:`Store.save_task` for a task that has been planned but
#: not played, and for one whose match has been mirrored.
_STATUS_PLANNED = "planned"
_STATUS_DONE = "done"

#: Longest ``tournament_id`` a task id can carry. A task id is
#: ``<tournament_id>#r00-g000-<template_id>-<seed>`` and the store's id columns
#: are ``String(64)``: ten characters of separators and counters, up to sixteen
#: of template id and up to twenty of seed leave twenty-four. SQLite ignores the
#: declared length and Postgres does not, so the check happens here rather than
#: surfacing as a backend specific insert failure halfway through a tournament.
_MAX_TOURNAMENT_ID_CHARS = 24


def background_harness(name: str) -> HarnessConfig:
    """Build the :class:`~pxe.types.HarnessConfig` of one background baseline.

    ``TournamentConfig.background_baselines`` holds baseline **names**, and every
    consumer downstream (pairing, ratings, elites, the store) speaks harness
    keys, so exactly one function turns a name into a harness. Doing it in two
    places would give the same floor two keys and split its rating history.

    Args:
        name: One of :data:`pxe.agents.base.BASELINES`.

    Returns:
        A scripted harness at :data:`BACKGROUND_HARNESS_VERSION`.

    Raises:
        InvalidConfigError: If ``name`` is not a registered baseline.
    """
    if name not in BASELINES:
        raise InvalidConfigError("unknown background baseline", name=name, known=list(BASELINES))
    return HarnessConfig(harness_id=name, version=BACKGROUND_HARNESS_VERSION, kind="scripted")


# --------------------------------------------------------------------------
# TOML presets (configs/*.toml)
#
# Section 2.6: TOML parsing happens only in pxe.cli and here. Nothing else in
# the codebase reads a file to configure itself.
# --------------------------------------------------------------------------
def _table(data: Mapping[str, object], key: str) -> Mapping[str, object]:
    """Return a sub-table of a parsed TOML document.

    Args:
        data: The parsed document.
        key: Name of the table.

    Returns:
        The table, or an empty mapping when absent.

    Raises:
        InvalidConfigError: If the key is present but is not a table.
    """
    value = data.get(key, {})
    if not isinstance(value, Mapping):
        raise InvalidConfigError("expected a TOML table", key=key)
    return value


def _dataclass_kwargs(table: Mapping[str, object], target: type, *, skip: frozenset[str]) -> dict[str, object]:
    """Filter a TOML table into keyword arguments of a frozen dataclass.

    Args:
        table: The parsed table.
        target: The dataclass the keys must belong to.
        skip: Field names this function must not fill (they are derived).

    Returns:
        The accepted keyword arguments.

    Raises:
        InvalidConfigError: If the table holds a key that is not a field.
    """
    known = {field.name for field in fields(target)} - skip
    unknown = sorted(key for key in table if key not in known)
    if unknown:
        raise InvalidConfigError("unknown configuration key", target=target.__name__, keys=unknown)
    return {key: table[key] for key in table}


def _harness_from_toml(entry: Mapping[str, object]) -> HarnessConfig:
    """Build one :class:`~pxe.types.HarnessConfig` from a TOML table.

    Args:
        entry: One ``[[harnesses]]`` table.

    Returns:
        The harness. ``config_hash`` is filled by ``__post_init__``.

    Raises:
        InvalidConfigError: If a mandatory key is missing or ``params`` is not a
            table of strings.
    """
    params_table = _table(entry, "params")
    params = tuple(sorted((str(key), str(value)) for key, value in params_table.items()))
    try:
        return HarnessConfig(
            harness_id=str(entry["harness_id"]),
            version=str(entry["version"]),
            kind=str(entry["kind"]),
            model=str(entry.get("model", "")),
            system_prompt=str(entry.get("system_prompt", "")),
            params=params,
        )
    except KeyError as exc:
        raise InvalidConfigError("a harness needs harness_id, version and kind", missing=str(exc)) from exc


def load_tournament_config(path: Path) -> TournamentConfig:
    """Read a ``configs/*.toml`` preset into a :class:`~pxe.types.TournamentConfig`.

    CONTRACTS section 2.6 puts TOML parsing in exactly two places, ``pxe.cli``
    and this module, and section 7.19 gives no signature for it; this is that
    function, so the CLI and the presets this package owns agree on one shape.
    See CONTRACT ISSUES.

    The document is::

        tournament_id = "T-nightly-0001"
        format = "round_robin"          # round_robin | swiss | exhibition
        template_ids = ["election"]
        seeds = [1, 2, 3]               # at least three (T3.3)
        agents_per_match = 6
        rounds = 1                      # Swiss rounds; 1 for the other formats
        background_baselines = ["fundamentalist"]
        max_cost_usd = 50.0
        [match_defaults]                # any MatchConfig field except mm
        ticks_total = 48
        [gateway]                       # any GatewayConfig field
        timeout_s = 60.0
        [[harnesses]]
        harness_id = "sonnet5"
        version = "1.0.0"
        kind = "llm"

    ``match_defaults.mm`` is deliberately not settable: the market maker block is
    derived from ``liquidity_profile_name`` so the two can never disagree, which
    the runner treats as fatal (section 2.6).

    Args:
        path: The preset file.

    Returns:
        The parsed configuration. It is **not** validated here beyond the
        dataclasses' own rules; :class:`TournamentOrchestrator` validates it.

    Raises:
        InvalidConfigError: On an unknown key, a missing mandatory key or an
            unparsable value.
    """
    with open(path, "rb") as handle:
        data = tomllib.load(handle)

    defaults_table = _table(data, "match_defaults")
    profile_name = LiquidityProfileName(str(defaults_table.get("liquidity_profile_name", "standard")))
    defaults_kwargs = _dataclass_kwargs(defaults_table, MatchConfig, skip=frozenset({"mm"}))
    defaults_kwargs["liquidity_profile_name"] = profile_name
    defaults_kwargs["mm"] = liquidity_profile(profile_name).mm
    match_defaults = MatchConfig(**defaults_kwargs)  # type: ignore[arg-type]

    gateway_kwargs = _dataclass_kwargs(_table(data, "gateway"), GatewayConfig, skip=frozenset())
    gateway = GatewayConfig(**gateway_kwargs)  # type: ignore[arg-type]

    harness_entries = data.get("harnesses", [])
    if not isinstance(harness_entries, list):
        raise InvalidConfigError("harnesses must be an array of tables", path=str(path))
    harnesses = tuple(_harness_from_toml(entry) for entry in harness_entries)

    try:
        return TournamentConfig(
            tournament_id=str(data["tournament_id"]),
            format=TournamentFormat(str(data["format"])),
            harnesses=harnesses,
            template_ids=tuple(str(value) for value in data["template_ids"]),
            seeds=tuple(int(value) for value in data["seeds"]),
            agents_per_match=int(data["agents_per_match"]),
            rounds=int(data.get("rounds", 1)),
            gateway=gateway,
            match_defaults=match_defaults,
            background_baselines=tuple(str(value) for value in data.get("background_baselines", ())),
            max_cost_usd=float(data.get("max_cost_usd", 0.0)),
        )
    except KeyError as exc:
        raise InvalidConfigError("missing tournament key", key=str(exc), path=str(path)) from exc


# --------------------------------------------------------------------------
# One unit of work, as a picklable payload
#
# A worker process receives exactly this and returns a MatchResult. It carries no
# Store, no gateway and no RngTree: everything is rebuilt from the seed inside
# the worker, which is what keeps a parallel tournament bit identical to a
# sequential one.
# --------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class _MatchJob:
    """Everything one match needs, in picklable form.

    Attributes:
        task: The planned task.
        config: The match configuration, already carrying ``task.seed``.
        harnesses: The harness of each seat, aligned with ``task.agent_ids``.
        runs_dir: The runs root, as a string so the payload stays trivially
            picklable on every platform.
    """

    task: MatchTask
    config: MatchConfig
    harnesses: tuple[HarnessConfig, ...]
    runs_dir: str

    @property
    def out_dir(self) -> Path:
        """The artefact directory of this match, ``runs/<match_id>``."""
        return match_dir(Path(self.runs_dir), self.task.match_id)


def _world_for(job: _MatchJob) -> World:
    """Generate the world of one job.

    A pure function of ``(template_id, seed)`` plus the metadata copies the
    runner cross checks against the configuration (section 2.6).

    Args:
        job: The unit of work.

    Returns:
        The generated world.
    """
    return generate_world(
        template_id=job.task.template_id,
        seed=job.task.seed,
        ticks_total=job.config.ticks_total,
        n_markets=job.config.n_markets,
        liquidity=job.config.liquidity_profile_name,
        talking_mode=job.config.talking_mode,
        held_out=job.task.held_out,
    )


def _specs_for(job: _MatchJob, world: World) -> tuple[AgentSpec, ...]:
    """Build one :class:`~pxe.types.AgentSpec` per seat of a job.

    The information profile of a seat is the one the Latin square assigned
    (``task.profile_assignment``), and a specialist's focus market is
    ``market_ids[seat_index % n_markets]``: a deterministic spread, so two
    specialists in the same match do not both watch ``M1``.

    Args:
        job: The unit of work.
        world: The generated world.

    Returns:
        The seats, ascending by ``agent_id``.

    Raises:
        InvalidConfigError: If the profile assignment does not cover the seats.
    """
    market_ids = world.market_ids()
    assignment = dict(job.task.profile_assignment)
    specs: list[AgentSpec] = []
    for index, agent_id in enumerate(job.task.agent_ids):
        kind = assignment.get(agent_id)
        if kind is None:
            raise InvalidConfigError("no profile assigned to a seat", agent_id=agent_id, task_id=job.task.task_id)
        focus = market_ids[index % len(market_ids)] if kind is InfoProfileKind.SPECIALIST else None
        specs.append(
            AgentSpec(
                agent_id=agent_id,
                harness=job.harnesses[index],
                info_profile=build_profile(kind, market_ids=market_ids, focus_market_id=focus),
            )
        )
    return tuple(specs)


def _scripted_agents(
    specs: Sequence[AgentSpec],
    *,
    config: MatchConfig,
    rng: RngTree,
) -> dict[str, object]:
    """Build one scripted baseline per scripted seat, each on its own substream.

    The substream is the one CONTRACTS section 3.1 spells out,
    ``root.child(f"agent/{agent_id}").substream(f"agent.{agent_id}")``, and it is
    spelled here once.

    Args:
        specs: The seats to build, scripted ones only.
        config: The match configuration.
        rng: The match root tree, ``RngTree(config.seed)``.

    Returns:
        Seat id to agent, ready for :class:`~pxe.gateway.scripted.ScriptedGateway`.
    """
    built: dict[str, object] = {}
    for spec in specs:
        built[spec.agent_id] = make_baseline(
            spec.harness.harness_id,
            agent_id=spec.agent_id,
            config=config,
            rng=rng.child(f"agent/{spec.agent_id}").substream(f"agent.{spec.agent_id}"),
        )
    return built


def _play_scripted(job: _MatchJob) -> MatchResult:
    """Play one all scripted match. This is the process pool worker.

    It is a module level function taking a picklable payload, which is what makes
    it usable with ``ProcessPoolExecutor`` on a spawn platform. It writes the
    match artefacts and returns the result; it touches no database, because only
    the orchestrator process writes there (CONTRACTS section 7.20).

    Args:
        job: The unit of work.

    Returns:
        The match result, including the AC-P1 journal hash.
    """
    world = _world_for(job)
    specs = _specs_for(job, world)
    rng = RngTree(job.config.seed)
    gateway = ScriptedGateway(agents=_scripted_agents(specs, config=job.config, rng=rng))  # type: ignore[arg-type]
    try:
        return run_match(
            config=job.config,
            world=world,
            agents=specs,
            gateway=gateway,
            out_dir=job.out_dir,
            rng=rng,
            match_id=job.task.match_id,
        )
    finally:
        gateway.close()


class TournamentOrchestrator:
    """Plans, runs and resumes a tournament (T3.1, T3.3, AC-P3).

    Not thread safe, by the same rule as :class:`pxe.store.db.Store`: this object
    is the single writer of the projection database and of the leaderboard.
    """

    __slots__ = (
        "_balance",
        "_budget",
        "_config",
        "_heldout",
        "_heldout_seeds",
        "_played_by_round",
        "_population",
        "_rng",
        "_store",
    )

    def __init__(
        self,
        *,
        config: TournamentConfig,
        store: Store,
        heldout: HeldoutBank | None = None,
    ) -> None:
        """Validate the configuration and register the tournament in the store.

        The store rows CONTRACTS section 7.20 says are written from here are
        written here: the ``tournament`` row, one ``scenario_template`` row per
        template id and one ``harness_version`` row per member of the population
        (the declared harnesses plus the background baselines).

        Args:
            config: The tournament definition. Validated here rather than in
                ``TournamentConfig.__post_init__``, which section 7.19 rule 5
                assigns the checks to but which ``pxe.types`` (A01, read only for
                this package) does not implement. See CONTRACT ISSUES.
            store: The projection database plus artefact directory. Its schema is
                created here, idempotently.
            heldout: Optional sealed seed bank. When given, every task's seed is
                drawn from it instead of from ``config.seeds``, the tasks are
                flagged ``held_out`` and the access log is mirrored into the
                store (T3.5, AC-P5). Keyword-only with a default, so the
                contracted two argument call is unchanged.

        Raises:
            InvalidConfigError: On any configuration error listed in section 7.19
                rule 5: fewer than three seeds, ``agents_per_match`` outside
                4..8, a population smaller than one match, an unknown template,
                an unknown background baseline, a duplicate seed or harness key,
                a non positive round count, or a ``tournament_id`` that is empty
                or holds the ``#`` the store's task id convention reserves.
        """
        self._config = config
        self._store = store
        self._population: tuple[HarnessConfig, ...] = self._build_population(config)
        self._validate(config, self._population)
        self._heldout = heldout
        self._heldout_seeds: dict[str, tuple[int, ...]] = {}
        self._played_by_round: dict[int, tuple[tuple[str, ...], ...]] = {}
        self._balance: BalanceReport = verify_balance(())
        self._budget = BudgetTracker(config.gateway)
        seed = derive_seed(config.match_defaults.seed, f"tournament/{config.tournament_id}") % 2**64
        self._rng = RngTree(seed, namespace="tournament")

        store.init_schema()
        store.save_tournament(config)
        for template_id in config.template_ids:
            template = get_template(template_id)
            store.save_scenario_template(
                template_id=template.template_id,
                template_version=template.template_version,
                default_ticks=template.default_ticks,
                default_markets=template.default_markets,
            )
        for harness in self._population:
            store.save_harness_version(harness)

    # -- configuration ----------------------------------------------------
    @staticmethod
    def _build_population(config: TournamentConfig) -> tuple[HarnessConfig, ...]:
        """Return the rated population: the declared harnesses plus the floors.

        PRD section 8's background population is "the reference market maker
        (out of the ranking) plus the four rated scripted baselines". The market
        maker is not a seat and needs no harness; the baselines do, and they are
        appended here so that they are paired, seated and rated exactly like a
        competitor, which is the only way they can be TrueSkill floors.

        Args:
            config: The tournament definition.

        Returns:
            The population, declared harnesses first, in declaration order, with
            a duplicate key kept once.
        """
        population: list[HarnessConfig] = []
        seen: set[str] = set()
        for harness in (*config.harnesses, *(background_harness(name) for name in config.background_baselines)):
            key = harness_key(harness)
            if key in seen:
                continue
            seen.add(key)
            population.append(harness)
        return tuple(population)

    @staticmethod
    def _validate(config: TournamentConfig, population: Sequence[HarnessConfig]) -> None:
        """Enforce CONTRACTS section 7.19 rule 5 plus the store's id conventions.

        Args:
            config: The tournament definition.
            population: The result of :meth:`_build_population`.

        Raises:
            InvalidConfigError: On any invalid field, with the offending value.
        """
        if not config.tournament_id:
            raise InvalidConfigError("a tournament needs an id")
        if "#" in config.tournament_id:
            raise InvalidConfigError(
                "the store reads the tournament id off the task id prefix, so # is reserved",
                tournament_id=config.tournament_id,
            )
        if len(config.tournament_id) > _MAX_TOURNAMENT_ID_CHARS:
            raise InvalidConfigError(
                "a tournament id must leave room for the task id suffix inside a 64 character column",
                tournament_id=config.tournament_id,
                limit=_MAX_TOURNAMENT_ID_CHARS,
            )
        if len(config.seeds) < MIN_SEEDS_PER_MATCHUP:
            raise InvalidConfigError(
                "at least three seeds per matchup (PRD section 5.7, T3.3, AC-P3)",
                seeds=len(config.seeds),
            )
        if len(set(config.seeds)) != len(config.seeds):
            raise InvalidConfigError("duplicate seed", seeds=list(config.seeds))
        for seed in config.seeds:
            if not 0 <= seed < SEED_SPACE:
                raise InvalidConfigError("a seed must fit in 63 unsigned bits", seed=seed)
        if not 4 <= config.agents_per_match <= 8:
            raise InvalidConfigError(
                "a match seats 4 to 8 agents (PRD section 5.7)",
                agents_per_match=config.agents_per_match,
            )
        if len(population) < config.agents_per_match:
            raise InvalidConfigError(
                "the population is smaller than one match",
                n_harnesses=len(population),
                agents_per_match=config.agents_per_match,
            )
        if not config.template_ids:
            raise InvalidConfigError("a tournament needs at least one world template")
        for template_id in config.template_ids:
            get_template(template_id)
        if config.rounds < 1:
            raise InvalidConfigError("a tournament plays at least one round", rounds=config.rounds)
        if config.max_cost_usd < 0.0:
            raise InvalidConfigError("a cost ceiling is never negative", max_cost_usd=config.max_cost_usd)
        if config.match_defaults.n_agents != config.agents_per_match:
            _LOG.debug(
                "match_defaults.n_agents is overridden by agents_per_match",
                extra={"n_agents": config.match_defaults.n_agents, "agents_per_match": config.agents_per_match},
            )

    @property
    def config(self) -> TournamentConfig:
        """The tournament definition this orchestrator was built with."""
        return self._config

    @property
    def population(self) -> tuple[HarnessConfig, ...]:
        """The rated population: declared harnesses plus background floors."""
        return self._population

    @property
    def profile_balance(self) -> BalanceReport:
        """The FR-5.3.2 balance of the last plan, for the report (section 7.24).

        Empty until :meth:`plan_round` has run at least once: the balance is a
        property of the schedule, not of the configuration.
        """
        return self._balance

    # -- planning ---------------------------------------------------------
    def plan(self) -> tuple[MatchTask, ...]:
        """Return the whole schedule up front.

        Only the two standings independent formats can answer this:
        ``plan()`` is ``plan_round(0, ())`` for round robin and for an
        exhibition. Swiss pairs one round at a time by construction, so asking
        for its whole schedule is a caller error and not an empty answer.

        Returns:
            Every task of the tournament, in playing order.

        Raises:
            TournamentError: If the format is Swiss.
        """
        if self._config.format is TournamentFormat.SWISS:
            raise TournamentError(
                "a Swiss tournament is planned one round at a time; call plan_round",
                tournament_id=self._config.tournament_id,
            )
        return self.plan_round(0, ())

    def plan_round(self, round_index: int, standings: Sequence[RatingRecord]) -> tuple[MatchTask, ...]:
        """Return the tasks of one round.

        The general form, and the only one Swiss can use: the pairing depends on
        the standings after the previous round. Every pairing group is played on
        **every** template and **every** seed of the configuration, which is what
        makes "at least three seeds per matchup" (T3.3) structural rather than a
        convention, and the Latin square rotates the information profiles over
        those seeds (FR-5.3.2).

        The call is idempotent: two calls with the same ``round_index`` and the
        same standings return equal tasks, because the round's own groups are
        recorded under that index rather than appended to a growing history.

        Args:
            round_index: The round, ``0`` based.
            standings: The leaderboard after the previous round. A harness of the
                population that is absent is completed at the TrueSkill prior, so
                round ``0`` can be planned from an empty sequence.

        Returns:
            The tasks, in playing order.

        Raises:
            InvalidConfigError: If ``round_index`` is negative, or if one
                ``(template, seed)`` pair would need more than 99 run indices,
                which a match id cannot express (section 2.2).
        """
        if round_index < 0:
            raise InvalidConfigError("a round index is never negative", round_index=round_index)
        keys = tuple(harness_key(harness) for harness in self._population)
        groups = format_pairings(
            self._config.format,
            harness_keys=self._field_for_format(keys),
            agents_per_match=self._config.agents_per_match,
            standings=self._completed_standings(standings, keys),
            played=self._played_before(round_index),
            challengers=self._challengers(keys),
            rng=self._rng.fresh_substream("tournament.pairing"),
        )
        self._played_by_round[round_index] = groups
        groups_per_round = max(len(groups), 1)
        if round_index * groups_per_round + len(groups) > MAX_RUNS_PER_SEED:
            raise InvalidConfigError(
                "more matchups than a two digit run index can express (section 2.2)",
                groups=len(groups),
                round_index=round_index,
                limit=MAX_RUNS_PER_SEED,
            )

        agent_ids = tuple(make_agent_id(index + 1) for index in range(self._config.agents_per_match))
        kinds: tuple[InfoProfileKind, ...] = tuple(InfoProfileKind)
        assignments: list[tuple[tuple[str, InfoProfileKind], ...]] = []
        tasks: list[MatchTask] = []
        for group_index, group in enumerate(groups):
            run_index = round_index * groups_per_round + group_index + 1
            for template_id in self._config.template_ids:
                for seed_index, seed in enumerate(self._seeds_for(template_id)):
                    assignment = assign_profiles(agent_ids=agent_ids, profile_kinds=kinds, seed_index=seed_index)
                    if group_index == 0 and template_id == self._config.template_ids[0]:
                        assignments.append(assignment)
                    tasks.append(
                        MatchTask(
                            task_id=(
                                f"{self._config.tournament_id}#r{round_index:02d}"
                                f"-g{group_index:03d}-{template_id}-{seed}"
                            ),
                            match_id=f"m-{template_id}-{seed}-{run_index:02d}",
                            template_id=template_id,
                            seed=seed,
                            agent_ids=agent_ids,
                            harness_keys=group,
                            profile_assignment=assignment,
                            held_out=self._heldout is not None,
                        )
                    )
        self._balance = verify_balance(assignments)
        return tuple(tasks)

    def _field_for_format(self, keys: Sequence[str]) -> tuple[str, ...]:
        """Return the ``harness_keys`` argument of the pairing function.

        Round robin pairs the whole population. An exhibition plays a challenger
        against a **fixed field**, which PRD section 8 says is the background
        population (or a Hall of Fame), so the field is the background baselines
        when there are any and the whole population otherwise. Swiss ignores this
        argument entirely and reads the standings.

        Args:
            keys: The population keys, in population order.

        Returns:
            The keys to hand to :func:`~pxe.tournament.scheduling.format_pairings`.
        """
        if self._config.format is not TournamentFormat.EXHIBITION:
            return tuple(keys)
        field = tuple(harness_key(background_harness(name)) for name in self._config.background_baselines)
        return field if field else tuple(keys)

    def _challengers(self, keys: Sequence[str]) -> tuple[str, ...]:
        """Return the exhibition challengers: the declared harnesses.

        Args:
            keys: The population keys, unused for any other format.

        Returns:
            One key per declared harness, in declaration order. Empty for the two
            other formats, which ignore the argument.
        """
        if self._config.format is not TournamentFormat.EXHIBITION:
            return ()
        declared = tuple(harness_key(harness) for harness in self._config.harnesses)
        return declared if declared else tuple(keys)

    def _completed_standings(
        self,
        standings: Sequence[RatingRecord],
        keys: Sequence[str],
    ) -> tuple[RatingRecord, ...]:
        """Complete a leaderboard with the prior for every unrated population key.

        Swiss sorts the standings and seats what it finds there, so a harness
        entering at round zero has to be present at the prior or it never plays.
        :meth:`pxe.tournament.ratings.RatingService.rating` returns the prior for
        an unknown key for exactly this reason; this method applies it to the
        whole population without needing the service.

        Args:
            standings: The known records.
            keys: Every population key.

        Returns:
            One record per population key, known records kept as they are.
        """
        known = {record.harness_key: record for record in standings}
        return tuple(
            known.get(key, RatingRecord(harness_key=key, mu=DEFAULT_MU, sigma=DEFAULT_SIGMA, matches=0)) for key in keys
        )

    def _played_before(self, round_index: int) -> tuple[frozenset[str], ...]:
        """Return every group played before one round, in round order.

        Swiss reads this twice: as the rematch filter, and through its length as
        the round index its signature does not carry (see CONTRACT ISSUES).

        Args:
            round_index: The round about to be paired.

        Returns:
            One frozen set per group, rounds in ascending order.
        """
        history: list[frozenset[str]] = []
        for index in sorted(self._played_by_round):
            if index >= round_index:
                break
            history.extend(frozenset(group) for group in self._played_by_round[index])
        return tuple(history)

    def _seeds_for(self, template_id: str) -> tuple[int, ...]:
        """Return the seeds of one template, sealed ones when a bank is bound.

        Every draw from the held-out bank is logged by the bank and mirrored into
        the store here, which is the AC-P5 audit trail. The draw is memoised per
        template so planning a second round does not log a second access for the
        same sealed set.

        Args:
            template_id: The template about to be planned.

        Returns:
            The seeds, in configuration order for a normal run and ascending for
            a sealed one.
        """
        if self._heldout is None:
            return self._config.seeds
        cached = self._heldout_seeds.get(template_id)
        if cached is None:
            cached = self._heldout.draw(
                template_id=template_id,
                count=len(self._config.seeds),
                requester=self._config.tournament_id,
                purpose=HELDOUT_PURPOSE,
            )
            self._heldout_seeds[template_id] = cached
            self._store.save_heldout_access(self._heldout.access_log_entries())
        return cached

    # -- running ----------------------------------------------------------
    def run(self, *, max_workers: int = DEFAULT_MAX_WORKERS) -> TournamentResult:
        """Play the whole tournament and return its result.

        Idempotent in the same way :meth:`resume` is: a task whose match is
        already in the store is not replayed, so calling ``run`` twice plays
        every match once. The two entry points share one algorithm on purpose,
        because a restart must not depend on the operator picking the right verb.

        A caller that runs this from a **script** with ``max_workers > 1`` must
        put the call behind ``if __name__ == "__main__":``. That is the standard
        requirement of the spawn start method (Windows and macOS): without the
        guard each worker re-executes the script's module level code. ``pxe.cli``
        and the tests are unaffected because they import rather than exec.

        Args:
            max_workers: Number of parallel worker **processes**. ``1`` runs in
                this process. A tournament holding an LLM harness always runs in
                this process whatever this value is, because the budget tracker
                enforcing the cost ceiling is a single object.

        Returns:
            The result: every match that ran or was already there, the final
            leaderboard, the total provider cost and the report path.

        Raises:
            InvalidConfigError: If ``max_workers`` is below one.
            ResumeError: If the store holds a pending task of this tournament
                that the plan does not contain, which means the configuration
                changed between two runs and the two schedules cannot be merged.
        """
        if max_workers < 1:
            raise InvalidConfigError("a tournament needs at least one worker", max_workers=max_workers)
        return self._execute(max_workers=max_workers)

    def resume(self) -> TournamentResult:
        """Continue an interrupted tournament without double counting.

        Idempotent: a task already present in the store is never replayed. The
        schedule is rebuilt from the configuration (it is a pure function of it
        and of the standings), every finished match's ranking is read back from
        its own journal and folded into the leaderboard in the same order an
        uninterrupted run would have folded it, and only the missing matches are
        played. The result is therefore the same match count and the same
        ratings as an uninterrupted run.

        Returns:
            The result of the completed tournament.

        Raises:
            ResumeError: If the store holds a pending task the plan does not
                contain.
        """
        return self._execute(max_workers=DEFAULT_MAX_WORKERS)

    def _execute(self, *, max_workers: int) -> TournamentResult:
        """Plan, play and persist every round. The one implementation of run.

        Args:
            max_workers: Worker processes, ``1`` meaning "in this process".

        Returns:
            The tournament result.

        Raises:
            ResumeError: If a pending stored task is not in the plan.
        """
        ratings = RatingService()
        archive = EliteArchive(axes=DEFAULT_ELITE_AXES, bins=DEFAULT_ELITE_BINS)
        results: list[MatchResult] = []
        n_rounds = self._config.rounds if self._config.format is TournamentFormat.SWISS else 1
        planned_ids: set[str] = set()
        stopped = False
        for round_index in range(n_rounds):
            tasks = self.plan_round(round_index, ratings.leaderboard())
            if not tasks:
                _LOG.info("no pairing left to play", extra={"round_index": round_index})
                break
            self._save_scenarios(tasks)
            for task in tasks:
                planned_ids.add(task.task_id)
                if not self._store.has_match(task.match_id):
                    self._store.save_task(task, status=_STATUS_PLANNED)
            for task, result in self._results_for(tasks, max_workers=max_workers):
                results.append(result)
                self._fold(ratings, archive, task=task, result=result)
                if self._over_ceiling():
                    _LOG.warning(
                        "tournament cost ceiling reached, stopping",
                        extra={"tournament_id": self._config.tournament_id, "matches": len(results)},
                    )
                    stopped = True
                    break
            self._store.save_ratings(self._config.tournament_id, ratings.leaderboard())
            self._store.save_elites(self._config.tournament_id, archive.cells())
            if stopped:
                break
        self._check_no_orphan_task(planned_ids)
        return self._result(results, ratings)

    def _check_no_orphan_task(self, planned_ids: set[str]) -> None:
        """Refuse to report success when the store holds a task outside the plan.

        A pending task the rebuilt schedule does not contain means the
        configuration changed between the interrupted run and this one, so the
        two schedules cannot be merged and "resumed without double counting" is
        not something this object can promise.

        Args:
            planned_ids: The task ids this run planned.

        Raises:
            ResumeError: If a stored pending task is unknown to the plan.
        """
        orphans = sorted(
            task.task_id
            for task in self._store.pending_tasks(self._config.tournament_id)
            if task.task_id not in planned_ids
        )
        if orphans:
            raise ResumeError(
                "the store holds pending tasks this plan does not contain",
                tournament_id=self._config.tournament_id,
                task_ids=orphans[:8],
            )

    def _results_for(
        self,
        tasks: Sequence[MatchTask],
        *,
        max_workers: int,
    ) -> Iterator[tuple[MatchTask, MatchResult]]:
        """Yield one result per task, in task order, playing only what is missing.

        A task whose ``match_id`` is already in the store is **not** replayed: its
        result is rebuilt from its journal, which is the "no double counting" half
        of T3.1. Everything else is played, either in this process or in a pool.

        Args:
            tasks: The round's tasks, in playing order.
            max_workers: Worker processes.

        Yields:
            ``(task, result)`` pairs in task order.
        """
        jobs = [self._job_for(task) for task in tasks]
        missing = [job for job in jobs if not self._store.has_match(job.task.match_id)]
        produced: dict[str, MatchResult] = {}
        if missing and max_workers > 1 and not self._has_llm():
            with ProcessPoolExecutor(max_workers=max_workers) as pool:
                for result in pool.map(_play_scripted, missing):
                    produced[result.match_id] = result
        for job in jobs:
            task = job.task
            if self._store.has_match(task.match_id):
                _LOG.info("already played, not replayed", extra={"match_id": task.match_id})
                yield task, self._reload(job)
                continue
            ready = produced.get(task.match_id)
            result = ready if ready is not None else self._play(job)
            self._persist(task, result)
            yield task, result

    def _job_for(self, task: MatchTask) -> _MatchJob:
        """Build the picklable payload of one task.

        Args:
            task: The planned task.

        Returns:
            The job. ``MatchConfig.seed`` is the task's seed and ``n_agents`` is
            the seat count, so the runner's section 2.6 cross checks pass.

        Raises:
            InvalidConfigError: If a harness key of the task is not in the
                population, which means the task was planned by another
                configuration.
        """
        by_key = {harness_key(harness): harness for harness in self._population}
        try:
            harnesses = tuple(by_key[key] for key in task.harness_keys)
        except KeyError as exc:
            raise InvalidConfigError(
                "a task names a harness that is not in this population",
                task_id=task.task_id,
                harness_key=str(exc),
            ) from exc
        config = replace(
            self._config.match_defaults,
            seed=task.seed,
            n_agents=len(task.agent_ids),
        )
        return _MatchJob(task=task, config=config, harnesses=harnesses, runs_dir=str(self._store.runs_dir))

    def _has_llm(self) -> bool:
        """Return True when any member of the population is an LLM harness.

        Returns:
            Whether the tournament must run in this process.
        """
        return any(harness.kind == "llm" for harness in self._population)

    def _play(self, job: _MatchJob) -> MatchResult:
        """Play one match in this process.

        Scripted seats go through :class:`~pxe.gateway.scripted.ScriptedGateway`
        and LLM seats through :class:`~pxe.gateway.claude_cli.ClaudeCliGateway`,
        joined by a :class:`~pxe.gateway.scripted.CompositeGateway` when the table
        is mixed, so each family keeps its own timeout and parallelism. The budget
        tracker is the tournament's, and its match scope is released before every
        match, which is what makes the per match cap a per match cap.

        Args:
            job: The unit of work.

        Returns:
            The match result.

        Raises:
            InvalidConfigError: If a seat's harness kind is neither scripted nor
                LLM, which ``HarnessConfig`` already refuses at construction.
        """
        if not self._has_llm():
            return _play_scripted(job)
        world = _world_for(job)
        specs = _specs_for(job, world)
        rng = RngTree(job.config.seed)
        scripted = tuple(spec for spec in specs if spec.harness.kind == "scripted")
        llm = tuple(spec for spec in specs if spec.harness.kind == "llm")
        table: list[tuple[tuple[str, ...], AgentGateway]] = []
        if scripted:
            table.append(
                (
                    tuple(spec.agent_id for spec in scripted),
                    ScriptedGateway(agents=_scripted_agents(scripted, config=job.config, rng=rng)),  # type: ignore[arg-type]
                )
            )
        if llm:
            table.append(
                (
                    tuple(spec.agent_id for spec in llm),
                    ClaudeCliGateway(
                        harnesses={spec.agent_id: spec.harness for spec in llm},
                        gateway_config=self._config.gateway,
                        budget=self._budget,
                        trace_path=artefact_paths(self._store.runs_dir, job.task.match_id)["llm_trace"],
                    ),
                )
            )
        gateway: AgentGateway = table[0][1] if len(table) == 1 else CompositeGateway(gateways=table)
        self._budget.reset_match()
        try:
            return run_match(
                config=job.config,
                world=world,
                agents=specs,
                gateway=gateway,
                out_dir=job.out_dir,
                rng=rng,
                match_id=job.task.match_id,
            )
        finally:
            gateway.close()

    def _persist(self, task: MatchTask, result: MatchResult) -> None:
        """Mirror one finished match: metrics file, database rows, task status.

        Every number written here is a projection of the journal (CONTRACTS
        section 4.1): the projection is folded from the events, the metrics are
        computed from the projection, and neither reads engine state.

        Args:
            task: The task that produced the match.
            result: The result the runner returned.
        """
        events = read_journal(artefact_paths(self._store.runs_dir, result.match_id)["journal"])
        projection = project(events)
        metrics = compute_all(projection)
        write_metrics(artefact_paths(self._store.runs_dir, result.match_id)["metrics"], metrics)
        self._store.save_match(result, projection, metrics)
        self._store.save_task(task, status=_STATUS_DONE)

    def _reload(self, job: _MatchJob) -> MatchResult:
        """Rebuild the :class:`~pxe.types.MatchResult` of an already played match.

        This is what makes resume free of double counting: the ranking a rating
        update needs comes from the journal of the finished match, and the match
        itself is not replayed. The scenario is rebuilt from ``MatchStarted`` the
        way ``replay_journal`` does (section 7.12), so no world is regenerated.

        Args:
            job: The unit of work whose match is already in the store.

        Returns:
            The result of that match.

        Raises:
            ResumeError: If the journal is missing, holds no ``MatchStarted`` or
                no ``MatchEnded``. A mirrored match without a complete journal
                cannot be folded into the ratings, and guessing would be the
                double counting this method exists to prevent.
        """
        path = artefact_paths(self._store.runs_dir, job.task.match_id)["journal"]
        if not path.exists():
            raise ResumeError("a mirrored match has no journal", match_id=job.task.match_id, path=str(path))
        events = read_journal(path)
        started = _match_started(events, match_id=job.task.match_id)
        ended = _match_ended(events, match_id=job.task.match_id)
        scenario = ScenarioSpec(
            template_id=started.scenario_template_id,
            template_version=started.scenario_template_version,
            seed=started.seed,
            ticks_total=started.ticks_total,
            markets=tuple(market_spec_from_dict(entry) for entry in started.markets),
            talking_mode=job.config.talking_mode,
            liquidity_profile_name=job.config.liquidity_profile_name,
            held_out=job.task.held_out,
        )
        return MatchResult(
            match_id=job.task.match_id,
            seed=started.seed,
            scenario=scenario,
            rankings=tuple(
                MatchRanking(
                    rank=int(row["rank"]),
                    agent_id=str(row["agent_id"]),
                    pnl_cents=int(row["pnl_cents"]),
                    final_cash_cents=int(row["final_cash_cents"]),
                    pnl_pct_bps=int(row["pnl_pct_bps"]),
                )
                for row in ended.rankings
            ),
            journal_path=str(path),
            journal_hash=journal_hash(events),
            event_count=len(events),
            mm_pnl_cents=ended.mm_pnl_cents,
            fees_collected_cents=ended.fees_collected_cents,
        )

    def _fold(self, ratings: RatingService, archive: EliteArchive, *, task: MatchTask, result: MatchResult) -> None:
        """Fold one match into the leaderboard and into the MAP-Elites archive, once.

        An **exhibition** never moves a rating (CONTRACTS section 7.19): a
        novelty match against a curated field is not evidence about the field,
        and for the same reason it never populates the archive either.
        ``MM`` and ``FEES`` are absent from ``harness_of`` by construction, so
        FR-5.8.5 is structural here and not a filter.

        Args:
            ratings: The service holding the leaderboard.
            archive: The MAP-Elites grid of the tournament (T5.2).
            task: The task, which is where the seat to harness mapping lives.
            result: The finished match.
        """
        if self._config.format is TournamentFormat.EXHIBITION:
            return
        harness_of = dict(zip(task.agent_ids, task.harness_keys, strict=True))
        ratings.update(result.rankings, harness_of=harness_of)
        self._offer_elites(ratings, archive, harness_of=harness_of, match_id=result.match_id)

    def _offer_elites(
        self, ratings: RatingService, archive: EliteArchive, *, harness_of: Mapping[str, str], match_id: str
    ) -> None:
        """Offer every seat of a finished match to the archive (T5.2, section 7.20).

        The style vector is A17's, read back from the ``metric_record`` rows
        :meth:`_persist` wrote, so a resumed tournament fills the archive from
        the store exactly as an uninterrupted one does and no match is replayed
        for it. ``mu`` is the rating **after** this match, which is what makes
        "the elite of a cell is its best mu" a statement about the tournament
        and not about the order matches happened to finish in.

        Args:
            ratings: The service holding the leaderboard.
            archive: The grid to fill.
            harness_of: Seat to harness key, from the task.
            match_id: The finished match.
        """
        descriptors = {row.agent_id: row for row in self._store.load_metrics(match_id).descriptors}
        for agent_id in sorted_ids(list(harness_of)):
            style = descriptors.get(agent_id)
            if style is None:
                continue
            harness = harness_of[agent_id]
            archive.offer(harness_key=harness, mu=ratings.rating(harness).mu, descriptors=style)

    def _costs(self) -> tuple[tuple[str, float], ...]:
        """Return the provider cost of this tournament so far, per harness key.

        Cost is forbidden in a journal (section 3.5), so the only source is
        ``runs/<match_id>/llm_trace.jsonl`` as summed into the ``agent`` table by
        :meth:`pxe.store.db.Store.save_match`. A scripted tournament reports
        nothing at all, which is why the query is skipped for one.

        Returns:
            ``(harness_key, cost_usd)`` pairs, empty for an all scripted run.
        """
        if not self._has_llm():
            return ()
        return self._store.load_costs_usd(self._config.tournament_id)

    def _ceiling_usd(self) -> float:
        """Return the tournament cost ceiling in USD (AC-P3).

        ``TournamentConfig.max_cost_usd`` wins when it is set. Zero means "not
        configured here", and the gateway's ``max_budget_usd_per_tournament``
        applies instead, so a tournament always has a finite ceiling and an
        operator cannot disable the cap by omitting a field.

        Returns:
            The ceiling.
        """
        if self._config.max_cost_usd > 0.0:
            return self._config.max_cost_usd
        return self._config.gateway.max_budget_usd_per_tournament

    def _over_ceiling(self) -> bool:
        """Return True when no further match may be started (AC-P3).

        The check is between matches: a match already running is never abandoned
        halfway, which would leave a journal without a ``MatchEnded``.

        Returns:
            Whether the accumulated cost has reached the ceiling.
        """
        spent = sum(cost for _key, cost in self._costs())
        return spent >= self._ceiling_usd()

    def _result(self, results: Sequence[MatchResult], ratings: RatingService) -> TournamentResult:
        """Assemble the :class:`~pxe.types.TournamentResult` and its report path.

        The report itself is A23's (:mod:`pxe.tournament.report`, section 7.24).
        It is written here when that module is importable, which is what makes
        T3.6's "end of tournament, report generated with no manual action" true;
        until it lands, ``report_path`` names the file the report will be written
        to and nothing is fabricated. See CONTRACT ISSUES.

        Args:
            results: Every match of the tournament, in playing order.
            ratings: The service holding the final leaderboard.

        Returns:
            The tournament result.
        """
        out_dir = self._store.runs_dir / self._config.tournament_id
        result = TournamentResult(
            tournament_id=self._config.tournament_id,
            match_results=tuple(results),
            ratings=ratings.leaderboard(),
            total_cost_usd=sum(cost for _key, cost in self._costs()),
            report_path=str(out_dir / "report.md"),
        )
        markdown, _html = write_report(result=result, store=self._store, out_dir=out_dir)
        return replace(result, report_path=str(markdown))

    def _save_scenarios(self, tasks: Sequence[MatchTask]) -> None:
        """Mirror every distinct world of a round (section 7.20 writer table).

        ``scenario_instance`` is the only record of the correlations and of the
        scripted cancellations of a world, which no journal event carries, and
        section 7.20 names the orchestrator as its writer "after
        ``generate_world``". There are ``len(template_ids) * len(seeds)`` distinct
        worlds however many matches play them, so this generates a handful of
        worlds and not one per match.

        Args:
            tasks: The round's tasks.
        """
        seen: set[tuple[str, int]] = set()
        for task in tasks:
            key = (task.template_id, task.seed)
            if key in seen:
                continue
            seen.add(key)
            scenario = _world_for(self._job_for(task)).scenario
            self._store.save_scenario_instance(scenario, world_hash=_world_hash(scenario))


def _world_hash(scenario: ScenarioSpec) -> str:
    """Return the digest of one scenario, for ``Store.save_scenario_instance``.

    ``Store.save_scenario_instance`` takes the digest from its caller and section
    7.20 names the orchestrator as that caller, so the one spelling of it lives
    here: blake2b over the canonical JSON of the journalled scenario, 32 hex
    characters. It is a pure function of the scenario, so two machines agree.

    Args:
        scenario: The generated world's public description.

    Returns:
        32 hexadecimal characters.
    """
    payload = canonical_json(scenario_to_journal_dict(scenario))
    return blake2b(payload.encode("utf-8"), digest_size=16).hexdigest()


def _match_started(events: Sequence[Event], *, match_id: str) -> MatchStarted:
    """Return the ``MatchStarted`` of a journal, which is always its first event.

    Args:
        events: The journal, in ``seq`` order.
        match_id: For the error message.

    Returns:
        The event.

    Raises:
        ResumeError: If the journal holds none.
    """
    for event in events:
        if isinstance(event, MatchStarted):
            return event
    raise ResumeError("a mirrored journal has no MatchStarted", match_id=match_id)


def _match_ended(events: Sequence[Event], *, match_id: str) -> MatchEnded:
    """Return the ``MatchEnded`` of a journal, which is always its last event.

    Args:
        events: The journal, in ``seq`` order.
        match_id: For the error message.

    Returns:
        The event.

    Raises:
        ResumeError: If the journal holds none, that is if the match was
            interrupted. Folding an unfinished match into the ratings is exactly
            the double counting resume must not do: the match is replayed
            instead, which is what the missing ``match`` row already asks for.
    """
    for event in reversed(events):
        if isinstance(event, MatchEnded):
            return event
    raise ResumeError("a mirrored journal has no MatchEnded", match_id=match_id)
