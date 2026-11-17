"""Hidden oracle of B4 (counter_app), derived only from bench/briefs/B4-counter-app.md."""

from __future__ import annotations

import re
from pathlib import Path

from bench.oracle import Check, Product, Server

_ASSET = re.compile(r"""(?:src|href)\s*=\s*["'](/?(?:\./)?assets/[^"'?#]+)""", re.IGNORECASE)


def checks(product: Product, tmp: Path) -> list[Check]:
    db = tmp / "counter-oracle.db"
    results: list[Check] = []

    def record(check_id: str, passed: bool, detail: str = "") -> None:
        results.append(Check(check_id, bool(passed), "" if passed else detail))

    try:
        with Server(product, extra_env={"COUNTER_DB": str(db)}) as api:
            status, body = api.request("GET", "/health")
            record("health", status == 200 and body == {"status": "ok"}, f"{status} {body}")

            status, body = api.request("GET", "/api/counter")
            record("initial_value_zero", status == 200 and body == {"value": 0}, f"{status} {body}")

            status, body = api.request("POST", "/api/counter/increment")
            record("increment_returns_new_value", status == 200 and body == {"value": 1}, f"{status} {body}")

            status, body = api.request("POST", "/api/counter/increment")
            status_get, got = api.request("GET", "/api/counter")
            record("two_increments", status == 200 and body == {"value": 2} and got == {"value": 2},
                   f"increment -> {status} {body}, then GET -> {status_get} {got}")

            status, body = api.request("POST", "/api/counter/reset")
            status_get, got = api.request("GET", "/api/counter")
            record("reset_returns_zero", status == 200 and body == {"value": 0} and got == {"value": 0},
                   f"reset -> {status} {body}, then GET -> {status_get} {got}")

            for _ in range(3):
                api.request("POST", "/api/counter/increment")

            status, page = api.request("GET", "/")
            has_root = isinstance(page, str) and '<div id="root">' in page
            record("index_serves_built_page", status == 200 and has_root,
                   f"GET / -> {status}" + ("" if has_root else ', no <div id="root">'))

            assets = _ASSET.findall(page) if isinstance(page, str) else []
            if not assets:
                record("built_asset_served", False, "index.html references no /assets/... file")
            else:
                path = "/" + assets[0].lstrip("./")
                status, content = api.request("GET", path)
                record("built_asset_served", status == 200 and bool(content), f"GET {path} -> {status}")

        with Server(product, extra_env={"COUNTER_DB": str(db)}) as api:
            status, body = api.request("GET", "/api/counter")
            record("persists_across_restart", status == 200 and body == {"value": 3}, f"{status} {body}")
    except RuntimeError as exc:
        results.append(Check("server_starts", False, str(exc)))
    return results
