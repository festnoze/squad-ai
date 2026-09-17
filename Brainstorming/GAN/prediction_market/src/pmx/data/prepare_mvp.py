"""Prepare the exploratory MVP snapshot locally (CONTRACTS_MVP, decisions MVP-2 and MVP-3).

The historical source's byte integrity is checked independently of its obsolete fold counts. The
existing builder then tags and partitions every original market, and the normal strict loader verifies
the derivative. No network request, reconstructed tape, fabricated audit or source edit is involved.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from pmx.data.builder import build_config_from_manifest, build_dataset_from_payloads
from pmx.data.loader import (
    load_dataset,
    load_manifest,
    load_news,
    read_cluster_groups,
    read_json_file,
    reseal_hash,
    verify_dataset_report,
    write_manifest,
)
from pmx.errors import DatasetHashMismatchError, InvalidConfigError, PmxError, SchemaError
from pmx.types import DatasetManifest, sha256_hex

DEFAULT_SOURCE = Path("data/datasets/y2026")
DEFAULT_OUTPUT = Path("data/datasets/mvp2026")
PREPARATION_VERSION = "mvp-offline.v1"


def _source_note(source: Path, manifest: DatasetManifest) -> str:
    """Stable provenance, including the source manifest whose historical split is being replaced."""
    manifest_hash = sha256_hex((source / "manifest.json").read_bytes())
    return (
        f"{PREPARATION_VERSION}; source_name={manifest.name}; "
        f"source_dataset_hash={manifest.dataset_hash}; source_manifest_sha256={manifest_hash}"
    )


def _check_source(source: Path, manifest: DatasetManifest) -> None:
    """Permit obsolete folds, never changed or missing source data."""
    report = verify_dataset_report(source, manifest=manifest)
    if not report.ok:
        raise DatasetHashMismatchError(
            "the MVP source bytes do not match their original manifest",
            **report.to_dict(),
        )
    if manifest.purpose == "showcase" or manifest.providers == ("demo",):
        raise InvalidConfigError("the MVP needs real imported research data", source=manifest.name)
    if (source / "instruments").is_dir() and any((source / "instruments").iterdir()):
        raise InvalidConfigError("the MVP derivative supports binary source data only")


def _market_payloads(source: Path, manifest: DatasetManifest) -> list[Mapping[str, object]]:
    rows: list[Mapping[str, object]] = []
    for path in sorted((source / "markets").glob("*.json")):
        payload = read_json_file(path)
        if not isinstance(payload, dict):
            raise SchemaError("a source market is a JSON object", path=str(path))
        if payload.get("source") != "imported":
            raise InvalidConfigError("the MVP source needs imported tapes", path=str(path))
        rows.append(payload)
    if not rows or len(rows) != manifest.counts.markets:
        raise SchemaError(
            "source market count differs from its manifest",
            actual=len(rows),
            expected=manifest.counts.markets,
        )
    return rows


def prepare_mvp(source: Path, out: Path) -> Path:
    """Build all source markets with corrected folds, or verify the identical existing derivative.

    Source and output must be disjoint directories. Existing output is never overwritten: matching
    provenance is verified, otherwise the caller receives a useful error. A new build is validated in
    a temporary sibling directory and published only when every original market survived. The source
    remains unchanged even on failure. Cohort shortfalls stay in ``manifest.build`` and do not block
    this explicitly exploratory delivery.
    """
    source = source.resolve()
    out = out.resolve()
    if source == out or source in out.parents or out in source.parents:
        raise InvalidConfigError("MVP source and output directories must be disjoint")
    manifest = load_manifest(source)
    _check_source(source, manifest)
    provenance = _source_note(source, manifest)
    if out.exists():
        existing = load_manifest(out)
        if not existing.notes.startswith(provenance + ";"):
            raise InvalidConfigError(
                "existing MVP output has different provenance; choose a new output directory",
                path=str(out),
            )
        load_dataset(out, verify=True)
        return out

    payloads = _market_payloads(source, manifest)
    news = [item.to_dict() for item in load_news(source, manifest=manifest)]
    # Background snapshots are separate files and must retain their publication/revision provenance.
    for path in sorted((source / "wiki_asof").glob("*/*.json")):
        payload = read_json_file(path)
        if not isinstance(payload, dict):
            raise SchemaError("a background snapshot is a JSON object", path=str(path))
        news.append(payload)
    config = replace(build_config_from_manifest(manifest), limit_per_provider=None)
    notes = (
        provenance
        + "; exploratory derivative, not a certified edge; original imported price/trade tapes retained; "
        "daily bars imply one-bar decision latency; historical fills approximate liquidity; "
        "Kalshi USD and Manifold mana must be evaluated separately; cohort coverage targets remain "
        "unmet where reported; taxonomy and news links have not been human-audited"
    )
    source_ids = {str(row["id"]) for row in payloads}
    out.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".mvp-preparing-", dir=out.parent) as temporary:
        staging = Path(temporary) / "dataset"
        result = build_dataset_from_payloads(
            out_dir=staging,
            config=config,
            market_payloads=payloads,
            news_payloads=news,
            clusters=read_cluster_groups(source),
            name="mvp2026",
            notes=notes,
        )
        if set(result.kept_ids) != source_ids:
            raise InvalidConfigError(
                "MVP preparation must retain every source market",
                missing=sorted(source_ids - set(result.kept_ids)),
                removed=dict(result.removed),
            )
        # A pre-existing cluster definition must accompany the split computed from it.
        if (source / "clusters").is_dir():
            shutil.copytree(source / "clusters", staging / "clusters")
            write_manifest(staging, reseal_hash(staging, result.manifest))
        load_dataset(staging, verify=True)
        # Recheck the source after processing, before publishing a derivative with its provenance.
        if _source_note(source, load_manifest(source)) != provenance:
            raise DatasetHashMismatchError("the source manifest changed during MVP preparation")
        _check_source(source, manifest)
        staging.rename(out)
    return out


def main(argv: Sequence[str] | None = None) -> int:
    """``python -m pmx.data.prepare_mvp``: an offline, repeatable setup command."""
    parser = argparse.ArgumentParser(description="Prepare the real MVP dataset offline")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    try:
        path = prepare_mvp(args.source, args.out)
    except (PmxError, OSError) as error:
        print(f"MVP preparation failed: {error}", file=sys.stderr)
        return 1
    manifest = load_manifest(path)
    print(f"MVP dataset ready: {path}")
    print(f"Markets: {manifest.counts.markets}; dataset hash: {manifest.dataset_hash}")
    print(
        f"Folds: train={manifest.split.n_train}, validation={manifest.split.n_validation}, "
        f"sealed={manifest.split.n_sealed}"
    )
    print("Exploratory data only. Cohort coverage and unaudited taxonomy remain visible in the manifest.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
