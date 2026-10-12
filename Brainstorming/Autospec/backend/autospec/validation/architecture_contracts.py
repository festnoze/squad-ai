"""Relais Support architecture contracts: real SQLite/API, bounded conclusions.

SQL probes target the canonical fixture schema. A campaign with different column
names supplies a trusted logical table map, never product-derived expectations.
Missing schema/runner/review/clock is NOT_VERIFIED, not guessed conformity.
"""
from __future__ import annotations

import re
import sqlite3
import time
from collections import Counter
from uuid import uuid4

from .business_contracts import ProbePack, STATUSES, digest
from .support_adapter import AdapterUnavailable

ARCHITECTURE_CHECKS = {
    "ARC-01": ("backend_map", "frontend_map", "rules", "abstractions"),
    "ARC-02": ("foreign_keys", "constraints", "null_ids", "integer_versions", "schema_review"),
    "ARC-03": ("distinct_connections", "busy", "rollback", "transactions"),
    "ARC-04": ("fresh_migration", "replay", "schema_version"),
    "ARC-05": ("query_counts", "query_plan", "index_rationale"),
    "ARC-06": ("openapi", "validation", "public_dto", "error_dto", "frontend_errors", "error_client"),
    "ARC-07": ("bounds", "sorts", "totals", "detail", "no_secrets", "refused_unchanged"),
    "ARC-08": ("utc", "ties", "clock", "timezone_independent"),
    "ARC-09": ("domains", "http_csrf_errors", "typed_dto", "duplication_risk"),
}
ARCH_REVIEW = {"backend_map", "frontend_map", "rules", "abstractions", "schema_review", "transactions",
               "index_rationale", "public_dto", "frontend_errors", "timezone_independent",
               "domains", "http_csrf_errors", "typed_dto", "duplication_risk"}
ROUTES = {
    "/api/auth/login":{"post"}, "/api/auth/logout":{"post"}, "/api/auth/me":{"get"},
    "/api/users":{"get","post"}, "/api/users/{id}":{"patch"}, "/api/assignees":{"get"},
    "/api/tickets":{"get","post"}, "/api/tickets/{id}":{"get","patch"},
    "/api/tickets/{id}/messages":{"get","post"}, "/api/tickets/{id}/history":{"get"},
    "/api/dashboard":{"get"},
}


class ArchitectureContractVerifier(ProbePack):
    pack = "architecture"
    checks = ARCHITECTURE_CHECKS
    review_checks = ARCH_REVIEW
    ui_checks = {"error_client"}

    def connect(self):
        if self.adapter.manifest.metadata.get("independent_fixture") is not True:
            raise AdapterUnavailable("host SQLite fallback is for an explicitly independent fixture only; exported DB is not live")
        fn=getattr(self.adapter,"connect_db",None)
        if fn is None: raise AdapterUnavailable("true SQLite connection port absent")
        connection=fn()
        if not isinstance(connection,sqlite3.Connection):
            raise AdapterUnavailable("connection is not a real SQLite connection")
        return connection

    def table(self, logical):
        name=self.adapter.manifest.metadata.get("sqlite_tables",{}).get(logical,logical)
        if not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*",name):
            raise AdapterUnavailable("invalid trusted SQLite table map")
        return name

    def insert_counterexample(self, con, table, changes, name):
        """Clone an actual fixture row, mutate fixed invariant inputs, roll back.

        Existing values fill unrelated mandatory fields, not expected outcomes.
        Every direct write is inside a savepoint and removed on either outcome.
        """
        columns=[r[1] for r in con.execute(f'PRAGMA table_info("{table}")')]
        if not columns or not all(re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*",c) for c in columns):
            raise AdapterUnavailable(f"canonical table missing: {table}")
        row=con.execute(f'SELECT * FROM "{table}" LIMIT 1').fetchone()
        if row is None: raise AdapterUnavailable(f"seed row absent for direct constraint probe: {table}")
        if not set(changes)<=set(columns): raise AdapterUnavailable(f"canonical columns absent: {set(changes)-set(columns)}")
        data=dict(zip(columns,row)); data.update(changes)
        con.execute("SAVEPOINT independent_constraint")
        rejected=False; error=""
        try:
            con.execute(f'INSERT INTO "{table}" ({",".join(chr(34)+c+chr(34) for c in columns)}) VALUES ({",".join("?" for _ in columns)})',
                        [data[c] for c in columns])
        except sqlite3.IntegrityError as exc:
            rejected=True; error=str(exc)
        finally:
            con.execute("ROLLBACK TO independent_constraint"); con.execute("RELEASE independent_constraint")
        self.check(name,rejected,{"table":table,"mutated_fields":changes,"integrity_error":error},
                   f"direct INSERT {table}, fixed mutation {changes}; required DB constraint must reject")

    async def _ARC02(self):
        await self.prepare(); before=await self.state()
        live=getattr(self.adapter,"live_sqlite",False) is True
        connections=[] if live else [self.connect(),self.connect()]
        try:
            for con in connections:
                self.check("foreign_keys",con.execute("PRAGMA foreign_keys").fetchone()[0]==1,
                           {"enabled":con.execute("PRAGMA foreign_keys").fetchone()[0]},"each distinct app SQLite connection enables FK")
            con=connections[0] if connections else None
            async def probe(logical,changes,name):
                if not live:
                    return self.insert_counterexample(con,self.table(logical),changes,name)
                result=await self.adapter.command("constraint_probe",table=logical,changes=changes)
                if not isinstance(result,dict) or type(result.get("rejected")) is not bool or result.get("rolled_back") is not True or result.get("foreign_keys")!=1 or not result.get("connection_id"):
                    raise AdapterUnavailable("real live SQLite rollback/constraint observation absent")
                self.check(name,result["rejected"],{"table":logical,"mutated_fields":changes,"actual_result":result},
                    f"owned live SQLite INSERT {logical}, fixed invariant mutation {changes}; rollback in independent connection")
            await self.create()  # populate messages/events through actual API, not fabricated constraint results
            await self.message()
            # Compare preservation after these deliberate seed writes, before direct SQL probes.
            before=await self.state()
            suffix=str(uuid4())
            # SQLite TEXT PRIMARY KEY alone famously permits NULL; explicit NOT NULL required.
            await probe("users",{"id":None,"email":f"null-{suffix}@example.test","email_normalized":f"null-{suffix}@example.test"},"null_ids")
            await probe("tickets",{"id":None},"null_ids")
            await probe("tickets",{"id":str(uuid4()),"version":1.5},"integer_versions")
            await probe("tickets",{"id":str(uuid4()),"version":0},"integer_versions")
            await probe("tickets",{"id":str(uuid4()),"owner_id":str(uuid4())},"constraints")
            await probe("tickets",{"id":str(uuid4()),"status":"invalid"},"constraints")
            await probe("tickets",{"id":str(uuid4()),"priority":"urgent"},"constraints")
            await probe("tickets",{"id":str(uuid4()),"owner_id":None},"constraints")
            await probe("users",{"id":str(uuid4())},"constraints")
            await probe("idempotency_keys",{},"constraints")
            await probe("users",{"id":str(uuid4()),"email":f"role-{suffix}@example.test",
                "email_normalized":f"role-{suffix}@example.test","role":"superadmin"},"constraints")
            for column in ("title","description","status","priority","version","created_at","updated_at"):
                await probe("tickets",{"id":str(uuid4()),column:None},"constraints")
            for logical,changes in (("messages",{"id":str(uuid4()),"ticket_id":str(uuid4())}),
                ("messages",{"id":str(uuid4()),"visibility":"private"}),
                ("messages",{"id":str(uuid4()),"author_id":None}),
                ("sessions",{"token_hash":str(uuid4()),"user_id":str(uuid4())})):
                await probe(logical,changes,"constraints")
            await probe("messages",{"id":None},"null_ids")
            pragmas=await self.adapter.observe("app_connection_pragmas")
            if not isinstance(pragmas,list) or len(pragmas)<2:
                raise AdapterUnavailable("actual API SQLite connection PRAGMA instrumentation absent")
            self.check("foreign_keys",all(p.get("foreign_keys")==1 for p in pragmas),
                {"actual_app_connections":pragmas},"independent instrumentation verifies FK on actual HTTP handler connections, not only direct harness connections")
        finally:
            for con in connections: con.close()
        self.check("constraints",before==await self.state(),{"before_digest":digest(before),"after_digest":digest(await self.state())},
                   "all direct constraint probes roll back; full business DB preserved")

    async def _ARC03(self):
        await self.prepare(); await self.adapter.login("camille")
        before=await self.state(); version=(await self.ticket_state(self.ticket()))["version"]
        live=getattr(self.adapter,"live_sqlite",False) is True
        holder=other=None
        try:
            if live:
                lock=await self.adapter.command("hold_write_lock")
                pragmas=await self.adapter.observe("app_connection_pragmas")
                if lock.get("held") is not True or not lock.get("connection_id") or not pragmas:
                    raise AdapterUnavailable("owned live SQLite write-lock observation absent")
                ids={p["connection_id"] for p in pragmas}
                self.check("distinct_connections",lock["connection_id"] not in ids,
                    {"lock_connection":lock["connection_id"],"app_connections":sorted(ids)},"actual separate live-volume connection holds BEGIN IMMEDIATE; no exported copy lock")
            else:
                holder=self.connect();other=self.connect()
                self.check("distinct_connections",holder is not other,{"different_objects":holder is not other},"two actual independent-fixture SQLite connections")
                other.close(); holder.execute("BEGIN IMMEDIATE")
            start=time.monotonic()
            response=await self.patch({"priority":"high","expected_version":version})
            elapsed=time.monotonic()-start
            configured=await self.adapter.observe("db_busy_timeout_ms")
            waits=await self.adapter.observe("db_busy_waits") if live else []
            measured=max((p["elapsed_seconds"] for p in waits),default=elapsed)
            if live and not waits: raise AdapterUnavailable("actual SQLite busy wait timing absent")
            self.check("busy",response.status_code==503 and self.error(response,"DB_BUSY") and
                0 <= configured <=5000 and measured<=5.5,
                {"status":response.status_code,"body":self.body(response),"http_elapsed_seconds":elapsed,"sqlite_busy_elapsed_seconds":measured,"configured_timeout_ms":configured},
                "hold BEGIN IMMEDIATE on independent connection; real PATCH bounded wait <=5s (+0.5s measured HTTP overhead), 503 DB_BUSY")
        finally:
            if live: await self.adapter.command("release_write_lock")
            elif holder is not None: holder.rollback();holder.close()
        after=await self.state()
        self.check("rollback",before==after,{"before_digest":digest(before),"after_digest":digest(after)},"busy refusal leaves ticket/audit/idempotency full DB unchanged")

    async def _ARC04(self):
        await self.prepare(migration_scenario=True)
        fresh=await self.adapter.command("migrate_fresh")
        if getattr(self.adapter,"live_sqlite",False) is True:
            schema=await self.adapter.observe("schema")
            present={r["name"] for r in schema["tables"]};version=schema["user_version"]
        else:
            con=self.connect()
            try:
                present={r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                version=con.execute("PRAGMA user_version").fetchone()[0]
            finally: con.close()
        self.check("fresh_migration",fresh.get("exit_code")==0 and
            {self.table(t) for t in ("users","sessions","tickets","messages","ticket_events","idempotency_keys")}<=present,
            {"runner":fresh,"tables":sorted(present)},"reviewed migration command on disposable empty DB")
        self.check("schema_version",version>=1,{"version":version},"schema migration version visible independently")
        await self.adapter.command("populate_migration_fixture")
        before=await self.database_state("full_database_state")
        replay=await self.adapter.command("migrate_replay")
        after=await self.database_state("full_database_state")
        self.check("replay",replay.get("exit_code")==0 and bool(before) and before==after,
            {"runner":replay,"before_digest":digest(before),"after_digest":digest(after)},"rerun migration with all table rows/sessions/keys retained, no drop/reseed")

    async def _ARC05(self):
        counts=[]; traces=[]
        for n in (1,50):
            await self.prepare(query_count=n)
            await self.adapter.login("camille"); await self.adapter.command("sql_trace_start")
            r=await self.req("camille","GET","/api/tickets",params={"page_size":50})
            trace=await self.adapter.observe("sql_trace")
            if not isinstance(trace,list) or not trace: raise AdapterUnavailable("actual SQL trace absent")
            selects=[q for q in trace if str(q).lstrip().upper().startswith("SELECT")]
            # SQLite trace callbacks expand bound literals, including session hashes.
            safe_selects=[re.sub(r"'(?:''|[^'])*'", "'[bound]'",str(q)) for q in selects]
            counts.append(len(selects)); traces.append(safe_selects)
            self.check("query_counts",r.status_code==200 and self.body(r).get("total")==n,
                       {"ticket_count":n,"select_count":len(selects),"queries":safe_selects},"compare actual SQL requests for one vs fifty fixture tickets (bound literals redacted)")
        signatures=[Counter(re.sub(r"\s+"," ",q).strip().lower() for q in queries) for queries in traces]
        per_ticket=[q for q,count in signatures[1].items() if count>=50 and signatures[0].get(q)==1 and
                    "where" in q and "ticket" in q]
        self.check("query_counts",not per_ticket,{"counts_1_50":counts,"scaled_related_queries":per_ticket},
                   "same related-ticket SELECT shape executed once for one row and >=50 times for fifty rows: concrete N+1, no arbitrary total-query/time threshold")
        plan=await self.adapter.observe("query_plan")
        self.check("query_plan",isinstance(plan,list) and bool(plan),{"query_plan":plan},"real EXPLAIN QUERY PLAN for list/messages, reviewed query symbols")

    async def _ARC06(self):
        await self.prepare(); r=await self.req(None,"GET","/openapi.json"); spec=self.body(r)
        paths=spec.get("paths",{})
        # Parameter spelling is immaterial; canonical structure/methods are not.
        normalized={re.sub(r"\{[^}]+\}","{id}",p):set(methods) for p,methods in paths.items()}
        absent={p:sorted(methods-normalized.get(p,set())) for p,methods in ROUTES.items() if not methods<=normalized.get(p,set())}
        self.check("openapi",r.status_code==200 and not absent and bool(spec.get("components",{}).get("schemas")),
                   {"status":r.status_code,"missing":absent,"schema_names":list(spec.get("components",{}).get("schemas",{}))},
                   "actual OpenAPI GET; required routes/methods and concrete schemas")
        for extra in ({"owner_id":str(uuid4())},{"unexpected":True},{"version":2}):
            response=await self.create(**extra)
            self.check("validation",response.status_code==422,{"status":response.status_code,"fields":list(extra)},"strict creation schema rejects unknown/server fields")
            body=self.body(response)
            self.check("error_dto",isinstance(body.get("error"),dict) and isinstance(body["error"].get("code"),str) and
                isinstance(body["error"].get("message"),str) and bool(body["error"]["message"]),body,"errors shaped {error:{code,message,fields?}}")

    async def _ARC07(self):
        await self.prepare()
        for path,actor,sort in (("/api/users","emma","email"),("/api/assignees","camille","email"),
            ("/api/tickets","camille","tickets"),(f"/api/tickets/{self.ticket()}/messages","camille","created"),
            (f"/api/tickets/{self.ticket()}/history","camille","created")):
            for params,code in (({"page":0},422),({"page_size":51},422),({"page":1,"page_size":1},200),({"page_size":50},200)):
                before=await self.state(); r=await self.req(actor,"GET",path,params=params); body=self.body(r)
                self.check("bounds",r.status_code==code,{"path":path,"params":params,"status":r.status_code},"all lists including directories enforce page bounds")
                if code==422:
                    self.check("refused_unchanged",before==await self.state(),{"path":path,"unchanged":before==await self.state()},"refused list query has no business DB effect")
                if r.status_code==200:
                    items=body.get("items",[])
                    self.check("totals",isinstance(body.get("total"),int) and len(items)<=params.get("page_size",20) and
                        body.get("page")==params.get("page",1) and body.get("page_size")==params.get("page_size",20),body,"bounded list envelope exact page/size/total")
                    if sort=="email": keys=[(i.get("email_normalized",i.get("email","")).strip().lower(),str(i.get("id"))) for i in items]
                    elif sort=="created": keys=[(i.get("created_at",""),str(i.get("id"))) for i in items]
                    else: keys=[(i.get("updated_at",""),str(i.get("id"))) for i in items]
                    self.check("sorts",keys==sorted(keys,reverse=sort=="tickets"),{"path":path,"keys":keys},"email ASC / messages+history created ASC / tickets updated DESC, ID tie-break")
                    self.check("no_secrets",not self._secret_fields(body),{"path":path,"secret_fields":self._secret_fields(body)},"public list DTO has no password/hash/session/token fields")
        r=await self.req("alice","GET",f"/api/tickets/{self.ticket()}"); body=self.body(r)
        collections={k:v for k,v in body.items() if k in {"messages","events","history"} and isinstance(v,list)}
        self.check("detail",r.status_code==200 and not any(len(v)>50 for v in collections.values()),
                   {"status":r.status_code,"collection_lengths":{k:len(v) for k,v in collections.items()}},"ticket detail has no observed unbounded embedded messages/events")
        if collections:
            self._limits[self._rid].append("embedded collection bound unproven; need overflow fixture or explicit bounded envelope")

    @classmethod
    def _secret_fields(cls,value,path=""):
        found=[]
        if isinstance(value,dict):
            for k,v in value.items():
                if re.search(r"password|hash|session|cookie|csrf|token",k,re.I): found.append(path+"."+k)
                found.extend(cls._secret_fields(v,path+"."+k))
        elif isinstance(value,list):
            for i,v in enumerate(value): found.extend(cls._secret_fields(v,f"{path}[{i}]"))
        return found

    async def _ARC08(self):
        await self.prepare(timestamp_ties=True)
        r=await self.message(); body=self.body(r)
        timestamp=body.get("created_at","")
        self.check("utc",r.status_code==201 and isinstance(timestamp,str) and timestamp.endswith(("Z","+00:00")),
                   {"status":r.status_code,"created_at":timestamp},"actual server timestamp explicitly UTC")
        r=await self.req("camille","GET","/api/tickets",params={"page_size":50})
        ids=[i.get("id") for i in self.body(r).get("items",[])]; expected=self.adapter.manifest.metadata.get("tie_expected")
        if expected is None: raise AdapterUnavailable("independent equal-timestamp ordering fixture absent")
        self.check("ties",r.status_code==200 and ids==expected,{"expected":expected,"observed":ids},"same timestamps sort by UUID DESC independent of insert order")
        await self.adapter.login("alice"); await self.adapter.advance_clock(8*3600-1)
        before=await self.req("alice","GET","/api/auth/me",authenticate=False)
        await self.adapter.advance_clock(1)
        after=await self.req("alice","GET","/api/auth/me",authenticate=False)
        self.check("clock",before.status_code==200 and after.status_code==401,
                   {"before":before.status_code,"at_8h":after.status_code},"injectable clock: absolute 8h expiration without activity extension")
