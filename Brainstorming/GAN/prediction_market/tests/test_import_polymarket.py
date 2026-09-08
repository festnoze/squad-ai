"""D4: the Polymarket importer and the ANJ block detector, offline.

Two things are tested here and they are not the same thing.

The **block detector** is tested against evidence, not against a story. On 2026-09-07 the three
Polymarket API hosts answered this machine with one certificate for `*.anj.fr` and, over plain TLS, with
a 14 KB French block page behind a `200`. Both are recorded under `tests/fixtures/d4/`
(`anj_block_page.html`, `anj_block_response.json`) and every detector test reads them from disk, so the
tests hold in a jurisdiction where Polymarket is reachable and keep holding here. The property they pin is
the one D4 exists for: a block raises `ProviderBlockedError` after exactly **one** request, because a DNS
answer and a certificate do not become truer on the fourth handshake.

The **import** is tested against synthesized Gamma and CLOB payloads whose shapes are copied from the
provider's documented fields (`_provenance.json` says which file is recorded and which is written by hand,
and why the live shapes could not be recorded from here). Those tests pin the mapping the contract states:
prices in basis points through `Decimal` and never through a float, a dense daily grid that carries the
previous close, ids and categories inside their regexes, the canonical `(resolved_at_ms, id)` order, and
the market validating against `src/pmx/schemas/market.v2.json` field by field.

The schema is read from the package directory rather than through `pmx.data.schema.load_schema`: this file
validates the bytes C0 shipped, and does it without waiting for another wave-1 package to land.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import ssl
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

import pmx
from pmx.data.importers import polymarket as poly
from pmx.errors import (
    InvalidConfigError,
    MalformedResponseError,
    NotConfiguredError,
    ProviderBlockedError,
    ProviderError,
)
from pmx.types import MS_PER_DAY, RE_MARKET_ID, Market, bar_of

FIXTURES = Path(__file__).parent / "fixtures" / "d4"
SCHEMA_PATH = Path(pmx.__file__).parent / "schemas" / "market.v2.json"

#: The freeze of the reference dataset (2026-09-07, PRD AC-1) and the window it implies. The literal is
#: spelled out rather than copied from the contract's units table, whose worked example reads
#: `1_757_203_200_000 is 2026-09-07T00:00:00Z` and is a year off (that instant is 2025-09-07): a package
#: that copied it would build a window shifted by twelve months. Reported as a contract issue.
FREEZE_MS = 1_788_739_200_000
WINDOW_START_MS = FREEZE_MS - 365 * MS_PER_DAY
WINDOW_END_MS = FREEZE_MS - MS_PER_DAY

LISTING_PAGES = ("gamma_markets_page1.json", "gamma_markets_page2.json")
PAGE_SIZE = 6

SLUG_A = "will-eth-close-above-4000-on-2026-03-31"
SLUG_B = "will-atlas-fc-win-the-2026-continental-cup"
SLUG_H = (
    "will-the-federal-reserve-cut-the-target-rate-by-at-least-fifty-basis-points-at-its-"
    "july-2026-meeting-according-to-the-fomc-statement"
)
ID_A = f"polymarket-{SLUG_A}"
ID_B = f"polymarket-{SLUG_B}"
#: The slugs of the six rows that must never reach a dataset, and the CLOB tokens they carry: a skipped
#: row must be skipped before its tape is fetched.
SKIPPED_SLUGS = (
    "will-the-mission-launch-before-2027",
    "who-will-be-the-2026-nominee",
    "will-the-treaty-be-signed-in-2026",
    "will-the-index-close-above-7000-on-2026-09-18",
    "will-the-2024-season-end-before-march-2024",
)
SKIPPED_TOKENS = tuple(str(n) for n in range(1, 12))


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _rows(name: str) -> list[dict[str, Any]]:
    loaded = json.loads(_read(name))
    assert isinstance(loaded, list)
    return loaded


def _index() -> tuple[dict[str, str], dict[str, str]]:
    """`(slug -> gamma id, clob token -> gamma id)` over the recorded listing pages.

    The stub answers `/prices-history` by token, exactly as the provider is addressed, so the mapping to a
    fixture file has to come from the listing itself rather than from a hand-written table that could
    disagree with it.
    """
    slug_to_id: dict[str, str] = {}
    token_to_id: dict[str, str] = {}
    for page in LISTING_PAGES:
        for row in _rows(page):
            market_id = str(row["id"])
            slug_to_id[str(row["slug"])] = market_id
            for token in json.loads(str(row["clobTokenIds"])):
                token_to_id[str(token)] = market_id
    return slug_to_id, token_to_id


SLUG_TO_ID, TOKEN_TO_ID = _index()


EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def ms(stamp: str) -> int:
    """A strict `yyyy-mm-ddThh:mm:ss[.fff]Z` instant as epoch milliseconds, for the expected values.

    Strict on purpose: the importer's own parser is tolerant of three provider spellings, and a test that
    reused it could not tell a parsing bug from a mapping bug.
    """
    parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    return (parsed.astimezone(UTC) - EPOCH) // timedelta(milliseconds=1)


# --------------------------------------------------------------------------------------------------
# The stub client: the whole `HttpClient` surface D4 uses, plus a request log
# --------------------------------------------------------------------------------------------------
class StubClient:
    """Answers from `tests/fixtures/d4` and records every request; never opens a socket.

    It carries the public attributes of `HttpClient` that the importer reads (`base_url`, `user_agent`,
    `min_interval_ms`, `cache_dir`, `max_retries`, `timeout_s`, `proxy`), because deriving the second
    host's client from the first is part of the contract issue D4 reports and has to be testable.
    """

    def __init__(
        self,
        *,
        pages: Sequence[str] = LISTING_PAGES,
        page_size: int = PAGE_SIZE,
        body: str | None = None,
        error: BaseException | None = None,
        overrides: Mapping[str, str] | None = None,
        empty_window: bool = False,
        base_url: str = poly.CLOB_BASE_URL,
    ) -> None:
        self.base_url = base_url
        self.user_agent = "pmx-research/2.0.0-dev (contact: d4@example.org)"
        self.min_interval_ms = 0
        self.cache_dir = Path("tests-never-write-here")
        self.max_retries = 3
        self.timeout_s = 30.0
        self.proxy: str | None = None
        self.requests: list[tuple[str, dict[str, object]]] = []
        self.closed = 0
        self._pages = tuple(pages)
        self._page_size = page_size
        self._body = body
        self._error = error
        self._overrides = dict(overrides or {})
        self._empty_window = empty_window

    # -- the surface of contract 7.11 ---------------------------------------------------------------
    def get_text(self, path: str, params: Mapping[str, str | int] | None = None, *, cache: bool = True) -> str:
        self.requests.append((path, dict(params or {})))
        if self._error is not None:
            raise self._error
        if self._body is not None:
            return self._body
        if path in self._overrides:
            return self._overrides[path]
        return self._fixture(path, dict(params or {}))

    def get_json(self, path: str, params: Mapping[str, str | int] | None = None, *, cache: bool = True) -> object:
        raise AssertionError("D4 reads text and parses with parse_float=Decimal, never get_json")

    def close(self) -> None:
        self.closed += 1

    # -- the fixture router --------------------------------------------------------------------------
    def _fixture(self, path: str, params: Mapping[str, object]) -> str:
        if path == poly.GAMMA_MARKETS_PATH:
            slug = params.get("slug")
            if slug is not None:
                return _read(f"gamma_market_slug_{SLUG_TO_ID[str(slug)]}.json")
            page = int(str(params.get("offset", 0))) // self._page_size
            return _read(self._pages[page]) if page < len(self._pages) else "[]"
        if path == poly.CLOB_PRICES_HISTORY_PATH:
            token = str(params["market"])
            if self._empty_window and "startTs" in params:
                # A provider that honours `interval` and ignores the window pair answers like this.
                return '{"history": []}'
            return _read(f"clob_prices_history_{TOKEN_TO_ID[token]}.json")
        raise AssertionError(f"the importer asked for an unexpected path: {path}")

    # -- what the assertions read --------------------------------------------------------------------
    def paths(self, path: str) -> list[dict[str, object]]:
        return [params for requested, params in self.requests if requested == path]


#: The stub's own knobs, which are not arguments of `import_polymarket`. `page_size` is in both: the
#: provider's page size and the caller's have to agree or the fixtures would answer the wrong page.
STUB_ONLY = ("pages", "body", "error", "overrides", "empty_window")


def clients(**kwargs: Any) -> tuple[StubClient, StubClient]:
    """A `(clob, gamma)` stub pair, one request log each, because they are two hosts."""
    tape = StubClient(base_url=poly.CLOB_BASE_URL, **kwargs)
    metadata = StubClient(base_url=poly.GAMMA_BASE_URL, **kwargs)
    return tape, metadata


def run_import(**kwargs: Any) -> tuple[tuple[Market, ...], StubClient, StubClient]:
    """The fixture-backed import over the reference window, and the two stubs it went through."""
    stub_kwargs = {key: kwargs.pop(key) for key in STUB_ONLY if key in kwargs}
    page_size = int(kwargs.pop("page_size", PAGE_SIZE))
    tape, metadata = clients(page_size=page_size, **stub_kwargs)
    call: dict[str, Any] = {
        "window_start_ms": WINDOW_START_MS,
        "window_end_ms": WINDOW_END_MS,
        "freeze_ms": FREEZE_MS,
        "page_size": page_size,
    }
    call.update(kwargs)
    markets = poly.import_polymarket(
        client=tape,  # type: ignore[arg-type]
        gamma_client=metadata,  # type: ignore[arg-type]
        **call,
    )
    return markets, tape, metadata


def market_by_id(markets: Sequence[Market], market_id: str) -> Market:
    matches = [market for market in markets if market.id == market_id]
    assert len(matches) == 1, [market.id for market in markets]
    return matches[0]


# --------------------------------------------------------------------------------------------------
# The recorded evidence
# --------------------------------------------------------------------------------------------------
def test_the_freeze_instant_is_the_one_the_calendar_says() -> None:
    """The window arithmetic of every other test rests on this one integer."""
    assert ms("2026-09-07T00:00:00Z") == FREEZE_MS
    assert ms("2025-09-07T00:00:00Z") == WINDOW_START_MS
    assert ms("2026-09-06T00:00:00Z") == WINDOW_END_MS


def test_the_recorded_block_page_is_the_page_that_was_served() -> None:
    """The fixture is intact and carries no HTTP-level signal: only its content identifies the block."""
    recorded = json.loads(_read("anj_block_response.json"))
    body = (FIXTURES / recorded["body_file"]).read_bytes()
    assert hashlib.sha256(body).hexdigest() == recorded["body_sha256"]
    assert recorded["status"] == 200
    assert recorded["headers"]["content-type"] == "text/html"
    assert recorded["certificate"]["dns_names"] == ["*.anj.fr", "anj.fr"]
    assert "anj.fr" in body.decode("utf-8")


def test_the_block_page_body_is_detected() -> None:
    assert poly.anj_block_reason(body=_read("anj_block_page.html")) == poly.BLOCK_REASON_ANJ_BODY


def test_a_provider_payload_is_not_a_block() -> None:
    """The detector must not fire on the thing it is supposed to let through."""
    assert poly.anj_block_reason(body=_read("gamma_markets_page1.json")) is None
    assert poly.anj_block_reason(body=_read("clob_prices_history_512901.json")) is None
    assert poly.anj_block_reason(body='{"history": []}') is None
    assert poly.anj_block_reason() is None
    # A market that asks about the regulator is a market, not a block page: a JSON body is the provider
    # answering, whatever it says.
    payload = '[{"question": "Will the ANJ unblock anj.fr listed sites in 2027?", "closed": false}]'
    assert poly.anj_block_reason(body=payload) is None


def test_the_recorded_certificate_failure_is_detected_through_the_cause_chain() -> None:
    """The wrapper says nothing; the `ssl` cause says everything. The detector reads the chain."""
    recorded = json.loads(_read("anj_block_response.json"))
    message = recorded["tls_error"]["message"]
    assert "anj" not in message.lower()  # CPython 3.12 names the host asked for, not the certificate
    wrapper = ProviderError("the request failed", url=poly.GAMMA_BASE_URL, attempts=1)
    wrapper.__cause__ = ssl.SSLCertVerificationError(message)
    assert poly.anj_block_reason(error=wrapper) == poly.BLOCK_REASON_FOREIGN_CERTIFICATE


def test_a_certificate_that_names_anj_is_detected_as_the_anj() -> None:
    """The spelling of a stack that lists the certificate's names, which is the stronger signature."""
    older = ssl.SSLCertVerificationError(
        "hostname 'gamma-api.polymarket.com' doesn't match either of '*.anj.fr', 'anj.fr'"
    )
    assert poly.anj_block_reason(error=older) == poly.BLOCK_REASON_ANJ_CERTIFICATE


def test_an_ordinary_transport_failure_is_not_a_block() -> None:
    """A reset connection is a retryable failure and must keep its own error and its own diagnosis."""
    failure = ProviderError("the request failed", url=poly.CLOB_BASE_URL, attempts=4, cause="connection reset")
    assert poly.anj_block_reason(error=failure) is None
    assert poly.anj_block_reason(error=TimeoutError("timed out")) is None


# --------------------------------------------------------------------------------------------------
# The block, end to end: one request, no retry
# --------------------------------------------------------------------------------------------------
def test_the_block_page_stops_the_import_at_the_first_request() -> None:
    with pytest.raises(ProviderBlockedError) as raised:
        run_import(body=_read("anj_block_page.html"))
    assert type(raised.value) is ProviderBlockedError
    assert raised.value.message == poly.ANJ_BLOCK_MESSAGE
    assert raised.value.context["reason"] == poly.BLOCK_REASON_ANJ_BODY
    assert raised.value.context["provider"] == "polymarket"
    assert raised.value.context["url"] == f"{poly.GAMMA_BASE_URL}{poly.GAMMA_MARKETS_PATH}"


def test_the_block_page_is_not_reported_as_a_parse_failure() -> None:
    """A 14 KB HTML page behind a 200 would otherwise surface as "the body is not JSON", which sends the
    reader after a provider shape change that never happened."""
    tape, metadata = clients(body=_read("anj_block_page.html"))
    with pytest.raises(ProviderBlockedError):
        poly.import_polymarket(
            client=tape,  # type: ignore[arg-type]
            gamma_client=metadata,  # type: ignore[arg-type]
            window_start_ms=WINDOW_START_MS,
            window_end_ms=WINDOW_END_MS,
            freeze_ms=FREEZE_MS,
        )
    assert len(metadata.requests) == 1
    assert tape.requests == []


def test_the_certificate_failure_stops_the_import_at_the_first_request() -> None:
    recorded = json.loads(_read("anj_block_response.json"))
    wrapper = ProviderError("the request failed", url=poly.GAMMA_BASE_URL, attempts=1)
    cause = ssl.SSLCertVerificationError(recorded["tls_error"]["message"])
    wrapper.__cause__ = cause
    tape, metadata = clients(error=wrapper)
    with pytest.raises(ProviderBlockedError) as raised:
        poly.import_polymarket(
            client=tape,  # type: ignore[arg-type]
            gamma_client=metadata,  # type: ignore[arg-type]
            window_start_ms=WINDOW_START_MS,
            window_end_ms=WINDOW_END_MS,
            freeze_ms=FREEZE_MS,
        )
    assert raised.value.context["reason"] == poly.BLOCK_REASON_FOREIGN_CERTIFICATE
    assert raised.value.__cause__ is wrapper
    assert len(metadata.requests) == 1


def test_an_ordinary_transport_failure_is_not_converted_into_a_block() -> None:
    failure = ProviderError("the request failed", url=poly.GAMMA_BASE_URL, attempts=4, cause="connection reset")
    with pytest.raises(ProviderError) as raised:
        run_import(error=failure)
    assert raised.value is failure


def test_polymarket_never_retries_by_construction() -> None:
    """Every client this module builds carries `max_retries = 0`, so the wall is hit once.

    `HttpClient` retries a transport failure `max_retries` times (a reported contract issue against
    contract 7.11, which lists 429 and 5xx only), which would spend four handshakes on a certificate that
    is not going to change. The factory and the derived sibling both forbid it.
    """
    assert poly.POLYMARKET_MAX_RETRIES == 0
    built: list[dict[str, Any]] = []

    class Recorder(StubClient):
        def __init__(self, **kwargs: Any) -> None:
            built.append(dict(kwargs))
            super().__init__(base_url=str(kwargs["base_url"]))

    original = poly.HttpClient
    poly.HttpClient = Recorder  # type: ignore[assignment,misc]
    try:
        clob, gamma = poly.make_clients(
            cache_dir=Path("cache-never-written"),
            env={"PMX_USER_AGENT_CONTACT": "d4@example.org", "PMX_HTTP_PROXY": "http://proxy.local:8888"},
        )
    finally:
        poly.HttpClient = original  # type: ignore[assignment,misc]
    assert [entry["base_url"] for entry in built] == [poly.CLOB_BASE_URL, poly.GAMMA_BASE_URL]
    assert [entry["max_retries"] for entry in built] == [0, 0]
    assert [entry["proxy"] for entry in built] == ["http://proxy.local:8888"] * 2
    expected_agent = f"pmx-research/{pmx.__version__} (contact: d4@example.org)"
    assert [entry["user_agent"] for entry in built] == [expected_agent] * 2
    assert clob.base_url == poly.CLOB_BASE_URL
    assert gamma.base_url == poly.GAMMA_BASE_URL


# --------------------------------------------------------------------------------------------------
# The settings
# --------------------------------------------------------------------------------------------------
def test_the_proxy_setting_is_pmx_http_proxy_and_is_the_shared_client_s() -> None:
    from pmx.data.importers import _http

    assert poly.PMX_HTTP_PROXY == "PMX_HTTP_PROXY"
    assert poly.PMX_HTTP_PROXY == _http.HTTP_PROXY_ENV
    assert poly.proxy_from_env({}) is None
    assert poly.proxy_from_env({"PMX_HTTP_PROXY": "   "}) is None
    assert poly.proxy_from_env({"PMX_HTTP_PROXY": " http://proxy.local:8888 "}) == "http://proxy.local:8888"


def test_make_clients_refuses_to_send_a_bare_user_agent() -> None:
    """No contact address, no request: Wikipedia answers 403 to a bare agent and a provider is entitled to
    know who is calling (contract 7.11)."""
    built: list[dict[str, Any]] = []

    class Recorder(StubClient):
        def __init__(self, **kwargs: Any) -> None:
            built.append(dict(kwargs))
            super().__init__(base_url=str(kwargs["base_url"]))

    original = poly.HttpClient
    poly.HttpClient = Recorder  # type: ignore[assignment,misc]
    try:
        with pytest.raises(NotConfiguredError) as raised:
            poly.make_clients(cache_dir=Path("cache-never-written"), env={})
    finally:
        poly.HttpClient = original  # type: ignore[assignment,misc]
    assert raised.value.context["setting"] == "PMX_USER_AGENT_CONTACT"
    assert built == []


def test_a_single_client_derives_its_sibling_and_closes_it() -> None:
    """One client cannot reach two hosts, so the importer derives the other one and cleans up after it."""
    built: list[dict[str, Any]] = []
    derived: list[StubClient] = []

    class Recorder(StubClient):
        def __init__(self, **kwargs: Any) -> None:
            built.append(dict(kwargs))
            super().__init__(base_url=str(kwargs["base_url"]))
            derived.append(self)

    tape = StubClient(base_url=poly.CLOB_BASE_URL)
    tape.proxy = "http://proxy.local:8888"
    original = poly.HttpClient
    poly.HttpClient = Recorder  # type: ignore[assignment,misc]
    try:
        markets = poly.import_polymarket(
            client=tape,  # type: ignore[arg-type]
            window_start_ms=WINDOW_START_MS,
            window_end_ms=WINDOW_END_MS,
            freeze_ms=FREEZE_MS,
            page_size=PAGE_SIZE,
        )
    finally:
        poly.HttpClient = original  # type: ignore[assignment,misc]
    assert len(built) == 1
    assert built[0]["base_url"] == poly.GAMMA_BASE_URL
    assert built[0]["proxy"] == "http://proxy.local:8888"
    assert built[0]["user_agent"] == tape.user_agent
    assert built[0]["max_retries"] == 0
    assert derived[0].closed == 1
    assert len(markets) == 3


# --------------------------------------------------------------------------------------------------
# The import, against the recorded shapes
# --------------------------------------------------------------------------------------------------
def test_the_fixture_import_writes_valid_v2_markets_in_canonical_order() -> None:
    markets, _tape, _metadata = run_import()
    validator = Draft202012Validator(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))
    for market in markets:
        errors = sorted(validator.iter_errors(market.to_dict()), key=str)
        assert errors == [], [error.message for error in errors]
    assert [market.id for market in markets] == [ID_A, ID_B, f"polymarket-{poly.market_slug(SLUG_H)}"]
    assert [market.resolved_at_ms for market in markets] == sorted(market.resolved_at_ms for market in markets)


def test_the_imported_market_carries_the_provenance_and_the_units_of_the_contract() -> None:
    markets, _tape, _metadata = run_import()
    market = market_by_id(markets, ID_A)
    assert market.schema_version == "market.v2"
    assert (market.provider, market.currency, market.source) == ("polymarket", "usd", "imported")
    assert market.fee_schedule_id == "polymarket-zero-2026-09"
    assert market.provider_id == "512901"
    assert market.url == f"https://polymarket.com/event/eth-price-on-march-31-2026/{SLUG_A}"
    assert market.question == "Will ETH close above $4,000 on March 31, 2026?"
    assert market.resolution == 1
    assert market.resolution_source == "https://www.coingecko.com/en/coins/ethereum"
    assert market.created_at_ms == ms("2026-02-25T09:14:02.517Z")
    # The venue settled at 18:05 and published a 12:00 close, and `close_at_ms <= resolved_at_ms` is a
    # schema rule: the earlier of the two is the close.
    assert market.close_at_ms == ms("2026-03-31T12:00:00Z")
    assert market.resolved_at_ms == ms("2026-03-31T18:05:00Z")
    assert market.interval_min == 1_440
    assert market.first_price_bp == 3_800
    assert market.final_price_bp == 9_350
    assert market.trades == ()
    assert market.wiki_subjects == ()
    assert market.hardness_tags == ()
    # Contract 7.2 assigns `event_key` from Kalshi and Manifold fields and `null` everywhere else; the
    # Gamma event slug is a contract change and is reported, not taken.
    assert market.event_key is None
    assert "no size" in market.notes


def test_the_resolution_reads_the_settled_leg_and_not_the_first_leg() -> None:
    """`["0", "1"]` on `["Yes", "No"]` is a NO, and reading index 0 as the probability of YES was the v1
    importer's shortcut."""
    markets, _tape, _metadata = run_import()
    assert market_by_id(markets, ID_B).resolution == 0
    assert market_by_id(markets, ID_A).resolution == 1


def test_the_bars_are_dense_aligned_and_carry_the_previous_close() -> None:
    markets, _tape, _metadata = run_import()
    expected_bars = {ID_A: 35, ID_B: 36, f"polymarket-{poly.market_slug(SLUG_H)}": 29}
    for market in markets:
        step = MS_PER_DAY
        assert market.bars[0].t_ms == bar_of(market.created_at_ms, 1_440)
        assert market.bars[-1].t_ms == bar_of(market.resolved_at_ms, 1_440)
        assert [bar.t_ms for bar in market.bars] == [
            market.bars[0].t_ms + step * k for k in range(len(market.bars))
        ]
        assert len(market.bars) == expected_bars[market.id]
        assert all(bar.t_ms % MS_PER_DAY == 0 for bar in market.bars)
        for bar in market.bars:
            assert bar.low_bp <= min(bar.open_bp, bar.close_bp, bar.vwap_bp)
            assert bar.high_bp >= max(bar.open_bp, bar.close_bp, bar.vwap_bp)
            assert (bar.volume_milli, bar.n_trades) == (0, 0)
            assert (bar.yes_bid_bp, bar.yes_ask_bp, bar.open_interest) == (None, None, None)
    market = market_by_id(markets, ID_A)
    # The tape starts on 2026-02-26 and the market opened on 2026-02-25, so the bars before the first
    # point carry `first_price_bp` (contract 5.2).
    assert market.bars[0].close_bp == market.first_price_bp == 3_800
    # 2026-02-28 printed 0.4147 and 2026-03-01 printed nothing: the empty bar repeats the close it was
    # handed and not the first price.
    assert market.bars[3].close_bp == 4_147
    flat = market.bars[4]
    assert (flat.open_bp, flat.high_bp, flat.low_bp, flat.close_bp, flat.vwap_bp) == (4_147,) * 5
    assert market.bars[-1].close_bp == market.bars[-2].close_bp == 9_350


def test_a_bar_with_several_points_reports_the_true_open_high_low_and_mean() -> None:
    """Three points landed inside the 2026-03-10 bar: 0.51 at 04:00, 0.5881 at 12:00, 0.645 at 20:00.

    `vwap_bp` is their unweighted mean rounded half up, because the CLOB tape carries no size at all: it
    is the honest reading of an unweighted source, and it stays inside `[low, high]`.
    """
    markets, _tape, _metadata = run_import()
    market = market_by_id(markets, ID_A)
    bar = market.bar_at(ms("2026-03-10T00:00:00Z"))
    assert bar is not None
    assert (bar.open_bp, bar.high_bp, bar.low_bp, bar.close_bp) == (5_100, 6_450, 5_100, 6_450)
    assert bar.vwap_bp == 5_810


def test_every_number_of_an_imported_market_is_an_integer() -> None:
    """No float in a price, a quantity or an instant: the provider's decimals came in through `Decimal`."""
    markets, _tape, _metadata = run_import()

    def walk(node: object, path: str) -> None:
        if isinstance(node, bool):
            raise AssertionError(f"{path} is a bool")
        if isinstance(node, float):
            raise AssertionError(f"{path} is a float: {node!r}")
        if isinstance(node, dict):
            for key, value in node.items():
                walk(value, f"{path}.{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{path}[{index}]")

    for market in markets:
        walk(market.to_dict(), market.id)
        assert isinstance(market.first_price_bp, int)
        assert isinstance(market.quality.volume_milli_total, int)


def test_a_float_never_reaches_a_mapper() -> None:
    """The payloads are parsed with `parse_float=Decimal`, so a float in a mapper is a broken parse path
    and is refused rather than rounded."""
    with pytest.raises(MalformedResponseError):
        poly._decimal(0.5, field="history[].p")
    assert poly._decimal("0.6327", field="history[].p") * 10_000 == 6_327


def test_the_quality_block_counts_what_the_tape_actually_covered() -> None:
    markets, _tape, _metadata = run_import()
    market = market_by_id(markets, ID_A)
    assert market.quality.traded_bars == 17
    assert market.quality.traded_bars < len(market.bars)
    assert market.quality.n_trades == 0
    assert market.quality.unique_bettors is None
    assert market.quality.life_days == 34
    assert market.quality.volume_milli_total == 1_843_922_510
    assert market_by_id(markets, ID_B).quality.traded_bars == 18


def test_the_category_and_the_tags_come_from_the_provider_labels() -> None:
    markets, _tape, _metadata = run_import()
    assert market_by_id(markets, ID_A).category == "crypto"
    assert market_by_id(markets, ID_A).tags == ("crypto", "crypto-prices", "ethereum")
    assert market_by_id(markets, ID_B).category == "sports"
    assert market_by_id(markets, ID_B).tags == ("soccer",)
    long_market = market_by_id(markets, f"polymarket-{poly.market_slug(SLUG_H)}")
    # "Fed Rates" is not a contract category; the per-provider table maps it to economics.
    assert long_market.category == "economics"
    assert long_market.tags == ("economy", "fed-rates")


def test_an_over_long_provider_slug_becomes_a_legal_and_distinct_id() -> None:
    """A Polymarket slug is a sentence and the id regex of contract section 2 stops at 96 characters."""
    markets, _tape, _metadata = run_import()
    slug = poly.market_slug(SLUG_H)
    assert len(SLUG_H) > poly.MARKET_SLUG_MAX
    assert len(slug) == poly.MARKET_SLUG_MAX
    assert slug == poly.market_slug(SLUG_H)  # deterministic: no clock, no randomness
    assert SLUG_H.startswith(slug[:87])
    for market in markets:
        assert RE_MARKET_ID.match(market.id), market.id
    # Two slugs that share the first 87 characters must not share an id.
    twin_a = SLUG_H
    twin_b = SLUG_H[:100] + "-revised-statement"
    assert poly.market_slug(twin_a) != poly.market_slug(twin_b)
    assert poly.market_slug(twin_a)[:87] == poly.market_slug(twin_b)[:87]


def test_the_ineligible_rows_are_skipped_before_their_tape_is_fetched() -> None:
    """Open, multi-outcome, voided, post-freeze and pre-window rows never enter and never cost a request."""
    markets, tape, _metadata = run_import()
    imported = {market.id for market in markets}
    for slug in SKIPPED_SLUGS:
        assert f"polymarket-{slug}" not in imported
    asked_for = {str(params["market"]) for params in tape.paths(poly.CLOB_PRICES_HISTORY_PATH)}
    assert asked_for.isdisjoint(SKIPPED_TOKENS)
    assert len(asked_for) == 3


def test_the_freeze_is_the_hard_edge_of_the_window() -> None:
    """A market that resolved after the freeze is refused even when the window would accept it."""
    after_freeze = ms("2026-09-18T22:10:00Z")
    markets, _tape, _metadata = run_import(window_end_ms=after_freeze + MS_PER_DAY)
    assert markets, "an empty import would satisfy the freeze rule without testing it"
    assert all(market.resolved_at_ms < FREEZE_MS for market in markets)
    assert "polymarket-will-the-index-close-above-7000-on-2026-09-18" not in {m.id for m in markets}
    # ... and it is the window, not the fixture, that hides it: widen the freeze and it arrives.
    late, _tape2, _metadata2 = run_import(
        window_end_ms=after_freeze + MS_PER_DAY, freeze_ms=after_freeze + MS_PER_DAY
    )
    assert "polymarket-will-the-index-close-above-7000-on-2026-09-18" in {m.id for m in late}


def test_the_prices_history_request_asks_for_the_window_of_the_market() -> None:
    """One request per market, `startTs` and `endTs` on the market's own first and last bar."""
    markets, tape, _metadata = run_import()
    market = market_by_id(markets, ID_A)
    requests = tape.paths(poly.CLOB_PRICES_HISTORY_PATH)
    assert len(requests) == 3
    for params in requests:
        assert set(params) == {"market", "fidelity", "startTs", "endTs"}
        assert params["fidelity"] == poly.DEFAULT_FIDELITY_MIN
    yes_token = json.loads(str(_rows(LISTING_PAGES[0])[0]["clobTokenIds"]))[0]
    first = requests[0]
    assert first["market"] == yes_token
    assert int(str(first["startTs"])) * 1_000 == market.bars[0].t_ms
    assert int(str(first["endTs"])) * 1_000 == market.bars[-1].t_ms + MS_PER_DAY


def test_an_empty_window_falls_back_to_the_whole_life_query() -> None:
    """The CLOB documents `startTs`/`endTs` and `interval` as two spellings of one query and the block
    means neither can be confirmed against the live endpoint, so a window that answers nothing is asked
    again with `interval` before the market is given up on."""
    markets, tape, _metadata = run_import(empty_window=True)
    assert len(markets) == 3
    requests = tape.paths(poly.CLOB_PRICES_HISTORY_PATH)
    assert len(requests) == 6
    windowed = [params for params in requests if "startTs" in params]
    whole_life = [params for params in requests if "interval" in params]
    assert len(windowed) == 3
    assert len(whole_life) == 3
    for params in whole_life:
        assert set(params) == {"market", "fidelity", "interval"}
        assert params["interval"] == poly.DEFAULT_PRICES_HISTORY_INTERVAL
        assert params["interval"] in poly.PRICES_HISTORY_INTERVALS
    assert market_by_id(markets, ID_A).first_price_bp == 3_800


def test_the_listing_request_carries_the_window_and_walks_the_offsets() -> None:
    markets, _tape, metadata = run_import()
    requests = metadata.paths(poly.GAMMA_MARKETS_PATH)
    assert [params["offset"] for params in requests] == [0, PAGE_SIZE]
    assert all(params["closed"] == "true" for params in requests)
    assert all(params["limit"] == PAGE_SIZE for params in requests)
    assert all(params["order"] == "endDate" for params in requests)
    assert requests[0]["end_date_min"] == "2025-09-07T00:00:00Z"
    assert requests[0]["end_date_max"] == "2026-09-06T00:00:00Z"
    # The second page is where two of the three markets come from, so pagination is load bearing.
    assert ID_B in {market.id for market in markets}


def test_the_listing_stops_on_a_short_page() -> None:
    """A page shorter than `page_size` is the last one: no request is spent proving it."""
    _markets, _tape, metadata = run_import(page_size=100)
    assert [params["offset"] for params in metadata.paths(poly.GAMMA_MARKETS_PATH)] == [0]


def test_the_limit_caps_the_import_and_the_requests() -> None:
    markets, tape, metadata = run_import(limit=1)
    assert len(markets) == 1
    assert len(tape.paths(poly.CLOB_PRICES_HISTORY_PATH)) == 1
    assert len(metadata.paths(poly.GAMMA_MARKETS_PATH)) == 1


def test_a_named_slug_is_imported_alone_through_the_v1_path() -> None:
    """The v1 importer's only entry point was one slug; it survives as `slugs=`."""
    markets, tape, metadata = run_import(slugs=[SLUG_A])
    assert [market.id for market in markets] == [ID_A]
    assert metadata.paths(poly.GAMMA_MARKETS_PATH) == [{"slug": SLUG_A}]
    assert len(tape.paths(poly.CLOB_PRICES_HISTORY_PATH)) == 1


def test_a_slug_the_provider_does_not_know_is_refused() -> None:
    tape, metadata = clients(overrides={poly.GAMMA_MARKETS_PATH: "[]"})
    with pytest.raises(MalformedResponseError) as raised:
        poly.import_polymarket(
            client=tape,  # type: ignore[arg-type]
            gamma_client=metadata,  # type: ignore[arg-type]
            window_start_ms=WINDOW_START_MS,
            window_end_ms=WINDOW_END_MS,
            freeze_ms=FREEZE_MS,
            slugs=["no-such-market"],
        )
    assert raised.value.context["slug"] == "no-such-market"


def test_a_history_that_is_not_a_history_is_refused() -> None:
    """A provider shape change is an error with a name, not an empty dataset."""
    tape, metadata = clients(overrides={poly.CLOB_PRICES_HISTORY_PATH: '{"data": [1, 2]}'})
    with pytest.raises(MalformedResponseError):
        poly.import_polymarket(
            client=tape,  # type: ignore[arg-type]
            gamma_client=metadata,  # type: ignore[arg-type]
            window_start_ms=WINDOW_START_MS,
            window_end_ms=WINDOW_END_MS,
            freeze_ms=FREEZE_MS,
        )


def test_a_body_that_is_not_json_is_refused_with_its_head() -> None:
    tape, metadata = clients(overrides={poly.GAMMA_MARKETS_PATH: "<html><body>gateway</body></html>"})
    with pytest.raises(MalformedResponseError) as raised:
        poly.import_polymarket(
            client=tape,  # type: ignore[arg-type]
            gamma_client=metadata,  # type: ignore[arg-type]
            window_start_ms=WINDOW_START_MS,
            window_end_ms=WINDOW_END_MS,
            freeze_ms=FREEZE_MS,
        )
    assert "gateway" in str(raised.value.context["head"])


def test_the_grid_and_the_request_shape_are_validated_before_the_first_request() -> None:
    tape, metadata = clients()
    for bad in ({"interval_min": 15}, {"history_interval": "3h"}, {"fidelity_min": 0}, {"page_size": 0}):
        with pytest.raises(InvalidConfigError):
            poly.import_polymarket(
                client=tape,  # type: ignore[arg-type]
                gamma_client=metadata,  # type: ignore[arg-type]
                window_start_ms=WINDOW_START_MS,
                window_end_ms=WINDOW_END_MS,
                freeze_ms=FREEZE_MS,
                **bad,
            )
    assert tape.requests == []
    assert metadata.requests == []


def test_an_hourly_grid_is_a_second_dataset_and_not_a_resampling() -> None:
    """Contract 5.3: one grid per run. The importer takes the grid and builds it; it never resamples."""
    markets, _tape, _metadata = run_import(interval_min=60, slugs=[SLUG_A])
    market = markets[0]
    assert market.interval_min == 60
    assert all(bar.t_ms % 3_600_000 == 0 for bar in market.bars)
    assert market.bars[0].t_ms == bar_of(market.created_at_ms, 60)
    assert market.bars[-1].t_ms == bar_of(market.resolved_at_ms, 60)
    # 2026-02-25T09:00Z to 2026-03-31T18:00Z inclusive, one bar an hour.
    assert len(market.bars) == 34 * 24 + 9 + 1


def test_the_provider_date_spellings_all_parse() -> None:
    """One Gamma payload spells its instants three ways, and a string without an offset is refused."""
    assert poly._parse_instant_ms("2026-03-31T12:00:00Z", field="endDate") == ms("2026-03-31T12:00:00Z")
    assert poly._parse_instant_ms("2026-03-31 18:05:00+00", field="closedTime") == ms("2026-03-31T18:05:00Z")
    assert poly._parse_instant_ms("2026-02-25T09:14:02.517Z", field="createdAt") == ms("2026-02-25T09:14:02.517Z")
    for bad in ("2026-03-31T12:00:00", "", "not a date", None, 17):
        with pytest.raises(MalformedResponseError):
            poly._parse_instant_ms(bad, field="endDate")


@pytest.mark.skipif(os.environ.get("PMX_LIVE") != "1", reason="live network test; set PMX_LIVE=1 to run")
def test_live_polymarket_is_either_reachable_or_blocked(tmp_path: Path) -> None:
    """The one network test of D4, opt-in: from a blocked jurisdiction it must be a `ProviderBlockedError`
    naming a reason, and from anywhere else it must be markets that pass the same schema."""
    clob, gamma = poly.make_clients(cache_dir=tmp_path / "cache")
    try:
        try:
            markets = poly.import_polymarket(
                client=clob,
                gamma_client=gamma,
                window_start_ms=WINDOW_START_MS,
                window_end_ms=WINDOW_END_MS,
                freeze_ms=FREEZE_MS,
                limit=1,
            )
        except ProviderBlockedError as blocked:
            assert blocked.message == poly.ANJ_BLOCK_MESSAGE
            assert blocked.context["reason"] in {
                poly.BLOCK_REASON_ANJ_BODY,
                poly.BLOCK_REASON_ANJ_CERTIFICATE,
                poly.BLOCK_REASON_FOREIGN_CERTIFICATE,
            }
        else:
            validator = Draft202012Validator(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))
            for market in markets:
                assert list(validator.iter_errors(market.to_dict())) == []
    finally:
        clob.close()
        gamma.close()


def test_the_module_names_no_em_dash_and_no_wall_clock() -> None:
    """Two house rules, checked here on the file the package owns (the tree-wide sweep is the gate's)."""
    source = (Path(poly.__file__)).read_text(encoding="utf-8")
    assert chr(0x2014) not in source
    assert not re.search(r"datetime\.(now|utcnow|today)\(|time\.(time|monotonic)\(|uuid4\(", source)
