"""The ``ala`` command-line entry point (W13, CONTRACTS section 14).

This is the operator surface for the engine: build a deterministic match from flags, run it into a
fresh journal, and report the outcome (ranking, journal hash, incidents, metric families). It also
verifies reproducibility (`match verify`), replays a journal offline (`match replay`), and serves the
read-only API (`api serve`).

Design notes (WHY):
- The metrics and detector modules live one layer above the runner and may be authored separately; the
  reporting imports are therefore done lazily inside the reporting helper so importing ``ala.cli`` and
  running a match never hard-depend on them. A missing reporting module degrades to a printed note
  rather than a crash, because the journal (the source of truth) is already on disk by then.
- ``main`` returns an int exit code and never calls ``sys.exit`` except in the ``__main__`` guard, so it
  is callable from tests and from the ``ala`` script mapping alike.
- Randomness and gateway state are rebuilt fresh for every run (including each ``verify`` repeat) so two
  runs of the same seed are byte-identical.
"""

from __future__ import annotations

import argparse
import tempfile
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from ala.gateway import Gateway, ScriptedGateway
from ala.journal import Journal
from ala.metrics.projection import MatchProjection
from ala.rng import RngTree
from ala.runner import run_match
from ala.scenario import make_scenario
from ala.scenario.base import WorldSpec
from ala.types import MatchConfig, MatchResult

_DEFAULT_AGENTS = "grinder,allier,raider,forger"
_IMPOSSIBLE_RATE_PCT = 20  # one task in five is impossible (CONTRACTS section 9)
_PERMISSIONS = ("silent", "sandbox", "carte_blanche")


# --- config assembly ----------------------------------------------------------------------------


def _seat_specs(agents_csv: str) -> dict[str, str]:
    """Map the comma list of archetype names onto seats ``seat-01``, ``seat-02``, ... in order."""
    archetypes = [a.strip() for a in agents_csv.split(",") if a.strip()]
    return {f"seat-{i:02d}": arch for i, arch in enumerate(archetypes, start=1)}


def _build_config(args: argparse.Namespace, agent_specs: tuple[str, ...]) -> MatchConfig:
    return MatchConfig(
        scenario=args.scenario,
        seed=args.seed,
        agent_specs=agent_specs,
        ticks=args.ticks,
        cull_every=args.cull_every,
        start_budget=args.start_budget,
        floor_start=args.floor_start,
        floor_step=args.floor_step,
        clone_top_k=args.clone_top_k,
        permission=args.permission,
    )


def _world_spec(args: argparse.Namespace) -> WorldSpec:
    return WorldSpec(
        start_budget=args.start_budget,
        sudoers_defect_rate_pct=args.defect,
        impossible_task_rate_pct=_IMPOSSIBLE_RATE_PCT,
    )


def _run_into(args: argparse.Namespace, journal_path: Path) -> MatchResult:
    """Build a fresh rng, gateway, scenario and journal and run one match into ``journal_path``.

    Everything is rebuilt per call so the run is a pure function of the flags: this is what makes two
    runs of the same seed byte-identical (the property ``match verify`` checks).
    """
    seats = _seat_specs(args.agents)
    config = _build_config(args, tuple(seats.values()))
    rng = RngTree(config.seed)
    gateway = ScriptedGateway(seats, rng)
    scenario = make_scenario(args.scenario, _world_spec(args))
    journal = Journal(journal_path)
    try:
        # ScriptedGateway satisfies the Gateway protocol structurally; the cast documents that the
        # read-only ``agent_ids`` property is the intended (never reassigned) usage in the runner.
        return run_match(config, cast(Gateway, gateway), scenario, journal, rng)
    finally:
        journal.close()


def _unique_match_dir(out_root: Path, match_id: str) -> Path:
    """Return a fresh directory under ``out_root`` for ``match_id``, suffixing ``-01``, ``-02`` on
    collision so a re-run never clobbers an earlier journal."""
    candidate = out_root / match_id
    if not candidate.exists():
        candidate.mkdir(parents=True)
        return candidate
    suffix = 1
    while True:
        candidate = out_root / f"{match_id}-{suffix:02d}"
        if not candidate.exists():
            candidate.mkdir(parents=True)
            return candidate
        suffix += 1


# --- reporting ----------------------------------------------------------------------------------


def _report_projection(proj: MatchProjection) -> None:
    """Print the metric families and the incidents for a projection.

    Reporting modules sit above the runner and may not exist in every build; import them here so a run
    can complete and its journal be written even when the metric layer is absent.
    """
    try:
        from ala.metrics.outcome import outcome_summary
    except ImportError as exc:  # pragma: no cover - depends on peer module availability
        print(f"[metrics unavailable: {exc}]")
    else:
        _print_metric("outcome", outcome_summary(proj))
        _report_extra_metrics(proj)

    try:
        from ala.detectors import run_detectors
    except ImportError as exc:  # pragma: no cover - depends on peer module availability
        print(f"[detectors unavailable: {exc}]")
        return
    incidents = list(run_detectors(proj))
    _print_incidents(incidents)


def _report_extra_metrics(proj: MatchProjection) -> None:
    """Print the cooperation, conflict and exploitation families, each optional."""
    try:
        from ala.metrics.cooperation import cooperation_metrics

        _print_metric("cooperation", cooperation_metrics(proj))
    except ImportError:  # pragma: no cover
        pass
    try:
        from ala.metrics.conflict import conflict_metrics

        _print_metric("conflict", conflict_metrics(proj))
    except ImportError:  # pragma: no cover
        pass
    try:
        from ala.metrics.exploitation import exploitation_metrics

        _print_metric("exploitation", exploitation_metrics(proj))
    except ImportError:  # pragma: no cover
        pass


def _print_metric(name: str, values: object) -> None:
    print(f"metric {name}:")
    if isinstance(values, dict):
        for key in sorted(values):
            print(f"  {key} = {values[key]}")
    else:
        print(f"  {values}")


def _print_incidents(incidents: Sequence[object]) -> None:
    print(f"incidents ({len(incidents)}):")
    grouped: dict[str, list[object]] = defaultdict(list)
    for inc in incidents:
        kind = str(getattr(inc, "kind", "unknown"))
        grouped[kind].append(inc)
    if not grouped:
        print("  (none)")
        return
    for kind in sorted(grouped):
        items = grouped[kind]
        print(f"  {kind} ({len(items)}):")
        for inc in items:
            tick = getattr(inc, "tick", "?")
            agents = ",".join(getattr(inc, "agents", ()) or ())
            detail = getattr(inc, "detail", {}) or {}
            print(f"    tick={tick} agents=[{agents}] detail={dict(detail)}")


# --- subcommands --------------------------------------------------------------------------------


def _cmd_match_run(args: argparse.Namespace) -> int:
    out_root = Path(args.out)
    match_id = f"m-{args.scenario}-{args.seed}"
    match_dir = _unique_match_dir(out_root, match_id)
    journal_path = match_dir / "journal.jsonl"

    result = _run_into(args, journal_path)

    print(f"match_id: {result.match_id}")
    print(f"journal: {journal_path}")
    print(f"ticks: {result.ticks}")
    print("final ranking:")
    for rank, agent_id in enumerate(result.final_ranking, start=1):
        print(f"  {rank}. {agent_id}")
    print(f"journal hash: {result.journal_hash}")

    proj = MatchProjection.from_journal(journal_path)
    _report_projection(proj)
    return 0


def _cmd_match_verify(args: argparse.Namespace) -> int:
    hashes: list[str] = []
    with tempfile.TemporaryDirectory(prefix="ala-verify-") as tmp:
        tmp_dir = Path(tmp)
        for i in range(args.repeat):
            journal_path = tmp_dir / f"run-{i:02d}.jsonl"
            result = _run_into(args, journal_path)
            hashes.append(result.journal_hash)
            print(f"run {i:02d}: {result.journal_hash}")

    first = hashes[0] if hashes else ""
    ok = all(h == first for h in hashes)
    print("OK" if ok else "MISMATCH")
    return 0 if ok else 1


def _cmd_match_replay(args: argparse.Namespace) -> int:
    journal_path = Path(args.journal_path)
    proj = MatchProjection.from_journal(journal_path)
    print(f"scenario: {proj.scenario}")
    print(f"seed: {proj.seed}")
    print(f"ticks: {proj.ticks}")
    print(f"agents: {', '.join(proj.all_agents())}")
    print("final ranking:")
    for rank, agent_id in enumerate(proj.final_ranking, start=1):
        print(f"  {rank}. {agent_id}")
    _report_projection(proj)
    return 0


def _cmd_api_serve(args: argparse.Namespace) -> int:
    try:
        from ala.api.app import create_app
    except ImportError as exc:
        print(f"the API layer is not available: {exc}")
        return 1
    try:
        import uvicorn
    except ImportError as exc:
        print(f"uvicorn is required to serve the API: {exc}")
        return 1
    app = create_app(args.runs_dir)
    uvicorn.run(app, host=args.host, port=args.port)
    return 0


# --- argument parsing ---------------------------------------------------------------------------


def _add_run_flags(parser: argparse.ArgumentParser) -> None:
    """Attach the flags shared by ``match run`` and ``match verify``."""
    parser.add_argument("--scenario", default="concours")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--agents", default=_DEFAULT_AGENTS)
    parser.add_argument("--ticks", type=int, default=24)
    parser.add_argument("--cull-every", dest="cull_every", type=int, default=8)
    parser.add_argument("--defect", type=int, default=100)
    parser.add_argument("--start-budget", dest="start_budget", type=int, default=100)
    parser.add_argument("--floor-start", dest="floor_start", type=int, default=20)
    parser.add_argument("--floor-step", dest="floor_step", type=int, default=15)
    parser.add_argument("--clone-top-k", dest="clone_top_k", type=int, default=1)
    parser.add_argument("--permission", choices=_PERMISSIONS, default="silent")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ala", description="AllAllowed match engine CLI")
    top = parser.add_subparsers(dest="group")

    match_parser = top.add_parser("match", help="run, verify or replay a match")
    match_sub = match_parser.add_subparsers(dest="action")

    run_parser = match_sub.add_parser("run", help="run one match and report it")
    _add_run_flags(run_parser)
    run_parser.add_argument("--out", default="runs")
    run_parser.set_defaults(func=_cmd_match_run)

    verify_parser = match_sub.add_parser("verify", help="run the same seed twice and compare hashes")
    _add_run_flags(verify_parser)
    verify_parser.add_argument("--repeat", type=int, default=2)
    verify_parser.set_defaults(func=_cmd_match_verify)

    replay_parser = match_sub.add_parser("replay", help="replay a journal and print its metrics")
    replay_parser.add_argument("journal_path")
    replay_parser.set_defaults(func=_cmd_match_replay)

    api_parser = top.add_parser("api", help="serve the read-only match API")
    api_sub = api_parser.add_subparsers(dest="action")
    serve_parser = api_sub.add_parser("serve", help="serve the API with uvicorn")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8165)
    serve_parser.add_argument("--runs-dir", dest="runs_dir", default="runs")
    serve_parser.set_defaults(func=_cmd_api_serve)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    func = getattr(args, "func", None)
    if func is None:
        parser.print_help()
        return 2
    result: int = func(args)
    return result


if __name__ == "__main__":  # pragma: no cover
    import sys

    sys.exit(main(sys.argv[1:]))
