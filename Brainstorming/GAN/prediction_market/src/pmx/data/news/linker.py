"""Score a dated news item against a market, deterministically, in integers, and store the score.

Why this module exists at all: an agent that reads "the news of the time" is only honest if the link between
a headline and a market was decided by a rule a reviewer can re-run, not by a similarity model whose weights
nobody can audit and whose output moves with its version. So the linker is arithmetic (CONTRACTS_V2 section
7.6): six hundred permille for the article titles the item and the market share, four hundred for the keyword
overlap, a threshold below which nothing is linked, and the score written into the item so every link in a
dataset can be recomputed from the two texts that produced it.

It is also the one D5 module that opens no socket and reads no clock, which is why the four fetchers import
their shared vocabulary from here (the ``news.v1`` field caps, the tokeniser, the lexicon directory): the
architecture test of the plan classes this file with the engine, and a constant that lives here cannot drift
into a second spelling in a fetcher.

The lexicons under ``src/pmx/lexicons/`` are D5's other deliverable and are read here too, so their shape
stays private to this package and ``newsbayes`` (A1) never has to guess it. A missing file means no hits and
no stop words, never an exception: a dataset built without the lexicons is a worse dataset, not a crash.
"""

from __future__ import annotations

import dataclasses
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from pmx.types import (
    LINK_THRESHOLD_PERMILLE,
    SUBJECT_DERIVED,
    SUBJECT_STATED,
    Market,
    NewsItem,
    round_half_up,
)

# --------------------------------------------------------------------------------------------------
# The caps of news.v1 (CONTRACTS_V2 section 7.3) and the linker's own constants
# --------------------------------------------------------------------------------------------------
NEWS_HEADLINE_MAX = 300
NEWS_TEXT_MAX = 4_000
NEWS_URL_MAX = 1_024
WIKI_LINKS_MAX = 32
SOURCE_URLS_MAX = 16

#: The weight of the two terms of the score, in permille, and they sum to one thousand. The threshold below
#: which nothing is linked is ``pmx.types.LINK_THRESHOLD_PERMILLE`` (section 7.6), imported above.
SHARED_LINKS_WEIGHT_PERMILLE = 600
KEYWORD_WEIGHT_PERMILLE = 400

#: The keyword weight when the market carries **no** ``wiki_subjects``, which is the renormalisation of
#: the two weights above over the evidence that market actually has. Measured on the first real dataset:
#: of 400 staged Manifold markets 392 carried no subject and every Kalshi market carried none, so the
#: 600-permille term was structurally zero, no score could exceed 400, and a link needed a keyword
#: overlap of 375 permille to clear a threshold of 150. Seven thousand three hundred and ninety one
#: Wikipedia Current events items linked to nothing at all. A market with no subjects has exactly one
#: kind of evidence, so that evidence carries the whole thousand and is judged against the same
#: threshold; a market with subjects keeps the 600/400 split of section 7.6 unchanged.
KEYWORD_ONLY_WEIGHT_PERMILLE = 1_000

#: The lexicons live *inside* the package, at ``src/pmx/lexicons/``, for exactly the reason ruling R29
#: moved the five JSON schemas there (decision D-17): ``newsbayes`` (A1) reads them at run time, and a
#: path relative to the repository root does not exist in an installed wheel. ``parents[2]`` is
#: ``src/pmx`` from ``src/pmx/data/news/linker.py`` (ruling R94).
LEXICON_DIR = Path(__file__).resolve().parents[2] / "lexicons"
STOPWORDS_FILE = "stopwords.v1.json"
PARAPHRASES_FILE = "paraphrases.v1.json"

#: A token of ``K_item`` or ``K_market``: lowercase alphabetic, four characters or more (section 7.6).
TOKEN_RE = re.compile(r"[a-z]{4,}")

#: A run of capitalised words inside a question or a title, which is the only subject candidate a
#: provider that publishes no Wikipedia link leaves behind. Apostrophes, dots and hyphens are inside a
#: run ("Trump's", "U.S.", "Jean-Luc"); anything else ends it.
CAPITALISED_RUN_RE = re.compile(r"[A-Z][A-Za-z0-9'.-]*(?:\s+[A-Z][A-Za-z0-9'.-]*)*")

#: How many derived subjects one question may contribute. The ``market.v2`` cap is eight subjects in
#: total (section 7.2), and a stated subject is worth more than a derived one, so a question keeps the
#: first few runs and leaves the rest of the room to the provider's own.
DERIVED_SUBJECTS_MAX = 4

#: A derived subject shorter than this is noise ("US", "AI" survive as tokens of the keyword term and do
#: not need to be article titles).
DERIVED_SUBJECT_MIN_CHARS = 4

#: ``market.v2`` caps a market at eight subjects (section 7.2), which is where ``merge_subjects`` cuts.
WIKI_SUBJECTS_LIMIT = 8

_STOPWORDS_CACHE: dict[str, frozenset[str]] = {}
_LEXICON_CACHE: dict[str, Lexicon] = {}


# --------------------------------------------------------------------------------------------------
# Truncation: every field of news.v1 has a cap and a fetcher that overruns one loses the whole item
# --------------------------------------------------------------------------------------------------
def clip(text: str, limit: int) -> str:
    """``text`` cut to ``limit`` characters, the last three replaced by dots when the cut removed anything.

    Truncating a headline is lossy either way; an explicit ellipsis at least tells a reader that the
    provider said more, which is what the market ``description`` rule of section 7.2 does too."""
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    if limit <= 3:
        return text[:limit]
    return text[: limit - 3] + "..."


# --------------------------------------------------------------------------------------------------
# Tokenisation and the stop list
# --------------------------------------------------------------------------------------------------
def load_stopwords(directory: Path | None = None) -> frozenset[str]:
    """The stop list of ``pmx/lexicons/stopwords.v1.json``; an empty set when the file is absent."""
    root = LEXICON_DIR if directory is None else directory
    key = str(root)
    cached = _STOPWORDS_CACHE.get(key)
    if cached is not None:
        return cached
    payload = _read_json(root / STOPWORDS_FILE)
    words: frozenset[str] = frozenset()
    if isinstance(payload, dict):
        raw = payload.get("stopwords")
        if isinstance(raw, list):
            words = frozenset(word for word in raw if isinstance(word, str))
    _STOPWORDS_CACHE[key] = words
    return words


def tokens_of(texts: Iterable[str], stopwords: frozenset[str]) -> frozenset[str]:
    """``K`` of section 7.6: the lowercase alphabetic tokens of length four or more, minus the stop list."""
    found: set[str] = set()
    for text in texts:
        found.update(TOKEN_RE.findall(text.lower()))
    return frozenset(found - stopwords)


def market_tokens(market: Market, stopwords: frozenset[str]) -> frozenset[str]:
    """``K_market``: the tokens of the market's question plus its tags (section 7.6)."""
    return tokens_of((market.question, *market.tags), stopwords)


def item_tokens(item: NewsItem, stopwords: frozenset[str]) -> frozenset[str]:
    """``K_item``: the tokens of the item's headline plus its text (section 7.6)."""
    return tokens_of((item.headline, item.text), stopwords)


def derived_subjects_of(
    text: str, stopwords: frozenset[str], *, limit: int = DERIVED_SUBJECTS_MAX
) -> tuple[str, ...]:
    """Subject candidates read off a question or a title: its capitalised word runs, in order of first
    appearance, deduplicated, with stop words trimmed off both ends and stop-word-only runs dropped.

    Why this exists: the linker's dominant term compares an item's ``wiki_links`` against the market's
    ``wiki_subjects`` (section 7.6), and two of the three real providers publish no subject at all. A
    capitalised run of a real question is what a person would look up: "Will the Nasdaq-100 be above
    30000" yields ``Nasdaq-100``, which is exactly the article title a Current events item links to. It is
    a candidate and says so: every subject built this way is stored with provenance ``derived``, so a
    reviewer can tell it from one the venue itself stated, and the ``wikipedia_asof`` schedule prefers the
    stated one when a market has both.

    The result is **not** lowercased and not otherwise normalised: a subject is compared verbatim against
    an article title, where capitals are part of the name.
    """
    found: list[str] = []
    for match in CAPITALISED_RUN_RE.finditer(text):
        words = match.group(0).split()
        while words and words[0].lower().strip(".'-") in stopwords:
            words = words[1:]
        while words and words[-1].lower().strip(".'-") in stopwords:
            words = words[:-1]
        candidate = " ".join(words).strip(" ,;:-")
        # One real word is the bar: a run of initialisms ("A US AI EV") is not an article title, while
        # "Bank", "Nasdaq-100" and "Donald Trump" all carry one word long enough to be a name.
        if len(candidate) < DERIVED_SUBJECT_MIN_CHARS or not any(
            len(core) >= DERIVED_SUBJECT_MIN_CHARS and any(char.isalpha() for char in core)
            for core in (word.strip(".'-") for word in words)
        ):
            continue
        if candidate not in found:
            found.append(candidate)
        if len(found) >= limit:
            break
    return tuple(found)


def merge_subjects(
    stated: Sequence[str], derived: Sequence[str], *, limit: int = WIKI_SUBJECTS_LIMIT
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """``(wiki_subjects, wiki_subject_provenance)``: the two aligned lists of section 7.2.

    Stated subjects are taken first, so the eight-subject cap never drops one the provider published in
    favour of an alphabetically earlier guess; a title both sources offer is stated, because the stronger
    provenance wins. The result is sorted and unique, which is what the loader demands, and the
    provenance list is permuted with it so flag ``k`` still describes subject ``k``.

    It is one function rather than one per importer because "which subject wins the cap" is a rule about
    the dataset and not about a provider, and two spellings of it would drift.
    """
    provenance: dict[str, str] = {}
    for title in stated:
        if len(provenance) >= limit:
            break
        provenance.setdefault(title, SUBJECT_STATED)
    for title in derived:
        if len(provenance) >= limit:
            break
        provenance.setdefault(title, SUBJECT_DERIVED)
    ordered = sorted(provenance)
    return tuple(ordered), tuple(provenance[title] for title in ordered)


# --------------------------------------------------------------------------------------------------
# The score
# --------------------------------------------------------------------------------------------------
def link_score_permille(
    *,
    item_links: Sequence[str],
    item_keywords: frozenset[str],
    market_subjects: Iterable[str],
    market_keywords: frozenset[str],
) -> int:
    """The `match_score_permille` of section 7.6, in `[0, 1000]`.

    ``item_links`` are the item's ``wiki_links`` and ``market_subjects`` the market's ``wiki_subjects``:
    never its ``tags``, whose slug pattern forbids the spaces every real article title carries (ruling R17).

    The weights are renormalised over the evidence **the market** carries. A market with subjects is
    scored 600 for the shared article titles and 400 for the keyword overlap, exactly as section 7.6
    writes it. A market with no subject has no share to compute, so the keyword overlap carries the whole
    thousand (:data:`KEYWORD_ONLY_WEIGHT_PERMILLE`) and is judged against the same threshold: the
    alternative, kept until the first real dataset was built, was a dominant term that was structurally
    zero on every real market and a score that could never exceed 400.
    """
    links = tuple(dict.fromkeys(item_links))
    subjects = frozenset(market_subjects)
    shared_links = sum(1 for link in links if link in subjects)
    keyword_overlap = (
        round_half_up(1_000 * len(item_keywords & market_keywords), len(market_keywords))
        if market_keywords
        else 0
    )
    if not subjects:
        return (KEYWORD_ONLY_WEIGHT_PERMILLE * keyword_overlap) // 1_000
    return round_half_up(SHARED_LINKS_WEIGHT_PERMILLE * shared_links, max(1, len(links))) + (
        KEYWORD_WEIGHT_PERMILLE * keyword_overlap
    ) // 1_000


@dataclass(frozen=True, slots=True)
class MarketTerms:
    """One market as the linker sees it: an id, its subjects and its keyword set, and nothing else.

    It exists so that the two callers of the linker (``link_items`` over ``Market`` objects, and the
    builder over the JSON payloads it is about to write) reach the same arithmetic through the same door.
    A market's tape, outcome and quality are not evidence about a headline and are deliberately absent.
    """

    market_id: str
    subjects: frozenset[str]
    keywords: frozenset[str]


def market_terms_of(
    *, market_id: str, question: str, tags: Sequence[str], wiki_subjects: Sequence[str],
    stopwords: frozenset[str],
) -> MarketTerms:
    """``MarketTerms`` from the four fields section 7.6 reads off a market."""
    return MarketTerms(
        market_id=market_id,
        subjects=frozenset(wiki_subjects),
        keywords=tokens_of((question, *tags), stopwords),
    )


class LinkIndex:
    """Every market of a dataset, indexed by keyword and by subject, ready to score one item at a time.

    Why an index rather than the obvious double loop: a real dataset is eight thousand news items against
    several hundred markets, and the score of a pair that shares neither a keyword nor an article title is
    zero by construction (both terms of section 7.6 have an empty intersection in the numerator). So the
    index yields the candidate markets and :func:`link_score_permille` decides them, which is the same
    answer as scoring every pair and is what makes linking affordable inside a build.
    """

    __slots__ = ("_by_keyword", "_by_subject", "_terms")

    def __init__(self, terms: Sequence[MarketTerms]) -> None:
        self._terms = tuple(terms)
        self._by_keyword: dict[str, list[int]] = {}
        self._by_subject: dict[str, list[int]] = {}
        for index, market in enumerate(self._terms):
            for token in market.keywords:
                self._by_keyword.setdefault(token, []).append(index)
            for subject in market.subjects:
                self._by_subject.setdefault(subject, []).append(index)

    @property
    def markets(self) -> tuple[MarketTerms, ...]:
        return self._terms

    def links_for(
        self, *, item_links: Sequence[str], item_keywords: frozenset[str],
        threshold_permille: int = LINK_THRESHOLD_PERMILLE,
    ) -> tuple[tuple[str, int], ...]:
        """``(market_id, score)`` for every market this item links to, sorted by market id."""
        candidates: set[int] = set()
        for token in item_keywords:
            candidates.update(self._by_keyword.get(token, ()))
        for link in item_links:
            candidates.update(self._by_subject.get(link, ()))
        hits: list[tuple[str, int]] = []
        for index in sorted(candidates):
            market = self._terms[index]
            score = link_score_permille(
                item_links=item_links,
                item_keywords=item_keywords,
                market_subjects=market.subjects,
                market_keywords=market.keywords,
            )
            if score >= threshold_permille:
                hits.append((market.market_id, score))
        return tuple(sorted(hits))


def score_item_against_market(item: NewsItem, market: Market, stopwords: frozenset[str]) -> int:
    """``link_score_permille`` for one pair, with both token sets computed from the two objects."""
    return link_score_permille(
        item_links=tuple(item.wiki_links),
        item_keywords=item_tokens(item, stopwords),
        market_subjects=tuple(market.wiki_subjects),
        market_keywords=market_tokens(market, stopwords),
    )


def link_items(items: Sequence[NewsItem], markets: Sequence[Market]) -> tuple[NewsItem, ...]:
    """Copies of ``items`` with ``match_ids`` and ``match_scores_permille`` filled (section 7.12).

    The input is untouched, ``match_ids`` is sorted ascending by code point with its scores aligned, and a
    pair scoring below ``LINK_THRESHOLD_PERMILLE`` is not a link. Two runs over the same inputs produce the
    same lists: nothing here reads a clock, a set iteration order or a hash seed.

    A link the item already carries is **kept** (ruling R95). A Manifold comment is the one news item whose
    link is stated by the venue rather than inferred, at ``1000`` permille, and the earlier spelling
    replaced the whole list, so passing comments through the linker silently unlinked every one of them.
    Where both a stated and a scored link exist for the same market the higher score wins.
    """
    stopwords = load_stopwords()
    index = LinkIndex(
        [
            market_terms_of(
                market_id=market.id,
                question=market.question,
                tags=market.tags,
                wiki_subjects=market.wiki_subjects,
                stopwords=stopwords,
            )
            for market in markets
        ]
    )
    linked: list[NewsItem] = []
    for item in items:
        scores: dict[str, int] = dict(
            zip(item.match_ids, item.match_scores_permille, strict=True)
        )
        for market_id, score in index.links_for(
            item_links=tuple(item.wiki_links), item_keywords=item_tokens(item, stopwords)
        ):
            scores[market_id] = max(score, scores.get(market_id, 0))
        hits = sorted(scores.items())
        linked.append(
            replace_item(
                item,
                match_ids=tuple(market_id for market_id, _ in hits),
                match_scores_permille=tuple(score for _, score in hits),
            )
        )
    return tuple(linked)


# --------------------------------------------------------------------------------------------------
# The lexicons: D5 ships them, newsbayes (A1) reads them through this door
# --------------------------------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Lexicon:
    """One category's word lists. ``for_permille`` and ``against_permille`` map a token to permille of one
    ``newsbayes`` hit, so a family sums the signed permille of every match and applies
    ``(sum_signed_permille * weight_per_hit_milli) // 1_000`` to its integer logit (section 10.5)."""

    lexicon_id: str
    category: str
    for_permille: Mapping[str, int]
    against_permille: Mapping[str, int]

    @property
    def is_empty(self) -> bool:
        return not self.for_permille and not self.against_permille


def load_lexicon(category: str, directory: Path | None = None) -> Lexicon:
    """The lexicon of one category. A missing or malformed file yields an empty lexicon (section 7.6)."""
    root = LEXICON_DIR if directory is None else directory
    key = f"{root}\n{category}"
    cached = _LEXICON_CACHE.get(key)
    if cached is not None:
        return cached
    payload = _read_json(root / f"{category}.v1.json")
    lexicon = Lexicon(
        lexicon_id=f"{category}.v1",
        category=category,
        for_permille=_weights(payload, "for"),
        against_permille=_weights(payload, "against"),
    )
    _LEXICON_CACHE[key] = lexicon
    return lexicon


def signed_hits_permille(lexicon: Lexicon, texts: Iterable[str]) -> int:
    """The signed weight of every lexicon token occurring in ``texts``, in permille of one hit.

    Positive is evidence for YES, negative against. Every occurrence counts, so a headline that says
    "approves" twice weighs twice: the caller's ``weight_per_hit_milli`` is what scales the total, and
    truncating the count here would hide the difference between one mention and ten.
    """
    if lexicon.is_empty:
        return 0
    total = 0
    counts: dict[str, int] = {}
    for text in texts:
        for token in TOKEN_RE.findall(text.lower()):
            counts[token] = counts.get(token, 0) + 1
    for token in sorted(counts):
        occurrences = counts[token]
        total += occurrences * lexicon.for_permille.get(token, 0)
        total -= occurrences * lexicon.against_permille.get(token, 0)
    return total


def load_paraphrases(directory: Path | None = None) -> tuple[str, ...]:
    """The three paraphrase instructions of ``paraphrases.v1.json`` (A6's contamination prompt, 11.5)."""
    root = LEXICON_DIR if directory is None else directory
    payload = _read_json(root / PARAPHRASES_FILE)
    if isinstance(payload, dict):
        raw = payload.get("paraphrases")
        if isinstance(raw, list):
            return tuple(entry for entry in raw if isinstance(entry, str))
    return ()


# --------------------------------------------------------------------------------------------------
# Internals
# --------------------------------------------------------------------------------------------------
def replace_item(item: NewsItem, **changes: object) -> NewsItem:
    """``item`` with ``changes`` applied, as a new object, leaving the original untouched.

    ``NewsItem`` is a frozen dataclass (D1), so this is one call; it exists as a named function because
    "the input is untouched" is part of ``link_items``'s contract (section 7.12) and a named function is
    what a test can point at."""
    return dataclasses.replace(item, **cast("Any", changes))


def _read_json(path: Path) -> object:
    """The parsed file, or ``None`` when it is missing or is not JSON: D5's data files are optional."""
    try:
        with open(path, encoding="utf-8", newline="\n") as handle:
            text = handle.read()
    except OSError:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return None


def _weights(payload: object, side: str) -> Mapping[str, int]:
    if not isinstance(payload, dict):
        return {}
    entries = payload.get(side)
    if not isinstance(entries, list):
        return {}
    weights: dict[str, int] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        token = entry.get("token")
        weight = entry.get("weight_permille")
        if isinstance(token, str) and isinstance(weight, int) and not isinstance(weight, bool):
            weights[token] = weight
    return weights
