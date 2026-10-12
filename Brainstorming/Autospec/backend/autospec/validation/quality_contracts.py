"""Independent quality evidence admission, never execution of product scripts.

Native suites/builds run in the coordinator-owned isolated runner. This module
checks their attested observations and exact proof files, including denominators
and the six source-defined E2E scenarios. Missing records stay NOT_VERIFIED.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from uuid import uuid4

from .support_adapter import AdapterUnavailable, Proof

QUALITY_IDS = tuple(f"TST-{i:02d}" for i in range(1, 7))
E2E_IDS = tuple(f"E2E-{i:02d}" for i in range(1, 7))


def source_e2e_scenarios(contract):
    section = contract.reference.split("## 8. Six parcours E2E minimum", 1)
    if len(section) != 2:
        raise AdapterUnavailable("six E2E scenarios unavailable in frozen reference")
    rows = re.findall(r"^([1-6])\. (.+)$", section[1].split("## 9.", 1)[0], re.M)
    if [int(i) for i, _ in rows] != list(range(1, 7)):
        raise AdapterUnavailable("six source scenarios are malformed")
    return [{"id": f"E2E-{int(i):02d}", "expected": text.rstrip("\r")} for i, text in rows]


def quality_generation_requirements(contract):
    facts = [f for f in contract.facts if f.kind == "quality_profile"]
    requirements = {r.id: r for r in contract.requirements}
    if len(facts) != 1 or not set(QUALITY_IDS) <= set(facts[0].requirement_ids):
        raise AdapterUnavailable("reviewed quality_profile unavailable")
    return {"contract_hash": contract.contract_hash, "brief_hash": contract.brief_hash,
            "reference_hash": contract.reference_hash, "formal_profile": facts[0].expected,
            "requirements": [{"id": rid, "expected": requirements[rid].expected,
                              "evidence": list(requirements[rid].required_evidence)} for rid in QUALITY_IDS],
            "scenarios": source_e2e_scenarios(contract),
            "instructions": ["Do not skip or xfail a critical assertion to obtain green.",
                             "Include never-executed business files in coverage denominators.",
                             "Run each E2E alone and together on real UI/API/DB; isolated fixtures are not product qualification.",
                             "Product scripts/configuration are untrusted input, not host-side executable instructions."]}


class QualityVerifier:
    """Ports: observe(name), proofs(RID), snapshot_hash(), contract_hash()."""
    def __init__(self, contract, adapter):
        self.contract, self.adapter = contract, adapter
        self.contract_hash = contract.contract_hash
        facts = [f for f in contract.facts if f.kind == "quality_profile"]
        self.profile = facts[0].expected if len(facts) == 1 and set(QUALITY_IDS) <= set(facts[0].requirement_ids) else None

    async def _identity(self, snapshot):
        if (self.contract.contract_hash != self.contract_hash or await self.adapter.contract_hash() != self.contract_hash or
                await self.adapter.snapshot_hash() != snapshot):
            raise ValueError("quality oracle/snapshot changed")

    async def verify(self, snapshot_hash):
        await self._identity(snapshot_hash)
        results = []
        requirements = {r.id: r for r in self.contract.requirements}
        for rid in QUALITY_IDS:
            checks, limits, proofs = [], [], []
            def check(tag, observed, expected):
                checks.append({"check": rid + ":" + tag, "observed": observed, "expected": expected, "passed": observed == expected})
            if (not isinstance(self.profile, dict) or not {"required_suites","coverage","coverage_domains"} <= set(self.profile)
                    or rid not in requirements):
                limits.append("reviewed source quality profile missing")
            else:
                try:
                    await getattr(self, "_tst" + rid[-2:])(check)
                except Exception as exc:
                    limits.append("required quality observation unavailable: " + type(exc).__name__)
            await self._identity(snapshot_hash)
            if checks:
                self.adapter.evidence_root.mkdir(parents=True, exist_ok=True)
                path = self.adapter.evidence_root / (rid + "-" + uuid4().hex + ".json")
                path.write_text(json.dumps({"id": rid, "contract_hash": self.contract_hash, "snapshot_hash": snapshot_hash,
                                            "checks": checks}, ensure_ascii=False, indent=2), encoding="utf-8")
                proofs.append(Proof("X", str(path), hashlib.sha256(path.read_bytes()).hexdigest(), snapshot_hash,
                                    self.contract_hash, tuple(x["check"] for x in checks), all(x["passed"] for x in checks)))
            try:
                for proof in await self.adapter.proofs(rid):
                    if proof.intact(snapshot_hash=snapshot_hash, contract_hash=self.contract_hash) and any(
                            tag == rid or tag.startswith(rid + ":") for tag in proof.checks):
                        proofs.append(proof)
                    else:
                        limits.append("stale/unmapped quality proof rejected")
            except Exception as exc:
                limits.append("quality proof unavailable: " + type(exc).__name__)
            required = set(requirements[rid].required_evidence) if rid in requirements else {"X", "R"}
            missing = required - {p.type for p in proofs}
            if missing: limits.append("missing proof types: " + ",".join(sorted(missing)))
            failed = any(not c["passed"] for c in checks) or any(not p.passed for p in proofs)
            results.append({"id": rid, "gate": requirements[rid].gate if rid in requirements else "B",
                            "status": "FAIL" if failed else "NOT_VERIFIED" if limits or not checks else "PASS",
                            "expected": requirements[rid].expected if rid in requirements else "source missing",
                            "observed": checks, "proofs": [p.__dict__ for p in proofs], "limits": limits,
                            "contract_hash": self.contract_hash, "snapshot_hash": snapshot_hash})
        await self._identity(snapshot_hash)
        return {"pack": "quality", "status": "FAIL" if any(r["status"] == "FAIL" for r in results) else
                "PASS" if all(r["status"] == "PASS" for r in results) else "NOT_VERIFIED",
                "contract_hash": self.contract_hash, "snapshot_hash": snapshot_hash, "requirements": results}

    async def _suites(self):
        suites = await self.adapter.observe("native_suites")
        if not isinstance(suites, list) or not suites:
            raise AdapterUnavailable("native suite records absent")
        return suites

    async def _tst01(self, check):
        suites = await self._suites()
        for suite in suites:
            name = suite["name"]
            check(name + "_exit", suite["return_code"], 0)
            check(name + "_collected", type(suite["collected"]) is int and suite["collected"] > 0, True)
            check(name + "_accounted", suite["passed"] + suite["failed"] + suite["skipped"] + suite["xfail"], suite["collected"])
            check(name + "_critical_skip", suite["critical_skipped"] + suite["critical_xfail"], 0)
            check(name + "_nominal_mocks", suite["nominal_security_db_mocks"], False)
            check(name + "_assertions_reviewed", suite["assertions_reviewed"], True)
        check("required_suites", set(self.profile["required_suites"]) <= {s["name"] for s in suites}, True)

    async def _tst02(self, check):
        mapping = await self.adapter.observe("requirement_test_mapping")
        expected = {r.id for r in self.contract.requirements if r.gate != "D"}
        check("all_mandatory_ids_mapped", expected <= set(mapping), True)
        for rid in sorted(expected):
            rows = mapping.get(rid, [])
            check(rid + "_assertions", bool(rows) and all(row.get("executed") is True and row.get("assertion_reviewed") is True
                   and bool(row.get("test")) and bool(row.get("assertion")) for row in rows), True)

    async def _tst03(self, check):
        reports = await self.adapter.observe("coverage")
        for suite, metrics in self.profile["coverage"].items():
            report = reports[suite]
            inventory = report["source_inventory"]
            files = report["files"]
            check(suite + "_complete_inventory", bool(inventory) and set(inventory) == set(files), True)
            check(suite + "_business_exclusions", report["business_excluded"], [])
            for metric, threshold in metrics.items():
                included = sum(row[metric]["total"] for row in files.values())
                covered = sum(row[metric]["covered"] for row in files.values())
                check(suite + metric + "_denominator", report[metric]["total"], included)
                check(suite + metric + "_numerator", report[metric]["covered"], covered)
                check(suite + metric + "_nonzero", included > 0 and 0 <= covered <= included, True)
                check(suite + metric + "_threshold", included > 0 and covered * 100 >= threshold * included, True)
            check(suite + "_auth_services_http_present", set(self.profile["coverage_domains"][suite]) <= set(report["domains"]), True)

    async def _tst04(self, check):
        evidence = await self.adapter.observe("real_sqlite_test_environment")
        path, root = Path(evidence["database_path"]).resolve(), Path(evidence["isolated_root"]).resolve()
        check("temporary_owned_database", root in path.parents and evidence["isolated"] is True, True)
        check("real_sqlite_header", path.read_bytes()[:16].hex(), b"SQLite format 3\x00".hex())
        check("distinct_connections", len(set(evidence["connection_ids"])) >= 2, True)
        check("restart_exercised", evidence["restart_verified"], True)
        check("cleanup_owned_only", evidence["cleanup_owned_only"], True)

    async def _tst05(self, check):
        runs = await self.adapter.observe("browser_e2e")
        expected = {s["id"] for s in source_e2e_scenarios(self.contract)}
        for mode in ["alone", "together"]:
            rows = [r for r in runs if r["mode"] == mode]
            check(mode + "_exact_six", len(rows) == 6 and {r["id"] for r in rows} == expected, True)
            for row in rows:
                if row["status"] not in {"PASS","FAIL"}:
                    raise AdapterUnavailable("E2E scenario was not verified: " + row["id"])
                check(mode + row["id"] + "_executed", row["status"], "PASS")
                check(mode + row["id"] + "_nominal", row["real_ui_api_db"] is True and row["nominal_mocks"] is False, True)
                check(mode + row["id"] + "_console", row["unhandled_console_errors"], [])
                check(mode + row["id"] + "_not_blank", row["nonblank"], True)
                check(mode + row["id"] + "_isolated_fixture", row["fixture_reset_before"], True)

    async def _tst06(self, check):
        mutation = await self.adapter.observe("authorization_mutation")
        check("isolated_mutation", mutation["temporary_copy"] is True, True)
        check("original_unchanged", mutation["original_before_sha256"], mutation["original_after_sha256"])
        check("mutation_distinct", mutation["mutated_sha256"] != mutation["original_before_sha256"], True)
        check("original_pass", mutation["original_status"], "PASS")
        check("mutation_detected", mutation["mutated_status"], "FAIL")
        check("independent_probes", {"SEC-09", "SEC-10", "FUN-06"} <= set(mutation["independent_probes"]), True)
