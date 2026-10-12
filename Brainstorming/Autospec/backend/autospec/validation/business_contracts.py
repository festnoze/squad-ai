"""Independent Relais Support v0.2 business probes; never import product tests.

The fixture and observation ports belong to the supervisor. They must operate on
an isolated database, not a user's database. Missing ports/evidence fail closed
as NOT_VERIFIED. A concrete observed counterexample always takes precedence.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

from autospec.contracts import AcceptanceContract, import_contract
from .support_adapter import AdapterUnavailable, Proof, SupportAdapter

BRIEF_HASH = "0a99950df5ee132253fa5aefb1a8f6e4f7a4b64c1436072564be6d28195fb0f3"
REFERENCE_HASH = "efdab8ea54208557f01abcb5324172e42b9c5cf88536611d64ba65b92564cbf4"
STATUSES = ("open", "in_progress", "resolved", "closed")
TRANSITIONS = {("open", "in_progress"), ("in_progress", "open"),
               ("in_progress", "resolved"), ("resolved", "in_progress"), ("resolved", "closed")}
BUSINESS_CHECKS = {
    "FUN-01": ("creation", "roles", "bounds"),
    "FUN-02": ("scope", "missing", "ui_clear"),
    "FUN-03": ("priority", "assignment", "closed", "disable_exception"),
    "FUN-04": ("matrix", "preconditions"),
    "FUN-05": ("messages", "bounds", "identity", "visibility"),
    "FUN-06": ("patch_race", "close_wins", "message_wins", "distinct_connections", "transactions", "ui_draft"),
    "FUN-07": ("retry", "simultaneous", "conflicts", "users", "rights", "restart", "closed_replay", "durable_constraints"),
    "FUN-08": ("history", "rollback", "append_only"),
    "FUN-09": ("disable", "revocation", "assignment_race", "reactivate", "atomic_disable"),
    "FUN-10": ("search", "bounds", "literal", "notes", "acl_before_page"),
    "FUN-11": ("filters", "bounds", "pagination", "sort"),
    "FUN-12": ("dashboard", "refresh", "ui_refresh"),
    "FUN-13": ("noop", "stale_noop", "atomic_patch", "message_version"),
}
REVIEW_CHECKS = {"transactions", "durable_constraints", "append_only", "atomic_disable"}
UI_CHECKS = {"ui_clear", "ui_draft", "ui_refresh"}
_SECRET = re.compile(r"password|hash_password|password_hash|cookie|csrf|authorization|session_token", re.I)


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): ("[redacted]" if _SECRET.search(str(k)) else redact(v)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    return value


class ProbePack:
    """Evidence-bound base shared with architecture_contracts.

    Native checks are recorded only after actual execution. Supplemental proofs
    must name exact ``RID:check`` IDs, carry X/R/V, and match both hashes and file
    bytes. A valid artifact is necessary, not an authority to overwrite a FAIL.
    """
    checks: dict[str, tuple[str, ...]] = {}
    pack = ""
    review_checks = REVIEW_CHECKS
    ui_checks = UI_CHECKS

    def __init__(self, adapter: SupportAdapter, contract: AcceptanceContract):
        if (contract.brief_hash, contract.reference_hash) != (BRIEF_HASH, REFERENCE_HASH):
            raise ValueError("this pack is pinned to the reviewed Relais Support v0.2 documents")
        self.adapter, self.contract = adapter, contract
        self.requirements = {r.id: r for r in contract.requirements}
        canonical = import_contract(contract.brief, contract.reference, reviewed_by=contract.reviewed_by)
        if contract.requirements != canonical.requirements:
            raise ValueError("requirements must match the pinned source table, not a rewritten expectation")
        if not set(self.checks) <= self.requirements.keys():
            raise ValueError("acceptance contract lacks required IDs")
        self._observed: dict[str, list[dict]] = {}
        self._limits: dict[str, list[str]] = {}
        self._rid = ""

    def check(self, name: str, passed: bool, observed: Any, reproduction: str):
        if name not in self.checks[self._rid] or type(passed) is not bool:
            raise ValueError("unknown check or non-boolean assertion")
        self._observed[self._rid].append(dict(check=name, passed=passed,
            observed=redact(observed), reproduction=reproduction, evidence="X"))

    async def prepare(self, **options):
        manifest=await self.adapter.prepare_case(self._rid, **options)
        # A failed fixture login is an unavailable business prerequisite, not a
        # demonstrated role/transition defect. Security pack diagnoses the login.
        for actor in ("alice","bob","camille","dylan","emma"):
            response=await self.adapter.login(actor)
            if response.status_code!=200:
                raise AdapterUnavailable(f"real fixture login failed for {actor}: HTTP {response.status_code}")
        return manifest

    def ticket(self, alias="alice_open"):
        try:
            return self.adapter.manifest.tickets[alias]
        except KeyError as exc:
            raise AdapterUnavailable(f"fixture ticket absent: {alias}") from exc

    async def state(self):
        return await self.database_state("business_state")

    async def database_state(self,name):
        value=await self.adapter.observe(name)
        required={"users","tickets","messages","ticket_events","idempotency_keys"}
        if name=="full_database_state": required.add("sessions")
        if not isinstance(value,dict) or not required<=value.keys() or any(
            not isinstance(value[table],(list,tuple)) for table in required):
            raise AdapterUnavailable(f"{name} must expose actual canonical table rows, not null/boolean/digest only")
        return value

    async def ticket_state(self, ticket_id):
        value=await self.adapter.observe("ticket_state", ticket_id=ticket_id)
        fields={"status","priority","assignee_id","version","audit_count","message_count"}
        if not isinstance(value,dict) or not fields<=value.keys() or any(
            type(value[k]) is not int for k in ("version","audit_count","message_count")):
            raise AdapterUnavailable("ticket_state must expose actual version/counts/domain fields")
        return value

    async def req(self, actor, method, path, **kw):
        return await self.adapter.request(actor, method, path, **kw)

    async def patch(self, payload, *, actor="camille", ticket_id=None, **kw):
        return await self.req(actor, "PATCH", f"/api/tickets/{ticket_id or self.ticket()}", json=payload, **kw)

    async def create(self, *, actor="alice", title="Titre valide", description="Description valide " * 2,
                     key=None, **extra):
        return await self.req(actor, "POST", "/api/tickets", json=dict(title=title,
            description=description, client_request_id=key or str(uuid4()), **extra))

    async def message(self, *, actor="camille", content="Réponse publique", visibility="public",
                      ticket_id=None, key=None, **extra):
        return await self.req(actor, "POST", f"/api/tickets/{ticket_id or self.ticket()}/messages",
            json=dict(content=content, visibility=visibility, client_request_id=key or str(uuid4()), **extra))

    @staticmethod
    def body(response):
        try:
            value=response.json()
            return value if isinstance(value,dict) else {"invalid_json_shape":type(value).__name__}
        except (ValueError, UnicodeDecodeError):
            return {"invalid_json": True}

    def error(self, response, code):
        error=self.body(response).get("error")
        return isinstance(error,dict) and error.get("code")==code

    async def refused_unchanged(self, name, call, statuses=(403, 404, 409, 422), reproduction=""):
        before = await self.state()
        response = await call()
        after = await self.state()
        self.check(name, response.status_code in statuses and before == after,
                   {"status": response.status_code, "body": self.body(response),
                    "before_digest": digest(before), "after_digest": digest(after)}, reproduction)
        return response

    async def verify(self, snapshot_hash: str, *, ids=None) -> dict:
        if not re.fullmatch(r"[0-9a-f]{64}", snapshot_hash):
            raise ValueError("snapshot_hash must be SHA256")
        selected = list(self.checks) if ids is None else ids
        if (not isinstance(selected, (list, tuple)) or not selected or
                any(not isinstance(rid, str) or rid not in self.checks for rid in selected) or
                len(selected) != len(set(selected))):
            raise ValueError("explicit unique supported requirement IDs required")
        self._observed = {rid: [] for rid in self.checks}
        self._limits = {rid: [] for rid in self.checks}
        try:
            identity = (await self.adapter.snapshot_hash(), await self.adapter.contract_hash())
            identity_ok = identity == (snapshot_hash, self.contract.contract_hash)
        except (AdapterUnavailable,OSError,httpx.HTTPError) as exc:
            identity_ok, identity = False, str(exc)
        results = []
        for rid in selected:
            names = self.checks[rid]
            self._rid = rid
            if identity_ok:
                handler = getattr(self, "_" + rid.replace("-", ""), None)
                if handler:
                    try:
                        await handler()
                    except AdapterUnavailable as exc:
                        self._limits[rid].append(str(exc))
                    except (KeyError, TypeError, ValueError) as exc:
                        self._limits[rid].append(f"observable shape/port cannot be verified: {type(exc).__name__}: {exc}")
                    except (OSError, httpx.HTTPError, sqlite3.Error, TimeoutError) as exc:
                        self._limits[rid].append(f"execution prerequisite unavailable: {type(exc).__name__}")
                elif not set(names) <= self.review_checks:
                    self._limits[rid].append("independent source review required")
            else:
                self._limits[rid].append(f"snapshot/contract identity mismatch or unavailable: {identity}")
            requirement = self.requirements[rid]
            entries = self._observed[rid]
            if identity_ok:
                try:
                    if (await self.adapter.snapshot_hash(), await self.adapter.contract_hash()) != identity:
                        self._limits[rid].append("snapshot or oracle changed during execution; evidence not complete")
                except AdapterUnavailable as exc:
                    self._limits[rid].append(str(exc))
            proofs: list[Proof] = []
            if entries:
                root = Path(self.adapter.evidence_root).resolve() / snapshot_hash / self.pack
                path = root / f"{rid}-{uuid4().hex}.json"
                # Supervisor-owned evidence root is never mounted product-writable.
                data = dict(requirement_id=rid, snapshot_hash=snapshot_hash,
                            contract_hash=self.contract.contract_hash, observed=entries)
                try:
                    root.mkdir(parents=True, exist_ok=True)
                    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                    proofs.append(Proof("X", str(path), hashlib.sha256(path.read_bytes()).hexdigest(),
                        snapshot_hash, self.contract.contract_hash,
                        tuple(dict.fromkeys(f"{rid}:{e['check']}" for e in entries)), all(e["passed"] for e in entries)))
                except OSError:
                    self._limits[rid].append("supervisor evidence root unavailable; native artifact cannot be retained")
            # Completeness is a fact about this execution, never about supplied
            # PASS/R/UI receipts. Failed native assertions remain failed; this
            # metadata cannot authorize them or fill an unexecuted API/DB check.
            native_names = set(names) - self.review_checks - self.ui_checks
            native_complete = bool(identity_ok and not self._limits[rid] and
                native_names <= {entry["check"] for entry in entries})
            if identity_ok:
                try:
                    supplied = await self.adapter.proofs(rid)
                    proofs.extend(p for p in supplied if p.intact(snapshot_hash=snapshot_hash,
                                  contract_hash=self.contract.contract_hash))
                    if len(supplied) != len(proofs) - bool(entries):
                        self._limits[rid].append("stale, tampered or wrong-identity supplemental proof ignored")
                except (AdapterUnavailable,OSError,TypeError,AttributeError) as exc:
                    self._limits[rid].append(f"supplemental evidence unavailable: {type(exc).__name__}")
            missing = []
            failed = any(not e["passed"] for e in entries)
            for name in names:
                kind = "R" if name in self.review_checks else "X"
                observed = [e for e in entries if e["check"] == name]
                valid = [p for p in proofs if p.type == kind and f"{rid}:{name}" in p.checks]
                if observed:
                    # Native multi-case checks must all pass; external cannot replace them.
                    continue
                if valid:
                    failed |= any(not p.passed for p in valid)
                else:
                    missing.append(f"{rid}:{name} ({kind})")
            for kind in requirement.required_evidence:
                if not any(p.type == kind for p in proofs):
                    missing.append(f"evidence type {kind}")
            # Supplemental artifacts cannot satisfy unexecuted API/DB subprobes.
            external_only = self.review_checks | self.ui_checks
            for name in names:
                if name not in external_only and not any(e["check"] == name for e in entries):
                    marker = f"native execution absent: {rid}:{name}"
                    if marker not in missing:
                        missing.append(marker)
            status = "FAIL" if failed else "NOT_VERIFIED" if missing or self._limits[rid] or not identity_ok else "PASS"
            results.append(dict(id=rid, gate=requirement.gate, status=status, expected=requirement.expected,
                                native_complete=native_complete,
                observed=entries, reproduction=[e["reproduction"] for e in entries if not e["passed"]],
                proofs=[asdict(p) for p in proofs], impact=("contractual invariant violated" if failed else
                "no observed counterexample; coverage must remain complete"),
                limits=self._limits[rid] + missing))
        status = "FAIL" if any(r["status"] == "FAIL" for r in results) else (
            "PASS" if all(r["status"] == "PASS" for r in results) else "NOT_VERIFIED")
        return dict(pack=self.pack, status=status, snapshot_hash=snapshot_hash,
                    contract_hash=self.contract.contract_hash, requirements=results,
                    limits=["bounded contract probes, not an exhaustive arbitrary assertion verifier",
                            "historic PASS is not reused; every current native probe is executed"])


class BusinessContractVerifier(ProbePack):
    pack = "business"
    checks = BUSINESS_CHECKS

    async def _FUN01(self):
        await self.prepare()
        response = await self.create()
        body = self.body(response)
        self.check("creation", response.status_code == 201 and
            (body.get("owner_id"), body.get("status"), body.get("priority"), body.get("assignee_id"), body.get("version")) ==
            (self.adapter.manifest.accounts["alice"].id, "open", "normal", None, 1),
            {"status": response.status_code, "ticket": body}, "Alice POST /api/tickets; inspect server defaults")
        for actor in ("camille", "emma"):
            await self.refused_unchanged("roles", lambda actor=actor: self.create(actor=actor), (403,),
                                         f"{actor} POST /api/tickets is forbidden")
        for title, description, code in [("x"*n, "d"*20, 201 if 5 <= n <= 120 else 422) for n in (4,5,120,121)] + [
            ("Title", "d"*n, 201 if 20 <= n <= 5000 else 422) for n in (19,20,5000,5001)] + [
            (" \n \t", "d"*20,422), ("Title", " \n \t"*20,422), ("  Title  ","d"*20,201)]:
            r = await self.create(title=title, description=description)
            self.check("bounds", r.status_code == code and (code != 201 or self.body(r).get("title") == title.strip()),
                       {"status": r.status_code, "title_len": len(title), "description_len": len(description)},
                       f"POST title length {len(title)}, description length {len(description)}; expected {code}")

    async def _FUN02(self):
        await self.prepare()
        for actor, count in (("alice",6),("camille",12),("emma",12)):
            r = await self.req(actor,"GET","/api/tickets",params={"page_size":50})
            body=self.body(r)
            self.check("scope", r.status_code==200 and body.get("total")==count and len(body.get("items",[]))==count,
                       {"status":r.status_code,"body":body},f"{actor} GET tickets; fixture count {count}")
        r=await self.req("alice","GET",f"/api/tickets/{uuid4()}")
        self.check("missing",r.status_code==404,{"status":r.status_code},"GET absent UUID after viewing a real ticket")

    async def _FUN03(self):
        await self.prepare()
        for priority in ("low","normal","high"):
            s=await self.ticket_state(self.ticket())
            r=await self.patch({"priority":priority,"expected_version":s["version"]})
            self.check("priority",r.status_code==200 and self.body(r).get("priority")==priority,
                       {"status":r.status_code,"body":self.body(r)},f"staff PATCH priority {priority}")
        for actor,priority in (("alice","high"),("camille","urgent")):
            s=await self.ticket_state(self.ticket())
            await self.refused_unchanged("priority",lambda actor=actor,priority=priority,s=s:
                self.patch({"priority":priority,"expected_version":s["version"]},actor=actor),
                (403,) if actor=="alice" else (422,),f"reject priority {priority} by {actor}")
        for actor in ("camille","emma",None):
            s=await self.ticket_state(self.ticket()); target=self.adapter.manifest.accounts[actor].id if actor else None
            r=await self.patch({"assignee_id":target,"expected_version":s["version"]})
            self.check("assignment",r.status_code==200 and self.body(r).get("assignee_id")==target,
                       {"status":r.status_code},f"assign active {actor} or null")
        await self.adapter.command("deactivate_fixture_account", actor="dylan")
        for target in (self.adapter.manifest.accounts["alice"].id,self.adapter.manifest.accounts["dylan"].id,str(uuid4())):
            s=await self.ticket_state(self.ticket())
            await self.refused_unchanged("assignment",lambda target=target,s=s:
                self.patch({"assignee_id":target,"expected_version":s["version"]}),reproduction="reject client/inactive/missing assignable")
        s=await self.ticket_state(self.ticket())
        await self.refused_unchanged("assignment",lambda:self.patch({"assignee_id":None,"expected_version":s["version"]},actor="alice"),
                                     (403,),"client cannot assign/unassign own ticket")
        await self.prepare(status="closed")
        s=await self.ticket_state(self.ticket())
        await self.refused_unchanged("closed",lambda:self.patch({"assignee_id":None,"expected_version":s["version"]}),
                                     (409,),"manual unassignment of closed ticket")
        r=await self.patch({"priority":"high","expected_version":s["version"]})
        self.check("closed",r.status_code==200,{"status":r.status_code},"priority change remains allowed on closed ticket")
        r=await self.req("emma","PATCH",f"/api/users/{self.adapter.manifest.accounts['camille'].id}",json={"active":False})
        s=await self.ticket_state(self.ticket())
        self.check("disable_exception",r.status_code==200 and s["assignee_id"] is None,
                   {"status":r.status_code,"state":s},"disable assigned account clears even closed assignment")
        await self.prepare(status="resolved",public_staff_reply=True)
        s=await self.ticket_state(self.ticket())
        await self.refused_unchanged("closed",lambda:self.patch({"status":"closed","assignee_id":None,"expected_version":s["version"]}),
                                     (409,),"effective manual assignment change with resulting closed state is forbidden atomically")

    async def _FUN04(self):
        for source in STATUSES:
            for target in STATUSES:
                await self.prepare(status=source, assigned=True, public_staff_reply=True)
                before=await self.ticket_state(self.ticket())
                r=await self.patch({"status":target,"expected_version":before["version"]})
                after=await self.ticket_state(self.ticket())
                allowed=source==target or (source,target) in TRANSITIONS
                expected=200 if allowed else 409
                changed=source!=target and allowed
                ok=r.status_code==expected and after["status"]==(target if allowed else source) and (
                    after["version"]==before["version"]+int(changed) and
                    after["audit_count"]==before["audit_count"]+int(changed))
                self.check("matrix",ok,{"from":source,"to":target,"status":r.status_code,"before":before,"after":after},
                           f"PATCH {source}->{target}; expected {expected}, version/audit delta {int(changed)}")
        for source,target,options in [("open","in_progress",{"assigned":False}),
            ("resolved","in_progress",{"assigned":False}),
            ("in_progress","resolved",{"public_staff_reply":False}),
            ("in_progress","resolved",{"public_staff_reply":False,"internal_reply":True}),
            ("in_progress","resolved",{"public_staff_reply":False,"client_reply":True})]:
            await self.prepare(status=source, **options)
            s=await self.ticket_state(self.ticket())
            await self.refused_unchanged("preconditions",lambda target=target,s=s:
                self.patch({"status":target,"expected_version":s["version"]}),(409,),
                f"PATCH {source}->{target} with preconditions {options} must be atomic refusal")

    async def _FUN05(self):
        await self.prepare()
        for actor,visibility in (("alice","public"),("camille","public"),("camille","internal")):
            before=await self.ticket_state(self.ticket()); r=await self.message(actor=actor,visibility=visibility)
            after=await self.ticket_state(self.ticket()); body=self.body(r)
            self.check("messages",r.status_code==201 and after["status"]==before["status"] and after["version"]==before["version"]+1,
                       {"status":r.status_code,"before":before,"after":after},f"{actor} posts {visibility}, no implicit workflow")
            self.check("identity",body.get("author_id")==self.adapter.manifest.accounts[actor].id and
                isinstance(body.get("created_at"),str) and (body["created_at"].endswith("Z") or body["created_at"].endswith("+00:00")),
                body,"message author from session, timestamp explicit UTC")
        for content,code in [("x"*n,201 if 1<=n<=5000 else 422) for n in (0,1,5000,5001)]+[(" \n \t",422)]:
            r=await self.message(content=content)
            self.check("bounds",r.status_code==code,{"status":r.status_code,"length":len(content)},f"message bounds length {len(content)} ->{code}")
        await self.refused_unchanged("visibility",lambda:self.message(actor="alice",visibility="internal"),(403,),"client internal message forbidden")
        await self.refused_unchanged("visibility",lambda:self.message(actor="bob"),(404,),"other client cannot message Alice ticket")
        for extra in ({"author_id":str(uuid4())},{"created_at":"2000-01-01T00:00:00Z"}):
            await self.refused_unchanged("identity",lambda extra=extra:self.message(**extra),(422,),"server-only message identity/date fields cannot be supplied")
        r=await self.req("alice","GET",f"/api/tickets/{self.ticket()}/messages",params={"page_size":50})
        self.check("visibility",r.status_code==200 and all(m.get("visibility")=="public" for m in self.body(r).get("items",[])),
                   self.body(r),"client message list excludes internal before pagination")
        await self.prepare(status="closed")
        await self.refused_unchanged("messages",lambda:self.message(),(409,),"new message on closed ticket refused")

    async def _FUN06(self):
        await self.prepare()
        await self.adapter.login("camille",ip="127.0.0.2"); await self.adapter.login("dylan",ip="127.0.0.3")
        before=await self.ticket_state(self.ticket())
        await self.adapter.arm_race("ticket_patch",2)
        responses=await asyncio.gather(self.patch({"priority":"high","expected_version":before["version"]},ip="127.0.0.2"),
            self.patch({"priority":"low","expected_version":before["version"]},actor="dylan",ip="127.0.0.3"))
        after=await self.ticket_state(self.ticket())
        self.check("patch_race",sorted(r.status_code for r in responses)==[200,409] and
            after["version"]==before["version"]+1 and after["audit_count"]==before["audit_count"]+1,
            {"statuses":[r.status_code for r in responses],"before":before,"after":after},"barrier synchronized same-version PATCH on separate clients/DB connections")
        connections=await self.adapter.observe("race_connections")
        self.check("distinct_connections",len(set(connections))>=2,{"connections":connections},"trusted SQL trace records distinct connection identities")
        for winner in ("close","message"):
            await self.prepare(status="resolved",public_staff_reply=True)
            before=await self.ticket_state(self.ticket())
            await self.adapter.arm_race("close_message",2)
            await self.adapter.command("schedule_race_winner",winner=winner)
            responses=await asyncio.gather(self.patch({"status":"closed","expected_version":before["version"]}),self.message())
            after=await self.ticket_state(self.ticket())
            expected=[200,409] if winner=="close" else [409,201]
            self.check("close_wins" if winner=="close" else "message_wins",[r.status_code for r in responses]==expected and
                after["message_count"]==before["message_count"]+int(winner=="message") and after["version"]==before["version"]+1 and
                after["audit_count"]==before["audit_count"]+1 and len(set(await self.adapter.observe("race_connections")))>=2,
                {"statuses":[r.status_code for r in responses],"before":before,"after":after},f"controlled distinct-connection close/message overlap: {winner} commits first")

    async def _FUN07(self):
        await self.prepare(); key=str(uuid4())
        original=await self.state()
        r1=await self.create(key=key); before=await self.state(); r2=await self.create(key=key); after=await self.state()
        self.check("retry",r1.status_code==201 and r2.status_code==200 and self.body(r1).get("id")==self.body(r2).get("id") and before==after,
                   {"first":r1.status_code,"retry":r2.status_code,"same_state":before==after},"same user/UUID/normalized ticket payload replay")
        self.check("retry",len(before["tickets"])==len(original["tickets"])+1 and len(before["ticket_events"])==len(original["ticket_events"])+1,
                   {"ticket_delta":len(before["tickets"])-len(original["tickets"]),"audit_delta":len(before["ticket_events"])-len(original["ticket_events"])},
                   "ticket create and replay materialize exactly one ticket/event")
        normalized=await self.create(key=key,title="  Titre valide  ",description="  "+"Description valide "*2+"  ")
        self.check("retry",normalized.status_code==200,{"status":normalized.status_code},"same normalized ticket payload with outer whitespace replays")
        await self.refused_unchanged("conflicts",lambda:self.create(key=key,title="Autre titre"),(409,),"same idempotency key changed title")
        r=await self.create(actor="bob",key=key)
        self.check("users",r.status_code==201 and self.body(r).get("id")!=self.body(r1).get("id"),{"status":r.status_code},"same key isolated per user")
        r=await self.create(actor="camille",key=key)
        self.check("rights",r.status_code==403,{"status":r.status_code},"rights checked before key replay")
        cross_type=await self.message(actor="alice",key=key)
        self.check("users",cross_type.status_code==201,{"status":cross_type.status_code},"same user UUID isolated per operation type (ticket vs message)")
        alice_key=str(uuid4()); first_alice=await self.message(actor="alice",key=alice_key)
        self.check("rights",first_alice.status_code==201,{"status":first_alice.status_code},"prepare genuine Alice-owned message key")
        await self.refused_unchanged("rights",lambda:self.message(actor="alice",key=alice_key,ticket_id=self.ticket("bob_resolved")),
                                     (404,),"existing Alice key targeting inaccessible Bob ticket checks authorization before replay/conflict")
        key2=str(uuid4()); before=await self.state(); await self.adapter.arm_race("ticket_create",2)
        rr=await asyncio.gather(self.create(key=key2),self.create(key=key2))
        after=await self.state()
        self.check("simultaneous",sorted(r.status_code for r in rr)==[200,201] and self.body(rr[0]).get("id")==self.body(rr[1]).get("id"),
                   {"statuses":[r.status_code for r in rr]},"simultaneous same-key ticket creation returns one ID")
        self.check("simultaneous",len(after["tickets"])==len(before["tickets"])+1 and len(after["ticket_events"])==len(before["ticket_events"])+1 and
            len(set(await self.adapter.observe("race_connections")))>=2,{"ticket_delta":len(after["tickets"])-len(before["tickets"])},"distinct-connection simultaneous ticket retry creates one row/event")
        key3=str(uuid4()); first=await self.message(key=key3); saved=await self.state(); replay=await self.message(key=key3)
        self.check("retry",first.status_code==201 and replay.status_code==200 and self.body(first).get("id")==self.body(replay).get("id") and saved==await self.state(),
                   {"first":first.status_code,"retry":replay.status_code},"message retry one row/event/version")
        key4=str(uuid4()); before=await self.ticket_state(self.ticket()); await self.adapter.arm_race("message_create",2)
        rr=await asyncio.gather(self.message(key=key4),self.message(key=key4))
        after=await self.ticket_state(self.ticket())
        self.check("simultaneous",sorted(r.status_code for r in rr)==[200,201] and self.body(rr[0]).get("id")==self.body(rr[1]).get("id") and
            after["message_count"]==before["message_count"]+1 and after["version"]==before["version"]+1 and after["audit_count"]==before["audit_count"]+1 and
            len(set(await self.adapter.observe("race_connections")))>=2,
            {"statuses":[r.status_code for r in rr],"before":before,"after":after},"synchronized distinct-connection message retry one row/event/version")
        for options in ({"content":"Autre message"},{"visibility":"internal"},{"ticket_id":self.ticket("alice_second")}):
            r=await self.refused_unchanged("conflicts",lambda options=options:self.message(key=key3,**options),(409,),"same message key different content/visibility/target")
            self.check("conflicts",self.error(r,"IDEMPOTENCY_CONFLICT"),self.body(r),"stable IDEMPOTENCY_CONFLICT code")
        await self.adapter.restart(); replay=await self.message(key=key3)
        self.check("restart",replay.status_code==200 and self.body(replay).get("id")==self.body(first).get("id"),{"status":replay.status_code},"real server restart, same harness-retained key")
        await self.adapter.command("close_fixture_ticket",ticket_id=self.ticket())
        replay=await self.message(key=key3); new=await self.message()
        self.check("closed_replay",replay.status_code==200 and new.status_code==409,{"retry":replay.status_code,"new":new.status_code},"existing message replay allowed after closure, new key forbidden")
        await self.req("emma","PATCH",f"/api/users/{self.adapter.manifest.accounts['alice'].id}",json={"active":False})
        before=await self.state()
        r=await self.message(actor="alice",key=alice_key)
        self.check("rights",r.status_code==401 and before==await self.state(),{"status":r.status_code,"unchanged":before==await self.state()},
                   "disabled user cannot replay existing key through old real cookie")

    async def _FUN08(self):
        await self.prepare(); before=await self.ticket_state(self.ticket())
        r=await self.patch({"priority":"high","expected_version":before["version"]})
        history=await self.req("camille","GET",f"/api/tickets/{self.ticket()}/history",params={"page_size":50})
        items=self.body(history).get("items",[]); last=items[-1] if items else {}
        self.check("history",r.status_code==200 and history.status_code==200 and
            last.get("actor_id")==self.adapter.manifest.accounts["camille"].id and last.get("before",{}).get("priority")=="normal" and
            last.get("after",{}).get("priority")=="high" and str(last.get("created_at","")).endswith(("Z","+00:00")),
            {"status":history.status_code,"last_event":last},"effective priority PATCH creates actor/before/after/UTC event")
        before=await self.state(); version=(await self.ticket_state(self.ticket()))["version"]
        await self.adapter.set_fault("after_business_before_audit",True)
        try:
            r=await self.patch({"priority":"low","expected_version":version})
        finally:
            await self.adapter.set_fault("after_business_before_audit",False)
        after=await self.state()
        self.check("rollback",r.status_code>=500 and before==after,{"status":r.status_code,"before_digest":digest(before),"after_digest":digest(after)},
                   "trusted fixture fault between business and audit; entire transaction rolls back")

    async def _FUN09(self):
        await self.prepare(disable_scenario=True)
        await self.adapter.login("camille")
        before=await self.adapter.observe("assigned_tickets",actor="camille")
        r=await self.req("emma","PATCH",f"/api/users/{self.adapter.manifest.accounts['camille'].id}",json={"active":False})
        after=await self.adapter.observe("tickets_by_ids",ids=[t["id"] for t in before])
        self.check("disable",r.status_code==200 and bool(before) and len(before)==len(after) and all(
            b["assignee_id"] is None and b["version"]==a["version"]+1 and b["audit_count"]==a["audit_count"]+1 and b["status"]==a["status"]
            for a,b in zip(sorted(before,key=lambda t:t["id"]),sorted(after,key=lambda t:t["id"]))),
            {"status":r.status_code,"before":before,"after":after},"disable clears all assignments including closed and preserves in_progress")
        r=await self.req("camille","GET","/api/auth/me",authenticate=False)
        self.check("revocation",r.status_code==401,{"status":r.status_code},"pre-disable real session is permanently revoked")
        await self.req("emma","PATCH",f"/api/users/{self.adapter.manifest.accounts['camille'].id}",json={"active":True})
        r=await self.req("camille","GET","/api/auth/me",authenticate=False)
        assignments=await self.adapter.observe("assigned_tickets",actor="camille")
        self.check("reactivate",r.status_code==401 and assignments==[],{"status":r.status_code,"assigned":assignments},"reactivation restores neither old sessions nor assignments")
        await self.prepare(); target=self.adapter.manifest.accounts["camille"].id; s=await self.ticket_state(self.ticket())
        await self.adapter.arm_race("assign_disable",2)
        rr=await asyncio.gather(self.patch({"assignee_id":target,"expected_version":s["version"]},actor="dylan"),
            self.req("emma","PATCH",f"/api/users/{target}",json={"active":False}))
        invalid=await self.adapter.observe("inactive_assignments")
        self.check("assignment_race",rr[1].status_code==200 and invalid==[],{"statuses":[r.status_code for r in rr],"invalid":invalid},"overlapping assignment/deactivation has no inactive assignee")
        await self.prepare(disable_scenario=True)
        await self.adapter.login("emma"); await self.adapter.login("camille")
        before=await self.database_state("full_database_state")
        await self.adapter.set_fault("after_business_before_audit",True)
        try:
            r=await self.req("emma","PATCH",f"/api/users/{self.adapter.manifest.accounts['camille'].id}",json={"active":False})
        finally:
            await self.adapter.set_fault("after_business_before_audit",False)
        after=await self.database_state("full_database_state")
        self.check("disable",r.status_code>=500 and before==after,
            {"status":r.status_code,"before_digest":digest(before),"after_digest":digest(after)},
            "failed disable rolls back users, revoked sessions, all tickets and audit together")

    async def _FUN10(self):
        await self.prepare(search_scenario=True)
        # Trusted fixture declares exact expected IDs; not derived from product queries.
        expected=self.adapter.manifest.metadata.get("search_expected")
        if expected is None: raise AdapterUnavailable("independent search fixture expectations absent")
        for query,ids in expected.items():
            r=await self.req("alice","GET","/api/tickets",params={"q":query,"page_size":50}); body=self.body(r)
            name="notes" if query=="INTERNAL_ONLY" else "literal" if query in ("%","_","'") else "search"
            self.check(name,r.status_code==200 and body.get("total")==len(ids) and {i.get("id") for i in body.get("items",[])}==set(ids),
                {"q":query,"status":r.status_code,"body":body},f"search literal {query!r}, fixture IDs {ids}")
        for n,code in ((0,200),(100,200),(101,422)):
            r=await self.req("alice","GET","/api/tickets",params={"q":"x"*n})
            self.check("bounds",r.status_code==code,{"length":n,"status":r.status_code},f"q length {n} ->{code}")
        r=await self.req("alice","GET","/api/tickets",params={"q":"shared","page_size":1})
        ids=self.adapter.manifest.metadata["search_expected"]["shared"]
        self.check("acl_before_page",r.status_code==200 and self.body(r).get("total")==len(ids) and
            all(i.get("owner_id")==self.adapter.manifest.accounts["alice"].id for i in self.body(r).get("items",[])),
            self.body(r),"ACL before total/page_size=1, Bob also has matching shared ticket")

    async def _FUN11(self):
        await self.prepare(pagination_scenario=True)
        expected=self.adapter.manifest.metadata.get("pagination_expected")
        if expected is None: raise AdapterUnavailable("independent pagination fixture expectations absent")
        for params,code in (({"page":1},200),({"page":0},422),({"page_size":1},200),({"page_size":50},200),({"page_size":51},422),
            ({"assigned_to_me":True,"unassigned":True},422)):
            r=await self.req("camille","GET","/api/tickets",params=params)
            self.check("bounds",r.status_code==code,{"params":params,"status":r.status_code},f"pagination bounds {params} ->{code}")
        for params in ({"assigned_to_me":True},{"unassigned":True}):
            r=await self.req("alice","GET","/api/tickets",params=params)
            self.check("filters",r.status_code==403,{"params":params,"status":r.status_code},"staff-only assignment filters forbidden to client")
        for params,ids in self.adapter.manifest.metadata.get("filter_expected",[]):
            r=await self.req("camille","GET","/api/tickets",params={"page_size":50,**params}); body=self.body(r)
            self.check("filters",r.status_code==200 and body.get("total")==len(ids) and [i.get("id") for i in body.get("items",[])]==ids,
                       {"params":params,"body":body},"AND status/priority/assignment filters exact fixture IDs")
        found=[]
        for page in range(1,(len(expected)+19)//20+1):
            r=await self.req("camille","GET","/api/tickets",params={"page":page,"page_size":20}); body=self.body(r)
            self.check("pagination",r.status_code==200 and body.get("total")==len(expected) and body.get("page")==page and body.get("page_size")==20,
                       {"status":r.status_code,"total":body.get("total"),"page":page},"stable >50 ticket page envelope")
            found.extend(i.get("id") for i in body.get("items",[]))
        self.check("sort",found==expected and len(found)==len(set(found)),{"expected":expected,"observed":found},"all pages updated_at DESC,id DESC, no omissions/duplicates")
        r=await self.req("camille","GET","/api/tickets",params={"page":9999})
        self.check("pagination",r.status_code==200 and self.body(r).get("items")==[] and self.body(r).get("total")==len(expected),self.body(r),"high page empty with unchanged total")

    async def _FUN12(self):
        await self.prepare()
        for actor,total in (("alice",6),("camille",12)):
            r=await self.req(actor,"GET","/api/dashboard"); body=self.body(r)
            expected=self.adapter.manifest.metadata.get("dashboard_expected",{}).get(actor)
            if expected is None: raise AdapterUnavailable("independent dashboard expectations absent")
            self.check("dashboard",r.status_code==200 and body==expected and body.get("total")==total and
                sum(body.get(s,-1000) for s in STATUSES)==total,body,f"{actor} scoped four status counts including zeros")
        created=await self.create(); r=await self.req("alice","GET","/api/dashboard"); body=self.body(r)
        old=self.adapter.manifest.metadata["dashboard_expected"]["alice"]
        expected={**old,"total":old["total"]+1,"open":old["open"]+1}
        self.check("refresh",created.status_code==201 and r.status_code==200 and body==expected,body,"GET dashboard after ticket creation updates own counts")

    async def _FUN13(self):
        await self.prepare(); s=await self.ticket_state(self.ticket()); before=await self.state()
        r=await self.patch({"priority":s["priority"],"expected_version":s["version"]})
        self.check("noop",r.status_code==200 and before==await self.state(),{"status":r.status_code,"before_digest":digest(before),"after_digest":digest(await self.state())},"same-version no-op leaves all business bytes unchanged")
        await self.message(); now=await self.ticket_state(self.ticket())
        r=await self.refused_unchanged("stale_noop",lambda:self.patch({"priority":now["priority"],"expected_version":s["version"]}),(409,),"stale expected_version rejected even for current identical value")
        self.check("stale_noop",self.error(r,"VERSION_CONFLICT"),self.body(r),"stable VERSION_CONFLICT code")
        await self.refused_unchanged("atomic_patch",lambda:self.patch({"priority":"high","status":"resolved","expected_version":now["version"]}),(409,),"invalid final workflow + valid priority must not partially apply")
        for payload in ({"priority":"high"},{"priority":"high","expected_version":0},
            {"priority":"high","expected_version":1.5},{"expected_version":now["version"]},
            {"title":"Changed immutable title","expected_version":now["version"]}):
            await self.refused_unchanged("atomic_patch",lambda payload=payload:self.patch(payload),(422,),
                                         "PATCH requires integer expected_version >=1 and a permitted mutable field only")
        r=await self.message(); after=await self.ticket_state(self.ticket())
        self.check("message_version",r.status_code==201 and after["version"]==now["version"]+1 and after["audit_count"]==now["audit_count"]+1,
                   {"status":r.status_code,"before":now,"after":after},"one effective message -> one version and one event")
