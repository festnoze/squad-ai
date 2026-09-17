"""Pinned archive acquisition and causal hourly research dataset construction."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence
from pathlib import Path


def _command(args: argparse.Namespace) -> int:
    from pmx.data.importers.polymarket_archive_http import create_inventory, download_archive

    archive = Path(args.archive_dir)
    if args.archive_action == "inventory":
        result = create_inventory(archive)
        print(
            json.dumps(
                {"files": len(result["files"]), "bytes": result["total_bytes"], "revision": result["revision"]}
            )
        )
    elif args.archive_action == "download":
        # Public Xet endpoints stalled in the measured local environment; ordinary
        # HTTPS keeps TLS verification and the hub's resumable download semantics.
        if not args.use_xet:
            os.environ["HF_HUB_DISABLE_XET"] = "1"
        result = download_archive(
            archive,
            max_workers=args.workers,
            start_date=args.start_date,
            end_date=args.end_date,
            skip_ctf=args.skip_ctf,
        )
        print(json.dumps({"verified_files": sum(row["status"] == "verified" for row in result["files"])}))
    elif args.archive_action == "project-ctf":
        from pmx.data.polymarket_archive import epoch_ms
        from pmx.data.polymarket_ctf_projection import create_ctf_projection

        print(create_ctf_projection(archive, end_ms=epoch_ms(args.end_date), cutoff_block=args.cutoff_block))
    else:
        from pmx.data.polymarket_archive import build_archive_dataset

        report = build_archive_dataset(
            archive_dir=archive,
            output_dir=Path(args.output_dir),
            start_date=args.start_date,
            end_date=args.end_date,
            max_markets=args.max_markets,
            rpc_url=args.rpc_url,
            fee_schedule_id=args.fee_schedule_id,
            memory_limit=args.memory_limit,
            ctf_projection_dir=None if args.ctf_projection_dir is None else Path(args.ctf_projection_dir),
        )
        print(json.dumps(report, ensure_ascii=True))
    return 0


def build_parser(parser: argparse.ArgumentParser) -> None:
    actions = parser.add_subparsers(dest="archive_action", required=True)
    inventory = actions.add_parser("inventory", help="record pinned files, published sizes and checksums")
    download = actions.add_parser("download", help="resume and verify the 13.37 GB initial archive selection")
    download.add_argument("--workers", type=int, default=6)
    download.add_argument("--start-date", default=None)
    download.add_argument("--end-date", default=None)
    download.add_argument(
        "--skip-ctf", action="store_true", help="use an explicit CTF projection instead of whole files"
    )
    download.add_argument(
        "--use-xet", action="store_true", help="opt into Xet transfer instead of ordinary verified HTTPS"
    )
    build = actions.add_parser("build", help="build hourly selected-universe tapes and settled research adapter")
    project = actions.add_parser("project-ctf", help="verified range projection with complete historical cutoff")
    project.add_argument("--end-date", default="2024-01-01")
    project.add_argument("--cutoff-block", type=int, default=60_000_000)
    for action in (inventory, download, build, project):
        action.add_argument("--archive-dir", default="data/external/polymarket-v1")
        action.set_defaults(func=_command)
    build.add_argument("--output-dir", required=True)
    build.add_argument("--start-date", default="2025-01-01")
    build.add_argument("--end-date", default="2026-01-01")
    build.add_argument("--max-markets", type=int, default=1500)
    build.add_argument("--rpc-url", default="https://polygon.drpc.org")
    build.add_argument("--fee-schedule-id", default="polymarket-research-2026-04")
    build.add_argument("--memory-limit", default="4GB")
    build.add_argument("--ctf-projection-dir", default=None)


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    build_parser(subparsers.add_parser("archive", help="public pinned Polymarket archive"))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pmx archive")
    build_parser(parser)
    return _command(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
