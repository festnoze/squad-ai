"""D3: the Manifold importer and the Manifold comment fetcher, against recorded responses.

Every test here is offline and deterministic. The fixtures under ``tests/fixtures/d3/`` are verbatim
response bodies recorded from ``api.manifold.markets`` on 2026-09-07 (``provenance.json`` names the URL of
each one and the two synthetic derivations), with one edit: the em-dash character is replaced by a hyphen,
because the house rule forbids U+2014 in produced content and ``tests/test_architecture.py`` scans this
directory. The one test that touches the network is guarded by ``PMX_LIVE`` and skipped otherwise.

The stub is not a hand-written double of ``HttpClient``: it is the real ``HttpClient`` driven through an
``httpx.MockTransport`` whose handler re-implements the venue's own paging semantics (``offset`` on
``/v0/search-markets``, ``before=<betId>`` on ``/v0/bets``, ``page`` on ``/v0/comments``) over the recorded
rows. So the throttle, the cache, the retry policy and the URL building are exercised for real, the
importer's paging loops are exercised against the same contract the venue publishes, and a request the
importer should never have made shows up as a recorded call rather than as a silent success.

What the tests pin, in the order of D3's done-when: a fixture import writes a valid v2 market (schema and
strict-model validated, floats refused); every bar close equals the ``probAfter`` of the last print of that
bar and a trade-free bar carries the previous close; every comment carries a ``published_at_ms`` at most
the market's ``resolved_at_ms``, which the primary fixture proves by containing one written 15 minutes
after settlement.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator, Mapping, Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest

from pmx.data.importers import manifold as manifold_module
from pmx.data.importers._http import HttpClient, build_user_agent, evenly_spaced
from pmx.data.importers.manifold import (
    BETS_PAGE_LIMIT,
    EXCLUDE_FREEZE,
    EXCLUDE_NOT_BINARY,
    EXCLUDE_NOT_MANA,
    EXCLUDE_RESOLUTION,
    EXCLUDE_TOO_SHORT,
    EXCLUDE_UNRESOLVED,
    EXCLUDE_WINDOW,
    MANIFOLD_BASE_URL,
    MANIFOLD_CATEGORY_BY_GROUP_SLUG,
    MANIFOLD_CURRENCY,
    MANIFOLD_FEE_SCHEDULE_ID,
    MANIFOLD_INTERVAL_MIN,
    MANIFOLD_MIN_INTERVAL_MS,
    RESOLUTION_SOURCE_CREATOR,
    SEARCH_PAGE_LIMIT,
    SEARCH_RESOLVED_PAGE_LIMIT,
    build_market,
    category_of,
    classify_lite_market,
    close_at_ms_of,
    import_manifold,
    is_self_resolved,
    list_open_manifold,
    market_id_of,
    parse_body,
    price_bp_from_prob,
    size_milli_from_amount,
    tags_of,
    trades_from_bets,
)
from pmx.data.news.manifold_comments import (
    COMMENTS_PAGE_LIMIT,
    FULL_MATCH_PERMILLE,
    author_key_of,
    build_item,
    fetch_comments,
    flatten_prosemirror,
    is_readable,
    news_id_of,
    source_urls,
    wikipedia_titles,
)
from pmx.data.schema import market_from_payload, news_item_from_payload
from pmx.errors import MalformedResponseError, ProviderError
from pmx.types import (
    CATEGORIES,
    MS_PER_DAY,
    PPM_ONE,
    SAFETY_LAG_MS_DEFAULT,
    Market,
    NewsItem,
    Trade,
    bar_of,
    bp_from_ppm,
    day_key,
    interval_ms,
    round_half_up,
    round_half_up_decimal,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "d3"

#: The recorded markets. ``PRIMARY`` resolved YES with 253 bets and 8 comments over 22 days of life;
#: ``SECONDARY`` resolved NO with 155 bets over 69 days. Both were resolved by their own creator, which on
#: this venue is the normal case.
PRIMARY = "g52tSltgqh"
SECONDARY = "hZh0pEPsnn"
#: In the recorded search page, in the venue's descending resolve order: two CANCEL, one MKT, and one YES
#: that only the narrow window excludes.
CANCELLED = ("6y05CL2Q0O", "UZQZlE0EEy")
RESOLVED_TO_MARKET = "82OAcscIUs"
BELOW_NARROW_WINDOW = "QyRSUc8qRl"
#: The derived edge rows: a sweepstakes contract, a market resolved five days before its published close,
#: and a market whose whole life is one second.
CASH_TOKEN = "cashOnlyTest1"
EARLY_RESOLUTION = "zZearly00001"
TOO_SHORT = "tooShortTest1"
#: Two recorded comments of ``PRIMARY`` that are not a sentence: one is a single image, one is mostly a
#: mention of another market.
IMAGE_ONLY_COMMENT = "b2t03xmr6x"
CONTRACT_MENTION_COMMENT = "gen0gcvxwt"
#: The recorded open markets, ascending close date. ``OPEN_NO_TAPE`` has never been bet on.
OPEN_WITH_TAPE = ("8qcRzthOO8", "PUySSCQEcu", "2RulS0zPUO")
OPEN_NO_TAPE = "p9n92gQlPy"

#: 2026-09-08T00:00:00Z: the day after the last recorded settlement, so every recorded market resolved
#: strictly before the freeze.
FREEZE_MS = 1_788_825_600_000
WINDOW_END_MS = FREEZE_MS - MS_PER_DAY
#: The default window opens *between* two recorded resolutions, so the descending walk stops inside the
#: recorded page: the rows below it are deliberately without a tape fixture, which is what proves the walk
#: stopped rather than merely skipped them.
WINDOW_START_MS = 1_788_700_000_000
#: The contract's own twelve-month window (section 7.4). It reaches the rows this fixture set does not
#: cover, so an import over it must fail on the missing tape rather than stop early.
WIDE_WINDOW_START_MS = FREEZE_MS - 365 * MS_PER_DAY
#: 2026-09-07T00:00:00Z, a bar boundary, for the open-market listing.
NOW_MS = 1_788_739_200_000


# --------------------------------------------------------------------------------------------------
# The recorded venue
# --------------------------------------------------------------------------------------------------
def load_fixture(name: str, *, exact: bool = True) -> Any:
    """A recorded body.

    ``exact`` parses every number as a ``Decimal``, which is how the importer reads one and how a test
    computes an expected price without a float. The stub loads the same file *without* it, because it has
    to hand the body back as JSON and ``json.dumps`` cannot write a ``Decimal`` as a number; a test below
    pins that the round trip through the stub changes no digit.
    """
    text = (FIXTURES / name).read_text(encoding="utf-8")
    return json.loads(text, parse_float=Decimal) if exact else json.loads(text)


def rows_of(name: str, *, exact: bool = True) -> list[dict[str, Any]]:
    payload = load_fixture(name, exact=exact)
    assert isinstance(payload, list)
    return [row for row in payload if isinstance(row, dict)]


def row_of(name: str, *, exact: bool = True) -> dict[str, Any]:
    payload = load_fixture(name, exact=exact)
    assert isinstance(payload, dict)
    return payload


def lite_of(market_id: str, *, name: str = "search_markets.json") -> dict[str, Any]:
    for row in rows_of(name):
        if row.get("id") == market_id:
            return row
    raise AssertionError(f"{market_id} is not in {name}")


class RecordedManifold:
    """The venue's paging semantics over recorded rows, as an ``httpx`` transport handler.

    ``search_by_filter`` maps the ``filter`` query parameter to a list of lite markets; ``full`` and
    ``bets`` and ``comments`` map a contract id to its recorded payload. A path or an id with no fixture
    answers ``404``, which is what makes "the importer must not have asked for this" a real assertion:
    :attr:`calls` records every request that reached the transport.
    """

    def __init__(
        self,
        *,
        search_by_filter: Mapping[str, Sequence[Mapping[str, Any]]],
        with_tapes: Sequence[str] = (),
        with_comments: Sequence[str] = (),
    ) -> None:
        self.search_by_filter = dict(search_by_filter)
        self.full: dict[str, Mapping[str, Any]] = {
            market_id: row_of(f"market_{market_id}.json", exact=False) for market_id in with_tapes
        }
        self.bets: dict[str, list[dict[str, Any]]] = {
            market_id: rows_of(f"bets_{market_id}.json", exact=False) for market_id in with_tapes
        }
        self.comments: dict[str, list[dict[str, Any]]] = {
            market_id: rows_of(f"comments_{market_id}.json", exact=False) for market_id in with_comments
        }
        self.calls: list[tuple[str, dict[str, str]]] = []

    # -- the transport ---------------------------------------------------------------------------
    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        params = {key: value for key, value in request.url.params.items()}
        self.calls.append((path, params))
        if path == "/v0/search-markets":
            return self._search(params)
        if path.startswith("/v0/market/"):
            return self._market(path.rsplit("/", 1)[-1])
        if path == "/v0/bets":
            return self._bets(params)
        if path == "/v0/comments":
            return self._comments(params)
        return httpx.Response(404, json={"message": f"no route {path}"})

    def paths(self) -> list[str]:
        return [path for path, _ in self.calls]

    def asked_for(self, market_id: str) -> bool:
        """Did any request name this contract, on any endpoint?"""
        return any(
            market_id in path or market_id in params.get("contractId", "") for path, params in self.calls
        )

    # -- the endpoints ---------------------------------------------------------------------------
    def _search(self, params: Mapping[str, str]) -> httpx.Response:
        """The venue's two paging modes, and its refusal above ``offset = 1000``.

        ``beforeTime`` is a bound on ``createdTime`` and orders by creation descending, which is what the
        resolved walk uses; ``offset`` is the open listing's mode and is refused above a thousand exactly
        as the venue refuses it (measured on 2026-09-08: ``400 offset must be <= 1000``).
        """
        rows = list(self.search_by_filter.get(params["filter"], ()))
        limit = int(params["limit"])
        if "beforeTime" in params:
            before = int(params["beforeTime"])
            newest_first = sorted(
                (row for row in rows if int(row["createdTime"]) < before),
                key=lambda row: (-int(row["createdTime"]), str(row["id"])),
            )
            return _json_response(newest_first[:limit])
        offset = int(params.get("offset", "0"))
        if offset > 1_000:
            return httpx.Response(400, json={"message": "offset must be <= 1000."})
        # The offset mode answers in the order the fixture records, which is the order the venue's own
        # ``sort`` produced when it was recorded.
        return _json_response(list(rows[offset : offset + limit]))

    def _market(self, market_id: str) -> httpx.Response:
        payload = self.full.get(market_id)
        if payload is None:
            return httpx.Response(404, json={"message": f"no market {market_id}"})
        return _json_response(payload)

    def _bets(self, params: Mapping[str, str]) -> httpx.Response:
        rows = self.bets.get(params["contractId"])
        if rows is None:
            return httpx.Response(404, json={"message": "no bets"})
        start = 0
        before = params.get("before")
        if before is not None:
            start = next(index for index, row in enumerate(rows) if row["betId"] == before) + 1
        limit = int(params["limit"])
        return _json_response(rows[start : start + limit])

    def _comments(self, params: Mapping[str, str]) -> httpx.Response:
        rows = self.comments.get(params["contractId"])
        if rows is None:
            return httpx.Response(404, json={"message": "no comments"})
        limit = int(params["limit"])
        page = int(params.get("page", "0"))
        return _json_response(rows[page * limit : (page + 1) * limit])


def _json_response(payload: object) -> httpx.Response:
    """The body as the venue sends one: numbers as numbers, so the importer parses digits and not text."""
    return httpx.Response(
        200,
        content=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )


def client_for(api: RecordedManifold, cache_dir: Path) -> HttpClient:
    """The real client, with the throttle's clock and sleeper injected so a test costs no seconds."""
    ticks = iter(range(1, 10_000_000))
    return HttpClient(
        base_url=MANIFOLD_BASE_URL,
        user_agent="pmx-research/test (contact: tests@pmx.local)",
        min_interval_ms=MANIFOLD_MIN_INTERVAL_MS,
        cache_dir=cache_dir,
        transport=httpx.MockTransport(api),
        clock=lambda: next(ticks) * 1_000_000_000,
        sleeper=lambda _ms: None,
    )


@pytest.fixture
def resolved_api() -> RecordedManifold:
    return RecordedManifold(
        search_by_filter={"resolved": rows_of("search_markets.json", exact=False)},
        with_tapes=(PRIMARY, SECONDARY),
        with_comments=(PRIMARY, SECONDARY),
    )


@pytest.fixture
def resolved_client(resolved_api: RecordedManifold, tmp_path: Path) -> Iterator[HttpClient]:
    client = client_for(resolved_api, tmp_path / "cache")
    try:
        yield client
    finally:
        client.close()


def imported(
    client: HttpClient,
    *,
    window_start_ms: int = WINDOW_START_MS,
    window_end_ms: int = WINDOW_END_MS,
    freeze_ms: int = FREEZE_MS,
    limit: int | None = None,
) -> tuple[Market, ...]:
    return import_manifold(
        client=client,
        window_start_ms=window_start_ms,
        window_end_ms=window_end_ms,
        freeze_ms=freeze_ms,
        limit=limit,
    )


# --------------------------------------------------------------------------------------------------
# A fixture-backed import writes a valid v2 market (done-when 1)
# --------------------------------------------------------------------------------------------------
def test_import_returns_the_two_valid_candidates_in_canonical_order(resolved_client: HttpClient) -> None:
    markets = imported(resolved_client)
    assert [market.id for market in markets] == [market_id_of(SECONDARY), market_id_of(PRIMARY)]
    assert [market.resolved_at_ms for market in markets] == sorted(m.resolved_at_ms for m in markets)


def test_every_imported_market_validates_against_market_v2(resolved_client: HttpClient) -> None:
    """Schema, then the strict pydantic model: the pass that refuses a float in an integer field."""
    for market in imported(resolved_client):
        reloaded = market_from_payload(market.to_dict(), where=market.id)
        assert reloaded == market


def test_the_market_metadata_is_the_venue_own(resolved_client: HttpClient) -> None:
    market = _market(imported(resolved_client), PRIMARY)
    lite = lite_of(PRIMARY)
    assert market.provider == "manifold"
    assert market.provider_id == PRIMARY
    assert market.currency == MANIFOLD_CURRENCY
    assert market.source == "imported"
    assert market.interval_min == MANIFOLD_INTERVAL_MIN
    assert market.fee_schedule_id == MANIFOLD_FEE_SCHEDULE_ID
    assert market.url == lite["url"]
    assert market.question == lite["question"]
    assert market.resolution == 1
    assert market.created_at_ms == lite["createdTime"]
    assert market.resolved_at_ms == lite["resolutionTime"]
    assert market.hardness_tags == (), "the builder computes the tags, not the importer (7.12)"


def test_the_no_resolution_market_resolves_to_zero(resolved_client: HttpClient) -> None:
    assert _market(imported(resolved_client), SECONDARY).resolution == 0


def test_no_float_reaches_a_market_field(resolved_client: HttpClient) -> None:
    """The whole point of parsing with ``Decimal``: nothing in the payload is a float or a Decimal."""
    for market in imported(resolved_client):
        offenders = [
            f"{pointer}={value!r}"
            for pointer, value in _walk(market.to_dict())
            if isinstance(value, float | Decimal)
        ]
        assert offenders == []


def test_description_and_group_metadata_come_from_the_full_market(resolved_client: HttpClient) -> None:
    market = _market(imported(resolved_client), PRIMARY)
    full = row_of(f"market_{PRIMARY}.json")
    assert market.description == str(full["textDescription"]).strip()
    assert market.description.startswith("This market resolves YES if")
    assert market.event_key == full["groupSlugs"][0]
    assert market.tags == tuple(sorted(full["groupSlugs"]))
    assert market.category == "politics", "the elections group is the first row of the table that matches"


def test_the_second_market_takes_its_category_from_a_later_table_row(resolved_client: HttpClient) -> None:
    market = _market(imported(resolved_client), SECONDARY)
    assert "wars" in market.tags
    assert market.category == "world"


# --------------------------------------------------------------------------------------------------
# The tape: bars, trades, quality (done-when 1, section 5.2)
# --------------------------------------------------------------------------------------------------
def expected_closes(market_id: str) -> dict[int, int]:
    """The close of every traded bar, recomputed from the recorded bets independently of the importer.

    The rule under test is the contract's: the bar's close is the ``probAfter`` of the last print inside
    it, in the venue's chronological order.
    """
    lite = lite_of(market_id)
    created, resolved = int(lite["createdTime"]), int(lite["resolutionTime"])
    closes: dict[int, int] = {}
    for bet in reversed(rows_of(f"bets_{market_id}.json")):  # recorded newest first
        if bet.get("isRedemption") is True or bet.get("isCancelled") is True:
            continue
        t_ms = int(bet["createdTime"])
        if not created <= t_ms <= resolved:
            continue
        if round_half_up_decimal(abs(Decimal(bet["amount"])) * 1_000) < 1:
            continue
        closes[bar_of(t_ms, MANIFOLD_INTERVAL_MIN)] = bp_from_ppm(
            round_half_up_decimal(Decimal(bet["probAfter"]) * PPM_ONE)
        )
    return closes


@pytest.mark.parametrize("market_id", [PRIMARY, SECONDARY])
def test_bar_closes_match_the_bets_prob_after_at_each_bar_boundary(
    resolved_client: HttpClient, market_id: str
) -> None:
    market = _market(imported(resolved_client), market_id)
    closes = expected_closes(market_id)
    assert closes, "the fixture must carry prints, or this test would pass on an empty tape"
    traded = [bar for bar in market.bars if bar.n_trades > 0]
    assert len(traded) == len(closes)
    for bar in traded:
        assert bar.close_bp == closes[bar.t_ms], f"bar {bar.t_ms} of {market_id}"


@pytest.mark.parametrize("market_id", [PRIMARY, SECONDARY])
def test_a_trade_free_bar_carries_the_previous_close(resolved_client: HttpClient, market_id: str) -> None:
    market = _market(imported(resolved_client), market_id)
    quiet = [
        (index, bar) for index, bar in enumerate(market.bars) if bar.n_trades == 0 and bar.volume_milli == 0
    ]
    assert quiet, "the fixture must carry a quiet bar, or this test would assert nothing"
    for index, bar in quiet:
        carried = market.bars[index - 1].close_bp if index else market.first_price_bp
        assert (bar.open_bp, bar.high_bp, bar.low_bp, bar.close_bp, bar.vwap_bp) == (carried,) * 5


@pytest.mark.parametrize("market_id", [PRIMARY, SECONDARY])
def test_bars_are_dense_on_the_daily_grid_from_creation_to_settlement(
    resolved_client: HttpClient, market_id: str
) -> None:
    market = _market(imported(resolved_client), market_id)
    step = interval_ms(MANIFOLD_INTERVAL_MIN)
    first = bar_of(market.created_at_ms, MANIFOLD_INTERVAL_MIN)
    last = bar_of(market.resolved_at_ms, MANIFOLD_INTERVAL_MIN)
    assert [bar.t_ms for bar in market.bars] == list(range(first, last + step, step))
    assert all(bar.t_ms % MS_PER_DAY == 0 for bar in market.bars)


@pytest.mark.parametrize("market_id", [PRIMARY, SECONDARY])
def test_every_bar_is_internally_consistent(resolved_client: HttpClient, market_id: str) -> None:
    market = _market(imported(resolved_client), market_id)
    for bar in market.bars:
        assert 1 <= bar.low_bp <= bar.open_bp <= bar.high_bp <= 9_999
        assert bar.low_bp <= bar.close_bp <= bar.high_bp
        assert bar.low_bp <= bar.vwap_bp <= bar.high_bp
        assert (bar.yes_bid_bp, bar.yes_ask_bp, bar.open_interest) == (None, None, None)


def test_the_vwap_is_the_integer_weighted_mean_of_the_bar_prints(resolved_client: HttpClient) -> None:
    market = _market(imported(resolved_client), PRIMARY)
    by_bar: dict[int, list[Trade]] = {}
    for trade in market.trades:
        by_bar.setdefault(bar_of(trade.t_ms, MANIFOLD_INTERVAL_MIN), []).append(trade)
    busiest = max(by_bar, key=lambda t_ms: len(by_bar[t_ms]))
    assert len(by_bar[busiest]) > 1
    inside = by_bar[busiest]
    volume = sum(trade.size_milli for trade in inside)
    expected = round_half_up(sum(trade.price_bp * trade.size_milli for trade in inside), volume)
    bar = next(bar for bar in market.bars if bar.t_ms == busiest)
    assert bar.vwap_bp == expected
    assert bar.volume_milli == volume
    assert bar.n_trades == len(inside)


def test_trades_are_sorted_in_the_canonical_order(resolved_client: HttpClient) -> None:
    markets = imported(resolved_client)
    assert len(markets) == 2
    for market in markets:
        assert market.trades, "a market with no print would pass every line below"
        keys = [(t.t_ms, t.price_bp, t.size_milli, t.side) for t in market.trades]
        assert keys == sorted(keys)
        assert all(trade.size_milli >= 1 for trade in market.trades)
        assert all(1 <= trade.price_bp <= 9_999 for trade in market.trades)
        assert all(trade.side in ("yes", "no", "unknown") for trade in market.trades)


def test_redemptions_and_cancelled_orders_are_not_prints() -> None:
    """A redemption moves no mana at a price: counting it would fabricate volume and a zero-move print."""
    lite = lite_of(PRIMARY)
    bets = list(reversed(rows_of(f"bets_{PRIMARY}.json")))
    dropped = [bet for bet in bets if bet.get("isRedemption") is True or bet.get("isCancelled") is True]
    assert len(dropped) >= 2, "the fixture must contain refused bets for this test to mean anything"
    trades = trades_from_bets(bets, start_ms=int(lite["createdTime"]), end_ms=int(lite["resolutionTime"]))
    tiny = [
        bet
        for bet in bets
        if bet not in dropped and round_half_up_decimal(abs(Decimal(bet["amount"])) * 1_000) < 1
    ]
    assert len(trades) == len(bets) - len(dropped) - len(tiny)


def test_the_first_price_is_the_probability_before_the_first_bet(resolved_client: HttpClient) -> None:
    market = _market(imported(resolved_client), PRIMARY)
    oldest = rows_of(f"bets_{PRIMARY}.json")[-1]
    assert market.first_price_bp == bp_from_ppm(round_half_up_decimal(Decimal(oldest["probBefore"]) * PPM_ONE))
    assert market.final_price_bp == market.bars[-1].close_bp


def test_the_quality_block_counts_the_tape_that_was_kept(resolved_client: HttpClient) -> None:
    market = _market(imported(resolved_client), PRIMARY)
    lite = lite_of(PRIMARY)
    assert market.quality.n_trades == len(market.trades)
    assert market.quality.unique_bettors == lite["uniqueBettorCount"]
    assert market.quality.volume_milli_total == sum(trade.size_milli for trade in market.trades)
    assert market.quality.traded_bars == sum(1 for bar in market.bars if bar.n_trades > 0)
    assert market.quality.life_days == (market.resolved_at_ms - market.created_at_ms) // MS_PER_DAY
    assert 0 < market.quality.traded_bars <= len(market.bars)


# --------------------------------------------------------------------------------------------------
# Refusals, and the requests they must not cost
# --------------------------------------------------------------------------------------------------
def test_a_resolution_that_is_not_yes_or_no_is_refused_before_any_tape_is_fetched(
    resolved_api: RecordedManifold, resolved_client: HttpClient
) -> None:
    imported_ids = {market.provider_id for market in imported(resolved_client)}
    for market_id in (*CANCELLED, RESOLVED_TO_MARKET):
        assert market_id not in imported_ids
        assert not resolved_api.asked_for(market_id), "a refusal must cost no request"


def test_the_exclusion_reasons_name_the_filter() -> None:
    window = {
        "window_start_ms": WIDE_WINDOW_START_MS,
        "window_end_ms": WINDOW_END_MS,
        "freeze_ms": FREEZE_MS,
    }
    assert classify_lite_market(lite_of(PRIMARY), **window) is None
    assert classify_lite_market(lite_of(RESOLVED_TO_MARKET), **window) == EXCLUDE_RESOLUTION
    assert classify_lite_market(lite_of(CANCELLED[0]), **window) == EXCLUDE_RESOLUTION
    edge = "search_markets_edge.json"
    assert classify_lite_market(lite_of(CASH_TOKEN, name=edge), **window) == EXCLUDE_NOT_MANA
    assert classify_lite_market(lite_of(TOO_SHORT, name=edge), **window) == EXCLUDE_TOO_SHORT
    assert classify_lite_market(lite_of(EARLY_RESOLUTION, name=edge), **window) is None
    assert (
        classify_lite_market(lite_of(PRIMARY), **{**window, "window_end_ms": WINDOW_START_MS})
        == EXCLUDE_WINDOW
    )
    assert (
        classify_lite_market(lite_of(PRIMARY), **{**window, "freeze_ms": WINDOW_START_MS}) == EXCLUDE_FREEZE
    ), "the freeze is checked before the window: a leak is not a filter"
    assert classify_lite_market({**lite_of(PRIMARY), "isResolved": False}, **window) == EXCLUDE_UNRESOLVED
    assert classify_lite_market({**lite_of(PRIMARY), "resolutionTime": None}, **window) == EXCLUDE_UNRESOLVED
    assert classify_lite_market({"outcomeType": "MULTIPLE_CHOICE"}, **window) == EXCLUDE_NOT_BINARY


def test_the_window_excludes_the_row_below_it_and_a_wider_window_reaches_it(
    resolved_api: RecordedManifold, resolved_client: HttpClient
) -> None:
    """The row below the window resolves YES and is in the page, so only the window can exclude it.

    The second half is the proof that the exclusion is the window's and not the page's: widened to the
    contract's twelve months, the same walk reaches that row and asks for a tape this fixture set does not
    record, which the stub answers with a 404. The walk itself is bounded by creation, not by resolution
    (the venue refuses ``offset > 1000``), so the row is read from the listing either way and it is
    ``classify_lite_market`` that refuses it.
    """
    assert lite_of(BELOW_NARROW_WINDOW)["resolution"] == "YES"
    markets = imported(resolved_client)
    assert [market.provider_id for market in markets] == [SECONDARY, PRIMARY]
    assert not resolved_api.asked_for(BELOW_NARROW_WINDOW)
    with pytest.raises(ProviderError):
        imported(resolved_client, window_start_ms=WIDE_WINDOW_START_MS)
    assert resolved_api.asked_for(BELOW_NARROW_WINDOW)


def test_a_market_resolved_at_the_freeze_is_refused(
    resolved_api: RecordedManifold, resolved_client: HttpClient
) -> None:
    """The freeze bound is strict: a freeze set at the newest settlement excludes it and keeps the next."""
    markets = imported(resolved_client, freeze_ms=int(lite_of(PRIMARY)["resolutionTime"]), limit=1)
    assert [market.provider_id for market in markets] == [SECONDARY]
    assert not resolved_api.asked_for(PRIMARY)


def test_the_resolved_walk_pages_by_creation_and_never_by_offset(
    resolved_api: RecordedManifold, resolved_client: HttpClient
) -> None:
    """The walk the venue's paging limit forced (measured on 2026-09-08).

    ``/v0/search-markets`` refuses ``offset > 1000``, so the resolution-ordered listing bottoms out at
    about forty-five days and a twelve-month window got a ``400`` on its eleventh page. The walk pages by
    ``beforeTime``, which bounds ``createdTime`` and has no depth limit at all.
    """
    markets = imported(resolved_client)
    assert [market.provider_id for market in markets] == [SECONDARY, PRIMARY]
    searches = [params for path, params in resolved_api.calls if path == "/v0/search-markets"]
    assert searches, "the walk asked for at least one page"
    assert all(params["sort"] == "newest" for params in searches)
    assert all("offset" not in params for params in searches)
    assert all(params["filter"] == "resolved" for params in searches)
    assert int(searches[0]["limit"]) == SEARCH_RESOLVED_PAGE_LIMIT
    assert len(searches) == 1, "a page shorter than the page size is the last page"


def test_each_page_of_the_resolved_walk_reaches_further_back_than_the_last(
    resolved_api: RecordedManifold, resolved_client: HttpClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Paging is by the oldest creation of the page, so a deep walk is bounded and terminates.

    The page size is dropped to two so that six recorded rows take four pages; the real walk reads a
    thousand rows a page and covers a twelve-month window in twelve of them.
    """
    monkeypatch.setattr(manifold_module, "SEARCH_RESOLVED_PAGE_LIMIT", 2)
    markets = imported(resolved_client)
    assert [market.provider_id for market in markets] == [SECONDARY, PRIMARY]
    searches = [params for path, params in resolved_api.calls if path == "/v0/search-markets"]
    assert len(searches) > 1, "six rows at two a page is more than one page"
    assert "beforeTime" not in searches[0], "the first page has no bound"
    bounds = [int(params["beforeTime"]) for params in searches if "beforeTime" in params]
    assert bounds == sorted(bounds, reverse=True), "each page reaches further back than the last"
    assert len(set(bounds)) == len(bounds), "the same page is never asked for twice"


def test_a_market_created_before_the_floor_is_neither_staged_nor_fetched(
    resolved_api: RecordedManifold, resolved_client: HttpClient
) -> None:
    """The floor is the caller's, and it is what the builder's ``opened_early`` filter would enforce."""
    created = int(lite_of(BELOW_NARROW_WINDOW)["createdTime"])
    markets = import_manifold(
        client=resolved_client,
        window_start_ms=WIDE_WINDOW_START_MS,
        window_end_ms=WINDOW_END_MS,
        freeze_ms=FREEZE_MS,
        created_floor_ms=created + 1,
    )
    assert [market.provider_id for market in markets] == [SECONDARY, PRIMARY]
    assert not resolved_api.asked_for(BELOW_NARROW_WINDOW), "its tape was never fetched"
    # Without the floor the same wide window reaches it, and this fixture set records no tape for it.
    with pytest.raises(ProviderError):
        import_manifold(
            client=resolved_client,
            window_start_ms=WIDE_WINDOW_START_MS,
            window_end_ms=WINDOW_END_MS,
            freeze_ms=FREEZE_MS,
            created_floor_ms=created,
        )


def test_the_limit_is_a_fetch_budget_and_not_the_end_of_the_walk(
    resolved_api: RecordedManifold, resolved_client: HttpClient
) -> None:
    """The listing walk still covers the window; ``limit`` decides whose tape is fetched.

    The first real build read the newest 400 resolutions and staged thirteen days of a twelve-month
    window, because the import stopped as soon as it had built 400 markets. The walk now classifies the
    whole window first and the budget is spent at equal stride over what it found, so the markets that
    are staged are spread across the window rather than taken from its newest end.
    """
    markets = imported(resolved_client, limit=1)
    # The eligible rows are ordered by settlement before the budget is spent, so a budget of one buys
    # the oldest settlement of the window and not the newest resolution the listing happened to answer.
    assert [market.provider_id for market in markets] == [SECONDARY]
    assert not resolved_api.asked_for(PRIMARY), "a tape outside the budget is never fetched"
    assert evenly_spaced((SECONDARY, PRIMARY), 1) == (SECONDARY,)
    assert evenly_spaced((SECONDARY, PRIMARY), None) == (SECONDARY, PRIMARY)


def test_the_close_is_clamped_to_the_settlement(tmp_path: Path) -> None:
    """The derived row publishes a close five days after its settlement; ``tradable`` would trade it."""
    lite = lite_of(EARLY_RESOLUTION, name="search_markets_edge.json")
    assert lite["closeTime"] > lite["resolutionTime"]
    api = RecordedManifold(
        search_by_filter={"resolved": rows_of("search_markets_edge.json", exact=False)},
        with_tapes=(EARLY_RESOLUTION,),
    )
    client = client_for(api, tmp_path / "cache")
    try:
        markets = imported(client)
    finally:
        client.close()
    assert [market.provider_id for market in markets] == [EARLY_RESOLUTION]
    assert markets[0].close_at_ms == markets[0].resolved_at_ms
    assert close_at_ms_of(lite, resolved_at_ms=int(lite["resolutionTime"])) == lite["resolutionTime"]
    assert not api.asked_for(CASH_TOKEN)
    assert not api.asked_for(TOO_SHORT)


def test_a_market_with_no_print_is_refused() -> None:
    """``EXCLUDE_NO_TAPE``: the recorded contract nobody ever bet on is the venue's own empty tape."""
    assert rows_of(f"bets_{OPEN_NO_TAPE}.json") == [], "the fixture is the venue's answer for an unbet market"
    assert build_market(lite_of(PRIMARY), row_of(f"market_{PRIMARY}.json"), []) is None


def test_a_creator_resolved_market_is_kept_and_says_so(resolved_client: HttpClient) -> None:
    """CONTRACTS_V2 7.4 asks D6 to refuse these; every recorded Manifold market is one, so the importer
    records the fact in ``resolution_source`` and leaves the filter to the builder (reported issue)."""
    assert is_self_resolved(lite_of(PRIMARY))
    markets = imported(resolved_client)
    assert len(markets) == 2
    for market in markets:
        assert market.resolution_source == RESOLUTION_SOURCE_CREATOR


# --------------------------------------------------------------------------------------------------
# Paging: the same tape whatever the page size
# --------------------------------------------------------------------------------------------------
def test_paging_the_search_and_the_bets_changes_nothing_but_the_request_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def run(search_page: int, bets_page: int) -> tuple[list[dict[str, object]], int]:
        monkeypatch.setattr("pmx.data.importers.manifold.SEARCH_PAGE_LIMIT", search_page)
        monkeypatch.setattr("pmx.data.importers.manifold.BETS_PAGE_LIMIT", bets_page)
        api = RecordedManifold(
            search_by_filter={"resolved": rows_of("search_markets.json", exact=False)},
            with_tapes=(PRIMARY, SECONDARY),
        )
        client = client_for(api, tmp_path / f"cache-{search_page}-{bets_page}")
        try:
            markets = imported(client)
        finally:
            client.close()
        return [market.to_dict() for market in markets], len(api.calls)

    whole, few_requests = run(SEARCH_PAGE_LIMIT, BETS_PAGE_LIMIT)
    paged, many_requests = run(2, 25)
    assert whole == paged
    assert many_requests > few_requests
    assert whole, "an empty import would make this equality meaningless"


# --------------------------------------------------------------------------------------------------
# Conversions and refusals of the payload readers
# --------------------------------------------------------------------------------------------------
def test_the_price_conversion_is_the_contract_worked_example() -> None:
    assert price_bp_from_prob(Decimal("0.4187")) == 4_187
    assert price_bp_from_prob(Decimal("0")) == 1, "a tradable price is never zero"
    assert price_bp_from_prob(Decimal("1")) == 9_999
    assert price_bp_from_prob(Decimal("0.63275")) == 6_327
    assert price_bp_from_prob(Decimal("0.9791195212815591")) == 9_791


def test_the_size_conversion_drops_the_sign_and_rounds_half_up() -> None:
    assert size_milli_from_amount(Decimal("-2.5686155")) == 2_569
    assert size_milli_from_amount(Decimal("12.5")) == 12_500
    assert size_milli_from_amount(Decimal("0.0004")) == 0, "a sub-thousandth bet is not a print"


def test_a_body_that_is_not_json_is_a_malformed_response() -> None:
    with pytest.raises(MalformedResponseError):
        parse_body("<html>429</html>", what="bets")


def test_a_json_constant_is_refused() -> None:
    with pytest.raises(MalformedResponseError):
        parse_body('{"probAfter": NaN}', what="bets")


def test_a_float_never_becomes_a_price() -> None:
    """A body parsed by something other than ``parse_body`` must fail loudly, not round silently."""
    floats = json.loads('[{"createdTime": 1, "amount": 1.5, "probAfter": 0.5, "outcome": "YES"}]')
    with pytest.raises(MalformedResponseError):
        trades_from_bets(floats, start_ms=0, end_ms=10)
    exact = parse_body('[{"createdTime": 1, "amount": 1.5, "probAfter": 0.5, "outcome": "YES"}]', what="bets")
    assert isinstance(exact, list)
    assert trades_from_bets(exact, start_ms=0, end_ms=10) == (
        Trade(t_ms=1, price_bp=5_000, size_milli=1_500, side="yes"),
    )


def test_the_category_table_only_names_contract_categories() -> None:
    assert {category for _, category in MANIFOLD_CATEGORY_BY_GROUP_SLUG} <= set(CATEGORIES)
    assert category_of(["a-group-nobody-mapped"]) == "other"
    assert category_of([]) == "other"
    assert category_of(["mlb", "politics-default"]) == "politics", "the table's order decides"


def test_tags_keep_only_legal_slugs() -> None:
    assert tags_of(["german-politics", "BSW", "a" * 40, "ok_2"]) == ("german-politics", "ok_2")
    assert len(tags_of([f"tag-{index}" for index in range(30)])) == 16


def test_the_market_id_is_the_contract_id() -> None:
    assert market_id_of(PRIMARY) == f"manifold-{PRIMARY}"


# --------------------------------------------------------------------------------------------------
# Open markets for L1 (section 7.12)
# --------------------------------------------------------------------------------------------------
@pytest.fixture
def open_api() -> RecordedManifold:
    return RecordedManifold(
        search_by_filter={"open": rows_of("search_open_markets.json", exact=False)},
        with_tapes=(*OPEN_WITH_TAPE, OPEN_NO_TAPE),
    )


def test_open_markets_carry_a_tape_truncated_at_the_last_completed_bar(
    open_api: RecordedManifold, tmp_path: Path
) -> None:
    client = client_for(open_api, tmp_path / "cache")
    try:
        markets = list_open_manifold(client=client, now_ms=NOW_MS)
    finally:
        client.close()
    assert [market.provider_id for market in markets] == list(OPEN_WITH_TAPE)
    step = interval_ms(MANIFOLD_INTERVAL_MIN)
    for market in markets:
        assert market.close_at_ms > NOW_MS
        assert market.bars, "every recorded open market was created days ago"
        assert market.bars[-1].t_ms + step <= NOW_MS, "an incomplete bar is not as-of data"
        assert market.bars[0].t_ms == bar_of(market.created_at_ms, MANIFOLD_INTERVAL_MIN)
        assert market.last_price_bp == market.bars[-1].close_bp
        assert market.currency == MANIFOLD_CURRENCY
        assert market.fee_schedule_id == MANIFOLD_FEE_SCHEDULE_ID
        assert market.id == market_id_of(market.provider_id)


def test_an_open_market_never_carries_an_outcome(open_api: RecordedManifold, tmp_path: Path) -> None:
    client = client_for(open_api, tmp_path / "cache")
    try:
        markets = list_open_manifold(client=client, now_ms=NOW_MS, limit=1)
    finally:
        client.close()
    assert len(markets) == 1
    payload = markets[0].to_dict()
    for leak in ("resolution", "resolved_at_ms", "final_price_bp", "hardness_tags"):
        assert leak not in payload


def test_an_open_market_with_no_bet_is_skipped(open_api: RecordedManifold, tmp_path: Path) -> None:
    client = client_for(open_api, tmp_path / "cache")
    try:
        markets = list_open_manifold(client=client, now_ms=NOW_MS)
    finally:
        client.close()
    assert OPEN_NO_TAPE not in {market.provider_id for market in markets}
    assert not rows_of(f"bets_{OPEN_NO_TAPE}.json"), "the fixture is the venue's empty answer"


# --------------------------------------------------------------------------------------------------
# The comments (done-when 2)
# --------------------------------------------------------------------------------------------------
def fetched_comments(
    client: HttpClient,
    market: Market,
    *,
    safety_lag_ms: int = SAFETY_LAG_MS_DEFAULT,
    index_offset_by_day: Mapping[str, int] | None = None,
) -> tuple[NewsItem, ...]:
    return fetch_comments(
        client=client,
        market=market,
        safety_lag_ms=safety_lag_ms,
        index_offset_by_day=index_offset_by_day,
    )


def test_no_comment_is_published_after_the_market_resolved(resolved_client: HttpClient) -> None:
    """The primary fixture carries a comment written after settlement, so the cap is really tested."""
    market = _market(imported(resolved_client), PRIMARY)
    payloads = rows_of(f"comments_{PRIMARY}.json")
    late = [row for row in payloads if int(row["createdTime"]) > market.resolved_at_ms]
    assert late, "the fixture must contain a post-resolution comment"
    items = fetched_comments(resolved_client, market)
    assert items
    assert all(item.published_at_ms <= market.resolved_at_ms for item in items)
    kept = {item.url.rsplit("#", 1)[-1] for item in items}
    assert kept & {str(row["id"]) for row in late} == set()
    # The two the fetcher drops: the one written after settlement, and one that is a picture and no text.
    assert len(items) == len(payloads) - len(late) - 1
    assert IMAGE_ONLY_COMMENT not in kept


def test_every_comment_validates_against_news_v1(resolved_client: HttpClient) -> None:
    market = _market(imported(resolved_client), PRIMARY)
    items = fetched_comments(resolved_client, market)
    assert items
    for item in items:
        assert news_item_from_payload(item.to_dict(), where=item.news_id) == item
        assert item.source == "manifold_comment"
        assert item.kind == "comment"
        assert item.lang == "en"
        assert (item.revid, item.asof_day, item.section) == (None, None, None)


def test_the_items_are_oldest_first_and_their_ids_are_positional_inside_the_day(
    resolved_client: HttpClient,
) -> None:
    market = _market(imported(resolved_client), PRIMARY)
    items = fetched_comments(resolved_client, market)
    assert [item.published_at_ms for item in items] == sorted(item.published_at_ms for item in items)
    seen: dict[str, int] = {}
    for item in items:
        key = day_key(item.published_at_ms)
        assert item.news_id == news_id_of(item.published_at_ms, seen.get(key, 0))
        seen[key] = seen.get(key, 0) + 1
    assert len(set(item.news_id for item in items)) == len(items)


def test_the_day_index_can_be_offset_so_two_markets_do_not_collide(resolved_client: HttpClient) -> None:
    """A ``mfc`` id is positional inside its day (section 2), which two markets would collide on."""
    market = _market(imported(resolved_client), PRIMARY)
    plain = fetched_comments(resolved_client, market)
    day = day_key(plain[0].published_at_ms)
    shifted = fetched_comments(resolved_client, market, index_offset_by_day={day: 7})
    assert shifted[0].news_id == news_id_of(plain[0].published_at_ms, 7)
    assert not set(item.news_id for item in plain) & set(
        item.news_id for item in shifted if day_key(item.published_at_ms) == day
    )


def test_the_safety_lag_is_stamped_on_every_item(resolved_client: HttpClient) -> None:
    market = _market(imported(resolved_client), PRIMARY)
    lagged = fetched_comments(resolved_client, market)
    unlagged = fetched_comments(resolved_client, market, safety_lag_ms=0)
    assert len(lagged) == len(unlagged) >= 2
    for item in lagged:
        assert item.visible_from_ms == item.published_at_ms + SAFETY_LAG_MS_DEFAULT
    for item in unlagged:
        assert item.visible_from_ms == item.published_at_ms


def test_a_comment_is_linked_to_its_own_market_at_full_score(resolved_client: HttpClient) -> None:
    market = _market(imported(resolved_client), PRIMARY)
    items = fetched_comments(resolved_client, market)
    assert len(items) >= 2
    for item in items:
        assert item.match_ids == (market.id,)
        assert item.match_scores_permille == (FULL_MATCH_PERMILLE,)
        assert item.score_for(market.id) == FULL_MATCH_PERMILLE
        assert item.url.startswith(market.url)


def test_the_author_is_a_hash_and_never_the_venue_identifier(resolved_client: HttpClient) -> None:
    market = _market(imported(resolved_client), PRIMARY)
    by_id = {str(row["id"]): row for row in rows_of(f"comments_{PRIMARY}.json")}
    items = fetched_comments(resolved_client, market)
    assert items
    for item in items:
        payload = by_id[item.url.rsplit("#", 1)[-1]]
        user_id = str(payload["userId"])
        key = item.author_key
        assert key == author_key_of(user_id)
        assert key is not None
        assert len(key) == 16
        assert set(key) <= set("0123456789abcdef")
        rendered = json.dumps(item.to_dict(), ensure_ascii=False)
        assert user_id not in rendered, "the venue identifier is the secret, and it is hashed"
        assert str(payload["userUsername"]) != key
    assert author_key_of("abc") == author_key_of("abc") != author_key_of("abd")


def test_the_headline_is_the_first_line_of_the_comment(resolved_client: HttpClient) -> None:
    market = _market(imported(resolved_client), PRIMARY)
    for item in fetched_comments(resolved_client, market):
        assert item.headline
        assert len(item.headline) <= 300
        assert item.text.startswith(item.headline.removesuffix("..."))


def test_paging_the_comments_changes_nothing(
    resolved_client: HttpClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    market = _market(imported(resolved_client), PRIMARY)
    whole = [item.to_dict() for item in fetched_comments(resolved_client, market)]
    monkeypatch.setattr("pmx.data.news.manifold_comments.COMMENTS_PAGE_LIMIT", 2)
    paged = [item.to_dict() for item in fetched_comments(resolved_client, market)]
    assert len(whole) > 2
    for one, other in zip(whole, paged, strict=True):
        assert {key: value for key, value in one.items() if key != "fetched_at_ms"} == {
            key: value for key, value in other.items() if key != "fetched_at_ms"
        }
    assert COMMENTS_PAGE_LIMIT == 1_000, "the module constant is the venue's own cap"


def test_the_fetch_stamp_is_a_plausible_wall_clock(resolved_client: HttpClient) -> None:
    """``fetched_at_ms`` is the one clock read the data layer is allowed (section 7.3)."""
    market = _market(imported(resolved_client), PRIMARY)
    items = fetched_comments(resolved_client, market)
    stamps = {item.fetched_at_ms for item in items}
    assert len(stamps) == 1, "one fetch, one stamp"
    assert stamps.pop() > market.resolved_at_ms


def test_a_comment_that_is_only_a_picture_is_not_news() -> None:
    """``headline`` has a minimum length of one, and an image carries no sentence to read or to score."""
    payload = next(row for row in rows_of(f"comments_{PRIMARY}.json") if row["id"] == IMAGE_ONLY_COMMENT)
    text, links = flatten_prosemirror(payload["content"])
    assert text == ""
    assert links and links[0].startswith("https://firebasestorage.googleapis.com/")
    assert (
        build_item(
            payload,
            market_id="manifold-x",
            market_url="https://manifold.markets/x",
            index=0,
            safety_lag_ms=0,
            fetched_at_ms=0,
        )
        is None
    )


def test_a_comment_mentioning_another_market_keeps_its_path() -> None:
    payload = next(row for row in rows_of(f"comments_{PRIMARY}.json") if row["id"] == CONTRACT_MENTION_COMMENT)
    text, _links = flatten_prosemirror(payload["content"])
    assert text.startswith("Nice market. Also created a copy for")
    assert "/Primer/the-greens-receive-at-least-5-and-e" in text


def test_a_hidden_or_private_comment_is_not_news() -> None:
    assert is_readable({"visibility": "public"})
    assert is_readable({})
    assert not is_readable({"visibility": "unlisted"})
    assert not is_readable({"hidden": True})
    assert not is_readable({"deleted": True, "visibility": "public"})


# --------------------------------------------------------------------------------------------------
# The ProseMirror walker
# --------------------------------------------------------------------------------------------------
def test_flatten_walks_blocks_breaks_mentions_and_links() -> None:
    document = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "See "},
                    {
                        "type": "text",
                        "text": "the article",
                        "marks": [{"type": "link", "attrs": {"href": "https://en.wikipedia.org/wiki/Sahra_Wagenknecht"}}],
                    },
                    {"type": "hardBreak"},
                    {"type": "text", "text": "and "},
                    {"type": "mention", "attrs": {"label": "someone", "id": "u1"}},
                ],
            },
            {"type": "image", "attrs": {"src": "https://example.org/chart.png"}},
            {"type": "paragraph", "content": [{"type": "text", "text": "Second block."}]},
            {"type": "somethingNobodyMapped", "content": [{"type": "text", "text": " tail"}]},
        ],
    }
    text, links = flatten_prosemirror(document)
    assert text == "See the article\nand @someone\nSecond block.\n tail"
    assert links == (
        "https://en.wikipedia.org/wiki/Sahra_Wagenknecht",
        "https://example.org/chart.png",
    )


def test_flatten_tolerates_a_plain_string_and_junk() -> None:
    assert flatten_prosemirror("just text") == ("just text", ())
    assert flatten_prosemirror(None) == ("", ())
    assert flatten_prosemirror(17) == ("", ())
    assert flatten_prosemirror({"type": "paragraph"}) == ("", ())
    assert flatten_prosemirror([{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]) == ("ab", ())
    assert flatten_prosemirror({"type": "text", "text": "x", "marks": "not a list"}) == ("x", ())


def test_the_links_are_split_between_wikipedia_titles_and_source_urls() -> None:
    links = (
        "https://en.wikipedia.org/wiki/2026_Saxony-Anhalt_state_election#Results",
        "https://en.wikipedia.org/wiki/Sahra%20Wagenknecht",
        "https://www.reuters.com/world/europe/story",
    )
    assert wikipedia_titles(links) == ("2026 Saxony-Anhalt state election", "Sahra Wagenknecht")
    assert source_urls(links) == ("https://www.reuters.com/world/europe/story",)


def test_a_real_comment_flattens_to_its_own_paragraphs() -> None:
    payload = next(row for row in rows_of(f"comments_{PRIMARY}.json") if row["id"] == "4zeugos0lg7")
    text, links = flatten_prosemirror(payload["content"])
    assert links == ()
    assert text.startswith("5.2 percent.")
    assert text.endswith("The cycle continues.")
    assert "\n" in text


# --------------------------------------------------------------------------------------------------
# House rules on the fixtures themselves
# --------------------------------------------------------------------------------------------------
def test_every_fixture_is_named_in_the_provenance_file() -> None:
    provenance = row_of("provenance.json")
    declared = {str(entry["file"]) for entry in provenance["files"]}
    on_disk = {path.name for path in FIXTURES.glob("*.json")} - {"provenance.json"}
    assert on_disk <= declared, sorted(on_disk - declared)
    assert provenance["recorded_on"] == "2026-09-07"


def test_the_stub_round_trip_changes_no_digit() -> None:
    """The stub re-serialises what it loaded, so a shortest-repr float must give back the same digits.

    If this ever failed, every price in every offline test would be off by a bit, and the fixtures would
    have to be served verbatim instead of re-paged.
    """
    for name in (f"bets_{PRIMARY}.json", f"bets_{SECONDARY}.json", "search_markets.json"):
        served = parse_body(json.dumps(rows_of(name, exact=False), ensure_ascii=False), what=name)
        assert served == rows_of(name)


def test_no_fixture_carries_an_em_dash() -> None:
    """The sanitisation the provenance file declares, asserted rather than trusted."""
    for path in sorted(FIXTURES.glob("*.json")):
        assert chr(0x2014) not in path.read_text(encoding="utf-8"), path.name


# --------------------------------------------------------------------------------------------------
# The one live test
# --------------------------------------------------------------------------------------------------
@pytest.mark.skipif(not os.environ.get("PMX_LIVE"), reason="set PMX_LIVE=1 to hit api.manifold.markets")
def test_live_smoke_imports_one_market_and_its_comments(tmp_path: Path) -> None:
    """The one networked test. It needs ``PMX_LIVE=1`` and ``PMX_USER_AGENT_CONTACT`` (7.11).

    It asserts what only a live run can: that the shapes this module reads are still the shapes the venue
    sends, that the whole chain (search, market, bets, comments) still answers, and that what comes back
    validates against ``market.v2.json`` and ``news.v1.json``.
    """
    client = HttpClient(
        base_url=MANIFOLD_BASE_URL,
        user_agent=build_user_agent(),
        min_interval_ms=MANIFOLD_MIN_INTERVAL_MS,
        cache_dir=tmp_path / "cache",
    )
    try:
        markets = import_manifold(
            client=client,
            window_start_ms=WIDE_WINDOW_START_MS,
            window_end_ms=2 * FREEZE_MS,
            freeze_ms=2 * FREEZE_MS,
            limit=1,
        )
        assert len(markets) == 1
        market = markets[0]
        assert market_from_payload(market.to_dict(), where=market.id) == market
        assert market.provider == "manifold"
        assert market.bars and market.trades
        for item in fetch_comments(client=client, market=market):
            assert news_item_from_payload(item.to_dict(), where=item.news_id) == item
        opens = list_open_manifold(client=client, now_ms=market.resolved_at_ms, limit=1)
        assert len(opens) == 1
        assert opens[0].close_at_ms > market.resolved_at_ms
    finally:
        client.close()


# --------------------------------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------------------------------
def _market(markets: Sequence[Market], provider_id: str) -> Market:
    for market in markets:
        if market.provider_id == provider_id:
            return market
    raise AssertionError(f"{provider_id} was not imported")


def _walk(payload: object, pointer: str = "") -> Iterator[tuple[str, object]]:
    if isinstance(payload, dict):
        for key, value in payload.items():
            yield from _walk(value, f"{pointer}/{key}")
    elif isinstance(payload, list):
        for index, value in enumerate(payload):
            yield from _walk(value, f"{pointer}/{index}")
    else:
        yield pointer, payload
