"""``pmx backtest`` and ``pmx replay`` (CONTRACTS_V2 sections 9.5, 12.11 and 13).

Two commands, both thin: everything they do beyond parsing is a call into
``pmx.engine.runner``, ``pmx.metrics.projection`` and ``pmx.store``. ``backtest`` builds the run's
``RngTree`` and its ``LiquidityModel`` (the runner builds neither, sections 6.2 and 16.1), runs the
roster over the dataset, indexes the run, and prints the summary. ``replay`` rebuilds ``results.json``
from ``journal.jsonl`` alone and refuses a journal written by another engine with exit code 2, which is
what section 13.2 asks for.

The roster is A1's to build (``pmx.agents.registry``, wave 3). It is imported inside the handler rather
than at module level so that this file is importable, testable and usable for ``replay`` while wave 2 is
being built, and a run asked for before A1 lands fails with ``NotConfiguredError`` naming the missing
name rather than with an ``ImportError``. Reported as a contract issue: section 10.5 names
``FAMILIES`` and ``DEFAULT_ROSTER`` but no constructor, and ``pmx.cli_run`` needs one.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from importlib import import_module
from pathlib import Path
from typing import cast

from pmx import ENGINE_VERSION
from pmx.engine.liquidity import make_liquidity
from pmx.engine.runner import Agent, replay, run_backtest
from pmx.errors import JournalError, NotConfiguredError, PmxError
from pmx.journal import canonical_json
from pmx.metrics.leaderboard import build as build_leaderboard
from pmx.metrics.projection import RunHandle
from pmx.rng import RngTree
from pmx.store import DEFAULT_STORE_NAME, RunStore
from pmx.types import Dataset, RunConfig, market_set_hash

__all__ = ("build_parser", "config_from_args", "main", "register", "run_from_args")

#: Where a run directory is created unless the caller says otherwise (section 9.5).
DEFAULT_RUNS_DIR = Path("runs")


def _load_dataset(path: Path) -> Dataset:
    """Load a dataset from a directory path (``pmx.data.loader``, D1)."""
    from pmx.data.loader import load_dataset

    return load_dataset(path)


def _build_roster(dataset: Dataset, agent_ids: Sequence[str]) -> tuple[Agent, ...]:
    """The run's roster, from A1's registry (section 10.5).

    Args:
        dataset: The dataset, so a registry that wants the run's providers can have them.
        agent_ids: The agent ids to run, or empty for A1's ``DEFAULT_ROSTER``.

    Raises:
        NotConfiguredError: While ``pmx.agents.registry`` (A1, wave 3) does not exist, or does not
            expose the two names section 10.5 describes. The message names what is missing, because a
            wave-2 caller that wants a run drives ``pmx.engine.runner.run_backtest`` directly with its
            own agents, exactly as ``tests/test_runner.py`` does.
    """
    try:
        registry = import_module("pmx.agents.registry")
    except ModuleNotFoundError as error:
        raise NotConfiguredError(
            "the agent registry lands in wave 3 (A1); run_backtest takes a roster directly",
            missing="pmx.agents.registry",
        ) from error
    default_roster = getattr(registry, "DEFAULT_ROSTER", None)
    build_agent = getattr(registry, "build_agent", None)
    if default_roster is None or build_agent is None:
        raise NotConfiguredError(
            "pmx.agents.registry must expose DEFAULT_ROSTER and build_agent",
            missing="DEFAULT_ROSTER,build_agent",
        )
    rows = cast(Sequence[tuple[str, object]], default_roster)
    wanted = frozenset(agent_ids)
    builder = cast(Callable[..., Agent], build_agent)
    return tuple(
        builder(agent_id=agent_id, genome=genome)
        for agent_id, genome in rows
        if not wanted or agent_id in wanted
    )


def config_from_args(args: argparse.Namespace, dataset: Dataset, market_ids: Sequence[str]) -> RunConfig:
    """The run's ``RunConfig``, with ``market_ids_hash`` filled in by the caller (section 8.1).

    ``market_ids_hash`` is the caller's job and ``run_backtest`` refuses an empty or mismatching value,
    so this is the one place a command line turns into the hash the run id is built from.
    """
    return RunConfig(
        seed=int(args.seed),
        interval_min=dataset.manifest.interval_min,
        t0_ms=args.t0_ms,
        t1_ms=args.t1_ms,
        bankroll_cents=int(args.bankroll_cents),
        fold=str(args.fold),
        amnesic=bool(args.amnesic),
        no_hive=bool(args.no_hive),
        market_ids_hash=market_set_hash(market_ids),
    )


def run_from_args(args: argparse.Namespace) -> RunHandle:
    """Run one backtest from parsed arguments and return its handle (section 12.11)."""
    dataset = _load_dataset(Path(args.dataset))
    market_ids = [meta.id for meta in dataset.metas if args.fold in ("all", meta.fold)]
    config = config_from_args(args, dataset, market_ids)
    roster = _build_roster(dataset, tuple(str(name) for name in (args.agents or ())))
    handle = run_backtest(
        dataset,
        roster,
        config,
        tree=RngTree(config.seed),
        journal_dir=Path(args.runs_dir),
        liquidity=make_liquidity(config),
        dump_observations=bool(args.dump_observations),
    )
    if not args.no_index:
        with RunStore(Path(args.runs_dir) / DEFAULT_STORE_NAME) as store:
            store.index_run(
                handle,
                dataset_name=dataset.manifest.name,
                seed=config.seed,
                fold=config.fold,
                market_ids_hash=config.market_ids_hash,
            )
            store.index_projection(handle, fold=config.fold)
    return handle


def _cmd_backtest(args: argparse.Namespace) -> int:
    handle = run_from_args(args)
    if args.json:
        print(canonical_json(handle.to_dict()))
        return 0
    print(f"run_id       {handle.run_id}")
    print(f"journal      {handle.journal_path.as_posix()}")
    print(f"journal_hash {handle.journal_hash}")
    print(f"bars         {handle.n_bars}")
    print(f"events       {handle.n_events}")
    for row in handle.projection.agents:
        print(
            f"  {row.agent_id:<24} brier {row.brier_tw_micro:>8} "
            f"skill {row.skill.point:>9} pnl {row.pnl_cents:>9} "
            f"markets {row.n_markets:>4} traded {row.n_markets_traded:>4}"
            + (" RUINED" if row.ruined else "")
        )
    return 0


def _cmd_replay(args: argparse.Namespace) -> int:
    run_dir = Path(args.runs_dir) / str(args.run_id)
    if not (run_dir / "journal.jsonl").exists():
        print(f"error: no journal at {run_dir.as_posix()}", file=sys.stderr)
        return 2
    try:
        projection = replay(run_dir)
    except JournalError as error:
        message = str(error)
        print(f"error: {message}", file=sys.stderr)
        return 2 if "engine" in message else 1
    if args.leaderboard:
        rows = build_leaderboard(projection)
        print(canonical_json([row.to_dict() for row in rows]))
        return 0
    if args.json:
        print(canonical_json(projection.to_dict()))
        return 0
    print(f"run_id       {projection.run_id}")
    print(f"engine       {ENGINE_VERSION}")
    print(f"agents       {len(projection.agents)}")
    print(f"markets      {len(projection.markets)}")
    print(f"rows         {len(projection.per_market)}")
    print("results.json rebuilt from the journal and identical")
    return 0


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--runs-dir", default=str(DEFAULT_RUNS_DIR), help="where run directories live")
    parser.add_argument("--json", action="store_true", help="print canonical JSON instead of a summary")


def _add_backtest(parser: argparse.ArgumentParser) -> None:
    """The arguments of ``pmx backtest``."""
    parser.add_argument("--dataset", required=True, help="path to a dataset directory")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--fold", default="all", choices=("train", "validation", "sealed", "all"))
    parser.add_argument("--bankroll-cents", dest="bankroll_cents", type=int, default=100_000)
    parser.add_argument("--t0-ms", dest="t0_ms", type=int, default=None)
    parser.add_argument("--t1-ms", dest="t1_ms", type=int, default=None)
    parser.add_argument("--agents", nargs="*", default=(), help="agent ids, default the whole roster")
    parser.add_argument("--amnesic", action="store_true", help="start from an empty memory")
    parser.add_argument("--no-hive", dest="no_hive", action="store_true", help="empty every hive read")
    parser.add_argument(
        "--dump-observations",
        dest="dump_observations",
        action="store_true",
        help="write observations/<bar_ms>-<agent_id>.json for the leak audit",
    )
    parser.add_argument(
        "--no-index", dest="no_index", action="store_true", help="do not touch the sqlite run index"
    )
    _add_common(parser)
    parser.set_defaults(func=_cmd_backtest)


def _add_replay(parser: argparse.ArgumentParser) -> None:
    """The arguments of ``pmx replay``."""
    parser.add_argument("run_id")
    parser.add_argument(
        "--leaderboard", action="store_true", help="print the leaderboard rows of section 12.10"
    )
    _add_common(parser)
    parser.set_defaults(func=_cmd_replay)


def build_parser(parser: argparse.ArgumentParser) -> None:
    """Mount ``backtest`` and ``replay`` as the two actions of a standalone parser."""
    sub = parser.add_subparsers(dest="action", required=True)
    _add_backtest(sub.add_parser("backtest", help="run a roster over a dataset and journal every event"))
    _add_replay(sub.add_parser("replay", help="rebuild results.json from journal.jsonl and compare"))


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Mount ``pmx backtest`` and ``pmx replay`` on the top level parser (U4, wave 5).

    Two top-level commands rather than a group, because that is how section 13 names them: the plan
    gives E5 ``pmx backtest`` and ``pmx replay``, not ``pmx run <action>``.
    """
    _add_backtest(subparsers.add_parser("backtest", help="run a roster over a dataset"))
    _add_replay(subparsers.add_parser("replay", help="rebuild results.json from a journal and compare"))


def main(argv: Sequence[str] | None = None) -> int:
    """Run the two commands as a program, which is how they are driven before U4 wires them in."""
    parser = argparse.ArgumentParser(
        prog="pmx run", description="Run a backtest over a dataset, and replay one from its journal."
    )
    build_parser(parser)
    args = parser.parse_args(list(argv) if argv is not None else None)
    handler = getattr(args, "func", None)
    if handler is None:  # pragma: no cover - the subparser is required
        parser.print_help()
        return 2
    try:
        return cast(Callable[[argparse.Namespace], int], handler)(args)
    except PmxError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover - exercised through main() in the tests
    raise SystemExit(main())
