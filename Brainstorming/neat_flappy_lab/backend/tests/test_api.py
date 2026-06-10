"""Smoke tests for the FastAPI HTTP + WebSocket layer (no browser needed)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from nfl.api.server import app


def test_config_schema_endpoint() -> None:
    client = TestClient(app)
    resp = client.get("/config/schema")
    assert resp.status_code == 200
    schema = resp.json()
    assert "properties" in schema
    # A few headline tunables must be present in the schema.
    for field in ("mode", "pop_size", "active_sensors", "gd_steps", "compat_threshold"):
        assert field in schema["properties"]


def test_config_defaults_endpoint() -> None:
    client = TestClient(app)
    resp = client.get("/config/defaults")
    assert resp.status_code == 200
    defaults = resp.json()
    assert defaults["mode"] == "evolution_only"
    assert defaults["pop_size"] >= 2


def test_websocket_runs_generations() -> None:
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        # First message is the current-config greeting.
        greeting = ws.receive_json()
        assert greeting["type"] == "config"

        # Configure a tiny, fast run and start it.
        ws.send_json(
            {
                "type": "config",
                "patch": {
                    "pop_size": 16,
                    "max_ticks_per_gen": 150,
                    "stream_mode": "fast",
                    "mode": "evolution_only",
                    "seed": 1,
                },
            }
        )
        ws.send_json({"type": "control", "action": "play"})

        # Collect a couple of generation messages (ignore config echoes etc.).
        generations = []
        for _ in range(40):
            msg = ws.receive_json()
            if msg["type"] == "generation":
                generations.append(msg)
                if len(generations) >= 2:
                    break

        assert len(generations) >= 2
        first = generations[0]
        assert {"gen", "fitnessMax", "fitnessMean", "species", "bestGenome"} <= set(first)
        assert isinstance(first["bestGenome"]["nodes"], list)
        assert first["bestGenome"]["nodes"]  # non-empty topology

        ws.send_json({"type": "control", "action": "pause"})


def test_websocket_select_returns_genome() -> None:
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        assert ws.receive_json()["type"] == "config"  # greeting
        ws.send_json(
            {"type": "config", "patch": {"pop_size": 12, "stream_mode": "fast", "seed": 2}}
        )
        # Step exactly one generation so genomes exist and are evaluated.
        ws.send_json({"type": "control", "action": "step"})
        ws.send_json({"type": "select", "birdId": 0})

        got_genome = False
        for _ in range(40):
            msg = ws.receive_json()
            if msg["type"] == "genome":
                assert msg["birdId"] == 0
                assert "nodes" in msg["genome"]
                got_genome = True
                break
        assert got_genome
