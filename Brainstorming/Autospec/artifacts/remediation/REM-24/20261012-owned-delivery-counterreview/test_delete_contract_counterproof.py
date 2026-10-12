"""Read-only API counterproof: all external effects replaced, no product run."""
from types import SimpleNamespace

import httpx
import pytest

from autospec.api import server
from autospec.models import ProjectState

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("kind", ["fullstack", "cli"])
@pytest.mark.parametrize("flushed", [False, True])
@pytest.mark.parametrize("live_pipeline", [False, True])
async def test_delete_contract_uses_external_journal_even_before_state_flush(
    tmp_path, monkeypatch, kind, flushed, live_pipeline
):
    project = "delete-contract-counterproof"
    state = ProjectState(
        id=project, name="trusted meta fixture", goal="no generation",
        acceptance_contract_hash="a" * 64, technical_stack={"kind": kind},
        deployed_image="sha256:" + "b" * 64 if flushed else "",
        deployed_container="c" * 64 if flushed and kind == "fullstack" else "",
        deploy_status=("deployed" if kind == "fullstack" else "packaged") if flushed else "",
    )
    calls = []
    async def dispose():
        calls.append(("dispose", {}))
    pipeline = SimpleNamespace(state=state, adispose=dispose)
    monkeypatch.setattr(server, "pipelines", {project: pipeline} if live_pipeline else {})
    monkeypatch.setattr(server, "load_state", lambda _id: state)
    monkeypatch.setattr(server, "_force_delete_workspace", lambda _id: True)
    monkeypatch.setattr(server.bus, "publish", lambda _event: None)
    def undeploy(_id, **options):
        assert _id == project
        calls.append(("withdraw", options))
        return SimpleNamespace(ok=True, detail="mock exact journal withdrawal")
    monkeypatch.setattr(server.docker_deploy, "undeploy", undeploy)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://trusted-test"
    ) as client:
        response = await client.delete("/api/projects/" + project)
    assert response.status_code == 200, response.text
    withdrawals = [options for action, options in calls if action == "withdraw"]
    assert withdrawals, "contract journal cleanup ignored before UI state flush"
    argument = "packaging_root" if kind == "cli" else "publication_root"
    assert any(argument in options for options in withdrawals), "qualified contract deletion entered legacy name/latest path"
    assert all(set(options) in ({"publication_root"}, {"packaging_root"}) for options in withdrawals), "contract cleanup lacks exact single-journal authority"
