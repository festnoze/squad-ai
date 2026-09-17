"""HTTP integration for bounded discovery campaigns and their persisted finalist replays."""

from __future__ import annotations

import time
from dataclasses import replace
from pathlib import Path
from threading import Event
from typing import Any

import pytest
from fastapi.testclient import TestClient
from tests.test_campaign_analysis import REPORT, wait_review
from tests.test_discovery_engine import research_dataset

from pmx.api import campaigns as campaigns_module
from pmx.api.app import create_app
from pmx.api.catalogue import Catalogue
from pmx.types import Dataset, meta_of


def kalshi_research_dataset() -> Dataset:
    """The planted discovery fixture under an API-accepted real provider and native currency."""
    source = research_dataset()
    markets = [
        replace(source.market(meta.id), provider="kalshi", currency="USD")
        for meta in source.metas
    ]
    metas = [
        meta_of(market, fold=source.manifest.split.fold_of(market.resolved_at_ms))
        for market in markets
    ]
    return replace(
        source,
        metas=tuple(metas),
        market_loader=None,
        _markets={market.id: market for market in markets},
        _whole={market.id: market for market in markets},
    )


def wait_job(client: TestClient, job_id: str, *, timeout: float = 60) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/api/jobs/{job_id}")
        assert response.status_code == 200, response.text
        job: dict[str, Any] = response.json()
        if job["status"] in ("completed", "failed", "cancelled"):
            return job
        time.sleep(0.02)
    raise AssertionError("Discovery API job timed out")


@pytest.fixture
def api_dataset(monkeypatch: pytest.MonkeyPatch) -> Dataset:
    dataset = kalshi_research_dataset()

    def load(_catalogue: Catalogue, name: str) -> Dataset:
        if name != dataset.manifest.name:
            raise KeyError(name)
        return dataset

    monkeypatch.setattr(Catalogue, "load", load)
    return dataset


def test_real_campaign_exports_replays_caches_and_survives_restart(
    api_dataset: Dataset, tmp_path: Path,
) -> None:
    runs = tmp_path / "runs"
    request = {
        "dataset": api_dataset.manifest.name,
        "provider": "kalshi",
        "seed": 7,
        "n_trials": 4,
        "max_markets": 20,
        "bankroll_cents": 100_000,
        "n_splits": 2,
        "finalists": 1,
    }
    app = create_app(dataset_root=tmp_path / "catalogue", runs_dir=runs)
    review_calls = []

    def review(packet: dict[str, Any], _path: Path) -> dict[str, Any]:
        review_calls.append(packet["campaign_id"])
        return REPORT

    app.state.analysis_service.reviewer = review
    with TestClient(app) as client:
        assert client.post("/api/analysis/settings", json={"enabled": True}).status_code == 200
        submitted = client.post("/api/campaigns", json=request)
        assert submitted.status_code == 202, submitted.text
        first_job = wait_job(client, submitted.json()["job_id"])
        assert first_job["status"] == "completed", first_job
        campaign_id = first_job["campaign_id"]
        # Completion publishes the review without a manual request. Cache hits do not repeat it.
        deadline = time.monotonic() + 5
        while client.get(f"/api/campaigns/{campaign_id}/analysis").json()["status"] == "not_requested":
            assert time.monotonic() < deadline
            time.sleep(0.01)
        assert wait_review(app.state.analysis_service, campaign_id)["status"] == "completed"
        assert review_calls == [campaign_id]

        detail_response = client.get(f"/api/campaigns/{campaign_id}")
        assert detail_response.status_code == 200, detail_response.text
        detail = detail_response.json()
        assert detail["status"] == "completed"
        assert detail["dataset"] == api_dataset.manifest.name
        assert detail["currency"] == "USD"
        assert detail["progress"] == {"completed_trials": 4, "total_trials": 4}
        assert len(detail["candidates"]) == 4
        assert all(candidate["train_results"] for candidate in detail["candidates"])
        assert all(candidate["rejection_reasons"] is not None for candidate in detail["candidates"])
        assert detail["selected_candidate_ids"], detail

        history = client.get("/api/campaigns").json()["campaigns"]
        summary = next(row for row in history if row["campaign_id"] == campaign_id)
        assert "candidates" not in summary and "splits" not in summary
        assert summary["progress"] == detail["progress"]
        exported = client.get(f"/api/campaigns/{campaign_id}/export")
        assert exported.status_code == 200
        assert exported.json() == detail
        assert exported.headers["content-disposition"] == (
            f'attachment; filename="pmx-{campaign_id}.json"'
        )

        finalist = next(candidate for candidate in detail["candidates"] if candidate["selected"])
        assert finalist["validation_status"] == "completed"
        validation = finalist["validation_results"][0]
        run_id = validation["run_id"]
        run_response = client.get(f"/api/runs/{run_id}")
        assert run_response.status_code == 200, run_response.text
        run = run_response.json()
        assert run["run"]["campaign_id"] == campaign_id
        assert run["run"]["candidate_id"] == finalist["candidate_id"]
        assert run["run"]["currency"] == "USD"
        market_id = run["run"]["market_ids"][0]
        replay = client.get(f"/api/runs/{run_id}/markets/{market_id}")
        assert replay.status_code == 200, replay.text
        assert replay.json()["ticks"]

        cached_response = client.post("/api/campaigns", json=request)
        assert cached_response.status_code == 202
        cached_job = cached_response.json()
        assert cached_job["status"] == "completed"
        assert cached_job["campaign_id"] == campaign_id
        assert client.get(f"/api/campaigns/{campaign_id}").json() == detail
        assert review_calls == [campaign_id]

    with TestClient(create_app(dataset_root=tmp_path / "catalogue", runs_dir=runs)) as restarted:
        assert restarted.get(f"/api/campaigns/{campaign_id}").json() == detail
        assert any(
            row["campaign_id"] == campaign_id
            for row in restarted.get("/api/campaigns").json()["campaigns"]
        )
        assert restarted.get(f"/api/runs/{run_id}").json() == run
        assert restarted.get(f"/api/runs/{run_id}/markets/{market_id}").json() == replay.json()


def test_campaign_cancellation_capacity_and_failure_are_visible(
    api_dataset: Dataset, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = Event()

    def cancellable(
        dataset: Dataset, config: Any, output_dir: Path, **kwargs: Any,
    ) -> dict[str, Any]:
        started.set()
        cancelled = kwargs["cancel_requested"]
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not cancelled():
            time.sleep(0.01)
        assert cancelled(), "the cancellation endpoint did not reach the campaign worker"
        return {"status": "cancelled", "error": None}

    monkeypatch.setattr(campaigns_module, "run_campaign", cancellable)
    request = {
        "dataset": api_dataset.manifest.name,
        "provider": "kalshi",
        "n_trials": 1,
        "max_markets": 6,
        "n_splits": 2,
        "finalists": 1,
    }
    with TestClient(create_app(dataset_root=tmp_path / "catalogue", runs_dir=tmp_path / "runs")) as client:
        first = client.post("/api/campaigns", json=request)
        assert first.status_code == 202, first.text
        assert started.wait(timeout=5)
        assert client.post("/api/campaigns", json={**request, "seed": 8}).status_code == 409
        assert client.post("/api/runs", json={"dataset": api_dataset.manifest.name,
                                               "provider": "kalshi", "fold": "train"}).status_code == 409
        cancelled = client.post(f"/api/jobs/{first.json()['job_id']}/cancel")
        assert cancelled.status_code == 200
        assert cancelled.json()["cancel_requested"] is True
        stopped = wait_job(client, first.json()["job_id"])
        assert stopped["status"] == "cancelled"

        def explode(*args: Any, **kwargs: Any) -> dict[str, Any]:
            raise RuntimeError("controlled discovery failure")

        monkeypatch.setattr(campaigns_module, "run_campaign", explode)
        failed_response = client.post("/api/campaigns", json={**request, "seed": 9})
        assert failed_response.status_code == 202
        failed = wait_job(client, failed_response.json()["job_id"])
        assert failed["status"] == "failed"
        assert "controlled discovery failure" in failed["error"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("provider", "demo"),
        ("n_trials", 0),
        ("n_trials", 101),
        ("max_markets", 5),
        ("max_markets", 201),
        ("n_splits", 1),
        ("finalists", 6),
    ],
)
def test_campaign_request_bounds_are_public_validation_errors(
    api_dataset: Dataset, tmp_path: Path, field: str, value: object,
) -> None:
    request: dict[str, object] = {
        "dataset": api_dataset.manifest.name,
        "provider": "kalshi",
        "n_trials": 1,
        "max_markets": 6,
    }
    request[field] = value
    with TestClient(create_app(dataset_root=tmp_path / "catalogue", runs_dir=tmp_path / "runs")) as client:
        response = client.post("/api/campaigns", json=request)
        assert response.status_code == 422
        assert isinstance(response.json()["detail"], str)
