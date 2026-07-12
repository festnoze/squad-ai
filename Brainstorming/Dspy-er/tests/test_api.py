from __future__ import annotations

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

import dspyer.main as main_module
from dspyer.main import app

REQUEST_BODY = {
    "prompt_name": "capitals",
    "dataset_name": "capitals-ds",
    "evaluators": [{"type": "exact_match"}],
    "methods": ["opro"],
    "task_model": "test-model",
    "rounds": 1,
    "candidates_per_method": 1,
}


@pytest.fixture
async def client(fake_langfuse, monkeypatch):
    monkeypatch.setattr(main_module, "get_langfuse_service", lambda: fake_langfuse)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http


async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_methods_listing(client):
    response = await client.get("/methods")
    body = response.json()
    assert "dspy" in body["methods"]
    assert "llm_judge" in body["evaluator_types"]


async def test_job_lifecycle(client, fake_llm, monkeypatch):
    # patch the loop's LLMClient so the job uses the fake
    import dspyer.loop as loop_module

    monkeypatch.setattr(loop_module, "LLMClient", lambda: fake_llm)

    response = await client.post("/optimizations", json=REQUEST_BODY)
    assert response.status_code == 202
    job_id = response.json()["id"]

    for _ in range(100):
        response = await client.get(f"/optimizations/{job_id}")
        body = response.json()
        if body["status"] in ("succeeded", "failed"):
            break
        await asyncio.sleep(0.05)

    assert body["status"] == "succeeded", body.get("error")
    assert body["result"]["best_score"] == 1.0

    response = await client.get(f"/optimizations/{job_id}/best-prompt")
    assert response.status_code == 200
    assert "BE PRECISE" in response.json()["prompt"]


async def test_get_missing_job(client):
    response = await client.get("/optimizations/nope")
    assert response.status_code == 404


async def test_validation_rejects_empty_evaluators(client):
    bad = dict(REQUEST_BODY, evaluators=[])
    response = await client.post("/optimizations", json=bad)
    assert response.status_code == 422
