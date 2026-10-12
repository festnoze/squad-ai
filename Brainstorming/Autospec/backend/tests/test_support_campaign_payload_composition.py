"""Compose the real launcher payload/API/stack; intercept BEFORE bootstrap/LLM.

Trusted factory code and fictional metadata only. No product import, Docker,
native provider or generated application is executed on the host.
"""
import asyncio
import importlib.util
from pathlib import Path

import httpx
import pytest

from autospec.agents.runner import FakeRunner
from autospec.api import server
from autospec.config import settings
from autospec.orchestrator import workspace
from autospec.orchestrator.pipeline import Pipeline

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "support_composition_campaign", ROOT / "tools/support_benchmark_campaign.py"
)
campaign = importlib.util.module_from_spec(spec)
spec.loader.exec_module(campaign)


@pytest.fixture
def intercepted_factory(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "project_bootstrap", True)
    monkeypatch.setattr(settings, "fake_agents", False)
    monkeypatch.setattr(server, "pipelines", {})
    monkeypatch.setattr(server, "_runner", FakeRunner([]))
    observations = []

    def scaffold(state, **kwargs):
        observations.append(dict(state.technical_stack))

    async def before_bootstrap(self):
        self._block_delivery("Trusted test interception before product bootstrap", source="test")
        return False

    monkeypatch.setattr(workspace, "scaffold", scaffold)
    monkeypatch.setattr(Pipeline, "_abootstrap_phase", before_bootstrap)
    receipt = {"sources": {
        name: (ROOT / name).read_bytes().decode("utf-8") for name in campaign.HASHES
    }}
    body = campaign.payload(receipt, tmp_path / "relais-support-rem25-composition")
    return body, observations


async def settled(project_id):
    pipeline = server.pipelines[project_id]
    await asyncio.wait_for(asyncio.shield(pipeline._task), timeout=5)
    return pipeline.state.model_dump(mode="json")


async def test_real_campaign_payload_reaches_bootstrap_with_sealed_stack(intercepted_factory):
    body, observations = intercepted_factory
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://127.0.0.1"
    ) as client:
        response = await client.post("/api/projects", json=body)
        assert response.status_code == 200
        state = await settled(response.json()["id"])
    assert len(observations) == 1, state["bootstrap_detail"]
    decision = observations[0]
    assert {key: decision[key] for key in ("backend", "framework", "frontend", "database", "kind")} == {
        "backend": "python", "framework": "fastapi", "frontend": "react",
        "database": "sqlite", "kind": "fullstack",
    }
    assert decision["version"] == "1" and len(decision["decision_sha256"]) == 64
    assert state["budget_usd"] == 40 and state["usage"]["agent_calls"] == 0
    assert state["usage"]["cost_usd"] == 0 and state["acceptance_contract_hash"]
    assert state["phase"] == "needs_attention" and not state["delivery_ready"]


async def test_legacy_labels_fail_then_same_project_language_recovery_keeps_contract(intercepted_factory):
    body, observations = intercepted_factory
    body["technical_stack"] = {
        "backend": "Python/FastAPI", "frontend": "React/TypeScript/Vite", "database": "SQLite"
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://127.0.0.1"
    ) as client:
        response = await client.post("/api/projects", json=body)
        project_id = response.json()["id"]
        failed = await settled(project_id)
        assert failed["bootstrap_status"] == "failed" and not observations
        assert "BackendLanguage" in failed["bootstrap_detail"]
        repaired = await client.put(f"/api/projects/{project_id}/language", json={"language": "python"})
        assert repaired.status_code == 200
        corrected = repaired.json()["state"]
        for key in ("id", "brief", "acceptance_contract_hash", "budget_usd", "usage", "iteration"):
            assert corrected[key] == failed[key]
        assert corrected["technical_stack"] == {"backend": "python", "source": "explicit"}
        assert len(server.pipelines) == 1 and not observations
        resumed = await client.post(f"/api/projects/{project_id}/resume-build")
        assert resumed.status_code == 200
        final = await settled(project_id)
    assert len(observations) == 1 and observations[0]["database"] == "sqlite"
    assert observations[0]["frontend"] == "react" and observations[0]["framework"] == "fastapi"
    assert final["id"] == failed["id"] and final["budget_usd"] == 40
    assert final["usage"] == failed["usage"] and final["usage"]["agent_calls"] == 0
    assert len(server.pipelines) == 1 and not final["delivery_ready"]
