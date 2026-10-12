"""Executable HTTP/SQLite/Argon2 oracle fixtures, never production repair code."""

from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
import sqlite3
import threading
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

import httpx
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from autospec.contracts import ContractFact, ContractStore, import_contract
from autospec.validation.support_adapter import AdapterUnavailable, FixtureAccount, FixtureManifest, HttpxSupportAdapter, Proof
from autospec.validation.entropy_protocol import correlate_entropy, entropy_execution_proof


HASHER = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)
PASSWORDS = {"alice": "Alice password 漢字 2026", "bob": "Bob password 漢字 2026", "agent": "Camille password 漢字 2026",
             "agent2": "Dylan password 漢字 2026", "admin": "Emma password 漢字 2026"}
BASE_HASHES = {actor: HASHER.hash(password) for actor, password in PASSWORDS.items()}
DUMMY_HASH = HASHER.hash("Dummy account password 2026")


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


def security_contract():
    docs = Path(__file__).resolve().parents[4] / "docs/validation/support-client"
    brief = (docs / "01_specification.md").read_bytes().decode("utf-8")
    reference = (docs / "02_requirements_verification.md").read_bytes().decode("utf-8")
    profile = json.loads(Path(__file__).with_name("profile.json").read_text(encoding="utf-8"))
    return import_contract(brief, reference, reviewed_by="fixture-oracle-review", facts=[
        ContractFact.create("support-security-v02", "security_profile", profile,
                            [f"SEC-{i:02d}" for i in range(1, 16)], brief)])


class SecurityApplication:
    def __init__(self, root: Path, *, broken: str = "", only: str = ""):
        self.root, self.broken = root, broken
        self.only = only
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = root / "isolated.sqlite"
        self.now = 1_791_000_000.0
        self.limiters = {}
        self.dummy_count = 0
        self.race_point, self.barrier = "", None
        self.race_connections = []
        self.connection_counter = 0
        self.counter_lock = threading.Lock()
        self.db_fault = False
        self.logs = []
        self.entropy_records = []
        self.local_http_explicit = True
        self.allowed_origin = "https://localhost"
        self.manifest = FixtureManifest()
        self.app = self._app()

    def connect(self):
        conn = sqlite3.connect(self.db_path, timeout=5, check_same_thread=False, factory=ClosingConnection)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _schema(self):
        self.db_path.unlink(missing_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE users(id TEXT PRIMARY KEY, email TEXT, email_normalized TEXT, display_name TEXT,
                                   password_hash TEXT, role TEXT, active INTEGER);
                CREATE TABLE sessions(token_digest TEXT PRIMARY KEY,user_id TEXT REFERENCES users(id),csrf TEXT,expires REAL);
                CREATE TABLE tickets(id TEXT PRIMARY KEY,owner_id TEXT REFERENCES users(id),title TEXT,description TEXT,version INTEGER);
                CREATE TABLE messages(id TEXT PRIMARY KEY,ticket_id TEXT REFERENCES tickets(id),author_id TEXT REFERENCES users(id),content TEXT,visibility TEXT);
                CREATE TABLE events(id TEXT PRIMARY KEY,ticket_id TEXT REFERENCES tickets(id),message_id TEXT,visibility TEXT);
                CREATE TABLE idempotency(user_id TEXT,key TEXT,ticket_id TEXT,object_id TEXT,PRIMARY KEY(user_id,key));
            """)
            if self.broken != "SEC-02":
                db.execute("CREATE UNIQUE INDEX unique_email ON users(email_normalized)")

    def _insert_user(self, db, account, password_hash=None):
        db.execute("INSERT INTO users VALUES (?,?,?,?,?,?,?)", (account.id, account.email, account.email.strip().lower(),
                   account.email.split("@")[0], password_hash or HASHER.hash(account.password), account.role, int(account.active)))

    async def prepare(self, rid, **options):
        if self.only and rid != self.only:
            raise AdapterUnavailable("this oracle fixture isolates one family only")
        self._schema()
        self.now, self.limiters, self.logs, self.dummy_count = 1_791_000_000.0, {}, [], 0
        self.entropy_records = []
        self.race_point, self.barrier, self.race_connections = "", None, []
        accounts = {actor: FixtureAccount(str(uuid4()), actor + "@example.test", password,
                    "admin" if actor == "admin" else "agent" if actor.startswith("agent") else "client")
                    for actor, password in PASSWORDS.items()}
        tickets = {name: str(uuid4()) for name in ["alice", "bob", "internal_only"]}
        self.manifest = FixtureManifest(accounts, tickets, {"alice_ticket_count": 2})
        with self.connect() as db:
            if rid != "SEC-01" or self.broken == "SEC-01":
                for actor, account in accounts.items():
                    self._insert_user(db, account, BASE_HASHES[actor])
            if rid != "SEC-01":
                for name, tid in tickets.items():
                    owner = accounts["bob" if name == "bob" else "alice"].id
                    db.execute("INSERT INTO tickets VALUES (?,?,?,?,1)", (tid, owner, "Fixture " + name, "Fixture description long enough"))
                for visibility, tid in [("public", tickets["alice"]), ("internal", tickets["internal_only"])]:
                    mid = str(uuid4())
                    db.execute("INSERT INTO messages VALUES (?,?,?,?,?)", (mid, tid, accounts["agent"].id, "Seed " + visibility, visibility))
                    db.execute("INSERT INTO events VALUES (?,?,?,?)", (str(uuid4()), tid, mid, visibility))
        return self.manifest

    def error(self, code, status):
        return JSONResponse({"error": {"code": code, "message": "Requête refusée"}}, status_code=status)

    def actor(self, request, db):
        token = request.cookies.get("fixture_session", "")
        digest = hashlib.sha256(token.encode()).hexdigest()
        return db.execute("SELECT users.*,sessions.csrf FROM users JOIN sessions ON users.id=sessions.user_id "
                          "WHERE token_digest=? AND expires>? AND active=1", (digest, self.now)).fetchone()

    def guard(self, request, db, *, mutate=False, admin=False, staff=False):
        actor = self.actor(request, db)
        if not actor:
            return None, self.error("SESSION_REQUIRED", 401)
        if admin and actor["role"] != "admin" or staff and actor["role"] not in ["admin", "agent"]:
            return actor, self.error("FORBIDDEN", 403)
        if mutate:
            if request.headers.get("origin") != self.allowed_origin:
                return actor, self.error("ORIGIN", 403)
            if (self.broken != "SEC-07" or request.url.path != "/api/auth/logout") and request.headers.get("x-csrf-token") != actor["csrf"]:
                return actor, self.error("CSRF", 403)
        return actor, None

    def race(self, point, db):
        if self.barrier is not None and self.race_point == point:
            with self.counter_lock:
                self.connection_counter += 1
                self.race_connections.append((self.connection_counter, id(db)))
            barrier = self.barrier
            barrier.wait(timeout=5)

    def _app(self):
        app = FastAPI()

        @app.middleware("http")
        async def cache(request, call_next):
            response = await call_next(request)
            if self.broken != "SEC-15":
                response.headers["Cache-Control"] = "no-store"
            return response

        @app.post("/api/auth/login")
        def login(request: Request, body: dict):
            if request.headers.get("origin") != self.allowed_origin:
                return self.error("ORIGIN", 403)
            ip = request.client.host
            count, start = self.limiters.get(ip, (0, self.now))
            if self.now - start >= 60:
                count, start = 0, self.now
            if count >= 10:
                r = self.error("RATE_LIMITED", 429)
                r.headers["Retry-After"] = str(max(1, int(60 - (self.now - start))))
                return r
            with self.connect() as db:
                account = db.execute("SELECT * FROM users WHERE email_normalized=?", (body.get("email", "").strip().lower(),)).fetchone()
                encoded = account["password_hash"] if account else DUMMY_HASH
                valid = False
                if account or self.broken != "SEC-04":
                    self.dummy_count += int(account is None)
                    try:
                        if encoded.startswith("sha256:"):
                            valid = encoded == "sha256:" + hashlib.sha256(body.get("password", "").encode()).hexdigest()
                        else:
                            valid = HASHER.verify(encoded, body.get("password", ""))
                    except (VerifyMismatchError, InvalidHashError):
                        valid = False
                if not account or not account["active"] or not valid:
                    self.limiters[ip] = (count + 1, start)
                    return self.error("LOGIN_FAILED", 401)
                self.limiters[ip] = (0 if self.broken == "SEC-04" else count, start)
                nbytes = 16 if self.broken == "entropy_small" else 32
                generated = secrets.token_urlsafe(nbytes)
                self.entropy_records.append(dict(generator="secrets.token_urlsafe", nbytes=nbytes,
                    default_argument=False, entropy_bits=nbytes*8, cryptographic=True,
                    encoded_sha256={"utf8":hashlib.sha256(generated.encode("utf-8")).hexdigest()}))
                token = generated[:10] if self.broken == "entropy_truncated" else generated
                csrf = secrets.token_urlsafe(32)
                db.execute("INSERT INTO sessions VALUES (?,?,?,?)", (hashlib.sha256(token.encode()).hexdigest(), account["id"], csrf, self.now + 28800))
                response = JSONResponse({"id": account["id"], "csrf_token": csrf})
                secure = request.url.scheme == "https" or not self.local_http_explicit
                response.set_cookie("fixture_session", token, httponly=True, samesite="lax", path="/", secure=False if self.broken == "SEC-05" else secure)
                if self.broken == "SEC-15":
                    self.logs.append(body.get("password", ""))
                return response

        @app.get("/api/auth/me")
        def me(request: Request):
            with self.connect() as db:
                actor, error = self.guard(request, db)
                return error if error else {"id": actor["id"], "role": actor["role"], "csrf_token": actor["csrf"]}

        @app.post("/api/auth/logout")
        def logout(request: Request):
            if request.headers.get("origin") != self.allowed_origin:
                return self.error("ORIGIN", 403)
            with self.connect() as db:
                actor = self.actor(request, db)
                if actor:
                    _, error = self.guard(request, db, mutate=True)
                    if error:
                        return error
                    if self.broken != "SEC-06":
                        db.execute("DELETE FROM sessions WHERE token_digest=?", (hashlib.sha256(request.cookies["fixture_session"].encode()).hexdigest(),))
            response = Response(status_code=204)
            response.delete_cookie("fixture_session", path="/")
            return response

        @app.get("/api/users")
        def list_users(request: Request):
            with self.connect() as db:
                actor, error = self.guard(request, db, admin=True)
                if error:
                    return error
                rows = [self.dto(row) for row in db.execute("SELECT * FROM users ORDER BY email_normalized,id")]
                return self.page(rows, request)

        @app.post("/api/users")
        def create_user(request: Request, body: dict):
            with self.connect() as db:
                actor, error = self.guard(request, db, mutate=True, admin=True)
                if error:
                    return error
                if set(body) != {"email", "password", "display_name", "role"} or not 14 <= len(body["password"]) <= 128:
                    return self.error("VALIDATION", 422)
                self.race("create_user", db)
                normalized = body["email"] if self.broken == "SEC-02" else body["email"].strip().lower()
                encoded = ("sha256:" + hashlib.sha256(body["password"].encode()).hexdigest() if self.broken == "SEC-03" else HASHER.hash(body["password"]))
                uid = str(uuid4())
                try:
                    db.execute("INSERT INTO users VALUES (?,?,?,?,?,?,1)", (uid, body["email"], normalized, body["display_name"], encoded, body["role"]))
                except sqlite3.IntegrityError:
                    return self.error("DUPLICATE_EMAIL", 409)
                return JSONResponse({"id": uid, "display_name": body["display_name"], "role": body["role"]}, status_code=201)

        @app.patch("/api/users/{uid}")
        def patch_user(uid: str, request: Request, body: dict):
            with self.connect() as db:
                actor, error = self.guard(request, db, mutate=True, admin=True)
                if error:
                    return error
                if set(body) != {"active"}:
                    if self.broken != "SEC-14":
                        return self.error("VALIDATION", 422)
                    for field in ["email", "role"]:
                        if field in body:
                            db.execute(f"UPDATE users SET {field}=? WHERE id=?", (body[field], uid))
                    return {"id": uid}
                old = db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
                if not old:
                    return self.error("USER_NOT_FOUND", 404)
                stale_count = db.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND active=1").fetchone()[0]
                self.race("deactivate_admin", db)
                db.execute("BEGIN IMMEDIATE")
                count = stale_count if self.broken == "SEC-13" else db.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND active=1").fetchone()[0]
                if old["role"] == "admin" and old["active"] and not body["active"] and count <= 1:
                    return self.error("LAST_ADMIN", 409)
                db.execute("UPDATE users SET active=? WHERE id=?", (int(body["active"]), uid))
                if not body["active"] and self.broken != "SEC-06":
                    db.execute("DELETE FROM sessions WHERE user_id=?", (uid,))
                return {"id": uid, "active": body["active"]}

        @app.get("/api/assignees")
        def assignees(request: Request):
            with self.connect() as db:
                actor, error = self.guard(request, db, staff=True)
                if error:
                    return error
                return self.page([{"id": r["id"], "display_name": r["display_name"]} for r in
                                  db.execute("SELECT * FROM users WHERE active=1 AND role IN ('agent','admin')")], request)

        @app.get("/api/tickets")
        def list_tickets(request: Request):
            if self.db_fault:
                status={"db_fault_502":502,"db_busy_503":503,"db_fault_success":200}.get(self.broken,500)
                if self.broken=="db_fault_html": return Response("opaque failure",status_code=status)
                code="DB_BUSY" if self.broken.startswith("db_busy_") else "DB_ERROR"
                return JSONResponse({"error": {"code": code, "message": "Traceback SELECT SECRET_SQL_PRIVATE_PATH" if self.broken == "SEC-15" else "Service indisponible"}}, status_code=status)
            with self.connect() as db:
                actor, error = self.guard(request, db)
                if error and self.broken != "SEC-08":
                    return error
                query, params = "SELECT * FROM tickets WHERE 1=1", []
                if actor and actor["role"] == "client" and self.broken != "SEC-09":
                    query += " AND owner_id=?"
                    params.append(actor["id"])
                q = request.query_params.get("q", "")
                if q:
                    query += " AND (instr(title,?)>0 OR instr(description,?)>0)"
                    params += [q, q]
                rows = [dict(r) for r in db.execute(query, params)]
                return self.page(rows, request)

        @app.post("/api/tickets")
        def create_ticket(request: Request, body: dict):
            with self.connect() as db:
                actor, error = self.guard(request, db, mutate=True)
                if error:
                    return error
                if actor["role"] != "client":
                    return self.error("FORBIDDEN", 403)
                if set(body) != {"title", "description", "client_request_id"} and self.broken != "SEC-11":
                    return self.error("VALIDATION", 422)
                tid = str(uuid4())
                db.execute("INSERT INTO tickets VALUES (?,?,?,?,1)", (tid, actor["id"], body["title"], body["description"]))
                return JSONResponse({"id": tid}, status_code=201)

        @app.get("/api/tickets/{tid}")
        def ticket(tid: str, request: Request):
            with self.connect() as db:
                actor, row, error = self.visible(request, db, tid)
                return error if error else dict(row)

        @app.patch("/api/tickets/{tid}")
        def patch_ticket(tid: str, request: Request, body: dict):
            with self.connect() as db:
                actor, row, error = self.visible(request, db, tid, mutate=True)
                if error:
                    return error
                return self.error("FORBIDDEN", 403) if actor["role"] == "client" else dict(row)

        @app.get("/api/tickets/{tid}/messages")
        def messages(tid: str, request: Request):
            with self.connect() as db:
                actor, row, error = self.visible(request, db, tid)
                if error:
                    return error
                rows = [dict(r) for r in db.execute("SELECT * FROM messages WHERE ticket_id=? ORDER BY rowid", (tid,))
                        if actor["role"] != "client" or r["visibility"] == "public" or self.broken == "SEC-10"]
                return self.page(rows, request)

        @app.post("/api/tickets/{tid}/messages")
        def create_message(tid: str, request: Request, body: dict):
            with self.connect() as db:
                actor, row, error = self.visible(request, db, tid, mutate=True)
                if error:
                    return error
                if set(body) != {"content", "visibility", "client_request_id"} and self.broken != "SEC-11":
                    return self.error("VALIDATION", 422)
                if actor["role"] == "client" and body["visibility"] == "internal":
                    return self.error("FORBIDDEN", 403)
                replay = db.execute("SELECT * FROM idempotency WHERE user_id=? AND key=?", (actor["id"], body["client_request_id"])).fetchone()
                if replay:
                    old = db.execute("SELECT * FROM messages WHERE id=?", (replay["object_id"],)).fetchone()
                    return dict(old)
                content = body["content"].replace("'", "").replace("<", "") if self.broken == "SEC-12" else body["content"]
                mid = str(uuid4())
                db.execute("INSERT INTO messages VALUES (?,?,?,?,?)", (mid, tid, actor["id"], content, body["visibility"]))
                db.execute("INSERT INTO events VALUES (?,?,?,?)", (str(uuid4()), tid, mid, body["visibility"]))
                db.execute("INSERT INTO idempotency VALUES (?,?,?,?)", (actor["id"], body["client_request_id"], tid, mid))
                return JSONResponse({"id": mid, "content": content, "visibility": body["visibility"]}, status_code=201)

        @app.get("/api/tickets/{tid}/history")
        def history(tid: str, request: Request):
            with self.connect() as db:
                actor, row, error = self.visible(request, db, tid)
                if error:
                    return error
                rows = [dict(r) for r in db.execute("SELECT * FROM events WHERE ticket_id=?", (tid,))
                        if actor["role"] != "client" or r["visibility"] == "public" or self.broken == "SEC-10"]
                return self.page(rows, request)

        @app.get("/api/dashboard")
        def dashboard(request: Request):
            with self.connect() as db:
                actor, error = self.guard(request, db)
                if error:
                    return error
                total = db.execute("SELECT COUNT(*) FROM tickets" + (" WHERE owner_id=?" if actor["role"] == "client" else ""),
                                   (actor["id"],) if actor["role"] == "client" else ()).fetchone()[0]
                return {"total": total}

        return app

    def visible(self, request, db, tid, mutate=False):
        actor, error = self.guard(request, db, mutate=mutate)
        if error:
            return actor, None, error
        row = db.execute("SELECT * FROM tickets WHERE id=?", (tid,)).fetchone()
        if not row or actor["role"] == "client" and row["owner_id"] != actor["id"] and self.broken != "SEC-09":
            return actor, None, self.error("TICKET_NOT_FOUND", 404)
        return actor, row, None

    def page(self, rows, request):
        size = int(request.query_params.get("page_size", 20))
        page = int(request.query_params.get("page", 1))
        return {"items": rows[(page - 1) * size:page * size], "total": len(rows), "page": page, "page_size": size}

    def dto(self, row):
        return {k: row[k] for k in ["id", "email", "display_name", "role", "active"]}

    def rows(self, tables):
        with self.connect() as db:
            return {table: [dict(r) for r in db.execute(f"SELECT * FROM {table} ORDER BY rowid")] for table in tables}

    async def observe(self, name, **params):
        if name == "route_inventory":
            return [{"path": route.path, "method": method, "business": True}
                    for route in self.app.routes if getattr(route, "path", "").startswith("/api/") and
                    not route.path.startswith("/api/auth/") for method in route.methods
                    if "{" not in route.path] + [
                        {"path": f"/api/tickets/{self.manifest.tickets['alice']}" + suffix, "method": "GET", "business": True}
                        for suffix in ["", "/messages", "/history"]]
        with self.connect() as db:
            if name == "account_count":
                return db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            if name == "account_fingerprints":
                return [hashlib.sha256(r["password_hash"].encode()).hexdigest() for r in db.execute("SELECT password_hash FROM users ORDER BY id")]
            if name in ["business_state", "security_state", "snapshot"]:
                tables = ["users", "tickets", "messages", "events", "idempotency"] + (["sessions"] if name == "security_state" else [])
                return hashlib.sha256(json.dumps(self.rows(tables), sort_keys=True).encode()).hexdigest()
            if name == "email_count":
                return db.execute("SELECT COUNT(*) FROM users WHERE lower(trim(email))=?", (params["email"],)).fetchone()[0]
            if name == "email_unique_constraint":
                return any(index["unique"] and
                           [column["name"] for column in db.execute("PRAGMA index_info(" + index["name"] + ")")] == ["email_normalized"]
                           for index in db.execute("PRAGMA index_list(users)"))
            if name == "password_hashes":
                return [db.execute("SELECT password_hash FROM users WHERE email_normalized=?", (email,)).fetchone()[0] for email in params["emails"]]
            if name == "dummy_hash_verifications":
                return self.dummy_count
            if name == "session_storage":
                return [{"stored": r[0]} for r in db.execute("SELECT token_digest FROM sessions WHERE token_digest=?", (hashlib.sha256(params["token"].encode()).hexdigest(),))]
            if name == "active_admin_count":
                return db.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND active=1").fetchone()[0]
            if name == "race_connections":
                return [str(item) for item in self.race_connections]
            if name == "business_counts":
                return {table: db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in ["tickets", "messages", "events"]}
            if name == "essential_tables_present":
                return {"users", "sessions", "tickets", "messages", "events", "idempotency"} <= {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if name == "secret_scan":
                path = self.root / "logs.txt"
                path.write_text("\n".join(self.logs), encoding="utf-8")
                return {"findings": ["raw secret in isolated log"] if any(p in path.read_text(encoding="utf-8") for p in PASSWORDS.values()) else [],
                        "scopes": ["logs", "artifacts"],
                        "artifacts": [{"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}]}
        if name == "cookie_modes":
            modes = []
            for mode, scheme, explicit in [("https", "https", False), ("http_local_explicit", "http", True), ("http_without_exception", "http", False)]:
                self.local_http_explicit = explicit
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url=scheme + "://localhost") as client:
                    r = await client.post("/api/auth/login", json={"email": self.manifest.accounts["alice"].email, "password": PASSWORDS["alice"]}, headers={"Origin": "https://localhost"})
                    modes.append({"mode": mode, "secure": "secure" in r.headers.get("set-cookie", "").lower()})
            self.local_http_explicit = True
            return modes
        raise ValueError("unknown independent observation " + name)

    async def command(self, action, **params):
        if action == "register_actor":
            self.manifest.accounts[params["actor"]] = FixtureAccount(params["id"], params["email"], params["password"], params["role"])
            return {"exit_code": 0}
        with self.connect() as db:
            if action == "bootstrap":
                credentials = params.get("credentials")
                if not credentials or db.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()[0]:
                    return {"exit_code": 1}
                self._insert_user(db, self.manifest.accounts["admin"])
                return {"exit_code": 0}
            if action == "seed":
                if not params.get("demo") or not params.get("credentials"):
                    return {"exit_code": 1}
                for actor, account in self.manifest.accounts.items():
                    existing = db.execute("SELECT id FROM users WHERE email_normalized=?", (account.email.strip().lower(),)).fetchone()
                    if existing and existing["id"] != account.id:
                        return {"exit_code": 1}
                    if not existing:
                        self._insert_user(db, account, BASE_HASHES[actor])
                return {"exit_code": 0}
            if action == "seed_collision":
                # External fixture preparation: replace a demo identity, then run
                # the very same seed command against this real DB collision.
                account = self.manifest.accounts["alice"]
                db.execute("UPDATE users SET id=? WHERE email_normalized=?", (str(uuid4()), account.email.strip().lower()))
                db.commit()
        if action == "seed_collision":
            before = await self.observe("business_state")
            result = await self.command("seed", demo=True, credentials=True)
            return result | {"preserved": before == await self.observe("business_state")}
        raise ValueError("unknown harness action")

    async def clock(self, seconds):
        self.now += seconds

    async def arm_race(self, point, parties):
        self.race_point, self.barrier = point, threading.Barrier(parties)
        self.race_connections = []

    async def fault(self, point, enabled):
        assert point == "db_read"
        self.db_fault = enabled

    def adapter(self, contract, *, reviews=True, base_url="https://localhost", real_http=False):
        store = ContractStore(self.root.parent / "independent-oracles", product_write_roots=[self.root])
        oracle = store.save(contract)
        snapshot = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        async def attest_snapshot():
            return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        async def attest_contract():
            return store.load(oracle).contract_hash
        async def evidence(rid):
            if not reviews:
                return []
            path = self.root.parent / "review-proofs" / (rid + ".json")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"requirement": rid, "fixture_source": str(Path(__file__).resolve()),
                "fixture_source_hash": snapshot, "symbol": "SecurityApplication._app", "scope": "oracle-fixture validation only, not product acceptance"}), encoding="utf-8")
            return [Proof("R", str(path), hashlib.sha256(path.read_bytes()).hexdigest(), snapshot, contract.contract_hash,
                          (rid,"SEC-05:entropy") if rid=="SEC-05" else (rid,),
                          detail="Source-linked fixture proof; independent product review still required for campaign")]
        async def observations(name, **params):
            if name != "session_entropy": return await self.observe(name, **params)
            if self.broken == "entropy_missing": raise AdapterUnavailable("native capability intentionally absent")
            value=correlate_entropy(self.entropy_records,params.get("token_sha256"))
            native=entropy_execution_proof(self.root.parent/"execution-proofs",value,snapshot,contract.contract_hash)
            if self.broken == "entropy_forged": value["entropy_bits"]=4096
            return {**value,"proofs":[asdict(native),*[asdict(p) for p in await evidence("SEC-05")]]}
        self.allowed_origin = base_url
        adapter = HttpxSupportAdapter(base_url=base_url, auth_path="/api/auth/login", origin=self.allowed_origin,
            csrf_field="csrf_token", evidence_root=self.root.parent / "execution-proofs", prepare=self.prepare,
            observe=observations, snapshot=attest_snapshot, oracle=attest_contract, command=self.command, clock=self.clock,
            proofs=evidence, race=self.arm_race, fault=self.fault, db_connect=self.connect,
            transport_factory=None if real_http else lambda ip: httpx.ASGITransport(app=self.app, client=(ip, 12345), raise_app_exceptions=False))
        return adapter, snapshot, oracle
