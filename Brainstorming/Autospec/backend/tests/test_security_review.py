"""Tests of the security & supply-chain review (S1): after a delivered iteration
an agent audits the generated code + dependencies and feeds security findings
into the feedback-impact pipeline (E2)."""

import json

import httpx
import pytest

from autospec.agents.runner import FakeRunner
from autospec.api import server
from autospec.models import (
    AcceptanceCriterion,
    ChatRole,
    Epic,
    PipelinePhase,
    ProjectState,
    StoryStatus,
    UserStory,
)
from autospec.orchestrator.pipeline import Pipeline

from .conftest import wait_until

SEC_FINDINGS = json.dumps(
    {
        "message": "Une faille critique détectée.",
        "findings": [
            {
                "id": "SEC-1",
                "severity": "high",
                "kind": "security",
                "title": "Injection de commande",
                "detail": "subprocess shell=True sur entrée utilisateur.",
            }
        ],
    },
    ensure_ascii=False,
)
SEC_EMPTY = json.dumps({"message": "RAS côté sécurité.", "findings": []}, ensure_ascii=False)
IMPACT_UPDATE = json.dumps(
    {
        "message": "On durcit la story non implémentée.",
        "action": "update_story",
        "story_id": "US-1",
        "updates": {"description": "valide et échappe l'entrée utilisateur"},
    },
    ensure_ascii=False,
)


@pytest.fixture
def no_real_audit(monkeypatch):
    """Never run pip-audit/npm audit against the workspace in tests."""

    async def _fake_audit(self):
        return "(audit simulé : aucune dépendance vulnérable)"

    monkeypatch.setattr(Pipeline, "_arun_dep_audit", _fake_audit)


def make_done_pipeline(replies):
    state = ProjectState(
        id="proj-sec",
        name="todo",
        goal="Une todo-list",
        phase=PipelinePhase.DONE,
        brief="# Brief",
        epics=[Epic(id="EPIC-1", title="Cœur")],
        stories=[
            UserStory(
                id="US-1",
                epic_id="EPIC-1",
                title="Story à venir",
                status=StoryStatus.TODO,
                acceptance_criteria=[AcceptanceCriterion(id="AC-1", text="critère")],
            ),
            UserStory(id="US-2", epic_id="EPIC-1", title="Déjà livrée", status=StoryStatus.DONE),
        ],
    )
    return Pipeline(state, FakeRunner(replies))


async def test_security_findings_feed_impact_pipeline(no_real_audit):
    pipeline = make_done_pipeline([SEC_FINDINGS, IMPACT_UPDATE])
    await pipeline._asecurity_phase(force=True)
    assert len(pipeline.state.findings) == 1
    finding = pipeline.state.findings[0]
    assert finding.severity == "high" and finding.kind == "security"
    assert finding.iteration == pipeline.state.iteration
    assert any("Injection de commande" in f for f in pipeline.state.feedback)
    assert any(m.role == ChatRole.QA and "🔒" in m.content for m in pipeline.state.chat)
    assert pipeline.state.story("US-1").description == "valide et échappe l'entrée utilisateur"


async def test_security_no_findings_skips_impact(no_real_audit):
    runner = FakeRunner([SEC_EMPTY])
    pipeline = make_done_pipeline([])
    pipeline.runner = runner
    pipeline._tracked.pipeline = pipeline
    await pipeline._asecurity_phase(force=True)
    assert pipeline.state.findings == []
    assert len(runner.calls) == 1
    assert any(m.role == ChatRole.QA for m in pipeline.state.chat)


async def test_security_rejected_while_building(no_real_audit):
    state = ProjectState(id="proj-sec2", name="todo", goal="g", phase=PipelinePhase.BUILD)
    pipeline = Pipeline(state, FakeRunner([]))
    with pytest.raises(ValueError):
        await pipeline.asecurity_review()


async def test_security_disabled_by_default_in_lifecycle(green_pytest, no_real_audit):
    pm_brief = json.dumps({"type": "brief", "message": "OK", "brief": "# Brief"})
    po_plan = json.dumps(
        {"epics": [{"id": "EPIC-1", "title": "E", "stories": [
            {"id": "US-1", "title": "S", "description": "d", "acceptance_criteria": ["c"],
             "gherkin": "Feature: F Scenario s Given a When b Then c",
             "depends_on": []}]}]}
    )
    qa_trivial = json.dumps({"message": "Trivial.", "tests": []})
    dev_green = json.dumps({"status": "green", "summary": "ok", "files": []})
    state = ProjectState(id="proj-sec3", name="todo", goal="Une todo-list")
    pipeline = Pipeline(state, FakeRunner([pm_brief, po_plan, qa_trivial, dev_green]))
    pipeline.start()
    await wait_until(lambda: pipeline.state.phase == PipelinePhase.DONE)
    assert pipeline.state.findings == []


async def test_security_endpoint_triggers_findings(green_pytest, no_real_audit):
    pm_brief = json.dumps({"type": "brief", "message": "OK", "brief": "# Brief"})
    po_plan = json.dumps(
        {"epics": [{"id": "EPIC-1", "title": "E", "stories": [
            {"id": "US-1", "title": "S", "description": "d", "acceptance_criteria": ["c"],
             "gherkin": "Feature: F Scenario s Given a When b Then c",
             "depends_on": []}]}]}
    )
    qa_trivial = json.dumps({"message": "Trivial.", "tests": []})
    dev_green = json.dumps({"status": "green", "summary": "ok", "files": []})
    server.pipelines.clear()
    server.set_runner(
        FakeRunner([pm_brief, po_plan, qa_trivial, dev_green, SEC_FINDINGS, IMPACT_UPDATE])
    )
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        project_id = (
            await client.post("/api/projects", json={"goal": "Une todo-list", "name": "todo"})
        ).json()["id"]

        import asyncio

        async def adone():
            r = await client.get(f"/api/projects/{project_id}")
            return r.json()["phase"] == "done"

        ok = False
        for _ in range(2000):
            if await adone():
                ok = True
                break
            await asyncio.sleep(0.01)
        assert ok

        resp = await client.post(f"/api/projects/{project_id}/security-review")
        assert resp.status_code == 200

        async def afindings():
            r = await client.get(f"/api/projects/{project_id}")
            return len(r.json()["findings"]) == 1

        for _ in range(2000):
            if await afindings():
                break
            await asyncio.sleep(0.01)
        assert await afindings()


async def test_security_unknown_project_404():
    server.pipelines.clear()
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.post("/api/projects/nope/security-review")).status_code == 404
