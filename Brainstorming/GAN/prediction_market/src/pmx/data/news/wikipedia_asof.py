"""The background article as it read on a past day, not as it reads today.

This is the highest-value fetch in the data layer and the most dangerous one. An agent forecasting "will the
United Kingdom vote to leave the European Union" is far better off with the referendum's Wikipedia article
than with a day's headlines, but the *current* article opens with the answer. So this module never asks for a
page; it asks for the newest revision that existed at 23:59:59Z of a stated day
(``rvstart=<asof_day>T23:59:59Z&rvdir=older&rvlimit=1``) and stores the ``revid`` it got, which is what makes
the snapshot auditable: a reviewer re-fetches that revision by id and compares bytes (CONTRACTS_V2 section
7.1, ruling R16).

Two guards sit on top of the API's own ordering, because "the API returned the right revision" is exactly the
assumption a leak hides behind:

- a revision stamped after the end of ``asof_day`` raises ``LeakError`` here, before it can reach a file. The
  loader repeats the check (section 7.3) and the builder repeats it against the freeze; three readings of the
  same rule is the correct number for the leak that would silently invalidate every result;
- the stored ``text`` is a byte-exact prefix of the revision's wikitext, cut at the ``news.v1`` cap with no
  ellipsis, so the identity "stored text equals the revision" is checkable at all.

D6 asks for one snapshot per seven days of market life and none at or after ``bar_of(resolved_at_ms)``
(section 7.1); this module fetches the day it is given and refuses to invent the schedule.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import re
import time
from typing import TYPE_CHECKING, Final

from pmx.data.news.linker import NEWS_HEADLINE_MAX, NEWS_TEXT_MAX, WIKI_LINKS_MAX, clip
from pmx.data.news.wikipedia_current_events import MEDIAWIKI_PATH, wiki_links_of
from pmx.errors import InvalidConfigError, LeakError, MalformedResponseError
from pmx.types import MS_PER_DAY, SAFETY_LAG_MS_DEFAULT, Market, NewsItem, bar_of, day_start_ms

if TYPE_CHECKING:  # the one client of section 7.11; imported for the annotation only
    from pmx.data.importers._http import HttpClient

#: A permanent link to one revision, which is what ``url`` carries for a snapshot.
REVISION_URL_TEMPLATE: Final = "https://en.wikipedia.org/w/index.php?oldid={revid}"

#: The host every path in this module is relative to. ``pmx.cli_data`` builds the shared client from
#: this constant, so the URL exists once in the repository (ruling R96).
WIKIPEDIA_BASE_URL: Final = "https://en.wikipedia.org"
BASE_URL: Final = WIKIPEDIA_BASE_URL
ASOF_DAY_RE: Final = re.compile(r"^([0-9]{4})-([0-9]{2})-([0-9]{2})$")
TIMESTAMP_RE: Final = re.compile(
    r"^([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})Z$"
)
#: The four digits of a news id, which a single-item fetch derives from its market and title (see below).
NEWS_ID_SLOTS: Final = 10_000

#: One snapshot per seven days of market life (section 7.1). Denser would multiply the request count by
#: seven for a background article that barely moves between two Tuesdays.
ASOF_INTERVAL_DAYS: Final = 7


def asof_days_for(market: Market) -> tuple[str, ...]:
    """The days a market's background snapshots are asked for, oldest first (section 7.1).

    Every seventh day from the market's creation day, and **none** at or after ``bar_of(resolved_at_ms)``:
    the last bar of a market's tape is the one where the outcome is public, and a revision from that day
    would state it. The schedule lives here rather than in the builder because it is the same rule as the
    leak guard below, and one rule with two spellings is one rule too many.
    """
    first_ms = day_start_ms(market.created_at_ms)
    limit_ms = bar_of(market.resolved_at_ms, market.interval_min)
    days: list[str] = []
    day_ms = first_ms
    while day_ms < limit_ms:
        days.append(_iso_day(day_ms))
        day_ms += ASOF_INTERVAL_DAYS * MS_PER_DAY
    return tuple(days)


def day_start_ms_of(asof_day: str) -> int:
    """Midnight UTC of a ``yyyy-mm-dd`` day, in epoch milliseconds, by whole-day arithmetic."""
    match = ASOF_DAY_RE.match(asof_day)
    if match is None:
        raise InvalidConfigError("asof_day is not yyyy-mm-dd", asof_day=asof_day)
    year, month, day = (int(part) for part in match.groups())
    try:
        date = dt.date(year, month, day)
    except ValueError as exc:
        raise InvalidConfigError("asof_day is not a real date", asof_day=asof_day) from exc
    return (date - dt.date(1970, 1, 1)).days * MS_PER_DAY


def timestamp_ms(timestamp: str) -> int:
    """A MediaWiki ISO-8601 UTC timestamp as epoch milliseconds, integer throughout."""
    match = TIMESTAMP_RE.match(timestamp)
    if match is None:
        raise MalformedResponseError("revision timestamp is not ISO-8601 UTC", timestamp=timestamp)
    year, month, day, hour, minute, second = (int(part) for part in match.groups())
    try:
        date = dt.date(year, month, day)
    except ValueError as exc:
        raise MalformedResponseError("revision timestamp is not a real date", timestamp=timestamp) from exc
    days = (date - dt.date(1970, 1, 1)).days
    return days * MS_PER_DAY + ((hour * 60 + minute) * 60 + second) * 1_000


def news_id_index(market_id: str, title: str) -> int:
    """The positional slot of a snapshot's news id, derived from its market and title.

    Section 2 makes a news id positional inside the day it names, but a snapshot fetch returns exactly one
    item for one market and one title, so there is no position to count: two markets whose snapshots land on
    the same revision day would both be index ``0000``. A digest of the pair the item belongs to keeps the id
    deterministic and collision-free in practice, and it is stable across runs and machines, which a counter
    held by the caller would not be. Reported as a contract issue against section 2.
    """
    digest = hashlib.sha256(f"{market_id}\n{title}".encode()).hexdigest()
    return int(digest[:8], 16) % NEWS_ID_SLOTS


def fetch_wikipedia_asof(
    *,
    client: HttpClient,
    title: str,
    asof_day: str,
    market_id: str,
    safety_lag_ms: int = SAFETY_LAG_MS_DEFAULT,
) -> tuple[NewsItem, ...]:
    """The newest revision of ``title`` that existed at the end of ``asof_day``, as one background item.

    Empty when the page does not exist or had no revision by that day. Never more than one item, so D6 can
    write it at ``wiki_asof/<market_id>/<yyyymmdd>.json`` without choosing between rows.
    """
    if not title.strip():
        raise InvalidConfigError("title is empty", market_id=market_id)
    asof_start_ms = day_start_ms_of(asof_day)
    asof_end_ms = asof_start_ms + MS_PER_DAY
    payload = client.get_json(
        MEDIAWIKI_PATH,
        {
            "action": "query",
            "prop": "revisions",
            "titles": title,
            "rvstart": f"{asof_day}T23:59:59Z",
            "rvdir": "older",
            "rvlimit": 1,
            "rvprop": "ids|timestamp|content",
            "rvslots": "main",
            "format": "json",
            "formatversion": 2,
            "redirects": 1,
        },
    )
    revision = _revision_of(payload, title=title)
    if revision is None:
        return ()
    revid, timestamp, content = revision
    published_at_ms = timestamp_ms(timestamp)
    if published_at_ms > asof_end_ms:
        raise LeakError(
            "the revision is newer than the day it was asked for",
            market_id=market_id,
            title=title,
            asof_day=asof_day,
            revid=revid,
            published_at_ms=published_at_ms,
        )
    links: dict[str, None] = {title: None}
    for link in wiki_links_of(content):
        links[link] = None
    return (
        NewsItem(
            schema_version="news.v1",
            news_id=f"wasof-{_yyyymmdd(published_at_ms)}-{news_id_index(market_id, title):04d}",
            source="wikipedia_asof",
            kind="background",
            published_at_ms=published_at_ms,
            revid=revid,
            asof_day=asof_day,
            visible_from_ms=published_at_ms + safety_lag_ms,
            fetched_at_ms=_fetched_at_ms(),
            url=REVISION_URL_TEMPLATE.format(revid=revid),
            headline=clip(title, NEWS_HEADLINE_MAX),
            # A plain slice, not `clip`: the stored text must stay a byte-exact prefix of the revision so
            # that "the snapshot is the revision named by its revid" is a checkable statement (section 7.1).
            text=content[:NEWS_TEXT_MAX],
            section=None,
            wiki_links=tuple(sorted(tuple(links)[:WIKI_LINKS_MAX])),
            # The item is the source: the citations of an article's raw wikitext are its own reference list,
            # and the first sixteen of them are template noise rather than the story's provenance.
            source_urls=(),
            match_ids=(),
            match_scores_permille=(),
            lang="en",
            author_key=None,
        ),
    )


def _revision_of(payload: object, *, title: str) -> tuple[int, str, str] | None:
    """``(revid, timestamp, wikitext)`` of the one revision the API returned, or ``None`` when there is none."""
    if not isinstance(payload, dict):
        raise MalformedResponseError("revisions response is not an object", title=title)
    error = payload.get("error")
    if isinstance(error, dict):
        raise MalformedResponseError("mediawiki error", title=title, code=str(error.get("code")))
    query = payload.get("query")
    if not isinstance(query, dict):
        raise MalformedResponseError("revisions response carries no query object", title=title)
    pages = query.get("pages")
    if not isinstance(pages, list) or not pages:
        return None
    page = pages[0]
    if not isinstance(page, dict) or page.get("missing") is True:
        return None
    revisions = page.get("revisions")
    if not isinstance(revisions, list) or not revisions:
        return None
    revision = revisions[0]
    if not isinstance(revision, dict):
        raise MalformedResponseError("revision is not an object", title=title)
    revid = revision.get("revid")
    timestamp = revision.get("timestamp")
    content = _content_of(revision)
    if not isinstance(revid, int) or isinstance(revid, bool) or not isinstance(timestamp, str):
        raise MalformedResponseError("revision carries no revid or timestamp", title=title)
    if content is None:
        raise MalformedResponseError("revision carries no wikitext", title=title, revid=revid)
    return (revid, timestamp, content)


def _content_of(revision: dict[str, object]) -> str | None:
    """The main slot's wikitext, accepting the slotted shape and the flat one the older API returns."""
    slots = revision.get("slots")
    if isinstance(slots, dict):
        main = slots.get("main")
        if isinstance(main, dict):
            content = main.get("content")
            if isinstance(content, str):
                return content
    flat = revision.get("content")
    return flat if isinstance(flat, str) else None


def _yyyymmdd(t_ms: int) -> str:
    return (dt.date(1970, 1, 1) + dt.timedelta(days=t_ms // MS_PER_DAY)).strftime("%Y%m%d")


def _iso_day(t_ms: int) -> str:
    return (dt.date(1970, 1, 1) + dt.timedelta(days=t_ms // MS_PER_DAY)).isoformat()


def _fetched_at_ms() -> int:
    """The wall clock of the fetch, which ``news.v1`` stores (section 7.3): a dataset is built, not run."""
    return time.time_ns() // 1_000_000
