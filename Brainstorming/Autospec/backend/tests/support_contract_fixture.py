"""Small real FastAPI/SQLite subject for independent pack meta-tests.

It is a harness-owned fixture, not the generated support product. Deliberate
faults are configuration before startup, never shipped debug HTTP routes.
Auth verifies randomly generated credentials against PBKDF2, then uses genuine
cookie sessions stored as token digests. All mutation connections are distinct.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import secrets
import shutil
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from autospec.validation.support_adapter import (
    AdapterUnavailable, FixtureAccount, FixtureManifest, HttpxSupportAdapter,
)

STATES=("open","in_progress","resolved","closed")
TRANSITIONS={("open","in_progress"),("in_progress","open"),("in_progress","resolved"),
             ("resolved","in_progress"),("resolved","closed")}


def retain_fixture_report(report,subject):
    """Optional supervisor-selected export: JSON only, never DB/credentials.

    Reports are explicitly fixture meta-tests, not product campaign verdicts.
    Proof bytes are copied unmodified and their SHA remains verifiable.
    """
    selected=os.environ.get("AUTOSPEC_CONTRACT_FIXTURE_EVIDENCE_ROOT")
    if not selected: return
    rem="REM-16" if report["pack"]=="business" else "REM-17"
    target=Path(selected).resolve()/rem/"fixtures"/subject.root.name
    target.mkdir(parents=True,exist_ok=True)
    result=json.loads(json.dumps(report))
    for requirement in result["requirements"]:
        for proof in requirement["proofs"]:
            source=Path(proof["path"])
            if source.suffix!=".json" or subject.root.resolve() not in source.resolve().parents:
                raise ValueError("only native temporary fixture JSON may be exported")
            destination=target/source.name
            shutil.copyfile(source,destination); proof["path"]=str(destination)
    result["kind"]="independent-pack fixture meta-test, not generated-product conformity"
    result["fixture_fault"]=subject.bug
    (target/"report.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")


class SubjectError(Exception):
    def __init__(self,status,code): self.status,self.code=status,code


class SQLiteSupportSubject:
    def __init__(self, root: Path, contract, bug: str=""):
        self.root=root; root.mkdir(parents=True,exist_ok=True)
        self.db=root/"subject.sqlite"; self.contract=contract; self.bug=bug
        self.snapshot="a"*64; self.now=1800000000.; self.fail_audit=False
        self.trace=[]; self.trace_enabled=False; self.connection_count=0; self.lock=threading.Lock()
        self.race=None; self.race_ids=[]; self.winner=None; self.manifest=FixtureManifest()
        self.app_connections=[]
        self.credentials={}; self._create_schema(); self.app=FastAPI()
        self._routes()
        async def snapshot(): return self.snapshot
        async def oracle(): return self.contract.contract_hash
        self.adapter=HttpxSupportAdapter(base_url="http://127.0.0.1",auth_path="/api/auth/login",
            origin="http://127.0.0.1",csrf_field="csrf_token",evidence_root=root/"proofs",
            prepare=self.prepare,observe=self.observe,snapshot=snapshot,oracle=oracle,command=self.command,
            race=self.arm_race,clock=self.clock,restart=self.restart,fault=self.fault,db_connect=self.connect,
            transport_factory=lambda ip:httpx.ASGITransport(app=self.app,client=(ip,1234),raise_app_exceptions=False))

    def connect(self):
        con=sqlite3.connect(self.db,timeout=.08,check_same_thread=False)
        con.execute("PRAGMA foreign_keys=ON"); con.row_factory=sqlite3.Row
        with self.lock: self.connection_count+=1
        if self.trace_enabled: con.set_trace_callback(self.trace.append)
        return con

    def _create_schema(self):
        con=self.connect()
        null="" if self.bug=="null_id" else "NOT NULL"
        integer="" if self.bug=="fractional_version" else "AND typeof(version)='integer'"
        con.executescript(f"""
        CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY {null},email TEXT NOT NULL,
          email_normalized TEXT NOT NULL UNIQUE,password_hash TEXT NOT NULL,
          role TEXT NOT NULL CHECK(role IN ('client','agent','admin')),active INTEGER NOT NULL CHECK(active IN(0,1)));
        CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY NOT NULL,user_id TEXT NOT NULL REFERENCES users(id),
          csrf TEXT NOT NULL,expires REAL NOT NULL,revoked INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS tickets(id TEXT PRIMARY KEY {null},owner_id TEXT NOT NULL REFERENCES users(id),
          title TEXT NOT NULL,description TEXT NOT NULL,status TEXT NOT NULL CHECK(status IN('open','in_progress','resolved','closed')),
          priority TEXT NOT NULL CHECK(priority IN('low','normal','high')),assignee_id TEXT REFERENCES users(id),
          version INTEGER NOT NULL CHECK(version>=1 {integer}),created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY NOT NULL,ticket_id TEXT NOT NULL REFERENCES tickets(id),
          author_id TEXT NOT NULL REFERENCES users(id),content TEXT NOT NULL,visibility TEXT NOT NULL CHECK(visibility IN('public','internal')),
          created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS ticket_events(id INTEGER PRIMARY KEY,ticket_id TEXT NOT NULL REFERENCES tickets(id),
          actor_id TEXT NOT NULL REFERENCES users(id),type TEXT NOT NULL,before_json TEXT NOT NULL,after_json TEXT NOT NULL,
          created_at TEXT NOT NULL,visibility TEXT NOT NULL DEFAULT 'public');
        CREATE TABLE IF NOT EXISTS idempotency_keys(user_id TEXT NOT NULL REFERENCES users(id),kind TEXT NOT NULL,
          key TEXT NOT NULL,payload TEXT NOT NULL,response TEXT NOT NULL,PRIMARY KEY(user_id,kind,key));
        CREATE INDEX IF NOT EXISTS ticket_list ON tickets(updated_at DESC,id DESC);
        CREATE INDEX IF NOT EXISTS message_list ON messages(ticket_id,created_at,id);
        PRAGMA user_version=1;
        """)
        con.close()

    def timestamp(self): return datetime.fromtimestamp(self.now,timezone.utc).isoformat()

    @staticmethod
    def password_hash(password,salt):
        return salt+":"+hashlib.pbkdf2_hmac("sha256",password.encode(),bytes.fromhex(salt),1000).hex()

    async def prepare(self,case_id,**options):
        self.now=1800000000.; self.race=None; self.race_ids=[]; self.winner=None; self.fail_audit=False
        self.app_connections=[]
        con=self.connect()
        for table in ("idempotency_keys","ticket_events","messages","tickets","sessions","users"):
            con.execute(f"DELETE FROM {table}")
        accounts={}
        for index,(name,role) in enumerate((("alice","client"),("bob","client"),("camille","agent"),("dylan","agent"),("emma","admin")),1):
            password=secrets.token_urlsafe(24); email=name+"@example.test"; uid=str(UUID(int=index))
            accounts[name]=FixtureAccount(uid,email,password,role)
            con.execute("INSERT INTO users VALUES(?,?,?,?,?,1)",(uid,email,email,self.password_hash(password,secrets.token_hex(16)),role))
        tickets={}; all_rows=[]
        n=options.get("query_count",61 if options.get("pagination_scenario") else 12)
        for i in range(n):
            tid=str(UUID(int=100+i)); owner=accounts["alice" if i<6 else "bob"].id
            status=STATES[i%4]; priority=("normal","high","low")[i%3]
            assignee=accounts["camille"].id if i%2==0 else None
            if i==0:
                status=options.get("status","open"); priority="normal"
                assignee=accounts["camille"].id if options.get("assigned",True) else None
            if options.get("disable_scenario") and i in (0,2,3): assignee=accounts["camille"].id
            timestamp=self.timestamp(); title=f"Ticket {i:03d}"; description=f"Description fixture ticket {i:03d}"
            if options.get("search_scenario"):
                title=["ASCII marker shared","Unicode Éclair","Literal % only","Literal _ only","Literal ' only","Last shared"][i%6]
                if i>=6: title+=" Bob"
            con.execute("INSERT INTO tickets VALUES(?,?,?,?,?,?,?,?,?,?)",(tid,owner,title,description,status,priority,assignee,1,timestamp,timestamp))
            all_rows.append(dict(id=tid,owner_id=owner,status=status,priority=priority,assignee_id=assignee,title=title,description=description))
            if i==0: tickets["alice_open"]=tid
            if i==1: tickets["alice_second"]=tid
            if i==6: tickets["bob_resolved"]=tid
        for option,actor,visibility in (("public_staff_reply","camille","public"),("internal_reply","camille","internal"),("client_reply","alice","public")):
            if options.get(option):
                con.execute("INSERT INTO messages VALUES(?,?,?,?,?,?)",(str(uuid4()),tickets["alice_open"],accounts[actor].id,"Fixture reply",visibility,self.timestamp()))
        # A seed key exercises actual DB duplicate constraints, not an empty-table inference.
        con.execute("INSERT INTO idempotency_keys VALUES(?,?,?,?,?)",(accounts["alice"].id,"fixture",str(uuid4()),"{}","{}"))
        if options.get("search_scenario"):
            con.execute("INSERT INTO messages VALUES(?,?,?,?,?,?)",(str(uuid4()),tickets["alice_open"],accounts["camille"].id,"INTERNAL_ONLY","internal",self.timestamp()))
        con.commit(); con.close()
        metadata={"dashboard_expected":{},"independent_fixture":True}
        for actor in ("alice","camille"):
            rows=all_rows if actor=="camille" else [r for r in all_rows if r["owner_id"]==accounts[actor].id]
            metadata["dashboard_expected"][actor]={"total":len(rows),**{s:sum(r["status"]==s for r in rows) for s in STATES}}
        metadata["pagination_expected"]=sorted([r["id"] for r in all_rows],reverse=True)
        metadata["tie_expected"]=metadata["pagination_expected"].copy()
        metadata["filter_expected"]=[(p,[r["id"] for r in reversed(all_rows) if all(r[k]==v for k,v in p.items())])
            for p in ({"status":"open","priority":"normal"},{"status":"in_progress","priority":"high"})]
        metadata["filter_expected"] += [({"status":"open","assigned_to_me":True},[r["id"] for r in reversed(all_rows)
            if r["status"]=="open" and r["assignee_id"]==accounts["camille"].id]),
            ({"priority":"high","unassigned":True},[r["id"] for r in reversed(all_rows) if r["priority"]=="high" and r["assignee_id"] is None])]
        metadata["search_expected"]={
            "ascii":[str(UUID(int=100))],"Éclair":[str(UUID(int=101))],"éclair":[],
            "%":[str(UUID(int=102))],"_":[str(UUID(int=103))],"'":[str(UUID(int=104))],
            "INTERNAL_ONLY":[],"shared":[str(UUID(int=100)),str(UUID(int=105))]}
        self.manifest=FixtureManifest(accounts,tickets,metadata)
        return self.manifest

    def ticket_state_sync(self,con,ticket_id):
        row=con.execute("SELECT * FROM tickets WHERE id=?",(ticket_id,)).fetchone()
        if row is None: raise SubjectError(404,"NOT_FOUND")
        data=dict(row)
        data["audit_count"]=con.execute("SELECT count(*) FROM ticket_events WHERE ticket_id=?",(ticket_id,)).fetchone()[0]
        data["message_count"]=con.execute("SELECT count(*) FROM messages WHERE ticket_id=?",(ticket_id,)).fetchone()[0]
        return data

    async def observe(self,name,**params):
        con=self.connect()
        try:
            if name in ("business_state","snapshot","full_database_state"):
                tables=("users","tickets","messages","ticket_events","idempotency_keys") if name!="full_database_state" else (
                    "users","tickets","messages","ticket_events","idempotency_keys","sessions")
                return {table:[tuple(r) for r in con.execute(f"SELECT * FROM {table} ORDER BY rowid")] for table in tables}
            if name=="ticket_state": return self.ticket_state_sync(con,params["ticket_id"])
            if name=="race_connections": return self.race_ids.copy()
            if name=="app_connection_pragmas": return self.app_connections.copy()
            if name=="db_busy_timeout_ms": return con.execute("PRAGMA busy_timeout").fetchone()[0]
            if name=="sql_trace": self.trace_enabled=False; return self.trace.copy()
            if name=="query_plan": return [tuple(r) for r in con.execute("EXPLAIN QUERY PLAN SELECT * FROM tickets ORDER BY updated_at DESC,id DESC LIMIT 50")]
            if name=="inactive_assignments": return [dict(r) for r in con.execute("SELECT tickets.* FROM tickets JOIN users ON users.id=tickets.assignee_id WHERE users.active=0")]
            if name=="assigned_tickets":
                ids=[r[0] for r in con.execute("SELECT id FROM tickets WHERE assignee_id=?",(self.manifest.accounts[params["actor"]].id,))]
                return [self.ticket_state_sync(con,i) for i in ids]
            if name=="tickets_by_ids": return [self.ticket_state_sync(con,i) for i in params["ids"]]
            raise AdapterUnavailable(f"fixture observation unsupported: {name}")
        finally: con.close()

    async def command(self,action,**params):
        con=self.connect()
        try:
            if action=="deactivate_fixture_account": con.execute("UPDATE users SET active=0 WHERE id=?",(self.manifest.accounts[params["actor"]].id,))
            elif action=="close_fixture_ticket": con.execute("UPDATE tickets SET status='closed' WHERE id=?",(params["ticket_id"],))
            elif action=="schedule_race_winner": self.winner=params["winner"]
            elif action=="sql_trace_start": self.trace=[]; self.trace_enabled=True
            elif action in ("migrate_fresh","migrate_replay"):
                if action=="migrate_fresh":
                    # An actually new SQLite file, not DELETE on an existing schema.
                    self.db=self.root/("migration-"+str(uuid4())+".sqlite")
                self._create_schema()
                if action=="migrate_replay" and self.bug=="migration_reset":
                    con.execute("UPDATE tickets SET title='Lost data'")
            elif action=="populate_migration_fixture":
                await self.prepare("migration")
            else: raise AdapterUnavailable(f"fixture command unsupported: {action}")
            con.commit(); return {"exit_code":0,"command":action,"fixture_only":True}
        finally: con.close()

    async def clock(self,seconds): self.now+=seconds
    async def fault(self,point,enabled):
        if point!="after_business_before_audit": raise AdapterUnavailable("fault point unsupported")
        self.fail_audit=enabled
    async def restart(self):
        # Replace the actual application instance; preserve SQLite file/session data.
        self.app=FastAPI(); self._routes()
        await self.adapter.close()
    async def arm_race(self,point,parties):
        self.race={"point":point,"parties":parties,"arrived":0,"start":asyncio.Event(),"done":asyncio.Event()}; self.race_ids=[]

    async def join_race(self,action):
        race=self.race
        eligible={"ticket_patch":{"patch"},"ticket_create":{"create"},"message_create":{"message"},"close_message":{"close","message"},"assign_disable":{"patch","disable"}}
        if not race or action not in eligible.get(race["point"],set()): return None
        self.race_ids.append(self.connection_count); race["arrived"]+=1
        if race["arrived"]>=race["parties"]: race["start"].set()
        await asyncio.wait_for(race["start"].wait(),3)
        if race["point"]=="close_message" and action!=self.winner:
            await asyncio.wait_for(race["done"].wait(),3)
        return race

    def auth(self,request,con):
        token=request.cookies.get("session",""); token_hash=hashlib.sha256(token.encode()).hexdigest()
        row=con.execute("SELECT users.*,sessions.csrf,sessions.expires,sessions.revoked FROM sessions JOIN users ON users.id=sessions.user_id WHERE token_hash=?",(token_hash,)).fetchone()
        if row is None or row["revoked"] or not row["active"] or row["expires"]<=self.now: raise SubjectError(401,"UNAUTHENTICATED")
        if request.method not in ("GET","HEAD") and (request.headers.get("Origin")!="http://127.0.0.1" or request.headers.get("X-CSRF-Token")!=row["csrf"]):
            raise SubjectError(403,"FORBIDDEN")
        return dict(row)

    def ticket_visible(self,con,actor,ticket_id):
        ticket=con.execute("SELECT * FROM tickets WHERE id=?",(ticket_id,)).fetchone()
        if not ticket or actor["role"]=="client" and ticket["owner_id"]!=actor["id"]: raise SubjectError(404,"NOT_FOUND")
        return dict(ticket)

    def audit(self,con,ticket_id,actor,kind,before,after,visibility="public"):
        if self.fail_audit: raise RuntimeError("controlled trusted fixture audit failure")
        con.execute("INSERT INTO ticket_events(ticket_id,actor_id,type,before_json,after_json,created_at,visibility) VALUES(?,?,?,?,?,?,?)",
                    (ticket_id,actor["id"],kind,json.dumps(before),json.dumps(after),self.timestamp(),visibility))

    def replay(self,con,actor,kind,payload):
        key=payload.get("client_request_id")
        try: UUID(key)
        except (TypeError,ValueError,AttributeError): raise SubjectError(422,"VALIDATION_ERROR")
        normal=json.dumps({k:(v.strip() if isinstance(v,str) else v) for k,v in payload.items() if k!="client_request_id"},sort_keys=True)
        old=con.execute("SELECT * FROM idempotency_keys WHERE user_id=? AND kind=? AND key=?",(actor["id"],kind,key)).fetchone()
        if old:
            if old["payload"]!=normal: raise SubjectError(409,"IDEMPOTENCY_CONFLICT")
            return normal,json.loads(old["response"])
        return normal,None

    def save_key(self,con,actor,kind,payload,normal,response):
        con.execute("INSERT INTO idempotency_keys VALUES(?,?,?,?,?)",(actor["id"],kind,payload["client_request_id"],normal,json.dumps(response)))

    def mutate(self,con,actor,action,payload,ticket_id=None,user_id=None):
        con.execute("BEGIN IMMEDIATE")
        if action=="create":
            if actor["role"]!="client" and self.bug!="agent_creation": raise SubjectError(403,"FORBIDDEN")
            if set(payload)!={"title","description","client_request_id"}: raise SubjectError(422,"VALIDATION_ERROR")
            title=payload["title"].strip(); description=payload["description"].strip()
            if not 5<=len(title)<=120 or not 20<=len(description)<=5000: raise SubjectError(422,"VALIDATION_ERROR")
            normal,old=self.replay(con,actor,"ticket",payload)
            if old: return old,200
            tid=str(uuid4()); con.execute("INSERT INTO tickets VALUES(?,?,?,?,?,?,?,?,?,?)",(tid,actor["id"],title,description,"open","normal",None,1,self.timestamp(),self.timestamp()))
            response=dict(con.execute("SELECT * FROM tickets WHERE id=?",(tid,)).fetchone())
            self.audit(con,tid,actor,"created",{},response); self.save_key(con,actor,"ticket",payload,normal,response)
            return response,201
        if action=="disable":
            if actor["role"]!="admin": raise SubjectError(403,"FORBIDDEN")
            if set(payload)!={"active"} or type(payload["active"]) is not bool: raise SubjectError(422,"VALIDATION_ERROR")
            user=con.execute("SELECT * FROM users WHERE id=?",(user_id,)).fetchone()
            if not user: raise SubjectError(404,"NOT_FOUND")
            con.execute("UPDATE users SET active=? WHERE id=?",(int(payload["active"]),user_id))
            if not payload["active"]:
                con.execute("UPDATE sessions SET revoked=1 WHERE user_id=?",(user_id,))
                rows=con.execute("SELECT * FROM tickets WHERE assignee_id=?",(user_id,)).fetchall()
                for row in rows:
                    before=dict(row); after={**before,"assignee_id":None,"version":before["version"]+1,"updated_at":self.timestamp()}
                    con.execute("UPDATE tickets SET assignee_id=NULL,version=version+1,updated_at=? WHERE id=?",(self.timestamp(),row["id"]))
                    self.audit(con,row["id"],actor,"unassigned",before,after)
            return {"id":user_id,"active":payload["active"]},200
        ticket=self.ticket_visible(con,actor,ticket_id)
        if action in ("patch","close"):
            if actor["role"]=="client": raise SubjectError(403,"FORBIDDEN")
            if not set(payload)<={"priority","status","assignee_id","expected_version"} or not set(payload)&{"priority","status","assignee_id"} or type(payload.get("expected_version")) is not int or payload["expected_version"]<1:
                raise SubjectError(422,"VALIDATION_ERROR")
            if payload["expected_version"]!=ticket["version"]: raise SubjectError(409,"VERSION_CONFLICT")
            after={**ticket,**{k:v for k,v in payload.items() if k!="expected_version"}}
            if after["priority"] not in ("low","normal","high") or after["status"] not in STATES: raise SubjectError(422,"VALIDATION_ERROR")
            if after["assignee_id"]:
                assigned=con.execute("SELECT role,active FROM users WHERE id=?",(after["assignee_id"],)).fetchone()
                if assigned is None or assigned["role"]=="client" or not assigned["active"]: raise SubjectError(422,"VALIDATION_ERROR")
            if "assignee_id" in payload and (ticket["status"]=="closed" or after["status"]=="closed") and after["assignee_id"]!=ticket["assignee_id"]:
                raise SubjectError(409,"INVALID_TRANSITION")
            if ticket["status"]!=after["status"]:
                pair=(ticket["status"],after["status"])
                if pair not in TRANSITIONS and not (self.bug=="open_resolved" and pair==("open","resolved")): raise SubjectError(409,"INVALID_TRANSITION")
                if after["status"]=="in_progress" and not after["assignee_id"]: raise SubjectError(409,"INVALID_TRANSITION")
                if after["status"]=="resolved" and not con.execute("SELECT 1 FROM messages JOIN users ON users.id=messages.author_id WHERE ticket_id=? AND visibility='public' AND role IN('agent','admin')",(ticket_id,)).fetchone():
                    raise SubjectError(409,"INVALID_TRANSITION")
            if after==ticket: return ticket,200
            after["version"]+=1; after["updated_at"]=self.timestamp()
            con.execute("UPDATE tickets SET priority=?,status=?,assignee_id=?,version=?,updated_at=? WHERE id=?",(after["priority"],after["status"],after["assignee_id"],after["version"],after["updated_at"],ticket_id))
            self.audit(con,ticket_id,actor,"updated",ticket,after)
            return after,200
        if action=="message":
            if set(payload)!={"content","visibility","client_request_id"}: raise SubjectError(422,"VALIDATION_ERROR")
            visibility=payload["visibility"]; content=payload["content"].strip()
            if visibility=="internal" and actor["role"]=="client": raise SubjectError(403,"FORBIDDEN")
            if visibility not in ("public","internal") or not 1<=len(content)<=5000: raise SubjectError(422,"VALIDATION_ERROR")
            keyed={**payload,"ticket_id":ticket_id}; normal,old=self.replay(con,actor,"message",keyed)
            if old: return old,200
            if ticket["status"]=="closed": raise SubjectError(409,"TICKET_CLOSED")
            mid=str(uuid4()); response=dict(id=mid,ticket_id=ticket_id,author_id=actor["id"],content=content,visibility=visibility,created_at=self.timestamp())
            con.execute("INSERT INTO messages VALUES(?,?,?,?,?,?)",tuple(response[k] for k in ("id","ticket_id","author_id","content","visibility","created_at")))
            con.execute("UPDATE tickets SET version=version+1,updated_at=? WHERE id=?",(self.timestamp(),ticket_id))
            self.audit(con,ticket_id,actor,"message",{},dict(message_id=mid,visibility=visibility),visibility)
            self.save_key(con,actor,"message",keyed,normal,response)
            return response,201
        raise SubjectError(404,"NOT_FOUND")

    @staticmethod
    def pagination(request):
        try: page=int(request.query_params.get("page",1)); size=int(request.query_params.get("page_size",20))
        except ValueError: raise SubjectError(422,"VALIDATION_ERROR")
        if page<1 or not 1<=size<=50: raise SubjectError(422,"VALIDATION_ERROR")
        return page,size

    def read(self,con,actor,request,path,ticket_id=None):
        page,size=self.pagination(request)
        if path=="me": return {"id":actor["id"],"role":actor["role"]}
        if path in ("users","assignees"):
            if actor["role"]=="client" or path=="users" and actor["role"]!="admin": raise SubjectError(403,"FORBIDDEN")
            rows=[dict(id=r["id"],email=r["email"],email_normalized=r["email_normalized"],role=r["role"],active=bool(r["active"])) for r in con.execute("SELECT * FROM users ORDER BY email_normalized,id")]
            if path=="assignees": rows=[r for r in rows if r["role"]!="client" and r["active"]]
        elif path in ("tickets","dashboard"):
            rows=[dict(r) for r in con.execute("SELECT * FROM tickets ORDER BY updated_at DESC,id DESC")]
            if actor["role"]=="client": rows=[r for r in rows if r["owner_id"]==actor["id"]]
            if path=="dashboard": return {"total":len(rows),**{s:sum(r["status"]==s for r in rows) for s in STATES}}
            q=request.query_params.get("q","")
            if len(q)>100: raise SubjectError(422,"VALIDATION_ERROR")
            lower=lambda s:s.translate(str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ","abcdefghijklmnopqrstuvwxyz"))
            rows=[r for r in rows if lower(q) in lower(r["title"]+" "+r["description"])]
            mine=request.query_params.get("assigned_to_me")=="true"; unassigned=request.query_params.get("unassigned")=="true"
            if mine and unassigned: raise SubjectError(422,"VALIDATION_ERROR")
            if (mine or unassigned) and actor["role"]=="client": raise SubjectError(403,"FORBIDDEN")
            if self.bug!="ignored_filters":
                for field in ("status","priority"):
                    if field in request.query_params: rows=[r for r in rows if r[field]==request.query_params[field]]
                if mine: rows=[r for r in rows if r["assignee_id"]==actor["id"]]
                if unassigned: rows=[r for r in rows if r["assignee_id"] is None]
            if self.bug=="n_plus_one":
                for row in rows: con.execute("SELECT id FROM messages WHERE ticket_id=?",(row["id"],)).fetchall()
        elif path=="detail": return self.ticket_visible(con,actor,ticket_id)
        else:
            self.ticket_visible(con,actor,ticket_id)
            table="messages" if path=="messages" else "ticket_events"
            rows=[dict(r) for r in con.execute(f"SELECT * FROM {table} WHERE ticket_id=? ORDER BY created_at,id",(ticket_id,))]
            if actor["role"]=="client": rows=[r for r in rows if r["visibility"]=="public"]
            if path=="history":
                for row in rows: row["before"]=json.loads(row.pop("before_json")); row["after"]=json.loads(row.pop("after_json"))
        return {"items":rows[(page-1)*size:page*size],"total":len(rows),"page":page,"page_size":size}

    def _routes(self):
        @self.app.exception_handler(SubjectError)
        async def subject_error(request,exc): return JSONResponse({"error":{"code":exc.code,"message":"Requête refusée"}},status_code=exc.status)
        @self.app.post("/api/auth/login")
        async def login(request:Request):
            if request.headers.get("Origin")!="http://127.0.0.1": raise SubjectError(403,"FORBIDDEN")
            data=await request.json(); con=self.connect()
            try:
                row=con.execute("SELECT * FROM users WHERE email_normalized=?",(data.get("email","").strip().lower(),)).fetchone()
                if row is None or not row["active"]: raise SubjectError(401,"UNAUTHENTICATED")
                salt=row["password_hash"].split(":")[0]
                if not hmac.compare_digest(self.password_hash(data.get("password",""),salt),row["password_hash"]): raise SubjectError(401,"UNAUTHENTICATED")
                token=secrets.token_urlsafe(32); csrf=secrets.token_urlsafe(32)
                con.execute("INSERT INTO sessions VALUES(?,?,?,?,0)",(hashlib.sha256(token.encode()).hexdigest(),row["id"],csrf,self.now+28800)); con.commit()
                response=JSONResponse({"csrf_token":csrf}); response.set_cookie("session",token,httponly=True,samesite="strict",path="/")
                return response
            finally: con.close()
        @self.app.post("/api/auth/logout")
        async def logout(request:Request): return JSONResponse({},status_code=204)
        async def endpoint(path:str,request:Request):
            con=self.connect(); race=None; action=None
            if self.bug=="app_foreign_keys_off": con.execute("PRAGMA foreign_keys=OFF")
            self.app_connections.append({"connection_id":self.connection_count,"foreign_keys":con.execute("PRAGMA foreign_keys").fetchone()[0],
                                         "busy_timeout_ms":con.execute("PRAGMA busy_timeout").fetchone()[0]})
            try:
                actor=self.auth(request,con); parts=path.split("/"); ticket_id=parts[1] if len(parts)>1 else None
                if request.method=="GET":
                    selected="me" if path=="auth/me" else parts[0] if len(parts)==1 else "detail" if len(parts)==2 else parts[2]
                    return self.read(con,actor,request,selected,ticket_id)
                payload=await request.json()
                if path=="tickets" and request.method=="POST": action="create"
                elif parts[0]=="tickets" and len(parts)==2 and request.method=="PATCH": action="close" if payload.get("status")=="closed" else "patch"
                elif parts[0]=="tickets" and len(parts)==3 and parts[2]=="messages" and request.method=="POST": action="message"
                elif parts[0]=="users" and len(parts)==2 and request.method=="PATCH": action="disable"
                else: raise SubjectError(404,"NOT_FOUND")
                race=await self.join_race(action)
                def transaction():
                    try:
                        value,status=self.mutate(con,actor,action,payload,ticket_id,ticket_id)
                        con.commit(); return value,status
                    except BaseException: con.rollback(); raise
                value,status=await asyncio.to_thread(transaction)
                return JSONResponse(value,status_code=status)
            except sqlite3.OperationalError as exc:
                if "locked" in str(exc): raise SubjectError(503,"DB_BUSY")
                raise
            except RuntimeError:
                return JSONResponse({"error":{"code":"INTERNAL_ERROR","message":"Erreur interne"}},status_code=500)
            finally:
                if race and action==self.winner: race["done"].set()
                con.close()
        for method in ("GET","POST","PATCH"):
            self.app.add_api_route("/api/{path:path}",endpoint,methods=[method],
                                   operation_id="fixture_catchall_"+method.lower())
