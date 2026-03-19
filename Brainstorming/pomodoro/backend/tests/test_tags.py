"""Tests for tags: list defaults, create custom, duplicate prevention."""

from fastapi.testclient import TestClient


class TestListTags:
    def test_default_tags_created(self, client: TestClient, auth_headers: dict):
        resp = client.get("/api/tags", headers=auth_headers)
        assert resp.status_code == 200
        tags = resp.json()
        assert len(tags) == 5
        names = {t["name"] for t in tags}
        assert "Work" in names
        assert "Study" in names
        assert "Creative" in names
        assert "Health" in names
        assert "Side Project" in names

    def test_default_tags_only_created_once(self, client: TestClient, auth_headers: dict):
        client.get("/api/tags", headers=auth_headers)
        resp = client.get("/api/tags", headers=auth_headers)
        assert len(resp.json()) == 5

    def test_tags_user_isolation(
        self, client: TestClient, auth_headers: dict, second_auth_headers: dict
    ):
        """Each user gets their own tags."""
        client.get("/api/tags", headers=auth_headers)
        client.post(
            "/api/tags",
            json={"name": "Custom", "color": "#123456"},
            headers=auth_headers,
        )
        resp = client.get("/api/tags", headers=second_auth_headers)
        # Second user gets their own defaults, not the custom tag
        names = {t["name"] for t in resp.json()}
        assert "Custom" not in names


class TestCreateTag:
    def test_create_custom_tag(self, client: TestClient, auth_headers: dict):
        resp = client.post(
            "/api/tags",
            json={"name": "Reading", "color": "#AABBCC"},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Reading"
        assert data["color"] == "#AABBCC"

    def test_duplicate_tag_rejected(self, client: TestClient, auth_headers: dict):
        client.post(
            "/api/tags",
            json={"name": "Reading", "color": "#AABBCC"},
            headers=auth_headers,
        )
        resp = client.post(
            "/api/tags",
            json={"name": "Reading", "color": "#DDEEFF"},
            headers=auth_headers,
        )
        assert resp.status_code == 409

    def test_invalid_color_rejected(self, client: TestClient, auth_headers: dict):
        resp = client.post(
            "/api/tags",
            json={"name": "Bad", "color": "not-a-color"},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    def test_empty_name_rejected(self, client: TestClient, auth_headers: dict):
        resp = client.post(
            "/api/tags",
            json={"name": "", "color": "#AABBCC"},
            headers=auth_headers,
        )
        assert resp.status_code == 422
