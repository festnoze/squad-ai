"""Import genuine historical markets from Polymarket (requires a network).

This is the path to real tapes. It reads a resolved market's metadata from the Gamma API and its YES
price history from the CLOB, maps them onto :mod:`pmx`'s schema with ``source: "imported"``, and writes
one JSON file the engine consumes exactly like a bundled one. It is best-effort and never a dependency
of the offline arena: if there is no network, or the provider shape changed, it raises a clear error and
the bundled dataset still runs everything.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"


class ImportError_(RuntimeError):
    """Raised when a market cannot be imported (no network, unknown slug, unresolved market)."""


def _get_json(url: str, params: dict[str, Any]) -> Any:
    import httpx

    try:
        resp = httpx.get(url, params=params, timeout=20.0)
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001 - surface any network/HTTP failure as our own error
        raise ImportError_(f"request to {url} failed: {exc}") from exc
    return resp.json()


def import_polymarket(slug: str, out_dir: Path) -> Path:
    """Fetch one resolved Polymarket market by slug and write it as a pmx market JSON.

    Args:
        slug: the market slug, e.g. ``will-trump-win-the-2024-election``.
        out_dir: directory to write ``<slug>.json`` into.

    Returns:
        The path written.
    """
    markets = _get_json(f"{GAMMA}/markets", {"slug": slug})
    if not markets:
        raise ImportError_(f"no market found for slug {slug!r}")
    m = markets[0]

    outcome_prices = (
        json.loads(m.get("outcomePrices", "[]"))
        if isinstance(m.get("outcomePrices"), str)
        else m.get("outcomePrices", [])
    )
    if not m.get("closed") or not outcome_prices:
        raise ImportError_(f"market {slug!r} is not a closed, resolved market")
    # Binary market: the YES token is index 0; resolution is which outcome settled at 1.
    resolution = 1 if float(outcome_prices[0]) >= 0.5 else 0

    token_ids = (
        json.loads(m.get("clobTokenIds", "[]"))
        if isinstance(m.get("clobTokenIds"), str)
        else m.get("clobTokenIds", [])
    )
    if not token_ids:
        raise ImportError_(f"market {slug!r} exposes no CLOB token to read a price history from")
    history = _get_json(f"{CLOB}/prices-history", {"market": token_ids[0], "interval": "all", "fidelity": 720})
    points = history.get("history", []) if isinstance(history, dict) else []
    if len(points) < 2:
        raise ImportError_(f"market {slug!r} returned too few price points")

    prices = []
    for pt in points:
        cents = max(1, min(99, round(float(pt["p"]) * 100)))
        prices.append({"t": str(pt["t"]), "price": cents})

    payload = {
        "id": slug,
        "question": m.get("question", slug),
        "category": (m.get("category") or "other").lower(),
        "source": "imported",
        "resolution": resolution,
        "resolved_date": str(m.get("endDate", ""))[:10],
        "notes": "Imported from Polymarket (Gamma + CLOB).",
        "prices": prices,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{slug}.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path
