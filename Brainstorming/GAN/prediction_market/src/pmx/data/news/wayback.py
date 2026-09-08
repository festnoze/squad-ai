"""Front pages as they were archived on the day, through the Wayback CDX index.

What this adds over the Current events portal: an editorial signal. The portal tells you an event happened;
a front page tells you it led the news. The CDX index (``/cdx/search/cdx?url=&from=&to=&output=json``) answers
with one row per capture and no page body, which is exactly the right amount: the item stores the permanent
snapshot URL and its capture instant, so a reviewer can open the page a reader saw that morning, and the
dataset carries a pointer rather than a megabyte of someone else's HTML.

The source is optional in every sense of section 7.12 and this module treats it that way. The Internet
Archive is slow, rate-limited and sometimes down; a build spanning three hundred and sixty-five days must not
die because one day's index call failed, so a provider failure on one site drops that site's item for that
day and is not an exception. What it never does is invent a capture: no row means no item.
"""

from __future__ import annotations

import datetime as dt
import re
import time
from typing import TYPE_CHECKING, Final

from pmx.data.news.linker import NEWS_HEADLINE_MAX, NEWS_URL_MAX, clip
from pmx.errors import MalformedResponseError, ProviderError
from pmx.types import MS_PER_DAY, SAFETY_LAG_MS_DEFAULT, NewsItem

if TYPE_CHECKING:  # the one client of section 7.11; imported for the annotation only
    from pmx.data.importers._http import HttpClient

#: The host D6 builds the client for, and the politeness interval this source asks for. The CDX index is
#: served over plain HTTP; the snapshot URLs the items carry are https.
#: The host every path in this module is relative to. ``pmx.cli_data`` builds the shared client from
#: this constant, so the URL exists once in the repository (ruling R96).
WAYBACK_BASE_URL: Final = "https://web.archive.org"
BASE_URL: Final = WAYBACK_BASE_URL
WAYBACK_MIN_INTERVAL_MS: Final = 2_000

#: The CDX search endpoint, relative to the client's ``base_url``.
CDX_PATH: Final = "/cdx/search/cdx"
SNAPSHOT_URL_TEMPLATE: Final = "https://web.archive.org/web/{timestamp}/{original}"

#: The front pages asked for, in this order, which is also the order of the day's news ids. English-language
#: wire services and broadcasters, because the dataset's markets and the lexicons are English (``lang: "en"``).
WAYBACK_FRONT_PAGES: Final = (
    "reuters.com",
    "apnews.com",
    "bbc.co.uk/news",
    "npr.org",
)

#: The CDX timestamp: ``yyyymmddhhmmss``, always UTC.
CDX_TIMESTAMP_RE: Final = re.compile(
    r"^([0-9]{4})([0-9]{2})([0-9]{2})([0-9]{2})([0-9]{2})([0-9]{2})$"
)


def fetch_wayback(
    *,
    client: HttpClient,
    day_start_ms: int,
    safety_lag_ms: int = SAFETY_LAG_MS_DEFAULT,
    front_pages: tuple[str, ...] = WAYBACK_FRONT_PAGES,
) -> tuple[NewsItem, ...]:
    """The first successful capture of each front page on one day, as ``frontpage`` items (section 7.12).

    At most one item per front page and never a capture from another day, so the day key of the file D6
    writes always matches ``day_start_ms(published_at_ms)`` (section 7.1).
    """
    day = _yyyymmdd(day_start_ms)
    day_end_ms = day_start_ms + MS_PER_DAY
    items: list[NewsItem] = []
    for site in front_pages:
        capture = _first_capture(client, site=site, day=day)
        if capture is None:
            continue
        timestamp, original = capture
        published_at_ms = _timestamp_ms(timestamp)
        if not day_start_ms <= published_at_ms < day_end_ms:
            continue
        url = clip(SNAPSHOT_URL_TEMPLATE.format(timestamp=timestamp, original=original), NEWS_URL_MAX)
        items.append(
            NewsItem(
                schema_version="news.v1",
                news_id=f"wb-{day}-{len(items):04d}",
                source="wayback",
                kind="frontpage",
                published_at_ms=published_at_ms,
                revid=None,
                asof_day=None,
                visible_from_ms=published_at_ms + safety_lag_ms,
                fetched_at_ms=_fetched_at_ms(),
                url=url,
                headline=clip(f"{site} front page archived {_iso_minute(published_at_ms)}", NEWS_HEADLINE_MAX),
                # The CDX index carries no page body, and this module deliberately does not fetch one: the
                # value is the dated pointer, not a copy of a publisher's HTML.
                text="",
                section=None,
                wiki_links=(),
                source_urls=(url,),
                match_ids=(),
                match_scores_permille=(),
                lang="en",
                author_key=None,
            )
        )
    return tuple(items)


def _first_capture(client: HttpClient, *, site: str, day: str) -> tuple[str, str] | None:
    """``(timestamp, original)`` of the day's first 200 capture of ``site``, or ``None``.

    A provider failure returns ``None``: this source is optional (section 7.12) and one archive outage must
    not stop a build, and an outage page where JSON was promised is an outage. A body that **is** JSON but is
    not a CDX table is a different matter and raises, because that means the index changed shape and every
    day of every future build would be silently empty.
    """
    try:
        payload = client.get_json(
            CDX_PATH,
            {
                "url": site,
                "from": day,
                "to": day,
                "output": "json",
                "filter": "statuscode:200",
                "collapse": "timestamp:8",
                "limit": 1,
            },
        )
    except (ProviderError, MalformedResponseError):
        return None
    if payload is None:
        return None
    if not isinstance(payload, list):
        raise MalformedResponseError("cdx response is not a table", site=site, day=day)
    if len(payload) < 2:
        return None
    header = payload[0]
    if not isinstance(header, list):
        raise MalformedResponseError("cdx header is not a row", site=site, day=day)
    columns = [str(name) for name in header]
    try:
        timestamp_at = columns.index("timestamp")
        original_at = columns.index("original")
    except ValueError as exc:
        raise MalformedResponseError("cdx header has no timestamp column", site=site, day=day) from exc
    row = payload[1]
    if not isinstance(row, list) or len(row) <= max(timestamp_at, original_at):
        raise MalformedResponseError("cdx row is short", site=site, day=day)
    return (str(row[timestamp_at]), str(row[original_at]))


def _timestamp_ms(timestamp: str) -> int:
    """A CDX ``yyyymmddhhmmss`` capture instant as epoch milliseconds, integer throughout."""
    match = CDX_TIMESTAMP_RE.match(timestamp)
    if match is None:
        raise MalformedResponseError("cdx timestamp is not yyyymmddhhmmss", timestamp=timestamp)
    year, month, day, hour, minute, second = (int(part) for part in match.groups())
    try:
        date = dt.date(year, month, day)
    except ValueError as exc:
        raise MalformedResponseError("cdx timestamp is not a real date", timestamp=timestamp) from exc
    days = (date - dt.date(1970, 1, 1)).days
    return days * MS_PER_DAY + ((hour * 60 + minute) * 60 + second) * 1_000


def _iso_minute(t_ms: int) -> str:
    moment = dt.datetime(1970, 1, 1, tzinfo=dt.UTC) + dt.timedelta(milliseconds=t_ms)
    return moment.strftime("%Y-%m-%d %H:%MZ")


def _yyyymmdd(t_ms: int) -> str:
    return (dt.date(1970, 1, 1) + dt.timedelta(days=t_ms // MS_PER_DAY)).strftime("%Y%m%d")


def _fetched_at_ms() -> int:
    """The wall clock of the fetch, which ``news.v1`` stores (section 7.3): a dataset is built, not run."""
    return time.time_ns() // 1_000_000
