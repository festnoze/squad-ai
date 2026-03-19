"""Tests for profile and settings endpoints."""

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


class TestProfile:
    def test_default_profile(self, client: TestClient, auth_headers: dict):
        resp = client.get("/api/profile", headers=auth_headers)
        assert resp.status_code == 200
        profile = resp.json()
        assert profile["xp"] == 0
        assert profile["level"] == 0
        assert profile["current_streak"] == 0
        assert profile["longest_streak"] == 0
        assert profile["focus_duration"] == 25
        assert profile["short_break_duration"] == 5
        assert profile["long_break_duration"] == 15
        assert profile["sessions_before_long_break"] == 4
        assert profile["auto_advance"] is False
        assert "void" in profile["unlocked_realms"]
        assert "ember" in profile["unlocked_realms"]
        assert profile["active_realm"] == "void"

    def test_level_calculation(self, client: TestClient, auth_headers: dict):
        """Level = floor(sqrt(xp / 10)). After a few sessions, check the level."""
        # 1 session = 15 XP -> level = floor(sqrt(1.5)) = 1
        client.post(
            "/api/sessions", json=_make_session_payload(), headers=auth_headers
        )
        resp = client.get("/api/profile", headers=auth_headers)
        assert resp.json()["level"] == 1

    def test_profile_requires_auth(self, client: TestClient):
        resp = client.get("/api/profile")
        assert resp.status_code == 403


class TestSettings:
    def test_update_timer_settings(self, client: TestClient, auth_headers: dict):
        resp = client.put(
            "/api/profile/settings",
            json={"focus_duration": 50, "short_break_duration": 10},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        profile = resp.json()
        assert profile["focus_duration"] == 50
        assert profile["short_break_duration"] == 10
        # Others unchanged
        assert profile["long_break_duration"] == 15

    def test_update_auto_advance(self, client: TestClient, auth_headers: dict):
        resp = client.put(
            "/api/profile/settings",
            json={"auto_advance": True},
            headers=auth_headers,
        )
        assert resp.json()["auto_advance"] is True

    def test_switch_realm(self, client: TestClient, auth_headers: dict):
        # "ember" is unlocked by default
        resp = client.put(
            "/api/profile/settings",
            json={"active_realm": "ember"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["active_realm"] == "ember"

    def test_switch_to_locked_realm_rejected(self, client: TestClient, auth_headers: dict):
        resp = client.put(
            "/api/profile/settings",
            json={"active_realm": "cosmos"},
            headers=auth_headers,
        )
        assert resp.status_code == 403

    def test_invalid_duration_rejected(self, client: TestClient, auth_headers: dict):
        resp = client.put(
            "/api/profile/settings",
            json={"focus_duration": 0},
            headers=auth_headers,
        )
        assert resp.status_code == 422

        resp = client.put(
            "/api/profile/settings",
            json={"focus_duration": 100},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    def test_partial_update(self, client: TestClient, auth_headers: dict):
        """Sending only one field should not reset others."""
        client.put(
            "/api/profile/settings",
            json={"focus_duration": 45},
            headers=auth_headers,
        )
        resp = client.put(
            "/api/profile/settings",
            json={"auto_advance": True},
            headers=auth_headers,
        )
        profile = resp.json()
        assert profile["focus_duration"] == 45
        assert profile["auto_advance"] is True
