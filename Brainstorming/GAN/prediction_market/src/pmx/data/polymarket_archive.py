"""A pinned transaction archive, an outcome-blind universe, and a settled-only pmx adapter.

Frozen metadata never supplies a historical question, category, group, fee or expiry.
CTF payouts and actual Polygon block times are separate label evidence. The sparse
hourly tape preserves censored conditions; the legacy Market adapter requires settled
binary labels and is explicitly a conditional historical research sample.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from pmx import CONTRACT_VERSION, DATASET_SCHEMA, MARKET_SCHEMA, __version__
from pmx.data.builder import make_split, market_facts, plan_folds
from pmx.data.importers.polymarket_archive_http import (
    DEFAULT_RPC,
    REPOSITORY,
    REVISION,
    BlockTimestampResolver,
    archive_path,
    verify_entry,
)
from pmx.data.loader import (
    check_market_structure,
    dataset_files,
    dataset_hash_of,
    load_dataset,
    write_canonical_json,
    write_canonical_jsonl,
    write_manifest,
)
from pmx.data.schema import validate_against_schema
from pmx.types import (
    REMOVED_FILTER_KEYS,
    RNG_ALGORITHM_VERSION,
    Bar,
    BuiltBy,
    DatasetCounts,
    DatasetFilters,
    DatasetManifest,
    DatasetNews,
    DatasetWindow,
    Market,
    MarketQuality,
)

HOUR_MS = 3_600_000
DAY_MS = 24 * HOUR_MS
ARCHIVE_MARKER = "pmx-polymarket-archive-v1"
FROZEN_FIELDS = (
    "market_slug",
    "category",
    "category_refined",
    "opens_at",
    "close_at",
    "resolved_at",
    "winning_outcome_label",
    "resolution_status",
    "taker_base_fee",
    "maker_base_fee",
)


def epoch_ms(date: str) -> int:
    return int(datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=UTC).timestamp()) * 1000


def resolution_block(event_id: str) -> int:
    match = re.fullmatch(r"137_([0-9]+)_([0-9]+)", event_id)
    if match is None:
        raise ValueError(f"Malformed Polygon CTF event id: {event_id!r}")
    return int(match.group(1))


def binary_payout(payouts: Sequence[str], slots: int) -> int | None:
    """Only unambiguous, complete reference-leg binary payments enter the adapter."""
    if slots != 2 or len(payouts) != 2:
        return None
    if any(not re.fullmatch(r"[0-9]+", str(value)) for value in payouts):
        raise ValueError("CTF payout numerators must be nonnegative integers")
    first, second = map(int, payouts)
    if first > 0 and second == 0:
        return 1
    if second > 0 and first == 0:
        return 0
    return None


def choose_conditions(population: Sequence[Mapping[str, Any]], max_markets: int) -> list[str]:
    """Stable hash sampling reads condition IDs only, before payout/metadata lookups."""
    if max_markets < 1:
        raise ValueError("max_markets must be positive")
    ids = {str(row["condition_id"]) for row in population}
    return sorted(ids, key=lambda value: (hashlib.sha256(value.encode()).hexdigest(), value))[:max_markets]


def dense_bars(hourly: Sequence[Mapping[str, Any]], end_ms: int) -> tuple[Bar, ...]:
    """Complete hourly OHLC, then zero-volume carry-forward; never backfill before first print.

    A bar is available only at t_ms + HOUR_MS, as enforced by Market.bars_before.
    Last-trade times remain in the sparse evidence tape so every stale interval is measurable.
    """
    if not hourly:
        return ()
    by_hour = {int(row["t_ms"]): row for row in hourly}
    if len(by_hour) != len(hourly):
        raise ValueError("Duplicate hourly aggregate")
    output: list[Bar] = []
    previous: int | None = None
    for instant in range(min(by_hour), end_ms // HOUR_MS * HOUR_MS + 1, HOUR_MS):
        row = by_hour.get(instant)
        if row is None:
            if previous is None:
                raise ValueError("Cannot invent a price before first print")
            values, volume, trades = [previous] * 5, 0, 0
        else:
            values = [int(row[key]) for key in ("open_bp", "high_bp", "low_bp", "close_bp", "vwap_bp")]
            volume, trades = int(row["volume_milli"]), int(row["n_trades"])
            if volume == 0:
                raise ValueError("Positive source trades round to zero contract volume")
        output.append(
            Bar(instant, values[0], values[1], values[2], values[3], values[4], volume, trades, None, None, None)
        )
        previous = values[3]
    return tuple(output)


def _dict_rows(connection: Any, query: str, parameters: Sequence[Any] = ()) -> list[dict[str, Any]]:
    cursor = connection.execute(query, parameters)
    keys = [entry[0] for entry in cursor.description]
    return [dict(zip(keys, row, strict=True)) for row in cursor.fetchall()]


def _paths(
    archive_dir: Path, start_ms: int, end_ms: int, *, projected_ctf: bool = False
) -> tuple[list[str], dict[str, Any]]:
    manifest = json.loads((archive_dir / "download-manifest.json").read_text(encoding="utf-8"))
    if manifest.get("revision") != REVISION or manifest.get("repository") != REPOSITORY:
        raise ValueError("Archive source is not the pinned revision")
    declared_paths = [entry["path"] for entry in manifest["files"]]
    if len(set(declared_paths)) != len(declared_paths):
        raise ValueError("Archive inventory contains duplicate paths")
    if not {"CTF/preparations.parquet", "CTF/resolutions.parquet"}.issubset(declared_paths):
        raise ValueError("Archive inventory must verify both CTF lifecycle files")
    files = []
    used_entries = []
    for entry in manifest["files"]:
        if projected_ctf and entry["path"].startswith("CTF/"):
            continue
        if entry["path"].startswith("daily_aligned/"):
            partition_day = datetime.strptime(Path(entry["path"]).stem, "%Y_%m_%d").replace(tzinfo=UTC)
            partition_ms = int(partition_day.timestamp()) * 1000
            # The publisher describes both UTC and UTC+8 partitioning: include both boundary days.
            # Observation filtering below always uses actual epoch timestamps, never filenames.
            if partition_ms < start_ms - DAY_MS or partition_ms > end_ms + DAY_MS:
                continue
        path = archive_path(archive_dir, entry["path"])
        if not verify_entry(path, entry):
            raise ValueError(f"Required cohort partition is incomplete or corrupt: {entry['path']}")
        used_entries.append({key: value for key, value in entry.items() if key not in ("status", "verified_sha256")})
        if entry["path"].startswith("daily_aligned/"):
            files.append(str(path.resolve()))
    if not files:
        raise ValueError("No verified daily_aligned partitions")
    used_manifest = {key: value for key, value in manifest.items() if key not in ("files", "total_bytes")}
    used_manifest["files"] = sorted(used_entries, key=lambda row: row["path"])
    used_manifest["total_bytes"] = sum(row["bytes"] for row in used_entries)
    used_manifest["full_inventory_total_bytes"] = manifest["total_bytes"]
    used_manifest["selection"] = (
        "CTF lifecycle + daily partitions covering requested UTC window with one-day edge padding"
    )
    return files, used_manifest


def _prepare_views(
    connection: Any, paths: Sequence[str], start_ms: int, end_ms: int, max_markets: int
) -> tuple[list[dict[str, Any]], list[str]]:
    # DuckDB does predicate/column pushdown into local Parquet. No raw tape is copied.
    connection.from_parquet(list(paths), filename=True, file_row_number=True).create_view("source")
    connection.execute(
        "CREATE TEMP TABLE population AS SELECT condition_id, min(block_timestamp)*1000 AS first_trade_ms, "
        "max(block_timestamp)*1000 AS last_trade_ms, count(*) AS source_rows FROM source "
        "WHERE block_timestamp >= ? AND block_timestamp < ? GROUP BY condition_id",
        [start_ms // 1000, end_ms // 1000],
    )
    population = _dict_rows(connection, "SELECT * FROM population ORDER BY condition_id")
    if any(not row["condition_id"] for row in population):
        raise ValueError("Source contains missing condition ids")
    selected = choose_conditions(population, max_markets)
    connection.execute("CREATE TEMP TABLE selected(condition_id VARCHAR PRIMARY KEY)")
    connection.executemany("INSERT INTO selected VALUES (?)", [(condition,) for condition in selected])
    connection.execute(
        "CREATE TEMP TABLE selected_trades AS SELECT s.condition_id,s.block_timestamp,s.price,s.usdc_amount,"
        "s.fee_usdc,s.outcome_seq,s.p_event,s.neg_risk,s.asset_id,s.maker,s.taker,s.taker_direction,"
        "s.outcome_label,s.winning_outcome_label,s.filename,s.file_row_number "
        "FROM source s JOIN selected USING(condition_id) "
        "WHERE block_timestamp >= ? AND block_timestamp < ?",
        [start_ms // 1000, end_ms // 1000],
    )
    return population, selected


def _aggregate(connection: Any) -> dict[str, Any]:
    failures = _dict_rows(
        connection,
        """
        SELECT condition_id, count(*) AS invalid_rows FROM selected_trades
        WHERE price IS NULL OR NOT isfinite(price) OR price <= 0 OR price >= 1
          OR usdc_amount IS NULL OR NOT isfinite(usdc_amount) OR usdc_amount < 0
          OR outcome_seq IS NULL OR outcome_seq NOT IN (1,2)
          OR p_event IS NULL OR NOT isfinite(p_event)
          OR abs(p_event - CASE WHEN outcome_seq=1 THEN price ELSE 1-price END) > 0.0000001
          OR lower(neg_risk) NOT IN ('false','f') OR neg_risk IS NULL
        GROUP BY condition_id
    """,
    )
    # Reject an entire condition visibly, rather than silently repair financial observations.
    connection.execute("CREATE TEMP TABLE invalid_conditions(condition_id VARCHAR PRIMARY KEY)")
    if failures:
        connection.executemany(
            "INSERT INTO invalid_conditions VALUES (?)", [(row["condition_id"],) for row in failures]
        )
    zeros = connection.execute("SELECT count(*) FROM selected_trades WHERE usdc_amount=0").fetchone()[0]
    connection.execute("""CREATE TEMP TABLE clean AS SELECT *,
        CAST(floor(block_timestamp/3600)*3600000 AS BIGINT) AS t_ms,
        CASE WHEN outcome_seq=1 THEN price ELSE 1-price END AS ref_price,
        usdc_amount/price AS shares
        FROM selected_trades ANTI JOIN invalid_conditions USING(condition_id) WHERE usdc_amount > 0""")
    duplicates = connection.execute("""SELECT coalesce(sum(n-1),0) FROM (
        SELECT count(*) n FROM clean GROUP BY condition_id,block_timestamp,asset_id,price,maker,taker,
        taker_direction,usdc_amount,fee_usdc HAVING count(*)>1)""").fetchone()[0]
    connection.execute("""CREATE TEMP TABLE hourly AS SELECT condition_id,t_ms,
        CAST(round(first(ref_price ORDER BY block_timestamp,filename,file_row_number)*10000) AS BIGINT) open_bp,
        CAST(round(max(ref_price)*10000) AS BIGINT) high_bp,
        CAST(round(min(ref_price)*10000) AS BIGINT) low_bp,
        CAST(round(last(ref_price ORDER BY block_timestamp,filename,file_row_number)*10000) AS BIGINT) close_bp,
        CAST(round(sum(ref_price*shares)/sum(shares)*10000) AS BIGINT) vwap_bp,
        CAST(round(sum(shares)*1000) AS BIGINT) volume_milli,
        count(*) AS n_trades,min(block_timestamp)*1000 AS first_trade_ms,
        max(block_timestamp)*1000 AS last_trade_ms,
        CAST(round(sum(usdc_amount)*1000000) AS BIGINT) notional_micro_usdc,
        CAST(round(sum(fee_usdc)*1000000) AS BIGINT) observed_fee_micro_usdc
        FROM clean GROUP BY condition_id,t_ms""")
    connection.execute("CREATE INDEX hourly_condition ON hourly(condition_id)")
    return {
        "invalid_conditions": failures,
        "zero_notional_rows_excluded": zeros,
        "identical_row_excess_retained": duplicates,
        "tie_order": "block_timestamp, pinned filename, file_row_number; economic log order unavailable",
    }


def _labels(connection: Any, archive_dir: Path, ctf_projection_dir: Path | None = None) -> dict[str, dict[str, Any]]:
    for name in ("preparations", "resolutions"):
        ctf_dir = ctf_projection_dir if ctf_projection_dir is not None else archive_dir / "CTF"
        connection.from_parquet(str(ctf_dir / f"{name}.parquet")).create_view(name)
    preparations = _dict_rows(connection, "SELECT p.* FROM preparations p JOIN selected USING(condition_id)")
    resolutions = _dict_rows(connection, "SELECT r.* FROM resolutions r JOIN selected USING(condition_id)")
    prep: dict[str, list[dict[str, Any]]] = {}
    resolution: dict[str, list[dict[str, Any]]] = {}
    for row in preparations:
        prep.setdefault(row["condition_id"], []).append(row)
    for row in resolutions:
        resolution.setdefault(row["condition_id"], []).append(row)
    labels = {}
    for row in _dict_rows(connection, "SELECT condition_id FROM selected ORDER BY condition_id"):
        condition = row["condition_id"]
        ps, rs = prep.get(condition, []), resolution.get(condition, [])
        label: dict[str, Any] = {
            "condition_id": condition,
            "resolution": None,
            "available_at_ms": None,
            "status": "unresolved_or_missing_ctf",
            "preparations": ps,
            "resolutions": rs,
        }
        if len(ps) != 1 or len(rs) > 1:
            label["status"] = "ambiguous_or_missing_ctf_preparation"
        elif rs:
            p, r = ps[0], rs[0]
            if any(p[field] != r[field] for field in ("oracle", "question_id", "outcome_slot_count")):
                raise ValueError(f"CTF preparation/resolution mismatch: {condition}")
            value = binary_payout(r["payout_numerators"], r["outcome_slot_count"])
            label["status"] = "nonbinary_or_ambiguous_payout" if value is None else "pending_timestamp"
            if value is not None:
                label["resolution"] = value
                label["block_number"] = resolution_block(r["id"])
        labels[condition] = label
        if ctf_projection_dir is not None and label["status"] == "unresolved_or_missing_ctf":
            label["status"] = "unresolved_before_projection_cutoff"
    # Cross-check the archive's winning label, but never use its date as availability.
    for row in _dict_rows(
        connection,
        "SELECT DISTINCT condition_id,outcome_seq,outcome_label,winning_outcome_label FROM selected_trades",
    ):
        label = labels[row["condition_id"]]
        winner = row["winning_outcome_label"]
        if label["resolution"] is None or winner is None or str(winner).lower() in ("", "none", "nan", "null"):
            continue
        if str(row["outcome_label"]).strip().lower() == str(winner).strip().lower():
            expected = 1 if row["outcome_seq"] == 1 else 0
            if label["resolution"] != expected:
                raise ValueError(f"Archive winner disagrees with CTF payout: {row['condition_id']}")
    return labels


def settled_market(
    condition: str, hourly: Sequence[Mapping[str, Any]], label: Mapping[str, Any], fee_schedule_id: str
) -> Market:
    resolved = int(label["available_at_ms"])
    # Exclude the entire settlement hour: its OHLC can contain post-settlement prints.
    observations = [row for row in hourly if int(row["t_ms"]) + HOUR_MS <= resolved]
    if not observations:
        raise ValueError("no_completed_preresolution_hour")
    bars = dense_bars(observations, resolved)
    if len(bars) < 2:
        raise ValueError("fewer_than_two_hourly_bars")
    if any(
        not 1 <= getattr(bar, name) <= 9999
        for bar in bars
        for name in ("open_bp", "high_bp", "low_bp", "close_bp", "vwap_bp")
    ):
        raise ValueError("price_outside_legacy_basis_point_range")
    market = Market(
        schema_version=MARKET_SCHEMA,
        id=f"polymarket-{condition}",
        provider="polymarket",
        provider_id=condition,
        url="",
        question=f"Polygon condition {condition}, reference outcome 1",
        description="",
        category="other",
        tags=(),
        wiki_subjects=(),
        currency="usdc",
        source="imported",
        created_at_ms=int(observations[0]["first_trade_ms"]),
        close_at_ms=resolved,
        resolved_at_ms=resolved,
        resolution=int(label["resolution"]),
        resolution_source="Polygon CTF ConditionResolution + public block timestamp",
        event_key=None,
        interval_min=60,
        bars=bars,
        trades=(),
        first_price_bp=bars[0].open_bp,
        final_price_bp=bars[-1].close_bp,
        hardness_tags=(),
        quality=MarketQuality(
            sum(bar.n_trades for bar in bars),
            None,
            (resolved - int(observations[0]["first_trade_ms"])) // DAY_MS,
            sum(bar.volume_milli for bar in bars),
            sum(bar.n_trades > 0 for bar in bars),
        ),
        fee_schedule_id=fee_schedule_id,
        close_time_verified=False,
        notes=f"{ARCHIVE_MARKER}; historical_close_unknown; close_at_ms is an internal settlement boundary, "
        "not a historical expiry forecast. Sparse evidence and censoring in archive/. "
        "No order book, news, verified event groups, or historical fee schedule. "
        "Zero-volume carried bars are stale observations, not executable quotes.",
    )
    validate_against_schema("market.v2.json", market.to_dict(), where=market.id)
    check_market_structure(market, manifest=None)
    return market


def build_archive_dataset(
    *,
    archive_dir: Path,
    output_dir: Path,
    start_date: str = "2025-01-01",
    end_date: str = "2026-01-01",
    max_markets: int = 1500,
    rpc_url: str = DEFAULT_RPC,
    fee_schedule_id: str = "polymarket-research-2026-04",
    memory_limit: str = "4GB",
    timestamp_resolver: Callable[[int], dict[str, Any]] | None = None,
    ctf_projection_dir: Path | None = None,
    progress: Callable[[str], None] = print,
) -> dict[str, Any]:
    import duckdb

    start_ms, end_ms = epoch_ms(start_date), epoch_ms(end_date)
    if not 0 < end_ms - start_ms <= 730 * DAY_MS:
        raise ValueError("Archive cohort must span between one day and 730 days")
    if (output_dir / "manifest.json").exists():
        raise ValueError("Output dataset already exists; choose a new directory")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("Output directory must be empty; source downloads and block evidence resume separately")
    progress("Verifying pinned local source checksums")
    projection = None
    if ctf_projection_dir is not None:
        from pmx.data.polymarket_ctf_projection import load_ctf_projection

        projection = load_ctf_projection(ctf_projection_dir, end_ms=end_ms)
        inventory = json.loads((archive_dir / "download-manifest.json").read_text(encoding="utf-8"))
        originals = {entry["path"]: entry for entry in inventory["files"] if entry["path"].startswith("CTF/")}
        for projected in projection["source_objects"]:
            original = originals.get(projected["path"])
            if original is None or any(original[key] != projected[key] for key in ("path", "bytes", "sha256")):
                raise ValueError("CTF projection object does not match the archive's pinned source inventory")
    paths, source_manifest = _paths(archive_dir, start_ms, end_ms, projected_ctf=projection is not None)
    if projection is not None:
        source_manifest["ctf_projection"] = projection
        source_manifest["total_bytes"] += projection["downloaded_range_bytes"]
    output_dir.mkdir(parents=True, exist_ok=True)
    evidence = output_dir / "archive"
    evidence.mkdir(exist_ok=True)
    if projection is not None and ctf_projection_dir is not None:
        for entry in projection["artifacts"]:
            destination = evidence / "ctf-projection" / entry["path"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ctf_projection_dir / entry["path"], destination)
        write_canonical_json(evidence / "ctf-projection" / "projection-manifest.json", projection)
    con = duckdb.connect(str(output_dir / "archive-build.duckdb"))
    try:
        con.execute("SET memory_limit = ?", [memory_limit])
        con.execute("SET threads = 4")
        progress("Selecting conditions by stable identifier hash, before reading labels")
        population, selected = _prepare_views(con, paths, start_ms, end_ms, max_markets)
        if not selected:
            raise ValueError("No condition traded in the requested window")
        progress(f"Aggregating hourly observations for {len(selected)} / {len(population)} conditions")
        quality = _aggregate(con)
        labels = _labels(con, archive_dir, ctf_projection_dir)
        blocks = sorted({row["block_number"] for row in labels.values() if row["status"] == "pending_timestamp"})
        resolver = timestamp_resolver or BlockTimestampResolver(archive_dir / "block-timestamps", rpc_url)
        progress(f"Verifying {len(blocks)} actual Polygon resolution block timestamps")
        # A transport/data failure stops the build; it must not silently change the eligible sample.
        with ThreadPoolExecutor(max_workers=8) as pool:
            resolved_blocks = dict(zip(blocks, pool.map(resolver, blocks), strict=True))
        for block, block_evidence in resolved_blocks.items():
            write_canonical_json(evidence / "blocks" / f"137_{block}.json", block_evidence)
        for label in labels.values():
            if label["status"] == "pending_timestamp":
                label["available_at_ms"] = resolved_blocks[label["block_number"]]["timestamp_ms"]
                label["status"] = "resolved" if label["available_at_ms"] < end_ms else "right_censored_at_window_end"
        # Sparse factual bars for ALL selected valid conditions, including unresolved/censored.
        parquet_path = str((evidence / "hourly.parquet").resolve()).replace("'", "''")
        con.execute(f"COPY (SELECT * FROM hourly ORDER BY condition_id,t_ms) TO '{parquet_path}' (FORMAT PARQUET)")
        provenance = _dict_rows(
            con,
            "SELECT condition_id,filename,count(*) source_rows,min(file_row_number) first_source_row, "
            "max(file_row_number) last_source_row FROM selected_trades GROUP BY condition_id,filename "
            "ORDER BY condition_id,filename",
        )
        for row in provenance:
            row["filename"] = Path(row["filename"]).relative_to(archive_dir.resolve()).as_posix()
        write_canonical_jsonl(evidence / "source-ranges.jsonl", provenance)
        invalid = {row["condition_id"] for row in quality["invalid_conditions"]}
        selected_set = set(selected)
        universe = []
        markets = []
        exclusions: Counter[str] = Counter()
        for entry in population:
            condition = entry["condition_id"]
            row = {**entry, "selected": condition in selected_set, "group_id": None}
            if condition not in selected_set:
                row["adapter_status"] = "outside_identifier_hash_cap"
            else:
                label = labels[condition]
                reason = "invalid_source_rows" if condition in invalid else label["status"]
                if reason == "resolved":
                    hourly = _dict_rows(con, "SELECT * FROM hourly WHERE condition_id=? ORDER BY t_ms", [condition])
                    try:
                        market = settled_market(condition, hourly, label, fee_schedule_id)
                    except ValueError as error:
                        reason = str(error)
                        if reason not in (
                            "no_completed_preresolution_hour",
                            "fewer_than_two_hourly_bars",
                            "price_outside_legacy_basis_point_range",
                        ):
                            raise
                    else:
                        markets.append(market)
                        reason = "included_settled_adapter"
                row["adapter_status"] = reason
                if reason != "included_settled_adapter":
                    exclusions[reason] += 1
            universe.append(row)
        write_canonical_jsonl(evidence / "universe.jsonl", universe)
        write_canonical_jsonl(evidence / "labels.jsonl", [labels[key] for key in sorted(labels)])
        report = {
            "schema": "pmx.polymarket-archive-coverage.v1",
            "dataset": output_dir.name,
            "repository": REPOSITORY,
            "revision": REVISION,
            "license": "CC-BY-4.0",
            "attribution": source_manifest["attribution"],
            "archive_marker": ARCHIVE_MARKER,
            "start_ms": start_ms,
            "end_ms": end_ms,
            "interval_min": 60,
            "source_files": len(paths),
            "source_bytes": source_manifest["total_bytes"],
            "ctf_source_mode": "range_projection" if projection is not None else "whole_files_sha256",
            "ctf_projection": None
            if projection is None
            else {
                "cutoff_block": projection["cutoff_block"],
                "cutoff_timestamp_ms": projection["cutoff_timestamp_ms"],
                "downloaded_range_bytes": projection["downloaded_range_bytes"],
                "verification": projection["verification"],
                "completeness": projection["completeness"],
            },
            "full_archive_inventory_bytes": source_manifest["full_inventory_total_bytes"],
            "source_scope": (
                "Verified pinned partitions covering this cohort window; full archive download independent"
            ),
            "population_conditions": len(population),
            "population_source_rows": sum(row["source_rows"] for row in population),
            "selected_conditions": len(selected),
            "selected_source_rows": sum(
                row["source_rows"] for row in population if row["condition_id"] in selected_set
            ),
            "selected_observed_hours": _dict_rows(con, "SELECT count(*) AS n FROM hourly")[0]["n"],
            "settled_adapter_markets": len(markets),
            "exclusions": dict(sorted(exclusions.items())),
            "label_status_counts": dict(Counter(label["status"] for label in labels.values())),
            "selection": (
                "SHA256(condition_id), first max_markets; active transactions in fixed UTC window; "
                "no outcome/price filters"
            ),
            "population_scope": (
                "Traded conditions in the archive; never-traded markets and metadata-join losses are unknown"
            ),
            "adapter_scope": (
                "Settled historical research selection; unresolved and censored observations "
                "preserved in archive/hourly.parquet"
            ),
            "quality": quality,
            "frozen_metadata_excluded_from_features": list(FROZEN_FIELDS),
            "known_historical_close": False,
            "metadata_verification": {
                "historical_question": False,
                "historical_category": False,
                "historical_expiry": False,
                "resolution_payout": "CTF preparation/resolution oracle, question and slots matched",
                "label_availability": "Exact Polygon block timestamp; no interpolation or archive date substitution",
            },
            "verified_event_groups": 0,
            "event_group_policy": (
                "Unknown; condition IDs are not independent event groups. Cross-market dependence remains unverified."
            ),
            "news_items": 0,
            "order_book_available": False,
            "historical_fee_schedule_known": False,
            "fee_schedule_id": fee_schedule_id,
            "fee_policy": "Explicit research scenario; source observed fees are descriptive only",
            "volume_policy": (
                "Sum of USDC.e notional / raw outcome price, in 1/1000 shares; "
                "archive cleaned fills, no deduplication guessed"
            ),
            "timing_policy": (
                "Epoch seconds converted to UTC; completed hourly bars only; settlement hour excluded from adapter"
            ),
            "provenance_policy": (
                "Pinned filename and zero-based file_row_number; "
                "source-ranges locate all contributing rows, no economic trade ID"
            ),
            "missing_hours_policy": (
                "Legacy adapter carries previous close with zero volume; sparse evidence retains last_trade_ms"
            ),
            "validation_policy": (
                "Chronological resolution folds; sealed held out; "
                "unknown cross-condition groups prevent independence certification"
            ),
        }
        if not markets:
            write_canonical_json(evidence / "coverage.json", report)
            raise ValueError("No verified settled market available; coverage and censored universe preserved")
        progress(f"Writing {len(markets)} settled hourly markets and sealed-fold allocation")
        _write_adapter(output_dir, markets, report, source_manifest, start_ms, end_ms)
        return report
    finally:
        con.close()


def _write_adapter(
    output_dir: Path,
    markets: Sequence[Market],
    report: dict[str, Any],
    source_manifest: Mapping[str, Any],
    start_ms: int,
    end_ms: int,
) -> None:
    facts = [market_facts(market.to_dict()) for market in markets]
    plan = plan_folds(facts, interval_min=60, window_start_ms=start_ms, clusters={})
    split = make_split(window_start_ms=start_ms, plan=plan)
    for market in markets:
        write_canonical_json(output_dir / "markets" / f"{market.id}.json", market.to_dict())
    report["folds"] = {"train": split.n_train, "validation": split.n_validation, "sealed": split.n_sealed}
    report["train_end_ms"], report["validation_end_ms"] = split.train_end_ms, split.validation_end_ms
    report["adapter_bars"] = sum(len(market.bars) for market in markets)
    report["adapter_observed_hours"] = sum(market.quality.traded_bars for market in markets)
    write_canonical_json(output_dir / "archive" / "coverage.json", report)
    write_canonical_json(output_dir / "archive" / "source-manifest.json", dict(source_manifest))
    freeze = datetime.fromtimestamp(end_ms / 1000, tz=UTC) + timedelta(days=2)
    days = (end_ms - start_ms) // DAY_MS + 2
    files = dataset_files(output_dir)
    if not any(entry.path == "archive/coverage.json" for entry in files):
        raise ValueError("Loader HASHED_DIRS must include archive before writing this dataset")
    manifest = DatasetManifest(
        schema_version=DATASET_SCHEMA,
        name=output_dir.name,
        freeze_date=freeze.strftime("%Y-%m-%d"),
        freeze_ms=int(freeze.timestamp()) * 1000,
        window=DatasetWindow(start_ms, end_ms),
        interval_min=60,
        providers=("polymarket",),
        safety_lag_ms=0,
        filters=DatasetFilters(
            {"window_days": days, "archive_marker": ARCHIVE_MARKER}, dict.fromkeys(REMOVED_FILTER_KEYS, 0)
        ),
        counts=DatasetCounts(
            len(markets),
            {"polymarket": len(markets)},
            {"other": len(markets)},
            sum(m.resolution for m in markets),
            sum(1 - m.resolution for m in markets),
            {},
        ),
        news=DatasetNews((), 0, 0),
        split=split,
        files=files,
        dataset_hash=dataset_hash_of(files),
        built_by=BuiltBy(__version__, CONTRACT_VERSION, RNG_ALGORITHM_VERSION),
        sealed=False,
        purpose="research",
        window_days=days,
        notes=f"{ARCHIVE_MARKER}; settled historical research selection. "
        "Censored universe, timestamp evidence and limitations "
        "are hashed in archive/. Actual expiry unavailable; internal close field is not an as-of feature. "
        "No news, order book or verified cross-condition event groups. Explicit research fee scenario.",
    )
    validate_against_schema("dataset.v1.json", manifest.to_dict(), where="archive manifest")
    write_manifest(output_dir, manifest)
    load_dataset(output_dir, verify=True)
