"""GDELT DOC 2.0: the wire of the last three months, for the recent tail of a window.

GDELT is the only source here that answers with a machine-readable list of articles for an arbitrary day, and
it is also the most fragile. Two of its documented limits are load-bearing and are enforced in this module
rather than trusted to a caller:

- **one request every five seconds.** Go faster and the API answers ``429`` with a plain-text warning rather
  than JSON. That is not a crash-worthy event, it is the API asking to be left alone, so it is a soft failure
  that returns no items. The client's throttle is what actually prevents it, and because the client is
  constructed by D6 this module checks the interval it was handed and refuses a client that would earn the
  project a ban;
- **a rolling three-month window.** Older days answer with an empty list or a warning, never with data, so a
  day outside the window returns nothing without spending a request. A 365-day dataset therefore gets GDELT
  coverage on its last quarter and Wikipedia coverage throughout, which is why ``news_sources`` defaults to
  the Wikipedia sources (section 7.4) and GDELT is opt-in.

The response body is read as text and parsed here, deliberately: a plain-text warning where JSON was promised
is the API's normal way of saying no, and it must land in the same soft path as a 429.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import time
from typing import TYPE_CHECKING, Final

from pmx.data.news.linker import NEWS_HEADLINE_MAX, NEWS_URL_MAX, clip
from pmx.errors import InvalidConfigError, MalformedResponseError, ProviderError
from pmx.types import MS_PER_DAY, SAFETY_LAG_MS_DEFAULT, NewsItem

if TYPE_CHECKING:  # the one client of section 7.11; imported for the annotation only
    from pmx.data.importers._http import HttpClient

#: The host D6 builds the client for, and the DOC 2.0 endpoint relative to it.
GDELT_BASE_URL: Final = "https://api.gdeltproject.org"
#: The host every path in this module is relative to. ``pmx.cli_data`` builds the shared client from
#: this constant, so the URL exists once in the repository (ruling R96).
BASE_URL: Final = GDELT_BASE_URL
GDELT_DOC_PATH: Final = "/api/v2/doc/doc"

#: One request every five seconds, which is GDELT's documented rate for the DOC API.
GDELT_MIN_INTERVAL_MS: Final = 5_000

#: The rolling window DOC 2.0 serves. Ninety-two days is the longest three-month span.
GDELT_WINDOW_DAYS: Final = 92

#: Articles per day. The API caps ``maxrecords`` at 250; seventy-five wire stories is a day's front section.
GDELT_MAX_RECORDS: Final = 75

#: The default query. DOC refuses an empty one, so the breadth comes from a domain list plus the language
#: filter: the dataset's markets, the lexicons and ``news.v1``'s ``lang`` are all English.
GDELT_QUERY: Final = (
    "sourcelang:english (domainis:reuters.com OR domainis:apnews.com OR domainis:bbc.co.uk)"
)

#: GDELT stamps an article with ``yyyymmddThhmmssZ``.
SEENDATE_RE: Final = re.compile(r"^([0-9]{4})([0-9]{2})([0-9]{2})T([0-9]{2})([0-9]{2})([0-9]{2})Z$")

#: The plain-text warnings the API returns with a 200 when it declines to answer.
WARNING_PREFIXES: Final = ("your query", "warning", "error", "no results", "timespan")


def fetch_gdelt(
    *,
    client: HttpClient,
    day_start_ms: int,
    safety_lag_ms: int = SAFETY_LAG_MS_DEFAULT,
    query: str = GDELT_QUERY,
    now_ms: int | None = None,
) -> tuple[NewsItem, ...]:
    """One day of GDELT wire articles as ``article`` items, or nothing at all (section 7.12).

    Nothing at all happens on four legal paths: the day is older than the API's window, the API declined
    (429 or a plain-text warning), it answered with no articles, or every article it named fell outside the
    day. ``now_ms`` exists so a test can pin the window without moving the machine's clock; production leaves
    it unset and the wall clock of the fetch decides, which is legal at the impure edge (section 7.11).
    """
    _check_throttle(client)
    reference_ms = _fetched_at_ms() if now_ms is None else now_ms
    if day_start_ms < reference_ms - GDELT_WINDOW_DAYS * MS_PER_DAY:
        return ()
    day = _yyyymmdd(day_start_ms)
    day_end_ms = day_start_ms + MS_PER_DAY
    articles = _articles(
        client,
        params={
            "query": query,
            "mode": "artlist",
            "format": "json",
            "maxrecords": GDELT_MAX_RECORDS,
            "sort": "datedesc",
            "startdatetime": f"{day}000000",
            "enddatetime": f"{day}235959",
        },
    )
    fetched_at_ms = _fetched_at_ms()
    rows: list[tuple[int, str, str]] = []
    for article in articles:
        url = article.get("url")
        title = article.get("title")
        seendate = article.get("seendate")
        language = article.get("language")
        if not isinstance(url, str) or not isinstance(title, str) or not isinstance(seendate, str):
            continue
        if isinstance(language, str) and language.strip().lower() not in {"english", "en"}:
            continue
        headline = clip(" ".join(title.split()), NEWS_HEADLINE_MAX)
        if not headline:
            continue
        published_at_ms = _seendate_ms(seendate)
        if published_at_ms is None or not day_start_ms <= published_at_ms < day_end_ms:
            continue
        rows.append((published_at_ms, url, headline))
    # The API's own order wobbles between calls; the id of an item must not. Sorting by the two fields the
    # payload guarantees makes the index positional in a sense that survives a refetch.
    rows.sort(key=lambda row: (row[0], row[1]))
    items: list[NewsItem] = []
    for published_at_ms, url, headline in rows:
        items.append(
            NewsItem(
                schema_version="news.v1",
                news_id=f"gd-{day}-{len(items):04d}",
                source="gdelt",
                kind="article",
                published_at_ms=published_at_ms,
                revid=None,
                asof_day=None,
                visible_from_ms=published_at_ms + safety_lag_ms,
                fetched_at_ms=fetched_at_ms,
                url=clip(url, NEWS_URL_MAX),
                headline=headline,
                # DOC's article list carries a title and no body, and this module does not fetch the page:
                # the headline is the signal and the URL is the provenance.
                text="",
                section=None,
                wiki_links=(),
                source_urls=(clip(url, NEWS_URL_MAX),),
                match_ids=(),
                match_scores_permille=(),
                lang="en",
                author_key=None,
            )
        )
    return tuple(items)


def _check_throttle(client: HttpClient) -> None:
    """Refuse a client throttled faster than GDELT's documented rate.

    The client is built by the caller (section 7.12), so this is the only place that can catch the mistake
    before the API does, and the API's answer to it is a temporary ban rather than an error message."""
    if client.min_interval_ms < GDELT_MIN_INTERVAL_MS:
        raise InvalidConfigError(
            "the gdelt client must be throttled to one request per five seconds",
            min_interval_ms=client.min_interval_ms,
            required_ms=GDELT_MIN_INTERVAL_MS,
        )


def _articles(client: HttpClient, *, params: dict[str, str | int]) -> tuple[dict[str, object], ...]:
    """The ``articles`` array of a DOC response, empty on every way the API has of declining."""
    try:
        body = client.get_text(GDELT_DOC_PATH, params)
    except ProviderError:
        return ()
    stripped = body.strip()
    if not stripped:
        return ()
    if not stripped.startswith("{"):
        # A plain-text warning where JSON was promised: the API declining, not a broken contract.
        return ()
    lowered = stripped.lower()
    if any(lowered.startswith(prefix) for prefix in WARNING_PREFIXES):
        return ()
    try:
        payload = json.loads(stripped)
    except ValueError:
        return ()
    if not isinstance(payload, dict):
        raise MalformedResponseError("gdelt response is not an object")
    articles = payload.get("articles")
    if articles is None:
        return ()
    if not isinstance(articles, list):
        raise MalformedResponseError("gdelt articles is not a list")
    return tuple(article for article in articles if isinstance(article, dict))


def _seendate_ms(seendate: str) -> int | None:
    """A ``yyyymmddThhmmssZ`` stamp as epoch milliseconds, or ``None`` when it is not one."""
    match = SEENDATE_RE.match(seendate.strip())
    if match is None:
        return None
    year, month, day, hour, minute, second = (int(part) for part in match.groups())
    try:
        date = dt.date(year, month, day)
    except ValueError:
        return None
    days = (date - dt.date(1970, 1, 1)).days
    return days * MS_PER_DAY + ((hour * 60 + minute) * 60 + second) * 1_000


def _yyyymmdd(t_ms: int) -> str:
    return (dt.date(1970, 1, 1) + dt.timedelta(days=t_ms // MS_PER_DAY)).strftime("%Y%m%d")


def _fetched_at_ms() -> int:
    """The wall clock of the fetch, which ``news.v1`` stores (section 7.3): a dataset is built, not run."""
    return time.time_ns() // 1_000_000
