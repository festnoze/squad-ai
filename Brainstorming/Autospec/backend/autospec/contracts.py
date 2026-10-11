"""Versioned acceptance oracles derived from source documents, never product code.

The store is outside every product-write root. Actual denial of access to that
store is the execution backend's responsibility; a filesystem flag is not an
isolation boundary. Callers must review extracted facts before freezing them.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable


class ContractError(ValueError):
    pass


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Requirement:
    id: str
    gate: str
    expected: str
    required_evidence: tuple[str, ...]


@dataclass(frozen=True)
class ContractFact:
    id: str
    kind: str
    expected_json: str
    requirement_ids: tuple[str, ...]
    source_excerpt: str

    @classmethod
    def create(cls, id: str, kind: str, expected: Any, requirement_ids: Iterable[str], source_excerpt: str):
        return cls(id, kind, _json(expected), tuple(requirement_ids), source_excerpt)

    @property
    def expected(self) -> Any:
        # Return a fresh copy: consumers cannot mutate the frozen expectation.
        return json.loads(self.expected_json)


@dataclass(frozen=True)
class AcceptanceContract:
    brief: str
    reference: str
    requirements: tuple[Requirement, ...]
    facts: tuple[ContractFact, ...]
    reviewed_by: str
    version: int = 1

    @property
    def brief_hash(self) -> str:
        return _hash(self.brief)

    @property
    def reference_hash(self) -> str:
        return _hash(self.reference)

    def payload(self) -> dict:
        return {
            "version": self.version, "brief": self.brief, "reference": self.reference,
            "brief_hash": self.brief_hash, "reference_hash": self.reference_hash,
            "reviewed_by": self.reviewed_by,
            "requirements": [{"id": r.id, "gate": r.gate, "expected": r.expected,
                              "required_evidence": list(r.required_evidence)} for r in self.requirements],
            "facts": [{"id": f.id, "kind": f.kind, "expected": f.expected,
                       "requirement_ids": list(f.requirement_ids), "source_excerpt": f.source_excerpt}
                      for f in self.facts],
        }

    @property
    def contract_hash(self) -> str:
        return _hash(_json(self.payload()))


_ROW = re.compile(r"^\|\s*([A-Z][A-Z0-9_]*-\d+)\s*\|\s*([BMD])\s*/\s*([A-Z+]+)\s*\|\s*(.*?)\s*\|\s*$")


def import_contract(brief: str, reference: str, *, reviewed_by: str,
                    facts: Iterable[ContractFact] = ()) -> AcceptanceContract:
    """Parse a generic B/M/D reference table, retaining the ENTIRE source.

    This does not infer formal facts from prose or claim deterministic LLM
    extraction. Reviewed route/role/transition/bound/DTO/invariant/scenario/
    technical facts are supplied explicitly with a verbatim source anchor.
    """
    if any(not isinstance(value, str) or not value.strip() for value in (brief, reference, reviewed_by)):
        raise ContractError("brief, reference and explicit review are required")
    requirements = []
    for line in reference.splitlines():
        match = _ROW.match(line)
        if match:
            rid, gate, evidence, expected = match.groups()
            if not expected or not set(evidence.split("+")) <= {"X", "R", "V"}:
                raise ContractError(f"invalid expectation/evidence for {rid}")
            requirements.append(Requirement(rid, gate, expected, tuple(evidence.split("+"))))
        elif re.match(r"^\|\s*[A-Z][A-Z0-9_]*-\d+\s*\|", line):
            raise ContractError("malformed requirement row")
    ids = [r.id for r in requirements]
    if not ids or len(ids) != len(set(ids)):
        raise ContractError("requirement IDs must be present and unique")
    formal = tuple(facts)
    fact_ids = [f.id for f in formal]
    if len(fact_ids) != len(set(fact_ids)):
        raise ContractError("fact IDs must be unique")
    for fact in formal:
        if not fact.id or not fact.kind or not fact.requirement_ids:
            raise ContractError("facts require identity, kind and requirement mapping")
        if not set(fact.requirement_ids) <= set(ids):
            raise ContractError(f"unknown requirement for fact {fact.id}")
        if not fact.source_excerpt or (fact.source_excerpt not in brief and fact.source_excerpt not in reference):
            raise ContractError(f"fact {fact.id} has no verbatim source anchor")
        _json(fact.expected)  # reject invalid JSON/non-finite values
    return AcceptanceContract(brief, reference, tuple(requirements), formal, reviewed_by.strip())


class ContractStore:
    """Content-addressed, write-once store outside the product's editable tree."""

    def __init__(self, root: Path, *, product_write_roots: Iterable[Path]):
        self.root = Path(root).resolve()
        write_roots = tuple(Path(p).resolve() for p in product_write_roots)
        if not write_roots:
            raise ContractError("product write roots must be declared")
        if any(self.root == p or self.root.is_relative_to(p) for p in write_roots):
            raise ContractError("oracle store is inside a product-write root")
        self.product_write_roots = write_roots

    def save(self, contract: AcceptanceContract) -> Path:
        if contract.version != 1:
            raise ContractError("unsupported contract version")
        # Recheck resolved roots in case a caller changed a symlink/junction.
        ContractStore(self.root, product_write_roots=self.product_write_roots)
        self.root.mkdir(parents=True, exist_ok=True)
        target = self.root / f"{contract.contract_hash}.json"
        data = contract.payload() | {"contract_hash": contract.contract_hash}
        try:
            with target.open("x", encoding="utf-8", newline="\n") as out:
                out.write(_json(data) + "\n")
        except FileExistsError:
            if self.load(target).contract_hash != contract.contract_hash:
                raise ContractError("existing oracle does not match")
        return target

    def load(self, path: Path) -> AcceptanceContract:
        path = Path(path).resolve()
        if not path.is_relative_to(self.root):
            raise ContractError("oracle path is outside its store")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if type(data["version"]) is not int or data["version"] != 1:
                raise ContractError("unsupported contract version")
            contract = import_contract(data["brief"], data["reference"], reviewed_by=data["reviewed_by"],
                facts=[ContractFact.create(f["id"], f["kind"], f["expected"], f["requirement_ids"],
                                           f["source_excerpt"]) for f in data["facts"]])
            if (contract.contract_hash != data["contract_hash"] or path.stem != contract.contract_hash or
                contract.brief_hash != data["brief_hash"] or contract.reference_hash != data["reference_hash"] or
                contract.payload()["requirements"] != data["requirements"]):
                raise ContractError("oracle hash/source/requirements mismatch")
            return contract
        except (KeyError, TypeError, AttributeError, json.JSONDecodeError) as exc:
            raise ContractError("invalid oracle document") from exc


def probe_facts(contract: AcceptanceContract, probes: dict[str, Callable[[], Any]], *, snapshot_hash: str) -> dict:
    """Execute independent probes against an identified artifact.

    A matching fact is not a full requirement PASS: the complete X/R/V evidence
    remains the acceptance gate's responsibility. Missing probes/errors are
    NOT_VERIFIED, never silently successful.
    """
    if not snapshot_hash:
        raise ContractError("an identified snapshot is required")
    results = []
    for fact in contract.facts:
        result = {"id": fact.id, "requirement_ids": list(fact.requirement_ids), "expected": fact.expected}
        if fact.id not in probes:
            result.update(status="NOT_VERIFIED", detail="independent probe missing")
        else:
            try:
                actual = probes[fact.id]()
                result.update(observed=actual, status="PASS" if _json(actual) == fact.expected_json else "FAIL")
            except Exception as exc:
                # Do not copy exception payloads: they may contain credentials.
                result.update(status="NOT_VERIFIED", detail=f"probe unavailable: {type(exc).__name__}")
        results.append(result)
    status = ("fail" if any(r["status"] == "FAIL" for r in results) else
              "pass" if results and all(r["status"] == "PASS" for r in results) else "not_verified")
    return {"version": 1, "contract_hash": contract.contract_hash, "snapshot_hash": snapshot_hash,
            "status": status, "facts": results, "scope": "formal_facts_only"}
