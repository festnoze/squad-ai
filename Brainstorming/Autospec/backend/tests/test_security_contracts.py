import hashlib
import json
import asyncio
import socket
import threading
import time
from pathlib import Path

import pytest

from autospec.contracts import ContractError, import_contract
from autospec.validation.security_contracts import SECURITY_IDS, SecurityIdentityError, SecurityVerifier, security_generation_requirements
from autospec.validation.support_adapter import HttpxSupportAdapter, Proof
from tests.fixtures.security.app import PASSWORDS, SecurityApplication, security_contract


@pytest.mark.parametrize("rid", SECURITY_IDS)
async def test_good_executable_family_and_missing_browser_stays_not_verified(tmp_path, rid):
    contract = security_contract()
    app = SecurityApplication(tmp_path / "product", only=rid)
    adapter, snapshot, _ = app.adapter(contract)
    results = await SecurityVerifier(contract, adapter).verify(snapshot)
    result = next(result for result in results if result["id"] == rid)
    assert result["status"] == ("NOT_VERIFIED" if rid in {"SEC-01", "SEC-10", "SEC-12"} else "PASS"), result
    assert len(results) == 15 and len({r["id"] for r in results}) == 15
    assert all(r["status"] == "NOT_VERIFIED" for r in results if r["id"] != rid)
    if rid in {"SEC-10", "SEC-12"}:
        assert any("V" in limit for limit in result["limits"])


@pytest.mark.parametrize("rid", SECURITY_IDS)
async def test_bad_executable_family_is_detected_not_relabelled_by_review(tmp_path, rid):
    contract = security_contract()
    app = SecurityApplication(tmp_path / "product", broken=rid, only=rid)
    adapter, snapshot, _ = app.adapter(contract)
    results = await SecurityVerifier(contract, adapter).verify(snapshot)
    result = next(result for result in results if result["id"] == rid)
    assert result["status"] == "FAIL", result
    assert any(not check["passed"] for check in result["observed"])
    assert any(p["type"] == "X" and p["passed"] is False and rid in p["checks"] for p in result["proofs"])


async def test_full_good_fixture_auth_and_sqlite_are_real_and_proofs_redacted(tmp_path):
    contract = security_contract()
    app = SecurityApplication(tmp_path / "product")
    adapter, snapshot, _ = app.adapter(contract)
    results = await SecurityVerifier(contract, adapter).verify(snapshot)
    assert {r["id"] for r in results} == set(SECURITY_IDS)
    assert {r["id"] for r in results if r["status"] == "NOT_VERIFIED"} == {"SEC-01", "SEC-10", "SEC-12"}
    assert not any(r["status"] == "FAIL" for r in results)
    text = json.dumps(results, ensure_ascii=False)
    for password in PASSWORDS.values():
        assert password not in text
    for result in results:
        for proof in result["proofs"]:
            path = Path(proof["path"])
            assert hashlib.sha256(path.read_bytes()).hexdigest() == proof["sha256"]
            assert result["id"] in proof["checks"]
            for password in PASSWORDS.values():
                assert password not in path.read_text(encoding="utf-8")


async def test_missing_review_does_not_make_all_x_passes_a_requirement_pass(tmp_path):
    contract = security_contract()
    app = SecurityApplication(tmp_path / "product", only="SEC-03")
    adapter, snapshot, _ = app.adapter(contract, reviews=False)
    results = await SecurityVerifier(contract, adapter).verify(snapshot)
    result = next(r for r in results if r["id"] == "SEC-03")
    assert result["status"] == "NOT_VERIFIED"
    assert all(c["passed"] for c in result["observed"])


async def test_empty_formal_profile_has_no_passes_or_product_execution(tmp_path):
    original = security_contract()
    contract = import_contract(original.brief, original.reference, reviewed_by="reviewer", facts=[])
    app = SecurityApplication(tmp_path / "product")
    adapter, snapshot, _ = app.adapter(contract)
    results = await SecurityVerifier(contract, adapter).verify(snapshot)
    assert {r["status"] for r in results} == {"NOT_VERIFIED"}
    assert not app.db_path.exists()


async def test_oracle_tampering_or_foreign_snapshot_refuses_entire_run(tmp_path):
    contract = security_contract()
    app = SecurityApplication(tmp_path / "product", only="SEC-03")
    adapter, snapshot, oracle = app.adapter(contract)
    with pytest.raises(SecurityIdentityError):
        await SecurityVerifier(contract, adapter).verify("foreign-revision")
    data = json.loads(oracle.read_text(encoding="utf-8"))
    data["facts"][0]["expected"]["password"]["min"] = 1
    oracle.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises((ContractError, SecurityIdentityError)):
        await SecurityVerifier(contract, adapter).verify(snapshot)


def test_stale_broken_or_unmapped_proofs_are_not_intact(tmp_path):
    path = tmp_path / "proof.json"
    path.write_text("{}", encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    proof = Proof("R", str(path), digest, "revision", "contract", ("SEC-03",))
    assert proof.intact(snapshot_hash="revision", contract_hash="contract")
    assert not proof.intact(snapshot_hash="another", contract_hash="contract")
    path.write_text("changed", encoding="utf-8")
    assert not proof.intact(snapshot_hash="revision", contract_hash="contract")


def test_runtime_adapter_has_no_route_or_auth_rewrite_fallback(tmp_path):
    async def unused(*args, **kwargs):
        raise AssertionError("not invoked")
    with pytest.raises(ValueError, match="isolated"):
        HttpxSupportAdapter(base_url="https://external.example", auth_path="/api/auth/login", origin="https://external.example",
            csrf_field="csrf_token", evidence_root=tmp_path, prepare=unused, observe=unused, snapshot=unused, oracle=unused)


async def test_runtime_transport_real_tcp_http_nominal_argon2_and_sqlite(tmp_path):
    import uvicorn
    contract = security_contract()
    app = SecurityApplication(tmp_path / "product", only="SEC-03")
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(128)
    url = f"http://127.0.0.1:{sock.getsockname()[1]}"
    server = uvicorn.Server(uvicorn.Config(app.app, log_level="error", access_log=False))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 5
        while not server.started and time.monotonic() < deadline:
            await asyncio.sleep(0.01)
        assert server.started
        adapter, snapshot, _ = app.adapter(contract, base_url=url, real_http=True)
        results = await SecurityVerifier(contract, adapter).verify(snapshot)
        result = next(r for r in results if r["id"] == "SEC-03")
        assert result["status"] == "PASS", result
        one, two = adapter.connect_db(), adapter.connect_db()
        try:
            assert one is not two
            assert one.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] > 0
        finally:
            one.close()
            two.close()
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        sock.close()
        assert not thread.is_alive()


async def test_unreadable_review_provider_stays_not_verified_and_closes_clients(tmp_path):
    contract = security_contract()
    app = SecurityApplication(tmp_path / "product", only="SEC-03")
    adapter, snapshot, _ = app.adapter(contract)
    async def unavailable(rid):
        raise OSError("isolated proof missing")
    adapter._ports["proofs"] = unavailable
    results = await SecurityVerifier(contract, adapter).verify(snapshot)
    assert next(r for r in results if r["id"] == "SEC-03")["status"] == "NOT_VERIFIED"
    assert not adapter._clients


def test_generation_fragment_preserves_exact_source_expectations_and_profile():
    contract = security_contract()
    fragment = security_generation_requirements(contract)
    source = {r.id: r.expected for r in contract.requirements}
    assert fragment["contract_hash"] == contract.contract_hash
    assert {r["id"]: r["expected"] for r in fragment["requirements"]} == {rid: source[rid] for rid in SECURITY_IDS}
    fragment["formal_profile"]["password"]["min"] = 1
    assert security_generation_requirements(contract)["formal_profile"]["password"]["min"] == 14


async def test_stale_review_proof_cannot_promote_passing_probes(tmp_path):
    contract = security_contract()
    app = SecurityApplication(tmp_path / "product", only="SEC-03")
    adapter, snapshot, _ = app.adapter(contract, reviews=False)
    path = tmp_path / "stale-review.json"
    path.write_text("changed after review", encoding="utf-8")
    async def stale(rid):
        return [Proof("R", str(path), "0" * 64, snapshot, contract.contract_hash, (rid,))]
    adapter._ports["proofs"] = stale
    results = await SecurityVerifier(contract, adapter).verify(snapshot)
    result = next(r for r in results if r["id"] == "SEC-03")
    assert result["status"] == "NOT_VERIFIED"
    assert all(c["passed"] for c in result["observed"])
    assert any("stale" in limit for limit in result["limits"])


async def test_snapshot_mutation_during_run_invalidates_all_results_and_closes(tmp_path):
    contract = security_contract()
    app = SecurityApplication(tmp_path / "product", only="SEC-03")
    adapter, snapshot, _ = app.adapter(contract)
    calls = 0
    async def changed():
        nonlocal calls
        calls += 1
        return snapshot if calls == 1 else "changed-snapshot"
    adapter._ports["snapshot"] = changed
    with pytest.raises(SecurityIdentityError, match="changed"):
        await SecurityVerifier(contract, adapter).verify(snapshot)
    assert not adapter._clients
