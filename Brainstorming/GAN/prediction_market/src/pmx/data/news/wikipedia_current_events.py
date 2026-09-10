"""The news of the day as it was written on the day: one Wikipedia Current events page per date.

Why this source and not a news API: the Current events portal is dated by construction. The page
``Portal:Current events/2016 June 23`` was written on and about 23 June 2016, it is free, it needs no key, it
covers every day since 1998, and every bullet cites the outlet it came from. A commercial archive would give
richer text and no way for a reviewer to re-fetch the same bytes ten years later.

The page is wikitext, not prose: a bullet tree under bold (or, on older pages, definition-list) section
headings, where the shallow bullets are the running topic ("Russian invasion of Ukraine") and the deepest
bullet is the event. One ``NewsItem`` per **leaf** bullet is therefore one item per event, and the topic
bullets above it are not thrown away: their article titles are folded into the leaf's ``wiki_links``, which is
what gives the linker of section 7.6 something to match a market's ``wiki_subjects`` against. Without that
inheritance the Brexit referendum bullet ("Voters in the United Kingdom go to the polls") shares no article
title with any market and only the weaker keyword term of the score survives.

Dating follows CONTRACTS_V2 section 5.5 exactly, and decision D-R3 (ruling R249) made it a measurement
instead of a guess. A bullet is stamped with **the timestamp of the first revision of
``Portal:Current events/<day>`` that carries it**, read from the page's own revision history, so a bullet
added at 09:14Z is visible from 15:14Z and not from the next morning. The six-hour safety lag is unchanged
and is now a floor over a measured instant rather than a guess about the page. When the revision history
is unavailable, or when no revision carries a bullet's final wording, the stamp falls back to the **end of
day D** (``day_start_ms(D) + MS_PER_DAY``), which with the default lag is the PRD's "readable from D+1
06:00 UTC". The fallback is the conservative direction by construction: a later stamp is a later
visibility, so a failed match costs recall and can never create a leak.

The item id names ``D`` whatever the stamp is (ruling R7, section 2), while the news file it lands in is
keyed by ``day_start_ms(published_at_ms)`` (7.1), which is ``D`` for a revision-stamped bullet and
``D + 1`` for a page-day one; the loader checks that pairing and never the id.

This module reaches the network only through the shared client of section 7.11, and it writes no file: D6
alone writes files (section 7.12).
"""

from __future__ import annotations

import datetime as dt
import re
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pmx.data.news.linker import NEWS_HEADLINE_MAX, NEWS_TEXT_MAX, SOURCE_URLS_MAX, WIKI_LINKS_MAX, clip
from pmx.errors import MalformedResponseError
from pmx.types import MS_PER_DAY, SAFETY_LAG_MS_DEFAULT, NewsItem

if TYPE_CHECKING:  # the one client of section 7.11; imported for the annotation only
    from pmx.data.importers._http import HttpClient

#: The host D6 builds the client for, and the politeness interval this source asks for. Both live here
#: because "which host, how often" is knowledge about the source, and the client is built by the caller.
WIKIPEDIA_BASE_URL: Final = "https://en.wikipedia.org"
#: The host every path in this module is relative to. ``pmx.cli_data`` builds the shared client from
#: this constant, so the URL exists once in the repository (ruling R96).
BASE_URL: Final = WIKIPEDIA_BASE_URL
WIKIPEDIA_MIN_INTERVAL_MS: Final = 1_000

#: The MediaWiki entry point, relative to the client's ``base_url``.
MEDIAWIKI_PATH: Final = "/w/api.php"
WIKI_ARTICLE_BASE: Final = "https://en.wikipedia.org/wiki/"
CURRENT_EVENTS_PREFIX: Final = "Portal:Current events/"

#: Month names as the page titles spell them.
MONTH_NAMES: Final = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)

#: MediaWiki error codes that mean "this day has no page", which is an empty answer and not a failure.
MISSING_PAGE_CODES: Final = frozenset({"missingtitle", "invalidtitle", "nosuchpageid"})

#: The section headings the portal uses, mapped to the slug ``news.v1`` stores. Anything else is slugified.
SECTION_SLUGS: Final = {
    "armed conflicts and attacks": "armed_conflicts",
    "arts and culture": "arts_culture",
    "business and economy": "business",
    "disasters and accidents": "disasters",
    "health and environment": "health_environment",
    "international relations": "international_relations",
    "law and crime": "law_crime",
    "politics and elections": "politics",
    "science and technology": "science_technology",
    "sport": "sports",
    "sports": "sports",
}

#: Link namespaces that are not article subjects and are dropped from ``wiki_links``.
NON_ARTICLE_NAMESPACES: Final = frozenset(
    {
        "category", "commons", "file", "help", "image", "media", "mediawiki", "module", "portal",
        "special", "template", "wikipedia", "wikt", "wiktionary", "s", "q", "m", "w",
    }
)

COMMENT_RE: Final = re.compile(r"<!--.*?-->", re.DOTALL)
REF_RE: Final = re.compile(r"<ref[^>]*>.*?</ref>|<ref[^>]*/>", re.DOTALL | re.IGNORECASE)
TAG_RE: Final = re.compile(r"</?[A-Za-z][^>]*>")
TEMPLATE_RE: Final = re.compile(r"\{\{[^{}]*\}\}")
WIKILINK_RE: Final = re.compile(r"\[\[([^\[\]|]*)(?:\|([^\[\]]*))?\]\]")
EXTLINK_RE: Final = re.compile(r"\[(https?://[^\s\]]+)(?:\s+([^\]]*))?\]")
BARE_URL_RE: Final = re.compile(r"(?<![\[\w])(https?://[^\s\]]+)")
BULLET_RE: Final = re.compile(r"^(\*+)\s*(.*)$")
SEMI_HEADING_RE: Final = re.compile(r"^;\s*(.+?)\s*$")
BOLD_HEADING_RE: Final = re.compile(r"^'''\s*(.+?)\s*'''\s*$")
QUOTES_RE: Final = re.compile(r"'{2,5}")
WHITESPACE_RE: Final = re.compile(r"[ \t\u00a0]+")
SPACE_BEFORE_PUNCT_RE: Final = re.compile(r"\s+([,.;:!?)\]])")
SLUG_RE: Final = re.compile(r"[^a-z0-9]+")
#: The tokens a bullet is matched on across revisions (see :func:`bullet_key`).
TOKENS_RE: Final = re.compile(r"[a-z0-9]+")
ISO_TIMESTAMP_RE: Final = re.compile(
    r"([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})Z"
)

#: How many revisions of one day page the fetcher asks for. A Current events day page is edited a few
#: dozen times on its own day and rarely afterwards; five hundred is the MediaWiki page limit for an
#: anonymous ``rvlimit`` and is well above what any day needs, so the walk is one request per day in
#: practice and the cap is a guard rather than a policy.
REVISIONS_MAX: Final = 500

#: The two values of ``news.v1``'s ``published_at_source`` (7.3, ruling R249): which of section 5.5's two
#: stamps a bullet carries.
STAMP_REVISION: Final = "revision"
STAMP_PAGE_DAY: Final = "page_day"

#: HTML entities the portal actually uses. The dash entities become "-" and never the em-dash character.
ENTITIES: Final = {
    "&nbsp;": " ",
    "&amp;": "&",
    "&quot;": '"',
    "&apos;": "'",
    "&#39;": "'",
    "&ndash;": "-",
    "&mdash;": "-",
    "&hellip;": "...",
}


# --------------------------------------------------------------------------------------------------
# Page addressing
# --------------------------------------------------------------------------------------------------
def day_of(day_start_ms: int) -> dt.date:
    """The UTC date of a day-aligned instant, computed from whole days so no float and no clock is read."""
    return dt.date(1970, 1, 1) + dt.timedelta(days=day_start_ms // MS_PER_DAY)


def page_title_for(day_start_ms: int) -> str:
    """``Portal:Current events/2016 June 23``: the page title the portal uses, no zero padding on the day."""
    day = day_of(day_start_ms)
    return f"{CURRENT_EVENTS_PREFIX}{day.year} {MONTH_NAMES[day.month - 1]} {day.day}"


def page_url_for(day_start_ms: int) -> str:
    return WIKI_ARTICLE_BASE + page_title_for(day_start_ms).replace(" ", "_")


def yyyymmdd(day_start_ms: int) -> str:
    """The ``yyyymmdd`` a news id carries (section 2)."""
    return day_of(day_start_ms).strftime("%Y%m%d")


def ms_from_iso_timestamp(value: str) -> int:
    """``2016-06-23T09:14:00Z`` as integer epoch milliseconds, in integers throughout.

    MediaWiki stamps a revision in exactly this shape. ``datetime.timestamp()`` would go through a float
    and section 1's integer law forbids that on any quantity that reaches a stored field, and this one
    reaches ``published_at_ms``.
    """
    match = ISO_TIMESTAMP_RE.fullmatch(value.strip())
    if match is None:
        raise MalformedResponseError("a revision timestamp is not yyyy-mm-ddThh:mm:ssZ", timestamp=value)
    year, month, day, hour, minute, second = (int(part) for part in match.groups())
    days = (dt.date(year, month, day) - dt.date(1970, 1, 1)).days
    return days * MS_PER_DAY + ((hour * 60 + minute) * 60 + second) * 1_000


# --------------------------------------------------------------------------------------------------
# Wikitext, reduced to what news.v1 stores. Shared with wikipedia_asof.py, which parses the same markup.
# --------------------------------------------------------------------------------------------------
def wiki_links_of(wikitext: str) -> tuple[str, ...]:
    """The article titles the markup links to, in order of appearance, deduplicated.

    An anchor (``Solar Impulse#Solar Impulse 2``) is cut back to the article, an underscore becomes a space,
    and a non-article namespace (``File:``, ``Category:``) is dropped: the linker compares these titles to a
    market's ``wiki_subjects``, which hold articles and nothing else.
    """
    titles: dict[str, None] = {}
    for match in WIKILINK_RE.finditer(wikitext):
        target = match.group(1).split("#", 1)[0].replace("_", " ").strip()
        if not target:
            continue
        prefix, _, rest = target.partition(":")
        if rest and prefix.strip().lower() in NON_ARTICLE_NAMESPACES:
            continue
        titles[target] = None
    return tuple(titles)


def external_urls_of(wikitext: str) -> tuple[str, ...]:
    """The cited source URLs, in order of appearance, deduplicated and clipped to the ``news.v1`` cap."""
    urls: dict[str, None] = {}
    for match in EXTLINK_RE.finditer(wikitext):
        urls[clip(match.group(1), 1_024)] = None
    for match in BARE_URL_RE.finditer(wikitext):
        urls[clip(match.group(1), 1_024)] = None
    return tuple(urls)


def plain_text_of(wikitext: str) -> str:
    """The bullet as a reader sees it: links reduced to their label, citations, templates and markup gone.

    The external links are removed rather than kept as text because they are citations, and they are already
    stored in ``source_urls``: leaving "(Reuters)" in the middle of a sentence would put an outlet's name into
    the keyword tokens of section 7.6 and make every Reuters-cited item look alike to the linker.
    """
    text = COMMENT_RE.sub("", wikitext)
    text = REF_RE.sub("", text)
    for _ in range(3):  # templates nest at most a level or two on these pages
        reduced = TEMPLATE_RE.sub("", text)
        if reduced == text:
            break
        text = reduced
    text = EXTLINK_RE.sub("", text)
    text = WIKILINK_RE.sub(_wikilink_label, text)
    text = TAG_RE.sub("", text)
    for entity, replacement in ENTITIES.items():
        text = text.replace(entity, replacement)
    text = QUOTES_RE.sub("", text)
    text = text.replace("\u00a0", " ")
    text = WHITESPACE_RE.sub(" ", text)
    text = SPACE_BEFORE_PUNCT_RE.sub(r"\1", text)
    return text.strip(" ,;:")


def section_slug(heading: str) -> str | None:
    """The slug for a section heading, or ``None`` when nothing usable survives the slugifier."""
    known = SECTION_SLUGS.get(heading.strip().lower())
    if known is not None:
        return known
    slug = SLUG_RE.sub("_", heading.strip().lower()).strip("_")[:48]
    return slug or None


def _wikilink_label(match: re.Match[str]) -> str:
    label = match.group(2)
    if label:
        return label.strip()
    return match.group(1).split("#", 1)[0].replace("_", " ").strip()


# --------------------------------------------------------------------------------------------------
# The parser: wikitext in, NewsItems out, no network
# --------------------------------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class PageRevision:
    """One revision of a day page: its id, when it was saved, and the wikitext it saved."""

    revid: int
    timestamp_ms: int
    wikitext: str


@dataclass(frozen=True, slots=True)
class Appearance:
    """When a bullet first appeared on the page, and in which revision (decision D-R3, ruling R249)."""

    revid: int
    timestamp_ms: int


def bullet_key(text: str) -> str:
    """The match key of a bullet across revisions: its lowercase alphanumeric tokens, joined.

    Matching on the raw text would miss every bullet a later editor copyedited, and each miss falls back
    to the end of the page day, which costs eleven hours of recall for nothing. Matching on the tokens
    survives punctuation, capitalisation, wikilink piping and the spacing the markup reducer leaves
    behind, and it cannot match two different events: a Current events bullet is a sentence.
    """
    return " ".join(TOKENS_RE.findall(text.lower()))


def leaf_texts_of(wikitext: str) -> tuple[str, ...]:
    """The plain text of every leaf bullet of a page revision, in document order.

    Shared by the parser and by :func:`first_appearances`, so "what a bullet is" is decided once: a
    revision in which a bullet is not yet a leaf (its children arrive in a later edit) is not a revision
    that carries the event, and reading both sides through the same walk is what makes that consistent.
    """
    nodes = _nodes(wikitext)
    texts: list[str] = []
    for index, node in enumerate(nodes):
        if node.depth == 0 or not _is_leaf(nodes, index):
            continue
        text = clip(plain_text_of(node.content), NEWS_TEXT_MAX)
        if text:
            texts.append(text)
    return tuple(texts)


def first_appearances(revisions: Sequence[PageRevision]) -> dict[str, Appearance]:
    """Per bullet key, the earliest revision of the page that carries that bullet (ruling R249).

    Revisions are read oldest first whatever order they arrive in, so a caller that fetched them newest
    first gets the same answer; ties on the timestamp are broken by the lower revision id, which is the
    earlier save.
    """
    first: dict[str, Appearance] = {}
    for revision in sorted(revisions, key=lambda item: (item.timestamp_ms, item.revid)):
        for text in leaf_texts_of(revision.wikitext):
            key = bullet_key(text)
            if key and key not in first:
                first[key] = Appearance(revid=revision.revid, timestamp_ms=revision.timestamp_ms)
    return first


def parse_current_events(
    wikitext: str,
    *,
    day_start_ms: int,
    fetched_at_ms: int,
    safety_lag_ms: int = SAFETY_LAG_MS_DEFAULT,
    revisions: Sequence[PageRevision] = (),
) -> tuple[NewsItem, ...]:
    """One ``NewsItem`` per leaf bullet of a Current events day page, in document order.

    ``day_start_ms`` is the page day ``D`` and the ids are positional inside ``D`` (section 2). A bullet
    whose text is empty once the markup is gone yields no item and consumes no index, so the ids of two
    parses of the same page agree.

    **The stamp** (section 5.5, decision D-R3, ruling R249). With ``revisions`` given, a bullet carries
    the timestamp of the first revision that carried it; with none given, or for a bullet no revision
    matches, it carries the end of day ``D``. The safety lag is added on top of whichever stamp applies,
    which is what "the blanket lag remains only as a floor" means: the lag never shrinks, the instant it
    is measured from does.
    """
    day_end_ms = day_start_ms + MS_PER_DAY
    first = first_appearances(revisions)
    url = page_url_for(day_start_ms)
    day_key = yyyymmdd(day_start_ms)
    nodes = _nodes(wikitext)
    items: list[NewsItem] = []
    stack: list[str] = []
    for index, node in enumerate(nodes):
        if node.depth == 0:
            stack = []
            continue
        del stack[node.depth - 1 :]
        stack.append(node.content)
        if not _is_leaf(nodes, index):
            continue
        text = clip(plain_text_of(node.content), NEWS_TEXT_MAX)
        if not text:
            continue
        ancestors = stack[:-1]
        links: dict[str, None] = {}
        for ancestor in ancestors:
            for title in wiki_links_of(ancestor):
                links[title] = None
        for title in wiki_links_of(node.content):
            links[title] = None
        appearance = first.get(bullet_key(text))
        published_at_ms = appearance.timestamp_ms if appearance is not None else day_end_ms
        items.append(
            NewsItem(
                schema_version="news.v1",
                news_id=f"wce-{day_key}-{len(items):04d}",
                source="wikipedia_current_events",
                kind="headline",
                published_at_ms=published_at_ms,
                # The revision id belongs on the item (``news.v1``'s ``revid``, with
                # ``published_at_source = "revision"`` beside it, ruling R249) and ``pmx.types.NewsItem``
                # carries neither for a ``wce`` source: both are D1's fields and the agreement is
                # reported by DS1. The measured instant, which is the whole of what the as-of rule
                # reads, is on the item; the provenance of that instant is recoverable through
                # :func:`published_at_source_of` and :func:`first_appearances` until the field lands.
                revid=None,
                asof_day=None,
                visible_from_ms=published_at_ms + safety_lag_ms,
                fetched_at_ms=fetched_at_ms,
                url=url,
                headline=clip(text, NEWS_HEADLINE_MAX),
                text=text,
                section=node.section,
                wiki_links=tuple(sorted(tuple(links)[:WIKI_LINKS_MAX])),
                source_urls=external_urls_of(node.content)[:SOURCE_URLS_MAX],
                match_ids=(),
                match_scores_permille=(),
                lang="en",
                author_key=None,
            )
        )
    return tuple(items)


@dataclass(frozen=True, slots=True)
class _Node:
    """A parsed line: a section heading (``depth == 0``) or a bullet at ``depth >= 1``."""

    depth: int
    content: str
    section: str | None


def _nodes(wikitext: str) -> tuple[_Node, ...]:
    section: str | None = None
    nodes: list[_Node] = []
    for raw in COMMENT_RE.sub("", wikitext).splitlines():
        line = raw.strip()
        if not line:
            continue
        bullet = BULLET_RE.match(line)
        if bullet is not None:
            nodes.append(_Node(len(bullet.group(1)), bullet.group(2).strip(), section))
            continue
        heading = BOLD_HEADING_RE.match(line) or SEMI_HEADING_RE.match(line)
        if heading is not None:
            section = section_slug(plain_text_of(heading.group(1)))
            nodes.append(_Node(0, "", section))
    return tuple(nodes)


def published_at_source_of(item: NewsItem, *, day_start_ms: int) -> str:
    """``news.v1``'s ``published_at_source`` for a Current events bullet: which stamp it carries.

    The field is ``NewsItem.published_at_source`` in the contract (7.3, ruling R249) and D1's
    ``pmx.types`` does not carry it, so the value is derived here from the two things that do: the page
    day and the stamp. It is exact, because the page-day fallback is the one instant that is not a
    revision timestamp, and it is what the manifest's per-source report and the reviewer read until the
    field lands.
    """
    return STAMP_PAGE_DAY if item.published_at_ms == day_start_ms + MS_PER_DAY else STAMP_REVISION


def _is_leaf(nodes: tuple[_Node, ...], index: int) -> bool:
    """A bullet is a leaf when the next node is not a deeper bullet: children always follow their parent."""
    following = index + 1
    if following >= len(nodes):
        return True
    return nodes[following].depth <= nodes[index].depth


# --------------------------------------------------------------------------------------------------
# The fetcher
# --------------------------------------------------------------------------------------------------
def fetch_page_revisions(
    *, client: HttpClient, day_start_ms: int, limit: int = REVISIONS_MAX
) -> tuple[PageRevision, ...]:
    """The revision history of one day page, oldest first, with the wikitext of each revision.

    This is what decision D-R3 costs: one extra MediaWiki call per day, returning every saved version of
    the page rather than only the current one, so that "when did this bullet first appear" is a
    measurement. A page Wikipedia does not have, or a history the API declines to serve, yields an empty
    tuple and the parser falls back to the end of the page day: the stamp degrades, the build does not.
    """
    page = page_title_for(day_start_ms)
    payload = client.get_json(
        MEDIAWIKI_PATH,
        {
            "action": "query",
            "prop": "revisions",
            "titles": page,
            "rvlimit": min(limit, REVISIONS_MAX),
            "rvdir": "newer",
            "rvprop": "ids|timestamp|content",
            "rvslots": "main",
            "format": "json",
            "formatversion": 2,
            "redirects": 1,
        },
    )
    if not isinstance(payload, dict):
        raise MalformedResponseError("revision response is not an object", page=page)
    error = payload.get("error")
    if isinstance(error, dict):
        code = error.get("code")
        if isinstance(code, str) and code in MISSING_PAGE_CODES:
            return ()
        raise MalformedResponseError("mediawiki error", page=page, code=str(code))
    query = payload.get("query")
    if not isinstance(query, dict):
        raise MalformedResponseError("revision response carries no query object", page=page)
    pages = query.get("pages")
    if not isinstance(pages, list):
        raise MalformedResponseError("revision response carries no pages array", page=page)
    revisions: list[PageRevision] = []
    for entry in pages:
        if not isinstance(entry, dict):
            raise MalformedResponseError("a page entry is not an object", page=page)
        if entry.get("missing") is True:
            continue
        rows = entry.get("revisions")
        if not isinstance(rows, list):
            continue
        for row in rows:
            revision = _revision_of(row, page=page)
            if revision is not None:
                revisions.append(revision)
    return tuple(sorted(revisions, key=lambda item: (item.timestamp_ms, item.revid)))


def _revision_of(row: object, *, page: str) -> PageRevision | None:
    """One ``revisions`` row, or ``None`` for a revision whose content the API withheld.

    A deleted or suppressed revision comes back without its slot content, which is a fact about that
    revision and not a malformed answer: it is skipped, and a bullet that only ever appeared in it falls
    back to the page day.
    """
    if not isinstance(row, dict):
        raise MalformedResponseError("a revision row is not an object", page=page)
    revid = row.get("revid")
    timestamp = row.get("timestamp")
    if isinstance(revid, bool) or not isinstance(revid, int) or not isinstance(timestamp, str):
        raise MalformedResponseError("a revision row carries no revid and timestamp", page=page)
    slots = row.get("slots")
    if not isinstance(slots, dict):
        return None
    main = slots.get("main")
    if not isinstance(main, dict):
        return None
    content = main.get("content")
    if not isinstance(content, str):
        return None
    return PageRevision(
        revid=revid, timestamp_ms=ms_from_iso_timestamp(timestamp), wikitext=content
    )


def fetch_wikipedia_current_events(
    *,
    client: HttpClient,
    day_start_ms: int,
    safety_lag_ms: int = SAFETY_LAG_MS_DEFAULT,
    stamp_from_revisions: bool = True,
) -> tuple[NewsItem, ...]:
    """The Current events page of one day, parsed into items (section 7.12).

    The client carries the descriptive User-Agent of section 7.11: the MediaWiki API answers 403 to a generic
    one, verified against ``en.wikipedia.org`` on 2026-09-07, so a bare agent string is not a style question.
    A day Wikipedia has no page for yields no items rather than an error, because a build spanning a year
    must not die on one absent date; every other API error is a ``MalformedResponseError``.
    """
    page = page_title_for(day_start_ms)
    payload = client.get_json(
        MEDIAWIKI_PATH,
        {
            "action": "parse",
            "page": page,
            "prop": "wikitext",
            "format": "json",
            "formatversion": 2,
            "redirects": 1,
        },
    )
    if not isinstance(payload, dict):
        raise MalformedResponseError("current events response is not an object", page=page)
    error = payload.get("error")
    if isinstance(error, dict):
        code = error.get("code")
        if isinstance(code, str) and code in MISSING_PAGE_CODES:
            return ()
        raise MalformedResponseError("mediawiki error", page=page, code=str(code))
    parse = payload.get("parse")
    if not isinstance(parse, dict):
        raise MalformedResponseError("current events response carries no parse object", page=page)
    wikitext = parse.get("wikitext")
    if not isinstance(wikitext, str):
        raise MalformedResponseError("current events response carries no wikitext", page=page)
    revisions = (
        fetch_page_revisions(client=client, day_start_ms=day_start_ms)
        if stamp_from_revisions
        else ()
    )
    return parse_current_events(
        wikitext,
        day_start_ms=day_start_ms,
        fetched_at_ms=_fetched_at_ms(),
        safety_lag_ms=safety_lag_ms,
        revisions=revisions,
    )


def _fetched_at_ms() -> int:
    """The wall clock of the fetch, which ``news.v1`` stores (section 7.3): a dataset is built, not run."""
    return time.time_ns() // 1_000_000
