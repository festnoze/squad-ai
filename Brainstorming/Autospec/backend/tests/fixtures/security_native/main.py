"""Independent minimal HTTP/SQLite/Argon2 metatest, not the support product."""
import hashlib
import json
import os
import secrets
import sqlite3
import sys
from argon2 import PasswordHasher
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()
PH = PasswordHasher(memory_cost=19456, time_cost=2, parallelism=1)

def connection():
    return sqlite3.connect(os.environ['DATABASE_URL'].removeprefix('sqlite:///'))

def provision(action, data):
    with connection() as db:
        if action == 'migrate_fresh':
            for table, columns in {
                'users': 'id TEXT,email TEXT,email_normalized TEXT,password_hash TEXT,role TEXT,active INTEGER',
                'tickets': 'id TEXT,owner_id TEXT,title TEXT,description TEXT,status TEXT,priority TEXT,assignee_id TEXT,version INTEGER,created_at TEXT,updated_at TEXT',
                'messages': 'id TEXT,ticket_id TEXT,author_id TEXT,content TEXT,visibility TEXT,created_at TEXT',
                'ticket_events': 'id TEXT,ticket_id TEXT,event_type TEXT,created_at TEXT',
                'idempotency_keys': 'actor_id TEXT,kind TEXT,client_request_id TEXT,result_id TEXT',
                'sessions': 'token_hash TEXT,user_id TEXT,csrf TEXT,expires_at REAL',
                'probe_flags': 'bug TEXT',
            }.items():
                db.execute('CREATE TABLE IF NOT EXISTS '+table+'('+columns+')')
            db.execute('PRAGMA user_version=1')
        elif action in {'bootstrap', 'seed'}:
            payload = data if action == 'bootstrap' else data['payload']
            accounts = [payload['credentials']] if action == 'bootstrap' else payload['accounts']
            for a in accounts:
                if not db.execute('SELECT 1 FROM users WHERE id=?', (a['id'],)).fetchone():
                    db.execute('INSERT INTO users VALUES(?,?,?,?,?,?)',
                        (a['id'], a['email'], a['email'].lower(), PH.hash(a['password']), a['role'], a.get('active', True)))
            if action == 'seed':
                db.execute('DELETE FROM probe_flags')
                db.execute('INSERT INTO probe_flags VALUES(?)', (payload.get('bug', ''),))
        else: return 2
    return 0

@app.get('/')
def home():
    return {'scope': 'independent security observer fixture only'}

@app.post('/api/auth/login')
async def login(request: Request):
    data = await request.json()
    if request.headers.get('Origin') != os.environ['APP_ORIGIN']:
        return JSONResponse({'error': {'code': 'ORIGIN', 'message': 'Refus'}}, status_code=403)
    with connection() as db:
        row = db.execute('SELECT id,password_hash FROM users WHERE email_normalized=?', (data['email'].lower(),)).fetchone()
        if not row or not PH.verify(row[1], data['password']):
            return JSONResponse({'error': {'code': 'AUTH', 'message': 'Refus'}}, status_code=401)
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        db.execute('INSERT INTO sessions VALUES(?,?,?,?)', (hashlib.sha256(token.encode()).hexdigest(), row[0], csrf, 28800))
        bug = db.execute('SELECT bug FROM probe_flags').fetchone()
    response = JSONResponse({'csrf_token': csrf})
    secure = os.environ.get('SESSION_COOKIE_SECURE', 'true') == 'true'
    if bug and bug[0] == 'insecure-production': secure = False
    response.set_cookie('sid', token, secure=secure, httponly=True, samesite='lax', path='/')
    return response

@app.post('/probe/negative')
async def negative(request: Request):
    # Deliberately faulty fixture: first sensitive line would be lost to tail100.
    data = await request.json()
    print(data['password'], flush=True)
    for index in range(130): print('ordinary-log-line-'+str(index), flush=True)
    return JSONResponse({'error': {'code': 'DB', 'message': data['password']}}, status_code=503)

if __name__ == '__main__':
    if len(sys.argv) > 1: raise SystemExit(provision(sys.argv[1], json.load(sys.stdin)))
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=8000, access_log=False)
