"""O2: capture of LLM round-trips per work item — store, sidecar, and the
end-to-end attribution through a real pipeline build."""

import json

from autospec.models import AgentInteraction
from autospec.orchestrator.interactions import MAX_TEXT_CHARS, PER_ITEM_RING, InteractionStore
from autospec.orchestrator.pipeline import Pipeline
from autospec.models import PipelinePhase, ProjectState
from autospec.agents.runner import FakeRunner
from autospec import storage

from .conftest import wait_until
from .test_pipeline import PM_BRIEF, QA_PLAN, DEV_GREEN, po_plan_reply


def test_store_records_and_truncates():
    store = InteractionStore(per_item=3)
    store.record(item_id="US-1", phase="build", persona="dev", prompt="p", response="r")
    store.record(item_id="US-1", phase="build", persona="qa", prompt="x" * (MAX_TEXT_CHARS + 50), response="")
    got = store.for_item("US-1")
    assert [i.persona for i in got] == ["dev", "qa"]
    assert got[1].prompt_truncated is True
    assert len(got[1].prompt) <= MAX_TEXT_CHARS + len("\n…[tronqué]")
    # ring is bounded per item
    for _ in range(5):
        store.record(item_id="US-1", phase="build", persona="dev", prompt="p", response="r")
    assert len(store.for_item("US-1")) == 3


def test_default_ring_serves_more_than_forty():
    """BUG4: a LIVE item built with the production default ring (PER_ITEM_RING)
    must not truncate below the interactions endpoint's 200 max served limit. A
    busy item with 60 calls should keep all 60 in memory — not collapse to the
    old hard cap of 40 (which made live history shorter than the sidecar's)."""
    assert PER_ITEM_RING >= 200
    store = InteractionStore()  # constructed the way production does (default ring)
    for i in range(60):
        store.record(item_id="US-1", phase="build", persona="dev", prompt=str(i), response="")
    got = store.for_item("US-1")
    assert len(got) == 60  # > 40: live path no longer truncates below the API limit


def test_store_for_item_limit_and_isolation():
    store = InteractionStore()
    for i in range(4):
        store.record(item_id="US-1", phase="build", persona="dev", prompt=str(i), response="")
    store.record(item_id="US-2", phase="build", persona="dev", prompt="other", response="")
    assert [i.prompt for i in store.for_item("US-1", limit=2)] == ["2", "3"]
    assert len(store.for_item("US-2")) == 1
    assert store.for_item("US-unknown") == []


def test_sidecar_append_and_load(tmp_workspace):
    pid = "proj-trace"
    a = AgentInteraction(item_id="US-1", persona="dev", prompt="hello", response="world")
    b = AgentInteraction(item_id="US-2", persona="qa", prompt="q", response="a")
    storage.append_interaction(pid, a.model_dump_json())
    storage.append_interaction(pid, b.model_dump_json())
    storage.append_interaction(pid, "not json — must be skipped")
    only_us1 = storage.load_interactions(pid, item_id="US-1")
    assert [r["persona"] for r in only_us1] == ["dev"]
    assert storage.load_interactions(pid, item_id="US-1")[0]["prompt"] == "hello"
    assert len(storage.load_interactions(pid)) == 2  # both valid records, bad line skipped


async def test_build_attributes_interactions_to_item(green_pytest):
    """A full spec→plan→build run captures each call under the right item id:
    the PM/PO under their phase, the QA/Dev calls under the story they build."""
    replies = [PM_BRIEF, po_plan_reply(1, with_dep=False), QA_PLAN, DEV_GREEN]
    state = ProjectState(id="proj-int", name="todo", goal="Une todo-list", auto_spec=False)
    pipeline = Pipeline(state, FakeRunner(replies))
    pipeline.start()
    await wait_until(lambda: pipeline.state.phase == PipelinePhase.DONE)

    # The PM brief was a planning-phase call → bucketed under "phase:spec".
    pm_calls = pipeline.interactions.for_item("phase:spec")
    assert any(c.persona == "pm" for c in pm_calls)

    # The QA test-plan + Dev build calls are attributed to the built story US-1.
    us1 = pipeline.interactions.for_item("US-1")
    personas = {c.persona for c in us1}
    assert "dev" in personas
    assert "qa" in personas
    # The dev call captured the raw answer we fed it.
    dev_call = next(c for c in us1 if c.persona == "dev")
    assert json.loads(dev_call.response)["status"] == "green"
    assert dev_call.ok is True


async def test_failed_call_is_captured(green_pytest):
    """An agent error on a build call is captured (ok=False) so the operator can
    inspect the prompt that failed."""
    # PM brief + PO plan succeed; the QA design-tests call raises (no reply left).
    replies = [PM_BRIEF, po_plan_reply(1, with_dep=False)]
    state = ProjectState(id="proj-int-err", name="todo", goal="g", auto_spec=False)
    pipeline = Pipeline(state, FakeRunner(replies))
    pipeline.start()
    await wait_until(lambda: pipeline.state.phase in (PipelinePhase.DONE, PipelinePhase.ERROR))
    us1 = pipeline.interactions.for_item("US-1")
    assert any(c.ok is False and c.error for c in us1)
