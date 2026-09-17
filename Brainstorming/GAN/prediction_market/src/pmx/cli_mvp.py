"""Run the complete local MVP with ``python -m pmx.cli_mvp serve`` or a bounded CLI experiment."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

import uvicorn

from pmx.analysis.campaign import read_object
from pmx.api.analyses import AnalysisService
from pmx.api.app import create_app
from pmx.api.campaigns import campaign_config, persist_campaign_run
from pmx.api.catalogue import Catalogue
from pmx.api.models import CampaignRequest, RunRequest
from pmx.api.service import execute_run
from pmx.errors import PmxError
from pmx.optimizer.discovery import campaign_id_for, run_campaign


def _handle(args: argparse.Namespace) -> int:
    root, runs = Path(args.dataset_root), Path(args.runs_dir)
    if args.mvp_action == "serve":
        uvicorn.run(
            create_app(dataset_root=root, runs_dir=runs, web_dist=Path(args.web_dist)),
            host="127.0.0.1",
            port=args.port,
        )
        return 0
    if args.mvp_action == "search":
        campaign = CampaignRequest.model_validate({
            "dataset": args.dataset, "provider": args.provider, "seed": args.seed,
            "n_trials": args.n_trials, "max_markets": args.max_markets,
            "bankroll_cents": args.bankroll_cents, "n_splits": args.n_splits,
            "finalists": args.finalists,
        })
        dataset = Catalogue(root).load(campaign.dataset)
        config = campaign_config(campaign)
        record = runs / "campaigns" / campaign_id_for(dataset, config) / "campaign.json"
        cached = record.exists() and read_object(record).get("status") == "completed"
        result = run_campaign(
            dataset, config,
            output_dir=runs / "campaigns", runs_dir=runs, on_run=persist_campaign_run,
        )
        if not cached:
            analyses = AnalysisService(root, runs)
            try:
                analyses.enqueue_auto(result)
            finally:
                analyses.close()
        print(json.dumps(result, ensure_ascii=True))
        return 1 if result["status"] == "failed" else 0
    request = RunRequest.model_validate(
        {
            "dataset": args.dataset,
            "provider": args.provider,
            "fold": args.fold,
            "seed": args.seed,
            "bankroll_cents": args.bankroll_cents,
            "max_markets": args.max_markets,
            **({"agent_ids": args.agents} if args.agents is not None else {}),
        }
    )
    detail = execute_run(Catalogue(root).load(request.dataset), request, runs)
    # Escaping Unicode keeps the JSON usable even in Windows shells with a legacy code page.
    print(json.dumps(detail, ensure_ascii=True))
    return 0


def _command(args: argparse.Namespace) -> int:
    try:
        return _handle(args)
    except (PmxError, ValueError, KeyError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


def build_parser(parser: argparse.ArgumentParser) -> None:
    actions = parser.add_subparsers(dest="mvp_action", required=True)
    serve = actions.add_parser("serve", help="serve the local MVP UI and API")
    serve.add_argument("--port", type=int, default=8175)
    serve.add_argument("--web-dist", default="web/dist")
    run = actions.add_parser("run", help="run a bounded exploratory experiment")
    run.add_argument("--dataset", default="mvp2026")
    run.add_argument("--provider", choices=("kalshi", "manifold", "polymarket"), required=True)
    run.add_argument("--fold", choices=("train", "validation"), default="validation")
    run.add_argument("--agents", nargs="+", default=None)
    run.add_argument("--seed", type=int, default=7)
    run.add_argument("--bankroll-cents", type=int, default=100_000)
    run.add_argument("--max-markets", type=int, default=12)
    search = actions.add_parser("search", help="discover rules and parameters on chronological training windows")
    search.add_argument("--dataset", default="polyarchive2023")
    search.add_argument("--provider", choices=("kalshi", "manifold", "polymarket"), default="polymarket")
    search.add_argument("--seed", type=int, default=7)
    search.add_argument("--bankroll-cents", type=int, default=100_000)
    search.add_argument("--max-markets", type=int, default=60)
    search.add_argument("--n-trials", type=int, default=30)
    search.add_argument("--n-splits", type=int, default=3)
    search.add_argument("--finalists", type=int, default=3)
    for action in (serve, run, search):
        action.add_argument("--dataset-root", default="data/datasets")
        action.add_argument("--runs-dir", default="runs/mvp")
        action.set_defaults(func=_command)


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    build_parser(subparsers.add_parser("mvp", help="local research workbench"))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pmx mvp")
    build_parser(parser)
    args = parser.parse_args(argv)
    return _command(args)


if __name__ == "__main__":
    raise SystemExit(main())
