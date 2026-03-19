"""Tests for auth endpoints: register, login, me."""

from fastapi.testclient import TestClient


class TestRegister:
    def test_register_success(self, client: TestClient):
        resp = client.post(
            "/api/auth/register",
            json={"email": "new@example.com", "password": "secret123"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_register_duplicate_email(self, client: TestClient):
        client.post(
            "/api/auth/register",
            json={"email": "dup@example.com", "password": "secret123"},
        )
        resp = client.post(
            "/api/auth/register",
            json={"email": "dup@example.com", "password": "secret456"},
        )
        assert resp.status_code == 409

    def test_register_short_password(self, client: TestClient):
        resp = client.post(
            "/api/auth/register",
            json={"email": "short@example.com", "password": "abc"},
        )
        assert resp.status_code == 422

    def test_register_invalid_email(self, client: TestClient):
        resp = client.post(
            "/api/auth/register",
            json={"email": "not-an-email", "password": "secret123"},
        )
        assert resp.status_code == 422


class TestLogin:
    def test_login_success(self, client: TestClient):
        client.post(
            "/api/auth/register",
            json={"email": "login@example.com", "password": "secret123"},
        )
        resp = client.post(
            "/api/auth/login",
            json={"email": "login@example.com", "password": "secret123"},
        )
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    def test_login_wrong_password(self, client: TestClient):
        client.post(
            "/api/auth/register",
            json={"email": "login2@example.com", "password": "secret123"},
        )
        resp = client.post(
            "/api/auth/login",
            json={"email": "login2@example.com", "password": "wrongpass"},
        )
        assert resp.status_code == 401

    def test_login_nonexistent_user(self, client: TestClient):
        resp = client.post(
            "/api/auth/login",
            json={"email": "ghost@example.com", "password": "secret123"},
        )
        assert resp.status_code == 401


class TestMe:
    def test_me_authenticated(self, client: TestClient, auth_headers: dict):
        resp = client.get("/api/auth/me", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == "test@example.com"
        assert data["xp"] == 0
        assert data["current_streak"] == 0

    def test_me_no_token(self, client: TestClient):
        resp = client.get("/api/auth/me")
        assert resp.status_code == 403  # HTTPBearer returns 403 when no token

    def test_me_invalid_token(self, client: TestClient):
        resp = client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer invalidtoken"},
        )
        assert resp.status_code == 401
