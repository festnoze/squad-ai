"""Tests for sessions: create, list, stats, XP, streaks, realm unlocking."""

from datetime import datetime, timedelta

from fastapi.testclient import TestClient


def _make_session(
    day_offset: int = 0,
    duration: int = 25,
    completed: bool = True,
    session_type: str = "focus",
    tag: str | None = "Work",
    intention: str | None = None,
) -> dict:
    """Helper to build a session payload."""
    base = datetime(2025, 6, 1) + timedelta(days=day_offset)
    return {
        "tag": tag,
        "intention": intention,
        "duration_minutes": duration,
        "completed": completed,
        "started_at": base.isoformat(),
        "ended_at": (base + timedelta(minutes=duration)).isoformat(),
        "session_type": session_type,
    }


class TestCreateSession:
    def test_create_focus_session(self, client: TestClient, auth_headers: dict):
        resp = client.post(
            "/api/sessions",
            json=_make_session(),
            headers=auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["session_type"] == "focus"
        assert data["completed"] is True
        assert data["xp_earned"] > 0

    def test_create_break_session_no_xp(self, client: TestClient, auth_headers: dict):
        resp = client.post(
            "/api/sessions",
            json=_make_session(session_type="short_break"),
            headers=auth_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["xp_earned"] == 0

    def test_incomplete_session_no_xp(self, client: TestClient, auth_headers: dict):
        resp = client.post(
            "/api/sessions",
            json=_make_session(completed=False),
            headers=auth_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["xp_earned"] == 0

    def test_session_requires_auth(self, client: TestClient):
        resp = client.post("/api/sessions", json=_make_session())
        assert resp.status_code == 403


class TestXPCalculation:
    def test_first_session_xp(self, client: TestClient, auth_headers: dict):
        """First session: streak becomes 1, so base 10 + streak bonus 5 = 15 XP."""
        resp = client.post(
            "/api/sessions",
            json=_make_session(day_offset=0),
            headers=auth_headers,
        )
        assert resp.json()["xp_earned"] == 15

    def test_streak_multiplier_3_days(self, client: TestClient, auth_headers: dict):
        """After 3 consecutive days, multiplier is 1.5x."""
        # Day 1
        client.post(
            "/api/sessions", json=_make_session(day_offset=0), headers=auth_headers
        )
        # Day 2
        client.post(
            "/api/sessions", json=_make_session(day_offset=1), headers=auth_headers
        )
        # Day 3 — streak is now 3, multiplier 1.5x
        resp = client.post(
            "/api/sessions", json=_make_session(day_offset=2), headers=auth_headers
        )
        # base 10 + streak bonus 5 = 15, * 1.5 = 22
        assert resp.json()["xp_earned"] == 22

    def test_streak_resets_on_gap(self, client: TestClient, auth_headers: dict):
        """Missing a day resets streak to 1."""
        # Day 1
        client.post(
            "/api/sessions", json=_make_session(day_offset=0), headers=auth_headers
        )
        # Day 2
        client.post(
            "/api/sessions", json=_make_session(day_offset=1), headers=auth_headers
        )
        # Day 4 (skip day 3) — streak resets to 1
        resp = client.post(
            "/api/sessions", json=_make_session(day_offset=3), headers=auth_headers
        )
        # streak is 1 again: 10 + 5 = 15, * 1.0 = 15
        assert resp.json()["xp_earned"] == 15

    def test_same_day_no_streak_increase(self, client: TestClient, auth_headers: dict):
        """Multiple sessions on same day don't increase streak."""
        client.post(
            "/api/sessions", json=_make_session(day_offset=0), headers=auth_headers
        )
        resp = client.post(
            "/api/sessions", json=_make_session(day_offset=0, duration=20),
            headers=auth_headers,
        )
        # Streak is still 1
        assert resp.json()["xp_earned"] == 15


class TestStreakAndProfile:
    def test_streak_updates_in_profile(self, client: TestClient, auth_headers: dict):
        # 3 consecutive days
        for i in range(3):
            client.post(
                "/api/sessions", json=_make_session(day_offset=i), headers=auth_headers
            )
        resp = client.get("/api/profile", headers=auth_headers)
        profile = resp.json()
        assert profile["current_streak"] == 3
        assert profile["longest_streak"] == 3

    def test_longest_streak_preserved(self, client: TestClient, auth_headers: dict):
        # Build 3-day streak
        for i in range(3):
            client.post(
                "/api/sessions", json=_make_session(day_offset=i), headers=auth_headers
            )
        # Gap, then 1 session
        client.post(
            "/api/sessions", json=_make_session(day_offset=5), headers=auth_headers
        )
        resp = client.get("/api/profile", headers=auth_headers)
        profile = resp.json()
        assert profile["current_streak"] == 1
        assert profile["longest_streak"] == 3


class TestRealmUnlocking:
    def test_default_realms(self, client: TestClient, auth_headers: dict):
        resp = client.get("/api/profile", headers=auth_headers)
        realms = resp.json()["unlocked_realms"]
        assert "void" in realms
        assert "ember" in realms

    def test_glacier_unlocks_at_level_5(self, client: TestClient, auth_headers: dict):
        """Level 5 requires XP >= 250 (floor(sqrt(250/10)) = floor(5.0) = 5).
        We'll create enough sessions to accumulate >= 250 XP."""
        # Each session on same day = 15 XP. Need ~17 sessions for 255 XP.
        # But we need to be on consecutive days for streak bonuses.
        # Simpler: just create many sessions on different days.
        for i in range(20):
            client.post(
                "/api/sessions", json=_make_session(day_offset=i), headers=auth_headers
            )
        resp = client.get("/api/profile", headers=auth_headers)
        profile = resp.json()
        assert profile["xp"] >= 250
        assert "glacier" in profile["unlocked_realms"]


class TestListSessions:
    def test_list_all(self, client: TestClient, auth_headers: dict):
        for i in range(3):
            client.post(
                "/api/sessions", json=_make_session(day_offset=i), headers=auth_headers
            )
        resp = client.get("/api/sessions", headers=auth_headers)
        assert resp.status_code == 200
        assert len(resp.json()) == 3

    def test_filter_by_tag(self, client: TestClient, auth_headers: dict):
        client.post(
            "/api/sessions", json=_make_session(tag="Work"), headers=auth_headers
        )
        client.post(
            "/api/sessions",
            json=_make_session(tag="Study", day_offset=1),
            headers=auth_headers,
        )
        resp = client.get("/api/sessions?tag=Work", headers=auth_headers)
        assert len(resp.json()) == 1
        assert resp.json()[0]["tag"] == "Work"

    def test_filter_by_date_range(self, client: TestClient, auth_headers: dict):
        for i in range(5):
            client.post(
                "/api/sessions", json=_make_session(day_offset=i), headers=auth_headers
            )
        resp = client.get(
            "/api/sessions?date_from=2025-06-02&date_to=2025-06-03",
            headers=auth_headers,
        )
        assert len(resp.json()) == 2

    def test_user_isolation(
        self, client: TestClient, auth_headers: dict, second_auth_headers: dict
    ):
        """Users can only see their own sessions."""
        client.post(
            "/api/sessions", json=_make_session(), headers=auth_headers
        )
        resp = client.get("/api/sessions", headers=second_auth_headers)
        assert len(resp.json()) == 0


class TestSessionStats:
    def test_stats_aggregation(self, client: TestClient, auth_headers: dict):
        for i in range(3):
            client.post(
                "/api/sessions",
                json=_make_session(day_offset=i, duration=25),
                headers=auth_headers,
            )
        # Also add a break (should not count)
        client.post(
            "/api/sessions",
            json=_make_session(day_offset=0, session_type="short_break", duration=5),
            headers=auth_headers,
        )
        resp = client.get("/api/sessions/stats", headers=auth_headers)
        stats = resp.json()
        assert stats["total_focus_minutes"] == 75
        assert stats["total_sessions"] == 3
        assert stats["completed_sessions"] == 3
        assert len(stats["daily_breakdown"]) == 3
