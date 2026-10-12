"""Reviewed product bindings, real isolated HTTP and live SQLite observations.

This module never imports product Python on the host. Bindings are operational
facts, not expected acceptance outcomes. A reviewed command is executed only by
an owned RuntimeSession. Optional instrumentation is explicitly NOT the final
uninstrumented delivery-image observation. Missing ports stay NOT_VERIFIED.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import re
import secrets
import sqlite3
import time
import zlib
import httpx
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Awaitable, Callable, Protocol
from uuid import uuid4

from .support_adapter import AdapterUnavailable, FixtureAccount, FixtureManifest, HttpxSupportAdapter, Proof
from .entropy_protocol import (ENTROPY_BOOTSTRAP, ENTROPY_INSTALL, ENTROPY_PRIMITIVES,
    ENTROPY_CHECK, correlate_entropy, entropy_execution_proof)
from .security_observations import (SecurityObservationBindings, BoundedSecretScanner,
    COOKIE_MODE_LAUNCHER, COOKIE_MODE_REQUEST)


class OwnedRuntime(Protocol):
    """Only the factory-owned container API; never a shell or host fallback."""
    origin: str
    database_path: str
    def exec(self, argv: list[str], *, stdin: str = "", timeout: float = 30) -> tuple[int, str, str]: ...
    def restart(self) -> None: ...


_NAME = re.compile(r"[A-Za-z_][A-Za-z_0-9]*\Z")
_MODULE = re.compile(r"[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*\Z")
_SHA = re.compile(r"[a-f0-9]{64}\Z")


@dataclass(frozen=True)
class TableBinding:
    name: str
    columns: dict[str, str]

    def validate(self):
        if not _NAME.fullmatch(self.name) or not self.columns or any(
            not _NAME.fullmatch(k) or not _NAME.fullmatch(v) for k, v in self.columns.items()
        ) or len(set(self.columns.values())) != len(self.columns):
            raise ValueError("table/column bindings require explicit unique SQL identifiers")


@dataclass(frozen=True)
class CommandBinding:
    argv: tuple[str, ...]
    parameters: tuple[str, ...] = ()
    timeout: float = 30

    def validate(self):
        if not self.argv or self.argv[0] != "/opt/venv/bin/python" or any(
            not isinstance(a, str) or "\x00" in a for a in self.argv
        ) or not 0 < self.timeout <= 120:
            raise ValueError("reviewed Python argv and bounded timeout required")
        # Arguments are literal; data/credentials go through JSON stdin only.
        if len(set(self.parameters)) != len(self.parameters) or any(not _NAME.fullmatch(p) for p in self.parameters):
            raise ValueError("invalid command parameter allowlist")


@dataclass(frozen=True)
class InstrumentationBinding:
    app_module: str
    app_attribute: str
    clock_module: str = ""
    clock_attribute: str = ""
    clock_kind: str = "epoch"  # explicit source return type, not guessed
    password_module: str = ""
    password_attribute: str = ""  # callable verifying a dummy password hash
    business_tables: tuple[str, ...] = ()
    audit_table: str = ""
    races: dict[str, tuple[tuple[str, str], ...]] = field(default_factory=dict)
    race_winners: dict[str, dict[str, tuple[str, str]]] = field(default_factory=dict)
    proxy_headers: bool = True  # match the reviewed server; do not silently harden product
    entropy_module: str = ""
    entropy_attribute: str = ""
    entropy_primitive: str = ""  # exact captured stdlib primitive, never a product declaration

    def validate(self):
        for module, attribute in ((self.app_module, self.app_attribute),
                                  (self.clock_module, self.clock_attribute),
                                  (self.password_module, self.password_attribute),
                                  (self.entropy_module, self.entropy_attribute)):
            if bool(module) != bool(attribute) or (module and (
                not _MODULE.fullmatch(module) or not _NAME.fullmatch(attribute))):
                raise ValueError("explicit reviewed module:symbol binding required")
        if not self.app_module or self.clock_kind not in {"epoch", "utc_datetime"}:
            raise ValueError("Python ASGI instrumentation binding required")
        if type(self.proxy_headers) is not bool: raise ValueError("explicit reviewed ASGI proxy-header mode required")
        if bool(self.entropy_module) != bool(self.entropy_primitive) or (self.entropy_primitive and self.entropy_primitive not in ENTROPY_PRIMITIVES):
            raise ValueError("entropy instrumentation requires an exact reviewed CSPRNG binding")
        if any(not _NAME.fullmatch(t) for t in (*self.business_tables, *([self.audit_table] if self.audit_table else []))):
            raise ValueError("invalid fault-injection table")
        for name, routes in self.races.items():
            if not _NAME.fullmatch(name) or not routes or any(m not in {"POST", "PATCH", "PUT", "DELETE"} or
                not p.startswith("/") or p.startswith("//") or len(p) > 256 for m, p in routes):
                raise ValueError("race targets require explicit method and fullmatch regex path")
            for _, pattern in routes:
                re.compile(pattern)
        for point,winners in self.race_winners.items():
            if point not in self.races or any(not _NAME.fullmatch(w) or tuple(route) not in [tuple(r) for r in self.races[point]] for w,route in winners.items()):
                raise ValueError("scheduled winner must bind one exact reviewed race route")


@dataclass(frozen=True)
class ReviewedProductBindings:
    snapshot_hash: str
    contract_hash: str
    source_files: dict[str, str]
    review: Proof
    database_path: str
    tables: dict[str, TableBinding]
    commands: dict[str, CommandBinding]
    runtime_command: tuple[str, ...]
    auth_path: str
    csrf_field: str
    ticket_path: str
    auth_required: bool = True
    instrumentation: InstrumentationBinding | None = None
    query_plans: dict[str, tuple[str, tuple[Any, ...]]] = field(default_factory=dict)
    internal_port: int = 8000
    local_cookie_mode: bool = False
    browser_bindings: dict[str,str] = field(default_factory=dict)
    browser_routes: dict[str,str] = field(default_factory=dict)
    fixture_fingerprint: str = ""  # pair identity; empty only for legacy explicit fixtures
    security_observations: SecurityObservationBindings | None = None

    @classmethod
    def from_dict(cls, value: dict) -> "ReviewedProductBindings":
        """Parse external reviewed operational facts; no product discovery."""
        try:
            data=dict(value)
            data["review"]=Proof(**{**data["review"],"checks":tuple(data["review"]["checks"])})
            data["tables"]={k:TableBinding(**v) for k,v in data["tables"].items()}
            data["commands"]={k:CommandBinding(tuple(v["argv"]),tuple(v.get("parameters",())),v.get("timeout",30)) for k,v in data["commands"].items()}
            data["runtime_command"]=tuple(data["runtime_command"])
            if data.get("security_observations") is not None:
                data["security_observations"] = SecurityObservationBindings.from_dict(data["security_observations"])
            if data.get("instrumentation"):
                if "proxy_headers" not in data["instrumentation"]:
                    raise ValueError("source-reviewed proxy-header mode must be explicit")
                data["instrumentation"]=InstrumentationBinding(**data["instrumentation"])
            return cls(**data)
        except (KeyError,TypeError,ValueError) as exc:
            raise AdapterUnavailable("reviewed product-bindings schema invalid") from exc

    def fingerprint(self) -> str:
        payload=asdict(self); payload.pop("review")
        return hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=True).encode()).hexdigest()

    def validate(self, snapshot_root: Path):
        if not all(_SHA.fullmatch(s) for s in (self.snapshot_hash, self.contract_hash)):
            raise ValueError("frozen snapshot/contract SHA256 required")
        if self.fixture_fingerprint and not _SHA.fullmatch(self.fixture_fingerprint):
            raise ValueError("fixture pair identity must be SHA256")
        if not self.review.passed or self.review.type != "R" or not {"PRODUCT:bindings","PRODUCT:bindings:"+self.fingerprint()}<=set(self.review.checks) or not self.review.intact(
            snapshot_hash=self.snapshot_hash, contract_hash=self.contract_hash):
            raise AdapterUnavailable("independent intact source-binding review required")
        root = snapshot_root.resolve()
        if Path(self.review.path).resolve().is_relative_to(root):
            raise AdapterUnavailable("source-binding review must be outside producer snapshot")
        self.validate_structure(snapshot_root)

    def validate_structure(self, snapshot_root: Path):
        """Operational consistency only: this never grants source-review PASS."""
        root = snapshot_root.resolve()
        if not all(_SHA.fullmatch(s) for s in (self.snapshot_hash, self.contract_hash)):
            raise ValueError("frozen snapshot/contract SHA256 required")
        if not self.source_files:
            raise AdapterUnavailable("source-exact reviewed file inventory absent")
        for relative, expected in self.source_files.items():
            p = PurePosixPath(relative)
            target = (root / Path(*p.parts)).resolve()
            if p.is_absolute() or ".." in p.parts or not target.is_relative_to(root) or target.is_symlink() or not target.is_file() or not _SHA.fullmatch(expected):
                raise AdapterUnavailable("invalid reviewed source file")
            if hashlib.sha256(target.read_bytes()).hexdigest() != expected:
                raise AdapterUnavailable(f"reviewed binding source changed: {relative}")
        path = PurePosixPath(self.database_path)
        if not path.is_absolute() or ".." in path.parts or path.parent != PurePosixPath("/var/lib/autospec-validation") or path.name in {"", "."}:
            raise ValueError("exact factory-owned validation-volume SQLite path required")
        if not self.tables or any(not _NAME.fullmatch(k) for k in self.tables):
            raise ValueError("explicit logical table bindings required")
        for table in self.tables.values(): table.validate()
        if any(not _NAME.fullmatch(k) for k in self.commands): raise ValueError("literal command names must be identifiers")
        for command in self.commands.values(): command.validate()
        CommandBinding(self.runtime_command).validate()
        if not 1<=self.internal_port<=65535 or type(self.local_cookie_mode) is not bool or type(self.auth_required) is not bool:
            raise ValueError("explicit internal port/auth/cookie deployment binding required")
        for name,(query,parameters) in self.query_plans.items():
            if not _NAME.fullmatch(name) or not query.lstrip().upper().startswith("SELECT ") or ";" in query or len(query)>8000:
                raise ValueError("explicit reviewed SELECT query-plan binding required")
        for path in (self.auth_path, self.ticket_path):
            if not path.startswith("/") or path.startswith("//"):
                raise ValueError("explicit same-origin API paths required")
        if "{id}" not in self.ticket_path or not _NAME.fullmatch(self.csrf_field):
            raise ValueError("ticket route/CSRF field binding absent")
        if self.instrumentation: self.instrumentation.validate()
        if self.security_observations:
            if not self.auth_required: raise ValueError("security cookie observations require source auth")
            self.security_observations.validate()
        if any(not _NAME.fullmatch(k) or not isinstance(v,str) or not v or len(v)>1024 for k,v in self.browser_bindings.items()):
            raise ValueError("explicit bounded reviewed browser locator bindings required")
        if any(not isinstance(p,str) or not p.startswith("/") or p.startswith("//") for p in self.browser_routes.values()):
            raise ValueError("same-origin reviewed browser routes required")


# Runs inside the immutable owned Linux container. Read-only DB URI, one SQLite
# read transaction: before/after comparisons cannot combine torn table reads.
_READ_SQLITE = r'''
import base64, hashlib, json, os, sqlite3, sys, tempfile
q=json.load(sys.stdin); path=q['path']; con=sqlite3.connect('file:'+path+'?mode=ro',uri=True)
con.row_factory=sqlite3.Row; con.execute('BEGIN')
tables=q['tables']; rows={}
for logical,b in tables.items():
 names=list(b['columns']); select=','.join('"'+b['columns'][n]+'" AS "'+n+'"' for n in names)
 rows[logical]=[dict(r) for r in con.execute('SELECT '+select+' FROM "'+b['name']+'"')]
 rows[logical].sort(key=lambda r:json.dumps(r,sort_keys=True,ensure_ascii=True))
schema={'user_version':con.execute('PRAGMA user_version').fetchone()[0],
 'tables':[dict(r) for r in con.execute("SELECT name,sql FROM sqlite_master WHERE type='table' ORDER BY name")],
 'indexes':[dict(r) for r in con.execute("SELECT name,tbl_name,sql FROM sqlite_master WHERE type='index' ORDER BY name")],
 'foreign_key_check':[list(r) for r in con.execute('PRAGMA foreign_key_check')]}
con.rollback()
if q['operation']=='export':
 fd,dest=tempfile.mkstemp(prefix='autospec-export-',suffix='.sqlite'); os.close(fd)
 try:
  out=sqlite3.connect(dest); con.backup(out); out.close()
  if os.path.getsize(dest)>16*1024*1024: raise ValueError('DB export exceeds 16MiB')
  result={'base64':base64.b64encode(open(dest,'rb').read()).decode('ascii')}
 finally: os.unlink(dest)
else: result={'rows':rows,'schema':schema}
if q.get('query_plans'):
 result['query_plans']={name:[list(r) for r in con.execute('EXPLAIN QUERY PLAN '+sql,args)] for name,(sql,args) in q['query_plans'].items()}
con.close(); print(json.dumps(result,ensure_ascii=True))
'''


# The Unix socket is a supervisor control channel, not a delivered debug route.
# No source rewrite; all patches occur inside a disposable validation process.
# Product is not trusted to attest its own correctness: assertions/proofs remain
# outside /app. This instrumentation is diagnostic, not a hostile-process TEE.
TRUSTED_ASGI_LAUNCHER = r'''
import asyncio, contextvars, datetime, importlib, json, os, re, socket, sqlite3, sys, threading, time, uuid
import uvicorn
__ENTROPY_BOOTSTRAP__
b=json.loads(sys.argv[1]); guard=threading.RLock(); local=threading.local()
state={'clock':0.,'faults':{},'pragmas':[],'trace':[],'trace_enabled':False,'race_connections':[],
 'dummy_hash_verifications':0,'race':None,'barrier':None,'race_arrivals':0,'broken_races':0,
 'winner':None,'winner_done':None,'write_lock':None,'busy_events':[],'session_entropy':[]}
request_race=contextvars.ContextVar('autospec_request_race',default=False)
original=sqlite3.connect
def refresh(con):
 with guard:
  state['pragmas'].append({'connection_id':con._autospec_id,
   'foreign_keys':original_cursor(con).execute('PRAGMA foreign_keys').fetchone()[0],
   'busy_timeout_ms':original_cursor(con).execute('PRAGMA busy_timeout').fetchone()[0]})
def original_cursor(con): return sqlite3.Connection.cursor(con)
def traced(sql):
 with guard:
  if state['trace_enabled']: state['trace'].append(re.sub(r"'(?:''|[^'])*'","'[bound]'",sql)[:4000])
def before(con,sql):
 text=sql.strip(); upper=text.upper()
 with guard:
  if request_race.get() and con._autospec_id not in state['race_connections']: state['race_connections'].append(con._autospec_id)
  read_fault=state['faults'].get('db_read')
  audit_fault=state['faults'].get('after_business_before_audit')
 if upper.startswith('SELECT') and read_fault: raise sqlite3.OperationalError('trusted injected read failure')
 table=re.match(r'\s*(?:UPDATE\s+|INSERT\s+(?:OR\s+\w+\s+)?INTO\s+|DELETE\s+FROM\s+)["`\[]?([A-Za-z_][A-Za-z_0-9]*)',text,re.I)
 if table and table.group(1) in b['business_tables']: con._autospec_business_written=True
 if table and table.group(1)==b.get('audit_table') and audit_fault and con._autospec_business_written:
  raise sqlite3.OperationalError('trusted failure after business write before audit')
 if not upper.startswith('PRAGMA'): refresh(con)
class Cursor(sqlite3.Cursor):
 def execute(self,sql,parameters=()):
  before(self.connection,sql); start=time.monotonic()
  try: return super().execute(sql,parameters)
  except sqlite3.OperationalError as exc:
   if 'locked' in str(exc):
    with guard: state['busy_events'].append({'connection_id':self.connection._autospec_id,'elapsed_seconds':time.monotonic()-start,'operation':sql.strip().split()[0]})
   raise
 def executemany(self,sql,parameters): before(self.connection,sql); return super().executemany(sql,parameters)
 def executescript(self,sql): raise RuntimeError('instrumentation does not support unobservable executescript transactions')
class Connection(sqlite3.Connection):
 def set_trace_callback(self,callback): raise RuntimeError('product trace override needs reviewed instrumentation support')
 def cursor(self,factory=None):
  if factory not in (None,Cursor): raise RuntimeError('custom product SQLite cursor needs explicit instrumentation support')
  return super().cursor(Cursor)
 def execute(self,sql,parameters=()): return self.cursor().execute(sql,parameters)
 def executemany(self,sql,parameters): return self.cursor().executemany(sql,parameters)
 def executescript(self,sql): return self.cursor().executescript(sql)
 def commit(self):
  result=super().commit(); self._autospec_business_written=False; return result
 def rollback(self):
  result=super().rollback(); self._autospec_business_written=False; return result
def connect(*args,**kw):
 if kw.get('factory',Connection) not in (Connection,sqlite3.Connection): raise RuntimeError('custom product SQLite factory unsupported')
 kw['factory']=Connection; con=original(*args,**kw); con._autospec_id=uuid.uuid4().hex; con._autospec_business_written=False
 sqlite3.Connection.set_trace_callback(con,traced)
 return con
sqlite3.connect=connect; sqlite3.dbapi2.connect=connect
sys.path.insert(0,'/app') # explicit product import, only after trusted stdlib/deps
__ENTROPY_INSTALL__
if b.get('clock_module'):
 module=importlib.import_module(b['clock_module']); fn=getattr(module,b['clock_attribute'])
 if not callable(fn): raise RuntimeError('clock binding is not callable')
 clock_base=fn()
 def now(value=clock_base):
  with guard: offset=state['clock']
  return value+datetime.timedelta(seconds=offset) if b['clock_kind']=='utc_datetime' else value+offset
 setattr(module,b['clock_attribute'],now)
if b.get('password_module'):
 module=importlib.import_module(b['password_module']); fn=getattr(module,b['password_attribute'])
 if not callable(fn): raise RuntimeError('dummy verifier binding is not callable')
 def verify(*args,_fn=fn,**kw):
  with guard: state['dummy_hash_verifications']+=1
  return _fn(*args,**kw)
 setattr(module,b['password_attribute'],verify)
app=getattr(importlib.import_module(b['app_module']),b['app_attribute'])
async def wrapped(scope,receive,send):
 matched=False
 with guard:
  race=state['race']; barrier=state['barrier']; winner=state['winner']; winner_done=state['winner_done']
  if race and scope['type']=='http': matched=any(scope['method']==m and re.fullmatch(p,scope['path']) for m,p in b['races'][race])
 if matched:
  # Before entering the app/BEGIN; never block while holding a write lock.
  try: await asyncio.to_thread(barrier.wait,8)
  except threading.BrokenBarrierError:
   with guard: state['broken_races']+=1
   raise RuntimeError('trusted rendezvous timeout')
  with guard:
   state['race_arrivals']+=1
   if state['race_arrivals']==2: state['race']=None
  if winner and not (scope['method']==winner[0] and re.fullmatch(winner[1],scope['path'])):
   completed=await asyncio.to_thread(winner_done.wait,8)
   if not completed:
    with guard: state['broken_races']+=1
    raise RuntimeError('trusted scheduled race winner timed out')
 token=request_race.set(matched)
 try: await app(scope,receive,send)
 finally:
  request_race.reset(token)
  if matched and winner and scope['method']==winner[0] and re.fullmatch(winner[1],scope['path']): winner_done.set()
def handle(q):
 with guard:
  action=q['action']
  if action=='observe':
   if q['name']=='race_connections' and state['broken_races']: raise RuntimeError('race barrier was broken')
   return state[q['name']]
  if action=='clock':
   if not b.get('clock_module'): raise RuntimeError('clock binding absent')
   state['clock']+=q['seconds']; return {'offset':state['clock']}
  if action=='fault':
   if q['point'] not in {'db_read','after_business_before_audit'}: raise RuntimeError('unknown fault')
   if q['point']=='after_business_before_audit' and (not b.get('audit_table') or not b['business_tables']): raise RuntimeError('fault table bindings absent')
   state['faults'][q['point']]=q['enabled']; return {'armed':q['enabled']}
  if action=='trace': state['trace']=[]; state['trace_enabled']=True; return {'started':True}
  if action=='race':
   if q['point'] not in b['races'] or q['parties']!=2: raise RuntimeError('reviewed two-party race binding absent')
   state['race']=q['point']; state['barrier']=threading.Barrier(2); state['race_connections']=[]; state['race_arrivals']=0; state['broken_races']=0; state['winner']=None; state['winner_done']=threading.Event(); return {'armed':True}
  if action=='schedule':
   winners=b['race_winners'].get(state['race'],{})
   if q['winner'] not in winners: raise RuntimeError('reviewed deterministic winner binding absent')
   state['winner']=winners[q['winner']]; return {'scheduled':q['winner']}
  if action=='write_lock':
   if q['enabled']:
    if state['write_lock'] is not None: raise RuntimeError('live SQLite write lock already held')
    con=original(b['database_path']); con.execute('BEGIN IMMEDIATE'); state['write_lock']=con
    return {'held':True,'connection_id':uuid.uuid4().hex}
   if state['write_lock'] is None: raise RuntimeError('live SQLite write lock not held')
   state['write_lock'].rollback(); state['write_lock'].close(); state['write_lock']=None; return {'held':False}
  raise RuntimeError('unknown supervisor control action')
def server():
 path='/tmp/autospec-harness.sock'; s=socket.socket(socket.AF_UNIX); s.bind(path); os.chmod(path,0o600); s.listen(8)
 while True:
  client,_=s.accept()
  with client:
   try:
    data=b''
    while not data.endswith(b'\n'):
     part=client.recv(65536)
     if not part: raise RuntimeError('control request closed')
     data+=part
     if len(data)>1024*1024: raise ValueError('control request too large')
    result={'value':handle(json.loads(data))}
   except Exception as exc: result={'unavailable':type(exc).__name__+': '+str(exc)}
   client.sendall(json.dumps(result).encode()+b'\n')
threading.Thread(target=server,daemon=True).start()
uvicorn.run(wrapped,host='127.0.0.1',port=int(b['port']),log_level='warning',access_log=False,proxy_headers=b['proxy_headers'])
'''.replace('__ENTROPY_BOOTSTRAP__', ENTROPY_BOOTSTRAP).replace('__ENTROPY_INSTALL__', ENTROPY_INSTALL)


_CONTROL = r'''
import json,socket,sys
s=socket.socket(socket.AF_UNIX); s.settimeout(10); s.connect('/tmp/autospec-harness.sock')
s.sendall(sys.stdin.buffer.read()+b'\n'); data=b''
while not data.endswith(b'\n'):
 part=s.recv(65536)
 if not part: raise RuntimeError('supervisor control channel closed')
 data+=part
 if len(data)>8*1024*1024: raise RuntimeError('supervisor response exceeds bound')
sys.stdout.buffer.write(data); s.close()
'''

_EXPIRE_SESSION = r'''
import json,sqlite3,sys
q=json.load(sys.stdin); con=sqlite3.connect(q['path']); table=q['table']; column=q['user_column']
with con: result=con.execute('DELETE FROM "'+table+'" WHERE "'+column+'"=?',(q['user_id'],))
print(json.dumps({'revoked_rows':result.rowcount})); con.close()
'''

_CONSTRAINT_PROBE = r'''
import json,re,sqlite3,sys,uuid
q=json.load(sys.stdin); con=sqlite3.connect(q['path']); con.execute('PRAGMA foreign_keys=ON')
t=q['table']; columns=q['columns']; physical=[r[1] for r in con.execute('PRAGMA table_info("'+t+'")')]
if not physical or any(not re.fullmatch('[A-Za-z_][A-Za-z_0-9]*',c) for c in physical): raise ValueError('schema identifiers unavailable')
row=con.execute('SELECT * FROM "'+t+'" LIMIT 1').fetchone()
if row is None: raise ValueError('direct constraint probe requires seed row')
values=dict(zip(physical,row))
for logical,value in q['changes'].items(): values[columns[logical]]=value
con.execute('SAVEPOINT independent_constraint'); rejected=False; error=''
try:
 con.execute('INSERT INTO "'+t+'" ('+','.join('"'+c+'"' for c in physical)+') VALUES ('+','.join('?' for c in physical)+')',[values[c] for c in physical])
except sqlite3.IntegrityError as exc: rejected=True; error=str(exc)
finally: con.execute('ROLLBACK TO independent_constraint'); con.execute('RELEASE independent_constraint')
print(json.dumps({'rejected':rejected,'error':error,'rolled_back':True,'foreign_keys':con.execute('PRAGMA foreign_keys').fetchone()[0],'connection_id':uuid.uuid4().hex})); con.close()
'''


_IMAGE_SOURCE = r'''
import hashlib,json,os,stat
result={}; total=0
for root,dirs,files in os.walk('/app',followlinks=False):
 for name in dirs+files:
  path=os.path.join(root,name); info=os.lstat(path)
  if stat.S_ISLNK(info.st_mode): raise ValueError('baked source symlink forbidden')
 for name in files:
  path=os.path.join(root,name); relative=os.path.relpath(path,'/app').replace(os.sep,'/')
  if '__pycache__' in relative.split('/') or relative.endswith('.pyc'): continue
  info=os.stat(path)
  if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1: raise ValueError('baked source alias/special file forbidden')
  total+=info.st_size
  if len(result)>4096 or total>64*1024*1024: raise ValueError('baked source inventory exceeds bound')
  result[relative]=hashlib.sha256(open(path,'rb').read()).hexdigest()
print(json.dumps(result))
'''


_LINUX_HTTP = r'''
import base64,http.client,ipaddress,json,sys
q=json.load(sys.stdin);ip=ipaddress.IPv4Address(q['source_ip'])
if not ip.is_loopback or not q['path'].startswith('/') or q['path'].startswith('//'): raise ValueError('controlled Linux loopback HTTP target required')
body=base64.b64decode(q['body'],validate=True)
if len(body)>1024*1024: raise ValueError('HTTP request body exceeds bound')
con=http.client.HTTPConnection('127.0.0.1',q['port'],timeout=15,source_address=(str(ip),0))
con.request(q['method'],q['path'],body=body,headers=dict(q['headers']))
r=con.getresponse();payload=r.read(4*1024*1024+1)
if len(payload)>4*1024*1024: raise ValueError('HTTP response body exceeds bound')
print(json.dumps({'status':r.status,'headers':r.getheaders(),'body':base64.b64encode(payload).decode(),
                 'transport':'real-linux-kernel-loopback','source_ip':str(ip)}));con.close()
'''


class LinuxLoopbackTransport(httpx.AsyncBaseTransport):
    """Real HTTP socket in NETNONE, for secondary IPs unavailable on Windows.

    Not an ASGI mock and not XFF. Credentials/cookies are ephemeral input/output,
    never proof logs. Public default-IP/browser requests still use actual ingress.
    This diagnostic port does not certify multi-IP Windows ingress connectivity.
    """
    def __init__(self,harness,source_ip):
        import ipaddress
        ip=ipaddress.IPv4Address(source_ip)
        if not ip.is_loopback: raise AdapterUnavailable("only kernel loopback probe addresses are admitted")
        self.harness=harness;self.source_ip=str(ip)
    async def handle_async_request(self,request):
        body=await request.aread()
        result=await self.harness._exec(("/usr/local/bin/python","-I","-c",_LINUX_HTTP),dict(
            source_ip=self.source_ip,port=self.harness.bindings.internal_port,method=request.method,
            path=request.url.raw_path.decode("ascii"),headers=list(request.headers.multi_items()),
            body=base64.b64encode(body).decode()),timeout=20)
        if result.get("transport")!="real-linux-kernel-loopback" or result.get("source_ip")!=self.source_ip:
            raise AdapterUnavailable("genuine source-IP observation absent")
        self.harness._ip_transport_observations.add(self.source_ip)
        return httpx.Response(result["status"],headers=result["headers"],content=base64.b64decode(result["body"],validate=True),request=request)


FixtureFactory = Callable[..., Awaitable[tuple[FixtureManifest, dict[str, Any]]]]
ProofProvider = Callable[[str], Awaitable[list[Proof]]]


class SecurityObservedAdapter(HttpxSupportAdapter):
    """Remember fictitious probe secrets in memory, never in receipts."""
    def __init__(self, *, known_secrets, negative_output, **kwargs):
        self._known_secrets = known_secrets
        self._negative_output = negative_output
        super().__init__(**kwargs)

    def _remember(self, response):
        if response.status_code >= 400:
            self._negative_output(response.content)
        for value in response.cookies.values():
            self._known_secrets.add(value)
        try: token = response.json().get(self.csrf_field)
        except (ValueError, AttributeError): token = None
        if isinstance(token, str) and token: self._known_secrets.add(token)
        return response

    async def login(self, actor, **kwargs):
        if actor in self.manifest.accounts: self._known_secrets.add(self.manifest.accounts[actor].password)
        return self._remember(await super().login(actor, **kwargs))

    async def request(self, actor, method, path, **kwargs):
        data = kwargs.get("json")
        if isinstance(data, dict) and isinstance(data.get("password"), str):
            self._known_secrets.add(data["password"])
        return self._remember(await super().request(actor, method, path, **kwargs))


class ReviewedFixtureFactory:
    """Usable JSON fixture inputs, frozen independently of observed product.

    Explicit cases/variants only. `$generated` passwords and `$uuid` identifiers
    are created BEFORE command execution. A {$ref:'accounts.alice.email'} object
    injects a known input, never a value learned from a product response.
    Unknown options/cases are unavailable, not approximated by a nominal seed.
    """
    def __init__(self, path: Path, *, snapshot_hash: str, contract_hash: str, source_root: Path):
        self.path=path.resolve(); root=source_root.resolve()
        if self.path.is_relative_to(root) or not self.path.is_file() or self.path.stat().st_size>1024*1024:
            raise AdapterUnavailable("bounded supervisor-owned reviewed fixtures JSON required")
        raw=self.path.read_bytes(); self._sha=hashlib.sha256(raw).hexdigest()
        try:
            data=json.loads(raw); review=Proof(**{**data["review"],"checks":tuple(data["review"]["checks"])})
            content=dict(data); content.pop("review")
            digest=hashlib.sha256(json.dumps(content,sort_keys=True,ensure_ascii=True).encode()).hexdigest()
            if (data["snapshot_hash"],data["contract_hash"])!=(snapshot_hash,contract_hash) or not review.passed or review.type!="R" or not {"PRODUCT:fixtures","PRODUCT:fixtures:"+digest}<=set(review.checks) or not review.intact(snapshot_hash=snapshot_hash,contract_hash=contract_hash):
                raise AdapterUnavailable("independent fixture-input review missing/drifted")
            if Path(review.path).resolve().is_relative_to(root): raise AdapterUnavailable("fixture review inside product")
            if not isinstance(data["cases"],dict) or not data["cases"]: raise ValueError("cases empty")
            self.cases=data["cases"];self.fingerprint=digest
            self.review=review;self.snapshot=snapshot_hash;self.contract=contract_hash
        except (KeyError,ValueError,TypeError) as exc: raise AdapterUnavailable("reviewed fixtures schema invalid") from exc

    async def __call__(self,case_id,**options):
        if hashlib.sha256(self.path.read_bytes()).hexdigest()!=self._sha:
            raise AdapterUnavailable("reviewed fixture inputs changed")
        if not self.review.intact(snapshot_hash=self.snapshot,contract_hash=self.contract):
            raise AdapterUnavailable("fixture-input review artifact changed")
        if case_id not in self.cases: raise AdapterUnavailable("explicit fixture case absent: "+case_id)
        case=self.cases[case_id]
        variants=case.get("variants",[])
        if options:
            matches=[v for v in variants if v.get("options")==options]
            if len(matches)!=1: raise AdapterUnavailable("exact independently reviewed fixture option variant absent")
            case={**case,**matches[0]["fixture"]}
        accounts={}
        for alias,value in case.get("accounts",{}).items():
            a=dict(value)
            if a.get("password")=="$generated": a["password"]="Probe-é漢字-"+secrets.token_urlsafe(32)
            if a.get("id")=="$uuid": a["id"]=str(uuid4())
            if not _NAME.fullmatch(alias) or not isinstance(a.get("password"),str) or not a["password"]:
                raise AdapterUnavailable("explicit fixture account inputs malformed")
            accounts[alias]=FixtureAccount(**a)
        for alias,target in case.get("aliases",{}).items():
            if not _NAME.fullmatch(alias) or alias in accounts or target not in accounts:
                raise AdapterUnavailable("explicit fixture account alias malformed")
            accounts[alias]=accounts[target]
        tickets={k:str(uuid4()) if v=="$uuid" else v for k,v in case.get("tickets",{}).items()}
        known={"accounts":{k:asdict(v) for k,v in accounts.items()},"tickets":tickets}
        def render(value):
            if isinstance(value,dict) and set(value)=={"$ref"}:
                ref=value["$ref"].split("."); found=known
                for part in ref:
                    if not isinstance(found,dict) or part not in found: raise AdapterUnavailable("unknown trusted fixture input reference")
                    found=found[part]
                if ref==["accounts"]: return list({a["id"]:a for a in found.values()}.values())
                return found
            if isinstance(value,dict): return {k:render(v) for k,v in value.items()}
            if isinstance(value,list): return [render(v) for v in value]
            return value
        manifest=FixtureManifest(accounts,tickets,render(case.get("metadata",{})))
        payload=render(case.get("commands",{}))
        return manifest,payload


class ProductHarness:
    """Concrete ports to one exact owned SQLite/ASGI runtime.

    A fixture factory defines inputs/IDs before product execution; it does not
    infer expectations from returned product data. prepare_fixture must be an
    explicitly reviewed isolated source command accepting JSON stdin. The same
    DB volume persists across restart. Provision commands must provide their
    own transaction handling; a failed command never earns a PASS receipt.
    """
    def __init__(self, runtime: OwnedRuntime, bindings: ReviewedProductBindings, *,
                 snapshot_root: Path, evidence_root: Path, fixture_factory: FixtureFactory,
                 snapshot_hash: Callable[[], Awaitable[str]],
                 contract_hash: Callable[[], Awaitable[str]],
                 proof_provider: ProofProvider | None = None, instrumented: bool = False):
        bindings.validate(snapshot_root)
        if getattr(runtime, "database_path", None) != bindings.database_path or not callable(getattr(runtime,"exec",None)):
            raise AdapterUnavailable("runtime does not expose exact owned DB/exec ports")
        self.runtime, self.bindings = runtime, bindings
        self.snapshot_root, self.evidence_root = snapshot_root.resolve(), evidence_root.resolve()
        if self.evidence_root.is_relative_to(self.snapshot_root):
            raise ValueError("proof root must be supervisor-owned outside product snapshot")
        self.fixture_factory, self._snapshot, self._contract = fixture_factory, snapshot_hash, contract_hash
        self._inventory=self._source_inventory()
        self._proof_provider, self.instrumented = proof_provider, instrumented
        if instrumented and bindings.instrumentation is None:
            raise AdapterUnavailable("reviewed instrumentation bindings absent")
        self.manifest = FixtureManifest()
        self._command_receipts=[]
        self._ip_transport_observations=set()
        self._security_secrets=set()
        self._security_outputs=[]
        self._security_output_bytes=0
        self._security_output_overflow=False
        self._security_child_logs=[]
        import httpx
        self.adapter = SecurityObservedAdapter(known_secrets=self._security_secrets,
            negative_output=lambda raw:self._security_output("artifacts","negative-http-response",raw),
            base_url=runtime.origin, origin=runtime.origin,
            auth_path=bindings.auth_path, csrf_field=bindings.csrf_field, evidence_root=self.evidence_root,
            prepare=self.prepare_case, observe=self.observe, snapshot=snapshot_hash, oracle=contract_hash,
            command=self.command, clock=self.advance_clock, proofs=self.proofs, race=self.arm_race,
            restart=self.restart, fault=self.set_fault,
            # The owned ingress bridge has bounded TCP lifetimes. Disable pool
            # reuse rather than retrying a possibly committed mutation.
            transport_factory=lambda ip:httpx.AsyncHTTPTransport(local_address=ip,
                limits=httpx.Limits(max_keepalive_connections=0)) if ip=="127.0.0.1" else LinuxLoopbackTransport(self,ip))
        self.adapter.live_sqlite=True # supervisor capability, never a product claim
        self.adapter.supervised_runtime=runtime # exact owned namespace; no browser host fallback
        self.adapter.native_security_observation=self.collect_security_observation
        self.adapter.security_snapshot_root=self.snapshot_root

    async def _identity(self):
        if await self._snapshot()!=self.bindings.snapshot_hash or await self._contract()!=self.bindings.contract_hash:
            raise AdapterUnavailable("frozen snapshot/oracle identity drift")
        self.bindings.validate(self.snapshot_root)
        if self._source_inventory()!=self._inventory:
            raise AdapterUnavailable("runtime source stage changed during verification")

    def _source_inventory(self):
        from ..agents.file_broker import ExecutionContext,FileBroker
        broker=FileBroker(ExecutionContext("product-harness-observer",self.snapshot_root))
        result={}
        for path in self.snapshot_root.rglob("*"):
            relative=path.relative_to(self.snapshot_root)
            checked=broker.path(relative.as_posix())
            if checked.is_file() and checked.suffix!=".pyc" and "__pycache__" not in relative.parts:
                result[relative.as_posix()]=hashlib.sha256(checked.read_bytes()).hexdigest()
        return result

    async def _exec(self, argv, payload, timeout=30):
        await self._identity()
        rc,out,err=await asyncio.to_thread(self.runtime.exec,list(argv),stdin=json.dumps(payload,ensure_ascii=True),timeout=timeout)
        await self._identity()
        if rc:
            # Product logs may contain credentials. Do not echo them into proofs.
            raise AdapterUnavailable(f"isolated harness operation exited {rc} (output withheld)")
        try: return json.loads(out)
        except (ValueError,TypeError) as exc: raise AdapterUnavailable("isolated observation is not JSON") from exc

    async def _database(self, operation="read"):
        return await self._exec(("/usr/local/bin/python","-I","-c",_READ_SQLITE),dict(
            path=self.bindings.database_path,operation=operation,
            query_plans=self.bindings.query_plans,
            tables={k:dict(name=v.name,columns=v.columns) for k,v in self.bindings.tables.items()}))

    async def _control(self, action, **parameters):
        if not self.instrumented:
            raise AdapterUnavailable("diagnostic instrumentation unavailable on unmodified runtime")
        result=await self._exec(("/usr/local/bin/python","-I","-c",_CONTROL),dict(action=action,**parameters))
        if "unavailable" in result: raise AdapterUnavailable("isolated diagnostic control unavailable (details withheld)")
        return result["value"]

    async def prepare_case(self, case_id, **options):
        await self._identity()
        manifest,payload=await self.fixture_factory(case_id,**options)
        if not isinstance(manifest,FixtureManifest) or not isinstance(payload,dict):
            raise AdapterUnavailable("trusted fixture plan is malformed")
        self._command_receipts=[]
        steps=manifest.metadata.get("provisioning",("prepare_fixture",))
        if not isinstance(steps,(tuple,list)) or not steps or len(steps)>8 or any(s not in self.bindings.commands for s in steps):
            raise AdapterUnavailable("explicit reviewed fixture provisioning commands absent")
        for action in steps:
            parameters={"payload":payload} if action=="prepare_fixture" else payload.get(action)
            if not isinstance(parameters,dict): raise AdapterUnavailable("trusted command inputs absent: "+action)
            result=await self.command(action,**parameters)
            if result["exit_code"]!=0:
                raise AdapterUnavailable("isolated fixture provisioning failed; previous DB cannot stand in for fixture")
        self.manifest=manifest
        self._security_secrets.update(a.password for a in manifest.accounts.values())
        manifest.metadata["sqlite_tables"]={k:v.name for k,v in self.bindings.tables.items()}
        return manifest

    async def command(self, action, **parameters):
        if action=="register_actor":
            from .support_adapter import FixtureAccount
            required={"actor","id","email","password","role"}
            if set(parameters)!=required: raise AdapterUnavailable("explicit actor credentials required")
            self.manifest.accounts[parameters["actor"]]=FixtureAccount(parameters["id"],parameters["email"],parameters["password"],parameters["role"])
            return {"registered":True}
        if action=="sql_trace_start":
            return await self._control("trace")
        if action=="expire_actor":
            if set(parameters)!={"actor"} or parameters["actor"] not in self.manifest.accounts:
                raise AdapterUnavailable("explicit fixture actor required for session revocation")
            table=self.bindings.tables.get("sessions")
            if table is None or "user_id" not in table.columns: raise AdapterUnavailable("reviewed server session ownership column absent")
            return await self._exec(("/usr/local/bin/python","-I","-c",_EXPIRE_SESSION),dict(
                path=self.bindings.database_path,table=table.name,user_column=table.columns["user_id"],
                user_id=self.manifest.accounts[parameters["actor"]].id))
        if action=="schedule_race_winner":
            return await self._control("schedule",**parameters)
        if action=="hold_write_lock": return await self.hold_write_lock()
        if action=="release_write_lock": return await self.release_write_lock()
        if action=="constraint_probe":
            if set(parameters)!={"table","changes"}: raise AdapterUnavailable("fixed independent constraint parameters required")
            table=self.bindings.tables.get(parameters["table"]);changes=parameters["changes"]
            if table is None or not isinstance(changes,dict) or set(changes)-set(table.columns):
                raise AdapterUnavailable("reviewed logical constraint columns unavailable")
            return await self._exec(("/usr/local/bin/python","-I","-c",_CONSTRAINT_PROBE),dict(
                path=self.bindings.database_path,table=table.name,columns=table.columns,changes=changes))
        binding=self.bindings.commands.get(action)
        if binding is None or set(parameters)-set(binding.parameters):
            raise AdapterUnavailable(f"reviewed isolated command unavailable: {action}")
        await self._identity()
        before=await self.observe("business_state") if action=="seed_collision" else None
        rc,out,err=await asyncio.to_thread(self.runtime.exec,list(binding.argv),stdin=json.dumps(parameters),timeout=binding.timeout)
        self._security_output("logs","reviewed-command-"+action,(out+err).encode("utf-8"))
        await self._identity()
        result={"exit_code":rc,"command":action,"output":"withheld: may contain credentials"}
        self._command_receipts.append({"command":action,"exit_code":rc})
        if action=="seed_collision": result["preserved"]=before==await self.observe("business_state")
        return result

    async def observe(self, name, **params):
        if name in {"secret_scan", "cookie_modes"}:
            value, _ = await self.collect_security_observation(name, **params)
            return value
        if name=="session_entropy":
            hook=self.bindings.instrumentation
            if not hook or not hook.entropy_module:
                raise AdapterUnavailable("reviewed native CSPRNG instrumentation capability absent")
            await self._identity()
            observation=correlate_entropy(await self._control("observe",name="session_entropy"),params.get("token_sha256"))
            snapshot,contract=await self._snapshot(),await self._contract()
            native=entropy_execution_proof(self.evidence_root,observation,snapshot,contract)
            reviews=[p for p in await self.proofs("SEC-05") if p.type=="R" and p.passed is True and
                ENTROPY_CHECK in p.checks and p.intact(snapshot_hash=snapshot,contract_hash=contract)]
            await self._identity()
            return {**observation,"proofs":[asdict(p) for p in [native,*reviews]]}
        if name=="ip_transport_scope":
            return dict(default="real-public-loopback-ingress",alternate="real-linux-kernel-loopback",
                actual_source_ips=sorted(self._ip_transport_observations),
                limits=["secondary-IP public Windows ingress was not verified; no host network configuration changed"])
        if name in {"app_connection_pragmas","race_connections","sql_trace","dummy_hash_verifications","db_busy_timeout_ms","db_busy_waits"}:
            key={"app_connection_pragmas":"pragmas","sql_trace":"trace"}.get(name,name)
            if name=="db_busy_waits": key="busy_events"
            if name=="dummy_hash_verifications" and not (self.bindings.instrumentation and self.bindings.instrumentation.password_module):
                raise AdapterUnavailable("reviewed dummy verifier symbol absent")
            if name=="db_busy_timeout_ms":
                rows=await self._control("observe",name="pragmas")
                if not rows: raise AdapterUnavailable("actual application SQLite PRAGMAs absent")
                return max(r["busy_timeout_ms"] for r in rows)
            return await self._control("observe",name=key)
        data=await self._database(); rows=data["rows"]
        def table(key):
            if key not in rows: raise AdapterUnavailable(f"reviewed logical table absent: {key}")
            return rows[key]
        if name in {"business_state","full_database_state","security_state","snapshot"}:
            keys=set(self.bindings.tables)
            if name=="business_state": keys-={"sessions"}
            return {k:table(k) for k in sorted(keys)}
        if name=="account_count": return len(table("users"))
        if name=="account_fingerprints":
            return [{"id":r["id"],"password_hash_sha256":hashlib.sha256(r["password_hash"].encode()).hexdigest()} for r in table("users")]
        if name=="password_hashes":
            emails=set(params["emails"]); return [r["password_hash"] for r in table("users") if r["email_normalized"] in emails]
        if name=="email_count": return sum(r["email_normalized"]==params["email"].strip().lower() for r in table("users"))
        if name=="active_admin_count": return sum(r["role"]=="admin" and bool(r["active"]) for r in table("users"))
        if name=="business_counts": return {k:len(table(k)) for k in ("users","tickets","messages","ticket_events","idempotency_keys")}
        if name=="essential_tables_present":
            return {"users","sessions","tickets","messages","ticket_events","idempotency_keys"}<=set(rows)
        if name=="email_unique_constraint":
            # Real DB mutation on an exported clone, not a guessed index name.
            target=await self.export_sqlite(self.evidence_root/("unique-probe-"+uuid4().hex+".sqlite"))
            try:
                con=sqlite3.connect(target); t=self.bindings.tables["users"]
                seed=con.execute('SELECT * FROM "'+t.name+'" LIMIT 1').fetchone()
                if seed is None: raise AdapterUnavailable("seed user required for uniqueness probe")
                physical=[r[1] for r in con.execute('PRAGMA table_info("'+t.name+'")')]
                values=dict(zip(physical,seed)); values[t.columns["id"]]=str(uuid4())
                try:
                    con.execute('INSERT INTO "'+t.name+'" ('+','.join('"'+c+'"' for c in physical)+') VALUES ('+','.join('?' for _ in physical)+')',[values[c] for c in physical]); rejected=False
                except sqlite3.IntegrityError: rejected=True
                finally: con.rollback(); con.close()
                return rejected
            finally: target.unlink(missing_ok=True)
        if name=="session_storage": return [{"stored":r["token_hash"]} for r in table("sessions")]
        if name in {"assigned_tickets","inactive_assignments"}:
            users={r["id"]:r for r in table("users")}
            if name=="assigned_tickets":
                actor=self.manifest.accounts[params["actor"]].id
                return [r for r in table("tickets") if r["assignee_id"]==actor]
            return [r for r in table("tickets") if r["assignee_id"] in users and not users[r["assignee_id"]]["active"]]
        if name=="tickets_by_ids": return [r for r in table("tickets") if r["id"] in params["ids"]]
        if name=="browser_operation_count": return sum(r["title"]==params["title"] for r in table("tickets"))
        if name=="browser_message_count": return sum(r["ticket_id"]==params["ticket_id"] and r["content"]==params["content"] for r in table("messages"))
        if name=="browser_dashboard_expected":
            account=self.manifest.accounts[params["actor"]]
            scoped=[r for r in table("tickets") if account.role!="client" or r["owner_id"]==account.id]
            return dict(total=len(scoped),by_status={status:sum(r["status"]==status for r in scoped) for status in ("open","in_progress","resolved","closed")})
        if name=="frontend_api_origin_scan":
            scanned=[];urls=[]
            for path in self.snapshot_root.rglob("*"):
                if path.is_file() and path.suffix.lower() in {".js",".jsx",".ts",".tsx",".html"}:
                    raw=path.read_bytes()
                    if len(raw)>4*1024*1024: raise AdapterUnavailable("frontend source scan file exceeds bound")
                    scanned.append({"path":str(path),"sha256":hashlib.sha256(raw).hexdigest()})
                    urls.extend(re.findall(r'''https?://[^\s"'<>`]*?/api(?:/[^\s"'<>`]*)?''',raw.decode("utf-8",errors="replace")))
            if not scanned: raise AdapterUnavailable("frontend source inventory absent")
            return {"scanned_files":scanned,"absolute_api_urls":sorted(set(urls)),"limits":["literal source URL scan, not a proof about all computed URLs"]}
        if name=="ticket_state":
            ticket=next((r for r in table("tickets") if r["id"]==params["ticket_id"]),None)
            if ticket is None: raise AdapterUnavailable("fixture ticket absent from live DB")
            return {**{k:ticket[k] for k in ("status","priority","assignee_id","version")},
                "audit_count":sum(r["ticket_id"]==ticket["id"] for r in table("ticket_events")),
                "message_count":sum(r["ticket_id"]==ticket["id"] for r in table("messages"))}
        if name=="schema": return data["schema"]
        if name=="query_plan":
            if not self.bindings.query_plans: raise AdapterUnavailable("reviewed live SELECT query-plan bindings absent")
            return [{"query":name,"plan":plan} for name,plan in data["query_plans"].items()]
        if name=="route_inventory":
            response=await self.adapter.request(None,"GET","/openapi.json",authenticate=False)
            if response.status_code!=200: raise AdapterUnavailable("actual OpenAPI inventory unavailable")
            result=[]
            for p,methods in response.json().get("paths",{}).items():
                if not p.startswith("/api/"): continue
                for m in methods:
                    if m.lower() not in {"get","post","put","patch","delete"}: continue
                    # The source contract makes business APIs private. Only
                    # exact diagnostic/auth public exceptions are excluded.
                    public=p in {"/api/health","/api/health/db","/api/auth/login","/api/auth/logout"}
                    target=p.replace("{id}",str(uuid4()))
                    if "{" in target or "}" in target:
                        target=self.manifest.metadata.get("route_targets",{}).get(p)
                        if not isinstance(target,str) or not target.startswith("/api/") or "{" in target:
                            raise AdapterUnavailable("explicit valid secondary API route target unavailable")
                    result.append(dict(path=target,template=p,method=m.upper(),business=not public))
            return result
        # Cookie alternate deployment modes, query plans and secret scanning
        # need explicit independent services; no empty/True success defaults.
        raise AdapterUnavailable(f"independent observation port unavailable: {name}")

    async def export_sqlite(self, target: Path) -> Path:
        target=target.resolve()
        if not target.is_relative_to(self.evidence_root) or target.exists():
            raise ValueError("new supervisor-owned SQLite export target required")
        result=await self._database("export")
        blob=base64.b64decode(result["base64"],validate=True)
        if len(blob)>16*1024*1024 or not blob.startswith(b"SQLite format 3\x00"):
            raise AdapterUnavailable("invalid bounded SQLite export")
        target.parent.mkdir(parents=True,exist_ok=True)
        with target.open("xb") as out: out.write(blob)
        return target

    async def verify_image_source(self,snapshot_hash,contract_hash,*,additional_files=None):
        """Compare actual baked /app bytes, with no /app source bind overlay."""
        if self.instrumented or getattr(self.runtime,"mount_stage",True):
            raise AdapterUnavailable("unmodified baked image runtime required")
        if (snapshot_hash,contract_hash)!=(self.bindings.snapshot_hash,self.bindings.contract_hash):
            raise AdapterUnavailable("baked image identity mismatch")
        actual=await self._exec(("/usr/local/bin/python","-I","-c",_IMAGE_SOURCE),{})
        expected=self._source_inventory()
        for path,digest in (additional_files or {}).items():
            if path in expected or not path.startswith("frontend/dist/") or ".." in PurePosixPath(path).parts or not _SHA.fullmatch(digest):
                raise AdapterUnavailable("independently built frontend inventory invalid")
            expected[path]=digest
        passed=actual==expected
        proof=self._proof("image_source",dict(image_id=self.runtime.image,source_mount=False,
            actual_inventory=actual,expected_inventory=expected),passed,snapshot_hash,contract_hash)
        return dict(status="PASS" if passed else "FAIL",image_id=self.runtime.image,proofs=[proof.__dict__],
            scope="actual baked source bytes, not a source mount or health-only receipt")

    async def advance_clock(self, seconds):
        if not isinstance(seconds,(int,float)) or not 0<=seconds<=86400*30: raise ValueError("bounded forward clock delta required")
        await self._control("clock",seconds=seconds)

    async def arm_race(self, point, parties=2): await self._control("race",point=point,parties=parties)
    async def hold_write_lock(self): return await self._control("write_lock",enabled=True)
    async def release_write_lock(self): return await self._control("write_lock",enabled=False)
    async def set_fault(self, point, enabled=True):
        if type(enabled) is not bool: raise ValueError("fault flag must be boolean")
        await self._control("fault",point=point,enabled=enabled)
    async def restart(self):
        await self._identity(); await asyncio.to_thread(self.runtime.restart)
        await self.wait_ready(); await self._identity()

    async def wait_ready(self):
        """GET-only transport prerequisite after every new server process.

        A live SQLite volume does not establish ASGI readiness. Never retry an
        acceptance mutation here and never award a requirement from this GET.
        """
        import httpx
        deadline=time.monotonic()+15
        async with httpx.AsyncClient(timeout=10,limits=httpx.Limits(max_keepalive_connections=0)) as client:
            while time.monotonic()<deadline:
                try:
                    await client.get(self.runtime.origin+"/"); return
                except httpx.HTTPError: await asyncio.sleep(.1)
        raise AdapterUnavailable("isolated runtime did not become HTTP-ready within 15s")
    async def proofs(self, requirement_id):
        return [] if self._proof_provider is None else await self._proof_provider(requirement_id)

    def _security_output(self, scope, name, raw):
        self._security_output_bytes+=len(raw)
        if self._security_output_bytes>4*1024*1024:
            self._security_output_overflow=True
        elif not self._security_output_overflow:
            self._security_outputs.append((scope,name,raw))

    async def collect_security_observation(self, name, *, scope=None, image_id=None):
        """Dynamic observation after the actual case, never a cached narrative."""
        await self._identity()
        binding=self.bindings.security_observations
        if binding is None: raise AdapterUnavailable("source-reviewed native security observation facts absent")
        if name=="cookie_modes":
            if scope is not None or image_id is not None: raise AdapterUnavailable("unknown cookie observation parameters")
            return await self._cookie_modes(binding)
        if name!="secret_scan" or scope not in {"source_image_logs","logs_artifacts"}:
            raise AdapterUnavailable("exact native security scan scope required")
        scanner=BoundedSecretScanner(self._security_secrets)
        if self._security_output_overflow:
            raise AdapterUnavailable("complete probe command/negative-response scan exceeded bound")
        provenance={"instrumented_runtime":self.instrumented}
        logs, log_identity=await asyncio.to_thread(self.runtime.capture_security_logs)
        import io
        scanner.scan(io.BytesIO(logs),scope="logs",name="complete-owned-current-container-log")
        for index,(kind,label,raw) in enumerate(self._security_outputs):
            if kind=="logs" or scope=="logs_artifacts":
                scanner.scan(io.BytesIO(raw),scope=kind,name=label+"-"+str(index))
        provenance["logs"]=log_identity
        provenance["cookie_mode_logs"]=list(self._security_child_logs)
        if scope=="source_image_logs":
            if image_id is None: raise AdapterUnavailable("qualified immutable delivery image is required, not the dependency runtime image")
            scanner.scan_tree(self.snapshot_root,scope="source")
            provenance["image"]=await asyncio.to_thread(self.runtime.scan_security_image,
                image_id,self.bindings.snapshot_hash,scanner.scan_image)
            scopes=["source","image","logs"]
        else:
            if image_id is not None: raise AdapterUnavailable("negative-path scan cannot substitute unrelated image evidence")
            self.evidence_root.mkdir(parents=True,exist_ok=True)
            from ..agents.file_broker import ExecutionContext,FileBroker
            artifact_broker=FileBroker(ExecutionContext("owned-security-artifacts",self.evidence_root))
            for relative in binding.artifact_roots:
                # An exact "." declares this already-attested supervisor root,
                # not a producer file path or a relaxed broker navigation rule.
                root=self.evidence_root if relative=="." else artifact_broker.path(relative).resolve()
                if not root.is_relative_to(self.evidence_root): raise AdapterUnavailable("artifact scope escapes owned campaign evidence")
                scanner.scan_tree(root,scope="artifacts")
            scopes=["logs","artifacts"]
        await self._identity()
        value,proof=scanner.receipt(self.evidence_root,scopes=scopes,snapshot=self.bindings.snapshot_hash,
            contract=self.bindings.contract_hash,provenance=provenance)
        return value,[proof]

    async def _cookie_modes(self, binding):
        """Real isolated requests under reviewed deployment configurations.

        Factory ASGI/TLS launch only, same code/image, no auth mock. Each mode
        owns a fresh DB; certificates/keys stay in its /tmp, never in receipts.
        This checks cookie deployment behavior, not the delivered image CMD.
        """
        from ..orchestrator.isolated_validation import RuntimeSession
        image=(await asyncio.to_thread(self.runtime.inspect_configuration))["image_id"]
        if not re.fullmatch(r"sha256:[a-f0-9]{64}",image): raise AdapterUnavailable("immutable cookie probe image identity absent")
        rows=[];proofs=[]
        for name,mode in binding.modes.items():
            command=["/opt/venv/bin/python","-I","-u","-c",COOKIE_MODE_LAUNCHER,
                json.dumps(dict(module=binding.app_module,attribute=binding.app_attribute,tls=mode.tls,port=self.bindings.internal_port))]
            runtime=RuntimeSession(self.snapshot_root,image,command,port=self.bindings.internal_port,
                docker=self.runtime.docker,application_origin=True,persistent_database=True,
                mount_stage=getattr(self.runtime,"mount_stage",True),security_environment=mode.environment,
                application_origin_scheme="https" if mode.tls else "http")
            child=None
            try:
                await asyncio.to_thread(runtime.__enter__)
                child=ProductHarness(runtime,self.bindings,snapshot_root=self.snapshot_root,
                    evidence_root=self.evidence_root/("cookie-mode-"+uuid4().hex),fixture_factory=self.fixture_factory,
                    snapshot_hash=self._snapshot,contract_hash=self._contract)
                await child.prepare_case(binding.fixture_case)
                if binding.actor not in child.manifest.accounts: raise AdapterUnavailable("reviewed cookie fixture actor absent")
                account=child.manifest.accounts[binding.actor]
                self._security_secrets.add(account.password)
                observed=await child._exec(("/usr/local/bin/python","-I","-c",COOKIE_MODE_REQUEST),dict(
                    tls=mode.tls,port=self.bindings.internal_port,path=self.bindings.auth_path,cookie_name=binding.cookie_name,csrf_field=self.bindings.csrf_field,
                    origin=runtime.env["APP_ORIGIN"],credentials=dict(email=account.email,password=account.password)),timeout=20)
                private=observed.pop("_probe_secrets",None)
                if not isinstance(private,list) or any(not isinstance(s,str) for s in private):
                    raise AdapterUnavailable("private observer auth-secret trace unavailable")
                self._security_secrets.update(private)
                if observed.get("status")!=200 or not observed.get("cookie_present") or (mode.tls and not observed.get("tls_version")):
                    raise AdapterUnavailable("real reviewed cookie mode login/header evidence unavailable")
                configuration=await asyncio.to_thread(runtime.inspect_configuration)
                row=dict(mode=name,**observed,image_id=image,source_snapshot=self.bindings.snapshot_hash,
                    container_id=runtime.identifier,environment=mode.environment,
                    scope="actual cookie header from same-code factory ASGI deployment; not delivered CMD certification")
                rows.append(row)
                child.evidence_root.mkdir(parents=True,exist_ok=True)
                path=child.evidence_root/"cookie-mode.json"
                path.write_bytes(json.dumps(dict(snapshot_hash=self.bindings.snapshot_hash,contract_hash=self.bindings.contract_hash,
                    observed=row,configuration=configuration),sort_keys=True).encode())
                proofs.append(Proof("X",str(path),hashlib.sha256(path.read_bytes()).hexdigest(),self.bindings.snapshot_hash,
                    self.bindings.contract_hash,("SEC-05:cookie_mode:"+name,),True,"obtained real isolated header; oracle decides secure attribute"))
            finally:
                try:
                    if child:
                        self._security_secrets.update(child._security_secrets)
                        if child._security_output_overflow: self._security_output_overflow=True
                        for kind,label,raw in child._security_outputs:
                            self._security_output(kind,"cookie-mode-"+name+":"+label,raw)
                        try:
                            raw,identity=await asyncio.to_thread(runtime.capture_security_logs)
                            self._security_output("logs","cookie-mode-"+name,raw)
                            self._security_child_logs.append(dict(mode=name,**identity))
                        except Exception:
                            # Missing a removed container's log cannot become
                            # a later clean SEC-15 observation.
                            self._security_output_overflow=True
                finally:
                    if child: await child.adapter.close()
                    await asyncio.to_thread(runtime.close)
        await self._identity()
        return rows,proofs

    def _proof(self, stage, observed, passed, snapshot, contract):
        self.evidence_root.mkdir(parents=True,exist_ok=True)
        path=self.evidence_root/("vertical-"+stage+"-"+uuid4().hex+".json")
        payload=dict(stage=stage,observed=observed,passed=passed,snapshot_hash=snapshot,contract_hash=contract,
                     instrumented=self.instrumented)
        path.write_bytes(json.dumps(payload,ensure_ascii=True,sort_keys=True).encode())
        return Proof("X",str(path),hashlib.sha256(path.read_bytes()).hexdigest(),snapshot,contract,
                     ("VERTICAL:"+stage,),passed)

    async def verify_vertical(self, snapshot_hash, contract_hash, *, browser_smoke=None):
        """Narrow smoke receipt; cannot award full SEC/FUN compliance.

        Browser callback must execute the reviewed Playwright browser_smoke and
        return its genuine X/V proofs. It cannot be replaced by health checks.
        A login/create ID is checked independently over HTTP and live SQLite.
        """
        stages=[]; limits=[]
        async def stage(name,fn):
            try:
                observed,passed=await fn()
                proof=self._proof(name,observed,bool(passed),snapshot_hash,contract_hash)
                stages.append(dict(name=name,passed=bool(passed),proofs=[proof.__dict__]))
            except (AdapterUnavailable,KeyError,ValueError) as exc:
                stages.append(dict(name=name,passed=False,proofs=[])); limits.append(name+": "+str(exc))
        if self.instrumented:
            limits.append("vertical must use the uninstrumented final runtime, not diagnostic launcher")
            return dict(status="NOT_VERIFIED",snapshot_hash=snapshot_hash,contract_hash=contract_hash,stages=[],limits=limits)
        await self._identity()
        if (snapshot_hash,contract_hash)!=(self.bindings.snapshot_hash,self.bindings.contract_hash):
            raise AdapterUnavailable("vertical identity does not match reviewed bindings")
        async def schema():
            observed=await self.observe("schema")
            actual={t["name"] for t in observed["tables"]}
            required={t.name for t in self.bindings.tables.values()}
            migrated=any(r["command"]=="migrate_fresh" and r["exit_code"]==0 for r in self._command_receipts)
            observed["provisioning"]=list(self._command_receipts)
            return observed,migrated and required<=actual and not observed["foreign_key_check"] and observed["user_version"]>=1
        await stage("schema",schema)
        if self.bindings.auth_required:
            async def bootstrap():
                # Requires prepare_fixture to have executed explicit source bootstrap.
                actor=self.manifest.metadata.get("bootstrap_actor")
                if actor not in self.manifest.accounts: raise AdapterUnavailable("explicit bootstrap provenance absent")
                account=self.manifest.accounts[actor]
                users=(await self._database())["rows"]["users"]
                found=[r for r in users if r["id"]==account.id]
                names=[r["command"] for r in self._command_receipts if r["exit_code"]==0]
                explicit="migrate_fresh" in names and "bootstrap" in names and names.index("migrate_fresh")<names.index("bootstrap")
                return {"actor_id":account.id,"count":len(found),"role":found[0]["role"] if found else None,"commands":self._command_receipts},explicit and len(found)==1 and found[0]["role"]=="admin"
            await stage("bootstrap",bootstrap)
            async def argon2():
                from argon2 import PasswordHasher,extract_parameters
                from argon2.low_level import Type
                users=(await self._database())["rows"]["users"]
                account=self.manifest.accounts[self.manifest.metadata.get("vertical_actor","alice")]
                row=next(r for r in users if r["id"]==account.id)
                try:
                    p=extract_parameters(row["password_hash"])
                    valid=PasswordHasher().verify(row["password_hash"],account.password)
                    passed=valid and p.type==Type.ID and p.memory_cost>=19456 and p.time_cost>=2 and p.parallelism==1
                    return dict(verified=valid,type=p.type.name,memory_kib=p.memory_cost,iterations=p.time_cost,parallelism=p.parallelism),passed
                except Exception: return {"verified":False},False
            await stage("argon2",argon2)
        if any(not s["passed"] and s["proofs"] for s in stages):
            for name in (("browser_login","browser_create","api_read","db_committed") if self.bindings.auth_required else ("browser_create","api_read","db_committed")):
                stages.append(dict(name=name,passed=False,proofs=[]))
            await self._identity()
            return dict(status="FAIL",snapshot_hash=snapshot_hash,contract_hash=contract_hash,stages=stages,
                ticket_id=None,limits=["downstream business smoke not executed after observed prerequisite failure"],
                scope="narrow smoke; prerequisite counterexample is not full product acceptance")
        ticket_id=None
        if browser_smoke is None:
            for name in (("browser_login","browser_create") if self.bindings.auth_required else ("browser_create",)):
                stages.append(dict(name=name,passed=False,proofs=[])); limits.append(name+": reviewed real browser port absent")
        else:
            result=await browser_smoke(self.adapter,snapshot_hash,contract_hash)
            ticket_id=result.get("ticket_id"); limits.extend(result.get("limits",[]))
            for name in (("browser_login","browser_create") if self.bindings.auth_required else ("browser_create",)):
                proofs=[p for p in result.get("proofs",[]) if isinstance(p,Proof) and "VERTICAL:"+name in p.checks]
                passed=result.get("status")=="PASS" and {"X","V"}<={p.type for p in proofs} and all(p.passed and p.intact(snapshot_hash=snapshot_hash,contract_hash=contract_hash) for p in proofs)
                stages.append(dict(name=name,passed=passed,proofs=[p.__dict__ for p in proofs]))
        actor=self.manifest.metadata.get("vertical_actor","alice") if self.bindings.auth_required else None
        async def api_read():
            if not isinstance(ticket_id,str) or not ticket_id: raise AdapterUnavailable("browser creation server ID absent")
            r=await self.adapter.request(actor,"GET",self.bindings.ticket_path.replace("{id}",ticket_id))
            return dict(status=r.status_code,ticket_id=r.json().get("id")),r.status_code==200 and r.json().get("id")==ticket_id
        await stage("api_read",api_read)
        async def db_committed():
            if not ticket_id: raise AdapterUnavailable("browser creation server ID absent")
            rows=(await self._database())["rows"]; tickets=[r for r in rows["tickets"] if r["id"]==ticket_id]
            events=[r for r in rows["ticket_events"] if r["ticket_id"]==ticket_id]
            passed=len(tickets)==1 and bool(events)
            if actor: passed=passed and tickets[0]["owner_id"]==self.manifest.accounts[actor].id
            return dict(ticket_id=ticket_id,ticket_count=len(tickets),audit_count=len(events)),passed
        await stage("db_committed",db_committed); await self._identity()
        failed=any(not s["passed"] and s["proofs"] for s in stages)
        return dict(status="FAIL" if failed else "PASS" if stages and all(s["passed"] for s in stages) and not limits else "NOT_VERIFIED",
            snapshot_hash=snapshot_hash,contract_hash=contract_hash,stages=stages,limits=limits,
            ticket_id=ticket_id,
            scope="narrow isolated business smoke; not complete SEC/FUN/ARC acceptance")

    async def verify_persistence(self, snapshot_hash, contract_hash, *, ticket_id, actor="alice", requirement_ids=()):
        """OPS-04 runtime restart evidence with full live DB before/after.

        The runtime owns its ephemeral volume; this does not claim production
        backup/restore or arbitrary product README commands have been checked.
        """
        await self._identity()
        if (snapshot_hash,contract_hash)!=(self.bindings.snapshot_hash,self.bindings.contract_hash): raise AdapterUnavailable("persistence identity mismatch")
        before=(await self._database())["rows"]
        await self.restart()
        after=(await self._database())["rows"]
        response=await self.adapter.request(actor,"GET",self.bindings.ticket_path.replace("{id}",ticket_id))
        passed=before==after and response.status_code==200 and response.json().get("id")==ticket_id
        proof=self._proof("persistence",dict(before_sha256=hashlib.sha256(json.dumps(before,sort_keys=True).encode()).hexdigest(),
            after_sha256=hashlib.sha256(json.dumps(after,sort_keys=True).encode()).hexdigest(),status=response.status_code,ticket_id=ticket_id),passed,snapshot_hash,contract_hash)
        from dataclasses import replace
        if any(not re.fullmatch(r"[A-Z][A-Z0-9_]*-\d+",rid) for rid in requirement_ids): raise ValueError("invalid persistence requirement mapping")
        proof=replace(proof,checks=proof.checks+tuple(rid+":persistence" for rid in requirement_ids))
        return dict(status="PASS" if passed else "FAIL",proofs=[proof.__dict__],limits=["restart of same owned volume; no backup/restore or README certification"])

    async def verify_operations_persistence(self,snapshot_hash,contract_hash,*,client="alice",staff="camille"):
        """OPS-04: real ticket/public/internal/audit/keys, recreate + undeploy.

        Direct baked runtime only. Missing lifecycle or message routes are NV,
        not a substitute restart-only PASS. Requests use current real sessions.
        """
        await self._identity()
        if self.instrumented or getattr(self.runtime,"mount_stage",True):
            raise AdapterUnavailable("OPS-04 requires the actual unmodified baked image")
        if (snapshot_hash,contract_hash)!=(self.bindings.snapshot_hash,self.bindings.contract_hash):
            raise AdapterUnavailable("OPS-04 observation identity mismatch")
        detach=getattr(self.runtime,"detach",None);attach=getattr(self.runtime,"attach",None)
        if not callable(detach) or not callable(attach): raise AdapterUnavailable("owned volume-preserving undeploy/redeploy port absent")
        payload=dict(title="Independent OPS persistence "+uuid4().hex,
            description="Actual final-image public and internal durable history probe",client_request_id=str(uuid4()))
        created=await self.adapter.request(client,"POST","/api/tickets",json=payload)
        if created.status_code!=201 or not isinstance(created.json().get("id"),str):
            raise AdapterUnavailable("real OPS fixture ticket creation unavailable")
        ticket=created.json()["id"];path=self.bindings.ticket_path.replace("{id}",ticket)+"/messages"
        messages=[]
        for actor,visibility in ((client,"public"),(staff,"internal")):
            body=dict(content="Independent OPS "+visibility+" "+uuid4().hex,
                visibility=visibility,client_request_id=str(uuid4()))
            response=await self.adapter.request(actor,"POST",path,json=body)
            if response.status_code!=201 or not isinstance(response.json().get("id"),str):
                raise AdapterUnavailable("real OPS public/internal message creation unavailable")
            messages.append((actor,body,response.json()["id"]))
        before=(await self._database())["rows"]
        ids_before=dict(container=self.runtime.identifier,volume=self.runtime.volume_name,origin=self.runtime.origin)
        await self.restart()
        restarted=(await self._database())["rows"]
        await asyncio.to_thread(detach)
        detached_volume=self.runtime.volume_name
        await asyncio.to_thread(attach)
        await self.wait_ready()
        # No host import/route injection; readiness before API replay is only a
        # transport prerequisite, never an acceptance check.
        for _ in range(20):
            try:
                after=(await self._database())["rows"];break
            except AdapterUnavailable: await asyncio.sleep(.1)
        else: raise AdapterUnavailable("live SQLite unavailable after owned redeploy")
        replies=[];limits=[]
        # An observed destructive startup already contradicts persistence.
        # Do not lose this FAIL to a subsequent login port becoming unavailable
        # because the same defective process also deleted its accounts.
        durable=before==restarted==after
        committed=(sum(r["id"]==ticket for r in before["tickets"])==1
            and all(sum(r["id"]==mid for r in before["messages"])==1 for _,_,mid in messages)
            and sum(r["ticket_id"]==ticket for r in before["ticket_events"])>=3
            and all(any(r["result_id"]==mid for r in before["idempotency_keys"]) for mid in (ticket,*(m[2] for m in messages))))
        if durable and committed:
            replay=await self.adapter.request(client,"POST","/api/tickets",json=payload)
            replies.append(dict(kind="ticket",status=replay.status_code,id=replay.json().get("id"),expected_id=ticket))
            for actor,body,expected_id in messages:
                replay=await self.adapter.request(actor,"POST",path,json=body)
                replies.append(dict(kind=body["visibility"],status=replay.status_code,id=replay.json().get("id"),expected_id=expected_id))
        else:
            limits.append("replay not executed after observed missing committed record or destructive lifecycle")
        replayed=(await self._database())["rows"]
        passed=(committed and durable and before==replayed and ids_before["volume"]==detached_volume==self.runtime.volume_name
            and ids_before["origin"]==self.runtime.origin and ids_before["container"]!=self.runtime.identifier
            and len(replies)==3 and all(r["status"]==200 and r["id"]==r["expected_id"] for r in replies))
        from dataclasses import replace
        proof=self._proof("ops_persistence",dict(ticket_id=ticket,identities_before=ids_before,
            identities_after=dict(container=self.runtime.identifier,volume=self.runtime.volume_name,origin=self.runtime.origin),
            database_digests=[hashlib.sha256(json.dumps(r,sort_keys=True).encode()).hexdigest() for r in (before,restarted,after,replayed)],
            counts={t:len(rows) for t,rows in before.items()},initial_records_committed=committed,
            lifecycle_rows_preserved=durable,replays=replies),passed,snapshot_hash,contract_hash)
        proof=replace(proof,checks=("OPS-04","OPS-04:ticket_response_note_restart_undeploy_replay"))
        return dict(status="PASS" if passed else "FAIL",proofs=[asdict(proof)],limits=limits,
            observed=[dict(check="ticket_response_note_restart_undeploy_replay",passed=passed,replays=replies,
                initial_records_committed=committed,lifecycle_rows_preserved=durable,
                volume_preserved=ids_before["volume"]==self.runtime.volume_name)],
            reproduction=["create real ticket/public response/internal note; compare every DB row after recreate and volume-preserving undeploy; replay same three keys"])


def instrumented_command(binding: InstrumentationBinding, *, port=8000, database_path="/var/lib/autospec-validation/support.sqlite") -> list[str]:
    binding.validate()
    if not 1<=port<=65535: raise ValueError("invalid internal port")
    if PurePosixPath(database_path).parent!=PurePosixPath("/var/lib/autospec-validation") or ".." in PurePosixPath(database_path).parts:
        raise ValueError("factory-owned SQLite path required")
    # Runtime argv is bounded per argument. Split only this constant trusted
    # diagnostic launcher, never a product script or a user-supplied program.
    # Hash verification in NETNONE pins the decompressed bytes before exec.
    raw=TRUSTED_ASGI_LAUNCHER.encode("utf-8")
    encoded=base64.b64encode(zlib.compress(raw)).decode("ascii")
    bootstrap=("import sys,base64,zlib,hashlib; "
        "p=zlib.decompress(base64.b64decode(''.join(sys.argv[1:-1]),validate=True)); "
        f"assert len(p)=={len(raw)} and hashlib.sha256(p).hexdigest()=='{hashlib.sha256(raw).hexdigest()}'; "
        "sys.argv=[sys.argv[0],sys.argv[-1]]; exec(compile(p,'<trusted-ASGI-supervisor>','exec'))")
    return ["/opt/venv/bin/python","-I","-u","-c",bootstrap,
        *[encoded[i:i+4000] for i in range(0,len(encoded),4000)],
        json.dumps({**binding.__dict__,"port":port,"database_path":database_path})]


class OwnedProductHarnessSession:
    """Async lifetime from reviewed JSON facts to clean Linux runtime + ports.

    stage_root must be a new supervisor path outside source_root. The source is
    filtered before mounting. Network-enabled installs receive only manifests;
    executing product code has network NONE. Closing cleans container/volume.
    This context does not mutate the immutable source or infer its bindings.
    """
    def __init__(self, bindings: ReviewedProductBindings, *, source_root: Path,
                 stage_root: Path, evidence_root: Path, cache_root: Path,
                 fixture_factory: FixtureFactory | None = None, fixtures_path: Path | None = None,
                 snapshot_hash, contract_hash, proof_provider=None, instrumented=False, docker="docker",image_id=None):
        self.bindings=bindings; self.source_root=source_root.resolve(); self.stage_root=stage_root.resolve()
        self.evidence_root=evidence_root; self.cache_root=cache_root
        if fixture_factory is not None and fixtures_path is not None: raise ValueError("choose one fixture input provider")
        if fixture_factory is None:
            if fixtures_path is None: raise AdapterUnavailable("reviewed fixture JSON absent")
            fixture_factory=ReviewedFixtureFactory(fixtures_path,snapshot_hash=bindings.snapshot_hash,
                contract_hash=bindings.contract_hash,source_root=self.source_root)
        self.factory=fixture_factory
        if bindings.fixture_fingerprint and getattr(fixture_factory,"fingerprint",None)!=bindings.fixture_fingerprint:
            raise AdapterUnavailable("reviewed bindings/fixtures pair identity differs")
        self.snapshot=snapshot_hash; self.contract=contract_hash; self.proofs=proof_provider
        self.instrumented=instrumented; self.docker=docker; self.runtime=None; self.harness=None
        if image_id is not None and (instrumented or not re.fullmatch(r"sha256:[a-f0-9]{64}",image_id)):
            raise AdapterUnavailable("direct baked image requires immutable sha256 ID without instrumentation")
        self.image_id=image_id

    @classmethod
    def from_bindings(cls, path: Path, **kwargs):
        path=path.resolve()
        source=Path(kwargs["source_root"]).resolve()
        if path.is_relative_to(source) or not path.is_file() or path.stat().st_size>1024*1024:
            raise AdapterUnavailable("bindings must be a bounded external supervisor file")
        try: value=json.loads(path.read_bytes())
        except (ValueError,OSError) as exc: raise AdapterUnavailable("bindings JSON unavailable") from exc
        return cls(ReviewedProductBindings.from_dict(value),**kwargs)

    async def __aenter__(self):
        from ..orchestrator.validation_environment import LinuxEnvironmentManager,snapshot_product
        from ..orchestrator.isolated_validation import RuntimeSession
        self.bindings.validate(self.source_root)
        image=self.image_id
        if image is None:
            manager=LinuxEnvironmentManager(self.cache_root,docker=self.docker)
            environment=await asyncio.to_thread(manager.prepare,self.source_root,"python","runtime")
            image=environment.image
        stage=await asyncio.to_thread(snapshot_product,self.source_root,self.stage_root)
        command=instrumented_command(self.bindings.instrumentation,port=self.bindings.internal_port,database_path=self.bindings.database_path) if self.instrumented and self.bindings.instrumentation else list(self.bindings.runtime_command)
        if self.instrumented and self.bindings.instrumentation is None:
            raise AdapterUnavailable("instrumented session requires reviewed ASGI bindings")
        self.runtime=RuntimeSession(stage,image,command,port=self.bindings.internal_port,
            docker=self.docker,application_origin=True,local_cookie_mode=self.bindings.local_cookie_mode,persistent_database=True,
            mount_stage=self.image_id is None,use_image_command=self.image_id is not None)
        try:
            await asyncio.to_thread(self.runtime.__enter__)
            self.harness=ProductHarness(self.runtime,self.bindings,snapshot_root=stage,
                evidence_root=self.evidence_root,fixture_factory=self.factory,snapshot_hash=self.snapshot,
                contract_hash=self.contract,proof_provider=self.proofs,instrumented=self.instrumented)
            await self.wait_ready()
            return self.harness
        except BaseException:
            await asyncio.to_thread(self.runtime.close)
            raise

    async def wait_ready(self):
        await self.harness.wait_ready()

    async def __aexit__(self,*args):
        if self.harness: await self.harness.adapter.close()
        if self.runtime: await asyncio.to_thread(self.runtime.close)
