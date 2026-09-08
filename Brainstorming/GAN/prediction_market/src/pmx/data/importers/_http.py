"""The one HTTP client every pmx importer and news fetcher reaches the network through.

Why a single class rather than four: D2, D3, D4 and D5 are written in parallel, they all touch the impure
edge of the system, and politeness towards a provider is only real if it is unavoidable (CONTRACTS_V2 7.11,
decision D-11). Sharing one client makes the three rules that keep us welcome inescapable: a descriptive
User-Agent carrying a contact address, a minimum interval between two requests to the same host, and
exponential backoff on ``429`` and ``5xx``. It also makes a rebuild cheap, because every successful response
is written to an on-disk cache under the dataset directory: the second build of the same window issues no
request at all, which is what lets a reviewer reproduce a dataset offline.

This module is deliberately the only place in ``pmx`` that reads a clock. Throttling has to know how long
ago the last request went out, so the clock is real; it is ``time.monotonic_ns`` so that every interval is
integer milliseconds, and no value it produces ever reaches a journal, a score, a hash or a dataset file.
The three seams a test uses instead of a socket (``transport``, ``clock``, ``sleeper``) are keyword-only
extensions of the contracted signature, so an offline test is exact rather than approximate: nothing in
the package sleeps for real time and nothing opens a connection.
"""

from __future__ import annotations

import hashlib
import json
import os
import ssl
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import httpx

from pmx import __version__
from pmx.errors import InvalidConfigError, MalformedResponseError, NotConfiguredError, ProviderError
from pmx.journal import JOURNAL_ENCODING, JOURNAL_NEWLINE, canonical_json


def evenly_spaced[T](items: Sequence[T], limit: int | None) -> tuple[T, ...]:
    """At most ``limit`` of ``items``, spread evenly over the whole sequence rather than over its head.

    This is the one spelling of an importer's **fetch budget**, and it lives beside the client for the
    reason the client itself is shared: it is a rule about how much of a provider we ask for. It is not
    the dataset's cap, which is the builder's and is applied after the window has been walked and
    filtered (CONTRACTS_V2 7.4, ``limit_per_provider``).

    What it fixes: a settled Kalshi listing narrowed to the 731 series of the first real build carries
    54 333 markets inside a twelve-month window and each one costs a candlestick request plus a trade
    request, and a year of Manifold resolutions is of the same order, so no build fetches every tape. The
    previous spelling stopped the walk after ``limit`` markets, which staged the first two days of the
    year from one provider and the last thirteen days from the other, and every surviving market landed
    in one fold. Taking ``limit`` items at equal stride keeps the whole window represented whatever the
    budget is; it is arithmetic on the index, so two runs over the same listing fetch the same tapes.
    """
    total = len(items)
    if limit is None or limit <= 0 or total <= limit:
        return tuple(items)
    return tuple(items[(index * total) // limit] for index in range(limit))


DEFAULT_MIN_INTERVAL_MS: Final = 1_000
HTTP_MAX_RETRIES: Final = 3
HTTP_TIMEOUT_S: Final = 30.0  # a float, and one of the four legal float sites: never journaled
USER_AGENT_TEMPLATE: Final = "pmx-research/{version} (contact: {contact})"
USER_AGENT_CONTACT_ENV: Final = "PMX_USER_AGENT_CONTACT"
HTTP_PROXY_ENV: Final = "PMX_HTTP_PROXY"

#: The one status outside ``5xx`` that earns a retry: the provider is asking us to slow down.
HTTP_TOO_MANY_REQUESTS: Final = 429

#: Wordings that identify a TLS or certificate verification failure when the exception chain does not
#: carry an ``ssl.SSLError`` (httpx wraps some of them). Read by :func:`is_certificate_failure`.
CERTIFICATE_FAILURE_MARKERS: Final = (
    "certificate verify failed",
    "certificate is not valid",
    "hostname mismatch",
    "sslcertverificationerror",
    "ssl: ",
)

#: A ``path`` beginning with one of these is a URL of its own and is not joined to ``base_url``.
ABSOLUTE_URL_SCHEMES: Final = ("http://", "https://")

NS_PER_MS: Final = 1_000_000
MS_PER_SECOND: Final = 1_000


def sleep_ms(duration_ms: int) -> None:
    """Sleep ``duration_ms`` milliseconds. The one conversion to seconds in the package."""
    if duration_ms > 0:
        time.sleep(duration_ms / MS_PER_SECOND)


def is_certificate_failure(exc: BaseException) -> bool:
    """Whether ``exc`` is a TLS or certificate verification failure rather than a transient fault.

    Retrying one of these is worse than useless: the certificate a host serves does not change between
    two handshakes a second apart, and where a regulator has taken the DNS record over (D4's ANJ wall,
    section 13.1) three extra handshakes only delay the ``ProviderBlockedError`` the caller must see.
    CPython does not name the certificate in the message, so the exception chain is inspected first and
    the wording only as a fallback (ruling R92).
    """
    seen: list[BaseException] = []
    current: BaseException | None = exc
    while current is not None and len(seen) < 8:
        seen.append(current)
        if isinstance(current, ssl.SSLError):
            return True
        current = current.__cause__ or current.__context__
    text = " ".join(str(item) for item in seen).lower()
    return any(marker in text for marker in CERTIFICATE_FAILURE_MARKERS)


def build_user_agent(contact: str | None = None) -> str:
    """The descriptive User-Agent of CONTRACTS_V2 7.11, filled with the version and a contact address.

    Wikipedia answers ``403`` to a bare agent string and Kalshi rate-limits one harder, so a fetcher that
    finds ``PMX_USER_AGENT_CONTACT`` unset gets a :class:`NotConfiguredError` here rather than a confusing
    provider failure three calls later.
    """
    resolved = contact if contact is not None else os.environ.get(USER_AGENT_CONTACT_ENV, "")
    if not resolved.strip():
        raise NotConfiguredError(
            "no contact address for the HTTP User-Agent", env=USER_AGENT_CONTACT_ENV, provider="all"
        )
    return USER_AGENT_TEMPLATE.format(version=__version__, contact=resolved.strip())


def cache_key(method: str, url: str, params: Mapping[str, str | int] | None) -> str:
    """``sha256(method + " " + url + " " + canonical_json(params or {}))`` (CONTRACTS_V2 7.11).

    The parameters are hashed through ``canonical_json`` rather than through the query string so that two
    calls that differ only in the order of their keyword arguments share one cache entry.
    """
    payload = canonical_json(dict(params or {}))
    return hashlib.sha256(f"{method} {url} {payload}".encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class _Response:
    """What the cache stores and what a request returns: the three fields of CONTRACTS_V2 7.11."""

    status: int
    headers: Mapping[str, str]
    body: str

    def to_dict(self) -> dict[str, object]:
        return {"status": self.status, "headers": dict(self.headers), "body": self.body}


def _read_cache(path: Path) -> _Response | None:
    """The cached response at ``path``, or ``None`` for a miss.

    A file that is unreadable or is not the declared shape counts as a miss and is overwritten: the cache
    is documented as deletable at any time, so a corrupt entry must never be able to fail a build.
    """
    if not path.exists():
        return None
    try:
        with open(path, encoding=JOURNAL_ENCODING, newline=JOURNAL_NEWLINE) as handle:
            payload = json.load(handle)
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    status = payload.get("status")
    headers = payload.get("headers")
    body = payload.get("body")
    if not isinstance(status, int) or isinstance(status, bool) or not isinstance(body, str):
        return None
    if not isinstance(headers, dict) or any(not isinstance(value, str) for value in headers.values()):
        return None
    return _Response(status=status, headers={str(key): value for key, value in headers.items()}, body=body)


def _write_cache(path: Path, response: _Response) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding=JOURNAL_ENCODING, newline=JOURNAL_NEWLINE) as handle:
        handle.write(canonical_json(response.to_dict()) + JOURNAL_NEWLINE)


class HttpClient:
    """A throttled, cached, backing-off HTTP client for one provider host (CONTRACTS_V2 7.11).

    One instance is one ``base_url``: the throttle is per instance because the politeness rule is per host.
    ``get_json`` and ``get_text`` are the whole surface an importer needs; neither ever raises an httpx
    exception, so the callers only have to know ``ProviderError`` and ``MalformedResponseError``.
    """

    def __init__(
        self,
        *,
        base_url: str,
        user_agent: str,
        min_interval_ms: int,
        cache_dir: Path,
        max_retries: int = HTTP_MAX_RETRIES,
        timeout_s: float = HTTP_TIMEOUT_S,
        api_key: str | None = None,
        proxy: str | None = None,
        transport: httpx.BaseTransport | None = None,
        clock: Callable[[], int] = time.monotonic_ns,
        sleeper: Callable[[int], None] = sleep_ms,
    ) -> None:
        if min_interval_ms < 0:
            raise InvalidConfigError("min_interval_ms is negative", min_interval_ms=min_interval_ms)
        if max_retries < 0:
            raise InvalidConfigError("max_retries is negative", max_retries=max_retries)
        if not user_agent.strip():
            raise InvalidConfigError("user_agent is empty", base_url=base_url)
        self.base_url = base_url.rstrip("/")
        self.user_agent = user_agent
        self.min_interval_ms = min_interval_ms
        self.cache_dir = Path(cache_dir)
        self.max_retries = max_retries
        self.timeout_s = timeout_s
        self.proxy = proxy if proxy is not None else (os.environ.get(HTTP_PROXY_ENV) or None)
        #: Requests actually sent, cache hits excluded. Read by tests and by the builder's report.
        self.requests_made = 0
        self._headers: dict[str, str] = {"User-Agent": user_agent, "Accept": "application/json"}
        if api_key is not None and api_key.strip():
            self._headers["Authorization"] = f"Bearer {api_key.strip()}"
        self._clock = clock
        self._sleeper = sleeper
        self._last_request_ns: int | None = None
        self._client = httpx.Client(
            headers=self._headers,
            timeout=timeout_s,
            transport=transport,
            proxy=None if transport is not None else self.proxy,
            follow_redirects=True,
        )

    # -- the public surface ------------------------------------------------------------------------
    def get_json(
        self, path: str, params: Mapping[str, str | int] | None = None, *, cache: bool = True
    ) -> object:
        """The parsed JSON body of ``GET path``. A body that is not JSON is a `MalformedResponseError`."""
        response = self._fetch("GET", path, params, cache=cache)
        try:
            return json.loads(response.body)
        except ValueError as exc:
            raise MalformedResponseError(
                "the response body is not JSON",
                url=self._absolute_url(path),
                status=response.status,
                head=response.body[:120],
            ) from exc

    def get_text(
        self, path: str, params: Mapping[str, str | int] | None = None, *, cache: bool = True
    ) -> str:
        """The body of ``GET path`` verbatim, for the providers that answer HTML or CSV."""
        return self._fetch("GET", path, params, cache=cache).body

    def close(self) -> None:
        self._client.close()

    # -- internals --------------------------------------------------------------------------------
    def _absolute_url(self, path: str) -> str:
        """``base_url`` joined with ``path``, unless ``path`` is already absolute (ruling R91).

        The client always requests an absolute URL so that the URL the cache key hashes and the URL that
        goes out are the same string. A ``path`` that already carries a scheme is returned verbatim: D4
        needs two hosts for one provider (Gamma for the metadata, the CLOB for the tape), and the earlier
        spelling silently produced ``https://clob.polymarket.com/https://gamma-api.polymarket.com/markets``
        and then reported a provider shape change. A second host still deserves a second client, because
        the throttle is per host; this only makes the mistake impossible instead of invisible.
        """
        if path.startswith(ABSOLUTE_URL_SCHEMES):
            return path
        return f"{self.base_url}/{path.lstrip('/')}" if path else self.base_url

    def _cache_path(self, key: str) -> Path:
        return self.cache_dir / key[:2] / f"{key}.json"

    def _fetch(
        self, method: str, path: str, params: Mapping[str, str | int] | None, *, cache: bool
    ) -> _Response:
        url = self._absolute_url(path)
        on_disk = self._cache_path(cache_key(method, url, params))
        if cache:
            hit = _read_cache(on_disk)
            if hit is not None:
                return hit
        response = self._request_with_retries(method, url, params)
        if 200 <= response.status < 300:
            # Only a success is worth keeping: caching a redirect or a partial answer would serve it back
            # forever, and every failure already raised before reaching here.
            _write_cache(on_disk, response)
        return response

    def _backoff_ms(self, attempt: int) -> int:
        """``min_interval_ms * 2 ** attempt``, the wait before retry number ``attempt + 1``.

        Spelled as a shift because ``int ** int`` is typed ``Any``, and a doubling is exactly a shift here.
        """
        return self.min_interval_ms << attempt

    def _throttle(self) -> None:
        """Hold the floor of ``min_interval_ms`` between two requests from this client."""
        if self.min_interval_ms <= 0:
            return
        if self._last_request_ns is not None:
            elapsed_ms = (self._clock() - self._last_request_ns) // NS_PER_MS
            if elapsed_ms < self.min_interval_ms:
                self._sleeper(self.min_interval_ms - elapsed_ms)
        self._last_request_ns = self._clock()

    def _request_with_retries(
        self, method: str, url: str, params: Mapping[str, str | int] | None
    ) -> _Response:
        """One request, retried on ``429``, on ``5xx`` and on a transport failure, never on another ``4xx``.

        ``max_retries`` retries follow the first attempt, so at most ``max_retries + 1`` requests go out;
        the wait before retry ``n`` is ``min_interval_ms * 2 ** (n - 1)``. A TLS or certificate failure is
        the one transport failure that is not retried (ruling R92): it is a verdict about the host, and
        D4's block detector has to see it on the first attempt.
        """
        attempt = 0
        while True:
            last = attempt == self.max_retries
            self._throttle()
            self.requests_made += 1
            try:
                response = self._client.request(method, url, params=params)
            except httpx.HTTPError as exc:
                if is_certificate_failure(exc):
                    raise ProviderError(
                        "the host served a certificate this client refuses",
                        url=url,
                        attempts=attempt + 1,
                        certificate_failure="true",
                        cause=str(exc),
                    ) from exc
                if last:
                    raise ProviderError(
                        "the request failed", url=url, attempts=attempt + 1, cause=str(exc)
                    ) from exc
                self._sleeper(self._backoff_ms(attempt))
                attempt += 1
                continue
            status = response.status_code
            if status == HTTP_TOO_MANY_REQUESTS or 500 <= status < 600:
                if last:
                    raise ProviderError(
                        "the provider kept refusing the request",
                        url=url,
                        status=status,
                        attempts=attempt + 1,
                    )
                self._sleeper(self._backoff_ms(attempt))
                attempt += 1
                continue
            if 400 <= status < 500:
                raise ProviderError(
                    "the provider refused the request", url=url, status=status, head=response.text[:120]
                )
            return _Response(status=status, headers=dict(response.headers), body=response.text)
