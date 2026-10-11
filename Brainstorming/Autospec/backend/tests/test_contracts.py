import dataclasses
import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from autospec.contracts import ContractError, ContractFact, ContractStore, import_contract, probe_facts
from autospec.spec_import import parse_contract_import


BRIEF = "Lending: POST /loans. Title has 2..12 characters. requested -> returned is forbidden."
REFERENCE = """| ID | Gate / preuve | Expected |
| LIB-01 | B / X | POST /loans creates a loan. |
| LIB-02 | M / X | Title has 2..12 characters. |
| LIB-03 | B / X+R | requested -> returned is forbidden. |
"""


def lending_contract():
    return import_contract(BRIEF, REFERENCE, reviewed_by="independent-reviewer", facts=[
        ContractFact.create("route", "route", 201, ["LIB-01"], "POST /loans"),
        ContractFact.create("bound", "bound", 422, ["LIB-02"], "2..12 characters"),
        ContractFact.create("transition", "transition", 409, ["LIB-03"], "requested -> returned is forbidden"),
    ])


class LendingApplication:
    """Executable non-support product fixture, backed by a real SQLite table."""

    def __init__(self, broken=False):
        self.broken = broken
        self.db = sqlite3.connect(":memory:")
        self.db.execute("CREATE TABLE loans (id INTEGER PRIMARY KEY, title TEXT, state TEXT)")

    def request(self, method, path, body):
        create_route = "/borrow" if self.broken else "/loans"
        if method == "POST" and path == create_route:
            title = body["title"]
            if not self.broken and not 2 <= len(title) <= 12:
                return 422
            self.db.execute("INSERT INTO loans(title,state) VALUES (?, 'requested')", (title,))
            self.db.commit()
            return 201
        if method == "PATCH" and path == "/loans/1":
            if not self.broken and body["state"] == "returned":
                return 409
            self.db.execute("UPDATE loans SET state=? WHERE id=1", (body["state"],))
            self.db.commit()
            return 200
        return 404

    def probes(self):
        # Create independently for the transition probe, even when the public
        # route differs; observations are not used to rewrite the oracle.
        def transition():
            route = "/borrow" if self.broken else "/loans"
            self.request("POST", route, {"title": "Atlas"})
            return self.request("PATCH", "/loans/1", {"state": "returned"})
        return {
            "route": lambda: self.request("POST", "/loans", {"title": "Atlas"}),
            "bound": lambda: self.request("POST", "/borrow" if self.broken else "/loans", {"title": "x" * 13}),
            "transition": transition,
        }


def test_support_reference_exact_57_ids_and_source_hashes():
    docs = Path(__file__).resolve().parents[2] / "docs/validation/support-client"
    brief = (docs / "01_specification.md").read_bytes().decode("utf-8")
    reference = (docs / "02_requirements_verification.md").read_bytes().decode("utf-8")
    contract = parse_contract_import(brief, reference, reviewed_by="reviewer")
    expected = {f"{prefix}-{n:02d}" for prefix, count in
                [("SEC", 15), ("FUN", 13), ("ARC", 9), ("UX", 8), ("TST", 6), ("OPS", 6)]
                for n in range(1, count + 1)}
    assert {r.id for r in contract.requirements} == expected
    assert len(contract.requirements) == 57
    assert sum(r.gate in {"B", "M"} for r in contract.requirements) == 56
    assert contract.brief == brief  # no legacy 20,000-character clipping
    assert contract.brief_hash == hashlib.sha256(brief.encode()).hexdigest()
    assert contract.reference_hash == hashlib.sha256(reference.encode()).hexdigest()


@pytest.mark.parametrize("broken,expected", [(False, "pass"), (True, "fail")])
def test_functional_other_application_detects_route_bound_transition_divergence(broken, expected):
    app = LendingApplication(broken)
    contract = lending_contract()
    try:
        result = probe_facts(contract, app.probes(), snapshot_hash="fixture-revision")
        assert result["status"] == expected
        assert result["contract_hash"] == contract.contract_hash
        assert {r["status"] for r in result["facts"]} == ({"FAIL"} if broken else {"PASS"})
        if not broken:
            assert app.db.execute("SELECT COUNT(*) FROM loans WHERE state='returned'").fetchone()[0] == 0
            assert app.db.execute("SELECT COUNT(*) FROM loans WHERE length(title)>12").fetchone()[0] == 0
    finally:
        app.db.close()


def test_external_store_write_once_and_tampering_detected(tmp_path):
    product = tmp_path / "product"
    product.mkdir()
    with pytest.raises(ContractError, match="product-write"):
        ContractStore(product / "tests", product_write_roots=[product])
    store = ContractStore(tmp_path / "independent", product_write_roots=[product])
    contract = lending_contract()
    path = store.save(contract)
    assert store.save(contract) == path  # idempotence does not overwrite
    assert store.load(path) == contract
    data = json.loads(path.read_text(encoding="utf-8"))
    data["facts"][0]["expected"] = 404
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ContractError, match="mismatch"):
        store.load(path)
    # Even changing all embedded hashes does not replace the pinned oracle.
    replacement = import_contract(BRIEF, REFERENCE, reviewed_by="other reviewer", facts=contract.facts)
    path.write_text(json.dumps(replacement.payload() | {"contract_hash": replacement.contract_hash}), encoding="utf-8")
    with pytest.raises(ContractError, match="mismatch"):
        store.load(path)


def test_sources_and_expectations_are_frozen_and_require_review():
    with pytest.raises(ContractError, match="review"):
        import_contract(BRIEF, REFERENCE, reviewed_by="")
    with pytest.raises(ContractError, match="unique"):
        import_contract(BRIEF, REFERENCE + REFERENCE, reviewed_by="reviewer")
    with pytest.raises(ContractError, match="anchor"):
        import_contract(BRIEF, REFERENCE, reviewed_by="reviewer", facts=[
            ContractFact.create("invented", "DTO", {}, ["LIB-01"], "not in source")])
    contract = lending_contract()
    with pytest.raises(dataclasses.FrozenInstanceError):
        contract.brief = "product-implied requirement"
    fact = ContractFact.create("object", "DTO", {"a": [1]}, ["LIB-01"], "POST /loans")
    mutated = fact.expected
    mutated["a"].append(2)
    assert fact.expected == {"a": [1]}


def test_missing_or_unavailable_probe_never_passes_and_error_details_are_redacted():
    def unavailable():
        raise RuntimeError("credential=secret")
    result = probe_facts(lending_contract(), {"route": unavailable}, snapshot_hash="revision")
    assert result["status"] == "not_verified"
    assert "secret" not in json.dumps(result)
    with pytest.raises(ContractError, match="snapshot"):
        probe_facts(lending_contract(), {}, snapshot_hash="")
