"""Authenticated QA intent is external, canonical, bounded and conservative."""
import asyncio
import json

import pytest

from autospec.orchestrator import acceptance,streams
from autospec.orchestrator.dependencies import atomic_json
from autospec.agents.file_broker import IsolationViolation,ClaimViolation
from tests.test_acceptance_pipeline_remediation import task_pipeline


async def setup():
    pipeline,root=task_pipeline()
    item=streams.build_work_graph(pipeline.state).items["T-A"]
    await pipeline._claim_arbiter.reserve(item.id,pipeline._canonical_item_claims(item))
    return pipeline,root,item


async def test_only_supervisor_qa_role_records_intent_before_product_mutation():
    pipeline,root,item=await setup()
    control=acceptance.supervisor_root(pipeline.state.id)
    await pipeline._aauthorize_agent_write(item.id,("books/a.py",),"dev")
    assert not (control/"qa-authored-files.json").exists()
    await pipeline._aauthorize_agent_write(item.id,("books/a.py",),"qa")
    assert json.loads((control/"qa-authored-files.json").read_bytes())=={"files":["books/a.py"]}
    assert not (root/"books/a.py").exists() and not control.is_relative_to(root)


async def test_rejected_claim_never_creates_qa_provenance():
    pipeline,root,item=await setup()
    with pytest.raises(ClaimViolation): await pipeline._aauthorize_agent_write(item.id,("outside.py",),"qa")
    assert not (acceptance.supervisor_root(pipeline.state.id)/"qa-authored-files.json").exists()


async def test_simultaneous_qa_intents_preserve_union_without_producer_roles():
    pipeline,root,item=await setup()
    await pipeline._aexpand_agent_claim(item.id,{"task_id":item.id,"paths":["books/b.py"],"reason":"QA helper"},"qa")
    await asyncio.gather(pipeline._aauthorize_agent_write(item.id,("books/a.py",),"qa"),
        pipeline._aauthorize_agent_write(item.id,("books/b.py",),"qa"))
    value=json.loads((acceptance.supervisor_root(pipeline.state.id)/"qa-authored-files.json").read_bytes())
    assert value=={"files":["books/a.py","books/b.py"]}


@pytest.mark.parametrize("value",[{"files":["../escape.py"]},{"files":["books/a.py"],"role":"qa"},
    {"files":["books/a.py","books/a.py"]},{"files":[1]},{"files":"books/a.py"}])
async def test_malformed_existing_journal_is_never_replaced_with_success(value):
    pipeline,root,item=await setup()
    path=acceptance.supervisor_root(pipeline.state.id)/"qa-authored-files.json"
    atomic_json(path,value)
    before=path.read_bytes()
    with pytest.raises((IsolationViolation,ValueError)):
        await pipeline._aauthorize_agent_write(item.id,("books/a.py",),"qa")
    assert path.read_bytes()==before


async def test_native_journal_lock_preserves_union_between_factory_instances(tmp_path):
    from autospec.orchestrator.qa_provenance import record_qa_write_intent
    root=tmp_path/"supervisor"
    await asyncio.gather(*(asyncio.to_thread(record_qa_write_intent,root,(f"checks/helper_{n}.py",)) for n in range(12)))
    value=json.loads((root/"qa-authored-files.json").read_bytes())
    assert value=={"files":sorted(f"checks/helper_{n}.py" for n in range(12))}
