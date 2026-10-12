"""Real trusted fixture HTTP/SQLite/Argon2/Chromium; not product acceptance.

No nominal auth, API or backend response is mocked. The local browser permission
is explicit for this factory-owned fixture; live products use DockerBrowserSession.
"""
from __future__ import annotations

import hashlib
import inspect
import json
import os
import shutil
from pathlib import Path

import pytest
from fastapi.responses import HTMLResponse

from autospec.validation.architecture_browser import collect_architecture_client
from autospec.validation.browser_contracts import PlaywrightHarness
from autospec.validation.support_adapter import Proof
from tests.fixtures.browser.app import BrowserSubject, CONTROLS, browser_contract, fixture_snapshot


class ArchitectureBrowserSubject(BrowserSubject):
    """Narrow good/bad client, with unchanged real fixture auth and server errors."""
    def __init__(self, root, contract, bug=""):
        super().__init__(root, contract, bug)
        self.snapshot = self.digest()
        self.actual_requests = []
        async def snapshot():
            return self.digest()
        self.adapter._ports["snapshot"] = snapshot
        @self.app.middleware("http")
        async def observe(request, call_next):
            response = await call_next(request)
            self.actual_requests.append({"method": request.method, "path": request.url.path, "status": response.status_code})
            return response

    def digest(self):
        return hashlib.sha256((fixture_snapshot(self.browser_bug) +
            hashlib.sha256(Path(inspect.getfile(ArchitectureBrowserSubject)).read_bytes()).hexdigest()).encode()).hexdigest()

    async def prepare(self, case_id, **options):
        manifest = await super().prepare(case_id, **options)
        manifest.metadata["browser_probes"]["architecture_client"] = {
            "identity_pointer": "/display_name", "error_presentation": "server_message"}
        return manifest

    def read(self, con, actor, request, path, ticket_id=None):
        result = super().read(con, actor, request, path, ticket_id)
        if path == "me":
            result["display_name"] = con.execute("SELECT name FROM user_names WHERE user_id=?", (actor["id"],)).fetchone()[0]
            if self.browser_bug == "wrong_actor":
                result["id"] = "different-subject-id"
        return result

    def _routes(self):
        super()._routes()
        self.app.router.routes = [r for r in self.app.router.routes if getattr(r, "path", "") != "/{path:path}"]
        @self.app.get("/{path:path}")
        async def frontend(path: str):
            # This is trusted fixture source, never a repaired/generated product.
            html = Path(inspect.getfile(BrowserSubject)).with_name("ui.html").read_text(encoding="utf-8")
            html = html.replace("__FIXTURE_BUG__", self.browser_bug)
            html = html.replace('<main><h1>Relais fixture</h1>', '<main><h1>Relais fixture</h1><span id="current-user-name"></span>')
            name = "me.name" if self.browser_bug == "wrong_name" else "me.display_name"
            html = html.replace("user=me;csrf=me.csrf_token;", "$('current-user-name').textContent=" + name + ";user=me;csrf=me.csrf_token;")
            if self.browser_bug != "discard_error_dto":
                html = html.replace("const e=Error('Requête refusée');e.status=r.status;throw e",
                    "const dto=await r.json();const e=Error(dto.error.message);e.code=dto.error.code;e.status=r.status;throw e")
                html = html.replace("e.status===409?'Conflit':'Erreur récupérable : réessayez'", "e.message")
            return HTMLResponse(html)

    def harness(self):
        return PlaywrightHarness(self.adapter, bindings={**CONTROLS, "current_user_name": "#current-user-name"},
            routes={"home": "/", "ticket": "/tickets/{id}", "admin": "/admin"},
            executable_path=os.environ.get("AUTOSPEC_TRUSTED_CHROMIUM"), trusted_fixture_local_browser=True)


def retain(report, subject, name):
    base = os.environ.get("AUTOSPEC_ARC_BROWSER_EVIDENCE")
    if not base:
        return
    target = Path(base) / name
    target.mkdir(parents=True, exist_ok=True)
    for row in report["requirements"]:
        for proof in row["proofs"]:
            original = Path(proof["path"]).resolve()
            assert original.is_relative_to(subject.root.parent.resolve())
            destination = target / original.name
            shutil.copyfile(original, destination)
            proof["path"] = str(destination.resolve())
            assert hashlib.sha256(destination.read_bytes()).hexdigest() == proof["sha256"]
    payload = {"scope": "trusted real fixture observer metatest, not generated-product qualification",
            "observer_sha256": hashlib.sha256(Path(inspect.getfile(collect_architecture_client)).read_bytes()).hexdigest(),
            "actual_server_requests": subject.actual_requests, "report": report}
    (target / "report.json").write_bytes(json.dumps(payload, sort_keys=True, ensure_ascii=True).encode())


@pytest.mark.parametrize("bug", ["", "wrong_name", "discard_error_dto", "wrong_actor"])
async def test_actual_architecture_browser_nominal_and_dto_counterexamples(tmp_path, bug):
    contract = browser_contract()
    subject = ArchitectureBrowserSubject(tmp_path / "subject", contract, bug)
    subject.start_http()
    try:
        report = await collect_architecture_client(contract, subject.harness(), subject.snapshot)
        row = report["requirements"][0]
        assert row["status"] == ("FAIL" if bug else "PASS"), row
        assert row["scope"].endswith("not full ARC-06 acceptance")
        assert row["expected"] == next(r.expected for r in contract.requirements if r.id == "ARC-06")
        assert any(r["path"] == "/api/auth/me" and r["status"] == 200 for r in subject.actual_requests)
        assert any(r["path"].startswith("/api/tickets/") and r["status"] == 404 for r in subject.actual_requests)
        x = [Proof(**{**p, "checks": tuple(p["checks"])}) for p in row["proofs"] if p["type"] == "X"]
        assert len(x) == 1 and "ARC-06:error_client" in x[0].checks
        assert x[0].passed is (not bool(bug))
        assert x[0].intact(snapshot_hash=subject.snapshot, contract_hash=contract.contract_hash)
        assert any(p["type"] == "V" for p in row["proofs"])
        if bug:
            assert any(c["passed"] is False for c in row["observed"])
        else:
            assert row["limits"] == [] and all(c["passed"] for c in row["observed"])
        serialized = json.dumps(report)
        assert "csrf_token" not in serialized
        for account in subject.adapter.manifest.accounts.values():
            assert account.password not in serialized
        retain(report, subject, bug or "nominal")
    finally:
        subject.stop_http()
        await subject.adapter.close()


async def test_missing_reviewed_identity_locator_is_nv_not_a_guess(tmp_path):
    subject = ArchitectureBrowserSubject(tmp_path / "subject", browser_contract())
    harness = subject.harness()
    harness.bindings.pop("current_user_name")
    report = await collect_architecture_client(subject.contract, harness, subject.snapshot)
    assert report["status"] == "NOT_VERIFIED"
    assert not report["requirements"][0]["proofs"]
    assert any("bindings absent" in limit for limit in report["requirements"][0]["limits"])


async def test_source_snapshot_drift_is_nv_before_browser_execution(tmp_path):
    subject = ArchitectureBrowserSubject(tmp_path / "subject", browser_contract())
    report = await collect_architecture_client(subject.contract, subject.harness(), "f" * 64)
    assert report["status"] == "NOT_VERIFIED"
    assert not report["requirements"][0]["proofs"]


async def test_fixture_actor_changed_after_navigation_cannot_publish_complete_x(tmp_path):
    subject = ArchitectureBrowserSubject(tmp_path / "subject", browser_contract())
    subject.start_http()
    try:
        original = subject.adapter.snapshot_hash
        calls = 0
        async def changed_fixture():
            nonlocal calls
            calls += 1
            if calls == 2:
                subject.adapter.manifest.metadata["changed_after_browser_navigation"] = True
            return await original()
        subject.adapter.snapshot_hash = changed_fixture
        report = await collect_architecture_client(subject.contract, subject.harness(), subject.snapshot)
        row = report["requirements"][0]
        assert row["status"] == "NOT_VERIFIED", row
        assert any("fixture/actor identity drift" in limit for limit in row["limits"])
        assert not any(p["type"] == "X" and p["passed"] and "ARC-06:error_client" in p["checks"] for p in row["proofs"])
    finally:
        subject.stop_http()
        await subject.adapter.close()
