"""Independent report admission: no native green or model score substitutes evidence."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from dataclasses import dataclass, asdict
from pathlib import Path

from ..contracts import AcceptanceContract
from ..agents.file_broker import ExecutionContext, FileBroker, IsolationViolation
from ..orchestrator.dependencies import atomic_json


_EXCLUDED_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache", ".ruff_cache",
                  ".mypy_cache", ".autospec", ".agents", ".claude", ".codex", ".aws", ".ssh",
                  "dist", "build", "coverage", ".vite", "test-results"}
_EXCLUDED_FILES = {"autospec-state.json", "build-monitor.jsonl", "autospec-interactions.jsonl"}
_HASH = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class Snapshot:
    files: dict[str, str]
    version: int = 1

    @property
    def digest(self):
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def source_snapshot(root: Path) -> Snapshot:
    root = Path(root).resolve()
    broker = FileBroker(ExecutionContext("snapshot", root))
    files = {}
    for directory, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(name for name in dirs if name not in _EXCLUDED_DIRS)
        for name in sorted(names):
            rel = (Path(directory) / name).relative_to(root).as_posix()
            if name in _EXCLUDED_FILES or name.endswith((".sqlite", ".sqlite3", ".db", ".db-wal", ".db-shm")):
                continue
            try:
                path = broker.path(rel)
            except IsolationViolation:
                # Secrets/configuration/links cannot enter a delivery snapshot.
                # A link is refused, not followed or silently trusted as code.
                if Path(directory, name).is_symlink() or name not in {".git", ".gitignore"} and not name.startswith(".env"):
                    raise
                continue
            if path.is_file():
                files[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
        # Validate directories before the next traversal (junctions too).
        for name in dirs:
            broker.path((Path(directory) / name).relative_to(root).as_posix())
    if not files:
        raise ValueError("empty product snapshot cannot be delivered")
    return Snapshot(files)


def freeze_snapshot(root: Path, store: Path) -> tuple[Snapshot, Path]:
    root, store = Path(root).resolve(), Path(store).resolve()
    if store == root or store.is_relative_to(root):
        raise ValueError("snapshot must be outside producer writable root")
    snapshot = source_snapshot(root)
    destination = store / snapshot.digest
    destination.mkdir(parents=True, exist_ok=True)
    code = destination / "source"
    for relative, digest in snapshot.files.items():
        source, target = root / relative, code / relative
        if hashlib.sha256(source.read_bytes()).hexdigest() != digest:
            raise ValueError("source changed during snapshot capture")
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise ValueError("frozen snapshot was modified")
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copyfile(source, target)
    if source_snapshot(root).digest != snapshot.digest or source_snapshot(code).digest != snapshot.digest:
        raise ValueError("snapshot changed while freezing")
    atomic_json(destination / "snapshot.json", dict(asdict(snapshot), snapshot_hash=snapshot.digest))
    return snapshot, code


@dataclass(frozen=True)
class FinalAdmission:
    status: str
    contract_hash: str
    snapshot_hash: str
    requirements: tuple[dict, ...]
    findings: tuple[str, ...]
    version: int = 1

    @property
    def ready(self):
        return self.status == "PASS"

    def payload(self):
        return asdict(self)


def _valid_proof(proof: dict, requirement_id: str, *, root: Path, snapshot: str, contract: str) -> bool:
    try:
        path = Path(proof["path"]).resolve()
        checks = proof["checks"]
        scope = str(proof.get("detail", "")).casefold()
        if (proof["type"] not in {"X", "R", "V"} or proof["passed"] is not True or
            proof["snapshot_hash"] != snapshot or proof["contract_hash"] != contract or
            not path.is_relative_to(root) or not path.is_file() or path.is_symlink() or
            not isinstance(checks, (list, tuple)) or not any(
                isinstance(check, str) and (check == requirement_id or check.startswith(requirement_id + ":")) for check in checks) or
            "fixture" in scope and "only" in scope):
            return False
        return _HASH.fullmatch(proof["sha256"]) is not None and hashlib.sha256(path.read_bytes()).hexdigest() == proof["sha256"]
    except (OSError, ValueError, KeyError, TypeError):
        return False


def admit_reports(contract: AcceptanceContract, reports: list[dict], *, snapshot_hash: str,
                  evidence_root: Path, required_ids: set[str] | None = None) -> FinalAdmission:
    """Producer text, borrowed snapshots, empty receipts and missing X/R/V block.

    D is diagnostic; every selected B/M is mandatory. FAIL remains FAIL even
    with an incomplete report; an unproven PASS becomes NOT_VERIFIED.
    """
    root = Path(evidence_root).resolve()
    if not _HASH.fullmatch(snapshot_hash):
        raise ValueError("identified SHA-256 snapshot required")
    known = {requirement.id: requirement for requirement in contract.requirements}
    selected = set(known) if required_ids is None else set(required_ids)
    if not selected or not selected <= known.keys():
        raise ValueError("explicit known, nonempty requirement selection required")
    records, errors = {}, []
    for report in reports:
        if (not isinstance(report, dict) or report.get("contract_hash") != contract.contract_hash or
            report.get("snapshot_hash") != snapshot_hash or not isinstance(report.get("requirements"), list)):
            errors.append("report identity/shape invalid")
            continue
        for row in report["requirements"]:
            rid = row.get("id") if isinstance(row, dict) else None
            if rid not in known:
                errors.append(f"unknown requirement: {rid}")
            elif rid in records:
                errors.append(f"duplicate requirement: {rid}")
                records[rid] = None
            else:
                records[rid] = row
    normalized = []
    for requirement in contract.requirements:
        if requirement.id not in selected:
            continue
        row = records.get(requirement.id)
        issues = []
        status = row.get("status") if isinstance(row, dict) else "NOT_VERIFIED"
        if not isinstance(row, dict):
            issues.append("missing or duplicate result")
            row = {}
        if status not in {"PASS", "FAIL", "NOT_VERIFIED"}:
            issues.append("invalid result status")
            status = "NOT_VERIFIED"
        if row.get("gate") != requirement.gate or row.get("expected") != requirement.expected:
            issues.append("expectation/gate differs from frozen source")
        proofs = row.get("proofs", [])
        intact = [proof for proof in proofs if isinstance(proof, dict) and _valid_proof(proof, requirement.id,
            root=root, snapshot=snapshot_hash, contract=contract.contract_hash)] if isinstance(proofs, list) else []
        missing = set(requirement.required_evidence) - {proof["type"] for proof in intact}
        if missing:
            issues.append("missing valid evidence: " + ",".join(sorted(missing)))
        for key in ("observed", "reproduction", "impact", "limits"):
            if key not in row:
                issues.append(f"missing report field: {key}")
        if status == "PASS" and (issues or errors):
            status = "NOT_VERIFIED"
        normalized.append(dict(row, id=requirement.id, gate=requirement.gate, expected=requirement.expected,
            status=status, proof_issues=issues, admitted_proofs=intact))
    mandatory = [row for row in normalized if row["gate"] in {"B", "M"}]
    status = ("FAIL" if any(row["status"] == "FAIL" for row in mandatory) else "PASS" if
              not errors and mandatory and all(row["status"] == "PASS" for row in mandatory) else "NOT_VERIFIED")
    return FinalAdmission(status, contract.contract_hash, snapshot_hash, tuple(normalized), tuple(errors))
