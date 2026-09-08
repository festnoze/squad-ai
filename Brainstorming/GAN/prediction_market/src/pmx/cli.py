"""The pmx command line: seed data, backtest one market, run a tournament, walk forward, import, serve.

Every command that scores is free and deterministic. ``import`` is the only one that touches a network,
and ``api serve`` is the only long-running one.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from pmx.v1.agents import AGENT_IDS
from pmx.v1.data.bundled import seed_dataset
from pmx.v1.data.loader import load_market, load_markets
from pmx.v1.engine import run_backtest
from pmx.v1.metrics import LeaderRow
from pmx.v1.tournament import run_tournament, walk_forward

DEFAULT_DATA = "data/markets"


def _pct(brier_micro: int) -> str:
    """Show a Brier micro-score as a 0.000 to 1.000 number."""
    return f"{brier_micro / 1_000_000:.3f}"


def _agents(csv: str | None) -> tuple[str, ...]:
    if not csv:
        return AGENT_IDS
    return tuple(a.strip() for a in csv.split(",") if a.strip())


def _cmd_seed(args: argparse.Namespace) -> int:
    n = seed_dataset(Path(args.out))
    print(f"wrote {n} markets to {args.out}")
    return 0


def _cmd_backtest(args: argparse.Namespace) -> int:
    market = load_market(Path(args.market))
    replay = run_backtest(market, _agents(args.agents))
    print(f"market: {market.id}  ({'YES' if market.resolution else 'NO'})  source={market.source}")
    print(f"question: {market.question}")
    print(f"{'agent':<16} {'final_brier':>11} {'mean_brier':>10} {'pnl_$':>8} {'trades':>6}  vs_market")
    for r in sorted(replay.results, key=lambda x: x.final_brier_micro):
        edge = r.market_brier_micro - r.final_brier_micro
        flag = "beats" if edge > 0 else ("ties" if edge == 0 else "worse")
        print(
            f"{r.agent_id:<16} {_pct(r.final_brier_micro):>11} {_pct(r.mean_brier_micro):>10} "
            f"{r.pnl_cents / 100:>8.2f} {r.trades:>6}  {flag}"
        )
    return 0


def _print_board(board: list[LeaderRow], title: str) -> None:
    print(f"\n{title}")
    print(f"{'rank':<5}{'agent':<16}{'mean_brier':>11}{'beat_mkt':>9}{'total_$':>10}{'skill':>8}")
    for i, row in enumerate(board, start=1):
        print(
            f"{i:<5}{row.agent_id:<16}{_pct(row.mean_brier_micro):>11}"
            f"{str(row.beat_market_pct) + '%':>9}{row.total_pnl_cents / 100:>10.2f}"
            f"{_pct(row.skill_vs_market_micro):>8}"
        )


def _cmd_tournament(args: argparse.Namespace) -> int:
    markets = load_markets(Path(args.data))
    if not markets:
        print(f"no markets in {args.data}; run 'pmx data seed' first")
        return 1
    t = run_tournament(markets, _agents(args.agents))
    print(f"tournament over {len(markets)} markets, {len(t.agent_ids)} agents")
    _print_board(t.board, "leaderboard (best forecaster first)")
    best = t.board[0]
    print(
        f"\nbest agent: {best.agent_id} (mean Brier {_pct(best.mean_brier_micro)}, "
        f"beat the market on {best.beat_market_pct}% of markets)"
    )
    return 0


def _cmd_walkforward(args: argparse.Namespace) -> int:
    markets = load_markets(Path(args.data))
    if len(markets) < 4:
        print(f"need at least four markets in {args.data}; run 'pmx data seed' first")
        return 1
    wf = walk_forward(markets, _agents(args.agents))
    print(f"walk-forward: train on {len(wf.train_ids)} past markets, test on {len(wf.test_ids)} later ones")
    _print_board(wf.train_board, "TRAIN (the past)")
    _print_board(wf.test_board, "TEST (the held-out future)")
    print(f"\ntrain winner: {wf.train_winner}   test winner: {wf.test_winner}")
    print(
        "=> the winner generalised"
        if wf.generalised
        else "=> the train winner did NOT lead on the future (overfit risk)"
    )
    return 0


def _cmd_import(args: argparse.Namespace) -> int:
    from pmx.v1.data.importer import ImportError_, import_polymarket

    try:
        path = import_polymarket(args.slug, Path(args.out))
    except ImportError_ as exc:
        print(f"import failed: {exc}")
        return 1
    print(f"wrote {path}")
    return 0


def _cmd_api_serve(args: argparse.Namespace) -> int:
    try:
        import uvicorn

        from pmx.v1.api.app import create_app
    except ImportError as exc:
        print(f"api dependencies missing: {exc}")
        return 1
    uvicorn.run(create_app(args.data), host=args.host, port=args.port)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pmx", description="Prediction-market backtest arena.")
    sub = parser.add_subparsers(dest="command", required=True)

    data_p = sub.add_parser("data", help="dataset management")
    data_sub = data_p.add_subparsers(dest="action", required=True)
    seed_p = data_sub.add_parser("seed", help="write the bundled demo markets to disk")
    seed_p.add_argument("--out", default=DEFAULT_DATA)
    seed_p.set_defaults(func=_cmd_seed)

    bt = sub.add_parser("backtest", help="score every agent on one market")
    bt.add_argument("market", help="path to a market JSON file")
    bt.add_argument("--agents", default=None, help="comma list; default all")
    bt.set_defaults(func=_cmd_backtest)

    to = sub.add_parser("tournament", help="rank agents across all markets")
    to.add_argument("--data", default=DEFAULT_DATA)
    to.add_argument("--agents", default=None)
    to.set_defaults(func=_cmd_tournament)

    wf = sub.add_parser("walkforward", help="pick the best on the past, grade it on the future")
    wf.add_argument("--data", default=DEFAULT_DATA)
    wf.add_argument("--agents", default=None)
    wf.set_defaults(func=_cmd_walkforward)

    im = sub.add_parser("import", help="import a real resolved market from Polymarket (needs network)")
    im.add_argument("slug", help="Polymarket market slug")
    im.add_argument("--out", default=DEFAULT_DATA)
    im.set_defaults(func=_cmd_import)

    api = sub.add_parser("api", help="serve the read-only API")
    api_sub = api.add_subparsers(dest="action", required=True)
    serve = api_sub.add_parser("serve", help="serve with uvicorn")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8175)
    serve.add_argument("--data", default=DEFAULT_DATA)
    serve.set_defaults(func=_cmd_api_serve)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    func = getattr(args, "func", None)
    if func is None:
        parser.print_help()
        return 1
    result = func(args)
    return int(result)


if __name__ == "__main__":
    raise SystemExit(main())
