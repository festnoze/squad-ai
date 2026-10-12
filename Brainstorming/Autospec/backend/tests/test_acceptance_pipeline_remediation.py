"""Real API/plan/broker raccord, without paid model calls or product execution."""
import asyncio
import json

import httpx
import pytest

from autospec.agents.file_broker import FileBroker, ClaimViolation, IsolationViolation, active_execution, active_write_authorizer
from autospec.agents.personas import persona
from autospec.agents.runner import AgentResult, FakeRunner
from autospec.api import server
from autospec.config import settings
from autospec.contracts import ContractFact, import_contract
from autospec.models import ProjectState, Task, UserStory, Stream, StreamKind, StoryStatus
from autospec.orchestrator import acceptance, claims, plan_gates, plan_pipeline, streams
from autospec.orchestrator.pipeline import Pipeline, DeliveryBlocked, _BUILD_ITEM
from autospec.storage import workspace_dir


def oracle(brief="POST /books; title 2..12"):
    return import_contract(brief, "| BOOK-01 | B / X | POST /books; title 2..12 |",
        reviewed_by="source-reviewer", facts=[ContractFact.create("route", "route", "POST /books", ["BOOK-01"], "POST /books")])


def state_with_oracle():
    source = oracle()
    state = ProjectState(id="books", name="Books", goal="Books", brief=source.brief,
                         acceptance_contract_hash=source.contract_hash)
    acceptance.contract_store(state.id).save(source)
    return state, source


def admitted_plan():
    return {"epics": [{"id": "E-1", "stories": [{"id": "S-1", "title": "Books", "tasks": [
        {"id": "T-0", "title": "Foundation", "file_globs": ["books/foundation.py"], "requirement_ids": ["BOOK-01"]},
        {"id": "T-1", "title": "Vertical", "file_globs": ["books/vertical.py"], "requirement_ids": ["BOOK-01"], "depends_on": ["T-0"]},
        {"id": "T-2", "title": "Rest", "file_globs": ["books/rest.py"], "requirement_ids": ["BOOK-01"], "depends_on": ["T-1"]}]}]}],
        "lot_definition": "explicit_groups", "lots": [{"id": "L-1", "members": ["S-1"]}],
        "milestones": {"foundation": ["T-0"], "vertical": "T-1"}, "contract_facts": {"route": "POST /books"}}


async def test_api_freezes_complete_sources_outside_product_and_no_model(monkeypatch):
    started = []
    monkeypatch.setattr(server, "_runner", FakeRunner([]))
    monkeypatch.setattr(Pipeline, "start", lambda self: started.append(self))
    server.pipelines.clear()
    source = oracle("POST /books; title 2..12\n" + "detail\n" * 4000)
    payload = {"goal": "Books", "brief": source.brief, "acceptance_reference": source.reference,
        "acceptance_reviewed_by": source.reviewed_by, "acceptance_facts": source.payload()["facts"]}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://test") as client:
        response = await client.post("/api/projects", json=payload)
        assert response.status_code == 200
        state = started[0].state
        assert len(state.brief) > 20000 and state.brief == source.brief
        assert state.acceptance_contract_hash == source.contract_hash
        assert acceptance.load_contract(state) == source
        assert not acceptance.contract_store(state.id).root.is_relative_to(workspace_dir(state.id).resolve())
        assert not started[0].runner.calls
        payload["acceptance_facts"][0]["source_excerpt"] = "not in source"
        assert (await client.post("/api/projects", json=payload)).status_code == 422
        assert len(started) == 1
    server.pipelines.clear()


async def test_oracle_persistence_failure_never_starts_pipeline(monkeypatch):
    started = []
    monkeypatch.setattr(Pipeline, "start", lambda self: started.append(self))
    monkeypatch.setattr("autospec.contracts.ContractStore.save", lambda *a: (_ for _ in ()).throw(OSError("unavailable")))
    source = oracle()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://test") as client:
        response = await client.post("/api/projects", json={"goal": "Books", "brief": source.brief,
            "acceptance_reference": source.reference, "acceptance_reviewed_by": source.reviewed_by})
    assert response.status_code == 503 and not started


@pytest.mark.parametrize("submitted", [3, 5, 7, 100, True, "4", 4.0])
async def test_api_plan_limit_drift_never_persists_or_starts(monkeypatch, submitted):
    stored, started = [], []
    runner = FakeRunner([])
    monkeypatch.setattr(server, "_runner", runner)
    monkeypatch.setattr(Pipeline, "start", lambda self: started.append(self))
    monkeypatch.setattr("autospec.contracts.ContractStore.save", lambda *args: stored.append(args))
    source = import_contract("Books: at most four lots.",
        "| BOOK-01 | B / X | Nominal API |", reviewed_by="source-only reviewer",
        facts=[ContractFact.create("lot-limit", "plan_limits", {"max_lots": 4},
            ["BOOK-01"], "at most four lots")])
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://test") as client:
        response = await client.post("/api/projects", json={"goal": "Books", "brief": source.brief,
            "acceptance_reference": source.reference, "acceptance_reviewed_by": source.reviewed_by,
            "acceptance_facts": source.payload()["facts"], "acceptance_max_lots": submitted})
    assert response.status_code == 422
    assert not stored and not started and not runner.calls


async def test_api_exact_source_plan_limit_is_persisted_before_start(monkeypatch):
    started = []
    runner = FakeRunner([])
    monkeypatch.setattr(server, "_runner", runner)
    monkeypatch.setattr(Pipeline, "start", lambda self: started.append(self))
    source = import_contract("Books: at most four lots.",
        "| BOOK-01 | B / X | Nominal API |", reviewed_by="source-only reviewer",
        facts=[ContractFact.create("lot-limit", "plan_limits", {"max_lots": 4},
            ["BOOK-01"], "at most four lots")])
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://test") as client:
        response = await client.post("/api/projects", json={"goal": "Books", "brief": source.brief,
            "acceptance_reference": source.reference, "acceptance_reviewed_by": source.reviewed_by,
            "acceptance_facts": source.payload()["facts"], "acceptance_max_lots": 4})
    assert response.status_code == 200 and len(started) == 1
    state = started[0].state
    assert state.acceptance_max_lots == 4 and acceptance.load_contract(state) == source
    assert not runner.calls
    server.pipelines.pop(state.id, None)


async def test_source_only_contract_refused_before_any_paid_plan_call():
    state, source = state_with_oracle()
    source = import_contract(source.brief, source.reference, reviewed_by="reviewer")
    state.acceptance_contract_hash = source.contract_hash
    acceptance.contract_store(state.id).save(source)
    runner = FakeRunner([])
    pipeline = Pipeline(state, runner)
    with pytest.raises(DeliveryBlocked):
        await pipeline._aplan_phase()
    assert not runner.calls and not state.delivery_ready


@pytest.mark.parametrize("tamper", ["brief", "store", "identity"])
async def test_tampered_oracle_fails_closed_before_plan(tamper):
    state, source = state_with_oracle()
    if tamper == "brief":
        state.brief += " weakening"
    elif tamper == "identity":
        state.acceptance_contract_hash = "../other"
    else:
        path = acceptance.contract_store(state.id).root / f"{source.contract_hash}.json"
        path.write_text("{}")
    runner = FakeRunner([])
    pipeline = Pipeline(state, runner)
    with pytest.raises(DeliveryBlocked):
        await pipeline._aplan_phase()
    assert not runner.calls and not state.delivery_ready


async def test_legacy_po_path_is_admitted_and_preserves_milestones_mapping():
    state, source = state_with_oracle()
    state.stories = [UserStory(id="S-1", epic_id="old", title="Old", iteration=0,
                              tasks=[Task(id="T-0", story_id="S-1", status=StoryStatus.DONE)])]
    state.stories[0].status = StoryStatus.DONE
    runner = FakeRunner([json.dumps(admitted_plan())])
    pipeline = Pipeline(state, runner)
    await pipeline._aplan_phase()
    assert state.plan_admission["status"] == "pass"
    assert source.contract_hash in runner.calls[0]["prompt"]
    new = state.stories[-1]
    assert new.id != "S-1" and new.tasks[0].id != "T-0"
    assert state.plan_admission["milestones"]["foundation"] == [new.tasks[0].id]
    assert state.plan_admission["milestones"]["vertical"] == new.tasks[1].id
    assert new.tasks[1].depends_on == [new.tasks[0].id]
    assert all(task.requirement_ids == ["BOOK-01"] for task in new.tasks)


async def test_bad_plan_never_materializes_and_structured_failure_has_no_fallback(monkeypatch):
    state, source = state_with_oracle()
    invalid = admitted_plan()
    invalid["contract_facts"]["route"] = "POST /other"
    pipeline = Pipeline(state, FakeRunner([json.dumps(invalid)]))
    with pytest.raises(DeliveryBlocked):
        await pipeline._aplan_phase()
    assert not state.stories and not state.delivery_ready
    monkeypatch.setattr(settings, "po_pipeline", "on")
    async def rejected(*a, **kw):
        raise plan_pipeline.PlanAdmissionError(plan_gates.PlanAdmission("fail", source.contract_hash, ("constraint",)))
    monkeypatch.setattr(plan_pipeline, "arun_po_pipeline", rejected)
    pipeline = Pipeline(state, FakeRunner([json.dumps(admitted_plan())]))
    with pytest.raises(DeliveryBlocked):
        await pipeline._aplan_phase()
    assert not pipeline.runner.calls


def task_pipeline():
    task = Task(id="T-A", story_id="S-A", files_hint=["books/a.py"])
    story = UserStory(id="S-A", epic_id="E", title="Books", tasks=[task])
    state = ProjectState(id="claims", name="Claims", goal="Books", stories=[story])
    root = workspace_dir(state.id)
    root.mkdir(parents=True)
    return Pipeline(state, FakeRunner([])), root


async def test_write_batch_claims_checked_atomically_before_any_mutation():
    pipeline, root = task_pipeline()
    item = streams.build_work_graph(pipeline.state).items["T-A"]
    await pipeline._claim_arbiter.reserve(item.id, pipeline._canonical_item_claims(item))
    context, transient = await pipeline._aprepare_tool_context(root, item.id, "dev")
    assert not transient
    loop = asyncio.get_running_loop()
    def authorize(paths):
        return asyncio.run_coroutine_threadsafe(pipeline._aauthorize_agent_write(item.id, paths, "dev"), loop).result(2)
    token = active_write_authorizer.set(authorize)
    try:
        broker = FileBroker(context)
        with pytest.raises(ClaimViolation):
            await asyncio.to_thread(broker.apply, {"tool": "write_files", "files": [
                {"path": "books/a.py", "content": "first"}, {"path": "books/b.py", "content": "second"}]})
        assert not (root / "books/a.py").exists()
        await pipeline._aexpand_agent_claim(item.id, {"task_id": item.id, "paths": ["books/b.py"], "reason": "shared DTO required"}, "dev")
        await asyncio.to_thread(broker.apply, {"tool": "write_files", "files": [{"path": "books/b.py", "content": "allowed"}]})
        assert (root / "books/b.py").read_text() == "allowed"
        assert "books/b.py" in pipeline.state.task(item.id).files_hint
    finally:
        active_write_authorizer.reset(token)
        await pipeline._claim_arbiter.release(item.id)


async def test_claim_expansion_refuses_active_writer_without_permission():
    pipeline, root = task_pipeline()
    item = streams.build_work_graph(pipeline.state).items["T-A"]
    await pipeline._claim_arbiter.reserve(item.id, pipeline._canonical_item_claims(item))
    await pipeline._claim_arbiter.reserve("T-B", [claims.canonical_claim("books/b.py", project_root=root, owner="T-B")])
    with pytest.raises(ClaimViolation, match="waiting_claim"):
        await pipeline._aexpand_agent_claim(item.id, {"task_id": item.id, "paths": ["books/b.py"], "reason": "need DTO"}, "dev")
    assert not await pipeline._claim_arbiter.authorize_batch(item.id, ("books/b.py",), project_root=root)
    assert "books/b.py" not in pipeline.state.task(item.id).files_hint


async def test_manifests_and_review_roles_have_no_uncontrolled_write_capability():
    pipeline, root = task_pipeline()
    (root / "pyproject.toml").write_text("[project]\nname='books'\n")
    context, transient = await pipeline._aprepare_tool_context(root, "T-A", "dev")
    with pytest.raises(IsolationViolation):
        FileBroker(context).apply({"tool": "write_files", "files": [{"path": "pyproject.toml", "content": "unsafe"}]})
    with pytest.raises(IsolationViolation, match="no write"):
        await pipeline._aauthorize_agent_write("T-A", ("books/a.py",), "critic")
    if transient:
        await pipeline._claim_arbiter.release("T-A")


async def test_tracked_real_broker_raccord_and_release_on_exit():
    pipeline, root = task_pipeline()
    class BrokerRunner:
        async def arun(self, *a, **kw):
            context = active_execution.get()
            assert context.task_id == "T-A" and context.project_root == root
            await asyncio.to_thread(FileBroker(context).apply, {"tool": "write_files", "files": [{"path": "books/a.py", "content": "nominal"}]})
            return AgentResult(text='{"done":true}', usage_reported=True)
    pipeline.runner = BrokerRunner()
    token = _BUILD_ITEM.set("T-A")
    try:
        await pipeline._tracked.arun("build", persona("dev"), cwd=root)
    finally:
        _BUILD_ITEM.reset(token)
    assert (root / "books/a.py").read_text() == "nominal"
    assert not (await pipeline._claim_arbiter.snapshot())["active"]
    assert active_execution.get() is None and active_write_authorizer.get() is None
