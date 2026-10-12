"""Supervisor proof-join metatests; no generated application acceptance issued."""
import hashlib
import json
from dataclasses import asdict
from types import SimpleNamespace
from uuid import uuid4

import pytest

from autospec.validation.coordinator import SupervisorEvidenceStore, _native_browser_packs, _current_rows
from autospec.validation.evidence_join import CROSSED_IDS, join_rechecked_native, publish_backend_receipt
from autospec.validation.support_adapter import AdapterUnavailable, Proof


SNAPSHOT = "a" * 64
ORACLE = "b" * 64


def receipt(root, rid, checks, *, observed=None, kind="X", passed=True):
    path = root / (rid + "-" + uuid4().hex + ".json")
    path.write_bytes(json.dumps(dict(id=rid, snapshot_hash=SNAPSHOT, contract_hash=ORACLE,
        checks=observed, scope="trusted join protocol metatest only; NOT product acceptance")).encode())
    return Proof(kind, str(path), hashlib.sha256(path.read_bytes()).hexdigest(),
                 SNAPSHOT, ORACLE, tuple(checks), passed)


def row(rid, *, status="PASS", complete=True, observed=None, proofs=()):
    return dict(id=rid, status=status, native_complete=complete, observed=observed or [],
        proofs=[asdict(p) for p in proofs], limits=[], reproduction=[],
        snapshot_hash=SNAPSHOT, contract_hash=ORACLE)


@pytest.mark.parametrize("prior,current,expected", [
    ("FAIL", "PASS", "FAIL"), ("NOT_VERIFIED", "PASS", "PASS"),
    ("NOT_VERIFIED", "FAIL", "FAIL"), ("PASS", "NOT_VERIFIED", "NOT_VERIFIED")])
def test_only_fresh_complete_native_replay_can_consume_browser(prior, current, expected):
    first = row("FUN-02", status=prior)
    second = row("FUN-02", status=current)
    assert join_rechecked_native(first, second, row("FUN-02"))["status"] == expected


@pytest.mark.parametrize("which", ["previous", "current"])
def test_incomplete_native_never_promotes_even_with_forged_green_metadata(which):
    first, second = row("FUN-02"), row("FUN-02")
    (first if which == "previous" else second)["native_complete"] = False
    assert join_rechecked_native(first, second, row("FUN-02"))["status"] == "NOT_VERIFIED"


@pytest.mark.parametrize("which,key", [("current", "id"), ("current", "snapshot_hash"),
    ("current", "contract_hash"), ("browser", "snapshot_hash"), ("previous", "contract_hash")])
def test_join_rejects_current_oracle_identity_drift(which, key):
    rows = {name: row("FUN-02") for name in ("previous", "current", "browser")}
    rows[which][key] = "changed"
    with pytest.raises(AdapterUnavailable, match="identity"):
        join_rechecked_native(**rows)


@pytest.mark.parametrize("fault,expected", [(None, True), ("incomplete", False),
    ("empty", False), ("payload", False), ("tampered", "error"), ("wrong_pass", "error")])
async def test_backend_alias_requires_actual_retained_complete_execution(tmp_path, fault, expected):
    store = SupervisorEvidenceStore(tmp_path, SNAPSHOT, ORACLE)
    observed = [dict(check="scope", passed=True)]
    proof = receipt(tmp_path, "FUN-02", ("FUN-02:scope",), observed=observed,
                    passed=fault != "wrong_pass")
    value = row("FUN-02", observed=observed, proofs=(proof,))
    if fault == "incomplete": value["native_complete"] = False
    if fault == "empty": value["observed"] = []
    if fault == "payload": value["observed"] = [dict(check="scope", passed=False)]
    if fault == "tampered":
        from pathlib import Path
        Path(proof.path).write_bytes(b"changed retained bytes")
    if expected == "error":
        with pytest.raises(AdapterUnavailable): await publish_backend_receipt(store, value)
    else:
        assert await publish_backend_receipt(store, value) is expected
        proofs = await store.proofs("FUN-02")
        assert bool(proofs) is expected
        if expected:
            assert "FUN-02:backend" in proofs[0].checks
            assert proofs[0].type == "X"  # no R authority minted.


@pytest.mark.parametrize("fault,affected,expected", [
    (None, None, "PASS"), ("native_fail", "FUN-02", "FAIL"),
    ("native_missing", "FUN-06", "NOT_VERIFIED"),
    ("native_tampered", "FUN-12", "NOT_VERIFIED"),
    ("fresh_incomplete", "SEC-10", "NOT_VERIFIED"),
    ("fresh_fail", "SEC-12", "FAIL"), ("missing_ui_tag", "FUN-02", "NOT_VERIFIED"),
    ("missing_review", "FUN-06", "NOT_VERIFIED"),
    ("browser_drift", "FUN-12", "NOT_VERIFIED"),
    ("arc_partial", "ARC-06", "NOT_VERIFIED"), ("arc_native_fail", "ARC-06", "FAIL")])
async def test_coordinator_join_order_preserves_scope_and_negative_results(tmp_path, monkeypatch, fault, affected, expected):
    # Verifier execution replaced by explicitly scoped supervisor receipts.
    # Tests wiring/authority, not actual UI/API/DB behavior (qualified separately).
    import autospec.validation.security_contracts as security
    import autospec.validation.business_contracts as business
    import autospec.validation.architecture_contracts as architecture
    import autospec.validation.architecture_browser as architecture_browser
    import autospec.validation.browser_contracts as browser
    ids = sorted(CROSSED_IDS) + ["ARC-06", "UX-01"]
    contract = SimpleNamespace(contract_hash=ORACLE, requirements=[SimpleNamespace(id=rid) for rid in ids])
    store = SupervisorEvidenceStore(tmp_path, SNAPSHOT, ORACLE)
    calls = []
    for rid in ids:
        if not (fault == "missing_review" and rid == affected):
            r = receipt(tmp_path, rid, (rid,), kind="R")
            # External R fixture only; native publication cannot produce R.
            store.contributions[rid] = [r]

    class Pack:
        prefix = ""
        def __init__(self, *args): pass
        async def verify(self, snapshot, *, ids=None):
            chosen = ids or [rid for rid in contract_ids if rid.startswith(self.prefix)]
            calls.append((self.prefix, tuple(chosen), ids is not None))
            rows = []
            for rid in chosen:
                supplied = await store.proofs(rid)
                review = any(p.type == "R" and p.passed for p in supplied)
                complete = not (fault == "native_missing" and rid == affected)
                if ids is not None and fault == "fresh_incomplete" and rid == affected: complete = False
                failed = (rid == affected and (fault in {"native_fail", "arc_native_fail"} or
                          ids is not None and fault == "fresh_fail"))
                observed = [dict(check="actual_metatest_execution", passed=not failed)] if complete else []
                tag = rid + ":" + {"FUN-02":"ui_clear", "FUN-06":"ui_draft", "FUN-12":"ui_refresh",
                                    "ARC-06":"error_client"}.get(rid, "browser_check")
                supplemental = any(p.type == "V" for p in supplied) and (
                    rid.startswith("SEC-") or any(tag in p.checks for p in supplied))
                value = row(rid, status="FAIL" if failed else "PASS" if complete and review and supplemental
                            else "NOT_VERIFIED", complete=complete, observed=observed)
                if observed:
                    x = receipt(tmp_path, rid, (rid + ":actual_metatest_execution",), observed=observed, passed=not failed)
                    value["proofs"] = [asdict(x)] + [asdict(p) for p in supplied]
                    if ids is None and fault == "native_tampered" and rid == affected:
                        from pathlib import Path
                        Path(x.path).write_bytes(b"tampered")
                rows.append(value)
            return dict(snapshot_hash=snapshot, contract_hash=ORACLE, requirements=rows)
    contract_ids = set(ids)
    for module, name, prefix in ((security, "SecurityVerifier", "SEC-"),
            (business, "BusinessContractVerifier", "FUN-"), (architecture, "ArchitectureContractVerifier", "ARC-")):
        monkeypatch.setattr(module, name, type(name, (Pack,), {"prefix":prefix}))

    async def arc(*args):
        observed = [dict(check="error_client", passed=True)]
        complete = fault != "arc_partial"
        x = receipt(tmp_path, "ARC-06", ("ARC-06:error_client",) if complete else ("ARC-06:partial",), observed=observed)
        v = receipt(tmp_path, "ARC-06", ("ARC-06:visual",), kind="V")
        return dict(snapshot_hash=SNAPSHOT, contract_hash=ORACLE,
                    requirements=[row("ARC-06", status="PASS" if complete else "NOT_VERIFIED", proofs=(x,v))])
    monkeypatch.setattr(architecture_browser, "collect_architecture_client", arc)
    monkeypatch.setattr(browser, "BROWSER_IDS", tuple(sorted(CROSSED_IDS)) + ("UX-01",))
    monkeypatch.setattr(browser, "PlaywrightHarness", lambda *a, **k: None)
    class Browser:
        def __init__(self, *args): pass
        async def verify(self, snapshot):
            rows = []
            for rid in browser.BROWSER_IDS:
                supplied = await store.proofs(rid)
                backend = rid == "UX-01" or any(rid + ":backend" in p.checks for p in supplied)
                review = any(p.type == "R" for p in supplied)
                failed = any(not p.passed for p in supplied)
                tag = rid + ":" + {"FUN-02":"ui_clear", "FUN-06":"ui_draft", "FUN-12":"ui_refresh"}.get(rid, "browser_check")
                if fault == "missing_ui_tag" and rid == affected: tag = rid + ":other"
                x = receipt(tmp_path, rid, (tag,), observed=[dict(check=tag, passed=True)])
                v = receipt(tmp_path, rid, (rid + ":visual",), kind="V")
                value = row(rid, status="FAIL" if failed else "PASS" if backend and review else "NOT_VERIFIED",
                            proofs=(x,v))
                rows.append(value)
            return dict(snapshot_hash="c"*64 if fault == "browser_drift" else snapshot,
                        contract_hash=ORACLE, requirements=rows)
    monkeypatch.setattr(browser, "BrowserVerifier", Browser)
    harness = SimpleNamespace(adapter=SimpleNamespace(),
        bindings=SimpleNamespace(browser_bindings={}, browser_routes={}))
    result, limits = await _native_browser_packs(contract, harness, store, SNAPSHOT)
    assert set(result) == set(ids) if fault != "browser_drift" else set(ids) - {"UX-01"}
    if affected is None:
        assert not limits
        assert {r["status"] for r in result.values()} == {"PASS"}
        assert {rid for prefix, chosen, replay in calls if replay for rid in chosen} == CROSSED_IDS
    else:
        assert result[affected]["status"] == expected, result[affected]
    if fault in {"native_fail", "native_missing", "native_tampered"}:
        assert not any(affected in chosen for _, chosen, replay in calls if replay)
    if fault != "native_tampered":
        assert all(Proof(**p).intact(snapshot_hash=SNAPSHOT, contract_hash=ORACLE)
                   for value in result.values() for p in value["proofs"])


@pytest.mark.parametrize("fault", ["duplicate", "missing", "unknown", "snapshot", "oracle"])
def test_pack_identity_must_be_current_and_exact(fault):
    report = dict(snapshot_hash=SNAPSHOT, contract_hash=ORACLE, requirements=[row("FUN-02")])
    if fault == "duplicate": report["requirements"].append(row("FUN-02"))
    if fault == "missing": report["requirements"] = []
    if fault == "unknown": report["requirements"] = [row("FUN-01")]
    if fault == "snapshot": report["snapshot_hash"] = "c"*64
    if fault == "oracle": report["requirements"][0]["contract_hash"] = "c"*64
    with pytest.raises(AdapterUnavailable): _current_rows(report, {"FUN-02"}, SNAPSHOT, ORACLE)


@pytest.mark.parametrize("ids", ["SEC-10", [], ["SEC-10", "SEC-10"], ["FUN-02"], ["SEC-10", 1]])
async def test_security_selector_rejects_before_native_ports(tmp_path, ids):
    from autospec.validation.security_contracts import SecurityVerifier
    from tests.fixtures.security.app import SecurityApplication, security_contract
    contract = security_contract()
    app = SecurityApplication(tmp_path / "product", only="SEC-10")
    adapter, snapshot, _ = app.adapter(contract)
    async def forbidden(): raise AssertionError("invalid selector must not inspect/execute native ports")
    adapter._ports["snapshot"] = forbidden
    with pytest.raises(ValueError, match="unique security"):
        await SecurityVerifier(contract, adapter).verify(snapshot, ids=ids)


@pytest.mark.parametrize("broken,expected", [(False, "NOT_VERIFIED"), (True, "FAIL")])
async def test_real_trusted_security_fixture_completion_is_not_acceptance(tmp_path, broken, expected):
    from autospec.validation.security_contracts import SecurityVerifier
    from tests.fixtures.security.app import SecurityApplication, security_contract
    contract = security_contract()
    app = SecurityApplication(tmp_path / "product", only="SEC-10", broken="SEC-10" if broken else None)
    adapter, snapshot, _ = app.adapter(contract)
    value, = await SecurityVerifier(contract, adapter).verify(snapshot, ids=["SEC-10"])
    assert value["native_complete"] is True and value["status"] == expected
    # Actual trusted factory fixture API/SQLite, not generated code on host.
    store = SupervisorEvidenceStore(app.root.parent, snapshot, contract.contract_hash)
    assert await publish_backend_receipt(store, value)
    assert any("SEC-10:backend" in p.checks and p.passed is not broken for p in await store.proofs("SEC-10"))
