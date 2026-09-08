"""The Polymarket importer: the optional path, kept honest about the wall in front of it.

Polymarket is the deepest real-money prediction market on earth and the worst possible dependency for
this project from where it is built. Verified from this machine on 2026-09-07: `gamma-api.polymarket.com`,
`clob.polymarket.com` and `data-api.polymarket.com` all resolve to `145.239.225.117` and all serve one
certificate whose only names are `*.anj.fr` and `anj.fr`, so httpx fails the handshake with a hostname
mismatch and `curl -k` gets a French block page from the Autorite Nationale des Jeux instead of JSON
(fixtures under `tests/fixtures/d4/`). A silent retry loop against that is a machine burning a request
budget on a wall, and a JSON parse error on a 14 KB HTML page is a misleading diagnosis, so this module
detects the block on both signatures (the certificate failure and the block page body) and raises
`ProviderBlockedError` once, with no retry and with the reason in the context. That is the reason D4 is
the optional wave-1 package: the dataset of PRD AC-1 is built from Kalshi and Manifold, and Polymarket
enters only from a jurisdiction where the tape is reachable, or through `PMX_HTTP_PROXY`.

What it reads, when it is reachable: Gamma (`/markets`) for the metadata and the resolution, the CLOB
(`/prices-history`) for the YES price tape. The CLOB tape carries a price and an instant and no size at
all, which is why every bar this importer builds reports `volume_milli = 0` and `trades = ()`: inventing a
volume the source never had would invent a volume cap, a slippage and a liquidity filter too (contract
8.6, ruling R41 took the same decision for the migrated v1 pack). The honest consequence is recorded in
`Market.notes` and in `quality.traded_bars`, which counts the bars the tape actually covered.

Every number crosses into `pmx` as an integer through `Decimal`: the CLOB answers `{"t": 1772323200,
"p": 0.6327}` and a JSON float is banned by rule 3 of the contract, so both payloads are parsed with
`json.loads(..., parse_float=Decimal)` and a float that reaches a mapper is a `MalformedResponseError`
rather than a rounding surprise three waves later.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Final

from pmx import MARKET_SCHEMA, __version__
from pmx.data.importers._http import (
    HTTP_PROXY_ENV,
    USER_AGENT_CONTACT_ENV,
    USER_AGENT_TEMPLATE,
    HttpClient,
)
from pmx.errors import InvalidConfigError, MalformedResponseError, NotConfiguredError, ProviderBlockedError
from pmx.types import (
    BP_ONE,
    CATEGORIES,
    INTERVALS_MIN,
    MS_PER_DAY,
    Bar,
    Market,
    MarketQuality,
    bar_of,
    clamp_price_bp,
    interval_ms,
    round_half_up,
    round_half_up_decimal,
    sort_markets,
)

# --------------------------------------------------------------------------------------------------
# The two hosts, the two paths, the settings
# --------------------------------------------------------------------------------------------------
PROVIDER: Final = "polymarket"

GAMMA_BASE_URL: Final = "https://gamma-api.polymarket.com"
CLOB_BASE_URL: Final = "https://clob.polymarket.com"
GAMMA_MARKETS_PATH: Final = "/markets"
CLOB_PRICES_HISTORY_PATH: Final = "/prices-history"

#: `PMX_HTTP_PROXY` is the one setting that makes this importer usable from a blocked jurisdiction
#: (contract 7.11 and section 14, which names the constant against D4). It is re-exported from the
#: shared client rather than re-spelled, so the environment variable can never drift between the two.
PMX_HTTP_PROXY: Final = HTTP_PROXY_ENV

#: The intervals the CLOB accepts on `/prices-history`. `startTs` and `endTs` pin the window; `interval`
#: is the coarse alternative the provider offers for "the whole life of the market".
PRICES_HISTORY_INTERVALS: Final = ("max", "all", "1m", "1w", "1d", "6h", "1h")
DEFAULT_PRICES_HISTORY_INTERVAL: Final = "max"
#: `fidelity` is in minutes. 60 keeps a daily bar informative (open, high, low and close differ) while
#: staying inside the provider's point budget over a year of life.
DEFAULT_FIDELITY_MIN: Final = 60
#: One UNIX second per `t` in the CLOB answer.
PRICES_HISTORY_T_UNIT_MS: Final = 1_000
#: Two bars is what `market.v2.json` requires of a tape; one bar is not a tape.
MIN_BARS: Final = 2
MIN_PRICE_POINTS: Final = 2

GAMMA_PAGE_SIZE: Final = 100
GAMMA_MAX_PAGES: Final = 500
POLYMARKET_MIN_INTERVAL_MS: Final = 1_000
#: Zero retries on Polymarket, deliberately. `HttpClient` retries a transport failure `max_retries` times
#: (contract 7.11 lists 429 and 5xx only, so this is a reported contract issue against `_http.py`), and a
#: certificate that names another domain is not a transient failure: it is the same wall four handshakes in
#: a row. Every client this module builds carries `max_retries = 0`, which is what makes D4's "no retry"
#: true of the real path and not only of the detector.
POLYMARKET_MAX_RETRIES: Final = 0
#: Standard Polymarket markets carry no trading fee (contract 8.8).
POLYMARKET_FEE_SCHEDULE_ID: Final = "polymarket-zero-2026-09"

MARKET_SLUG_MAX: Final = 96
QUESTION_MAX: Final = 500
DESCRIPTION_MAX: Final = 4_000
RESOLUTION_SOURCE_MAX: Final = 500
NOTES_MAX: Final = 2_000
TAGS_MAX: Final = 16
TAG_MAX_CHARS: Final = 32
PROVIDER_ID_MAX: Final = 128

_EPOCH: Final = datetime(1970, 1, 1, tzinfo=UTC)
_ONE_MS: Final = timedelta(milliseconds=1)
_SLUG_ILLEGAL_RE: Final = re.compile(r"[^A-Za-z0-9._-]+")
_TAG_ILLEGAL_RE: Final = re.compile(r"[^a-z0-9_-]+")

# --------------------------------------------------------------------------------------------------
# The ANJ block detector
# --------------------------------------------------------------------------------------------------
ANJ_BLOCK_MESSAGE: Final = "Polymarket is blocked in this jurisdiction (ANJ)"

#: Lowercased needles of the block page recorded in `tests/fixtures/d4/anj_block_page.html`. The page is
#: served with status 200 and `content-type: text/html`, so nothing but its content identifies it.
ANJ_BODY_MARKERS: Final = (
    "anj.fr",
    "offre-illegale",
    "autorite nationale des jeux",
    "autorité nationale des jeux",
)
#: Needles of the certificate failure. CPython 3.12 names the host it asked for and not the names the
#: served certificate carries, so the mismatch alone is the signature: a Polymarket host that answers with
#: a certificate for another name is, by the error taxonomy of contract 13.1, a block ("the ANJ block page
#: or any non-provider certificate was served"). Stacks that do spell the certificate names out are caught
#: one line earlier, by `anj.fr` in the failure text.
_CERTIFICATE_MISMATCH_MARKERS: Final = (
    "hostname mismatch",
    "certificate is not valid for",
    "doesn't match",
    "does not match",
    "hostname doesn't match",
)
_CERTIFICATE_FAILURE_MARKERS: Final = (
    "certificate_verify_failed",
    "certificate verify failed",
    "sslcertverificationerror",
    "certificateerror",
    "ssl: ",
)

#: Reasons `anj_block_reason` returns, ordered from the most specific to the least.
BLOCK_REASON_ANJ_BODY: Final = "anj_block_page"
BLOCK_REASON_ANJ_CERTIFICATE: Final = "anj_certificate"
BLOCK_REASON_FOREIGN_CERTIFICATE: Final = "foreign_certificate"


def _error_chain_text(error: BaseException) -> str:
    """Every message of an exception chain, lowercased, so one scan reads the whole cause tree.

    The shared client wraps a transport failure in `ProviderError`, httpx wraps `ssl` in `httpcore`, and
    which layer names the certificate depends on the stack. Reading the chain rather than the top frame is
    what makes the detector survive all three.
    """
    seen: list[str] = []
    current: BaseException | None = error
    depth = 0
    while current is not None and depth < 16:
        seen.append(f"{type(current).__module__}.{type(current).__name__}: {current}")
        current = current.__cause__ or current.__context__
        depth += 1
    return "\n".join(seen).lower()


def anj_block_reason(*, body: str | None = None, error: BaseException | None = None) -> str | None:
    """Name the ANJ block signature in a response body or a transport failure, or return `None`.

    Three signatures, all verified on 2026-09-07 (fixture `anj_block_response.json`):

    - `anj_block_page`: a 200 whose body is the block page of the Autorite Nationale des Jeux;
    - `anj_certificate`: a handshake failure whose chain names `anj.fr`;
    - `foreign_certificate`: a certificate hostname mismatch on a Polymarket host, which is the same
      event seen by a stack that does not print the certificate's names.

    The function is pure and takes strings, so the detector is tested offline against a recorded page and
    a recorded failure chain rather than against a live jurisdiction.
    """
    if body is not None and body.lstrip()[:1] not in ("{", "["):
        # A body that parses as JSON is the provider answering, whatever it says: a market whose question
        # names the regulator must not be read as the regulator's block page. The block page is HTML.
        haystack = body.lower()
        for marker in ANJ_BODY_MARKERS:
            if marker in haystack:
                return BLOCK_REASON_ANJ_BODY
    if error is not None:
        text = _error_chain_text(error)
        if "anj.fr" in text:
            return BLOCK_REASON_ANJ_CERTIFICATE
        is_tls_failure = any(marker in text for marker in _CERTIFICATE_FAILURE_MARKERS)
        is_mismatch = any(marker in text for marker in _CERTIFICATE_MISMATCH_MARKERS)
        if is_tls_failure and is_mismatch:
            return BLOCK_REASON_FOREIGN_CERTIFICATE
    return None


def raise_if_blocked(*, url: str, body: str | None = None, error: BaseException | None = None) -> None:
    """Raise `ProviderBlockedError` once when the block is detected, and never retry.

    A retry is what this guard exists to prevent: the block is a DNS answer and a certificate, so it holds
    for every request from this network and a backoff only spends the throttle budget.
    """
    reason = anj_block_reason(body=body, error=error)
    if reason is None:
        return
    blocked = ProviderBlockedError(ANJ_BLOCK_MESSAGE, provider=PROVIDER, reason=reason, url=url)
    if error is not None:
        raise blocked from error
    raise blocked


# --------------------------------------------------------------------------------------------------
# The clients (the one place the proxy setting is read)
# --------------------------------------------------------------------------------------------------
def proxy_from_env(env: Mapping[str, str] | None = None) -> str | None:
    """The proxy for both Polymarket hosts, from `PMX_HTTP_PROXY`; `None` when unset or empty.

    `env` is injectable so the setting is tested without touching the process environment.
    """
    source: Mapping[str, str] = os.environ if env is None else env
    value = source.get(PMX_HTTP_PROXY, "").strip()
    return value or None


def make_clients(
    *,
    cache_dir: Path,
    env: Mapping[str, str] | None = None,
    min_interval_ms: int = POLYMARKET_MIN_INTERVAL_MS,
) -> tuple[HttpClient, HttpClient]:
    """Build the `(clob, gamma)` client pair for Polymarket, both carrying `PMX_HTTP_PROXY`.

    Two clients because the metadata and the tape live on two hosts and `HttpClient` binds one `base_url`
    (contract 7.11), and one factory because the proxy and the User-Agent must be identical on both: a
    proxy that covers Gamma and not the CLOB would import metadata for markets whose tape then fails.
    """
    source: Mapping[str, str] = os.environ if env is None else env
    contact = source.get(USER_AGENT_CONTACT_ENV, "").strip()
    if not contact:
        raise NotConfiguredError(
            f"set {USER_AGENT_CONTACT_ENV} to a contact address before importing Polymarket",
            provider=PROVIDER,
            setting=USER_AGENT_CONTACT_ENV,
        )
    user_agent = USER_AGENT_TEMPLATE.format(version=__version__, contact=contact)
    proxy = proxy_from_env(source)
    clob = HttpClient(
        base_url=CLOB_BASE_URL,
        user_agent=user_agent,
        min_interval_ms=min_interval_ms,
        cache_dir=cache_dir,
        max_retries=POLYMARKET_MAX_RETRIES,
        proxy=proxy,
    )
    gamma = HttpClient(
        base_url=GAMMA_BASE_URL,
        user_agent=user_agent,
        min_interval_ms=min_interval_ms,
        cache_dir=cache_dir,
        max_retries=POLYMARKET_MAX_RETRIES,
        proxy=proxy,
    )
    return clob, gamma


def _sibling_client(client: HttpClient, base_url: str) -> HttpClient:
    """The second host's client, derived from the one the caller handed over.

    `HttpClient` binds one `base_url` and joins a path onto it by string, so one client cannot reach two
    hosts and the absolute-URL trick does not work either. Deriving keeps the caller's User-Agent,
    throttle, cache directory and proxy (so the two hosts stay one polite identity behind one proxy) and
    forces `max_retries = 0`.
    """
    return HttpClient(
        base_url=base_url,
        user_agent=client.user_agent,
        min_interval_ms=client.min_interval_ms,
        cache_dir=client.cache_dir,
        max_retries=POLYMARKET_MAX_RETRIES,
        timeout_s=client.timeout_s,
        proxy=client.proxy,
    )


def _is_gamma_host(base_url: str) -> bool:
    """Whether a base URL names the metadata host rather than the CLOB."""
    return "gamma" in base_url.lower()


def _resolve_clients(
    client: HttpClient, gamma_client: HttpClient | None
) -> tuple[HttpClient, HttpClient, tuple[HttpClient, ...]]:
    """`(tape client, metadata client, the clients this call must close)`."""
    if gamma_client is not None:
        return client, gamma_client, ()
    if _is_gamma_host(client.base_url):
        tape = _sibling_client(client, CLOB_BASE_URL)
        return tape, client, (tape,)
    metadata = _sibling_client(client, GAMMA_BASE_URL)
    return client, metadata, (metadata,)


# --------------------------------------------------------------------------------------------------
# Fetch helpers: every payload passes the block detector before it is parsed
# --------------------------------------------------------------------------------------------------
def _get_payload(client: HttpClient, path: str, params: Mapping[str, str | int]) -> object:
    """One GET, one block check, one integer-safe JSON parse.

    `get_text` rather than `get_json` for two reasons: the block page is HTML behind a 200 and has to be
    read as text before anything tries to parse it, and `parse_float=Decimal` is the only way a provider
    decimal reaches the mappers without ever having been a float (contract 7.2).
    """
    url = f"{client.base_url}{path}"
    try:
        raw = client.get_text(path, params)
    except ProviderBlockedError:
        raise
    except Exception as exc:
        raise_if_blocked(url=url, error=exc)
        raise
    raise_if_blocked(url=url, body=raw)
    try:
        return json.loads(raw, parse_float=Decimal)
    except json.JSONDecodeError as exc:
        raise MalformedResponseError(
            "provider answered with a body that is not JSON",
            provider=PROVIDER,
            path=path,
            head=raw[:120],
        ) from exc


def _iso_z(t_ms: int) -> str:
    """`t_ms` as the second-resolution UTC string the Gamma query parameters take."""
    return (_EPOCH + timedelta(milliseconds=t_ms)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_instant_ms(value: object, *, field: str) -> int:
    """A provider date string as epoch milliseconds, or `MalformedResponseError`.

    Gamma spells its instants three ways in one payload (`2026-03-31T00:00:00Z`,
    `2026-03-31 18:05:00+00`, `2026-01-05T18:20:31.263Z`), so the shapes are normalised here and a string
    without a `Z` or an explicit offset is refused rather than guessed at (contract 5.1).
    """
    if not isinstance(value, str) or not value.strip():
        raise MalformedResponseError("instant is missing", provider=PROVIDER, field=field)
    text = value.strip().replace(" ", "T", 1)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    if re.search(r"[+-][0-9]{2}$", text):
        text = text + ":00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise MalformedResponseError(
            "instant is not an ISO-8601 date", provider=PROVIDER, field=field, value=value
        ) from exc
    if parsed.tzinfo is None:
        raise MalformedResponseError(
            "instant carries no timezone", provider=PROVIDER, field=field, value=value
        )
    return (parsed.astimezone(UTC) - _EPOCH) // _ONE_MS


def _decimal(value: object, *, field: str) -> Decimal:
    """A provider number as `Decimal`; a float is a bug in the parse path, not a value to round."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        raise MalformedResponseError("number is a boolean", provider=PROVIDER, field=field)
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, str):
        text = value.strip()
        try:
            return Decimal(text)
        except ArithmeticError as exc:
            raise MalformedResponseError(
                "number is not decimal", provider=PROVIDER, field=field, value=text[:40]
            ) from exc
    raise MalformedResponseError(
        "number arrived as an unsupported type", provider=PROVIDER, field=field, type=type(value).__name__
    )


def _json_list(value: object, *, field: str) -> list[object]:
    """Gamma sends its own arrays as JSON strings (`outcomes`, `outcomePrices`, `clobTokenIds`)."""
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            decoded = json.loads(text, parse_float=Decimal)
        except json.JSONDecodeError as exc:
            raise MalformedResponseError(
                "embedded array is not JSON", provider=PROVIDER, field=field, value=text[:60]
            ) from exc
        value = decoded
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    raise MalformedResponseError(
        "field is not an array", provider=PROVIDER, field=field, type=type(value).__name__
    )


def _text(value: object, *, limit: int, default: str = "") -> str:
    """A provider string, truncated with an ellipsis at the contract's cap (contract 7.2)."""
    if not isinstance(value, str):
        return default
    text = " ".join(value.split()) if "\n" in value or "\r" in value else value.strip()
    if not text:
        return default
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


# --------------------------------------------------------------------------------------------------
# Identifiers, category, tags
# --------------------------------------------------------------------------------------------------
def market_slug(raw_slug: str) -> str:
    """The `<slug>` part of a market id: the provider's own slug, legal and inside 96 characters.

    Polymarket slugs are sentences (`will-the-fed-cut-rates-by-50-bps-at-the-march-2026-meeting-...`) and
    regularly pass the 96 characters the id regex of contract section 2 allows, so an over-long slug keeps
    its first 87 characters and gains `-<sha256(slug)[:8]>`. The mapping is deterministic, collision-free
    in practice and reversible through `provider_id`, which stays verbatim.
    """
    cleaned = _SLUG_ILLEGAL_RE.sub("-", raw_slug.strip()).strip("-")
    cleaned = re.sub(r"-{2,}", "-", cleaned)
    if not cleaned:
        raise MalformedResponseError("market carries no slug", provider=PROVIDER, slug=raw_slug[:60])
    if len(cleaned) <= MARKET_SLUG_MAX:
        return cleaned
    digest = hashlib.sha256(raw_slug.encode("utf-8")).hexdigest()[:8]
    return f"{cleaned[: MARKET_SLUG_MAX - 9]}-{digest}"


#: Provider label or tag slug to the twelve categories of contract section 2. `other` is the fallback and
#: is never an error: a category that stops matching costs a row in the per-category leaderboard, not an
#: import. The keys are lowercased slugs, so `Pop Culture` and `pop-culture` both land.
POLYMARKET_CATEGORY_MAP: Final[Mapping[str, str]] = {
    "politics": "politics",
    "us-politics": "politics",
    "us-election": "politics",
    "elections": "politics",
    "election": "politics",
    "global-elections": "politics",
    "congress": "politics",
    "trump": "politics",
    "biden": "politics",
    "economics": "economics",
    "economy": "economics",
    "inflation": "economics",
    "fed": "economics",
    "fed-rates": "economics",
    "gdp": "economics",
    "jobs": "economics",
    "finance": "finance",
    "business": "finance",
    "stocks": "finance",
    "companies": "finance",
    "earnings": "finance",
    "ipo": "finance",
    "commodities": "finance",
    "crypto": "crypto",
    "crypto-prices": "crypto",
    "bitcoin": "crypto",
    "ethereum": "crypto",
    "solana": "crypto",
    "defi": "crypto",
    "nft": "crypto",
    "sports": "sports",
    "nfl": "sports",
    "nba": "sports",
    "mlb": "sports",
    "nhl": "sports",
    "soccer": "sports",
    "football": "sports",
    "basketball": "sports",
    "baseball": "sports",
    "tennis": "sports",
    "golf": "sports",
    "olympics": "sports",
    "chess": "sports",
    "f1": "sports",
    "science": "science",
    "space": "science",
    "spacex": "science",
    "climate": "science",
    "environment": "science",
    "nobel": "science",
    "tech": "tech",
    "technology": "tech",
    "ai": "tech",
    "artificial-intelligence": "tech",
    "openai": "tech",
    "apple": "tech",
    "entertainment": "entertainment",
    "pop-culture": "entertainment",
    "movies": "entertainment",
    "music": "entertainment",
    "awards": "entertainment",
    "oscars": "entertainment",
    "grammys": "entertainment",
    "celebrities": "entertainment",
    "tv": "entertainment",
    "weather": "weather",
    "hurricane": "weather",
    "hurricanes": "weather",
    "temperature": "weather",
    "health": "health",
    "coronavirus": "health",
    "covid": "health",
    "covid-19": "health",
    "medicine": "health",
    "pandemic": "health",
    "world": "world",
    "geopolitics": "world",
    "middle-east": "world",
    "israel": "world",
    "ukraine": "world",
    "russia": "world",
    "china": "world",
    "war": "world",
    "nato": "world",
    "eu": "world",
}


def _slugify(label: str) -> str:
    """A provider label as a tag slug of contract 7.2 (`^[a-z0-9_-]{1,32}$`), or `""`."""
    slug = _TAG_ILLEGAL_RE.sub("-", label.strip().lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return slug[:TAG_MAX_CHARS].strip("-")


def _tag_slugs(raw: Mapping[str, object]) -> tuple[str, ...]:
    """The market's tags, then its event's, as sorted unique slugs capped at sixteen."""
    labels: list[str] = []
    for key in ("tags", "categories"):
        for entry in _json_list(raw.get(key), field=key):
            if isinstance(entry, str):
                labels.append(entry)
            elif isinstance(entry, Mapping):
                for field in ("slug", "label", "name"):
                    candidate = entry.get(field)
                    if isinstance(candidate, str) and candidate.strip():
                        labels.append(candidate)
                        break
    for event in _events(raw):
        for entry in _json_list(event.get("tags"), field="events[].tags"):
            if isinstance(entry, str):
                labels.append(entry)
            elif isinstance(entry, Mapping):
                for field in ("slug", "label", "name"):
                    candidate = entry.get(field)
                    if isinstance(candidate, str) and candidate.strip():
                        labels.append(candidate)
                        break
    slugs = {slug for slug in (_slugify(label) for label in labels) if slug}
    return tuple(sorted(slugs)[:TAGS_MAX])


def _events(raw: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    events = raw.get("events")
    if not isinstance(events, list):
        return ()
    return tuple(event for event in events if isinstance(event, Mapping))


def _category(raw: Mapping[str, object], tags: Sequence[str]) -> str:
    """The contract category, from the market label, then the event label, then the tags, then `other`."""
    candidates: list[str] = []
    for key in ("category", "groupItemTitle"):
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            candidates.append(value)
    for event in _events(raw):
        value = event.get("category")
        if isinstance(value, str) and value.strip():
            candidates.append(value)
    candidates.extend(tags)
    for candidate in candidates:
        slug = _slugify(candidate)
        if slug in CATEGORIES:
            return slug
        mapped = POLYMARKET_CATEGORY_MAP.get(slug)
        if mapped is not None:
            return mapped
    return "other"


def _url(raw: Mapping[str, object], slug: str) -> str:
    """The public market page, from the event slug when Gamma carries one."""
    for event in _events(raw):
        event_slug = event.get("slug")
        if isinstance(event_slug, str) and event_slug.strip():
            return f"https://polymarket.com/event/{event_slug.strip()}/{slug}"
    return f"https://polymarket.com/market/{slug}"


# --------------------------------------------------------------------------------------------------
# The tape
# --------------------------------------------------------------------------------------------------
def _price_points(
    payload: object,
    *,
    interval_min: int,
    first_bar_ms: int,
    last_bar_ms: int,
) -> tuple[tuple[int, int], ...]:
    """`(t_ms, price_bp)` of the CLOB answer, ascending, restricted to the market's own bar range.

    A point outside `[first_bar, last_bar]` is dropped rather than clamped: the grid of contract 5.2 is
    dense from `bar_of(created_at_ms)` to `bar_of(resolved_at_ms)` and a print stamped outside that range
    is either a provider quirk or a unit mistake, neither of which may silently move a bar.
    """
    if not isinstance(payload, Mapping):
        raise MalformedResponseError(
            "prices-history is not an object", provider=PROVIDER, type=type(payload).__name__
        )
    history = payload.get("history")
    if not isinstance(history, list):
        raise MalformedResponseError("prices-history carries no history array", provider=PROVIDER)
    step = interval_ms(interval_min)
    points: list[tuple[int, int]] = []
    for entry in history:
        if not isinstance(entry, Mapping):
            raise MalformedResponseError("history point is not an object", provider=PROVIDER)
        t_ms = round_half_up_decimal(_decimal(entry.get("t"), field="history[].t")) * PRICES_HISTORY_T_UNIT_MS
        price_bp = clamp_price_bp(round_half_up_decimal(_decimal(entry.get("p"), field="history[].p") * BP_ONE))
        if t_ms < first_bar_ms or t_ms >= last_bar_ms + step:
            continue
        points.append((t_ms, price_bp))
    points.sort()
    return tuple(points)


def _fetch_points(
    client: HttpClient,
    *,
    yes_token: str,
    interval_min: int,
    first_bar_ms: int,
    last_bar_ms: int,
    fidelity_min: int,
    history_interval: str,
) -> tuple[tuple[int, int], ...]:
    """The YES tape: the windowed query first, the whole-life query as the fallback.

    The CLOB documents two spellings of one query, `startTs` with `endTs` and `interval`, and the pair is
    the one that matches a dataset window to the millisecond, so it goes first and asks for exactly the
    bars the market has. `interval` is asked for only when the window answered with nothing to build a bar
    from, which is what a provider that honours one spelling and ignores the other looks like from here:
    the block means neither spelling can be confirmed against the live endpoint (`_provenance.json`), and a
    single unverifiable request shape would have been the whole tape or nothing.
    """
    step = interval_ms(interval_min)
    windowed: dict[str, str | int] = {
        "market": yes_token,
        "fidelity": fidelity_min,
        "startTs": first_bar_ms // PRICES_HISTORY_T_UNIT_MS,
        "endTs": (last_bar_ms + step) // PRICES_HISTORY_T_UNIT_MS,
    }
    points = _price_points(
        _get_payload(client, CLOB_PRICES_HISTORY_PATH, windowed),
        interval_min=interval_min,
        first_bar_ms=first_bar_ms,
        last_bar_ms=last_bar_ms,
    )
    if len(points) >= MIN_PRICE_POINTS:
        return points
    whole_life: dict[str, str | int] = {
        "market": yes_token,
        "fidelity": fidelity_min,
        "interval": history_interval,
    }
    return _price_points(
        _get_payload(client, CLOB_PRICES_HISTORY_PATH, whole_life),
        interval_min=interval_min,
        first_bar_ms=first_bar_ms,
        last_bar_ms=last_bar_ms,
    )


def _bars(
    points: Sequence[tuple[int, int]],
    *,
    interval_min: int,
    first_bar_ms: int,
    last_bar_ms: int,
    first_price_bp: int,
) -> tuple[tuple[Bar, ...], int]:
    """The dense bar grid and the count of bars the tape actually covered.

    A bar with no point repeats the previous close as `open = high = low = close = vwap` with
    `volume_milli = 0` (contract 5.2); the bars before the first point carry `first_price_bp`. `vwap_bp` is
    the unweighted mean of the points inside the bar, because the CLOB tape carries no size and a weighted
    mean would need one: the value stays inside `[low, high]`, which is what the schema checks.
    """
    step = interval_ms(interval_min)
    by_bar: dict[int, list[int]] = {}
    for t_ms, price_bp in points:
        by_bar.setdefault(bar_of(t_ms, interval_min), []).append(price_bp)
    bars: list[Bar] = []
    carried = first_price_bp
    traded_bars = 0
    for t_ms in range(first_bar_ms, last_bar_ms + step, step):
        prices = by_bar.get(t_ms)
        if prices:
            traded_bars += 1
            carried = prices[-1]
            bars.append(
                Bar(
                    t_ms=t_ms,
                    open_bp=prices[0],
                    high_bp=max(prices),
                    low_bp=min(prices),
                    close_bp=prices[-1],
                    vwap_bp=round_half_up(sum(prices), len(prices)),
                    volume_milli=0,
                    n_trades=0,
                    yes_bid_bp=None,
                    yes_ask_bp=None,
                    open_interest=None,
                )
            )
        else:
            bars.append(
                Bar(
                    t_ms=t_ms,
                    open_bp=carried,
                    high_bp=carried,
                    low_bp=carried,
                    close_bp=carried,
                    vwap_bp=carried,
                    volume_milli=0,
                    n_trades=0,
                    yes_bid_bp=None,
                    yes_ask_bp=None,
                    open_interest=None,
                )
            )
    return tuple(bars), traded_bars


# --------------------------------------------------------------------------------------------------
# One raw Gamma market to one v2 Market
# --------------------------------------------------------------------------------------------------
def _yes_index(outcomes: Sequence[object]) -> int | None:
    """The index of the YES leg of a binary market, or `None` when the market is not binary.

    Polymarket writes its binary legs `["Yes", "No"]` and its multi-outcome events as their own markets;
    anything that is not a two-leg yes/no pair is not this project's shape and is skipped rather than bent.
    """
    if len(outcomes) != 2:
        return None
    labels = [outcome.strip().lower() if isinstance(outcome, str) else "" for outcome in outcomes]
    if sorted(labels) != ["no", "yes"]:
        return None
    return labels.index("yes")


def _resolution(prices: Sequence[object], yes_index: int) -> int | None:
    """`1`, `0`, or `None` when the pair is not settled on one leg.

    A settled Polymarket pair pays one leg in full: `["1", "0"]` or `["0", "1"]`. A pair still quoting
    (`["0.62", "0.38"]`) is an open or a voided market and never enters a dataset (contract 7.4).
    """
    if len(prices) != 2:
        return None
    yes = _decimal(prices[yes_index], field="outcomePrices[yes]")
    no = _decimal(prices[1 - yes_index], field="outcomePrices[no]")
    if yes == 1 and no == 0:
        return 1
    if yes == 0 and no == 1:
        return 0
    return None


def _build_market(
    raw: Mapping[str, object],
    *,
    client: HttpClient,
    window_start_ms: int,
    window_end_ms: int,
    freeze_ms: int,
    interval_min: int,
    fidelity_min: int,
    history_interval: str,
) -> Market | None:
    """One eligible Gamma row plus its CLOB tape as a `Market`, or `None` when the row is not eligible.

    Not eligible, all silent and all documented: still open, not settled on one leg, not a two-leg yes/no
    pair, resolved outside `[window_start_ms, min(window_end_ms, freeze_ms))`, a life shorter than two
    bars, or a tape with fewer than two points. Malformed, all raised: a missing slug, an unparseable
    instant, no CLOB token for the YES leg, a history that is not an array. A missing question or
    description is neither: those fall back to the slug and to the empty string, because a market with a
    real tape and a thin label is still a scorable market.
    """
    if raw.get("closed") is not True:
        return None
    outcomes = _json_list(raw.get("outcomes"), field="outcomes")
    yes_index = _yes_index(outcomes)
    if yes_index is None:
        return None
    resolution = _resolution(_json_list(raw.get("outcomePrices"), field="outcomePrices"), yes_index)
    if resolution is None:
        return None

    slug_value = raw.get("slug")
    if not isinstance(slug_value, str) or not slug_value.strip():
        raise MalformedResponseError("market carries no slug", provider=PROVIDER)
    slug = market_slug(slug_value)

    close_source = raw.get("endDate") or raw.get("end_date_iso") or raw.get("closedTime")
    resolved_source = raw.get("closedTime") or raw.get("umaEndDate") or close_source
    created_source = raw.get("createdAt") or raw.get("startDate") or raw.get("startDateIso")
    close_raw_ms = _parse_instant_ms(close_source, field="endDate")
    resolved_at_ms = _parse_instant_ms(resolved_source, field="closedTime")
    created_at_ms = _parse_instant_ms(created_source, field="createdAt")
    # The venue sometimes settles before its own published close; `close_at_ms <= resolved_at_ms` is a
    # schema rule of contract 7.2, so the earlier of the two is the close.
    close_at_ms = min(close_raw_ms, resolved_at_ms)
    if not created_at_ms < close_at_ms:
        return None
    if not window_start_ms <= resolved_at_ms < min(window_end_ms, freeze_ms):
        return None

    first_bar_ms = bar_of(created_at_ms, interval_min)
    last_bar_ms = bar_of(resolved_at_ms, interval_min)
    if (last_bar_ms - first_bar_ms) // interval_ms(interval_min) + 1 < MIN_BARS:
        return None

    token_ids = _json_list(raw.get("clobTokenIds"), field="clobTokenIds")
    if len(token_ids) <= yes_index or not isinstance(token_ids[yes_index], str):
        raise MalformedResponseError("market exposes no CLOB token for its YES leg", provider=PROVIDER, slug=slug)
    yes_token = str(token_ids[yes_index]).strip()
    if not yes_token:
        raise MalformedResponseError("market exposes an empty CLOB token", provider=PROVIDER, slug=slug)

    points = _fetch_points(
        client,
        yes_token=yes_token,
        interval_min=interval_min,
        first_bar_ms=first_bar_ms,
        last_bar_ms=last_bar_ms,
        fidelity_min=fidelity_min,
        history_interval=history_interval,
    )
    if len(points) < MIN_PRICE_POINTS:
        return None

    first_price_bp = points[0][1]
    bars, traded_bars = _bars(
        points,
        interval_min=interval_min,
        first_bar_ms=first_bar_ms,
        last_bar_ms=last_bar_ms,
        first_price_bp=first_price_bp,
    )
    tags = _tag_slugs(raw)
    provider_id = raw.get("id") or raw.get("conditionId") or slug_value
    volume_total = raw.get("volume") if raw.get("volume") is not None else raw.get("volumeNum")
    volume_milli_total = (
        round_half_up_decimal(_decimal(volume_total, field="volume") * 1_000) if volume_total is not None else 0
    )
    quality = MarketQuality(
        n_trades=0,
        unique_bettors=None,
        life_days=(resolved_at_ms - created_at_ms) // MS_PER_DAY,
        volume_milli_total=max(0, volume_milli_total),
        traded_bars=traded_bars,
    )
    return Market(
        schema_version=MARKET_SCHEMA,
        id=f"{PROVIDER}-{slug}",
        provider=PROVIDER,
        provider_id=_text(str(provider_id), limit=PROVIDER_ID_MAX, default=slug),
        url=_url(raw, slug_value.strip()),
        question=_text(raw.get("question"), limit=QUESTION_MAX, default=slug),
        description=_text(raw.get("description"), limit=DESCRIPTION_MAX),
        category=_category(raw, tags),
        tags=tags,
        # Polymarket publishes no article titles, and inventing one from the question would feed the
        # linker of contract 7.6 a guess it would then score as evidence.
        wiki_subjects=(),
        currency="usd",
        source="imported",
        created_at_ms=created_at_ms,
        close_at_ms=close_at_ms,
        resolved_at_ms=resolved_at_ms,
        resolution=resolution,
        resolution_source=_text(raw.get("resolutionSource"), limit=RESOLUTION_SOURCE_MAX, default="venue"),
        # Contract 7.2 assigns `event_key` from Kalshi's `event_ticker` and Manifold's `groupSlugs[0]` and
        # `null` everywhere else. Gamma's `events[0].slug` would be the natural block key of 12.3; taking
        # it is a contract change, not an importer decision, so it is reported and not taken.
        event_key=None,
        interval_min=interval_min,
        bars=bars,
        trades=(),
        first_price_bp=first_price_bp,
        final_price_bp=bars[-1].close_bp,
        hardness_tags=(),
        quality=quality,
        fee_schedule_id=POLYMARKET_FEE_SCHEDULE_ID,
        notes=_text(
            f"Imported from Polymarket Gamma metadata and CLOB prices-history "
            f"(interval={history_interval}, fidelity={fidelity_min} min, {len(points)} points over "
            f"{len(bars)} bars, {traded_bars} of them covered by the tape). The CLOB price history carries "
            f"no size, so every bar reports volume_milli 0 and trades is empty.",
            limit=NOTES_MAX,
        ),
    )


# --------------------------------------------------------------------------------------------------
# Discovery and the public importer
# --------------------------------------------------------------------------------------------------
def _gamma_rows(payload: object, *, path: str) -> tuple[Mapping[str, object], ...]:
    """The market rows of a Gamma answer, which is a bare array on `/markets`."""
    if isinstance(payload, Mapping):
        for key in ("data", "markets"):
            nested = payload.get(key)
            if isinstance(nested, list):
                payload = nested
                break
    if not isinstance(payload, list):
        raise MalformedResponseError(
            "gamma answered with no market array", provider=PROVIDER, path=path, type=type(payload).__name__
        )
    rows: list[Mapping[str, object]] = []
    for row in payload:
        if not isinstance(row, Mapping):
            raise MalformedResponseError("gamma market row is not an object", provider=PROVIDER, path=path)
        rows.append(row)
    return tuple(rows)


def import_polymarket(
    *,
    client: HttpClient,
    window_start_ms: int,
    window_end_ms: int,
    freeze_ms: int,
    limit: int | None = None,
    gamma_client: HttpClient | None = None,
    slugs: Sequence[str] | None = None,
    interval_min: int = 1_440,
    fidelity_min: int = DEFAULT_FIDELITY_MIN,
    history_interval: str = DEFAULT_PRICES_HISTORY_INTERVAL,
    page_size: int = GAMMA_PAGE_SIZE,
) -> tuple[Market, ...]:
    """Import settled binary Polymarket markets that resolved inside the window.

    The five keyword arguments of contract 7.12 are the whole calling convention D6 needs; the rest carry
    defaults and exist because the contract's importer signature has no room for them:

    - `gamma_client`: the metadata host. Polymarket answers metadata on `gamma-api` and the tape on
      `clob`, `HttpClient` binds one `base_url` and joins paths onto it by string (contract 7.11), so one
      client cannot reach both. Hand the second one here; when it is absent, `client` is read for its
      User-Agent, throttle, cache directory and proxy and a sibling client for the other host is derived
      and closed on the way out. `client` may be either host: the one whose base URL names `gamma` is the
      metadata client. Reported as a contract issue against 7.11 and 7.12.
    - `slugs`: import exactly these markets by slug (`/markets?slug=`), which is the v1 path this module
      ports and the only way to import a single named tape.
    - `interval_min`, `fidelity_min`, `history_interval`, `page_size`: the grid and the provider's
      pagination. The grid is `BuildConfig.interval_min` in D6's hands and the contract's importer
      signature does not carry it, which is the second reported issue.

    Raises `ProviderBlockedError` on the ANJ block, at the first request and without a retry.
    """
    if interval_min not in INTERVALS_MIN:
        raise InvalidConfigError("interval_min is not a contract grid", interval_min=interval_min)
    if history_interval not in PRICES_HISTORY_INTERVALS:
        raise InvalidConfigError("history_interval is not a prices-history interval", value=history_interval)
    if fidelity_min < 1:
        raise InvalidConfigError("fidelity_min is in minutes and at least one", fidelity_min=fidelity_min)
    if page_size < 1:
        raise InvalidConfigError("page_size is at least one", page_size=page_size)
    if limit is not None and limit < 0:
        raise InvalidConfigError("limit is not negative", limit=limit)

    tape_client, metadata_client, derived = _resolve_clients(client, gamma_client)
    metadata_path = GAMMA_MARKETS_PATH
    window_top_ms = min(window_end_ms, freeze_ms)

    markets: list[Market] = []
    seen_ids: set[str] = set()

    def keep(row: Mapping[str, object]) -> bool:
        """Map one row and record the market; `False` once `limit` is reached."""
        if limit is not None and len(markets) >= limit:
            return False
        market = _build_market(
            row,
            client=tape_client,
            window_start_ms=window_start_ms,
            window_end_ms=window_end_ms,
            freeze_ms=freeze_ms,
            interval_min=interval_min,
            fidelity_min=fidelity_min,
            history_interval=history_interval,
        )
        if market is not None and market.id not in seen_ids:
            seen_ids.add(market.id)
            markets.append(market)
        return limit is None or len(markets) < limit

    try:
        if slugs is not None:
            for slug in slugs:
                payload = _get_payload(metadata_client, metadata_path, {"slug": slug})
                rows = _gamma_rows(payload, path=metadata_path)
                if not rows:
                    raise MalformedResponseError("no market for slug", provider=PROVIDER, slug=slug)
                if not keep(rows[0]):
                    break
        else:
            for page in range(GAMMA_MAX_PAGES):
                payload = _get_payload(
                    metadata_client,
                    metadata_path,
                    {
                        "closed": "true",
                        "limit": page_size,
                        "offset": page * page_size,
                        "order": "endDate",
                        "ascending": "true",
                        "end_date_min": _iso_z(window_start_ms),
                        "end_date_max": _iso_z(window_top_ms),
                    },
                )
                rows = _gamma_rows(payload, path=metadata_path)
                room = True
                for row in rows:
                    room = keep(row)
                    if not room:
                        break
                if not room or len(rows) < page_size:
                    break
    finally:
        for extra in derived:
            extra.close()

    # Canonical order of contract section 3: `(resolved_at_ms, id)` ascending.
    return sort_markets(markets)
