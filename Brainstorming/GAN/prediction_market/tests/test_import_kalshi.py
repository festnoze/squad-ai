"""D2: the shared HTTP client and the Kalshi importer, offline against recorded payloads.

Every test here runs without a socket. The client's one seam for that is its ``transport`` argument, and
the fixtures under ``tests/fixtures/d2/`` are the shapes the live API answered with on 2026-09-07: the
settled listing with its opaque cursor, the historical cutoff, both candlestick paths (live under
``/series/...`` and historical under ``/historical/markets/...``), and the trade tape in both the newer
decimal-dollar shape and the older integer-cent shape. One test hits the real API and is skipped unless
``PMX_LIVE=1``, which is the single legal skip of the project.

What these tests are really guarding, beyond "the parser parses":

* the cutoff decides the path. A pre-cutoff market read on the live path answers an empty tape instead of
  an error, so the wrong choice would produce a silently flat market that every later filter would accept;
* the bar grid is dense whatever the provider did. Kalshi omits a period with no trade, sometimes answers
  one with a null price, and stops answering entirely for a day; all three become the carry-forward bar of
  CONTRACTS_V2 5.2 and none of them becomes a gap the loader would refuse;
* no float and no invented price. A cent is 100 bp, a decimal-dollar string goes through ``Decimal``, a
  price of 100 cents clamps to 9 999 bp while a *quote* of 100 cents becomes no quote at all, because
  clamping a quote would invent a bid;
* the shards stay out. The settled list is mostly ``KXMVE`` legs that live for minutes, and a dataset made
  of them would be a dataset of near-duplicates with no forecastable content;
* politeness is mechanical: one User-Agent with a contact address, a minimum interval enforced by the
  client, exponential backoff on 429 and 5xx, no retry on any other 4xx, and a cache that makes the second
  build of a window issue no request at all.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import httpx
import pytest
from jsonschema import Draft202012Validator

from pmx.data.importers import kalshi as kalshi_module
from pmx.data.importers._http import (
    DEFAULT_MIN_INTERVAL_MS,
    HTTP_MAX_RETRIES,
    HTTP_PROXY_ENV,
    HTTP_TIMEOUT_S,
    USER_AGENT_CONTACT_ENV,
    USER_AGENT_TEMPLATE,
    HttpClient,
    build_user_agent,
    cache_key,
    evenly_spaced,
)
from pmx.data.importers.kalshi import (
    CATEGORY_FALLBACK,
    KALSHI_ALLOWED_SERIES,
    KALSHI_BASE_URL,
    KALSHI_EXCLUDED_SERIES,
    KALSHI_FEE_SCHEDULE_ID,
    KALSHI_MARKETS_MAX_PAGES,
    KALSHI_SETTLEMENT_SLACK_MS,
    WIKI_SUBJECTS_MAX,
    historical_cutoff_ms,
    import_kalshi,
    is_excluded_ticker,
    kalshi_series,
    list_open_kalshi,
    load_series_categories,
    load_series_subjects,
    series_category,
    wiki_subjects_of,
)
from pmx.data.importers.metaculus import METACULUS_TOKEN_ENV, import_metaculus
from pmx.data.schema import load_schema
from pmx.errors import InvalidConfigError, MalformedResponseError, NotConfiguredError, ProviderError
from pmx.journal import canonical_json
from pmx.types import (
    CATEGORIES as CATEGORIES_OF_SECTION_2,
)
from pmx.types import (
    MS_PER_DAY,
    MS_PER_HOUR,
    TAPE_KIND_BARS_ONLY,
    TAPE_KIND_PRINTS,
    Bar,
    Market,
    OpenMarket,
)

FIXTURES: Final = Path(__file__).resolve().parent / "fixtures" / "d2"
CONTACT: Final = "pmx-tests@example.invalid"
NS_PER_S: Final = 1_000_000_000


def ms(text: str) -> int:
    """An ISO instant as epoch milliseconds, computed in integers so the expectations are exact."""
    moment = datetime.fromisoformat(text).astimezone(UTC)
    delta = moment - datetime(1970, 1, 1, tzinfo=UTC)
    return delta.days * MS_PER_DAY + delta.seconds * 1_000 + delta.microseconds // 1_000


# The dataset window the fixtures were recorded for: freeze 2026-09-07, twelve months back.
FREEZE_MS: Final = ms("2026-09-07T00:00:00+00:00")
WINDOW_START_MS: Final = FREEZE_MS - 365 * MS_PER_DAY
WINDOW_END_MS: Final = FREEZE_MS - MS_PER_DAY
CUTOFF_MS: Final = ms("2026-07-08T00:00:00+00:00")
NBA_TICKER: Final = "KXNBAGAME-26MAY31-LAL"
PARTY_TICKER: Final = "KXPRESPARTY-28-R"
FED_TICKER: Final = "KXFED-26SEP-T425"


# --------------------------------------------------------------------------------------------------
# The offline seam: a transport that answers from the recorded payloads and records what was asked
# --------------------------------------------------------------------------------------------------
@dataclass
class _Sent:
    method: str
    url: str
    path: str
    params: dict[str, str]
    headers: dict[str, str]


def _fixture_for(path: str, params: Mapping[str, str], *, candlesticks: str | None) -> str | None:
    """The recorded payload that answers ``path``, or ``None`` when nothing was recorded for it."""
    if path.endswith("/historical/cutoff"):
        return "historical_cutoff.json"
    if path.endswith("/historical/markets"):
        return "historical_markets.json"
    if path.endswith("/markets/trades"):
        page = 2 if params.get("cursor") else 1
        return f"trades_{params.get('ticker', '')}_page{page}.json"
    historical = re.search(r"/historical/markets/([^/]+)/candlesticks$", path)
    if historical is not None:
        return candlesticks or f"candlesticks_historical_{historical.group(1)}.json"
    live = re.search(r"/series/([^/]+)/markets/([^/]+)/candlesticks$", path)
    if live is not None:
        return candlesticks or f"candlesticks_{live.group(2)}.json"
    if path.endswith("/markets"):
        status = params.get("status", "")
        if status == "open":
            return "markets_open.json"
        if status == "settled":
            return "markets_settled_page2.json" if params.get("cursor") else "markets_settled_page1.json"
    return None


class _FixtureTransport(httpx.BaseTransport):
    """Answers every Kalshi route from ``tests/fixtures/d2`` and remembers every request."""

    def __init__(self, *, candlesticks: str | None = None) -> None:
        self.sent: list[_Sent] = []
        self._candlesticks = candlesticks

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        params = {key: value for key, value in request.url.params.multi_items()}
        self.sent.append(
            _Sent(
                method=request.method,
                url=str(request.url),
                path=request.url.path,
                params=params,
                headers={key.lower(): value for key, value in request.headers.items()},
            )
        )
        name = _fixture_for(request.url.path, params, candlesticks=self._candlesticks)
        if name is None or not (FIXTURES / name).exists():
            return httpx.Response(404, json={"error": {"message": f"no fixture for {request.url}"}})
        body = (FIXTURES / name).read_text(encoding="utf-8")
        return httpx.Response(200, text=body, headers={"content-type": "application/json"})

    def paths(self) -> list[str]:
        return [entry.path for entry in self.sent]


@dataclass
class _ScriptedTransport(httpx.BaseTransport):
    """Answers a fixed list of statuses in order, repeating the last one forever."""

    statuses: Sequence[int]
    body: str = '{"ok": true}'
    calls: int = 0

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        status = self.statuses[min(self.calls, len(self.statuses) - 1)]
        self.calls += 1
        return httpx.Response(status, text=self.body, headers={"content-type": "application/json"})


@dataclass
class _StepClock:
    """A monotonic clock in nanoseconds that advances by ``step_ns`` at every reading."""

    step_ns: int = 0
    now_ns: int = 0

    def __call__(self) -> int:
        value = self.now_ns
        self.now_ns += self.step_ns
        return value


@dataclass
class _Sleeps:
    """The sleeper the client is given instead of ``time.sleep``: it records and returns at once."""

    waited_ms: list[int] = field(default_factory=list)

    def __call__(self, duration_ms: int) -> None:
        self.waited_ms.append(duration_ms)


def _client(
    tmp_path: Path,
    transport: httpx.BaseTransport,
    *,
    min_interval_ms: int = 0,
    clock: _StepClock | None = None,
    sleeps: _Sleeps | None = None,
    max_retries: int = HTTP_MAX_RETRIES,
    api_key: str | None = None,
    proxy: str | None = None,
) -> HttpClient:
    return HttpClient(
        base_url=KALSHI_BASE_URL,
        user_agent=USER_AGENT_TEMPLATE.format(version="test", contact=CONTACT),
        min_interval_ms=min_interval_ms,
        cache_dir=tmp_path / "cache",
        max_retries=max_retries,
        api_key=api_key,
        proxy=proxy,
        transport=transport,
        clock=clock or _StepClock(step_ns=NS_PER_S),
        sleeper=sleeps or _Sleeps(),
    )


def _market_payload(market: Market) -> dict[str, object]:
    """The market as the JSON object ``market.v2.json`` describes, however D1 spells serialisation."""
    for name, kwargs in (("to_dict", {}), ("model_dump", {"mode": "json"})):
        method = getattr(market, name, None)
        if callable(method):
            payload = method(**kwargs)
            assert isinstance(payload, dict), f"{name}() must answer a JSON object"
            return {str(key): value for key, value in payload.items()}
    raise AssertionError("pmx.types.Market exposes neither to_dict() nor model_dump()")


def _bars(market: Market | OpenMarket) -> list[Bar]:
    return list(market.bars)


# --------------------------------------------------------------------------------------------------
# The shared client: User-Agent, cache, throttle, backoff
# --------------------------------------------------------------------------------------------------
def test_user_agent_carries_the_version_and_the_contact(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(USER_AGENT_CONTACT_ENV, f"  {CONTACT}  ")
    agent = build_user_agent()
    assert agent.startswith("pmx-research/")
    assert f"(contact: {CONTACT})" in agent
    assert build_user_agent("other@example.invalid").endswith("(contact: other@example.invalid)")


def test_a_missing_contact_address_is_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(USER_AGENT_CONTACT_ENV, raising=False)
    with pytest.raises(NotConfiguredError) as raised:
        build_user_agent()
    assert USER_AGENT_CONTACT_ENV in str(raised.value)
    monkeypatch.setenv(USER_AGENT_CONTACT_ENV, "   ")
    with pytest.raises(NotConfiguredError):
        build_user_agent()


def test_every_request_carries_the_user_agent_and_the_timeout(tmp_path: Path) -> None:
    transport = _FixtureTransport()
    client = _client(tmp_path, transport)
    assert historical_cutoff_ms(client) == CUTOFF_MS
    assert transport.sent[0].headers["user-agent"] == USER_AGENT_TEMPLATE.format(
        version="test", contact=CONTACT
    )
    assert client.timeout_s == HTTP_TIMEOUT_S
    client.close()


def test_an_api_key_becomes_an_authorization_header(tmp_path: Path) -> None:
    transport = _FixtureTransport()
    client = _client(tmp_path, transport, api_key="  secret-key  ")
    client.get_json("/historical/cutoff")
    assert transport.sent[0].headers["authorization"] == "Bearer secret-key"


def test_the_proxy_defaults_to_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(HTTP_PROXY_ENV, "http://proxy.invalid:3128")
    assert _client(tmp_path, _FixtureTransport()).proxy == "http://proxy.invalid:3128"
    assert _client(tmp_path, _FixtureTransport(), proxy="http://other.invalid").proxy == "http://other.invalid"
    monkeypatch.delenv(HTTP_PROXY_ENV, raising=False)
    assert _client(tmp_path, _FixtureTransport()).proxy is None


def test_the_cache_answers_the_second_call_without_a_request(tmp_path: Path) -> None:
    transport = _FixtureTransport()
    client = _client(tmp_path, transport)
    first = client.get_json("/markets", {"status": "settled", "limit": 1_000})
    second = client.get_json("/markets", {"limit": 1_000, "status": "settled"})
    assert first == second
    assert client.requests_made == 1, "the parameters differ only in key order, so it is one cache entry"
    assert len(transport.sent) == 1

    key = cache_key("GET", f"{KALSHI_BASE_URL}/markets", {"limit": 1_000, "status": "settled"})
    on_disk = tmp_path / "cache" / key[:2] / f"{key}.json"
    assert on_disk.exists(), "the cache layout of CONTRACTS_V2 7.11 is <dir>/<key[:2]>/<key>.json"
    entry = json.loads(on_disk.read_text(encoding="utf-8"))
    assert sorted(entry) == ["body", "headers", "status"]
    assert entry["status"] == 200
    assert json.loads(entry["body"])["cursor"] == "CURSOR_SETTLED_2"
    assert entry["headers"]["content-type"] == "application/json"
    assert on_disk.read_text(encoding="utf-8") == canonical_json(entry) + "\n"


def test_cache_false_refetches_and_rewrites(tmp_path: Path) -> None:
    transport = _FixtureTransport()
    client = _client(tmp_path, transport)
    client.get_json("/historical/cutoff")
    client.get_json("/historical/cutoff", cache=False)
    assert client.requests_made == 2
    client.get_json("/historical/cutoff")
    assert client.requests_made == 2, "the refetch rewrote the entry, so the third call is a hit"


def test_a_corrupt_cache_entry_is_a_miss_and_not_a_failure(tmp_path: Path) -> None:
    transport = _FixtureTransport()
    client = _client(tmp_path, transport)
    client.get_json("/historical/cutoff")
    key = cache_key("GET", f"{KALSHI_BASE_URL}/historical/cutoff", None)
    (tmp_path / "cache" / key[:2] / f"{key}.json").write_text("{not json", encoding="utf-8")
    assert historical_cutoff_ms(client) == CUTOFF_MS
    assert client.requests_made == 2


def test_get_text_returns_the_body_verbatim(tmp_path: Path) -> None:
    client = _client(tmp_path, _FixtureTransport())
    body = client.get_text("/historical/cutoff")
    assert body == (FIXTURES / "historical_cutoff.json").read_text(encoding="utf-8")


def test_the_throttle_holds_the_minimum_interval(tmp_path: Path) -> None:
    sleeps = _Sleeps()
    frozen = _StepClock(step_ns=0)
    client = _client(tmp_path, _FixtureTransport(), min_interval_ms=1_000, clock=frozen, sleeps=sleeps)
    client.get_json("/historical/cutoff", cache=False)
    assert sleeps.waited_ms == [], "the first request waits for nothing"
    client.get_json("/historical/cutoff", cache=False)
    client.get_json("/historical/cutoff", cache=False)
    assert sleeps.waited_ms == [1_000, 1_000], "a clock that never advances owes the whole interval twice"

    moving = _StepClock(step_ns=5 * NS_PER_S)
    patient = _client(tmp_path, _FixtureTransport(), min_interval_ms=1_000, clock=moving, sleeps=(late := _Sleeps()))
    patient.get_json("/historical/cutoff", cache=False)
    patient.get_json("/historical/cutoff", cache=False)
    assert late.waited_ms == [], "five seconds went by on their own, so nothing is owed"


def test_backoff_retries_a_429_and_a_5xx_then_succeeds(tmp_path: Path) -> None:
    transport = _ScriptedTransport(statuses=(429, 503, 200))
    sleeps = _Sleeps()
    client = _client(
        tmp_path, transport, min_interval_ms=100, clock=_StepClock(step_ns=NS_PER_S), sleeps=sleeps
    )
    assert client.get_json("/markets", {"status": "settled"}) == {"ok": True}
    assert transport.calls == 3
    assert sleeps.waited_ms == [100, 200], "min_interval_ms * 2 ** attempt, and nothing else"


def test_a_provider_that_keeps_failing_raises_after_max_retries(tmp_path: Path) -> None:
    transport = _ScriptedTransport(statuses=(500,))
    sleeps = _Sleeps()
    client = _client(
        tmp_path, transport, min_interval_ms=100, clock=_StepClock(step_ns=NS_PER_S), sleeps=sleeps
    )
    with pytest.raises(ProviderError) as raised:
        client.get_json("/markets")
    assert transport.calls == HTTP_MAX_RETRIES + 1 == 4
    assert sleeps.waited_ms == [100, 200, 400]
    assert "status=500" in str(raised.value)
    assert f"attempts={HTTP_MAX_RETRIES + 1}" in str(raised.value)


def test_a_4xx_other_than_429_fails_at_once(tmp_path: Path) -> None:
    transport = _ScriptedTransport(statuses=(404,))
    sleeps = _Sleeps()
    client = _client(tmp_path, transport, min_interval_ms=100, sleeps=sleeps)
    with pytest.raises(ProviderError) as raised:
        client.get_json("/markets/unknown")
    assert transport.calls == 1, "a 404 is not going to become a 200"
    assert sleeps.waited_ms == []
    assert "status=404" in str(raised.value)


def test_a_body_that_is_not_json_is_a_malformed_response(tmp_path: Path) -> None:
    client = _client(tmp_path, _ScriptedTransport(statuses=(200,), body="<html>blocked</html>"))
    with pytest.raises(MalformedResponseError):
        client.get_json("/markets")
    assert client.get_text("/markets") == "<html>blocked</html>"


def test_a_refused_client_configuration_is_an_invalid_config(tmp_path: Path) -> None:
    common: dict[str, object] = {
        "base_url": KALSHI_BASE_URL,
        "user_agent": "pmx-research/test (contact: x@example.invalid)",
        "cache_dir": tmp_path,
        "min_interval_ms": 0,
    }
    for override in ({"min_interval_ms": -1}, {"max_retries": -1}, {"user_agent": "   "}):
        with pytest.raises(InvalidConfigError):
            HttpClient(**{**common, **override}, transport=_FixtureTransport())  # type: ignore[arg-type]


def test_the_cache_key_is_the_contract_formula() -> None:
    params = {"period_interval": 1_440, "start_ts": 1_786_406_400}
    expected_material = f"GET {KALSHI_BASE_URL}/markets {canonical_json(dict(params))}"
    assert cache_key("GET", f"{KALSHI_BASE_URL}/markets", params) == hashlib.sha256(
        expected_material.encode()
    ).hexdigest()
    assert cache_key("GET", "u", None) == cache_key("GET", "u", {})


# --------------------------------------------------------------------------------------------------
# The series rules
# --------------------------------------------------------------------------------------------------
def test_the_shard_rule_refuses_kxmve_and_the_excluded_series() -> None:
    assert "KXMVE" in KALSHI_EXCLUDED_SERIES
    assert KALSHI_ALLOWED_SERIES == (), "an empty allow-list means every series that is not excluded"
    assert kalshi_series("KXPRESPARTY-28-R") == "KXPRESPARTY"
    assert kalshi_series("kxfed-26sep-t425") == "KXFED"
    assert is_excluded_ticker("KXMVE-26AUG25-T5")
    assert is_excluded_ticker("KXMVEFOO-1")
    assert not is_excluded_ticker(PARTY_TICKER)
    assert is_excluded_ticker(PARTY_TICKER, excluded=("KXPRESPARTY",))
    assert is_excluded_ticker(PARTY_TICKER, allow_list=("KXFED",))
    assert not is_excluded_ticker(PARTY_TICKER, allow_list=("kxpresparty", "KXFED"))


# --------------------------------------------------------------------------------------------------
# The importer
# --------------------------------------------------------------------------------------------------
@pytest.fixture
def imported(tmp_path: Path) -> tuple[tuple[Market, ...], _FixtureTransport]:
    transport = _FixtureTransport()
    client = _client(tmp_path, transport)
    markets = import_kalshi(
        client=client,
        window_start_ms=WINDOW_START_MS,
        window_end_ms=WINDOW_END_MS,
        freeze_ms=FREEZE_MS,
    )
    return markets, transport


def test_the_window_markets_arrive_in_canonical_order(
    imported: tuple[tuple[Market, ...], _FixtureTransport],
) -> None:
    markets, _ = imported
    assert [market.id for market in markets] == [f"kalshi-{NBA_TICKER}", f"kalshi-{PARTY_TICKER}"]
    assert [market.resolved_at_ms for market in markets] == sorted(m.resolved_at_ms for m in markets)


def test_the_dropped_rows_are_dropped_for_the_contracted_reasons(
    imported: tuple[tuple[Market, ...], _FixtureTransport],
) -> None:
    markets, transport = imported
    ids = {market.id for market in markets}
    assert "kalshi-KXMVE-26AUG25-T5" not in ids, "the shard rule of CONTRACTS_V2 7.4"
    assert "kalshi-KXMVE-26MAY31-T2" not in ids, "the same rule on the historical tables"
    assert "kalshi-KXHIGHNY-26AUG20-B70" not in ids, "created and settled inside one bar: no grid"
    assert "kalshi-KXSPEAKER-26-VOID" not in ids, "result 'void' is not a binary outcome"
    assert "kalshi-KXOLDONE-24-A" not in ids, "settled two years before the window"
    assert "kalshi-KXFUTURE-26SEP-X" not in ids, "settles after the window end"
    fetched = {path for path in transport.paths() if path.endswith("candlesticks")}
    assert not any("KXMVE" in path or "KXHIGHNY" in path for path in fetched), (
        "a dropped row must never cost a tape request"
    )


def test_both_listing_paths_are_walked_and_the_cursor_is_followed(
    imported: tuple[tuple[Market, ...], _FixtureTransport],
) -> None:
    _, transport = imported
    listings = [entry for entry in transport.sent if entry.path.endswith(("/markets", "/historical/markets"))]
    assert [entry.path for entry in listings] == [
        "/trade-api/v2/historical/markets",
        "/trade-api/v2/markets",
        "/trade-api/v2/markets",
    ]
    assert listings[1].params["status"] == "settled"
    assert "cursor" not in listings[1].params
    assert listings[2].params["cursor"] == "CURSOR_SETTLED_2"
    assert int(listings[1].params["max_close_ts"]) == WINDOW_END_MS // 1_000
    assert transport.sent[0].path.endswith("/historical/cutoff"), "the cutoff is read before anything else"


def test_the_cutoff_chooses_the_candlestick_path(
    imported: tuple[tuple[Market, ...], _FixtureTransport],
) -> None:
    markets, transport = imported
    nba, party = markets
    assert nba.resolved_at_ms < CUTOFF_MS <= party.resolved_at_ms
    candlesticks = [path for path in transport.paths() if path.endswith("candlesticks")]
    assert candlesticks == [
        f"/trade-api/v2/historical/markets/{NBA_TICKER}/candlesticks",
        f"/trade-api/v2/series/KXPRESPARTY/markets/{PARTY_TICKER}/candlesticks",
    ]
    params = [entry.params for entry in transport.sent if entry.path.endswith("candlesticks")]
    assert params[0]["period_interval"] == "1440"
    assert int(params[0]["start_ts"]) == ms("2026-05-25T00:00:00+00:00") // 1_000
    # The last bar of this market opens on 2026-05-31 and the range ends two intervals later, not one:
    # the endpoint selects periods by their *end*, and the period that opens inside the last bar ends
    # after it whenever the provider's day is not UTC's (Kalshi's daily period ends at midnight
    # Eastern). Asking for one interval of slack dropped the settling bar's price and size.
    assert int(params[0]["end_ts"]) == ms("2026-06-03T00:00:00+00:00") // 1_000


def test_the_imported_markets_validate_against_the_market_schema(
    imported: tuple[tuple[Market, ...], _FixtureTransport],
) -> None:
    markets, _ = imported
    validator = Draft202012Validator(load_schema("market.v2.json"))
    for market in markets:
        payload = _market_payload(market)
        errors = sorted(validator.iter_errors(payload), key=str)
        assert errors == [], f"{market.id}: {[error.message for error in errors]}"
        assert payload["schema_version"] == "market.v2"
        assert payload["source"] == "imported"
        assert payload["currency"] == "usd"
        assert payload["hardness_tags"] == [], "D6 computes the tags, not the importer"
        assert payload["fee_schedule_id"] == KALSHI_FEE_SCHEDULE_ID
        # Kalshi publishes no article title of its own, so every subject of these two fixtures is one
        # the importer derived from the question, and the flags say so, one per subject and aligned.
        subjects = payload["wiki_subjects"]
        flags = payload.get("wiki_subject_provenance", [])
        assert isinstance(subjects, list) and isinstance(flags, list)
        assert len(flags) == len(subjects) <= WIKI_SUBJECTS_MAX
        assert set(flags) <= {"derived"}
        assert subjects == sorted(set(subjects))


def test_the_metadata_of_a_settled_market_is_the_venue_metadata(
    imported: tuple[tuple[Market, ...], _FixtureTransport],
) -> None:
    _, party = imported[0]
    assert party.provider == "kalshi"
    assert party.provider_id == PARTY_TICKER
    assert party.question == "Which party wins the 2028 presidential election? (Republican)"
    assert party.description.startswith("If the Republican nominee wins")
    assert "certified electoral college count" in party.description
    assert party.category == "politics"
    assert sorted(party.tags) == ["kxpresparty", "politics"]
    assert party.event_key == "KXPRESPARTY-28"
    assert party.url == "https://kalshi.com/markets/kxpresparty/kxpresparty-28"
    assert party.resolution == 1
    assert party.resolution_source == "venue"
    assert party.created_at_ms == ms("2026-08-11T14:00:00+00:00")
    assert party.resolved_at_ms == ms("2026-08-25T22:03:17+00:00")
    assert party.close_at_ms == party.resolved_at_ms, (
        "the market closed early, so its scheduled close is superseded by its settlement"
    )
    assert party.interval_min == 1_440


def test_the_bar_grid_is_dense_and_carries_the_previous_close(
    imported: tuple[tuple[Market, ...], _FixtureTransport],
) -> None:
    _, party = imported[0]
    bars = _bars(party)
    assert len(bars) == 15
    t_first = ms("2026-08-11T00:00:00+00:00")
    assert [bar.t_ms for bar in bars] == [t_first + index * MS_PER_DAY for index in range(15)]

    first = bars[0]
    assert (first.open_bp, first.high_bp, first.low_bp, first.close_bp, first.vwap_bp) == (
        4_000,
        4_500,
        3_900,
        4_400,
        4_200,
    )
    assert (first.volume_milli, first.n_trades) == (1_200_000, 1)
    assert (first.yes_bid_bp, first.yes_ask_bp, first.open_interest) == (4_300, 4_500, 500)

    quiet = bars[5]  # 2026-08-16: the provider answered the period with a null price
    assert quiet.t_ms == ms("2026-08-16T00:00:00+00:00")
    assert {quiet.open_bp, quiet.high_bp, quiet.low_bp, quiet.close_bp, quiet.vwap_bp} == {5_700}
    assert (quiet.volume_milli, quiet.n_trades) == (0, 0)
    assert (quiet.yes_bid_bp, quiet.yes_ask_bp) == (5_600, 5_800), "the book is still quoted"

    absent = bars[7]  # 2026-08-18: the provider answered no period at all
    assert absent.t_ms == ms("2026-08-18T00:00:00+00:00")
    assert {absent.open_bp, absent.close_bp, absent.vwap_bp} == {6_300}
    assert (absent.volume_milli, absent.n_trades) == (0, 0)
    assert (absent.yes_bid_bp, absent.yes_ask_bp, absent.open_interest) == (None, None, None)

    for bar in bars:
        assert bar.low_bp <= min(bar.open_bp, bar.close_bp, bar.vwap_bp)
        assert bar.high_bp >= max(bar.open_bp, bar.close_bp, bar.vwap_bp)
        assert bar.low_bp >= 1 and bar.high_bp <= 9_999


def test_a_cent_is_a_hundred_basis_points_and_a_hundred_cents_clamps(
    imported: tuple[tuple[Market, ...], _FixtureTransport],
) -> None:
    _, party = imported[0]
    settling = _bars(party)[-1]
    assert settling.t_ms == ms("2026-08-25T00:00:00+00:00")
    assert (settling.open_bp, settling.low_bp, settling.vwap_bp) == (8_700, 8_600, 9_500)
    assert settling.close_bp == 9_999, "a 100 cent print clamps into the tradable band (CONTRACTS_V2 1.2)"
    assert settling.high_bp == 9_999
    assert party.final_price_bp == 9_999
    assert party.first_price_bp == 4_000, "the first period's open, which is also the first bar's as-of price"
    assert settling.yes_bid_bp == 9_900
    assert settling.yes_ask_bp is None, "a quote at 100 cents is no quote: clamping it would invent an ask"


def test_a_crossed_or_absent_quote_becomes_no_quote(
    imported: tuple[tuple[Market, ...], _FixtureTransport],
) -> None:
    _, party = imported[0]
    bars = _bars(party)
    crossed = bars[13]  # 2026-08-24: bid 90, ask 85
    assert crossed.t_ms == ms("2026-08-24T00:00:00+00:00")
    assert (crossed.yes_bid_bp, crossed.yes_ask_bp) == (None, None)
    assert crossed.close_bp == 8_700, "the crossed book does not touch the printed price"
    zero_bid = bars[9]  # 2026-08-20: bid 0, ask 62
    assert zero_bid.t_ms == ms("2026-08-20T00:00:00+00:00")
    assert (zero_bid.yes_bid_bp, zero_bid.yes_ask_bp) == (None, 6_200)


def test_the_trade_tape_reads_both_provider_shapes_and_is_sorted(
    imported: tuple[tuple[Market, ...], _FixtureTransport],
) -> None:
    nba, party = imported[0]
    assert [(trade.t_ms, trade.price_bp, trade.size_milli, trade.side) for trade in party.trades] == [
        (ms("2026-08-11T15:04:11+00:00"), 4_200, 10_000, "yes"),
        (ms("2026-08-13T09:00:00+00:00"), 4_900, 3_500, "no"),
        (ms("2026-08-17T20:15:00+00:00"), 6_000, 25_000, "yes"),
        (ms("2026-08-24T11:00:00+00:00"), 8_400, 8_000, "no"),
        (ms("2026-08-25T13:30:00+00:00"), 9_500, 40_000, "yes"),
    ], "decimal dollars, a fractional count, and a NO-only print mirrored onto the YES grid"
    assert [(trade.t_ms, trade.price_bp, trade.size_milli, trade.side) for trade in nba.trades] == [
        (ms("2026-05-25T17:00:00+00:00"), 5_600, 20_000, "yes"),
        (ms("2026-05-28T02:00:00+00:00"), 4_400, 5_000, "no"),
        (ms("2026-06-01T03:59:00+00:00"), 200, 100_000, "no"),
    ], "the older integer cent shape"
    keys = [(trade.t_ms, trade.price_bp, trade.size_milli, trade.side) for trade in party.trades]
    assert keys == sorted(keys), "the canonical trade order of CONTRACTS_V2 section 3"


def test_the_trade_pages_are_followed_and_a_stampless_print_is_dropped(
    imported: tuple[tuple[Market, ...], _FixtureTransport],
) -> None:
    _, transport = imported
    trade_calls = [entry for entry in transport.sent if entry.path.endswith("/markets/trades")]
    assert [(entry.params["ticker"], entry.params.get("cursor", "")) for entry in trade_calls] == [
        (NBA_TICKER, ""),
        (PARTY_TICKER, ""),
        (PARTY_TICKER, "CURSOR_TRADES_2"),
    ], "one page for the historical market, two for the market whose tape carries a cursor"
    party = imported[0][1]
    assert len(party.trades) == 5, "the sixth recorded print carries no created_time and is dropped"


def test_quality_counts_come_from_the_tape_and_never_from_a_guess(
    imported: tuple[tuple[Market, ...], _FixtureTransport],
) -> None:
    nba, party = imported[0]
    assert party.quality.n_trades == 5
    assert party.quality.unique_bettors is None, "Kalshi publishes no trader count"
    assert party.quality.life_days == 14
    assert party.quality.volume_milli_total == 21_100_000 == sum(bar.volume_milli for bar in party.bars)
    assert party.quality.traded_bars == 12
    assert nba.quality.volume_milli_total == 7_420_000, "the candlestick volumes, which are complete"
    assert nba.quality.n_trades == 3
    assert nba.quality.life_days == 6
    assert nba.quality.traded_bars == 8


def test_a_no_settlement_is_a_zero_and_the_historical_tape_is_daily(
    imported: tuple[tuple[Market, ...], _FixtureTransport],
) -> None:
    nba = imported[0][0]
    assert nba.resolution == 0
    assert nba.category == "sports"
    assert nba.close_at_ms == ms("2026-06-01T04:00:00+00:00")
    assert nba.resolved_at_ms == ms("2026-06-01T04:12:00+00:00")
    bars = _bars(nba)
    assert len(bars) == 8
    assert bars[0].t_ms == ms("2026-05-25T00:00:00+00:00")
    assert bars[0].close_bp == 5_700
    assert bars[-1].close_bp == 100 == nba.final_price_bp
    assert nba.notes.endswith("historical candlestick path.")


def test_the_limit_is_a_fetch_budget_spread_over_the_window(tmp_path: Path) -> None:
    """``limit`` decides which tapes are fetched, not where the walk stops.

    The dataset's cap is the builder's and is applied after the window has been walked and filtered
    (section 7.4). What is left here is a budget, because a settled Kalshi listing narrowed to the 731
    series of the first real build carries 54 333 markets in a twelve-month window and each one costs two
    requests. The budget is spent at equal stride over the walk, so it never buys one end of the window,
    and inside a stride it buys the busiest row (``_fetch_budget``), which here is the 18 543-contract
    ``KXPRESPARTY-28-R`` rather than the 7 420-contract market the walk happens to reach first.
    """
    transport = _FixtureTransport()
    markets = import_kalshi(
        client=_client(tmp_path, transport),
        window_start_ms=WINDOW_START_MS,
        window_end_ms=WINDOW_END_MS,
        freeze_ms=FREEZE_MS,
        limit=1,
    )
    assert [market.id for market in markets] == [f"kalshi-{PARTY_TICKER}"]
    assert not any(NBA_TICKER in path for path in transport.paths()), (
        "a tape outside the budget is never fetched"
    )


def test_a_fetch_budget_takes_the_whole_range_and_not_its_head() -> None:
    rows = tuple(range(10))
    assert evenly_spaced(rows, None) == rows
    assert evenly_spaced(rows, 0) == rows, "no budget is no thinning"
    assert evenly_spaced(rows, 20) == rows
    assert evenly_spaced(rows, 10) == rows
    # Two of ten: one from the first half and one from the second, never the first two.
    assert evenly_spaced(rows, 2) == (0, 5)
    assert evenly_spaced(rows, 4) == (0, 2, 5, 7)
    assert evenly_spaced((), 4) == ()
    # It is arithmetic on the index, so the same listing always buys the same tapes.
    assert evenly_spaced(rows, 3) == evenly_spaced(rows, 3)


def test_a_settlement_at_or_after_the_freeze_is_refused(tmp_path: Path) -> None:
    """The window is normally inside the freeze; when a caller widens it, the freeze still holds."""
    transport = _FixtureTransport()
    markets = import_kalshi(
        client=_client(tmp_path, transport),
        window_start_ms=WINDOW_START_MS,
        window_end_ms=FREEZE_MS + 30 * MS_PER_DAY,
        freeze_ms=FREEZE_MS,
    )
    ids = {market.id for market in markets}
    assert "kalshi-KXFUTURE-26SEP-X" not in ids, "it settles on 2026-09-08, after the freeze"
    assert ids == {f"kalshi-{NBA_TICKER}", f"kalshi-{PARTY_TICKER}"}


def test_the_hourly_grid_asks_for_hourly_candlesticks(tmp_path: Path) -> None:
    """An hourly dataset (ruling R24) is a second dataset, and the importer asks for its own grid.

    The ten-hour weather market that the daily grid cannot represent (one bar) is a real market on the
    hourly grid, which is the clearest evidence that ``interval_min`` reaches the provider and not just
    the record.
    """
    transport = _FixtureTransport()
    markets = import_kalshi(
        client=_client(tmp_path, transport),
        window_start_ms=WINDOW_START_MS,
        window_end_ms=WINDOW_END_MS,
        freeze_ms=FREEZE_MS,
        interval_min=60,
    )
    params = [entry.params for entry in transport.sent if entry.path.endswith("candlesticks")]
    assert params and all(entry["period_interval"] == "60" for entry in params)
    by_id = {market.id: market for market in markets}
    assert "kalshi-KXHIGHNY-26AUG20-B70" in by_id, "ten hours is one daily bar but eleven hourly bars"
    weather = by_id["kalshi-KXHIGHNY-26AUG20-B70"]
    assert weather.interval_min == 60
    assert weather.category == "weather"
    hourly = _bars(weather)
    assert [bar.t_ms for bar in hourly] == [
        ms("2026-08-20T13:00:00+00:00") + index * MS_PER_HOUR for index in range(11)
    ]
    assert hourly[0].close_bp == 3_400
    assert hourly[6].close_bp == 6_900, "the 19:00 period printed nothing and carries 18:00 forward"
    assert hourly[6].volume_milli == 0
    assert weather.final_price_bp == 9_700
    assert weather.quality.n_trades == 2
    party = by_id[f"kalshi-{PARTY_TICKER}"]
    bars = _bars(party)
    assert [bar.t_ms for bar in bars] == [bars[0].t_ms + index * MS_PER_HOUR for index in range(len(bars))]
    assert bars[0].t_ms == ms("2026-08-11T14:00:00+00:00")
    assert bars[-1].t_ms == ms("2026-08-25T22:00:00+00:00")


def test_an_interval_off_the_grid_is_an_invalid_config(tmp_path: Path) -> None:
    client = _client(tmp_path, _FixtureTransport())
    with pytest.raises(InvalidConfigError):
        import_kalshi(
            client=client,
            window_start_ms=WINDOW_START_MS,
            window_end_ms=WINDOW_END_MS,
            freeze_ms=FREEZE_MS,
            interval_min=15,
        )
    with pytest.raises(InvalidConfigError):
        list_open_kalshi(client=client, now_ms=FREEZE_MS, interval_min=1)


def test_a_series_allow_list_keeps_only_what_it_names(tmp_path: Path) -> None:
    markets = import_kalshi(
        client=_client(tmp_path, _FixtureTransport()),
        window_start_ms=WINDOW_START_MS,
        window_end_ms=WINDOW_END_MS,
        freeze_ms=FREEZE_MS,
        series_allow_list=("KXPRESPARTY",),
    )
    assert [market.id for market in markets] == [f"kalshi-{PARTY_TICKER}"]


@dataclass
class _CursorTransport(httpx.BaseTransport):
    """A listing that never ends: it answers one market row and a cursor, ``repeat``ed or fresh each page."""

    repeat: bool = False
    calls: int = 0

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        cursor = "SAME" if self.repeat else f"CURSOR_{self.calls}"
        row = json.loads((FIXTURES / "markets_settled_page1.json").read_text(encoding="utf-8"))["markets"][0]
        return httpx.Response(200, json={"markets": [row], "cursor": cursor})


def test_a_listing_that_repeats_its_cursor_stops(tmp_path: Path) -> None:
    transport = _CursorTransport(repeat=True)
    client = _client(tmp_path, transport)
    rows = kalshi_module._list_rows(client, path="/markets", params={"status": "settled"})
    assert transport.calls == 2, "the second page repeated the cursor, which is how a broken page reads"
    assert len(rows) == 2


def test_a_listing_that_never_ends_raises_instead_of_truncating(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(kalshi_module, "KALSHI_MARKETS_MAX_PAGES", 2)
    transport = _CursorTransport()
    with pytest.raises(MalformedResponseError) as raised:
        kalshi_module._list_rows(_client(tmp_path, transport), path="/markets", params={"status": "settled"})
    assert "pages=2" in str(raised.value), "a shortfall is reported, never silent"
    assert transport.calls == 2


def test_the_candlestick_request_is_chunked_without_a_gap_or_an_overlap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A year of hourly periods is far past what the endpoint answers, so the range is walked in chunks.

    With the cap lowered to five periods the fifteen daily bars of the recorded market take three requests,
    and the union of the three ranges has to be exactly the market's life: a gap would be a hole in the
    tape the loader refuses, an overlap would be a wasted request.
    """
    monkeypatch.setattr(kalshi_module, "KALSHI_CANDLESTICK_MAX_PERIODS", 5)
    transport = _FixtureTransport()
    client = _client(tmp_path, transport)
    row = kalshi_module._row_of(
        json.loads((FIXTURES / "markets_settled_page1.json").read_text(encoding="utf-8"))["markets"][0],
        where="fixture",
    )
    assert row is not None and row.ticker == PARTY_TICKER
    first_ms = ms("2026-08-11T00:00:00+00:00")
    last_ms = ms("2026-08-25T00:00:00+00:00")
    candles = kalshi_module._candlesticks(
        client, row=row, interval_min=1_440, start_ms=first_ms, end_ms=last_ms, historical=False
    )
    ranges = [
        (int(entry.params["start_ts"]), int(entry.params["end_ts"]))
        for entry in transport.sent
        if entry.path.endswith("candlesticks")
    ]
    assert len(ranges) == 3
    assert ranges[0][0] == first_ms // 1_000
    # Two intervals past the last bar, and only on the last chunk: the endpoint selects periods by their
    # end, and the period that opens inside the last bar ends after it on a provider whose day is not
    # UTC's. An intermediate chunk keeps the exact butt-joint below, so no request is wasted.
    assert ranges[-1][1] == (last_ms + 2 * MS_PER_DAY) // 1_000
    for earlier, later in zip(ranges, ranges[1:], strict=False):
        assert later[0] == earlier[1], "each chunk starts where the previous one ended"
    assert len(candles) == 14, "the recorded tape has fourteen periods for fifteen bars"


def test_a_malformed_candlestick_payload_is_a_malformed_response(tmp_path: Path) -> None:
    client = _client(tmp_path, _FixtureTransport(candlesticks="candlesticks_malformed.json"))
    with pytest.raises(MalformedResponseError) as raised:
        import_kalshi(
            client=client,
            window_start_ms=WINDOW_START_MS,
            window_end_ms=WINDOW_END_MS,
            freeze_ms=FREEZE_MS,
        )
    assert "candlesticks" in str(raised.value)


def test_a_cutoff_without_its_instant_is_a_malformed_response(tmp_path: Path) -> None:
    client = _client(tmp_path, _ScriptedTransport(statuses=(200,), body='{"trade_ts": "2026-07-08T00:00:00Z"}'))
    with pytest.raises(MalformedResponseError):
        historical_cutoff_ms(client)


# --------------------------------------------------------------------------------------------------
# The open-market lister (L1)
# --------------------------------------------------------------------------------------------------
def test_open_markets_stop_at_the_last_completed_bar(tmp_path: Path) -> None:
    now_ms = ms("2026-09-05T12:00:00+00:00")
    transport = _FixtureTransport()
    open_markets = list_open_kalshi(client=_client(tmp_path, transport), now_ms=now_ms)
    assert [market.id for market in open_markets] == [f"kalshi-{FED_TICKER}"], "the open shard is dropped"
    fed = open_markets[0]
    assert fed.provider == "kalshi"
    assert fed.question == "Fed target rate after the September 2026 meeting? (4.25 to 4.50)"
    assert fed.category == "economics"
    assert fed.created_at_ms == ms("2026-09-01T10:00:00+00:00")
    assert fed.close_at_ms == ms("2026-09-17T18:00:00+00:00")
    assert fed.fee_schedule_id == KALSHI_FEE_SCHEDULE_ID
    bars = _bars(fed)
    assert [bar.t_ms for bar in bars] == [
        ms("2026-09-01T00:00:00+00:00") + index * MS_PER_DAY for index in range(4)
    ], "the bar covering now_ms has not finished and must not be shown"
    assert bars[0].close_bp == 6_100, "the decimal-dollar candlestick shape"
    assert bars[2].close_bp == 6_300, "a period with no print carries the previous close forward"
    assert fed.first_price_bp == 6_000
    assert fed.last_price_bp == 6_500 == bars[-1].close_bp


def test_open_markets_carry_the_as_of_tape_only(tmp_path: Path) -> None:
    now_ms = ms("2026-09-05T12:00:00+00:00")
    fed = list_open_kalshi(client=_client(tmp_path, _FixtureTransport()), now_ms=now_ms)[0]
    assert fed.quality.n_trades == 2, "the print recorded on 2026-09-06 is after now_ms and is dropped"
    assert fed.quality.volume_milli_total == 2_800_000
    assert fed.quality.traded_bars == 3
    assert fed.quality.life_days == 4
    assert not hasattr(fed, "resolution"), "an open market carries no outcome (CONTRACTS_V2 7.12)"
    assert not hasattr(fed, "resolved_at_ms")


def test_a_market_with_no_completed_bar_still_states_a_price(tmp_path: Path) -> None:
    """Ruling R11: with no completed bar there are no bars, and the as-of price is the first price."""
    now_ms = ms("2026-09-01T18:00:00+00:00")
    fed = list_open_kalshi(client=_client(tmp_path, _FixtureTransport()), now_ms=now_ms)[0]
    assert _bars(fed) == []
    assert fed.first_price_bp == fed.last_price_bp == 6_000, "the first print, since no period is complete"
    assert fed.quality.n_trades == 1
    assert fed.quality.traded_bars == 0


# --------------------------------------------------------------------------------------------------
# The shape the provider answers today: decimal strings where the recorded fixtures carry integers
# --------------------------------------------------------------------------------------------------
CURRENT_TICKER: Final = "KXCURRENT-26AUG20-T1"
QUIET_TICKER: Final = "KXCURRENT-26AUG20-T2"


def _current_row(ticker: str, *, volume_fp: str) -> dict[str, object]:
    """One settled listing row exactly as ``api.elections.kalshi.com`` answers it now.

    Every quantity is a decimal string under a renamed key: ``volume_fp`` where the recorded fixtures
    carry ``volume``, ``yes_bid_dollars`` where they carry ``yes_bid``, and so on. The old spellings are
    absent from the answer, not merely reformatted.
    """
    return {
        "ticker": ticker,
        "series_ticker": "KXCURRENT",
        "event_ticker": "KXCURRENT-26AUG20",
        "title": "Will the current shape parse?",
        "yes_sub_title": "Yes",
        "category": "Economics",
        "rules_primary": "Resolves YES when the importer reads the decimal shape.",
        "open_time": "2026-08-10T00:00:00Z",
        "close_time": "2026-08-20T00:00:00Z",
        "settlement_ts": "2026-08-20T00:00:00Z",
        "expiration_time": "2026-08-27T00:00:00Z",
        "expected_expiration_time": "2026-08-20T00:00:00Z",
        "status": "finalized",
        "result": "yes",
        "volume_fp": volume_fp,
        "volume_24h_fp": "0.00",
        "open_interest_fp": "967.75",
        "last_price_dollars": "0.4200",
        "yes_bid_dollars": "0.4300",
        "yes_ask_dollars": "0.4500",
        "settlement_value_dollars": "1.0000",
    }


def _current_candles(*, volume: str) -> dict[str, object]:
    return {
        "candlesticks": [
            {
                "end_period_ts": ms("2026-08-11T00:00:00+00:00") // 1_000,
                "open_interest": "967.75",
                "volume": volume,
                "price": {
                    "open": "0.4000",
                    "high": "0.4500",
                    "low": "0.3900",
                    "close": "0.4200",
                    "mean": "0.4200",
                },
                "yes_bid": {"close": "0.4300"},
                "yes_ask": {"close": "0.4500"},
            },
            {
                "end_period_ts": ms("2026-08-12T00:00:00+00:00") // 1_000,
                "open_interest": "0.00",
                "volume": "0.00",
                "price": {"open": None, "high": None, "low": None, "close": None, "mean": None},
                "yes_bid": {"close": "0.0000"},
                "yes_ask": {"close": "1.0000"},
            },
        ]
    }


class _CurrentShapeTransport(httpx.BaseTransport):
    """Answers the settled routes with the decimal shape the provider serves today.

    ``prints=False`` answers the print tape the way the live exchange answers it for a **settled**
    ticker: an empty list, whatever the market traded. That is not a broken fixture, it is the measured
    behaviour of ``GET /markets/trades?ticker=<settled ticker>`` (probed on 2026-09-07 against a market
    that had traded 5 376 236 contracts), and it is what ``quality.tape_kind`` exists to record.
    """

    def __init__(self, *, prints: bool = True) -> None:
        self.sent: list[str] = []
        self._prints = prints

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.sent.append(path)
        params = {key: value for key, value in request.url.params.multi_items()}
        payload: dict[str, object]
        if path.endswith("/historical/cutoff"):
            payload = {"market_settled_ts": CUTOFF_MS // 1_000}
        elif path.endswith("/historical/markets"):
            payload = {"markets": [], "cursor": ""}
        elif path.endswith("/markets/trades"):
            prints = [
                {
                    "created_time": "2026-08-11T15:04:11Z",
                    "yes_price_dollars": "0.4200",
                    "count": "3.00",
                    "taker_side": "yes",
                }
            ]
            payload = {"trades": prints if self._prints else [], "cursor": ""}
        elif path.endswith("/candlesticks"):
            quiet = f"/{QUIET_TICKER}/" in path
            payload = _current_candles(volume="0.00" if quiet else "12.50")
        elif path.endswith("/markets"):
            assert params.get("status") == "settled"
            payload = {
                "markets": [
                    _current_row(CURRENT_TICKER, volume_fp="8252.22"),
                    _current_row(QUIET_TICKER, volume_fp="8252.22"),
                ],
                "cursor": "",
            }
        else:  # pragma: no cover - a route the importer is not supposed to reach
            return httpx.Response(404, json={"error": {"message": path}})
        return httpx.Response(200, json=payload, headers={"content-type": "application/json"})


def _import_current(tmp_path: Path, *, prints: bool = True) -> tuple[Market, ...]:
    client = _client(tmp_path, _CurrentShapeTransport(prints=prints))
    try:
        return import_kalshi(
            client=client,
            window_start_ms=WINDOW_START_MS,
            window_end_ms=WINDOW_END_MS,
            freeze_ms=FREEZE_MS,
            series_allow_list=("KXCURRENT",),
        )
    finally:
        client.close()


def test_a_candlestick_volume_that_arrives_as_a_decimal_string_is_a_contract_count(tmp_path: Path) -> None:
    """The defect the first real dataset build hit: ``volume`` answered as ``"0.00"``.

    Both candlestick tapes answer ``volume`` and ``open_interest`` as decimal strings. Read as integers
    they raised ``MalformedResponseError`` and the whole Kalshi import died on its first market; read as
    decimals they are a contract count, in thousandths for a size and in whole contracts for open
    interest.
    """
    traded, _quiet = _import_current(tmp_path)
    assert traded.id.endswith(CURRENT_TICKER)
    bars = _bars(traded)
    assert bars[0].t_ms == ms("2026-08-10T00:00:00+00:00")
    assert bars[0].volume_milli == 12_500, "12.50 contracts is 12 500 thousandths"
    assert bars[0].open_interest == 968, "967.75 contracts rounds half up to a whole contract"
    assert bars[1].volume_milli == 0
    assert bars[1].open_interest == 0
    assert (bars[0].open_bp, bars[0].close_bp) == (4_000, 4_200)
    assert (bars[0].high_bp, bars[0].low_bp) == (4_500, 3_900)
    assert traded.quality.volume_milli_total == 12_500


def test_a_print_count_that_arrives_as_a_decimal_string_is_still_a_size(tmp_path: Path) -> None:
    traded, _quiet = _import_current(tmp_path)
    assert [(trade.price_bp, trade.size_milli, trade.side) for trade in traded.trades] == [
        (4_200, 3_000, "yes")
    ]
    assert traded.quality.n_trades == 1


def test_the_listing_row_reads_the_renamed_decimal_fields(tmp_path: Path) -> None:
    """``volume_fp``, ``last_price_dollars`` and the two ``_dollars`` quotes replaced the old keys.

    The row's volume is the fallback the quality block uses when the candlestick tape printed nothing, so
    a row parsed under the old key names reports a market with no volume at all.
    """
    _traded, quiet = _import_current(tmp_path)
    assert quiet.id.endswith(QUIET_TICKER)
    assert all(bar.volume_milli == 0 for bar in quiet.bars), "this market's periods printed no size"
    assert quiet.quality.volume_milli_total == 8_252_220, "8252.22 contracts, from the row's volume_fp"
    assert quiet.resolution == 1


def test_the_settlement_instant_beats_the_scheduled_expiration(tmp_path: Path) -> None:
    """``settlement_ts`` is when the market settled; ``expiration_time`` is the latest it could.

    They differ on every settled row the provider answers today, by up to a week, and ``resolved_at`` is
    what fixes a market's last bar, the window filter and the fold it lands in.
    """
    traded, _quiet = _import_current(tmp_path)
    assert traded.resolved_at_ms == ms("2026-08-20T00:00:00+00:00")
    assert _bars(traded)[-1].t_ms == ms("2026-08-20T00:00:00+00:00")


def test_a_settlement_value_in_dollars_resolves_the_market() -> None:
    row = dict(_current_row(CURRENT_TICKER, volume_fp="0.00"))
    del row["result"]
    assert kalshi_module._resolution_of(row) == 1
    row["settlement_value_dollars"] = "0.0000"
    assert kalshi_module._resolution_of(row) == 0
    row["settlement_value_dollars"] = "0.5000"
    assert kalshi_module._resolution_of(row) is None


# --------------------------------------------------------------------------------------------------
# The bars-only tape, the series categories and the series subjects
# --------------------------------------------------------------------------------------------------
def test_a_settled_market_with_no_print_tape_is_a_bars_only_market(tmp_path: Path) -> None:
    """The tape kind is read off what the fetch answered, not off what the endpoint promises.

    The exchange answers no print for a settled ticker, so ``n_trades`` is ``0`` and stays ``0``: the
    honest count of a tape that publishes none. What the candlesticks do carry is size, so
    ``traded_bars`` counts the periods that traded and the ``min_trades`` filter of section 7.4 has
    something real to read for this provider.
    """
    traded, quiet = _import_current(tmp_path, prints=False)
    assert traded.trades == ()
    assert traded.quality.n_trades == 0
    assert traded.quality.tape_kind == TAPE_KIND_BARS_ONLY
    assert traded.quality.traded_bars == 1, "one of the two periods carried volume"
    assert traded.quality.volume_milli_total == 12_500
    assert quiet.quality.tape_kind == TAPE_KIND_BARS_ONLY
    assert quiet.quality.traded_bars == 0, "this market printed no size in any period"


def test_a_settled_market_with_a_print_tape_is_a_prints_market(tmp_path: Path) -> None:
    traded, _quiet = _import_current(tmp_path)
    assert traded.quality.tape_kind == TAPE_KIND_PRINTS
    assert traded.quality.n_trades == 1


def test_the_tape_kind_is_written_only_when_the_tape_carries_no_print(tmp_path: Path) -> None:
    """The flag marks the exception, so a print tape's market file keeps the bytes it always had."""
    prints, _ = _import_current(tmp_path)
    bars_only, _ = _import_current(tmp_path / "second", prints=False)
    quality_with_prints = _market_payload(prints)["quality"]
    quality_bars_only = _market_payload(bars_only)["quality"]
    assert isinstance(quality_with_prints, dict) and isinstance(quality_bars_only, dict)
    assert "tape_kind" not in quality_with_prints
    assert quality_bars_only["tape_kind"] == TAPE_KIND_BARS_ONLY


def test_the_series_category_map_answers_the_twelve_categories_and_nothing_else() -> None:
    """The listing rows carry no category, so a series map is the only place one can come from."""
    categories = load_series_categories()
    assert len(categories) >= 700, "the map covers the series list the first real build asked for"
    assert set(categories.values()) <= set(CATEGORIES_OF_SECTION_2)
    assert series_category("KXINX") == "finance"
    assert series_category("kxinx") == "finance", "a series ticker is compared upper case"
    assert series_category("KXHIGHNY") == "weather"
    assert series_category("KXBTCMAXMON") == "crypto"
    assert series_category("NOSUCHSERIES") is None, "an unmapped series is a fallback, not a guess"


def test_a_row_without_a_category_takes_the_one_its_series_maps_to() -> None:
    row = dict(_current_row(CURRENT_TICKER, volume_fp="0.00"))
    del row["category"]
    assert kalshi_module._category_of(row, "KXHIGHNY") == "weather"
    assert kalshi_module._category_of(row, "NOSUCHSERIES") == CATEGORY_FALLBACK
    # A row that does carry a category is still believed: a provider that starts publishing one again
    # is a better source than any map.
    assert kalshi_module._category_of({"category": "Crypto"}, "KXHIGHNY") == "crypto"


def test_the_series_subject_map_names_stated_subjects_and_the_question_names_derived_ones() -> None:
    subjects = load_series_subjects()
    assert subjects["KXINX"] == ("S&P 500", "Stock market index")
    titles, flags = wiki_subjects_of(
        "KXINX", "Will the index close above the Dow Jones Industrial Average on Jul 8, 2026?"
    )
    assert titles == tuple(sorted(titles)) and len(titles) == len(flags)
    stated = {title for title, flag in zip(titles, flags, strict=True) if flag == "stated"}
    derived = {title for title, flag in zip(titles, flags, strict=True) if flag == "derived"}
    assert stated == {"S&P 500", "Stock market index"}
    assert derived == {"Dow Jones Industrial Average"}, "the question names candidates of its own"


def test_an_unmapped_series_still_gets_the_subjects_its_own_question_names() -> None:
    titles, flags = wiki_subjects_of(
        "NOSUCHSERIES", "Will Donald Trump visit Greenland before Feb 1, 2026?"
    )
    assert set(flags) == {"derived"}
    assert "Donald Trump" in titles and "Greenland" in titles


def test_a_question_with_no_capitalised_run_gets_no_derived_subject() -> None:
    titles, flags = wiki_subjects_of("NOSUCHSERIES", "will it rain tomorrow?")
    assert titles == () and flags == ()


def test_the_eight_subject_cap_keeps_the_stated_ones() -> None:
    stated = tuple(f"Article {index}" for index in range(9))
    titles, flags = wiki_subjects_of(
        "MANY",
        "Will Alpha Bravo Charlie Delta happen?",
        subjects={"MANY": stated},
    )
    assert len(titles) == WIKI_SUBJECTS_MAX
    assert set(flags) == {"stated"}, "a curated title outranks a guess when the cap bites"


# --------------------------------------------------------------------------------------------------
# Metaculus: declared, token-gated, unbuilt
# --------------------------------------------------------------------------------------------------
def test_the_metaculus_importer_is_not_configured(tmp_path: Path) -> None:
    client = _client(tmp_path, _FixtureTransport())
    with pytest.raises(NotConfiguredError) as raised:
        import_metaculus(
            client=client,
            window_start_ms=WINDOW_START_MS,
            window_end_ms=WINDOW_END_MS,
            freeze_ms=FREEZE_MS,
        )
    assert METACULUS_TOKEN_ENV in str(raised.value)


# --------------------------------------------------------------------------------------------------
# The one live probe: skipped unless PMX_LIVE=1
# --------------------------------------------------------------------------------------------------
@pytest.mark.skipif(os.environ.get("PMX_LIVE") != "1", reason="live network probe; set PMX_LIVE=1 to run it")
def test_live_kalshi_answers_the_cutoff_and_a_settled_page(tmp_path: Path) -> None:
    client = HttpClient(
        base_url=KALSHI_BASE_URL,
        user_agent=build_user_agent(os.environ.get(USER_AGENT_CONTACT_ENV, CONTACT)),
        min_interval_ms=DEFAULT_MIN_INTERVAL_MS,
        cache_dir=tmp_path / "cache",
        api_key=os.environ.get("PMX_KALSHI_API_KEY"),
    )
    try:
        cutoff_ms = historical_cutoff_ms(client)
        assert cutoff_ms > ms("2025-01-01T00:00:00+00:00")
        payload = client.get_json("/markets", {"status": "settled", "limit": 20})
        assert isinstance(payload, dict)
        rows = payload["markets"]
        assert isinstance(rows, list) and rows, "a settled page with no market means the shape moved"
        first = rows[0]
        assert isinstance(first, dict)
        assert {"ticker", "status", "result"} <= set(first)
    finally:
        client.close()


# --------------------------------------------------------------------------------------------------
# The Eastern-time candlestick grid, the live path's field names and the fetch budget
# (the three defects the 2026-09-08 rebuild of data/datasets/y2026 exposed, docs/BUILD_STATE.md 7)
# --------------------------------------------------------------------------------------------------
EASTERN_SERIES: Final = "KXEASTERN"
#: 04:00 UTC, which is midnight in New York while daylight saving is in force. Every daily candlestick
#: the exchange answers ends there (or at 05:00 UTC in winter), never at a UTC midnight.
EASTERN_MIDNIGHT_S: Final = 4 * (MS_PER_HOUR // 1_000)
HISTORICAL_EASTERN_TICKER: Final = "KXEASTERN-26MAY10-T1"
LIVE_EASTERN_TICKER: Final = "KXEASTERN-26AUG10-T1"
QUIET_EASTERN_TICKER: Final = "KXEASTERN-26MAY10-T2"
SHORT_EASTERN_TICKER: Final = "KXEASTERN-26MAY03-T3"


def _eastern_row(ticker: str, *, opened: str, settled: str, volume_fp: str) -> dict[str, object]:
    return {
        "ticker": ticker,
        "series_ticker": EASTERN_SERIES,
        "event_ticker": ticker.rsplit("-", 1)[0],
        "title": "Will the Eastern grid land on a UTC bar?",
        "yes_sub_title": "Yes",
        "rules_primary": "Resolves YES when every period lands on the bar it opens in.",
        "open_time": opened,
        "close_time": settled,
        "settlement_ts": settled,
        "expiration_time": settled,
        "status": "finalized",
        "result": "yes",
        "volume_fp": volume_fp,
        "open_interest_fp": "100.00",
        "last_price_dollars": "0.5000",
    }


def _eastern_candles(*, first_end_s: int, periods: int, live: bool) -> list[dict[str, object]]:
    """``periods`` daily candlesticks ending at midnight Eastern, in the shape the path answers.

    The two paths do not answer the same keys: ``/historical/markets/...`` serves ``volume`` and
    ``price.close``, the live ``/series/...`` path serves ``volume_fp`` and ``price.close_dollars``.
    """
    prices = {"open": "0.5000", "high": "0.6000", "low": "0.4000", "close": "0.5500", "mean": "0.5200"}
    out: list[dict[str, object]] = []
    for index in range(periods):
        end_s = first_end_s + index * (MS_PER_DAY // 1_000)
        if live:
            out.append(
                {
                    "end_period_ts": end_s,
                    "open_interest_fp": "100.00",
                    "volume_fp": "7.00",
                    "price": {f"{key}_dollars": value for key, value in prices.items()},
                    "yes_bid": {"close_dollars": "0.5400"},
                    "yes_ask": {"close_dollars": "0.5600"},
                }
            )
        else:
            out.append(
                {
                    "end_period_ts": end_s,
                    "open_interest": "100.00",
                    "volume": "7.00",
                    "price": dict(prices),
                    "yes_bid": {"close": "0.5400"},
                    "yes_ask": {"close": "0.5600"},
                }
            )
    return out


class _EasternTransport(httpx.BaseTransport):
    """The exchange as it answers today: an Eastern candlestick grid, selected by the period's end.

    Two settled markets, one on each side of the historical cutoff, so both candlestick paths and both
    field spellings are exercised by one import. The candlestick route answers only the periods whose
    **end** falls inside the requested range, which is what the real endpoint does and what decides
    whether the settling bar's period is reachable at all.
    """

    def __init__(self) -> None:
        self.sent: list[str] = []
        self.ranges: dict[str, tuple[int, int]] = {}

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.sent.append(path)
        params = {key: value for key, value in request.url.params.multi_items()}
        payload: dict[str, object]
        if path.endswith("/historical/cutoff"):
            payload = {"market_settled_ts": CUTOFF_MS // 1_000}
        elif path.endswith("/historical/markets"):
            payload = {
                "markets": [
                    _eastern_row(
                        HISTORICAL_EASTERN_TICKER,
                        opened="2026-05-01T12:00:00Z",
                        settled="2026-05-10T18:00:00Z",
                        volume_fp="70.00",
                    ),
                    # Never traded, so it can pass no branch of the min_trades filter of 7.4.
                    _eastern_row(
                        QUIET_EASTERN_TICKER,
                        opened="2026-05-01T12:00:00Z",
                        settled="2026-05-10T18:00:00Z",
                        volume_fp="0.00",
                    ),
                    # Two days of life, so the min_life filter of 7.4 removes it whatever its tape says.
                    _eastern_row(
                        SHORT_EASTERN_TICKER,
                        opened="2026-05-01T12:00:00Z",
                        settled="2026-05-03T18:00:00Z",
                        volume_fp="500.00",
                    ),
                ],
                "cursor": "",
            }
        elif path.endswith("/markets/trades"):
            payload = {"trades": [], "cursor": ""}
        elif path.endswith("/candlesticks"):
            live = "/series/" in path
            ticker = LIVE_EASTERN_TICKER if live else HISTORICAL_EASTERN_TICKER
            first_day = "2026-08-02T00:00:00+00:00" if live else "2026-05-02T00:00:00+00:00"
            first_end_s = ms(first_day) // 1_000 + EASTERN_MIDNIGHT_S
            start_s, end_s = int(params["start_ts"]), int(params["end_ts"])
            self.ranges[ticker] = (start_s, end_s)
            answered = [
                candle
                for candle in _eastern_candles(first_end_s=first_end_s, periods=10, live=live)
                if start_s <= int(str(candle["end_period_ts"])) <= end_s
            ]
            payload = {"ticker": ticker, "candlesticks": answered}
        elif path.endswith("/markets"):
            payload = {
                "markets": [
                    _eastern_row(
                        LIVE_EASTERN_TICKER,
                        opened="2026-08-01T12:00:00Z",
                        settled="2026-08-10T18:00:00Z",
                        volume_fp="70.00",
                    )
                ],
                "cursor": "",
            }
        else:  # pragma: no cover - a route the importer is not supposed to reach
            return httpx.Response(404, json={"error": {"message": path}})
        return httpx.Response(200, json=payload, headers={"content-type": "application/json"})


def _import_eastern(
    tmp_path: Path, *, min_life_days: int = 0
) -> tuple[tuple[Market, ...], _EasternTransport]:
    transport = _EasternTransport()
    client = _client(tmp_path, transport)
    try:
        markets = import_kalshi(
            client=client,
            window_start_ms=WINDOW_START_MS,
            window_end_ms=WINDOW_END_MS,
            freeze_ms=FREEZE_MS,
            series_allow_list=(EASTERN_SERIES,),
            min_life_days=min_life_days,
        )
    finally:
        client.close()
    return markets, transport


def _by_ticker(markets: Sequence[Market], ticker: str) -> Market:
    return next(market for market in markets if market.provider_id == ticker)


def test_a_daily_candlestick_that_ends_at_midnight_eastern_lands_on_the_bar_it_opens_in(
    tmp_path: Path,
) -> None:
    """The defect that left the rebuilt dataset with zero Kalshi markets.

    A ``period_interval=1440`` answer ends every period at midnight New York, which is 04:00 or 05:00
    UTC, so ``end_period_ts`` minus one day is never a multiple of a day and never a bar of the grid.
    The candles were therefore keyed four hours off the grid, ``_bars`` found none of them, every bar
    repeated the first price with ``volume_milli = 0``, and ``quality.traded_bars`` came out ``0`` for
    every Kalshi market: the one count ruling R167's branch of ``min_trades`` reads.
    """
    markets, _transport = _import_eastern(tmp_path)
    historical = _by_ticker(markets, HISTORICAL_EASTERN_TICKER)
    bars = _bars(historical)
    assert bars[0].t_ms == ms("2026-05-01T00:00:00+00:00")
    assert bars[-1].t_ms == ms("2026-05-10T00:00:00+00:00")
    assert [bar.t_ms for bar in bars] == [bars[0].t_ms + index * MS_PER_DAY for index in range(10)]
    assert all(bar.volume_milli == 7_000 for bar in bars), "every period carried seven contracts"
    assert all(bar.close_bp == 5_500 for bar in bars), "a bar with a candle carries the candle's close"
    assert historical.quality.traded_bars == 10
    assert historical.quality.tape_kind == TAPE_KIND_BARS_ONLY
    assert historical.quality.volume_milli_total == 70_000


def test_the_settling_bar_keeps_the_period_that_ends_after_it(tmp_path: Path) -> None:
    """The last bar's period ends after the last bar, so the range asks for one period of slack.

    The endpoint selects periods by their end. A market settling on 2026-05-10 has its last period
    running to midnight Eastern on 2026-05-11, so a range that stopped at 2026-05-11T00:00Z answered
    nine periods for ten bars and the settling bar, the one that fixes ``final_price_bp``, was left
    carrying the previous close.
    """
    markets, transport = _import_eastern(tmp_path)
    start_s, end_s = transport.ranges[HISTORICAL_EASTERN_TICKER]
    assert start_s == ms("2026-05-01T00:00:00+00:00") // 1_000
    assert end_s == ms("2026-05-12T00:00:00+00:00") // 1_000
    last = _bars(_by_ticker(markets, HISTORICAL_EASTERN_TICKER))[-1]
    assert last.t_ms == ms("2026-05-10T00:00:00+00:00")
    assert last.volume_milli == 7_000, "the settling bar has its own period, not the previous close"
    assert _by_ticker(markets, HISTORICAL_EASTERN_TICKER).final_price_bp == 5_500


def test_the_live_candlestick_path_answers_the_renamed_fields(tmp_path: Path) -> None:
    """``volume_fp``, ``open_interest_fp`` and ``price.close_dollars`` on the live path.

    A market that settled after the historical cutoff is only reachable through
    ``/series/{series}/markets/{ticker}/candlesticks``, and that path answers the renamed keys. Read
    under the historical spellings alone its periods carried no price and no size at all, so the last
    two months of a twelve-month window, which are the sealed fold of section 7.7, contributed nothing
    but flat tapes.
    """
    markets, transport = _import_eastern(tmp_path)
    assert any("/series/" in path and path.endswith("candlesticks") for path in transport.sent)
    live = _by_ticker(markets, LIVE_EASTERN_TICKER)
    bars = _bars(live)
    assert len(bars) == 10
    assert all(bar.volume_milli == 7_000 for bar in bars)
    assert all(bar.open_interest == 100 for bar in bars)
    assert [bars[0].open_bp, bars[0].high_bp, bars[0].low_bp, bars[0].close_bp] == [
        5_000,
        6_000,
        4_000,
        5_500,
    ]
    assert (bars[0].yes_bid_bp, bars[0].yes_ask_bp) == (5_400, 5_600)
    assert live.quality.traded_bars == 10


def test_the_walk_does_not_buy_a_tape_the_build_filters_would_remove(tmp_path: Path) -> None:
    """Two necessary conditions read off the listing row, so the fetch budget buys no certain refusal.

    A row whose reported lifetime volume is zero has neither a print nor a bar with size, so it fails
    ``min_trades`` on all three of its branches; a row that lived two days fails ``min_life_days = 7``.
    Neither is a new filter: both are the builder's, and skipping the tape only saves the two requests
    the builder was going to throw away. Of the 166 586 settled rows the first real build's listing
    offered inside its window, 88 per cent lived under a week.
    """
    markets, transport = _import_eastern(tmp_path, min_life_days=7)
    kept = {market.provider_id for market in markets}
    assert kept == {HISTORICAL_EASTERN_TICKER, LIVE_EASTERN_TICKER}
    assert not any(QUIET_EASTERN_TICKER in path for path in transport.sent)
    assert not any(SHORT_EASTERN_TICKER in path for path in transport.sent)


def test_the_walk_keeps_a_short_row_when_no_life_floor_is_asked_for(tmp_path: Path) -> None:
    """The floor defaults to nothing, so an importer call that passes no build config is unchanged."""
    markets, _transport = _import_eastern(tmp_path)
    assert SHORT_EASTERN_TICKER in {market.provider_id for market in markets}


def test_the_fetch_budget_takes_the_busiest_row_of_each_stride() -> None:
    """The stride of ``evenly_spaced``, with the busiest row of each stride instead of its first.

    The window is still covered, because the strides are still equal slices of a walk ordered by
    settlement; what changes is which tape inside a slice is worth its two requests. A budget of 400
    buys 2.6 per cent of the rows the first real build's listing offered, and the head of a stride was
    typically a market that traded a handful of contracts on a single day.
    """
    rows = tuple(
        kalshi_module._Row(
            ticker=f"KX-{index:02d}",
            series="KX",
            event_key="KX-1",
            question="q",
            description="d",
            category="other",
            created_at_ms=0,
            close_at_ms=MS_PER_DAY,
            resolved_at_ms=index * MS_PER_DAY,
            resolution=1,
            volume_milli=(index % 5) * 1_000,
            quote_mid_bp=5_000,
            last_price_bp=5_000,
        )
        for index in range(10)
    )
    assert kalshi_module._fetch_budget(rows, None) == rows
    assert kalshi_module._fetch_budget(rows, 0) == rows, "no budget is no thinning"
    assert kalshi_module._fetch_budget(rows, 20) == rows
    # Two of ten: the busiest of the first half and the busiest of the second, never the first two.
    assert [row.ticker for row in kalshi_module._fetch_budget(rows, 2)] == ["KX-04", "KX-09"]
    assert [row.ticker for row in kalshi_module._fetch_budget(rows, 5)] == [
        "KX-01",
        "KX-03",
        "KX-04",
        "KX-07",
        "KX-09",
    ]
    assert kalshi_module._fetch_budget((), 4) == ()
    assert kalshi_module._fetch_budget(rows, 3) == kalshi_module._fetch_budget(rows, 3)


# --------------------------------------------------------------------------------------------------
# The descending walk floor of ruling R100
# --------------------------------------------------------------------------------------------------
#: Older than every floor of the window, so a page of these ends the walk.
ANCIENT_TICKER: Final = "KXFLOOR-24JAN02-T1"
#: Closed before the window but inside the settlement slack, so its page may not end the walk.
SLACK_TICKER: Final = "KXFLOOR-25AUG20-T1"
#: The one row of the window, on the page after the floor page.
FLOOR_WINDOW_TICKER: Final = "KXFLOOR-25SEP20-T1"
FLOOR_SERIES: Final = "KXFLOOR"


def _floor_row(ticker: str, *, opened: str, settled: str) -> dict[str, object]:
    row = _eastern_row(ticker, opened=opened, settled=settled, volume_fp="500.00")
    row["series_ticker"] = FLOOR_SERIES
    row["event_ticker"] = ticker.rsplit("-", 1)[0]
    return row


class _FloorTransport(httpx.BaseTransport):
    """A settled listing that answers in descending close order and never runs out of pages.

    This is the shape ruling R100 measured: ``/historical/markets`` ignores ``min_close_ts`` and
    ``max_close_ts``, so the only bound on its walk is the client's own. Every page carries a cursor,
    so a walk that does not stop itself follows the cursor to the page cap and raises rather than
    reaching the window.
    """

    def __init__(self, pages: Sequence[Sequence[dict[str, object]]]) -> None:
        self.pages = list(pages)
        self.listing_calls = 0
        self.candlestick_calls = 0

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        params = {key: value for key, value in request.url.params.multi_items()}
        payload: dict[str, object]
        if path.endswith("/historical/cutoff"):
            payload = {"market_settled_ts": CUTOFF_MS // 1_000}
        elif path.endswith("/markets/trades"):
            payload = {"trades": [], "cursor": ""}
        elif path.endswith("/candlesticks"):
            self.candlestick_calls += 1
            payload = {"candlesticks": []}
        elif path.endswith("/historical/markets") or path.endswith("/markets"):
            self.listing_calls += 1
            cursor = params.get("cursor", "")
            index = int(cursor[1:]) if cursor.startswith("p") else 0
            markets = list(self.pages[index]) if index < len(self.pages) else []
            # Never an empty cursor: the provider always claims one more page.
            payload = {"markets": markets, "cursor": f"p{index + 1}"}
        else:  # pragma: no cover - a route this transport is not asked for
            return httpx.Response(404, json={"error": {"message": path}})
        return httpx.Response(200, json=payload, headers={"content-type": "application/json"})


def _import_floor(
    tmp_path: Path, pages: Sequence[Sequence[dict[str, object]]]
) -> tuple[tuple[Market, ...], _FloorTransport]:
    transport = _FloorTransport(pages)
    client = _client(tmp_path, transport)
    try:
        markets = import_kalshi(
            client=client,
            window_start_ms=WINDOW_START_MS,
            window_end_ms=WINDOW_END_MS,
            freeze_ms=FREEZE_MS,
            series_allow_list=(FLOOR_SERIES,),
        )
    finally:
        client.close()
    return markets, transport


def test_the_settled_walk_stops_at_the_window_floor_instead_of_reaching_the_page_cap(
    tmp_path: Path,
) -> None:
    """A page entirely older than the floor ends the walk (ruling R100).

    Both settled listings answer in descending close order and the historical one honours neither time
    filter, so a page whose newest row already closed before the floor means every later page is older
    still. Without the stop the walk follows the cursor to ``KALSHI_MARKETS_MAX_PAGES`` and raises
    ``MalformedResponseError``, which killed the whole Kalshi provider rather than one market.
    """
    ancient = [_floor_row(ANCIENT_TICKER, opened="2023-12-01T12:00:00Z", settled="2024-01-02T18:00:00Z")]
    markets, transport = _import_floor(tmp_path, [ancient, ancient, ancient])
    assert markets == ()
    # One page per listing: the historical one and the live settled one, each stopped on its first page.
    assert transport.listing_calls == 2
    assert transport.listing_calls < KALSHI_MARKETS_MAX_PAGES
    assert transport.candlestick_calls == 0, "no tape is bought for a row outside the window"


def test_a_page_inside_the_settlement_slack_does_not_end_the_walk(tmp_path: Path) -> None:
    """The floor is the window start minus the settlement slack, not the window start itself.

    A Kalshi market can close before it settles, so a row that closed just before the window can still
    have settled inside it. The floor therefore sits ``KALSHI_SETTLEMENT_SLACK_MS`` below the window
    start, and a page whose newest close falls in that band must be walked past, or the first weeks of
    the window are unreachable.
    """
    slack_close_ms = ms("2025-08-20T18:00:00+00:00")
    assert WINDOW_START_MS - KALSHI_SETTLEMENT_SLACK_MS < slack_close_ms < WINDOW_START_MS, (
        "the row closed before the window and inside the settlement slack"
    )
    slack_page = [_floor_row(SLACK_TICKER, opened="2025-08-01T12:00:00Z", settled="2025-08-20T18:00:00Z")]
    window_page = [
        _floor_row(FLOOR_WINDOW_TICKER, opened="2025-09-08T12:00:00Z", settled="2025-09-20T18:00:00Z")
    ]
    ancient = [_floor_row(ANCIENT_TICKER, opened="2023-12-01T12:00:00Z", settled="2024-01-02T18:00:00Z")]
    markets, transport = _import_floor(tmp_path, [slack_page, window_page, ancient])
    assert [market.provider_id for market in markets] == [FLOOR_WINDOW_TICKER]
    # Three pages of the historical listing (the third ends it) and three of the settled one.
    assert transport.listing_calls == 6
