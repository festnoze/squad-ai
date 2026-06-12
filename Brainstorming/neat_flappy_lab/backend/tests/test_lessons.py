"""Smoke tests for didactic lesson endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient

from nfl.api.server import app


def test_linear_lesson_endpoint_returns_trace() -> None:
    client = TestClient(app)
    resp = client.get("/lessons/linear?steps=12&lr=0.05&seed=1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["formula"] == "y = w*x + b"
    assert len(data["samples"]) > 10
    assert len(data["trace"]) == 13
    assert data["trace"][-1]["loss"] < data["trace"][0]["loss"]


def test_quadratic_lesson_endpoint_returns_snapshots() -> None:
    client = TestClient(app)
    resp = client.get("/lessons/quadratic?steps=40&hidden=4&seed=2")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["samples"]) > 10
    assert len(data["trace"]) >= 4
    assert {"prediction", "weights", "probe"} <= set(data["trace"][0])


def test_neat_intro_endpoint_returns_evolution_trace() -> None:
    client = TestClient(app)
    resp = client.get("/lessons/neat-intro?generations=10&seed=3")
    assert resp.status_code == 200
    data = resp.json()
    assert data["task"] == "XOR"
    assert len(data["trace"]) == 11
    assert data["bestGenome"]["nodes"]
    assert data["bestGenome"]["connections"]

