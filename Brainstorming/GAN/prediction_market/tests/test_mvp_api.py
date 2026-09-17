"""Offline MVP integration: real sealed fixture build, real v2 engine, persisted results and replay."""

from __future__ import annotations

import time
from pathlib import Path
from threading import Event
from typing import Any

import pytest
from fastapi.testclient import TestClient
from tests.test_builder import build, staged_markets

from pmx.api import service as service_module
from pmx.api.app import create_app
from pmx.api.catalogue import Catalogue
from pmx.api.models import RunRequest
from pmx.api.service import RunService, select_dataset, write_json
from pmx.engine.runner import replay
from pmx.journal import FeeCharged, Filled, read_journal


@pytest.fixture(scope="module")
def dataset_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("mvp-datasets")
    payloads = staged_markets()
    # These fixture prints must have enough executable volume to exercise cash and fees, not only
    # order attempts rejected by the shared liquidity cap.
    for payload in payloads:
        for trade in payload["trades"]:
            trade["size_milli"] *= 100
        for bar in payload["bars"]:
            bar["volume_milli"] = max(1_000_000, bar["volume_milli"])
    build(root, out_dir=root / "mvp2026", name="mvp2026", market_payloads=payloads)
    return root


def wait_job(client: TestClient, job_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        response = client.get(f"/api/jobs/{job_id}")
        assert response.status_code == 200
        job: dict[str, Any] = response.json()
        if job["status"] in ("completed", "failed"):
            return job
        time.sleep(0.02)
    raise AssertionError("MVP fixture run timed out")


def test_complete_user_journey_replays_and_survives_restart(dataset_root: Path, tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    with TestClient(create_app(dataset_root=dataset_root, runs_dir=runs)) as client:
        assert client.get("/api/health").json() == {"status": "ok", "dataset_available": True}
        summary = client.get("/api/datasets").json()["datasets"][0]
        assert summary["name"] == "mvp2026"
        listing = client.get("/api/datasets/mvp2026/markets?provider=kalshi&fold=train").json()
        assert listing["total"] > 0
        assert all(item["fold"] == "train" and item["provider"] == "kalshi" for item in listing["items"])
        market_id = listing["items"][0]["id"]
        market = client.get(f"/api/datasets/mvp2026/markets/{market_id}").json()
        assert market["bars"] and market["market"]["id"] == market_id
        assert client.get("/api/datasets/mvp2026/markets?fold=sealed").status_code == 422
        hidden_id = next(
            meta.id for meta in client.app.state.catalogue.load("mvp2026").metas if meta.fold == "sealed"
        )
        assert client.get(f"/api/datasets/mvp2026/markets/{hidden_id}").status_code == 404
        assert len(client.get("/api/agents").json()["agents"]) == 3
        request = {"provider": "kalshi", "fold": "train", "max_markets": 2}
        submitted = client.post("/api/runs", json=request)
        assert submitted.status_code == 202, submitted.text
        job = wait_job(client, submitted.json()["job_id"])
        assert job["status"] == "completed", job
        run_id = job["run_id"]
        detail_response = client.get(f"/api/runs/{run_id}")
        assert detail_response.status_code == 200
        detail = detail_response.json()
        follower = next(row for row in detail["leaderboard"] if row["agent_id"] == "follower")
        assert follower["skill_micro"] == follower["pnl_cents"] == follower["fees_cents"] == 0
        assert follower["mean_brier_micro"] == follower["market_brier_micro"]
        assert follower["final_equity_cents"] == 100_000
        assert all(row["provider"] == "kalshi" and row["fold"] == "train" for row in detail["markets"])
        assert detail["run"]["n_markets"] == 2
        market_id = detail["run"]["market_ids"][0]
        ticks_response = client.get(f"/api/runs/{run_id}/markets/{market_id}")
        assert ticks_response.status_code == 200
        ticks = ticks_response.json()
        exported = client.get(f"/api/runs/{run_id}/export")
        assert exported.json() == detail
        assert exported.headers["content-disposition"] == f'attachment; filename="pmx-{run_id}.json"'
        exported_replay = client.get(f"/api/runs/{run_id}/markets/{market_id}/export")
        assert exported_replay.json() == ticks
        assert exported_replay.headers["content-disposition"].startswith("attachment;")
        assert client.get(f"/api/runs/{run_id}/markets/missing/export").status_code == 404
        assert ticks["ticks"]
        assert all(tick["agents"]["follower"]["position"] == 0 for tick in ticks["ticks"])
        assert all(tick["agents"]["follower"]["prob_ppm"] == tick["price_bp"] * 100 for tick in ticks["ticks"])
        projection = replay(runs / run_id)
        assert projection.run_id == run_id
        journal = read_journal(runs / run_id / "journal.jsonl")
        fills = [
            event
            for event in journal
            if isinstance(event, Filled) and event.market_id == market_id and event.filled_size > 0
        ]
        assert len(ticks["fills"]) == len(fills)
        assert sum(row["fee_cents"] for row in ticks["fills"]) == sum(
            event.fee_cents for event in journal if isinstance(event, FeeCharged) and event.market_id == market_id
        )
        assert sum(row["n_fills"] for row in detail["leaderboard"]) > 0
        again = wait_job(client, client.post("/api/runs", json=request).json()["job_id"])
        assert again["run_id"] == run_id
        assert client.get(f"/api/runs/{run_id}").json() == detail
        assert client.get(f"/api/runs/{run_id}/markets/missing").status_code == 404
    with TestClient(create_app(dataset_root=dataset_root, runs_dir=runs)) as restarted:
        assert restarted.get("/api/runs").json()["runs"] == [detail["run"]]
        assert restarted.get(f"/api/jobs/{job['job_id']}").json() == job
        assert restarted.get(f"/api/runs/{run_id}").json() == detail


@pytest.mark.parametrize(
    "fields",
    [
        {"fold": "sealed"},
        {"agent_ids": []},
        {"agent_ids": ["trend", "trend"]},
        {"agent_ids": ["arbitrary.module"]},
        {"provider": "demo"},
        {"max_markets": 31},
        {"max_markets": True},
        {"seed": -1},
        {"bankroll_cents": 0},
        {"dataset": "../y2026"},
    ],
)
def test_invalid_runs_are_visible_strings(dataset_root: Path, tmp_path: Path, fields: dict[str, Any]) -> None:
    with TestClient(create_app(dataset_root=dataset_root, runs_dir=tmp_path)) as client:
        response = client.post("/api/runs", json={"provider": "kalshi", **fields})
        assert response.status_code == 422
        assert isinstance(response.json()["detail"], str)


def test_empty_dataset_state_and_unknown_routes(tmp_path: Path) -> None:
    with TestClient(create_app(dataset_root=tmp_path / "missing", runs_dir=tmp_path / "runs")) as client:
        assert client.get("/api/health").json()["dataset_available"] is False
        assert client.get("/api/datasets").json() == {"datasets": []}
        assert client.post("/api/runs", json={"provider": "kalshi"}).status_code == 404
        assert client.get("/api/not-present").status_code == 404
        assert client.get("/api/jobs/bad..id").status_code == 404


def test_worker_capacity_failure_and_interrupted_recovery(
    dataset_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started, release = Event(), Event()

    def fail(*args: object, **kwargs: object) -> dict[str, Any]:
        started.set()
        release.wait(timeout=10)
        raise ValueError("controlled engine failure")

    monkeypatch.setattr(service_module, "execute_run", fail)
    with TestClient(create_app(dataset_root=dataset_root, runs_dir=tmp_path)) as client:
        request = {"provider": "kalshi", "fold": "train"}
        first = client.post("/api/runs", json=request)
        assert first.status_code == 202
        assert started.wait(timeout=5)
        assert client.post("/api/runs", json=request).status_code == 409
        release.set()
        failed = wait_job(client, first.json()["job_id"])
        assert failed["status"] == "failed"
        assert "controlled engine failure" in failed["error"]
    write_json(
        tmp_path / "mvp-jobs" / "j-interrupted.json",
        {
            "job_id": "j-interrupted",
            "status": "running",
            "error": None,
            "run_id": None,
        },
    )
    service = RunService(Catalogue(dataset_root), tmp_path)
    try:
        assert service.get_job("j-interrupted")["status"] == "failed"
    finally:
        service.close()


def test_selection_is_deterministic_bounded_and_does_not_include_other_providers(dataset_root: Path) -> None:
    dataset = Catalogue(dataset_root).load("mvp2026")
    request = RunRequest(provider="kalshi", fold="train", max_markets=1)
    first, config = select_dataset(dataset, request)
    second, same = select_dataset(dataset, request)
    assert [meta.id for meta in first.metas] == [meta.id for meta in second.metas]
    assert len(first.metas) == 1 and config == same
    assert all(meta.provider == "kalshi" and meta.fold == "train" for meta in first.metas)
    assert first.market_loader is dataset.market_loader


def test_static_frontend_and_spa_fallback_do_not_swallow_api_errors(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>MVP frontend</html>", encoding="utf-8")
    with TestClient(create_app(dataset_root=tmp_path, runs_dir=tmp_path / "runs", web_dist=dist)) as client:
        assert "MVP frontend" in client.get("/").text
        assert "MVP frontend" in client.get("/runs/history").text
        assert client.get("/api/unknown").status_code == 404
