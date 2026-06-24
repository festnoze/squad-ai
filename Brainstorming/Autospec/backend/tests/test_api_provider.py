"""Tests of the provider endpoint (M1) and the components endpoints (E3/E4)."""

import json

import httpx

from autospec.agents.providers import OllamaRunner
from autospec.agents.runner import FakeRunner
from autospec.api import server
from autospec.config import settings
from autospec.storage import workspace_dir

PM_QUESTION = json.dumps({"type": "question", "message": "CLI ou web ?"})


def make_client(replies: list[str]) -> httpx.AsyncClient:
    server.pipelines.clear()
    server.set_runner(FakeRunner(replies))
    transport = httpx.ASGITransport(app=server.app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def test_get_provider_defaults(monkeypatch):
    monkeypatch.setattr(settings, "agent_provider", "claude")
    monkeypatch.setattr(settings, "claude_model", None)
    async with make_client([]) as client:
        data = (await client.get("/api/provider")).json()
        assert data["provider"] == "claude"
        # Claude is the default provider: first in the list.
        assert data["available"] == ["claude", "codex", "openai", "ollama", "anthropic"]
        # Adaptive 2nd dropdown: per-provider model choices.
        assert data["models"]["claude"] == ["opus", "sonnet", "haiku"]
        assert "gpt-4.1" in data["models"]["openai"]
        assert data["models"]["codex"]  # codex has suggested models too


async def test_switch_anthropic_model(monkeypatch):
    monkeypatch.setattr(settings, "agent_provider", "claude")
    async with make_client([]) as client:
        resp = await client.post(
            "/api/provider",
            json={"provider": "anthropic", "model": "claude-opus-4-8"},
        )
        assert resp.status_code == 200
        assert resp.json() == {
            "ok": True,
            "provider": "anthropic",
            "model": "claude-opus-4-8",
        }
        assert settings.anthropic_model == "claude-opus-4-8"


async def test_switch_provider_updates_pipelines(monkeypatch):
    monkeypatch.setattr(settings, "agent_provider", "claude")
    monkeypatch.setattr(settings, "ollama_model", "llama3.1")
    async with make_client([PM_QUESTION]) as client:
        project_id = (
            await client.post("/api/projects", json={"goal": "Une todo-list"})
        ).json()["id"]
        resp = await client.post(
            "/api/provider", json={"provider": "ollama", "model": "qwen3"}
        )
        assert resp.status_code == 200
        assert resp.json() == {"ok": True, "provider": "ollama", "model": "qwen3"}
        assert settings.agent_provider == "ollama"
        # Live pipelines now point at the new backend.
        assert isinstance(server.pipelines[project_id].runner, OllamaRunner)


async def test_switch_provider_rejects_unknown(monkeypatch):
    monkeypatch.setattr(settings, "agent_provider", "claude")
    async with make_client([]) as client:
        assert (
            await client.post("/api/provider", json={"provider": "gemini"})
        ).status_code == 422


async def test_provider_locked_in_demo_mode(monkeypatch):
    monkeypatch.setattr(settings, "fake_agents", True)
    async with make_client([]) as client:
        data = (await client.get("/api/provider")).json()
        assert data["provider"] == "fake"
        assert (
            await client.post("/api/provider", json={"provider": "claude"})
        ).status_code == 409


async def test_components_endpoints(monkeypatch):
    async with make_client([PM_QUESTION]) as client:
        project_id = (
            await client.post("/api/projects", json={"goal": "Une todo-list"})
        ).json()["id"]
        # No approved component yet -> setup refused.
        assert (
            await client.post(f"/api/projects/{project_id}/components/setup")
        ).status_code == 409
        # User validates a components list.
        resp = await client.put(
            f"/api/projects/{project_id}/components",
            json={"components": [
                {"id": "backend", "kind": "backend", "name": "API",
                 "technology": "FastAPI", "status": "approved"},
            ]},
        )
        assert resp.status_code == 200
        assert resp.json()["state"]["components"][0]["status"] == "approved"
        # Setup materializes it.
        assert (
            await client.post(f"/api/projects/{project_id}/components/setup")
        ).status_code == 200

        import asyncio

        deadline = asyncio.get_event_loop().time() + 20
        ws = workspace_dir(project_id)
        while not (ws / "backend" / "pyproject.toml").exists():
            assert asyncio.get_event_loop().time() < deadline
            await asyncio.sleep(0.02)
        # Unknown status value -> 422.
        assert (
            await client.put(
                f"/api/projects/{project_id}/components",
                json={"components": [{"id": "x", "status": "weird"}]},
            )
        ).status_code == 422
