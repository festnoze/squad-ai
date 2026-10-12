"""Trusted Playwright observers against an isolated HTTP product origin.

UI bindings locate controls; they do not define or weaken source expectations.
No product configuration, npm script or Python module is executed on the host.
Only negative network scenarios intercept traffic. Nominal auth is the real UI.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from uuid import uuid4
from types import SimpleNamespace

from .support_adapter import AdapterUnavailable, Proof
from .quality_contracts import source_e2e_scenarios

BROWSER_IDS = tuple(f"UX-{i:02d}" for i in range(1, 9)) + ("SEC-10", "SEC-12", "FUN-02", "FUN-06", "FUN-12")
BROWSER_NETWORK_LIMITS = ["HTTP(S) interception, blocked Service Workers and denied WebSockets are browser API guards, not an OS sandbox.",
    "WebRTC/UDP and other non-HTTP transports are not qualified; hostile browser code needs an external OS/network boundary."]


async def browser_smoke(harness, snapshot_hash, contract_hash, actor_fixture, *, title, description, viewport_width=1280):
    """Narrow real-browser foundation proof, NOT a SEC/FUN/UX acceptance verdict.

    The runtime owner verifies APIread and DBcommit from the returned ticket ID.
    Credentials come from an explicit isolated fixture; no session is injected.
    """
    adapter = harness.adapter
    async def identity():
        if await adapter.snapshot_hash() != snapshot_hash or await adapter.contract_hash() != contract_hash:
            raise ValueError("browser smoke oracle/snapshot changed")
    await identity()
    owner = SimpleNamespace(harness=harness, profile={"desktop_width":viewport_width}, snapshot=snapshot_hash, contract_hash=contract_hash)
    case = _BrowserCase(owner, "VERTICAL")
    ticket_id, limits = None, []
    try:
        page = await case.page()
        await harness.control(page,"email").fill(actor_fixture.email)
        await harness.control(page,"password").fill(actor_fixture.password)
        async with page.expect_response(lambda r: r.request.method=="POST" and urlsplit(r.url).path=="/api/auth/login") as response:
            await harness.control(page,"login").click()
        case.check("browser_login", (await response.value).status, 200)
        case.check("authenticated_list", await case.visible(page,"ticket_list"))
        await case.capture(page,"browser_login")
        await harness.control(page,"create").click()
        await harness.control(page,"title").fill(title)
        await harness.control(page,"description").fill(description)
        async with page.expect_response(lambda r: r.request.method=="POST" and urlsplit(r.url).path=="/api/tickets") as response:
            await harness.control(page,"submit").click()
        created = await response.value
        case.check("browser_create", created.status, 201)
        if created.status==201:
            ticket_id = (await created.json()).get("id")
        case.check("server_ticket_id", isinstance(ticket_id,str) and bool(ticket_id))
        case.check("detail_navigation", await case.visible(page,"detail"))
        await case.capture(page,"browser_create")
        case.check("unhandled_console", case.console_errors, [])
    except AdapterUnavailable as exc:
        limits.append(str(exc))
    except Exception as exc:
        case.check("interaction", type(exc).__name__, "completed")
    finally:
        await harness.close()
    await identity()
    if case.checks:
        root = adapter.evidence_root; root.mkdir(parents=True,exist_ok=True)
        path = root/("VERTICAL-"+uuid4().hex+".json")
        path.write_text(json.dumps({"snapshot_hash":snapshot_hash,"contract_hash":contract_hash,"checks":case.checks,
                                   "requests":case.requests},ensure_ascii=False,indent=2),encoding="utf-8")
        case.proofs.append(Proof("X",str(path),hashlib.sha256(path.read_bytes()).hexdigest(),snapshot_hash,contract_hash,
                                 tuple(x["check"] for x in case.checks),all(x["passed"] for x in case.checks)))
    failed = any(not x["passed"] for x in case.checks)
    return {"status":"FAIL" if failed else "NOT_VERIFIED" if limits or not ticket_id else "PASS",
            "scope":"vertical browser login/create only, not product acceptance", "ticket_id":ticket_id,
            "proofs":case.proofs,"limits":limits,"contract_hash":contract_hash,"snapshot_hash":snapshot_hash,
            "environment_limits":harness.environment_limits,
            "browser_environment":harness.browser_environment}


def browser_generation_requirements(contract):
    profiles = [f for f in contract.facts if f.kind == "browser_profile"]
    requirements = {r.id: r for r in contract.requirements}
    if len(profiles) != 1 or not set(BROWSER_IDS) <= set(profiles[0].requirement_ids):
        raise AdapterUnavailable("reviewed browser profile missing")
    return {"contract_hash": contract.contract_hash, "brief_hash": contract.brief_hash,
            "reference_hash": contract.reference_hash, "formal_profile": profiles[0].expected,
            "requirements": [{"id": rid, "expected": requirements[rid].expected,
                               "evidence": list(requirements[rid].required_evidence)} for rid in BROWSER_IDS],
            "scenarios": source_e2e_scenarios(contract),
            "instructions": ["Keep uncertainty payload and UUID unchanged until explicit replay, no automatic reapplication after 409.",
                             "A real 401 must clear private caches/drafts and route to login; role switches cannot reveal previous data.",
                             "An obsolete search response cannot replace the current result; filters/page survive URL reload.",
                             "UI bindings are reviewed locator metadata, not permission to change these frozen expectations."]}


class PlaywrightHarness:
    """Remote NETNONE browser for products; explicit local trusted-fixture only."""
    def __init__(self, adapter, *, bindings: dict, routes: dict, executable_path=None,
                 trusted_fixture_local_browser=False):
        origin = urlsplit(adapter.base_url)
        if origin.scheme not in {"http", "https"} or origin.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("isolated loopback browser origin required")
        self.adapter, self.bindings, self.routes = adapter, bindings, routes
        self.executable_path = executable_path
        if type(trusted_fixture_local_browser) is not bool:
            raise ValueError("explicit trusted-fixture browser flag required")
        self.trusted_fixture_local_browser=trusted_fixture_local_browser
        self.playwright = self.browser = None
        self.docker_browser=None
        self.browser_environment={"qualified":False}
        self.contexts = []

    @property
    def environment_limits(self):
        if self.browser_environment.get("host_chromium") is False:
            return ["Docker Linux kernel/daemon and constant factory image are trusted; Chromium's internal sandbox is not attested.",
                "Browser shares only the exact product NETNONE network namespace: product/control loopback remains reachable, no host/client network exposure."]
        return BROWSER_NETWORK_LIMITS

    async def start(self):
        try:
            self.browser_environment={"qualified":False}
            runtime=getattr(self.adapter,"supervised_runtime",None)
            if runtime is None and (getattr(self.adapter,"live_sqlite",False) or not self.trusted_fixture_local_browser):
                raise AdapterUnavailable("product browser requires an exact supervised NETNONE runtime; no host fallback")
            if runtime is not None:
                if self.executable_path is not None:
                    raise AdapterUnavailable("host Chromium override forbidden for supervised product browser")
                from .docker_browser import DockerBrowserSession
                self.docker_browser=DockerBrowserSession(runtime,origin=self.adapter.base_url)
                await asyncio.to_thread(self.docker_browser.start)
            from playwright.async_api import async_playwright
            self.playwright = await async_playwright().start()
            if self.docker_browser is not None:
                # Empty exposure explicitly denies the connecting host's network.
                self.browser=await self.playwright.chromium.connect(self.docker_browser.endpoint,timeout=10000,expose_network="")
                self.browser_environment=dict(self.docker_browser.receipt,qualified=True)
            else:
                self.browser=await self.playwright.chromium.launch(headless=True, executable_path=self.executable_path)
                self.browser_environment={"qualified":False,"host_chromium":True,"trusted_fixture_only":True}
        except BaseException as exc:
            await self.close()
            if not isinstance(exc,Exception): raise
            # The underlying driver's connection error can contain the private
            # WS capability. Do not publish it through exception chaining/logs.
            raise AdapterUnavailable("locked isolated Playwright/Chromium unavailable; no host fallback") from None

    async def close(self):
        failure=None
        try:
            if self.contexts:
                try:
                    results=await asyncio.wait_for(asyncio.gather(*(c.close() for c in self.contexts),return_exceptions=True),5)
                    failure=next((x for x in results if isinstance(x,Exception)),None)
                except Exception as exc: failure=exc
            if self.browser:
                try: await asyncio.wait_for(self.browser.close(),5)
                except Exception as exc: failure=exc
        finally:
            self.contexts.clear()
            try:
                if self.docker_browser: await asyncio.to_thread(self.docker_browser.close)
            finally:
                if self.playwright: await asyncio.wait_for(self.playwright.stop(),5)
                self.browser=self.playwright=None
        if failure: raise AdapterUnavailable("owned browser channel cleanup failed") from failure

    def control(self, page, name):
        if name not in self.bindings:
            raise AdapterUnavailable("reviewed UI binding missing: " + name)
        return page.locator(self.bindings[name])

    async def page(self, case, viewport):
        if self.browser is None: await self.start()
        context = await self.browser.new_context(viewport={"width": viewport, "height": 900},service_workers="block")
        self.contexts.append(context)
        origin = urlsplit(self.adapter.base_url)
        allowed = (origin.scheme, origin.netloc)
        async def confined(route):
            target = urlsplit(route.request.url)
            if target.scheme not in {"http", "https", "data", "blob", "about"} or (target.scheme in {"http", "https"} and (target.scheme,target.netloc) != allowed):
                case.check("external_request_blocked", target.scheme+"://"+target.netloc, origin.scheme+"://"+origin.netloc)
                await route.abort()
            else: await route.continue_()
        async def denied_websocket(ws):
            case.check("websocket_attempt_blocked",ws.url,"no WebSocket channel permitted by trusted harness")
            await ws.close(code=1008,reason="trusted harness WebSocket deny policy")
        try:
            await context.route("**/*", confined)
            await context.route_web_socket("**",denied_websocket)
        except Exception as exc:
            await context.close();self.contexts.remove(context)
            raise AdapterUnavailable("HTTP/ServiceWorker/WebSocket guards unavailable before page creation") from exc
        page = await context.new_page()
        page.set_default_timeout(2500)
        page.on("pageerror", lambda error: case.console_errors.append(self.redact(str(error))))
        page.on("console", lambda message: case.console_errors.append(self.redact(message.text)) if
                message.type == "error" and "Failed to load resource" not in message.text else None)
        def request(request):
            path = urlsplit(request.url).path
            if not path.startswith("/api/"): return
            try: payload = request.post_data_json
            except Exception: payload = None
            if path.startswith("/api/auth/"): payload = "[AUTH_INPUT_REDACTED]"
            case.requests.append({"method": request.method, "path": path, "payload": self.redact(payload),
                                  "query": self.redact(parse_qs(urlsplit(request.url).query))})
        page.on("request", request)
        await page.goto(self.adapter.base_url + self.routes["home"])
        return page

    async def guard_probe_route(self,route,case):
        target,origin=urlsplit(route.request.url),urlsplit(self.adapter.base_url)
        if (target.scheme,target.netloc)!=(origin.scheme,origin.netloc):
            case.check("negative_probe_external_request_blocked",target.scheme+"://"+target.netloc,origin.scheme+"://"+origin.netloc)
            await route.abort();return False
        return True

    def redact(self, value):
        if isinstance(value, dict):
            return {k:"[REDACTED]" if any(s in k.lower() for s in ["password","cookie","csrf","token","hash"]) else self.redact(v) for k,v in value.items()}
        if isinstance(value, list): return [self.redact(v) for v in value]
        if isinstance(value, str):
            for account in self.adapter.manifest.accounts.values():
                if account.password: value=value.replace(account.password,"[REDACTED]")
        return value


class _BrowserCase:
    def __init__(self, verifier, rid):
        self.v, self.rid = verifier, rid
        self.checks, self.requests, self.console_errors, self.proofs = [], [], [], []
        self.pages = []

    def check(self, tag, observed, expected=True):
        self.checks.append({"check": self.rid + ":" + tag, "observed": self.v.harness.redact(observed), "expected": self.v.harness.redact(expected), "passed": observed == expected})

    async def page(self):
        page = await self.v.harness.page(self, self.v.profile["desktop_width"])
        self.pages.append(page)
        return page

    async def visible(self, page, name):
        try:
            await self.v.harness.control(page, name).wait_for(state="visible")
            return True
        except Exception:
            return False

    async def capture(self, page, tag):
        root = self.v.harness.adapter.evidence_root
        root.mkdir(parents=True, exist_ok=True)
        # RID:sous-probe remains a proof tag, never an NTFS alternate stream.
        path = root / (self.rid.replace(":","-") + "-" + tag + "-" + uuid4().hex + ".png")
        masks = [page.locator("input[type=password]")] + [page.get_by_text(a.password, exact=False)
                 for a in self.v.harness.adapter.manifest.accounts.values()]
        await page.screenshot(path=str(path), full_page=True, mask=masks)
        self.proofs.append(Proof("V", str(path), hashlib.sha256(path.read_bytes()).hexdigest(), self.v.snapshot,
                                self.v.contract_hash, (self.rid + ":" + tag,), all(x["passed"] for x in self.checks)))


class BrowserVerifier:
    def __init__(self, contract, harness):
        self.contract, self.harness = contract, harness
        self.contract_hash, self.snapshot = contract.contract_hash, ""
        self.created_titles={}
        facts = [f for f in contract.facts if f.kind == "browser_profile"]
        self.profile = facts[0].expected if len(facts) == 1 and set(BROWSER_IDS) <= set(facts[0].requirement_ids) else None

    async def _identity(self):
        if (self.contract.contract_hash != self.contract_hash or await self.harness.adapter.contract_hash() != self.contract_hash or
                await self.harness.adapter.snapshot_hash() != self.snapshot):
            raise ValueError("browser oracle/snapshot changed")

    async def verify(self, snapshot_hash, *, ids=None):
        self.snapshot = snapshot_hash
        await self._identity()
        requirements = {r.id: r for r in self.contract.requirements}
        results = []
        try:
            for rid in ids or BROWSER_IDS:
                if rid not in BROWSER_IDS: raise ValueError("unsupported browser requirement")
                case, limits = _BrowserCase(self, rid), []
                if (not isinstance(self.profile, dict) or not {"timeout_ms","desktop_width","mobile_width","client_ticket_count",
                        "search_a","search_b","search_a_marker","search_b_marker"} <= set(self.profile) or rid not in requirements):
                    limits.append("reviewed browser source profile missing")
                else:
                    try:
                        await self.harness.adapter.prepare_case(rid)
                        method = "_" + rid.lower().replace("-", "")
                        await getattr(self, method)(case)
                        case.check("unhandled_page_errors", case.console_errors, [])
                    except AdapterUnavailable as exc:
                        limits.append(str(exc))
                    except Exception as exc:
                        case.check("interaction_failed", type(exc).__name__, "completed")
                    for page in case.pages:
                        try: await case.capture(page, "final")
                        except Exception: limits.append("browser screenshot unavailable")
                await self._identity()
                if case.checks:
                    root = self.harness.adapter.evidence_root
                    root.mkdir(parents=True, exist_ok=True)
                    path = root / (rid + "-" + uuid4().hex + ".json")
                    path.write_text(json.dumps({"id": rid, "snapshot_hash": self.snapshot, "contract_hash": self.contract_hash,
                        "checks": case.checks, "requests": case.requests, "console_errors": case.console_errors}, ensure_ascii=False, indent=2), encoding="utf-8")
                    case.proofs.append(Proof("X", str(path), hashlib.sha256(path.read_bytes()).hexdigest(), self.snapshot,
                        self.contract_hash, tuple(x["check"] for x in case.checks), all(x["passed"] for x in case.checks)))
                external = []
                try:
                    for proof in await self.harness.adapter.proofs(rid):
                        if proof.intact(snapshot_hash=self.snapshot, contract_hash=self.contract_hash) and any(
                                tag == rid or tag.startswith(rid + ":") for tag in proof.checks):
                            external.append(proof)
                        else: limits.append("stale/unmapped browser proof rejected")
                except Exception: limits.append("external browser evidence unavailable")
                if rid.startswith(("SEC-", "FUN-")) and not any(rid + ":backend" in p.checks for p in external):
                    limits.append("browser contribution only: independent backend probes still required")
                proofs = case.proofs + external
                required = set(requirements[rid].required_evidence) if rid in requirements else {"X", "V"}
                required.add("V")
                missing = required - {p.type for p in proofs}
                if missing: limits.append("missing proof types: " + ",".join(sorted(missing)))
                failed = any(not x["passed"] for x in case.checks) or any(not p.passed for p in proofs)
                results.append({"id": rid, "gate": requirements[rid].gate if rid in requirements else "B",
                    "status": "FAIL" if failed else "NOT_VERIFIED" if limits or not case.checks else "PASS",
                    "expected": requirements[rid].expected if rid in requirements else "source unavailable",
                    "observed": case.checks, "proofs": [p.__dict__ for p in proofs], "limits": limits,
                    "reproduction":case.requests,"impact":"UI source invariant violated" if failed else "",
                    "contract_hash": self.contract_hash, "snapshot_hash": self.snapshot, "layer": "browser"})
                await self.harness.close()
            await self._identity()
        finally:
            await self.harness.close()
            await self.harness.adapter.close()
        return {"pack": "browser", "status": "FAIL" if any(r["status"] == "FAIL" for r in results) else
                "PASS" if all(r["status"] == "PASS" for r in results) else "NOT_VERIFIED",
                "contract_hash": self.contract_hash, "snapshot_hash": self.snapshot, "requirements": results,
                "environment_limits":self.harness.environment_limits,
                "browser_environment":self.harness.browser_environment}

    def ui(self, page, name): return self.harness.control(page, name)

    async def detail_ready(self, page):
        expected=self.created_titles.get(page)
        pattern=re.compile("^"+re.escape(expected)+"$") if expected else re.compile(r"\S")
        await self.ui(page, "detail_title").filter(has_text=pattern).wait_for()

    async def login(self, case, page, actor):
        account = self.harness.adapter.manifest.accounts[actor]
        await self.ui(page, "email").fill(account.email)
        await self.ui(page, "password").fill(account.password)
        async with page.expect_response(lambda r:r.request.method=="POST" and urlsplit(r.url).path=="/api/auth/login") as response:
            await self.ui(page, "login").click()
        case.check("real_login_http_"+actor,(await response.value).status,200)
        # A zero-ticket client has a genuine authenticated empty state. An
        # empty zero-height result container is not a failed authentication.
        case.check("real_login_" + actor, await case.visible(page, "ticket_nav"))

    async def create(self, case, page, title):
        self.created_titles[page]=title
        await self.ui(page, "create").click()
        await self.ui(page, "title").fill(title)
        await self.ui(page, "description").fill("Independent browser probe description long enough")
        await self.ui(page, "submit").click()

    async def _ux01(self, c):
        p = await c.page(); await self.login(c, p, "alice")
        title = "Nominal browser " + uuid4().hex
        await self.create(c, p, title)
        await self.detail_ready(p)
        c.check("creation_to_detail", await c.visible(p, "reply"))
        c.check("created_title_visible", await self.ui(p, "detail").inner_text() and title in await self.ui(p, "detail").inner_text())
        await self.ui(p, "reply").fill("Browser public response")
        await self.ui(p, "send").click()
        await self.ui(p, "messages").get_by_text("Browser public response", exact=True).wait_for()
        c.check("response_confirmation", True)
        c.check("french_document",await p.evaluate("document.documentElement.lang.startsWith('fr')"))
        labels=self.profile.get("french_action_labels")
        if not isinstance(labels,dict) or not labels:
            raise AdapterUnavailable("independently reviewed French action label profile missing")
        for name, expected in labels.items():
            c.check("french_action_"+name,(await self.ui(p,name).inner_text()).strip(),expected)
        for actor in ["camille","emma"]:
            q=await c.page();await self.login(c,q,actor)
            c.check(actor+"_cannot_create",not await self.ui(q,"create").is_visible())
            c.check(actor+"_admin_navigation",await self.ui(q,"admin_nav").is_visible(),actor=="emma")
            await self.ui(q,"dashboard_nav").click()
            await self.ui(q,"dashboard_total").filter(has_text=re.compile(r"\S")).wait_for()
            c.check(actor+"_staff_scope",int(await self.ui(q,"dashboard_total").inner_text()),self.profile["staff_ticket_count"]+1)
            await c.capture(q,"role-"+actor)

    async def _ux02(self, c):
        p = await c.page(); await self.login(c, p, "alice")
        await p.route("**/api/tickets?*", lambda route: self._slow_read(route, .3,c))
        await self.ui(p, "search").fill("nothing-" + uuid4().hex)
        c.check("slow_loading", await c.visible(p, "loading"))
        c.check("empty_state", await c.visible(p, "empty"))
        await c.capture(p,"slow-empty")
        await p.unroute("**/api/tickets?*")
        async def server_error(route):
            if not await self.harness.guard_probe_route(route,c):return
            await route.fulfill(status=500,json={"error":{"code":"CONTROLLED_FAILURE","message":"Erreur contrôlée"}})
        await p.route("**/api/tickets?*",server_error)
        await self.ui(p,"refresh").click()
        c.check("api500_recoverable",await c.visible(p,"error"))
        await self.ui(p,"loading").wait_for(state="hidden")
        c.check("api500_not_empty",not await self.ui(p,"empty").is_visible())
        await c.capture(p,"api500")
        await p.unroute("**/api/tickets?*")
        await p.context.set_offline(True);await self.ui(p,"refresh").click()
        c.check("network_failure_explicit",await c.visible(p,"error"))
        await p.context.set_offline(False)
        await self.ui(p,"search").fill("");await self.ui(p,"refresh").click()
        await self.ui(p,"total").get_by_text(str(self.profile["client_ticket_count"]),exact=True).wait_for()
        c.check("read_reusable_after_failure",await c.visible(p,"ticket_list"))
        refused_title="KNOWN_REFUSAL_"+uuid4().hex
        async def refuse_once(route):
            if not await self.harness.guard_probe_route(route,c):return
            await route.fulfill(status=422,json={"error":{"code":"VALIDATION_ERROR","message":"Refus contrôlé"}})
        await p.route("**/api/tickets",refuse_once)
        async with p.expect_response(lambda r:r.request.method=="POST" and urlsplit(r.url).path=="/api/tickets") as refused:
            await self.create(c,p,refused_title)
        c.check("known_refusal_status",(await refused.value).status,422)
        c.check("known_refusal_draft_conserved",await self.ui(p,"title").input_value(),refused_title)
        c.check("known_refusal_editable",not await self.ui(p,"title").is_disabled())
        c.check("known_refusal_no_object",await self.harness.adapter.observe("browser_operation_count",title=refused_title),0)
        await p.unroute("**/api/tickets")
        await p.keyboard.press("Escape")
        title = "Uncertain " + uuid4().hex
        lost = False
        async def loss(route):
            nonlocal lost
            if not await self.harness.guard_probe_route(route,c):return
            if route.request.method == "POST" and not lost:
                lost = True
                await route.fetch(max_redirects=0)  # real commit, no host-side redirected fetch
                # A blackholed response tests the application's actual HTTP
                # timeout, not a harness-imposed immediate failure.
                try:
                    await p.wait_for_event("requestfailed",predicate=lambda r:r.url==route.request.url and r.method=="POST",
                                           timeout=self.profile["timeout_ms"]+3000)
                except Exception:pass
                try: await route.abort("failed")
                except Exception: pass
            else: await route.continue_()
        await p.route("**/api/tickets", loss)
        started = time.monotonic()
        await self.create(c, p, title)
        try:
            await self.ui(p,"retry").wait_for(state="visible",timeout=self.profile["timeout_ms"]+1000)
            uncertain=True
        except Exception: uncertain=False
        c.check("recoverable_uncertainty", uncertain)
        c.check("bounded_timeout", (time.monotonic()-started)*1000 <= self.profile["timeout_ms"] + 1000)
        c.check("uncertain_payload_frozen", await self.ui(p, "title").is_disabled())
        await self.ui(p, "retry").click()
        c.check("retry_completed", await c.visible(p, "reply"))
        submitted = [r["payload"] for r in c.requests if r["method"] == "POST" and r["path"] == "/api/tickets" and r["payload"]["title"]==title]
        c.check("retry_same_payload_uuid", len(submitted) == 2 and submitted[0] == submitted[1])
        counts = await self.harness.adapter.observe("browser_operation_count", title=title)
        c.check("retry_no_duplicate", counts, 1)
        await self.detail_ready(p)
        tid=urlsplit(p.url).path.rsplit("/",1)[-1]
        message="MESSAGE_UNCERTAINTY_"+uuid4().hex
        message_lost=False
        async def lost_message(route):
            nonlocal message_lost
            if not await self.harness.guard_probe_route(route,c):return
            if route.request.method=="POST" and not message_lost:
                message_lost=True;await route.fetch(max_redirects=0);await route.abort("failed")
            else:await route.continue_()
        await p.route("**/api/tickets/*/messages",lost_message)
        await self.ui(p,"reply").fill(message);await self.ui(p,"send").click()
        c.check("message_uncertain_replay",await c.visible(p,"reply_retry"))
        c.check("message_uncertain_frozen",await self.ui(p,"reply").is_disabled())
        await self.ui(p,"reply_retry").click()
        await self.ui(p,"messages").get_by_text(message,exact=True).wait_for()
        submitted=[r["payload"] for r in c.requests if r["method"]=="POST" and r["path"]==f"/api/tickets/{tid}/messages"]
        c.check("message_same_payload_uuid",len(submitted)==2 and submitted[0]==submitted[1])
        c.check("message_retry_no_duplicate",await self.harness.adapter.observe("browser_message_count",ticket_id=tid,content=message),1)
        c.check("message_form_reusable",not await self.ui(p,"reply").is_disabled())

    async def _slow_read(self, route, seconds,case):
        if not await self.harness.guard_probe_route(route,case):return
        response = await route.fetch(max_redirects=0); await asyncio.sleep(seconds); await route.fulfill(response=response)

    async def _ux03(self, c):
        p = await c.page(); await self.login(c, p, "alice")
        await p.keyboard.press("Tab");await self.ui(p, "create").focus()
        c.check("focus_visible",await self.ui(p,"create").evaluate("e=>{const s=getComputedStyle(e);return s.outlineStyle!=='none'&&parseFloat(s.outlineWidth)>0}"))
        await c.capture(p,"keyboard-focus")
        await p.keyboard.press("Enter")
        c.check("modal_keyboard_open", await c.visible(p, "modal"))
        modal = self.harness.bindings["modal"]
        for _ in range(9):
            await p.keyboard.press("Tab")
            c.check("focus_confined", await p.evaluate("s=>!!document.querySelector(s)?.contains(document.activeElement)", modal))
        await p.keyboard.press("Escape")
        c.check("escape_closes", not await self.ui(p, "modal").is_visible())
        c.check("focus_return", await self.ui(p, "create").evaluate("e=>e===document.activeElement"))
        await self.ui(p, "create").click(); await self.ui(p, "submit").click()
        c.check("field_error_associated", await self.ui(p, "title").evaluate("e=>e.getAttribute('aria-invalid')==='true' && !!document.getElementById(e.getAttribute('aria-describedby'))"))
        for name in ["title","description","email","password"]:
            c.check("accessible_label_"+name,await self.ui(p,name).evaluate("e=>e.labels?.length>0"))
        await p.keyboard.press("Escape");await self.ui(p,"logout").focus();await p.keyboard.press("Enter")
        await self.ui(p,"email").wait_for();await self.ui(p,"email").focus();await p.keyboard.press("Tab")
        c.check("login_logical_tab",await self.ui(p,"password").evaluate("e=>e===document.activeElement"))

    async def _ux04(self, c):
        p = await c.page(); await self.login(c, p, "alice")
        await self.create(c,p,"MOTLONG"*15);await self.detail_ready(p)
        for width in [self.profile["desktop_width"], self.profile["mobile_width"]]:
            await p.set_viewport_size({"width": width, "height": 900})
            c.check("no_global_overflow_"+str(width), await p.evaluate("document.documentElement.scrollWidth<=window.innerWidth"))
            c.check("actions_visible_"+str(width), await self.ui(p, "create").is_visible())
            c.check("actions_not_clipped_"+str(width),await self.ui(p,"create").evaluate("e=>{let r=e.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth&&r.top>=0&&r.bottom<=innerHeight}"))
            c.check("status_not_color_only_"+str(width),bool((await self.ui(p,"detail_status").inner_text()).strip()))
            await c.capture(p, "viewport-"+str(width))

    async def _ux05(self, c):
        p = await c.page(); await self.login(c, p, "alice")
        private_title="ALICE_PRIVATE_TICKET_"+uuid4().hex
        await self.create(c,p,private_title);await self.detail_ready(p)
        await self.ui(p,"reply").fill("ALICE_PRIVATE_REPLY_DRAFT")
        await self.ui(p, "create").click()
        marker = "ALICE_PRIVATE_DRAFT_" + uuid4().hex
        await self.ui(p, "title").fill(marker)
        await p.keyboard.press("Escape")
        await self.ui(p, "logout").click()
        c.check("logout_login_screen", await c.visible(p, "email"))
        await self.login(c, p, "bob")
        c.check("role_switch_no_residue", await self._private_clean(p, [marker,private_title,"ALICE_PRIVATE_REPLY_DRAFT"]))
        await self.ui(p, "logout").click(); await self.login(c, p, "alice")
        await self.harness.adapter.command("expire_actor", actor="alice")
        await self.ui(p, "refresh").click()
        c.check("real_401_routes_login", await c.visible(p, "email"))
        c.check("401_purges_private", await self._private_clean(p, [marker]))
        await self.login(c,p,"alice")
        admin_email=self.harness.adapter.manifest.accounts["emma"].email
        await p.add_init_script("window.__private_transient=false;new MutationObserver(()=>{if(document.body?.innerText.includes("+json.dumps(admin_email)+"))window.__private_transient=true}).observe(document,{subtree:true,childList:true})")
        await p.goto(self.harness.adapter.base_url+self.harness.routes["admin"])
        c.check("admin_route_refused",await c.visible(p,"error"))
        c.check("admin_no_transient",await p.evaluate("window.__private_transient===false"))
        c.check("admin_no_private_cache",await self._private_clean(p,[admin_email]))

    async def _private_clean(self, p, markers):
        return await p.evaluate("ms=>{const data=document.documentElement.outerHTML+document.body.innerText+[...document.querySelectorAll('input,textarea,select')].map(e=>e.value).join('|')+JSON.stringify(localStorage)+JSON.stringify(sessionStorage);return ms.every(m=>!data.includes(m))}", markers)

    async def _ux06(self, c):
        p = await c.page(); await self.login(c, p, "alice")
        delivered_a = asyncio.Event(); release_a = asyncio.Event(); completed_a = asyncio.Event()
        a, b = self.profile["search_a"], self.profile["search_b"]
        async def reverse(route):
            if not await self.harness.guard_probe_route(route,c):return
            response = await route.fetch(max_redirects=0)
            if parse_qs(urlsplit(route.request.url).query).get("q") == [a]:
                delivered_a.set(); await release_a.wait()
            try: await route.fulfill(response=response)
            except Exception: pass  # cancellation is a valid anti-stale mechanism
            finally:
                if parse_qs(urlsplit(route.request.url).query).get("q") == [a]: completed_a.set()
        await p.route("**/api/tickets?*", reverse)
        await self.ui(p, "search").fill(a)
        await asyncio.wait_for(delivered_a.wait(), 3)
        async with p.expect_response(lambda r: parse_qs(urlsplit(r.url).query).get("q") == [b]) as response_b:
            await self.ui(p, "search").fill(b)
        b_body = await (await response_b.value).json()
        await p.wait_for_function("args=>document.querySelector(args[0])?.textContent===String(args[1])",
                                 arg=[self.harness.bindings["total"], b_body["total"]])
        await self.ui(p, "ticket_list").get_by_text(self.profile["search_b_marker"], exact=False).wait_for()
        release_a.set(); await asyncio.wait_for(completed_a.wait(), 3); await asyncio.sleep(1)
        text = await self.ui(p, "ticket_list").inner_text()
        c.check("late_a_cannot_replace_b", self.profile["search_b_marker"] in text and self.profile["search_a_marker"] not in text)
        c.check("search_in_url", parse_qs(urlsplit(p.url).query).get("q"), [b])
        await p.reload(); c.check("search_survives_reload", await self.ui(p, "search").input_value(), b)
        await self.ui(p,"search").fill("")
        await self.ui(p,"total").get_by_text(str(self.profile["client_ticket_count"]),exact=True).wait_for()
        await self.ui(p,"page_next").click()
        await p.wait_for_function("new URLSearchParams(location.search).get('page')==='2'")
        await p.reload()
        c.check("page_survives_reload",parse_qs(urlsplit(p.url).query).get("page"),["2"])
        await self.ui(p,"priority_filter").select_option("high")
        await p.wait_for_function("new URLSearchParams(location.search).get('priority')==='high'")
        c.check("filter_resets_page1",parse_qs(urlsplit(p.url).query).get("page"),["1"])
        await p.reload();c.check("filter_survives_reload",await self.ui(p,"priority_filter").input_value(),"high")
        await self.ui(p,"status_filter").select_option("closed")
        await p.wait_for_function("new URLSearchParams(location.search).get('status')==='closed'")
        c.check("status_resets_page1",parse_qs(urlsplit(p.url).query).get("page"),["1"])
        await p.reload();c.check("status_survives_reload",await self.ui(p,"status_filter").input_value(),"closed")
        staff=await c.page();await self.login(c,staff,"camille")
        for mode,param in [("mine","assigned_to_me"),("unassigned","unassigned")]:
            await self.ui(staff,"page_next").click()
            await self.ui(staff,"assignment_filter").select_option(mode)
            await staff.wait_for_function("p=>new URLSearchParams(location.search).get(p)==='true'",arg=param)
            c.check("assignment_resets_page1_"+mode,parse_qs(urlsplit(staff.url).query).get("page"),["1"])
            await staff.reload();c.check("assignment_survives_reload_"+mode,await self.ui(staff,"assignment_filter").input_value(),mode)

    async def _ux07(self, c, *, doubleclick=True):
        p = await c.page(); await self.login(c, p, "camille")
        q = await c.page(); await self.login(c, q, "dylan")
        path = self.harness.routes["ticket"].format(id=self.harness.adapter.manifest.tickets["alice_open"])
        await p.goto(self.harness.adapter.base_url+path); await q.goto(self.harness.adapter.base_url+path)
        await self.detail_ready(p); await self.detail_ready(q)
        draft = "CONFLICT_DRAFT_" + uuid4().hex
        await self.ui(q, "reply").fill(draft)
        await self.ui(p, "priority").select_option("high")
        async with p.expect_response(lambda r: r.request.method=="PATCH") as first:
            await self.ui(p, "apply").click()
        c.check("first_patch_success", (await first.value).status, 200)
        await self.ui(q, "priority").select_option("low"); await self.ui(q, "apply").click()
        c.check("conflict_is_explicit", await c.visible(q, "conflict"))
        c.check("draft_conserved", await self.ui(q, "reply").input_value(), draft)
        async with q.expect_response(lambda r: r.request.method=="GET" and urlsplit(r.url).path.endswith("/messages")) as reloaded:
            await self.ui(q, "reload").click()
        await (await reloaded.value).body()
        await self.detail_ready(q)
        c.check("reload_conserves_draft", await self.ui(q, "reply").input_value(), draft)
        state = await self.harness.adapter.observe("ticket_state", ticket_id=self.harness.adapter.manifest.tickets["alice_open"])
        c.check("no_automatic_reapplication", state["priority"], "high")
        await self.ui(q,"send").click()
        await self.ui(q,"messages").get_by_text(draft,exact=True).wait_for()
        c.check("form_reusable_after_conflict",await self.harness.adapter.observe("browser_message_count",ticket_id=self.harness.adapter.manifest.tickets["alice_open"],content=draft),1)
        if doubleclick:
            client=await c.page();await self.login(c,client,"alice")
            title="DOUBLE_CLICK_"+uuid4().hex
            await self.ui(client,"create").click();await self.ui(client,"title").fill(title)
            await self.ui(client,"description").fill("Independent double click description long enough")
            await self.ui(client,"submit").dblclick();await self.detail_ready(client)
            c.check("doubleclick_one_object",await self.harness.adapter.observe("browser_operation_count",title=title),1)

    async def _ux08(self, c):
        p = await c.page(); await self.login(c, p, "camille")
        path = self.harness.routes["ticket"].format(id=self.harness.adapter.manifest.tickets["alice_open"])
        await p.goto(self.harness.adapter.base_url+path)
        c.check("staff_visibility_explicit", await c.visible(p, "visibility"))
        await self.ui(p, "visibility").select_option("internal")
        await self.ui(p, "reply").fill("INTERNAL_BROWSER_PROBE")
        await self.ui(p, "send").click()
        await self.ui(p, "messages").get_by_text("INTERNAL_BROWSER_PROBE", exact=True).wait_for()
        c.check("note_label_not_color_only", "interne" in (await self.ui(p, "messages").inner_text()).lower())
        internal=self.ui(p,"messages").locator(self.harness.bindings["internal_note"])
        c.check("internal_structure",await internal.count()>0)
        c.check("internal_distinct_not_color_only",await internal.first.evaluate("e=>parseFloat(getComputedStyle(e).borderLeftWidth)>0"))
        q = await c.page(); await self.login(c, q, "alice"); await q.goto(self.harness.adapter.base_url+path)
        await self.ui(q, "visibility").wait_for(state="hidden")
        c.check("client_visibility_absent", not await self.ui(q, "visibility").is_visible())
        scan = await self.harness.adapter.observe("frontend_api_origin_scan")
        c.check("no_hardcoded_backend_origin", scan["absolute_api_urls"], [])
        if not scan["scanned_files"]: raise AdapterUnavailable("bundle/source origin scan missing")
        for artifact in scan["scanned_files"]:
            if hashlib.sha256(Path(artifact["path"]).read_bytes()).hexdigest() != artifact["sha256"]:
                raise AdapterUnavailable("bundle/source scan snapshot stale")

    async def _sec10(self, c):
        p=await c.page();await self.login(c,p,"alice")
        markers=self.harness.adapter.manifest.metadata["internal_markers"]
        markers=markers+[self.harness.adapter.manifest.metadata["internal_author_id"]]
        for key in ["alice_mixed","alice_internal_only"]:
            tid=self.harness.adapter.manifest.tickets[key]
            await p.goto(self.harness.adapter.base_url+self.harness.routes["ticket"].format(id=tid));await self.detail_ready(p)
            async with p.expect_response(lambda r:urlsplit(r.url).path.endswith("/messages")) as messages:
                await self.ui(p,"refresh").click()
            body=await(await messages.value).json()
            c.check(key+"_json_private_absent",not any(m in json.dumps(body) for m in markers))
            c.check(key+"_dom_private_absent",await self._private_clean(p,markers))
            c.check(key+"_no_internal_selector",not await self.ui(p,"visibility").is_visible())
            # Network response samples include each pagination boundary, not a
            # React-side filtered list inferred from the DOM.
            for page in [1,2]:
                response=await p.request.get(self.harness.adapter.base_url+f"/api/tickets/{tid}/messages?page={page}&page_size=1",max_redirects=0)
                data=await response.json();c.check(key+"_page"+str(page)+"_private_absent",not any(m in json.dumps(data) for m in markers))
                c.requests.append({"method":"GET","path":f"/api/tickets/{tid}/messages","query":{"page":page,"page_size":1},"status":response.status})
            history=await p.request.get(self.harness.adapter.base_url+f"/api/tickets/{tid}/history?page_size=50",max_redirects=0)
            history_text=await history.text()
            c.check(key+"_events_absent",not any(m in history_text for m in markers))
        await self.ui(p,"ticket_nav").click()
        for marker in self.harness.adapter.manifest.metadata["internal_markers"]:
            await self.ui(p,"search").fill(marker)
            await self.ui(p,"total").get_by_text("0",exact=True).wait_for()
            c.check("internal_search_zero",await self.ui(p,"total").inner_text(),"0")
        await self.ui(p,"logout").click();await self.ui(p,"email").wait_for();await self.login(c,p,"bob")
        c.check("account_switch_private_absent",await self._private_clean(p,markers))

    async def _sec12(self, c):
        p=await c.page();await self.login(c,p,"alice")
        staff=await c.page();await self.login(c,staff,"camille")
        admin=await c.page();await self.login(c,admin,"emma")
        for payload in ["<script>window.__security_probe=1</script>","<img src=x onerror=window.__security_probe=1>","O'Reilly %_ ' OR 1=1 --"]:
            await self.create(c,p,payload);await self.detail_ready(p)
            c.check("literal_title",payload in await self.ui(p,"detail").inner_text())
            tid=urlsplit(p.url).path.rsplit("/",1)[-1]
            for page,visibility in [(p,"public"),(staff,"internal")]:
                if page is staff:
                    await page.goto(self.harness.adapter.base_url+self.harness.routes["ticket"].format(id=tid));await self.detail_ready(page)
                    await self.ui(page,"visibility").select_option(visibility)
                await self.ui(page,"reply").fill(payload)
                async with page.expect_response(lambda r:r.request.method=="POST" and urlsplit(r.url).path==f"/api/tickets/{tid}/messages") as sent:
                    await self.ui(page,"send").click()
                c.check("literal_http_"+visibility,(await sent.value).status,201)
                messages=self.ui(page,"messages")
                if visibility=="internal":messages=messages.locator(self.harness.bindings["internal_note"])
                await messages.get_by_text(payload,exact=True).wait_for()
                c.check("literal_"+visibility,await messages.get_by_text(payload,exact=True).is_visible())
                c.check("no_js_"+visibility,await page.evaluate("window.__security_probe===undefined"))
                c.check("one_literal_db_message_"+visibility,await self.harness.adapter.observe("browser_message_count",ticket_id=tid,content=payload),1 if visibility=="public" else 2)
            uid=await self._create_account_ui(c,admin,role="agent",actor="xss_actor",display_name=payload)
            await self.ui(admin,"users").get_by_text(re.compile(re.escape(payload))).wait_for()
            c.check("literal_account_name",payload in await self.ui(admin,"users").inner_text())
            c.check("no_js_name",await admin.evaluate("window.__security_probe===undefined"))

    async def _fun02(self, c):
        p = await c.page(); await self.login(c, p, "alice")
        c.check("client_count", await self.ui(p, "total").inner_text(), str(self.profile["client_ticket_count"]))
        path = self.harness.routes["ticket"].format(id=self.harness.adapter.manifest.tickets["alice_open"])
        await p.goto(self.harness.adapter.base_url+path); await self.detail_ready(p); c.check("known_detail", await c.visible(p, "reply"))
        await p.goto(self.harness.adapter.base_url+self.harness.routes["ticket"].format(id=str(uuid4())))
        await self.ui(p, "error").wait_for()
        c.check("missing_clears_previous_detail", not await self.ui(p, "reply").is_visible())
        c.check("missing_error", await c.visible(p, "error"))

    async def _fun06(self, c): await self._ux07(c)

    async def _fun12(self, c):
        p = await c.page(); await self.login(c, p, "alice")
        expected=self.harness.adapter.manifest.metadata["dashboard_expected"]["alice"]
        await self.ui(p, "dashboard_nav").click()
        await self.ui(p, "dashboard_total").filter(has_text=re.compile(r"\S")).wait_for()
        c.check("scoped_dashboard", await self.ui(p, "dashboard_total").inner_text(), str(self.profile["client_ticket_count"]))
        await self._dashboard_check(c,p,expected)
        await p.reload()
        await self.ui(p, "dashboard_total").filter(has_text=re.compile(r"\S")).wait_for()
        c.check("dashboard_reload", await self.ui(p, "dashboard_total").inner_text(), str(self.profile["client_ticket_count"]))
        await self.create(c,p,"COUNTER_MUTATION_"+uuid4().hex);await self.detail_ready(p)
        await self.ui(p,"dashboard_nav").click()
        await self._dashboard_check(c,p,{**expected,"total":expected["total"]+1,"open":expected["open"]+1})
        await p.reload();await self._dashboard_check(c,p,{**expected,"total":expected["total"]+1,"open":expected["open"]+1})
        admin=await c.page();await self.login(c,admin,"emma")
        created=await self._create_account_ui(c,admin,role="client",actor="empty_client",display_name="Client sans ticket")
        empty=await c.page();await self.login(c,empty,"empty_client")
        await self.ui(empty,"dashboard_nav").click()
        await self._dashboard_check(c,empty,{"total":0,"open":0,"in_progress":0,"resolved":0,"closed":0})

    async def verify_e2e(self, snapshot_hash, *, mode, scenario_ids=None):
        """Execute source-defined scenarios separately on freshly prepared DBs.

        Missing reviewed UI bindings/observations give NOT_VERIFIED, not an
        invented successful scenario. A together run still resets before each.
        """
        if mode not in {"alone", "together"}: raise ValueError("E2E mode required")
        self.snapshot = snapshot_hash; await self._identity()
        expected = {s["id"]:s["expected"] for s in source_e2e_scenarios(self.contract)}
        runs = []
        try:
            for sid in scenario_ids or expected:
                if sid not in expected: raise ValueError("unknown source scenario")
                case, limits = _BrowserCase(self,"TST-05:"+sid), []
                reset = False
                try:
                    if not isinstance(self.profile,dict): raise AdapterUnavailable("browser source profile missing")
                    await self.harness.adapter.prepare_case(sid); reset = True
                    await getattr(self,"_e2e"+sid[-2:])(case)
                    case.check("console",case.console_errors,[])
                except AdapterUnavailable as exc: limits.append(str(exc))
                except Exception as exc: case.check("interaction",type(exc).__name__,"completed")
                for page in case.pages:
                    try: await case.capture(page,"scenario-final")
                    except Exception: limits.append("scenario visual proof unavailable")
                await self._identity()
                root=self.harness.adapter.evidence_root;root.mkdir(parents=True,exist_ok=True)
                path=root/(sid+"-"+mode+"-"+uuid4().hex+".json")
                path.write_text(json.dumps({"source_expected":expected[sid],"mode":mode,"contract_hash":self.contract_hash,
                    "snapshot_hash":self.snapshot,"checks":case.checks,"requests":case.requests,"limits":limits},
                    ensure_ascii=False,indent=2),encoding="utf-8")
                case.proofs.append(Proof("X",str(path),hashlib.sha256(path.read_bytes()).hexdigest(),self.snapshot,self.contract_hash,
                    tuple(x["check"] for x in case.checks),bool(case.checks) and all(x["passed"] for x in case.checks)))
                failed=any(not x["passed"] for x in case.checks)
                runs.append({"id":sid,"expected":expected[sid],"mode":mode,"status":"FAIL" if failed else
                    "NOT_VERIFIED" if limits or not case.checks else "PASS","observed":case.checks,"limits":limits,
                    "proofs":[p.__dict__ for p in case.proofs],"fixture_reset_before":reset,
                    "reproduction":case.requests,"impact":"E2E source scenario violated" if failed else "",
                    "real_ui_api_db":bool(case.requests) and reset,"nominal_mocks":False,
                    "unhandled_console_errors":case.console_errors,
                    "nonblank":bool(case.pages) and all([bool((await p.locator("body").inner_text()).strip()) for p in case.pages]),
                    "contract_hash":self.contract_hash,"snapshot_hash":self.snapshot})
                await self.harness.close()
        finally:
            await self.harness.close(); await self.harness.adapter.close()
        await self._identity()
        return {"pack":"browser_e2e","status":"FAIL" if any(r["status"]=="FAIL" for r in runs) else
                "PASS" if runs and all(r["status"]=="PASS" for r in runs) else "NOT_VERIFIED",
                "contract_hash":self.contract_hash,"snapshot_hash":self.snapshot,"scenarios":runs,
                "environment_limits":self.harness.environment_limits,
                "browser_environment":self.harness.browser_environment}

    async def _e2e01(self,c):
        p=await c.page();await self.login(c,p,"alice")
        title="E2E client "+uuid4().hex;reply="E2E public response "+uuid4().hex
        await self.create(c,p,title);await self.detail_ready(p)
        await self.ui(p,"reply").fill(reply);await self.ui(p,"send").click()
        await self.ui(p,"messages").get_by_text(reply,exact=True).wait_for()
        await self.ui(p,"ticket_nav").click();await self.ui(p,"search").fill(title)
        await self.ui(p,"ticket_list").get_by_text(title,exact=True).click();await self.detail_ready(p)
        await p.reload();await self.detail_ready(p)
        await self.ui(p,"messages").get_by_text(reply,exact=True).wait_for()
        c.check("reload_public_response",await self.ui(p,"messages").get_by_text(reply,exact=True).is_visible())
        c.check("one_db_ticket",await self.harness.adapter.observe("browser_operation_count",title=title),1)

    async def _patch_ui(self,c,p,**fields):
        for field,value in fields.items(): await self.ui(p,field).select_option(value)
        async with p.expect_response(lambda r:r.request.method=="GET" and urlsplit(r.url).path.endswith("/messages")) as loaded:
            async with p.expect_response(lambda r:r.request.method=="PATCH") as changed:
                await self.ui(p,"apply").click()
            c.check("patch_"+"_".join(fields),(await changed.value).status,200)
        await (await loaded.value).body();await self.detail_ready(p)

    async def _e2e02(self,c):
        p=await c.page();await self.login(c,p,"camille")
        tid=self.harness.adapter.manifest.tickets["alice_open"]
        await p.goto(self.harness.adapter.base_url+self.harness.routes["ticket"].format(id=tid));await self.detail_ready(p)
        await self._patch_ui(c,p,assignee=self.harness.adapter.manifest.accounts["camille"].id,status="in_progress")
        for visibility,content in [("internal","E2E_PRIVATE_NOTE"),("public","E2E_PUBLIC_RESPONSE")]:
            await self.ui(p,"visibility").select_option(visibility);await self.ui(p,"reply").fill(content)
            await self.ui(p,"send").click();await self.ui(p,"messages").get_by_text(content,exact=True).wait_for()
        await self._patch_ui(c,p,status="resolved");await self._patch_ui(c,p,status="closed")
        q=await c.page();await self.login(c,q,"alice")
        await q.goto(self.harness.adapter.base_url+self.harness.routes["ticket"].format(id=tid));await self.detail_ready(q)
        await self.ui(q,"messages").get_by_text("E2E_PUBLIC_RESPONSE",exact=True).wait_for()
        c.check("client_public_only",await self._private_clean(q,["E2E_PRIVATE_NOTE"]))
        state=await self.harness.adapter.observe("ticket_state",ticket_id=tid)
        c.check("db_closed",state["status"],"closed")

    async def _e2e03(self,c):
        p=await c.page();await self.login(c,p,"bob")
        before=await self.harness.adapter.observe("business_state")
        tid=self.harness.adapter.manifest.tickets["alice_open"]
        async with p.expect_response(lambda r:r.request.method=="GET" and urlsplit(r.url).path=="/api/tickets/"+tid) as denied:
            await p.goto(self.harness.adapter.base_url+self.harness.routes["ticket"].format(id=tid))
        c.check("foreign_ticket_404",(await denied.value).status,404)
        await self.ui(p,"error").wait_for();c.check("foreign_detail_cleared",not await self.ui(p,"reply").is_visible())
        await p.goto(self.harness.adapter.base_url+self.harness.routes["admin"])
        c.check("admin_route_denied",await c.visible(p,"error"))
        c.check("admin_client_no_private",await self._private_clean(p,[self.harness.adapter.manifest.accounts["emma"].email]))
        c.check("denied_reads_no_business_db_effect",await self.harness.adapter.observe("business_state")==before)
        await self.harness.adapter.command("deactivate_fixture_account",actor="dylan")
        q=await c.page();actor=self.harness.adapter.manifest.accounts["dylan"]
        await self.ui(q,"email").fill(actor.email);await self.ui(q,"password").fill(actor.password)
        async with q.expect_response(lambda r:r.request.method=="POST" and urlsplit(r.url).path=="/api/auth/login") as inactive:
            await self.ui(q,"login").click()
        c.check("inactive_login_401",(await inactive.value).status,401)

    async def _e2e04(self,c):
        await self._ux07(c,doubleclick=False)
        await self._ux02(c)

    async def _e2e05(self,c):
        p=await c.page();await self.login(c,p,"emma")
        uid=await self._create_account_ui(c,p,role="agent",actor="new_agent",display_name="Agent E2E")
        q=await c.page();await self.login(c,q,"new_agent")
        tid=self.harness.adapter.manifest.tickets["alice_open"]
        await p.goto(self.harness.adapter.base_url+self.harness.routes["ticket"].format(id=tid));await self.detail_ready(p)
        await self._patch_ui(c,p,assignee=uid)
        await self.ui(p,"admin_nav").click()
        toggle=p.locator(self.harness.bindings["user_toggle"].format(id=uid))
        async with p.expect_response(lambda r:r.request.method=="PATCH" and urlsplit(r.url).path=="/api/users/"+uid) as disabled:
            await toggle.click()
            if await self.ui(p,"confirm").is_visible(): await self.ui(p,"confirm").click()
        c.check("agent_deactivated",(await disabled.value).status,200)
        await self.ui(q,"refresh").click();c.check("old_session_revoked",await c.visible(q,"email"))
        state=await self.harness.adapter.observe("ticket_state",ticket_id=tid);c.check("db_unassigned",state["assignee_id"],None)
        async with p.expect_response(lambda r:r.request.method=="PATCH" and urlsplit(r.url).path=="/api/users/"+uid) as activated:
            await toggle.click()
        c.check("agent_reactivated",(await activated.value).status,200)
        async with q.expect_response(lambda r:r.request.method=="GET" and urlsplit(r.url).path=="/api/auth/me") as old:
            await q.reload()
        c.check("reactivation_old_session_http401",(await old.value).status,401)
        c.check("reactivation_old_session_still_revoked",await c.visible(q,"email"))
        await self.login(c,q,"new_agent")
        admin=self.harness.adapter.manifest.accounts["emma"].id
        async with p.expect_response(lambda r:r.request.method=="PATCH" and urlsplit(r.url).path=="/api/users/"+admin) as last:
            await p.locator(self.harness.bindings["user_toggle"].format(id=admin)).click()
            if await self.ui(p,"confirm").is_visible():await self.ui(p,"confirm").click()
        c.check("last_admin_409",(await last.value).status,409)

    async def _create_account_ui(self,c,p,*,role,actor,display_name):
        await self.ui(p,"admin_nav").click()
        # All these controls must be independently bound; never fabricate a
        # successful administration journey from role/button presence.
        email="browser-"+uuid4().hex+"@example.test"
        await self.ui(p,"new_email").fill(email)
        await self.ui(p,"new_name").fill(display_name)
        await self.ui(p,"new_password").fill("Independent E2E password 2026")
        await self.ui(p,"new_role").select_option(role)
        async with p.expect_response(lambda r:r.request.method=="POST" and urlsplit(r.url).path=="/api/users") as created:
            await self.ui(p,"create_user").click()
        response=await created.value;c.check("account_created_"+role,response.status,201)
        uid=(await response.json())["id"]
        await self.harness.adapter.command("register_actor",actor=actor,id=uid,email=email,
            password="Independent E2E password 2026",role=role)
        return uid

    async def _e2e06(self,c):
        await self._ux06(c);await self._ux03(c)
        p=await c.page();await self.login(c,p,"alice")
        expected=self.harness.adapter.manifest.metadata["dashboard_expected"]["alice"]
        await self.ui(p,"dashboard_nav").click();await self._dashboard_check(c,p,expected)
        await self.ui(p,"create").click();title="MOTLONG"*15
        await self.ui(p,"title").fill(title);await self.ui(p,"description").fill("E2E dashboard mutation description long enough")
        await self.ui(p,"submit").click();await self.detail_ready(p)
        for width in [self.profile["desktop_width"],self.profile["mobile_width"]]:
            await p.set_viewport_size({"width":width,"height":900})
            c.check("e2e_no_overflow_"+str(width),await p.evaluate("document.documentElement.scrollWidth<=innerWidth"))
            await c.capture(p,"e2e-viewport-"+str(width))
        updated={**expected,"total":expected["total"]+1,"open":expected["open"]+1}
        await self.ui(p,"dashboard_nav").click();await self._dashboard_check(c,p,updated)
        await p.reload();await self._dashboard_check(c,p,updated)
        async def slow(route):await self._slow_read(route,.3,c)
        await p.route("**/api/tickets?*",slow);await self.ui(p,"ticket_nav").click()
        c.check("e2e_slow_loading",await c.visible(p,"loading"));await self.ui(p,"total").get_by_text(str(updated["total"]),exact=True).wait_for()
        await p.unroute("**/api/tickets?*");await p.context.set_offline(True);await self.ui(p,"refresh").click()
        c.check("e2e_network_failure",await c.visible(p,"error"));await p.context.set_offline(False)
        await self.ui(p,"refresh").click();await self.ui(p,"total").get_by_text(str(updated["total"]),exact=True).wait_for()
        await self.ui(p,"logout").click();await self.ui(p,"email").wait_for();await self.login(c,p,"bob")
        c.check("e2e_switch_no_alice",await self._private_clean(p,[title]))

    async def _dashboard_check(self,c,p,expected):
        try:await self.ui(p,"dashboard_total").filter(has_text=re.compile("^"+str(expected["total"])+"$")).wait_for()
        except Exception:pass  # record the actual mismatching counter below
        c.check("dashboard_total",int(await self.ui(p,"dashboard_total").inner_text()),expected["total"])
        observed=[]
        for state in ["open","in_progress","resolved","closed"]:
            value=int(await self.ui(p,"dashboard_"+state).inner_text());observed.append(value)
            c.check("dashboard_"+state,value,expected[state])
        c.check("dashboard_sum",sum(observed),expected["total"])
