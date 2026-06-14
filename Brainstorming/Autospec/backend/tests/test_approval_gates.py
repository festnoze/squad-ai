"""Tests of the granular approval gates (U4): with gates on, the pipeline blocks
after planning and waits for explicit human approval before building."""

import asyncio
import json

import httpx

from autospec.agents.runner import FakeRunner
from autospec.api import server
from autospec.config import settings as cfg
from autospec.models import PipelinePhase, ProjectState
from autospec.orchestrator.pipeline import Pipeline

from .conftest import wait_until

PM = json.dumps({"type": "brief", "message": "OK", "brief": "# Brief"})
PO = json.dumps({"epics": [{"id": "EPIC-1", "title": "E", "stories": [
    {"id": "US-1", "title": "S", "description": "d", "acceptance_criteria": ["c"],
     "gherkin": "Feature: F Scenario s Given a When b Then c", "depends_on": []}]}]})
QA = json.dumps({"message": "Trivial.", "tests": []})
DEV = json.dumps({"status": "green", "summary": "ok", "files": []})


async def test_gate_blocks_then_approves(green_pytest, monkeypatch):
    monkeypatch.setattr(cfg, "approval_gates_enabled", True)
    state = ProjectState(id="p-appr1", name="todo", goal="g")
    pipeline = Pipeline(state, FakeRunner([PM, PO, QA, DEV]))
    pipeline.start()
    await wait_until(lambda: pipeline.state.awaiting_approval == "plan")
    assert all(s.status.value != "done" for s in pipeline.state.stories)
    await pipeline.aapprove()
    await wait_until(lambda: pipeline.state.phase == PipelinePhase.DONE)
    assert pipeline.state.awaiting_approval == ""
    assert any(s.status.value == "done" for s in pipeline.state.stories)


async def test_gate_reject_stops(green_pytest, monkeypatch):
    monkeypatch.setattr(cfg, "approval_gates_enabled", True)
    state = ProjectState(id="p-appr2", name="todo", goal="g")
    pipeline = Pipeline(state, FakeRunner([PM, PO, QA, DEV]))
    pipeline.start()
    await wait_until(lambda: pipeline.state.awaiting_approval == "plan")
    await pipeline.areject()
    await wait_until(lambda: pipeline.state.phase == PipelinePhase.STOPPED)
    assert pipeline.state.awaiting_approval == ""
    assert all(s.status.value != "done" for s in pipeline.state.stories)


async def test_gate_disabled_by_default(green_pytest):
    state = ProjectState(id="p-appr3", name="todo", goal="g")
    pipeline = Pipeline(state, FakeRunner([PM, PO, QA, DEV]))
    pipeline.start()
    await wait_until(lambda: pipeline.state.phase == PipelinePhase.DONE)
    assert pipeline.state.awaiting_approval == ""


async def test_approve_endpoint(green_pytest, monkeypatch):
    monkeypatch.setattr(cfg, "approval_gates_enabled", True)
    server.pipelines.clear()
    server.set_runner(FakeRunner([PM, PO, QA, DEV]))
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        pid = (
            await client.post("/api/projects", json={"goal": "g", "name": "todo"})
        ).json()["id"]

        async def awaiting():
            r = await client.get(f"/api/projects/{pid}")
            return r.json()["awaiting_approval"] == "plan"

        for _ in range(2000):
            if await awaiting():
                break
            await asyncio.sleep(0.01)
        assert await awaiting()

        assert (await client.post(f"/api/projects/{pid}/approve")).status_code == 200

        async def done():
            r = await client.get(f"/api/projects/{pid}")
            return r.json()["phase"] == "done"

        for _ in range(2000):
            if await done():
                break
            await asyncio.sleep(0.01)
        assert await done()
