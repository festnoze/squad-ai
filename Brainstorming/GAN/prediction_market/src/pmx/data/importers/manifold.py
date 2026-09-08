"""Manifold Markets importer: resolved binary markets with their full bet tape (CONTRACTS_V2 7.2, 7.12).

Manifold is the one provider that publishes *every* print. ``/v0/bets`` pages the complete history of a
contract, each bet carrying the probability before and after it, so a market's price path can be rebuilt
exactly instead of being interpolated from candles. That is why this importer exists next to the Kalshi
one even though the money is play money: the tape is honest, the resolutions are dated, and a forecaster
that cannot beat a mana market will not beat a dollar one.

Three decisions in here are worth the reader's time.

**No float ever touches a price.** The API answers with JSON *numbers* (``"probAfter": 0.9791195212815591``),
not with the decimal strings section 7.2 assumed, and ``json.loads`` would turn them into binary floats
before this module could object. So the body is read as text through the one HTTP client and parsed with
``parse_float=Decimal``: the digits the venue sent are the digits that get rounded, once, by
``round_half_up_decimal``, and a float reaching a conversion is a ``MalformedResponseError`` rather than a
silent rounding difference between two machines.

**Bars come from the tape, through D6's one resampler.** Manifold serves no candles and a ``Market`` is
invalid without dense bars (section 7.2), so the importer resamples its own prints with
``pmx.data.resample.bars_from_trades`` (section 5.2). Section 7.12 declares no signature for it, so this
module codes against the one D6 wrote rather than keeping a second copy of the arithmetic: two spellings
of "which print closes this bar" would mean the bars shipped in a market file and the bars the builder
recomputes from that file's own ``trades`` array could disagree.

**A creator-resolved market is kept, and says so.** Section 7.4 asks for Manifold markets to be refused
when ``resolverId == creatorId``, but on this venue that is the normal case (every one of the twenty most
recently resolved binary markets read on 2026-09-07 was resolved by its own creator), so applying it here
would return an empty provider. The importer instead records the fact in the contracted
``resolution_source`` field (``"creator"`` or ``"venue"``) and leaves the decision and the count to D6,
whose ``BuildConfig.exclude_self_resolved`` is where a filter belongs. Everything a ``Market`` cannot
represent *is* refused here: a non-binary contract, a ``MKT`` / ``CANCEL`` / free-form resolution, a
sweepstakes (``CASH``) contract, a market outside the window or after the freeze, a market whose life does
not span two bars, and a market with no print at all.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping, Sequence
from decimal import Decimal
from typing import TYPE_CHECKING, Final

from pmx.data.importers._http import evenly_spaced
from pmx.data.news.linker import derived_subjects_of, load_stopwords, merge_subjects
from pmx.data.news.manifold_comments import flatten_prosemirror, wikipedia_titles
from pmx.data.resample import bars_from_trades, traded_bars, volume_milli_total
from pmx.errors import InvalidConfigError, MalformedResponseError
from pmx.types import (
    INTERVALS_MIN,
    MS_PER_DAY,
    PPM_ONE,
    RE_TAG,
    Bar,
    Market,
    MarketQuality,
    OpenMarket,
    Trade,
    bar_of,
    bp_from_ppm,
    interval_ms,
    round_half_up_decimal,
    sort_markets,
)

if TYPE_CHECKING:  # the client is passed in by D6; this module never constructs one (section 7.12)
    from pmx.data.importers._http import HttpClient

PROVIDER: Final = "manifold"
MANIFOLD_BASE_URL: Final = "https://api.manifold.markets"
MANIFOLD_MIN_INTERVAL_MS: Final = 1_000
SEARCH_PATH: Final = "/v0/search-markets"
MARKET_PATH: Final = "/v0/market"
BETS_PATH: Final = "/v0/bets"

#: Page sizes. The venue caps both at 1 000; the search pages are kept smaller so a window that ends early
#: costs less, and both are plain module constants so a test can drive the pagination loop against a
#: recorded fixture instead of a thousand rows.
SEARCH_PAGE_LIMIT: int = 100

#: The page size of the resolved walk. The venue serves a thousand rows a page and the walk pages by
#: creation instant, so a twelve-month window is twelve requests instead of a hundred and twenty.
SEARCH_RESOLVED_PAGE_LIMIT: Final = 1_000

#: How far before the window a resolved market may have been created and still be worth staging. It is
#: section 7.4's ``opened_early_days`` default: a market created earlier is removed by the builder, so
#: fetching its tape buys nothing. ``import_manifold(created_floor_ms=...)`` overrides it, and the CLI
#: passes the build's own ``opened_early_days`` so that the two cannot disagree.
MANIFOLD_CREATED_SLACK_MS: Final = 90 * MS_PER_DAY

#: The venue refuses ``offset > 1000`` on ``/v0/search-markets``. The open listing of L1 pages by offset
#: and stops here rather than asking for a refusal.
SEARCH_OFFSET_MAX: Final = 1_000
BETS_PAGE_LIMIT: int = 1_000
#: Loop guards: a provider that never stops answering must not spin forever.
SEARCH_MAX_PAGES: Final = 400
BETS_MAX_PAGES: Final = 400

MANIFOLD_INTERVAL_MIN: Final = 1_440


def check_interval_min(interval_min: int) -> None:
    """Refuse a grid that is not one of the two of section 5.3 before a single request goes out."""
    if interval_min not in INTERVALS_MIN:
        raise InvalidConfigError("interval_min is not a dataset grid", interval_min=interval_min)

MANIFOLD_CURRENCY: Final = "mana"
MANIFOLD_FEE_SCHEDULE_ID: Final = "manifold-zero-2026-09"
MANIFOLD_TOKEN_MANA: Final = "MANA"
MANIFOLD_OUTCOME_TYPE: Final = "BINARY"

#: ``resolution_source`` values (section 7.2, "the venue's stated source"). ``creator`` is the marker D6's
#: ``exclude_self_resolved`` filter reads, because ``resolverId`` has no field on a ``Market``.
RESOLUTION_SOURCE_CREATOR: Final = "creator"
RESOLUTION_SOURCE_VENUE: Final = "venue"

#: Why a candidate was refused. :func:`classify_lite_market` returns one of these so D6 can count what it
#: did not receive: the ``import_manifold`` signature of section 7.12 returns markets and nothing else.
#: ``no_tape`` is the one reason that needs the bet tape, so it is what a ``None`` from
#: :func:`build_market` means.
EXCLUDE_NOT_BINARY: Final = "not_binary"
EXCLUDE_UNRESOLVED: Final = "unresolved"
EXCLUDE_RESOLUTION: Final = "resolution"
EXCLUDE_NOT_MANA: Final = "not_mana"
EXCLUDE_WINDOW: Final = "window"
EXCLUDE_FREEZE: Final = "freeze"
EXCLUDE_TOO_SHORT: Final = "too_short"
EXCLUDE_NO_TAPE: Final = "no_tape"

#: The two resolutions a binary outcome can carry. ``MKT``, ``CANCEL``, ``N/A`` and the free-form answer
#: ids a multiple-choice contract resolves to are refused (section 7.4).
RESOLUTION_YES: Final = "YES"
RESOLUTION_NO: Final = "NO"

QUESTION_MAX: Final = 500
DESCRIPTION_MAX: Final = 4_000
TAGS_MAX: Final = 16
WIKI_SUBJECTS_MAX: Final = 8
EVENT_KEY_MAX_CHARS: Final = 128
PROVIDER_ID_MAX_CHARS: Final = 128
TRUNCATION_MARK: Final = "..."

#: The per-provider category table of section 2, matched against a market's ``groupSlugs``. The order is
#: the table's own: the first row whose slug the market carries wins, so a market tagged both ``ai`` and
#: ``politics-default`` lands where the more specific row says. Manifold's ``-default`` slugs are the
#: venue's own top-level topics; the rest are the high-traffic groups those do not cover.
MANIFOLD_CATEGORY_BY_GROUP_SLUG: Final[tuple[tuple[str, str], ...]] = (
    ("elections", "politics"),
    ("us-politics", "politics"),
    ("politics-default", "politics"),
    ("geopolitics", "world"),
    ("wars", "world"),
    ("world-default", "world"),
    ("crypto-prices", "crypto"),
    ("crypto", "crypto"),
    ("bitcoin", "crypto"),
    ("stocks", "finance"),
    ("finance", "finance"),
    ("economics-default", "economics"),
    ("macroeconomics", "economics"),
    ("inflation", "economics"),
    ("ai", "tech"),
    ("technology-default", "tech"),
    ("space", "science"),
    ("science-default", "science"),
    ("mathematics", "science"),
    ("health", "health"),
    ("medicine", "health"),
    ("public-health", "health"),
    ("climate", "weather"),
    ("weather", "weather"),
    ("sports-default", "sports"),
    ("football", "sports"),
    ("soccer", "sports"),
    ("nfl", "sports"),
    ("nba", "sports"),
    ("mlb", "sports"),
    ("chess", "sports"),
    ("movies", "entertainment"),
    ("music", "entertainment"),
    ("tv-shows", "entertainment"),
    ("culture-default", "entertainment"),
    ("gaming", "entertainment"),
)
CATEGORY_FALLBACK: Final = "other"


# --------------------------------------------------------------------------------------------------
# Payload readers: every field is read once, typed, and blamed by name when it is not what it should be
# --------------------------------------------------------------------------------------------------
def _refuse_constant(name: str) -> object:
    raise MalformedResponseError("manifold sent a JSON constant", provider=PROVIDER, constant=name)


def parse_body(body: str, *, what: str) -> object:
    """Parse a Manifold response body keeping every number exact.

    ``parse_float=Decimal`` is the whole point: a probability or a mana amount must reach
    ``round_half_up_decimal`` as the digits the venue wrote, never as a binary float (section 7.2, R20).
    ``NaN`` and ``Infinity``, which JavaScript can emit and JSON cannot carry, are refused rather than
    turned into a price.
    """
    try:
        return json.loads(body, parse_float=Decimal, parse_constant=_refuse_constant)
    except ValueError as error:
        raise MalformedResponseError(
            "manifold sent a body that is not JSON", provider=PROVIDER, what=what, detail=str(error)
        ) from error


def _rows(payload: object, *, what: str) -> tuple[Mapping[str, object], ...]:
    if not isinstance(payload, list):
        raise MalformedResponseError(
            "manifold sent no list", provider=PROVIDER, what=what, got=type(payload).__name__
        )
    rows: list[Mapping[str, object]] = []
    for index, row in enumerate(payload):
        if not isinstance(row, dict):
            raise MalformedResponseError(
                "manifold sent a non-object row", provider=PROVIDER, what=what, index=index, got=type(row).__name__
            )
        rows.append(row)
    return tuple(rows)


def _object(payload: object, *, what: str) -> Mapping[str, object]:
    if not isinstance(payload, dict):
        raise MalformedResponseError(
            "manifold sent no object", provider=PROVIDER, what=what, got=type(payload).__name__
        )
    return payload


def _string(row: Mapping[str, object], key: str, *, what: str) -> str:
    value = row.get(key)
    if not isinstance(value, str):
        raise MalformedResponseError("manifold field is not a string", provider=PROVIDER, what=what, field=key)
    return value


def _optional_string(row: Mapping[str, object], key: str) -> str | None:
    value = row.get(key)
    return value if isinstance(value, str) else None


def _integer(row: Mapping[str, object], key: str, *, what: str) -> int:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise MalformedResponseError("manifold field is not an integer", provider=PROVIDER, what=what, field=key)
    return value


def _optional_integer(row: Mapping[str, object], key: str) -> int | None:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _decimal(row: Mapping[str, object], key: str, *, what: str) -> Decimal:
    """Read a number as an exact ``Decimal``, refusing a float outright.

    A float here means the body was parsed by something other than :func:`parse_body`, which is the one
    way a price could differ by a bit between two machines. That is a malformed response, not a rounding
    question.
    """
    value = row.get(key)
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        raise MalformedResponseError("manifold field is not a number", provider=PROVIDER, what=what, field=key)
    if isinstance(value, int):
        return Decimal(value)
    raise MalformedResponseError(
        "manifold field is not an exact number",
        provider=PROVIDER,
        what=what,
        field=key,
        got=type(value).__name__,
    )


def _flag(row: Mapping[str, object], key: str) -> bool:
    return row.get(key) is True


def _group_slugs(row: Mapping[str, object]) -> tuple[str, ...]:
    raw = row.get("groupSlugs")
    if not isinstance(raw, list):
        return ()
    return tuple(slug for slug in raw if isinstance(slug, str) and slug)


# --------------------------------------------------------------------------------------------------
# Unit conversions (section 7.2: Decimal in, integer out, never a float)
# --------------------------------------------------------------------------------------------------
def price_bp_from_prob(prob: Decimal) -> int:
    """A Manifold probability (``0.4187``) as a tradable price in basis points (``4_187``)."""
    return bp_from_ppm(round_half_up_decimal(prob * PPM_ONE))


def size_milli_from_amount(amount: Decimal) -> int:
    """A mana ``amount`` as thousandths of a mana, sign dropped: a sale is a print of the same size."""
    return round_half_up_decimal(abs(amount) * 1_000)


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - len(TRUNCATION_MARK)] + TRUNCATION_MARK


def category_of(group_slugs: Sequence[str]) -> str:
    """The category of section 2 for a market's group slugs, ``other`` when the table knows none."""
    carried = set(group_slugs)
    for slug, category in MANIFOLD_CATEGORY_BY_GROUP_SLUG:
        if slug in carried:
            return category
    return CATEGORY_FALLBACK


def tags_of(group_slugs: Sequence[str]) -> tuple[str, ...]:
    """The market's group slugs that are legal tags (section 7.2), sorted, unique, at most sixteen."""
    kept = {slug for slug in group_slugs if RE_TAG.match(slug) is not None}
    return tuple(sorted(kept)[:TAGS_MAX])


def description_text(full: Mapping[str, object]) -> tuple[str, tuple[str, ...]]:
    """The market's resolution criteria as plain text, plus every link it carries.

    Manifold serves a plain ``textDescription`` beside the ProseMirror document and it is the venue's own
    flattening, so it wins; the document is still walked for its hyperlinks, which is where the Wikipedia
    subjects of a well-written market live.
    """
    flattened, links = flatten_prosemirror(full.get("description"))
    plain = full.get("textDescription")
    text = plain if isinstance(plain, str) and plain.strip() else flattened
    return text.strip(), links


# --------------------------------------------------------------------------------------------------
# Candidate classification (cheap: it reads the search payload and asks the network nothing)
# --------------------------------------------------------------------------------------------------
def is_self_resolved(lite: Mapping[str, object]) -> bool:
    """Did the market's own creator resolve it? The fact behind ``resolution_source`` (section 7.4)."""
    resolver = _optional_string(lite, "resolverId")
    creator = _optional_string(lite, "creatorId")
    return resolver is not None and resolver == creator


def close_at_ms_of(lite: Mapping[str, object], *, resolved_at_ms: int) -> int:
    """The venue's published close, never after settlement (section 7.2: ``close_at_ms <= resolved_at_ms``).

    Manifold lets a creator resolve a market before its close date and leaves ``closeTime`` in the future.
    Left alone, ``tradable(m, t)`` (section 5.3) would let an agent trade the settling day, which is the
    one bar that carries prints made after the outcome was known, so the close is clamped here, once, at
    import.
    """
    published = _optional_integer(lite, "closeTime")
    if published is None:
        return resolved_at_ms
    return min(published, resolved_at_ms)


def classify_lite_market(
    lite: Mapping[str, object],
    *,
    window_start_ms: int,
    window_end_ms: int,
    freeze_ms: int,
    interval_min: int = MANIFOLD_INTERVAL_MIN,
) -> str | None:
    """The reason ``lite`` cannot enter a dataset, or ``None`` when it can.

    Public because ``import_manifold`` returns markets only (section 7.12) while D6's
    ``manifest.filters.removed`` needs the counts: the builder can classify the same payloads it handed
    over, or the gate can wire this function into the loop.

    ``interval_min`` is the dataset's grid (ruling R93): whether a contract's life covers the two bars a
    ``Market`` needs is a question about the grid, and on an hourly dataset a contract that lived four
    hours is admissible while on a daily one it is not.
    """
    check_interval_min(interval_min)
    if _string(lite, "outcomeType", what="search-markets") != MANIFOLD_OUTCOME_TYPE:
        return EXCLUDE_NOT_BINARY
    token = _optional_string(lite, "token")
    if token is not None and token != MANIFOLD_TOKEN_MANA:
        return EXCLUDE_NOT_MANA
    if not _flag(lite, "isResolved"):
        return EXCLUDE_UNRESOLVED
    if _optional_string(lite, "resolution") not in (RESOLUTION_YES, RESOLUTION_NO):
        return EXCLUDE_RESOLUTION
    resolved_at_ms = _optional_integer(lite, "resolutionTime")
    if resolved_at_ms is None:
        return EXCLUDE_UNRESOLVED
    if resolved_at_ms >= freeze_ms:
        return EXCLUDE_FREEZE
    if not window_start_ms <= resolved_at_ms < window_end_ms:
        return EXCLUDE_WINDOW
    created_at_ms = _integer(lite, "createdTime", what="search-markets")
    if created_at_ms >= close_at_ms_of(lite, resolved_at_ms=resolved_at_ms):
        return EXCLUDE_TOO_SHORT
    if bar_of(created_at_ms, interval_min) >= bar_of(resolved_at_ms, interval_min):
        return EXCLUDE_TOO_SHORT  # a Market carries at least two bars (section 7.2)
    return None


# --------------------------------------------------------------------------------------------------
# Fetching
# --------------------------------------------------------------------------------------------------
def _search_page(
    client: HttpClient,
    *,
    limit: int,
    market_filter: str,
    sort: str,
    offset: int | None = None,
    before_time_ms: int | None = None,
) -> tuple[Mapping[str, object], ...]:
    """One page of ``/v0/search-markets``, paged by offset or by creation instant.

    The venue caps ``offset`` at 1 000 and says so in the refusal it answers above it: "offset must be
    <= 1000. Use sort=newest with the beforeTime parameter to page through contracts". So a walk that has
    to reach further than two thousand rows pages by ``beforeTime`` instead, which is a bound on
    ``createdTime`` and has no depth limit.
    """
    params: dict[str, str | int] = {
        "term": "",
        "filter": market_filter,
        "sort": sort,
        "contractType": MANIFOLD_OUTCOME_TYPE,
        "limit": limit,
    }
    if offset is not None:
        params["offset"] = offset
    if before_time_ms is not None:
        params["beforeTime"] = before_time_ms
    body = client.get_text(SEARCH_PATH, params)
    return _rows(parse_body(body, what="search-markets"), what="search-markets")


def _iter_resolved_lite(
    client: HttpClient, *, created_floor_ms: int
) -> Iterator[Mapping[str, object]]:
    """Every resolved binary mana market created at or after ``created_floor_ms``, newest creation first.

    The walk is by **creation** instant and not by resolution, because the venue refuses
    ``offset > 1000`` and the resolution-ordered listing is only reachable through ``offset``: the
    previous spelling could see the two thousand most recent resolutions, about forty-five days, and a
    twelve-month window asked for page eleven and got ``400 offset must be <= 1000. Use sort=newest with
    the beforeTime parameter to page through contracts`` (measured on 2026-09-08, which is what made this
    walk necessary). ``sort=newest`` with ``beforeTime`` pages by creation with no depth limit at all:
    measured the same day, twelve pages of a thousand rows cover every resolved binary market created in
    the last 455 days in nineteen seconds, and 10 373 of them resolved inside the window.

    The floor is a creation bound and therefore does not lose a market the dataset could keep: section
    7.4's ``opened_early`` filter drops a market created more than ``opened_early_days`` before the
    window, so a market below the floor would be removed by the builder anyway. The one consequence to
    read in the manifest is that such markets are no longer staged and so no longer counted there.

    Each page's oldest creation is the next page's bound, and a page whose rows all share that instant
    steps one millisecond further back rather than asking for the same page again. Ids already seen are
    dropped, so a row on a page boundary is yielded once.
    """
    before_time_ms: int | None = None
    seen: set[str] = set()
    for _page_index in range(SEARCH_MAX_PAGES):
        page = _search_page(
            client,
            limit=SEARCH_RESOLVED_PAGE_LIMIT,
            market_filter="resolved",
            sort="newest",
            before_time_ms=before_time_ms,
        )
        if not page:
            return
        oldest_created_ms: int | None = None
        for lite in page:
            created_at_ms = _optional_integer(lite, "createdTime")
            if created_at_ms is not None:
                oldest_created_ms = (
                    created_at_ms if oldest_created_ms is None else min(oldest_created_ms, created_at_ms)
                )
            if created_at_ms is not None and created_at_ms < created_floor_ms:
                continue
            market_id = _optional_string(lite, "id")
            if market_id is None or market_id in seen:
                continue
            seen.add(market_id)
            yield lite
        if oldest_created_ms is None or oldest_created_ms < created_floor_ms:
            return
        if before_time_ms is not None and oldest_created_ms >= before_time_ms:
            before_time_ms -= 1
        else:
            before_time_ms = oldest_created_ms
        if len(page) < SEARCH_RESOLVED_PAGE_LIMIT:
            return


def fetch_full_market(client: HttpClient, provider_id: str) -> Mapping[str, object]:
    """The full contract payload: the resolution criteria and the group slugs the search result omits."""
    body = client.get_text(f"{MARKET_PATH}/{provider_id}", None)
    return _object(parse_body(body, what="market"), what="market")


def fetch_bets(client: HttpClient, provider_id: str) -> tuple[Mapping[str, object], ...]:
    """Every bet of a contract, oldest first.

    ``/v0/bets`` answers newest first and pages with ``before=<betId>``, exclusive, so the walk carries
    the last id of each page and reverses the whole tape once at the end. The venue's own order is kept
    inside a millisecond: two bets stamped the same ``createdTime`` open and close a bar in the order the
    venue lists them, which is the only tie-break that exists.
    """
    pages: list[tuple[Mapping[str, object], ...]] = []
    before: str | None = None
    for _ in range(BETS_MAX_PAGES):
        params: dict[str, str | int] = {"contractId": provider_id, "limit": BETS_PAGE_LIMIT}
        if before is not None:
            params["before"] = before
        page = _rows(parse_body(client.get_text(BETS_PATH, params), what="bets"), what="bets")
        if not page:
            break
        pages.append(page)
        before = _string(page[-1], "betId", what="bets")
        if len(page) < BETS_PAGE_LIMIT:
            break
    return tuple(reversed([bet for page in pages for bet in page]))


# --------------------------------------------------------------------------------------------------
# The tape
# --------------------------------------------------------------------------------------------------
def trades_from_bets(
    bets: Sequence[Mapping[str, object]], *, start_ms: int, end_ms: int
) -> tuple[Trade, ...]:
    """The prints of a bet tape in ``[start_ms, end_ms]``, in the venue's chronological order.

    A bet is a print when it moved mana: a redemption (the automatic YES plus NO merge), a cancelled or
    unfilled limit order, the creation ante and any bet whose amount rounds below a thousandth of a mana
    are not trades, and counting them would fabricate volume at a price nobody paid. ``probAfter`` is the
    print price (the tape's own mark after the bet) and ``|amount|`` its size.
    """
    trades: list[Trade] = []
    for bet in bets:
        if _flag(bet, "isRedemption") or _flag(bet, "isCancelled") or _flag(bet, "isAnte"):
            continue
        t_ms = _integer(bet, "createdTime", what="bets")
        if not start_ms <= t_ms <= end_ms:
            continue
        size_milli = size_milli_from_amount(_decimal(bet, "amount", what="bets"))
        if size_milli < 1:
            continue
        trades.append(
            Trade(
                t_ms=t_ms,
                price_bp=price_bp_from_prob(_decimal(bet, "probAfter", what="bets")),
                size_milli=size_milli,
                side=_side(bet),
            )
        )
    return tuple(trades)


def _side(bet: Mapping[str, object]) -> str:
    outcome = _optional_string(bet, "outcome")
    if outcome == RESOLUTION_YES:
        return "yes"
    if outcome == RESOLUTION_NO:
        return "no"
    return "unknown"


def first_price_bp_of(bets: Sequence[Mapping[str, object]]) -> int | None:
    """The market's opening quote: the probability before its very first bet (section 7.2).

    It is read from the earliest bet whatever that bet is, redemption included, because ``probBefore`` is
    a quote and not a print: it is the price the market showed before anyone traded it.
    """
    if not bets:
        return None
    return price_bp_from_prob(_decimal(bets[0], "probBefore", what="bets"))


def _quality(
    trades: Sequence[Trade], bars: Sequence[Bar], *, lite: Mapping[str, object], life_ms: int
) -> MarketQuality:
    """What the quality filters of section 7.4 read, counted off the bars the market actually carries.

    ``traded_bars`` and ``volume_milli_total`` are D6's own counters, so the density filter reads the same
    integers this file wrote. ``unique_bettors`` is the venue's number and stays ``None`` when it sent
    none: an invented count would pass a filter the market never earned.
    """
    return MarketQuality(
        n_trades=len(trades),
        unique_bettors=_optional_integer(lite, "uniqueBettorCount"),
        life_days=life_ms // MS_PER_DAY,
        volume_milli_total=volume_milli_total(bars),
        traded_bars=traded_bars(bars),
    )


def wiki_subjects_of(question: str, links: Sequence[str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """``(wiki_subjects, wiki_subject_provenance)`` for one Manifold contract (section 7.2).

    Two sources. The Wikipedia links of the resolution criteria are ``stated``: the creator wrote them,
    and they are the strongest evidence a market carries. The capitalised runs of the question itself are
    ``derived`` candidates, and they are what makes the linker work at all on this provider: of the 400
    Manifold markets staged for the first real dataset, 392 carried no stated subject, so the linker's
    dominant term was zero for effectively every market and the Wikipedia archive linked to nothing.
    """
    return merge_subjects(
        wikipedia_titles(links),
        derived_subjects_of(question, load_stopwords()),
        limit=WIKI_SUBJECTS_MAX,
    )


def _canonical_trades(trades: Sequence[Trade]) -> tuple[Trade, ...]:
    """Section 3's trade order: ``(t_ms, price_bp, size_milli, side)`` ascending."""
    return tuple(sorted(trades, key=lambda trade: (trade.t_ms, trade.price_bp, trade.size_milli, trade.side)))


# --------------------------------------------------------------------------------------------------
# The importers
# --------------------------------------------------------------------------------------------------
def market_id_of(provider_id: str) -> str:
    """``manifold-<contract id>``, section 2.

    The contract id is used rather than the slug: a Manifold slug is unique per creator, not per venue
    (the URL is ``manifold.markets/<user>/<slug>``), and some slugs are longer than the 96 characters a
    market id allows. Section 2 accepts "the provider's own id", and this one is short, stable and
    globally unique.
    """
    return f"{PROVIDER}-{provider_id}"


def build_market(
    lite: Mapping[str, object],
    full: Mapping[str, object],
    bets: Sequence[Mapping[str, object]],
    *,
    interval_min: int = MANIFOLD_INTERVAL_MIN,
) -> Market | None:
    """One ``Market`` from the three payloads a Manifold contract is made of, or ``None`` for no tape.

    Pure: every field comes from the payloads, nothing is fetched and nothing is written. ``bets`` is
    **oldest first**, the order :func:`fetch_bets` returns, because the opening quote is the ``probBefore``
    of the first row. ``None`` is :data:`EXCLUDE_NO_TAPE`: a contract whose bets moved no mana inside its
    own life has no price path to import.
    """
    resolved_at_ms = _integer(lite, "resolutionTime", what="search-markets")
    created_at_ms = _integer(lite, "createdTime", what="search-markets")
    provider_id = _string(lite, "id", what="search-markets")
    trades = trades_from_bets(bets, start_ms=created_at_ms, end_ms=resolved_at_ms)
    first_price_bp = first_price_bp_of(bets)
    if not trades or first_price_bp is None:
        return None
    check_interval_min(interval_min)
    bars = bars_from_trades(
        trades,
        interval_min=interval_min,
        start_ms=bar_of(created_at_ms, interval_min),
        end_ms=bar_of(resolved_at_ms, interval_min),
        first_price_bp=first_price_bp,
    )
    description, links = description_text(full)
    group_slugs = _group_slugs(full) or _group_slugs(lite)
    event_key = group_slugs[0] if group_slugs and len(group_slugs[0]) <= EVENT_KEY_MAX_CHARS else None
    mechanism = _optional_string(lite, "mechanism") or "unknown"
    question = _truncate(_string(lite, "question", what="search-markets"), QUESTION_MAX)
    subjects, provenance = wiki_subjects_of(question, links)
    return Market(
        schema_version="market.v2",
        id=market_id_of(provider_id),
        provider=PROVIDER,
        provider_id=provider_id[:PROVIDER_ID_MAX_CHARS],
        url=_optional_string(lite, "url") or f"{MANIFOLD_BASE_URL}/market/{provider_id}",
        question=question,
        description=_truncate(description, DESCRIPTION_MAX),
        category=category_of(group_slugs),
        tags=tags_of(group_slugs),
        wiki_subjects=subjects,
        wiki_subject_provenance=provenance,
        currency=MANIFOLD_CURRENCY,
        source="imported",
        created_at_ms=created_at_ms,
        close_at_ms=close_at_ms_of(lite, resolved_at_ms=resolved_at_ms),
        resolved_at_ms=resolved_at_ms,
        resolution=1 if _string(lite, "resolution", what="search-markets") == RESOLUTION_YES else 0,
        resolution_source=RESOLUTION_SOURCE_CREATOR if is_self_resolved(lite) else RESOLUTION_SOURCE_VENUE,
        event_key=event_key,
        interval_min=interval_min,
        bars=bars,
        trades=_canonical_trades(trades),
        first_price_bp=first_price_bp,
        final_price_bp=bars[-1].close_bp,
        hardness_tags=(),
        quality=_quality(trades, bars, lite=lite, life_ms=resolved_at_ms - created_at_ms),
        fee_schedule_id=MANIFOLD_FEE_SCHEDULE_ID,
        notes=f"manifold {mechanism}; {len(bets)} bets read",
    )


def import_manifold(
    *,
    client: HttpClient,
    window_start_ms: int,
    window_end_ms: int,
    freeze_ms: int,
    limit: int | None = None,
    interval_min: int = MANIFOLD_INTERVAL_MIN,
    created_floor_ms: int | None = None,
) -> tuple[Market, ...]:
    """Resolved Manifold binary markets settled in ``[window_start_ms, window_end_ms)``, canonical order.

    Every returned market is unsealed and incomplete by design (section 7.12): no hardness tags, no fold,
    ``quality`` filled from what the venue gave. Nothing is written to disk; D6 writes files.

    ``interval_min`` is the keyword-only extension ruling R93 adds to every importer of section 7.12, so
    that one dataset carries one grid (section 5.3) whatever provider a market came from.
    """
    check_interval_min(interval_min)
    # The listing walk is one request per thousand contracts and covers the whole window; the tape of one
    # contract is two requests or more. So the window is walked and classified first, and ``limit`` is
    # then a fetch budget spread evenly over what the walk found (:func:`evenly_spaced`) rather than a
    # break that stops the walk at the newest ``limit`` resolutions and stages thirteen days of a year.
    floor_ms = (
        window_start_ms - MANIFOLD_CREATED_SLACK_MS if created_floor_ms is None else created_floor_ms
    )
    eligible: list[Mapping[str, object]] = []
    for lite in _iter_resolved_lite(client, created_floor_ms=floor_ms):
        reason = classify_lite_market(
            lite,
            window_start_ms=window_start_ms,
            window_end_ms=window_end_ms,
            freeze_ms=freeze_ms,
            interval_min=interval_min,
        )
        if reason is None:
            eligible.append(lite)
    # Ordered by settlement before the budget is spent, so the stride of ``evenly_spaced`` spreads the
    # sample over the window's resolutions, which is what the folds of section 7.7 are cut on.
    eligible.sort(
        key=lambda lite: (
            _integer(lite, "resolutionTime", what="search-markets"),
            _string(lite, "id", what="search-markets"),
        )
    )
    markets: list[Market] = []
    for lite in evenly_spaced(eligible, limit):
        provider_id = _string(lite, "id", what="search-markets")
        market = build_market(
            lite,
            fetch_full_market(client, provider_id),
            fetch_bets(client, provider_id),
            interval_min=interval_min,
        )
        if market is None:
            continue
        markets.append(market)
    return tuple(sort_markets(markets))


def list_open_manifold(
    *,
    client: HttpClient,
    now_ms: int,
    limit: int | None = None,
    interval_min: int = MANIFOLD_INTERVAL_MIN,
) -> tuple[OpenMarket, ...]:
    """Open binary Manifold markets for L1: a tape truncated at ``now_ms``, no outcome (section 7.12).

    ``sort=close-date`` puts the markets that settle soonest first, which is the order a live forecaster
    wants, and the tape is cut to completed bars only so ``last_price_bp`` is the as-of price of section
    5.4 rather than a print the forecaster could not have seen. ``interval_min`` is the grid L1's book is
    kept on (ruling R93).
    """
    check_interval_min(interval_min)
    open_markets: list[OpenMarket] = []
    for page_index in range(SEARCH_MAX_PAGES):
        offset = page_index * SEARCH_PAGE_LIMIT
        if offset > SEARCH_OFFSET_MAX:
            return tuple(open_markets)
        page = _search_page(
            client,
            offset=offset,
            limit=SEARCH_PAGE_LIMIT,
            market_filter="open",
            sort="close-date",
        )
        for lite in page:
            market = _open_market_from(client, lite, now_ms=now_ms, interval_min=interval_min)
            if market is None:
                continue
            open_markets.append(market)
            if limit is not None and len(open_markets) >= limit:
                return tuple(open_markets)
        if len(page) < SEARCH_PAGE_LIMIT:
            break
    return tuple(open_markets)


def _open_market_from(
    client: HttpClient, lite: Mapping[str, object], *, now_ms: int, interval_min: int
) -> OpenMarket | None:
    if _string(lite, "outcomeType", what="search-markets") != MANIFOLD_OUTCOME_TYPE:
        return None
    token = _optional_string(lite, "token")
    if token is not None and token != MANIFOLD_TOKEN_MANA:
        return None
    if _flag(lite, "isResolved"):
        return None
    created_at_ms = _integer(lite, "createdTime", what="search-markets")
    close_at_ms = _optional_integer(lite, "closeTime")
    if close_at_ms is None or close_at_ms <= now_ms or created_at_ms >= close_at_ms:
        return None
    step = interval_ms(interval_min)
    start_ms = bar_of(created_at_ms, interval_min)
    last_complete_ms = bar_of(now_ms, interval_min) - step
    provider_id = _string(lite, "id", what="search-markets")
    bets = fetch_bets(client, provider_id)
    first_price_bp = first_price_bp_of(bets)
    if first_price_bp is None:
        return None
    # The tape stops at the last completed bar: a print inside the bar being decided is not as-of data,
    # and it would reach a live forecaster through `quality` even if no bar carried it (section 5.4).
    trades = trades_from_bets(bets, start_ms=created_at_ms, end_ms=last_complete_ms + step - 1)
    bars = (
        bars_from_trades(
            trades,
            interval_min=interval_min,
            start_ms=start_ms,
            end_ms=last_complete_ms,
            first_price_bp=first_price_bp,
        )
        if last_complete_ms >= start_ms
        else ()
    )
    full = fetch_full_market(client, provider_id)
    description, links = description_text(full)
    group_slugs = _group_slugs(full) or _group_slugs(lite)
    question = _truncate(_string(lite, "question", what="search-markets"), QUESTION_MAX)
    subjects, _provenance = wiki_subjects_of(question, links)
    return OpenMarket(
        id=market_id_of(provider_id),
        provider=PROVIDER,
        provider_id=provider_id[:PROVIDER_ID_MAX_CHARS],
        url=_optional_string(lite, "url") or f"{MANIFOLD_BASE_URL}/market/{provider_id}",
        question=question,
        description=_truncate(description, DESCRIPTION_MAX),
        category=category_of(group_slugs),
        tags=tags_of(group_slugs),
        wiki_subjects=subjects,
        currency=MANIFOLD_CURRENCY,
        created_at_ms=created_at_ms,
        close_at_ms=close_at_ms,
        interval_min=interval_min,
        bars=bars,
        first_price_bp=first_price_bp,
        last_price_bp=bars[-1].close_bp if bars else first_price_bp,
        quality=_quality(trades, bars, lite=lite, life_ms=now_ms - created_at_ms),
        fee_schedule_id=MANIFOLD_FEE_SCHEDULE_ID,
    )
