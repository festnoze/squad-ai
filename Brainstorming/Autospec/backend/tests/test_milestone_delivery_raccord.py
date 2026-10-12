import hashlib
import json

import pytest

from autospec.agents.runner import FakeRunner
from autospec.contracts import ContractFact, import_contract
from autospec.models import ProjectState, StoryStatus, Task, UserStory
from autospec.orchestrator import acceptance, milestones
from autospec.orchestrator.dependencies import atomic_json
from autospec.orchestrator.pipeline import Pipeline
from autospec.storage import workspace_dir
from autospec.validation.final_gate import source_snapshot, verification_cache_context


def setup(auth=False):
    brief = "Books require real browser creation and committed DB data."
    fact = ContractFact.create("vertical", "security_profile" if auth else "vertical_profile",
        {} if auth else {"auth": False}, ["BOOK-01"], brief)
    contract = import_contract(brief, "| BOOK-01 | B / X+V | Browser creates a stored book |", reviewed_by="reviewer", facts=[fact])
    tasks = [Task(id="F", story_id="S"), Task(id="V", story_id="S", depends_on=["F"]),
             Task(id="R", story_id="S", depends_on=["V"])]
    state = ProjectState(id="book-milestones", name="Books", goal="Books", brief=brief,
        acceptance_contract_hash=contract.contract_hash, stories=[UserStory(id="S", epic_id="E", title="Books", tasks=tasks)],
        plan_admission={"status": "pass", "contract_hash": contract.contract_hash,
                        "milestones": {"foundation": ["F"], "vertical": "V"}, "lots": [{"id": "L", "members": ["S"]}]})
    acceptance.contract_store(state.id).save(contract)
    return state, contract


def proof(store, kind, check, snapshot, contract):
    path = store / (kind + check.replace(":", "-") + ".json")
    atomic_json(path, {"checked": check, "passed": True})
    return {"type": kind, "path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "checks": [check], "snapshot_hash": snapshot, "contract_hash": contract.contract_hash, "passed": True}


def vertical_result(store, snapshot, contract, auth=False):
    names = ["schema", "browser_create", "api_read", "db_committed"]
    if auth: names += ["bootstrap", "argon2", "browser_login"]
    return {"contract_hash": contract.contract_hash, "snapshot_hash": snapshot, "stages": [
        {"name": name, "passed": True, "proofs": [proof(store, kind, "VERTICAL:" + name, snapshot, contract)
            for kind in (["X", "V"] if name.startswith("browser_") else ["X"])]} for name in names]}


@pytest.mark.parametrize("auth", [False, True])
def test_vertical_requires_actual_full_chain_and_intact_external_receipt(tmp_path, auth):
    state, contract = setup(auth)
    snapshot = "a" * 64
    result = vertical_result(tmp_path, snapshot, contract, auth)
    admitted = milestones.admit_vertical(contract, result, snapshot_hash=snapshot, evidence_root=tmp_path)
    assert admitted["status"] == "PASS"
    state.plan_admission["vertical_receipt_hash"] = milestones.save_receipt(admitted, tmp_path)
    assert milestones.load_receipt(state, contract, tmp_path)["status"] == "PASS"
    path = tmp_path / "XVERTICAL-db_committed.json"
    path.write_text("modified")
    with pytest.raises(milestones.MilestoneError, match="proof"):
        milestones.load_receipt(state, contract, tmp_path)


@pytest.mark.parametrize("problem", ["health_only", "missing_db", "no_visual", "wrong_snapshot", "failed", "duplicate"])
def test_vertical_false_green_refused(tmp_path, problem):
    state, contract = setup()
    snapshot = "a" * 64
    result = vertical_result(tmp_path, snapshot, contract)
    if problem == "health_only": result["stages"] = [{"name": "health", "passed": True, "proofs": []}]
    elif problem == "missing_db": result["stages"] = result["stages"][:-1]
    elif problem == "no_visual": result["stages"][1]["proofs"] = result["stages"][1]["proofs"][:1]
    elif problem == "wrong_snapshot": result["snapshot_hash"] = "b" * 64
    elif problem == "failed": result["stages"][2]["passed"] = False
    elif problem == "duplicate": result["stages"].append(result["stages"][0])
    assert milestones.admit_vertical(contract, result, snapshot_hash=snapshot, evidence_root=tmp_path)["status"] == "NOT_VERIFIED"


@pytest.mark.parametrize("problem", ["unknown", "cycle", "self", "duplicate", "bypass", "added"])
def test_post_admission_graph_mutations_never_silently_sanitized(problem):
    state, contract = setup()
    if problem == "unknown": state.task("R").depends_on = ["missing"]
    elif problem == "cycle": state.task("F").depends_on = ["R"]
    elif problem == "self": state.task("R").depends_on = ["R"]
    elif problem == "duplicate": state.stories[0].tasks.append(Task(id="R", story_id="S"))
    elif problem == "bypass": state.task("R").depends_on = ["F"]
    elif problem == "added":
        state.plan_admission["lots"][0]["members"] = ["F", "V", "R"]
        state.stories[0].tasks.append(Task(id="NEW", story_id="S", depends_on=["V"]))
    with pytest.raises(milestones.MilestoneError):
        milestones.milestone_owners(state, milestones.strict_graph(state))


async def test_pipeline_vertical_probe_persists_receipt_before_downstream(monkeypatch):
    state, contract = setup()
    root = workspace_dir(state.id)
    root.mkdir(parents=True)
    (root / "main.py").write_text("pass")
    pipeline = Pipeline(state, FakeRunner())
    async def probe(contract, frozen, snapshot):
        assert frozen != root and frozen.is_dir()
        return vertical_result(acceptance.supervisor_root(state.id), snapshot, contract)
    monkeypatch.setattr(pipeline, "_avertical_probe", probe)
    assert await pipeline._avertical_milestone()
    assert state.plan_admission["vertical_receipt_hash"]
    assert not state.delivery_ready and not pipeline.runner.calls


async def test_missing_vertical_harness_never_spends_repair_calls(monkeypatch):
    state, contract = setup()
    root = workspace_dir(state.id)
    root.mkdir(parents=True)
    (root / "main.py").write_text("pass")
    pipeline = Pipeline(state, FakeRunner())
    async def unavailable(*args): raise RuntimeError("bindings absent")
    monkeypatch.setattr(pipeline, "_avertical_probe", unavailable)
    assert not await pipeline._avertical_milestone()
    assert pipeline._delivery_blocked and not state.delivery_ready and not pipeline.runner.calls


async def test_final_gate_cached_reports_rechecked_against_current_source_and_proofs(monkeypatch):
    state, contract = setup()
    for task in state.stories[0].tasks: task.status = StoryStatus.DONE
    state.stories[0].status = StoryStatus.DONE
    root = workspace_dir(state.id)
    root.mkdir(parents=True)
    (root / "main.py").write_text("pass")
    pipeline = Pipeline(state, FakeRunner())
    assert pipeline._apply_definition_of_done() and not state.delivery_ready
    snapshot = source_snapshot(root).digest
    supervisor = acceptance.supervisor_root(state.id)
    requirement = contract.requirements[0]
    row = {"id": requirement.id, "gate": requirement.gate, "expected": requirement.expected, "status": "PASS",
           "observed": "executed", "reproduction": ["run"], "impact": "none", "limits": [],
           "proofs": [proof(supervisor, kind, "BOOK-01:create", snapshot, contract) for kind in ("X", "V")]}
    atomic_json(supervisor / "reports" / snapshot / "verification-reports.json",
                [{"contract_hash": contract.contract_hash, "snapshot_hash": snapshot, "requirements": [row]}])
    reports_path=supervisor/"reports"/snapshot/"verification-reports.json"
    atomic_json(reports_path.with_name("verification-context.json"),
        {"context":verification_cache_context(contract.contract_hash,snapshot,supervisor),
         "reports_sha256":hashlib.sha256(reports_path.read_bytes()).hexdigest()})
    async def review(*args,**kwargs):return {"status":"REVIEWED"}  # inert admission metatest only
    monkeypatch.setattr(pipeline,"_await_reviewed_configuration",review)
    assert await pipeline._aindependent_acceptance_phase() and state.delivery_ready
    (root / "main.py").write_text("changed")
    assert not await pipeline._aindependent_acceptance_phase() and not state.delivery_ready
    assert state.acceptance_result["status"] == "NOT_VERIFIED"
