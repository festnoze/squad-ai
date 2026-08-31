from fastapi.testclient import TestClient

from server.main import app

client = TestClient(app)


def test_health_and_step() -> None:
    assert client.get("/api/health").status_code == 200
    response = client.post("/api/step", json={"steps": 2})
    assert response.status_code == 200
    assert response.json()["tick"] >= 2


def test_reset_rejects_unknown_scenario() -> None:
    response = client.post("/api/reset", json={"scenario": "unknown", "seed": 2})
    assert response.status_code == 400


def test_replay_and_mode_comparison() -> None:
    client.post(
        "/api/reset",
        json={"scenario": "honeypot", "seed": 117, "warden_mode": "causal"},
    )
    client.post("/api/step", json={"steps": 10})
    replay = client.get("/api/replay")
    comparison = client.post(
        "/api/compare",
        json={"scenario": "honeypot", "seed": 117, "ticks": 24},
    )

    assert replay.status_code == 200
    assert len(replay.json()["frames"]) == 11
    assert comparison.status_code == 200
    assert [row["mode"] for row in comparison.json()["results"]] == ["strict", "naive", "causal"]
