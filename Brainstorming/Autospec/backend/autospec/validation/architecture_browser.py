"""Native ARC-06 client contribution, not a complete architecture verdict.

Locator/DTO pointers and optional code-to-presentation mappings are operational
bindings reviewed with the subject. Expectations stay in the immutable source.
No response is synthesized and no product module executes on the host.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit
from uuid import uuid4

from .browser_contracts import _BrowserCase
from .support_adapter import AdapterUnavailable, Proof


def _manifest_digest(manifest):
    # Credentials contribute to identity but are never exported or logged.
    return hashlib.sha256(json.dumps(asdict(manifest), sort_keys=True, ensure_ascii=True).encode()).hexdigest()


def _bindings(harness):
    probes = harness.adapter.manifest.metadata.get("browser_probes", {})
    value = probes.get("architecture_client")
    if (not isinstance(value, dict) or set(value) - {"identity_pointer", "error_presentation", "error_messages"}
            or value.get("identity_pointer") not in {"/display_name", "/user/display_name"}
            or value.get("error_presentation") not in {"server_message", "code_mapping"}
            or not {"current_user_name", "error", "email", "password", "login", "ticket_nav"} <= harness.bindings.keys()):
        raise AdapterUnavailable("reviewed ARC-06 locator/DTO/presentation bindings absent")
    if value["error_presentation"] == "code_mapping":
        mapping = value.get("error_messages")
        if (not isinstance(mapping, dict) or not 1 <= len(mapping) <= 100
                or any(not isinstance(k, str) or not k or not isinstance(v, str) or not v.strip()
                       or len(k) > 200 or len(v) > 2000 for k, v in mapping.items())):
            raise AdapterUnavailable("reviewed code-to-presentation mapping absent")
    return value


async def _json(response):
    length = response.headers.get("content-length")
    if length is not None and (not length.isdecimal() or int(length) > 65536):
        raise AdapterUnavailable("bounded architecture API DTO required")
    body = await response.body()
    if len(body) > 65536:
        raise AdapterUnavailable("architecture API DTO exceeds bound")
    value = json.loads(body)
    if not isinstance(value, dict):
        raise ValueError("architecture API response is not an object")
    return value, hashlib.sha256(body).hexdigest()


async def collect_architecture_client(contract, harness, snapshot_hash):
    """Observe real frontend GET /api/auth/me and a real absent-ticket 404.

    Return X/V for ARC-06:error_client only. The coordinator must publish these
    proofs BEFORE ArchitectureContractVerifier; it must not merge this narrow
    PASS into a full ARC-06 PASS. Existing reviewed source/binding R is separate.
    The adapter/runtime stays owned by the caller; only our browser is closed.
    """
    requirement = next((r for r in contract.requirements if r.id == "ARC-06"), None)
    if requirement is None:
        raise AdapterUnavailable("frozen ARC-06 requirement absent")
    contract_hash = contract.contract_hash
    owner = SimpleNamespace(harness=harness, profile={"desktop_width": 1280},
                            snapshot=snapshot_hash, contract_hash=contract_hash)
    case = _BrowserCase(owner, "ARC-06")
    limits, fingerprint, binding = [], None, None

    async def identity():
        if (contract.contract_hash != contract_hash or await harness.adapter.contract_hash() != contract_hash
                or await harness.adapter.snapshot_hash() != snapshot_hash):
            raise AdapterUnavailable("architecture browser snapshot/oracle drift")
        if fingerprint is not None and _manifest_digest(harness.adapter.manifest) != fingerprint:
            raise AdapterUnavailable("architecture browser fixture/actor identity drift")

    def response_is(response, path):
        parsed, origin = urlsplit(response.url), urlsplit(harness.adapter.base_url)
        return (response.request.method == "GET" and (parsed.scheme, parsed.netloc) == (origin.scheme, origin.netloc)
                and parsed.path == path)

    async def execute():
        nonlocal fingerprint, binding
        await identity()
        await harness.adapter.prepare_case("ARC-06")
        binding = _bindings(harness)
        fingerprint = _manifest_digest(harness.adapter.manifest)
        if "alice" not in harness.adapter.manifest.accounts:
            raise AdapterUnavailable("reviewed Alice fixture actor absent")
        account = harness.adapter.manifest.accounts["alice"]
        page = await case.page()
        page.set_default_timeout(15000)
        await harness.control(page, "email").fill(account.email)
        await harness.control(page, "password").fill(account.password)
        async with page.expect_response(lambda r: r.request.method == "POST" and
                urlsplit(r.url).path == "/api/auth/login" and
                (urlsplit(r.url).scheme, urlsplit(r.url).netloc) ==
                (urlsplit(harness.adapter.base_url).scheme, urlsplit(harness.adapter.base_url).netloc), timeout=15000) as login:
            await harness.control(page, "login").click()
        case.check("error_client:real_login_status", (await login.value).status, 200)
        await harness.control(page, "ticket_nav").wait_for(state="visible")
        # Set the observer BEFORE a fresh navigation; never catch an old/pending
        # response and never use p.request.get as a substitute for client usage.
        async with page.expect_response(lambda r: response_is(r, "/api/auth/me"), timeout=15000) as me:
            await page.reload(timeout=15000)
        response = await me.value
        case.check("error_client:real_me_status", response.status, 200)
        dto, dto_sha = await _json(response)
        user = dto.get("user") if binding["identity_pointer"].startswith("/user/") else dto
        valid = isinstance(user, dict) and isinstance(user.get("display_name"), str) and bool(user["display_name"].strip())
        case.check("error_client:display_name_dto", valid)
        case.check("error_client:actor_id", user.get("id") if isinstance(user, dict) else None, account.id)
        await harness.control(page, "ticket_nav").wait_for(state="visible")
        await harness.control(page, "current_user_name").wait_for(state="attached")
        displayed = (await harness.control(page, "current_user_name").inner_text()).strip()
        case.check("error_client:display_name_consumed", displayed, user.get("display_name") if valid else None)
        case.requests.append({"method": "GET", "path": "/api/auth/me", "status": response.status,
                              "body_sha256": dto_sha, "fixture_actor_id": account.id})
        await case.capture(page, "identity")
        await identity()
        missing = str(uuid4())
        if missing in harness.adapter.manifest.tickets.values():
            raise AdapterUnavailable("absent UUID unexpectedly matches the fixture")
        route = harness.routes.get("ticket")
        if not isinstance(route, str) or "{id}" not in route:
            raise AdapterUnavailable("reviewed ticket navigation binding absent")
        target = route.format(id=missing)
        parsed = urlsplit(target)
        if not target.startswith("/") or target.startswith("//") or parsed.netloc or parsed.scheme or parsed.fragment:
            raise AdapterUnavailable("ticket navigation must remain on the exact origin")
        api_path = "/api/tickets/" + missing
        async with page.expect_response(lambda r: response_is(r, api_path), timeout=15000) as refused:
            await page.goto(harness.adapter.base_url + target, timeout=15000)
        response = await refused.value
        case.check("error_client:real_missing_ticket_status", response.status, 404)
        dto, dto_sha = await _json(response)
        error = dto.get("error")
        valid = (isinstance(error, dict) and isinstance(error.get("code"), str) and bool(error["code"])
                 and isinstance(error.get("message"), str) and bool(error["message"].strip()))
        case.check("error_client:real_error_dto", valid)
        if not valid:
            raise ValueError("actual API error DTO does not expose code/message")
        if binding["error_presentation"] == "server_message":
            expected = error["message"]
        else:
            expected = binding["error_messages"].get(error["code"])
            if expected is None:
                raise AdapterUnavailable("actual error code lacks reviewed UI presentation mapping")
        await harness.control(page, "error").wait_for(state="visible")
        text = (await harness.control(page, "error").inner_text()).strip()
        case.check("error_client:server_error_consumed", expected in text)
        case.requests.append({"method": "GET", "path": api_path, "status": response.status,
            "code": error["code"], "message": error["message"], "body_sha256": dto_sha})
        case.check("error_client:unhandled_console", case.console_errors, [])
        await case.capture(page, "server-error")
        await identity()

    try:
        await asyncio.wait_for(execute(), timeout=60)
    except AdapterUnavailable as exc:
        limits.append(str(exc))
    except asyncio.TimeoutError:
        limits.append("bounded native architecture browser observation timed out")
    except Exception as exc:
        case.check("error_client:interaction", type(exc).__name__, "completed")
    finally:
        try:
            await identity()
        except AdapterUnavailable as exc:
            limits.append(str(exc))
        await harness.close()
    failed = any(check["passed"] is False for check in case.checks)
    complete = not limits and not failed and any(c["check"] == "ARC-06:error_client:server_error_consumed" for c in case.checks)
    if case.checks:
        root = Path(harness.adapter.evidence_root)
        root.mkdir(parents=True, exist_ok=True)
        path = root / ("ARC-06-error-client-" + uuid4().hex + ".json")
        payload = {"id": "ARC-06", "scope": "native error_client contribution only", "snapshot_hash": snapshot_hash,
            "contract_hash": contract_hash, "fixture_fingerprint": fingerprint, "checks": case.checks,
            "requests": case.requests, "limits": limits, "binding": binding,
            "observer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
        path.write_bytes(json.dumps(payload, sort_keys=True, ensure_ascii=True).encode())
        # A partial observation cannot satisfy the complete external-only check.
        checks = ("ARC-06:error_client",) if complete or failed else tuple(c["check"] for c in case.checks)
        case.proofs.append(Proof("X", str(path), hashlib.sha256(path.read_bytes()).hexdigest(), snapshot_hash,
            contract_hash, checks, not failed and complete))
    row = {"id": "ARC-06", "scope": "error_client contribution; not full ARC-06 acceptance", "layer": "browser",
        "status": "FAIL" if failed else "PASS" if complete else "NOT_VERIFIED", "gate": requirement.gate,
        "expected": requirement.expected, "observed": case.checks, "reproduction": case.requests,
        "impact": "frontend did not consume the actual public identity/error DTO" if failed else "",
        "limits": limits, "proofs": [asdict(p) for p in case.proofs], "snapshot_hash": snapshot_hash,
        "contract_hash": contract_hash}
    return {"pack": "architecture_browser_contribution", "status": row["status"], "requirements": [row],
        "snapshot_hash": snapshot_hash, "contract_hash": contract_hash,
        "environment_limits": harness.environment_limits, "browser_environment": harness.browser_environment}
