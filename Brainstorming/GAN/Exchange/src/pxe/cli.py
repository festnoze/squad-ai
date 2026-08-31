"""The Prediction Exchange command line (A23, CONTRACTS section 7.22).

This is the product's front door and the only module besides
:mod:`pxe.tournament.orchestrator` that parses TOML or reads ``sys.argv``
(section 2.6). It is also the only place that configures logging handlers
(section 2.5) and, together with the orchestrator, the only place that builds
an :class:`~pxe.rng.RngTree` for a match (section 3.1).

Every verb of section 7.22 is here::

    pxe match run            run one match, scripted or LLM
    pxe match verify         run the same seed N times, compare hashes (AC-P1)
    pxe match replay         replay a journal and print the projected metrics
    pxe tournament run       run a tournament from a TOML config
    pxe tournament resume    idempotent resume
    pxe report build         build the MD/HTML report of a tournament
    pxe api serve            start the replay API
    pxe api openapi          write docs/REPLAY_API.md, optionally the fixtures
    pxe schema dump          print a versioned schema
    pxe world stats          run the FR-5.2.2 frequency test
    pxe mm study             measure the cost of liquidity (T2.6)
    pxe store init           create the schema
    pxe store rebuild        re import every projection table from the journals
    pxe integrity scan       run the detectors offline and write incidents.jsonl

Exit codes, exactly as section 7.22 states them: ``0`` success, ``1`` user
error, ``2`` determinism failure, ``3`` budget exceeded, ``4`` invariant
violation.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import uvicorn

from pxe import __version__
from pxe.agents.base import make_baseline
from pxe.api.app import create_app, render_replay_api_markdown, write_sample_fixtures
from pxe.errors import BudgetExceededError, DeterminismError, InvariantViolationError, PxeError
from pxe.events import JOURNAL_ENCODING, JOURNAL_NEWLINE, Event, MatchEnded, MatchStarted
from pxe.gateway.budget import BudgetTracker
from pxe.gateway.claude_cli import ClaudeCliGateway
from pxe.gateway.protocol import AgentGateway
from pxe.gateway.scripted import CompositeGateway, ScriptedGateway
from pxe.info.profiles import build_profile, default_profile_kinds
from pxe.integrity.detectors import run_detectors, write_incidents
from pxe.journal import Journal, read_journal, verify_journal
from pxe.metrics.aggregate import compute_all, write_metrics
from pxe.metrics.projection import project
from pxe.mm.profiles import build_liquidity_study, render_liquidity_study
from pxe.rng import RngTree
from pxe.runner.match_runner import MatchRunner, run_match
from pxe.runner.replay import replay_journal
from pxe.runner.schema_registry import load_schema
from pxe.store.db import Store, default_store_url
from pxe.store.files import artefact_paths, match_dir
from pxe.tournament.heldout import HeldoutBank
from pxe.tournament.orchestrator import (
    TournamentOrchestrator,
    background_harness,
    load_tournament_config,
)
from pxe.tournament.report import write_report
from pxe.types import (
    LIQUIDITY_PROFILES,
    AgentSpec,
    GatewayConfig,
    HarnessConfig,
    InfoProfileKind,
    LiquidityProfileName,
    MatchConfig,
    MatchRanking,
    MatchResult,
    ScenarioSpec,
    TournamentResult,
    config_from_journal_dict,
    liquidity_profile,
    make_agent_id,
    market_spec_from_dict,
)
from pxe.world.generator import World, generate_world, list_templates, outcome_frequency

__all__ = [
    "EXIT_OK",
    "EXIT_USER_ERROR",
    "EXIT_DETERMINISM",
    "EXIT_BUDGET",
    "EXIT_INVARIANT",
    "DEFAULT_AGENTS",
    "main",
]

#: Success.
EXIT_OK = 0

#: The operator asked for something impossible: an unknown template, a bad
#: flag, a missing file, an LLM harness handed to ``match verify``.
EXIT_USER_ERROR = 1

#: Two runs of the same seed produced two journal hashes, or a journal failed
#: its own replay. Never used for a usage error, which is why argparse's own
#: exit code is remapped: a wrong flag must not look like a broken engine.
EXIT_DETERMINISM = 2

#: A provider budget cap was reached (FR-6.2.3).
EXIT_BUDGET = 3

#: A closed system invariant of section 6 was breached. This is an engine bug.
EXIT_INVARIANT = 4

#: Default seat list of ``pxe match run``: six scripted baselines, which is the
#: PRD section 5.7 seat count, one of each behaviour so a default match is not
#: six copies of the same policy.
DEFAULT_AGENTS: tuple[str, ...] = (
    "fundamentalist",
    "momentum",
    "noise",
    "zero_intelligence",
    "bayesian",
    "mute",
)

#: Version of the harness a ``--llm-model`` seat is given. The model id and the
#: system prompt go into the config hash, so two different prompts still get
#: two different harness keys (section 2.2).
_CLI_LLM_HARNESS_VERSION = "cli-1"

#: System prompt of a ``--llm-model`` seat when the operator gives none.
_DEFAULT_SYSTEM_PROMPT = "You are a disciplined prediction market trader."

#: How many matches ``Store.list_matches`` returns when a report rebuilds a
#: tournament result from the store. A nightly round robin is 252 matches
#: (configs/nightly_round_robin.toml), so the page has to be larger than that.
_MATCH_PAGE = 10_000

_LOG = logging.getLogger("pxe.cli")


class _UsageError(Exception):
    """Raised instead of argparse's own ``SystemExit(2)``.

    Section 7.22 reserves exit code ``2`` for a determinism failure, so a bad
    flag must not produce it. The parser below raises this instead and
    :func:`main` turns it into :data:`EXIT_USER_ERROR`.
    """


class _CliParser(argparse.ArgumentParser):
    """An :class:`argparse.ArgumentParser` that never exits with code 2."""

    def error(self, message: str) -> Any:
        """Raise :class:`_UsageError` instead of exiting.

        Args:
            message: The parser's own message.

        Raises:
            _UsageError: Always.
        """
        raise _UsageError(message)


# --------------------------------------------------------------------------
# Shared helpers
# --------------------------------------------------------------------------
def _configure_logging(*, verbose: bool, quiet: bool) -> None:
    """Install the one logging handler of the process (section 2.5).

    Args:
        verbose: Log at ``DEBUG``.
        quiet: Log at ``ERROR``.
    """
    level = logging.DEBUG if verbose else (logging.ERROR if quiet else logging.INFO)
    logging.basicConfig(level=level, format="%(levelname)s %(name)s %(message)s", stream=sys.stderr)


def _emit(payload: Mapping[str, Any], *, as_json: bool, lines: Sequence[str]) -> None:
    """Print either the machine readable payload or the human readable lines.

    Args:
        payload: What ``--json`` prints, as one object on one line.
        as_json: True when ``--json`` was given.
        lines: The human readable rendering.
    """
    if as_json:
        print(json.dumps(payload, sort_keys=True, ensure_ascii=False))
        return
    for line in lines:
        print(line)


def _store_for(args: argparse.Namespace) -> Store:
    """Build the projection database the verb will write into.

    Args:
        args: Parsed arguments carrying ``runs_dir`` and ``db_url``.

    Returns:
        An initialised :class:`~pxe.store.db.Store`.
    """
    runs_dir = Path(args.runs_dir)
    runs_dir.mkdir(parents=True, exist_ok=True)
    url = args.db_url if getattr(args, "db_url", None) else default_store_url(runs_dir)
    store = Store(url=url, runs_dir=runs_dir)
    store.init_schema()
    return store


def _profile_of(name: str) -> LiquidityProfileName:
    """Turn a ``--liquidity`` string into its enum member.

    Args:
        name: One of the three preset names.

    Returns:
        The member.

    Raises:
        _UsageError: If the name is not a preset.
    """
    try:
        return LiquidityProfileName(name)
    except ValueError as exc:
        known = ", ".join(str(member) for member in LiquidityProfileName)
        raise _UsageError(f"unknown liquidity profile {name!r}, known: {known}") from exc


def _seat_names(args: argparse.Namespace) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Split the seat list into scripted baseline names and LLM model ids.

    Args:
        args: Parsed arguments carrying ``agents`` and ``llm_model``.

    Returns:
        ``(scripted names, llm model ids)`` in seat order, scripted first.
    """
    return _baseline_names(args), tuple(str(model) for model in (args.llm_model or ()))


def _baseline_names(args: argparse.Namespace) -> tuple[str, ...]:
    """Parse the comma separated ``--agents`` list into baseline names.

    Args:
        args: Parsed arguments carrying ``agents``.

    Returns:
        The names, in seat order, blanks dropped.
    """
    return tuple(part.strip() for part in str(args.agents).split(",") if part.strip())


def _harness_for_model(model: str, system_prompt: str) -> HarnessConfig:
    """Build the harness of one ``--llm-model`` seat.

    Args:
        model: Provider model id.
        system_prompt: The prompt handed to it.

    Returns:
        An ``llm`` kind harness. Its ``config_hash`` is filled by
        ``HarnessConfig.__post_init__``, so two prompts never share a key.
    """
    return HarnessConfig(
        harness_id=model,
        version=_CLI_LLM_HARNESS_VERSION,
        kind="llm",
        model=model,
        system_prompt=system_prompt,
    )


def _specs_for(
    *, scripted: Sequence[str], llm_models: Sequence[str], world: World, system_prompt: str
) -> tuple[AgentSpec, ...]:
    """Build one :class:`~pxe.types.AgentSpec` per seat, ascending.

    Profiles come from :func:`pxe.info.profiles.default_profile_kinds`, that is
    the same declaration order vector the Latin square rotates (section 7.19),
    and a specialist watches ``market_ids[seat_index % n_markets]`` exactly as
    the orchestrator spreads them.

    Args:
        scripted: Baseline names, in seat order.
        llm_models: Model ids of the LLM seats, after the scripted ones.
        world: The generated world, for the market ids.
        system_prompt: System prompt of every LLM seat.

    Returns:
        The seats.

    Raises:
        _UsageError: If a baseline name is unknown.
    """
    market_ids = world.market_ids()
    harnesses: list[HarnessConfig] = []
    for name in scripted:
        try:
            harnesses.append(background_harness(name))
        except PxeError as exc:
            raise _UsageError(f"unknown baseline {name!r}: {exc}") from exc
    harnesses.extend(_harness_for_model(model, system_prompt) for model in llm_models)
    kinds = default_profile_kinds(len(harnesses))
    specs: list[AgentSpec] = []
    for index, harness in enumerate(harnesses):
        kind = kinds[index]
        focus = market_ids[index % len(market_ids)] if kind is InfoProfileKind.SPECIALIST else None
        specs.append(
            AgentSpec(
                agent_id=make_agent_id(index + 1),
                harness=harness,
                info_profile=build_profile(kind, market_ids=market_ids, focus_market_id=focus),
            )
        )
    return tuple(specs)


def _scripted_gateway(specs: Sequence[AgentSpec], *, config: MatchConfig, rng: RngTree) -> ScriptedGateway:
    """Build the gateway of the scripted seats, each on its own substream.

    Args:
        specs: The scripted seats only.
        config: The match configuration.
        rng: The match root tree.

    Returns:
        The gateway.
    """
    agents = {
        spec.agent_id: make_baseline(
            spec.harness.harness_id,
            agent_id=spec.agent_id,
            config=config,
            rng=rng.child(f"agent/{spec.agent_id}").substream(f"agent.{spec.agent_id}"),
        )
        for spec in specs
    }
    return ScriptedGateway(agents=agents)


def _gateway_for(
    specs: Sequence[AgentSpec],
    *,
    config: MatchConfig,
    rng: RngTree,
    gateway_config: GatewayConfig,
    trace_path: Path,
) -> AgentGateway:
    """Build the gateway of a possibly mixed table.

    Args:
        specs: Every seat of the match.
        config: The match configuration.
        rng: The match root tree.
        gateway_config: Timeouts, retries and budgets. Never journalled.
        trace_path: Destination of ``llm_trace.jsonl``.

    Returns:
        A :class:`~pxe.gateway.scripted.ScriptedGateway`, a
        :class:`~pxe.gateway.claude_cli.ClaudeCliGateway` or a
        :class:`~pxe.gateway.scripted.CompositeGateway` over both.
    """
    scripted = tuple(spec for spec in specs if spec.harness.kind == "scripted")
    llm = tuple(spec for spec in specs if spec.harness.kind == "llm")
    table: list[tuple[tuple[str, ...], AgentGateway]] = []
    if scripted:
        table.append((tuple(spec.agent_id for spec in scripted), _scripted_gateway(scripted, config=config, rng=rng)))
    if llm:
        table.append(
            (
                tuple(spec.agent_id for spec in llm),
                ClaudeCliGateway(
                    harnesses={spec.agent_id: spec.harness for spec in llm},
                    gateway_config=gateway_config,
                    budget=BudgetTracker(gateway_config),
                    trace_path=trace_path,
                ),
            )
        )
    if not table:
        raise _UsageError("a match needs at least one seat")
    return table[0][1] if len(table) == 1 else CompositeGateway(gateways=table)


def _match_config(args: argparse.Namespace, *, n_agents: int) -> MatchConfig:
    """Build the authoritative :class:`~pxe.types.MatchConfig` of a run.

    Args:
        args: Parsed arguments.
        n_agents: Number of seats actually built.

    Returns:
        The configuration.

    Raises:
        _UsageError: If a value is outside the range the dataclass allows.
    """
    profile = _profile_of(args.liquidity)
    try:
        return MatchConfig(
            seed=int(args.seed),
            ticks_total=int(args.ticks),
            n_agents=n_agents,
            n_markets=int(args.markets),
            taker_fee_bps=int(args.taker_fee_bps),
            talking_mode=bool(args.talking),
            mm=liquidity_profile(profile).mm,
            liquidity_profile_name=profile,
        )
    except PxeError as exc:
        raise _UsageError(str(exc)) from exc


def _match_id_of(args: argparse.Namespace) -> str:
    """Return the match id of a standalone run.

    Args:
        args: Parsed arguments.

    Returns:
        ``--match-id`` when given, else the ``m-<template>-<seed>-01`` of
        section 2.2, which is what :func:`pxe.runner.match_runner.run_match`
        would derive on its own.
    """
    if args.match_id:
        return str(args.match_id)
    return f"m-{args.template}-{int(args.seed)}-01"


def _world_for(args: argparse.Namespace) -> World:
    """Generate the world of a standalone run.

    Args:
        args: Parsed arguments.

    Returns:
        The world.

    Raises:
        _UsageError: If the template is unknown or an argument is out of range.
    """
    try:
        return generate_world(
            template_id=str(args.template),
            seed=int(args.seed),
            ticks_total=int(args.ticks),
            n_markets=int(args.markets),
            liquidity=_profile_of(args.liquidity),
            talking_mode=bool(args.talking),
        )
    except PxeError as exc:
        known = ", ".join(list_templates())
        raise _UsageError(f"{exc} (known templates: {known})") from exc


# --------------------------------------------------------------------------
# pxe match
# --------------------------------------------------------------------------
def _cmd_match_run(args: argparse.Namespace) -> int:
    """Run one match, scripted or LLM, and write its artefacts.

    Args:
        args: Parsed arguments.

    Returns:
        :data:`EXIT_OK`.
    """
    scripted, llm_models = _seat_names(args)
    world = _world_for(args)
    specs = _specs_for(scripted=scripted, llm_models=llm_models, world=world, system_prompt=str(args.system_prompt))
    config = _match_config(args, n_agents=len(specs))
    match_id = _match_id_of(args)
    runs_dir = Path(args.runs_dir)
    out_dir = match_dir(runs_dir, match_id)
    paths = artefact_paths(runs_dir, match_id)
    gateway_config = GatewayConfig(
        timeout_s=float(args.timeout_s),
        max_budget_usd_per_match=float(args.max_budget_usd),
        trace_dir=str(out_dir),
    )
    rng = RngTree(config.seed)
    gateway = _gateway_for(specs, config=config, rng=rng, gateway_config=gateway_config, trace_path=paths["llm_trace"])
    try:
        result = run_match(
            config=config,
            world=world,
            agents=specs,
            gateway=gateway,
            out_dir=out_dir,
            rng=rng,
            match_id=match_id,
        )
    finally:
        gateway.close()

    events = read_journal(Path(result.journal_path))
    projection = project(events)
    metrics = compute_all(projection)
    write_metrics(paths["metrics"], metrics)
    if not args.no_store:
        with _store_for(args) as store:
            store.save_match(result, projection, metrics)
    _emit(
        {
            "match_id": result.match_id,
            "seed": result.seed,
            "journal_path": result.journal_path,
            "journal_hash": result.journal_hash,
            "event_count": result.event_count,
            "mm_pnl_cents": result.mm_pnl_cents,
            "fees_collected_cents": result.fees_collected_cents,
            "rankings": [
                {"rank": row.rank, "agent_id": row.agent_id, "pnl_cents": row.pnl_cents} for row in result.rankings
            ],
        },
        as_json=bool(args.json),
        lines=[
            f"match {result.match_id} finished in {result.event_count} events",
            f"journal {result.journal_path}",
            f"journal_hash {result.journal_hash}",
            f"mm_pnl_cents {result.mm_pnl_cents}  fees_collected_cents {result.fees_collected_cents}",
            *(
                f"  #{row.rank} {row.agent_id} pnl_cents {row.pnl_cents} ({row.pnl_pct_bps} bps)"
                for row in result.rankings
            ),
        ],
    )
    return EXIT_OK


def _verify_child_argv(args: argparse.Namespace, *, runs_dir: Path) -> list[str]:
    """Build the command line of one ``match verify`` child process.

    Args:
        args: Parsed arguments of the parent.
        runs_dir: This child's own runs root, so two children never share a
            journal path.

    Returns:
        The argv, running this very interpreter through ``-m pxe.cli``.
    """
    return [
        sys.executable,
        "-m",
        "pxe.cli",
        "--quiet",
        "match",
        "run",
        "--template",
        str(args.template),
        "--seed",
        str(int(args.seed)),
        "--ticks",
        str(int(args.ticks)),
        "--markets",
        str(int(args.markets)),
        "--agents",
        str(args.agents),
        "--liquidity",
        str(args.liquidity),
        "--taker-fee-bps",
        str(int(args.taker_fee_bps)),
        "--runs-dir",
        str(runs_dir),
        "--no-store",
        "--json",
    ]


def _run_verify_child(args: argparse.Namespace, *, index: int, runs_dir: Path) -> str:
    """Run one child process and return the journal hash it printed.

    The child gets a **different** ``PYTHONHASHSEED`` on every index, and none
    at all on index ``0``: section 3.6 asks for exactly that, because a seeded
    interpreter hash is the classic way a "deterministic" engine turns out to
    depend on dictionary iteration order.

    Args:
        args: Parsed arguments of the parent.
        index: Which repetition this is.
        runs_dir: This child's own runs root.

    Returns:
        The ``journal_hash`` field of the child's JSON output.

    Raises:
        _UsageError: If the child failed or printed something unreadable.
    """
    env = dict(os.environ)
    env.pop("PYTHONHASHSEED", None)
    if index > 0:
        env["PYTHONHASHSEED"] = str(index)
    completed = subprocess.run(  # noqa: S603 - argv is built above, never from user text
        _verify_child_argv(args, runs_dir=runs_dir),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    if completed.returncode != EXIT_OK:
        raise _UsageError(f"verification run {index} failed: {completed.stderr.strip()[:400]}")
    for line in reversed(completed.stdout.splitlines()):
        if line.startswith("{"):
            return str(json.loads(line)["journal_hash"])
    raise _UsageError(f"verification run {index} printed no result")


def _cmd_match_verify(args: argparse.Namespace) -> int:
    """AC-P1: run the same seed N times in fresh processes and compare hashes.

    Args:
        args: Parsed arguments.

    Returns:
        :data:`EXIT_OK` when every hash agrees, :data:`EXIT_DETERMINISM` when
        they do not.

    Raises:
        _UsageError: If ``--repeat`` is below two, or if the table holds an LLM
            harness. Section 3.7 is explicit: AC-P1 is a claim about scripted
            matches, and this verb refuses rather than reporting a spurious
            failure (exit code ``1``, not ``2``).
    """
    if int(args.repeat) < 2:
        raise _UsageError("--repeat must be at least 2: one run compares with nothing")
    if args.llm_model:
        raise _UsageError(
            "match verify refuses an LLM harness: AC-P1 is a claim about scripted matches (CONTRACTS section 3.7)"
        )
    hashes: list[str] = []
    with tempfile.TemporaryDirectory(prefix="pxe-verify-") as scratch:
        for index in range(int(args.repeat)):
            hashes.append(_run_verify_child(args, index=index, runs_dir=Path(scratch) / f"run{index}"))
    identical = len(set(hashes)) == 1
    _emit(
        {"identical": identical, "repeat": len(hashes), "hashes": hashes},
        as_json=bool(args.json),
        lines=[
            *(f"run {index}: {value}" for index, value in enumerate(hashes)),
            "identical" if identical else "DIFFERENT: the journal is not a function of the seed",
        ],
    )
    return EXIT_OK if identical else EXIT_DETERMINISM


def _cmd_match_replay(args: argparse.Namespace) -> int:
    """Replay a journal and print the projected metrics.

    Args:
        args: Parsed arguments.

    Returns:
        :data:`EXIT_OK`.

    Raises:
        _UsageError: If the file does not exist.
    """
    path = Path(args.journal)
    if not path.is_file():
        raise _UsageError(f"no such journal: {path}")
    events = read_journal(path)
    verify_journal(events)
    state = replay_journal(events)
    projection = project(events)
    metrics = compute_all(projection)
    rows = [
        {
            "agent_id": row.agent_id,
            "pnl_cents": row.pnl_cents,
            "pnl_bps": row.pnl_bps,
            "sharpe_milli": row.sharpe_milli,
            "max_drawdown_bps": row.max_drawdown_bps,
            "trade_count": row.trade_count,
            "brier_ppm": brier.brier_ppm,
            "n_terms": brier.n_terms,
        }
        for row, brier in zip(metrics.performance, metrics.calibration, strict=True)
    ]
    _emit(
        {
            "match_id": metrics.match_id,
            "ticks_total": projection.ticks_total,
            "event_count": len(events),
            "final_tick": state.tick,
            "mm_pnl_cents": metrics.mm_pnl_cents,
            "fees_collected_cents": metrics.fees_collected_cents,
            "agents": rows,
        },
        as_json=bool(args.json),
        lines=[
            f"match {metrics.match_id}: {len(events)} events over {projection.ticks_total} ticks",
            f"mm_pnl_cents {metrics.mm_pnl_cents}  fees_collected_cents {metrics.fees_collected_cents}",
            "agent      pnl_cents   pnl_bps  sharpe  drawdown_bps  trades  brier_ppm  n_terms",
            *(
                f"{row['agent_id']:<10} {row['pnl_cents']:>9} {row['pnl_bps']:>9} "
                f"{row['sharpe_milli']:>7} {row['max_drawdown_bps']:>13} {row['trade_count']:>7} "
                f"{row['brier_ppm']:>10} {row['n_terms']:>8}"
                for row in rows
            ),
        ],
    )
    return EXIT_OK


# --------------------------------------------------------------------------
# pxe tournament and pxe report
# --------------------------------------------------------------------------
def _tournament_lines(result: TournamentResult) -> list[str]:
    """Render a finished tournament for a terminal.

    Args:
        result: The result.

    Returns:
        The lines.
    """
    return [
        f"tournament {result.tournament_id}: {len(result.match_results)} matches, {result.total_cost_usd:.4f} USD",
        f"report {result.report_path}",
        *(
            f"  #{index} {record.harness_key} mu {record.mu:.3f} sigma {record.sigma:.3f} ({record.matches} matches)"
            for index, record in enumerate(result.ratings, start=1)
        ),
    ]


def _heldout_bank(args: argparse.Namespace, *, template_ids: Sequence[str], base_seed: int) -> HeldoutBank | None:
    """Build the sealed seed bank of a held-out evaluation run (T3.5, AC-P5).

    ``--heldout-bank`` is how the front door reaches the sealed set at all: the
    orchestrator takes the bank as a keyword argument and nothing else in the
    product constructs one. ``--heldout-reserve`` seals that many seeds per
    template first, which is a deliberate operator act and never implicit: a
    bank that silently sealed itself on first use would make "the seeds were
    never seen during training" unverifiable.

    Args:
        args: Parsed arguments.
        template_ids: The templates the tournament plays.
        base_seed: Root seed of the reservation derivation.

    Returns:
        The bank, or ``None`` when ``--heldout-bank`` was not given.
    """
    if not args.heldout_bank:
        return None
    path = Path(args.heldout_bank)
    bank = HeldoutBank(path=path, access_log=path.with_name(path.stem + "_access.jsonl"))
    reserve = int(args.heldout_reserve)
    if reserve > 0:
        for template_id in template_ids:
            bank.reserve(template_id=template_id, count=reserve, base_seed=base_seed)
    return bank


def _run_tournament(args: argparse.Namespace, *, resume: bool) -> int:
    """Run or resume a tournament from a TOML preset.

    Args:
        args: Parsed arguments.
        resume: True for ``pxe tournament resume``.

    Returns:
        :data:`EXIT_OK`.

    Raises:
        _UsageError: If the preset does not exist.
    """
    path = Path(args.config)
    if not path.is_file():
        raise _UsageError(f"no such tournament config: {path}")
    config = load_tournament_config(path)
    bank = _heldout_bank(args, template_ids=config.template_ids, base_seed=config.seeds[0])
    with _store_for(args) as store:
        orchestrator = TournamentOrchestrator(config=config, store=store, heldout=bank)
        result = orchestrator.resume() if resume else orchestrator.run(max_workers=int(args.max_workers))
    _emit(
        {
            "tournament_id": result.tournament_id,
            "matches": len(result.match_results),
            "total_cost_usd": result.total_cost_usd,
            "report_path": result.report_path,
            "ratings": [
                {"harness_key": row.harness_key, "mu": row.mu, "sigma": row.sigma, "matches": row.matches}
                for row in result.ratings
            ],
        },
        as_json=bool(args.json),
        lines=_tournament_lines(result),
    )
    return EXIT_OK


def _cmd_tournament_run(args: argparse.Namespace) -> int:
    """Run a tournament from a TOML config.

    Args:
        args: Parsed arguments.

    Returns:
        :data:`EXIT_OK`.
    """
    return _run_tournament(args, resume=False)


def _cmd_tournament_resume(args: argparse.Namespace) -> int:
    """Resume an interrupted tournament, idempotently.

    Args:
        args: Parsed arguments.

    Returns:
        :data:`EXIT_OK`.
    """
    return _run_tournament(args, resume=True)


def _scenario_of(started: MatchStarted, *, held_out: bool) -> ScenarioSpec:
    """Rebuild the scenario of a finished match from its journal.

    ``report.py`` only reads ``held_out`` and ``liquidity_profile_name`` off
    the scenario, and both are in the journal: the flag comes from the store's
    ``match_task`` row and the preset name from ``MatchStarted.config``. The
    correlations and the scripted cancellations are **not** rebuilt, because no
    event carries them and the report does not read them.

    Args:
        started: The first event of the journal.
        held_out: What the store's task row says about this match.

    Returns:
        The reconstructed spec.
    """
    config = config_from_journal_dict(started.config)
    return ScenarioSpec(
        template_id=started.scenario_template_id,
        template_version=started.scenario_template_version,
        seed=int(started.seed),
        ticks_total=int(started.ticks_total),
        markets=tuple(market_spec_from_dict(entry) for entry in started.markets),
        talking_mode=config.talking_mode,
        liquidity_profile_name=config.liquidity_profile_name,
        held_out=bool(held_out),
    )


def _match_result_of(row: Mapping[str, Any], events: Sequence[Event]) -> MatchResult:
    """Rebuild one :class:`~pxe.types.MatchResult` from the store and a journal.

    Args:
        row: One ``Store.list_matches`` mapping.
        events: The journal of that match.

    Returns:
        The reconstructed result.

    Raises:
        _UsageError: If the journal holds no ``MatchStarted``.
    """
    started = next((event for event in events if isinstance(event, MatchStarted)), None)
    if started is None:
        raise _UsageError(f"journal of {row['match_id']} holds no match_started event")
    ended = next((event for event in reversed(events) if isinstance(event, MatchEnded)), None)
    rankings = tuple(MatchRanking(**entry) for entry in (() if ended is None else ended.rankings))
    return MatchResult(
        match_id=str(row["match_id"]),
        seed=int(row["seed"]),
        scenario=_scenario_of(started, held_out=bool(row["held_out"])),
        rankings=rankings,
        journal_path=str(row["journal_path"]),
        journal_hash=str(row["journal_hash"]),
        event_count=int(row["event_count"]),
        mm_pnl_cents=int(row["mm_pnl_cents"]),
        fees_collected_cents=int(row["fees_collected_cents"]),
    )


def _tournament_result_from_store(store: Store, tournament_id: str, *, out_dir: Path) -> TournamentResult:
    """Rebuild a :class:`~pxe.types.TournamentResult` from the store alone.

    ``pxe report build`` is run after the fact, often in another process, so it
    cannot be handed the object the orchestrator returned. Everything it needs
    is a projection: the match rows and their journals, the ``rating_record``
    table and the per harness costs.

    Args:
        store: The projection database.
        tournament_id: The tournament to rebuild.
        out_dir: Where the report will be written.

    Returns:
        The reconstructed result.

    Raises:
        _UsageError: If the tournament has no saved match.
    """
    rows = store.list_matches(tournament_id=tournament_id, limit=_MATCH_PAGE)
    if not rows:
        raise _UsageError(f"tournament {tournament_id!r} has no saved match: nothing to report")
    results = tuple(_match_result_of(row, store.load_journal(str(row["match_id"]))) for row in rows)
    return TournamentResult(
        tournament_id=tournament_id,
        match_results=results,
        ratings=store.load_ratings(tournament_id),
        total_cost_usd=sum(cost for _key, cost in store.load_costs_usd(tournament_id)),
        report_path=str(out_dir / "report.md"),
    )


def _scan_match(store: Store, *, match_id: str, runs_dir: Path) -> int:
    """Run the offline detectors over one match and persist what they found.

    Args:
        store: The projection database.
        match_id: The match to scan.
        runs_dir: The runs root.

    Returns:
        The number of incidents raised.
    """
    events = store.load_journal(match_id)
    incidents = run_detectors(project(events))
    write_incidents(artefact_paths(runs_dir, match_id)["incidents"], incidents)
    if store.has_match(match_id):
        store.save_incidents(match_id, incidents)
    return len(incidents)


def _cmd_report_build(args: argparse.Namespace) -> int:
    """Build the Markdown and HTML report of a tournament (T3.6, AC-P3, AC-P5).

    The detectors run first unless ``--no-scan`` is given, which is what makes
    the ``incident`` table the report reads a current one: section 7.20 names
    ``pxe report build`` as one of the two callers of ``save_incidents``.

    Args:
        args: Parsed arguments.

    Returns:
        :data:`EXIT_OK`.
    """
    runs_dir = Path(args.runs_dir)
    with _store_for(args) as store:
        out_dir = Path(args.out) if args.out else runs_dir / str(args.tournament_id)
        result = _tournament_result_from_store(store, str(args.tournament_id), out_dir=out_dir)
        scanned = 0
        if not args.no_scan:
            for item in result.match_results:
                scanned += _scan_match(store, match_id=item.match_id, runs_dir=runs_dir)
        markdown, html_path = write_report(result=result, store=store, out_dir=out_dir)
    heldout_dir = out_dir / "heldout"
    _emit(
        {
            "tournament_id": result.tournament_id,
            "matches": len(result.match_results),
            "incidents": scanned,
            "markdown": str(markdown),
            "html": str(html_path),
            "heldout_markdown": str(heldout_dir / "report.md"),
            "heldout_html": str(heldout_dir / "report.html"),
        },
        as_json=bool(args.json),
        lines=[
            f"report {markdown}",
            f"report {html_path}",
            f"held-out report {heldout_dir / 'report.md'}",
            f"held-out report {heldout_dir / 'report.html'}",
            f"{scanned} integrity incident(s) over {len(result.match_results)} match(es)",
        ],
    )
    return EXIT_OK


# --------------------------------------------------------------------------
# pxe api, pxe schema, pxe world, pxe mm, pxe store, pxe integrity
# --------------------------------------------------------------------------
def _cmd_api_serve(args: argparse.Namespace) -> int:
    """Start the read only replay API.

    Args:
        args: Parsed arguments.

    Returns:
        :data:`EXIT_OK` once the server stops.
    """
    runs_dir = Path(args.runs_dir)
    runs_dir.mkdir(parents=True, exist_ok=True)
    origins = tuple(str(value) for value in (args.cors_origin or ()))
    app = create_app(runs_dir=runs_dir, cors_origins=origins) if origins else create_app(runs_dir=runs_dir)
    uvicorn.run(app, host=str(args.host), port=int(args.port), log_level="info")
    return EXIT_OK


def _cmd_api_openapi(args: argparse.Namespace) -> int:
    """Write ``docs/REPLAY_API.md`` and, with ``--samples``, the UI fixtures.

    Args:
        args: Parsed arguments.

    Returns:
        :data:`EXIT_OK`.

    Raises:
        _UsageError: If ``--samples`` is given without a ``--match-id``.
    """
    runs_dir = Path(args.runs_dir)
    runs_dir.mkdir(parents=True, exist_ok=True)
    app = create_app(runs_dir=runs_dir)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding=JOURNAL_ENCODING, newline=JOURNAL_NEWLINE) as handle:
        handle.write(render_replay_api_markdown(app))
    written: list[str] = []
    if args.samples:
        if not args.match_id:
            raise _UsageError("--samples needs --match-id: the fixtures are sampled from a real recorded match")
        written = [
            str(path)
            for path in write_sample_fixtures(
                app,
                match_id=str(args.match_id),
                out_dir=Path(args.fixtures_dir),
                tournament_id=str(args.tournament_id) if args.tournament_id else None,
            )
        ]
    _emit(
        {"document": str(out), "fixtures": written},
        as_json=bool(args.json),
        lines=[f"wrote {out}", *(f"wrote {path}" for path in written)],
    )
    return EXIT_OK


def _cmd_schema_dump(args: argparse.Namespace) -> int:
    """Print one versioned JSON schema.

    Args:
        args: Parsed arguments.

    Returns:
        :data:`EXIT_OK`.

    ``observation`` and ``action`` are accepted as shorthands for the current
    major version, ``observation.v1`` and ``action.v1``, because section 7.22
    spells the verb ``pxe schema dump <name>`` and an operator should not have
    to know the file naming to read a schema.

    Raises:
        _UsageError: If the schema name is unknown.
    """
    name = str(args.name)
    resolved = name if "." in name else f"{name}.v1"
    try:
        schema = load_schema(resolved)
    except PxeError as exc:
        raise _UsageError(str(exc)) from exc
    print(json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False))
    return EXIT_OK


def _cmd_world_stats(args: argparse.Namespace) -> int:
    """Run the FR-5.2.2 outcome frequency test of one template.

    Args:
        args: Parsed arguments.

    Returns:
        :data:`EXIT_OK`.

    Raises:
        _UsageError: If the template is unknown or an argument is out of range.
    """
    try:
        frequency = outcome_frequency(
            str(args.template),
            draws=int(args.draws),
            base_seed=int(args.base_seed),
            n_markets=int(args.markets),
        )
    except PxeError as exc:
        known = ", ".join(list_templates())
        raise _UsageError(f"{exc} (known templates: {known})") from exc
    _emit(
        {"template_id": str(args.template), "draws": int(args.draws), "yes_frequency_ppm": dict(frequency)},
        as_json=bool(args.json),
        lines=[
            f"{args.template}: {args.draws} draws from seed {args.base_seed}",
            *(f"  {market_id} yes {value} ppm" for market_id, value in frequency.items()),
        ],
    )
    return EXIT_OK


def _study_journal(args: argparse.Namespace, *, profile: LiquidityProfileName, index: int) -> tuple[Event, ...]:
    """Play one study match of one preset and return its journal, in memory.

    The journal is not written to disk: a two hundred match study per preset
    would leave six hundred directories behind, and
    :func:`pxe.mm.profiles.liquidity_cost_row` reads events, not files.

    Args:
        args: Parsed arguments.
        profile: The preset to measure.
        index: Which match of the study this is; it offsets the seed.

    Returns:
        The events of the finished match.
    """
    seed = int(args.seed) + index
    world = generate_world(
        template_id=str(args.template),
        seed=seed,
        ticks_total=int(args.ticks),
        n_markets=int(args.markets),
        liquidity=profile,
    )
    specs = _specs_for(scripted=_baseline_names(args), llm_models=(), world=world, system_prompt="")
    config = MatchConfig(
        seed=seed,
        ticks_total=int(args.ticks),
        n_agents=len(specs),
        n_markets=int(args.markets),
        mm=liquidity_profile(profile).mm,
        liquidity_profile_name=profile,
    )
    rng = RngTree(seed)
    gateway = _scripted_gateway(specs, config=config, rng=rng)
    journal = Journal(f"m-{args.template}-{seed}-01")
    try:
        MatchRunner(
            config=config,
            world=world,
            agents=specs,
            gateway=gateway,
            journal=journal,
            match_id=journal.match_id,
            rng=rng,
        ).run()
        return journal.events
    finally:
        gateway.close()
        journal.close()


def _cmd_mm_study(args: argparse.Namespace) -> int:
    """Measure the cost of liquidity and write the T2.6 document.

    Args:
        args: Parsed arguments.

    Returns:
        :data:`EXIT_OK`.

    Raises:
        _UsageError: If ``--matches`` is below one.
    """
    if int(args.matches) < 1:
        raise _UsageError("--matches must be at least 1")
    names = (
        tuple(LiquidityProfileName(str(profile.name)) for profile in LIQUIDITY_PROFILES)
        if str(args.profile) == "all"
        else (_profile_of(str(args.profile)),)
    )
    journals = {
        str(profile): [_study_journal(args, profile=profile, index=index) for index in range(int(args.matches))]
        for profile in names
    }
    study = build_liquidity_study(
        seed=int(args.seed),
        ticks_total=int(args.ticks),
        n_markets=int(args.markets),
        n_agents=len(_baseline_names(args)),
        journals_by_profile=journals,
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding=JOURNAL_ENCODING, newline=JOURNAL_NEWLINE) as handle:
        handle.write(render_liquidity_study(study))
    _emit(
        {
            "document": str(out),
            "matches_per_profile": int(args.matches),
            "rows": [
                {"profile_name": row.profile_name, "mm_pnl_cents": row.mm_pnl_cents, "two_sided_ppm": row.two_sided_ppm}
                for row in study.rows
            ],
        },
        as_json=bool(args.json),
        lines=[
            f"wrote {out}",
            *(
                f"  {row.profile_name}: mm_pnl_cents {row.mm_pnl_cents}, two sided {row.two_sided_ppm} ppm"
                for row in study.rows
            ),
        ],
    )
    return EXIT_OK


def _cmd_store_init(args: argparse.Namespace) -> int:
    """Create the projection schema, idempotently.

    Args:
        args: Parsed arguments.

    Returns:
        :data:`EXIT_OK`.
    """
    with _store_for(args) as store:
        _emit(
            {"url": store.url, "schema_version": store.schema_version()},
            as_json=bool(args.json),
            lines=[f"schema {store.schema_version()} ready at {store.url}"],
        )
    return EXIT_OK


def _cmd_store_rebuild(args: argparse.Namespace) -> int:
    """Drop and re import every projection table from the journals.

    Args:
        args: Parsed arguments.

    Returns:
        :data:`EXIT_OK`.
    """
    with _store_for(args) as store:
        imported = store.rebuild(runs_dir=Path(args.runs_dir))
    _emit(
        {"runs_dir": str(args.runs_dir), "matches": imported},
        as_json=bool(args.json),
        lines=[f"re imported {imported} match(es) from {args.runs_dir}"],
    )
    return EXIT_OK


def _cmd_integrity_scan(args: argparse.Namespace) -> int:
    """Run the detectors offline over one match and write ``incidents.jsonl``.

    Args:
        args: Parsed arguments.

    Returns:
        :data:`EXIT_OK`.
    """
    runs_dir = Path(args.runs_dir)
    with _store_for(args) as store:
        count = _scan_match(store, match_id=str(args.match_id), runs_dir=runs_dir)
    path = artefact_paths(runs_dir, str(args.match_id))["incidents"]
    _emit(
        {"match_id": str(args.match_id), "incidents": count, "path": str(path)},
        as_json=bool(args.json),
        lines=[f"{count} incident(s) written to {path}"],
    )
    return EXIT_OK


# --------------------------------------------------------------------------
# Parser
# --------------------------------------------------------------------------
def _add_common(parser: argparse.ArgumentParser) -> None:
    """Add the flags every verb accepts.

    Args:
        parser: The sub-parser to extend.
    """
    parser.add_argument("--json", action="store_true", help="print one JSON object instead of a human rendering")


def _add_store_options(parser: argparse.ArgumentParser) -> None:
    """Add the runs directory and the database URL.

    Args:
        parser: The sub-parser to extend.
    """
    parser.add_argument("--runs-dir", default="runs", help="artefact root, default runs")
    parser.add_argument("--db-url", default="", help="SQLAlchemy URL, default SQLite inside the runs directory")


def _add_match_options(parser: argparse.ArgumentParser) -> None:
    """Add the world and table flags shared by ``match run`` and ``match verify``.

    Args:
        parser: The sub-parser to extend.
    """
    parser.add_argument("--template", required=True, help=f"world template: {', '.join(list_templates())}")
    parser.add_argument("--seed", type=int, required=True, help="unsigned 64 bit root seed")
    parser.add_argument("--ticks", type=int, default=MatchConfig().ticks_total, help="horizon T, 24 to 96")
    parser.add_argument("--markets", type=int, default=MatchConfig().n_markets, help="number of markets, 2 to 8")
    parser.add_argument(
        "--agents",
        default=",".join(DEFAULT_AGENTS),
        help="comma separated scripted baseline names, one per seat",
    )
    parser.add_argument(
        "--llm-model",
        action="append",
        default=[],
        help="add one LLM seat behind the Claude Code CLI, repeatable",
    )
    parser.add_argument(
        "--liquidity",
        default=str(LiquidityProfileName.STANDARD),
        help="market maker preset: liquid, standard or illiquid",
    )
    parser.add_argument("--talking", action="store_true", help="enable FR-5.6.1 public messages")
    parser.add_argument("--taker-fee-bps", type=int, default=0, help="taker fee in basis points, 0 to 200")


def _build_match_parsers(subparsers: Any) -> None:
    """Register ``pxe match run``, ``verify`` and ``replay``.

    Args:
        subparsers: The ``pxe match`` sub-parser action.
    """
    run = subparsers.add_parser("run", help="run one match, scripted or LLM")
    _add_match_options(run)
    _add_store_options(run)
    _add_common(run)
    run.add_argument("--match-id", default="", help="override the derived m-<template>-<seed>-01")
    run.add_argument("--no-store", action="store_true", help="do not mirror the match into the database")
    run.add_argument("--system-prompt", default=_DEFAULT_SYSTEM_PROMPT, help="system prompt of every LLM seat")
    run.add_argument("--timeout-s", type=float, default=GatewayConfig().timeout_s, help="per call timeout")
    run.add_argument(
        "--max-budget-usd",
        type=float,
        default=GatewayConfig().max_budget_usd_per_match,
        help="provider budget cap of this match",
    )
    run.set_defaults(handler=_cmd_match_run)

    verify = subparsers.add_parser("verify", help="run the same seed N times and compare journal hashes (AC-P1)")
    _add_match_options(verify)
    _add_common(verify)
    verify.add_argument("--repeat", type=int, default=2, help="number of fresh processes, at least 2")
    verify.set_defaults(handler=_cmd_match_verify)

    replay = subparsers.add_parser("replay", help="replay a journal and print the projected metrics")
    replay.add_argument("journal", help="path to a journal.jsonl")
    _add_common(replay)
    replay.set_defaults(handler=_cmd_match_replay)


def _build_tournament_parsers(subparsers: Any) -> None:
    """Register ``pxe tournament run`` and ``resume``.

    Args:
        subparsers: The ``pxe tournament`` sub-parser action.
    """
    for name, handler, helptext in (
        ("run", _cmd_tournament_run, "run a tournament from a TOML config"),
        ("resume", _cmd_tournament_resume, "resume an interrupted tournament, idempotently"),
    ):
        parser = subparsers.add_parser(name, help=helptext)
        parser.add_argument("config", help="path to a configs/*.toml preset")
        _add_store_options(parser)
        _add_common(parser)
        parser.add_argument("--max-workers", type=int, default=4, help="parallel worker processes")
        parser.add_argument("--heldout-bank", default="", help="sealed seed bank to draw every seed from (AC-P5)")
        parser.add_argument(
            "--heldout-reserve",
            type=int,
            default=0,
            help="seal this many seeds per template into the bank before running",
        )
        parser.set_defaults(handler=handler)


def _build_api_parsers(subparsers: Any) -> None:
    """Register ``pxe api serve`` and ``pxe api openapi``.

    Args:
        subparsers: The ``pxe api`` sub-parser action.
    """
    serve = subparsers.add_parser("serve", help="start the read only replay API")
    _add_store_options(serve)
    _add_common(serve)
    serve.add_argument("--host", default="127.0.0.1", help="bind address")
    serve.add_argument("--port", type=int, default=8000, help="bind port")
    serve.add_argument("--cors-origin", action="append", default=[], help="allowed browser origin, repeatable")
    serve.set_defaults(handler=_cmd_api_serve)

    openapi = subparsers.add_parser("openapi", help="write docs/REPLAY_API.md from the FastAPI schema")
    _add_store_options(openapi)
    _add_common(openapi)
    openapi.add_argument("--out", default=str(Path("docs") / "REPLAY_API.md"), help="destination document")
    openapi.add_argument("--samples", action="store_true", help="also write one JSON fixture per payload")
    openapi.add_argument("--match-id", default="", help="the recorded match the fixtures are sampled from")
    openapi.add_argument("--tournament-id", default="", help="a recorded tournament to sample as well")
    openapi.add_argument(
        "--fixtures-dir",
        default=str(Path("web") / "tests" / "fixtures"),
        help="destination of the --samples fixtures",
    )
    openapi.set_defaults(handler=_cmd_api_openapi)


def _build_store_parsers(subparsers: Any) -> None:
    """Register ``pxe store init`` and ``pxe store rebuild``.

    Args:
        subparsers: The ``pxe store`` sub-parser action.
    """
    init = subparsers.add_parser("init", help="create the projection schema")
    _add_store_options(init)
    _add_common(init)
    init.set_defaults(handler=_cmd_store_init)

    rebuild = subparsers.add_parser("rebuild", help="re import every projection table from the journals")
    rebuild.add_argument("runs_dir", help="the runs root holding runs/<match_id>/journal.jsonl")
    rebuild.add_argument("--db-url", default="", help="SQLAlchemy URL, default SQLite inside the runs directory")
    _add_common(rebuild)
    rebuild.set_defaults(handler=_cmd_store_rebuild)


def _build_leaf_parsers(groups: Any) -> None:
    """Register the verbs that have a single leaf: report, schema, world, mm, integrity.

    They live in their own function only so that :func:`_build_parser` stays
    readable; each one is still exactly the verb section 7.22 names.

    Args:
        groups: The top level sub-parser action.
    """
    report = groups.add_parser("report", help="build the report of a tournament").add_subparsers(dest="verb")
    build = report.add_parser("build", help="write report.md and report.html, train and held-out")
    build.add_argument("tournament_id", help="the tournament to report on")
    _add_store_options(build)
    _add_common(build)
    build.add_argument("--out", default="", help="destination directory, default runs/<tournament_id>")
    build.add_argument("--no-scan", action="store_true", help="do not re run the integrity detectors first")
    build.set_defaults(handler=_cmd_report_build)

    schema = groups.add_parser("schema", help="print a versioned schema").add_subparsers(dest="verb")
    dump = schema.add_parser("dump", help="print one schema as JSON")
    dump.add_argument("name", help="observation, action, or an explicit observation.v1 / action.v1")
    _add_common(dump)
    dump.set_defaults(handler=_cmd_schema_dump)

    world = groups.add_parser("world", help="world generation statistics").add_subparsers(dest="verb")
    stats = world.add_parser("stats", help="run the FR-5.2.2 frequency test")
    stats.add_argument("template", help=f"world template: {', '.join(list_templates())}")
    stats.add_argument("--draws", type=int, default=10_000, help="number of worlds to draw")
    stats.add_argument("--base-seed", type=int, default=0, help="seed of the first draw")
    stats.add_argument("--markets", type=int, default=MatchConfig().n_markets, help="markets per drawn world")
    _add_common(stats)
    stats.set_defaults(handler=_cmd_world_stats)

    mm = groups.add_parser("mm", help="market maker studies").add_subparsers(dest="verb")
    study = mm.add_parser("study", help="measure the cost of liquidity (T2.6)")
    study.add_argument("--profile", default="all", help="liquid, standard, illiquid or all")
    study.add_argument("--matches", type=int, default=200, help="matches per preset")
    study.add_argument("--template", default="election", help="world template of the study matches")
    study.add_argument("--seed", type=int, default=20260827, help="root seed of the first study match")
    study.add_argument("--ticks", type=int, default=24, help="horizon of one study match")
    study.add_argument("--markets", type=int, default=2, help="markets per study match")
    study.add_argument("--agents", default=",".join(DEFAULT_AGENTS), help="comma separated baseline names")
    study.add_argument("--out", default=str(Path("docs") / "MM_LIQUIDITY_COST.md"), help="destination document")
    _add_common(study)
    study.set_defaults(handler=_cmd_mm_study)

    integrity = groups.add_parser("integrity", help="offline integrity detectors").add_subparsers(dest="verb")
    scan = integrity.add_parser("scan", help="run the detectors and write incidents.jsonl")
    scan.add_argument("match_id", help="the match to scan")
    _add_store_options(scan)
    _add_common(scan)
    scan.set_defaults(handler=_cmd_integrity_scan)


def _build_parser() -> _CliParser:
    """Build the whole command line grammar of section 7.22.

    Returns:
        The parser.
    """
    parser = _CliParser(prog="pxe", description="Prediction Exchange: a deterministic LLM trading arena.")
    parser.add_argument("--version", action="version", version=f"pxe {__version__}")
    parser.add_argument("--verbose", action="store_true", help="log at DEBUG")
    parser.add_argument("--quiet", action="store_true", help="log at ERROR")
    groups = parser.add_subparsers(dest="group")

    match_group = groups.add_parser("match", help="run, verify or replay one match")
    _build_match_parsers(match_group.add_subparsers(dest="verb"))
    _build_tournament_parsers(
        groups.add_parser("tournament", help="run or resume a tournament").add_subparsers(dest="verb")
    )
    _build_api_parsers(groups.add_parser("api", help="serve or document the replay API").add_subparsers(dest="verb"))
    store_group = groups.add_parser("store", help="create or rebuild the projection database")
    _build_store_parsers(store_group.add_subparsers(dest="verb"))

    _build_leaf_parsers(groups)

    return parser


def _exit_code_of(error: PxeError) -> int:
    """Map a library error onto the exit codes of section 7.22.

    Args:
        error: The raised error.

    Returns:
        ``2`` for a determinism failure, ``3`` for a budget breach, ``4`` for an
        invariant violation, ``1`` for anything else, which is by construction
        something the operator asked for.
    """
    if isinstance(error, InvariantViolationError):
        return EXIT_INVARIANT
    if isinstance(error, BudgetExceededError):
        return EXIT_BUDGET
    if isinstance(error, DeterminismError):
        return EXIT_DETERMINISM
    return EXIT_USER_ERROR


def main(argv: Sequence[str] | None = None) -> int:
    """Run one command line and return its exit code (section 7.22).

    Args:
        argv: The arguments after the program name, or ``None`` to read
            ``sys.argv``.

    Returns:
        ``0`` success, ``1`` user error, ``2`` determinism failure, ``3`` budget
        exceeded, ``4`` invariant violation.
    """
    parser = _build_parser()
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
    except _UsageError as exc:
        print(f"pxe: {exc}", file=sys.stderr)
        return EXIT_USER_ERROR
    except SystemExit as exc:  # --help and --version
        return EXIT_OK if exc.code in (0, None) else EXIT_USER_ERROR
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return EXIT_USER_ERROR
    _configure_logging(verbose=bool(args.verbose), quiet=bool(args.quiet))
    try:
        return int(handler(args))
    except _UsageError as exc:
        print(f"pxe: {exc}", file=sys.stderr)
        return EXIT_USER_ERROR
    except FileNotFoundError as exc:
        print(f"pxe: {exc}", file=sys.stderr)
        return EXIT_USER_ERROR
    except KeyboardInterrupt:
        print("pxe: interrupted", file=sys.stderr)
        return EXIT_USER_ERROR
    except PxeError as exc:
        code = _exit_code_of(exc)
        _LOG.error("%s: %s", type(exc).__name__, exc)
        print(f"pxe: {type(exc).__name__}: {exc}", file=sys.stderr)
        return code


if __name__ == "__main__":  # pragma: no cover - the -m entry point
    sys.exit(main())
