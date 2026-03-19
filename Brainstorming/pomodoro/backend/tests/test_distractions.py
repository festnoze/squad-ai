"""Tests for distractions: log, stats, validation."""

from datetime import datetime, timedelta

from fastapi.testclient import TestClient


def _make_session_payload(day_offset: int = 0) -> dict:
    base = datetime(2025, 6, 1) + timedelta(days=day_offset)
    return {
        "tag": "Work",
        "duration_minutes": 25,
        "completed": True,
        "started_at": base.isoformat(),
        "ended_at": (base + timedelta(minutes=25)).isoformat(),
        "session_type": "focus",
    }


class TestCreateDistraction:
    def test_log_distraction(self, client: TestClient, auth_headers: dict):
        resp = client.post(
            "/api/distractions",
            json={"category": "Phone", "note": "Checked notifications"},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["category"] == "Phone"
        assert data["note"] == "Checked notifications"

    def test_log_distraction_with_session(self, client: TestClient, auth_headers: dict):
        # Create a session first
        sess_resp = client.post(
            "/api/sessions", json=_make_session_payload(), headers=auth_headers
        )
        session_id = sess_resp.json()["id"]

        resp = client.post(
            "/api/distractions",
            json={"session_id": session_id, "category": "Noise"},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["session_id"] == session_id

    def test_invalid_category_rejected(self, client: TestClient, auth_headers: dict):
        resp = client.post(
            "/api/distractions",
            json={"category": "InvalidCategory"},
            headers=auth_headers,
        )
        assert resp.status_code == 400

    def test_distraction_requires_auth(self, client: TestClient):
        resp = client.post(
            "/api/distractions",
            json={"category": "Phone"},
        )
        assert resp.status_code == 403


class TestDistractionStats:
    def test_empty_stats(self, client: TestClient, auth_headers: dict):
        resp = client.get("/api/distractions/stats", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["total_distractions"] == 0
        assert resp.json()["categories"] == {}

    def test_stats_aggregation(self, client: TestClient, auth_headers: dict):
        for _ in range(3):
            client.post(
                "/api/distractions",
                json={"category": "Phone"},
                headers=auth_headers,
            )
        for _ in range(2):
            client.post(
                "/api/distractions",
                json={"category": "Noise"},
                headers=auth_headers,
            )
        client.post(
            "/api/distractions",
            json={"category": "Hunger"},
            headers=auth_headers,
        )

        resp = client.get("/api/distractions/stats", headers=auth_headers)
        stats = resp.json()
        assert stats["total_distractions"] == 6
        assert stats["categories"]["Phone"] == 3
        assert stats["categories"]["Noise"] == 2
        assert stats["categories"]["Hunger"] == 1

    def test_stats_user_isolation(
        self, client: TestClient, auth_headers: dict, second_auth_headers: dict
    ):
        client.post(
            "/api/distractions",
            json={"category": "Phone"},
            headers=auth_headers,
        )
        resp = client.get("/api/distractions/stats", headers=second_auth_headers)
        assert resp.json()["total_distractions"] == 0
