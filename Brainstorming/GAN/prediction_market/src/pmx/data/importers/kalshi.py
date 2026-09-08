"""Import settled Kalshi binary markets, with their bar tape and their trade tape, as ``market.v2``.

Kalshi is the one provider of the four that is a real exchange with real money, a published fee schedule
and an outcome nobody can dispute, so it is the provider a claim is worth making on. Reading it honestly
takes four endpoints and one boundary:

* ``GET /markets?status=settled`` lists what settled recently, paginated by an opaque cursor;
* ``GET /historical/cutoff`` names the instant (``market_settled_ts``) before which a settled market has
  been moved out of the live tables. A market that settled earlier is invisible to ``/markets`` and its
  tape is only reachable under ``/historical/markets`` and
  ``/historical/markets/{ticker}/candlesticks``. Everything else is under
  ``/series/{series}/markets/{ticker}/candlesticks``. Choosing the wrong side of that boundary returns an
  empty tape rather than an error, which is why the cutoff is fetched first and pinned by a test;
* ``GET .../candlesticks`` gives the bar grid: yes bid and ask, the OHLC of the traded price, the volume
  and the open interest of each period, with ``period_interval`` in ``{1, 60, 1440}`` minutes;
* ``GET /markets/trades?ticker=`` gives the print tape, in the newer ``*_dollars`` decimal shape or the
  older integer-cents shape, both of which this module reads without ever building a float.

The settled list is flooded with auto-generated multi-leg shards (tickers starting ``KXMVE``) that live
for minutes and would drown a dataset in near-duplicate questions, so the shard rule of CONTRACTS_V2 7.4
is applied here, at the edge, together with an optional series allow-list: a caller that wants a curated
set of series passes it and gets nothing else.

Two rules of the wider contract shape everything below. Prices are basis points of one dollar, so a Kalshi
cent is exactly ``100`` bp and a decimal-dollar string goes through ``Decimal`` and never through a float
(CONTRACTS_V2 1.2, 7.2). And an importer returns objects, writes no file, and never returns a partial
market: a row whose tape carries no price at all, or whose life does not cover two bars of the grid, is
dropped rather than guessed at (it would fail the min-life and density filters of 7.4 anyway).
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Final

from pmx import MARKET_SCHEMA
from pmx.data.importers._http import HttpClient
from pmx.data.news.linker import LEXICON_DIR, derived_subjects_of, load_stopwords, merge_subjects
from pmx.errors import InvalidConfigError, MalformedResponseError
from pmx.types import (
    BP_ONE,
    CATEGORIES,
    CENTS_PER_UNIT,
    INTERVALS_MIN,
    MS_PER_DAY,
    PRICE_MAX_BP,
    PRICE_MIN_BP,
    TAPE_KIND_BARS_ONLY,
    TAPE_KIND_PRINTS,
    Bar,
    Market,
    MarketQuality,
    OpenMarket,
    Trade,
    bar_of,
    clamp_price_bp,
    interval_ms,
    round_half_up_decimal,
    sort_markets,
)

KALSHI_PROVIDER: Final = "kalshi"
KALSHI_BASE_URL: Final = "https://api.elections.kalshi.com/trade-api/v2"
KALSHI_API_KEY_ENV: Final = "PMX_KALSHI_API_KEY"
KALSHI_CURRENCY: Final = "usd"

#: Every imported Kalshi market carries the general schedule (CONTRACTS_V2 8.8). The reduced schedule is
#: series data that E2 reads off the fee PDF; while ``KALSHI_REDUCED_FEE_SERIES`` is empty there is nothing
#: for the importer to apply, and re-stamping a market later moves no byte of its tape.
KALSHI_FEE_SCHEDULE_ID: Final = "kalshi-general-2026-09"

#: Auto-generated multi-leg shards: the prefix rule of CONTRACTS_V2 7.4, compiled once.
KALSHI_SHARD_RE: Final = re.compile(r"^KXMVE")

#: Series refused whatever their ticker looks like (CONTRACTS_V2 7.4, "data, D2"). ``KXMVE`` is named here
#: as well as in the prefix rule so that the two spellings of the same decision cannot drift apart, and so
#: that a new shard family found by a later probe is one tuple entry rather than a new regex.
KALSHI_EXCLUDED_SERIES: Final[tuple[str, ...]] = ("KXMVE",)

#: A curated series allow-list. Empty means "every series that is not excluded", which is the default: a
#: hard-coded allow-list of tickers would silently empty a dataset the day Kalshi renames a series, so the
#: curation is a caller's argument (``import_kalshi(series_allow_list=...)``) and not a shipped constant.
KALSHI_ALLOWED_SERIES: Final[tuple[str, ...]] = ()

#: Page sizes and page caps. The caps exist so a broken cursor cannot spin forever; each one is reported in
#: the error it raises when it is hit, so a shortfall is never silent.
KALSHI_MARKETS_PAGE_LIMIT: Final = 1_000
KALSHI_MARKETS_MAX_PAGES: Final = 200
KALSHI_TRADES_PAGE_LIMIT: Final = 1_000
KALSHI_TRADES_MAX_PAGES: Final = 50
KALSHI_CANDLESTICK_MAX_PERIODS: Final = 5_000

#: A settled market's tape is looked for from ``window_start - slack`` on the live path, because Kalshi
#: settles at or after the close and the two instants can be a month apart on a long-dated market.
KALSHI_SETTLEMENT_SLACK_MS: Final = 30 * MS_PER_DAY

#: The Kalshi category strings seen on the API, mapped onto the twelve categories of CONTRACTS_V2 section 2.
#: Keys are compared lowercased and stripped; anything unknown lands on ``other``, never on a guess.
KALSHI_CATEGORIES: Final[Mapping[str, str]] = {
    "politics": "politics",
    "elections": "politics",
    "us politics": "politics",
    "world": "world",
    "world politics": "world",
    "geopolitics": "world",
    "economics": "economics",
    "economy": "economics",
    "inflation": "economics",
    "financials": "finance",
    "finance": "finance",
    "companies": "finance",
    "indices": "finance",
    "crypto": "crypto",
    "cryptocurrencies": "crypto",
    "sports": "sports",
    "science and technology": "tech",
    "technology": "tech",
    "tech": "tech",
    "science": "science",
    "space": "science",
    "climate and weather": "weather",
    "weather": "weather",
    "climate": "weather",
    "health": "health",
    "entertainment": "entertainment",
    "culture": "entertainment",
    "awards": "entertainment",
    "transportation": "other",
}
CATEGORY_FALLBACK: Final = "other"

#: The series-keyed data files this importer reads, beside the twelve lexicons of D5 and in the same
#: directory for the same reason (ruling R94): they are read at run time and a path relative to the
#: repository root does not exist in an installed wheel.
KALSHI_CATEGORIES_FILE: Final = "kalshi_series_categories.v1.json"
KALSHI_SUBJECTS_FILE: Final = "kalshi_series_subjects.v1.json"

#: ``market.v2`` caps a market at eight subjects (section 7.2).
WIKI_SUBJECTS_MAX: Final = 8

_SERIES_CATEGORIES_CACHE: dict[str, Mapping[str, str]] = {}
_SERIES_SUBJECTS_CACHE: dict[str, Mapping[str, tuple[str, ...]]] = {}

_HISTORICAL_CUTOFF_PATH: Final = "/historical/cutoff"
_HISTORICAL_MARKETS_PATH: Final = "/historical/markets"
_MARKETS_PATH: Final = "/markets"
_TRADES_PATH: Final = "/markets/trades"

_MS_PER_SECOND: Final = 1_000
_BP_PER_CENT: Final = BP_ONE // CENTS_PER_UNIT
_EPOCH: Final = datetime(1970, 1, 1, tzinfo=UTC)
_SECONDS_CEILING: Final = 100_000_000_000  # above this an integer instant is already milliseconds
_TAG_RE: Final = re.compile(r"^[a-z0-9_-]{1,32}$")
_SLUG_RE: Final = re.compile(r"^[A-Za-z0-9._-]{1,96}$")
_QUESTION_MAX: Final = 500
_DESCRIPTION_MAX: Final = 4_000
_URL_MAX: Final = 512

#: Where each instant of a market row is read from, in order of preference. Kalshi has renamed these
#: fields more than once and the historical tables answer with epoch seconds where the live ones answer
#: with an ISO string, so both shapes are accepted for every key.
_CREATED_KEYS: Final = ("open_time", "open_ts", "created_time")
_CLOSE_KEYS: Final = ("close_time", "close_ts")
#: The instants a settled row can carry its settlement under, most authoritative first. ``settlement_ts``
#: is the one the API answers today and it is the fact, not the schedule: measured over the 227 381
#: settled rows of the first real dataset build, every row carried it, none carried any of the four older
#: spellings, and ``expiration_time`` differed from it on every single row (it is the *latest* expiration
#: the contract allows, typically a week after the market actually settled). Reading ``expiration_time``
#: first therefore moved every real market's ``resolved_at`` forward by up to a week, which moves its last
#: bar, the window filter and the fold split with it.
_SETTLED_KEYS: Final = (
    "settled_time",
    "settlement_time",
    "settled_ts",
    "market_settled_ts",
    "settlement_ts",
    "expiration_time",
    "expected_expiration_time",
)


# --------------------------------------------------------------------------------------------------
# JSON reading helpers: every one of them raises MalformedResponseError instead of a TypeError
# --------------------------------------------------------------------------------------------------
def _as_object(payload: object, *, where: str) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise MalformedResponseError(
            "expected a JSON object", provider=KALSHI_PROVIDER, where=where, got=type(payload).__name__
        )
    return {str(key): value for key, value in payload.items()}


def _as_list(payload: object, *, where: str) -> list[object]:
    if not isinstance(payload, list):
        raise MalformedResponseError(
            "expected a JSON array", provider=KALSHI_PROVIDER, where=where, got=type(payload).__name__
        )
    return list(payload)


def _as_text(value: object) -> str:
    """A string field, empty when the provider sent ``null`` or something that is not a string."""
    return value.strip() if isinstance(value, str) else ""


def _as_int_or_none(value: object, *, where: str) -> int | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool):
        raise MalformedResponseError("expected an integer, got a boolean", provider=KALSHI_PROVIDER, where=where)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError as exc:
            raise MalformedResponseError(
                "expected an integer", provider=KALSHI_PROVIDER, where=where, got=value[:40]
            ) from exc
    raise MalformedResponseError(
        "expected an integer", provider=KALSHI_PROVIDER, where=where, got=type(value).__name__
    )


def _decimal_of(value: object, *, where: str) -> Decimal:
    """A provider decimal, read through ``Decimal`` and never through a float.

    A JSON float is converted by way of its shortest repr, which is the only lossless reading of a number
    the provider itself wrote as a decimal string in every other version of this API.
    """
    try:
        if isinstance(value, bool):
            raise InvalidOperation
        if isinstance(value, int):
            return Decimal(value)
        if isinstance(value, float):
            return Decimal(repr(value))
        if isinstance(value, str):
            return Decimal(value.strip())
    except InvalidOperation as exc:
        raise MalformedResponseError(
            "expected a decimal number", provider=KALSHI_PROVIDER, where=where, got=str(value)[:40]
        ) from exc
    raise MalformedResponseError(
        "expected a decimal number", provider=KALSHI_PROVIDER, where=where, got=type(value).__name__
    )


def _count_milli(value: object, *, where: str) -> int | None:
    """A provider contract count in thousandths of a contract, or ``None`` when the field is absent.

    Kalshi answers the same quantity in two shapes and both are read here. The older shape is a whole
    number of contracts (``12``); the current one is a decimal string (``"12.00"``, and ``"0.00"`` for a
    period nobody traded), which is what ``api.elections.kalshi.com`` answered on every listing row and
    every candlestick while the first real dataset was built. The decimal is read through
    :func:`_decimal_of`, never through a float, and a fractional count survives as thousandths exactly as
    ``count_fp`` already does on the print tape.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool):
        raise MalformedResponseError("expected a count, got a boolean", provider=KALSHI_PROVIDER, where=where)
    if isinstance(value, int):
        return value * 1_000
    return round_half_up_decimal(_decimal_of(value, where=where) * 1_000)


def _count_of(value: object, *, where: str) -> int | None:
    """A provider contract count in whole contracts, from either shape, or ``None`` when absent.

    Open interest is a number of contracts and not a tradable size, so the decimal shape is rounded back
    to a whole contract rather than kept in thousandths.
    """
    milli = _count_milli(value, where=where)
    return None if milli is None else (milli + 500) // 1_000


def _either(row: Mapping[str, object], *keys: str) -> object:
    """The first of ``keys`` the payload actually carries, or ``None``.

    Kalshi renamed the money and size fields of its listing rows: ``volume`` became ``volume_fp``,
    ``yes_bid`` became ``yes_bid_dollars`` and so on, and the old spellings are simply absent from what
    the API answers now. Reading both spellings is what keeps a recorded fixture and a live answer parsing
    through the same code.
    """
    for key in keys:
        if key in row and row[key] is not None:
            return row[key]
    return None


def _ms_of(value: object, *, where: str) -> int | None:
    """One instant of a Kalshi payload in epoch milliseconds, from an ISO string or an epoch integer.

    ``datetime.fromisoformat`` handles the ``Z`` suffix from 3.11 on, and the epoch difference is taken in
    integer days, seconds and microseconds so no float touches a time.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        raise MalformedResponseError("expected an instant, got a boolean", provider=KALSHI_PROVIDER, where=where)
    if isinstance(value, int):
        if value == 0:
            return None
        return value if abs(value) >= _SECONDS_CEILING else value * _MS_PER_SECOND
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        moment = datetime.fromisoformat(value.strip())
    except ValueError as exc:
        raise MalformedResponseError(
            "expected an ISO-8601 instant", provider=KALSHI_PROVIDER, where=where, got=value[:40]
        ) from exc
    if moment.tzinfo is None:
        raise MalformedResponseError(
            "an instant without a timezone is ambiguous", provider=KALSHI_PROVIDER, where=where, got=value[:40]
        )
    delta = moment.astimezone(UTC) - _EPOCH
    return delta.days * MS_PER_DAY + delta.seconds * _MS_PER_SECOND + delta.microseconds // _MS_PER_SECOND


def _first_instant_ms(row: Mapping[str, object], keys: Sequence[str], *, where: str) -> int | None:
    for key in keys:
        if key in row:
            found = _ms_of(row[key], where=f"{where}.{key}")
            if found is not None:
                return found
    return None


def _ohlc_bp(value: object, *, where: str) -> int | None:
    """One OHLC price of the candlestick tape in basis points, or ``None`` when the period had no print.

    An integer is Kalshi cents; a string or a float is dollars. A settled market's last period can print at
    100 cents, so the result is clamped into the tradable band exactly as CONTRACTS_V2 1.2 prescribes.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool):
        raise MalformedResponseError("expected a price, got a boolean", provider=KALSHI_PROVIDER, where=where)
    if isinstance(value, int):
        return clamp_price_bp(value * _BP_PER_CENT)
    return clamp_price_bp(round_half_up_decimal(_decimal_of(value, where=where) * BP_ONE))


def _quote_bp(value: object, *, where: str) -> int | None:
    """One side of the book in basis points, or ``None``.

    A quote is *not* clamped: a yes bid of 0 cents means "nobody is bidding", and clamping it to ``1`` bp
    would invent a bid the book never showed. Anything outside the tradable band is therefore no quote.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool):
        raise MalformedResponseError("expected a quote, got a boolean", provider=KALSHI_PROVIDER, where=where)
    price_bp = (
        value * _BP_PER_CENT
        if isinstance(value, int)
        else round_half_up_decimal(_decimal_of(value, where=where) * BP_ONE)
    )
    return price_bp if PRICE_MIN_BP <= price_bp <= PRICE_MAX_BP else None


def _truncate(text: str, limit: int) -> str:
    """``text`` at most ``limit`` characters, the tail replaced by ``...`` (CONTRACTS_V2 7.2)."""
    return text if len(text) <= limit else text[: limit - 3] + "..."


# --------------------------------------------------------------------------------------------------
# The series rules
# --------------------------------------------------------------------------------------------------
def kalshi_series(ticker: str) -> str:
    """The series ticker of a market ticker: ``KXPRESPARTY-28-R`` is series ``KXPRESPARTY``."""
    return ticker.split("-", 1)[0].upper()


def is_excluded_ticker(
    ticker: str,
    *,
    allow_list: Sequence[str] = KALSHI_ALLOWED_SERIES,
    excluded: Sequence[str] = KALSHI_EXCLUDED_SERIES,
) -> bool:
    """Whether the shard rule of CONTRACTS_V2 7.4 refuses ``ticker``.

    A ticker is refused when it matches the ``KXMVE`` prefix, when its series is in ``excluded``, or when
    ``allow_list`` is non-empty and its series is not in it. An empty allow-list allows every series that
    is not excluded, so the two mechanisms compose without a special case.
    """
    if KALSHI_SHARD_RE.match(ticker):
        return True
    series = kalshi_series(ticker)
    if series in {entry.upper() for entry in excluded}:
        return True
    return bool(allow_list) and series not in {entry.upper() for entry in allow_list}


def historical_cutoff_ms(client: HttpClient) -> int:
    """The ``market_settled_ts`` of ``GET /historical/cutoff`` in epoch milliseconds.

    A market that settled strictly before this instant is only readable on the historical path. The probe
    of 2026-09-07 answered ``2026-07-08T00:00:00Z``; the value moves forward on its own, which is exactly
    why it is fetched rather than pinned in the code.
    """
    payload = _as_object(client.get_json(_HISTORICAL_CUTOFF_PATH), where="historical/cutoff")
    cutoff = _first_instant_ms(payload, ("market_settled_ts", "settled_ts", "cutoff_ts"), where="cutoff")
    if cutoff is None:
        raise MalformedResponseError(
            "the historical cutoff carries no market_settled_ts",
            provider=KALSHI_PROVIDER,
            keys=",".join(sorted(payload)),
        )
    return cutoff


# --------------------------------------------------------------------------------------------------
# One market row, parsed
# --------------------------------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class _Row:
    """A market row of the settled, historical or open listing, parsed and nothing more."""

    ticker: str
    series: str
    event_key: str | None
    question: str
    description: str
    category: str
    created_at_ms: int
    close_at_ms: int
    resolved_at_ms: int | None
    resolution: int | None
    volume_milli: int
    last_price_bp: int | None
    quote_mid_bp: int | None


def _resolution_of(row: Mapping[str, object]) -> int | None:
    """``1`` for a YES settlement, ``0`` for NO, ``None`` for anything else (void, cancelled, open).

    Kalshi answers ``result`` and, on the historical tables, ``settlement_value`` in cents of the notional.
    A row that says neither is not a settled binary market and is dropped by the caller.
    """
    result = _as_text(row.get("result")).lower()
    if result in {"yes", "y"}:
        return 1
    if result in {"no", "n"}:
        return 0
    if result:
        return None
    value = _as_int_or_none(row.get("settlement_value"), where="market.settlement_value")
    if value is not None:
        if value >= CENTS_PER_UNIT:
            return 1
        return 0 if value <= 0 else None
    dollars = _either(row, "settlement_value_dollars")
    if dollars is None:
        return None
    settled_bp = round_half_up_decimal(
        _decimal_of(dollars, where="market.settlement_value_dollars") * BP_ONE
    )
    if settled_bp >= BP_ONE:
        return 1
    return 0 if settled_bp <= 0 else None


def _question_of(row: Mapping[str, object]) -> str:
    """The question a forecaster is answering: the event title, narrowed by the YES leg's subtitle.

    A Kalshi event carries one title for every leg ("Who will win?") and the leg is named by
    ``yes_sub_title`` ("Republican"), so the title alone would make several legs of one event look like the
    same question to an agent and to the linker.
    """
    title = _as_text(row.get("title"))
    leg = _as_text(row.get("yes_sub_title")) or _as_text(row.get("subtitle"))
    if leg and leg.lower() not in title.lower():
        title = f"{title} ({leg})" if title else leg
    return _truncate(title, _QUESTION_MAX)


def _description_of(row: Mapping[str, object]) -> str:
    primary = _as_text(row.get("rules_primary"))
    secondary = _as_text(row.get("rules_secondary"))
    joined = "\n".join(part for part in (primary, secondary) if part)
    return _truncate(joined, _DESCRIPTION_MAX)


def _read_series_file(path: Path) -> Mapping[str, object]:
    """The ``{"series": {...}}`` body of one series data file, or an empty map.

    A missing or malformed file means "no mapping", never an exception, exactly as a missing lexicon
    does (section 7.6): a dataset built without the file is a worse dataset, not a failed build.
    """
    try:
        with open(path, encoding="utf-8", newline="\n") as handle:
            payload = json.loads(handle.read())
    except (OSError, ValueError):
        return {}
    if not isinstance(payload, dict):
        return {}
    series = payload.get("series")
    if not isinstance(series, dict):
        return {}
    return {str(key).upper(): value for key, value in series.items()}


def load_series_categories(directory: Path | None = None) -> Mapping[str, str]:
    """Series ticker to one of the twelve categories of CONTRACTS_V2 section 2, from the data file.

    A settled listing row carries no ``category`` field: measured over the 227 381 settled rows of the
    first real dataset build, not one of them has it, so without this map every Kalshi market lands on
    ``other`` and the per-category breakdown of the whole provider is flat. An entry naming a category
    that is not one of the twelve is dropped rather than written into a market.
    """
    root = LEXICON_DIR if directory is None else directory
    key = str(root)
    cached = _SERIES_CATEGORIES_CACHE.get(key)
    if cached is not None:
        return cached
    mapping = {
        series: value
        for series, value in _read_series_file(root / KALSHI_CATEGORIES_FILE).items()
        if isinstance(value, str) and value in CATEGORIES
    }
    _SERIES_CATEGORIES_CACHE[key] = mapping
    return mapping


def load_series_subjects(directory: Path | None = None) -> Mapping[str, tuple[str, ...]]:
    """Series ticker to the Wikipedia article titles that are its markets' subject, from the data file.

    These are the **stated** subjects of a Kalshi market: a human named them from the series title, and
    the linker of section 7.6 compares them verbatim against a news item's ``wiki_links``.
    """
    root = LEXICON_DIR if directory is None else directory
    key = str(root)
    cached = _SERIES_SUBJECTS_CACHE.get(key)
    if cached is not None:
        return cached
    mapping: dict[str, tuple[str, ...]] = {}
    for series, value in _read_series_file(root / KALSHI_SUBJECTS_FILE).items():
        if not isinstance(value, list):
            continue
        titles = tuple(title for title in value if isinstance(title, str) and title.strip())
        if titles:
            mapping[series] = titles
    _SERIES_SUBJECTS_CACHE[key] = mapping
    return mapping


def series_category(series: str, *, categories: Mapping[str, str] | None = None) -> str | None:
    """The mapped category of a series ticker, or ``None`` when the map does not name it."""
    table = load_series_categories() if categories is None else categories
    return table.get(series.upper())


def _category_of(row: Mapping[str, object], series: str) -> str:
    """The market's category: what the row says, else what the series map says, else the fallback.

    The row is asked first because a provider that starts publishing a category again is the better
    source; the map is the measured answer for a provider that does not.
    """
    raw = _as_text(row.get("category")).lower()
    if raw in KALSHI_CATEGORIES:
        return KALSHI_CATEGORIES[raw]
    mapped = series_category(series)
    return mapped if mapped is not None else CATEGORY_FALLBACK


def wiki_subjects_of(
    series: str,
    question: str,
    *,
    subjects: Mapping[str, tuple[str, ...]] | None = None,
    stopwords: frozenset[str] | None = None,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """``(wiki_subjects, wiki_subject_provenance)`` for one Kalshi market, sorted and aligned.

    Two sources, in this order of authority: the curated series map, whose entries are ``stated``, and
    the capitalised runs of the market's own question, which are ``derived``. A title that both sources
    offer is stated, because the stronger provenance wins. The result is sorted and unique, which is what
    section 7.2 and the loader demand, and the provenance list is permuted with it so flag ``k`` still
    describes subject ``k``.

    Without this a Kalshi market carried no subject at all, the 600-permille term of the linker was
    structurally zero for the whole provider, and ``wikipedia_asof`` had nothing to snapshot.
    """
    stated = tuple(
        dict.fromkeys(
            (load_series_subjects() if subjects is None else subjects).get(series.upper(), ())
        )
    )
    words = load_stopwords() if stopwords is None else stopwords
    derived = tuple(
        title for title in derived_subjects_of(question, words) if title not in set(stated)
    )
    return merge_subjects(stated, derived, limit=WIKI_SUBJECTS_MAX)


def _tags_of(series: str, category: str) -> tuple[str, ...]:
    """The provider labels worth keeping: the series, lowercased, and the mapped category."""
    candidates = {category, series.lower()}
    return tuple(sorted(tag for tag in candidates if _TAG_RE.match(tag)))


def _url_of(series: str, event_key: str | None) -> str:
    """The venue's public page for the market's event, the closest stable URL a leg has."""
    tail = f"/{event_key.lower()}" if event_key else ""
    return _truncate(f"https://kalshi.com/markets/{series.lower()}{tail}", _URL_MAX)


def _row_of(payload: object, *, where: str) -> _Row | None:
    """Parse one listing row, or ``None`` when it is not a usable binary market.

    ``None`` is returned for a row without a ticker, without an open or close instant, or whose close is
    at or before its open: those are not markets with a tape, and inventing an instant for them would put
    a fabricated bar grid into a dataset.
    """
    row = _as_object(payload, where=where)
    ticker = _as_text(row.get("ticker"))
    if not ticker or not _SLUG_RE.match(ticker):
        return None
    created_at_ms = _first_instant_ms(row, _CREATED_KEYS, where=where)
    close_at_ms = _first_instant_ms(row, _CLOSE_KEYS, where=where)
    if created_at_ms is None or close_at_ms is None or close_at_ms <= created_at_ms:
        return None
    resolved_at_ms = _first_instant_ms(row, _SETTLED_KEYS, where=where)
    if resolved_at_ms is not None and resolved_at_ms < close_at_ms:
        # Kalshi markets can close early: the published close is the schedule, the settlement is the fact.
        close_at_ms = resolved_at_ms
    volume_milli = _count_milli(_either(row, "volume", "volume_fp"), where=f"{where}.volume") or 0
    bid_bp = _quote_bp(_either(row, "yes_bid", "yes_bid_dollars"), where=f"{where}.yes_bid")
    ask_bp = _quote_bp(_either(row, "yes_ask", "yes_ask_dollars"), where=f"{where}.yes_ask")
    mid_bp = clamp_price_bp((bid_bp + ask_bp) // 2) if bid_bp is not None and ask_bp is not None else None
    series = _as_text(row.get("series_ticker")).upper() or kalshi_series(ticker)
    category = _category_of(row, series)
    return _Row(
        ticker=ticker,
        series=series,
        event_key=_as_text(row.get("event_ticker")) or None,
        question=_question_of(row),
        description=_description_of(row),
        category=category,
        created_at_ms=created_at_ms,
        close_at_ms=close_at_ms,
        resolved_at_ms=resolved_at_ms,
        resolution=_resolution_of(row),
        volume_milli=max(0, volume_milli),
        last_price_bp=_ohlc_bp(_either(row, "last_price", "last_price_dollars"), where=f"{where}.last_price"),
        quote_mid_bp=mid_bp,
    )


# --------------------------------------------------------------------------------------------------
# Listing
# --------------------------------------------------------------------------------------------------
def _list_rows(
    client: HttpClient,
    *,
    path: str,
    params: Mapping[str, str | int],
    stop_before_ms: int | None = None,
) -> list[_Row]:
    """Every row of a cursor-paginated listing, in the order the provider returned them.

    The loop stops on an empty cursor, on a cursor the provider repeats (which is how a broken page reads)
    and on the page cap, which raises rather than truncating in silence.

    ``stop_before_ms`` ends the walk once a whole page closed before it (ruling R100). Both Kalshi
    listings answer in descending close order, so a page whose newest row is already older than the bound
    means every page after it is older still; without the stop, a twelve-month window over the unnarrowed
    historical archive hits the page cap after 200 000 rows without having reached the window at all.
    """
    rows: list[_Row] = []
    cursor = ""
    seen: set[str] = set()
    for page in range(KALSHI_MARKETS_MAX_PAGES):
        page_params: dict[str, str | int] = dict(params)
        if cursor:
            page_params["cursor"] = cursor
        payload = _as_object(client.get_json(path, page_params), where=path)
        page_rows: list[_Row] = []
        for index, entry in enumerate(_as_list(payload.get("markets", []), where=f"{path}.markets")):
            row = _row_of(entry, where=f"{path}.markets[{index}]")
            if row is not None:
                page_rows.append(row)
        rows.extend(page_rows)
        if page_rows and stop_before_ms is not None and max(r.close_at_ms for r in page_rows) < stop_before_ms:
            return rows
        cursor = _as_text(payload.get("cursor"))
        if not cursor or cursor in seen:
            return rows
        seen.add(cursor)
        if page + 1 == KALSHI_MARKETS_MAX_PAGES:
            raise MalformedResponseError(
                "the listing did not end within the page cap",
                provider=KALSHI_PROVIDER,
                path=path,
                pages=KALSHI_MARKETS_MAX_PAGES,
            )
    return rows


def _settled_rows(
    client: HttpClient,
    *,
    window_start_ms: int,
    window_end_ms: int,
    cutoff_ms: int,
    series_allow_list: Sequence[str] = (),
) -> list[_Row]:
    """The settled rows that can possibly fall in the window, from both sides of the historical cutoff.

    The live listing is narrowed server-side by close time (a settled market closed at or before it
    settled, at most ``KALSHI_SETTLEMENT_SLACK_MS`` earlier). The historical listing ignores those two
    parameters (verified against ``api.elections.kalshi.com`` on 2026-09-07: the answer is identical with
    and without them), so its walk is bounded by the descending stop of :func:`_list_rows` instead.

    ``series_allow_list`` is passed through as ``series_ticker``, one listing per series, because it is
    the one narrowing both endpoints honour (ruling R100). Without it a twelve-month window is out of
    reach: the unnarrowed settled universe is dominated by ``KXMVE`` shards at about eight thousand rows
    per minute of close time, so neither the page cap nor a client-side filter can walk a year of it.
    """
    floor_ms = max(0, window_start_ms - KALSHI_SETTLEMENT_SLACK_MS)
    series = tuple(dict.fromkeys(entry.upper() for entry in series_allow_list))
    rows: list[_Row] = []
    for narrowing in [{"series_ticker": name} for name in series] or [{}]:
        if window_start_ms < cutoff_ms:
            rows.extend(
                _list_rows(
                    client,
                    path=_HISTORICAL_MARKETS_PATH,
                    params={"limit": KALSHI_MARKETS_PAGE_LIMIT, **narrowing},
                    stop_before_ms=floor_ms,
                )
            )
        if window_end_ms > cutoff_ms:
            rows.extend(
                _list_rows(
                    client,
                    path=_MARKETS_PATH,
                    params={
                        "status": "settled",
                        "limit": KALSHI_MARKETS_PAGE_LIMIT,
                        "min_close_ts": floor_ms // _MS_PER_SECOND,
                        "max_close_ts": window_end_ms // _MS_PER_SECOND,
                        **narrowing,
                    },
                    stop_before_ms=floor_ms,
                )
            )
    unique: dict[str, _Row] = {}
    for row in rows:
        unique.setdefault(row.ticker, row)
    return sorted(unique.values(), key=lambda row: (row.resolved_at_ms or 0, row.ticker))


# --------------------------------------------------------------------------------------------------
# The tape: candlesticks and trades
# --------------------------------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class _Candle:
    """One candlestick period, keyed by the bar it opens (CONTRACTS_V2 5.2: a bar is named by its open)."""

    t_ms: int
    #: The end of the provider's period, which is not on the grid when the provider's day is not UTC's.
    t_end_ms: int
    open_bp: int | None
    high_bp: int | None
    low_bp: int | None
    close_bp: int | None
    vwap_bp: int | None
    volume_milli: int
    yes_bid_bp: int | None
    yes_ask_bp: int | None
    open_interest: int | None


def _candle_of(payload: object, *, interval_min: int, where: str) -> _Candle | None:
    """One candlestick, or ``None`` when it carries no period stamp.

    ``end_period_ts`` names the *end* of the period, so the period opens one interval earlier, and the
    candle is keyed by the **bar that period opens in** (``bar_of``, CONTRACTS_V2 5.2: a bar is named by
    its open, on a grid measured from the epoch). The snap is not decoration: Kalshi's daily periods run
    on Eastern time, so every ``end_period_ts`` of a ``period_interval=1440`` answer falls at 04:00 UTC
    (EDT) or 05:00 UTC (EST) and the raw ``end - step`` is never a multiple of a day. Without the snap
    every daily candle missed the grid, :func:`_bars` found no candle for any bar, and every Kalshi
    market came out with a flat price path, ``volume_milli = 0`` on every bar and ``traded_bars = 0``,
    which is exactly what ruling R167's ``min_traded_bars`` branch reads (``docs/BUILD_STATE.md`` 7).
    """
    step_ms = interval_ms(interval_min)
    entry = _as_object(payload, where=where)
    end_ms = _first_instant_ms(entry, ("end_period_ts", "end_ts", "period_end_ts"), where=where)
    if end_ms is None:
        return None
    price = _as_object(entry.get("price", {}), where=f"{where}.price")
    bid = _as_object(entry.get("yes_bid", {}), where=f"{where}.yes_bid")
    ask = _as_object(entry.get("yes_ask", {}), where=f"{where}.yes_ask")
    # Both spellings, everywhere, for the reason :func:`_either` exists: the two candlestick paths do not
    # answer the same shape. ``/historical/markets/{ticker}/candlesticks`` still serves ``volume``,
    # ``open_interest`` and ``price.close``; ``/series/{series}/markets/{ticker}/candlesticks``, which is
    # the only path for a market settled after the historical cutoff, serves ``volume_fp``,
    # ``open_interest_fp`` and ``price.close_dollars``. Reading only the historical spelling left every
    # market of the last two months of the window with no price and no size on any bar.
    open_bp = _ohlc_bp(_either(price, "open", "open_dollars"), where=f"{where}.price.open")
    close_bp = _ohlc_bp(_either(price, "close", "close_dollars"), where=f"{where}.price.close")
    high_bp = _ohlc_bp(_either(price, "high", "high_dollars"), where=f"{where}.price.high")
    low_bp = _ohlc_bp(_either(price, "low", "low_dollars"), where=f"{where}.price.low")
    mean_bp = _ohlc_bp(_either(price, "mean", "mean_dollars"), where=f"{where}.price.mean")
    bid_bp = _quote_bp(_either(bid, "close", "close_dollars"), where=f"{where}.yes_bid.close")
    ask_bp = _quote_bp(_either(ask, "close", "close_dollars"), where=f"{where}.yes_ask.close")
    if bid_bp is not None and ask_bp is not None and bid_bp > ask_bp:
        # A crossed book is a provider artefact and the loader refuses it; no quote is the honest reading.
        bid_bp, ask_bp = None, None
    volume_milli = _count_milli(_either(entry, "volume", "volume_fp"), where=f"{where}.volume") or 0
    return _Candle(
        t_ms=bar_of(end_ms - step_ms, interval_min),
        t_end_ms=end_ms,
        open_bp=open_bp,
        high_bp=high_bp,
        low_bp=low_bp,
        close_bp=close_bp,
        vwap_bp=mean_bp,
        volume_milli=max(0, volume_milli),
        yes_bid_bp=bid_bp,
        yes_ask_bp=ask_bp,
        open_interest=_count_of(
            _either(entry, "open_interest", "open_interest_fp"), where=f"{where}.open_interest"
        ),
    )


def _candlesticks(
    client: HttpClient,
    *,
    row: _Row,
    interval_min: int,
    start_ms: int,
    end_ms: int,
    historical: bool,
) -> dict[int, _Candle]:
    """The candlestick tape of one market on the run's grid, keyed by bar open.

    The request is chunked at ``KALSHI_CANDLESTICK_MAX_PERIODS`` periods because the endpoint caps the
    number of candlesticks it will answer with, and an hourly year is far past that cap.
    """
    path = (
        f"{_HISTORICAL_MARKETS_PATH}/{row.ticker}/candlesticks"
        if historical
        else f"/series/{row.series}/markets/{row.ticker}/candlesticks"
    )
    step_ms = interval_ms(interval_min)
    chunk_ms = step_ms * KALSHI_CANDLESTICK_MAX_PERIODS
    candles: dict[int, _Candle] = {}
    chunk_start_ms = start_ms
    while chunk_start_ms <= end_ms:
        chunk_end_ms = min(end_ms, chunk_start_ms + chunk_ms - step_ms)
        slack_ms = step_ms if chunk_end_ms >= end_ms else 0
        payload = _as_object(
            client.get_json(
                path,
                {
                    "start_ts": chunk_start_ms // _MS_PER_SECOND,
                    # The last chunk asks for one period of slack past the last bar. The endpoint selects
                    # periods by their *end*, and a Kalshi daily period that opens inside the last bar
                    # ends at midnight Eastern, four or five hours into the next UTC day, so a range that
                    # stopped one interval past the last bar lost the settling bar's price and size
                    # (measured on ``KXCPI-25AUG-T0.4``: the answer stopped one bar short of
                    # settlement). An intermediate chunk needs no slack, because the period that opens in
                    # its last bar ends inside the next chunk's range and is keyed by its own bar there.
                    "end_ts": (chunk_end_ms + step_ms + slack_ms) // _MS_PER_SECOND,
                    "period_interval": interval_min,
                },
            ),
            where=path,
        )
        entries = _as_list(payload.get("candlesticks", []), where=f"{path}.candlesticks")
        for index, entry in enumerate(entries):
            candle = _candle_of(entry, interval_min=interval_min, where=f"{path}.candlesticks[{index}]")
            if candle is not None and start_ms <= candle.t_ms <= end_ms:
                # Two periods never open in the same bar while the period and the grid are the same
                # length (measured: no collision over the 871 cached candlestick answers of the first
                # real build), and a later period wins if the provider ever answers overlapping ones.
                previous = candles.get(candle.t_ms)
                if previous is None or previous.t_end_ms <= candle.t_end_ms:
                    candles[candle.t_ms] = candle
        chunk_start_ms = chunk_end_ms + step_ms
    return candles


def _trade_of(payload: object, *, where: str) -> Trade | None:
    """One print of the trade tape, or ``None`` when it carries no instant, no price or no size.

    Both API shapes are read: the newer ``yes_price_dollars`` / ``count_fp`` decimals and the older
    integer ``yes_price`` cents / ``count`` contracts. A tape that only carries the NO price is mirrored,
    because a NO print at 0.37 is a YES print at 0.63 and the bar grid is a YES grid.
    """
    entry = _as_object(payload, where=where)
    t_ms = _first_instant_ms(entry, ("created_time", "created_ts", "ts"), where=where)
    if t_ms is None:
        return None
    price_bp = _ohlc_bp(entry.get("yes_price_dollars"), where=f"{where}.yes_price_dollars")
    if price_bp is None:
        price_bp = _ohlc_bp(entry.get("yes_price"), where=f"{where}.yes_price")
    if price_bp is None:
        no_bp = _ohlc_bp(entry.get("no_price_dollars"), where=f"{where}.no_price_dollars")
        if no_bp is None:
            no_bp = _ohlc_bp(entry.get("no_price"), where=f"{where}.no_price")
        price_bp = clamp_price_bp(BP_ONE - no_bp) if no_bp is not None else None
    if price_bp is None:
        return None
    count_milli = _count_milli(entry.get("count"), where=f"{where}.count")
    if count_milli is not None:
        size_milli = count_milli
    elif "count_fp" in entry:
        size_milli = round_half_up_decimal(_decimal_of(entry["count_fp"], where=f"{where}.count_fp") * 1_000)
    else:
        return None
    if size_milli < 1:
        return None
    side = _as_text(entry.get("taker_side")).lower()
    return Trade(
        t_ms=t_ms,
        price_bp=price_bp,
        size_milli=size_milli,
        side=side if side in {"yes", "no"} else "unknown",
    )


def _trades(client: HttpClient, *, ticker: str, end_ms: int) -> tuple[Trade, ...]:
    """The whole print tape of one market, sorted in the canonical trade order of CONTRACTS_V2 section 3."""
    collected: list[Trade] = []
    cursor = ""
    seen: set[str] = set()
    for page in range(KALSHI_TRADES_MAX_PAGES):
        params: dict[str, str | int] = {"ticker": ticker, "limit": KALSHI_TRADES_PAGE_LIMIT}
        if cursor:
            params["cursor"] = cursor
        payload = _as_object(client.get_json(_TRADES_PATH, params), where=_TRADES_PATH)
        entries = _as_list(payload.get("trades", []), where=f"{_TRADES_PATH}.trades")
        for index, entry in enumerate(entries):
            trade = _trade_of(entry, where=f"{_TRADES_PATH}.trades[{index}]")
            if trade is not None and trade.t_ms <= end_ms:
                collected.append(trade)
        cursor = _as_text(payload.get("cursor"))
        if not cursor or cursor in seen:
            break
        seen.add(cursor)
        if page + 1 == KALSHI_TRADES_MAX_PAGES:
            raise MalformedResponseError(
                "the trade tape did not end within the page cap",
                provider=KALSHI_PROVIDER,
                ticker=ticker,
                pages=KALSHI_TRADES_MAX_PAGES,
            )
    return tuple(sorted(collected, key=lambda trade: (trade.t_ms, trade.price_bp, trade.size_milli, trade.side)))


def _first_price_bp(row: _Row, candles: Mapping[int, _Candle], trades: Sequence[Trade]) -> int | None:
    """The market's opening price: the first period that printed, else its book, else the first print.

    CONTRACTS_V2 5.2 wants "the provider's opening quote when known, else the first print", and this is
    also the as-of price of a market's very first bar (5.4, ruling R11), so a market that has none of the
    three is dropped by the caller rather than started at an invented 50 cents.
    """
    for t_ms in sorted(candles):
        candle = candles[t_ms]
        for price_bp in (candle.open_bp, candle.close_bp, candle.vwap_bp):
            if price_bp is not None:
                return price_bp
        mid = (
            clamp_price_bp((candle.yes_bid_bp + candle.yes_ask_bp) // 2)
            if candle.yes_bid_bp is not None and candle.yes_ask_bp is not None
            else None
        )
        if mid is not None:
            return mid
    if trades:
        return trades[0].price_bp
    return row.quote_mid_bp or row.last_price_bp


def _bars(
    *,
    candles: Mapping[int, _Candle],
    trades: Sequence[Trade],
    interval_min: int,
    t_first_ms: int,
    t_last_ms: int,
    first_price_bp: int,
) -> tuple[Bar, ...]:
    """The dense bar grid of one market, from its first bar to its settling bar inclusive.

    A period Kalshi never answered for, or answered without a price, is a bar with no trade: it repeats the
    previous close as ``open == high == low == close == vwap`` with ``volume_milli = 0`` and
    ``n_trades = 0`` (CONTRACTS_V2 5.2). ``n_trades`` comes from the print tape rather than from the
    candlestick, which carries no count; ``volume_milli`` comes from the candlestick, which is complete
    even when the print tape was capped.
    """
    step_ms = interval_ms(interval_min)
    counts: dict[int, int] = {}
    for trade in trades:
        bucket = bar_of(trade.t_ms, interval_min)
        counts[bucket] = counts.get(bucket, 0) + 1
    bars: list[Bar] = []
    carried_bp = first_price_bp
    t_ms = t_first_ms
    while t_ms <= t_last_ms:
        candle = candles.get(t_ms)
        close_bp = candle.close_bp if candle is not None else None
        if candle is None or close_bp is None:
            bars.append(
                Bar(
                    t_ms=t_ms,
                    open_bp=carried_bp,
                    high_bp=carried_bp,
                    low_bp=carried_bp,
                    close_bp=carried_bp,
                    vwap_bp=carried_bp,
                    volume_milli=0,
                    n_trades=0,
                    yes_bid_bp=candle.yes_bid_bp if candle is not None else None,
                    yes_ask_bp=candle.yes_ask_bp if candle is not None else None,
                    open_interest=candle.open_interest if candle is not None else None,
                )
            )
        else:
            open_bp = candle.open_bp if candle.open_bp is not None else carried_bp
            vwap_bp = candle.vwap_bp if candle.vwap_bp is not None else close_bp
            high_bp = max(candle.high_bp or close_bp, open_bp, close_bp, vwap_bp)
            low_bp = min(candle.low_bp or close_bp, open_bp, close_bp, vwap_bp)
            bars.append(
                Bar(
                    t_ms=t_ms,
                    open_bp=open_bp,
                    high_bp=high_bp,
                    low_bp=low_bp,
                    close_bp=close_bp,
                    vwap_bp=vwap_bp,
                    volume_milli=candle.volume_milli,
                    n_trades=counts.get(t_ms, 0),
                    yes_bid_bp=candle.yes_bid_bp,
                    yes_ask_bp=candle.yes_ask_bp,
                    open_interest=candle.open_interest,
                )
            )
            carried_bp = close_bp
        t_ms += step_ms
    return tuple(bars)


def _quality(
    *, row: _Row, bars: Sequence[Bar], trades: Sequence[Trade], created_at_ms: int, end_ms: int
) -> MarketQuality:
    """What the provider gave, counted and nothing more (CONTRACTS_V2 7.12: D6 computes the rest).

    ``unique_bettors`` is ``None`` because Kalshi publishes no trader count, which is exactly why the
    quality filter of 7.4 reads it as "n_trades >= 50 **or** unique_bettors >= 30".

    ``tape_kind`` is set from what this import **actually fetched**, not from what the endpoint promises:
    ``prints`` when the print tape answered at least one usable print, ``bars_only`` when it answered
    none. For a settled Kalshi market it answers none, whatever the market traded
    (``GET /markets/trades?ticker=<settled ticker>`` returns an empty list even for a market that traded
    five million contracts: the public tape holds only what is trading now), while the candlestick tape
    still carries volume and open interest per period. So ``n_trades`` stays the honest ``0`` and
    ``traded_bars`` becomes the count the ``min_trades`` filter reads for this provider.
    """
    volume_milli_total = sum(bar.volume_milli for bar in bars)
    return MarketQuality(
        n_trades=len(trades),
        unique_bettors=None,
        life_days=(end_ms - created_at_ms) // MS_PER_DAY,
        volume_milli_total=volume_milli_total or row.volume_milli,
        traded_bars=sum(1 for bar in bars if bar.volume_milli > 0),
        tape_kind=TAPE_KIND_PRINTS if trades else TAPE_KIND_BARS_ONLY,
    )


def _fetch_budget(rows: Sequence[_Row], limit: int | None) -> tuple[_Row, ...]:
    """At most ``limit`` rows: the busiest row of each equal stride of the walk.

    This is ``evenly_spaced`` with one change, and for one measured reason. The stride is the same, so the
    budget still covers the whole window and the builder's stratified cap (ruling R168) still finds a
    market in every month; what a stride contributes is no longer its first row but its **busiest** row,
    by the lifetime ``volume`` the listing reports, ties to the lower ticker.

    The narrowed Kalshi listing of the first real build offers 15 090 settled rows that live a week or
    more inside a twelve-month window, and a budget of 400 buys 2.6 per cent of them. Spent on the head
    of each stride it bought mostly markets that traded a few contracts on one day, and 20 per cent of
    what it bought survived the quality filters of section 7.4 (measured: 8 of 40). Spent on the busiest
    row of each stride it buys tapes with size on most of their days, which is what ``min_trades`` and
    ``density`` read (measured: 27 of 36). The choice is deterministic and depends on nothing but the
    listing, so two builds of the same window fetch the same tapes.
    """
    total = len(rows)
    if limit is None or limit <= 0 or total <= limit:
        return tuple(rows)
    chosen: list[_Row] = []
    for index in range(limit):
        start = (index * total) // limit
        stop = max(start + 1, ((index + 1) * total) // limit)
        chosen.append(min(rows[start:stop], key=lambda row: (-row.volume_milli, row.ticker)))
    return tuple(chosen)


def _check_interval(interval_min: int) -> None:
    if interval_min not in INTERVALS_MIN:
        raise InvalidConfigError(
            "the grid of a dataset is hourly or daily", interval_min=interval_min, allowed=str(INTERVALS_MIN)
        )


# --------------------------------------------------------------------------------------------------
# The two public importers
# --------------------------------------------------------------------------------------------------
def import_kalshi(
    *,
    client: HttpClient,
    window_start_ms: int,
    window_end_ms: int,
    freeze_ms: int,
    limit: int | None = None,
    interval_min: int = 1_440,
    series_allow_list: Sequence[str] | None = None,
    min_life_days: int = 0,
) -> tuple[Market, ...]:
    """Every settled Kalshi binary market whose settlement falls in the window, with its full tape.

    ``interval_min`` and ``series_allow_list`` are keyword-only extensions of the signature of
    CONTRACTS_V2 7.12 with the defaults the contract implies (the daily grid, no curation); an hourly
    dataset (ruling R24) has no other way to ask for hourly candlesticks.

    A row is dropped, never repaired, when it is a shard, when its settlement is outside
    ``[window_start_ms, window_end_ms)``, when it settles at or after the freeze (CONTRACTS_V2 5.6), when
    it did not settle YES or NO, when its life does not cover two bars of the grid, or when its tape
    carries no price at all. Everything else that the dataset needs (hardness tags, the fold, the quality
    filters) is D6's, and this function writes no file.

    Two of those drops exist so the **fetch budget** is not spent on a tape the builder is certain to
    remove, which is the same reason the Manifold import takes ``created_floor_ms``. Both are necessary
    conditions read off the listing row, never a substitute for a filter of 7.4:

    * a row whose reported lifetime ``volume`` is zero has neither a print nor a bar with size, so it
      fails ``min_trades`` on all three of its branches (Kalshi publishes no ``unique_bettors``);
    * a row whose life is shorter than ``min_life_days`` fails ``min_life``. The default ``0`` asks for
      no floor, so an importer call that does not pass a build's config behaves exactly as before.

    The narrowed listing of the first real build holds 166 586 settled rows inside a twelve-month window
    and 88 per cent of them live under a week, so a budget spread evenly over the raw walk spent almost
    all of itself on tapes ``min_life`` then removed (``docs/BUILD_STATE.md`` 7).
    """
    _check_interval(interval_min)
    allow_list = tuple(series_allow_list) if series_allow_list is not None else KALSHI_ALLOWED_SERIES
    cutoff_ms = historical_cutoff_ms(client)
    step_ms = interval_ms(interval_min)
    eligible: list[_Row] = []
    for row in _settled_rows(
        client,
        window_start_ms=window_start_ms,
        window_end_ms=window_end_ms,
        cutoff_ms=cutoff_ms,
        series_allow_list=allow_list,
    ):
        resolved_at_ms = row.resolved_at_ms
        if resolved_at_ms is None or row.resolution is None:
            continue
        if not window_start_ms <= resolved_at_ms < window_end_ms or resolved_at_ms >= freeze_ms:
            continue
        if is_excluded_ticker(row.ticker, allow_list=allow_list):
            continue
        if row.volume_milli <= 0:
            continue
        if resolved_at_ms - row.created_at_ms < min_life_days * MS_PER_DAY:
            continue
        t_first_ms = bar_of(row.created_at_ms, interval_min)
        t_last_ms = bar_of(resolved_at_ms, interval_min)
        if t_last_ms - t_first_ms < step_ms:
            continue
        eligible.append(row)
    # The whole window is walked first and only then thinned to the fetch budget, so a budget never
    # truncates the window to its first days (see :func:`_fetch_budget`).
    markets: list[Market] = []
    for row in _fetch_budget(eligible, limit):
        resolved_at_ms = row.resolved_at_ms
        if resolved_at_ms is None or row.resolution is None:  # pragma: no cover - filtered above
            continue
        t_first_ms = bar_of(row.created_at_ms, interval_min)
        t_last_ms = bar_of(resolved_at_ms, interval_min)
        historical = resolved_at_ms < cutoff_ms
        candles = _candlesticks(
            client,
            row=row,
            interval_min=interval_min,
            start_ms=t_first_ms,
            end_ms=t_last_ms,
            historical=historical,
        )
        trades = _trades(client, ticker=row.ticker, end_ms=resolved_at_ms)
        first_price_bp = _first_price_bp(row, candles, trades)
        if first_price_bp is None:
            continue
        bars = _bars(
            candles=candles,
            trades=trades,
            interval_min=interval_min,
            t_first_ms=t_first_ms,
            t_last_ms=t_last_ms,
            first_price_bp=first_price_bp,
        )
        subjects, provenance = wiki_subjects_of(row.series, row.question)
        markets.append(
            Market(
                schema_version=MARKET_SCHEMA,
                id=f"{KALSHI_PROVIDER}-{row.ticker}",
                provider=KALSHI_PROVIDER,
                provider_id=row.ticker,
                url=_url_of(row.series, row.event_key),
                question=row.question,
                description=row.description,
                category=row.category,
                tags=_tags_of(row.series, row.category),
                wiki_subjects=subjects,
                wiki_subject_provenance=provenance,
                currency=KALSHI_CURRENCY,
                source="imported",
                created_at_ms=row.created_at_ms,
                close_at_ms=row.close_at_ms,
                resolved_at_ms=resolved_at_ms,
                resolution=row.resolution,
                resolution_source="venue",
                event_key=row.event_key,
                interval_min=interval_min,
                bars=bars,
                trades=trades,
                first_price_bp=first_price_bp,
                final_price_bp=bars[-1].close_bp,
                hardness_tags=(),
                quality=_quality(
                    row=row,
                    bars=bars,
                    trades=trades,
                    created_at_ms=row.created_at_ms,
                    end_ms=resolved_at_ms,
                ),
                fee_schedule_id=KALSHI_FEE_SCHEDULE_ID,
                notes=(
                    "Imported from the Kalshi trade API v2, "
                    f"{'historical' if historical else 'live'} candlestick path."
                ),
            )
        )
    return tuple(sort_markets(markets))


def list_open_kalshi(
    *,
    client: HttpClient,
    now_ms: int,
    limit: int | None = None,
    interval_min: int = 1_440,
    series_allow_list: Sequence[str] | None = None,
) -> tuple[OpenMarket, ...]:
    """The Kalshi markets that are open at ``now_ms``, with the tape completed bars only (L1, 7.12).

    An open market has no outcome, so it never enters a dataset; what L1 needs from it is the as-of state a
    forecast is made against. The bars therefore stop at the last bar that finished before ``now_ms``, and
    ``last_price_bp`` is that bar's close, or ``first_price_bp`` when the market has no completed bar at
    all (CONTRACTS_V2 5.4, ruling R11). The live candlestick path is the only one that can answer here:
    an open market is by definition past the historical cutoff.
    """
    _check_interval(interval_min)
    allow_list = tuple(series_allow_list) if series_allow_list is not None else KALSHI_ALLOWED_SERIES
    step_ms = interval_ms(interval_min)
    rows = _list_rows(
        client, path=_MARKETS_PATH, params={"status": "open", "limit": KALSHI_MARKETS_PAGE_LIMIT}
    )
    open_markets: list[OpenMarket] = []
    for row in sorted(rows, key=lambda entry: entry.ticker):
        if limit is not None and len(open_markets) >= limit:
            break
        if is_excluded_ticker(row.ticker, allow_list=allow_list) or row.created_at_ms >= now_ms:
            continue
        t_first_ms = bar_of(row.created_at_ms, interval_min)
        t_last_ms = bar_of(now_ms, interval_min) - step_ms
        candles = (
            _candlesticks(
                client,
                row=row,
                interval_min=interval_min,
                start_ms=t_first_ms,
                end_ms=t_last_ms,
                historical=False,
            )
            if t_last_ms >= t_first_ms
            else {}
        )
        trades = _trades(client, ticker=row.ticker, end_ms=now_ms)
        first_price_bp = _first_price_bp(row, candles, trades)
        if first_price_bp is None:
            continue
        bars = (
            _bars(
                candles=candles,
                trades=trades,
                interval_min=interval_min,
                t_first_ms=t_first_ms,
                t_last_ms=t_last_ms,
                first_price_bp=first_price_bp,
            )
            if t_last_ms >= t_first_ms
            else ()
        )
        subjects, _provenance = wiki_subjects_of(row.series, row.question)
        open_markets.append(
            OpenMarket(
                id=f"{KALSHI_PROVIDER}-{row.ticker}",
                provider=KALSHI_PROVIDER,
                provider_id=row.ticker,
                url=_url_of(row.series, row.event_key),
                question=row.question,
                description=row.description,
                category=row.category,
                tags=_tags_of(row.series, row.category),
                wiki_subjects=subjects,
                currency=KALSHI_CURRENCY,
                created_at_ms=row.created_at_ms,
                close_at_ms=row.close_at_ms,
                interval_min=interval_min,
                bars=bars,
                first_price_bp=first_price_bp,
                last_price_bp=bars[-1].close_bp if bars else first_price_bp,
                quality=_quality(
                    row=row, bars=bars, trades=trades, created_at_ms=row.created_at_ms, end_ms=now_ms
                ),
                fee_schedule_id=KALSHI_FEE_SCHEDULE_ID,
            )
        )
    return tuple(open_markets)
