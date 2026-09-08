"""Manifold comments as dated news of the time (CONTRACTS_V2 7.3, 7.12, source code ``mfc``).

A Manifold comment is the cheapest honest signal in the whole dataset: a timestamped, attributed sentence
about one market, written by someone with money on it, and published before the outcome was known. It is
the only news source in the design that is *already* linked to a market, which is why every item this
module returns carries ``match_ids = [market.id]`` at the full ``1_000`` permille instead of waiting for
the linker's keyword overlap to rediscover a link the venue stated.

Two mechanics are worth reading.

**The content is a document, not a string.** Manifold stores a comment as a ProseMirror tree (paragraphs,
hard breaks, mentions, link marks, embedded images), so :func:`flatten_prosemirror` walks it into plain
text and collects every hyperlink it passes. The links are where the value is: a comment that cites
``en.wikipedia.org/wiki/Sahra_Wagenknecht`` hands the linker a shared article title (section 7.6), and one
that cites a news site hands the reader a source url.

**Nothing published after the outcome may enter.** A comment written after ``market.resolved_at_ms``
states the answer, so it is dropped here rather than filtered later: the safety lag of section 5.5 delays
an item, it does not undo one. What survives is stamped ``visible_from_ms = published_at_ms +
safety_lag_ms``, the one field the observation builder reads.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Final
from urllib.parse import unquote

from pmx.errors import MalformedResponseError
from pmx.types import SAFETY_LAG_MS_DEFAULT, NewsItem, day_key

if TYPE_CHECKING:  # the client is passed in by D6; this module never constructs one (section 7.12)
    from pmx.data.importers._http import HttpClient
    from pmx.types import Market

PROVIDER: Final = "manifold"
COMMENTS_PATH: Final = "/v0/comments"
#: The venue caps the page at 1 000. A module constant so a test can drive the pagination loop against a
#: recorded fixture instead of a thousand rows.
COMMENTS_PAGE_LIMIT: int = 1_000
COMMENTS_MAX_PAGES: Final = 100

NEWS_SOURCE: Final = "manifold_comment"
NEWS_KIND: Final = "comment"
NEWS_ID_PREFIX: Final = "mfc"
NEWS_ID_MAX_INDEX: Final = 9_999
LANG: Final = "en"

HEADLINE_MAX: Final = 300
TEXT_MAX: Final = 4_000
WIKI_LINKS_MAX: Final = 32
WIKI_TITLE_MAX_CHARS: Final = 256
SOURCE_URLS_MAX: Final = 16
URL_MAX: Final = 1_024
TRUNCATION_MARK: Final = "..."
FULL_MATCH_PERMILLE: Final = 1_000

#: ProseMirror nodes that end a line of text. Everything else is inline, or a container whose children
#: carry the text.
BLOCK_TYPES: Final = frozenset(
    {
        "blockquote",
        "bulletList",
        "codeBlock",
        "doc",
        "heading",
        "horizontalRule",
        "listItem",
        "orderedList",
        "paragraph",
    }
)
#: Node attributes that hold a hyperlink.
LINK_ATTRS: Final = ("href", "src")

WIKIPEDIA_ARTICLE_PREFIX: Final = "https://en.wikipedia.org/wiki/"


# --------------------------------------------------------------------------------------------------
# The ProseMirror document
# --------------------------------------------------------------------------------------------------
def flatten_prosemirror(node: object) -> tuple[str, tuple[str, ...]]:
    """Flatten a ProseMirror document into plain text plus the hyperlinks it carries, in reading order.

    Tolerant by design: a ``str`` (how the venue stored a description before the rich editor), a bare
    list of nodes, a node type this walker has never seen, a missing ``content`` and a malformed ``marks``
    all flatten to the text they do carry instead of raising. A comment is news, not a contract: the right
    failure is a shorter sentence, never a refused import.
    """
    links: list[str] = []
    text = _render(node, links)
    return _collapse(text), tuple(links)


def _render(node: object, links: list[str]) -> str:
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return "".join(_render(child, links) for child in node)
    if not isinstance(node, dict):
        return ""
    _collect_links(node, links)
    kind = node.get("type")
    if kind == "text":
        raw = node.get("text")
        return raw if isinstance(raw, str) else ""
    if kind == "hardBreak":
        return "\n"
    if isinstance(kind, str) and kind.endswith("mention"):
        return _mention(node, kind)
    inner = _render(node.get("content"), links)
    if kind in BLOCK_TYPES:
        return f"{inner}\n"
    return inner


def _mention(node: Mapping[str, object], kind: str) -> str:
    """A mention as text: ``@name`` for a user, the market's own path for a ``contract-mention``.

    A comment that says "see [other market]" carries that market's path and nothing else in its text, so
    dropping the node would lose both the sentence and every token the linker could match on.
    """
    label = _attr(node, "label") or _attr(node, "id") or ""
    return f"@{label}" if kind == "mention" else label


def _collect_links(node: Mapping[str, object], links: list[str]) -> None:
    for key in LINK_ATTRS:
        _remember(_attr(node, key), links)
    marks = node.get("marks")
    if not isinstance(marks, list):
        return
    for mark in marks:
        if isinstance(mark, dict) and mark.get("type") == "link":
            _remember(_attr(mark, "href"), links)


def _attr(node: Mapping[str, object], key: str) -> str | None:
    attrs = node.get("attrs")
    if not isinstance(attrs, dict):
        return None
    value = attrs.get(key)
    return value if isinstance(value, str) and value else None


def _remember(url: str | None, links: list[str]) -> None:
    if url is not None and len(url) <= URL_MAX and url not in links:
        links.append(url)


def _collapse(text: str) -> str:
    """One blank line at most between two blocks, no trailing whitespace: a stable, comparable string."""
    lines = [line.rstrip() for line in text.split("\n")]
    kept: list[str] = []
    for line in lines:
        if line == "" and kept[-1:] == [""]:
            continue
        kept.append(line)
    return "\n".join(kept).strip()


# --------------------------------------------------------------------------------------------------
# The links, split the way news.v1.json splits them
# --------------------------------------------------------------------------------------------------
def wikipedia_titles(urls: Sequence[str]) -> tuple[str, ...]:
    """The English Wikipedia article titles among ``urls``, sorted and unique (section 7.6).

    Spelled as a title is spelled, because that is what the linker compares against a market's
    ``wiki_subjects``: percent-decoded, underscores as spaces, anchors and query strings dropped. This is
    the one spelling; the importer imports it from here for a market's ``wiki_subjects`` so the two sides
    of a link can never drift.
    """
    titles: list[str] = []
    for url in urls:
        if not url.startswith(WIKIPEDIA_ARTICLE_PREFIX):
            continue
        tail = url[len(WIKIPEDIA_ARTICLE_PREFIX) :].split("#", 1)[0].split("?", 1)[0]
        title = unquote(tail).replace("_", " ").strip()
        if title and len(title) <= WIKI_TITLE_MAX_CHARS and title not in titles:
            titles.append(title)
    return tuple(sorted(titles))


def source_urls(urls: Sequence[str]) -> tuple[str, ...]:
    """The links that are not Wikipedia articles, in reading order, at most sixteen (section 7.3)."""
    return tuple(url for url in urls if not url.startswith(WIKIPEDIA_ARTICLE_PREFIX))[:SOURCE_URLS_MAX]


# --------------------------------------------------------------------------------------------------
# Fetching
# --------------------------------------------------------------------------------------------------
def _rows(payload: object) -> tuple[Mapping[str, object], ...]:
    if not isinstance(payload, list):
        raise MalformedResponseError(
            "manifold sent no list", provider=PROVIDER, what="comments", got=type(payload).__name__
        )
    rows: list[Mapping[str, object]] = []
    for index, row in enumerate(payload):
        if not isinstance(row, dict):
            raise MalformedResponseError(
                "manifold sent a non-object comment", provider=PROVIDER, what="comments", index=index
            )
        rows.append(row)
    return tuple(rows)


def fetch_comment_payloads(client: HttpClient, provider_id: str) -> tuple[Mapping[str, object], ...]:
    """Every comment of a contract as the venue serves it, newest first, paged with ``page``."""
    payloads: list[Mapping[str, object]] = []
    for page_index in range(COMMENTS_MAX_PAGES):
        body = client.get_text(
            COMMENTS_PATH,
            {"contractId": provider_id, "limit": COMMENTS_PAGE_LIMIT, "page": page_index},
        )
        try:
            parsed = json.loads(body)
        except ValueError as error:
            raise MalformedResponseError(
                "manifold sent a body that is not JSON", provider=PROVIDER, what="comments", detail=str(error)
            ) from error
        page = _rows(parsed)
        payloads.extend(page)
        if len(page) < COMMENTS_PAGE_LIMIT:
            break
    return tuple(payloads)


def is_readable(payload: Mapping[str, object]) -> bool:
    """Is this comment public, present and not moderated away? A hidden comment is not news."""
    if payload.get("hidden") is True or payload.get("deleted") is True:
        return False
    visibility = payload.get("visibility")
    return not (isinstance(visibility, str) and visibility != "public")


# --------------------------------------------------------------------------------------------------
# The item
# --------------------------------------------------------------------------------------------------
def news_id_of(published_at_ms: int, index: int) -> str:
    """``mfc-<yyyymmdd>-<idx:04d>`` (section 2), positional inside the day the id names."""
    if not 0 <= index <= NEWS_ID_MAX_INDEX:
        raise MalformedResponseError("more comments in one day than a news id can number", index=index)
    return f"{NEWS_ID_PREFIX}-{day_key(published_at_ms)}-{index:04d}"


def _headline(text: str) -> str:
    first = next((line for line in text.split("\n") if line.strip()), "")
    if len(first) <= HEADLINE_MAX:
        return first
    return first[: HEADLINE_MAX - len(TRUNCATION_MARK)] + TRUNCATION_MARK


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - len(TRUNCATION_MARK)] + TRUNCATION_MARK


def author_key_of(user_id: str) -> str:
    """``sha256(user_id)[:16]``: the same author is the same key across markets, and never a user name."""
    return hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:16]


def now_ms() -> int:
    """The wall clock, in integer milliseconds.

    Legal here and nowhere in the engine: ``fetched_at_ms`` records when a dataset was *built*, and a
    dataset is built once (section 7.3). ``time_ns`` keeps it an integer.
    """
    return time.time_ns() // 1_000_000


def build_item(
    payload: Mapping[str, object],
    *,
    market_id: str,
    market_url: str,
    index: int,
    safety_lag_ms: int,
    fetched_at_ms: int,
) -> NewsItem | None:
    """One ``NewsItem`` from one comment payload, or ``None`` when the comment carries no readable text.

    Pure: no clock, no network. ``fetched_at_ms`` is passed in so that every item of one fetch carries the
    same stamp and so that this function stays testable to the millisecond.
    """
    comment_id = payload.get("id")
    published = payload.get("createdTime")
    user_id = payload.get("userId")
    if not isinstance(comment_id, str) or not isinstance(user_id, str):
        raise MalformedResponseError("manifold comment has no id or no author", provider=PROVIDER, what="comments")
    if isinstance(published, bool) or not isinstance(published, int):
        raise MalformedResponseError(
            "manifold comment has no createdTime", provider=PROVIDER, what="comments", comment_id=comment_id
        )
    text, links = flatten_prosemirror(payload.get("content"))
    headline = _headline(text)
    if not headline:
        return None
    return NewsItem(
        schema_version="news.v1",
        news_id=news_id_of(published, index),
        source=NEWS_SOURCE,
        kind=NEWS_KIND,
        published_at_ms=published,
        revid=None,
        asof_day=None,
        visible_from_ms=published + safety_lag_ms,
        fetched_at_ms=fetched_at_ms,
        url=_truncate(f"{market_url}#{comment_id}", URL_MAX),
        headline=headline,
        text=_truncate(text, TEXT_MAX),
        section=None,
        wiki_links=wikipedia_titles(links)[:WIKI_LINKS_MAX],
        source_urls=source_urls(links),
        match_ids=(market_id,),
        match_scores_permille=(FULL_MATCH_PERMILLE,),
        lang=LANG,
        author_key=author_key_of(user_id),
    )


def fetch_comments(
    *,
    client: HttpClient,
    market: Market,
    safety_lag_ms: int = SAFETY_LAG_MS_DEFAULT,
    index_offset_by_day: Mapping[str, int] | None = None,
) -> tuple[NewsItem, ...]:
    """Every readable comment of ``market`` published at or before its settlement, oldest first.

    ``safety_lag_ms`` and ``index_offset_by_day`` are optional extensions of the section 7.12 signature,
    both reported as contract issues and both harmless to a caller that passes neither: the lag has no
    parameter anywhere in 7.12 although 7.12 requires the returned items to carry the caller's lag, and a
    ``mfc`` id is positional inside its day (section 2), which two markets commented on the same day would
    collide on. ``index_offset_by_day`` maps a ``yyyymmdd`` to the first free index of that day, so D6 can
    number one dataset's comments without a second pass.
    """
    fetched_at_ms = now_ms()
    payloads = [
        payload
        for payload in fetch_comment_payloads(client, market.provider_id)
        if is_readable(payload) and _published_in_time(payload, market.resolved_at_ms)
    ]
    payloads.sort(key=lambda payload: (_published_at(payload), str(payload.get("id"))))
    taken = dict(index_offset_by_day or {})
    items: list[NewsItem] = []
    for payload in payloads:
        published = _published_at(payload)
        key = day_key(published)
        index = taken.get(key, 0)
        item = build_item(
            payload,
            market_id=market.id,
            market_url=market.url,
            index=index,
            safety_lag_ms=safety_lag_ms,
            fetched_at_ms=fetched_at_ms,
        )
        if item is None:
            continue
        taken[key] = index + 1
        items.append(item)
    return tuple(items)


def _published_at(payload: Mapping[str, object]) -> int:
    published = payload.get("createdTime")
    if isinstance(published, bool) or not isinstance(published, int):
        raise MalformedResponseError("manifold comment has no createdTime", provider=PROVIDER, what="comments")
    return published


def _published_in_time(payload: Mapping[str, object], resolved_at_ms: int) -> bool:
    """A comment written after the settlement states the outcome, so it is not news (section 5.5)."""
    return _published_at(payload) <= resolved_at_ms
