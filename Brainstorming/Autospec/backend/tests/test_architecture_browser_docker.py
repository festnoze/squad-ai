"""One new transport proof; fixture application is never imported on the host."""
import hashlib
import json
import os
import shutil
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from autospec.orchestrator.sandbox import _container_identity
from autospec.validation.architecture_browser import collect_architecture_client
from autospec.validation.browser_contracts import PlaywrightHarness
from autospec.validation.final_gate import source_snapshot
from autospec.validation.product_harness import OwnedProductHarnessSession
from autospec.validation.support_adapter import Proof
from tests.fixtures.browser.app import browser_contract
from tests import test_product_harness as fixture


@pytest.mark.skipif(os.environ.get("AUTOSPEC_ARC_BROWSER_DOCKER") != "1", reason="explicit single ARC-06 NETNONE transport proof")
async def test_real_owned_netnone_architecture_client_transport(tmp_path, monkeypatch):
    from playwright.async_api import BrowserType
    async def forbidden_host_launch(*args, **kwargs):
        raise AssertionError("host Chromium launch is forbidden for this native proof")
    monkeypatch.setattr(BrowserType, "launch", forbidden_host_launch)
    contract = browser_contract()
    monkeypatch.setattr(fixture, "CONTRACT", contract.contract_hash)
    source = tmp_path / "source"
    source.mkdir()
    for name in ("pyproject.toml", "uv.lock"):
        shutil.copyfile(fixture.ROOT / name, source / name)
    # Materialize a constant independent fixture copy; no historical product is
    # repaired and no application package/config/script executes on the host.
    text = (fixture.ROOT / "main.py").read_text(encoding="utf-8")
    before = 'return e or {"id":a["id"],"role":a["role"]}'
    assert text.count(before) == 1
    text = text.replace(before, 'return e or {"id":a["id"],"role":a["role"],"display_name":a["email"].split("@")[0].capitalize()}')
    begin, end = text.index("HTML='''"), text.index('@app.get("/",response_class=HTMLResponse)')
    text = text[:begin] + 'from pathlib import Path\nHTML=Path(__file__).with_name("architecture_native.html").read_text(encoding="utf-8")\n' + text[end:]
    (source / "main.py").write_bytes(text.encode())
    shutil.copyfile(Path(__file__).parent / "fixtures/browser/architecture_native.html", source / "architecture_native.html")
    snapshot = source_snapshot(source).digest
    definition = fixture.fixture_definition()
    definition["metadata"]["browser_probes"] = {"architecture_client": {
        "identity_pointer": "/display_name", "error_presentation": "server_message"}}
    fixtures_path = fixture.reviewed_fixture_file(tmp_path, source, snapshot, definition)
    content = json.loads(fixtures_path.read_bytes())
    content.pop("review")
    content["cases"] = {"ARC-06": definition}
    fingerprint = hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=True).encode()).hexdigest()
    review_path = tmp_path / "fixture-review.json"
    fixture.write_json(review_path, {"scope": "trusted isolated transport metatest, not GPT/product review", "fingerprint": fingerprint})
    review = Proof("R", str(review_path), hashlib.sha256(review_path.read_bytes()).hexdigest(), snapshot,
                  contract.contract_hash, ("PRODUCT:fixtures", "PRODUCT:fixtures:" + fingerprint))
    fixture.write_json(fixtures_path, {**content, "review": asdict(review)})
    bindings = fixture.make_bindings(tmp_path, source, snapshot)
    bindings = replace(bindings, browser_bindings={"email": "#email", "password": "#password", "login": "#login",
        "ticket_nav": "#ticket-nav", "current_user_name": "#current-user-name", "error": "#error"}, fixture_fingerprint=fingerprint)
    bindings = replace(bindings, review=replace(bindings.review, checks=("PRODUCT:bindings", "PRODUCT:bindings:" + bindings.fingerprint())))
    async def identity(): return source_snapshot(source).digest
    async def oracle(): return contract.contract_hash
    async with OwnedProductHarnessSession(bindings, source_root=source, stage_root=tmp_path / "stage",
            evidence_root=tmp_path / "evidence", cache_root=tmp_path / "cache", fixtures_path=fixtures_path,
            snapshot_hash=identity, contract_hash=oracle) as subject:
        runtime_identity = subject.runtime.inspect_configuration()
        harness = PlaywrightHarness(subject.adapter, bindings=bindings.browser_bindings, routes=bindings.browser_routes)
        report = await collect_architecture_client(contract, harness, snapshot)
        assert report["status"] == "PASS", report
        assert report["browser_environment"]["qualified"] is True
        assert report["browser_environment"]["host_chromium"] is False
        assert report["browser_environment"]["parent_network_mode"] == "none"
        assert report["browser_environment"]["network_mode"] == "container:" + runtime_identity["container_id"]
        row = report["requirements"][0]
        assert all(c["passed"] for c in row["observed"])
        assert any(r.get("path") == "/api/auth/me" and r.get("status") == 200 for r in row["reproduction"])
        assert any(r.get("path", "").startswith("/api/tickets/") and r.get("status") == 404 for r in row["reproduction"])
        for p in row["proofs"]:
            assert Proof(**{**p, "checks": tuple(p["checks"])}).intact(snapshot_hash=snapshot, contract_hash=contract.contract_hash)
        assert any(p["type"] == "X" and "ARC-06:error_client" in p["checks"] for p in row["proofs"])
        assert any(p["type"] == "V" for p in row["proofs"])
        assert source_snapshot(source).digest == snapshot
        dest = os.environ.get("AUTOSPEC_ARC_BROWSER_EVIDENCE")
        if dest:
            target = Path(dest) / "docker-nominal"
            target.mkdir(parents=True, exist_ok=True)
            for p in row["proofs"]:
                original = Path(p["path"])
                destination = target / original.name
                shutil.copyfile(original, destination)
                assert hashlib.sha256(destination.read_bytes()).hexdigest() == p["sha256"]
                p["path"] = str(destination.resolve())
            fixture.write_json(target / "report.json", {"report": report, "runtime": runtime_identity,
                "scope": "one genuine NETNONE transport/collector metatest, not full ARC or product acceptance"})
    assert _container_identity("docker", runtime_identity["container_id"], runtime_identity["owner"]) is None
