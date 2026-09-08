"""D5: the dated news archive, the deterministic linker and the lexicons.

Every test here is offline. The four fetchers are driven through the real ``HttpClient`` of section 7.11 with
an ``httpx.MockTransport`` in front of it, so the request that would go out (its path, its query, its
User-Agent) is asserted rather than assumed, and no test opens a socket. The one exception is
``test_live_current_events_page``, which is skipped unless ``PMX_LIVE`` is set: that is the single legal skip
of the plan.

Provenance of the fixtures under ``tests/fixtures/d5/``, all recorded from the live providers on 2026-09-07:

- ``wce_parse_20160623.json`` and ``wce_parse_20250903.json``: ``action=parse&prop=wikitext`` responses for
  ``Portal:Current events/2016 June 23`` and ``.../2025 September 3``, verbatim. The first uses the older
  definition-list headings (``;Politics and elections``) and carries the Brexit referendum bullets; the
  second uses the bold headings of the current format. Two formats, because a parser that only handles the
  format of this month silently returns nothing for half the window;
- ``wce_parse_missing.json``: the ``missingtitle`` error the API returns for a day that has no page;
- ``wasof_revisions_20160620.json``: the ``prop=revisions&rvdir=older`` answer for the referendum article as
  of 2016-06-20, with the revision's wikitext kept to its first 8 000 characters (the article is 132 000 and
  carries an em-dash past character 11 000, which the house rule forbids in the repository). Eight thousand
  is still twice the ``news.v1`` text cap, so the truncation the fetcher performs is a real one;
- ``cdx_reuters_20160623.json``: the CDX table for ``reuters.com`` on 2016-06-23, verbatim;
- ``gdelt_doc_20250903.json``: a DOC 2.0 ``artlist`` answer, verbatim;
- ``gdelt_warning.txt``: the shape of the plain-text warning DOC returns instead of JSON when it declines.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path

import httpx
import pytest

from pmx import NEWS_SCHEMA
from pmx.data.importers._http import build_user_agent
from pmx.data.news import gdelt as gd
from pmx.data.news import linker as lk
from pmx.data.news import wayback as wb
from pmx.data.news import wikipedia_asof as wa
from pmx.data.news import wikipedia_current_events as wce
from pmx.errors import InvalidConfigError, LeakError, MalformedResponseError
from pmx.types import (
    CATEGORIES,
    LEXICON_COUNT,
    LINK_THRESHOLD_PERMILLE,
    MS_PER_DAY,
    SAFETY_LAG_MS_DEFAULT,
    Bar,
    Market,
    MarketQuality,
    NewsItem,
    day_start_ms,
    rank_news_items,
    round_half_up,
)

FIXTURES = Path(__file__).parent / "fixtures" / "d5"
LEXICONS = Path(__file__).resolve().parents[1] / "src" / "pmx" / "lexicons"

DAY_20160623 = 1_466_640_000_000
DAY_20250903 = 1_756_857_600_000
CONTACT = "d5-tests@pmx.invalid"

Handler = Callable[[httpx.Request], httpx.Response]


# --------------------------------------------------------------------------------------------------
# Scaffolding
# --------------------------------------------------------------------------------------------------
def fixture_text(name: str) -> str:
    with open(FIXTURES / name, encoding="utf-8", newline="\n") as handle:
        return handle.read()


def fixture_json(name: str) -> object:
    return json.loads(fixture_text(name))


def client_for(
    tmp_path: Path,
    handler: Handler,
    *,
    base_url: str = wce.WIKIPEDIA_BASE_URL,
    min_interval_ms: int = 0,
) -> object:
    """The real client of section 7.11 with a mock transport: no socket, no sleep, real code path."""
    from pmx.data.importers._http import HttpClient

    return HttpClient(
        base_url=base_url,
        user_agent=build_user_agent(CONTACT),
        min_interval_ms=min_interval_ms,
        cache_dir=tmp_path / "cache",
        transport=httpx.MockTransport(handler),
        sleeper=lambda _duration_ms: None,
    )


def recording_handler(body: str, *, status: int = 200) -> tuple[Handler, list[httpx.Request]]:
    """A handler that always answers ``body`` and keeps every request it was asked for."""
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, text=body)

    return handle, seen


def market(
    market_id: str,
    question: str,
    *,
    wiki_subjects: Iterable[str] = (),
    tags: Iterable[str] = (),
    category: str = "politics",
    created_at_ms: int = DAY_20160623,
    resolved_at_ms: int = DAY_20160623 + MS_PER_DAY,
) -> Market:
    """A market with the four fields the linker reads and a legal skeleton for everything else."""
    bars = tuple(
        Bar(
            t_ms=created_at_ms + index * MS_PER_DAY,
            open_bp=5_000,
            high_bp=5_000,
            low_bp=5_000,
            close_bp=5_000,
            vwap_bp=5_000,
            volume_milli=1_000,
            n_trades=1,
            yes_bid_bp=None,
            yes_ask_bp=None,
            open_interest=None,
        )
        for index in range(2)
    )
    return Market(
        schema_version="market.v2",
        id=market_id,
        provider="demo",
        provider_id=market_id,
        url="",
        question=question,
        description="",
        category=category,
        tags=tuple(tags),
        wiki_subjects=tuple(wiki_subjects),
        currency="usd",
        source="imported",
        created_at_ms=created_at_ms,
        close_at_ms=resolved_at_ms,
        resolved_at_ms=resolved_at_ms,
        resolution=1,
        resolution_source="venue",
        event_key=None,
        interval_min=1_440,
        bars=bars,
        trades=(),
        first_price_bp=5_000,
        final_price_bp=5_000,
        hardness_tags=(),
        quality=MarketQuality(
            n_trades=1, unique_bettors=None, life_days=1, volume_milli_total=1_000, traded_bars=2
        ),
        fee_schedule_id="demo-zero",
        notes="",
    )


def news_item(
    news_id: str,
    *,
    headline: str = "",
    text: str = "",
    wiki_links: Iterable[str] = (),
    published_at_ms: int = DAY_20160623,
) -> NewsItem:
    return NewsItem(
        schema_version=NEWS_SCHEMA,
        news_id=news_id,
        source="wikipedia_current_events",
        kind="headline",
        published_at_ms=published_at_ms,
        revid=None,
        asof_day=None,
        visible_from_ms=published_at_ms + SAFETY_LAG_MS_DEFAULT,
        fetched_at_ms=published_at_ms,
        url="https://en.wikipedia.org/wiki/Portal:Current_events",
        headline=headline or news_id,
        text=text,
        section="politics",
        wiki_links=tuple(wiki_links),
        source_urls=(),
        match_ids=(),
        match_scores_permille=(),
        lang="en",
        author_key=None,
    )


def parsed_2016() -> tuple[NewsItem, ...]:
    payload = fixture_json("wce_parse_20160623.json")
    assert isinstance(payload, dict)
    parse = payload["parse"]
    assert isinstance(parse, dict)
    wikitext = parse["wikitext"]
    assert isinstance(wikitext, str)
    return wce.parse_current_events(wikitext, day_start_ms=DAY_20160623, fetched_at_ms=1_700_000_000_000)


def query_of(request: httpx.Request) -> Mapping[str, str]:
    return dict(httpx.QueryParams(request.url.query.decode("ascii")))


# --------------------------------------------------------------------------------------------------
# Wikipedia Current events: addressing and dating
# --------------------------------------------------------------------------------------------------
def test_the_page_title_of_a_day_is_the_portal_spelling() -> None:
    assert wce.page_title_for(DAY_20160623) == "Portal:Current events/2016 June 23"
    assert wce.page_title_for(DAY_20250903) == "Portal:Current events/2025 September 3"
    assert wce.page_url_for(DAY_20160623) == "https://en.wikipedia.org/wiki/Portal:Current_events/2016_June_23"
    assert wce.yyyymmdd(DAY_20160623) == "20160623"


def test_a_page_day_is_stamped_at_the_end_of_the_day_and_lagged_from_there() -> None:
    """Section 5.5: the page of D is published at the end of D and readable at D+1 06:00Z by default."""
    item = parsed_2016()[0]
    assert item.published_at_ms == DAY_20160623 + MS_PER_DAY
    assert item.visible_from_ms == item.published_at_ms + SAFETY_LAG_MS_DEFAULT
    assert item.visible_from_ms == DAY_20160623 + MS_PER_DAY + 6 * 3_600_000


def test_the_item_id_names_the_page_day_while_its_file_day_is_the_next_one() -> None:
    """Ruling R7: ``wce-20160623-0007`` lives in ``news/20160624.jsonl``, and that is deliberate."""
    item = parsed_2016()[7]
    assert item.news_id == "wce-20160623-0007"
    assert wce.yyyymmdd(day_start_ms(item.published_at_ms)) == "20160624"


def test_the_safety_lag_is_applied_at_build_time_by_the_fetcher() -> None:
    items = wce.parse_current_events(
        fixture_wikitext("wce_parse_20160623.json"),
        day_start_ms=DAY_20160623,
        fetched_at_ms=1,
        safety_lag_ms=3 * MS_PER_DAY,
    )
    assert items
    assert all(item.visible_from_ms == item.published_at_ms + 3 * MS_PER_DAY for item in items)


def fixture_wikitext(name: str) -> str:
    payload = fixture_json(name)
    assert isinstance(payload, dict)
    parse = payload["parse"]
    assert isinstance(parse, dict)
    wikitext = parse["wikitext"]
    assert isinstance(wikitext, str)
    return wikitext


# --------------------------------------------------------------------------------------------------
# Wikipedia Current events: the parser
# --------------------------------------------------------------------------------------------------
def test_the_2016_day_page_parses_one_item_per_leaf_bullet_with_its_section() -> None:
    items = parsed_2016()
    assert len(items) == 17
    assert [item.news_id for item in items] == [f"wce-20160623-{index:04d}" for index in range(17)]
    assert [item.section for item in items] == [
        "armed_conflicts",
        "disasters",
        "international_relations",
        "international_relations",
        "international_relations",
        "international_relations",
        "law_crime",
        "law_crime",
        "law_crime",
        "law_crime",
        "law_crime",
        "politics",
        "politics",
        "politics",
        "politics",
        "science_technology",
        "sports",
    ]
    assert all(item.source == "wikipedia_current_events" for item in items)
    assert all(item.kind == "headline" for item in items)
    assert all(item.schema_version == NEWS_SCHEMA for item in items)
    assert all(item.lang == "en" for item in items)
    assert all(item.revid is None and item.asof_day is None for item in items)


def test_the_2025_day_page_parses_the_bold_heading_format() -> None:
    """The heading spelling changed between 2016 and 2025; both must yield the same slugs."""
    items = wce.parse_current_events(
        fixture_wikitext("wce_parse_20250903.json"), day_start_ms=DAY_20250903, fetched_at_ms=1
    )
    assert len(items) == 22
    assert items[0].section == "armed_conflicts"
    assert items[0].news_id == "wce-20250903-0000"
    sections = {item.section for item in items}
    assert sections == {
        "armed_conflicts",
        "arts_culture",
        "business",
        "disasters",
        "international_relations",
        "law_crime",
        "politics",
        "science_technology",
    }
    assert "Gaza war" in items[0].wiki_links


def test_a_leaf_inherits_the_topic_links_of_the_bullets_above_it() -> None:
    """The referendum article title appears only on the parent bullet, and it is the one the linker needs."""
    items = parsed_2016()
    brexit = items[11]
    assert brexit.section == "politics"
    assert brexit.text.startswith("Voters in the United Kingdom go to the polls")
    assert "United Kingdom European Union membership referendum, 2016" in brexit.wiki_links
    assert "United Kingdom" in brexit.wiki_links
    # The parent bullet is a topic, not an event: it produced no item of its own.
    assert len(items) > 11
    assert all(item.text != "United Kingdom European Union membership referendum, 2016" for item in items)


def test_the_parser_strips_the_markup_and_keeps_the_citations_separately() -> None:
    items = parsed_2016()
    tornado = items[1]
    assert tornado.section == "disasters"
    assert "hailstones, kills at least 98 people" in tornado.text
    assert "Lianshui County" in tornado.text
    assert len(tornado.source_urls) == 3
    assert tornado.source_urls[0] == "http://weibo.com/1618051664/DBGLigdOj"
    for item in items:
        assert "[[" not in item.text
        assert "'''" not in item.text
        assert "http" not in item.text
        assert "<!--" not in item.text
        assert item.text == item.text.strip()
        assert item.headline
        assert len(item.headline) <= 300
        assert len(item.text) <= 4_000
        assert len(item.wiki_links) <= 32
        assert len(item.source_urls) <= 16
        assert list(item.wiki_links) == sorted(set(item.wiki_links))
        assert item.url == wce.page_url_for(DAY_20160623)


def test_a_headline_longer_than_the_cap_is_clipped_with_an_ellipsis() -> None:
    long_text = "word " * 200
    items = wce.parse_current_events(
        f"'''Politics and elections'''\n*{long_text}\n", day_start_ms=DAY_20160623, fetched_at_ms=1
    )
    assert len(items) == 1
    assert len(items[0].headline) == 300
    assert items[0].headline.endswith("...")
    assert items[0].text.startswith("word word")


def test_a_bullet_with_no_text_left_yields_no_item_and_consumes_no_index() -> None:
    wikitext = "'''Politics and elections'''\n*{{template}}\n*Real news happened today.\n"
    items = wce.parse_current_events(wikitext, day_start_ms=DAY_20160623, fetched_at_ms=1)
    assert len(items) == 1
    assert items[0].news_id == "wce-20160623-0000"
    assert items[0].text == "Real news happened today."


def test_an_unknown_heading_is_slugified_and_an_unusable_one_is_dropped() -> None:
    assert wce.section_slug("Armed conflicts and attacks") == "armed_conflicts"
    assert wce.section_slug("Sport") == "sports"
    assert wce.section_slug("Business, industry and money") == "business_industry_and_money"
    assert wce.section_slug("!!!") is None
    slug = wce.section_slug("x" * 80)
    assert slug is not None
    assert len(slug) == 48


def test_two_parses_of_the_same_page_agree_field_for_field() -> None:
    first = parsed_2016()
    second = parsed_2016()
    assert [item.to_dict() for item in first] == [item.to_dict() for item in second]


# --------------------------------------------------------------------------------------------------
# Wikipedia Current events: the fetcher
# --------------------------------------------------------------------------------------------------
def test_the_fetcher_asks_for_the_day_page_with_a_descriptive_user_agent(tmp_path: Path) -> None:
    """A generic User-Agent earns a 403 from the MediaWiki API, verified live on 2026-09-07."""
    handler, seen = recording_handler(fixture_text("wce_parse_20160623.json"))
    client = client_for(tmp_path, handler)
    items = wce.fetch_wikipedia_current_events(client=client, day_start_ms=DAY_20160623)  # type: ignore[arg-type]
    assert len(items) == 17
    assert len(seen) == 1
    request = seen[0]
    assert request.url.path == wce.MEDIAWIKI_PATH
    query = query_of(request)
    assert query["action"] == "parse"
    assert query["prop"] == "wikitext"
    assert query["formatversion"] == "2"
    assert query["page"] == "Portal:Current events/2016 June 23"
    agent = request.headers["User-Agent"]
    assert agent.startswith("pmx-research/")
    assert CONTACT in agent
    assert items[0].fetched_at_ms > 1_600_000_000_000


def test_a_day_without_a_page_yields_no_items_rather_than_an_error(tmp_path: Path) -> None:
    handler, seen = recording_handler(fixture_text("wce_parse_missing.json"))
    client = client_for(tmp_path, handler)
    assert wce.fetch_wikipedia_current_events(client=client, day_start_ms=DAY_20160623) == ()  # type: ignore[arg-type]
    assert len(seen) == 1


def test_another_mediawiki_error_is_a_malformed_response(tmp_path: Path) -> None:
    handler, _ = recording_handler(json.dumps({"error": {"code": "readapidenied", "info": "no"}}))
    client = client_for(tmp_path, handler)
    with pytest.raises(MalformedResponseError) as raised:
        wce.fetch_wikipedia_current_events(client=client, day_start_ms=DAY_20160623)  # type: ignore[arg-type]
    assert raised.value.context["code"] == "readapidenied"


def test_a_response_without_wikitext_is_a_malformed_response(tmp_path: Path) -> None:
    handler, _ = recording_handler(json.dumps({"parse": {"title": "x", "pageid": 1}}))
    client = client_for(tmp_path, handler)
    with pytest.raises(MalformedResponseError):
        wce.fetch_wikipedia_current_events(client=client, day_start_ms=DAY_20160623)  # type: ignore[arg-type]


# --------------------------------------------------------------------------------------------------
# The point-in-time background article
# --------------------------------------------------------------------------------------------------
def asof_fixture() -> dict[str, object]:
    payload = fixture_json("wasof_revisions_20160620.json")
    assert isinstance(payload, dict)
    return payload


def asof_content() -> str:
    revision = asof_fixture()["query"]["pages"][0]["revisions"][0]  # type: ignore[index]
    content = revision["slots"]["main"]["content"]
    assert isinstance(content, str)
    return content


def test_the_snapshot_stores_the_revision_it_came_from_byte_for_byte(tmp_path: Path) -> None:
    """Section 7.1: the stored text must be checkable against the revision named by its ``revid``."""
    handler, seen = recording_handler(fixture_text("wasof_revisions_20160620.json"))
    client = client_for(tmp_path, handler)
    items = wa.fetch_wikipedia_asof(
        client=client,  # type: ignore[arg-type]
        title="United Kingdom European Union membership referendum",
        asof_day="2016-06-20",
        market_id="demo-brexit-2016",
    )
    assert len(items) == 1
    item = items[0]
    content = asof_content()
    assert len(content) > 4_000
    assert item.text == content[:4_000]
    assert not item.text.endswith("...")
    assert item.revid == 726_239_737
    assert item.asof_day == "2016-06-20"
    assert item.url == "https://en.wikipedia.org/w/index.php?oldid=726239737"
    assert item.source == "wikipedia_asof"
    assert item.kind == "background"
    assert item.section is None
    assert item.source_urls == ()
    assert item.headline == "United Kingdom European Union membership referendum"
    assert "United Kingdom European Union membership referendum" in item.wiki_links
    assert len(item.wiki_links) <= 32
    assert item.published_at_ms == 1_466_463_744_000
    assert item.published_at_ms <= day_start_ms(item.published_at_ms) + MS_PER_DAY
    assert item.visible_from_ms == item.published_at_ms + SAFETY_LAG_MS_DEFAULT
    assert item.news_id.startswith("wasof-20160620-")
    query = query_of(seen[0])
    assert query["prop"] == "revisions"
    assert query["rvstart"] == "2016-06-20T23:59:59Z"
    assert query["rvdir"] == "older"
    assert query["rvlimit"] == "1"
    assert query["rvprop"] == "ids|timestamp|content"
    assert query["titles"] == "United Kingdom European Union membership referendum"


def test_a_revision_newer_than_the_day_it_was_asked_for_is_a_leak(tmp_path: Path) -> None:
    """The API ordering is not trusted: today's article stamped with an early date is the design's worst leak."""
    payload = asof_fixture()
    revision = payload["query"]["pages"][0]["revisions"][0]  # type: ignore[index]
    revision["timestamp"] = "2016-06-24T10:00:00Z"
    handler, _ = recording_handler(json.dumps(payload))
    client = client_for(tmp_path, handler)
    with pytest.raises(LeakError) as raised:
        wa.fetch_wikipedia_asof(
            client=client,  # type: ignore[arg-type]
            title="United Kingdom European Union membership referendum",
            asof_day="2016-06-20",
            market_id="demo-brexit-2016",
        )
    assert raised.value.context["revid"] == 726_239_737


def test_a_missing_page_yields_no_snapshot(tmp_path: Path) -> None:
    body = json.dumps({"query": {"pages": [{"title": "Nope", "missing": True}]}})
    handler, _ = recording_handler(body)
    client = client_for(tmp_path, handler)
    assert (
        wa.fetch_wikipedia_asof(
            client=client,  # type: ignore[arg-type]
            title="Nope",
            asof_day="2016-06-20",
            market_id="demo-brexit-2016",
        )
        == ()
    )


def test_a_page_with_no_revision_by_that_day_yields_no_snapshot(tmp_path: Path) -> None:
    body = json.dumps({"query": {"pages": [{"title": "Later", "pageid": 5, "revisions": []}]}})
    handler, _ = recording_handler(body)
    client = client_for(tmp_path, handler)
    assert (
        wa.fetch_wikipedia_asof(
            client=client,  # type: ignore[arg-type]
            title="Later",
            asof_day="2016-06-20",
            market_id="demo-brexit-2016",
        )
        == ()
    )


def test_the_snapshot_id_is_deterministic_and_separates_two_markets() -> None:
    first = wa.news_id_index("demo-brexit-2016", "Brexit")
    assert first == wa.news_id_index("demo-brexit-2016", "Brexit")
    assert 0 <= first < 10_000
    assert first != wa.news_id_index("kalshi-BREXIT-24", "Brexit")


def test_the_snapshot_schedule_is_weekly_and_stops_before_the_settling_bar() -> None:
    """Section 7.1: one snapshot per seven days of life, and none from the day the outcome is public."""
    created_ms = 1_451_606_400_000  # 2016-01-01T00:00Z
    resolved_ms = 1_466_726_400_000 + 3_600_000  # 2016-06-24T01:00Z, so the settling bar is 2016-06-24
    brexit = market(
        "demo-brexit-2016",
        "Will the UK leave?",
        created_at_ms=created_ms,
        resolved_at_ms=resolved_ms,
    )
    days = wa.asof_days_for(brexit)
    assert days[0] == "2016-01-01"
    assert days[-1] == "2016-06-17"
    assert len(days) == 25
    assert "2016-06-24" not in days
    assert "2016-06-23" not in days
    for earlier, later in zip(days, days[1:], strict=False):
        assert wa.day_start_ms_of(later) - wa.day_start_ms_of(earlier) == 7 * MS_PER_DAY
    assert all(wa.day_start_ms_of(day) < day_start_ms(resolved_ms) for day in days)


def test_a_market_that_settles_the_day_it_opened_gets_no_snapshot_day() -> None:
    same_day = market(
        "demo-flash",
        "Will it settle today?",
        created_at_ms=DAY_20160623,
        resolved_at_ms=DAY_20160623 + 3_600_000,
    )
    assert wa.asof_days_for(same_day) == ()


def test_an_impossible_asof_day_is_refused() -> None:
    assert wa.day_start_ms_of("1970-01-01") == 0
    assert wa.day_start_ms_of("2016-06-20") == 1_466_380_800_000
    with pytest.raises(InvalidConfigError):
        wa.day_start_ms_of("20160620")
    with pytest.raises(InvalidConfigError):
        wa.day_start_ms_of("2016-02-31")


def test_a_broken_revision_timestamp_is_a_malformed_response() -> None:
    assert wa.timestamp_ms("2016-06-20T23:02:24Z") == 1_466_463_744_000
    with pytest.raises(MalformedResponseError):
        wa.timestamp_ms("2016-06-20 23:02:24")


# --------------------------------------------------------------------------------------------------
# The Wayback front pages
# --------------------------------------------------------------------------------------------------
def test_the_first_capture_of_the_day_becomes_a_frontpage_item(tmp_path: Path) -> None:
    handler, seen = recording_handler(fixture_text("cdx_reuters_20160623.json"))
    client = client_for(tmp_path, handler, base_url=wb.WAYBACK_BASE_URL, min_interval_ms=0)
    items = wb.fetch_wayback(client=client, day_start_ms=DAY_20160623, front_pages=("reuters.com",))  # type: ignore[arg-type]
    assert len(items) == 1
    item = items[0]
    assert item.news_id == "wb-20160623-0000"
    assert item.source == "wayback"
    assert item.kind == "frontpage"
    assert item.text == ""
    assert item.wiki_links == ()
    assert item.published_at_ms == DAY_20160623 + ((0 * 60 + 8) * 60 + 40) * 1_000
    assert item.visible_from_ms == item.published_at_ms + SAFETY_LAG_MS_DEFAULT
    assert item.url == "https://web.archive.org/web/20160623000840/http://www.reuters.com/"
    assert item.source_urls == (item.url,)
    assert item.headline == "reuters.com front page archived 2016-06-23 00:08Z"
    query = query_of(seen[0])
    assert query["url"] == "reuters.com"
    assert query["from"] == "20160623"
    assert query["to"] == "20160623"
    assert query["output"] == "json"


def test_a_capture_from_another_day_is_dropped(tmp_path: Path) -> None:
    body = json.dumps(
        [
            ["urlkey", "timestamp", "original", "mimetype", "statuscode", "digest", "length"],
            ["com,reuters)/", "20160624000840", "http://www.reuters.com/", "text/html", "200", "X", "1"],
        ]
    )
    handler, _ = recording_handler(body)
    client = client_for(tmp_path, handler, base_url=wb.WAYBACK_BASE_URL)
    assert wb.fetch_wayback(client=client, day_start_ms=DAY_20160623, front_pages=("reuters.com",)) == ()  # type: ignore[arg-type]


def test_an_archive_outage_drops_that_site_and_keeps_the_ids_dense(tmp_path: Path) -> None:
    """The archive is optional (section 7.12): one site failing must not cost the day its other items."""
    good = fixture_text("cdx_reuters_20160623.json")

    def handle(request: httpx.Request) -> httpx.Response:
        if "npr.org" in request.url.query.decode("ascii"):
            return httpx.Response(503, text="Service Unavailable")
        if "apnews.com" in request.url.query.decode("ascii"):
            return httpx.Response(200, text="<html>the archive is down</html>")
        return httpx.Response(200, text=good)

    client = client_for(tmp_path, handle, base_url=wb.WAYBACK_BASE_URL)
    items = wb.fetch_wayback(
        client=client,  # type: ignore[arg-type]
        day_start_ms=DAY_20160623,
        front_pages=("npr.org", "apnews.com", "reuters.com"),
    )
    assert [item.news_id for item in items] == ["wb-20160623-0000"]
    assert items[0].headline.startswith("reuters.com")


def test_a_json_body_that_is_not_a_cdx_table_raises(tmp_path: Path) -> None:
    handler, _ = recording_handler(json.dumps({"error": "the index moved"}))
    client = client_for(tmp_path, handler, base_url=wb.WAYBACK_BASE_URL)
    with pytest.raises(MalformedResponseError):
        wb.fetch_wayback(client=client, day_start_ms=DAY_20160623, front_pages=("reuters.com",))  # type: ignore[arg-type]


def test_an_empty_cdx_table_yields_nothing(tmp_path: Path) -> None:
    header = [["urlkey", "timestamp", "original", "mimetype", "statuscode", "digest", "length"]]
    handler, _ = recording_handler(json.dumps(header))
    client = client_for(tmp_path, handler, base_url=wb.WAYBACK_BASE_URL)
    assert wb.fetch_wayback(client=client, day_start_ms=DAY_20160623, front_pages=("reuters.com",)) == ()  # type: ignore[arg-type]


# --------------------------------------------------------------------------------------------------
# GDELT
# --------------------------------------------------------------------------------------------------
def test_a_day_of_gdelt_articles_becomes_items_in_a_reproducible_order(tmp_path: Path) -> None:
    handler, seen = recording_handler(fixture_text("gdelt_doc_20250903.json"))
    client = client_for(
        tmp_path, handler, base_url=gd.GDELT_BASE_URL, min_interval_ms=gd.GDELT_MIN_INTERVAL_MS
    )
    items = gd.fetch_gdelt(
        client=client,  # type: ignore[arg-type]
        day_start_ms=DAY_20250903,
        now_ms=DAY_20250903 + 10 * MS_PER_DAY,
    )
    payload = fixture_json("gdelt_doc_20250903.json")
    assert isinstance(payload, dict)
    articles = payload["articles"]
    assert isinstance(articles, list)
    assert len(items) == len(articles) > 20
    assert [item.news_id for item in items] == [f"gd-20250903-{index:04d}" for index in range(len(items))]
    assert all(item.source == "gdelt" and item.kind == "article" for item in items)
    assert all(item.lang == "en" for item in items)
    assert all(DAY_20250903 <= item.published_at_ms < DAY_20250903 + MS_PER_DAY for item in items)
    assert all(item.text == "" for item in items)
    assert all(item.url == item.source_urls[0] for item in items)
    ordered = [(item.published_at_ms, item.url) for item in items]
    assert ordered == sorted(ordered)
    query = query_of(seen[0])
    assert query["mode"] == "artlist"
    assert query["startdatetime"] == "20250903000000"
    assert query["enddatetime"] == "20250903235959"
    assert query["query"] == gd.GDELT_QUERY


def test_a_client_that_would_earn_a_ban_is_refused(tmp_path: Path) -> None:
    """One request per five seconds is documented; going faster is answered with a 429 and then a ban."""
    handler, seen = recording_handler(fixture_text("gdelt_doc_20250903.json"))
    client = client_for(tmp_path, handler, base_url=gd.GDELT_BASE_URL, min_interval_ms=1_000)
    with pytest.raises(InvalidConfigError) as raised:
        gd.fetch_gdelt(client=client, day_start_ms=DAY_20250903, now_ms=DAY_20250903)  # type: ignore[arg-type]
    assert raised.value.context["required_ms"] == 5_000
    assert seen == []


def test_the_plain_text_warning_is_a_soft_failure(tmp_path: Path) -> None:
    handler, seen = recording_handler(fixture_text("gdelt_warning.txt"))
    client = client_for(
        tmp_path, handler, base_url=gd.GDELT_BASE_URL, min_interval_ms=gd.GDELT_MIN_INTERVAL_MS
    )
    assert (
        gd.fetch_gdelt(client=client, day_start_ms=DAY_20250903, now_ms=DAY_20250903 + MS_PER_DAY) == ()  # type: ignore[arg-type]
    )
    assert len(seen) == 1


def test_a_429_after_every_retry_is_a_soft_failure(tmp_path: Path) -> None:
    handler, seen = recording_handler("Too Many Requests", status=429)
    client = client_for(
        tmp_path, handler, base_url=gd.GDELT_BASE_URL, min_interval_ms=gd.GDELT_MIN_INTERVAL_MS
    )
    assert (
        gd.fetch_gdelt(client=client, day_start_ms=DAY_20250903, now_ms=DAY_20250903 + MS_PER_DAY) == ()  # type: ignore[arg-type]
    )
    assert len(seen) > 1


def test_a_day_outside_the_documented_window_costs_no_request(tmp_path: Path) -> None:
    handler, seen = recording_handler(fixture_text("gdelt_doc_20250903.json"))
    client = client_for(
        tmp_path, handler, base_url=gd.GDELT_BASE_URL, min_interval_ms=gd.GDELT_MIN_INTERVAL_MS
    )
    stale = DAY_20250903 + (gd.GDELT_WINDOW_DAYS + 1) * MS_PER_DAY
    assert gd.fetch_gdelt(client=client, day_start_ms=DAY_20250903, now_ms=stale) == ()  # type: ignore[arg-type]
    assert seen == []


def test_articles_outside_the_day_or_the_language_are_dropped(tmp_path: Path) -> None:
    body = json.dumps(
        {
            "articles": [
                {
                    "url": "https://example.invalid/a",
                    "title": "Inside the day",
                    "seendate": "20250903T120000Z",
                    "language": "English",
                },
                {
                    "url": "https://example.invalid/b",
                    "title": "The day after",
                    "seendate": "20250904T000000Z",
                    "language": "English",
                },
                {
                    "url": "https://example.invalid/c",
                    "title": "Pas en anglais",
                    "seendate": "20250903T130000Z",
                    "language": "French",
                },
                {"url": "https://example.invalid/d", "title": "No date"},
            ]
        }
    )
    handler, _ = recording_handler(body)
    client = client_for(
        tmp_path, handler, base_url=gd.GDELT_BASE_URL, min_interval_ms=gd.GDELT_MIN_INTERVAL_MS
    )
    items = gd.fetch_gdelt(
        client=client,  # type: ignore[arg-type]
        day_start_ms=DAY_20250903,
        now_ms=DAY_20250903 + MS_PER_DAY,
    )
    assert [item.headline for item in items] == ["Inside the day"]


# --------------------------------------------------------------------------------------------------
# The linker
# --------------------------------------------------------------------------------------------------
def test_the_score_is_the_two_terms_of_the_contract_and_nothing_else() -> None:
    """Section 7.6, by hand: two of four links shared, and two of five market keywords matched."""
    score = lk.link_score_permille(
        item_links=("Alpha", "Beta", "Gamma", "Delta"),
        item_keywords=frozenset({"referendum", "kingdom"}),
        market_subjects=("Alpha", "Beta"),
        market_keywords=frozenset({"referendum", "kingdom", "leave", "union", "membership"}),
    )
    keyword_overlap = round_half_up(1_000 * 2, 5)
    assert keyword_overlap == 400
    assert score == round_half_up(600 * 2, 4) + (400 * 400) // 1_000
    assert score == 300 + 160


def test_a_perfect_match_is_exactly_one_thousand_permille() -> None:
    score = lk.link_score_permille(
        item_links=("Alpha",),
        item_keywords=frozenset({"referendum"}),
        market_subjects=("Alpha",),
        market_keywords=frozenset({"referendum"}),
    )
    assert score == 1_000


def test_an_item_with_nothing_in_common_scores_zero_and_is_not_linked() -> None:
    score = lk.link_score_permille(
        item_links=("Alpha",),
        item_keywords=frozenset({"tornado"}),
        market_subjects=("Beta",),
        market_keywords=frozenset({"referendum"}),
    )
    assert score == 0
    assert score < LINK_THRESHOLD_PERMILLE


def test_a_market_with_no_keywords_scores_only_the_link_term() -> None:
    score = lk.link_score_permille(
        item_links=("Alpha", "Beta"),
        item_keywords=frozenset({"tornado"}),
        market_subjects=("Alpha",),
        market_keywords=frozenset(),
    )
    assert score == 300


def test_the_linker_links_the_brexit_bullet_to_the_brexit_market_and_stores_the_score() -> None:
    items = parsed_2016()
    brexit = market(
        "demo-brexit-2016",
        "Will the United Kingdom vote to leave the European Union in the 2016 referendum?",
        wiki_subjects=("United Kingdom European Union membership referendum, 2016",),
    )
    tornado = market(
        "demo-jiangsu-2016",
        "Will a tornado in Jiangsu kill more than fifty people?",
        wiki_subjects=("2016 Jiangsu tornado",),
        category="weather",
    )
    linked = lk.link_items(items, [brexit, tornado])
    by_id = {item.news_id: item for item in linked}
    referendum = by_id["wce-20160623-0011"]
    assert referendum.match_ids == ("demo-brexit-2016",)
    assert referendum.match_scores_permille[0] >= LINK_THRESHOLD_PERMILLE
    assert referendum.score_for("demo-brexit-2016") == referendum.match_scores_permille[0]
    assert referendum.score_for("demo-jiangsu-2016") == 0
    jiangsu = by_id["wce-20160623-0001"]
    assert jiangsu.match_ids == ("demo-jiangsu-2016",)
    # The NBA draft bullet shares neither an article nor a keyword with either market.
    assert by_id["wce-20160623-0016"].match_ids == ()
    # Every stored score is aligned with its id, inside the schema's range, and reproducible.
    for item in linked:
        assert len(item.match_ids) == len(item.match_scores_permille)
        assert list(item.match_ids) == sorted(item.match_ids)
        assert all(LINK_THRESHOLD_PERMILLE <= score <= 1_000 for score in item.match_scores_permille)
    again = lk.link_items(items, [brexit, tornado])
    assert [item.to_dict() for item in again] == [item.to_dict() for item in linked]


def test_match_ids_are_sorted_whatever_order_the_markets_arrived_in() -> None:
    """Section 7.3 stores ``match_ids`` sorted, and the caller's market order is not an ordering."""
    item = news_item(
        "wce-20160623-0000",
        headline="The referendum result is announced",
        wiki_links=("Alpha", "Zebra"),
    )
    zebra = market("demo-zebra", "Will the referendum result be announced?", wiki_subjects=("Zebra",))
    alpha = market("demo-alpha", "Will the referendum result be announced?", wiki_subjects=("Alpha",))
    linked = lk.link_items([item], [zebra, alpha])
    assert linked[0].match_ids == ("demo-alpha", "demo-zebra")
    assert linked[0].match_scores_permille == (
        linked[0].score_for("demo-alpha"),
        linked[0].score_for("demo-zebra"),
    )
    mirrored = lk.link_items([item], [alpha, zebra])
    assert mirrored[0].to_dict() == linked[0].to_dict()


def test_the_linker_leaves_its_input_untouched() -> None:
    item = news_item("wce-20160623-0000", headline="Voters go to the polls", wiki_links=("Alpha",))
    target = market("demo-alpha", "Will the voters go to the polls?", wiki_subjects=("Alpha",))
    linked = lk.link_items([item], [target])
    assert linked[0].match_ids == ("demo-alpha",)
    assert item.match_ids == ()
    assert item.match_scores_permille == ()
    assert linked[0] is not item


def test_shared_links_are_counted_against_wiki_subjects_and_never_against_tags() -> None:
    """Ruling R17: a tag cannot hold an article title, and comparing against tags scored zero for the
    market that carried the subject in the field designed for it."""
    item = news_item("wce-20160623-0000", headline="Nothing in common", wiki_links=("2016 Jiangsu tornado",))
    with_subject = market("demo-with", "Question", wiki_subjects=("2016 Jiangsu tornado",))
    with_tag_only = market("demo-without", "Question", tags=("tornado",))
    stopwords = lk.load_stopwords()
    assert lk.score_item_against_market(item, with_subject, stopwords) == 600
    assert lk.score_item_against_market(item, with_tag_only, stopwords) == 0


def test_the_stop_list_drops_the_words_every_item_shares() -> None:
    stopwords = lk.load_stopwords()
    assert "would" in stopwords
    assert "referendum" not in stopwords
    assert all(len(word) >= 4 and word.isalpha() and word.islower() for word in stopwords)
    tokens = lk.tokens_of(("The government would have said that it will report today",), stopwords)
    assert tokens == frozenset({"government"})


def test_the_tokeniser_keeps_alphabetic_tokens_of_four_characters_or_more() -> None:
    tokens = lk.tokens_of(("UK vote 2016: leave or Remain!",), frozenset())
    assert tokens == frozenset({"vote", "leave", "remain"})


def test_the_digest_order_is_best_link_then_oldest_then_id() -> None:
    weak = news_item("wce-20160623-0002", published_at_ms=DAY_20160623)
    strong_late = news_item("wce-20160623-0001", published_at_ms=DAY_20160623 + MS_PER_DAY)
    strong_early = news_item("wce-20160623-0000", published_at_ms=DAY_20160623)
    ranked = rank_news_items(
        [
            lk.replace_item(weak, match_ids=("demo-a",), match_scores_permille=(200,)),
            lk.replace_item(strong_late, match_ids=("demo-a",), match_scores_permille=(900,)),
            lk.replace_item(strong_early, match_ids=("demo-a",), match_scores_permille=(900,)),
        ],
        market_id="demo-a",
    )
    assert [item.news_id for item in ranked] == [
        "wce-20160623-0000",
        "wce-20160623-0001",
        "wce-20160623-0002",
    ]
    unlinked = rank_news_items([weak, strong_early], market_id="demo-b")
    assert [item.news_id for item in unlinked] == ["wce-20160623-0000", "wce-20160623-0002"]


def test_the_linker_keeps_a_link_the_venue_itself_stated() -> None:
    """Ruling R95: ``link_items`` adds links, it does not replace them.

    A Manifold comment arrives from D3 already linked to its own market at 1000 permille, which is the one
    link in the system that is stated rather than inferred. Before the ruling, passing comments through
    the linker unlinked every one of them, because a comment's text rarely scores 150 against its market's
    question. The market below deliberately shares no article title and no keyword with the comment, so a
    linker that recomputed from scratch would return an empty ``match_ids``.
    """
    comment = lk.replace_item(
        news_item(
            "mfc-20160623-0000",
            headline="i think this is going the other way",
            text="my read of the polling is that turnout decides it",
        ),
        source="manifold_comment",
        kind="comment",
        match_ids=("manifold-abc",),
        match_scores_permille=(1_000,),
    )
    target = market(
        "manifold-abc",
        "Will the incumbent hold the seat?",
        wiki_subjects=("Some Unrelated Article",),
    )
    assert lk.score_item_against_market(comment, target, lk.load_stopwords()) < LINK_THRESHOLD_PERMILLE
    (linked,) = lk.link_items([comment], [target])
    assert linked.match_ids == ("manifold-abc",)
    assert linked.match_scores_permille == (1_000,)


def test_clipping_is_exact_at_the_boundary() -> None:
    assert lk.clip("abcd", 4) == "abcd"
    assert lk.clip("abcde", 4) == "a..."
    assert lk.clip("abcde", 0) == ""
    assert lk.clip("abcde", 2) == "ab"



# --------------------------------------------------------------------------------------------------
# The renormalised score, and the subjects a question yields
# --------------------------------------------------------------------------------------------------
def test_a_market_with_no_subject_is_scored_on_its_keywords_alone() -> None:
    """The defect the first real dataset exposed: the dominant term was structurally zero.

    Section 7.6 weights shared article titles at 600 permille and the keyword overlap at 400. A market
    with no ``wiki_subjects`` has no share to compute, so its score could never exceed 400 and a link
    needed a keyword overlap of 375 permille to clear a threshold of 150. Renormalised over the evidence
    the market actually carries, the keyword overlap carries the whole thousand, and the same threshold
    decides it.
    """
    item = news_item(
        "wce-20160623-0000",
        headline="Voters go to the polls in the referendum",
        text="Turnout is high across the country",
        wiki_links=("Some Article",),
    )
    stopwords = lk.load_stopwords()
    without = market("demo-none", "Will the referendum turnout be high?")
    assert without.wiki_subjects == ()
    keywords_only = lk.score_item_against_market(item, without, stopwords)
    assert keywords_only == 1_000, "every keyword of the question is in the item"
    assert keywords_only >= LINK_THRESHOLD_PERMILLE

    # A market that does carry a subject keeps the 600/400 split of section 7.6 untouched.
    with_subject = market(
        "demo-some", "Will the referendum turnout be high?", wiki_subjects=("Some Article",)
    )
    assert lk.score_item_against_market(item, with_subject, stopwords) == 600 + 400


def test_the_renormalised_score_still_refuses_a_weak_overlap() -> None:
    """Renormalising raises the ceiling; it does not lower the bar."""
    item = news_item(
        "wce-20160623-0001",
        headline="Cricket season opens in Adelaide",
        text="The visiting side won the toss",
    )
    subjectless = market(
        "demo-none",
        "Will the central bank raise interest rates before the general election in France?",
    )
    score = lk.score_item_against_market(item, subjectless, lk.load_stopwords())
    assert score < LINK_THRESHOLD_PERMILLE
    (linked,) = lk.link_items([item], [subjectless])
    assert linked.match_ids == ()


def test_the_link_index_answers_what_scoring_every_pair_answers() -> None:
    """The index is an optimisation, so it has to be indistinguishable from the double loop."""
    items = parsed_2016()
    markets = [
        market("demo-brexit-2016", "Will the United Kingdom vote to leave the European Union?"),
        market("demo-jiangsu-2016", "Will a tornado in Jiangsu kill more than fifty people?"),
        market("demo-nba-2016", "Will the first pick of the NBA draft be a centre?", category="sports"),
    ]
    stopwords = lk.load_stopwords()
    index = lk.LinkIndex(
        [
            lk.market_terms_of(
                market_id=entry.id,
                question=entry.question,
                tags=entry.tags,
                wiki_subjects=entry.wiki_subjects,
                stopwords=stopwords,
            )
            for entry in markets
        ]
    )
    for item in items:
        by_index = index.links_for(
            item_links=tuple(item.wiki_links), item_keywords=lk.item_tokens(item, stopwords)
        )
        by_pair = tuple(
            sorted(
                (entry.id, lk.score_item_against_market(item, entry, stopwords))
                for entry in markets
                if lk.score_item_against_market(item, entry, stopwords) >= LINK_THRESHOLD_PERMILLE
            )
        )
        assert by_index == by_pair, item.news_id


def test_a_question_yields_its_capitalised_runs_as_derived_subjects() -> None:
    stopwords = lk.load_stopwords()
    assert lk.derived_subjects_of(
        "Will Donald Trump and Zohran Mamdani meet before Jan 1, 2026?", stopwords
    ) == ("Donald Trump", "Zohran Mamdani")
    # The leading question word is a stop word and is trimmed off the run it starts.
    assert lk.derived_subjects_of("What will the Bank of England do?", stopwords)[0] == "Bank"
    # Runs are deduplicated in order of first appearance and capped.
    assert lk.derived_subjects_of("Alpha Alpha Bravo Charlie Delta Echo Foxtrot", stopwords) == (
        "Alpha Alpha Bravo Charlie Delta Echo Foxtrot",
    )
    assert lk.derived_subjects_of("nothing capitalised here at all", stopwords) == ()
    assert lk.derived_subjects_of("A US AI EV question", stopwords) == ()


def test_merged_subjects_are_sorted_aligned_and_capped_with_the_stated_ones_first() -> None:
    titles, flags = lk.merge_subjects(("Zebra", "Alpha"), ("Alpha", "Mango"))
    assert titles == ("Alpha", "Mango", "Zebra")
    assert flags == ("stated", "derived", "stated"), "a title both sources offer is stated"
    many, many_flags = lk.merge_subjects(
        tuple(f"Stated {index}" for index in range(8)), ("Derived",)
    )
    assert len(many) == len(many_flags) == 8
    assert set(many_flags) == {"stated"}
    assert lk.merge_subjects((), ()) == ((), ())


# --------------------------------------------------------------------------------------------------
# The lexicons
# --------------------------------------------------------------------------------------------------
def test_there_is_exactly_one_lexicon_per_category() -> None:
    assert LEXICON_COUNT == len(CATEGORIES) == 12
    for index, category in enumerate(CATEGORIES):
        lexicon = lk.load_lexicon(category)
        assert lexicon.lexicon_id == f"{category}.v1"
        assert (LEXICONS / f"{category}.v1.json").exists()
        assert not lexicon.is_empty, category
        assert 0 <= index < LEXICON_COUNT
    shipped = sorted(path.name for path in LEXICONS.glob("*.v1.json"))
    assert shipped == sorted(
        [f"{category}.v1.json" for category in CATEGORIES]
        + ["paraphrases.v1.json", "stopwords.v1.json"]
        + KALSHI_SERIES_FILES
    )


#: The two series-keyed data files D2 reads. They are not lexicons and are not one per category: they
#: live in this directory for the reason ruling R94 moved the lexicons into the package, which is that a
#: path relative to the repository root does not exist in an installed wheel. The inventory above names
#: them so that a third file nobody declared still fails a test.
KALSHI_SERIES_FILES = [
    "kalshi_series_categories.v1.json",
    "kalshi_series_subjects.v1.json",
]


def test_a_lexicon_has_two_disjoint_sides_of_well_formed_tokens() -> None:
    for category in CATEGORIES:
        lexicon = lk.load_lexicon(category)
        both = set(lexicon.for_permille) & set(lexicon.against_permille)
        assert both == set(), (category, both)
        assert len(lexicon.for_permille) >= 5
        assert len(lexicon.against_permille) >= 5
        for token, weight in (*lexicon.for_permille.items(), *lexicon.against_permille.items()):
            assert token.isalpha() and token.islower() and 4 <= len(token) <= 24, (category, token)
            assert 1 <= weight <= 1_000, (category, token, weight)


def test_a_missing_lexicon_means_no_hits_and_not_a_crash(tmp_path: Path) -> None:
    """Section 7.6: a build without the lexicons is a worse dataset, never an exception."""
    empty = lk.load_lexicon("politics", tmp_path)
    assert empty.is_empty
    assert lk.signed_hits_permille(empty, ("the court approves the merger",)) == 0
    assert lk.load_stopwords(tmp_path) == frozenset()
    assert lk.load_paraphrases(tmp_path) == ()
    broken_dir = tmp_path / "broken"
    broken_dir.mkdir()
    with open(broken_dir / "politics.v1.json", "w", encoding="utf-8", newline="\n") as handle:
        handle.write("{not json")
    with open(broken_dir / "stopwords.v1.json", "w", encoding="utf-8", newline="\n") as handle:
        handle.write('{"stopwords": "not a list"}')
    assert lk.load_lexicon("politics", broken_dir).is_empty
    assert lk.load_stopwords(broken_dir) == frozenset()


def test_a_hit_is_signed_and_counts_every_occurrence() -> None:
    politics = lk.load_lexicon("politics")
    assert politics.for_permille["elected"] == 900
    assert politics.against_permille["recount"] == 600
    assert lk.signed_hits_permille(politics, ("the candidate is elected",)) == 900
    assert lk.signed_hits_permille(politics, ("elected, and elected again",)) == 1_800
    assert lk.signed_hits_permille(politics, ("a recount is ordered",)) == -600
    assert lk.signed_hits_permille(politics, ("elected after a recount",)) == 300
    assert lk.signed_hits_permille(politics, ("nothing of the sort happened",)) == 0


def test_the_paraphrases_file_carries_the_three_instructions_a6_asks_for() -> None:
    paraphrases = lk.load_paraphrases()
    assert len(paraphrases) == 3
    assert all(instruction.strip() for instruction in paraphrases)
    payload = json.loads((LEXICONS / "paraphrases.v1.json").read_text(encoding="utf-8"))
    assert list(payload) == ["paraphrases"]


def test_every_lexicon_file_is_utf8_with_lf_endings_and_no_carriage_return() -> None:
    for path in sorted(LEXICONS.glob("*.json")):
        raw = path.read_bytes()
        assert b"\r" not in raw, path.name
        assert raw.endswith(b"\n"), path.name
        json.loads(raw.decode("utf-8"))


# --------------------------------------------------------------------------------------------------
# Every source, against the schema it must satisfy
# --------------------------------------------------------------------------------------------------
def test_every_source_produces_items_that_validate_against_news_v1(tmp_path: Path) -> None:
    """The four fetchers write no file, so ``news.v1.json`` is the only thing that can reject their shape
    before D6 does. Every id pattern, every section slug and the ``wikipedia_asof`` revision rule is in
    there, and one bad slug would otherwise surface a wave later as a build that refuses its own data."""
    from pmx.data.schema import validate_against_schema

    handler, _ = recording_handler(fixture_text("wasof_revisions_20160620.json"))
    asof = wa.fetch_wikipedia_asof(
        client=client_for(tmp_path / "asof", handler),  # type: ignore[arg-type]
        title="United Kingdom European Union membership referendum",
        asof_day="2016-06-20",
        market_id="demo-brexit-2016",
    )
    cdx_handler, _ = recording_handler(fixture_text("cdx_reuters_20160623.json"))
    frontpages = wb.fetch_wayback(
        client=client_for(tmp_path / "wb", cdx_handler, base_url=wb.WAYBACK_BASE_URL),  # type: ignore[arg-type]
        day_start_ms=DAY_20160623,
        front_pages=("reuters.com",),
    )
    gdelt_handler, _ = recording_handler(fixture_text("gdelt_doc_20250903.json"))
    articles = gd.fetch_gdelt(
        client=client_for(  # type: ignore[arg-type]
            tmp_path / "gd",
            gdelt_handler,
            base_url=gd.GDELT_BASE_URL,
            min_interval_ms=gd.GDELT_MIN_INTERVAL_MS,
        ),
        day_start_ms=DAY_20250903,
        now_ms=DAY_20250903 + MS_PER_DAY,
    )
    headlines = parsed_2016()
    linked = lk.link_items(
        headlines,
        [
            market(
                "demo-brexit-2016",
                "Will the United Kingdom vote to leave the European Union?",
                wiki_subjects=("United Kingdom European Union membership referendum, 2016",),
            )
        ],
    )
    every = (*headlines, *linked, *asof, *frontpages, *articles)
    assert len(asof) == 1
    assert len(frontpages) == 1
    assert len(articles) > 20
    assert len(every) == 2 * 17 + 1 + 1 + len(articles)
    for item in every:
        validate_against_schema("news.v1.json", item.to_dict(), where=item.news_id)


# --------------------------------------------------------------------------------------------------
# The one live test, skipped unless asked for
# --------------------------------------------------------------------------------------------------
@pytest.mark.skipif(not os.environ.get("PMX_LIVE"), reason="PMX_LIVE is not set")
def test_live_current_events_page(tmp_path: Path) -> None:
    """Against the real API: the descriptive User-Agent is what turns a 403 into a 200 (section 7.11)."""
    from pmx.data.importers._http import HttpClient

    client = HttpClient(
        base_url=wce.WIKIPEDIA_BASE_URL,
        user_agent=build_user_agent(),
        min_interval_ms=wce.WIKIPEDIA_MIN_INTERVAL_MS,
        cache_dir=tmp_path / "cache",
    )
    try:
        items = wce.fetch_wikipedia_current_events(client=client, day_start_ms=DAY_20160623)
    finally:
        client.close()
    assert len(items) >= 10
    assert any("United Kingdom" in item.text for item in items)
