"""Explicit partial-object CTF projection with a complete, proven historical block cutoff.

All ID column chunks are read, so variable-width decimal block IDs cannot invalidate
lexicographic footer pruning. Only the first row group's other columns are fetched.
These artifacts never masquerade as whole-source files verified by their LFS hash.
"""

from __future__ import annotations

import json
import re
import struct
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from pmx.data.importers.polymarket_archive_http import (
    REPOSITORY,
    REVISION,
    BlockTimestampResolver,
    archive_path,
    atomic_json,
    cached_range,
    sha256_file,
)


def validate_omitted_groups(metadata: Sequence[Mapping[str, Any]], cutoff_block: int) -> None:
    for row in metadata:
        if row["path_in_schema"] != "id":
            continue
        values = []
        for key in ("stats_min_value", "stats_max_value"):
            match = re.fullmatch(r"137_([0-9]{8})_[0-9]+", str(row[key]))
            if match is None:
                raise ValueError("CTF footer has ambiguous chain/block-width bounds")
            values.append(int(match.group(1)))
        if values[0] > values[1]:
            raise ValueError("CTF footer has reversed numeric block bounds")
        if row["row_group_id"] != 0 and values[0] < cutoff_block:
            raise ValueError("Omitted CTF row group overlaps the declared block cutoff")


def _rows(connection: Any, sql: str, args: Sequence[Any] = ()) -> list[dict[str, Any]]:
    cursor = connection.execute(sql, args)
    return [dict(zip([item[0] for item in cursor.description], row, strict=True)) for row in cursor.fetchall()]


def create_ctf_projection(
    archive_dir: Path, *, end_ms: int, cutoff_block: int = 60_000_000, progress: Callable[[str], None] = print
) -> Path:
    import duckdb

    if not 10_000_000 <= cutoff_block < 100_000_000:
        raise ValueError("This projection requires an eight-digit Polygon block cutoff")
    directory = archive_dir / ".projections" / f"ctf-before-{cutoff_block}"
    if (directory / "projection-manifest.json").exists():
        load_ctf_projection(directory, end_ms=end_ms)
        return directory
    inventory = json.loads((archive_dir / "download-manifest.json").read_text(encoding="utf-8"))
    if inventory["revision"] != REVISION or inventory["repository"] != REPOSITORY:
        raise ValueError("Projection inventory does not identify the pinned source")
    block = BlockTimestampResolver(archive_dir / "block-timestamps")(cutoff_block)
    if block["timestamp_ms"] <= end_ms:
        raise ValueError("Projection cutoff must be after the entire requested observation window")
    directory.mkdir(parents=True, exist_ok=True)
    atomic_json(directory / "cutoff-block.json", block)
    work: dict[str, dict[str, Any]] = {}
    jobs: list[tuple[str, int, int, int]] = []
    connection = duckdb.connect()
    for name in ("preparations", "resolutions"):
        entry = next(row for row in inventory["files"] if row["path"] == f"CTF/{name}.parquet")
        total = int(entry["bytes"])
        tail_path, tail_receipt = cached_range(
            entry["path"],
            start=max(0, total - 65536),
            end=total - 1,
            total=total,
            cache_dir=directory / name / "ranges",
        )
        tail = tail_path.read_bytes()
        footer_size = struct.unpack("<I", tail[-8:-4])[0] + 8
        if tail[-4:] != b"PAR1" or footer_size > len(tail):
            raise ValueError("Projection footer is not complete Parquet metadata")
        footer_path = directory / name / "footer-only.parquet"
        footer_path.write_bytes(b"PAR1" + tail[-footer_size:])
        metadata = _rows(
            connection,
            "SELECT row_group_id,row_group_num_rows,path_in_schema,stats_min_value,"
            "stats_max_value,total_compressed_size,data_page_offset,dictionary_page_offset "
            "FROM parquet_metadata(?)",
            [str(footer_path)],
        )
        validate_omitted_groups(metadata, cutoff_block)
        atomic_json(directory / name / "row-groups.json", metadata)
        group_end = max(
            int(row["dictionary_page_offset"] or row["data_page_offset"]) + int(row["total_compressed_size"])
            for row in metadata
            if row["row_group_id"] == 0
        )
        spans = [(start, min(start + 1_048_576, group_end) - 1) for start in range(0, group_end, 1_048_576)]
        for row in metadata:
            if row["path_in_schema"] == "id" and row["row_group_id"] != 0:
                start = int(row["dictionary_page_offset"] or row["data_page_offset"])
                spans.append((start, start + int(row["total_compressed_size"]) - 1))
        jobs.extend((name, start, end, total) for start, end in spans)
        work[name] = {
            "entry": entry,
            "total": total,
            "tail": tail_path,
            "footer_size": footer_size,
            "etag": tail_receipt["etag"],
            "spans": spans,
        }
    progress(
        f"CTF projection: {len(jobs)} fragments, {sum(end - start + 1 for _, start, end, _ in jobs):,} bytes; "
        "all ID columns plus the complete first row group"
    )

    def fetch(job: tuple[str, int, int, int]) -> tuple[str, Path, dict[str, Any]]:
        name, start, end, total = job
        path, receipt = cached_range(
            f"CTF/{name}.parquet", start=start, end=end, total=total, cache_dir=directory / name / "ranges"
        )
        if receipt["etag"] != work[name]["etag"]:
            raise ValueError("CTF range ETag changed between footer and data fragments")
        return name, path, receipt

    with ThreadPoolExecutor(max_workers=8) as pool:
        pending = [pool.submit(fetch, job) for job in jobs]
        for index, future in enumerate(as_completed(pending), 1):
            name, _, receipt = future.result()
            progress(f"CTF fragment {index}/{len(jobs)} verified: {name} {receipt['content_range']}")
    projected_counts = {}
    for name, item in work.items():
        # Temporary sparse logical source, outside the evidence namespace copied into datasets.
        sparse = archive_dir / f".ctf-{name}-projection-work.parquet"
        with sparse.open("wb") as stream:
            for start, end in item["spans"]:
                stream.seek(start)
                stream.write((directory / name / "ranges" / f"{start}-{end}.bin").read_bytes())
            stream.seek(item["total"] - item["footer_size"])
            stream.write(item["tail"].read_bytes()[-item["footer_size"] :])
        connection.from_parquet(str(sparse)).create_view("ctf_source", replace=True)
        bad = _rows(
            connection,
            "SELECT count(*) AS n FROM ctf_source "
            "WHERE NOT regexp_full_match(id,'137_[0-9]{8}_[0-9]+') OR id IS NULL",
        )[0]["n"]
        if bad:
            raise ValueError("Actual CTF IDs have mixed widths/chains; footer pruning is not proven")
        # Count by a numeric predicate over every ID chunk, then compare to the pruned output.
        before = _rows(
            connection,
            "SELECT count(*) AS n FROM ctf_source WHERE CAST(split_part(id,'_',2) AS BIGINT) < ?",
            [cutoff_block],
        )[0]["n"]
        output = directory / f"{name}.parquet"
        if output.exists():
            output.unlink()
        connection.sql(f"SELECT * FROM ctf_source WHERE id < '137_{cutoff_block}_'").write_parquet(str(output))
        after = _rows(connection, "SELECT count(*) AS n FROM read_parquet(?)", [str(output)])[0]["n"]
        if before != after:
            raise ValueError("Pruned CTF projection lost rows before the cutoff")
        projected_counts[name] = after
        sparse.unlink()
    connection.close()
    artifacts: list[dict[str, Any]] = [
        {"path": path.relative_to(directory).as_posix(), "bytes": path.stat().st_size, "sha256": sha256_file(path)}
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    ]
    manifest = {
        "schema": "pmx.ctf-range-projection.v1",
        "repository": REPOSITORY,
        "revision": REVISION,
        "cutoff_block": cutoff_block,
        "cutoff_timestamp_ms": block["timestamp_ms"],
        "requested_end_ms": end_ms,
        "counts": projected_counts,
        "artifacts": artifacts,
        "source_objects": [
            {key: value for key, value in item["entry"].items() if key not in ("status", "verified_sha256")}
            for item in work.values()
        ],
        "downloaded_range_bytes": sum(row["bytes"] for row in artifacts if row["path"].endswith(".bin")),
        "verification": "Pinned HTTPS ranges + stable ETags + all-ID completeness audit; whole LFS hash not verified",
        "completeness": "Every source ID is chain 137 with eight block digits; all numerically earlier IDs "
        "are retained. No omitted row group overlaps the cutoff.",
    }
    atomic_json(directory / "projection-manifest.json", manifest)
    return directory


def load_ctf_projection(directory: Path, *, end_ms: int) -> dict[str, Any]:
    import duckdb

    manifest = json.loads((directory / "projection-manifest.json").read_text(encoding="utf-8"))
    if (
        manifest.get("schema") != "pmx.ctf-range-projection.v1"
        or manifest["repository"] != REPOSITORY
        or manifest["revision"] != REVISION
        or manifest["cutoff_timestamp_ms"] <= end_ms
    ):
        raise ValueError("CTF projection does not cover the requested pinned observation window")
    objects = {entry["path"]: entry for entry in manifest["source_objects"]}
    if (
        set(objects) != {"CTF/preparations.parquet", "CTF/resolutions.parquet"}
        or len(manifest["source_objects"]) != 2
    ):
        raise ValueError("Projection must identify both original CTF source objects")
    for entry in objects.values():
        if (
            not isinstance(entry["bytes"], int)
            or entry["bytes"] <= 0
            or not re.fullmatch("[0-9a-f]{64}", entry["sha256"])
        ):
            raise ValueError("Projection source object is missing its published size/hash")
    names = [entry["path"] for entry in manifest["artifacts"]]
    actual = {
        path.relative_to(directory).as_posix()
        for path in directory.rglob("*")
        if path.is_file() and path.name != "projection-manifest.json"
    }
    mandatory = {"preparations.parquet", "resolutions.parquet", "cutoff-block.json"}
    mandatory |= {
        f"{name}/{file}"
        for name in ("preparations", "resolutions")
        for file in ("footer-only.parquet", "row-groups.json")
    }
    if (
        len(set(name.casefold() for name in names)) != len(names)
        or not mandatory.issubset(names)
        or set(names) != actual
    ):
        raise ValueError(
            "Projection manifest must inventory every artifact, including both CTF tables and cutoff evidence"
        )
    for entry in manifest["artifacts"]:
        path = archive_path(directory, entry["path"])
        if not path.is_file() or path.stat().st_size != entry["bytes"] or sha256_file(path) != entry["sha256"]:
            raise ValueError(f"CTF projection artifact failed its retained hash: {entry['path']}")
    block = json.loads((directory / "cutoff-block.json").read_text(encoding="utf-8"))
    rpc = block["rpc_response"]["result"]
    if (
        block["chain_id"] != 137
        or block["block_number"] != manifest["cutoff_block"]
        or int(rpc["number"], 16) != manifest["cutoff_block"]
        or int(rpc["timestamp"], 16) * 1000 != manifest["cutoff_timestamp_ms"]
        or block["timestamp_ms"] != manifest["cutoff_timestamp_ms"]
        or block["block_hash"] != rpc["hash"]
        or not str(block["source_url"]).startswith("https://")
    ):
        raise ValueError("Projection cutoff does not match its retained Polygon block evidence")
    for name in ("preparations", "resolutions"):
        validate_omitted_groups(
            json.loads((directory / name / "row-groups.json").read_text(encoding="utf-8")), manifest["cutoff_block"]
        )
        fragments = [path for path in names if path.startswith(f"{name}/ranges/") and path.endswith(".bin")]
        if not fragments:
            raise ValueError("Projection has no retained source ranges")
        etags = set()
        for relative in fragments:
            receipt = json.loads((directory / relative).with_suffix(".json").read_text(encoding="utf-8"))
            start, end = map(int, Path(relative).stem.split("-"))
            total = objects[f"CTF/{name}.parquet"]["bytes"]
            if (
                receipt["revision"] != REVISION
                or receipt["status"] != 206
                or not receipt["etag"]
                or receipt["sha256"] != sha256_file(directory / relative)
                or receipt["bytes"] != (directory / relative).stat().st_size
                or not 0 <= start <= end < total
                or receipt["bytes"] != end - start + 1
                or receipt["content_range"] != f"bytes {start}-{end}/{total}"
                or receipt["url"]
                != f"https://huggingface.co/datasets/{REPOSITORY}/resolve/{REVISION}/CTF/{name}.parquet"
            ):
                raise ValueError("Projection range receipt does not match the pinned fragment")
            etags.add(receipt["etag"])
        if len(etags) != 1:
            raise ValueError("Projection fragments do not share an object ETag")
        with duckdb.connect() as connection:
            count = _rows(
                connection, "SELECT count(*) AS n FROM read_parquet(?)", [str(directory / f"{name}.parquet")]
            )[0]["n"]
            if count != manifest["counts"][name]:
                raise ValueError("Projection row count differs from retained completeness evidence")
    return dict(manifest)
