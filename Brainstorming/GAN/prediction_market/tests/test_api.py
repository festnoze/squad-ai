"""The read-only API surface."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from pmx.v1.api.app import create_app


def test_markets_and_backtest(seeded_data: Path) -> None:
    client = TestClient(create_app(seeded_data))

    markets = client.get("/markets").json()
    assert len(markets) == 12
    assert all("resolution" in m and "source" in m for m in markets)

    mid = markets[0]["id"]
    full = client.get(f"/markets/{mid}").json()
    assert len(full["prices"]) >= 2

    bt = client.get(f"/markets/{mid}/backtest").json()
    assert bt["market"]["id"] == mid
    assert len(bt["ticks"]) == full["n_ticks"]
    assert bt["results"]
    # every tick row carries a price and a per-agent state
    row = bt["ticks"][0]
    assert "price" in row and row["agents"]


def test_tournament_and_walkforward(seeded_data: Path) -> None:
    client = TestClient(create_app(seeded_data))

    t = client.get("/tournament").json()
    assert t["board"]
    assert t["board"] == sorted(t["board"], key=lambda r: r["mean_brier_micro"])

    wf = client.get("/walkforward").json()
    assert "train_winner" in wf and "test_winner" in wf
    assert len(wf["train_ids"]) + len(wf["test_ids"]) == 12


def test_unknown_market_is_404(seeded_data: Path) -> None:
    client = TestClient(create_app(seeded_data))
    assert client.get("/markets/nope").status_code == 404


def test_bad_agent_is_422(seeded_data: Path) -> None:
    client = TestClient(create_app(seeded_data))
    assert client.get("/tournament?agents=wizard").status_code == 422
