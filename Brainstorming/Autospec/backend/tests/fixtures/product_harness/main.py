"""Independent Linux-only fixture; never imported on the test host.

Real Argon2, HTTP cookies, SQLite/CAS/audit and browser form. Deliberately NOT
complete Relais Support. Trusted seed selects lost_commit/weak_hash negatives.
"""
import hashlib
import json
import os
import secrets
import sqlite3
import sys
import time
from uuid import uuid4
from argon2 import PasswordHasher
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

DB=os.environ["DATABASE_URL"].removeprefix("sqlite:///")
PH=PasswordHasher(time_cost=2,memory_cost=19456,parallelism=1)
app=FastAPI()
LOGIN_FAILURES={}
def now(): return time.time()
def connect():
    con=sqlite3.connect(DB,timeout=.15); con.row_factory=sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON"); con.execute("PRAGMA busy_timeout=150")
    return con

SCHEMA="""
CREATE TABLE users(id TEXT NOT NULL PRIMARY KEY,email TEXT NOT NULL,email_normalized TEXT NOT NULL UNIQUE,password_hash TEXT NOT NULL,role TEXT NOT NULL,active INTEGER NOT NULL);
CREATE TABLE tickets(id TEXT NOT NULL PRIMARY KEY,owner_id TEXT NOT NULL REFERENCES users(id),title TEXT NOT NULL,description TEXT NOT NULL,status TEXT NOT NULL,priority TEXT NOT NULL,assignee_id TEXT REFERENCES users(id),version INTEGER NOT NULL CHECK(typeof(version)='integer' AND version>=1),created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE messages(id TEXT NOT NULL PRIMARY KEY,ticket_id TEXT NOT NULL REFERENCES tickets(id),author_id TEXT NOT NULL REFERENCES users(id),content TEXT NOT NULL,visibility TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE ticket_events(id TEXT NOT NULL PRIMARY KEY,ticket_id TEXT NOT NULL REFERENCES tickets(id),event_type TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE idempotency_keys(actor_id TEXT NOT NULL REFERENCES users(id),kind TEXT NOT NULL,client_request_id TEXT NOT NULL,result_id TEXT NOT NULL,PRIMARY KEY(actor_id,kind,client_request_id));
CREATE TABLE sessions(token_hash TEXT NOT NULL PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id),csrf TEXT NOT NULL,expires_at REAL NOT NULL);
CREATE TABLE fixture_flags(name TEXT PRIMARY KEY,value TEXT NOT NULL);
PRAGMA user_version=1;
"""
def put_account(con,a,weak=False):
    encoded="not-argon2" if weak else PH.hash(a["password"])
    con.execute("INSERT INTO users VALUES(?,?,?,?,?,?)",(a["id"],a["email"],a["email"].strip().lower(),encoded,a["role"],int(a.get("active",True))))
def cli(action,params):
    if action=="migrate_fresh":
        for suffix in ("","-wal","-shm"):
            try: os.unlink(DB+suffix)
            except FileNotFoundError: pass
        schema=SCHEMA
        if params.get("fault")=="null_id": schema=schema.replace("tickets(id TEXT NOT NULL PRIMARY KEY","tickets(id TEXT PRIMARY KEY")
        if params.get("fault")=="fractional_version": schema=schema.replace(" CHECK(typeof(version)='integer' AND version>=1)","")
        with connect() as con: con.executescript(schema)
        return 0
    if action=="bootstrap":
        a=params.get("credentials")
        if not a: return 2
        with connect() as con:
            if con.execute("SELECT COUNT(*) FROM users").fetchone()[0]: return 3
            put_account(con,a,params.get("fault")=="weak_bootstrap")
        return 0
    if action=="seed":
        p=params["payload"]
        with connect() as con:
            for a in p["accounts"]:
                if not con.execute("SELECT id FROM users WHERE id=?",(a["id"],)).fetchone(): put_account(con,a,p.get("bug")=="weak_hash")
            for t in p["tickets"]:
                if not con.execute("SELECT id FROM tickets WHERE id=?",(t["id"],)).fetchone():
                    con.execute("INSERT INTO tickets VALUES(?,?,?,?,?,?,?,?,?,?)",(t["id"],t["owner_id"],t["title"],t["description"],"open","normal",None,1,"2026-10-01T12:00:00Z","2026-10-01T12:00:00Z"))
            con.execute("INSERT OR REPLACE INTO fixture_flags VALUES('bug',?)",(p.get("bug",""),))
        return 0
    if action=="reject": return 9
    return 2
def error(status,code): return JSONResponse({"error":{"code":code,"message":code}},status_code=status)
def authenticate(request,con,mutation=False):
    token=request.cookies.get("sid","")
    row=con.execute("SELECT users.*,sessions.csrf,sessions.expires_at FROM users JOIN sessions ON users.id=sessions.user_id WHERE sessions.token_hash=?",(hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
    if not row or not row["active"] or row["expires_at"]<=now(): return None,error(401,"UNAUTHENTICATED")
    if mutation and (request.headers.get("origin")!=os.environ["APP_ORIGIN"] or request.headers.get("x-csrf-token")!=row["csrf"]): return None,error(403,"CSRF")
    return dict(row),None

@app.post("/api/auth/login")
async def login(request:Request):
    p=await request.json()
    ip=request.client.host; bucket=LOGIN_FAILURES.get(ip)
    if bucket and now()-bucket[0]>=60: LOGIN_FAILURES.pop(ip);bucket=None
    if bucket and bucket[1]>=10:
        r=error(429,"RATE_LIMITED");r.headers["Retry-After"]=str(max(1,int(60-(now()-bucket[0]))));return r
    with connect() as con:
        a=con.execute("SELECT * FROM users WHERE email_normalized=?",(p["email"].strip().lower(),)).fetchone()
        try: valid=bool(a and a["active"] and PH.verify(a["password_hash"],p["password"]))
        except Exception: valid=False
        if not valid:
            if bucket: LOGIN_FAILURES[ip]=(bucket[0],bucket[1]+1)
            else: LOGIN_FAILURES[ip]=(now(),1)
            return error(401,"UNAUTHENTICATED")
        token=secrets.token_urlsafe(32); csrf=secrets.token_urlsafe(24)
        con.execute("INSERT INTO sessions VALUES(?,?,?,?)",(hashlib.sha256(token.encode()).hexdigest(),a["id"],csrf,now()+28800))
        response=JSONResponse({"csrf_token":csrf,"id":a["id"]})
        response.set_cookie("sid",token,httponly=True,samesite="lax",secure=False)
        return response
@app.get("/api/auth/me")
def me(request:Request):
    with connect() as con:
        a,e=authenticate(request,con)
        return e or {"id":a["id"],"role":a["role"]}
@app.get("/api/tickets")
def tickets(request:Request):
    with connect() as con:
        a,e=authenticate(request,con)
        if e: return e
        rows=[dict(r) for r in con.execute("SELECT * FROM tickets WHERE owner_id=? ORDER BY updated_at DESC,id DESC",(a["id"],))]
        return {"items":rows,"total":len(rows),"page":1,"page_size":20}
@app.post("/api/tickets")
async def create(request:Request):
    p=await request.json()
    try:
        with connect() as con:
            a,e=authenticate(request,con,True)
            if e: return e
            con.execute("BEGIN IMMEDIATE")
            key=p["client_request_id"]
            cached=con.execute("SELECT result_id FROM idempotency_keys WHERE actor_id=? AND kind='ticket' AND client_request_id=?",(a["id"],key)).fetchone()
            if cached: return JSONResponse({"id":cached[0]},status_code=200)
            id=str(uuid4()); created="2026-10-12T12:00:00Z"
            bug=con.execute("SELECT value FROM fixture_flags WHERE name='bug'").fetchone()[0]
            if bug!="lost_commit":
                con.execute("INSERT INTO tickets VALUES(?,?,?,?,?,?,?,?,?,?)",(id,a["id"],p["title"],p["description"],"open","normal",None,1,created,created))
                con.execute("INSERT INTO ticket_events VALUES(?,?,?,?)",(str(uuid4()),id,"created",created))
                con.execute("INSERT INTO idempotency_keys VALUES(?,?,?,?)",(a["id"],"ticket",key,id))
            return JSONResponse({"id":id,"title":p["title"],"version":1},status_code=201)
    except sqlite3.OperationalError as exc: return error(503 if "locked" in str(exc) else 500,"DB_BUSY" if "locked" in str(exc) else "DB_FAILURE")
@app.get("/api/tickets/{id}")
def detail(id:str,request:Request):
    with connect() as con:
        a,e=authenticate(request,con)
        if e: return e
        row=con.execute("SELECT * FROM tickets WHERE id=? AND owner_id=?",(id,a["id"])).fetchone()
        if not row: return error(404,"NOT_FOUND")
        result=dict(row)
        if request.headers.get("x-fixture-view")=="browser":
            result["title"]="server:"+result["title"]
            result["description"]="server:"+result["description"]
        return result
@app.patch("/api/tickets/{id}")
async def patch(id:str,request:Request):
    p=await request.json()
    try:
        with connect() as con:
            a,e=authenticate(request,con,True)
            if e: return e
            con.execute("BEGIN IMMEDIATE")
            row=con.execute("SELECT * FROM tickets WHERE id=?",(id,)).fetchone()
            if not row: return error(404,"NOT_FOUND")
            if row["version"]!=p["expected_version"]: return error(409,"STALE_VERSION")
            con.execute("UPDATE tickets SET priority=?,version=version+1 WHERE id=?",(p["priority"],id))
            con.execute("INSERT INTO ticket_events VALUES(?,?,?,?)",(str(uuid4()),id,"updated","2026-10-12T12:00:00Z"))
            return {"id":id,"version":row["version"]+1}
    except sqlite3.OperationalError as exc: return error(503 if "locked" in str(exc) else 500,"DB_BUSY" if "locked" in str(exc) else "DB_FAILURE")

@app.post("/api/tickets/{id}/messages")
async def message(id:str,request:Request):
    p=await request.json()
    with connect() as con:
        a,e=authenticate(request,con,True)
        if e: return e
        con.execute("BEGIN IMMEDIATE")
        row=con.execute("SELECT * FROM tickets WHERE id=?",(id,)).fetchone()
        if not row or (a["role"]=="client" and row["owner_id"]!=a["id"]): return error(404,"NOT_FOUND")
        if p["visibility"]=="internal" and a["role"]=="client": return error(403,"FORBIDDEN")
        cached=con.execute("SELECT result_id FROM idempotency_keys WHERE actor_id=? AND kind='message' AND client_request_id=?",(a["id"],p["client_request_id"])).fetchone()
        if cached: return JSONResponse({"id":cached[0]},status_code=200)
        mid=str(uuid4());created="2026-10-12T12:00:00Z"
        bug=con.execute("SELECT value FROM fixture_flags WHERE name='bug'").fetchone()[0]
        if bug=="lost_note" and p["visibility"]=="internal": return JSONResponse({"id":mid},status_code=201)
        con.execute("INSERT INTO messages VALUES(?,?,?,?,?,?)",(mid,id,a["id"],p["content"],p["visibility"],created))
        con.execute("INSERT INTO ticket_events VALUES(?,?,?,?)",(str(uuid4()),id,"message_"+p["visibility"],created))
        con.execute("UPDATE tickets SET version=version+1 WHERE id=?",(id,))
        con.execute("INSERT INTO idempotency_keys VALUES(?,?,?,?)",(a["id"],"message",p["client_request_id"],mid))
        return JSONResponse({"id":mid},status_code=201)

@app.get("/api/health")
def health(): return {"status":"ok"}

HTML='''<!doctype html><html><body><form id="auth"><input id="email" aria-label="Email"><input id="password" type="password" aria-label="Password"><button id="login">Login</button></form><section id="tickets" hidden><button id="create">Créer</button><form id="creation" hidden><input id="title" aria-label="Title"><textarea id="description" aria-label="Description"></textarea><button id="submit">Envoyer</button></form></section><article id="detail" data-bug="__BUG__" hidden></article><script>
let csrf=''; document.querySelector('#auth').onsubmit=async e=>{e.preventDefault();let r=await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:email.value,password:password.value})});let p=await r.json();if(r.ok){csrf=p.csrf_token;auth.hidden=true;tickets.hidden=false;}};
create.onclick=()=>creation.hidden=false; creation.onsubmit=async e=>{e.preventDefault();let r=await fetch('/api/tickets',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({title:title.value,description:description.value,client_request_id:crypto.randomUUID()})});let p=await r.json();if(r.ok){history.pushState({},'',`/tickets/${p.id}`);let bug=detail.dataset.bug;let t;if(bug==='missing_detail_get'){t={title:p.title,description:description.value};}else if(bug==='local_echo_with_unused_get'){let d=await fetch(`/api/tickets/${p.id}`,{headers:{'X-Fixture-View':'browser'}});await d.json();t={title:p.title,description:description.value};}else{let d=await fetch(`/api/tickets/${p.id}`);t=await d.json();}detail.textContent=bug==='static_detail'?'Ticket créé':bug==='wrong_detail'?t.title+' (wrong)\\n'+t.description:t.title+'\\n'+t.description;detail.hidden=false;creation.hidden=true;}};
</script></body></html>'''
@app.get("/",response_class=HTMLResponse)
@app.get("/tickets/{id}",response_class=HTMLResponse)
def home():
    bug=""
    try:
        with connect() as con:
            row=con.execute("SELECT value FROM fixture_flags WHERE name='bug'").fetchone()
            bug=row[0] if row else ""
    except Exception: pass
    return HTML.replace("__BUG__",bug)
if __name__=="__main__":
    if len(sys.argv)>1: sys.exit(cli(sys.argv[1],json.load(sys.stdin)))
    if os.path.exists(DB):
        with connect() as con:
            flags=con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='fixture_flags'").fetchone()
            bug=con.execute("SELECT value FROM fixture_flags WHERE name='bug'").fetchone() if flags else None
            if bug and bug[0]=="reset_on_start":
                for table in ("sessions","messages","ticket_events","idempotency_keys","tickets","users"): con.execute("DELETE FROM "+table)
    import uvicorn
    uvicorn.run(app,host="127.0.0.1",port=8000,log_level="warning",access_log=False,proxy_headers=False)
