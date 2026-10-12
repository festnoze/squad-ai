"""Owned browser meta-test subject: real HTTP, SQLite, Argon2 and server cookies.

This is NOT a generated support product. Positive/adversarial fixtures exercise
the independent observers; their results never qualify a generated snapshot.
"""
from __future__ import annotations
import hashlib
import json
import os
import inspect
import shutil
import secrets
import socket
import threading
import time
from pathlib import Path

import uvicorn
from argon2 import PasswordHasher
from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from autospec.contracts import ContractFact, ContractStore, import_contract
from autospec.validation.browser_contracts import BROWSER_IDS, PlaywrightHarness
from autospec.validation.quality_contracts import QUALITY_IDS
from autospec.validation.support_adapter import AdapterUnavailable, FixtureAccount
from tests.support_contract_fixture import SQLiteSupportSubject, SubjectError

HASHER = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)


def fixture_snapshot(bug):
    files = [Path(__file__), Path(__file__).with_name("ui.html"), Path(inspect.getfile(SQLiteSupportSubject))]
    return hashlib.sha256(b"".join(path.read_bytes() for path in files) + bug.encode()).hexdigest()
CONTROLS = {name: "#" + identifier for name, identifier in {
    "email":"email", "password":"password", "login":"login", "ticket_list":"ticket-list", "detail":"detail", "detail_title":"detail-title", "detail_status":"detail-status",
    "create":"create", "ticket_nav":"tickets", "admin_nav":"admin-nav", "title":"title", "description":"description", "submit":"submit", "search":"search",
    "reply":"reply", "send":"send", "messages":"messages", "visibility":"visibility", "logout":"logout",
    "refresh":"refresh", "retry":"retry", "reply_retry":"reply-retry", "loading":"loading", "empty":"empty", "error":"error",
    "modal":"modal", "priority":"priority", "status":"status", "assignee":"assignee", "apply":"apply",
    "conflict":"conflict", "reload":"reload", "total":"total", "dashboard_nav":"dashboard-nav", "dashboard_total":"dashboard-total",
    "users":"users",
    "new_email":"new-email", "new_password":"new-password", "new_name":"new-name", "new_role":"new-role", "create_user":"create-user",
    "confirm":"confirm", "page_next":"page-next", "page_previous":"page-previous", "priority_filter":"priority-filter",
    "status_filter":"status-filter", "dashboard_open":"dashboard-open", "dashboard_in_progress":"dashboard-in_progress",
    "assignment_filter":"assignment-filter",
    "dashboard_resolved":"dashboard-resolved", "dashboard_closed":"dashboard-closed"
}.items()}
CONTROLS["user_toggle"] = '[data-user="{id}"]'
CONTROLS["internal_note"] = '.internal'


def retain_browser_fixture_report(report,subject):
    """Optional supervisor export: only report/proof bytes, never credentials/DB."""
    selected=os.environ.get("AUTOSPEC_BROWSER_FIXTURE_EVIDENCE_ROOT")
    if not selected:return
    target=Path(selected).resolve()/subject.root.parent.name/(report["pack"]+"-"+getattr(subject,"browser_bug","good"))
    target.mkdir(parents=True,exist_ok=True)
    result=json.loads(json.dumps(report))
    for row in result.get("requirements",result.get("scenarios",[])):
        for proof in row["proofs"]:
            source=Path(proof["path"]).resolve()
            if (not source.is_relative_to(subject.root.parent.resolve()) or source.suffix not in {".json",".png",".txt"}
                    or source.stat().st_size>10_000_000):raise ValueError("only bounded owned fixture proofs may be retained")
            destination=target/source.name
            shutil.copyfile(source,destination);proof["path"]=str(destination)
    result.update(scope="independent observer fixture meta-test, not generated-product conformity",
                  fixture_fault=getattr(subject,"browser_bug",""))
    (target/("report-"+str(report.get("mode",""))+".json")).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")


def browser_contract():
    root = Path(__file__).resolve().parents[4]
    brief = (root / "docs/validation/support-client/01_specification.md").read_bytes().decode("utf-8")
    reference = (root / "docs/validation/support-client/02_requirements_verification.md").read_bytes().decode("utf-8")
    profile = json.loads(Path(__file__).with_name("profile.json").read_text(encoding="utf-8"))
    return import_contract(brief, reference, reviewed_by="independent browser fixture review", facts=[
        ContractFact.create("browser-fixture-v02", "browser_profile", profile["browser"], BROWSER_IDS, brief),
        ContractFact.create("quality-fixture-v02", "quality_profile", profile["quality"], QUALITY_IDS, brief)])


class BrowserSubject(SQLiteSupportSubject):
    def __init__(self, root, contract, bug=""):
        self.browser_bug = bug
        self.http_origin = "http://127.0.0.1"
        super().__init__(root, contract)
        self.snapshot = fixture_snapshot(bug)
        self.adapter.evidence_root = root.parent / "browser-proofs"
        store = ContractStore(root.parent / "browser-oracle", product_write_roots=[root])
        oracle = store.save(contract)
        async def oracle_hash(): return store.load(oracle).contract_hash
        async def snapshot():
            return fixture_snapshot(bug)
        self.adapter._ports["oracle"] = oracle_hash
        self.adapter._ports["snapshot"] = snapshot

    @staticmethod
    def password_hash(password, salt):
        return HASHER.hash(password)

    def _create_schema(self):
        super()._create_schema()
        con=self.connect()
        try:
            con.execute("CREATE TABLE IF NOT EXISTS user_names(user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,name TEXT NOT NULL)")
            con.commit()
        finally:con.close()

    async def prepare(self, case_id, **options):
        options = dict(options, assigned=False, search_scenario=True)
        manifest=await super().prepare(case_id, **options)
        manifest.metadata["browser_probes"] = json.loads(Path(__file__).with_name("profile.json").read_text(encoding="utf-8"))["browser_probes"]
        con=self.connect()
        try:
            con.executemany("INSERT INTO user_names VALUES(?,?)",[(a.id,name.capitalize()) for name,a in manifest.accounts.items()]);con.commit()
            from uuid import UUID, uuid4
            mixed=manifest.tickets["alice_second"];only=str(UUID(int=104))
            manifest.tickets.update(alice_mixed=mixed,alice_internal_only=only)
            con.execute("UPDATE tickets SET assignee_id=? WHERE id=?",(manifest.accounts["camille"].id,mixed))
            for tid,actor,visibility,content in [(mixed,"camille","public","PUBLIC_SEED_MESSAGE"),(mixed,"dylan","internal","INTERNAL_SEED_MIXED"),
                                                 (only,"dylan","internal","INTERNAL_SEED_ONLY")]:
                mid=str(uuid4());con.execute("INSERT INTO messages VALUES(?,?,?,?,?,?)",(mid,tid,manifest.accounts[actor].id,content,visibility,self.timestamp()))
                self.audit(con,tid,{"id":manifest.accounts[actor].id},"message",{},dict(message_id=mid,visibility=visibility),visibility)
            con.commit()
            manifest.metadata["internal_markers"]=["INTERNAL_SEED_MIXED","INTERNAL_SEED_ONLY"]
            manifest.metadata["internal_author_id"]=manifest.accounts["dylan"].id
        finally:con.close()
        return manifest

    def auth(self, request, con):
        token = request.cookies.get("session", "")
        row = con.execute("SELECT users.*,sessions.csrf,sessions.expires,sessions.revoked FROM sessions JOIN users ON users.id=sessions.user_id WHERE token_hash=?",
                          (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
        if row is None or (row["revoked"] and self.browser_bug!="old_session_revived") or not row["active"] or row["expires"] <= self.now:
            raise SubjectError(401, "UNAUTHENTICATED")
        if request.method not in ("GET", "HEAD") and (request.headers.get("Origin") != self.http_origin or request.headers.get("X-CSRF-Token") != row["csrf"]):
            raise SubjectError(403, "FORBIDDEN")
        return dict(row)

    def ticket_visible(self,con,actor,ticket_id):
        if self.browser_bug=="idor_disabled":
            row=con.execute("SELECT * FROM tickets WHERE id=?",(ticket_id,)).fetchone()
            if row is None:raise SubjectError(404,"NOT_FOUND")
            return dict(row)
        return super().ticket_visible(con,actor,ticket_id)

    def read(self, con, actor, request, path, ticket_id=None):
        if path == "me": return {"id": actor["id"], "role": actor["role"], "csrf_token": actor["csrf"]}
        result=super().read(con, actor, request, path, ticket_id)
        if path=="messages" and self.browser_bug=="internal_leak":
            result["items"]=[dict(row) for row in con.execute("SELECT * FROM messages WHERE ticket_id=?",(ticket_id,))]
            result["total"]=len(result["items"])
        if path=="dashboard":return {"total":result["total"],"by_status":{s:result[s] for s in ["open","in_progress","resolved","closed"]}}
        if path in {"users","assignees"}:
            for row in result["items"]:
                row["display_name"]=con.execute("SELECT name FROM user_names WHERE user_id=?",(row["id"],)).fetchone()[0]
            if path=="assignees":result["items"]=[{"id":row["id"],"display_name":row["display_name"]} for row in result["items"]]
        return result

    def mutate(self,con,actor,action,payload,ticket_id=None,user_id=None):
        if action!="disable":return super().mutate(con,actor,action,payload,ticket_id,user_id)
        con.execute("BEGIN IMMEDIATE")
        if actor["role"]!="admin":raise SubjectError(403,"FORBIDDEN")
        if set(payload)!={"active"} or type(payload["active"]) is not bool:raise SubjectError(422,"VALIDATION_ERROR")
        account=con.execute("SELECT * FROM users WHERE id=?",(user_id,)).fetchone()
        if not account:raise SubjectError(404,"NOT_FOUND")
        if not payload["active"] and account["role"]=="admin" and account["active"] and con.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND active=1").fetchone()[0]<=1:
            raise SubjectError(409,"LAST_ADMIN")
        con.execute("UPDATE users SET active=? WHERE id=?",(int(payload["active"]),user_id))
        if not payload["active"]:
            con.execute("UPDATE sessions SET revoked=1 WHERE user_id=?",(user_id,))
            for row in con.execute("SELECT * FROM tickets WHERE assignee_id=?",(user_id,)).fetchall():
                before=dict(row);con.execute("UPDATE tickets SET assignee_id=NULL,version=version+1,updated_at=? WHERE id=?",(self.timestamp(),row["id"]))
                after=dict(con.execute("SELECT * FROM tickets WHERE id=?",(row["id"],)).fetchone())
                self.audit(con,row["id"],actor,"system_unassigned",before,after)
        return {"id":user_id,"active":payload["active"]},200

    def _routes(self):
        super()._routes()
        self.app.router.routes = [route for route in self.app.router.routes if getattr(route, "path", "") not in ["/api/auth/login", "/api/auth/logout"]]
        @self.app.post("/api/auth/login")
        async def login(request: Request):
            if request.headers.get("Origin") != self.http_origin: raise SubjectError(403, "FORBIDDEN")
            data = await request.json(); con = self.connect()
            try:
                row = con.execute("SELECT * FROM users WHERE email_normalized=?", (data.get("email", "").strip().lower(),)).fetchone()
                if row is None or not row["active"]: raise SubjectError(401, "UNAUTHENTICATED")
                try: HASHER.verify(row["password_hash"], data.get("password", ""))
                except Exception: raise SubjectError(401, "UNAUTHENTICATED")
                token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
                con.execute("INSERT INTO sessions VALUES(?,?,?,?,0)", (hashlib.sha256(token.encode()).hexdigest(), row["id"], csrf, self.now+28800)); con.commit()
                response = JSONResponse({"csrf_token": csrf})
                response.set_cookie("session", token, httponly=True, samesite="lax", path="/")
                return response
            finally: con.close()
        login_route = self.app.router.routes.pop(); self.app.router.routes.insert(0, login_route)
        @self.app.post("/api/auth/logout")
        async def logout(request: Request):
            if request.headers.get("Origin") != self.http_origin: raise SubjectError(403, "FORBIDDEN")
            con = self.connect()
            try:
                token = request.cookies.get("session", "")
                if token:
                    self.auth(request, con)
                    con.execute("UPDATE sessions SET revoked=1 WHERE token_hash=?", (hashlib.sha256(token.encode()).hexdigest(),)); con.commit()
                response = Response(status_code=204); response.delete_cookie("session", path="/"); return response
            finally: con.close()
        logout_route = self.app.router.routes.pop(); self.app.router.routes.insert(0, logout_route)
        @self.app.post("/api/users")
        async def create_user(request:Request):
            import re
            con=self.connect()
            try:
                actor=self.auth(request,con)
                if actor["role"]!="admin":raise SubjectError(403,"FORBIDDEN")
                payload=await request.json()
                if set(payload)!={"email","display_name","password","role"}:raise SubjectError(422,"VALIDATION_ERROR")
                email=payload["email"].strip().lower();name=payload["display_name"].strip();password=payload["password"]
                if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+",email) or len(email)>254 or not 1<=len(name)<=80 or not 14<=len(password)<=128 or payload["role"] not in {"client","agent","admin"}:
                    raise SubjectError(422,"VALIDATION_ERROR")
                from uuid import uuid4
                uid=str(uuid4());con.execute("BEGIN IMMEDIATE")
                try:con.execute("INSERT INTO users VALUES(?,?,?,?,?,1)",(uid,email,email,HASHER.hash(password),payload["role"]))
                except Exception:raise SubjectError(409,"EMAIL_CONFLICT")
                con.execute("INSERT INTO user_names VALUES(?,?)",(uid,name));con.commit()
                return JSONResponse({"id":uid,"email":email,"display_name":name,"role":payload["role"],"active":True},status_code=201)
            except BaseException:con.rollback();raise
            finally:con.close()
        user_route=self.app.router.routes.pop();self.app.router.routes.insert(0,user_route)
        @self.app.get("/{path:path}")
        async def frontend(path: str):
            html = Path(__file__).with_name("ui.html").read_text(encoding="utf-8").replace("__FIXTURE_BUG__", self.browser_bug)
            return HTMLResponse(html)

    async def observe(self, name, **params):
        if name == "browser_operation_count":
            con = self.connect()
            try: return con.execute("SELECT COUNT(*) FROM tickets WHERE title=?", (params["title"],)).fetchone()[0]
            finally: con.close()
        if name=="browser_message_count":
            con=self.connect()
            try:return con.execute("SELECT COUNT(*) FROM messages WHERE ticket_id=? AND content=?",(params["ticket_id"],params["content"])).fetchone()[0]
            finally:con.close()
        if name=="browser_dashboard_expected":
            con=self.connect()
            try:
                account=self.manifest.accounts[params["actor"]]
                rows=con.execute("SELECT status FROM tickets"+(" WHERE owner_id=?" if account.role=="client" else ""),(account.id,) if account.role=="client" else ()).fetchall()
                return {"total":len(rows),"by_status":{s:sum(r[0]==s for r in rows) for s in ["open","in_progress","resolved","closed"]}}
            finally:con.close()
        if name == "frontend_api_origin_scan":
            import re
            path = Path(__file__).with_name("ui.html")
            text = path.read_text(encoding="utf-8")
            return {"absolute_api_urls": re.findall(r"https?://[^\s\"']+/api", text), "scanned_files": [
                {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}]}
        return await super().observe(name, **params)

    async def command(self, action, **params):
        if action=="register_actor":
            self.manifest.accounts[params["actor"]]=FixtureAccount(params["id"],params["email"],params["password"],params["role"])
            return {"exit_code":0,"fixture_only":True}
        if action == "expire_actor":
            con = self.connect()
            try:
                con.execute("UPDATE sessions SET expires=? WHERE user_id=?", (self.now-1, self.manifest.accounts[params["actor"]].id)); con.commit()
                return {"exit_code": 0, "fixture_only": True}
            finally: con.close()
        return await super().command(action, **params)

    def start_http(self):
        self.socket = socket.socket(); self.socket.bind(("127.0.0.1", 0)); self.socket.listen(128)
        self.http_origin = f"http://127.0.0.1:{self.socket.getsockname()[1]}"
        self.adapter.base_url = self.adapter.origin = self.http_origin
        self.server = uvicorn.Server(uvicorn.Config(self.app, log_level="error", access_log=False, ws="none"))
        self.thread = threading.Thread(target=self.server.run, kwargs={"sockets": [self.socket]}, daemon=True)
        self.thread.start(); deadline = time.monotonic()+5
        while not self.server.started and time.monotonic()<deadline: time.sleep(.01)
        if not self.server.started: raise AdapterUnavailable("owned browser fixture HTTP server failed")

    def stop_http(self):
        self.server.should_exit = True; self.thread.join(timeout=5); self.socket.close()
        if self.thread.is_alive(): raise RuntimeError("owned browser fixture did not stop")

    def harness(self):
        return PlaywrightHarness(self.adapter, bindings=CONTROLS, routes={"home":"/", "ticket":"/tickets/{id}", "admin":"/admin"},
                                 executable_path=os.environ.get("AUTOSPEC_TRUSTED_CHROMIUM"),trusted_fixture_local_browser=True)
