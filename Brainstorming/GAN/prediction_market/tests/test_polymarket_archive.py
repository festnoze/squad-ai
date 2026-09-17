from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from pmx.data.importers.polymarket_archive_http import (
    REPOSITORY,
    REVISION,
    archive_path,
    download_archive,
    validate_range_response,
    verify_entry,
)
from pmx.data.loader import load_dataset
from pmx.data.polymarket_archive import (
    HOUR_MS,
    _paths,
    binary_payout,
    build_archive_dataset,
    choose_conditions,
    dense_bars,
    epoch_ms,
    resolution_block,
    settled_market,
)
from pmx.data.polymarket_ctf_projection import validate_omitted_groups


def hourly(instant: int, price: int = 4000) -> dict[str, int]:
    return {
        "t_ms": instant,
        "open_bp": price,
        "high_bp": price,
        "low_bp": price,
        "close_bp": price,
        "vwap_bp": price,
        "volume_milli": 2000,
        "n_trades": 1,
        "first_trade_ms": instant + 1000,
        "last_trade_ms": instant + 1000,
    }


def test_causal_hourly_grid_and_settlement_hour_exclusion() -> None:
    start = epoch_ms("2025-01-01")
    observations = [hourly(start), hourly(start + 2 * HOUR_MS, 7000), hourly(start + 3 * HOUR_MS, 9999)]
    label = {"available_at_ms": start + 3 * HOUR_MS + 1000, "resolution": 1}
    market = settled_market("0xabc", observations, label, "polymarket-research-2026-04")
    assert market.bars_before(start + HOUR_MS - 1, 20) == ()
    assert market.bars_before(start + HOUR_MS, 20)[0].close_bp == 4000
    assert market.bars[1].volume_milli == 0
    assert market.bars[1].n_trades == 0
    assert market.bars[-1].close_bp == 7000
    assert market.bars[-1].yes_bid_bp is None
    assert market.event_key is None and market.tags == ()
    assert "historical_close_unknown" in market.notes


def test_reference_ctf_payout_and_block_validation() -> None:
    assert binary_payout(["1", "0"], 2) == 1
    assert binary_payout(["0", "2"], 2) == 0
    assert binary_payout(["1", "1"], 2) is None
    assert binary_payout(["0", "0"], 2) is None
    assert resolution_block("137_654321_42") == 654321
    with pytest.raises(ValueError):
        resolution_block("1_654321_42")
    with pytest.raises(ValueError):
        binary_payout(["-1", "1"], 2)


def test_projection_refuses_an_omitted_group_that_can_contain_earlier_events() -> None:
    row = {
        "row_group_id": 1,
        "path_in_schema": "id",
        "stats_min_value": "137_50000000_1",
        "stats_max_value": "137_80000000_1",
    }
    with pytest.raises(ValueError, match="overlaps"):
        validate_omitted_groups([row], 60_000_000)
    row["stats_min_value"] = "137_70000000_1"
    validate_omitted_groups([row], 60_000_000)
    row["stats_min_value"] = "137_7000000_1"
    with pytest.raises(ValueError, match="ambiguous"):
        validate_omitted_groups([row], 60_000_000)


def test_projection_refuses_truncated_or_misaligned_range() -> None:
    response = httpx.Response(206, content=b"abc", headers={"content-range": "bytes 0-3/100", "etag": "fixed"})
    with pytest.raises(ValueError, match="Truncated"):
        validate_range_response(response, start=0, end=3, total=100)
    with pytest.raises(ValueError, match="Content-Range"):
        validate_range_response(response, start=10, end=13, total=100)


def test_selection_is_outcome_blind_and_order_invariant() -> None:
    first = [{"condition_id": str(i), "resolution": i % 2} for i in range(40)]
    poison = [{"condition_id": str(i), "resolution": 1 - i % 2, "profit": 9999} for i in reversed(range(40))]
    assert choose_conditions(first, 12) == choose_conditions(poison, 12)
    assert len(choose_conditions(first, 12)) == 12


def test_checksum_and_path_checks(tmp_path: Path) -> None:
    path = tmp_path / "part.parquet"
    path.write_bytes(b"verified")
    entry = {"bytes": 8, "sha256": hashlib.sha256(b"verified").hexdigest()}
    assert verify_entry(path, entry)
    path.write_bytes(b"tampered")
    assert not verify_entry(path, entry)
    with pytest.raises(ValueError):
        archive_path(tmp_path, "../escape.parquet")
    with pytest.raises(ValueError):
        archive_path(tmp_path, str(tmp_path.parent / "escape.parquet"))


def test_dense_grid_never_invents_pretrade_price() -> None:
    assert dense_bars([], 10 * HOUR_MS) == ()
    assert dense_bars([hourly(2 * HOUR_MS)], 4 * HOUR_MS)[0].t_ms == 2 * HOUR_MS


def test_download_resumes_verified_files_and_commits_only_matching_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = b"complete parquet payload"
    entry = {
        "path": "daily_aligned/test.parquet",
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "status": "pending",
    }
    manifest = {"repository": REPOSITORY, "revision": REVISION, "files": [entry]}
    (tmp_path / "download-manifest.json").write_text(json.dumps(manifest))
    calls = []

    def fetch(repository: str, filename: str, **kwargs: object) -> str:
        calls.append(filename)
        stage = Path(str(kwargs["local_dir"])) / filename
        stage.parent.mkdir(parents=True, exist_ok=True)
        stage.write_bytes(payload)
        return str(stage)

    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(hf_hub_download=fetch))
    result = download_archive(tmp_path, progress=lambda _: None, max_workers=2)
    assert result["files"][0]["status"] == "verified"
    assert (tmp_path / entry["path"]).read_bytes() == payload
    download_archive(tmp_path, progress=lambda _: None)
    assert calls == [entry["path"]]


def test_download_checksum_failure_remains_explicit_and_uncommitted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = {
        "path": "daily_aligned/test.parquet",
        "bytes": 3,
        "sha256": hashlib.sha256(b"yes").hexdigest(),
        "status": "pending",
    }
    (tmp_path / "download-manifest.json").write_text(
        json.dumps({"repository": REPOSITORY, "revision": REVISION, "files": [entry]})
    )

    def fetch(repository: str, filename: str, **kwargs: object) -> str:
        stage = Path(str(kwargs["local_dir"])) / filename
        stage.parent.mkdir(parents=True, exist_ok=True)
        stage.write_bytes(b"bad")
        return str(stage)

    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(hf_hub_download=fetch))
    with pytest.raises(ValueError, match="checksum/size mismatch"):
        download_archive(tmp_path, progress=lambda _: None)
    assert not (tmp_path / entry["path"]).exists()
    assert (
        json.loads((tmp_path / "download-manifest.json").read_text())["files"][0]["status"] == "verification_failed"
    )


def make_archive(root: Path) -> tuple[Path, dict[int, int]]:
    duckdb = pytest.importorskip("duckdb")
    archive = root / "source"
    (archive / "daily_aligned").mkdir(parents=True)
    (archive / "CTF").mkdir()
    connection = duckdb.connect()
    connection.execute("""CREATE TABLE trades(condition_id VARCHAR,block_timestamp BIGINT,price DOUBLE,
        usdc_amount DOUBLE,fee_usdc DOUBLE,outcome_seq BIGINT,p_event DOUBLE,neg_risk VARCHAR,
        asset_id VARCHAR,maker VARCHAR,taker VARCHAR,taker_direction VARCHAR,outcome_label VARCHAR,
        winning_outcome_label VARCHAR)""")
    start = epoch_ms("2025-01-01")
    stamps = {}
    for index in range(5):
        first = start + index * 10 * 24 * HOUR_MS
        stamps[100 + index] = first + 5 * HOUR_MS
        for hour in (0, 2):
            # NO raw price .7 corresponds to reference price .3, 10/.7 shares.
            connection.execute(
                "INSERT INTO trades VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [
                    f"0x{index:064x}",
                    (first + hour * HOUR_MS + 1000) // 1000,
                    0.7,
                    7.0,
                    0.01,
                    2,
                    0.3,
                    "f",
                    "asset",
                    "maker",
                    "taker",
                    "BUY",
                    "No",
                    None,
                ],
            )
    trade_path = archive / "daily_aligned" / "2025_01_01.parquet"
    connection.execute(f"COPY trades TO '{trade_path.as_posix()}' (FORMAT PARQUET)")
    connection.execute(
        "CREATE TABLE preparations(id VARCHAR,condition_id VARCHAR,oracle VARCHAR,"
        "question_id VARCHAR,outcome_slot_count BIGINT)"
    )
    connection.execute(
        "CREATE TABLE resolutions(id VARCHAR,condition_id VARCHAR,oracle VARCHAR,"
        "question_id VARCHAR,outcome_slot_count BIGINT,payout_numerators VARCHAR[])"
    )
    stamps[104] = epoch_ms("2026-01-02")
    for index in range(5):
        connection.execute(
            "INSERT INTO preparations VALUES (?,?,?,?,?)",
            [f"137_{index + 1}_0", f"0x{index:064x}", "oracle", f"q{index}", 2],
        )
        if index != 3:
            connection.execute(
                "INSERT INTO resolutions VALUES (?,?,?,?,?,?)",
                [f"137_{index + 100}_0", f"0x{index:064x}", "oracle", f"q{index}", 2, ["1", "0"]],
            )
    for name in ("preparations", "resolutions"):
        path = archive / "CTF" / f"{name}.parquet"
        connection.execute(f"COPY {name} TO '{path.as_posix()}' (FORMAT PARQUET)")
    connection.close()
    files = [
        {
            "path": path.relative_to(archive).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "status": "verified",
        }
        for path in archive.rglob("*.parquet")
    ]
    (archive / "download-manifest.json").write_text(
        json.dumps(
            {
                "repository": REPOSITORY,
                "revision": REVISION,
                "attribution": "Test fixture",
                "files": files,
                "total_bytes": sum(row["bytes"] for row in files),
            }
        )
    )
    return archive, stamps


def test_archive_integration_preserves_censored_and_loads_verified_adapter(tmp_path: Path) -> None:
    archive, stamps = make_archive(tmp_path)
    output = tmp_path / "archive2025"
    report = build_archive_dataset(
        archive_dir=archive,
        output_dir=output,
        max_markets=10,
        timestamp_resolver=lambda block: {"timestamp_ms": stamps[block]},
        progress=lambda _: None,
    )
    assert report["population_conditions"] == 5
    assert report["selected_conditions"] == 5
    assert report["settled_adapter_markets"] == 3
    assert report["label_status_counts"]["unresolved_or_missing_ctf"] == 1
    assert report["label_status_counts"]["right_censored_at_window_end"] == 1
    labels = [json.loads(line) for line in (output / "archive" / "labels.jsonl").read_text().splitlines()]
    assert labels[3]["available_at_ms"] is None and labels[3]["resolution"] is None
    assert labels[4]["available_at_ms"] > report["end_ms"]
    dataset = load_dataset(output, verify=True)
    assert len(dataset.metas) == 3
    assert {meta.interval_min for meta in dataset.metas} == {60}
    assert any(entry.path == "archive/hourly.parquet" for entry in dataset.manifest.files)
    assert sum(report["folds"].values()) == 3


def test_timestamp_failure_is_not_silently_a_population_exclusion(tmp_path: Path) -> None:
    archive, _ = make_archive(tmp_path)

    def unavailable(block: int) -> dict[str, int]:
        raise OSError("RPC unavailable")

    with pytest.raises(OSError, match="RPC unavailable"):
        build_archive_dataset(
            archive_dir=archive,
            output_dir=tmp_path / "failed2025",
            max_markets=10,
            timestamp_resolver=unavailable,
            progress=lambda _: None,
        )


def test_cohort_verifies_all_required_partitions_without_waiting_for_other_years(tmp_path: Path) -> None:
    archive, _ = make_archive(tmp_path)
    path = archive / "download-manifest.json"
    manifest = json.loads(path.read_text())
    manifest["files"].append(
        {"path": "daily_aligned/2026_03_01.parquet", "bytes": 999, "sha256": "0" * 64, "status": "pending"}
    )
    manifest["total_bytes"] += 999
    path.write_text(json.dumps(manifest))
    _, projection = _paths(archive, epoch_ms("2025-01-01"), epoch_ms("2026-01-01"))
    assert all("status" not in row for row in projection["files"])
    assert projection["full_inventory_total_bytes"] - projection["total_bytes"] == 999
    manifest["files"][-1]["path"] = "daily_aligned/2025_02_01.parquet"
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="incomplete or corrupt"):
        _paths(archive, epoch_ms("2025-01-01"), epoch_ms("2026-01-01"))


def test_projection_complete_cache_requires_ctf_outputs_and_retained_rpc_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import duckdb

    import pmx.data.polymarket_ctf_projection as projection_module
    from pmx.data.importers.polymarket_archive_http import atomic_json

    archive, _ = make_archive(tmp_path)
    manifest_path = archive / "download-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    for entry in manifest["files"]:
        if not entry["path"].startswith("CTF/"):
            continue
        path = archive / entry["path"]
        connection = duckdb.connect()
        connection.execute(
            "CREATE TABLE padded AS SELECT '137_' || lpad(split_part(id,'_',2),8,'0') || '_' || "
            "split_part(id,'_',3) AS id,* EXCLUDE(id) FROM read_parquet(?)",
            [str(path)],
        )
        path.unlink()
        connection.table("padded").write_parquet(str(path))
        connection.close()
        entry["bytes"] = path.stat().st_size
        entry["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    atomic_json(manifest_path, manifest)
    timestamp = epoch_ms("2026-02-01")

    def block(number: int) -> dict[str, object]:
        raw = {"number": hex(number), "timestamp": hex(timestamp // 1000), "hash": "0x" + "a" * 64}
        return {
            "chain_id": 137,
            "block_number": number,
            "timestamp_ms": timestamp,
            "block_hash": raw["hash"],
            "source_url": "https://fixture.invalid",
            "rpc_response": {"result": raw},
        }

    def local_range(
        name: str, *, start: int, end: int, total: int, cache_dir: Path
    ) -> tuple[Path, dict[str, object]]:
        path = cache_dir / f"{start}-{end}.bin"
        path.parent.mkdir(parents=True, exist_ok=True)
        data = (archive / name).read_bytes()[start : end + 1]
        path.write_bytes(data)
        meta = {
            "url": f"https://huggingface.co/datasets/{REPOSITORY}/resolve/{REVISION}/{name}",
            "revision": REVISION,
            "status": 206,
            "etag": "fixture",
            "content_range": f"bytes {start}-{end}/{total}",
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
        atomic_json(path.with_suffix(".json"), meta)
        return path, meta

    monkeypatch.setattr(projection_module, "BlockTimestampResolver", lambda directory: block)
    monkeypatch.setattr(projection_module, "cached_range", local_range)
    target = projection_module.create_ctf_projection(archive, end_ms=epoch_ms("2026-01-01"), progress=lambda _: None)
    result = projection_module.load_ctf_projection(target, end_ms=epoch_ms("2026-01-01"))
    assert result["counts"]["preparations"] == 5
    assert result["counts"]["resolutions"] == 4
    record_path = target / "projection-manifest.json"
    record = json.loads(record_path.read_text())
    record["artifacts"] = [row for row in record["artifacts"] if row["path"] != "resolutions.parquet"]
    atomic_json(record_path, record)
    with pytest.raises(ValueError, match="inventory every artifact"):
        projection_module.load_ctf_projection(target, end_ms=epoch_ms("2026-01-01"))
