import asyncio
import json

import httpx
import pytest

from autospec.agents.runner import FakeRunner
from autospec.api import server

PM_QUESTION = json.dumps({"type": "question", "message": "CLI ou web ?"})
PM_BRIEF = json.dumps({"type": "brief", "message": "OK", "brief": "# Brief"})
PO_PLAN = json.dumps(
    {"epics": [{"id": "EPIC-1", "title": "E", "stories": [
        {"id": "US-1", "title": "S", "description": "d", "acceptance_criteria": ["c"],
         "gherkin": "Feature: F\n  Scenario: s\n    Given a\n    When b\n    Then c", "depends_on": []},
    ]}]}
)
QA_TRIVIAL = json.dumps({"message": "Story triviale, le Gherkin suffit.", "tests": []})
DEV_GREEN = json.dumps({"status": "green", "summary": "ok", "files": []})


def make_client(replies: list[str]) -> httpx.AsyncClient:
    server.pipelines.clear()
    server.set_runner(FakeRunner(replies))
    transport = httpx.ASGITransport(app=server.app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def wait_until_async(apredicate, timeout=5.0):
    deadline = asyncio.get_event_loop().time() + timeout
    while not await apredicate():
        if asyncio.get_event_loop().time() > deadline:
            raise TimeoutError("condition not met in time")
        await asyncio.sleep(0.02)


async def test_create_and_complete_project(green_pytest):
    async with make_client([PM_BRIEF, PO_PLAN, QA_TRIVIAL, DEV_GREEN]) as client:
        resp = await client.post("/api/projects", json={"goal": "Une todo-list", "name": "todo"})
        assert resp.status_code == 200
        project_id = resp.json()["id"]

        async def adone():
            r = await client.get(f"/api/projects/{project_id}")
            return r.json()["phase"] == "done"

        await wait_until_async(adone)
        state = (await client.get(f"/api/projects/{project_id}")).json()
        assert state["brief"] == "# Brief"
        assert [s["status"] for s in state["stories"]] == ["done"]
        assert (await client.get("/api/projects")).json()[0]["id"] == project_id


async def test_stop_during_interview(green_pytest):
    async with make_client([PM_QUESTION]) as client:
        resp = await client.post("/api/projects", json={"goal": "Une todo-list"})
        project_id = resp.json()["id"]

        async def aasked():
            r = await client.get(f"/api/projects/{project_id}")
            return any(m["role"] == "pm" for m in r.json()["chat"])

        await wait_until_async(aasked)
        await client.post(f"/api/projects/{project_id}/stop")

        async def astopped():
            r = await client.get(f"/api/projects/{project_id}")
            return r.json()["phase"] == "stopped"

        await wait_until_async(astopped)


async def test_delete_project(green_pytest):
    async with make_client([PM_BRIEF, PO_PLAN, QA_TRIVIAL, DEV_GREEN]) as client:
        project_id = (
            await client.post("/api/projects", json={"goal": "Une todo-list"})
        ).json()["id"]

        async def adone():
            r = await client.get(f"/api/projects/{project_id}")
            return r.json()["phase"] == "done"

        await wait_until_async(adone)

        resp = await client.delete(f"/api/projects/{project_id}")
        assert resp.status_code == 200
        assert project_id not in server.pipelines
        assert (await client.get(f"/api/projects/{project_id}")).status_code == 404
        assert (await client.get("/api/projects")).json() == []
        # Deleting again is a 404.
        assert (await client.delete(f"/api/projects/{project_id}")).status_code == 404


async def test_create_project_requires_goal(green_pytest):
    async with make_client([]) as client:
        resp = await client.post("/api/projects", json={"goal": "   "})
        assert resp.status_code == 422


async def test_unknown_project_404(green_pytest):
    async with make_client([]) as client:
        assert (await client.get("/api/projects/nope")).status_code == 404
        assert (await client.post("/api/projects/nope/run")).status_code == 404
