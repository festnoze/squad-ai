"""Tests of spec import (I3): an imported brief seeds the project and skips the
PM interview, going straight to planning."""

import asyncio
import json

import httpx

from autospec.agents.runner import FakeRunner
from autospec.api import server
from autospec.models import PipelinePhase, ProjectState
from autospec.orchestrator.pipeline import Pipeline
from autospec.spec_import import MAX_BRIEF_CHARS, parse_spec_import

from .conftest import wait_until

PO = json.dumps({"epics": [{"id": "EPIC-1", "title": "E", "stories": [
    {"id": "US-1", "title": "S", "description": "d", "acceptance_criteria": ["c"],
     "gherkin": "Feature: F Scenario s Given a When b Then c", "depends_on": []}]}]})
QA = json.dumps({"message": "Trivial.", "tests": []})
DEV = json.dumps({"status": "green", "summary": "ok", "files": []})


def test_parse_spec_import_trims_and_caps():
    assert parse_spec_import("  hello  ") == "hello"
    assert parse_spec_import(None) == ""
    assert len(parse_spec_import("x" * (MAX_BRIEF_CHARS + 100))) == MAX_BRIEF_CHARS


async def test_imported_brief_skips_interview(green_pytest):
    state = ProjectState(id="p-i3", name="m", goal="g", brief="# Imported brief")
    pipeline = Pipeline(state, FakeRunner([PO, QA, DEV]))  # no PM interview reply queued
    pipeline.start()
    await wait_until(lambda: pipeline.state.phase == PipelinePhase.DONE)
    assert pipeline.state.brief == "# Imported brief"
    assert any(s.status.value == "done" for s in pipeline.state.stories)


async def test_create_endpoint_with_imported_brief(green_pytest):
    server.pipelines.clear()
    server.set_runner(FakeRunner([PO, QA, DEV]))
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/api/projects", json={"goal": "g", "name": "imp", "brief": "# Spec doc"}
        )
        pid = r.json()["id"]
        assert r.json()["state"]["brief"] == "# Spec doc"

        async def done():
            rr = await client.get(f"/api/projects/{pid}")
            return rr.json()["phase"] == "done"

        for _ in range(2000):
            if await done():
                break
            await asyncio.sleep(0.01)
        assert await done()
