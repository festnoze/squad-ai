"""Causal anchors, exact targets, held-out isolation and persistent fixed-protocol jobs."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from tests.test_observation import a_market

from pmx.analysis.signals import (
    CORPUS_END,
    END,
    HOUR,
    START,
    definitions,
    market_observations,
    protected_ids,
    study,
    summary,
)
from pmx.api import signals as signal_service
from pmx.api.app import create_app
from pmx.api.catalogue import Catalogue
from pmx.api.service import write_json
from pmx.types import Dataset, Market, meta_of


def market() -> Market:
    base = a_market()
    prices = [5000] * 72
    prices[0], prices[24], prices[48] = 7000, 6500, 7500
    bars = tuple(
        replace(
            base.bars[0],
            t_ms=START + index * HOUR,
            open_bp=price,
            high_bp=price,
            low_bp=price,
            close_bp=price,
            vwap_bp=price,
            volume_milli=1000,
        )
        for index, price in enumerate(prices)
    )
    return replace(
        base,
        id="polymarket-fixture",
        provider="polymarket",
        bars=bars,
        trades=(),
        interval_min=60,
        created_at_ms=START,
        close_at_ms=START + 72 * HOUR,
        resolved_at_ms=START + 72 * HOUR,
    )


def fixture_dataset() -> tuple[Dataset, list[str]]:
    record = market()
    seen: list[str] = []

    def load(identifier: str) -> Market:
        seen.append(identifier)
        assert identifier == record.id, "A held-out or protected tape was requested"
        return record

    metas = [
        meta_of(record, fold="train"),
        replace(meta_of(record, fold="validation"), id="validation"),
        replace(meta_of(record, fold="sealed"), id="sealed"),
        replace(meta_of(record, fold="train"), id="previous-sealed"),
    ]
    manifest = SimpleNamespace(
        name="polyarchive2024h1",
        dataset_hash="abc",
        interval_min=60,
        window=SimpleNamespace(start_ms=START, end_ms=CORPUS_END),
        split=SimpleNamespace(train_end_ms=END),
    )
    return cast(Dataset, SimpleNamespace(manifest=manifest, metas=metas, market=load)), seen


def test_first_reversal_target_is_exact_and_missing_target_never_moves_anchor() -> None:
    original = market()
    rows, _ = market_observations(original, cutoff=END)
    reversal = next(row for row in rows if row["key"] == "reversal-24-1")
    assert reversal["t_ms"] == START + 25 * HOUR
    assert reversal["effect_bp"] == 1000
    sparse = replace(
        original,
        bars=tuple(replace(bar, volume_milli=0) if index == 48 else bar for index, bar in enumerate(original.bars)),
    )
    rows, _ = market_observations(sparse, cutoff=END)
    matches = [row for row in rows if row["key"] == "reversal-24-1"]
    assert len(matches) == 1
    assert matches[0]["t_ms"] == reversal["t_ms"]
    assert matches[0]["effect_bp"] is None
    assert matches[0]["missing_reason"] == "target_without_observed_trade"


def test_activity_filters_the_fixed_anchor_without_waiting_for_later_liquidity() -> None:
    original = market()
    stale = replace(
        original,
        bars=tuple(
            replace(bar, volume_milli=0) if 1 <= index <= 24 else bar for index, bar in enumerate(original.bars)
        ),
    )
    rows, _ = market_observations(stale, cutoff=END)
    anchor = next(row for row in rows if row["key"].startswith("calibration"))
    assert anchor["staleness_hours"] == 24
    assert not anchor["active_fresh"]
    variants = [row for row in definitions() if row["key"] == anchor["key"]]
    assert summary(variants[0], rows)["n_anchors"] == 1
    assert summary(variants[1], rows)["n_anchors"] == 0


def test_previous_sealed_metadata_is_verified_and_cut_boundary_is_protected(tmp_path: Path) -> None:
    path = tmp_path / "archive/labels.jsonl"
    path.parent.mkdir()
    path.write_text(
        "\n".join(
            json.dumps(row)
            for row in [
                {"condition_id": "earlier", "available_at_ms": START - 1},
                {"condition_id": "boundary", "available_at_ms": START},
                {"condition_id": "unresolved", "available_at_ms": None},
            ]
        ),
        encoding="utf-8",
    )
    write_json(
        tmp_path / "manifest.json",
        {
            "dataset_hash": "protected",
            "split": {"validation_end_ms": START},
            "files": [{"path": "archive/labels.jsonl", "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}],
        },
    )
    assert protected_ids(tmp_path) == ({"polymarket-boundary"}, "protected")
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="protection"):
        protected_ids(tmp_path)


def test_future_label_and_volume_cannot_change_causal_anchors_or_activity() -> None:
    original = market()
    changed = replace(
        original,
        resolution=1 - original.resolution,
        bars=tuple(
            replace(bar, volume_milli=0, close_bp=9000) if index > 24 else bar
            for index, bar in enumerate(original.bars)
        ),
    )
    before, _ = market_observations(original, cutoff=START + 49 * HOUR)
    after, _ = market_observations(changed, cutoff=START + 49 * HOUR)
    for observations in (before, after):
        calibration = next(row for row in observations if row["key"].startswith("calibration"))
        assert calibration["effect_bp"] is None
        assert calibration["outcome"] is None
        assert calibration["missing_reason"] == "label_after_cutoff"
    # Changed later observations can create/remove later triggers, but cannot change earlier ones.
    assert [row for row in before if row["t_ms"] <= START + 25 * HOUR] == [
        row for row in after if row["t_ms"] <= START + 25 * HOUR
    ]


def test_only_train_and_unprotected_ids_enter_study_and_empty_variants_remain_visible() -> None:
    dataset, seen = fixture_dataset()
    result, observations = study(dataset, excluded={"previous-sealed"}, protection_hash="protected")
    assert seen == ["polymarket-fixture"]
    assert len(result["rows"]) == 28
    assert len({row["variant_id"] for row in result["rows"]}) == 28
    assert result["excluded_overlap"] == 1
    assert all(row["status"] == "inconclusive" for row in result["rows"])
    assert any(row["n_anchors"] == 0 and row["mean_effect_bp"] is None for row in result["rows"])
    assert len({(row["market_id"], row["key"]) for row in observations}) == len(observations)


def test_missing_targets_and_week_blocks_prevent_spurious_screening() -> None:
    definition = definitions()[0]
    rows = [
        {
            "key": definition["key"],
            "active_fresh": True,
            "effect_bp": 200,
            "price_bp": 500,
            "outcome": 1,
            "week": "2024-W01",
            "month": month,
            "missing_reason": None,
        }
        for month in ("2024-01", "2024-02", "2024-03")
        for _ in range(20)
    ]
    assert summary(definition, rows)["status"] == "inconclusive"  # Sixty markets, one effective block.
    for index, row in enumerate(rows):
        row["week"] = f"2024-W{index // 5 + 1:02}"
    assert summary(definition, rows)["status"] == "candidate_for_replication"
    for row in rows[:20]:
        row.update(effect_bp=None, missing_reason="target_without_observed_trade")
    result = summary(definition, rows)
    assert result["target_coverage"] == pytest.approx(2 / 3)
    assert result["status"] == "inconclusive"


def test_signal_api_complete_cache_exports_and_restart(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dataset, seen = fixture_dataset()
    dataset_root = tmp_path / "data"
    corpus = dataset_root / "polyarchive2024h1"
    write_json(
        corpus / "manifest.json",
        {"purpose": "research", "dataset_hash": "abc", "window": {"start_ms": START, "end_ms": CORPUS_END}},
    )
    write_json(corpus / "archive/coverage.json", {"adapter_bars": 72, "adapter_observed_hours": 72})
    write_json(
        dataset_root / "polyarchive2023/archive/coverage.json", {"adapter_bars": 100, "adapter_observed_hours": 8}
    )
    monkeypatch.setattr(Catalogue, "load", lambda *_args: dataset)
    monkeypatch.setattr(signal_service, "protected_ids", lambda _root: ({"previous-sealed"}, "protected"))
    with TestClient(create_app(dataset_root=dataset_root, runs_dir=tmp_path / "runs")) as client:
        assert (
            client.post("/api/signal-studies", json={"dataset": "polyarchive2024h1", "threshold": 1}).status_code
            == 422
        )
        reply = client.post("/api/signal-studies", json={"dataset": "polyarchive2024h1"})
        assert reply.status_code == 202
        identifier = reply.json()["study_id"]
        deadline = time.monotonic() + 5
        detail: dict[str, Any] = {}
        while time.monotonic() < deadline:
            detail = client.get(f"/api/signal-studies/{identifier}").json()
            if detail["status"] in ("completed", "failed"):
                break
            time.sleep(0.01)
        assert detail["status"] == "completed", detail
        assert len(detail["result"]["rows"]) == 28
        assert (
            client.post("/api/signal-studies", json={"dataset": "polyarchive2024h1"}).json()["study_id"] == identifier
        )
        assert seen == ["polymarket-fixture"]
        assert client.get(f"/api/signal-studies/{identifier}/export").status_code == 200
        assert client.get(f"/api/signal-studies/{identifier}/observations").status_code == 200
    with TestClient(create_app(dataset_root=dataset_root, runs_dir=tmp_path / "runs")) as restarted:
        assert restarted.get(f"/api/signal-studies/{identifier}").json() == detail
