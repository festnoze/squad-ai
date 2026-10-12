"""Independent executable SEC-01..15 acceptance probes.

All routes, statuses and numeric security limits are a reviewed security_profile
fact in the immutable source contract. The generated product never defines the
oracle. Missing harness/review/browser evidence stays NOT_VERIFIED.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any
from uuid import uuid4

from ..contracts import AcceptanceContract
from .support_adapter import AdapterUnavailable, Proof, SupportAdapter


SECURITY_IDS = tuple(f"SEC-{i:02d}" for i in range(1, 16))


class SecurityIdentityError(ValueError):
    pass


def security_generation_requirements(contract: AcceptanceContract) -> dict:
    """Source-exact fragment for the coordinator-owned generation prompt.

    This exposes the reviewed immutable requirements, never product-inferred
    expectations. It is not a verdict or an automatic approval of the facts.
    """
    profiles = [f for f in contract.facts if f.kind == "security_profile"]
    requirements = {r.id: r for r in contract.requirements}
    if (len(profiles) != 1 or not set(SECURITY_IDS) <= set(profiles[0].requirement_ids) or
            not set(SECURITY_IDS) <= set(requirements)):
        raise AdapterUnavailable("reviewed security source profile incomplete")
    return {"contract_hash": contract.contract_hash, "brief_hash": contract.brief_hash,
            "reference_hash": contract.reference_hash, "reviewed_by": contract.reviewed_by,
            "profile_fact_id": profiles[0].id, "formal_profile": profiles[0].expected,
            "requirements": [{"id": rid, "gate": requirements[rid].gate,
                              "expected": requirements[rid].expected,
                              "required_evidence": list(requirements[rid].required_evidence)} for rid in SECURITY_IDS],
            "instructions": ["Implement the frozen API and security requirements exactly; do not adapt the oracle to generated code.",
                             "Declare runtime security primitives in the manifest and lock; exercise nominal authentication without mocks.",
                             "Missing executable, source-review or browser evidence is NOT_VERIFIED, never PASS."]}


class _Case:
    def __init__(self, verifier, rid):
        self.v, self.rid = verifier, rid
        self.checks: list[dict] = []
        self.reproduction: list[dict] = []

    def expect(self, name, observed, expected):
        self.checks.append({"check": name, "passed": observed == expected,
                            "observed": self.v.redact(observed), "expected": self.v.redact(expected)})

    async def request(self, actor, method, route, *, json=None, **kwargs):
        if isinstance(json, dict) and isinstance(json.get("password"), str):
            self.v._secrets.add(json["password"])
        response = await self.v.adapter.request(actor, method, route, json=json, **kwargs)
        try:
            body = response.json()
        except ValueError:
            body = response.text
        self.reproduction.append({"actor": actor or "anonymous", "method": method, "path": route,
            "input": self.v.redact(json), "headers": self.v.redact(kwargs.get("headers", {})),
            "status": response.status_code, "body": self.v.redact(body)})
        return response

    async def observe(self, name, **params):
        value = await self.v.adapter.observe(name, **params)
        self.reproduction.append({"observation": name, "params": self.v.redact(params),
                                  "value": self.v.redact(value)})
        return value

    async def command(self, action, **params):
        value = await self.v.adapter.command(action, **params)
        self.reproduction.append({"command": action, "params": self.v.redact(params),
                                  "value": self.v.redact(value)})
        return value


class SecurityVerifier:
    def __init__(self, contract: AcceptanceContract, adapter: SupportAdapter):
        self.contract, self.adapter = contract, adapter
        self.pinned_contract_hash = contract.contract_hash
        profiles = [f for f in contract.facts if f.kind == "security_profile"]
        self.profile = (profiles[0].expected if len(profiles) == 1 and
                        set(SECURITY_IDS) <= set(profiles[0].requirement_ids) else None)
        self._secrets: set[str] = set()
        self.snapshot = ""
        self._active_case = None

    def redact(self, value: Any):
        if isinstance(value, dict):
            return {k: "[REDACTED]" if any(s in k.casefold() for s in
                    ("password", "cookie", "csrf", "token", "hash", "secret")) else self.redact(v)
                    for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self.redact(v) for v in value]
        if isinstance(value, str):
            text = re.sub(r"\$argon2(?:id|i|d)\$[^\s\"']+", "[REDACTED_HASH]", value)
            for secret in sorted(self._secrets, key=len, reverse=True):
                if secret:
                    text = text.replace(secret, "[REDACTED]")
            return text
        return value

    def route(self, name, **ids):
        return self.profile["api"][name].format(**ids)

    def status(self, name):
        return self.profile["statuses"][name]

    async def _identity(self):
        if (self.contract.contract_hash != self.pinned_contract_hash or
            await self.adapter.contract_hash() != self.pinned_contract_hash or
            await self.adapter.snapshot_hash() != self.snapshot):
            raise SecurityIdentityError("oracle/snapshot identity changed; results are invalid")

    async def _login(self, actor):
        response = await self.adapter.login(actor)
        self._secrets.add(self.adapter.manifest.accounts[actor].password)
        if self._active_case is not None:
            self._active_case.expect("nominal_login_" + actor, response.status_code, self.status("ok"))
            self._active_case.reproduction.append({"actor": actor, "method": "POST", "path": self.route("login"),
                "input": {"email": self.adapter.manifest.accounts[actor].email, "password": "[REDACTED]"},
                "status": response.status_code})
        if response.status_code != self.status("ok"):
            raise AdapterUnavailable("nominal fixture login failed")
        try:
            self._secrets.update(str(v) for k, v in response.json().items() if "csrf" in k.lower() or "token" in k.lower())
        except ValueError:
            pass
        for cookie in response.cookies.values():
            self._secrets.add(cookie)
        return response

    async def _user(self, c, *, email=None, password=None, role="client", display_name="Probe User"):
        response = await c.request("admin", "POST", self.route("users"), json={
            "email": email or f"probe-{uuid4()}@example.test", "password": password or "Probe password 漢字 2026",
            "display_name": display_name, "role": role})
        return response

    def _scan_artifacts_intact(self, scan):
        if not scan.get("artifacts"):
            raise AdapterUnavailable("scan artifacts absent")
        for artifact in scan["artifacts"]:
            path = Path(artifact["path"])
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != artifact["sha256"]:
                raise AdapterUnavailable("scan artifact missing or changed")

    def _ticket_payload(self):
        return {"title": "Independent contract probe", "description": "Independent security probe description",
                "client_request_id": str(uuid4())}

    async def _message(self, c, actor, ticket, *, visibility="public", content="Independent probe", request_id=None, **extra):
        body = {"content": content, "visibility": visibility, "client_request_id": request_id or str(uuid4())} | extra
        return await c.request(actor, "POST", self.route("messages", id=ticket), json=body)

    async def verify(self, snapshot_hash: str) -> list[dict]:
        try:
            return await self._verify(snapshot_hash)
        finally:
            await self.adapter.close()

    async def _verify(self, snapshot_hash: str) -> list[dict]:
        if not snapshot_hash:
            raise SecurityIdentityError("identified snapshot required")
        self.snapshot = snapshot_hash
        await self._identity()
        requirements = {r.id: r for r in self.contract.requirements}
        results = []
        valid_profile = (isinstance(self.profile, dict) and
                         all(isinstance(self.profile.get(k), dict) for k in ["api", "statuses", "password", "rate", "session"]))
        for rid in SECURITY_IDS:
            requirement = requirements.get(rid)
            c = _Case(self, rid)
            self._active_case = c
            limits = []
            if requirement is None or not valid_profile:
                limits.append("source requirement or reviewed security_profile unavailable")
            else:
                try:
                    manifest = await self.adapter.prepare_case(rid)
                    self._secrets.update(a.password for a in manifest.accounts.values())
                    await getattr(self, f"_sec{int(rid[-2:]):02d}")(c)
                except (AdapterUnavailable, KeyError, TypeError, AttributeError) as exc:
                    limits.append(f"required harness/profile evidence unavailable: {type(exc).__name__}")
                except Exception as exc:
                    # A provider/HTTP exception is not an observed product FAIL.
                    limits.append(f"execution incomplete: {type(exc).__name__}")
            await self._identity()
            proofs = []
            if c.checks or c.reproduction:
                payload = {"id": rid, "contract_hash": self.pinned_contract_hash, "snapshot_hash": self.snapshot,
                           "checks": c.checks, "reproduction": c.reproduction}
                self.adapter.evidence_root.mkdir(parents=True, exist_ok=True)
                path = self.adapter.evidence_root / f"{rid}-{uuid4().hex}.json"
                path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                proofs.append(Proof("X", str(path), hashlib.sha256(path.read_bytes()).hexdigest(), self.snapshot,
                                    self.pinned_contract_hash, (rid,) + tuple(x["check"] for x in c.checks),
                                    passed=bool(c.checks) and all(x["passed"] for x in c.checks)))
            try:
                external = await self.adapter.proofs(rid)
            except Exception as exc:
                external = []
                limits.append(f"external evidence unavailable: {type(exc).__name__}")
            for proof in external:
                try:
                    intact = proof.intact(snapshot_hash=self.snapshot, contract_hash=self.pinned_contract_hash) and rid in proof.checks
                except (OSError, AttributeError, TypeError):
                    intact = False
                if intact:
                    proofs.append(proof)
                else:
                    limits.append("stale/unreadable/unmapped external proof rejected")
            required = set(requirement.required_evidence) if requirement else {"X", "R"}
            if rid in {"SEC-10", "SEC-12"}:
                required.add("V")
            if required - {p.type for p in proofs}:
                limits.append("missing proof types: " + ",".join(sorted(required - {p.type for p in proofs})))
            failed = any(not check["passed"] for check in c.checks) or any(not p.passed for p in proofs)
            status = "FAIL" if failed else "NOT_VERIFIED" if limits or not c.checks else "PASS"
            results.append({"id": rid, "gate": requirement.gate if requirement else "B", "status": status,
                "contract_hash": self.pinned_contract_hash, "snapshot_hash": self.snapshot,
                "expected": requirement.expected if requirement else "requirement absent from frozen source",
                "observed": c.checks, "reproduction": c.reproduction,
                "proofs": [p.__dict__ for p in proofs], "impact": "source security invariant violated" if failed else "",
                "limits": limits})
        await self._identity()
        return results

    async def _sec01(self, c):
        c.expect("empty_database", await c.observe("account_count"), 0)
        absent = await c.command("bootstrap", credentials=None)
        c.expect("bootstrap_requires_credentials", absent["exit_code"] != 0, True)
        admin = self.adapter.manifest.accounts["admin"]
        made = await c.command("bootstrap", credentials={"email": admin.email, "password": admin.password})
        c.expect("explicit_bootstrap", made["exit_code"], 0)
        first = await c.observe("account_fingerprints")
        repeated = await c.command("bootstrap", credentials={"email": admin.email, "password": "different password"})
        c.expect("existing_admin_refused", repeated["exit_code"] != 0, True)
        c.expect("bootstrap_preserves_password", await c.observe("account_fingerprints"), first)
        seed = await c.command("seed", demo=True, credentials=True)
        c.expect("explicit_demo_seed", seed["exit_code"], 0)
        state = await c.observe("business_state")
        fingerprints = await c.observe("account_fingerprints")
        await c.command("seed", demo=True, credentials=True)
        c.expect("seed_idempotent", await c.observe("business_state"), state)
        c.expect("seed_no_password_reset", await c.observe("account_fingerprints"), fingerprints)
        c.expect("seed_credentials_missing_refused", (await c.command("seed", demo=True, credentials=False))["exit_code"] != 0, True)
        collision = await c.command("seed_collision")
        c.expect("collision_refused", collision["exit_code"] != 0, True)
        c.expect("collision_preserved_existing_data", collision["preserved"], True)
        scan = await c.observe("secret_scan", scope="source_image_logs")
        c.expect("source_image_logs_no_secret", scan["findings"], [])
        self._scan_artifacts_intact(scan)
        if not {"source", "image", "logs"} <= set(scan.get("scopes", [])):
            raise AdapterUnavailable("source/image/log scan artifacts missing")

    async def _sec02(self, c):
        await self._login("admin")
        first = await self._user(c, email=" Alice.Unique@Example.test ")
        c.expect("normalized_first_create", first.status_code, self.status("created"))
        duplicate = await self._user(c, email="alice.unique@example.test")
        c.expect("normalized_duplicate", duplicate.status_code, self.status("conflict"))
        uid = first.json()["id"]
        await c.request("admin", "PATCH", self.route("user", id=uid), json={"active": False})
        duplicate = await self._user(c, email="ALICE.UNIQUE@EXAMPLE.TEST")
        c.expect("inactive_email_remains_unique", duplicate.status_code, self.status("conflict"))
        c.expect("one_normalized_account", await c.observe("email_count", email="alice.unique@example.test"), 1)
        await self.adapter.arm_race("create_user", 2)
        a, b = await asyncio.gather(self._user(c, email="race@example.test"), self._user(c, email=" RACE@example.test "))
        c.expect("concurrent_unique", sorted([a.status_code, b.status_code]), sorted([self.status("created"), self.status("conflict")]))
        c.expect("one_account_after_race", await c.observe("email_count", email="race@example.test"), 1)
        c.expect("distinct_db_connections", len(set(await c.observe("race_connections"))) >= 2, True)
        c.expect("uniqueness_enforced_by_db", await c.observe("email_unique_constraint"), True)

    async def _sec03(self, c):
        from argon2 import PasswordHasher, extract_parameters
        from argon2.low_level import Type
        await self._login("admin")
        bounds = self.profile["password"]
        for length, expected in [(bounds["min"] - 1, "invalid"), (bounds["min"], "created"),
                                 (bounds["max"], "created"), (bounds["max"] + 1, "invalid")]:
            response = await self._user(c, email=f"length-{length}@example.test", password="x" * length)
            c.expect(f"password_length_{length}", response.status_code, self.status(expected))
        password = " é漢字 " + " " * bounds["min"]
        self._secrets.add(password)
        for n in [1, 2]:
            response = await self._user(c, email=f"salt-{n}@example.test", password=password)
            c.expect(f"unicode_spaces_{n}", response.status_code, self.status("created"))
            c.expect(f"public_dto_no_hash_{n}", any("password" in k.lower() or "hash" in k.lower() for k in response.json()), False)
        hashes = await c.observe("password_hashes", emails=["salt-1@example.test", "salt-2@example.test"])
        c.expect("salt_distinct", len(set(hashes)), 2)
        for n, encoded in enumerate(hashes):
            try:
                p = extract_parameters(encoded)
                verified = PasswordHasher().verify(encoded, password)
            except Exception:
                c.expect(f"valid_real_argon2_hash_{n}", False, True)
                continue
            c.expect(f"argon2id_{n}", p.type == Type.ID, True)
            c.expect(f"memory_{n}", p.memory_cost >= bounds["memory_kib"], True)
            c.expect(f"iterations_{n}", p.time_cost >= bounds["iterations"], True)
            c.expect(f"parallelism_{n}", p.parallelism == bounds["parallelism"], True)
            c.expect(f"real_hash_verification_{n}", verified, True)
        login = await c.request(None, "POST", self.route("login"), json={"email": "salt-1@example.test", "password": password})
        c.expect("full_unicode_password_login", login.status_code, self.status("ok"))
        wrong = await c.request(None, "POST", self.route("login"), json={"email": "salt-1@example.test", "password": password.strip()})
        c.expect("password_not_silently_trimmed", wrong.status_code, self.status("unauthorized"))

    async def _sec04(self, c):
        await self._login("admin")
        await c.request("admin", "PATCH", self.route("user", id=self.adapter.manifest.accounts["bob"].id), json={"active": False})
        failures = []
        for email, password in [(self.adapter.manifest.accounts["alice"].email, "wrong"),
                                ("absent@example.test", "wrong"),
                                (self.adapter.manifest.accounts["bob"].email, self.adapter.manifest.accounts["bob"].password)]:
            r = await c.request(None, "POST", self.route("login"), json={"email": email, "password": password}, ip="127.0.0.2")
            failures.append((r.status_code, r.json()))
        c.expect("uniform_failures", all(f == failures[0] for f in failures), True)
        c.expect("failure_status", failures[0][0], self.status("unauthorized"))
        c.expect("absent_account_dummy_hash", await c.observe("dummy_hash_verifications") > 0, True)
        alice = self.adapter.manifest.accounts["alice"]
        await c.request(None, "POST", self.route("login"), json={"email": alice.email, "password": "wrong"})
        correct = await c.request(None, "POST", self.route("login"), json={"email": alice.email, "password": alice.password})
        c.expect("nominal_login", correct.status_code, self.status("ok"))
        for _ in range(self.profile["rate"]["failures"] - 1):
            await c.request(None, "POST", self.route("login"), json={"email": alice.email, "password": "wrong"})
        limited = await c.request(None, "POST", self.route("login"), json={"email": alice.email, "password": alice.password}, headers={"X-Forwarded-For": "127.0.0.9"})
        c.expect("success_does_not_reset_limit_or_trust_xff", limited.status_code, self.status("rate_limited"))
        c.expect("retry_after_present", bool(limited.headers.get("Retry-After")), True)
        other = await c.request(None, "POST", self.route("login"), json={"email": alice.email, "password": alice.password}, ip="127.0.0.3")
        c.expect("ip_independent", other.status_code, self.status("ok"))
        await self.adapter.advance_clock(self.profile["rate"]["window_seconds"] - 1)
        blocked = await c.request(None, "POST", self.route("login"), json={"email": alice.email, "password": alice.password})
        c.expect("fixed_window_before_boundary", blocked.status_code, self.status("rate_limited"))
        await self.adapter.advance_clock(1)
        r = await c.request(None, "POST", self.route("login"), json={"email": alice.email, "password": alice.password})
        c.expect("fixed_window_after_boundary", r.status_code, self.status("ok"))

    def _cookie(self, response):
        cookie = SimpleCookie()
        cookie.load(response.headers.get("set-cookie", ""))
        if not cookie:
            raise AdapterUnavailable("session cookie missing")
        name, morsel = next(iter(cookie.items()))
        self._secrets.add(morsel.value)
        return name, morsel

    async def _sec05(self, c):
        response = await self._login("alice")
        name, cookie = self._cookie(response)
        for attribute, expected in [("httponly", True), ("samesite", "lax"), ("path", "/")]:
            observed = cookie[attribute].casefold() if attribute == "samesite" else cookie[attribute]
            c.expect("cookie_" + attribute, observed, expected)
        c.expect("https_secure", bool(cookie["secure"]), self.adapter.base_url.startswith("https://"))
        c.expect("token_minimum_bits_shape", len(cookie.value) >= self.profile["session"]["min_token_chars"], True)
        records = await c.observe("session_storage", token=cookie.value)
        c.expect("server_token_not_raw", bool(records) and all(r["stored"] != cookie.value for r in records), True)
        second = await self._login("alice")
        _, newer = self._cookie(second)
        c.expect("new_token_per_login", newer.value != cookie.value, True)
        await self.adapter.advance_clock(self.profile["session"]["absolute_seconds"] - 1)
        r = await c.request("alice", "GET", self.route("me"))
        c.expect("active_before_absolute_expiry", r.status_code, self.status("ok"))
        await self.adapter.advance_clock(1)
        r = await c.request("alice", "GET", self.route("me"))
        c.expect("absolute_expiry_not_sliding", r.status_code, self.status("unauthorized"))
        for mode in await c.observe("cookie_modes"):
            c.expect("secure_mode_" + mode["mode"], mode["secure"], self.profile["session"]["modes"][mode["mode"]])

    async def _sec06(self, c):
        response = await self._login("alice")
        name, cookie = self._cookie(response)
        old = f"{name}={cookie.value}"
        r = await c.request("alice", "POST", self.route("logout"))
        c.expect("logout_nominal", r.status_code, self.status("no_content"))
        r = await c.request("alice", "GET", self.route("me"), headers={"Cookie": old})
        c.expect("logout_server_revocation", r.status_code, self.status("unauthorized"))
        r = await c.request(None, "POST", self.route("logout"))
        c.expect("logout_no_session_idempotent", r.status_code, self.status("no_content"))
        c.expect("logout_cookie_expired", "max-age=0" in r.headers.get("set-cookie", "").lower(), True)
        r = await c.request(None, "POST", self.route("logout"), headers={"Origin": None})
        c.expect("logout_no_session_still_checks_origin", r.status_code, self.status("forbidden"))
        await self._login("alice")
        await self._login("admin")
        uid = self.adapter.manifest.accounts["alice"].id
        for active in [False, True]:
            r = await c.request("admin", "PATCH", self.route("user", id=uid), json={"active": active})
            c.expect("active_toggle_" + str(active), r.status_code, self.status("ok"))
            r = await c.request("alice", "GET", self.route("me"))
            c.expect("old_session_stays_revoked_" + str(active), r.status_code, self.status("unauthorized"))
        c.expect("reactivated_new_login", (await self.adapter.login("alice")).status_code, self.status("ok"))

    async def _sec07(self, c):
        await self._login("alice")
        await self._login("bob")
        other = self.adapter.csrf_token("bob")
        for route, body in [(self.route("tickets"), self._ticket_payload()), (self.route("logout"), None)]:
            for token in [None, "invalid", other]:
                before = await c.observe("security_state")
                r = await c.request("alice", "POST", route, json=body, headers={"X-CSRF-Token": token})
                c.expect("csrf_refused_" + route + str(token is None), r.status_code, self.status("forbidden"))
                c.expect("csrf_refusal_no_mutation", await c.observe("security_state"), before)
        for origin in [None, "null", "https://foreign.example"]:
            r = await c.request("alice", "POST", self.route("tickets"), json=self._ticket_payload(), headers={"Origin": origin})
            c.expect("mutation_origin_" + str(origin), r.status_code, self.status("forbidden"))
            alice = self.adapter.manifest.accounts["alice"]
            r = await c.request(None, "POST", self.route("login"), json={"email": alice.email, "password": alice.password}, headers={"Origin": origin})
            c.expect("login_origin_" + str(origin), r.status_code, self.status("forbidden"))
        r = await c.request(None, "POST", self.route("tickets"), json=self._ticket_payload(), headers={"Origin": None})
        c.expect("anonymous_before_csrf", r.status_code, self.status("unauthorized"))
        r = await c.request("alice", "POST", self.route("tickets"), json=self._ticket_payload())
        c.expect("legitimate_mutation", r.status_code, self.status("created"))
        c.expect("cors_no_wildcard_credentials", not (r.headers.get("access-control-allow-credentials") == "true" and
                 r.headers.get("access-control-allow-origin") == "*"), True)

    async def _sec08(self, c):
        for actor in ["alice", "agent", "admin"]:
            await self._login(actor)
        for actor in [None, "alice", "agent", "admin"]:
            for endpoint in ["users", "assignees", "tickets", "dashboard"]:
                expected = ("unauthorized" if actor is None else "forbidden" if
                    (endpoint == "users" and actor != "admin") or (endpoint == "assignees" and actor == "alice") else "ok")
                r = await c.request(actor, "GET", self.route(endpoint))
                c.expect(f"role_{actor}_{endpoint}", r.status_code, self.status(expected))
        for actor in ["agent", "admin"]:
            before = await c.observe("business_state")
            r = await c.request(actor, "POST", self.route("tickets"), json=self._ticket_payload())
            c.expect("staff_cannot_create_ticket_" + actor, r.status_code, self.status("forbidden"))
            c.expect("staff_refusal_no_effect", await c.observe("business_state"), before)
        for method in ["PUT", "DELETE"]:
            r = await c.request(None, method, self.route("users"), json={})
            c.expect("no_alternative_method_auth_bypass_" + method, r.status_code in
                     [self.status("unauthorized"), self.status("forbidden"), 404, 405], True)
        inventory = await c.observe("route_inventory")
        if not inventory or not any(route.get("business") for route in inventory):
            raise AdapterUnavailable("authenticated route inventory absent")
        for route in inventory:
            if route.get("business") and route.get("method") == "GET":
                r = await c.request(None, "GET", route["path"])
                c.expect("secondary_route_protected_" + route["path"], r.status_code, self.status("unauthorized"))

    async def _sec09(self, c):
        await self._login("alice")
        await self._login("bob")
        ticket = self.adapter.manifest.tickets["bob"]
        absent = str(uuid4())
        before = await c.observe("business_state")
        for method, endpoint, payload in [("GET", "ticket", None), ("PATCH", "ticket", {"expected_version": 1, "priority": "high"}),
                                          ("GET", "messages", None), ("GET", "history", None)]:
            foreign = await c.request("alice", method, self.route(endpoint, id=ticket), json=payload)
            missing = await c.request("alice", method, self.route(endpoint, id=absent), json=payload)
            c.expect("idor_" + method + endpoint, foreign.status_code, self.status("invisible"))
            c.expect("idor_indistinguishable_" + method + endpoint, foreign.json(), missing.json())
        c.expect("idor_no_db_effect", await c.observe("business_state"), before)
        key = str(uuid4())
        await self._message(c, "bob", ticket, request_id=key)
        replay = await self._message(c, "alice", ticket, request_id=key)
        c.expect("permissions_before_idempotency_replay", replay.status_code, self.status("invisible"))
        r = await c.request("alice", "GET", self.route("tickets"))
        c.expect("list_no_foreign_ticket", ticket not in json.dumps(r.json()), True)
        c.expect("scoped_list_total", r.json()["total"], self.adapter.manifest.metadata["alice_ticket_count"])
        r = await c.request("alice", "GET", self.route("dashboard"))
        c.expect("scoped_dashboard_total", r.json()["total"], self.adapter.manifest.metadata["alice_ticket_count"])

    async def _sec10(self, c):
        await self._login("alice")
        await self._login("agent2")
        for ticket in [self.adapter.manifest.tickets["alice"], self.adapter.manifest.tickets["internal_only"]]:
            before = await c.request("alice", "GET", self.route("messages", id=ticket), params={"page_size": 1})
            before_total = before.json()["total"]
            marker = "INDEPENDENT_INTERNAL_MARKER_" + uuid4().hex
            r = await self._message(c, "agent2", ticket, visibility="internal", content=marker)
            c.expect("staff_internal_note_created", r.status_code, self.status("created"))
            internal_id = r.json()["id"]
            for endpoint in ["ticket", "messages", "history"]:
                response = await c.request("alice", "GET", self.route(endpoint, id=ticket), params={"page_size": 1} if endpoint != "ticket" else None)
                text = json.dumps(response.json())
                c.expect("internal_absent_" + endpoint, marker not in text and internal_id not in text and
                         self.adapter.manifest.accounts["agent2"].id not in text, True)
                if endpoint == "messages":
                    c.expect("internal_filtered_before_pagination", response.json()["total"], before_total)
                    c.expect("no_internal_message_dto", all(row.get("visibility") != "internal" for row in response.json()["items"]), True)
            response = await c.request("alice", "GET", self.route("tickets"), params={"q": marker})
            c.expect("internal_not_searchable", response.json()["total"], 0)

    async def _sec11(self, c):
        for actor in ["alice", "admin"]:
            await self._login(actor)
        for field in ["owner_id", "author_id", "created_at", "version", "status", "unknown_field"]:
            before = await c.observe("business_state")
            r = await c.request("alice", "POST", self.route("tickets"), json=self._ticket_payload() | {field: "forbidden"})
            c.expect("strict_ticket_field_" + field, r.status_code, self.status("invalid"))
            c.expect("mass_assignment_no_effect", await c.observe("business_state"), before)
        ticket = self.adapter.manifest.tickets["alice"]
        for field in ["author_id", "created_at", "role", "unknown_field"]:
            before = await c.observe("business_state")
            r = await self._message(c, "alice", ticket, **{field: "forbidden"})
            c.expect("strict_message_field_" + field, r.status_code, self.status("invalid"))
            c.expect("message_refusal_no_effect", await c.observe("business_state"), before)
        r = await self._message(c, "alice", ticket, visibility="internal")
        c.expect("client_internal_refused", r.status_code, self.status("forbidden"))
        r = await self._user(c, role="agent")
        c.expect("admin_may_set_role_on_create", r.status_code, self.status("created"))

    async def _sec12(self, c):
        for actor in ["alice", "agent", "admin"]:
            await self._login(actor)
        ticket = self.adapter.manifest.tickets["alice"]
        for payload in ["<script>window.__security_probe=1</script>", "<img src=x onerror=window.__security_probe=1>", "O'Reilly %_ ' OR 1=1 --"]:
            for actor, visibility in [("alice", "public"), ("agent", "internal")]:
                r = await self._message(c, actor, ticket, visibility=visibility, content=payload)
                c.expect("literal_message_store_" + visibility, r.status_code, self.status("created"))
                c.expect("literal_message_roundtrip_" + visibility, r.json().get("content"), payload)
            r = await c.request("alice", "GET", self.route("tickets"), params={"q": payload})
            c.expect("query_does_not_expand_scope", r.json()["total"], 0)
            r = await self._user(c, display_name=payload)
            c.expect("literal_account_name_create", r.status_code, self.status("created"))
            c.expect("literal_account_name_roundtrip", r.json().get("display_name"), payload)
            r = await c.request("alice", "POST", self.route("tickets"), json=self._ticket_payload() | {"title": payload})
            c.expect("literal_ticket_title_create", r.status_code, self.status("created"))
            detail = await c.request("alice", "GET", self.route("ticket", id=r.json()["id"]))
            c.expect("literal_ticket_title_roundtrip", detail.json().get("title"), payload)
            matches = await c.request("alice", "GET", self.route("tickets"), params={"q": payload})
            c.expect("literal_query_exact_match", matches.json()["total"], 1)
        c.expect("sqlite_tables_preserved", await c.observe("essential_tables_present"), True)

    async def _sec13(self, c):
        await self._login("admin")
        uid = self.adapter.manifest.accounts["admin"].id
        r = await c.request("admin", "PATCH", self.route("user", id=uid), json={"active": False})
        c.expect("last_admin_refused", r.status_code, self.status("conflict"))
        created = await self._user(c, email="second-admin@example.test", role="admin")
        c.expect("second_admin_create", created.status_code, self.status("created"))
        await self.adapter.command("register_actor", actor="admin2", id=created.json()["id"], email="second-admin@example.test", password="Probe password 漢字 2026", role="admin")
        await self._login("admin2")
        second_id = self.adapter.manifest.accounts["admin2"].id
        await self.adapter.arm_race("deactivate_admin", 2)
        a, b = await asyncio.gather(c.request("admin", "PATCH", self.route("user", id=uid), json={"active": False}),
                                  c.request("admin2", "PATCH", self.route("user", id=second_id), json={"active": False}))
        c.expect("admin_concurrency_one_refusal", sorted([a.status_code, b.status_code]), sorted([self.status("ok"), self.status("conflict")]))
        c.expect("admin_survives", await c.observe("active_admin_count") >= 1, True)
        c.expect("admin_race_distinct_connections", len(set(await c.observe("race_connections"))) >= 2, True)

    async def _sec14(self, c):
        for actor in ["alice", "agent", "admin"]:
            await self._login(actor)
        uid = self.adapter.manifest.accounts["alice"].id
        for field, value in [("role", "admin"), ("email", "replaced@example.test")]:
            before = await c.observe("business_state")
            r = await c.request("admin", "PATCH", self.route("user", id=uid), json={field: value})
            c.expect("immutable_user_" + field, r.status_code, self.status("invalid"))
            c.expect("immutable_refusal_no_effect", await c.observe("business_state"), before)
        r = await c.request("agent", "POST", self.route("users"), json={"email": "forbidden@example.test", "password": "Probe password 2026", "role": "client", "display_name": "Forbidden"})
        c.expect("agent_cannot_create_account", r.status_code, self.status("forbidden"))
        r = await c.request("alice", "GET", self.route("assignees"))
        c.expect("client_no_staff_directory", r.status_code, self.status("forbidden"))
        r = await c.request("agent", "GET", self.route("assignees"))
        forbidden = {"password", "password_hash", "sessions", "token"}
        c.expect("minimal_assignable_directory", all(not forbidden.intersection(row) and row["id"] != uid for row in r.json()["items"]), True)
        before = await c.observe("business_counts")
        r = await c.request("admin", "PATCH", self.route("user", id=self.adapter.manifest.accounts["agent"].id), json={"active": False})
        c.expect("deactivate_nominal", r.status_code, self.status("ok"))
        after = await c.observe("business_counts")
        c.expect("deactivation_preserves_tickets_messages", after["tickets"] == before["tickets"] and after["messages"] == before["messages"], True)

    async def _sec15(self, c):
        await self._login("alice")
        for actor in [None, "alice"]:
            r = await c.request(actor, "GET", self.route("tickets"))
            c.expect("private_no_store_" + str(actor), "no-store" in r.headers.get("cache-control", ""), True)
        await self.adapter.set_fault("db_read", True)
        r = await c.request("alice", "GET", self.route("tickets"))
        c.expect("controlled_db_error", r.status_code in self.profile["statuses"]["db_fault"], True)
        c.expect("error_no_store", "no-store" in r.headers.get("cache-control", ""), True)
        c.expect("error_no_private_detail", not any(marker in r.text for marker in
                 ["Traceback", "SELECT ", "sqlite3.", "SECRET_SQL_PRIVATE_PATH"]), True)
        await self.adapter.set_fault("db_read", False)
        scan = await c.observe("secret_scan", scope="logs_artifacts")
        c.expect("negative_logs_redacted", scan["findings"], [])
        self._scan_artifacts_intact(scan)
        if not {"logs", "artifacts"} <= set(scan.get("scopes", [])):
            raise AdapterUnavailable("negative-path logs/artifact scan scope incomplete")
